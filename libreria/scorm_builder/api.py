"""API de alto nivel del motor.

La función `build_complete_course` hace todo el ciclo:
DOCX → parser → renderer → PDFs → Aiken → SCORM ZIP, en una sola llamada.

NOVEDADES v0.2:
- Acepta `extra_resources` (lista de rutas) que se incluyen como
  carpeta `recursos/` dentro del SCORM y son referenciables por el HTML.
- Acepta `mastery_override` y `author_override`.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Iterable
from dataclasses import dataclass, field

from scorm_builder.parser import parse_docx, CourseStructure
from scorm_builder.renderer import render_html
from scorm_builder.packager import build_all_topics
from scorm_builder.themes import get_theme, make_custom_theme, Theme
from scorm_builder.aiken_builder import build_aiken_file
from scorm_builder.pdf_builder import build_pdf

logger = logging.getLogger(__name__)


@dataclass
class BuildResult:
    """Resultado de una construcción completa."""
    course: CourseStructure
    scorm_zips: List[Path] = field(default_factory=list)
    aiken_files: List[Path] = field(default_factory=list)
    pdf_files: List[Path] = field(default_factory=list)
    resource_files: List[Path] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def num_topics(self) -> int:
        return len(self.course.topics)

    @property
    def num_questions(self) -> int:
        return sum(len(t.quiz) for t in self.course.topics)


def build_scorm_from_docx(
    docx_path: str | Path,
    output: str | Path,
    theme: str = "azul",
    title_override: Optional[str] = None,
) -> Path:
    """Genera un único SCORM (el primer tema o todo si solo hay uno) en un ZIP.

    Wrapper sencillo para uso rápido. Para más control, usa `build_complete_course`.
    """
    course = parse_docx(docx_path)
    if title_override:
        course.metadata.title = title_override
    theme_obj = get_theme(theme)
    htmls = render_html(course, theme_obj)

    output = Path(output)
    if output.suffix.lower() == ".zip":
        # Solo el primer tema
        from scorm_builder.packager import build_scorm_package
        if not course.topics:
            raise ValueError("El documento no contiene ningún tema.")
        topic = course.topics[0]
        return build_scorm_package(
            topic=topic,
            html_content=htmls[topic.number],
            course_title=course.metadata.title,
            output_path=output,
            mastery=course.metadata.mastery,
        )
    else:
        # Directorio: todos los temas
        zips = build_all_topics(course, htmls, output)
        return zips[0] if zips else output


def _stage_extra_resources(
    extra_resources: Iterable[str | Path],
    target_dir: Path,
) -> List[Path]:
    """Copia los recursos adicionales (lista de archivos) en target_dir.
    Devuelve la lista de rutas resultantes."""
    target_dir.mkdir(parents=True, exist_ok=True)
    out: List[Path] = []
    for src in extra_resources or []:
        src = Path(src)
        if not src.exists() or not src.is_file():
            continue
        dest = target_dir / src.name
        counter = 1
        while dest.exists():
            stem, suf = src.stem, src.suffix
            dest = target_dir / f"{stem}_{counter}{suf}"
            counter += 1
        shutil.copy2(src, dest)
        out.append(dest)
    return out


def build_complete_course(
    docx_path: str | Path,
    output_dir: str | Path,
    theme: str | Theme = "azul",
    custom_palette: Optional[Dict[str, str]] = None,
    title_override: Optional[str] = None,
    author_override: Optional[str] = None,
    mastery_override: Optional[int] = None,
    weight_view_override: Optional[int] = None,
    weight_quiz_override: Optional[int] = None,
    view_min_seconds_override: Optional[int] = None,
    view_strategy_override: Optional[str] = None,
    generate_pdfs: bool = True,
    generate_aiken: bool = True,
    one_scorm_per_topic: bool = True,
    extra_resources: Optional[Iterable[str | Path]] = None,
    topic_title_override: Optional[str] = None,
) -> BuildResult:
    """Construye un curso completo desde un DOCX.

    Args:
        docx_path: ruta del archivo DOCX de entrada
        output_dir: directorio donde se generarán los archivos
        theme: nombre de paleta predefinida o objeto Theme custom
        custom_palette: si se pasa, sobreescribe theme con paleta personalizada
            Debe contener: primary_deep, primary, primary_bright (mínimo)
        title_override: si se pasa, sobreescribe el título del curso
        author_override: si se pasa, sobreescribe el autor del curso
        mastery_override: si se pasa, sobreescribe el % mínimo para aprobar
        weight_view_override: si se pasa, sobreescribe el peso de la visualización (0-100).
            Si solo se pasa este, weight_quiz se calcula como 100 - weight_view.
        weight_quiz_override: si se pasa, sobreescribe el peso del quiz (0-100).
        view_min_seconds_override: tiempo mínimo (segundos) por subapartado.
        view_strategy_override: 'scroll', 'time' o 'both' (estrategia para contar como visto).
        generate_pdfs: si True, genera un PDF por tema
        generate_aiken: si True, genera un .txt Aiken por tema
        one_scorm_per_topic: si True, un SCORM ZIP por tema; si False, un solo SCORM
        extra_resources: iterable de rutas a archivos adicionales (imágenes,
            vídeos, audios, PDFs...) que se incluirán en cada SCORM en la
            carpeta `recursos/` y podrán ser referenciados desde el DOCX.

    Returns:
        BuildResult con la información de lo generado
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Parsear DOCX
    logger.info(f"Parseando {docx_path}...")
    course = parse_docx(docx_path)
    if title_override:
        course.metadata.title = title_override
    if author_override:
        course.metadata.author = author_override
    if mastery_override is not None:
        try:
            course.metadata.mastery = max(0, min(100, int(mastery_override)))
        except (TypeError, ValueError):
            pass

    # Override del título de los temas (útil para modo lote: el SCORM toma
    # el nombre del fichero como título). Si hay un solo tema, lo reemplaza;
    # si hay varios, antepone el override como prefijo.
    if topic_title_override:
        if len(course.topics) == 1:
            course.topics[0].title = topic_title_override
        elif len(course.topics) > 1:
            for t in course.topics:
                t.title = f"{topic_title_override} · {t.title}"

    # Sistema de puntuación ponderada: aplicar overrides
    if weight_view_override is not None or weight_quiz_override is not None:
        try:
            wv = int(weight_view_override) if weight_view_override is not None else None
            wq = int(weight_quiz_override) if weight_quiz_override is not None else None
            if wv is not None and wq is None:
                wv = max(0, min(100, wv))
                course.metadata.weight_view = wv
                course.metadata.weight_quiz = 100 - wv
            elif wq is not None and wv is None:
                wq = max(0, min(100, wq))
                course.metadata.weight_quiz = wq
                course.metadata.weight_view = 100 - wq
            else:
                course.metadata.weight_view = max(0, min(100, wv))
                course.metadata.weight_quiz = max(0, min(100, wq))
            # Renormalizar (por si la suma no es 100)
            from scorm_builder.parser import _normalize_weights
            _normalize_weights(course)
        except (TypeError, ValueError):
            pass
    if view_min_seconds_override is not None:
        try:
            course.metadata.view_min_seconds = max(0, int(view_min_seconds_override))
        except (TypeError, ValueError):
            pass
    if view_strategy_override is not None:
        v = str(view_strategy_override).lower().strip()
        if v in ("scroll", "time", "both"):
            course.metadata.view_strategy = v

    # 2. Resolver tema
    if custom_palette:
        theme_obj = make_custom_theme(**custom_palette)
    elif isinstance(theme, Theme):
        theme_obj = theme
    else:
        # Si la paleta del documento es válida, prevalece sobre el parámetro por defecto
        from scorm_builder.themes import THEMES
        palette_doc = course.metadata.palette
        if palette_doc in THEMES:
            theme_obj = get_theme(palette_doc)
        else:
            theme_obj = get_theme(theme)

    # 3. Renderizar HTMLs
    logger.info(f"Renderizando {len(course.topics)} temas con paleta '{theme_obj.name}'...")
    htmls = render_html(course, theme_obj)

    # 4. Generar PDFs
    pdf_files: List[Path] = []
    descargas_dir = None
    if generate_pdfs and course.topics:
        logger.info("Generando PDFs descargables...")
        descargas_dir = output_dir / "_descargas_temp"
        descargas_dir.mkdir(exist_ok=True)
        for topic in course.topics:
            try:
                pdf_name = f"apuntes_T{topic.number:02d}.pdf"
                pdf_path = descargas_dir / pdf_name
                build_pdf(topic, course, theme_obj, pdf_path)
                pdf_files.append(pdf_path)
            except Exception as e:
                logger.warning(f"No se pudo generar PDF del tema {topic.number}: {e}")
                course.warnings.append(
                    f"No se pudo generar el PDF del tema {topic.number}: {e}"
                )

    # 5. Generar Aiken
    aiken_files: List[Path] = []
    if generate_aiken and course.topics:
        logger.info("Generando bancos Aiken...")
        aiken_dir = output_dir / "aiken"
        aiken_files = build_aiken_file(course, aiken_dir, one_per_topic=True)

    # 6. Preparar carpeta de recursos extra (multimedia, PDFs adicionales, etc.)
    recursos_dir: Optional[Path] = None
    staged_resources: List[Path] = []
    if extra_resources:
        recursos_dir = output_dir / "_recursos_temp"
        staged_resources = _stage_extra_resources(extra_resources, recursos_dir)
        logger.info(f"Incluidos {len(staged_resources)} recursos adicionales.")

    # 7. Empaquetar SCORM
    logger.info("Empaquetando SCORMs...")
    scorm_dir = output_dir / "scorm"
    scorm_zips = build_all_topics(
        course, htmls, scorm_dir,
        descargas_dir=descargas_dir,
        recursos_dir=recursos_dir,
    )

    # 8. Mover los PDFs a un sitio limpio (fuera del temporal)
    final_pdfs: List[Path] = []
    if generate_pdfs and pdf_files:
        final_pdf_dir = output_dir / "pdfs"
        final_pdf_dir.mkdir(exist_ok=True)
        for pdf in pdf_files:
            target = final_pdf_dir / pdf.name
            if pdf.exists():
                pdf.rename(target)
                final_pdfs.append(target)
        # Borrar carpeta temporal de descargas
        if descargas_dir and descargas_dir.exists():
            shutil.rmtree(descargas_dir, ignore_errors=True)

    # 9. Mover los recursos extra a una carpeta visible
    final_resources: List[Path] = []
    if staged_resources:
        final_res_dir = output_dir / "recursos"
        final_res_dir.mkdir(exist_ok=True)
        for r in staged_resources:
            target = final_res_dir / r.name
            if r.exists():
                shutil.move(str(r), str(target))
                final_resources.append(target)
        if recursos_dir and recursos_dir.exists():
            shutil.rmtree(recursos_dir, ignore_errors=True)

    return BuildResult(
        course=course,
        scorm_zips=scorm_zips,
        aiken_files=aiken_files,
        pdf_files=final_pdfs,
        resource_files=final_resources,
        warnings=course.warnings,
    )


def rebuild_from_structure(
    course: CourseStructure,
    output_dir: str | Path,
    theme: str | Theme = "azul",
    custom_palette: Optional[Dict[str, str]] = None,
    recursos_dir: Optional[str | Path] = None,
    generate_pdfs: bool = False,
    generate_aiken: bool = False,
) -> BuildResult:
    """Re-empaqueta un curso a partir de una CourseStructure ya editada.

    Útil para la edición desde la app: el usuario carga la estructura JSON
    persistida, modifica algún texto/pregunta/metadato, y se vuelve a generar
    el SCORM sin necesidad de partir del DOCX.

    Args:
        course: estructura ya parseada y posiblemente modificada
        output_dir: dónde escribir los SCORM
        theme: paleta predefinida o objeto Theme
        custom_palette: paleta custom si se quiere
        recursos_dir: carpeta con los recursos extra ya copiados (no se vuelven a copiar)
        generate_pdfs: regenerar PDFs
        generate_aiken: regenerar Aiken
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Renormalizar pesos por si el usuario los tocó
    from scorm_builder.parser import _normalize_weights
    _normalize_weights(course)

    # Resolver tema
    if custom_palette:
        theme_obj = make_custom_theme(**custom_palette)
    elif isinstance(theme, Theme):
        theme_obj = theme
    else:
        from scorm_builder.themes import THEMES
        palette_doc = course.metadata.palette
        if palette_doc in THEMES:
            theme_obj = get_theme(palette_doc)
        else:
            theme_obj = get_theme(theme)

    htmls = render_html(course, theme_obj)

    pdf_files = []
    if generate_pdfs:
        pdf_dir = output_dir / "pdfs"
        pdf_dir.mkdir(exist_ok=True)
        for topic in course.topics:
            try:
                pdf_path = pdf_dir / f"apuntes_T{topic.number:02d}.pdf"
                build_pdf(topic, course, theme_obj, pdf_path)
                pdf_files.append(pdf_path)
            except Exception as e:
                logger.warning(f"PDF tema {topic.number} falló: {e}")

    aiken_files = []
    if generate_aiken:
        aiken_dir = output_dir / "aiken"
        aiken_files = build_aiken_file(course, aiken_dir, one_per_topic=True)

    scorm_dir = output_dir / "scorm"
    scorm_zips = build_all_topics(
        course, htmls, scorm_dir,
        descargas_dir=None,  # los PDFs no se incluyen en el SCORM en re-empaque
        recursos_dir=recursos_dir,
    )

    return BuildResult(
        course=course,
        scorm_zips=scorm_zips,
        aiken_files=aiken_files,
        pdf_files=pdf_files,
        resource_files=[],
        warnings=course.warnings,
    )


def course_from_dict(data: dict) -> CourseStructure:
    """Reconstruye una CourseStructure a partir de un dict (deserializa to_dict)."""
    from scorm_builder.parser import (
        CourseStructure, CourseMetadata, Topic, Subsection, Block, BlockType, Question
    )
    md_data = data.get("metadata", {})
    metadata = CourseMetadata(
        title=md_data.get("title", "Curso sin título"),
        subtitle=md_data.get("subtitle", ""),
        author=md_data.get("author", ""),
        sector=md_data.get("sector", ""),
        palette=md_data.get("palette", "azul"),
        mastery=int(md_data.get("mastery", 70)),
        weight_view=int(md_data.get("weight_view", 40)),
        weight_quiz=int(md_data.get("weight_quiz", 60)),
        view_min_seconds=int(md_data.get("view_min_seconds", 10)),
        view_strategy=md_data.get("view_strategy", "both"),
    )
    course = CourseStructure(metadata=metadata)
    for t_data in data.get("topics", []):
        topic = Topic(
            number=int(t_data.get("number", 1)),
            title=t_data.get("title", ""),
            intro=t_data.get("intro"),
        )
        for s_data in t_data.get("subsections", []):
            sub = Subsection(
                id=s_data.get("id", ""),
                number=s_data.get("number", ""),
                title=s_data.get("title", ""),
            )
            for b_data in s_data.get("blocks", []):
                bt_str = b_data.get("type", "paragraph")
                try:
                    bt = BlockType(bt_str)
                except ValueError:
                    bt = BlockType.PARAGRAPH
                sub.blocks.append(Block(
                    type=bt,
                    text=b_data.get("text", ""),
                    items=list(b_data.get("items", [])),
                    rows=[list(r) for r in b_data.get("rows", [])],
                    extras=dict(b_data.get("extras", {})),
                ))
            topic.subsections.append(sub)
        for q_data in t_data.get("quiz", []):
            topic.quiz.append(Question(
                text=q_data.get("text", ""),
                options=list(q_data.get("options", [])),
                correct_index=int(q_data.get("correct_index", 0)),
                explanation=q_data.get("explanation"),
            ))
        course.topics.append(topic)
    course.warnings = list(data.get("warnings", []))
    return course

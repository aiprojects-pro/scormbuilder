"""Packager: empaqueta un tema en un SCORM 1.2 válido (ZIP).

NOVEDADES v0.2:
- Soporte para una carpeta `recursos/` con cualquier archivo (imágenes,
  vídeos, audios, PDFs, etc.) que el HTML pueda referenciar.
- El manifiesto SCORM declara automáticamente todos los archivos copiados.
"""
from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path
from typing import Optional, List, Iterable

from scorm_builder.parser import CourseStructure, Topic


MANIFEST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="{identifier}" version="1.0"
  xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2"
  xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2"
  xmlns:imsmd="http://www.imsglobal.org/xsd/imsmd_rootv1p2p1"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.imsproject.org/xsd/imscp_rootv1p1p2 imscp_rootv1p1p2.xsd
                      http://www.imsglobal.org/xsd/imsmd_rootv1p2p1 imsmd_rootv1p2p1.xsd
                      http://www.adlnet.org/xsd/adlcp_rootv1p2 adlcp_rootv1p2.xsd">

  <metadata>
    <schema>ADL SCORM</schema>
    <schemaversion>1.2</schemaversion>
    <imsmd:lom>
      <imsmd:general>
        <imsmd:identifier>{identifier}</imsmd:identifier>
        <imsmd:title>
          <imsmd:langstring xml:lang="es">{title}</imsmd:langstring>
        </imsmd:title>
        <imsmd:description>
          <imsmd:langstring xml:lang="es">{description}</imsmd:langstring>
        </imsmd:description>
        <imsmd:language>es</imsmd:language>
{keywords}      </imsmd:general>
    </imsmd:lom>
  </metadata>

  <organizations default="ORG-{identifier}">
    <organization identifier="ORG-{identifier}">
      <title>{title}</title>
      <item identifier="ITEM-{identifier}" identifierref="RES-{identifier}" isvisible="true">
        <title>{title}</title>
        <adlcp:masteryscore>{mastery}</adlcp:masteryscore>
      </item>
    </organization>
  </organizations>

  <resources>
    <resource identifier="RES-{identifier}" type="webcontent" adlcp:scormtype="sco" href="index.html">
      <file href="index.html"/>
{resource_files}
    </resource>
  </resources>
</manifest>
"""


def _slugify_id(text: str) -> str:
    """Convierte texto en un identificador ASCII seguro para SCORM."""
    text = re.sub(r"[^a-zA-Z0-9_]+", "_", text)
    text = text.strip("_").upper()
    return text or "SCORM"


def _xml_escape(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _copy_resources(
    src_dirs: Iterable[Path],
    target: Path,
) -> List[str]:
    """Copia los archivos de varias carpetas dentro de `target` y devuelve
    sus rutas relativas (para declararlas en el manifiesto)."""
    relative_paths: List[str] = []
    target.mkdir(parents=True, exist_ok=True)
    for src in src_dirs:
        if not src or not Path(src).exists():
            continue
        for f in Path(src).iterdir():
            if f.is_file():
                dest = target / f.name
                # Evitar pisar archivos del mismo nombre: añadimos sufijo numérico
                counter = 1
                while dest.exists():
                    stem, suf = f.stem, f.suffix
                    dest = target / f"{stem}_{counter}{suf}"
                    counter += 1
                shutil.copy2(f, dest)
                relative_paths.append(str(dest.relative_to(target.parent)).replace("\\", "/"))
    return relative_paths


def build_scorm_package(
    topic: Topic,
    html_content: str,
    course_title: str,
    output_path: Path,
    descargas_dir: Optional[Path] = None,
    recursos_dir: Optional[Path] = None,
    mastery: int = 70,
) -> Path:
    """Empaqueta un tema en un SCORM ZIP válido.

    Args:
        topic: el tema a empaquetar
        html_content: el HTML ya renderizado del tema
        course_title: título del curso completo (para metadata)
        output_path: ruta del ZIP de salida
        descargas_dir: directorio con los PDFs descargables (opcional)
        recursos_dir: directorio con recursos multimedia adicionales
            (imágenes, vídeos, audios, etc. que el HTML referencia)
        mastery: puntuación mínima (0-100) para considerar superado

    Returns:
        ruta del ZIP creado
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Identificador SCORM seguro
    identifier = _slugify_id(f"T{topic.number}_{topic.title}")[:60]

    # Construir el directorio temporal del SCORM
    work_dir = output_path.parent / f"_{output_path.stem}_build"
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)

    # 1. index.html
    (work_dir / "index.html").write_text(html_content, encoding="utf-8")

    # 2. Carpeta unificada `recursos/` (PDFs apuntes + multimedia subidos)
    resource_files_xml: List[str] = []
    target_resources = work_dir / "recursos"
    rel_paths = _copy_resources(
        [d for d in (descargas_dir, recursos_dir) if d],
        target_resources,
    )
    for rel in rel_paths:
        resource_files_xml.append(f'      <file href="{_xml_escape(rel)}"/>')

    # 3. Manifest (v0.5 Fase 2: incluye keywords del topic.tags)
    keywords_xml = ""
    tags = getattr(topic, "tags", None) or []
    if tags:
        kw_lines = []
        for tag in tags:
            kw_lines.append("        <imsmd:keyword>")
            kw_lines.append(
                f'          <imsmd:langstring xml:lang="es">{_xml_escape(tag)}</imsmd:langstring>'
            )
            kw_lines.append("        </imsmd:keyword>")
        keywords_xml = "\n".join(kw_lines) + "\n"

    manifest = MANIFEST_TEMPLATE.format(
        identifier=identifier,
        title=_xml_escape(topic.title),
        description=_xml_escape(f"Tema {topic.number} del curso '{course_title}'."),
        mastery=mastery,
        keywords=keywords_xml,
        resource_files="\n".join(resource_files_xml),
    )
    (work_dir / "imsmanifest.xml").write_text(manifest, encoding="utf-8")

    # 4. Empaquetar en ZIP
    if output_path.exists():
        output_path.unlink()
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in work_dir.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(work_dir)
                zf.write(file_path, arcname=str(arcname))

    # 5. Limpiar el directorio de trabajo
    shutil.rmtree(work_dir)

    return output_path


def build_all_topics(
    course: CourseStructure,
    htmls: dict,
    output_dir: Path,
    descargas_dir: Optional[Path] = None,
    recursos_dir: Optional[Path] = None,
) -> List[Path]:
    """Empaqueta todos los temas como SCORM independientes.

    Returns:
        lista de rutas de los ZIP generados
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    zips = []
    course_slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", course.metadata.title.lower())[:40]

    for topic in course.topics:
        topic_slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", topic.title.lower())[:40]
        zip_name = f"{course_slug}_T{topic.number:02d}_{topic_slug}_scorm.zip"
        zip_path = output_dir / zip_name

        html_content = htmls.get(topic.number)
        if not html_content:
            continue

        build_scorm_package(
            topic=topic,
            html_content=html_content,
            course_title=course.metadata.title,
            output_path=zip_path,
            descargas_dir=descargas_dir,
            recursos_dir=recursos_dir,
            mastery=course.metadata.mastery,
        )
        zips.append(zip_path)

    return zips

"""Generador de banco de preguntas en formato Aiken.

Aiken es un formato simple, soportado por Moodle, Canvas y otros LMS:

    1. Pregunta enunciada
    A. Opción A
    B. Opción B
    C. Opción C
    D. Opción D
    ANSWER: B

Las explicaciones no son parte del estándar Aiken puro, pero se incluyen
como comentarios "//" antes del bloque para que el formador las vea.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from scorm_builder.parser import CourseStructure, Topic


def _aiken_safe_line(text: str) -> str:
    """Aplana un texto a una sola línea, válida en formato Aiken.

    Aiken es line-based: cualquier `\\n` dentro de un enunciado u opción
    rompe el parser del LMS. También normalizamos espacios consecutivos.
    """
    if not text:
        return ""
    # Reemplazar todos los whitespace (incluido \n, \r, \t) por un único espacio.
    return " ".join(str(text).split())


def _option_letter(idx: int) -> str:
    """Letra de opción Aiken. Aiken solo admite A-Z (26 opciones máximo).
    Por encima de 26 se cae a 'Z' (el caller debería evitar quizes así, pero
    no queremos generar caracteres no-ASCII como `[` o `_`)."""
    if idx < 0:
        idx = 0
    if idx > 25:
        idx = 25
    return chr(ord("A") + idx)


# Reglas duras del banco Aiken (importable a Moodle):
#   - 4 opciones EXACTAS por pregunta. Las V/F y huecos NO entran.
#   - Mínimo 10 preguntas válidas por tema para considerar útil el banco.
AIKEN_OPTIONS_REQUIRED = 4
AIKEN_MIN_QUESTIONS_PER_TOPIC = 10


def _aiken_block(topic: Topic, course_title: str, course_mastery: int) -> str:
    """Genera el bloque Aiken de un tema en formato ESTRICTO Moodle.

    REGLAS APLICADAS:
      - Solo preguntas con EXACTAMENTE 4 opciones. Las que tengan otra
        cantidad (V/F con 2, huecos con 1, etc.) se filtran silenciosamente.
      - Cabecero `// ===...` eliminado (Moodle nuevo rechaza líneas-comentario
        antes de la primera pregunta).
      - v0.8.4: ELIMINADO `COMMENT:` con la explicación. Aiken estándar NO
        soporta retroalimentación: Moodle rechaza ficheros con COMMENT:.
        Si quieres feedback, usa formato GIFT (`build_gift_file`).
    """
    lines = []
    for q in topic.quiz:
        if not q.options or len(q.options) != AIKEN_OPTIONS_REQUIRED:
            # Filtrar V/F (2 opciones), huecos (1) o cualquier otra que no
            # encaje en el banco Aiken para Moodle.
            continue
        opts = list(q.options)
        ci = q.correct_index
        if not (0 <= ci < len(opts)):
            ci = 0
        lines.append(_aiken_safe_line(q.text))
        for idx, opt in enumerate(opts):
            lines.append(f"{_option_letter(idx)}. {_aiken_safe_line(opt)}")
        lines.append(f"ANSWER: {_option_letter(ci)}")
        lines.append("")

    return "\n".join(lines)


# ============================================================
# FORMATO GIFT (alternativa a Aiken CON retroalimentación)
# ============================================================
# GIFT es el formato nativo de Moodle para banco de preguntas con feedback.
# Estructura:
#     ::Título opcional:: Enunciado de la pregunta {
#     =Respuesta correcta #Feedback al acertar
#     ~Respuesta incorrecta 1 #Feedback al fallar 1
#     ~Respuesta incorrecta 2 #Feedback al fallar 2
#     ~Respuesta incorrecta 3 #Feedback al fallar 3
#     ####Feedback global de la pregunta (explicación general)
#     }
#
# Lo que el formato Aiken no soporta lo gestiona GIFT de forma nativa.

_GIFT_ESCAPE_CHARS = {"~": r"\~", "=": r"\=", "#": r"\#", "{": r"\{",
                      "}": r"\}", ":": r"\:"}

def _gift_safe(text: str) -> str:
    """Escapa los caracteres especiales de GIFT. Mantiene saltos de línea
    como `\\n` literales tal y como Moodle GIFT espera dentro de respuestas
    multilínea."""
    if not text:
        return ""
    s = " ".join(str(text).split())  # colapsar whitespace
    for ch, esc in _GIFT_ESCAPE_CHARS.items():
        s = s.replace(ch, esc)
    return s


def _gift_block(topic: Topic, course_title: str) -> str:
    """Genera el bloque GIFT de un tema. v0.8.4.

    A diferencia de Aiken:
      - Sí lleva retroalimentación (feedback) por respuesta + global.
      - Acepta cualquier número de opciones (no solo 4).
      - Se importa en Moodle desde Banco de preguntas → Importar → GIFT.
    """
    lines = []
    for q_idx, q in enumerate(topic.quiz):
        if not q.options or len(q.options) < 2:
            continue
        opts = list(q.options)
        ci = q.correct_index
        if not (0 <= ci < len(opts)):
            ci = 0
        # Título opcional: T{topic.number}-Q{idx+1}
        title = f"T{topic.number:02d}-Q{q_idx+1}"
        lines.append(f"::{_gift_safe(title)}:: {_gift_safe(q.text)} {{")
        for idx, opt in enumerate(opts):
            prefix = "=" if idx == ci else "~"
            opt_safe = _gift_safe(opt)
            if idx == ci:
                # Feedback positivo para la correcta
                lines.append(f"\t{prefix}{opt_safe} #Correcto")
            else:
                lines.append(f"\t{prefix}{opt_safe} #Incorrecto")
        # Retroalimentación global (la explicación de la pregunta)
        if q.explanation:
            lines.append(f"\t####{_gift_safe(q.explanation)}")
        lines.append("}")
        lines.append("")
    return "\n".join(lines)


def build_gift_file(
    course: CourseStructure,
    output_path: Path,
    one_per_topic: bool = True,
) -> List[Path]:
    """Genera ficheros GIFT (.txt) a partir del curso, CON retroalimentación.

    GIFT es el formato preferido de Moodle cuando necesitas feedback por
    pregunta (Aiken no lo soporta). Se importa en Moodle desde:
        Banco de preguntas → Importar → Formato: GIFT

    Args y returns idénticos a `build_aiken_file`.
    """
    output_path = Path(output_path)
    generated = []

    if one_per_topic:
        output_path.mkdir(parents=True, exist_ok=True)
        for topic in course.topics:
            if not topic.quiz:
                continue
            n_valid = sum(1 for q in topic.quiz
                          if q.text and q.options and len(q.options) >= 2
                          and 0 <= q.correct_index < len(q.options))
            if n_valid < 5:  # umbral más bajo que Aiken porque GIFT acepta más
                continue
            content = _gift_block(topic, course.metadata.title)
            fname = output_path / f"gift_T{topic.number:02d}.txt"
            fname.write_text(content, encoding="utf-8")
            generated.append(fname)
    else:
        if output_path.suffix == "":
            output_path = output_path / "gift_completo.txt"
        else:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        contents = []
        for topic in course.topics:
            if not topic.quiz:
                continue
            contents.append(_gift_block(topic, course.metadata.title))
        if contents:
            output_path.write_text("\n\n".join(contents), encoding="utf-8")
            generated.append(output_path)

    return generated


def _count_aiken_valid_questions(topic: Topic) -> int:
    """Cuenta cuántas preguntas del tema sirven para el banco Aiken
    (4 opciones exactas, índice válido, texto no vacío)."""
    n = 0
    for q in topic.quiz:
        if not q.text or not q.text.strip():
            continue
        if not q.options or len(q.options) != AIKEN_OPTIONS_REQUIRED:
            continue
        if not (0 <= q.correct_index < len(q.options)):
            continue
        n += 1
    return n


def build_aiken_file(
    course: CourseStructure,
    output_path: Path,
    one_per_topic: bool = True,
) -> List[Path]:
    """Genera ficheros Aiken (.txt) a partir del curso.

    Args:
        course: estructura del curso
        output_path: ruta del archivo o directorio
            Si one_per_topic=True, se trata como directorio.
            Si one_per_topic=False, se genera un único fichero con todas las preguntas.
        one_per_topic: si True, un fichero por tema; si False, todo junto

    Returns:
        lista de ficheros generados
    """
    output_path = Path(output_path)
    generated = []

    # v0.7.2: solo escribimos el .txt si el tema tiene al menos
    # AIKEN_MIN_QUESTIONS_PER_TOPIC preguntas válidas (4 opciones).
    # Si no, el banco no es útil para evaluación y mejor avisar.
    if one_per_topic:
        output_path.mkdir(parents=True, exist_ok=True)
        for topic in course.topics:
            if not topic.quiz:
                continue
            n_valid = _count_aiken_valid_questions(topic)
            if n_valid < AIKEN_MIN_QUESTIONS_PER_TOPIC:
                course.warnings.append(
                    f"Banco Aiken omitido para tema {topic.number} "
                    f"'{topic.title}': solo {n_valid} preguntas válidas "
                    f"(4 opciones); mínimo requerido: "
                    f"{AIKEN_MIN_QUESTIONS_PER_TOPIC}. "
                    "Añade más preguntas tipo test o ejecuta '📚 Banco Aiken "
                    "(30 preg/tema)' desde el editor para completar."
                )
                continue
            content = _aiken_block(topic, course.metadata.title, course.metadata.mastery)
            fname = output_path / f"aiken_T{topic.number:02d}.txt"
            fname.write_text(content, encoding="utf-8")
            generated.append(fname)
    else:
        # Todo en un solo fichero — combinamos solo los temas con suficientes
        if output_path.suffix == "":
            output_path = output_path / "aiken_completo.txt"
        else:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        contents = []
        skipped = []
        for topic in course.topics:
            if not topic.quiz:
                continue
            if _count_aiken_valid_questions(topic) < AIKEN_MIN_QUESTIONS_PER_TOPIC:
                skipped.append(topic.number)
                continue
            contents.append(_aiken_block(topic, course.metadata.title, course.metadata.mastery))
        if skipped:
            course.warnings.append(
                f"Banco Aiken combinado: temas {skipped} omitidos por tener "
                f"menos de {AIKEN_MIN_QUESTIONS_PER_TOPIC} preguntas válidas."
            )
        if contents:
            output_path.write_text("\n\n".join(contents), encoding="utf-8")
            generated.append(output_path)

    return generated


# ============================================================
# BANCO AIKEN EXTENDIDO CON IA (v0.5 Fase 2)
# Genera 30-50 preguntas adicionales por tema usando Claude, para que el
# formador tenga un banco amplio que importar en Moodle como cuestionario
# separado (independiente del quiz embebido en el SCORM).
# ============================================================

def build_extended_aiken(
    course: CourseStructure,
    output_dir: Path,
    n_questions_per_topic: int = 30,
    complexity: str = "mixto",
    n_options: int = 4,
    use_batch: Optional[bool] = None,
) -> List[Path]:
    """Genera un .txt Aiken por tema con N preguntas adicionales generadas por IA.

    Requiere ANTHROPIC_API_KEY. Si no está disponible, devuelve lista vacía
    sin error.

    Args:
        course: estructura del curso
        output_dir: directorio donde se generarán los .txt
        n_questions_per_topic: número objetivo de preguntas por tema
        complexity: "basico" | "intermedio" | "avanzado" | "mixto" — ajusta
            la distribución de tipos de pregunta según Bloom. Pasado a
            generate_extended_aiken.
        n_options: nº de opciones (respuestas) por pregunta. Default 4.
            v0.8.3 — configurable a petición del cliente.
        use_batch: v0.8.6 — usar Batch API (50% descuento). Si None, se
            decide automáticamente: batch si ≥3 temas (donde el ahorro
            compensa la mayor latencia), síncrono si <3 temas (usuario
            probablemente iterando y quiere feedback rápido).

    Returns:
        lista de ficheros generados (uno por tema si la IA respondió)
    """
    from scorm_builder.ai_assist import (
        is_available, generate_extended_aiken, generate_extended_aiken_batch,
    )

    if not is_available():
        return []

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    generated: List[Path] = []

    # v0.8.6: decidir batch vs síncrono
    if use_batch is None:
        use_batch = len(course.topics) >= 3

    def _questions_to_lines(questions):
        lines = []
        for q in questions:
            opts = list(q.get("options", []))[:26]
            if not opts:
                continue
            ci = q.get("correct_index", 0)
            try:
                ci = int(ci)
            except (TypeError, ValueError):
                ci = 0
            if not (0 <= ci < len(opts)):
                ci = 0
            lines.append(_aiken_safe_line(q.get("text", "")))
            for idx, opt in enumerate(opts):
                lines.append(f"{_option_letter(idx)}. {_aiken_safe_line(opt)}")
            lines.append(f"ANSWER: {_option_letter(ci)}")
            # v0.8.4: SIN `COMMENT:` (Aiken estándar Moodle no lo acepta).
            lines.append("")
        return lines

    if use_batch:
        # v0.8.6: Batch API — 50% descuento. Latencia: minutos.
        batch_results = generate_extended_aiken_batch(
            list(course.topics),
            n_questions=n_questions_per_topic,
            complexity=complexity,
            n_options=n_options,
        )
        for topic in course.topics:
            questions = batch_results.get(topic.number)
            if not questions:
                continue
            lines = _questions_to_lines(questions)
            fname = output_dir / f"aiken_T{topic.number:02d}_extendido.txt"
            fname.write_text("\n".join(lines), encoding="utf-8")
            generated.append(fname)
    else:
        # Modo síncrono (para 1-2 temas o si el batch falla).
        for topic in course.topics:
            questions = generate_extended_aiken(
                topic,
                n_questions=n_questions_per_topic,
                complexity=complexity,
                n_options=n_options,
            )
            if not questions:
                continue
            lines = _questions_to_lines(questions)
            fname = output_dir / f"aiken_T{topic.number:02d}_extendido.txt"
            fname.write_text("\n".join(lines), encoding="utf-8")
            generated.append(fname)

    return generated


def build_extended_gift(
    course: CourseStructure,
    output_dir: Path,
    n_questions_per_topic: int = 30,
    complexity: str = "mixto",
    n_options: int = 4,
) -> List[Path]:
    """v0.8.4: variante GIFT del banco extendido. Mismo IA, formato distinto.

    GIFT (Moodle native) sí soporta retroalimentación → cuando el formador
    quiere feedback al alumno usa este, no Aiken.
    """
    from scorm_builder.ai_assist import is_available, generate_extended_aiken

    if not is_available():
        return []

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    generated: List[Path] = []

    for topic in course.topics:
        questions = generate_extended_aiken(
            topic,
            n_questions=n_questions_per_topic,
            complexity=complexity,
            n_options=n_options,
        )
        if not questions:
            continue

        lines = []
        for q_idx, q in enumerate(questions):
            opts = list(q.get("options", []))
            if not opts or len(opts) < 2:
                continue
            ci = q.get("correct_index", 0)
            try:
                ci = int(ci)
            except (TypeError, ValueError):
                ci = 0
            if not (0 <= ci < len(opts)):
                ci = 0
            text = q.get("text", "")
            title = f"T{topic.number:02d}-Q{q_idx+1}"
            lines.append(f"::{_gift_safe(title)}:: {_gift_safe(text)} {{")
            for idx, opt in enumerate(opts):
                prefix = "=" if idx == ci else "~"
                opt_safe = _gift_safe(opt)
                fb = "Correcto" if idx == ci else "Incorrecto"
                lines.append(f"\t{prefix}{opt_safe} #{fb}")
            if q.get("explanation"):
                lines.append(f"\t####{_gift_safe(q['explanation'])}")
            lines.append("}")
            lines.append("")

        fname = output_dir / f"gift_T{topic.number:02d}_extendido.txt"
        fname.write_text("\n".join(lines), encoding="utf-8")
        generated.append(fname)

    return generated

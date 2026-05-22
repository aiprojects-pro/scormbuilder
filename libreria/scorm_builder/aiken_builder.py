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
from typing import List

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

    REGLAS APLICADAS (v0.7.2):
      - Solo preguntas con EXACTAMENTE 4 opciones. Las que tengan otra
        cantidad (V/F con 2, huecos con 1, etc.) se filtran silenciosamente.
        Aiken-Moodle no las acepta de forma fiable y el usuario las quiere
        homogéneas.
      - Cabecero `// ===...` eliminado (Moodle nuevo rechaza líneas-comentario
        antes de la primera pregunta).
      - Explicación va como `COMMENT:` oficial Aiken+Moodle (no `// Expl…`).
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
        if q.explanation:
            lines.append(f"COMMENT: {_aiken_safe_line(q.explanation)}")
        lines.append("")

    return "\n".join(lines)


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

    Returns:
        lista de ficheros generados (uno por tema si la IA respondió)
    """
    from scorm_builder.ai_assist import is_available, generate_extended_aiken

    if not is_available():
        return []

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    generated: List[Path] = []

    # v0.7.1: formato Aiken estricto (sin cabecero `// ===`). El archivo
    # generado se importa directamente en Moodle desde Banco de preguntas →
    # Importar → Formato Aiken.
    for topic in course.topics:
        questions = generate_extended_aiken(
            topic,
            n_questions=n_questions_per_topic,
            complexity=complexity,
        )
        if not questions:
            continue

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
            if q.get("explanation"):
                lines.append(f"COMMENT: {_aiken_safe_line(q['explanation'])}")
            lines.append("")

        fname = output_dir / f"aiken_T{topic.number:02d}_extendido.txt"
        fname.write_text("\n".join(lines), encoding="utf-8")
        generated.append(fname)

    return generated

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


def _aiken_block(topic: Topic, course_title: str, course_mastery: int) -> str:
    """Genera el bloque Aiken de un tema."""
    lines = []
    lines.append("// =====================================================================")
    lines.append(f"// Curso: {course_title}")
    lines.append(f"// Tema {topic.number}: {topic.title}")
    lines.append(f"// Total preguntas: {len(topic.quiz)}")
    lines.append(f"// Aprobado mínimo: {course_mastery}%")
    lines.append("// Codificación: UTF-8")
    lines.append("// =====================================================================")
    lines.append("")

    for q in topic.quiz:
        if not q.options:
            continue
        # Aiken solo admite hasta 26 opciones (A-Z). Truncamos por seguridad.
        opts = list(q.options)[:26]
        # correct_index puede venir fuera de rango por datos manipulados;
        # lo saturamos al rango válido para no generar letras inválidas.
        ci = q.correct_index
        if not (0 <= ci < len(opts)):
            ci = 0
        lines.append(_aiken_safe_line(q.text))
        for idx, opt in enumerate(opts):
            lines.append(f"{_option_letter(idx)}. {_aiken_safe_line(opt)}")
        lines.append(f"ANSWER: {_option_letter(ci)}")
        if q.explanation:
            lines.append(f"// Explicación: {_aiken_safe_line(q.explanation)}")
        lines.append("")

    return "\n".join(lines)


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

    if one_per_topic:
        output_path.mkdir(parents=True, exist_ok=True)
        for topic in course.topics:
            if not topic.quiz:
                continue
            content = _aiken_block(topic, course.metadata.title, course.metadata.mastery)
            fname = output_path / f"aiken_T{topic.number:02d}.txt"
            fname.write_text(content, encoding="utf-8")
            generated.append(fname)
    else:
        # Todo en un solo fichero
        if output_path.suffix == "":
            output_path = output_path / "aiken_completo.txt"
        else:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        contents = []
        for topic in course.topics:
            if topic.quiz:
                contents.append(_aiken_block(topic, course.metadata.title, course.metadata.mastery))
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
) -> List[Path]:
    """Genera un .txt Aiken por tema con N preguntas adicionales generadas por IA.

    Requiere ANTHROPIC_API_KEY. Si no está disponible, devuelve lista vacía
    sin error.

    Args:
        course: estructura del curso
        output_dir: directorio donde se generarán los .txt
        n_questions_per_topic: número objetivo de preguntas por tema

    Returns:
        lista de ficheros generados (uno por tema si la IA respondió)
    """
    from scorm_builder.ai_assist import is_available, generate_extended_aiken

    if not is_available():
        return []

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    generated: List[Path] = []

    for topic in course.topics:
        questions = generate_extended_aiken(topic, n_questions=n_questions_per_topic)
        if not questions:
            continue

        lines = []
        lines.append("// =====================================================================")
        lines.append(f"// Curso: {course.metadata.title}")
        lines.append(f"// Tema {topic.number}: {topic.title}")
        lines.append(f"// Banco AMPLIADO (generado por IA) — {len(questions)} preguntas")
        lines.append(f"// Para importar en Moodle como cuestionario separado")
        lines.append("// Codificación: UTF-8")
        lines.append("// =====================================================================")
        lines.append("")

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
                lines.append(f"// Explicación: {_aiken_safe_line(q['explanation'])}")
            lines.append("")

        fname = output_dir / f"aiken_T{topic.number:02d}_extendido.txt"
        fname.write_text("\n".join(lines), encoding="utf-8")
        generated.append(fname)

    return generated

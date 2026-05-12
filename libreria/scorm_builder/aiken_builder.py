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
        lines.append(q.text)
        for idx, opt in enumerate(q.options):
            letter = chr(ord("A") + idx)
            lines.append(f"{letter}. {opt}")
        correct_letter = chr(ord("A") + q.correct_index)
        lines.append(f"ANSWER: {correct_letter}")
        if q.explanation:
            lines.append(f"// Explicación: {q.explanation}")
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

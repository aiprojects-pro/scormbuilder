"""SCORM Builder - convierte DOCX en cursos SCORM con tu marca.

API pública:
    >>> from scorm_builder import build_scorm_from_docx
    >>> build_scorm_from_docx("mi_curso.docx", output="mi_curso.zip", theme="azul")
"""
from scorm_builder.parser import parse_docx, CourseStructure
from scorm_builder.renderer import render_html
from scorm_builder.packager import build_scorm_package
from scorm_builder.themes import get_theme, list_themes, Theme
from scorm_builder.aiken_builder import build_aiken_file
from scorm_builder.pdf_builder import build_pdf
from scorm_builder.api import build_scorm_from_docx, build_complete_course

__version__ = "0.1.0"

__all__ = [
    "parse_docx",
    "CourseStructure",
    "render_html",
    "build_scorm_package",
    "build_scorm_from_docx",
    "build_complete_course",
    "build_aiken_file",
    "build_pdf",
    "get_theme",
    "list_themes",
    "Theme",
]

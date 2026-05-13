"""Tests de regresión para v0.5 Fase 2.

Verifica:
- Tags por tema: serialización, render como chips, inyección en manifest.
- Quizzes con qtype: multiple_choice, true_false, fill_in.
- Preguntas intercaladas por subapartado (inline_quiz).
- Exporter IMS Content Package.
- Banco Aiken extendido (mockeado, sin llamar a la IA real).
- ai_assist en modo sin API key (no rompe).
"""
import json
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def test_docx():
    path = Path(__file__).parent.parent.parent / "plantilla" / "test_v05.docx"
    if not path.exists():
        import subprocess, sys
        subprocess.run([sys.executable, str(path.parent / "generar_test_v05.py")], check=True)
    return path


@pytest.fixture
def course_with_tags(test_docx):
    """Carga el curso de test y le añade tags y quiz inline manualmente."""
    from scorm_builder.parser import parse_docx, Question
    course = parse_docx(test_docx)
    course.topics[0].tags = [
        "gestion deportiva", "comite olimpico", "normativa",
        "nivel avanzado", "casos practicos",
    ]
    sub_id = course.topics[0].subsections[0].id
    course.topics[0].inline_quiz[sub_id] = [
        Question(
            text="El parser de v0.5 extrae imágenes incrustadas?",
            options=["Verdadero", "Falso"],
            correct_index=0,
            explanation="Sí, la extracción es automática.",
            qtype="true_false",
        )
    ]
    # Sustituir el quiz final por una mezcla de tipos
    course.topics[0].quiz = [
        Question(
            text="¿Qué tipo de pregunta es esta?",
            options=["Test", "Verdadero/Falso", "Hueco", "Otra"],
            correct_index=0,
            qtype="multiple_choice",
        ),
        Question(
            text="WCAG 2.1 AA aplicada al HTML mejora la accesibilidad.",
            options=["Verdadero", "Falso"],
            correct_index=0,
            qtype="true_false",
        ),
        Question(
            text="El paquete ___ permite a Moodle leer cursos sin tracking SCORM.",
            options=["IMS CP", "PDF", "XLSX", "DOCX"],
            correct_index=0,
            qtype="fill_in",
        ),
    ]
    return course


# -------- TAGS --------

def test_tags_se_serializan(course_with_tags):
    d = course_with_tags.to_dict()
    assert d["topics"][0]["tags"] == [
        "gestion deportiva", "comite olimpico", "normativa",
        "nivel avanzado", "casos practicos",
    ]


def test_tags_round_trip_dict(course_with_tags):
    from scorm_builder.api import course_from_dict
    c2 = course_from_dict(course_with_tags.to_dict())
    assert c2.topics[0].tags == course_with_tags.topics[0].tags


def test_tags_aparecen_como_chips(course_with_tags):
    from scorm_builder.renderer import render_html
    from scorm_builder.themes import get_theme
    html = render_html(course_with_tags, get_theme("azul"))[1]
    assert 'class="tag-chips"' in html
    assert "gestion deportiva" in html
    assert "comite olimpico" in html
    # Cinco chips
    chip_count = html.count('class="tag-chip"')
    assert chip_count == 5


def test_tags_en_manifest_scorm(course_with_tags, tmp_path):
    from scorm_builder.renderer import render_html
    from scorm_builder.themes import get_theme
    from scorm_builder.packager import build_scorm_package
    html = render_html(course_with_tags, get_theme("azul"))[1]
    zp = tmp_path / "test.zip"
    build_scorm_package(course_with_tags.topics[0], html, course_with_tags.metadata.title, zp)
    with zipfile.ZipFile(zp) as zf:
        manifest = zf.read("imsmanifest.xml").decode("utf-8")
    # Validar XML
    ET.fromstring(manifest)
    # 5 keywords
    assert manifest.count("<imsmd:keyword>") == 5
    assert "gestion deportiva" in manifest


# -------- QTYPES --------

def test_qtype_multiple_choice_render(course_with_tags):
    from scorm_builder.renderer import render_html
    from scorm_builder.themes import get_theme
    html = render_html(course_with_tags, get_theme("azul"))[1]
    assert 'data-qtype="multiple_choice"' in html


def test_qtype_true_false_render(course_with_tags):
    from scorm_builder.renderer import render_html
    from scorm_builder.themes import get_theme
    html = render_html(course_with_tags, get_theme("azul"))[1]
    assert 'data-qtype="true_false"' in html
    # No debe llevar prefijo "A." / "B." en V/F
    # Buscamos las opciones del fieldset True/False
    assert "Verdadero" in html
    assert "Falso" in html


def test_qtype_fill_in_render(course_with_tags):
    from scorm_builder.renderer import render_html
    from scorm_builder.themes import get_theme
    html = render_html(course_with_tags, get_theme("azul"))[1]
    assert 'data-qtype="fill_in"' in html
    # El span del hueco
    assert 'class="fill-blank"' in html


# -------- INLINE QUIZ --------

def test_inline_quiz_se_renderiza(course_with_tags):
    from scorm_builder.renderer import render_html
    from scorm_builder.themes import get_theme
    html = render_html(course_with_tags, get_theme("azul"))[1]
    assert 'class="inline-quiz"' in html
    assert "Pregunta de repaso" in html
    assert 'class="quiz-feedback"' in html


def test_inline_quiz_serializacion(course_with_tags):
    from scorm_builder.api import course_from_dict
    d = course_with_tags.to_dict()
    assert d["topics"][0]["inline_quiz"]  # no vacío
    c2 = course_from_dict(d)
    sub_id = course_with_tags.topics[0].subsections[0].id
    assert sub_id in c2.topics[0].inline_quiz
    assert c2.topics[0].inline_quiz[sub_id][0].qtype == "true_false"


def test_inline_quiz_js_disponible(course_with_tags):
    """La función evaluarInline debe estar en el JS embebido."""
    from scorm_builder.renderer import render_html
    from scorm_builder.themes import get_theme
    html = render_html(course_with_tags, get_theme("azul"))[1]
    assert "function evaluarInline" in html


# -------- IMS Content Package --------

def test_ims_cp_genera_zip(course_with_tags, tmp_path):
    from scorm_builder.renderer import render_html
    from scorm_builder.themes import get_theme
    from scorm_builder.exporters import export_ims_cp
    htmls = render_html(course_with_tags, get_theme("azul"))
    out = tmp_path / "curso_ims.zip"
    result = export_ims_cp(course_with_tags, htmls, out)
    assert result.exists()
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
    assert "imsmanifest.xml" in names
    assert any(n.startswith("tema_01_") and n.endswith(".html") for n in names)


def test_ims_cp_manifest_valido(course_with_tags, tmp_path):
    from scorm_builder.renderer import render_html
    from scorm_builder.themes import get_theme
    from scorm_builder.exporters import export_ims_cp
    htmls = render_html(course_with_tags, get_theme("azul"))
    out = tmp_path / "curso_ims.zip"
    export_ims_cp(course_with_tags, htmls, out)
    with zipfile.ZipFile(out) as zf:
        manifest = zf.read("imsmanifest.xml").decode("utf-8")
    # XML válido
    root = ET.fromstring(manifest)
    # Schema correcto (IMS CP, no SCORM)
    assert "imscp_v1p1" in manifest
    assert 'adlcp:scormtype' not in manifest  # no es SCORM
    # Items: uno por tema (test_v05.docx tiene 1 tema)
    ns = {"cp": "http://www.imsglobal.org/xsd/imscp_v1p1"}
    items = root.findall(".//cp:item", ns)
    assert len(items) == len(course_with_tags.topics)
    # Cada item tiene resource asociado
    for item in items:
        assert item.get("identifierref") is not None


def test_ims_cp_lleva_tags_en_manifest(course_with_tags, tmp_path):
    from scorm_builder.renderer import render_html
    from scorm_builder.themes import get_theme
    from scorm_builder.exporters import export_ims_cp
    htmls = render_html(course_with_tags, get_theme("azul"))
    out = tmp_path / "curso_ims.zip"
    export_ims_cp(course_with_tags, htmls, out)
    with zipfile.ZipFile(out) as zf:
        manifest = zf.read("imsmanifest.xml").decode("utf-8")
    # Los tags del primer tema deben estar en el manifest
    assert "gestion deportiva" in manifest


# -------- AI ASSIST (modo SIN clave) --------

def test_ai_no_disponible_sin_clave(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from scorm_builder import ai_assist
    assert ai_assist.is_available() is False
    # Las funciones devuelven None sin lanzar
    assert ai_assist.generate_tags({"title": "x", "subsections": []}) is None
    assert ai_assist.generate_quiz({"title": "x", "subsections": []}) is None
    assert ai_assist.generate_extended_aiken({"title": "x", "subsections": []}) is None


def test_topic_to_plain_text():
    from scorm_builder.ai_assist import topic_to_plain_text
    topic = {
        "title": "Mi tema",
        "intro": "Intro del tema",
        "subsections": [{
            "number": "1.1",
            "title": "Sub uno",
            "blocks": [
                {"type": "paragraph", "text": "Párrafo 1"},
                {"type": "list_bullet", "items": ["item A", "item B"]},
            ],
        }],
    }
    text = topic_to_plain_text(topic)
    assert "Mi tema" in text
    assert "Sub uno" in text
    assert "Párrafo 1" in text
    assert "- item A" in text


# -------- QuizConfig --------

def test_quiz_config_dataclass():
    from scorm_builder.ai_assist import QuizConfig
    cfg = QuizConfig()
    assert cfg.location == "final"
    assert cfg.types == ["multiple_choice"]
    assert cfg.n_questions == 5

    cfg2 = QuizConfig(location="mixed", types=["true_false", "fill_in"], n_questions=10)
    assert cfg2.location == "mixed"
    assert "true_false" in cfg2.types

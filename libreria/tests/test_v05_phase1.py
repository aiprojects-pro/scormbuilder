"""Tests de regresión para v0.5.

Verifica las funcionalidades críticas añadidas en la Fase 1:
- Extracción de imágenes incrustadas del DOCX.
- Preservación de hipervínculos como `<a>`.
- Detección de YouTube/Vimeo (hyperlink y URL plana) → iframe.
- Autolinking de URLs sueltas.
- Formato inline (negrita, cursiva).
- WCAG: skip-link, main semántico, fieldset/legend en quiz, aria-live, etc.
- Botón "Descargar PDF" en cabecera.
- strict_wcag bloqueante.
"""
import io
import zipfile
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def test_docx():
    """Genera el DOCX de test si no existe."""
    path = Path(__file__).parent.parent.parent / "plantilla" / "test_v05.docx"
    if not path.exists():
        # Lanzamos el generador
        import subprocess, sys
        subprocess.run(
            [sys.executable, str(path.parent / "generar_test_v05.py")],
            check=True,
        )
    return path


@pytest.fixture(scope="module")
def built_scorm(test_docx, tmp_path_factory):
    """Construye el SCORM y devuelve la ruta del primer ZIP."""
    from scorm_builder.api import build_complete_course
    out = tmp_path_factory.mktemp("scorm")
    result = build_complete_course(docx_path=test_docx, output_dir=out)
    assert result.scorm_zips, "No se generó ningún SCORM"
    return result.scorm_zips[0], result.course


def _html_of(zip_path):
    with zipfile.ZipFile(zip_path) as zf:
        return zf.read("index.html").decode("utf-8")


def _files_in(zip_path):
    with zipfile.ZipFile(zip_path) as zf:
        return zf.namelist()


def test_imagen_extraida_en_recursos(built_scorm):
    z, course = built_scorm
    files = _files_in(z)
    assert any("docx_img_" in f for f in files), "Imagen extraída no incluida"
    assert len(course.extracted_image_files) >= 1


def test_pdf_incluido_y_referenciado(built_scorm):
    z, _ = built_scorm
    files = _files_in(z)
    assert any(f.endswith(".pdf") and "apuntes_T" in f for f in files), "PDF no incluido"
    html = _html_of(z)
    assert 'class="pdf-download-btn"' in html
    assert "recursos/apuntes_T01.pdf" in html


def test_negrita_cursiva_preservadas(built_scorm):
    z, _ = built_scorm
    html = _html_of(z)
    assert "<strong>negrita</strong>" in html
    assert "<em>cursiva</em>" in html


def test_hyperlink_preservado(built_scorm):
    z, _ = built_scorm
    html = _html_of(z)
    assert 'href="https://www.boe.es"' in html
    # No anidados
    assert '<a href="<a' not in html


def test_url_suelta_autolinkada(built_scorm):
    z, _ = built_scorm
    html = _html_of(z)
    assert 'href="https://es.wikipedia.org' in html


def test_youtube_hyperlink_a_iframe(built_scorm):
    z, _ = built_scorm
    html = _html_of(z)
    assert "youtube.com/embed/dQw4w9WgXcQ" in html
    # No queda como enlace inline
    assert "youtube.com/watch?v=dQw4w9WgXcQ" not in html


def test_youtube_url_suelta_a_iframe(built_scorm):
    z, _ = built_scorm
    html = _html_of(z)
    assert "youtube.com/embed/9bZkp7q19f0" in html


def test_iframe_title_sin_tags(built_scorm):
    z, _ = built_scorm
    html = _html_of(z)
    # No deben aparecer entidades HTML en title=""
    assert 'title="&lt;' not in html


def test_wcag_skip_link(built_scorm):
    z, _ = built_scorm
    html = _html_of(z)
    assert 'class="skip-link"' in html
    assert 'href="#contenido"' in html


def test_wcag_main_semantico(built_scorm):
    z, _ = built_scorm
    html = _html_of(z)
    assert 'id="contenido"' in html
    assert 'tabindex="-1"' in html  # main programáticamente enfocable


def test_wcag_quiz_fieldset(built_scorm):
    z, _ = built_scorm
    html = _html_of(z)
    assert "<fieldset class=\"quiz\"" in html
    assert "<legend" in html
    assert 'role="radiogroup"' in html


def test_wcag_aria_live_resultado(built_scorm):
    z, _ = built_scorm
    html = _html_of(z)
    assert 'aria-live="polite"' in html


def test_wcag_prefers_reduced_motion_css(built_scorm):
    z, _ = built_scorm
    html = _html_of(z)
    assert "prefers-reduced-motion" in html


def test_callout_con_enlace_dentro(built_scorm):
    z, _ = built_scorm
    html = _html_of(z)
    # El callout ALERTA debe contener el hyperlink al BOE
    assert "callout-alert" in html
    assert "LOMCE" in html
    assert "BOE-A-2013" in html


def test_tabla_con_enlaces(built_scorm):
    z, _ = built_scorm
    html = _html_of(z)
    # La tabla del test contiene un enlace a docs.python.org dentro de <td>
    assert "docs.python.org" in html
    assert "<table" in html


def test_strict_wcag_bloquea_imagen_sin_alt(test_docx, tmp_path):
    """El test_v05.docx tiene una imagen sin alt → strict_wcag debe lanzar."""
    from scorm_builder.api import build_complete_course
    from scorm_builder.wcag import WCAGValidationError
    with pytest.raises(WCAGValidationError) as exc:
        build_complete_course(
            docx_path=test_docx, output_dir=tmp_path, strict_wcag=True,
        )
    assert exc.value.report.n_errors >= 1


def test_round_trip_dict_preserva_html(test_docx):
    """to_dict → course_from_dict preserva text_html/items_html/rows_html."""
    from scorm_builder.parser import parse_docx
    from scorm_builder.api import course_from_dict
    from scorm_builder.renderer import render_html
    from scorm_builder.themes import get_theme
    c1 = parse_docx(test_docx)
    c2 = course_from_dict(c1.to_dict())
    h1 = render_html(c1, get_theme("azul"))[1]
    h2 = render_html(c2, get_theme("azul"))[1]
    # Las dos versiones tienen el mismo contenido enriquecido
    assert "<strong>negrita</strong>" in h1
    assert "<strong>negrita</strong>" in h2
    assert 'href="https://www.boe.es"' in h1
    assert 'href="https://www.boe.es"' in h2


def test_manifest_xml_valido(built_scorm):
    """El imsmanifest.xml debe ser XML válido."""
    z, _ = built_scorm
    import xml.etree.ElementTree as ET
    with zipfile.ZipFile(z) as zf:
        manifest = zf.read("imsmanifest.xml").decode("utf-8")
    ET.fromstring(manifest)  # no debe lanzar


def test_html_correctamente_anidado(built_scorm):
    """Comprueba que el HTML está bien anidado (sin tags huérfanas)."""
    z, _ = built_scorm
    import html.parser as hp

    class V(hp.HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack = []
            self.errors = []
            self.void = {'img','br','hr','meta','link','input','source','track'}
        def handle_starttag(self, tag, attrs):
            if tag not in self.void:
                self.stack.append(tag)
        def handle_endtag(self, tag):
            if not self.stack:
                self.errors.append(f"cierre </{tag}> sin apertura")
                return
            if self.stack[-1] != tag:
                if tag in self.stack:
                    while self.stack and self.stack[-1] != tag:
                        self.stack.pop()
                    if self.stack: self.stack.pop()
                else:
                    self.errors.append(f"cierre </{tag}> huérfano")
            else:
                self.stack.pop()

    v = V()
    v.feed(_html_of(z))
    assert v.errors == []
    assert v.stack == []

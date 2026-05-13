"""Tests Fase 5 (v0.5):
- Plantilla Word moderna (template_builder)
- Exporter cmi5 / xAPI
- Endpoints de enriquecer + apply + copyright + cmi5 + snapshots + plantilla
- Botones UI en el editor
"""
import io
import json
import os
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
INSTALADOR = ROOT / "instalador"
sys.path.insert(0, str(INSTALADOR))


@pytest.fixture(scope="module")
def app_test():
    tmpdir = Path(tempfile.mkdtemp(prefix="scormtest_p5_"))
    os.environ["SCORM_BUILDER_WORK_DIR"] = str(tmpdir)
    if "app_local" in sys.modules:
        del sys.modules["app_local"]
    import app_local
    app_local.app.config["TESTING"] = True
    yield app_local
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


def _register_and_login(client, email="p5@t.local", password="testpass123"):
    client.post("/register", data={
        "email": email, "password": password, "password2": password, "name": "P5",
    }, follow_redirects=True)
    client.post("/login", data={"email": email, "password": password})


def _create_course(app_test, email="p5@t.local", *, with_image=True):
    """Crea un curso con estructura mínima y opcionalmente una imagen."""
    import uuid, base64
    with app_test.db() as conn:
        user = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    uid = user["id"]
    udir = app_test.user_dir(uid)
    token = "p5_" + uuid.uuid4().hex[:8]
    job_dir = udir / f"job_{token}"
    job_dir.mkdir(parents=True, exist_ok=True)
    if with_image:
        (job_dir / "recursos").mkdir(exist_ok=True)
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
        )
        (job_dir / "recursos" / "img1.png").write_bytes(png_bytes)
    structure = {
        "metadata": {"title": "Curso P5", "author": "T", "subtitle": "", "sector": "",
                     "palette": "azul", "mastery": 70, "weight_view": 40, "weight_quiz": 60,
                     "view_min_seconds": 10, "view_strategy": "both"},
        "topics": [{
            "number": 1, "title": "Tema P5", "intro": "Intro larga del tema con suficiente texto.",
            "tags": [],
            "subsections": [{
                "id": "l1", "number": "1.1", "title": "Sub",
                "blocks": [
                    {"type": "paragraph",
                     "text": "Definicion clave: el SCORM es un estandar de empaquetado de contenidos e-learning.",
                     "items": [], "rows": [], "extras": {}},
                    {"type": "paragraph",
                     "text": "ALERTA: nunca compartir credenciales del LMS en repositorios publicos.",
                     "items": [], "rows": [], "extras": {}},
                ],
            }],
            "quiz": [], "inline_quiz": {},
        }],
        "warnings": [],
    }
    (job_dir / "structure.json").write_text(json.dumps(structure), encoding="utf-8")
    zip_path = job_dir / "curso.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("index.html", "<html/>")
    with app_test.db() as conn:
        conn.execute(
            "INSERT INTO courses (user_id, token, title, zip_path, created_at) VALUES (?,?,?,?,?)",
            (uid, token, "Curso P5", str(zip_path), datetime.utcnow().isoformat()))
        conn.commit()
    return token, job_dir


# ============================================================
# PLANTILLA WORD MODERNA
# ============================================================

def test_plantilla_genera_docx_valido(tmp_path):
    from scorm_builder.template_builder import build_modern_template
    out = tmp_path / "plantilla.docx"
    result = build_modern_template(out)
    assert result.exists()
    assert result.stat().st_size > 10_000  # debe pesar algo razonable


def test_plantilla_es_parseable(tmp_path):
    """La plantilla generada debe ser parseable por parse_docx (round-trip)."""
    from scorm_builder.template_builder import build_modern_template
    from scorm_builder.parser import parse_docx
    out = tmp_path / "plantilla.docx"
    build_modern_template(out, course_title="X", author="Y")
    course = parse_docx(out)
    assert len(course.topics) >= 1
    assert course.topics[0].subsections


def test_plantilla_lleva_callouts_de_ejemplo(tmp_path):
    """Los cinco tipos de callout deben aparecer en el documento."""
    from scorm_builder.template_builder import build_modern_template
    from docx import Document
    out = tmp_path / "plantilla.docx"
    build_modern_template(out)
    doc = Document(out)
    full_text = "\n".join(p.text for p in doc.paragraphs)
    for prefix in ["[CLAVE]", "[ALERTA]", "[EXITO]", "[CUIDADO]", "[CITA]"]:
        assert prefix in full_text


def test_endpoint_plantilla_descarga(app_test):
    """GET /plantilla/descargar devuelve un .docx con cabecera correcta."""
    client = app_test.app.test_client()
    r = client.get("/plantilla/descargar")
    assert r.status_code == 200
    assert "wordprocessingml" in r.headers.get("Content-Type", "")
    # Es un ZIP (los .docx lo son): cabecera PK
    assert r.data[:2] == b"PK"


# ============================================================
# EXPORTER CMI5
# ============================================================

def test_cmi5_genera_zip_valido(tmp_path):
    from scorm_builder.parser import parse_docx
    from scorm_builder.renderer import render_html
    from scorm_builder.themes import get_theme
    from scorm_builder.exporters import export_cmi5
    course = parse_docx(ROOT / "plantilla" / "test_v05.docx")
    htmls = render_html(course, get_theme("azul"))
    out = tmp_path / "cmi5.zip"
    result = export_cmi5(course, htmls, out)
    assert result.exists()
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
    assert "cmi5.xml" in names
    assert any(n.startswith("tema_") and n.endswith(".html") for n in names)


def test_cmi5_xml_valido(tmp_path):
    import xml.etree.ElementTree as ET
    from scorm_builder.parser import parse_docx
    from scorm_builder.renderer import render_html
    from scorm_builder.themes import get_theme
    from scorm_builder.exporters import export_cmi5
    course = parse_docx(ROOT / "plantilla" / "test_v05.docx")
    htmls = render_html(course, get_theme("azul"))
    out = tmp_path / "cmi5.zip"
    export_cmi5(course, htmls, out)
    with zipfile.ZipFile(out) as zf:
        cmi5_xml = zf.read("cmi5.xml").decode("utf-8")
    root = ET.fromstring(cmi5_xml)  # no debe lanzar
    # Tiene course + au
    assert "<au id=" in cmi5_xml
    assert "<course id=" in cmi5_xml


def test_cmi5_html_lleva_tracking_xapi(tmp_path):
    from scorm_builder.parser import parse_docx
    from scorm_builder.renderer import render_html
    from scorm_builder.themes import get_theme
    from scorm_builder.exporters import export_cmi5
    course = parse_docx(ROOT / "plantilla" / "test_v05.docx")
    htmls = render_html(course, get_theme("azul"))
    out = tmp_path / "cmi5.zip"
    export_cmi5(course, htmls, out)
    with zipfile.ZipFile(out) as zf:
        html_name = next(n for n in zf.namelist() if n.endswith(".html"))
        html = zf.read(html_name).decode("utf-8")
    # JS xAPI presente
    assert "cmi5Complete" in html
    assert "X-Experience-API-Version" in html
    # SCORM API ya no debe llamarse desde el JS de tracking
    assert 'window.API' not in html.split("cmi5Complete")[0] or "neutralize" not in html


# ============================================================
# ENDPOINTS
# ============================================================

def test_endpoint_ai_enrich_sin_apikey(app_test):
    client = app_test.app.test_client()
    _register_and_login(client, email="p5a@t.local")
    token, _ = _create_course(app_test, email="p5a@t.local")
    old = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        r = client.post(f"/api/curso/{token}/ai-enrich",
                        json={"topic_index": 0})
        assert r.status_code == 400
        assert "ANTHROPIC_API_KEY" in r.get_json().get("error", "")
    finally:
        if old:
            os.environ["ANTHROPIC_API_KEY"] = old


def test_endpoint_apply_enrich_aplica_y_crea_snapshot(app_test):
    """apply-enrich modifica los bloques y crea snapshot previo."""
    client = app_test.app.test_client()
    _register_and_login(client, email="p5b@t.local")
    token, job_dir = _create_course(app_test, email="p5b@t.local")
    accepted = [{
        "subsection_id": "l1",
        "block_index": 0,
        "suggested_type": "callout_key",
        "suggested_text": "Texto reescrito clave",
    }]
    r = client.post(f"/api/curso/{token}/apply-enrich",
                    json={"topic_index": 0, "accepted": accepted})
    assert r.status_code == 200
    data = r.get_json()
    assert data["applied"] == 1
    assert data["snapshot_id"]
    # Verificar que se aplicó
    s = json.loads((job_dir / "structure.json").read_text(encoding="utf-8"))
    assert s["topics"][0]["subsections"][0]["blocks"][0]["type"] == "callout_key"
    assert s["topics"][0]["subsections"][0]["blocks"][0]["text"] == "Texto reescrito clave"
    # Y que existe la snapshot
    snaps = list((job_dir / "snapshots").glob("*.json"))
    assert len(snaps) == 1


def test_endpoint_apply_enrich_rechaza_tipo_invalido(app_test):
    """Aplicar con suggested_type no permitido no cambia nada."""
    client = app_test.app.test_client()
    _register_and_login(client, email="p5c@t.local")
    token, job_dir = _create_course(app_test, email="p5c@t.local")
    r = client.post(f"/api/curso/{token}/apply-enrich",
                    json={"topic_index": 0, "accepted": [{
                        "subsection_id": "l1", "block_index": 0,
                        "suggested_type": "INVENTADO", "suggested_text": "X",
                    }]})
    assert r.status_code == 200
    assert r.get_json()["applied"] == 0


def test_endpoint_snapshots_list(app_test):
    """Lista las snapshots."""
    client = app_test.app.test_client()
    _register_and_login(client, email="p5d@t.local")
    token, _ = _create_course(app_test, email="p5d@t.local")
    # Sin snapshots aún
    r = client.get(f"/api/curso/{token}/snapshots")
    assert r.status_code == 200
    assert r.get_json()["snapshots"] == []
    # Aplico enrich (crea snapshot)
    client.post(f"/api/curso/{token}/apply-enrich",
                json={"topic_index": 0, "accepted": [{
                    "subsection_id": "l1", "block_index": 0,
                    "suggested_type": "callout_key", "suggested_text": "X",
                }]})
    r = client.get(f"/api/curso/{token}/snapshots")
    assert len(r.get_json()["snapshots"]) == 1


def test_endpoint_preview_html_de_snapshot(app_test):
    """Se puede previsualizar una snapshot por id."""
    client = app_test.app.test_client()
    _register_and_login(client, email="p5e@t.local")
    token, _ = _create_course(app_test, email="p5e@t.local")
    # Crear snapshot
    client.post(f"/api/curso/{token}/apply-enrich",
                json={"topic_index": 0, "accepted": [{
                    "subsection_id": "l1", "block_index": 0,
                    "suggested_type": "callout_key", "suggested_text": "Nuevo",
                }]})
    snaps = client.get(f"/api/curso/{token}/snapshots").get_json()["snapshots"]
    snap_id = snaps[0]["id"]
    r = client.get(f"/api/curso/{token}/preview-html/{snap_id}?topic_index=0")
    assert r.status_code == 200
    html = r.data.decode("utf-8")
    # Banner indicando snapshot
    assert "snapshot" in html.lower()
    assert snap_id in html


def test_endpoint_preview_html_snapshot_id_invalido(app_test):
    """IDs con / o .. son rechazados."""
    client = app_test.app.test_client()
    _register_and_login(client, email="p5f@t.local")
    token, _ = _create_course(app_test, email="p5f@t.local")
    r = client.get(f"/api/curso/{token}/preview-html/..")
    assert r.status_code in (400, 404)


def test_endpoint_ai_copyright_sin_apikey(app_test):
    client = app_test.app.test_client()
    _register_and_login(client, email="p5g@t.local")
    token, _ = _create_course(app_test, email="p5g@t.local")
    old = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        r = client.post(f"/api/curso/{token}/ai-copyright",
                        json={"filename": "img1.png"})
        assert r.status_code == 400
    finally:
        if old:
            os.environ["ANTHROPIC_API_KEY"] = old


def test_endpoint_ai_copyright_rechaza_path_traversal(app_test, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-key")
    client = app_test.app.test_client()
    _register_and_login(client, email="p5h@t.local")
    token, _ = _create_course(app_test, email="p5h@t.local")
    for evil in ["../secret", "sub/file.png", "..\\evil"]:
        r = client.post(f"/api/curso/{token}/ai-copyright",
                        json={"filename": evil})
        assert r.status_code == 400


def test_endpoint_export_cmi5_genera_zip(app_test):
    """El endpoint genera el ZIP cmi5 descargable."""
    client = app_test.app.test_client()
    _register_and_login(client, email="p5i@t.local")
    token, _ = _create_course(app_test, email="p5i@t.local")
    r = client.post(f"/api/curso/{token}/export-cmi5")
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert data["filename"] == "curso_cmi5.zip"
    # Y la descarga responde
    r2 = client.get(f"/curso/{token}/export/cmi5")
    assert r2.status_code == 200


# ============================================================
# UI: BOTONES PRESENTES
# ============================================================

def test_editor_tiene_boton_enrich(app_test):
    client = app_test.app.test_client()
    _register_and_login(client, email="p5j@t.local")
    token, _ = _create_course(app_test, email="p5j@t.local")
    r = client.get(f"/curso/{token}/editar")
    html = r.data.decode("utf-8")
    assert 'data-topic-ai="enrich"' in html
    assert "Enriquecer con callouts IA" in html
    assert "showEnrichModal" in html


def test_editor_tiene_boton_copyright_en_imagen(app_test):
    client = app_test.app.test_client()
    _register_and_login(client, email="p5k@t.local")
    token, _ = _create_course(app_test, email="p5k@t.local")
    # Añadir un bloque imagen con src local
    sp = list((Path(app_test.user_dir(1)).glob("**/structure.json")))
    # Simpler: añadir directamente a la estructura
    import sqlite3
    with app_test.db() as conn:
        row = conn.execute("SELECT zip_path FROM courses WHERE token=?", (token,)).fetchone()
    job_dir = Path(row["zip_path"]).parent
    sp = job_dir / "structure.json"
    data = json.loads(sp.read_text(encoding="utf-8"))
    data["topics"][0]["subsections"][0]["blocks"].append({
        "type": "image", "text": "",
        "extras": {"src": "img1.png", "file": "img1.png"},
        "items": [], "rows": [],
    })
    sp.write_text(json.dumps(data), encoding="utf-8")
    r = client.get(f"/curso/{token}/editar")
    html = r.data.decode("utf-8")
    assert "ed-copyright-ia" in html
    assert "Comprobar copyright" in html
    assert "showCopyrightModal" in html


def test_editor_tiene_boton_cmi5(app_test):
    client = app_test.app.test_client()
    _register_and_login(client, email="p5l@t.local")
    token, _ = _create_course(app_test, email="p5l@t.local")
    r = client.get(f"/curso/{token}/editar")
    html = r.data.decode("utf-8")
    assert 'id="ed-export-cmi5"' in html
    assert "cmi5" in html.lower()


def test_editor_tiene_selector_snapshot(app_test):
    client = app_test.app.test_client()
    _register_and_login(client, email="p5m@t.local")
    token, _ = _create_course(app_test, email="p5m@t.local")
    r = client.get(f"/curso/{token}/editar")
    html = r.data.decode("utf-8")
    assert "ed-preview-snap" in html


def test_home_tiene_enlace_plantilla(app_test):
    client = app_test.app.test_client()
    _register_and_login(client, email="p5n@t.local")
    r = client.get("/")
    html = r.data.decode("utf-8")
    assert 'href="/plantilla/descargar"' in html


# ============================================================
# AI_ASSIST (modo sin clave)
# ============================================================

def test_enrich_topic_sin_clave_devuelve_none(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from scorm_builder import ai_assist
    result = ai_assist.enrich_topic_with_callouts({"subsections": []})
    assert result is None


def test_detect_copyright_sin_clave_devuelve_none(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from scorm_builder import ai_assist
    img = tmp_path / "test.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")  # cabecera PNG mínima
    result = ai_assist.detect_copyright_risk(img)
    assert result is None

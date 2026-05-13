"""Tests Fase 4 (v0.5): alt-text IA por bloque, WCAG check endpoint, vista previa iframe."""
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
    tmpdir = Path(tempfile.mkdtemp(prefix="scormtest_p4_"))
    os.environ["SCORM_BUILDER_WORK_DIR"] = str(tmpdir)
    if "app_local" in sys.modules:
        del sys.modules["app_local"]
    import app_local
    app_local.app.config["TESTING"] = True
    yield app_local
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


def _register_and_login(client, email="p4@t.local", password="testpass123"):
    client.post("/register", data={
        "email": email, "password": password, "password2": password, "name": "P4",
    }, follow_redirects=True)
    client.post("/login", data={"email": email, "password": password})


def _create_course(app_test, email="p4@t.local", *, include_image=True):
    """Crea un curso de test con una imagen real en /recursos/."""
    import uuid
    with app_test.db() as conn:
        user = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    uid = user["id"]
    udir = app_test.user_dir(uid)
    token = "p4_" + uuid.uuid4().hex[:8]
    job_dir = udir / f"job_{token}"
    job_dir.mkdir(parents=True, exist_ok=True)

    # Recurso imagen real (1x1 PNG rojo)
    if include_image:
        recursos = job_dir / "recursos"
        recursos.mkdir(exist_ok=True)
        import base64
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
        )
        (recursos / "docx_img_001.png").write_bytes(png_bytes)

    structure = {
        "metadata": {"title": "Curso P4", "author": "T", "subtitle": "", "sector": "",
                     "palette": "azul", "mastery": 70, "weight_view": 40, "weight_quiz": 60,
                     "view_min_seconds": 10, "view_strategy": "both"},
        "topics": [{
            "number": 1, "title": "Tema P4", "intro": "Intro",
            "tags": [],
            "subsections": [{
                "id": "l1", "number": "1.1", "title": "Sub",
                "blocks": [
                    {"type": "paragraph", "text": "Texto.",
                     "items": [], "rows": [], "extras": {}},
                    # Imagen con alt vacío → debería disparar error WCAG 1.1.1
                    {"type": "image", "text": "",
                     "items": [], "rows": [],
                     "extras": {"src": "docx_img_001.png", "file": "docx_img_001.png"}},
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
            (uid, token, "Curso P4", str(zip_path), datetime.utcnow().isoformat()))
        conn.commit()
    return token, job_dir


# -------- ENDPOINT WCAG CHECK --------

def test_wcag_check_devuelve_informe(app_test):
    """El endpoint /wcag-check devuelve un informe con la imagen sin alt como error."""
    client = app_test.app.test_client()
    _register_and_login(client, email="p4a@t.local")
    token, _ = _create_course(app_test, email="p4a@t.local")
    r = client.post(f"/api/curso/{token}/wcag-check")
    assert r.status_code == 200
    data = r.get_json()
    assert "passes" in data
    assert "issues" in data
    # Debe encontrar al menos el error 1.1.1 (imagen sin alt)
    codes = {i["code"] for i in data["issues"]}
    assert "1.1.1" in codes
    assert data["passes"] is False  # error bloqueante presente


def test_wcag_check_pasa_si_imagen_tiene_alt(app_test):
    """Tras añadir alt-text a la imagen, el validador pasa."""
    client = app_test.app.test_client()
    _register_and_login(client, email="p4b@t.local")
    token, job_dir = _create_course(app_test, email="p4b@t.local")
    # Modificar structure.json: añadir alt
    sp = job_dir / "structure.json"
    data = json.loads(sp.read_text(encoding="utf-8"))
    data["topics"][0]["subsections"][0]["blocks"][1]["text"] = "Imagen de prueba"
    sp.write_text(json.dumps(data), encoding="utf-8")
    r = client.post(f"/api/curso/{token}/wcag-check")
    data = r.get_json()
    codes = {i["code"] for i in data["issues"]}
    assert "1.1.1" not in codes  # ya no hay imagen sin alt


# -------- ENDPOINT VISTA PREVIA --------

def test_preview_html_devuelve_html_completo(app_test):
    """La vista previa devuelve el HTML del tema seleccionado."""
    client = app_test.app.test_client()
    _register_and_login(client, email="p4c@t.local")
    token, _ = _create_course(app_test, email="p4c@t.local")
    r = client.get(f"/api/curso/{token}/preview-html?topic_index=0")
    assert r.status_code == 200
    html = r.data.decode("utf-8")
    assert "<!DOCTYPE html>" in html
    assert "<title>" in html
    # WCAG features de Fase 1 deben seguir ahí
    assert 'class="skip-link"' in html


def test_preview_html_reescribe_rutas_de_recursos(app_test):
    """Las referencias a recursos/ se reescriben a la ruta servida por la app."""
    client = app_test.app.test_client()
    _register_and_login(client, email="p4d@t.local")
    token, _ = _create_course(app_test, email="p4d@t.local")
    r = client.get(f"/api/curso/{token}/preview-html?topic_index=0")
    html = r.data.decode("utf-8")
    # La ruta de la imagen debe apuntar al endpoint preview-resource
    assert f"/curso/{token}/preview-resource/" in html
    # No debería quedar ningún src="recursos/" pendiente
    assert 'src="recursos/' not in html


def test_preview_resource_sirve_imagen(app_test):
    """La ruta /preview-resource/ devuelve el binario de la imagen."""
    client = app_test.app.test_client()
    _register_and_login(client, email="p4e@t.local")
    token, _ = _create_course(app_test, email="p4e@t.local")
    r = client.get(f"/curso/{token}/preview-resource/docx_img_001.png")
    assert r.status_code == 200
    # Es una imagen PNG (cabecera estándar)
    assert r.data.startswith(b"\x89PNG")


def test_preview_resource_404_si_no_existe(app_test):
    """Pedir un recurso inexistente devuelve 404."""
    client = app_test.app.test_client()
    _register_and_login(client, email="p4f@t.local")
    token, _ = _create_course(app_test, email="p4f@t.local")
    r = client.get(f"/curso/{token}/preview-resource/no_existe.png")
    assert r.status_code == 404


def test_preview_resource_rechaza_path_traversal(app_test):
    """No se puede salir de la carpeta recursos/ por path traversal."""
    client = app_test.app.test_client()
    _register_and_login(client, email="p4g@t.local")
    token, _ = _create_course(app_test, email="p4g@t.local")
    # Intentos típicos de path traversal
    for evil in ["..%2Fstructure.json", "../structure.json", "..%5cstructure.json"]:
        r = client.get(f"/curso/{token}/preview-resource/{evil}")
        assert r.status_code in (403, 404)


def test_preview_html_topic_fuera_de_rango(app_test):
    """Si topic_index está fuera de rango, devuelve 404."""
    client = app_test.app.test_client()
    _register_and_login(client, email="p4h@t.local")
    token, _ = _create_course(app_test, email="p4h@t.local")
    r = client.get(f"/api/curso/{token}/preview-html?topic_index=99")
    assert r.status_code == 404


# -------- ALT-TEXT IA POR BLOQUE --------

def test_ai_alt_text_block_sin_apikey(app_test):
    """Sin ANTHROPIC_API_KEY devuelve 400 con mensaje claro."""
    client = app_test.app.test_client()
    _register_and_login(client, email="p4i@t.local")
    token, _ = _create_course(app_test, email="p4i@t.local")
    old_key = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        r = client.post(f"/api/curso/{token}/ai-alt-text-block",
                        json={"filename": "docx_img_001.png"})
        assert r.status_code == 400
        assert "ANTHROPIC_API_KEY" in r.get_json().get("error", "")
    finally:
        if old_key:
            os.environ["ANTHROPIC_API_KEY"] = old_key


def test_ai_alt_text_block_rechaza_filename_invalido(app_test, monkeypatch):
    """Filenames con / o .. son rechazados aunque haya API key."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-key-for-test")
    client = app_test.app.test_client()
    _register_and_login(client, email="p4j@t.local")
    token, _ = _create_course(app_test, email="p4j@t.local")
    for evil in ["../secret", "sub/file.png", "..\\evil"]:
        r = client.post(f"/api/curso/{token}/ai-alt-text-block",
                        json={"filename": evil})
        assert r.status_code == 400
        assert "filename" in r.get_json().get("error", "").lower()


def test_ai_alt_text_block_404_si_no_existe(app_test, monkeypatch):
    """Si el archivo no está en recursos/, 404."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-key-for-test")
    client = app_test.app.test_client()
    _register_and_login(client, email="p4k@t.local")
    token, _ = _create_course(app_test, email="p4k@t.local")
    r = client.post(f"/api/curso/{token}/ai-alt-text-block",
                    json={"filename": "fantasma.png"})
    assert r.status_code == 404


# -------- UI: botones presentes en el editor --------

def test_editor_tiene_boton_wcag_check(app_test):
    client = app_test.app.test_client()
    _register_and_login(client, email="p4l@t.local")
    token, _ = _create_course(app_test, email="p4l@t.local")
    r = client.get(f"/curso/{token}/editar")
    html = r.data.decode("utf-8")
    assert 'id="ed-wcag-check"' in html
    assert "Validar WCAG" in html


def test_editor_tiene_boton_preview(app_test):
    client = app_test.app.test_client()
    _register_and_login(client, email="p4m@t.local")
    token, _ = _create_course(app_test, email="p4m@t.local")
    r = client.get(f"/curso/{token}/editar")
    html = r.data.decode("utf-8")
    assert 'id="ed-preview"' in html
    assert "Vista previa" in html


def test_editor_tiene_boton_alt_ia_en_imagen(app_test):
    """En el bloque imagen aparece el botón "Sugerir alt con IA" porque
    el src es local."""
    client = app_test.app.test_client()
    _register_and_login(client, email="p4n@t.local")
    token, _ = _create_course(app_test, email="p4n@t.local")
    r = client.get(f"/curso/{token}/editar")
    html = r.data.decode("utf-8")
    assert "ed-alt-ia" in html
    assert "Sugerir alt con IA" in html


def test_editor_no_muestra_boton_alt_si_url_externa(app_test):
    """Si src es una URL https://..., no aparece el botón IA."""
    client = app_test.app.test_client()
    _register_and_login(client, email="p4o@t.local")
    token, job_dir = _create_course(app_test, email="p4o@t.local")
    sp = job_dir / "structure.json"
    data = json.loads(sp.read_text(encoding="utf-8"))
    # Cambiar el src de la imagen a una URL externa
    data["topics"][0]["subsections"][0]["blocks"][1]["extras"]["src"] = "https://example.com/foto.jpg"
    sp.write_text(json.dumps(data), encoding="utf-8")
    r = client.get(f"/curso/{token}/editar")
    html = r.data.decode("utf-8")
    # En este curso ya no hay ed-alt-ia (porque solo había una imagen y es URL externa)
    # Lo verificamos buscando que ese filename concreto NO tenga botón asociado
    assert 'data-filename="https://example.com/foto.jpg"' not in html


def test_modal_css_presente(app_test):
    """Las clases del modal WCAG/preview están en el CSS del editor."""
    client = app_test.app.test_client()
    _register_and_login(client, email="p4p@t.local")
    token, _ = _create_course(app_test, email="p4p@t.local")
    r = client.get(f"/curso/{token}/editar")
    html = r.data.decode("utf-8")
    assert ".ed-modal-overlay" in html
    assert ".ed-modal-card" in html
    assert ".wcag-error" in html
    assert "showWcagModal" in html
    assert "showPreviewModal" in html

"""Smoke test de la UI Fase 3 (panel de tags + asistente IA).

Arranca el app_local en modo test sin abrir navegador. Crea un usuario,
sube un curso, edita y verifica que la página de edición contiene la
nueva UI de tags + asistente avanzado.
"""
import io
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
INSTALADOR = ROOT / "instalador"
sys.path.insert(0, str(INSTALADOR))


@pytest.fixture(scope="module")
def app_test():
    """Configura el app en modo test con SQLite temporal."""
    tmpdir = Path(tempfile.mkdtemp(prefix="scormtest_"))
    os.environ["SCORM_BUILDER_WORK_DIR"] = str(tmpdir)
    # Limpiar el módulo si ya estaba importado
    if "app_local" in sys.modules:
        del sys.modules["app_local"]
    import app_local
    app_local.app.config["TESTING"] = True
    app_local.app.config["WTF_CSRF_ENABLED"] = False
    yield app_local
    # Cleanup
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


def _register_and_login(client, email="test@test.local", password="testpass123"):
    """Registra y loguea un usuario, devuelve el cliente con la sesión abierta."""
    client.post("/register", data={
        "email": email, "password": password, "password2": password,
        "name": "Test User",
    }, follow_redirects=True)
    r = client.post("/login", data={
        "email": email, "password": password,
    }, follow_redirects=False)
    assert r.status_code in (200, 302), f"Login devolvió {r.status_code}"


def _create_course_directly(app_test, email="test@test.local"):
    """Crea un curso directamente en la BD y un structure.json mínimo,
    saltándose el flujo de upload (que requiere ejecutar build completo)."""
    import sqlite3, uuid
    from datetime import datetime
    # Localizar al usuario
    with app_test.db() as conn:
        user = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    assert user
    uid = user["id"]
    udir = app_test.user_dir(uid)
    token = "test_" + uuid.uuid4().hex[:8]
    job_dir = udir / f"job_{token}"
    job_dir.mkdir(parents=True, exist_ok=True)
    # Estructura mínima válida con tags
    structure = {
        "metadata": {"title": "Curso test", "author": "T", "subtitle": "", "sector": "",
                     "palette": "azul", "mastery": 70, "weight_view": 40, "weight_quiz": 60,
                     "view_min_seconds": 10, "view_strategy": "both"},
        "topics": [{
            "number": 1, "title": "Tema 1", "intro": "Intro",
            "tags": ["normativa", "deportes"],
            "subsections": [{
                "id": "l1", "number": "1.1", "title": "Sub 1.1",
                "blocks": [{"type": "paragraph", "text": "Texto",
                           "items": [], "rows": [], "extras": {}}],
            }],
            "quiz": [],
            "inline_quiz": {},
        }],
        "warnings": [],
    }
    (job_dir / "structure.json").write_text(json.dumps(structure), encoding="utf-8")
    # ZIP vacío de placeholder (la UI no lo lee para editar)
    zip_path = job_dir / "curso.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("index.html", "<html/>")
    # Insertar en BD
    from datetime import datetime
    with app_test.db() as conn:
        conn.execute(
            "INSERT INTO courses (user_id, token, title, zip_path, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (uid, token, "Curso test", str(zip_path), datetime.utcnow().isoformat()),
        )
        conn.commit()
    return token


def test_editor_muestra_panel_tags(app_test):
    """El editor renderiza el bloque de tags con sus chips, input y botón IA."""
    client = app_test.app.test_client()
    _register_and_login(client)
    token = _create_course_directly(app_test)
    r = client.get(f"/curso/{token}/editar")
    assert r.status_code == 200
    html = r.data.decode("utf-8")
    # Chips + input + botón
    assert "ed-tags-block" in html
    assert "ed-tag-input" in html
    assert 'data-topic-ai="tags"' in html
    assert "Generar tags con IA" in html


def test_editor_muestra_panel_asistente_avanzado(app_test):
    """El panel colapsable de Asistente IA avanzado está presente."""
    client = app_test.app.test_client()
    _register_and_login(client, email="test2@test.local")
    token = _create_course_directly(app_test, email="test2@test.local")
    r = client.get(f"/curso/{token}/editar")
    assert r.status_code == 200
    html = r.data.decode("utf-8")
    assert "ed-ai-advanced" in html
    assert "Asistente IA avanzado" in html
    assert "ed-quiz-config" in html
    # Tres tipos de pregunta
    assert 'value="multiple_choice"' in html
    assert 'value="true_false"' in html
    assert 'value="fill_in"' in html
    # Las tres ubicaciones
    assert 'value="final"' in html
    assert 'value="per_subsection"' in html
    assert 'value="mixed"' in html


def test_editor_muestra_botones_globales_nuevos(app_test):
    """Los botones globales de IMS CP y Aiken extendido están en la barra de acciones."""
    client = app_test.app.test_client()
    _register_and_login(client, email="test3@test.local")
    token = _create_course_directly(app_test, email="test3@test.local")
    r = client.get(f"/curso/{token}/editar")
    assert r.status_code == 200
    html = r.data.decode("utf-8")
    assert 'id="ed-aiken-ext"' in html
    assert 'id="ed-export-imscp"' in html
    assert "Banco Aiken extendido" in html
    assert "Exportar como IMS CP" in html


def test_handler_js_tags_presente(app_test):
    """El JS para gestionar tags (añadir, borrar, generar IA) está presente."""
    client = app_test.app.test_client()
    _register_and_login(client, email="test4@test.local")
    token = _create_course_directly(app_test, email="test4@test.local")
    r = client.get(f"/curso/{token}/editar")
    html = r.data.decode("utf-8")
    # Handlers del JS
    assert "ed-tag-del" in html  # selector + clase
    assert 'data-topic-ai="quiz-config"' in html
    assert "/api/curso/" in html
    assert "ai-tags" in html  # endpoint usado
    assert "ai-quiz-config" in html


def test_ruta_descarga_imscp_responde(app_test):
    """La ruta de descarga /export/imscp existe (404 si no hay archivo, no 405)."""
    client = app_test.app.test_client()
    _register_and_login(client, email="test5@test.local")
    token = _create_course_directly(app_test, email="test5@test.local")
    # Sin haber generado el IMS CP, debe responder 404 (no 405 = método no permitido)
    r = client.get(f"/curso/{token}/export/imscp")
    assert r.status_code == 404  # archivo no existe aún


def test_ruta_descarga_aiken_ext_responde(app_test):
    """La ruta de descarga /export/aiken-ext existe."""
    client = app_test.app.test_client()
    _register_and_login(client, email="test6@test.local")
    token = _create_course_directly(app_test, email="test6@test.local")
    r = client.get(f"/curso/{token}/export/aiken-ext")
    assert r.status_code == 404


def test_ruta_descarga_kind_invalido_404(app_test):
    """Una kind inventada debe dar 404."""
    client = app_test.app.test_client()
    _register_and_login(client, email="test7@test.local")
    token = _create_course_directly(app_test, email="test7@test.local")
    r = client.get(f"/curso/{token}/export/inventado")
    assert r.status_code == 404


def test_endpoint_ai_tags_sin_apikey_devuelve_400(app_test):
    """Sin ANTHROPIC_API_KEY, el endpoint ai-tags responde 400 y NO crashea."""
    client = app_test.app.test_client()
    _register_and_login(client, email="test8@test.local")
    token = _create_course_directly(app_test, email="test8@test.local")
    # Desactivar API key (puede estar en .env del developer)
    old_key = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        r = client.post(f"/api/curso/{token}/ai-tags",
                        json={"topic_index": 0, "n": 5})
        assert r.status_code == 400
        data = r.get_json()
        assert "ANTHROPIC_API_KEY" in data.get("error", "")
    finally:
        if old_key:
            os.environ["ANTHROPIC_API_KEY"] = old_key


def test_endpoint_export_imscp_genera_zip(app_test):
    """El endpoint export-imscp genera realmente el ZIP en la carpeta del curso."""
    client = app_test.app.test_client()
    _register_and_login(client, email="test9@test.local")
    token = _create_course_directly(app_test, email="test9@test.local")
    r = client.post(f"/api/curso/{token}/export-imscp")
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("ok") is True
    assert data.get("filename") == "curso_imscp.zip"
    # Y ahora la descarga sí responde 200
    r2 = client.get(f"/curso/{token}/export/imscp")
    assert r2.status_code == 200
    assert r2.headers["Content-Type"].startswith("application/zip")

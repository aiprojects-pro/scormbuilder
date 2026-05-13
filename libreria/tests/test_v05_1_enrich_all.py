"""Tests v0.5.1: endpoint /ai-enrich-all + banner UI."""
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
    tmpdir = Path(tempfile.mkdtemp(prefix="scormtest_v051_"))
    os.environ["SCORM_BUILDER_WORK_DIR"] = str(tmpdir)
    if "app_local" in sys.modules:
        del sys.modules["app_local"]
    import app_local
    app_local.app.config["TESTING"] = True
    yield app_local
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


def _register_and_login(client, email="v51@t.local", password="testpass123"):
    client.post("/register", data={
        "email": email, "password": password, "password2": password, "name": "V51",
    }, follow_redirects=True)
    client.post("/login", data={"email": email, "password": password})


def _create_course(app_test, email="v51@t.local"):
    import uuid
    with app_test.db() as conn:
        user = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    uid = user["id"]
    udir = app_test.user_dir(uid)
    token = "v51_" + uuid.uuid4().hex[:8]
    job_dir = udir / f"job_{token}"
    job_dir.mkdir(parents=True, exist_ok=True)
    structure = {
        "metadata": {"title": "C", "author": "T", "subtitle": "", "sector": "",
                     "palette": "azul", "mastery": 70, "weight_view": 40,
                     "weight_quiz": 60, "view_min_seconds": 10, "view_strategy": "both"},
        "topics": [{
            "number": 1, "title": "Tema",
            "intro": "Intro",
            "tags": [],
            "subsections": [{
                "id": "l1", "number": "1.1", "title": "Sub",
                "blocks": [
                    {"type": "paragraph", "text": "Texto.",
                     "items": [], "rows": [], "extras": {}},
                ],
            }],
            "quiz": [], "inline_quiz": {},
        }],
        "warnings": [],
    }
    (job_dir / "structure.json").write_text(json.dumps(structure), encoding="utf-8")
    zp = job_dir / "curso.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.writestr("index.html", "<html/>")
    with app_test.db() as conn:
        conn.execute(
            "INSERT INTO courses (user_id, token, title, zip_path, created_at) VALUES (?,?,?,?,?)",
            (uid, token, "C", str(zp), datetime.utcnow().isoformat()))
        conn.commit()
    return token, job_dir


def test_editor_muestra_banner_enrich_all(app_test):
    """El banner aparece visible en el editor con su botón."""
    client = app_test.app.test_client()
    _register_and_login(client, email="v51a@t.local")
    token, _ = _create_course(app_test, email="v51a@t.local")
    r = client.get(f"/curso/{token}/editar")
    html = r.data.decode("utf-8")
    assert "ed-enrich-banner" in html
    assert 'id="ed-enrich-all"' in html
    assert "Aplicar mejoras IA al curso completo" in html
    assert "¿Primera vez en el editor?" in html


def test_endpoint_enrich_all_sin_apikey(app_test):
    """Sin clave devuelve 400 con mensaje claro."""
    client = app_test.app.test_client()
    _register_and_login(client, email="v51b@t.local")
    token, _ = _create_course(app_test, email="v51b@t.local")
    old = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        r = client.post(f"/api/curso/{token}/ai-enrich-all")
        assert r.status_code == 400
        assert "ANTHROPIC_API_KEY" in r.get_json().get("error", "")
    finally:
        if old:
            os.environ["ANTHROPIC_API_KEY"] = old


def test_endpoint_enrich_all_token_invalido(app_test, monkeypatch):
    """Token inexistente devuelve 404."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
    client = app_test.app.test_client()
    _register_and_login(client, email="v51c@t.local")
    r = client.post("/api/curso/inexistente/ai-enrich-all")
    assert r.status_code == 404


def test_endpoint_enrich_all_no_destructivo_sin_red(app_test, monkeypatch):
    """Con clave pero sin red (la llamada falla), debe:
       - Crear snapshot previa
       - No corromper structure.json (que sigue parseable)
       - Devolver errores en summary"""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake-no-network")
    client = app_test.app.test_client()
    _register_and_login(client, email="v51d@t.local")
    token, job_dir = _create_course(app_test, email="v51d@t.local")
    # Monkeypatch las funciones IA para que devuelvan None (simulando fallo de red)
    import scorm_builder.ai_assist as ai
    monkeypatch.setattr(ai, "generate_tags", lambda *a, **k: None)
    monkeypatch.setattr(ai, "enrich_topic_with_callouts", lambda *a, **k: None)
    monkeypatch.setattr(ai, "generate_quiz", lambda *a, **k: None)
    r = client.post(f"/api/curso/{token}/ai-enrich-all")
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    # Snapshot creada aunque no haya pasado nada
    assert data["snapshot_id"]
    # Nada aplicado pero estructura intacta
    assert data["summary"]["tags_generated"] == 0
    assert data["summary"]["callouts_applied"] == 0
    assert data["summary"]["quiz_final_generated"] == 0
    # structure.json sigue parseable y con su contenido
    s = json.loads((job_dir / "structure.json").read_text(encoding="utf-8"))
    assert s["topics"][0]["tags"] == []  # no se rellenó porque la IA falló


def test_endpoint_enrich_all_aplica_tags_y_callouts(app_test, monkeypatch):
    """Con IA simulada que sí devuelve resultados, se aplican y se persisten."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
    client = app_test.app.test_client()
    _register_and_login(client, email="v51e@t.local")
    token, job_dir = _create_course(app_test, email="v51e@t.local")
    # Mock: tags fija + 1 sugerencia válida de enrich
    import scorm_builder.ai_assist as ai
    monkeypatch.setattr(ai, "generate_tags",
        lambda topic, n=6: ["tag uno", "tag dos", "tag tres"])
    monkeypatch.setattr(ai, "enrich_topic_with_callouts",
        lambda topic: {"suggestions": [{
            "subsection_id": "l1",
            "block_index": 0,
            "current_type": "paragraph",
            "suggested_type": "callout_key",
            "current_text": "Texto.",
            "suggested_text": "Esto es ahora un callout clave.",
            "reason": "Definición central",
        }], "truncated": False})
    monkeypatch.setattr(ai, "generate_quiz", lambda *a, **k: None)

    r = client.post(f"/api/curso/{token}/ai-enrich-all")
    assert r.status_code == 200
    data = r.get_json()
    assert data["summary"]["tags_generated"] == 3
    assert data["summary"]["callouts_applied"] == 1

    # Verificar persistencia
    s = json.loads((job_dir / "structure.json").read_text(encoding="utf-8"))
    assert s["topics"][0]["tags"] == ["tag uno", "tag dos", "tag tres"]
    block = s["topics"][0]["subsections"][0]["blocks"][0]
    assert block["type"] == "callout_key"
    assert block["text"] == "Esto es ahora un callout clave."
    # Snapshot creada antes de tocar
    snaps = list((job_dir / "snapshots").glob("*.json"))
    assert len(snaps) == 1


def test_endpoint_enrich_all_respeta_tags_existentes(app_test, monkeypatch):
    """Si el tema ya tiene tags, no los sobrescribe."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
    client = app_test.app.test_client()
    _register_and_login(client, email="v51f@t.local")
    token, job_dir = _create_course(app_test, email="v51f@t.local")
    # Pre-poblar tags
    sp = job_dir / "structure.json"
    s = json.loads(sp.read_text(encoding="utf-8"))
    s["topics"][0]["tags"] = ["ya tengo tags"]
    sp.write_text(json.dumps(s), encoding="utf-8")

    import scorm_builder.ai_assist as ai
    # Si la IA llegase a llamarse, devolvería otros tags; pero no debe llamarse
    monkeypatch.setattr(ai, "generate_tags",
        lambda *a, **k: ["otros", "tags", "distintos"])
    monkeypatch.setattr(ai, "enrich_topic_with_callouts",
        lambda topic: {"suggestions": [], "truncated": False})
    monkeypatch.setattr(ai, "generate_quiz", lambda *a, **k: None)

    client.post(f"/api/curso/{token}/ai-enrich-all")
    s2 = json.loads(sp.read_text(encoding="utf-8"))
    # Tags preexistentes se respetan
    assert s2["topics"][0]["tags"] == ["ya tengo tags"]


def test_endpoint_enrich_all_resumen_por_tema(app_test, monkeypatch):
    """El resumen incluye detalle por tema."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
    client = app_test.app.test_client()
    _register_and_login(client, email="v51g@t.local")
    token, _ = _create_course(app_test, email="v51g@t.local")
    import scorm_builder.ai_assist as ai
    monkeypatch.setattr(ai, "generate_tags", lambda *a, **k: ["a", "b"])
    monkeypatch.setattr(ai, "enrich_topic_with_callouts",
        lambda topic: {"suggestions": [], "truncated": False})
    monkeypatch.setattr(ai, "generate_quiz", lambda *a, **k: None)
    r = client.post(f"/api/curso/{token}/ai-enrich-all")
    data = r.get_json()
    assert "details" in data
    assert len(data["details"]) == 1
    assert data["details"][0]["topic"] == 1
    assert data["details"][0]["tags"] == 2


def test_endpoint_enrich_all_genera_quiz_mixto_si_pocas_pregs(app_test, monkeypatch):
    """Si el tema tiene < 3 preguntas, el endpoint genera quiz mixto."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
    client = app_test.app.test_client()
    _register_and_login(client, email="v51h@t.local")
    token, job_dir = _create_course(app_test, email="v51h@t.local")
    # El curso de test tiene quiz=[] (0 preguntas, < 3), debe generar
    import scorm_builder.ai_assist as ai
    monkeypatch.setattr(ai, "generate_tags", lambda *a, **k: None)
    monkeypatch.setattr(ai, "enrich_topic_with_callouts",
        lambda topic: {"suggestions": [], "truncated": False})
    monkeypatch.setattr(ai, "generate_quiz", lambda topic, config=None: {
        "final": [
            {"qtype": "multiple_choice", "text": "Q1", "options": ["A","B","C","D"], "correct_index": 0, "explanation": "."},
            {"qtype": "true_false", "text": "Q2", "options": ["Verdadero","Falso"], "correct_index": 0, "explanation": "."},
            {"qtype": "fill_in", "text": "Q3 ___", "options": ["a","b","c","d"], "correct_index": 0, "explanation": "."},
        ],
        "by_subsection": {"l1": [
            {"qtype": "multiple_choice", "text": "Inline", "options": ["A","B"], "correct_index": 0, "explanation": "."},
        ]},
    })
    r = client.post(f"/api/curso/{token}/ai-enrich-all")
    assert r.status_code == 200
    data = r.get_json()
    assert data["summary"]["quiz_final_generated"] == 3
    assert data["summary"]["quiz_inline_generated"] == 1
    # Verificar persistencia
    s = json.loads((job_dir / "structure.json").read_text(encoding="utf-8"))
    assert len(s["topics"][0]["quiz"]) == 3
    assert len(s["topics"][0]["inline_quiz"]["l1"]) == 1


def test_endpoint_enrich_all_no_machaca_quiz_existente(app_test, monkeypatch):
    """Si el tema ya tiene 3+ preguntas, no genera quiz nuevo."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
    client = app_test.app.test_client()
    _register_and_login(client, email="v51i@t.local")
    token, job_dir = _create_course(app_test, email="v51i@t.local")
    # Pre-poblar quiz con 3 preguntas
    sp = job_dir / "structure.json"
    s = json.loads(sp.read_text(encoding="utf-8"))
    s["topics"][0]["quiz"] = [
        {"qtype": "multiple_choice", "text": f"Manual {i}",
         "options": ["A","B","C","D"], "correct_index": 0, "explanation": "."}
        for i in range(3)
    ]
    sp.write_text(json.dumps(s), encoding="utf-8")

    import scorm_builder.ai_assist as ai
    monkeypatch.setattr(ai, "generate_tags", lambda *a, **k: None)
    monkeypatch.setattr(ai, "enrich_topic_with_callouts",
        lambda topic: {"suggestions": [], "truncated": False})
    # generate_quiz no debe ser llamada; si lo es, devolvería cosa distinta
    called = {"count": 0}
    def mock_quiz(*a, **k):
        called["count"] += 1
        return {"final": [{"qtype":"multiple_choice","text":"NEW","options":["A","B"],"correct_index":0}], "by_subsection": {}}
    monkeypatch.setattr(ai, "generate_quiz", mock_quiz)

    r = client.post(f"/api/curso/{token}/ai-enrich-all")
    assert r.status_code == 200
    # Quiz preservado
    s2 = json.loads(sp.read_text(encoding="utf-8"))
    assert len(s2["topics"][0]["quiz"]) == 3
    assert s2["topics"][0]["quiz"][0]["text"] == "Manual 0"
    # Y generate_quiz no se ha llamado (el endpoint corta antes)
    assert called["count"] == 0


def test_endpoint_enrich_all_fusiona_inline_quiz(app_test, monkeypatch):
    """Si el subapartado ya tenía inline_quiz manual, se preserva (no se machaca)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
    client = app_test.app.test_client()
    _register_and_login(client, email="v51j@t.local")
    token, job_dir = _create_course(app_test, email="v51j@t.local")
    # Pre-poblar inline_quiz manual
    sp = job_dir / "structure.json"
    s = json.loads(sp.read_text(encoding="utf-8"))
    s["topics"][0]["inline_quiz"] = {
        "l1": [{"qtype": "true_false", "text": "Manual inline",
                "options": ["Verdadero","Falso"], "correct_index": 0, "explanation": "."}]
    }
    sp.write_text(json.dumps(s), encoding="utf-8")

    import scorm_builder.ai_assist as ai
    monkeypatch.setattr(ai, "generate_tags", lambda *a, **k: None)
    monkeypatch.setattr(ai, "enrich_topic_with_callouts",
        lambda topic: {"suggestions": [], "truncated": False})
    monkeypatch.setattr(ai, "generate_quiz", lambda *a, **k: {
        "final": [],
        "by_subsection": {"l1": [
            {"qtype":"multiple_choice","text":"IA inline","options":["A","B"],"correct_index":0}
        ]},
    })

    client.post(f"/api/curso/{token}/ai-enrich-all")
    s2 = json.loads(sp.read_text(encoding="utf-8"))
    # El inline_quiz manual de l1 se preserva (no se machaca)
    assert len(s2["topics"][0]["inline_quiz"]["l1"]) == 1
    assert s2["topics"][0]["inline_quiz"]["l1"][0]["text"] == "Manual inline"

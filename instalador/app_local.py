"""SCORM Builder · App web con cuentas y galería.

Mejora de v0.2:
  - Usuarios (registro / login / logout) basado en sesiones de Flask.
  - Subida de varios archivos a la vez: el .docx principal + cualquier número
    de imágenes, vídeos, audios, PDFs adicionales.
  - Cada usuario tiene SU panel de "Mis cursos" donde ver, redescargar o
    eliminar todos los cursos generados (galería de descargas).
  - Trabajo simultáneo: cada job se almacena con su propietario; varios
    usuarios pueden generar a la vez sin interferir.

La app sigue siendo 100% local (sin servicios externos), solo expone un
servidor en localhost:5000. El almacén es SQLite + sistema de archivos.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import threading
import uuid
import webbrowser
import zipfile
from datetime import datetime
from functools import wraps
from html import escape as html_escape
from pathlib import Path

from flask import (
    Flask, abort, flash, jsonify, redirect, render_template_string,
    request, send_file, session, url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from scorm_builder.api import build_complete_course
from scorm_builder.themes import THEMES


# ============================================================
# Configuración
# ============================================================
APP_DIR = Path(os.environ.get("SCORM_BUILDER_WORK_DIR", Path.home() / "Documentos" / "ScormBuilder"))
APP_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = APP_DIR / "scormbuilder.sqlite3"
USERS_DIR = APP_DIR / "users"
USERS_DIR.mkdir(parents=True, exist_ok=True)

# Tipos MIME aceptados para recursos adicionales
ALLOWED_RESOURCE_EXT = {
    # Imágenes
    "png", "jpg", "jpeg", "gif", "svg", "webp",
    # Vídeo
    "mp4", "webm", "ogv", "mov", "m4v",
    # Audio
    "mp3", "wav", "ogg", "m4a", "aac",
    # Subtítulos
    "vtt", "srt",
    # Documentos
    "pdf", "txt", "csv", "xlsx", "xls", "pptx", "ppt", "doc", "docx",
    # Otros
    "zip", "json", "xml",
}

MAX_TOTAL_UPLOAD_MB = 500  # límite total por petición


# ============================================================
# Aplicación Flask
# ============================================================
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_TOTAL_UPLOAD_MB * 1024 * 1024
# Clave de sesión: persistente entre arranques en la carpeta del usuario
_secret_path = APP_DIR / ".session_key"
if not _secret_path.exists():
    _secret_path.write_bytes(os.urandom(32))
app.secret_key = _secret_path.read_bytes()


# ============================================================
# Base de datos (SQLite, sin dependencias externas)
# ============================================================
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            display_name TEXT,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            author TEXT,
            num_topics INTEGER,
            num_questions INTEGER,
            num_pdfs INTEGER,
            num_aiken INTEGER,
            num_resources INTEGER,
            zip_path TEXT NOT NULL,
            zip_size INTEGER,
            warnings_json TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """)


init_db()


# ============================================================
# Helpers de auth
# ============================================================
def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    with db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        return dict(row) if row else None


def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not current_user():
            if request.path.startswith("/api/"):
                return jsonify({"error": "Necesitas iniciar sesión"}), 401
            return redirect(url_for("login", next=request.path))
        return f(*a, **kw)
    return wrapper


def user_dir(user_id: int) -> Path:
    d = USERS_DIR / f"u{user_id}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _allowed_file(filename: str, allowed: set) -> bool:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in allowed


# ============================================================
# Plantillas (HTML)
# ============================================================
BASE_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --ink: #0F172A; --ink-soft: #1E293B; --ink-mute: #475569;
  --paper: #F8FAFC; --paper-warm: #F1F5F9; --paper-deep: #E2E8F0;
  --primary-deep: #0A2540; --primary: #1D4ED8; --primary-bright: #2563EB;
  --primary-pale: #DBEAFE; --primary-mist: #EFF6FF;
  --ok: #059669; --warn: #D97706; --alert: #DC2626;
}
html { scroll-behavior: smooth; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  background: var(--paper); color: var(--ink); line-height: 1.6; min-height: 100vh;
}
a { color: var(--primary); text-decoration: none; }
a:hover { color: var(--primary-deep); text-decoration: underline; }
header.topbar {
  background: var(--primary-deep); color: white; padding: 1rem 0;
  border-bottom: 4px solid var(--primary-bright); position: sticky; top: 0; z-index: 100;
}
.topbar .inner {
  max-width: 1100px; margin: 0 auto; padding: 0 2rem;
  display: flex; justify-content: space-between; align-items: center; gap: 1rem;
}
.topbar h1 {
  font-size: 1.2rem; font-weight: 700; letter-spacing: -0.01em;
  display: flex; align-items: center; gap: 0.6rem;
}
.topbar h1 a { color: white; }
.topbar h1 a:hover { text-decoration: none; opacity: 0.9; }
.topbar .badge {
  background: var(--primary-bright); padding: 0.15rem 0.5rem; border-radius: 4px;
  font-size: 0.7rem; font-weight: 700; letter-spacing: 0.08em;
}
.topbar nav { display: flex; gap: 1rem; align-items: center; font-size: 0.95rem; }
.topbar nav a { color: var(--primary-pale); }
.topbar nav a:hover { color: white; text-decoration: none; }
.topbar nav a.active { color: white; font-weight: 600; }
.topbar .user-chip {
  background: rgba(255,255,255,0.1); padding: 0.4rem 0.85rem;
  border-radius: 20px; font-size: 0.85rem;
}
main { max-width: 1100px; margin: 2rem auto; padding: 0 2rem 4rem; }
.card {
  background: white; border-radius: 12px; padding: 2rem; margin-bottom: 1.5rem;
  box-shadow: 0 2px 12px rgba(10,37,64,0.06);
}
.card h2 {
  font-size: 1.2rem; color: var(--primary-deep); margin-bottom: 1rem;
  display: flex; align-items: center; gap: 0.6rem;
}
.card h2 .num {
  background: var(--primary-bright); color: white; width: 28px; height: 28px;
  border-radius: 50%; display: inline-flex; align-items: center; justify-content: center;
  font-size: 0.85rem; font-weight: 700;
}
.field { margin-bottom: 1rem; }
.field label {
  display: block; font-size: 0.85rem; font-weight: 600;
  color: var(--ink-mute); margin-bottom: 0.4rem;
}
.field input[type="text"], .field input[type="email"], .field input[type="password"],
.field input[type="number"], .field select, .field textarea {
  width: 100%; padding: 0.7rem 0.9rem; border: 1.5px solid var(--paper-deep);
  border-radius: 8px; font-size: 0.95rem; font-family: inherit; background: white;
}
.field input:focus, .field select:focus, .field textarea:focus {
  outline: none; border-color: var(--primary-bright);
}
.field input[type="color"] {
  width: 100%; height: 44px; border: 1.5px solid var(--paper-deep);
  border-radius: 8px; cursor: pointer; padding: 4px;
}
.row { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
@media (max-width: 600px) { .row { grid-template-columns: 1fr; } }
.btn {
  background: var(--primary-deep); color: white; border: none;
  padding: 0.85rem 1.6rem; border-radius: 8px; font-family: inherit;
  font-weight: 600; font-size: 0.95rem; cursor: pointer; transition: all 0.15s;
  display: inline-block; text-decoration: none;
}
.btn:hover:not(:disabled) {
  background: var(--primary-bright); transform: translateY(-1px);
  text-decoration: none; color: white;
}
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn.full { width: 100%; padding: 1rem; }
.btn.secondary { background: var(--paper-warm); color: var(--ink); border: 1.5px solid var(--paper-deep); }
.btn.secondary:hover:not(:disabled) { background: var(--paper-deep); color: var(--ink); }
.btn.danger { background: var(--alert); }
.btn.danger:hover:not(:disabled) { background: #B91C1C; }
.flash {
  padding: 0.85rem 1.1rem; border-radius: 8px; margin-bottom: 1.5rem;
  font-size: 0.92rem;
}
.flash.success { background: #ECFDF5; color: #064E3B; border-left: 4px solid var(--ok); }
.flash.error { background: #FEF2F2; color: #7F1D1D; border-left: 4px solid var(--alert); }
.flash.info { background: var(--primary-mist); color: var(--primary-deep); border-left: 4px solid var(--primary-bright); }
"""


def render_page(title, body, user=None, active=""):
    user_chip = ""
    nav_links = ""
    if user:
        user_chip = f'<span class="user-chip">👤 {user.get("display_name") or user["email"]}</span>'
        active_home = ' class="active"' if active == "home" else ""
        active_lib = ' class="active"' if active == "library" else ""
        nav_links = f'''
            <a href="/"{active_home}>Generar</a>
            <a href="/biblioteca"{active_lib}>Mis cursos</a>
            <a href="/logout">Salir</a>
        '''
    else:
        active_login = ' class="active"' if active == "login" else ""
        active_reg = ' class="active"' if active == "register" else ""
        nav_links = f'''
            <a href="/login"{active_login}>Iniciar sesión</a>
            <a href="/register"{active_reg}>Registrarse</a>
        '''

    flashes = ""
    for cat, msg in get_flashed():
        flashes += f'<div class="flash {cat}">{msg}</div>'

    return render_template_string(f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} · SCORM Builder</title>
<style>{BASE_CSS}{{{{ extra_css|safe }}}}</style>
</head>
<body>
<header class="topbar">
  <div class="inner">
    <h1><a href="/">SCORM Builder</a> <span class="badge">v0.5.1</span></h1>
    <nav>
      {nav_links}
      {user_chip}
    </nav>
  </div>
</header>
<main>
  {flashes}
  {body}
</main>
</body>
</html>""", extra_css="")


def get_flashed():
    """Lee y limpia los mensajes flash de la sesión."""
    flashes = []
    raw = session.pop("_flashes", None) or []
    for cat, msg in raw:
        flashes.append((cat, msg))
    return flashes


def push_flash(category, message):
    flashes = session.get("_flashes", [])
    flashes.append((category, message))
    session["_flashes"] = flashes


# ============================================================
# Rutas: AUTH
# ============================================================
LOGIN_BODY = """
<div class="card" style="max-width: 460px; margin: 3rem auto;">
  <h2>Iniciar sesión</h2>
  <form method="post">
    <div class="field">
      <label for="email">Email</label>
      <input type="email" id="email" name="email" required autofocus>
    </div>
    <div class="field">
      <label for="password">Contraseña</label>
      <input type="password" id="password" name="password" required>
    </div>
    <button type="submit" class="btn full">Entrar</button>
  </form>
  <p style="margin-top: 1.2rem; font-size: 0.9rem; color: var(--ink-mute); text-align: center;">
    ¿No tienes cuenta? <a href="/register">Regístrate gratis</a>
  </p>
</div>
"""

REGISTER_BODY = """
<div class="card" style="max-width: 460px; margin: 3rem auto;">
  <h2>Crear cuenta</h2>
  <form method="post">
    <div class="field">
      <label for="display_name">Tu nombre o entidad</label>
      <input type="text" id="display_name" name="display_name" placeholder="P. ej. María Pérez" required autofocus>
    </div>
    <div class="field">
      <label for="email">Email</label>
      <input type="email" id="email" name="email" required>
    </div>
    <div class="field">
      <label for="password">Contraseña (mínimo 6 caracteres)</label>
      <input type="password" id="password" name="password" minlength="6" required>
    </div>
    <button type="submit" class="btn full">Crear cuenta</button>
  </form>
  <p style="margin-top: 1.2rem; font-size: 0.9rem; color: var(--ink-mute); text-align: center;">
    ¿Ya tienes cuenta? <a href="/login">Inicia sesión</a>
  </p>
</div>
"""


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not email or not password:
            push_flash("error", "Email y contraseña son obligatorios.")
            return render_page("Iniciar sesión", LOGIN_BODY, active="login")
        with db() as conn:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not row or not check_password_hash(row["password_hash"], password):
            push_flash("error", "Email o contraseña incorrectos.")
            return render_page("Iniciar sesión", LOGIN_BODY, active="login")
        session["user_id"] = row["id"]
        push_flash("success", f"Bienvenido/a {row['display_name'] or row['email']}.")
        nxt = request.args.get("next", "/")
        if not nxt.startswith("/"):
            nxt = "/"
        return redirect(nxt)
    return render_page("Iniciar sesión", LOGIN_BODY, active="login")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        display_name = request.form.get("display_name", "").strip() or None
        if not email or not password or len(password) < 6:
            push_flash("error", "Email obligatorio y contraseña con mínimo 6 caracteres.")
            return render_page("Registrarse", REGISTER_BODY, active="register")
        with db() as conn:
            existing = conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
            if existing:
                push_flash("error", "Ya existe una cuenta con ese email.")
                return render_page("Registrarse", REGISTER_BODY, active="register")
            cur = conn.execute(
                "INSERT INTO users (email, display_name, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (email, display_name, generate_password_hash(password), datetime.utcnow().isoformat()),
            )
            conn.commit()
            user_id = cur.lastrowid
        session["user_id"] = user_id
        user_dir(user_id)  # crear carpeta
        push_flash("success", "Cuenta creada. ¡Empieza a generar tu primer curso!")
        return redirect("/")
    return render_page("Registrarse", REGISTER_BODY, active="register")


@app.route("/logout")
def logout():
    session.clear()
    push_flash("info", "Sesión cerrada.")
    return redirect("/login")


# ============================================================
# Rutas: PÁGINA PRINCIPAL (formulario de generación)
# ============================================================
HOME_BODY_TEMPLATE = """
<form id="form">

  <!-- Bloque 0: Cabecera del curso (UBICACIÓN PROMINENTE) -->
  <div class="card card-hero">
    <h2 style="margin-bottom:0.3rem;">Crear un nuevo curso</h2>
    <p style="color:var(--ink-mute); font-size:0.95rem; margin-bottom:1.4rem;">
      Rellena los datos del curso. Luego eliges los archivos Word, la versión de SCORM y los extras.
    </p>
    <div class="row">
      <div class="field" style="flex:2;">
        <label for="titulo">Título del curso *</label>
        <input type="text" id="titulo" name="titulo" placeholder="P. ej. Gestor Deportivo · Bloque 1" required>
        <span class="hint">Aparece en la cabecera del paquete y en el LMS.</span>
      </div>
      <div class="field">
        <label for="num_hours">Duración (horas)</label>
        <input type="number" id="num_hours" name="num_hours" value="20" min="1" max="999" step="0.5">
        <span class="hint">Total estimado de horas del curso.</span>
      </div>
      <div class="field">
        <label for="autor">Autor / entidad</label>
        <input type="text" id="autor" name="autor" placeholder="Tu nombre o asociación">
      </div>
    </div>
  </div>

  <!-- Bloque 1: Modo de subida -->
  <div class="card">
    <h2><span class="num">1</span> ¿Cómo subes el contenido?</h2>
    <div class="radio-cards" data-name="upload_mode">
      <label class="radio-card selected" data-value="single">
        <input type="radio" name="upload_mode" value="single" checked>
        <div class="rc-title">📄 Un único archivo Word</div>
        <div class="rc-desc">Subes un .docx y se genera <strong>un paquete SCORM</strong>.
          Recomendado para cursos cortos o cuando todo el contenido cabe en un solo documento.</div>
      </label>
      <label class="radio-card" data-value="batch">
        <input type="radio" name="upload_mode" value="batch">
        <div class="rc-title">📚 Varios archivos (lote)</div>
        <div class="rc-desc">Subes varios .docx a la vez. Se genera <strong>un SCORM por archivo</strong>,
          usando el nombre del fichero como título del paquete. Ideal para temarios largos
          con un tema por unidad.</div>
      </label>
    </div>
  </div>

  <!-- Bloque 2: Documento(s) Word -->
  <div class="card">
    <h2><span class="num">2</span> Sube tus documentos Word</h2>
    <div class="upload-zone" id="docxZone">
      <div class="icon">📄</div>
      <div class="text" id="docxZoneText">Haz clic o arrastra aquí tu archivo <strong>.docx</strong></div>
      <div class="filename" id="docxFilename"></div>
    </div>
    <input type="file" id="docx" name="docx" accept=".docx" required>
    <ul class="reslist" id="docxBatchList" style="display:none;"></ul>
    <p class="hint" id="docxHint" style="margin-top:0.6rem;">
      Solo se acepta <code>.docx</code>. Si el documento sigue la plantilla del proyecto,
      detectaremos automáticamente los temas, subapartados, callouts, ejemplos y quiz.
      <br>¿Sin plantilla? <a href="/plantilla/descargar" style="font-weight:600;">📥 Descarga la plantilla Word</a> con la convención aplicada.
    </p>
  </div>

  <!-- Bloque 3: Versión SCORM -->
  <div class="card">
    <h2><span class="num">3</span> Versión de SCORM</h2>
    <p style="font-size:0.92rem; color:var(--ink-mute); margin-bottom:1rem;">
      Elige según el LMS donde lo vayas a subir. Si tienes dudas, marca <strong>"Ambas versiones"</strong>:
      generamos los dos paquetes y eliges luego cuál usar.
    </p>
    <div class="radio-cards" data-name="scorm_version">
      <label class="radio-card" data-value="1.2">
        <input type="radio" name="scorm_version" value="1.2">
        <div class="rc-title">SCORM 1.2</div>
        <div class="rc-desc">El estándar más extendido y compatible. Lo aceptan prácticamente todos los LMS
          (Moodle, Blackboard, TalentLMS, etc.). Reporta estado (completado/aprobado), nota global, tiempo y
          posición. <strong>Más sencillo, máxima compatibilidad.</strong></div>
      </label>
      <label class="radio-card" data-value="2004">
        <input type="radio" name="scorm_version" value="2004">
        <div class="rc-title">SCORM 2004 (4ª ed.)</div>
        <div class="rc-desc">Versión moderna con modelo de datos más rico: separación entre completado/aprobado,
          puntuación normalizada, progreso granular, detalle pregunta a pregunta, objetivos de aprendizaje.
          Necesario para informes pedagógicos detallados. <strong>Más datos, requiere LMS reciente.</strong></div>
      </label>
      <label class="radio-card selected" data-value="both">
        <input type="radio" name="scorm_version" value="both" checked>
        <div class="rc-title">⭐ Ambas versiones <span class="rc-badge">recomendado</span></div>
        <div class="rc-desc">Generamos los dos paquetes en el mismo ZIP. Te quedas tranquilo:
          si un LMS rechaza una, siempre tienes la otra. Sin coste adicional.</div>
      </label>
    </div>
  </div>

  <!-- Bloque 4: Sistema de puntuación ponderada -->
  <div class="card">
    <h2><span class="num">4</span> Sistema de puntuación <span style="font-weight:400;color:var(--ink-mute);font-size:0.8rem;">(cómo se calcula la nota final)</span></h2>
    <p style="font-size: 0.92rem; color: var(--ink-mute); margin-bottom: 1.2rem;">
      La nota final combina cuánto contenido ha visto el alumno y su resultado en el quiz.
      Si tu cliente exige solo "haber visto el curso", sube la visualización; si valora más
      el conocimiento, sube el quiz. <strong>Los pesos suman siempre 100%.</strong>
    </p>

    <div class="weights-row">
      <div class="weight-field">
        <label for="weight_view">Peso de la visualización</label>
        <div class="slider-wrap">
          <input type="range" id="weight_view" name="weight_view" min="0" max="100" value="40" step="5">
          <output for="weight_view" id="weight_view_out">40%</output>
        </div>
        <span class="weight-hint">Cuánto pesa haber visto los subapartados.</span>
      </div>
      <div class="weight-field">
        <label for="weight_quiz">Peso del quiz</label>
        <div class="slider-wrap">
          <input type="range" id="weight_quiz" name="weight_quiz" min="0" max="100" value="60" step="5">
          <output for="weight_quiz" id="weight_quiz_out">60%</output>
        </div>
        <span class="weight-hint">Cuánto pesa el resultado del test.</span>
      </div>
    </div>

    <div class="weight-preview" id="weightPreview">
      Si el alumno ve el <strong>50%</strong> y saca <strong>80%</strong> en el quiz, su nota final será <strong id="previewScore">68%</strong>.
    </div>

    <details style="margin-top: 1rem;">
      <summary style="cursor: pointer; font-size: 0.9rem; color: var(--ink-mute); user-select: none;">
        ⚙ Opciones avanzadas
      </summary>
      <div style="margin-top: 1rem;">
        <div class="row">
          <div class="field">
            <label for="view_min_seconds">Tiempo mínimo por subapartado (segundos)</label>
            <input type="number" id="view_min_seconds" name="view_min_seconds" value="10" min="0" max="600">
            <span class="hint">El alumno debe permanecer al menos este tiempo en cada subapartado.</span>
          </div>
          <div class="field">
            <label for="view_strategy">¿Qué cuenta como "visto"?</label>
            <select id="view_strategy" name="view_strategy">
              <option value="both" selected>Ambos: scroll hasta el final + tiempo mínimo (recomendado)</option>
              <option value="scroll">Solo scroll hasta el final</option>
              <option value="time">Solo tiempo mínimo</option>
            </select>
          </div>
        </div>
      </div>
    </details>
  </div>

  <!-- Bloque 5: Datos a rastrear en el LMS -->
  <div class="card">
    <h2><span class="num">5</span> ¿Qué información rastrear en el LMS?</h2>
    <p style="font-size: 0.92rem; color: var(--ink-mute); margin-bottom: 1rem;">
      Estos son los datos que el SCORM enviará al LMS. Los <strong>recomendados</strong>
      vienen marcados por defecto: cubren el 95% de los casos. Solo desmárcalos si tu LMS no los soporta
      o si tu cliente pide algo específico.
    </p>

    <div class="track-grid">
      <label class="track-item">
        <input type="checkbox" id="track_completion" name="track_completion" checked>
        <div>
          <div class="track-title">Completado / no completado</div>
          <div class="track-desc">Marca el curso como finalizado al cumplir las condiciones. <span class="track-tag">imprescindible</span></div>
        </div>
      </label>

      <label class="track-item">
        <input type="checkbox" id="track_score" name="track_score" checked>
        <div>
          <div class="track-title">Puntuación final (0–100%)</div>
          <div class="track-desc">Envía la nota numérica al expediente del alumno.</div>
          <div class="track-extra">
            <label for="mastery" class="track-inline-label">Mínimo para aprobar (%):</label>
            <input type="number" id="mastery" name="mastery" value="70" min="0" max="100" class="track-inline-input">
          </div>
        </div>
      </label>

      <label class="track-item">
        <input type="checkbox" id="track_success" name="track_success" checked>
        <div>
          <div class="track-title">Aprobado / suspenso</div>
          <div class="track-desc">Estado independiente de "completado". En 1.2 va unido; en 2004 son campos separados.</div>
        </div>
      </label>

      <label class="track-item">
        <input type="checkbox" id="track_time" name="track_time" checked>
        <div>
          <div class="track-title">Tiempo dedicado por sesión</div>
          <div class="track-desc">Necesario para FUNDAE y obligaciones de horas lectivas.</div>
        </div>
      </label>

      <label class="track-item">
        <input type="checkbox" id="track_suspend" name="track_suspend" checked>
        <div>
          <div class="track-title">Guardar progreso entre sesiones</div>
          <div class="track-desc">El alumno puede cerrar y retomar donde lo dejó. <span class="track-tag">recomendado</span></div>
        </div>
      </label>

      <label class="track-item">
        <input type="checkbox" id="track_location" name="track_location" checked>
        <div>
          <div class="track-title">Marcador de posición</div>
          <div class="track-desc">Reabre el curso en el subapartado donde se quedó la última vez.</div>
        </div>
      </label>

      <label class="track-item">
        <input type="checkbox" id="track_interactions" name="track_interactions" checked>
        <div>
          <div class="track-title">Detalle pregunta a pregunta</div>
          <div class="track-desc">Reporta cada respuesta del quiz al LMS. Permite informes pedagógicos. <span class="track-tag">2004 brilla aquí</span></div>
        </div>
      </label>

      <label class="track-item">
        <input type="checkbox" id="track_progress" name="track_progress">
        <div>
          <div class="track-title">Progreso granular (% de avance)</div>
          <div class="track-desc">Barra de progreso continua en el LMS. <strong>Solo SCORM 2004.</strong> En 1.2 se ignora.</div>
        </div>
      </label>

      <label class="track-item">
        <input type="checkbox" id="track_objectives" name="track_objectives">
        <div>
          <div class="track-title">Objetivos de aprendizaje</div>
          <div class="track-desc">Reporta cumplimiento por objetivo, no solo global. <strong>Solo SCORM 2004.</strong></div>
        </div>
      </label>

      <label class="track-item">
        <input type="checkbox" id="track_max_time" name="track_max_time">
        <div>
          <div class="track-title">Tiempo máximo permitido</div>
          <div class="track-desc">Limita la duración del intento. Si lo activas, especifica abajo.</div>
          <div class="track-extra">
            <label for="max_time_minutes" class="track-inline-label">Minutos:</label>
            <input type="number" id="max_time_minutes" name="max_time_minutes" value="120" min="1" max="1440" class="track-inline-input">
          </div>
        </div>
      </label>

      <label class="track-item">
        <input type="checkbox" id="track_max_attempts" name="track_max_attempts">
        <div>
          <div class="track-title">Limitar intentos</div>
          <div class="track-desc">Por defecto, intentos ilimitados. Si lo activas, especifica cuántos.</div>
          <div class="track-extra">
            <label for="max_attempts" class="track-inline-label">Máximo:</label>
            <input type="number" id="max_attempts" name="max_attempts" value="3" min="1" max="20" class="track-inline-input">
          </div>
        </div>
      </label>
    </div>
  </div>

  <!-- Bloque 6: Recursos multimedia subidos -->
  <div class="card">
    <h2><span class="num">6</span> Recursos multimedia <span style="font-weight:400;color:var(--ink-mute);font-size:0.8rem;">(opcional)</span></h2>
    <p style="font-size: 0.92rem; color: var(--ink-mute); margin-bottom: 1rem;">
      Arrastra imágenes, vídeos, audios o PDFs que se referencien en tu Word con tags como
      <code>[IMAGEN] Pie | foto.png</code>, <code>[VIDEO] Título | video.mp4</code>.
    </p>
    <div class="upload-zone" id="resZone">
      <div class="icon">📎</div>
      <div class="text">Haz clic o arrastra varios archivos</div>
    </div>
    <input type="file" id="recursos" name="recursos" multiple>
    <ul class="reslist" id="resList"></ul>
    <p class="hint" style="margin-top:0.6rem;">
      Aceptados: imágenes (png/jpg/gif/svg/webp), vídeo (mp4/webm/ogv/mov),
      audio (mp3/wav/ogg/m4a), documentos (pdf/xlsx/pptx/docx), subtítulos (vtt/srt).
    </p>
  </div>

  <!-- Bloque 7: Recursos auto-generables -->
  <div class="card">
    <h2><span class="num">7</span> Recursos extra a generar e incluir</h2>
    <p style="font-size: 0.92rem; color: var(--ink-mute); margin-bottom: 1rem;">
      Marca qué materiales adicionales quieres que se generen automáticamente desde tu Word.
      Todos se incluyen en la entrega final. Ninguno rompe la compatibilidad con LMS.
    </p>

    <div class="res-grid">
      <label class="res-item">
        <input type="checkbox" id="gen_pdf" name="gen_pdf" checked>
        <div>
          <div class="res-title">📄 PDF de apuntes</div>
          <div class="res-desc">Un PDF imprimible por cada tema. Útil como material de estudio offline.</div>
        </div>
      </label>

      <label class="res-item">
        <input type="checkbox" id="gen_aiken" name="gen_aiken" checked>
        <div>
          <div class="res-title">📝 Banco Aiken (.txt)</div>
          <div class="res-desc">Preguntas del quiz en formato Aiken. Importable a Moodle, Canvas, etc.</div>
        </div>
      </label>

      <label class="res-item">
        <input type="checkbox" id="gen_html_standalone" name="gen_html_standalone">
        <div>
          <div class="res-title">🌐 Versión HTML standalone</div>
          <div class="res-desc">El mismo curso como sitio web estático (sin SCORM). Para colgar en una web propia.</div>
        </div>
      </label>

      <label class="res-item">
        <input type="checkbox" id="gen_glossary" name="gen_glossary">
        <div>
          <div class="res-title">📚 Glosario</div>
          <div class="res-desc">Listado de términos y definiciones detectados en el contenido.</div>
        </div>
      </label>

      <label class="res-item">
        <input type="checkbox" id="gen_json" name="gen_json" checked>
        <div>
          <div class="res-title">🧩 Estructura JSON</div>
          <div class="res-desc">Volcado de toda la estructura del curso para poder re-importarlo o auditarlo.</div>
        </div>
      </label>

      <label class="res-item">
        <input type="checkbox" id="gen_readme" name="gen_readme" checked>
        <div>
          <div class="res-title">📋 README dentro del SCORM</div>
          <div class="res-desc">Ficha con datos del curso (título, horas, autor, fecha, mastery) embebida en el ZIP.</div>
        </div>
      </label>

      <label class="res-item">
        <input type="checkbox" id="gen_certificate" name="gen_certificate">
        <div>
          <div class="res-title">🏆 Plantilla de certificado</div>
          <div class="res-desc">PDF imprimible con el título, horas y un hueco para nombre del alumno y firma.</div>
        </div>
      </label>

      <label class="res-item">
        <input type="checkbox" id="gen_anki" name="gen_anki">
        <div>
          <div class="res-title">🗂 Tarjetas Anki (.csv)</div>
          <div class="res-desc">Las preguntas del quiz exportadas como flashcards importables en Anki.</div>
        </div>
      </label>

      <label class="res-item">
        <input type="checkbox" id="gen_subtitles" name="gen_subtitles">
        <div>
          <div class="res-title">🎬 Subtítulos auto para vídeos</div>
          <div class="res-desc">Whisper transcribe los vídeos subidos en .vtt. Requiere <code>faster-whisper</code> instalado.</div>
        </div>
      </label>

      <label class="res-item">
        <input type="checkbox" id="gen_wcag" name="gen_wcag" checked>
        <div>
          <div class="res-title">♿ Validación WCAG 2.1 AA</div>
          <div class="res-desc">Revisa contraste, alt en imágenes, jerarquía de encabezados, vídeos sin subtítulos.</div>
        </div>
      </label>

      <label class="res-item">
        <input type="checkbox" id="gen_manifest_preview" name="gen_manifest_preview">
        <div>
          <div class="res-title">🔍 Vista del manifest</div>
          <div class="res-desc">Copia del <code>imsmanifest.xml</code> fuera del ZIP para inspeccionarlo sin descomprimir.</div>
        </div>
      </label>
    </div>
  </div>

  <!-- Bloque 8: Marca y colores -->
  <div class="card">
    <h2><span class="num">8</span> Marca y colores</h2>
    <div class="palette-grid" id="paletteGrid"></div>
    <details style="margin-top: 1.5rem;">
      <summary style="cursor: pointer; color: var(--ink-mute); font-size: 0.9rem;">
        ¿Quieres usar tus propios colores? (opcional)
      </summary>
      <div style="margin-top: 1rem;" class="row">
        <div class="field">
          <label for="color_deep">Color cabecera (oscuro)</label>
          <input type="color" id="color_deep" value="#0A2540">
        </div>
        <div class="field">
          <label for="color_primary">Color primario</label>
          <input type="color" id="color_primary" value="#1D4ED8">
        </div>
        <div class="field">
          <label for="color_bright">Color brillante (acentos)</label>
          <input type="color" id="color_bright" value="#2563EB">
        </div>
      </div>
    </details>
  </div>

  <!-- Bloque 9: Generar -->
  <div class="card">
    <h2><span class="num">9</span> Generar el paquete</h2>
    <div style="display: flex; gap: 0.7rem; flex-wrap: wrap; margin-bottom: 0.6rem;">
      <button type="button" class="btn secondary" id="btnPreview" style="flex: 0 0 auto;">👁 Vista previa</button>
      <button type="submit" class="btn full" id="btnGenerar" style="flex: 1;">Crear paquete(s) SCORM →</button>
    </div>
    <p style="font-size: 0.82rem; color: var(--ink-mute); margin-bottom: 0.8rem;">
      La vista previa muestra el primer tema en una nueva pestaña sin empaquetar (más rápido).
      Útil para ver cómo queda con la paleta y los pesos antes de generar el paquete final.
    </p>

    <div class="progress" id="progress">
      <div class="step">Subiendo el documento</div>
      <div class="step">Analizando contenido</div>
      <div class="step">Empaquetando recursos</div>
      <div class="step">Generando HTML del curso</div>
      <div class="step">Creando recursos adicionales</div>
      <div class="step">Empaquetando en SCORM</div>
    </div>

    <div class="result" id="result">
      <h3>✓ Curso generado correctamente</h3>
      <p id="resultStats"></p>
      <div style="display:flex; gap: 0.7rem; flex-wrap: wrap; margin-top: 0.8rem;">
        <a href="#" id="downloadLink" class="btn" download>Descargar paquete (ZIP)</a>
        <a href="/biblioteca" class="btn secondary">Ir a Mis cursos →</a>
      </div>
      <div class="warnings" id="warnings" style="display:none;">
        <strong>Avisos durante el procesamiento:</strong>
        <ul id="warningsList"></ul>
      </div>
    </div>
  </div>

</form>

<script>
const palettes = __PALETTES_JSON__;
let selectedPalette = "azul";

// ----- Render paleta -----
const grid = document.getElementById("paletteGrid");
for (const [name, info] of Object.entries(palettes)) {
  const card = document.createElement("div");
  card.className = "palette-card" + (name === "azul" ? " selected" : "");
  card.innerHTML = `
    <div class="palette-name">${info.label}</div>
    <div class="palette-colors">
      <span style="background:${info.deep}"></span>
      <span style="background:${info.primary}"></span>
      <span style="background:${info.bright}"></span>
    </div>`;
  card.onclick = () => {
    document.querySelectorAll(".palette-card").forEach(c => c.classList.remove("selected"));
    card.classList.add("selected");
    selectedPalette = name;
  };
  grid.appendChild(card);
}

// ----- Comportamiento radio-cards -----
document.querySelectorAll(".radio-cards").forEach(group => {
  group.querySelectorAll(".radio-card").forEach(card => {
    card.addEventListener("click", (e) => {
      // No interceptar el click sobre el radio nativo
      if (e.target.tagName === "INPUT") return;
      group.querySelectorAll(".radio-card").forEach(c => c.classList.remove("selected"));
      card.classList.add("selected");
      const radio = card.querySelector("input[type=radio]");
      radio.checked = true;
      radio.dispatchEvent(new Event("change"));
    });
    const radio = card.querySelector("input[type=radio]");
    radio.addEventListener("change", () => {
      if (radio.checked) {
        group.querySelectorAll(".radio-card").forEach(c => c.classList.remove("selected"));
        card.classList.add("selected");
      }
    });
  });
});

// ----- Modo de subida: alterna entre archivo único y múltiple -----
const docxInput = document.getElementById("docx");
const docxZoneText = document.getElementById("docxZoneText");
const docxName = document.getElementById("docxFilename");
const docxBatchList = document.getElementById("docxBatchList");
const docxHint = document.getElementById("docxHint");
let docxBatchFiles = [];

function setUploadMode(mode) {
  if (mode === "batch") {
    docxInput.setAttribute("multiple", "");
    docxZoneText.innerHTML = "Haz clic o arrastra aquí varios archivos <strong>.docx</strong>";
    docxHint.innerHTML = "Cada archivo generará su propio SCORM con el <strong>nombre del fichero</strong> como título del paquete.";
    docxName.textContent = "";
    docxBatchList.style.display = "flex";
    docxBatchFiles = [];
    syncDocxBatch();
  } else {
    docxInput.removeAttribute("multiple");
    docxZoneText.innerHTML = "Haz clic o arrastra aquí tu archivo <strong>.docx</strong>";
    docxHint.innerHTML = "Solo se acepta <code>.docx</code>. Si el documento sigue la plantilla del proyecto, detectaremos automáticamente los temas, subapartados, callouts, ejemplos y quiz.";
    docxBatchList.style.display = "none";
    docxBatchFiles = [];
    docxName.textContent = "";
    docxZone.classList.remove("has-file");
  }
}
document.querySelectorAll('input[name=upload_mode]').forEach(r => {
  r.addEventListener("change", () => { if (r.checked) setUploadMode(r.value); });
});

// ----- DOCX upload zone -----
const docxZone = document.getElementById("docxZone");
docxZone.addEventListener("click", () => docxInput.click());
["dragover","dragenter"].forEach(ev => docxZone.addEventListener(ev, e => {
  e.preventDefault(); docxZone.classList.add("dragover");
}));
["dragleave","drop"].forEach(ev => docxZone.addEventListener(ev, e => {
  e.preventDefault(); docxZone.classList.remove("dragover");
}));
docxZone.addEventListener("drop", e => {
  if (e.dataTransfer.files.length) handleDocxFiles(e.dataTransfer.files);
});
docxInput.addEventListener("change", () => handleDocxFiles(docxInput.files));

function handleDocxFiles(filelist) {
  const mode = document.querySelector('input[name=upload_mode]:checked').value;
  if (mode === "batch") {
    for (const f of filelist) {
      if (!f.name.toLowerCase().endsWith(".docx")) continue;
      if (docxBatchFiles.some(x => x.name === f.name && x.size === f.size)) continue;
      docxBatchFiles.push(f);
    }
    syncDocxBatch();
  } else {
    if (filelist.length) {
      docxName.textContent = filelist[0].name;
      docxZone.classList.add("has-file");
      const dt = new DataTransfer();
      dt.items.add(filelist[0]);
      docxInput.files = dt.files;
    }
  }
}
function syncDocxBatch() {
  docxBatchList.innerHTML = "";
  if (!docxBatchFiles.length) {
    docxZone.classList.remove("has-file");
  } else {
    docxZone.classList.add("has-file");
  }
  docxBatchFiles.forEach((f, idx) => {
    const li = document.createElement("li");
    li.innerHTML = `
      <span class="res-icon">DOCX</span>
      <span class="res-name">${f.name}</span>
      <span class="res-size">${(f.size/1024).toFixed(0)} KB</span>
      <button type="button" class="res-rm" data-i="${idx}" aria-label="Quitar">×</button>`;
    docxBatchList.appendChild(li);
  });
  docxBatchList.querySelectorAll(".res-rm").forEach(b => {
    b.onclick = () => { docxBatchFiles.splice(parseInt(b.dataset.i), 1); syncDocxBatch(); };
  });
  const dt = new DataTransfer();
  docxBatchFiles.forEach(f => dt.items.add(f));
  docxInput.files = dt.files;
}

// ----- Recursos multi-upload -----
const resZone = document.getElementById("resZone");
const resInput = document.getElementById("recursos");
const resList = document.getElementById("resList");
let resFiles = [];

resZone.addEventListener("click", () => resInput.click());
["dragover","dragenter"].forEach(ev => resZone.addEventListener(ev, e => {
  e.preventDefault(); resZone.classList.add("dragover");
}));
["dragleave","drop"].forEach(ev => resZone.addEventListener(ev, e => {
  e.preventDefault(); resZone.classList.remove("dragover");
}));
resZone.addEventListener("drop", e => {
  for (const f of e.dataTransfer.files) addRes(f);
  syncResInput();
});
resInput.addEventListener("change", () => {
  for (const f of resInput.files) addRes(f);
  syncResInput();
});
function addRes(file) {
  if (resFiles.some(f => f.name === file.name && f.size === file.size)) return;
  resFiles.push(file);
  renderResList();
}
function removeRes(idx) { resFiles.splice(idx, 1); renderResList(); syncResInput(); }
function renderResList() {
  resList.innerHTML = "";
  if (!resFiles.length) { resZone.classList.remove("has-file"); return; }
  resZone.classList.add("has-file");
  resFiles.forEach((f, idx) => {
    const li = document.createElement("li");
    const ext = (f.name.split(".").pop() || "").toLowerCase();
    li.innerHTML = `
      <span class="res-icon">${ext.toUpperCase().slice(0,4)}</span>
      <span class="res-name">${f.name}</span>
      <span class="res-size">${(f.size/1024).toFixed(0)} KB</span>
      <button type="button" class="res-rm" data-i="${idx}" aria-label="Quitar">×</button>`;
    resList.appendChild(li);
  });
  resList.querySelectorAll(".res-rm").forEach(b => {
    b.onclick = () => removeRes(parseInt(b.dataset.i));
  });
}
function syncResInput() {
  const dt = new DataTransfer();
  resFiles.forEach(f => dt.items.add(f));
  resInput.files = dt.files;
}

// ----- Sliders de puntuación -----
(function() {
  const sliderView = document.getElementById("weight_view");
  const sliderQuiz = document.getElementById("weight_quiz");
  const outView = document.getElementById("weight_view_out");
  const outQuiz = document.getElementById("weight_quiz_out");
  const preview = document.getElementById("weightPreview");
  const previewScore = document.getElementById("previewScore");
  const masteryInput = document.getElementById("mastery");

  function calcPreview() {
    const wv = parseInt(sliderView.value);
    const wq = parseInt(sliderQuiz.value);
    const score = Math.round((wv * 50 + wq * 80) / 100);
    if (previewScore) previewScore.textContent = score + "%";
    const mastery = parseInt(masteryInput.value || "70");
    if (preview) {
      preview.classList.toggle("invalid", score < mastery);
      preview.innerHTML = `Si el alumno ve el <strong>50%</strong> del contenido y saca <strong>80%</strong> en el quiz, su nota final será <strong>${score}%</strong>. (Aprobado a partir del ${mastery}%.)`;
    }
  }
  function updateOutputs() {
    outView.textContent = sliderView.value + "%";
    outQuiz.textContent = sliderQuiz.value + "%";
    calcPreview();
  }
  sliderView.addEventListener("input", () => {
    sliderQuiz.value = 100 - parseInt(sliderView.value); updateOutputs();
  });
  sliderQuiz.addEventListener("input", () => {
    sliderView.value = 100 - parseInt(sliderQuiz.value); updateOutputs();
  });
  masteryInput.addEventListener("input", calcPreview);
  updateOutputs();
})();

// ----- Vista previa -----
document.getElementById("btnPreview").addEventListener("click", async () => {
  const mode = document.querySelector('input[name=upload_mode]:checked').value;
  const files = (mode === "batch") ? docxBatchFiles : Array.from(docxInput.files);
  if (!files.length) {
    alert("Selecciona primero al menos un archivo Word para generar la vista previa.");
    return;
  }
  const btn = document.getElementById("btnPreview");
  btn.disabled = true;
  const orig = btn.textContent;
  btn.textContent = "Generando preview…";
  try {
    const fd = new FormData();
    fd.append("docx", files[0]);
    for (const f of resFiles) fd.append("recursos", f, f.name);
    fd.append("titulo", document.getElementById("titulo").value);
    fd.append("autor", document.getElementById("autor").value);
    fd.append("mastery", document.getElementById("mastery").value);
    fd.append("weight_view", document.getElementById("weight_view").value);
    fd.append("weight_quiz", document.getElementById("weight_quiz").value);
    fd.append("view_min_seconds", document.getElementById("view_min_seconds").value);
    fd.append("view_strategy", document.getElementById("view_strategy").value);
    fd.append("paleta", selectedPalette);
    fd.append("color_deep", document.getElementById("color_deep").value);
    fd.append("color_primary", document.getElementById("color_primary").value);
    fd.append("color_bright", document.getElementById("color_bright").value);

    const r = await fetch("/api/preview", { method: "POST", body: fd });
    if (!r.ok) {
      const data = await r.json().catch(() => ({error: "desconocido"}));
      alert("Error al generar preview: " + (data.error || "desconocido"));
      return;
    }
    const html = await r.text();
    const blob = new Blob([html], { type: "text/html;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const win = window.open(url, "_blank");
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    if (!win) alert("Tu navegador bloqueó la nueva pestaña. Permite ventanas emergentes en este sitio.");
  } catch (e) { alert("Error: " + e.message); }
  finally { btn.disabled = false; btn.textContent = orig; }
});

// ----- Submit -----
document.getElementById("form").addEventListener("submit", async e => {
  e.preventDefault();
  const mode = document.querySelector('input[name=upload_mode]:checked').value;
  const filesToSend = (mode === "batch") ? docxBatchFiles : Array.from(docxInput.files);
  if (!filesToSend.length) {
    alert("Selecciona al menos un archivo Word.");
    return;
  }
  const titulo = document.getElementById("titulo").value.trim();
  if (!titulo) { alert("Indica el título del curso."); return; }

  const btn = document.getElementById("btnGenerar");
  const progress = document.getElementById("progress");
  const result = document.getElementById("result");
  btn.disabled = true;
  btn.textContent = "Procesando...";
  progress.classList.add("active");
  result.classList.remove("active");

  for (let i = 1; i <= 4; i++) {
    setTimeout(() => {
      document.querySelectorAll(".progress .step").forEach((s, idx) => {
        s.classList.remove("active");
        if (idx < i) s.classList.add("done");
        if (idx === i) s.classList.add("active");
      });
    }, i * 350);
  }

  const fd = new FormData();
  for (const f of filesToSend) fd.append("docx", f, f.name);
  for (const f of resFiles) fd.append("recursos", f, f.name);

  fd.append("upload_mode", mode);
  fd.append("titulo", titulo);
  fd.append("num_hours", document.getElementById("num_hours").value);
  fd.append("autor", document.getElementById("autor").value);
  fd.append("mastery", document.getElementById("mastery").value);
  fd.append("scorm_version", document.querySelector('input[name=scorm_version]:checked').value);
  fd.append("weight_view", document.getElementById("weight_view").value);
  fd.append("weight_quiz", document.getElementById("weight_quiz").value);
  fd.append("view_min_seconds", document.getElementById("view_min_seconds").value);
  fd.append("view_strategy", document.getElementById("view_strategy").value);
  fd.append("paleta", selectedPalette);
  fd.append("color_deep", document.getElementById("color_deep").value);
  fd.append("color_primary", document.getElementById("color_primary").value);
  fd.append("color_bright", document.getElementById("color_bright").value);

  ["track_completion","track_score","track_success","track_time","track_suspend",
   "track_location","track_interactions","track_progress","track_objectives",
   "track_max_time","track_max_attempts"].forEach(k => {
    fd.append(k, document.getElementById(k).checked);
  });
  fd.append("max_time_minutes", document.getElementById("max_time_minutes").value);
  fd.append("max_attempts", document.getElementById("max_attempts").value);

  ["gen_pdf","gen_aiken","gen_html_standalone","gen_glossary","gen_json",
   "gen_readme","gen_certificate","gen_anki","gen_subtitles","gen_wcag",
   "gen_manifest_preview"].forEach(k => {
    fd.append(k, document.getElementById(k).checked);
  });

  try {
    const r = await fetch("/api/generar", { method: "POST", body: fd });
    const data = await r.json();
    if (!r.ok) {
      alert("Error: " + (data.error || "desconocido"));
      btn.disabled = false;
      btn.textContent = "Crear paquete(s) SCORM →";
      progress.classList.remove("active");
      return;
    }
    document.querySelectorAll(".progress .step").forEach(s => {
      s.classList.remove("active"); s.classList.add("done");
    });
    const stats = [];
    if (data.num_packages) stats.push(`<strong>${data.num_packages}</strong> paquete(s) SCORM`);
    if (data.num_topics) stats.push(`<strong>${data.num_topics}</strong> tema(s)`);
    if (data.num_questions) stats.push(`<strong>${data.num_questions}</strong> preguntas`);
    if (data.num_pdfs) stats.push(`<strong>${data.num_pdfs}</strong> PDF(s)`);
    if (data.num_aiken) stats.push(`<strong>${data.num_aiken}</strong> Aiken`);
    if (data.num_resources) stats.push(`<strong>${data.num_resources}</strong> recurso(s) extra`);
    document.getElementById("resultStats").innerHTML = stats.join(" · ");
    document.getElementById("downloadLink").href = "/api/descargar/" + data.token;
    if (data.warnings && data.warnings.length) {
      const ul = document.getElementById("warningsList");
      ul.innerHTML = "";
      data.warnings.forEach(w => {
        const li = document.createElement("li");
        li.textContent = w;
        ul.appendChild(li);
      });
      document.getElementById("warnings").style.display = "block";
    } else {
      document.getElementById("warnings").style.display = "none";
    }
    result.classList.add("active");
    result.scrollIntoView({behavior:"smooth", block:"center"});
    btn.disabled = false;
    btn.textContent = "Crear otro curso";
  } catch(err) {
    alert("Error inesperado: " + err);
    btn.disabled = false;
    btn.textContent = "Crear paquete(s) SCORM →";
  }
});
</script>
"""

HOME_EXTRA_CSS = """
.upload-zone {
  border: 2px dashed var(--primary-pale); border-radius: 10px;
  padding: 2rem; text-align: center; cursor: pointer;
  transition: all 0.2s; background: var(--primary-mist);
}
.upload-zone:hover, .upload-zone.dragover {
  border-color: var(--primary-bright); background: var(--primary-pale);
}
.upload-zone.has-file { border-color: var(--ok); background: #ECFDF5; }
.upload-zone .icon { font-size: 2.4rem; margin-bottom: 0.4rem; }
.upload-zone .text { color: var(--ink-mute); font-size: 0.95rem; }
.upload-zone .filename {
  color: var(--ink); font-weight: 600; font-size: 1rem; margin-top: 0.5rem;
}
input[type="file"] { display: none; }
.reslist {
  list-style: none; margin: 1rem 0 0; padding: 0;
  display: flex; flex-direction: column; gap: 0.4rem;
}

/* Sliders del sistema de puntuación */
.weights-row {
  display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem;
  margin-bottom: 1.2rem;
}
@media (max-width: 700px) { .weights-row { grid-template-columns: 1fr; } }
.weight-field { display: flex; flex-direction: column; gap: 0.5rem; }
.weight-field label {
  font-size: 0.85rem; font-weight: 600; color: var(--ink-soft);
}
.slider-wrap {
  display: flex; align-items: center; gap: 0.8rem;
  background: var(--paper-warm); padding: 0.7rem 1rem; border-radius: 8px;
}
.slider-wrap input[type="range"] {
  flex: 1; appearance: none; height: 6px;
  background: var(--paper-deep); border-radius: 999px; outline: none;
}
.slider-wrap input[type="range"]::-webkit-slider-thumb {
  appearance: none; width: 22px; height: 22px;
  background: var(--primary-bright); border-radius: 50%;
  cursor: pointer; border: 3px solid white;
  box-shadow: 0 1px 4px rgba(0,0,0,0.2);
}
.slider-wrap input[type="range"]::-moz-range-thumb {
  width: 22px; height: 22px;
  background: var(--primary-bright); border-radius: 50%;
  cursor: pointer; border: 3px solid white;
  box-shadow: 0 1px 4px rgba(0,0,0,0.2);
}
.slider-wrap output {
  font-weight: 700; font-size: 1rem; color: var(--primary-deep);
  min-width: 48px; text-align: right; font-variant-numeric: tabular-nums;
}
.weight-hint {
  font-size: 0.78rem; color: var(--ink-mute);
}
.weight-preview {
  background: var(--primary-mist);
  border-left: 3px solid var(--primary-bright);
  padding: 0.9rem 1.1rem; border-radius: 6px;
  font-size: 0.92rem; color: var(--ink-soft);
}
.weight-preview strong { color: var(--primary-deep); }
.weight-preview.invalid {
  background: #FEF2F2; border-left-color: var(--alert);
}

.reslist li {
  display: flex; align-items: center; gap: 0.7rem;
  padding: 0.6rem 0.8rem; background: var(--paper-warm);
  border-radius: 6px; font-size: 0.9rem;
}
.res-icon {
  background: var(--primary); color: white; padding: 0.2rem 0.5rem;
  border-radius: 4px; font-family: monospace; font-size: 0.7rem;
  font-weight: 700; min-width: 42px; text-align: center;
}
.res-name { flex: 1; font-weight: 500; word-break: break-all; }
.res-size { color: var(--ink-mute); font-size: 0.82rem; }
.res-rm {
  background: transparent; border: none; cursor: pointer;
  font-size: 1.4rem; line-height: 1; color: var(--ink-mute);
  width: 28px; height: 28px; border-radius: 50%;
}
.res-rm:hover { background: var(--alert); color: white; }
.palette-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 0.7rem;
}
.palette-card {
  border: 2px solid var(--paper-deep); border-radius: 10px;
  padding: 0.8rem; cursor: pointer; transition: all 0.15s;
}
.palette-card:hover { border-color: var(--primary-bright); }
.palette-card.selected { border-color: var(--primary-bright); background: var(--primary-mist); }
.palette-name { font-weight: 600; font-size: 0.85rem; margin-bottom: 0.5rem; }
.palette-colors { display: flex; gap: 0.3rem; }
.palette-colors span { width: 24px; height: 24px; border-radius: 6px; border: 1px solid rgba(0,0,0,0.1); }
.toggle { display: flex; align-items: center; gap: 0.7rem; margin-bottom: 0.7rem; }
.toggle input { width: 18px; height: 18px; }
.toggle label { font-size: 0.95rem; cursor: pointer; }
.progress {
  margin-top: 1rem; padding: 1rem; background: var(--paper-warm);
  border-radius: 8px; display: none;
}
.progress.active { display: block; }
.progress .step { color: var(--ink-mute); font-size: 0.9rem; padding: 0.25rem 0; }
.progress .step.done { color: var(--ok); }
.progress .step.done::before { content: "✓ "; }
.progress .step.active { color: var(--primary-bright); font-weight: 600; }
.progress .step.active::before { content: "→ "; }
.result {
  margin-top: 1.5rem; padding: 1.5rem; background: #ECFDF5;
  border: 1px solid #6EE7B7; border-radius: 10px; display: none;
}
.result.active { display: block; }
.result h3 { color: #064E3B; margin-bottom: 0.8rem; }
.warnings {
  margin-top: 1rem; padding: 1rem; background: #FFFBEB;
  border-left: 3px solid var(--warn); border-radius: 6px;
  font-size: 0.85rem; color: #92400E;
}
.warnings ul { margin: 0.3rem 0 0 1.5rem; }

/* Cabecera prominente "Crear nuevo curso" */
.card-hero {
  background: linear-gradient(135deg, var(--primary-mist) 0%, white 60%);
  border-left: 4px solid var(--primary-bright);
}
.card-hero h2 { color: var(--primary-deep); font-size: 1.5rem; }
.hint { font-size: 0.78rem; color: var(--ink-mute); display: block; margin-top: 0.3rem; }

/* Radio-cards (modo subida, versión SCORM) */
.radio-cards { display: grid; gap: 0.8rem; }
@media (min-width: 700px) {
  .radio-cards { grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }
}
.radio-card {
  border: 2px solid var(--paper-deep); border-radius: 10px;
  padding: 1rem 1.1rem; cursor: pointer; transition: all 0.15s;
  background: white; position: relative;
}
.radio-card:hover { border-color: var(--primary-bright); background: var(--primary-mist); }
.radio-card.selected {
  border-color: var(--primary-bright); background: var(--primary-mist);
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.12);
}
.radio-card input[type=radio] { position: absolute; opacity: 0; pointer-events: none; }
.rc-title { font-weight: 700; font-size: 1rem; color: var(--primary-deep); margin-bottom: 0.4rem; }
.rc-desc { font-size: 0.85rem; color: var(--ink-soft); line-height: 1.5; }
.rc-badge {
  display: inline-block; background: var(--primary-bright); color: white;
  font-size: 0.65rem; padding: 0.1rem 0.5rem; border-radius: 999px;
  font-weight: 600; vertical-align: middle; margin-left: 0.4rem;
  text-transform: uppercase; letter-spacing: 0.05em;
}

/* Track-grid (configuración de rastreo en LMS) */
.track-grid {
  display: grid; gap: 0.7rem;
  grid-template-columns: repeat(auto-fit, minmax(310px, 1fr));
}
.track-item {
  display: flex; align-items: flex-start; gap: 0.7rem;
  padding: 0.85rem 0.9rem; background: var(--paper-warm);
  border-radius: 8px; cursor: pointer; transition: background 0.15s;
  border: 1px solid transparent;
}
.track-item:hover { background: var(--primary-mist); border-color: var(--primary-pale); }
.track-item input[type=checkbox] {
  width: 18px; height: 18px; margin-top: 0.15rem; flex-shrink: 0;
  accent-color: var(--primary-bright);
}
.track-item > div { flex: 1; }
.track-title { font-weight: 600; font-size: 0.92rem; color: var(--ink); margin-bottom: 0.15rem; }
.track-desc { font-size: 0.8rem; color: var(--ink-mute); line-height: 1.45; }
.track-tag {
  display: inline-block; background: var(--ok); color: white;
  font-size: 0.65rem; padding: 0.05rem 0.45rem; border-radius: 999px;
  font-weight: 600; margin-left: 0.3rem; text-transform: lowercase;
}
.track-extra { margin-top: 0.6rem; display: flex; gap: 0.5rem; align-items: center; }
.track-inline-label { font-size: 0.8rem; color: var(--ink-soft); margin: 0; }
.track-inline-input {
  width: 70px; padding: 0.3rem 0.5rem; font-size: 0.85rem;
  border: 1px solid var(--paper-deep); border-radius: 5px;
}

/* Res-grid (recursos a auto-generar) */
.res-grid {
  display: grid; gap: 0.6rem;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
}
.res-item {
  display: flex; align-items: flex-start; gap: 0.7rem;
  padding: 0.8rem 0.85rem; background: var(--paper-warm);
  border-radius: 8px; cursor: pointer; transition: background 0.15s;
  border: 1px solid transparent;
}
.res-item:hover { background: var(--primary-mist); border-color: var(--primary-pale); }
.res-item input[type=checkbox] {
  width: 18px; height: 18px; margin-top: 0.15rem; flex-shrink: 0;
  accent-color: var(--primary-bright);
}
.res-item > div { flex: 1; }
.res-title { font-weight: 600; font-size: 0.9rem; color: var(--ink); margin-bottom: 0.15rem; }
.res-desc { font-size: 0.8rem; color: var(--ink-mute); line-height: 1.45; }
"""


def _palettes_json():
    out = {}
    for name, theme in THEMES.items():
        out[name] = {
            "label": theme.label,
            "deep": theme.primary_deep,
            "primary": theme.primary,
            "bright": theme.primary_bright,
        }
    return json.dumps(out)


@app.route("/")
@login_required
def index():
    user = current_user()
    body = HOME_BODY_TEMPLATE.replace("__PALETTES_JSON__", _palettes_json())
    page = render_page("Generar", body, user=user, active="home")
    page = page.replace("/* placeholder for extra css */", "")
    # Inyectar el CSS extra al final del bloque <style>
    return page.replace("</style>", HOME_EXTRA_CSS + "</style>", 1)


# ============================================================
# Rutas: BIBLIOTECA (galería de descargas)
# ============================================================
LIBRARY_EXTRA_CSS = """
.empty {
  background: white; padding: 4rem 2rem; border-radius: 12px;
  text-align: center; color: var(--ink-mute);
}
.empty .icon { font-size: 3rem; margin-bottom: 1rem; }
.empty h3 { color: var(--ink); margin-bottom: 0.5rem; }
.course-grid {
  display: grid; gap: 1rem;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
}
.course-card {
  background: white; border-radius: 12px; padding: 1.4rem;
  box-shadow: 0 2px 8px rgba(10,37,64,0.05);
  display: flex; flex-direction: column; gap: 0.7rem;
  border: 1px solid var(--paper-deep);
}
.course-card h3 {
  font-size: 1.05rem; color: var(--primary-deep);
  line-height: 1.3; word-break: break-word;
}
.course-meta {
  display: flex; flex-wrap: wrap; gap: 0.4rem;
  font-size: 0.78rem; color: var(--ink-mute);
}
.course-meta span {
  background: var(--paper-warm); padding: 0.2rem 0.55rem;
  border-radius: 12px;
}
.course-date { font-size: 0.82rem; color: var(--ink-mute); }
.course-actions {
  display: flex; gap: 0.5rem; flex-wrap: wrap; margin-top: auto;
  padding-top: 0.7rem; border-top: 1px solid var(--paper-deep);
}
.course-actions .btn { padding: 0.5rem 0.9rem; font-size: 0.85rem; }
"""


@app.route("/biblioteca")
@login_required
def library():
    user = current_user()
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM courses WHERE user_id = ? ORDER BY id DESC",
            (user["id"],),
        ).fetchall()
    if not rows:
        body = """
        <div class="empty">
          <div class="icon">📚</div>
          <h3>Aún no has generado ningún curso</h3>
          <p>Cuando generes tu primer SCORM, aparecerá aquí para que puedas
          descargarlo cuantas veces quieras.</p>
          <p style="margin-top: 1.5rem;"><a class="btn" href="/">Generar mi primer curso →</a></p>
        </div>
        """
    else:
        cards = []
        for r in rows:
            warnings = []
            try:
                warnings = json.loads(r["warnings_json"] or "[]")
            except Exception:
                pass
            warning_badge = (
                f'<span style="background:#FFFBEB;color:#92400E;">⚠ {len(warnings)} aviso(s)</span>'
                if warnings else ""
            )
            size_kb = (r["zip_size"] or 0) / 1024
            size_str = f"{size_kb:,.0f} KB" if size_kb < 1024 else f"{size_kb/1024:,.1f} MB"
            created = r["created_at"][:16].replace("T", " ")
            cards.append(f"""
            <div class="course-card">
              <h3>{(r['title'] or 'Sin título')}</h3>
              <div class="course-meta">
                <span>{r['num_topics'] or 0} tema(s)</span>
                <span>{r['num_questions'] or 0} preg.</span>
                <span>{r['num_pdfs'] or 0} PDF</span>
                <span>{r['num_resources'] or 0} recurso(s)</span>
                <span>{size_str}</span>
                {warning_badge}
              </div>
              <div class="course-date">📅 {created}</div>
              <div class="course-actions">
                <a class="btn" href="/api/descargar/{r['token']}">Descargar ZIP</a>
                <a class="btn secondary" href="/curso/{r['token']}">Detalle</a>
                <form method="post" action="/curso/{r['token']}/borrar" style="display:inline;"
                      onsubmit="return confirm('¿Borrar este curso definitivamente?')">
                  <button type="submit" class="btn danger">Borrar</button>
                </form>
              </div>
            </div>""")
        body = f'<div class="course-grid">{"".join(cards)}</div>'
    page = render_page("Mis cursos", body, user=user, active="library")
    return page.replace("</style>", LIBRARY_EXTRA_CSS + "</style>", 1)


@app.route("/curso/<token>")
@login_required
def course_detail(token):
    user = current_user()
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM courses WHERE token = ? AND user_id = ?",
            (token, user["id"]),
        ).fetchone()
    if not row:
        abort(404)
    warnings = []
    try:
        warnings = json.loads(row["warnings_json"] or "[]")
    except Exception:
        pass
    warns_html = ""
    if warnings:
        items = "".join(f"<li>{w}</li>" for w in warnings)
        warns_html = f"""
        <div class="card">
          <h2>Avisos</h2>
          <ul style="margin-left:1.2rem;">{items}</ul>
        </div>"""
    body = f"""
    <div class="card">
      <h2>{row['title']}</h2>
      <p style="color:var(--ink-mute); margin-bottom:1.2rem;">
        Generado el {row['created_at'][:16].replace('T', ' ')} · Autor: {row['author'] or '—'}
      </p>
      <div style="display:flex; flex-wrap:wrap; gap: 0.7rem; margin-bottom: 1rem;">
        <span class="course-meta-pill">{row['num_topics']} tema(s)</span>
        <span class="course-meta-pill">{row['num_questions']} preguntas</span>
        <span class="course-meta-pill">{row['num_pdfs']} PDF(s)</span>
        <span class="course-meta-pill">{row['num_aiken']} banco(s) Aiken</span>
        <span class="course-meta-pill">{row['num_resources']} recurso(s)</span>
      </div>
      <a class="btn" href="/api/descargar/{row['token']}">Descargar paquete completo (ZIP)</a>
      <a class="btn secondary" href="/curso/{row['token']}/editar">✎ Editar contenido</a>
      <button class="btn secondary" type="button" onclick="exportFormat('html', '{row['token']}')">🌐 Exportar como HTML</button>
      <button class="btn secondary" type="button" onclick="exportFormat('scorm2004', '{row['token']}')">📦 Exportar como SCORM 2004</button>
      <a class="btn secondary" href="/biblioteca">← Volver a Mis cursos</a>
    </div>
    {warns_html}
    <script>
    async function exportFormat(kind, token) {{{{
      const url = '/api/curso/' + token + '/export-' + (kind === 'html' ? 'html' : 'scorm2004');
      try {{{{
        const r = await fetch(url, {{{{method: 'POST'}}}});
        const data = await r.json();
        if (!r.ok) {{{{ alert('Error: ' + (data.error || 'desconocido')); return; }}}}
        // Descargar
        window.location.href = '/curso/' + token + '/export/' + (kind === 'html' ? 'html' : 'scorm2004');
      }}}} catch (e) {{{{ alert('Error: ' + e.message); }}}}
    }}}}
    </script>
    <style>
    .course-meta-pill {{
      background: var(--paper-warm); padding: 0.4rem 0.85rem;
      border-radius: 20px; font-size: 0.85rem; color: var(--ink);
    }}
    </style>
    """
    return render_page(row["title"], body, user=user, active="library")


@app.route("/curso/<token>/borrar", methods=["POST"])
@login_required
def course_delete(token):
    user = current_user()
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM courses WHERE token = ? AND user_id = ?",
            (token, user["id"]),
        ).fetchone()
        if not row:
            abort(404)
        # Borrar carpeta del job en disco
        zip_path = Path(row["zip_path"])
        job_dir = zip_path.parent
        if job_dir.exists() and job_dir.is_relative_to(user_dir(user["id"])):
            shutil.rmtree(job_dir, ignore_errors=True)
        conn.execute("DELETE FROM courses WHERE id = ?", (row["id"],))
        conn.commit()
    push_flash("info", "Curso eliminado.")
    return redirect("/biblioteca")


# ============================================================
# EDICIÓN DEL CURSO (sin volver al Word)
# ============================================================
@app.route("/curso/<token>/editar")
@login_required
def course_edit(token):
    """Página de edición del curso. Carga la estructura JSON y muestra un editor."""
    user = current_user()
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM courses WHERE token = ? AND user_id = ?",
            (token, user["id"]),
        ).fetchone()
    if not row:
        abort(404)
    structure_path = Path(row["zip_path"]).parent / "structure.json"
    if not structure_path.exists():
        push_flash("error", "Este curso no tiene estructura editable. Vuelve a generar el curso para activar la edición.")
        return redirect(f"/curso/{token}")

    body = f"""
    <div class="topbar-page">
      <h1>Editar curso</h1>
      <p class="page-sub">Cambios sobre <strong>{html_escape(row['title'])}</strong>. Al guardar se reempaqueta el SCORM con tus cambios; el ZIP descargable se actualiza automáticamente.</p>
    </div>
    <div id="editor-root">Cargando…</div>

    <script>
    const TOKEN = "{token}";
    const API_GET = "/api/curso/" + TOKEN + "/structure";
    const API_SAVE = "/api/curso/" + TOKEN + "/save";

    let course = null;
    let courseSnapshot = null;  // copia del estado guardado para detectar cambios y restaurar
    let dirty = false;

    async function load() {{
      const r = await fetch(API_GET);
      if (!r.ok) {{ document.getElementById('editor-root').innerHTML = '<p>Error al cargar la estructura.</p>'; return; }}
      course = await r.json();
      courseSnapshot = JSON.parse(JSON.stringify(course));  // snapshot inicial
      dirty = false;
      render();
    }}

    function markDirty() {{
      if (!dirty) {{
        dirty = true;
        const ind = document.getElementById('ed-dirty-indicator');
        if (ind) ind.style.display = 'inline-block';
      }}
    }}

    // Aviso si el usuario intenta salir con cambios sin guardar
    window.addEventListener('beforeunload', (e) => {{
      if (dirty) {{
        e.preventDefault();
        e.returnValue = 'Tienes cambios sin guardar. ¿Seguro que quieres salir?';
        return e.returnValue;
      }}
    }});

    function escapeHtml(s) {{
      return (s || "").replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}})[c]);
    }}

    function render() {{
      const root = document.getElementById('editor-root');
      let html = '';
      // Metadatos
      const md = course.metadata;
      html += '<div class="ed-card">';
      html += '<h2>Metadatos del curso</h2>';
      html += '<div class="ed-grid">';
      html += '<label>Título<input type="text" data-meta="title" value="' + escapeHtml(md.title) + '"></label>';
      html += '<label>Autor<input type="text" data-meta="author" value="' + escapeHtml(md.author) + '"></label>';
      html += '<label>Subtítulo<input type="text" data-meta="subtitle" value="' + escapeHtml(md.subtitle) + '"></label>';
      html += '<label>Sector<input type="text" data-meta="sector" value="' + escapeHtml(md.sector) + '"></label>';
      html += '<label>Mastery (%)<input type="number" data-meta="mastery" value="' + md.mastery + '" min="0" max="100"></label>';
      html += '<label>Peso visualización (%)<input type="number" data-meta="weight_view" value="' + md.weight_view + '" min="0" max="100"></label>';
      html += '<label>Peso quiz (%)<input type="number" data-meta="weight_quiz" value="' + md.weight_quiz + '" min="0" max="100"></label>';
      html += '<label>Tiempo mín. por subapartado (s)<input type="number" data-meta="view_min_seconds" value="' + md.view_min_seconds + '" min="0"></label>';
      html += '</div></div>';

      course.topics.forEach((t, ti) => {{
        html += '<div class="ed-card">';
        html += '<div class="ed-topic-head">';
        html += '<h2>Tema ' + t.number + ': <input type="text" class="ed-title" data-topic="' + ti + '" data-field="title" value="' + escapeHtml(t.title) + '"></h2>';
        html += '<div class="ed-struct-actions">';
        html += '<button type="button" class="btn-struct" data-action="topic-up" data-topic="' + ti + '" title="Mover tema arriba">↑</button>';
        html += '<button type="button" class="btn-struct" data-action="topic-down" data-topic="' + ti + '" title="Mover tema abajo">↓</button>';
        html += '<button type="button" class="btn-struct btn-del" data-action="topic-del" data-topic="' + ti + '" title="Borrar tema">🗑</button>';
        html += '</div></div>';
        if (t.intro != null) {{
          html += '<label class="ed-block">Introducción<textarea data-topic="' + ti + '" data-field="intro">' + escapeHtml(t.intro) + '</textarea></label>';
        }}

        // ----- TAGS / ETIQUETAS DEL TEMA (v0.5 Fase 3) -----
        const tags = Array.isArray(t.tags) ? t.tags : [];
        html += '<div class="ed-tags-block" data-topic="' + ti + '">';
        html += '<label class="ed-tags-label">🏷 Etiquetas del tema <span class="ed-tags-hint">(se incluyen en el manifest SCORM como keywords y aparecen como chips bajo el título)</span></label>';
        html += '<ul class="ed-tags-list" data-topic="' + ti + '">';
        tags.forEach((tag, tagi) => {{
          html += '<li class="ed-tag-chip">';
          html += escapeHtml(tag);
          html += '<button type="button" class="ed-tag-del" data-topic="' + ti + '" data-tag-index="' + tagi + '" title="Quitar etiqueta" aria-label="Quitar etiqueta">×</button>';
          html += '</li>';
        }});
        html += '</ul>';
        html += '<div class="ed-tags-actions">';
        html += '<input type="text" class="ed-tag-input" data-topic="' + ti + '" placeholder="Escribe una etiqueta y pulsa Enter">';
        html += '<button type="button" class="btn-ai-mini" data-topic-ai="tags" data-topic="' + ti + '">🏷 Generar tags con IA</button>';
        html += '</div>';
        html += '</div>';

        // Subapartados
        t.subsections.forEach((s, si) => {{
          html += '<div class="ed-sub">';
          html += '<div class="ed-sub-head">';
          html += '<h3>' + escapeHtml(s.number) + ' <input type="text" data-topic="' + ti + '" data-sub="' + si + '" data-field="title" value="' + escapeHtml(s.title) + '"></h3>';
          html += '<div class="ed-struct-actions">';
          html += '<button type="button" class="btn-struct" data-action="sub-up" data-topic="' + ti + '" data-sub="' + si + '" title="Subir">↑</button>';
          html += '<button type="button" class="btn-struct" data-action="sub-down" data-topic="' + ti + '" data-sub="' + si + '" title="Bajar">↓</button>';
          html += '<button type="button" class="btn-ai-mini" data-action="sub-illustration" data-topic="' + ti + '" data-sub="' + si + '" title="Generar ilustración SVG con IA">🎨 Ilustrar con IA</button>';
          html += '<button type="button" class="btn-struct btn-del" data-action="sub-del" data-topic="' + ti + '" data-sub="' + si + '" title="Borrar subapartado">🗑</button>';
          html += '</div></div>';
          s.blocks.forEach((b, bi) => {{
            const lbl = blockLabel(b.type);
            const ed = blockEditor(ti, si, bi, b);
            // Solo bloques de texto largo permiten reescritura por IA
            const allowAi = ['paragraph','callout_key','callout_alert','callout_success','callout_warn','quote','example'].includes(b.type);
            const aiBtn = allowAi
              ? '<details class="ed-ai-menu"><summary>✨</summary>' +
                '<button type="button" class="ed-ai-opt" data-rewrite="practical" data-topic="' + ti + '" data-sub="' + si + '" data-block="' + bi + '">Más práctico</button>' +
                '<button type="button" class="ed-ai-opt" data-rewrite="theoretical" data-topic="' + ti + '" data-sub="' + si + '" data-block="' + bi + '">Más teórico</button>' +
                '<button type="button" class="ed-ai-opt" data-rewrite="professional" data-topic="' + ti + '" data-sub="' + si + '" data-block="' + bi + '">Más profesional</button>' +
                '<button type="button" class="ed-ai-opt" data-rewrite="simple" data-topic="' + ti + '" data-sub="' + si + '" data-block="' + bi + '">Lectura fácil</button>' +
                '<button type="button" class="ed-ai-opt" data-rewrite="improve" data-topic="' + ti + '" data-sub="' + si + '" data-block="' + bi + '">Mejorar redacción</button>' +
                '<button type="button" class="ed-ai-opt" data-rewrite="summarize" data-topic="' + ti + '" data-sub="' + si + '" data-block="' + bi + '">Resumir</button>' +
                '<button type="button" class="ed-ai-opt" data-rewrite="expand" data-topic="' + ti + '" data-sub="' + si + '" data-block="' + bi + '">Expandir</button>' +
                '</details>'
              : '';
            const blockStruct = '<div class="ed-block-struct">' +
              '<button type="button" class="btn-struct btn-mini" data-action="block-up" data-topic="' + ti + '" data-sub="' + si + '" data-block="' + bi + '" title="Subir">↑</button>' +
              '<button type="button" class="btn-struct btn-mini" data-action="block-down" data-topic="' + ti + '" data-sub="' + si + '" data-block="' + bi + '" title="Bajar">↓</button>' +
              '<button type="button" class="btn-struct btn-mini btn-del" data-action="block-del" data-topic="' + ti + '" data-sub="' + si + '" data-block="' + bi + '" title="Borrar bloque">🗑</button>' +
              '</div>';
            html += '<div class="ed-block-row"><span class="ed-block-tag">' + lbl + '</span>' + ed + aiBtn + blockStruct + '</div>';
            // Separador "+ aquí" para insertar entre bloques (excepto después del último, que tiene su propio "+ Añadir bloque")
            if (bi < s.blocks.length - 1) {{
              html += '<div class="ed-insert-here">' +
                '<button type="button" class="btn-insert-here" data-action="block-add" data-topic="' + ti + '" data-sub="' + si + '" data-blocktype="paragraph" data-position="' + (bi + 1) + '" title="Insertar párrafo aquí">+ insertar aquí</button>' +
                '</div>';
            }}
          }});
          // Botón añadir bloque (al final del subapartado)
          html += '<div class="ed-add-block">';
          html += '<details><summary>+ Añadir bloque</summary>';
          html += '<div class="ed-add-group"><span class="ed-add-label">Texto:</span>';
          ['paragraph','heading_3','heading_4','quote','example'].forEach(bt => {{
            html += '<button type="button" class="ed-add-opt" data-action="block-add" data-topic="' + ti + '" data-sub="' + si + '" data-blocktype="' + bt + '">' + blockLabel(bt) + '</button>';
          }});
          html += '</div>';
          html += '<div class="ed-add-group"><span class="ed-add-label">Listas:</span>';
          ['list_bullet','list_number'].forEach(bt => {{
            html += '<button type="button" class="ed-add-opt" data-action="block-add" data-topic="' + ti + '" data-sub="' + si + '" data-blocktype="' + bt + '">' + blockLabel(bt) + '</button>';
          }});
          html += '</div>';
          html += '<div class="ed-add-group"><span class="ed-add-label">Llamadas de atención:</span>';
          ['callout_key','callout_alert','callout_success','callout_warn'].forEach(bt => {{
            html += '<button type="button" class="ed-add-opt" data-action="block-add" data-topic="' + ti + '" data-sub="' + si + '" data-blocktype="' + bt + '">' + blockLabel(bt) + '</button>';
          }});
          html += '</div>';
          html += '<div class="ed-add-group"><span class="ed-add-label">Multimedia:</span>';
          ['image','video','audio','embed','download','resource'].forEach(bt => {{
            html += '<button type="button" class="ed-add-opt" data-action="block-add" data-topic="' + ti + '" data-sub="' + si + '" data-blocktype="' + bt + '">' + blockLabel(bt) + '</button>';
          }});
          html += '</div>';
          html += '</details></div>';
          html += '</div>';
        }});
        // Botón añadir subapartado
        html += '<button type="button" class="btn-struct btn-add-wide" data-action="sub-add" data-topic="' + ti + '">+ Añadir subapartado</button>';
        // Botones a nivel de tema: objetivos / resumen
        html += '<div class="ed-topic-ai">';
        html += '<button type="button" class="btn-ai-mini" data-topic-ai="objectives" data-topic="' + ti + '">🎯 Generar objetivos de aprendizaje</button>';
        html += '<button type="button" class="btn-ai-mini" data-topic-ai="summary" data-topic="' + ti + '">📝 Generar resumen final</button>';
        html += '<button type="button" class="btn-ai-mini" data-topic-ai="enrich" data-topic="' + ti + '">✨ Enriquecer con callouts IA</button>';
        html += '</div>';

        // ----- ASISTENTE IA AVANZADO (v0.5 Fase 3, colapsable) -----
        const inlineCount = t.inline_quiz ? Object.values(t.inline_quiz).reduce((s, arr) => s + (arr ? arr.length : 0), 0) : 0;
        html += '<details class="ed-ai-advanced" data-topic="' + ti + '">';
        html += '<summary>⚙️ Asistente IA avanzado — configurador de quiz por tipos y bancos</summary>';
        html += '<div class="ed-ai-advanced-body">';

        // Configurador de quiz
        html += '<fieldset class="ed-quiz-config" data-topic="' + ti + '">';
        html += '<legend>Generador de quiz configurable</legend>';
        html += '<div class="ed-quiz-config-grid">';
        html += '<label>Ubicación<select class="ed-qc-location" data-topic="' + ti + '">';
        html += '<option value="final">Bloque final del tema (clásico)</option>';
        html += '<option value="per_subsection">Una pregunta de repaso por cada subapartado</option>';
        html += '<option value="mixed">Mixto: repaso por subapartado + bloque final</option>';
        html += '</select></label>';
        html += '<label>Nº preguntas (bloque final)<input type="number" class="ed-qc-n" data-topic="' + ti + '" min="1" max="15" value="5"></label>';
        html += '</div>';
        html += '<div class="ed-quiz-config-types">';
        html += '<label><input type="checkbox" class="ed-qc-type" data-topic="' + ti + '" value="multiple_choice" checked> Test (4 opciones)</label>';
        html += '<label><input type="checkbox" class="ed-qc-type" data-topic="' + ti + '" value="true_false"> Verdadero / Falso</label>';
        html += '<label><input type="checkbox" class="ed-qc-type" data-topic="' + ti + '" value="fill_in"> Completar huecos</label>';
        html += '</div>';
        html += '<p class="ed-qc-info">⚠️ Sustituye el quiz actual y las preguntas intercaladas del tema. ';
        if (inlineCount) html += 'Actualmente hay <strong>' + inlineCount + '</strong> pregunta(s) de repaso intercaladas.';
        html += '</p>';
        html += '<button type="button" class="btn-ai" data-topic-ai="quiz-config" data-topic="' + ti + '">🤖 Generar quiz con esta configuración</button>';
        html += '</fieldset>';

        html += '</div>';  // ed-ai-advanced-body
        html += '</details>';
        // Quiz
        if (t.quiz && t.quiz.length) {{
          html += '<div class="ed-quiz"><h3>Preguntas del quiz <button type="button" class="btn-ai-mini" data-topic="' + ti + '" data-mode="extra">+ Añadir 5 más con IA</button></h3>';
          t.quiz.forEach((q, qi) => {{
            html += '<div class="ed-question"><strong>P' + (qi+1) + '.</strong> ';
            html += '<input type="text" class="ed-q-text" data-topic="' + ti + '" data-quiz="' + qi + '" data-field="text" value="' + escapeHtml(q.text) + '">';
            q.options.forEach((opt, oi) => {{
              const isCorrect = (oi === q.correct_index);
              html += '<div class="ed-opt"><input type="radio" name="correct_' + ti + '_' + qi + '" data-topic="' + ti + '" data-quiz="' + qi + '" data-correct="' + oi + '" ' + (isCorrect ? 'checked' : '') + '>';
              html += '<input type="text" data-topic="' + ti + '" data-quiz="' + qi + '" data-opt="' + oi + '" value="' + escapeHtml(opt) + '"></div>';
            }});
            if (q.explanation != null) {{
              html += '<label class="ed-expl">Explicación<input type="text" data-topic="' + ti + '" data-quiz="' + qi + '" data-field="explanation" value="' + escapeHtml(q.explanation || '') + '"></label>';
            }}
            html += '<button type="button" class="btn-tiny btn-del-q" data-topic="' + ti + '" data-quiz="' + qi + '">🗑 Borrar pregunta</button>';
            html += '</div>';
          }});
          html += '</div>';
        }} else {{
          // Tema SIN quiz: ofrecer generación con IA
          html += '<div class="ed-quiz ed-quiz-empty">';
          html += '<h3>Preguntas del quiz</h3>';
          html += '<p style="color:var(--ink-mute);font-size:0.9rem;margin-bottom:0.7rem;">Este tema todavía no tiene quiz. Puedes generar 5 preguntas a partir del contenido con IA.</p>';
          html += '<button type="button" class="btn-ai" data-topic="' + ti + '" data-mode="new">🤖 Generar 5 preguntas con IA</button>';
          html += '</div>';
        }}
        html += '</div>';
      }});

      html += '<button type="button" class="btn-struct btn-add-wide" data-action="topic-add">+ Añadir tema nuevo</button>';

      // ============================================================
      // BANNER: aplicar mejoras IA al curso en un solo clic (v0.5.1)
      // ============================================================
      html += '<div class="ed-enrich-banner">';
      html += '<div class="ed-enrich-banner-text">';
      html += '<strong>✨ ¿Primera vez en el editor?</strong> ';
      html += 'Pulsa el botón para que la IA enriquezca tu curso automáticamente. ';
      html += 'Generará <strong>etiquetas temáticas</strong>, convertirá los párrafos clave en ';
      html += '<strong>callouts visuales</strong> ([CLAVE], [ALERTA], [CITA]...) y creará un ';
      html += '<strong>quiz mixto</strong> (test + V/F + huecos) en los temas con pocas preguntas. ';
      html += 'Luego puedes ver el resultado con <em>👁 Vista previa</em>.';
      html += '</div>';
      html += '<button type="button" class="btn-ai btn-enrich-all" id="ed-enrich-all">✨ Aplicar mejoras IA al curso completo</button>';
      html += '</div>';

      html += '<div class="ed-actions">';
      html += '<button class="btn" id="ed-save">💾 Guardar y reempaquetar</button>';
      html += '<button type="button" class="btn secondary" onclick="restoreSnapshot()" title="Descartar cambios desde el último guardado">↺ Descartar cambios</button>';
      html += '<a class="btn secondary" href="/curso/' + TOKEN + '">Salir</a>';
      html += '<button type="button" class="btn-ai" id="ed-glossary">📖 Generar glosario del curso con IA</button>';
      html += '<button type="button" class="btn-ai" id="ed-tts">🔊 Generar narración TTS de todo el curso</button>';
      html += '<button type="button" class="btn secondary" id="ed-wcag-check">🔍 Validar WCAG 2.1 AA</button>';
      html += '<button type="button" class="btn secondary" id="ed-preview">👁 Vista previa del SCORM</button>';
      html += '<button type="button" class="btn-ai" id="ed-aiken-ext">📚 Banco Aiken extendido con IA (30 pregs / tema)</button>';
      html += '<button type="button" class="btn secondary" id="ed-export-imscp">📦 Exportar como IMS CP (Moodle)</button>';
      html += '<button type="button" class="btn secondary" id="ed-export-cmi5">⚡ Exportar como cmi5 / xAPI</button>';
      html += '<span id="ed-dirty-indicator" style="display:' + (dirty ? 'inline-block' : 'none') + '; background:#fbbf24; color:#78350f; padding:0.3rem 0.6rem; border-radius:4px; font-size:0.8rem; font-weight:600;">● Cambios sin guardar</span>';
      html += '<span id="ed-status"></span>';
      html += '</div>';

      root.innerHTML = html;
      document.getElementById('ed-save').onclick = save;

      // Helper: marca botón ocupado y llama a un endpoint, luego restaura
      async function callAI(btn, url, payload) {{
        const orig = btn.textContent;
        btn.disabled = true;
        btn.textContent = '⏳ ...';
        try {{
          const r = await fetch(url, {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify(payload)
          }});
          const data = await r.json();
          if (!r.ok) {{
            alert('Error IA: ' + (data.error || 'desconocido'));
            return null;
          }}
          return data;
        }} catch (e) {{
          alert('Error: ' + e.message);
          return null;
        }} finally {{
          btn.disabled = false;
          btn.textContent = orig;
        }}
      }}

      function setStatus(msg) {{
        const status = document.getElementById('ed-status');
        if (status) status.textContent = msg;
      }}

      // ----- Botones de quiz (generar / añadir) -----
      document.querySelectorAll('.btn-ai[data-mode], .btn-ai-mini[data-mode]').forEach(btn => {{
        btn.onclick = async () => {{
          collectChanges();
          const ti = parseInt(btn.dataset.topic);
          const mode = btn.dataset.mode;
          const data = await callAI(btn, '/api/curso/' + TOKEN + '/ai-quiz', {{topic_index: ti, n_questions: 5}});
          if (!data) return;
          const newQs = data.questions || [];
          if (mode === 'new') course.topics[ti].quiz = newQs;
          else course.topics[ti].quiz = (course.topics[ti].quiz || []).concat(newQs);
          render();
          markDirty(); setStatus('✓ ' + newQs.length + ' preguntas generadas. Revísalas y guarda.');
        }};
      }});

      // ----- Botones a nivel de tema: objetivos / resumen -----
      document.querySelectorAll('[data-topic-ai]').forEach(btn => {{
        btn.onclick = async () => {{
          collectChanges();
          const ti = parseInt(btn.dataset.topic);
          const kind = btn.dataset.topicAi;
          if (kind === 'objectives') {{
            const data = await callAI(btn, '/api/curso/' + TOKEN + '/ai-objectives', {{topic_index: ti}});
            if (!data) return;
            const items = data.objectives || [];
            // Insertar como bloque de lista bullet al inicio del primer subapartado del tema
            // o, si no hay subapartados, crear uno. Pero como aún no tenemos UI para añadir
            // subapartados desde el editor, lo insertamos al principio del primer subapartado existente.
            const t = course.topics[ti];
            if (!t.subsections.length) {{
              alert('El tema no tiene subapartados — añade alguno en el Word antes.');
              return;
            }}
            const firstSub = t.subsections[0];
            firstSub.blocks.unshift({{
              type: 'heading_3', text: 'Objetivos de aprendizaje', items: [], rows: [], extras: {{}}
            }});
            firstSub.blocks.splice(1, 0, {{
              type: 'list_bullet', text: '', items: items, rows: [], extras: {{}}
            }});
            render();
            markDirty(); setStatus('✓ ' + items.length + ' objetivos insertados al inicio del primer subapartado.');
          }} else if (kind === 'summary') {{
            const data = await callAI(btn, '/api/curso/' + TOKEN + '/ai-summary', {{topic_index: ti}});
            if (!data) return;
            const summary = data.summary || '';
            // Insertar como heading + párrafo al final del último subapartado del tema
            const t = course.topics[ti];
            if (!t.subsections.length) {{
              alert('El tema no tiene subapartados — añade alguno en el Word antes.');
              return;
            }}
            const lastSub = t.subsections[t.subsections.length - 1];
            lastSub.blocks.push({{
              type: 'heading_3', text: 'Resumen del tema', items: [], rows: [], extras: {{}}
            }});
            lastSub.blocks.push({{
              type: 'callout_key', text: summary, items: [], rows: [], extras: {{}}
            }});
            render();
            markDirty(); setStatus('✓ Resumen insertado al final del tema.');
          }}
        }};
      }});

      // ----- Botón glosario del curso -----
      const gloBtn = document.getElementById('ed-glossary');
      if (gloBtn) {{
        gloBtn.onclick = async () => {{
          collectChanges();
          const data = await callAI(gloBtn, '/api/curso/' + TOKEN + '/ai-glossary', {{}});
          if (!data) return;
          const items = data.glossary || [];
          if (!items.length) {{ alert('La IA no devolvió términos.'); return; }}
          // Crear un nuevo "tema-glosario" al final
          const newTopic = {{
            number: course.topics.length + 1,
            title: 'Glosario',
            intro: 'Glosario de términos clave del curso.',
            subsections: [{{
              id: 'glo1',
              number: (course.topics.length + 1) + '.1',
              title: 'Términos',
              blocks: items.map(it => ({{
                type: 'callout_key',
                text: it.term + ': ' + it.definition,
                items: [], rows: [], extras: {{}}
              }}))
            }}],
            quiz: []
          }};
          course.topics.push(newTopic);
          render();
          markDirty(); setStatus('✓ Glosario con ' + items.length + ' términos añadido como tema final. Revísalo y guarda.');
        }};
      }}

      // ----- Botón TTS del curso -----
      const ttsBtn = document.getElementById('ed-tts');
      if (ttsBtn) {{
        ttsBtn.onclick = async () => {{
          if (!confirm('Esto generará un archivo de audio por cada subapartado del curso. Puede tardar varios minutos. ¿Continuar?')) return;
          collectChanges();
          // El backend modifica directamente structure.json y devuelve métricas.
          // Tras la llamada, recargamos la estructura para reflejar los nuevos bloques [AUDIO].
          ttsBtn.disabled = true;
          const orig = ttsBtn.textContent;
          ttsBtn.textContent = '⏳ Generando audios… (puede tardar)';
          try {{
            const r = await fetch('/api/curso/' + TOKEN + '/tts', {{
              method: 'POST',
              headers: {{'Content-Type': 'application/json'}},
              body: JSON.stringify({{}}),
            }});
            const data = await r.json();
            if (!r.ok) {{ alert('Error TTS: ' + (data.error || 'desconocido')); return; }}
            // Recargar la estructura desde el servidor (el backend la actualizó)
            const r2 = await fetch('/api/curso/' + TOKEN + '/structure');
            if (r2.ok) {{
              course = await r2.json();
              render();
              const errMsg = data.errors && data.errors.length ? ' (' + data.errors.length + ' errores)' : '';
              markDirty(); setStatus('✓ ' + data.generated + ' narraciones generadas' + errMsg + '. Guarda para que se incluyan en el SCORM.');
            }}
          }} catch (e) {{
            alert('Error: ' + e.message);
          }} finally {{
            ttsBtn.disabled = false;
            ttsBtn.textContent = orig;
          }}
        }};
      }}

      // ============================================================
      // HANDLERS FASE 3 (v0.5): UI para endpoints IA de Fase 2
      // ============================================================

      // ----- TAGS: chips, añadir manual y generar con IA -----
      // Click en × para borrar tag
      document.querySelectorAll('.ed-tag-del').forEach(btn => {{
        btn.onclick = () => {{
          const ti = parseInt(btn.dataset.topic);
          const idx = parseInt(btn.dataset.tagIndex);
          if (!course.topics[ti].tags) course.topics[ti].tags = [];
          course.topics[ti].tags.splice(idx, 1);
          render(); markDirty();
        }};
      }});

      // Pulsar Enter en el input para añadir tag manual
      document.querySelectorAll('.ed-tag-input').forEach(inp => {{
        inp.onkeydown = (e) => {{
          if (e.key === 'Enter') {{
            e.preventDefault();
            const ti = parseInt(inp.dataset.topic);
            const tag = inp.value.trim().toLowerCase()
              .replace(/[^a-z0-9áéíóúñü\\s\\-]/g, '').trim();
            if (!tag) return;
            if (!course.topics[ti].tags) course.topics[ti].tags = [];
            if (!course.topics[ti].tags.includes(tag)) {{
              course.topics[ti].tags.push(tag);
              render(); markDirty();
            }} else {{
              inp.value = '';
            }}
          }}
        }};
      }});

      // Botón "Generar tags con IA"
      document.querySelectorAll('[data-topic-ai="tags"]').forEach(btn => {{
        btn.onclick = async () => {{
          collectChanges();
          const ti = parseInt(btn.dataset.topic);
          const existing = course.topics[ti].tags || [];
          if (existing.length > 0) {{
            if (!confirm('Este tema ya tiene ' + existing.length + ' etiqueta(s). ¿Reemplazarlas por las que genere la IA?')) return;
          }}
          const data = await callAI(btn, '/api/curso/' + TOKEN + '/ai-tags', {{topic_index: ti, n: 6}});
          if (!data) return;
          course.topics[ti].tags = data.tags || [];
          render(); markDirty();
          setStatus('✓ ' + (data.tags || []).length + ' etiquetas generadas para el tema. Revísalas y guarda.');
        }};
      }});

      // ----- QUIZ CONFIGURABLE (Fase 2): location, tipos, n_questions -----
      document.querySelectorAll('[data-topic-ai="quiz-config"]').forEach(btn => {{
        btn.onclick = async () => {{
          collectChanges();
          const ti = parseInt(btn.dataset.topic);
          const root = btn.closest('.ed-quiz-config');
          const location = root.querySelector('.ed-qc-location').value;
          const n = parseInt(root.querySelector('.ed-qc-n').value) || 5;
          const types = Array.from(root.querySelectorAll('.ed-qc-type:checked')).map(c => c.value);
          if (!types.length) {{ alert('Selecciona al menos un tipo de pregunta.'); return; }}

          const inlineCount = course.topics[ti].inline_quiz
            ? Object.values(course.topics[ti].inline_quiz).reduce((s, arr) => s + (arr ? arr.length : 0), 0)
            : 0;
          const finalCount = (course.topics[ti].quiz || []).length;
          if (finalCount + inlineCount > 0) {{
            if (!confirm('Esto reemplazará ' + finalCount + ' preguntas del bloque final y ' + inlineCount + ' intercaladas. ¿Continuar?')) return;
          }}

          const data = await callAI(btn, '/api/curso/' + TOKEN + '/ai-quiz-config', {{
            topic_index: ti, location: location, types: types, n_questions: n
          }});
          if (!data) return;
          // Recargar estructura para reflejar lo persistido en backend
          const r2 = await fetch('/api/curso/' + TOKEN + '/structure');
          if (r2.ok) {{
            course = await r2.json();
            render(); markDirty();
            const inlineGen = Object.values(data.by_subsection_count || {{}}).reduce((s, n) => s + n, 0);
            setStatus('✓ Quiz generado: ' + data.final_count + ' del bloque final + ' + inlineGen + ' intercaladas. Guarda para reempaquetar.');
          }}
        }};
      }});

      // ----- BANCO AIKEN EXTENDIDO -----
      const aikenBtn = document.getElementById('ed-aiken-ext');
      if (aikenBtn) {{
        aikenBtn.onclick = async () => {{
          if (!confirm('Esto pedirá a la IA 30 preguntas adicionales por cada tema (banco para evaluación externa). Puede tardar varios minutos. ¿Continuar?')) return;
          collectChanges();
          const data = await callAI(aikenBtn, '/api/curso/' + TOKEN + '/ai-aiken-extendido', {{n: 30}});
          if (!data) return;
          const list = (data.files || []).map(f => '• ' + f).join('\\n');
          alert('✓ Banco Aiken extendido generado:\\n\\n' + list + '\\n\\nLos archivos están en la carpeta del curso (aiken_extendido/). Cuando guardes el curso se incluirán en el ZIP descargable.');
          setStatus('✓ ' + (data.files || []).length + ' bancos Aiken extendidos generados.');
        }};
      }}

      // ----- EXPORT IMS CONTENT PACKAGE -----
      const imsBtn = document.getElementById('ed-export-imscp');
      if (imsBtn) {{
        imsBtn.onclick = async () => {{
          if (dirty) {{
            if (!confirm('Hay cambios sin guardar. El IMS CP se generará con la última versión guardada. ¿Continuar?')) return;
          }}
          imsBtn.disabled = true;
          const orig = imsBtn.textContent;
          imsBtn.textContent = '⏳ Empaquetando…';
          try {{
            const r = await fetch('/api/curso/' + TOKEN + '/export-imscp', {{
              method: 'POST',
              headers: {{'Content-Type': 'application/json'}}, body: '{{}}'
            }});
            const data = await r.json();
            if (!r.ok) {{ alert('Error: ' + (data.error || 'desconocido')); return; }}
            // El backend deja el archivo en la carpeta del curso. Damos enlace de descarga.
            window.location.href = '/curso/' + TOKEN + '/export/imscp';
          }} catch (e) {{
            alert('Error: ' + e.message);
          }} finally {{
            imsBtn.disabled = false;
            imsBtn.textContent = orig;
          }}
        }};
      }}

      // ============================================================
      // HANDLERS FASE 4: alt-text IA, WCAG check, vista previa iframe
      // ============================================================

      // ----- BOTÓN "Sugerir alt con IA" en bloques imagen -----
      document.querySelectorAll('.ed-alt-ia').forEach(btn => {{
        btn.onclick = async () => {{
          collectChanges();
          const ti = parseInt(btn.dataset.topic);
          const si = parseInt(btn.dataset.sub);
          const bi = parseInt(btn.dataset.block);
          const filename = btn.dataset.filename;
          if (!filename) {{
            alert('El bloque no tiene archivo asociado. Pega primero el nombre del fichero en /recursos o súbelo desde el formulario inicial.');
            return;
          }}
          const data = await callAI(btn, '/api/curso/' + TOKEN + '/ai-alt-text-block',
                                    {{filename: filename}});
          if (!data) return;
          // Aplicar el alt sugerido al campo "text" del bloque
          const block = course.topics[ti].subsections[si].blocks[bi];
          if (block) {{
            // Preguntar si hay alt previo
            const prev = (block.text || '').trim();
            if (prev) {{
              if (!confirm('La imagen ya tiene texto:\\n\\n"' + prev + '"\\n\\n¿Reemplazarlo por la sugerencia de la IA?\\n\\n"' + data.alt + '"')) return;
            }}
            block.text = data.alt;
            render(); markDirty();
            setStatus('✓ Alt-text generado: "' + data.alt + '"');
          }}
        }};
      }});

      // ----- BOTÓN "Validar WCAG 2.1 AA" -----
      const wcagBtn = document.getElementById('ed-wcag-check');
      if (wcagBtn) {{
        wcagBtn.onclick = async () => {{
          collectChanges();
          // Guardar primero (silenciosamente) para que el validador lea estructura actualizada
          if (dirty) {{
            const r = await fetch(API_SAVE, {{
              method: 'POST',
              headers: {{'Content-Type': 'application/json'}},
              body: JSON.stringify(course)
            }});
            if (!r.ok) {{
              const errData = await r.json().catch(() => ({{}}));
              alert('No se pudo guardar antes de validar: ' + (errData.error || 'error desconocido'));
              return;
            }}
            dirty = false; courseSnapshot = JSON.parse(JSON.stringify(course));
          }}
          const orig = wcagBtn.textContent;
          wcagBtn.disabled = true; wcagBtn.textContent = '⏳ Validando…';
          try {{
            const r = await fetch('/api/curso/' + TOKEN + '/wcag-check', {{method: 'POST'}});
            const report = await r.json();
            if (!r.ok) {{ alert('Error: ' + (report.error || 'desconocido')); return; }}
            showWcagModal(report);
          }} finally {{
            wcagBtn.disabled = false; wcagBtn.textContent = orig;
          }}
        }};
      }}

      function showWcagModal(report) {{
        // Cierra modal previo si existe
        document.querySelectorAll('.ed-modal-overlay').forEach(m => m.remove());
        const overlay = document.createElement('div');
        overlay.className = 'ed-modal-overlay';
        overlay.onclick = (e) => {{ if (e.target === overlay) overlay.remove(); }};
        const summary = report.passes
          ? '<p class="ed-modal-ok">✓ ' + report.n_errors + ' errores bloqueantes, ' + report.n_warnings + ' avisos. <strong>Pasa la validación.</strong></p>'
          : '<p class="ed-modal-ko">✗ ' + report.n_errors + ' errores bloqueantes, ' + report.n_warnings + ' avisos. <strong>No pasa.</strong></p>';
        let body = '';
        const issuesByLoc = {{}};
        (report.issues || []).forEach(i => {{
          const k = i.location || '(general)';
          (issuesByLoc[k] = issuesByLoc[k] || []).push(i);
        }});
        Object.keys(issuesByLoc).sort().forEach(loc => {{
          body += '<div class="wcag-loc"><h4>' + escapeHtml(loc) + '</h4><ul>';
          issuesByLoc[loc].forEach(i => {{
            const sevClass = 'wcag-' + i.severity;
            const sevIcon = i.severity === 'error' ? '🔴' : (i.severity === 'warning' ? '🟡' : 'ℹ️');
            body += '<li class="' + sevClass + '">' + sevIcon + ' <strong>' + escapeHtml(i.code) + '</strong> ' + escapeHtml(i.title) + '<br><span class="wcag-desc">' + escapeHtml(i.description) + '</span></li>';
          }});
          body += '</ul></div>';
        }});
        if (!report.issues || !report.issues.length) {{
          body = '<p>Sin problemas detectados.</p>';
        }}
        overlay.innerHTML = '<div class="ed-modal-card">' +
          '<div class="ed-modal-head"><h3>Informe WCAG 2.1 AA</h3><button type="button" class="ed-modal-close" aria-label="Cerrar">×</button></div>' +
          '<div class="ed-modal-body">' + summary + body + '</div>' +
          '</div>';
        document.body.appendChild(overlay);
        overlay.querySelector('.ed-modal-close').onclick = () => overlay.remove();
      }}

      // ----- BOTÓN "Vista previa del SCORM" -----
      const previewBtn = document.getElementById('ed-preview');
      if (previewBtn) {{
        previewBtn.onclick = async () => {{
          collectChanges();
          if (dirty) {{
            const r = await fetch(API_SAVE, {{
              method: 'POST',
              headers: {{'Content-Type': 'application/json'}},
              body: JSON.stringify(course)
            }});
            if (!r.ok) {{
              const errData = await r.json().catch(() => ({{}}));
              alert('No se pudo guardar antes de previsualizar: ' + (errData.error || 'error desconocido'));
              return;
            }}
            dirty = false; courseSnapshot = JSON.parse(JSON.stringify(course));
          }}
          showPreviewModal(0);
        }};
      }}

      function showPreviewModal(topicIndex) {{
        document.querySelectorAll('.ed-modal-overlay').forEach(m => m.remove());
        const overlay = document.createElement('div');
        overlay.className = 'ed-modal-overlay';
        overlay.onclick = (e) => {{ if (e.target === overlay) overlay.remove(); }};

        // Selector de tema si hay más de uno
        let selector = '';
        if (course.topics.length > 1) {{
          selector = '<select id="ed-preview-topic">';
          course.topics.forEach((t, i) => {{
            const sel = i === topicIndex ? ' selected' : '';
            selector += '<option value="' + i + '"' + sel + '>Tema ' + t.number + ': ' + escapeHtml(t.title) + '</option>';
          }});
          selector += '</select>';
        }}

        // Selector de snapshot (versión actual vs anteriores)
        const snapSelector = '<select id="ed-preview-snap" title="Versión: actual o snapshot anterior"><option value="">Versión actual</option></select>';

        const iframeSrc = '/api/curso/' + TOKEN + '/preview-html?topic_index=' + topicIndex;
        overlay.innerHTML = '<div class="ed-modal-card ed-modal-preview">' +
          '<div class="ed-modal-head">' +
            '<h3>👁 Vista previa del SCORM</h3>' +
            selector +
            snapSelector +
            '<button type="button" class="ed-modal-close" aria-label="Cerrar">×</button>' +
          '</div>' +
          '<div class="ed-modal-body ed-modal-body-iframe">' +
            '<iframe src="' + iframeSrc + '" title="Vista previa del tema"></iframe>' +
          '</div>' +
          '</div>';
        document.body.appendChild(overlay);
        overlay.querySelector('.ed-modal-close').onclick = () => overlay.remove();

        const topicSel = overlay.querySelector('#ed-preview-topic');
        const snapSel = overlay.querySelector('#ed-preview-snap');

        function rebuildIframe() {{
          const ti = topicSel ? parseInt(topicSel.value) : 0;
          const snap = snapSel.value;
          let url = '/api/curso/' + TOKEN + '/preview-html';
          if (snap) url += '/' + encodeURIComponent(snap);
          url += '?topic_index=' + ti;
          overlay.querySelector('iframe').src = url;
        }}
        if (topicSel) topicSel.onchange = rebuildIframe;
        if (snapSel) snapSel.onchange = rebuildIframe;

        // Cargar snapshots disponibles
        fetch('/api/curso/' + TOKEN + '/snapshots')
          .then(r => r.json())
          .then(data => {{
            const snaps = (data && data.snapshots) || [];
            if (!snaps.length) return;
            snaps.forEach(s => {{
              const opt = document.createElement('option');
              opt.value = s.id;
              opt.textContent = '📸 ' + s.id;
              snapSel.appendChild(opt);
            }});
          }})
          .catch(() => {{}});
      }}


      // ============================================================
      // HANDLERS FASE 5: enrich callouts, copyright, cmi5, snapshots
      // ============================================================

      // ----- ENRICH: Sugerencias de callouts IA -----
      document.querySelectorAll('[data-topic-ai="enrich"]').forEach(btn => {{
        btn.onclick = async () => {{
          collectChanges();
          const ti = parseInt(btn.dataset.topic);
          // Guardar antes de enviar para que la IA vea el contenido actual
          if (dirty) {{
            const r = await fetch(API_SAVE, {{
              method: 'POST',
              headers: {{'Content-Type': 'application/json'}},
              body: JSON.stringify(course)
            }});
            if (!r.ok) {{ alert('Guarda los cambios manualmente primero.'); return; }}
            dirty = false; courseSnapshot = JSON.parse(JSON.stringify(course));
          }}
          const data = await callAI(btn, '/api/curso/' + TOKEN + '/ai-enrich',
                                    {{topic_index: ti}});
          if (!data) return;
          if (!data.suggestions || !data.suggestions.length) {{
            alert('La IA no ha detectado ningún párrafo que encaje claramente con un callout.');
            return;
          }}
          showEnrichModal(ti, data.suggestions, data.truncated);
        }};
      }});

      function showEnrichModal(topicIndex, suggestions, truncated) {{
        document.querySelectorAll('.ed-modal-overlay').forEach(m => m.remove());
        const overlay = document.createElement('div');
        overlay.className = 'ed-modal-overlay';
        overlay.onclick = (e) => {{ if (e.target === overlay) overlay.remove(); }};

        let body = '<p>La IA propone convertir los siguientes párrafos en callouts. ' +
                   'Marca los que quieras aplicar y pulsa "Aplicar seleccionados".</p>';
        if (truncated) body += '<p style="color:var(--warn);font-size:0.85rem;">⚠ Solo se muestran los primeros 30 candidatos (el tema es largo).</p>';
        body += '<ul class="enrich-list">';
        suggestions.forEach((s, i) => {{
          const typeLabel = {{
            'callout_key': '🔑 CLAVE',
            'callout_alert': '⚠️ ALERTA',
            'callout_warn': '⚡ CUIDADO',
            'callout_success': '✓ ÉXITO',
            'quote': '" CITA',
          }}[s.suggested_type] || s.suggested_type;
          body += '<li class="enrich-item">' +
            '<label class="enrich-check"><input type="checkbox" class="enrich-cb" data-i="' + i + '" checked> Aplicar</label>' +
            '<div class="enrich-type">' + typeLabel + '</div>' +
            '<div class="enrich-reason">' + escapeHtml(s.reason || '') + '</div>' +
            '<div class="enrich-before"><strong>Original:</strong> ' + escapeHtml(s.current_text) + '</div>' +
            '<div class="enrich-after"><strong>Propuesto:</strong> ' + escapeHtml(s.suggested_text) + '</div>' +
            '</li>';
        }});
        body += '</ul>';

        overlay.innerHTML = '<div class="ed-modal-card">' +
          '<div class="ed-modal-head">' +
            '<h3>✨ Enriquecer con callouts IA — ' + suggestions.length + ' sugerencias</h3>' +
            '<button type="button" class="ed-modal-close" aria-label="Cerrar">×</button>' +
          '</div>' +
          '<div class="ed-modal-body">' + body + '</div>' +
          '<div class="ed-modal-foot">' +
            '<button type="button" class="btn secondary" id="ed-enrich-toggle-all">Marcar/desmarcar todas</button>' +
            '<button type="button" class="btn" id="ed-enrich-apply">Aplicar seleccionados</button>' +
          '</div>' +
          '</div>';
        document.body.appendChild(overlay);
        overlay.querySelector('.ed-modal-close').onclick = () => overlay.remove();
        overlay.querySelector('#ed-enrich-toggle-all').onclick = () => {{
          const checks = overlay.querySelectorAll('.enrich-cb');
          const anyOff = Array.from(checks).some(c => !c.checked);
          checks.forEach(c => c.checked = anyOff);
        }};
        overlay.querySelector('#ed-enrich-apply').onclick = async () => {{
          const accepted = [];
          overlay.querySelectorAll('.enrich-cb').forEach(c => {{
            if (c.checked) {{
              accepted.push(suggestions[parseInt(c.dataset.i)]);
            }}
          }});
          if (!accepted.length) {{ alert('Selecciona al menos una sugerencia.'); return; }}
          const r = await fetch('/api/curso/' + TOKEN + '/apply-enrich', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{topic_index: topicIndex, accepted: accepted}}),
          }});
          const data = await r.json();
          if (!r.ok) {{ alert('Error: ' + (data.error || 'desconocido')); return; }}
          overlay.remove();
          // Recargar estructura
          const r2 = await fetch(API_GET);
          if (r2.ok) {{
            course = await r2.json();
            courseSnapshot = JSON.parse(JSON.stringify(course));
            dirty = false;
            render();
            setStatus('✓ ' + data.applied + ' callouts aplicados. Snapshot previo: ' + (data.snapshot_id || '—'));
          }}
        }};
      }}

      // ----- COPYRIGHT: análisis de imagen -----
      document.querySelectorAll('.ed-copyright-ia').forEach(btn => {{
        btn.onclick = async () => {{
          const filename = btn.dataset.filename;
          if (!filename) {{ alert('Imagen sin archivo asociado.'); return; }}
          const data = await callAI(btn, '/api/curso/' + TOKEN + '/ai-copyright',
                                    {{filename: filename}});
          if (!data) return;
          showCopyrightModal(filename, data);
        }};
      }});

      function showCopyrightModal(filename, report) {{
        document.querySelectorAll('.ed-modal-overlay').forEach(m => m.remove());
        const overlay = document.createElement('div');
        overlay.className = 'ed-modal-overlay';
        overlay.onclick = (e) => {{ if (e.target === overlay) overlay.remove(); }};
        const riskClass = 'risk-' + report.risk_level;
        const riskLabel = {{
          'low': '✓ Riesgo bajo',
          'medium': '⚠ Riesgo medio',
          'high': '⛔ Riesgo alto',
        }}[report.risk_level] || report.risk_level;
        const concernsHtml = (report.concerns || []).map(c => '<li>' + escapeHtml(c) + '</li>').join('');

        overlay.innerHTML = '<div class="ed-modal-card">' +
          '<div class="ed-modal-head">' +
            '<h3>⚠️ Análisis de copyright — ' + escapeHtml(filename) + '</h3>' +
            '<button type="button" class="ed-modal-close" aria-label="Cerrar">×</button>' +
          '</div>' +
          '<div class="ed-modal-body">' +
            '<div class="copy-risk ' + riskClass + '"><strong>' + riskLabel + '</strong></div>' +
            '<p class="copy-summary">' + escapeHtml(report.summary) + '</p>' +
            (concernsHtml ? '<h4>Elementos detectados</h4><ul class="copy-concerns">' + concernsHtml + '</ul>' : '') +
            (report.recommendation ? '<div class="copy-reco"><strong>Recomendación:</strong> ' + escapeHtml(report.recommendation) + '</div>' : '') +
          '</div>' +
          '</div>';
        document.body.appendChild(overlay);
        overlay.querySelector('.ed-modal-close').onclick = () => overlay.remove();
      }}

      // ----- CMI5 EXPORT -----
      const cmi5Btn = document.getElementById('ed-export-cmi5');
      if (cmi5Btn) {{
        cmi5Btn.onclick = async () => {{
          if (dirty) {{
            if (!confirm('Hay cambios sin guardar. El paquete cmi5 se generará con la última versión guardada. ¿Continuar?')) return;
          }}
          const orig = cmi5Btn.textContent;
          cmi5Btn.disabled = true; cmi5Btn.textContent = '⏳ Empaquetando…';
          try {{
            const r = await fetch('/api/curso/' + TOKEN + '/export-cmi5', {{method: 'POST'}});
            const data = await r.json();
            if (!r.ok) {{ alert('Error: ' + (data.error || 'desconocido')); return; }}
            window.location.href = '/curso/' + TOKEN + '/export/cmi5';
          }} finally {{
            cmi5Btn.disabled = false; cmi5Btn.textContent = orig;
          }}
        }};
      }}

      // ----- APLICAR MEJORAS IA AL CURSO COMPLETO (v0.5.1) -----
      const enrichAllBtn = document.getElementById('ed-enrich-all');
      if (enrichAllBtn) {{
        enrichAllBtn.onclick = async () => {{
          collectChanges();
          if (dirty) {{
            const r = await fetch(API_SAVE, {{
              method: 'POST',
              headers: {{'Content-Type': 'application/json'}},
              body: JSON.stringify(course)
            }});
            if (!r.ok) {{ alert('Guarda los cambios manualmente primero.'); return; }}
            dirty = false; courseSnapshot = JSON.parse(JSON.stringify(course));
          }}
          if (!confirm('La IA va a procesar todos los temas para:\\n' +
                       '  • Generar etiquetas (tags) en los temas que no tengan.\\n' +
                       '  • Convertir párrafos clave en callouts ([CLAVE], [ALERTA]...).\\n' +
                       '  • Crear un quiz mixto (test + V/F + huecos) en los temas con < 3 preguntas.\\n\\n' +
                       'Se creará una snapshot previa por si quieres revertir.\\n' +
                       'Esto puede tardar 30-90 segundos por tema.\\n\\n¿Continuar?')) return;

          const orig = enrichAllBtn.textContent;
          enrichAllBtn.disabled = true;
          enrichAllBtn.textContent = '⏳ Procesando temas... (puede tardar 1-2 min)';
          try {{
            const r = await fetch('/api/curso/' + TOKEN + '/ai-enrich-all', {{method: 'POST'}});
            const data = await r.json();
            if (!r.ok) {{ alert('Error: ' + (data.error || 'desconocido')); return; }}
            const s = data.summary || {{}};

            // Recargar estructura
            const r2 = await fetch(API_GET);
            if (r2.ok) {{
              course = await r2.json();
              courseSnapshot = JSON.parse(JSON.stringify(course));
              dirty = false;
              render();
            }}

            let msg = '✓ Mejoras IA aplicadas:\\n\\n';
            msg += '  • ' + (s.topics_processed || 0) + ' tema(s) procesados\\n';
            msg += '  • ' + (s.tags_generated || 0) + ' etiquetas generadas\\n';
            msg += '  • ' + (s.callouts_applied || 0) + ' callouts aplicados\\n';
            msg += '  • ' + (s.quiz_final_generated || 0) + ' preguntas del bloque final generadas\\n';
            msg += '  • ' + (s.quiz_inline_generated || 0) + ' preguntas de repaso intercaladas\\n';
            if (s.errors && s.errors.length) {{
              msg += '\\n⚠ ' + s.errors.length + ' error(es):\\n  - ' + s.errors.join('\\n  - ');
            }}
            msg += '\\n\\nSnapshot previa: ' + (data.snapshot_id || '—');
            msg += '\\n\\n¿Abrir vista previa para ver el resultado?';
            if (confirm(msg)) {{
              showPreviewModal(0);
            }} else {{
              setStatus('✓ Mejoras aplicadas. Pulsa "👁 Vista previa" cuando quieras ver el resultado.');
            }}
          }} catch (e) {{
            alert('Error: ' + e.message);
          }} finally {{
            enrichAllBtn.disabled = false;
            enrichAllBtn.textContent = orig;
          }}
        }};
      }}

      // ----- Menús de reescritura por bloque -----
      document.querySelectorAll('.ed-ai-opt').forEach(btn => {{
        btn.onclick = async () => {{
          collectChanges();
          const ti = parseInt(btn.dataset.topic);
          const si = parseInt(btn.dataset.sub);
          const bi = parseInt(btn.dataset.block);
          const tone = btn.dataset.rewrite;
          const block = course.topics[ti].subsections[si].blocks[bi];
          const orig = block.text || '';
          if (!orig.trim()) {{ alert('Bloque vacío.'); return; }}
          const data = await callAI(btn, '/api/curso/' + TOKEN + '/ai-rewrite',
            {{text: orig, tone: tone}});
          if (!data) return;
          const newText = (data.text || '').trim();
          if (!newText) return;
          // Mostrar diálogo con before/after
          if (confirm('Reescritura propuesta (modo "' + tone + '"):\\n\\n' + newText + '\\n\\n¿Aplicar?')) {{
            block.text = newText;
            render();
            markDirty(); setStatus('✓ Texto reescrito.');
          }}
          // Cerrar el menú desplegable
          const menu = btn.closest('details');
          if (menu) menu.open = false;
        }};
      }});

      // Botones de borrar pregunta
      document.querySelectorAll('.btn-del-q').forEach(btn => {{
        btn.onclick = () => {{
          if (!confirm('¿Borrar esta pregunta?')) return;
          collectChanges();
          const ti = parseInt(btn.dataset.topic);
          const qi = parseInt(btn.dataset.quiz);
          course.topics[ti].quiz.splice(qi, 1);
          render();
        }};
      }});

      // ----- Input listener: marcar dirty al teclear -----
      document.querySelectorAll('input, textarea').forEach(el => {{
        el.addEventListener('input', markDirty);
        el.addEventListener('change', markDirty);
      }});

      // ----- Acciones estructurales (subir / bajar / borrar / añadir) -----
      function moveItem(arr, from, to) {{
        if (to < 0 || to >= arr.length) return;
        const x = arr.splice(from, 1)[0];
        arr.splice(to, 0, x);
      }}
      function renumberSubs(t) {{
        t.subsections.forEach((s, i) => {{
          s.number = t.number + '.' + (i + 1);
          s.id = 'l' + (i + 1);
        }});
      }}
      function renumberTopics() {{
        course.topics.forEach((t, i) => {{
          t.number = i + 1;
          renumberSubs(t);
        }});
      }}
      document.querySelectorAll('[data-action]').forEach(btn => {{
        btn.onclick = () => {{
          collectChanges();
          const a = btn.dataset.action;
          const ti = btn.dataset.topic !== undefined ? parseInt(btn.dataset.topic) : -1;
          const si = btn.dataset.sub !== undefined ? parseInt(btn.dataset.sub) : -1;
          const bi = btn.dataset.block !== undefined ? parseInt(btn.dataset.block) : -1;

          if (a === 'sub-illustration') {{
            // Caso especial: llamada async a IA
            (async () => {{
              const data = await callAI(btn, '/api/curso/' + TOKEN + '/ai-illustration',
                {{topic_index: ti, sub_index: si, style: 'flat'}});
              if (!data) return;
              // Insertar bloque IMAGE al principio del subapartado
              course.topics[ti].subsections[si].blocks.unshift({{
                type: 'image',
                text: 'Ilustración generada por IA',
                items: [], rows: [],
                extras: {{src: data.filename, file: data.filename}},
              }});
              render();
              markDirty(); setStatus('✓ Ilustración generada e insertada.');
            }})();
            return;
          }}

          if (a === 'topic-up') moveItem(course.topics, ti, ti - 1);
          else if (a === 'topic-down') moveItem(course.topics, ti, ti + 1);
          else if (a === 'topic-del') {{
            if (!confirm('¿Borrar este tema y todo su contenido?')) return;
            course.topics.splice(ti, 1);
          }} else if (a === 'topic-add') {{
            const newNum = course.topics.length + 1;
            course.topics.push({{
              number: newNum, title: 'Nuevo tema', intro: '',
              subsections: [{{
                id: 'l1', number: newNum + '.1', title: 'Nuevo subapartado',
                blocks: [{{type:'paragraph', text:'Contenido del subapartado.', items:[], rows:[], extras:{{}}}}]
              }}],
              quiz: []
            }});
          }} else if (a === 'sub-up') moveItem(course.topics[ti].subsections, si, si - 1);
          else if (a === 'sub-down') moveItem(course.topics[ti].subsections, si, si + 1);
          else if (a === 'sub-del') {{
            if (!confirm('¿Borrar este subapartado?')) return;
            course.topics[ti].subsections.splice(si, 1);
          }} else if (a === 'sub-add') {{
            const t = course.topics[ti];
            const idx = t.subsections.length + 1;
            t.subsections.push({{
              id: 'l' + idx, number: t.number + '.' + idx,
              title: 'Nuevo subapartado',
              blocks: [{{type:'paragraph', text:'Contenido del subapartado.', items:[], rows:[], extras:{{}}}}]
            }});
          }} else if (a === 'block-up') moveItem(course.topics[ti].subsections[si].blocks, bi, bi - 1);
          else if (a === 'block-down') moveItem(course.topics[ti].subsections[si].blocks, bi, bi + 1);
          else if (a === 'block-del') {{
            if (!confirm('¿Borrar este bloque?')) return;
            course.topics[ti].subsections[si].blocks.splice(bi, 1);
          }} else if (a === 'block-add') {{
            const bt = btn.dataset.blocktype || 'paragraph';
            const block = {{type: bt, text: '', items: [], rows: [], extras: {{}}}};
            if (bt === 'list_bullet' || bt === 'list_number') block.items = ['Elemento 1'];
            else if (['image','video','audio','embed','resource','download'].includes(bt)) {{
              block.text = 'Pie de ' + bt;
              block.extras = {{src: '', file: ''}};
            }} else {{
              block.text = 'Texto del bloque';
            }}
            // Insertar en posición concreta si data-position lo indica, o al final si no
            const insertAt = btn.dataset.position !== undefined ? parseInt(btn.dataset.position) : course.topics[ti].subsections[si].blocks.length;
            course.topics[ti].subsections[si].blocks.splice(insertAt, 0, block);
          }} else if (a === 'item-add') {{
            const blk = course.topics[ti].subsections[si].blocks[bi];
            blk.items = blk.items || [];
            blk.items.push('Nuevo item');
          }} else if (a === 'item-del') {{
            const ii = parseInt(btn.dataset.item);
            const blk = course.topics[ti].subsections[si].blocks[bi];
            if (blk.items && blk.items.length > 1) {{
              blk.items.splice(ii, 1);
            }} else {{
              alert('Una lista debe tener al menos un item. Borra el bloque entero si quieres eliminar la lista.');
              return;
            }}
          }}

          renumberTopics();
          markDirty();
          render();
        }};
      }});
    }}

    function blockLabel(t) {{
      const labels = {{
        paragraph: 'Párrafo', heading_3: 'H3', heading_4: 'H4',
        list_bullet: 'Lista', list_number: 'Lista numerada',
        callout_key: 'CLAVE', callout_alert: 'ALERTA', callout_success: 'ÉXITO', callout_warn: 'CUIDADO',
        quote: 'CITA', download: 'DESCARGABLE', table: 'TABLA',
        image: 'IMAGEN', video: 'VIDEO', audio: 'AUDIO', embed: 'EMBED', resource: 'RECURSO',
        example: 'EJEMPLO',
      }};
      return labels[t] || t;
    }}

    function blockEditor(ti, si, bi, b) {{
      const t = b.type;
      const dataAttrs = 'data-topic="' + ti + '" data-sub="' + si + '" data-block="' + bi + '"';
      if (t === 'list_bullet' || t === 'list_number') {{
        const items = (b.items || []).map((it, ii) => {{
          return '<div class="ed-list-row">' +
            '<input type="text" ' + dataAttrs + ' data-item="' + ii + '" value="' + escapeHtml(it) + '">' +
            '<button type="button" class="btn-struct btn-mini btn-del" data-action="item-del" data-topic="' + ti + '" data-sub="' + si + '" data-block="' + bi + '" data-item="' + ii + '" title="Borrar este item">🗑</button>' +
            '</div>';
        }}).join('');
        const addBtn = '<button type="button" class="btn-struct btn-mini" data-action="item-add" data-topic="' + ti + '" data-sub="' + si + '" data-block="' + bi + '">+ Item</button>';
        return '<div class="ed-list">' + items + addBtn + '</div>';
      }}
      if (t === 'table') {{
        const nRows = (b.rows || []).length;
        return '<em class="ed-readonly">📊 Tabla con ' + nRows + ' filas. Edita la tabla en el Word original (no editable inline).</em>';
      }}
      if (['image', 'video', 'audio', 'embed', 'resource', 'download'].includes(t)) {{
        const placeholder = (t === 'embed') ? 'URL de YouTube/Vimeo' : 'archivo en /recursos o URL';
        // Si es imagen, añadimos botones "Sugerir alt" y "Comprobar copyright"
        let altBtn = '';
        let copyBtn = '';
        if (t === 'image') {{
          const src = (b.extras && b.extras.src) || '';
          const isLocal = src && !/^(https?:|data:)/i.test(src);
          if (isLocal) {{
            altBtn = '<button type="button" class="btn-ai-mini ed-alt-ia" ' + dataAttrs + ' data-filename="' + escapeHtml(src) + '" title="Generar texto alternativo descriptivo con IA (WCAG 1.1.1)">🤖 Sugerir alt con IA</button>';
            copyBtn = '<button type="button" class="btn-ai-mini ed-copyright-ia" ' + dataAttrs + ' data-filename="' + escapeHtml(src) + '" title="Evaluar riesgo de copyright con IA de visión">⚠️ Comprobar copyright</button>';
          }}
        }}
        return '<div class="ed-multimedia">' +
          '<input type="text" ' + dataAttrs + ' data-field="text" placeholder="Pie/Título (alt-text para imágenes)" value="' + escapeHtml(b.text || '') + '">' +
          '<input type="text" ' + dataAttrs + ' data-extra="src" placeholder="' + placeholder + '" value="' + escapeHtml((b.extras && b.extras.src) || '') + '">' +
          altBtn + copyBtn +
          '</div>';
      }}
      // Texto largo: textarea
      if (t === 'paragraph' || t === 'callout_key' || t === 'callout_alert' || t === 'callout_success' || t === 'callout_warn' || t === 'quote' || t === 'example') {{
        return '<textarea ' + dataAttrs + ' data-field="text">' + escapeHtml(b.text || '') + '</textarea>';
      }}
      // Headings cortos
      return '<input type="text" ' + dataAttrs + ' data-field="text" value="' + escapeHtml(b.text || '') + '">';
    }}

    function collectChanges() {{
      // Recoge todo del DOM y lo aplica a `course`
      document.querySelectorAll('[data-meta]').forEach(el => {{
        const k = el.dataset.meta;
        let v = el.value;
        if (['mastery','weight_view','weight_quiz','view_min_seconds'].includes(k)) v = parseInt(v) || 0;
        course.metadata[k] = v;
      }});
      document.querySelectorAll('[data-topic]').forEach(el => {{
        const ti = parseInt(el.dataset.topic);
        const t = course.topics[ti];
        if (!t) return;
        // Tema (title/intro)
        if (el.dataset.sub === undefined && el.dataset.quiz === undefined && el.dataset.field) {{
          t[el.dataset.field] = el.value;
          return;
        }}
        // Subapartado
        if (el.dataset.sub !== undefined) {{
          const si = parseInt(el.dataset.sub);
          const s = t.subsections[si];
          if (!s) return;
          if (el.dataset.block === undefined) {{
            // Editor del título del subapartado
            if (el.dataset.field) s[el.dataset.field] = el.value;
            return;
          }}
          const bi = parseInt(el.dataset.block);
          const b = s.blocks[bi];
          if (!b) return;
          if (el.dataset.field) b[el.dataset.field] = el.value;
          if (el.dataset.item !== undefined) {{
            const ii = parseInt(el.dataset.item);
            b.items = b.items || [];
            b.items[ii] = el.value;
          }}
          if (el.dataset.extra) {{
            b.extras = b.extras || {{}};
            b.extras[el.dataset.extra] = el.value;
            // mantenemos también "file" sincronizado para retrocompatibilidad
            if (el.dataset.extra === 'src') b.extras.file = el.value;
          }}
        }}
        // Quiz
        if (el.dataset.quiz !== undefined) {{
          const qi = parseInt(el.dataset.quiz);
          const q = t.quiz[qi];
          if (!q) return;
          if (el.dataset.field) {{
            q[el.dataset.field] = el.value;
          }}
          if (el.dataset.opt !== undefined) {{
            q.options[parseInt(el.dataset.opt)] = el.value;
          }}
          if (el.dataset.correct !== undefined && el.checked) {{
            q.correct_index = parseInt(el.dataset.correct);
          }}
        }}
      }});
    }}

    async function save() {{
      collectChanges();
      const status = document.getElementById('ed-status');
      const btn = document.getElementById('ed-save');
      btn.disabled = true;
      status.textContent = 'Reempaquetando…';
      try {{
        const r = await fetch(API_SAVE, {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify(course)
        }});
        const data = await r.json();
        if (!r.ok) {{
          // Errores de validación detallados
          if (data.validation_errors && Array.isArray(data.validation_errors)) {{
            const errsList = data.validation_errors.map(e => '  • ' + e).join('\\n');
            alert('No se puede guardar el curso:\\n\\n' + errsList +
                  '\\n\\nCorrige estos problemas y vuelve a intentarlo.');
            status.textContent = '✗ ' + data.validation_errors.length + ' problemas de estructura. Corrige y guarda.';
          }} else {{
            status.textContent = 'Error: ' + (data.error || 'desconocido');
          }}
          btn.disabled = false;
          return;
        }}
        // Save OK: reset del flag dirty y actualizar snapshot
        dirty = false;
        courseSnapshot = JSON.parse(JSON.stringify(course));
        const ind = document.getElementById('ed-dirty-indicator');
        if (ind) ind.style.display = 'none';
        status.textContent = '✓ Guardado correctamente. SCORM reempaquetado.';
        btn.disabled = false;
      }} catch (e) {{
        status.textContent = 'Error: ' + e.message;
        btn.disabled = false;
      }}
    }}

    // Restaurar último estado guardado
    function restoreSnapshot() {{
      if (!courseSnapshot) return;
      if (!dirty) {{ alert('No hay cambios pendientes que descartar.'); return; }}
      if (!confirm('¿Descartar todos los cambios desde el último guardado?')) return;
      course = JSON.parse(JSON.stringify(courseSnapshot));
      dirty = false;
      const ind = document.getElementById('ed-dirty-indicator');
      if (ind) ind.style.display = 'none';
      render();
      setStatus('✓ Cambios descartados. Estructura restaurada.');
    }}

    load();
    </script>

    <style>
    .ed-card {{ background: white; border-radius: 8px; padding: 1.5rem; margin-bottom: 1.2rem; box-shadow: 0 1px 4px rgba(0,0,0,0.05); }}
    .ed-card h2 {{ font-size: 1.1rem; margin-bottom: 1rem; color: var(--primary-deep); display: flex; align-items: center; gap: 0.5rem; }}
    .ed-card h3 {{ font-size: 0.95rem; margin: 1rem 0 0.6rem; color: var(--ink-soft); }}
    .ed-card input[type=text], .ed-card input[type=number], .ed-card textarea {{
      width: 100%; padding: 0.5rem 0.7rem; border: 1px solid var(--paper-deep); border-radius: 6px;
      font-family: inherit; font-size: 0.9rem; background: var(--paper-warm);
    }}
    .ed-card textarea {{ min-height: 3.2em; resize: vertical; }}
    .ed-card input[type=text]:focus, .ed-card textarea:focus {{ outline: 2px solid var(--primary-bright); border-color: var(--primary-bright); background: white; }}
    .ed-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 0.7rem; }}
    .ed-grid label {{ display: flex; flex-direction: column; gap: 0.3rem; font-size: 0.78rem; color: var(--ink-mute); font-weight: 600; }}
    @media (max-width:700px) {{ .ed-grid {{ grid-template-columns: 1fr; }} }}
    .ed-title {{ flex:1; font-size: 1rem !important; font-weight: 600 !important; }}
    .ed-sub {{ background: var(--paper-warm); border-radius: 6px; padding: 0.8rem 1rem; margin-top: 0.8rem; }}
    .ed-block-row {{ display: flex; gap: 0.6rem; margin: 0.4rem 0; align-items: flex-start; }}
    .ed-block-tag {{
      flex-shrink: 0; background: var(--primary-deep); color: white;
      padding: 0.2rem 0.55rem; border-radius: 4px; font-size: 0.7rem;
      font-family: monospace; font-weight: 700; min-width: 75px; text-align: center;
      margin-top: 0.5rem;
    }}
    .ed-block-row > input, .ed-block-row > textarea {{ flex: 1; }}
    .ed-list {{ display: flex; flex-direction: column; gap: 0.3rem; flex: 1; }}
    .ed-quiz {{ margin-top: 1rem; padding-top: 1rem; border-top: 1px dashed var(--paper-deep); }}
    .ed-question {{ background: var(--paper-warm); border-radius: 6px; padding: 0.8rem 1rem; margin-bottom: 0.8rem; }}
    .ed-q-text {{ margin: 0.4rem 0 0.7rem; }}
    .ed-opt {{ display: flex; gap: 0.5rem; align-items: center; margin: 0.3rem 0; }}
    .ed-opt input[type=radio] {{ width: auto; flex-shrink: 0; }}
    .ed-opt input[type=text] {{ flex: 1; }}
    .ed-expl {{ display: block; margin-top: 0.5rem; font-size: 0.78rem; color: var(--ink-mute); font-weight: 600; }}
    .ed-expl input {{ margin-top: 0.3rem; }}
    .ed-readonly {{ color: var(--ink-mute); font-size: 0.85rem; }}
    .ed-actions {{ display: flex; gap: 0.6rem; align-items: center; margin: 1.5rem 0 3rem; }}
    .ed-actions .btn {{ width: auto; }}
    .ed-quiz h3 {{ display: flex; align-items: center; gap: 0.7rem; flex-wrap: wrap; }}
    .ed-quiz-empty {{ background: var(--paper-warm); border-radius: 6px; padding: 1rem 1.2rem; }}
    .btn-ai {{
      background: linear-gradient(135deg, #8b5cf6, #6366f1); color: white; border: none;
      padding: 0.6rem 1.1rem; border-radius: 6px; cursor: pointer;
      font-family: inherit; font-size: 0.9rem; font-weight: 600;
    }}
    .btn-ai:hover:not(:disabled) {{ filter: brightness(1.1); }}
    .btn-ai:disabled {{ opacity: 0.5; cursor: not-allowed; }}
    .btn-ai-mini {{
      background: var(--primary-pale); color: var(--primary-deep); border: 1px solid var(--primary);
      padding: 0.25rem 0.6rem; border-radius: 4px; cursor: pointer;
      font-family: inherit; font-size: 0.75rem; font-weight: 600;
    }}
    .btn-ai-mini:hover:not(:disabled) {{ background: var(--primary-bright); color: white; }}
    .btn-ai-mini:disabled {{ opacity: 0.5; cursor: not-allowed; }}
    .btn-tiny {{
      background: transparent; color: var(--alert); border: 1px solid var(--alert);
      padding: 0.2rem 0.5rem; border-radius: 4px; cursor: pointer;
      font-family: inherit; font-size: 0.72rem; margin-top: 0.5rem;
    }}
    .btn-tiny:hover {{ background: var(--alert); color: white; }}
    #ed-status {{ font-size: 0.9rem; color: var(--ink-mute); margin-left: 0.6rem; }}

    /* Menú desplegable ✨ de reescritura */
    .ed-ai-menu {{ position: relative; flex-shrink: 0; margin-top: 0.3rem; }}
    .ed-ai-menu summary {{
      list-style: none; cursor: pointer;
      width: 32px; height: 32px;
      background: linear-gradient(135deg, #8b5cf6, #6366f1);
      color: white; border-radius: 6px;
      display: flex; align-items: center; justify-content: center;
      font-size: 1rem; user-select: none;
      transition: transform 0.15s;
    }}
    .ed-ai-menu summary::-webkit-details-marker {{ display: none; }}
    .ed-ai-menu summary:hover {{ transform: scale(1.05); }}
    .ed-ai-menu[open] summary {{ transform: scale(1.1); box-shadow: 0 0 0 2px white, 0 0 0 4px #8b5cf6; }}
    .ed-ai-menu[open] {{
      background: white; border: 1px solid var(--paper-deep); border-radius: 6px;
      box-shadow: 0 4px 16px rgba(0,0,0,0.12);
      position: absolute; right: 0; z-index: 100; width: 200px;
      padding: 0.4rem; display: flex; flex-direction: column; gap: 0.2rem;
    }}
    .ed-ai-menu[open] summary {{ position: absolute; top: -36px; right: 0; }}
    .ed-ai-opt {{
      background: transparent; border: none; padding: 0.5rem 0.7rem;
      text-align: left; cursor: pointer; border-radius: 4px;
      font-family: inherit; font-size: 0.85rem; color: var(--ink);
    }}
    .ed-ai-opt:hover {{ background: var(--primary-mist); }}

    /* Botonera a nivel de tema */
    .ed-topic-ai {{
      display: flex; gap: 0.5rem; flex-wrap: wrap;
      margin-top: 0.8rem; padding-top: 0.8rem;
      border-top: 1px dashed var(--paper-deep);
    }}

    /* Controles estructurales */
    .ed-topic-head, .ed-sub-head {{
      display: flex; align-items: flex-start; justify-content: space-between;
      gap: 0.7rem; flex-wrap: wrap;
    }}
    .ed-topic-head h2, .ed-sub-head h3 {{ flex: 1; min-width: 200px; }}
    .ed-struct-actions {{ display: flex; gap: 0.3rem; align-items: center; flex-shrink: 0; }}
    .btn-struct {{
      background: white; border: 1px solid var(--paper-deep);
      padding: 0.3rem 0.55rem; border-radius: 4px; cursor: pointer;
      font-family: inherit; font-size: 0.85rem; color: var(--ink-soft);
      line-height: 1; transition: all 0.15s;
    }}
    .btn-struct:hover {{ background: var(--paper-warm); border-color: var(--primary); color: var(--primary-deep); }}
    .btn-struct.btn-mini {{ padding: 0.2rem 0.4rem; font-size: 0.75rem; }}
    .btn-struct.btn-del:hover {{ background: var(--alert); color: white; border-color: var(--alert); }}
    .btn-struct.btn-add-wide {{
      width: 100%; margin-top: 0.6rem; padding: 0.5rem; background: var(--paper-warm);
      color: var(--ink-mute); border: 1px dashed var(--paper-deep); font-weight: 600;
    }}
    .btn-struct.btn-add-wide:hover {{
      background: var(--primary-mist); color: var(--primary-deep); border-color: var(--primary);
    }}
    .ed-block-struct {{
      display: flex; gap: 0.2rem; flex-shrink: 0; align-items: flex-start;
      margin-top: 0.3rem;
    }}
    .ed-add-block {{ margin-top: 0.5rem; }}
    .ed-add-block details {{ position: relative; }}
    .ed-add-block summary {{
      list-style: none; cursor: pointer; padding: 0.4rem 0.7rem;
      background: var(--paper-warm); border: 1px dashed var(--paper-deep);
      border-radius: 4px; font-size: 0.8rem; color: var(--ink-mute); user-select: none;
      display: inline-block;
    }}
    .ed-add-block summary::-webkit-details-marker {{ display: none; }}
    .ed-add-block summary:hover {{ background: var(--primary-mist); color: var(--primary-deep); }}
    .ed-add-block details[open] {{
      background: white; border: 1px solid var(--paper-deep); border-radius: 6px;
      padding: 0.5rem; margin-top: 0.3rem;
      display: flex; flex-wrap: wrap; gap: 0.3rem;
    }}
    .ed-add-block details[open] summary {{
      width: 100%; margin-bottom: 0.3rem; background: var(--primary-mist);
      color: var(--primary-deep); border-style: solid;
    }}
    .ed-add-opt {{
      background: var(--primary-pale); border: none; padding: 0.35rem 0.7rem;
      border-radius: 4px; cursor: pointer; font-family: inherit; font-size: 0.78rem;
      color: var(--primary-deep); font-weight: 600;
    }}
    .ed-add-opt:hover {{ background: var(--primary-bright); color: white; }}

    /* Listas con add/del de items */
    .ed-list-row {{ display: flex; gap: 0.4rem; align-items: center; margin-bottom: 0.25rem; }}
    .ed-list-row input {{ flex: 1; }}
    .ed-list .btn-struct.btn-mini {{ padding: 0.15rem 0.35rem; font-size: 0.7rem; }}

    /* Insertar entre bloques */
    .ed-insert-here {{ text-align: center; margin: 0.1rem 0; }}
    .btn-insert-here {{
      background: transparent; color: var(--ink-mute); border: 1px dashed transparent;
      padding: 0.15rem 0.6rem; border-radius: 4px; cursor: pointer;
      font-family: inherit; font-size: 0.72rem; font-style: italic;
      opacity: 0.4; transition: all 0.15s;
    }}
    .btn-insert-here:hover {{ opacity: 1; border-color: var(--primary); color: var(--primary-deep); background: var(--primary-mist); }}

    /* Multimedia con dos campos en columna */
    .ed-multimedia {{ display: flex; flex-direction: column; gap: 0.3rem; flex: 1; }}

    /* Grupos en el desplegable de añadir bloque */
    .ed-add-group {{ display: flex; flex-wrap: wrap; gap: 0.3rem; align-items: center; margin-bottom: 0.3rem; padding-bottom: 0.3rem; border-bottom: 1px dashed var(--paper-deep); }}
    .ed-add-group:last-child {{ border-bottom: none; }}
    .ed-add-label {{ font-size: 0.72rem; color: var(--ink-mute); font-weight: 600; min-width: 75px; }}

    /* =========================================================
       FASE 3 (v0.5): UI para etiquetas y asistente IA avanzado
       ========================================================= */
    .ed-tags-block {{
      margin: 1rem 0 0.6rem;
      padding: 0.9rem 1rem;
      background: var(--paper-warm, #FAF6EF);
      border: 1px solid var(--paper-deep);
      border-radius: 8px;
    }}
    .ed-tags-label {{
      display: block;
      font-weight: 600;
      color: var(--primary-deep);
      margin-bottom: 0.5rem;
      font-size: 0.95rem;
    }}
    .ed-tags-hint {{
      font-weight: 400;
      color: var(--ink-mute);
      font-size: 0.78rem;
    }}
    .ed-tags-list {{
      list-style: none; padding: 0; margin: 0 0 0.6rem;
      display: flex; flex-wrap: wrap; gap: 0.4rem;
      min-height: 1.6rem;
    }}
    .ed-tag-chip {{
      display: inline-flex; align-items: center; gap: 0.4rem;
      padding: 0.25rem 0.55rem 0.25rem 0.75rem;
      background: var(--primary-mist, #DBEAFE);
      color: var(--primary-deep);
      border-radius: 999px;
      font-size: 0.82rem;
      font-weight: 600;
    }}
    .ed-tag-del {{
      background: transparent; border: none; color: var(--primary-deep);
      cursor: pointer; font-size: 1rem; line-height: 1;
      padding: 0 0.1rem; opacity: 0.6;
      transition: opacity 0.15s;
    }}
    .ed-tag-del:hover {{ opacity: 1; color: var(--alert, #DC2626); }}
    .ed-tag-del:focus-visible {{ outline: 2px solid var(--primary); outline-offset: 1px; border-radius: 50%; }}
    .ed-tags-actions {{
      display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap;
    }}
    .ed-tag-input {{
      flex: 1; min-width: 200px;
      padding: 0.45rem 0.7rem; border: 1px solid var(--paper-deep);
      border-radius: 6px; font-family: inherit; font-size: 0.88rem;
    }}
    .ed-tag-input:focus {{
      outline: 2px solid var(--primary-bright);
      outline-offset: 1px;
      border-color: var(--primary);
    }}

    /* Panel "Asistente IA avanzado" colapsable */
    .ed-ai-advanced {{
      margin-top: 1rem;
      background: linear-gradient(135deg, rgba(139,92,246,0.05), rgba(99,102,241,0.05));
      border: 1px solid #c4b5fd;
      border-radius: 8px;
      overflow: hidden;
    }}
    .ed-ai-advanced > summary {{
      padding: 0.8rem 1rem;
      cursor: pointer;
      font-weight: 600;
      color: #5b21b6;
      background: rgba(139,92,246,0.08);
      list-style: none;
      user-select: none;
    }}
    .ed-ai-advanced > summary::-webkit-details-marker {{ display: none; }}
    .ed-ai-advanced > summary:hover {{ background: rgba(139,92,246,0.15); }}
    .ed-ai-advanced > summary::before {{
      content: '▸';
      display: inline-block;
      margin-right: 0.5rem;
      transition: transform 0.15s;
    }}
    .ed-ai-advanced[open] > summary::before {{ transform: rotate(90deg); }}
    .ed-ai-advanced-body {{
      padding: 1rem;
      display: flex; flex-direction: column; gap: 1rem;
    }}

    /* Configurador de quiz */
    .ed-quiz-config {{
      border: 1px solid var(--paper-deep);
      border-radius: 6px;
      padding: 1rem;
      margin: 0;
      background: white;
    }}
    .ed-quiz-config legend {{
      padding: 0 0.5rem;
      font-weight: 600;
      color: var(--primary-deep);
      font-size: 0.92rem;
    }}
    .ed-quiz-config-grid {{
      display: grid;
      grid-template-columns: 2fr 1fr;
      gap: 0.7rem;
      margin-bottom: 0.7rem;
    }}
    @media (max-width: 600px) {{
      .ed-quiz-config-grid {{ grid-template-columns: 1fr; }}
    }}
    .ed-quiz-config-grid label {{
      display: flex; flex-direction: column; gap: 0.25rem;
      font-size: 0.85rem; color: var(--ink-soft); font-weight: 600;
    }}
    .ed-quiz-config-grid select,
    .ed-quiz-config-grid input {{
      padding: 0.45rem 0.6rem;
      border: 1px solid var(--paper-deep);
      border-radius: 5px;
      font-family: inherit;
      font-size: 0.9rem;
    }}
    .ed-quiz-config-types {{
      display: flex; gap: 0.7rem; flex-wrap: wrap;
      margin-bottom: 0.7rem;
      padding-top: 0.5rem;
      border-top: 1px dashed var(--paper-deep);
    }}
    .ed-quiz-config-types label {{
      display: inline-flex; align-items: center; gap: 0.35rem;
      font-size: 0.88rem;
      font-weight: 500;
      cursor: pointer;
    }}
    .ed-qc-info {{
      font-size: 0.8rem;
      color: var(--ink-mute);
      margin: 0.5rem 0;
      padding: 0.5rem 0.6rem;
      background: var(--paper-warm, #FAF6EF);
      border-left: 3px solid var(--warn, #F59E0B);
      border-radius: 0 4px 4px 0;
    }}

    /* =========================================================
       FASE 4 (v0.5): modales para WCAG y vista previa
       ========================================================= */
    .ed-modal-overlay {{
      position: fixed; inset: 0;
      background: rgba(15, 23, 42, 0.6);
      z-index: 10000;
      display: flex; align-items: center; justify-content: center;
      padding: 1rem;
      animation: edModalFade 0.15s ease;
    }}
    @keyframes edModalFade {{
      from {{ opacity: 0; }} to {{ opacity: 1; }}
    }}
    .ed-modal-card {{
      background: white;
      border-radius: 10px;
      box-shadow: 0 12px 48px rgba(0,0,0,0.25);
      max-width: 900px; width: 100%;
      max-height: 90vh;
      display: flex; flex-direction: column;
      overflow: hidden;
    }}
    .ed-modal-preview {{ max-width: 1200px; }}
    .ed-modal-head {{
      display: flex; align-items: center;
      padding: 1rem 1.3rem;
      border-bottom: 1px solid var(--paper-deep);
      gap: 1rem;
    }}
    .ed-modal-head h3 {{
      margin: 0;
      font-size: 1.15rem;
      color: var(--primary-deep);
      flex: 1;
    }}
    .ed-modal-head select {{
      padding: 0.4rem 0.7rem;
      border: 1px solid var(--paper-deep);
      border-radius: 5px;
      font-family: inherit;
      font-size: 0.88rem;
      max-width: 360px;
    }}
    .ed-modal-close {{
      background: transparent;
      border: none;
      font-size: 1.6rem;
      line-height: 1;
      cursor: pointer;
      color: var(--ink-mute);
      padding: 0 0.4rem;
    }}
    .ed-modal-close:hover {{ color: var(--alert, #DC2626); }}
    .ed-modal-close:focus-visible {{
      outline: 2px solid var(--primary);
      border-radius: 4px;
    }}
    .ed-modal-body {{
      overflow-y: auto;
      padding: 1rem 1.3rem;
      flex: 1;
    }}
    .ed-modal-body-iframe {{
      padding: 0;
      display: flex;
    }}
    .ed-modal-body-iframe iframe {{
      flex: 1;
      width: 100%;
      min-height: 70vh;
      border: 0;
      background: white;
    }}

    /* Informe WCAG */
    .ed-modal-ok {{
      padding: 0.7rem 1rem;
      background: rgba(16,185,129,0.12);
      border-left: 4px solid #10B981;
      color: #064E3B;
      border-radius: 4px;
      margin-bottom: 1rem;
    }}
    .ed-modal-ko {{
      padding: 0.7rem 1rem;
      background: rgba(239,68,68,0.12);
      border-left: 4px solid #EF4444;
      color: #7F1D1D;
      border-radius: 4px;
      margin-bottom: 1rem;
    }}
    .wcag-loc {{
      margin-bottom: 1.2rem;
      padding: 0.7rem 0.9rem;
      background: var(--paper-warm, #FAF6EF);
      border-radius: 6px;
    }}
    .wcag-loc h4 {{
      margin: 0 0 0.5rem;
      font-size: 0.92rem;
      color: var(--primary-deep);
    }}
    .wcag-loc ul {{ list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 0.5rem; }}
    .wcag-loc li {{
      padding: 0.5rem 0.7rem;
      background: white;
      border-radius: 4px;
      border-left: 3px solid var(--paper-deep);
      font-size: 0.88rem;
    }}
    .wcag-loc li.wcag-error {{ border-left-color: #EF4444; }}
    .wcag-loc li.wcag-warning {{ border-left-color: #F59E0B; }}
    .wcag-loc li.wcag-info {{ border-left-color: #3B82F6; }}
    .wcag-desc {{
      display: block;
      color: var(--ink-mute);
      font-size: 0.82rem;
      margin-top: 0.3rem;
    }}

    /* =========================================================
       FASE 5 (v0.5): modales de enrich, copyright, snapshots
       ========================================================= */
    .ed-modal-foot {{
      display: flex;
      gap: 0.6rem;
      justify-content: flex-end;
      padding: 0.8rem 1.3rem;
      border-top: 1px solid var(--paper-deep);
      background: var(--paper-warm, #FAF6EF);
    }}
    /* Lista de sugerencias enrich */
    .enrich-list {{
      list-style: none; padding: 0; margin: 1rem 0 0;
      display: flex; flex-direction: column; gap: 0.8rem;
    }}
    .enrich-item {{
      padding: 0.9rem 1.1rem;
      background: white;
      border: 1px solid var(--paper-deep);
      border-radius: 6px;
      display: grid;
      grid-template-columns: auto auto 1fr;
      grid-template-areas:
        "check type reason"
        "before before before"
        "after after after";
      gap: 0.4rem 0.7rem;
      align-items: center;
    }}
    .enrich-check {{ grid-area: check; font-size: 0.85rem; display: inline-flex; align-items: center; gap: 0.3rem; font-weight: 600; }}
    .enrich-type {{
      grid-area: type;
      font-family: var(--mono, monospace);
      font-size: 0.78rem;
      letter-spacing: 0.06em;
      font-weight: 700;
      padding: 0.2rem 0.6rem;
      background: var(--primary-mist, #DBEAFE);
      color: var(--primary-deep);
      border-radius: 999px;
    }}
    .enrich-reason {{
      grid-area: reason;
      font-style: italic;
      color: var(--ink-mute);
      font-size: 0.85rem;
    }}
    .enrich-before, .enrich-after {{
      font-size: 0.85rem;
      padding: 0.45rem 0.6rem;
      border-radius: 4px;
    }}
    .enrich-before {{ grid-area: before; background: #FEF2F2; }}
    .enrich-after {{ grid-area: after; background: #ECFDF5; }}
    .enrich-before strong, .enrich-after strong {{ color: var(--ink); }}

    /* Modal copyright */
    .copy-risk {{
      padding: 0.7rem 1rem;
      border-radius: 6px;
      margin-bottom: 1rem;
      font-size: 1rem;
    }}
    .copy-risk.risk-low {{ background: rgba(16,185,129,0.12); border-left: 4px solid #10B981; color: #064E3B; }}
    .copy-risk.risk-medium {{ background: rgba(245,158,11,0.15); border-left: 4px solid #F59E0B; color: #78350F; }}
    .copy-risk.risk-high {{ background: rgba(239,68,68,0.15); border-left: 4px solid #EF4444; color: #7F1D1D; }}
    .copy-summary {{ font-size: 0.95rem; color: var(--ink); line-height: 1.5; }}
    .copy-concerns {{ list-style: disc inside; margin: 0.4rem 0 1rem; padding: 0; font-size: 0.88rem; color: var(--ink-soft); }}
    .copy-concerns li {{ margin: 0.2rem 0; }}
    .copy-reco {{
      padding: 0.7rem 0.9rem;
      background: var(--paper-warm);
      border-left: 3px solid var(--primary);
      border-radius: 0 4px 4px 0;
      font-size: 0.9rem;
      color: var(--ink-soft);
    }}

    /* Selector de snapshot en preview */
    #ed-preview-snap {{
      max-width: 240px;
      font-size: 0.85rem;
    }}

    /* =========================================================
       BANNER "Aplicar mejoras IA al curso completo" (v0.5.1)
       ========================================================= */
    .ed-enrich-banner {{
      margin: 1.5rem 0;
      padding: 1.2rem 1.4rem;
      background: linear-gradient(135deg, #ede9fe 0%, #ddd6fe 50%, #c7d2fe 100%);
      border: 2px solid #a78bfa;
      border-radius: 10px;
      display: flex;
      align-items: center;
      gap: 1.5rem;
      flex-wrap: wrap;
      box-shadow: 0 4px 12px rgba(139, 92, 246, 0.15);
    }}
    .ed-enrich-banner-text {{
      flex: 1;
      min-width: 280px;
      font-size: 0.95rem;
      line-height: 1.5;
      color: #4c1d95;
    }}
    .ed-enrich-banner-text strong {{ color: #312e81; }}
    .btn-enrich-all {{
      padding: 0.85rem 1.5rem !important;
      font-size: 0.95rem !important;
      font-weight: 700 !important;
      background: linear-gradient(135deg, #8b5cf6, #6366f1) !important;
      color: white !important;
      border: none !important;
      border-radius: 8px !important;
      cursor: pointer !important;
      box-shadow: 0 4px 12px rgba(139, 92, 246, 0.35) !important;
      transition: transform 0.12s, box-shadow 0.12s !important;
      white-space: nowrap;
    }}
    .btn-enrich-all:hover:not(:disabled) {{
      transform: translateY(-1px);
      box-shadow: 0 6px 16px rgba(139, 92, 246, 0.45) !important;
    }}
    .btn-enrich-all:disabled {{
      opacity: 0.7;
      cursor: not-allowed;
    }}
    </style>
    """
    return render_page("Editar · " + row["title"], body, user=user, active="library")


@app.route("/api/curso/<token>/structure")
@login_required
def course_structure_get(token):
    """Devuelve el JSON de la estructura editable."""
    user = current_user()
    with db() as conn:
        row = conn.execute(
            "SELECT zip_path FROM courses WHERE token = ? AND user_id = ?",
            (token, user["id"]),
        ).fetchone()
    if not row:
        abort(404)
    structure_path = Path(row["zip_path"]).parent / "structure.json"
    if not structure_path.exists():
        return jsonify({"error": "Sin estructura editable"}), 404
    with open(structure_path, encoding="utf-8") as f:
        data = json.load(f)
    return jsonify(data)


@app.route("/api/curso/<token>/save", methods=["POST"])
@login_required
def course_structure_save(token):
    """Recibe la estructura editada, la persiste y reempaqueta el SCORM."""
    user = current_user()
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM courses WHERE token = ? AND user_id = ?",
            (token, user["id"]),
        ).fetchone()
    if not row:
        abort(404)
    job_dir = Path(row["zip_path"]).parent
    structure_path = job_dir / "structure.json"

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON inválido"}), 400

    # Validación estructural mínima: detectar cursos vacíos o degenerados
    # antes de aceptar el guardado.
    validation_errors = []
    topics = payload.get("topics", [])
    if not isinstance(topics, list) or not topics:
        validation_errors.append(
            "El curso debe tener al menos un tema. Añade un tema antes de guardar."
        )
    else:
        for ti, t in enumerate(topics):
            if not isinstance(t, dict):
                validation_errors.append(f"Tema {ti+1}: estructura inválida")
                continue
            t_title = (t.get("title") or "").strip()
            if not t_title:
                validation_errors.append(f"Tema {ti+1}: falta el título")
            subs = t.get("subsections", [])
            if not isinstance(subs, list) or not subs:
                validation_errors.append(
                    f"Tema {ti+1} ({t_title or '?'}): debe tener al menos un subapartado"
                )
                continue
            for si, s in enumerate(subs):
                if not isinstance(s, dict):
                    validation_errors.append(f"Tema {ti+1}, subapartado {si+1}: estructura inválida")
                    continue
                blocks = s.get("blocks", [])
                if not isinstance(blocks, list) or not blocks:
                    validation_errors.append(
                        f"Tema {ti+1} > subapartado {si+1} "
                        f"({(s.get('title') or '?').strip() or '?'}): "
                        "debe tener al menos un bloque de contenido"
                    )
                # Validar listas no vacías
                for bi, b in enumerate(blocks):
                    if isinstance(b, dict) and b.get("type") in ("list_bullet", "list_number"):
                        items = b.get("items") or []
                        if not items or not any((str(it).strip()) for it in items):
                            validation_errors.append(
                                f"Tema {ti+1} > subapartado {si+1}, bloque {bi+1}: "
                                "lista vacía (debe tener al menos un item)"
                            )

    if validation_errors:
        return jsonify({
            "error": "El curso tiene problemas estructurales que impiden guardarlo",
            "validation_errors": validation_errors,
        }), 400

    # Reconstruir y validar la estructura
    try:
        from scorm_builder.api import course_from_dict, rebuild_from_structure
        course = course_from_dict(payload)
    except Exception as e:
        return jsonify({"error": f"Estructura malformada: {e}"}), 400

    # Guardar JSON actualizado
    try:
        with open(structure_path, "w", encoding="utf-8") as f:
            json.dump(course.to_dict(), f, ensure_ascii=False, indent=2)
    except Exception as e:
        return jsonify({"error": f"No se pudo guardar el JSON: {e}"}), 500

    # Reempaquetar SCORM
    output_dir = job_dir / "salida"
    # Limpiar SCORM antiguos para no acumular
    scorm_dir = output_dir / "scorm"
    if scorm_dir.exists():
        shutil.rmtree(scorm_dir, ignore_errors=True)
    recursos_dir = output_dir / "recursos" if (output_dir / "recursos").exists() else None
    try:
        result = rebuild_from_structure(
            course=course,
            output_dir=output_dir,
            theme=course.metadata.palette,
            recursos_dir=recursos_dir,
            generate_pdfs=False,
            generate_aiken=False,
        )
    except Exception as e:
        return jsonify({"error": f"Error al reempaquetar: {e}"}), 500

    # Reempaquetar el ZIP descargable
    final_zip = job_dir / f"curso_{token}.zip"
    if final_zip.exists():
        final_zip.unlink()
    with zipfile.ZipFile(final_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in output_dir.rglob("*"):
            if path.is_file():
                zf.write(path, arcname=str(path.relative_to(output_dir)))

    # Actualizar BD
    with db() as conn:
        conn.execute(
            """UPDATE courses
            SET title = ?, author = ?, num_topics = ?, num_questions = ?,
                zip_size = ?, warnings_json = ?
            WHERE id = ?""",
            (
                course.metadata.title or row["title"],
                course.metadata.author or row["author"],
                len(course.topics), sum(len(t.quiz) for t in course.topics),
                final_zip.stat().st_size,
                json.dumps(course.warnings, ensure_ascii=False),
                row["id"],
            ),
        )
        conn.commit()

    return jsonify({"ok": True, "token": token})


@app.route("/api/curso/<token>/ai-quiz", methods=["POST"])
@login_required
def course_ai_quiz(token):
    """Genera preguntas para un tema usando la API de Anthropic.

    Requiere variable de entorno ANTHROPIC_API_KEY.
    Recibe JSON con: {"topic_index": 0, "n_questions": 5}
    Devuelve: {"questions": [{"text", "options": [...], "correct_index", "explanation"}]}
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return jsonify({"error": "ANTHROPIC_API_KEY no configurada en el entorno"}), 400

    user = current_user()
    with db() as conn:
        row = conn.execute(
            "SELECT zip_path FROM courses WHERE token = ? AND user_id = ?",
            (token, user["id"]),
        ).fetchone()
    if not row:
        abort(404)

    structure_path = Path(row["zip_path"]).parent / "structure.json"
    if not structure_path.exists():
        return jsonify({"error": "Curso sin estructura editable"}), 404

    payload = request.get_json(silent=True) or {}
    try:
        topic_index = int(payload.get("topic_index", 0))
        n_questions = max(1, min(10, int(payload.get("n_questions", 5))))
    except (TypeError, ValueError):
        return jsonify({"error": "topic_index/n_questions inválidos"}), 400

    with open(structure_path, encoding="utf-8") as f:
        data = json.load(f)
    topics = data.get("topics", [])
    if topic_index < 0 or topic_index >= len(topics):
        return jsonify({"error": f"topic_index fuera de rango (0..{len(topics)-1})"}), 400

    # Construir el contenido del tema en texto plano para el prompt
    topic = topics[topic_index]
    parts = [f"# {topic.get('title', '')}"]
    if topic.get("intro"):
        parts.append(topic["intro"])
    for sub in topic.get("subsections", []):
        parts.append(f"\n## {sub.get('number', '')} {sub.get('title', '')}")
        for b in sub.get("blocks", []):
            t = b.get("type", "paragraph")
            if t in ("paragraph", "heading_3", "heading_4",
                     "callout_key", "callout_alert", "callout_success",
                     "callout_warn", "quote", "example"):
                parts.append(b.get("text", ""))
            elif t in ("list_bullet", "list_number"):
                parts.extend(f"- {it}" for it in b.get("items", []))
    content = "\n".join(parts)
    # Truncar si es enorme
    if len(content) > 12000:
        content = content[:12000] + "\n\n[... contenido truncado ...]"

    # Llamar a la API de Anthropic
    prompt = f"""Eres un experto pedagogo. Voy a darte el contenido de un tema de un curso e-learning. Tu tarea es generar exactamente {n_questions} preguntas tipo test de opción múltiple para evaluar la comprensión de los puntos clave.

Reglas:
- Cada pregunta debe tener exactamente 4 opciones (A, B, C, D).
- Solo UNA opción correcta.
- Las opciones incorrectas (distractores) deben ser plausibles, no absurdas.
- Las preguntas deben ser claras, sin trampas, basadas únicamente en el contenido proporcionado.
- Incluye una breve explicación de por qué la respuesta correcta es la correcta.
- Varía la dificultad: 2 fáciles (datos directos), 2 medias (aplicación), 1 difícil (análisis o caso).
- Responde EXCLUSIVAMENTE con un JSON válido siguiendo este esquema, sin texto antes ni después:

{{
  "questions": [
    {{
      "text": "Enunciado de la pregunta",
      "options": ["Opción A", "Opción B", "Opción C", "Opción D"],
      "correct_index": 0,
      "explanation": "Explicación breve de por qué es correcta."
    }}
  ]
}}

Contenido del tema:
---
{content}
---

Genera ahora las {n_questions} preguntas. Responde solo con el JSON."""

    try:
        import urllib.request
        import urllib.error
        body = json.dumps({
            "model": "claude-sonnet-4-5",
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=body,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            api_data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8", errors="ignore")
        except Exception:
            err_body = ""
        return jsonify({"error": f"Anthropic API HTTP {e.code}: {err_body[:300]}"}), 502
    except Exception as e:
        return jsonify({"error": f"Error llamando a Anthropic: {e}"}), 502

    # Extraer el texto de la respuesta
    try:
        content_blocks = api_data.get("content", [])
        text_parts = [b.get("text", "") for b in content_blocks if b.get("type") == "text"]
        raw_text = "\n".join(text_parts).strip()
        # Limpiar posibles backticks
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
            raw_text = re.sub(r"\s*```\s*$", "", raw_text)
        questions_data = json.loads(raw_text)
        questions = questions_data.get("questions", [])
    except Exception as e:
        return jsonify({"error": f"Respuesta de la IA no es JSON válido: {e}", "raw": raw_text[:500] if 'raw_text' in dir() else ""}), 502

    # Validar cada pregunta
    valid = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        text = q.get("text", "").strip()
        options = q.get("options", [])
        try:
            ci = int(q.get("correct_index", 0))
        except (TypeError, ValueError):
            continue
        if (text and isinstance(options, list) and len(options) >= 2
                and 0 <= ci < len(options)):
            valid.append({
                "text": text,
                "options": [str(o) for o in options],
                "correct_index": ci,
                "explanation": str(q.get("explanation", "")).strip() or None,
            })

    if not valid:
        return jsonify({"error": "La IA no devolvió preguntas válidas"}), 502

    return jsonify({"questions": valid})


# ============================================================
# ENDPOINTS FASE 2 (v0.5): tags IA, alt-text, quiz configurable,
# IMS CP, banco Aiken extendido
# ============================================================

@app.route("/api/curso/<token>/ai-tags", methods=["POST"])
@login_required
def course_ai_tags(token):
    """Genera 5-8 etiquetas temáticas para un tema usando la IA.

    Body JSON: {"topic_index": 0, "n": 6}
    Devuelve: {"tags": ["...", "..."]}
    Las etiquetas se guardan automáticamente en la estructura del curso.
    """
    from scorm_builder.ai_assist import is_available, generate_tags
    if not is_available():
        return jsonify({"error": "ANTHROPIC_API_KEY no configurada en el entorno"}), 400

    user = current_user()
    with db() as conn:
        row = conn.execute(
            "SELECT zip_path FROM courses WHERE token = ? AND user_id = ?",
            (token, user["id"]),
        ).fetchone()
    if not row:
        abort(404)

    structure_path = Path(row["zip_path"]).parent / "structure.json"
    if not structure_path.exists():
        return jsonify({"error": "Curso sin estructura editable"}), 404

    payload = request.get_json(silent=True) or {}
    try:
        topic_index = int(payload.get("topic_index", 0))
        n = max(4, min(8, int(payload.get("n", 6))))
    except (TypeError, ValueError):
        return jsonify({"error": "topic_index/n inválidos"}), 400

    with open(structure_path, encoding="utf-8") as f:
        data = json.load(f)
    topics = data.get("topics", [])
    if topic_index < 0 or topic_index >= len(topics):
        return jsonify({"error": f"topic_index fuera de rango (0..{len(topics)-1})"}), 400

    tags = generate_tags(topics[topic_index], n=n)
    if tags is None:
        return jsonify({"error": "La IA no devolvió etiquetas válidas"}), 502

    # Persistir
    topics[topic_index]["tags"] = tags
    with open(structure_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return jsonify({"tags": tags})


@app.route("/api/curso/<token>/ai-alt-text", methods=["POST"])
@login_required
def course_ai_alt_text(token):
    """Genera alt-text para una imagen subida. Body multipart con campo 'image'."""
    from scorm_builder.ai_assist import is_available, generate_alt_text
    if not is_available():
        return jsonify({"error": "ANTHROPIC_API_KEY no configurada en el entorno"}), 400

    user = current_user()
    with db() as conn:
        row = conn.execute(
            "SELECT 1 FROM courses WHERE token = ? AND user_id = ?",
            (token, user["id"]),
        ).fetchone()
    if not row:
        abort(404)

    if "image" not in request.files:
        return jsonify({"error": "Falta el archivo 'image'"}), 400
    f = request.files["image"]
    if not f or not f.filename:
        return jsonify({"error": "Archivo de imagen vacío"}), 400

    # Guardar temporalmente
    import tempfile
    suffix = "." + (f.filename.rsplit(".", 1)[-1] or "png").lower()
    tmp = Path(tempfile.mktemp(suffix=suffix))
    f.save(str(tmp))
    try:
        alt = generate_alt_text(tmp)
    finally:
        try: tmp.unlink()
        except Exception: pass

    if not alt:
        return jsonify({"error": "La IA no pudo generar alt-text"}), 502
    return jsonify({"alt": alt})


# ============================================================
# ENDPOINTS FASE 4: WCAG check + Vista previa
# ============================================================

@app.route("/api/curso/<token>/wcag-check", methods=["POST"])
@login_required
def course_wcag_check(token):
    """Ejecuta el validador WCAG 2.1 AA sobre la estructura actual.

    Devuelve un informe con errores bloqueantes (que impedirían empaquetar
    con strict_wcag=True), warnings (avisos no bloqueantes) y resumen.
    """
    user = current_user()
    with db() as conn:
        row = conn.execute(
            "SELECT zip_path FROM courses WHERE token = ? AND user_id = ?",
            (token, user["id"]),
        ).fetchone()
    if not row:
        abort(404)

    structure_path = Path(row["zip_path"]).parent / "structure.json"
    if not structure_path.exists():
        return jsonify({"error": "Curso sin estructura editable"}), 404

    with open(structure_path, encoding="utf-8") as f:
        data = json.load(f)

    from scorm_builder.api import course_from_dict
    from scorm_builder.wcag import validate_course

    course = course_from_dict(data)
    # Recursos del curso para que el validador pueda comprobar .vtt etc.
    recursos_dir = Path(row["zip_path"]).parent / "recursos"
    recursos_arg = recursos_dir if recursos_dir.exists() else None
    report = validate_course(course, recursos_dir=recursos_arg)
    return jsonify(report.to_dict())


@app.route("/api/curso/<token>/preview-html", methods=["GET"])
@login_required
def course_preview_html(token):
    """Renderiza el HTML de un tema sin empaquetar SCORM.

    Query params:
      - topic_index: índice del tema a previsualizar (default 0)

    Devuelve el HTML directamente (text/html). Útil para mostrarlo en un
    iframe dentro del editor sin descargar el SCORM.
    """
    user = current_user()
    with db() as conn:
        row = conn.execute(
            "SELECT zip_path FROM courses WHERE token = ? AND user_id = ?",
            (token, user["id"]),
        ).fetchone()
    if not row:
        abort(404)

    structure_path = Path(row["zip_path"]).parent / "structure.json"
    if not structure_path.exists():
        abort(404)

    try:
        topic_index = int(request.args.get("topic_index", 0))
    except ValueError:
        topic_index = 0

    with open(structure_path, encoding="utf-8") as f:
        data = json.load(f)

    from scorm_builder.api import course_from_dict
    from scorm_builder.renderer import render_html
    from scorm_builder.themes import get_theme

    course = course_from_dict(data)
    theme = get_theme(course.metadata.palette)
    if not course.topics or topic_index < 0 or topic_index >= len(course.topics):
        return "<p>Tema fuera de rango.</p>", 404
    topic = course.topics[topic_index]

    # En vista previa NO incluimos el botón PDF (el PDF se genera al
    # empaquetar). Pero sí los recursos: el HTML referencia recursos/
    # con rutas relativas. Como servimos el HTML desde la app, podemos
    # reescribir las rutas para que apunten a la carpeta de recursos del curso.
    htmls = render_html(course, theme)
    html_str = htmls.get(topic.number, "")
    # Reescribir 'recursos/...' a la ruta servida por la app
    serve_prefix = url_for("course_preview_resource", token=token, filename="").rstrip("/") + "/"
    html_str = html_str.replace('src="recursos/', f'src="{serve_prefix}')
    html_str = html_str.replace('href="recursos/', f'href="{serve_prefix}')

    from flask import Response
    return Response(html_str, mimetype="text/html; charset=utf-8")


@app.route("/curso/<token>/preview-resource/<path:filename>")
@login_required
def course_preview_resource(token, filename):
    """Sirve un fichero de la carpeta `recursos/` del curso para la vista
    previa (imágenes, PDFs, vídeos, etc.). Solo accesible por el dueño."""
    user = current_user()
    with db() as conn:
        row = conn.execute(
            "SELECT zip_path FROM courses WHERE token = ? AND user_id = ?",
            (token, user["id"]),
        ).fetchone()
    if not row:
        abort(404)
    resource = Path(row["zip_path"]).parent / "recursos" / filename
    if not resource.exists() or not resource.is_file():
        abort(404)
    # Sanity check: el resultado debe estar dentro de recursos/
    try:
        resource.resolve().relative_to((Path(row["zip_path"]).parent / "recursos").resolve())
    except ValueError:
        abort(403)
    return send_file(str(resource), as_attachment=False)


@app.route("/api/curso/<token>/ai-alt-text-block", methods=["POST"])
@login_required
def course_ai_alt_text_block(token):
    """Genera alt-text para una imagen ya incluida en el curso (en recursos/).

    Body JSON: {"filename": "docx_img_001.png"}
    Devuelve: {"alt": "..."}

    Variante del endpoint ai-alt-text que en lugar de subir la imagen,
    referencia una ya guardada como recurso del curso. Pensado para el
    botón "Sugerir alt" del editor sobre bloques IMAGE existentes.
    """
    from scorm_builder.ai_assist import is_available, generate_alt_text
    if not is_available():
        return jsonify({"error": "ANTHROPIC_API_KEY no configurada en el entorno"}), 400

    user = current_user()
    with db() as conn:
        row = conn.execute(
            "SELECT zip_path FROM courses WHERE token = ? AND user_id = ?",
            (token, user["id"]),
        ).fetchone()
    if not row:
        abort(404)

    payload = request.get_json(silent=True) or {}
    filename = (payload.get("filename") or "").strip()
    if not filename or "/" in filename or ".." in filename:
        return jsonify({"error": "filename inválido"}), 400

    img_path = Path(row["zip_path"]).parent / "recursos" / filename
    if not img_path.exists():
        return jsonify({"error": f"No se encuentra '{filename}' en recursos/"}), 404

    alt = generate_alt_text(img_path)
    if not alt:
        return jsonify({"error": "La IA no pudo generar alt-text"}), 502
    return jsonify({"alt": alt})


# ============================================================
# ENDPOINTS FASE 5: enriquecer Word, copyright, cmi5, snapshots, plantilla
# ============================================================

def _save_snapshot(job_dir: Path, label: str = "") -> Optional[str]:
    """Guarda una copia versionada de structure.json. Devuelve el ID."""
    import time
    structure_path = job_dir / "structure.json"
    if not structure_path.exists():
        return None
    snap_dir = job_dir / "snapshots"
    snap_dir.mkdir(exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    safe_label = re.sub(r"[^a-zA-Z0-9_-]+", "_", label)[:30]
    snap_id = f"{ts}_{safe_label}" if safe_label else ts
    target = snap_dir / f"{snap_id}.json"
    shutil.copy2(structure_path, target)
    # Limitar a últimas 10 snapshots
    snaps = sorted(snap_dir.glob("*.json"))
    while len(snaps) > 10:
        snaps[0].unlink()
        snaps = sorted(snap_dir.glob("*.json"))
    return snap_id


@app.route("/api/curso/<token>/snapshots", methods=["GET"])
@login_required
def course_snapshots_list(token):
    """Lista las snapshots disponibles del curso."""
    user = current_user()
    with db() as conn:
        row = conn.execute(
            "SELECT zip_path FROM courses WHERE token = ? AND user_id = ?",
            (token, user["id"]),
        ).fetchone()
    if not row:
        abort(404)
    snap_dir = Path(row["zip_path"]).parent / "snapshots"
    if not snap_dir.exists():
        return jsonify({"snapshots": []})
    out = []
    for p in sorted(snap_dir.glob("*.json"), reverse=True):
        out.append({
            "id": p.stem,
            "filename": p.name,
            "size": p.stat().st_size,
        })
    return jsonify({"snapshots": out})


@app.route("/api/curso/<token>/preview-html", methods=["GET"], defaults={"snapshot_id": None})
@app.route("/api/curso/<token>/preview-html/<snapshot_id>", methods=["GET"])
@login_required
def course_preview_html_snapshot(token, snapshot_id):
    """Variante de preview-html que puede renderizar una snapshot concreta.

    Si snapshot_id es None, comportamiento idéntico al endpoint original
    (renderiza la versión actual). Si se pasa, busca en snapshots/<id>.json.
    """
    # Si no hay snapshot, delegamos en la ruta original
    if not snapshot_id:
        return course_preview_html(token)

    user = current_user()
    with db() as conn:
        row = conn.execute(
            "SELECT zip_path FROM courses WHERE token = ? AND user_id = ?",
            (token, user["id"]),
        ).fetchone()
    if not row:
        abort(404)
    # Path traversal defense
    if "/" in snapshot_id or ".." in snapshot_id:
        abort(400)
    snap_path = Path(row["zip_path"]).parent / "snapshots" / f"{snapshot_id}.json"
    if not snap_path.exists():
        abort(404)
    try:
        topic_index = int(request.args.get("topic_index", 0))
    except ValueError:
        topic_index = 0
    with open(snap_path, encoding="utf-8") as f:
        data = json.load(f)

    from scorm_builder.api import course_from_dict
    from scorm_builder.renderer import render_html
    from scorm_builder.themes import get_theme

    course = course_from_dict(data)
    theme = get_theme(course.metadata.palette)
    if not course.topics or topic_index < 0 or topic_index >= len(course.topics):
        return "<p>Tema fuera de rango.</p>", 404
    topic = course.topics[topic_index]
    htmls = render_html(course, theme)
    html_str = htmls.get(topic.number, "")
    serve_prefix = url_for("course_preview_resource", token=token, filename="").rstrip("/") + "/"
    html_str = html_str.replace('src="recursos/', f'src="{serve_prefix}')
    html_str = html_str.replace('href="recursos/', f'href="{serve_prefix}')

    # Banner indicando que es vista de snapshot
    banner = (
        f'<div style="position:fixed;top:0;left:0;right:0;background:#F59E0B;'
        f'color:#78350F;padding:0.5rem 1rem;text-align:center;z-index:99999;'
        f'font-family:system-ui,sans-serif;font-weight:600;font-size:0.9rem;">'
        f'📸 Vista de snapshot: <code>{html_escape(snapshot_id)}</code></div>'
    )
    html_str = html_str.replace("<body>", "<body>" + banner, 1)

    from flask import Response
    return Response(html_str, mimetype="text/html; charset=utf-8")


@app.route("/api/curso/<token>/ai-enrich", methods=["POST"])
@login_required
def course_ai_enrich(token):
    """Sugiere convertir párrafos en callouts según su semántica.

    Body JSON: {"topic_index": 0}
    Devuelve: {"suggestions": [...], "truncated": bool}

    No modifica la estructura. El frontend muestra las sugerencias y, al
    aceptar, llama a /apply-enrich con los índices aceptados.
    """
    from scorm_builder.ai_assist import is_available, enrich_topic_with_callouts
    if not is_available():
        return jsonify({"error": "ANTHROPIC_API_KEY no configurada en el entorno"}), 400
    user = current_user()
    with db() as conn:
        row = conn.execute(
            "SELECT zip_path FROM courses WHERE token = ? AND user_id = ?",
            (token, user["id"]),
        ).fetchone()
    if not row:
        abort(404)
    structure_path = Path(row["zip_path"]).parent / "structure.json"
    if not structure_path.exists():
        return jsonify({"error": "Curso sin estructura editable"}), 404
    payload = request.get_json(silent=True) or {}
    try:
        topic_index = int(payload.get("topic_index", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "topic_index inválido"}), 400
    with open(structure_path, encoding="utf-8") as f:
        data = json.load(f)
    topics = data.get("topics", [])
    if topic_index < 0 or topic_index >= len(topics):
        return jsonify({"error": "topic_index fuera de rango"}), 400
    result = enrich_topic_with_callouts(topics[topic_index])
    if result is None:
        return jsonify({"error": "La IA no pudo procesar el tema"}), 502
    return jsonify(result)


@app.route("/api/curso/<token>/apply-enrich", methods=["POST"])
@login_required
def course_apply_enrich(token):
    """Aplica las sugerencias aceptadas de enrich. Crea snapshot previo.

    Body JSON:
      {
        "topic_index": 0,
        "accepted": [
          {"subsection_id": "l1", "block_index": 2,
           "suggested_type": "callout_key", "suggested_text": "..."}
        ]
      }
    """
    user = current_user()
    with db() as conn:
        row = conn.execute(
            "SELECT zip_path FROM courses WHERE token = ? AND user_id = ?",
            (token, user["id"]),
        ).fetchone()
    if not row:
        abort(404)
    job_dir = Path(row["zip_path"]).parent
    structure_path = job_dir / "structure.json"
    if not structure_path.exists():
        return jsonify({"error": "Curso sin estructura editable"}), 404
    payload = request.get_json(silent=True) or {}
    try:
        topic_index = int(payload.get("topic_index", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "topic_index inválido"}), 400
    accepted = payload.get("accepted", [])
    if not isinstance(accepted, list) or not accepted:
        return jsonify({"error": "Lista 'accepted' vacía"}), 400

    # Snapshot ANTES de aplicar
    snap_id = _save_snapshot(job_dir, label="pre_enrich")

    with open(structure_path, encoding="utf-8") as f:
        data = json.load(f)
    topics = data.get("topics", [])
    if topic_index < 0 or topic_index >= len(topics):
        return jsonify({"error": "topic_index fuera de rango"}), 400
    topic = topics[topic_index]
    sub_by_id = {s.get("id"): s for s in topic.get("subsections", [])}
    valid_types = {"callout_key", "callout_alert", "callout_warn",
                   "callout_success", "quote"}

    applied = 0
    for change in accepted:
        if not isinstance(change, dict):
            continue
        sub_id = change.get("subsection_id")
        try:
            bi = int(change.get("block_index", -1))
        except (TypeError, ValueError):
            continue
        new_type = change.get("suggested_type", "")
        new_text = (change.get("suggested_text") or "").strip()
        sub = sub_by_id.get(sub_id)
        if not sub or new_type not in valid_types or not new_text:
            continue
        blocks = sub.get("blocks", [])
        if bi < 0 or bi >= len(blocks):
            continue
        block = blocks[bi]
        # Solo cambiamos si sigue siendo un paragraph (defensivo: la
        # estructura puede haber cambiado desde que se generaron las sugerencias)
        if block.get("type") != "paragraph":
            continue
        block["type"] = new_type
        block["text"] = new_text
        # Limpiar text_html porque el texto ha cambiado
        block["text_html"] = None
        applied += 1

    with open(structure_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return jsonify({"applied": applied, "snapshot_id": snap_id})


@app.route("/api/curso/<token>/ai-copyright", methods=["POST"])
@login_required
def course_ai_copyright(token):
    """Analiza el riesgo de copyright de una imagen ya guardada.

    Body JSON: {"filename": "docx_img_001.png"}
    """
    from scorm_builder.ai_assist import is_available, detect_copyright_risk
    if not is_available():
        return jsonify({"error": "ANTHROPIC_API_KEY no configurada en el entorno"}), 400
    user = current_user()
    with db() as conn:
        row = conn.execute(
            "SELECT zip_path FROM courses WHERE token = ? AND user_id = ?",
            (token, user["id"]),
        ).fetchone()
    if not row:
        abort(404)
    payload = request.get_json(silent=True) or {}
    filename = (payload.get("filename") or "").strip()
    if not filename or "/" in filename or ".." in filename:
        return jsonify({"error": "filename inválido"}), 400
    img_path = Path(row["zip_path"]).parent / "recursos" / filename
    if not img_path.exists():
        return jsonify({"error": f"No se encuentra '{filename}' en recursos/"}), 404
    result = detect_copyright_risk(img_path)
    if not result:
        return jsonify({"error": "La IA no pudo analizar la imagen"}), 502
    return jsonify(result)


@app.route("/api/curso/<token>/export-cmi5", methods=["POST"])
@login_required
def course_export_cmi5(token):
    """Genera un paquete cmi5 (xAPI) del curso completo."""
    user = current_user()
    with db() as conn:
        row = conn.execute(
            "SELECT zip_path FROM courses WHERE token = ? AND user_id = ?",
            (token, user["id"]),
        ).fetchone()
    if not row:
        abort(404)
    structure_path = Path(row["zip_path"]).parent / "structure.json"
    if not structure_path.exists():
        return jsonify({"error": "Curso sin estructura editable"}), 404
    with open(structure_path, encoding="utf-8") as f:
        data = json.load(f)
    from scorm_builder.api import course_from_dict
    from scorm_builder.renderer import render_html
    from scorm_builder.themes import get_theme
    from scorm_builder.exporters import export_cmi5
    course = course_from_dict(data)
    theme = get_theme(course.metadata.palette)
    htmls = render_html(course, theme)
    course_dir = Path(row["zip_path"]).parent
    recursos_dir = course_dir / "recursos"
    recursos_arg = recursos_dir if recursos_dir.exists() else None
    out_zip = course_dir / "curso_cmi5.zip"
    export_cmi5(course, htmls, out_zip, recursos_dir=recursos_arg)
    return jsonify({"ok": True, "filename": out_zip.name})


@app.route("/api/curso/<token>/ai-enrich-all", methods=["POST"])
@login_required
def course_ai_enrich_all(token):
    """Aplica de un solo clic a TODOS los temas:
      1. Genera tags (5-6 por tema) si el tema aún no tiene ninguno.
      2. Sugiere y aplica callouts automáticamente (sin pasar por modal).
      3. Genera un quiz mixto (test + V/F + huecos) si el tema tiene < 3 preguntas.

    Crea UNA snapshot al inicio del proceso por si el usuario quiere revertir.
    Devuelve un resumen detallado por tema con tags, callouts y quiz generados.

    Es deliberadamente NO destructivo:
      - No toca tags ya existentes (solo añade si están vacíos).
      - No reemplaza quizzes que ya tengan 3+ preguntas (respeta los manuales).
      - Si la IA no devuelve nada útil para un tema, lo deja como estaba.
    """
    from scorm_builder.ai_assist import (
        is_available, generate_tags, enrich_topic_with_callouts,
        generate_quiz, QuizConfig,
    )
    if not is_available():
        return jsonify({"error": "ANTHROPIC_API_KEY no configurada en el entorno"}), 400

    user = current_user()
    with db() as conn:
        row = conn.execute(
            "SELECT zip_path FROM courses WHERE token = ? AND user_id = ?",
            (token, user["id"]),
        ).fetchone()
    if not row:
        abort(404)
    job_dir = Path(row["zip_path"]).parent
    structure_path = job_dir / "structure.json"
    if not structure_path.exists():
        return jsonify({"error": "Curso sin estructura editable"}), 404

    # Snapshot previo (uno solo para todo el batch)
    snap_id = _save_snapshot(job_dir, label="pre_enrich_all")

    with open(structure_path, encoding="utf-8") as f:
        data = json.load(f)
    topics = data.get("topics", [])

    valid_callout_types = {
        "callout_key", "callout_alert", "callout_warn",
        "callout_success", "quote",
    }
    total_tags = 0
    total_callouts = 0
    total_quiz_final = 0
    total_quiz_inline = 0
    details = []
    errors = []

    # Configuración fija del quiz mixto que aplicamos cuando el tema lo necesita
    QUIZ_CFG = QuizConfig(
        location="final",
        types=["multiple_choice", "true_false", "fill_in"],
        n_questions=5,
    )
    QUIZ_MIN_THRESHOLD = 3  # si el tema tiene menos preguntas que esto, generamos

    for ti, topic in enumerate(topics):
        t_detail = {
            "topic": ti + 1,
            "title": topic.get("title", "")[:60],
            "tags": 0, "callouts": 0,
            "quiz_final": 0, "quiz_inline": 0,
        }

        # 1) Tags si están vacíos
        if not topic.get("tags"):
            try:
                tags = generate_tags(topic, n=6)
                if tags:
                    topic["tags"] = tags
                    t_detail["tags"] = len(tags)
                    total_tags += len(tags)
            except Exception as e:
                errors.append(f"Tema {ti+1}: tags falló — {e}")

        # 2) Enrich con callouts
        try:
            result = enrich_topic_with_callouts(topic)
            if result and result.get("suggestions"):
                sub_by_id = {s.get("id"): s for s in topic.get("subsections", [])}
                applied = 0
                for s in result["suggestions"]:
                    sub_id = s.get("subsection_id")
                    bi = s.get("block_index")
                    new_type = s.get("suggested_type", "")
                    new_text = (s.get("suggested_text") or "").strip()
                    sub = sub_by_id.get(sub_id)
                    if not sub or new_type not in valid_callout_types or not new_text:
                        continue
                    blocks = sub.get("blocks", [])
                    try:
                        bi = int(bi)
                    except (TypeError, ValueError):
                        continue
                    if bi < 0 or bi >= len(blocks):
                        continue
                    block = blocks[bi]
                    if block.get("type") != "paragraph":
                        continue
                    block["type"] = new_type
                    block["text"] = new_text
                    block["text_html"] = None
                    applied += 1
                t_detail["callouts"] = applied
                total_callouts += applied
        except Exception as e:
            errors.append(f"Tema {ti+1}: callouts falló — {e}")

        # 3) Quiz mixto si el tema tiene menos de 3 preguntas
        current_quiz_n = len(topic.get("quiz", []))
        if current_quiz_n < QUIZ_MIN_THRESHOLD:
            try:
                quiz_result = generate_quiz(topic, config=QUIZ_CFG)
                if quiz_result and (quiz_result.get("final") or quiz_result.get("by_subsection")):
                    final_qs = quiz_result.get("final", []) or []
                    by_sub = quiz_result.get("by_subsection", {}) or {}
                    # Sustituye porque current_quiz_n < 3 (poco que preservar)
                    topic["quiz"] = [{**q} for q in final_qs]
                    # inline_quiz: fusionamos por subapartado (no machacamos los existentes
                    # si ya había algunos manuales)
                    existing_inline = topic.get("inline_quiz") or {}
                    for sub_id, qs in by_sub.items():
                        if sub_id not in existing_inline:
                            existing_inline[sub_id] = [{**q} for q in qs]
                    topic["inline_quiz"] = existing_inline
                    t_detail["quiz_final"] = len(final_qs)
                    t_detail["quiz_inline"] = sum(len(v) for v in by_sub.values())
                    total_quiz_final += t_detail["quiz_final"]
                    total_quiz_inline += t_detail["quiz_inline"]
            except Exception as e:
                errors.append(f"Tema {ti+1}: quiz falló — {e}")

        details.append(t_detail)

    with open(structure_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return jsonify({
        "ok": True,
        "snapshot_id": snap_id,
        "summary": {
            "topics_processed": len(topics),
            "tags_generated": total_tags,
            "callouts_applied": total_callouts,
            "quiz_final_generated": total_quiz_final,
            "quiz_inline_generated": total_quiz_inline,
            "errors": errors,
        },
        "details": details,
    })


# Ruta global para descargar la plantilla Word moderna
@app.route("/plantilla/descargar")
def plantilla_descargar():
    """Genera al vuelo y devuelve la plantilla Word moderna."""
    import tempfile
    from scorm_builder.template_builder import build_modern_template
    tmp = Path(tempfile.mktemp(suffix=".docx"))
    try:
        build_modern_template(tmp, course_title="Mi curso", author="Tu nombre")
        return send_file(
            str(tmp),
            as_attachment=True,
            download_name="Plantilla_Curso_SCORM_v5.docx",
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    finally:
        # Lo limpia el OS; con send_file con as_attachment Flask cierra el handle
        pass



@app.route("/api/curso/<token>/ai-quiz-config", methods=["POST"])
@login_required
def course_ai_quiz_config(token):
    """Genera quizzes según una configuración detallada por tema.

    Body JSON:
      {
        "topic_index": 0,
        "location": "final" | "per_subsection" | "mixed",
        "types": ["multiple_choice", "true_false", "fill_in"],
        "n_questions": 5
      }
    Devuelve: {"final": [...], "by_subsection": {sub_id: [...]}}
    Se guardan en la estructura del curso (sobreescribiendo quiz e inline_quiz).
    """
    from scorm_builder.ai_assist import is_available, generate_quiz, QuizConfig
    if not is_available():
        return jsonify({"error": "ANTHROPIC_API_KEY no configurada en el entorno"}), 400

    user = current_user()
    with db() as conn:
        row = conn.execute(
            "SELECT zip_path FROM courses WHERE token = ? AND user_id = ?",
            (token, user["id"]),
        ).fetchone()
    if not row:
        abort(404)

    structure_path = Path(row["zip_path"]).parent / "structure.json"
    if not structure_path.exists():
        return jsonify({"error": "Curso sin estructura editable"}), 404

    payload = request.get_json(silent=True) or {}
    try:
        topic_index = int(payload.get("topic_index", 0))
        n_questions = max(1, min(15, int(payload.get("n_questions", 5))))
    except (TypeError, ValueError):
        return jsonify({"error": "Parámetros inválidos"}), 400

    location = payload.get("location", "final")
    if location not in {"final", "per_subsection", "mixed"}:
        location = "final"
    types = payload.get("types") or ["multiple_choice"]
    types = [t for t in types if t in {"multiple_choice", "true_false", "fill_in"}]
    if not types:
        types = ["multiple_choice"]

    with open(structure_path, encoding="utf-8") as f:
        data = json.load(f)
    topics = data.get("topics", [])
    if topic_index < 0 or topic_index >= len(topics):
        return jsonify({"error": f"topic_index fuera de rango (0..{len(topics)-1})"}), 400

    cfg = QuizConfig(location=location, types=types, n_questions=n_questions)
    result = generate_quiz(topics[topic_index], config=cfg)
    if result is None:
        return jsonify({"error": "La IA no devolvió preguntas válidas"}), 502

    # Persistir: el quiz final reemplaza el existente; inline_quiz se reemplaza
    topics[topic_index]["quiz"] = [
        {**q} for q in result["final"]
    ]
    topics[topic_index]["inline_quiz"] = {
        sub_id: [{**q} for q in qs]
        for sub_id, qs in result["by_subsection"].items()
    }
    with open(structure_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return jsonify({
        "final_count": len(result["final"]),
        "by_subsection_count": {k: len(v) for k, v in result["by_subsection"].items()},
        "result": result,
    })



@app.route("/api/curso/<token>/export-imscp", methods=["POST"])
@login_required
def course_export_imscp(token):
    """Genera y guarda un paquete IMS Content Package del curso completo."""
    user = current_user()
    with db() as conn:
        row = conn.execute(
            "SELECT zip_path FROM courses WHERE token = ? AND user_id = ?",
            (token, user["id"]),
        ).fetchone()
    if not row:
        abort(404)

    structure_path = Path(row["zip_path"]).parent / "structure.json"
    if not structure_path.exists():
        return jsonify({"error": "Curso sin estructura editable"}), 404

    with open(structure_path, encoding="utf-8") as f:
        data = json.load(f)

    from scorm_builder.api import course_from_dict
    from scorm_builder.renderer import render_html
    from scorm_builder.themes import get_theme
    from scorm_builder.exporters import export_ims_cp

    course = course_from_dict(data)
    theme = get_theme(course.metadata.palette)
    htmls = render_html(course, theme)

    # Buscar recursos asociados al curso (PDFs, imágenes, etc.)
    course_dir = Path(row["zip_path"]).parent
    recursos_dir = course_dir / "recursos"
    recursos_arg = recursos_dir if recursos_dir.exists() else None

    out_zip = course_dir / "curso_imscp.zip"
    export_ims_cp(course, htmls, out_zip, recursos_dir=recursos_arg)

    return jsonify({"ok": True, "filename": out_zip.name})


@app.route("/api/curso/<token>/ai-aiken-extendido", methods=["POST"])
@login_required
def course_ai_aiken_extendido(token):
    """Genera un banco Aiken extendido (30-50 preguntas por tema) con IA."""
    from scorm_builder.ai_assist import is_available
    if not is_available():
        return jsonify({"error": "ANTHROPIC_API_KEY no configurada en el entorno"}), 400

    user = current_user()
    with db() as conn:
        row = conn.execute(
            "SELECT zip_path FROM courses WHERE token = ? AND user_id = ?",
            (token, user["id"]),
        ).fetchone()
    if not row:
        abort(404)

    structure_path = Path(row["zip_path"]).parent / "structure.json"
    if not structure_path.exists():
        return jsonify({"error": "Curso sin estructura editable"}), 404

    payload = request.get_json(silent=True) or {}
    try:
        n = max(10, min(60, int(payload.get("n", 30))))
    except (TypeError, ValueError):
        return jsonify({"error": "Parámetro n inválido"}), 400

    with open(structure_path, encoding="utf-8") as f:
        data = json.load(f)

    from scorm_builder.api import course_from_dict
    from scorm_builder.aiken_builder import build_extended_aiken

    course = course_from_dict(data)
    course_dir = Path(row["zip_path"]).parent
    aiken_dir = course_dir / "aiken_extendido"
    files = build_extended_aiken(course, aiken_dir, n_questions_per_topic=n)
    if not files:
        return jsonify({"error": "No se pudo generar el banco extendido"}), 502
    return jsonify({"ok": True, "files": [f.name for f in files]})


# ============================================================
# HELPERS DE IA Y ENDPOINTS DE CONTENIDO
# ============================================================

def _call_anthropic(prompt: str, max_tokens: int = 2048) -> tuple[bool, str]:
    """Llama a la API de Anthropic con un prompt simple. Devuelve (ok, texto/error)."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return False, "ANTHROPIC_API_KEY no configurada en el entorno"
    import urllib.request, urllib.error
    body = json.dumps({
        "model": "claude-sonnet-4-5",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            api_data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8", errors="ignore")
        except Exception:
            err_body = ""
        return False, f"Anthropic API HTTP {e.code}: {err_body[:300]}"
    except Exception as e:
        return False, f"Error llamando a Anthropic: {e}"
    try:
        blocks = api_data.get("content", [])
        text = "\n".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
        # Eliminar fences ```json … ``` si los hubiera
        if text.startswith("```"):
            text = re.sub(r"^```(?:\w+)?\s*", "", text)
            text = re.sub(r"\s*```\s*$", "", text)
        return True, text
    except Exception as e:
        return False, f"Respuesta inválida: {e}"


def _topic_to_text(topic: dict) -> str:
    """Aplana un tema (dict) a texto plano para enviárselo a la IA."""
    parts = [f"# {topic.get('title', '')}"]
    if topic.get("intro"):
        parts.append(topic["intro"])
    for sub in topic.get("subsections", []):
        parts.append(f"\n## {sub.get('number', '')} {sub.get('title', '')}")
        for b in sub.get("blocks", []):
            t = b.get("type", "paragraph")
            if t in ("paragraph", "heading_3", "heading_4",
                     "callout_key", "callout_alert", "callout_success",
                     "callout_warn", "quote", "example"):
                parts.append(b.get("text", ""))
            elif t in ("list_bullet", "list_number"):
                parts.extend(f"- {it}" for it in b.get("items", []))
    text = "\n".join(parts)
    if len(text) > 12000:
        text = text[:12000] + "\n\n[... contenido truncado ...]"
    return text


def _course_to_text(course_data: dict) -> str:
    """Aplana el curso entero (todos los temas) para análisis global como glosario."""
    parts = []
    md = course_data.get("metadata", {})
    if md.get("title"):
        parts.append(f"# Curso: {md['title']}")
    for t in course_data.get("topics", []):
        parts.append(_topic_to_text(t))
    text = "\n\n".join(parts)
    if len(text) > 25000:
        text = text[:25000] + "\n\n[... contenido truncado ...]"
    return text


def _load_course_for_user(token, user):
    """Devuelve (row_BD, structure_path, structure_dict) o (None, None, None)."""
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM courses WHERE token = ? AND user_id = ?",
            (token, user["id"]),
        ).fetchone()
    if not row:
        return None, None, None
    structure_path = Path(row["zip_path"]).parent / "structure.json"
    if not structure_path.exists():
        return row, structure_path, None
    with open(structure_path, encoding="utf-8") as f:
        return row, structure_path, json.load(f)


@app.route("/api/curso/<token>/ai-rewrite", methods=["POST"])
@login_required
def course_ai_rewrite(token):
    """Reescribe un texto en un tono concreto.

    Recibe: {"text": "...", "tone": "practical|theoretical|professional|simple|improve|summarize|expand"}
    Devuelve: {"text": "..."}
    """
    user = current_user()
    row, _, _ = _load_course_for_user(token, user)
    if not row:
        abort(404)

    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return jsonify({"error": "ANTHROPIC_API_KEY no configurada en el entorno"}), 400

    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()
    tone = (payload.get("tone") or "improve").strip().lower()
    if not text:
        return jsonify({"error": "Texto vacío"}), 400
    if len(text) > 8000:
        return jsonify({"error": "Texto demasiado largo (>8000 caracteres)"}), 400

    instructions = {
        "practical": (
            "Reescribe el siguiente texto en un tono MÁS PRÁCTICO y aplicable. "
            "Convierte teoría densa en algo accionable: añade ejemplos concretos, "
            "casos de uso, pasos numerados cuando proceda. Habla al alumno en segunda persona "
            "('tú'). Mantén el sentido original sin inventar datos. Conserva el mismo idioma."
        ),
        "theoretical": (
            "Reescribe el siguiente texto en un tono MÁS TEÓRICO y académico. "
            "Da contexto conceptual, mata\u00edza con marcos teóricos cuando sea coherente, "
            "profundiza en los porqués sin inventar. Tono formal y preciso. Conserva el mismo idioma."
        ),
        "professional": (
            "Reescribe el siguiente texto en un tono PROFESIONAL y corporativo. "
            "Vocabulario sectorial preciso, sin coloquialismos, sin emojis, "
            "neutro y respetuoso. Adecuado para formación obligatoria de empresa. "
            "Mantén el sentido original. Conserva el mismo idioma."
        ),
        "simple": (
            "Reescribe el siguiente texto en LECTURA FÁCIL: frases cortas (máximo 15 palabras), "
            "vocabulario sencillo, una idea por frase, evita tecnicismos sin explicar. "
            "Si necesitas usar un término técnico, explícalo entre paréntesis. "
            "Útil para accesibilidad y formación a personas con bajo nivel lector. "
            "Mantén el sentido original. Conserva el mismo idioma."
        ),
        "improve": (
            "Mejora la redacción del siguiente texto sin cambiar el tono ni el sentido: "
            "corrige errores, elimina muletillas y redundancias, mejora la fluidez. "
            "Conserva el mismo idioma y estilo aproximado."
        ),
        "summarize": (
            "Resume el siguiente texto en 2-3 frases claras que conserven la idea principal. "
            "Conserva el mismo idioma."
        ),
        "expand": (
            "Expande el siguiente texto: desarrolla las ideas, añade matices, ejemplos breves "
            "y contexto donde proceda, sin inventar datos concretos. "
            "Conserva el mismo idioma y tono."
        ),
    }
    instr = instructions.get(tone, instructions["improve"])
    prompt = (
        f"{instr}\n\n"
        "Devuelve EXCLUSIVAMENTE el texto reescrito, sin comillas, sin preámbulos, sin coletillas como "
        "'Aquí tienes el texto reescrito:'. Solo el texto.\n\n"
        f"Texto original:\n---\n{text}\n---"
    )
    ok, out = _call_anthropic(prompt, max_tokens=2048)
    if not ok:
        return jsonify({"error": out}), 502
    return jsonify({"text": out.strip()})


@app.route("/api/curso/<token>/ai-objectives", methods=["POST"])
@login_required
def course_ai_objectives(token):
    """Genera objetivos de aprendizaje para un tema.

    Recibe: {"topic_index": 0}
    Devuelve: {"objectives": ["...", "...", "..."]}
    """
    user = current_user()
    row, _, course_data = _load_course_for_user(token, user)
    if not row:
        abort(404)
    if not course_data:
        return jsonify({"error": "Curso sin estructura editable"}), 404
    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return jsonify({"error": "ANTHROPIC_API_KEY no configurada en el entorno"}), 400

    payload = request.get_json(silent=True) or {}
    try:
        ti = int(payload.get("topic_index", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "topic_index inválido"}), 400
    topics = course_data.get("topics", [])
    if ti < 0 or ti >= len(topics):
        return jsonify({"error": "topic_index fuera de rango"}), 400

    content = _topic_to_text(topics[ti])
    prompt = (
        "Genera entre 3 y 5 objetivos de aprendizaje para el siguiente tema de un curso. "
        "Cada objetivo debe empezar con un verbo en infinitivo o con la fórmula "
        "'Al finalizar este tema, el alumno será capaz de...'. Usa verbos medibles "
        "(identificar, aplicar, analizar, comparar, diseñar, evaluar). "
        "Devuelve EXCLUSIVAMENTE un JSON válido con esta forma:\n"
        '{"objectives": ["objetivo 1", "objetivo 2", "objetivo 3"]}\n\n'
        f"Contenido del tema:\n---\n{content}\n---"
    )
    ok, out = _call_anthropic(prompt, max_tokens=1024)
    if not ok:
        return jsonify({"error": out}), 502
    try:
        data = json.loads(out)
        objs = data.get("objectives", [])
        if isinstance(objs, list):
            objs = [str(o).strip() for o in objs if str(o).strip()]
        else:
            objs = []
    except Exception as e:
        return jsonify({"error": f"Respuesta de la IA no es JSON: {e}"}), 502
    if not objs:
        return jsonify({"error": "La IA no devolvió objetivos"}), 502
    return jsonify({"objectives": objs})


@app.route("/api/curso/<token>/ai-summary", methods=["POST"])
@login_required
def course_ai_summary(token):
    """Genera un resumen final para un tema.

    Recibe: {"topic_index": 0}
    Devuelve: {"summary": "..."}
    """
    user = current_user()
    row, _, course_data = _load_course_for_user(token, user)
    if not row:
        abort(404)
    if not course_data:
        return jsonify({"error": "Curso sin estructura editable"}), 404
    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return jsonify({"error": "ANTHROPIC_API_KEY no configurada en el entorno"}), 400
    payload = request.get_json(silent=True) or {}
    try:
        ti = int(payload.get("topic_index", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "topic_index inválido"}), 400
    topics = course_data.get("topics", [])
    if ti < 0 or ti >= len(topics):
        return jsonify({"error": "topic_index fuera de rango"}), 400

    content = _topic_to_text(topics[ti])
    prompt = (
        "Redacta un resumen final del siguiente tema, en 4-6 frases. "
        "El resumen debe recoger las ideas clave, no añadir información nueva, "
        "y servir al alumno para repasar. Tono didáctico, segunda persona ('hemos visto', 'recuerda'). "
        "Devuelve EXCLUSIVAMENTE el texto del resumen, sin etiquetas ni preámbulos.\n\n"
        f"Contenido:\n---\n{content}\n---"
    )
    ok, out = _call_anthropic(prompt, max_tokens=1024)
    if not ok:
        return jsonify({"error": out}), 502
    return jsonify({"summary": out.strip()})


@app.route("/api/curso/<token>/ai-glossary", methods=["POST"])
@login_required
def course_ai_glossary(token):
    """Detecta términos clave del curso completo y propone un glosario.

    Devuelve: {"glossary": [{"term": "...", "definition": "..."}, ...]}
    """
    user = current_user()
    row, _, course_data = _load_course_for_user(token, user)
    if not row:
        abort(404)
    if not course_data:
        return jsonify({"error": "Curso sin estructura editable"}), 404
    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return jsonify({"error": "ANTHROPIC_API_KEY no configurada en el entorno"}), 400

    content = _course_to_text(course_data)
    prompt = (
        "Analiza el siguiente curso e identifica entre 8 y 15 términos técnicos clave "
        "que aparecen en el contenido y que un alumno debería conocer. "
        "Para cada término, escribe una definición clara en 1-2 frases, basándote ÚNICAMENTE "
        "en el contenido proporcionado (no añadas información que no esté). "
        "Si un término no está suficientemente desarrollado en el texto, omítelo. "
        "Ordena los términos alfabéticamente. "
        "Devuelve EXCLUSIVAMENTE un JSON válido:\n"
        '{"glossary": [{"term": "Concepto", "definition": "Definición clara"}]}\n\n'
        f"Contenido del curso:\n---\n{content}\n---"
    )
    ok, out = _call_anthropic(prompt, max_tokens=3072)
    if not ok:
        return jsonify({"error": out}), 502
    try:
        data = json.loads(out)
        items = data.get("glossary", [])
        valid = []
        for it in items:
            if isinstance(it, dict):
                term = str(it.get("term", "")).strip()
                defn = str(it.get("definition", "")).strip()
                if term and defn:
                    valid.append({"term": term, "definition": defn})
    except Exception as e:
        return jsonify({"error": f"Respuesta de la IA no es JSON: {e}"}), 502
    if not valid:
        return jsonify({"error": "La IA no devolvió un glosario válido"}), 502
    return jsonify({"glossary": valid})


@app.route("/api/curso/<token>/ai-illustration", methods=["POST"])
@login_required
def course_ai_illustration(token):
    """Genera una ilustración SVG vectorial para un subapartado.

    Recibe: {"topic_index": 0, "sub_index": 0, "style": "flat|line|abstract"}
    Devuelve: {"svg": "<svg>...</svg>", "filename": "ilustracion_T1_1.svg"}

    El SVG se guarda automáticamente en la carpeta de recursos del curso y
    se inserta como bloque [IMAGEN] al inicio del subapartado.
    """
    user = current_user()
    row, _, course_data = _load_course_for_user(token, user)
    if not row:
        abort(404)
    if not course_data:
        return jsonify({"error": "Curso sin estructura editable"}), 404
    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return jsonify({"error": "ANTHROPIC_API_KEY no configurada en el entorno"}), 400

    payload = request.get_json(silent=True) or {}
    try:
        ti = int(payload.get("topic_index", 0))
        si = int(payload.get("sub_index", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "índices inválidos"}), 400
    style = (payload.get("style") or "flat").strip().lower()
    if style not in ("flat", "line", "abstract"):
        style = "flat"

    topics = course_data.get("topics", [])
    if ti < 0 or ti >= len(topics):
        return jsonify({"error": "topic_index fuera de rango"}), 400
    topic = topics[ti]
    subs = topic.get("subsections", [])
    if si < 0 or si >= len(subs):
        return jsonify({"error": "sub_index fuera de rango"}), 400
    sub = subs[si]

    # Resolver paleta para inyectar colores
    md = course_data.get("metadata", {})
    palette_name = md.get("palette", "azul")
    try:
        from scorm_builder.themes import get_theme
        theme = get_theme(palette_name)
        colors = {
            "deep": theme.primary_deep,
            "primary": theme.primary,
            "bright": theme.primary_bright,
            "ink": theme.ink,
            "paper": theme.paper,
        }
    except Exception:
        colors = {"deep":"#0A2540","primary":"#1D4ED8","bright":"#2563EB","ink":"#0F172A","paper":"#F8FAFC"}

    # Texto del subapartado para dar contexto a la ilustración
    text_summary = (sub.get("title", "") + ". ")
    for b in sub.get("blocks", []):
        bt = b.get("type", "")
        if bt in ("paragraph", "callout_key", "example") and b.get("text"):
            text_summary += b["text"] + " "
        if len(text_summary) > 1500:
            break
    text_summary = text_summary[:1500]

    style_descr = {
        "flat": "estilo flat-design moderno, formas geométricas simples, sin gradientes complejos, colores planos",
        "line": "estilo line-art minimalista, solo líneas finas y figuras esquemáticas, sin rellenos sólidos",
        "abstract": "estilo abstracto geométrico con composiciones de círculos, rectángulos y triángulos",
    }[style]

    prompt = (
        f"Eres un ilustrador profesional. Crea una ilustración vectorial SVG conceptual "
        f"para el siguiente subapartado de un curso e-learning. {style_descr}. "
        f"USA EXCLUSIVAMENTE estos colores de paleta: {colors['deep']}, {colors['primary']}, "
        f"{colors['bright']}, {colors['ink']}, {colors['paper']}. "
        "Dimensiones: viewBox=\"0 0 800 400\". "
        "Sin texto dentro del SVG (será una ilustración pura, no infografía). "
        "Composición clara y centrada. Profesional y limpia, no infantil. "
        "Formas simples y reconocibles que evoquen el concepto, no fotorrealismo. "
        "DEVUELVE EXCLUSIVAMENTE el código SVG válido, empezando por <svg y terminando por </svg>. "
        "Sin texto antes ni después, sin markdown, sin comentarios.\n\n"
        f"Subapartado: {sub.get('title', '')}\n"
        f"Contenido (resumen): {text_summary}"
    )
    ok, out = _call_anthropic(prompt, max_tokens=4096)
    if not ok:
        return jsonify({"error": out}), 502

    # Limpiar la respuesta para extraer solo el SVG
    svg = out.strip()
    if "<svg" not in svg:
        return jsonify({"error": "La IA no devolvió SVG válido", "raw": out[:300]}), 502
    # Quedarnos desde <svg hasta </svg>
    start = svg.find("<svg")
    end = svg.rfind("</svg>")
    if start < 0 or end < 0:
        return jsonify({"error": "SVG mal formado"}), 502
    svg = svg[start:end + len("</svg>")]

    # Guardar el SVG en la carpeta de recursos del curso
    job_dir = Path(row["zip_path"]).parent
    recursos_dir = job_dir / "salida" / "recursos"
    recursos_dir.mkdir(parents=True, exist_ok=True)
    filename = f"ilustracion_T{ti+1:02d}_{si+1:02d}.svg"
    target = recursos_dir / filename
    counter = 1
    while target.exists():
        filename = f"ilustracion_T{ti+1:02d}_{si+1:02d}_{counter}.svg"
        target = recursos_dir / filename
        counter += 1
    target.write_text(svg, encoding="utf-8")

    return jsonify({"svg": svg, "filename": filename})


@app.route("/api/curso/<token>/tts", methods=["POST"])
@login_required
def course_tts(token):
    """Genera narraciones TTS para todos los subapartados del curso.

    Devuelve {"generated": N, "skipped": M, "errors": [...]}
    Los archivos se guardan como audio_T<n>_<m>.wav en la carpeta de recursos
    y se referencian como bloque [AUDIO] al inicio del subapartado correspondiente.
    """
    user = current_user()
    row, structure_path, course_data = _load_course_for_user(token, user)
    if not row:
        abort(404)
    if not course_data:
        return jsonify({"error": "Curso sin estructura editable"}), 404

    try:
        from scorm_builder.tts import synthesize, subsection_to_text, tts_available
        from scorm_builder.parser import (
            CourseStructure, CourseMetadata, Topic, Subsection, Block, BlockType
        )
    except ImportError as e:
        return jsonify({"error": f"Módulo TTS no disponible: {e}"}), 500
    if not tts_available():
        return jsonify({"error": "pyttsx3 no instalado. Ejecuta: pip install pyttsx3"}), 400

    job_dir = Path(row["zip_path"]).parent
    recursos_dir = job_dir / "salida" / "recursos"
    recursos_dir.mkdir(parents=True, exist_ok=True)

    generated = 0
    skipped = 0
    errors = []

    for ti, topic in enumerate(course_data.get("topics", [])):
        for si, sub in enumerate(topic.get("subsections", [])):
            # Reconstituir subsection mínimo en formato dataclass para tts.subsection_to_text
            class _Sub:
                pass
            sub_obj = _Sub()
            sub_obj.title = sub.get("title", "")
            sub_obj.blocks = []
            for b in sub.get("blocks", []):
                blk = _Sub()
                bt = b.get("type", "paragraph")
                # bt como pseudo-enum: solo necesitamos .value
                class _BT:
                    def __init__(self, v): self.value = v
                blk.type = _BT(bt)
                blk.text = b.get("text", "")
                blk.items = b.get("items", [])
                sub_obj.blocks.append(blk)
            text = subsection_to_text(sub_obj)
            if not text.strip():
                skipped += 1
                continue
            filename = f"audio_T{ti+1:02d}_{si+1:02d}.wav"
            target = recursos_dir / filename
            try:
                result = synthesize(text, target, language="es")
                if result:
                    generated += 1
                    # Insertar bloque [AUDIO] al principio del subapartado si no existe ya
                    has_audio = any(
                        b.get("type") == "audio" and (b.get("extras", {}).get("src") == filename)
                        for b in sub.get("blocks", [])
                    )
                    if not has_audio:
                        sub.setdefault("blocks", []).insert(0, {
                            "type": "audio",
                            "text": "Narración del subapartado",
                            "items": [], "rows": [],
                            "extras": {"src": filename, "file": filename},
                        })
                else:
                    errors.append(f"T{ti+1}.{si+1}: TTS devolvió None")
            except Exception as e:
                errors.append(f"T{ti+1}.{si+1}: {e}")

    # Persistir la estructura actualizada
    try:
        with open(structure_path, "w", encoding="utf-8") as f:
            json.dump(course_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        errors.append(f"No se pudo guardar la estructura: {e}")

    return jsonify({
        "generated": generated,
        "skipped": skipped,
        "errors": errors,
    })


@app.route("/api/curso/<token>/export-html", methods=["POST"])
@login_required
def course_export_html(token):
    """Exporta el curso como sitio HTML standalone (sin SCORM)."""
    user = current_user()
    row, _, course_data = _load_course_for_user(token, user)
    if not row:
        abort(404)
    if not course_data:
        return jsonify({"error": "Curso sin estructura editable"}), 404

    try:
        from scorm_builder.api import course_from_dict
        from scorm_builder.renderer import render_html
        from scorm_builder.themes import get_theme
        from scorm_builder.exporters import export_html_standalone
        course = course_from_dict(course_data)
        theme = get_theme(course.metadata.palette)
        htmls = render_html(course, theme)
    except Exception as e:
        return jsonify({"error": f"Render falló: {e}"}), 500

    job_dir = Path(row["zip_path"]).parent
    out_zip = job_dir / f"curso_{token}_html_standalone.zip"
    try:
        export_html_standalone(course, htmls, out_zip)
    except Exception as e:
        return jsonify({"error": f"Export HTML falló: {e}"}), 500

    return jsonify({"ok": True, "filename": out_zip.name, "size": out_zip.stat().st_size})


@app.route("/api/curso/<token>/export-scorm2004", methods=["POST"])
@login_required
def course_export_scorm2004(token):
    """Exporta el curso como SCORM 2004 4ª edición."""
    user = current_user()
    row, _, course_data = _load_course_for_user(token, user)
    if not row:
        abort(404)
    if not course_data:
        return jsonify({"error": "Curso sin estructura editable"}), 404

    try:
        from scorm_builder.api import course_from_dict
        from scorm_builder.renderer import render_html
        from scorm_builder.themes import get_theme
        from scorm_builder.exporters import export_all_topics_2004
        course = course_from_dict(course_data)
        theme = get_theme(course.metadata.palette)
        htmls = render_html(course, theme)
    except Exception as e:
        return jsonify({"error": f"Render falló: {e}"}), 500

    job_dir = Path(row["zip_path"]).parent
    out_dir = job_dir / "scorm2004"
    out_dir.mkdir(parents=True, exist_ok=True)
    recursos_dir = job_dir / "salida" / "recursos" if (job_dir / "salida" / "recursos").exists() else None
    try:
        zips = export_all_topics_2004(course, htmls, out_dir, recursos_dir=recursos_dir)
    except Exception as e:
        return jsonify({"error": f"Export 2004 falló: {e}"}), 500

    # Empaquetar todos los SCORM 2004 en un solo ZIP
    out_zip = job_dir / f"curso_{token}_scorm2004.zip"
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for z in zips:
            zf.write(z, arcname=z.name)

    return jsonify({"ok": True, "filename": out_zip.name, "size": out_zip.stat().st_size,
                    "n_topics": len(zips)})


@app.route("/curso/<token>/export/<kind>")
@login_required
def course_export_download(token, kind):
    """Descarga del export adicional ya generado."""
    user = current_user()
    with db() as conn:
        row = conn.execute(
            "SELECT zip_path FROM courses WHERE token = ? AND user_id = ?",
            (token, user["id"]),
        ).fetchone()
    if not row:
        abort(404)
    job_dir = Path(row["zip_path"]).parent
    if kind == "html":
        path = job_dir / f"curso_{token}_html_standalone.zip"
    elif kind == "scorm2004":
        path = job_dir / f"curso_{token}_scorm2004.zip"
    elif kind == "imscp":
        # v0.5 Fase 3: IMS Content Package generado por export-imscp
        path = job_dir / "curso_imscp.zip"
    elif kind == "cmi5":
        # v0.5 Fase 5: paquete cmi5 / xAPI generado por export-cmi5
        path = job_dir / "curso_cmi5.zip"
    elif kind == "aiken-ext":
        # v0.5 Fase 3: ZIP con todos los bancos Aiken extendidos
        path = job_dir / "aiken_extendido.zip"
        if not path.exists():
            # Si no existe el ZIP pero sí la carpeta, lo creamos al vuelo
            ext_dir = job_dir / "aiken_extendido"
            if ext_dir.exists() and any(ext_dir.iterdir()):
                import zipfile
                with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for f in ext_dir.iterdir():
                        if f.is_file():
                            zf.write(f, arcname=f.name)
    else:
        abort(404)
    if not path.exists():
        abort(404)
    return send_file(str(path), as_attachment=True, download_name=path.name,
                     mimetype="application/zip")


# ============================================================
# API: GENERAR
# ============================================================
@app.route("/api/preview", methods=["POST"])
@login_required
def api_preview():
    """Genera el HTML del primer tema sin empaquetar SCORM. Más rápido para iterar."""
    user = current_user()
    udir = user_dir(user["id"])

    if "docx" not in request.files:
        return jsonify({"error": "Falta archivo Word"}), 400
    docx_file = request.files["docx"]
    if not docx_file.filename or not docx_file.filename.lower().endswith(".docx"):
        return jsonify({"error": "El archivo principal debe ser .docx"}), 400

    # Carpeta temporal de preview (se sobrescribe en cada preview del mismo usuario)
    preview_dir = udir / "_preview"
    if preview_dir.exists():
        shutil.rmtree(preview_dir, ignore_errors=True)
    preview_dir.mkdir(parents=True, exist_ok=True)

    docx_path = preview_dir / "preview.docx"
    docx_file.save(str(docx_path))

    # Recursos opcionales (mismas reglas que el generar normal)
    if "recursos" in request.files:
        recursos_in = preview_dir / "recursos"
        recursos_in.mkdir(parents=True, exist_ok=True)
        for f in request.files.getlist("recursos"):
            if not f or not f.filename:
                continue
            if not _allowed_file(f.filename, ALLOWED_RESOURCE_EXT):
                continue
            safe = secure_filename(f.filename) or "recurso"
            dest = recursos_in / safe
            f.save(str(dest))

    # Parámetros (los mismos que /api/generar)
    titulo = (request.form.get("titulo") or "").strip() or None
    autor = (request.form.get("autor") or "").strip() or None
    try:
        mastery = max(0, min(100, int(request.form.get("mastery", "70"))))
    except (TypeError, ValueError):
        mastery = 70
    try:
        weight_view = max(0, min(100, int(request.form.get("weight_view", "40"))))
    except (TypeError, ValueError):
        weight_view = 40
    try:
        weight_quiz = max(0, min(100, int(request.form.get("weight_quiz", "60"))))
    except (TypeError, ValueError):
        weight_quiz = 60
    try:
        view_min_seconds = max(0, int(request.form.get("view_min_seconds", "10")))
    except (TypeError, ValueError):
        view_min_seconds = 10
    view_strategy = request.form.get("view_strategy", "both").lower().strip()
    if view_strategy not in ("scroll", "time", "both"):
        view_strategy = "both"
    paleta = request.form.get("paleta", "azul")
    color_deep = request.form.get("color_deep", "")
    color_primary = request.form.get("color_primary", "")
    color_bright = request.form.get("color_bright", "")
    custom_palette = None
    defaults_match = (
        color_deep.lower() == "#0a2540"
        and color_primary.lower() == "#1d4ed8"
        and color_bright.lower() == "#2563eb"
    )
    if color_deep and color_primary and color_bright and not defaults_match:
        custom_palette = {
            "primary_deep": color_deep,
            "primary": color_primary,
            "primary_bright": color_bright,
        }

    # Parsear y renderizar (sin packager)
    try:
        from scorm_builder.parser import parse_docx, _normalize_weights
        from scorm_builder.renderer import render_topic
        from scorm_builder.themes import get_theme, make_custom_theme, Theme

        course = parse_docx(str(docx_path))
        if titulo:
            course.metadata.title = titulo
        if autor:
            course.metadata.author = autor
        course.metadata.mastery = mastery
        course.metadata.weight_view = weight_view
        course.metadata.weight_quiz = weight_quiz
        course.metadata.view_min_seconds = view_min_seconds
        course.metadata.view_strategy = view_strategy
        _normalize_weights(course)

        if custom_palette:
            theme_obj = make_custom_theme(**custom_palette)
        else:
            from scorm_builder.themes import THEMES
            theme_name = paleta if paleta in THEMES else "azul"
            theme_obj = get_theme(theme_name)

        if not course.topics:
            return jsonify({"error": "No se ha detectado ningún tema en el documento"}), 400

        # Solo el primer tema
        html = render_topic(course.topics[0], course, theme_obj)
        # Inyectar un baner de "vista previa" arriba del módulo
        banner = (
            '<div style="background:#fef3c7;border-bottom:2px solid #f59e0b;'
            'padding:0.5rem 1rem;font-family:system-ui,sans-serif;font-size:0.85rem;'
            'color:#78350f;text-align:center;position:sticky;top:0;z-index:1000;">'
            '👁 <strong>Vista previa</strong> — esto es solo el primer tema. '
            'Los recursos multimedia locales no se cargarán; el SCORM final sí los incluirá.'
            '</div>'
        )
        html = html.replace("<body>", "<body>" + banner, 1)
        return html, 200, {"Content-Type": "text/html; charset=utf-8"}
    except Exception as e:
        return jsonify({"error": f"Error al generar preview: {e}"}), 500


# ============================================================
# Generadores auxiliares para los recursos extra (v0.4.3)
# ============================================================
def _gen_readme(course_data: dict, num_hours: float, target: Path) -> Path:
    """Genera un README.txt con la ficha del curso."""
    md = course_data.get("metadata", {})
    topics = course_data.get("topics", [])
    lines = [
        "═" * 60,
        f"  {md.get('title', 'Curso sin título')}",
        "═" * 60,
        "",
        f"Autor / entidad : {md.get('author', '—')}",
        f"Duración        : {num_hours} horas estimadas",
        f"Mastery         : {md.get('mastery', 70)}% para aprobar",
        f"Peso vista      : {md.get('weight_view', 40)}%",
        f"Peso quiz       : {md.get('weight_quiz', 60)}%",
        f"Nº de temas     : {len(topics)}",
        f"Nº de preguntas : {sum(len(t.get('quiz', [])) for t in topics)}",
        f"Fecha de export : {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "Contenido:",
    ]
    for t in topics:
        lines.append(f"  · Tema {t.get('number')}: {t.get('title', '')}")
        for s in t.get("subsections", []):
            lines.append(f"      {s.get('number', '')}  {s.get('title', '')}")
    lines.append("")
    lines.append("Generado con SCORM Builder v0.5.1")
    target.write_text("\n".join(lines), encoding="utf-8")
    return target


def _gen_json_export(course_data: dict, target: Path) -> Path:
    """Genera el volcado JSON de la estructura del curso."""
    target.write_text(json.dumps(course_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def _gen_glossary(course_data: dict, target: Path) -> Path:
    """Extrae términos en negrita y los lista como glosario simple.

    Si en el documento hay callouts del tipo 'glosario' o 'concepto clave',
    los recoge. Es una primera versión sin IA; se puede sofisticar después.
    """
    md = course_data.get("metadata", {})
    topics = course_data.get("topics", [])
    terms: dict[str, str] = {}
    # Recolectar callouts de tipo "concepto clave" como entradas de glosario
    for t in topics:
        for s in t.get("subsections", []):
            for b in s.get("blocks", []):
                bt = b.get("type", "")
                txt = b.get("text", "")
                if bt == "callout_key" and txt:
                    # Tomar el primer fragmento "Término: definición" si lo hay
                    if ":" in txt:
                        term, _, defn = txt.partition(":")
                        term = term.strip().rstrip(".")
                        if term and term not in terms and len(term) < 80:
                            terms[term] = defn.strip()
                    else:
                        # Sin separador: lo dejamos como término sin def explícita
                        first_sentence = re.split(r"[.\n]", txt, maxsplit=1)[0].strip()
                        if first_sentence and first_sentence not in terms and len(first_sentence) < 80:
                            terms[first_sentence] = ""
    # Salida
    out_lines = [f"# Glosario — {md.get('title', 'Curso')}", ""]
    if not terms:
        out_lines.append("(No se han detectado términos automáticamente. Añade callouts")
        out_lines.append("de tipo 'concepto clave' a tu Word con formato 'Término: definición'.)")
    else:
        for term in sorted(terms.keys()):
            defn = terms[term]
            out_lines.append(f"**{term}**" + (f" — {defn}" if defn else ""))
            out_lines.append("")
    target.write_text("\n".join(out_lines), encoding="utf-8")
    return target


def _gen_anki_csv(course_data: dict, target: Path) -> Path:
    """Exporta las preguntas del quiz como flashcards Anki (CSV).

    Formato: Front | Back   (Anki acepta CSV con separador tab o coma)
    """
    import csv
    rows = []
    for t in course_data.get("topics", []):
        for i, q in enumerate(t.get("quiz", []) or []):
            text = q.get("text", "")
            options = q.get("options", [])
            correct = q.get("correct_index", 0)
            explanation = q.get("explanation") or ""
            try:
                correct_opt = options[correct] if 0 <= correct < len(options) else ""
            except Exception:
                correct_opt = ""
            front = text + "\n\n" + "\n".join(f"{chr(65+j)}) {o}" for j, o in enumerate(options))
            back = f"Respuesta correcta: {chr(65+correct)}) {correct_opt}"
            if explanation:
                back += f"\n\nExplicación: {explanation}"
            rows.append([front, back, f"Tema {t.get('number')}"])
    with open(target, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["Front", "Back", "Tag"])
        w.writerows(rows)
    return target


def _gen_certificate_pdf(course_data: dict, num_hours: float, target: Path) -> Optional[Path]:
    """Genera una plantilla PDF de certificado con espacio para el nombre del alumno."""
    try:
        from reportlab.lib.pagesizes import landscape, A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import cm
        from reportlab.lib.colors import HexColor
    except ImportError:
        return None
    md = course_data.get("metadata", {})
    title = md.get("title", "Curso")
    author = md.get("author", "")
    w, h = landscape(A4)
    c = canvas.Canvas(str(target), pagesize=landscape(A4))
    # Marco
    c.setStrokeColor(HexColor("#0A2540"))
    c.setLineWidth(3)
    c.rect(1.5*cm, 1.5*cm, w-3*cm, h-3*cm)
    c.setLineWidth(1)
    c.rect(1.8*cm, 1.8*cm, w-3.6*cm, h-3.6*cm)
    # Título
    c.setFillColor(HexColor("#0A2540"))
    c.setFont("Helvetica-Bold", 32)
    c.drawCentredString(w/2, h-3.5*cm, "CERTIFICADO DE APROVECHAMIENTO")
    c.setFont("Helvetica", 14)
    c.drawCentredString(w/2, h-4.5*cm, "Se otorga el presente a")
    # Hueco para nombre
    c.setStrokeColor(HexColor("#2563EB"))
    c.setLineWidth(1)
    c.line(w/2-9*cm, h-6.5*cm, w/2+9*cm, h-6.5*cm)
    c.setFont("Helvetica-Oblique", 10)
    c.setFillColor(HexColor("#94A3B8"))
    c.drawCentredString(w/2, h-7*cm, "(Nombre del alumno)")
    # Curso
    c.setFillColor(HexColor("#0F172A"))
    c.setFont("Helvetica", 13)
    c.drawCentredString(w/2, h-8.5*cm, "Por haber superado satisfactoriamente el curso")
    c.setFont("Helvetica-Bold", 18)
    c.setFillColor(HexColor("#1D4ED8"))
    c.drawCentredString(w/2, h-9.8*cm, title[:80])
    c.setFont("Helvetica", 12)
    c.setFillColor(HexColor("#0F172A"))
    c.drawCentredString(w/2, h-11*cm, f"con una duración de {num_hours} horas lectivas.")
    # Pie: fecha y firma
    c.setFont("Helvetica", 10)
    c.setFillColor(HexColor("#64748B"))
    c.drawString(3*cm, 3*cm, f"Fecha: {datetime.now().strftime('%d de %B de %Y')}")
    c.line(w-9*cm, 3.5*cm, w-3*cm, 3.5*cm)
    c.drawCentredString(w-6*cm, 3*cm, author or "Firma y sello de la entidad")
    c.save()
    return target


def _gen_manifest_preview(scorm_dir: Path, target_dir: Path) -> List[Path]:
    """Copia los imsmanifest.xml de los SCORMs fuera del ZIP para inspección."""
    out = []
    for zp in scorm_dir.glob("*.zip"):
        try:
            with zipfile.ZipFile(zp) as zf:
                manifest = zf.read("imsmanifest.xml")
            dst = target_dir / f"{zp.stem}_manifest.xml"
            dst.write_bytes(manifest)
            out.append(dst)
        except Exception:
            pass
    return out


@app.route("/api/generar", methods=["POST"])
@login_required
def api_generar():
    user = current_user()
    udir = user_dir(user["id"])

    # Aceptar múltiples archivos docx (modo lote)
    docx_files = request.files.getlist("docx")
    docx_files = [f for f in docx_files if f and f.filename and f.filename.lower().endswith(".docx")]
    if not docx_files:
        return jsonify({"error": "No has subido ningún archivo Word válido (.docx)"}), 400

    upload_mode = (request.form.get("upload_mode") or "single").lower()
    if upload_mode not in ("single", "batch"):
        upload_mode = "single"
    # En single, ignorar archivos extra (solo el primero)
    if upload_mode == "single":
        docx_files = docx_files[:1]

    # Carpeta única para este job
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    token = f"{timestamp}_{uuid.uuid4().hex[:8]}"
    job_dir = udir / f"job_{token}"
    job_dir.mkdir(parents=True, exist_ok=True)

    # Recursos extra (multimedia subidos)
    extra_resources_paths: list[Path] = []
    rejected: list[str] = []
    if "recursos" in request.files:
        recursos_dir_in = job_dir / "_input_recursos"
        recursos_dir_in.mkdir(parents=True, exist_ok=True)
        for f in request.files.getlist("recursos"):
            if not f or not f.filename:
                continue
            if not _allowed_file(f.filename, ALLOWED_RESOURCE_EXT):
                rejected.append(f.filename)
                continue
            safe = secure_filename(f.filename) or "recurso"
            dest = recursos_dir_in / safe
            counter = 1
            while dest.exists():
                stem, _, suf = safe.rpartition(".")
                dest = recursos_dir_in / (
                    f"{stem}_{counter}.{suf}" if suf else f"{safe}_{counter}"
                )
                counter += 1
            f.save(str(dest))
            extra_resources_paths.append(dest)

    # ----- Parámetros del formulario -----
    titulo_curso = (request.form.get("titulo") or "").strip()
    autor = (request.form.get("autor") or "").strip() or None
    try:
        num_hours = max(0.5, float(request.form.get("num_hours", "20")))
    except (TypeError, ValueError):
        num_hours = 20.0
    try:
        mastery = max(0, min(100, int(request.form.get("mastery", "70"))))
    except (TypeError, ValueError):
        mastery = 70
    scorm_version = (request.form.get("scorm_version") or "both").lower()
    if scorm_version not in ("1.2", "2004", "both"):
        scorm_version = "both"
    try:
        weight_view = max(0, min(100, int(request.form.get("weight_view", "40"))))
        weight_quiz = max(0, min(100, int(request.form.get("weight_quiz", "60"))))
        view_min_seconds = max(0, int(request.form.get("view_min_seconds", "10")))
    except (TypeError, ValueError):
        weight_view, weight_quiz, view_min_seconds = 40, 60, 10
    view_strategy = (request.form.get("view_strategy") or "both").lower().strip()
    if view_strategy not in ("scroll", "time", "both"):
        view_strategy = "both"

    # Paleta
    paleta = request.form.get("paleta", "azul")
    color_deep = request.form.get("color_deep", "")
    color_primary = request.form.get("color_primary", "")
    color_bright = request.form.get("color_bright", "")
    custom_palette = None
    defaults_match = (
        color_deep.lower() == "#0a2540"
        and color_primary.lower() == "#1d4ed8"
        and color_bright.lower() == "#2563eb"
    )
    if color_deep and color_primary and color_bright and not defaults_match:
        custom_palette = {
            "primary_deep": color_deep,
            "primary": color_primary,
            "primary_bright": color_bright,
        }

    # Tracking (informativo: la mayoría son flags que ya envía el wrapper SCORM
    # universal automáticamente; aquí los recogemos para uso futuro y para que
    # el manifest los refleje cuando aplique).
    def _bool(name, default=False):
        return request.form.get(name, str(default)).lower() == "true"

    tracking = {
        "completion": _bool("track_completion", True),
        "score": _bool("track_score", True),
        "success": _bool("track_success", True),
        "time": _bool("track_time", True),
        "suspend": _bool("track_suspend", True),
        "location": _bool("track_location", True),
        "interactions": _bool("track_interactions", True),
        "progress": _bool("track_progress", False),
        "objectives": _bool("track_objectives", False),
        "max_time": _bool("track_max_time", False),
        "max_attempts": _bool("track_max_attempts", False),
    }
    try:
        max_time_minutes = max(1, int(request.form.get("max_time_minutes", "120")))
    except (TypeError, ValueError):
        max_time_minutes = 120
    try:
        max_attempts = max(1, int(request.form.get("max_attempts", "3")))
    except (TypeError, ValueError):
        max_attempts = 3

    # Recursos a generar
    gen = {
        "pdf":               _bool("gen_pdf", True),
        "aiken":             _bool("gen_aiken", True),
        "html_standalone":   _bool("gen_html_standalone", False),
        "glossary":          _bool("gen_glossary", False),
        "json":              _bool("gen_json", True),
        "readme":            _bool("gen_readme", True),
        "certificate":       _bool("gen_certificate", False),
        "anki":              _bool("gen_anki", False),
        "subtitles":         _bool("gen_subtitles", False),
        "wcag":              _bool("gen_wcag", True),
        "manifest_preview":  _bool("gen_manifest_preview", False),
    }

    warnings: list[str] = []
    for r in rejected:
        warnings.append(f"Recurso rechazado por extensión no permitida: {r}")

    # ----- Subtítulos automáticos para vídeos (si se pide) -----
    if gen["subtitles"] and extra_resources_paths:
        try:
            from scorm_builder.subtitles import generate_subtitles, whisper_available
        except ImportError:
            whisper_available = lambda: False
            generate_subtitles = None
        if not whisper_available():
            warnings.append(
                "Subtítulos automáticos pedidos pero faster-whisper no está instalado. "
                "Instala con: pip install faster-whisper"
            )
        else:
            video_exts = {"mp4", "webm", "ogv", "mov", "m4v"}
            for path in list(extra_resources_paths):
                ext = path.suffix.lower().lstrip(".")
                if ext not in video_exts:
                    continue
                vtt_path = path.with_suffix(".vtt")
                if vtt_path.exists():
                    continue
                res = generate_subtitles(path, vtt_path, model_size="tiny")
                if res:
                    extra_resources_paths.append(res)
                else:
                    warnings.append(f"No se pudieron generar subtítulos para '{path.name}'.")

    # ----- Procesar cada DOCX -----
    output_dir = job_dir / "salida"
    output_dir.mkdir(parents=True, exist_ok=True)

    total_topics = 0
    total_questions = 0
    total_pdfs = 0
    total_aiken = 0
    total_resources = 0
    total_packages = 0
    course_titles: list[str] = []
    last_course_data: Optional[dict] = None

    for idx, docx_file in enumerate(docx_files):
        # Guardar el .docx subido
        safe_name = secure_filename(docx_file.filename) or f"curso_{idx+1}.docx"
        docx_path = job_dir / safe_name
        docx_file.save(str(docx_path))

        # Título de este SCORM: en batch usamos el nombre del archivo;
        # en single usamos el título del formulario.
        if upload_mode == "batch":
            file_stem = Path(safe_name).stem.replace("_", " ").strip()
            this_title = file_stem or titulo_curso or "Curso"
            # Subcarpeta por archivo en la salida
            this_out = output_dir / f"unidad_{idx+1:02d}_{Path(safe_name).stem[:30]}"
        else:
            this_title = titulo_curso or "Curso"
            this_out = output_dir / "curso"

        this_out.mkdir(parents=True, exist_ok=True)

        try:
            from scorm_builder.api import build_complete_course
            r = build_complete_course(
                docx_path=str(docx_path),
                output_dir=this_out,
                theme=paleta,
                custom_palette=custom_palette,
                title_override=this_title,
                author_override=autor,
                mastery_override=mastery,
                weight_view_override=weight_view,
                weight_quiz_override=weight_quiz,
                view_min_seconds_override=view_min_seconds,
                view_strategy_override=view_strategy,
                generate_pdfs=gen["pdf"],
                generate_aiken=gen["aiken"],
                extra_resources=extra_resources_paths,
                # En modo lote, el SCO toma el nombre del fichero como título
                topic_title_override=(this_title if upload_mode == "batch" else None),
            )
        except Exception as e:
            warnings.append(f"Error procesando '{safe_name}': {e}")
            continue

        total_topics += r.num_topics
        total_questions += r.num_questions
        total_pdfs += len(r.pdf_files)
        total_aiken += len(r.aiken_files)
        total_resources += len(r.resource_files)
        # En modo "solo 2004", los paquetes 1.2 que generó build_complete_course
        # NO cuentan (los borraremos abajo).
        if scorm_version != "2004":
            total_packages += len(r.scorm_zips)
        course_titles.append(r.course.metadata.title)
        course_dict = r.course.to_dict()
        course_dict["metadata"]["num_hours"] = num_hours
        last_course_data = course_dict

        # ----- SCORM 2004 (si se pide) -----
        if scorm_version in ("2004", "both"):
            try:
                from scorm_builder.exporters import export_scorm_2004
                from scorm_builder.renderer import render_html
                from scorm_builder.themes import get_theme, make_custom_theme
                theme_obj = (
                    make_custom_theme(**custom_palette)
                    if custom_palette else get_theme(paleta)
                )
                htmls = render_html(r.course, theme_obj)
                scorm2004_dir = this_out / "scorm_2004"
                scorm2004_dir.mkdir(exist_ok=True)
                for t in r.course.topics:
                    if t.number not in htmls:
                        continue
                    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", t.title.lower())[:40]
                    zip_path = scorm2004_dir / f"T{t.number:02d}_{slug}_scorm2004.zip"
                    export_scorm_2004(
                        topic=t,
                        html_content=htmls[t.number],
                        course_title=r.course.metadata.title,
                        output_path=zip_path,
                        recursos_dir=(this_out / "recursos") if (this_out / "recursos").exists() else None,
                        mastery=mastery,
                    )
                    total_packages += 1
            except Exception as e:
                warnings.append(f"No se pudo generar SCORM 2004 para '{safe_name}': {e}")

        # Si el usuario eligió SOLO 2004, eliminamos la carpeta 1.2 (no se quería)
        if scorm_version == "2004":
            scorm12_dir = this_out / "scorm"
            if scorm12_dir.exists():
                shutil.rmtree(scorm12_dir, ignore_errors=True)
        elif scorm_version == "both":
            scorm12_dir = this_out / "scorm"
            if scorm12_dir.exists():
                try:
                    scorm12_dir.rename(this_out / "scorm_1.2")
                except Exception:
                    pass
        # Si pidió solo 1.2, la carpeta "scorm" se queda como está

        # ----- Recursos auto-generables (por curso) -----
        extras_dir = this_out / "extras"
        extras_dir.mkdir(exist_ok=True)
        try:
            if gen["readme"]:
                _gen_readme(course_dict, num_hours, extras_dir / "README.txt")
            if gen["json"]:
                _gen_json_export(course_dict, extras_dir / "estructura_curso.json")
            if gen["glossary"]:
                _gen_glossary(course_dict, extras_dir / "glosario.md")
            if gen["anki"]:
                _gen_anki_csv(course_dict, extras_dir / "flashcards_anki.csv")
            if gen["certificate"]:
                cert = _gen_certificate_pdf(course_dict, num_hours, extras_dir / "plantilla_certificado.pdf")
                if cert is None:
                    warnings.append(
                        "Plantilla de certificado solicitada pero reportlab no está instalado. "
                        "Instala con: pip install reportlab"
                    )
            if gen["html_standalone"]:
                try:
                    from scorm_builder.exporters import export_html_standalone
                    from scorm_builder.renderer import render_html
                    from scorm_builder.themes import get_theme, make_custom_theme
                    theme_obj = (
                        make_custom_theme(**custom_palette)
                        if custom_palette else get_theme(paleta)
                    )
                    htmls = render_html(r.course, theme_obj)
                    export_html_standalone(r.course, htmls, extras_dir / "html_standalone.zip")
                except Exception as e:
                    warnings.append(f"HTML standalone falló: {e}")
            if gen["manifest_preview"]:
                # Buscar el subdir con SCORMs (puede ser scorm, scorm_1.2 o scorm_2004)
                for candidate in ("scorm", "scorm_1.2", "scorm_2004"):
                    d = this_out / candidate
                    if d.exists():
                        _gen_manifest_preview(d, extras_dir)
        except Exception as e:
            warnings.append(f"Error generando extras para '{safe_name}': {e}")

        # ----- WCAG (por curso) -----
        if gen["wcag"]:
            try:
                from scorm_builder.wcag import validate_course
                recursos_target = this_out / "recursos" if (this_out / "recursos").exists() else None
                report = validate_course(r.course, recursos_dir=recursos_target)
                for issue in report.issues:
                    tag = "🔴" if issue.severity == "error" else "🟡"
                    warnings.append(
                        f"[{safe_name}] {tag} WCAG {issue.code} — {issue.title}"
                        + (f" ({issue.location})" if issue.location else "")
                    )
            except Exception as e:
                warnings.append(f"No se pudo ejecutar WCAG para '{safe_name}': {e}")

        # Persistir estructura del último curso (para edición posterior)
        try:
            structure_json = json.dumps(course_dict, ensure_ascii=False, indent=2)
            (job_dir / f"structure_{idx+1}.json").write_text(
                structure_json, encoding="utf-8"
            )
            if upload_mode == "single" and idx == 0:
                (job_dir / "structure.json").write_text(
                    structure_json, encoding="utf-8"
                )
        except Exception:
            pass

    # ----- Empaquetar todo en un único ZIP descargable -----
    final_zip = job_dir / f"curso_{token}.zip"
    with zipfile.ZipFile(final_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in output_dir.rglob("*"):
            if path.is_file():
                zf.write(path, arcname=str(path.relative_to(output_dir)))

    # ----- Persistir en BD -----
    display_title = (
        titulo_curso if upload_mode == "single"
        else f"{titulo_curso} ({len(course_titles)} unidades)"
    )
    with db() as conn:
        conn.execute(
            """INSERT INTO courses
            (user_id, token, title, author, num_topics, num_questions,
             num_pdfs, num_aiken, num_resources, zip_path, zip_size,
             warnings_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user["id"], token,
                display_title or "Sin título",
                autor,
                total_topics, total_questions,
                total_pdfs, total_aiken, total_resources,
                str(final_zip), final_zip.stat().st_size,
                json.dumps(warnings, ensure_ascii=False),
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()

    return jsonify({
        "token": token,
        "num_packages": total_packages,
        "num_topics": total_topics,
        "num_questions": total_questions,
        "num_pdfs": total_pdfs,
        "num_aiken": total_aiken,
        "num_resources": total_resources,
        "scorm_version": scorm_version,
        "upload_mode": upload_mode,
        "warnings": warnings[:30],
    })


@app.route("/api/descargar/<token>")
def api_descargar(token):
    user = current_user()
    row = None
    if user:
        with db() as conn:
            row = conn.execute(
                "SELECT zip_path, title FROM courses WHERE token = ? AND user_id = ?",
                (token, user["id"]),
            ).fetchone()
    if row:
        zip_path = Path(row["zip_path"])
        title = row["title"] or "curso"
    else:
        # Compatibilidad con cursos creados antes de v0.4.1, cuando no había
        # cuentas ni tabla courses y los jobs vivían directamente en APP_DIR.
        zip_path = APP_DIR / f"job_{token}" / f"curso_{token}.zip"
        title = "curso"
    if not zip_path.exists():
        abort(410 if row else 404)
    safe_title = re.sub(r"[^A-Za-z0-9_-]+", "_", title)[:50]
    return send_file(
        str(zip_path),
        as_attachment=True,
        download_name=f"scorm_{safe_title}_{token}.zip",
        mimetype="application/zip",
    )


# ============================================================
# Lanzador
# ============================================================
def open_browser():
    import time
    time.sleep(1.2)
    port = int(os.environ.get("PORT", "5000"))
    webbrowser.open(f"http://localhost:{port}")


def main():
    print()
    print("=" * 60)
    print("  SCORM Builder · App web v0.5.1")
    print("=" * 60)
    print()
    print(f"  Carpeta de trabajo: {APP_DIR}")
    print()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    open_browser_on_start = os.environ.get("SCORM_BUILDER_OPEN_BROWSER", "1") == "1"
    print(f"  Servidor en http://{host}:{port}")
    print()
    print("  - Crea una cuenta la primera vez")
    print("  - Tus cursos quedan guardados en 'Mis cursos'")
    print("  - Para detener la app: Ctrl+C en esta ventana")
    print()
    print("=" * 60)
    print()
    if open_browser_on_start:
        threading.Thread(target=open_browser, daemon=True).start()
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()

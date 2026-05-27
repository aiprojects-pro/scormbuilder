"""Renderer: convierte una CourseStructure en HTML.

Cada tema se convierte en un HTML completo con:
- Cabecera coloreada con título del tema
- Sidebar lateral con subapartados (sticky)
- Cuerpo con bloques renderizados según su tipo
- Quiz interactivo con feedback automático y reporte SCORM
- Botón flotante "subir al inicio"
- Botón final "Completar tema" que notifica setCompleted al LMS
"""
from __future__ import annotations

import html
import re
from typing import List, Dict, Optional
from pathlib import Path

from scorm_builder.parser import (
    CourseStructure, Topic, Subsection, Block, BlockType, Question,
)
from scorm_builder.themes import Theme, theme_to_css_vars

from functools import lru_cache

# Carpeta de assets estáticos: course.css + course.js + scorm_api.js. Se
# carga por demanda y se cachea en memoria con lru_cache para no re-leer del
# disco N veces (uno por tema renderizado).
_ASSETS_DIR = Path(__file__).parent / "assets"


@lru_cache(maxsize=1)
def _load_css_body() -> str:
    return (_ASSETS_DIR / "css" / "course.css").read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _load_js_block() -> str:
    return (_ASSETS_DIR / "js" / "course.js").read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _load_scorm_api_js() -> str:
    return (_ASSETS_DIR / "js" / "scorm_api.js").read_text(encoding="utf-8")



# ============================================================
# CSS COMPLETO DEL CURSO
# ============================================================

def _image_tint_css(theme: Theme) -> str:
    """v0.5.7: filtro CSS para retintar las imágenes embebidas del DOCX
    (cajas con color, recuadros, tablas) hacia el color de la paleta.

    v0.8.2 BUG FIX: antes había un threshold `if abs(rotate) < 12: return ""`
    que cortaba el filtro cuando la paleta era azul (hue cercano al 220 del
    DOCX). El usuario seleccionaba "paleta azul" y las imágenes seguían con
    el tono original del Word, sin acercarse al azul corporativo de la paleta.
    Ahora el filtro SE APLICA SIEMPRE (excepto para tonos grises puros), y
    además combinamos `hue-rotate` con `saturate` para empujar el tono hacia
    la saturación del primary del tema — así dos azules distintos terminan
    pareciéndose visualmente, no solo el hue.

    Las imágenes con class 'no-tint' o atributo data-no-tint quedan sin tocar
    (fotografías, ilustraciones reales que no deben cambiar).
    """
    primary = (theme.primary or "").lstrip("#")
    if len(primary) != 6:
        return ""
    try:
        r = int(primary[0:2], 16) / 255.0
        g = int(primary[2:4], 16) / 255.0
        b = int(primary[4:6], 16) / 255.0
    except ValueError:
        return ""
    mx, mn = max(r, g, b), min(r, g, b)
    if mx == mn:
        return ""  # gris puro: sin filtro
    # Hue (0..360)
    if mx == r:
        h = ((g - b) / (mx - mn)) % 6
    elif mx == g:
        h = (b - r) / (mx - mn) + 2
    else:
        h = (r - g) / (mx - mn) + 4
    h_deg = round(h * 60)
    # Saturation (0..1) — HSL
    l = (mx + mn) / 2.0
    s = (mx - mn) / (1 - abs(2 * l - 1)) if l not in (0, 1) else 0
    # DOCX blue base: ~hue 220, saturación ~0.5 (Microsoft Word default)
    base_blue_hue = 220
    rotate = (h_deg - base_blue_hue) % 360
    if rotate > 180:
        rotate -= 360
    # v0.8.2: factor de saturación: empuja imágenes hacia la saturación de
    # la paleta. Si la paleta es muy saturada (s≈0.8, azul corporativo brillante)
    # multiplicamos saturación. Si la paleta es desaturada (s≈0.3, pasteles)
    # la reducimos. Rango razonable: 0.5 a 1.8.
    sat_factor = max(0.5, min(1.8, s * 1.6 + 0.5))
    return f"""
/* v0.8.2: retintado de imágenes embebidas del DOCX hacia la paleta.
   Combina hue-rotate ({rotate}deg) con saturate ({sat_factor:.2f}) para
   acercar la apariencia al primary del tema. Para excluir una imagen
   concreta: añade class="no-tint" o data-no-tint. */
.topic-body img:not(.no-tint):not([data-no-tint]),
.module-content img:not(.no-tint):not([data-no-tint]),
main img:not(.no-tint):not([data-no-tint]) {{
  filter: hue-rotate({rotate}deg) saturate({sat_factor:.2f});
}}
"""


def get_full_css(theme: Theme) -> str:
    """Devuelve el CSS completo del curso con la paleta aplicada.

    El cuerpo CSS estático se carga desde `assets/css/course.css` y se cachea.
    Solo se concatenan los pedazos dinámicos (variables CSS y tint) por delante.
    """
    return theme_to_css_vars(theme) + _image_tint_css(theme) + _load_css_body()


# ============================================================
# JS COMPLETO DEL CURSO
# ============================================================

# JS_BLOCK se carga ahora desde assets/js/course.js (vía _load_js_block).


# SCORM_API_JS se carga ahora desde assets/js/scorm_api.js (vía _load_scorm_api_js).


# ============================================================
# FUNCIONES DE RENDERIZADO
# ============================================================

def _h(text: str) -> str:
    """Escapa texto para HTML."""
    return html.escape(text or "", quote=True)


def _h_or_html(block: Block) -> str:
    """Devuelve `block.text_html` si está definido (HTML inline preservado),
    o el texto escapado si no. Centraliza la decisión en el renderer."""
    if block.text_html is not None:
        return block.text_html
    return _h(block.text)


def _items_or_html(block: Block) -> List[str]:
    """Devuelve los items renderizados como HTML, preservando inline si está disponible."""
    if block.items_html is not None and len(block.items_html) == len(block.items):
        return [
            h if h is not None else _h(t)
            for h, t in zip(block.items_html, block.items)
        ]
    return [_h(it) for it in block.items]


def _render_block(block: Block) -> str:
    """Renderiza un bloque individual."""
    bt = block.type
    if isinstance(bt, str):
        bt = BlockType(bt)

    if bt == BlockType.PARAGRAPH:
        return f"<p>{_h_or_html(block)}</p>"

    if bt == BlockType.HEADING_3:
        return f"<h3>{_h_or_html(block)}</h3>"

    if bt == BlockType.HEADING_4:
        return f"<h4>{_h_or_html(block)}</h4>"

    if bt == BlockType.LIST_BULLET:
        items_html = "\n".join(f"  <li>{it}</li>" for it in _items_or_html(block))
        return f"<ul>\n{items_html}\n</ul>"

    if bt == BlockType.LIST_NUMBER:
        items_html = "\n".join(f"  <li>{it}</li>" for it in _items_or_html(block))
        return f"<ol>\n{items_html}\n</ol>"

    if bt == BlockType.TABLE:
        if not block.rows:
            return ""
        # v0.5: si hay rows_html (celdas con enlaces/negritas), las usamos.
        if block.rows_html and len(block.rows_html) == len(block.rows):
            rows_data = block.rows_html
            cell_render = lambda c: c  # ya viene como HTML
        else:
            rows_data = block.rows
            cell_render = _h
        header = rows_data[0]
        body = rows_data[1:]
        # v0.6: detectar si la primera columna actúa como "header lateral".
        # Heurística: si TODAS las celdas de la primera columna del body son
        # cortas (≤ 80 chars de texto plano) y ninguna está vacía, las
        # marcamos como <th scope="row"> para que reciban el estilo de
        # cabecera con fondo claro y texto oscuro accesible.
        def _plain_len(c):
            s = c if isinstance(c, str) else str(c)
            import re as _re
            return len(_re.sub(r"<[^>]+>", "", s).strip())
        first_col_is_header = bool(body) and all(
            row and _plain_len(row[0]) > 0 and _plain_len(row[0]) <= 80
            for row in body
        )
        # Caption opcional si hay extras["caption"]
        caption_html = ""
        cap = (block.extras or {}).get("caption", "").strip() if block.extras else ""
        if cap:
            caption_html = f"<caption>{_h(cap)}</caption>"
        thead = "<thead><tr>" + "".join(f"<th scope=\"col\">{cell_render(c)}</th>" for c in header) + "</tr></thead>"
        def _row_html(row):
            cells = []
            for ci, c in enumerate(row):
                if ci == 0 and first_col_is_header:
                    cells.append(f'<th scope="row">{cell_render(c)}</th>')
                else:
                    cells.append(f'<td>{cell_render(c)}</td>')
            return "<tr>" + "".join(cells) + "</tr>"
        tbody = "<tbody>" + "".join(_row_html(row) for row in body) + "</tbody>"
        return f'<table class="edit-table">{caption_html}{thead}{tbody}</table>'

    if bt == BlockType.CALLOUT_KEY:
        return f'''<aside class="callout callout-key" role="note" aria-label="Concepto clave">
  <div class="callout-icon" aria-hidden="true">i</div>
  <div><p>{_h_or_html(block)}</p></div>
</aside>'''

    if bt == BlockType.CALLOUT_ALERT:
        return f'''<aside class="callout callout-alert" role="note" aria-label="Aviso importante">
  <div class="callout-icon" aria-hidden="true">!</div>
  <div><p>{_h_or_html(block)}</p></div>
</aside>'''

    if bt == BlockType.CALLOUT_SUCCESS:
        return f'''<aside class="callout callout-success" role="note" aria-label="Buena práctica">
  <div class="callout-icon" aria-hidden="true">✓</div>
  <div><p>{_h_or_html(block)}</p></div>
</aside>'''

    if bt == BlockType.CALLOUT_WARN:
        return f'''<aside class="callout callout-warn" role="note" aria-label="Precaución">
  <div class="callout-icon" aria-hidden="true">⚠</div>
  <div><p>{_h_or_html(block)}</p></div>
</aside>'''

    if bt == BlockType.QUOTE:
        # Si el texto empieza con "FUENTE:", separamos
        text = block.text or ""
        source = ""
        # Detección y eliminación case-insensitive del marcador "FUENTE:".
        # Antes se hacía con replace("FUENTE:", "", 1) seguido de un segundo
        # replace, ninguno de los dos case-insensitive — fallaba con "Fuente:".
        m = re.match(r"^\s*FUENTE:\s*", text, flags=re.IGNORECASE)
        if m:
            tail = text[m.end():]
            parts = tail.split("\n", 1)
            source = parts[0].strip()
            text = parts[1] if len(parts) > 1 else ""
        source_html = f'<cite class="concept-tag">{_h(source)}</cite>' if source else ""
        return f'''<blockquote class="concept-box">
  {source_html}
  <p class="quote">{_h(text)}</p>
</blockquote>'''

    if bt == BlockType.DOWNLOAD:
        filename = block.extras.get("file", "") or block.extras.get("src", "")
        if not filename:
            return ""
        # SEC: el filename viene del docx del usuario. Rechazamos rutas
        # absolutas y cualquier segmento ".." para que el descargable no
        # apunte fuera de la carpeta `recursos/` del SCORM.
        if (".." in filename.replace("\\", "/").split("/")) or filename.startswith(("/", "\\")):
            return f'<p class="download-rejected">{_h(block.text or filename)}</p>'
        ext = Path(filename).suffix.upper().lstrip(".") or "FILE"
        return f'''<a class="download-item" href="recursos/{_h(filename)}" target="_blank" download>
  <span class="icon">{_h(ext)}</span>
  <span class="label">{_h(block.text)}</span>
  <span class="meta">{_h(filename)}</span>
</a>'''

    # ---- BLOQUES MULTIMEDIA (v0.2 / v0.5) ----
    if bt == BlockType.IMAGE:
        src = block.extras.get("src", "") or block.extras.get("file", "")
        if not src:
            return ""
        # Resolver URL segura:
        #   http(s)://         → tal cual
        #   data:image/(png|jpeg|gif|webp);base64,...  → tal cual (raster seguro)
        #   data:image/svg+xml o cualquier otro data:  → rechazar (SVG admite <script>)
        #   resto              → tratar como archivo local en recursos/
        if src.startswith(("http://", "https://")):
            url = src
        elif src.startswith("data:"):
            if re.match(r"^data:image/(png|jpeg|gif|webp);base64,", src):
                url = src
            else:
                # data:image/svg+xml o data:text/* → riesgo XSS, omitir el bloque
                return f'<p class="media-image-rejected">{_h(block.text or "Imagen no incluida (formato data: no permitido)")}</p>'
        else:
            url = f"recursos/{src}"
        # Alt text WCAG 1.1.1: usamos block.text si lo hay, si no un genérico
        # (la validación previa habrá avisado de que falta).
        alt = (block.text or "").strip()
        if not alt:
            alt = "Imagen sin descripción"
        caption = f'<figcaption>{_h(block.text)}</figcaption>' if block.text else ""
        return f'''<figure class="media media-image">
  <img src="{_h(url)}" alt="{_h(alt)}" loading="lazy">
  {caption}
</figure>'''

    if bt == BlockType.VIDEO:
        src = block.extras.get("src", "") or block.extras.get("file", "")
        if not src:
            return ""
        is_url = src.startswith(("http://", "https://"))
        # YouTube / Vimeo → iframe (solo si la URL pasa la whitelist estricta
        # de _to_embed_url; en otro caso caemos al render como enlace simple)
        if is_url and ("youtube.com" in src or "youtu.be" in src or "vimeo.com" in src):
            embed_url = _to_embed_url(src)
            if embed_url:
                iframe_title = (block.text or "Vídeo del tema").strip()
                caption = f'<figcaption>{_h(block.text)}</figcaption>' if block.text else ""
                return f'''<figure class="media media-video media-embed">
  <div class="video-wrapper">
    <iframe src="{_h(embed_url)}" title="{_h(iframe_title)}" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>
  </div>
  {caption}
</figure>'''
            # URL parece YT/Vimeo pero no pasa la validación → enlace plano
            return f'<p class="media-embed-rejected"><a href="{_h(src)}" target="_blank" rel="noopener">{_h(block.text or src)}</a></p>'
        url = src if is_url else f"recursos/{src}"
        caption = f'<figcaption>{_h(block.text)}</figcaption>' if block.text else ""
        # Si hay archivo .vtt con el mismo nombre base, lo añadimos como pista de subtítulos
        track_html = ""
        if not is_url and src:
            # El nombre base sin extensión
            base = src.rsplit(".", 1)[0] if "." in src else src
            vtt_url = f"recursos/{base}.vtt"
            track_html = (
                f'\n    <track kind="captions" srclang="es" '
                f'label="Español" src="{_h(vtt_url)}" default>'
            )
        return f'''<figure class="media media-video">
  <video controls preload="metadata" playsinline>
    <source src="{_h(url)}">{track_html}
    Tu navegador no soporta la etiqueta de vídeo.
  </video>
  {caption}
</figure>'''

    if bt == BlockType.AUDIO:
        src = block.extras.get("src", "") or block.extras.get("file", "")
        if not src:
            return ""
        url = src if src.startswith(("http://", "https://")) else f"recursos/{src}"
        caption = f'<figcaption>{_h(block.text)}</figcaption>' if block.text else ""
        return f'''<figure class="media media-audio">
  <audio controls preload="metadata">
    <source src="{_h(url)}">
    Tu navegador no soporta la etiqueta de audio.
  </audio>
  {caption}
</figure>'''

    if bt == BlockType.EMBED:
        src = block.extras.get("src", "") or block.extras.get("file", "")
        if not src:
            return ""
        embed_url = _to_embed_url(src)
        if not embed_url:
            # URL no permitida (no es YouTube/Vimeo válido). No emitimos iframe
            # para evitar javascript:, data: u otros destinos arbitrarios.
            caption = _h(block.text) if block.text else _h(src)
            return f'<p class="media-embed-rejected">{caption}</p>'
        iframe_title = (block.text or "Contenido incrustado").strip()
        caption = f'<figcaption>{_h(block.text)}</figcaption>' if block.text else ""
        return f'''<figure class="media media-embed">
  <div class="video-wrapper">
    <iframe src="{_h(embed_url)}" title="{_h(iframe_title)}" frameborder="0" allow="autoplay; encrypted-media" allowfullscreen></iframe>
  </div>
  {caption}
</figure>'''

    if bt == BlockType.RESOURCE:
        filename = block.extras.get("file", "") or block.extras.get("src", "")
        if not filename:
            return ""
        ext = Path(filename).suffix.upper().lstrip(".") or "FILE"
        is_url = filename.startswith(("http://", "https://"))
        href = filename if is_url else f"recursos/{filename}"
        target_attr = ' target="_blank" rel="noopener"' if is_url else ' download'
        return f'''<a class="download-item"{target_attr} href="{_h(href)}">
  <span class="icon">{_h(ext)}</span>
  <span class="label">{_h(block.text or filename)}</span>
  <span class="meta">{_h(filename)}</span>
</a>'''

    return ""


def _to_embed_url(url: str) -> str:
    """Convierte URLs de YouTube y Vimeo a su versión embebible.

    Si no es de YouTube/Vimeo o ya es una URL embed válida, devuelve `""`.
    El llamador debe omitir el iframe si recibe cadena vacía: así evitamos
    insertar `<iframe src="javascript:...">` o destinos arbitrarios.

    Las regex están ancladas al inicio del host (tras el esquema) para evitar
    bypass tipo `https://youtube.com.evil.com/watch?v=xxx`.
    """
    if not url:
        return ""
    # Aceptar URLs embed ya generadas (idempotencia)
    if re.match(r"^https://www\.youtube\.com/embed/[A-Za-z0-9_\-]+", url):
        return url
    if re.match(r"^https://player\.vimeo\.com/video/\d+", url):
        return url
    # YouTube watch?v=
    m = re.match(r"^(?:https?:)?//(?:www\.)?youtube\.com/watch\?v=([A-Za-z0-9_\-]+)", url)
    if m:
        return f"https://www.youtube.com/embed/{m.group(1)}"
    # YouTube shorts
    m = re.match(r"^(?:https?:)?//(?:www\.)?youtube\.com/shorts/([A-Za-z0-9_\-]+)", url)
    if m:
        return f"https://www.youtube.com/embed/{m.group(1)}"
    # YouTube short link
    m = re.match(r"^(?:https?:)?//(?:www\.)?youtu\.be/([A-Za-z0-9_\-]+)", url)
    if m:
        return f"https://www.youtube.com/embed/{m.group(1)}"
    # Vimeo
    m = re.match(r"^(?:https?:)?//(?:www\.)?vimeo\.com/(\d+)", url)
    if m:
        return f"https://player.vimeo.com/video/{m.group(1)}"
    return ""


def _render_subsection(sub: Subsection, inline_questions: Optional[List[Question]] = None) -> str:
    """Renderiza un subapartado completo, con quiz inline opcional al final."""
    blocks_html = "\n".join(_render_block(b) for b in sub.blocks)
    inline_html = _render_inline_quiz(inline_questions, sub.id) if inline_questions else ""
    return f'''<h2 id="{sub.id}">{_h(sub.number)} {_h(sub.title)}</h2>
{blocks_html}
{inline_html}
'''


def _render_question_options(q: Question, name_prefix: str, q_idx: int) -> str:
    """Renderiza las opciones de una pregunta según su qtype."""
    opts_html_parts: List[str] = []
    qtype = getattr(q, "qtype", "multiple_choice")
    # Para fill_in renderizamos el enunciado con el hueco (lo hace _render_question_stem),
    # las opciones se muestran abajo como en multiple_choice.
    for opt_idx, opt in enumerate(q.options):
        input_id = f"{name_prefix}{q_idx}_opt{opt_idx}"
        if qtype == "true_false":
            label = _h(opt)  # "Verdadero" / "Falso"
        else:
            letter = chr(ord("A") + opt_idx)
            label = f"{letter}. {_h(opt)}"
        opts_html_parts.append(
            f'<label class="quiz-option" for="{input_id}"><input id="{input_id}" '
            f'type="radio" name="{name_prefix}{q_idx}" value="{opt_idx}"> {label}</label>'
        )
    return "\n".join(opts_html_parts)


def _render_question_stem(q: Question) -> str:
    """Renderiza el enunciado de una pregunta. Para fill_in marca el hueco."""
    qtype = getattr(q, "qtype", "multiple_choice")
    if qtype == "fill_in" and "___" in q.text:
        parts = q.text.split("___", 1)
        return f'{_h(parts[0])}<span class="fill-blank" aria-label="hueco a completar"></span>{_h(parts[1]) if len(parts) > 1 else ""}'
    return _h(q.text)


def _render_quiz(topic: Topic, mastery: int) -> str:
    """Renderiza el quiz final de un tema con cálculo de score y reporte SCORM."""
    if not topic.quiz:
        return ""

    questions_html = []
    for idx, q in enumerate(topic.quiz):
        qtype = getattr(q, "qtype", "multiple_choice")
        opts_html = _render_question_options(q, "qf", idx)
        stem_html = _render_question_stem(q)
        questions_html.append(f'''<fieldset class="quiz" data-q="{idx}" data-a="{q.correct_index}" data-qtype="{qtype}">
  <legend class="sr-only">Pregunta {idx+1} de {len(topic.quiz)}</legend>
  <span class="quiz-tag" aria-hidden="true">PREGUNTA {idx+1} / {len(topic.quiz)}</span>
  <p class="quiz-question">{stem_html}</p>
  <div class="quiz-options" role="radiogroup" aria-label="Opciones de respuesta">
    {opts_html}
  </div>
</fieldset>''')

    questions_block = "\n".join(questions_html)

    return f'''<h2 id="evaluacion">Evaluación final</h2>
<p>Responde a las {len(topic.quiz)} preguntas siguientes. Necesitas un <strong>{mastery}%</strong> de aciertos para superar el tema. Puedes repetir el test las veces que necesites.</p>

<form id="quiz-final" onsubmit="event.preventDefault(); evaluarFinal();">
{questions_block}

<button type="submit" class="btn" style="font-size:1.05rem; padding:1rem 2rem;">Comprobar mis respuestas</button>
</form>

<div id="resultado-final" role="status" aria-live="polite" aria-atomic="true" style="display:none; margin-top:2rem;"></div>
'''


def _render_inline_quiz(questions: List[Question], sub_id: str) -> str:
    """Renderiza preguntas intercaladas tras un subapartado (no evaluables,
    son de repaso). Se evalúan en el cliente con feedback inmediato."""
    if not questions:
        return ""
    parts: List[str] = ['<div class="inline-quiz-group">']
    for idx, q in enumerate(questions):
        qtype = getattr(q, "qtype", "multiple_choice")
        name_prefix = f"iq_{sub_id}_"
        opts_html = _render_question_options(q, name_prefix, idx)
        stem_html = _render_question_stem(q)
        feedback_id = f"{name_prefix}{idx}_fb"
        explanation = (q.explanation or "").strip()
        parts.append(f'''<div class="inline-quiz" data-q="{idx}" data-a="{q.correct_index}" data-qtype="{qtype}" data-feedback="{feedback_id}">
  <span class="inline-quiz-tag">💡 Pregunta de repaso</span>
  <p class="quiz-question">{stem_html}</p>
  <div class="quiz-options" role="radiogroup" aria-label="Opciones de respuesta">
    {opts_html}
  </div>
  <button type="button" class="btn-inline-check" onclick="evaluarInline(this)">Comprobar</button>
  <div id="{feedback_id}" class="quiz-feedback" role="status" aria-live="polite"
       data-explanation="{_h(explanation)}"></div>
</div>''')
    parts.append("</div>")
    return "\n".join(parts)


def render_topic(
    topic: Topic,
    course: CourseStructure,
    theme: Theme,
    pdf_filename: Optional[str] = None,
    audio_filename: Optional[str] = None,
) -> str:
    """Renderiza un tema completo como HTML standalone.

    Args:
        topic: el tema a renderizar
        course: el curso completo (para metadata)
        theme: paleta visual
        pdf_filename: si se pasa, se añade un botón "Descargar PDF" en la
            cabecera que apunta a `recursos/<pdf_filename>`. v0.5.
        audio_filename: si se pasa, se añade un botón "Descargar audio" en la
            cabecera apuntando a `recursos/<audio_filename>`. v0.6.
    """
    # Sidebar items: subapartados + evaluación si hay quiz
    sidebar_items = []
    for sub in topic.subsections:
        sidebar_items.append(f'<li><a href="#{sub.id}">{_h(sub.number)} {_h(sub.title)}</a></li>')
    if topic.quiz:
        sidebar_items.append('<li><a href="#evaluacion">Evaluación final</a></li>')
    sidebar_html = "\n".join(sidebar_items)

    # Cuerpo: intro + subapartados + quiz
    body_parts = []
    if topic.intro:
        body_parts.append(f'<p class="lead">{_h(topic.intro)}</p>')
    for sub in topic.subsections:
        # v0.5 Fase 2: si hay preguntas intercaladas para este subapartado, las insertamos
        inline_qs = topic.inline_quiz.get(sub.id) if topic.inline_quiz else None
        body_parts.append(_render_subsection(sub, inline_questions=inline_qs))
        body_parts.append('<div class="section-end"><a href="#top">↑ Subir al inicio del módulo</a></div>')

    if topic.quiz:
        body_parts.append(_render_quiz(topic, course.metadata.mastery))

    body_html = "\n".join(body_parts)

    css = get_full_css(theme)
    js_full = _load_scorm_api_js() + "\n" + _load_js_block()
    mastery = course.metadata.mastery
    weight_view = course.metadata.weight_view
    weight_quiz = course.metadata.weight_quiz
    view_min_seconds = course.metadata.view_min_seconds
    # view_strategy se inyecta dentro de un <script> como literal JS, así que
    # SOLO se aceptan valores de la whitelist conocida. Cualquier otro valor
    # (incluyendo datos manipulados que entren vía course_from_dict) cae al
    # default "both" para evitar inyección de código en el script del SCORM.
    _vs = course.metadata.view_strategy
    view_strategy = _vs if _vs in ("scroll", "time", "both") else "both"
    has_quiz = bool(topic.quiz)
    # Lista de ids de los subapartados, para que el JS sepa cuáles trackear
    subsection_ids_json = "[" + ",".join(f'"{s.id}"' for s in topic.subsections) + "]"

    # v0.5: botones de descarga en la cabecera (PDF + audio si están disponibles)
    download_buttons = []
    if pdf_filename:
        download_buttons.append(f'''<a class="pdf-download-btn" href="recursos/{_h(pdf_filename)}" download
       aria-label="Descargar apuntes del tema en PDF">
      <span class="pdf-icon" aria-hidden="true">📄</span>
      <span class="pdf-label">Descargar apuntes (PDF)</span>
    </a>''')
    if audio_filename:
        download_buttons.append(f'''<a class="audio-download-btn" href="recursos/{_h(audio_filename)}" download
       aria-label="Descargar narración del tema en audio">
      <span class="audio-icon" aria-hidden="true">🔊</span>
      <span class="audio-label">Descargar audio del tema</span>
    </a>''')
    pdf_btn_html = ""
    if download_buttons:
        pdf_btn_html = '<div class="download-bar">\n    ' + "\n    ".join(download_buttons) + '\n    </div>'

    # v0.5 Fase 2: chips de tags bajo el título
    tags_html = ""
    if topic.tags:
        chip_items = "\n".join(
            f'<li class="tag-chip">{_h(t)}</li>' for t in topic.tags
        )
        tags_html = f'''
    <ul class="tag-chips" aria-label="Etiquetas del tema">
{chip_items}
    </ul>'''

    return f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_h(course.metadata.title)} · {_h(topic.title)}</title>
<style>
{css}
</style>
</head>
<body>

<a class="skip-link" href="#contenido">Saltar al contenido</a>

<header class="module-header" role="banner">
  <div class="module-header-inner">
    <div class="crumb"><span class="dot" aria-hidden="true"></span> {_h(course.metadata.title.upper())}</div>
    <div class="module-number" aria-hidden="true">{topic.number:02d}</div>
    <h1 class="module-title">{_h(topic.title)}</h1>
    {tags_html}
    <div class="module-meta">
      <span><strong>Subapartados:</strong> {len(topic.subsections)}</span>
      <span><strong>Preguntas:</strong> {len(topic.quiz)}</span>
      {f'<span><strong>Aprobado:</strong> {mastery}%</span>' if topic.quiz else ''}
    </div>
    {pdf_btn_html}
  </div>
</header>

<div class="module-layout">

  <nav class="module-sidebar" aria-label="Índice del tema">
    <div class="sidebar-title">En este tema</div>
    <ol class="sidebar-nav">
      {sidebar_html}
    </ol>
  </nav>

  <main class="module-main" id="contenido" tabindex="-1">
    <span id="top" aria-hidden="true"></span>
    {body_html}

    <div class="nav-bottom">
      <button class="nav-btn primary" onclick="finalizarTema()" aria-describedby="completar-help">Completar tema ✓</button>
      <p id="completar-help" class="sr-only">Marca el tema como completado en la plataforma de formación.</p>
    </div>

  </main>

</div>

<footer class="module-footer" role="contentinfo">
  <div class="module-footer-inner">
    <div class="brand">{_h(course.metadata.title)}</div>
    <div>{_h(course.metadata.author or 'Curso e-learning')} · v1.0</div>
  </div>
</footer>

<script>
var MASTERY_SCORE = {mastery};
var WEIGHT_VIEW = {weight_view};
var WEIGHT_QUIZ = {weight_quiz};
var VIEW_MIN_SECONDS = {view_min_seconds};
var VIEW_STRATEGY = "{view_strategy}";
var HAS_QUIZ = {str(has_quiz).lower()};
var SUBSECTION_IDS = {subsection_ids_json};
{js_full}
</script>

</body>
</html>'''


def render_html(
    course: CourseStructure,
    theme: Theme,
    pdf_filenames: Optional[Dict[int, str]] = None,
    audio_filenames: Optional[Dict[int, str]] = None,
) -> Dict[int, str]:
    """Renderiza todos los temas del curso. Devuelve {numero_tema: html}.

    Args:
        course: el curso completo
        theme: paleta visual
        pdf_filenames: opcional, {numero_tema: nombre_pdf} para añadir el
            botón "Descargar PDF" en cada tema (v0.5).
        audio_filenames: opcional, {numero_tema: nombre_audio} para añadir el
            botón "Descargar audio del tema" en la cabecera (v0.6).
    """
    pdfs = pdf_filenames or {}
    audios = audio_filenames or {}
    return {
        topic.number: render_topic(
            topic, course, theme,
            pdf_filename=pdfs.get(topic.number),
            audio_filename=audios.get(topic.number),
        )
        for topic in course.topics
    }

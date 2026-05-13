"""Procesamiento inline de runs DOCX (v0.5).

Convierte el contenido de un párrafo Word en HTML enriquecido preservando:
- Negrita, cursiva, subrayado, tachado.
- Hipervínculos (`<w:hyperlink>`) como `<a href="...">`.
- URLs sueltas en texto plano (autolinking).
- Imágenes incrustadas (`<w:drawing>`) → se extraen a disco como recursos.
- Enlaces a YouTube/Vimeo → se devuelven como bloques de vídeo independientes
  (se "rompen" del párrafo y se emiten aparte para embeber el reproductor).

Diseñado para sustituir a `paragraph.text` (que devolvía texto plano y rompía
todo el formato del Word).
"""
from __future__ import annotations

import html
import logging
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any, Callable

logger = logging.getLogger(__name__)


# Namespaces XML del formato Office Open XML (DOCX)
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

W = f"{{{W_NS}}}"
A = f"{{{A_NS}}}"
R = f"{{{R_NS}}}"


# URL detection (plain text → <a>). Algo permisivo pero seguro: requiere esquema
# o www. para no convertir "foo.bar" arbitrarios.
URL_RE = re.compile(
    r"\b(?:https?://|www\.)"
    r"[^\s<>\"\)\]]+",
    re.IGNORECASE,
)


# ============================================================
# MODELO DE BLOQUES "EXTRA" EMITIDOS DESDE UN PÁRRAFO
# ============================================================

@dataclass
class ExtraBlock:
    """Bloque que se emite por separado al procesar un párrafo (imagen, vídeo embebido)."""
    type: str                       # "image" | "video_embed"
    src: str                        # ruta de archivo (imagen extraída) o URL externa
    caption: str = ""               # texto descriptivo (alt/título)
    extras: Dict[str, Any] = field(default_factory=dict)


# ============================================================
# DETECCIÓN DE ENLACES YouTube / Vimeo
# ============================================================

YT_VIMEO_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/|vimeo\.com/)",
    re.IGNORECASE,
)


def is_video_url(url: str) -> bool:
    """True si la URL es de YouTube o Vimeo."""
    return bool(url and YT_VIMEO_RE.search(url))


# ============================================================
# EXTRACTOR DE IMÁGENES INCRUSTADAS
# ============================================================

class ImageExtractor:
    """Extrae imágenes incrustadas de un DOCX a una carpeta destino.

    Mantiene un diccionario rId→ruta para reutilizar imágenes referenciadas
    varias veces y evitar colisiones de nombres.
    """

    def __init__(self, doc, target_dir: Path):
        self.doc = doc
        self.target_dir = Path(target_dir)
        self.target_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, str] = {}  # rId → filename (sin carpeta)
        self._counter = 0

    def extract_by_rid(self, rid: str) -> Optional[str]:
        """Extrae la imagen referenciada por rId y devuelve el nombre de fichero.

        Si la imagen ya se extrajo antes, devuelve el nombre cacheado.
        Devuelve None si rId no apunta a una imagen válida.
        """
        if rid in self._cache:
            return self._cache[rid]
        try:
            rel = self.doc.part.rels[rid]
        except KeyError:
            logger.warning(f"rId no encontrado en relaciones: {rid}")
            return None
        if "image" not in rel.reltype.lower():
            return None
        try:
            image_part = rel.target_part
            blob = image_part.blob
        except Exception as e:
            logger.warning(f"No se pudo leer la imagen {rid}: {e}")
            return None

        # Determinar extensión a partir del content_type o de la URL original
        ct = (image_part.content_type or "").lower()
        ext_map = {
            "image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg",
            "image/gif": "gif", "image/svg+xml": "svg", "image/webp": "webp",
            "image/bmp": "bmp", "image/tiff": "tif",
        }
        ext = ext_map.get(ct)
        if not ext:
            # Intentar deducir del partname (ej. /word/media/image3.png)
            partname = getattr(image_part, "partname", "")
            ext = Path(str(partname)).suffix.lstrip(".") or "png"

        self._counter += 1
        filename = f"docx_img_{self._counter:03d}.{ext}"

        out_path = self.target_dir / filename
        # Si ya existe (raro porque numeramos secuencial), añadir sufijo único
        while out_path.exists():
            filename = f"docx_img_{self._counter:03d}_{uuid.uuid4().hex[:4]}.{ext}"
            out_path = self.target_dir / filename

        out_path.write_bytes(blob)
        self._cache[rid] = filename
        return filename

    def extracted_filenames(self) -> List[str]:
        """Nombres únicos de imagen extraídos."""
        return sorted(set(self._cache.values()))


# ============================================================
# AUTOLINKING DE URLs SUELTAS
# ============================================================

def _strip_inline_tags(html_str: str) -> str:
    """Elimina tags HTML simples conservando el texto. Usado para construir
    atributos como `title` o alt text a partir de HTML enriquecido."""
    no_tags = re.sub(r"<[^>]+>", "", html_str)
    # Des-escapar las entidades básicas
    return (
        no_tags.replace("&amp;", "&").replace("&lt;", "<")
               .replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")
    ).strip()


def _autolink(text_html: str) -> str:
    """Convierte URLs en texto plano en `<a href>`, sin tocar las que ya están
    dentro de un `<a ...>...</a>` existente.

    Estrategia: dividimos el HTML por las regiones que están dentro de `<a>` y
    aplicamos el reemplazo solo en las "fuera".
    """
    # Dividir en segmentos alternando "fuera/dentro de <a>"
    parts = re.split(r"(<a\s[^>]*>.*?</a>)", text_html, flags=re.IGNORECASE | re.DOTALL)
    out = []
    for part in parts:
        if part.startswith("<a") or part.startswith("<A"):
            out.append(part)  # tal cual
            continue

        def _wrap(m: re.Match) -> str:
            url = m.group(0)
            href = url if url.startswith(("http://", "https://")) else f"https://{url}"
            return f'<a href="{html.escape(href, quote=True)}" target="_blank" rel="noopener">{url}</a>'

        out.append(URL_RE.sub(_wrap, part))
    return "".join(out)


# ============================================================
# PROCESAMIENTO DE UN RUN
# ============================================================

def _run_format_tags(run_pr) -> Tuple[str, str]:
    """Devuelve (apertura, cierre) de etiquetas según el formato de un `<w:rPr>`.

    Soporta negrita, cursiva, subrayado, tachado. Combina varias.
    """
    if run_pr is None:
        return "", ""
    open_tags = []
    close_tags = []

    def has(tag_name: str, attr: str = "val") -> bool:
        el = run_pr.find(f"{W}{tag_name}")
        if el is None:
            return False
        v = el.get(f"{W}{attr}")
        # En DOCX, <w:b/> sin atributo = True. <w:b w:val="0"/> = False.
        return v not in ("0", "false")

    if has("b"):
        open_tags.append("<strong>"); close_tags.append("</strong>")
    if has("i"):
        open_tags.append("<em>"); close_tags.append("</em>")
    if has("u"):
        open_tags.append("<u>"); close_tags.append("</u>")
    # tachado
    if run_pr.find(f"{W}strike") is not None:
        open_tags.append("<s>"); close_tags.append("</s>")
    return "".join(open_tags), "".join(reversed(close_tags))


def _run_text_html(run_el) -> str:
    """Extrae el texto de un `<w:r>` como HTML escapado, con formato inline."""
    rpr = run_el.find(f"{W}rPr")
    open_t, close_t = _run_format_tags(rpr)

    parts = []
    for child in run_el:
        tag = child.tag.split("}")[-1]
        if tag == "t":
            parts.append(html.escape(child.text or "", quote=False))
        elif tag == "tab":
            parts.append(" ")
        elif tag == "br":
            parts.append("<br>")
        elif tag == "noBreakHyphen":
            parts.append("&#8209;")
        # <w:drawing> se trata aparte por el caller (devuelve ExtraBlock)

    return open_t + "".join(parts) + close_t


def _extract_drawing_image(run_el, extractor: ImageExtractor) -> Optional[str]:
    """Si el run contiene un <w:drawing> con imagen, extrae y devuelve el filename."""
    drawing = run_el.find(f"{W}drawing")
    if drawing is None:
        return None
    blip = None
    for b in drawing.iter(f"{A}blip"):
        blip = b
        break
    if blip is None:
        return None
    rid = blip.get(f"{R}embed")
    if not rid:
        return None
    return extractor.extract_by_rid(rid)


def _drawing_alt_text(run_el) -> str:
    """Intenta sacar el alt text (descr/title) de un <w:drawing>."""
    drawing = run_el.find(f"{W}drawing")
    if drawing is None:
        return ""
    # Buscar wp:docPr con descr o title
    for el in drawing.iter():
        tag = el.tag.split("}")[-1]
        if tag == "docPr":
            descr = el.get("descr") or el.get("title") or ""
            if descr:
                return descr.strip()
    return ""


# ============================================================
# PROCESAMIENTO DE UN PÁRRAFO COMPLETO
# ============================================================

def _extract_plain_video_urls(text_html: str) -> Tuple[str, List[ExtraBlock]]:
    """Busca URLs de YouTube/Vimeo en texto plano (fuera de tags `<a>`) y las
    extrae como ExtraBlocks de tipo video_embed. Devuelve el HTML restante y
    los bloques que hay que emitir.

    Las URLs YT/Vimeo dentro de un `<a>...</a>` ya se procesaron como hyperlinks
    y se manejaron en `process_paragraph_inline`; aquí solo cubrimos las que
    aparecen como texto plano (caso típico: copiar y pegar la URL en el Word).
    """
    parts = re.split(r"(<a\s[^>]*>.*?</a>)", text_html, flags=re.IGNORECASE | re.DOTALL)
    extras: List[ExtraBlock] = []
    new_parts: List[str] = []
    for part in parts:
        if part.startswith("<a") or part.startswith("<A"):
            new_parts.append(part)
            continue
        # En este segmento sí podemos detectar URLs sueltas de YT/Vimeo
        def _hit(m: re.Match) -> str:
            url = m.group(0)
            href = url if url.startswith(("http://", "https://")) else f"https://{url}"
            extras.append(ExtraBlock(
                type="video_embed",
                src=href,
                caption="Vídeo",
            ))
            return ""  # eliminar la URL del texto, el reproductor irá aparte

        # Solo URLs YT/Vimeo (no cualquier URL)
        yt_url_re = re.compile(
            r"\bhttps?://(?:www\.)?(?:youtube\.com/(?:watch\?v=|shorts/|embed/)[A-Za-z0-9_\-]+"
            r"(?:[?&][^\s<>\"\)\]]*)?"
            r"|youtu\.be/[A-Za-z0-9_\-]+(?:\?[^\s<>\"\)\]]*)?"
            r"|vimeo\.com/\d+(?:[/?][^\s<>\"\)\]]*)?)",
            re.IGNORECASE,
        )
        new_parts.append(yt_url_re.sub(_hit, part))
    return "".join(new_parts), extras


def process_paragraph_inline(
    p,
    doc,
    extractor: Optional[ImageExtractor] = None,
) -> Tuple[str, List[ExtraBlock]]:
    """Convierte un párrafo Word en HTML inline + bloques extra."""
    html_parts: List[str] = []
    extras: List[ExtraBlock] = []
    p_el = p._p

    for child in p_el:
        tag = child.tag.split("}")[-1]

        if tag == "r":
            if extractor is not None:
                img_filename = _extract_drawing_image(child, extractor)
                if img_filename:
                    alt = _drawing_alt_text(child)
                    extras.append(ExtraBlock(
                        type="image",
                        src=img_filename,
                        caption=alt,
                    ))
                    continue
            html_parts.append(_run_text_html(child))

        elif tag == "hyperlink":
            url = ""
            rid = child.get(f"{R}id")
            if rid:
                try:
                    rel = doc.part.rels[rid]
                    url = rel.target_ref or ""
                except KeyError:
                    url = ""
            if not url:
                anchor = child.get(f"{W}anchor")
                if anchor:
                    inner = "".join(_run_text_html(r) for r in child if r.tag == f"{W}r")
                    html_parts.append(inner)
                    continue

            inner_parts = []
            for r in child:
                if r.tag == f"{W}r":
                    if extractor is not None:
                        img_filename = _extract_drawing_image(r, extractor)
                        if img_filename:
                            alt = _drawing_alt_text(r) or url
                            extras.append(ExtraBlock(
                                type="image",
                                src=img_filename,
                                caption=alt,
                                extras={"link": url},
                            ))
                            continue
                    inner_parts.append(_run_text_html(r))
            inner_html = "".join(inner_parts).strip()

            if is_video_url(url):
                clean_caption = _strip_inline_tags(inner_html) if inner_html else "Vídeo"
                extras.append(ExtraBlock(
                    type="video_embed",
                    src=url,
                    caption=clean_caption,
                ))
                continue

            if url and inner_html:
                safe_url = html.escape(url, quote=True)
                html_parts.append(
                    f'<a href="{safe_url}" target="_blank" rel="noopener">{inner_html}</a>'
                )
            elif inner_html:
                html_parts.append(inner_html)

        else:
            for r in child.iter(f"{W}r"):
                html_parts.append(_run_text_html(r))

    raw_html = "".join(html_parts)
    # 1) Extraer URLs sueltas de YouTube/Vimeo como ExtraBlock
    raw_html, plain_video_extras = _extract_plain_video_urls(raw_html)
    extras.extend(plain_video_extras)
    # 2) Autolinkar URLs restantes
    linked = _autolink(raw_html)
    return linked, extras


def get_plain_text(p) -> str:
    """Texto plano del párrafo (sin formato). Se usa para detección de headings,
    patrones, prefijos `[CLAVE]`, etc. Equivalente al antiguo `p.text` pero
    consistente con cómo trataremos `<w:hyperlink>`."""
    parts = []
    for child in p._p:
        tag = child.tag.split("}")[-1]
        if tag == "r":
            for t in child.iter(f"{W}t"):
                parts.append(t.text or "")
        elif tag == "hyperlink":
            for t in child.iter(f"{W}t"):
                parts.append(t.text or "")
        else:
            for t in child.iter(f"{W}t"):
                parts.append(t.text or "")
    return "".join(parts)

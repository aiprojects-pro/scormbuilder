"""Generador de PDF descargable a partir de un tema.

v0.6: cambios mayores
  - Registra fuentes Unicode (DejaVuSans) con fallback a Helvetica si no
    están disponibles. Soluciona los acentos rotos (á, é, í, ó, ú, ñ, ¿, ¡).
  - Soporta bloques IMAGE: incluye la imagen real en el PDF.
  - Tablas con colores del theme (no hardcoded). Cabecera con fondo claro
    primary_pale y texto oscuro primary_deep para legibilidad.
  - Acepta `recursos_dir` para resolver imágenes referenciadas.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List, Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor, white
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle,
    Image as RLImage, KeepTogether,
)
from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY, TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from scorm_builder.parser import (
    CourseStructure, Topic, Subsection, Block, BlockType,
)
from scorm_builder.themes import Theme

logger = logging.getLogger(__name__)


# ============================================================
# REGISTRO DE FUENTES UNICODE
# ============================================================

_FONTS_REGISTERED = False
_FONT_REGULAR = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"
_FONT_ITALIC = "Helvetica-Oblique"
_FONT_BOLDITALIC = "Helvetica-BoldOblique"


def _find_font(candidates: List[str]) -> Optional[str]:
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _register_unicode_fonts() -> None:
    """Registra fuentes con soporte Unicode. Idempotente.

    v0.8.2: BUG FIX — en UBI9/RHEL9, el paquete `dejavu-sans-fonts` instala
    los TTFs en `/usr/share/fonts/dejavu-sans-fonts/` (no en `/dejavu/`),
    así que buscábamos en la ruta equivocada y caíamos a Helvetica → los
    acentos se renderizaban como ■. Ahora hacemos una búsqueda RECURSIVA
    en /usr/share/fonts y rutas similares para no depender del nombre
    exacto del directorio que use cada distribución.
    """
    global _FONTS_REGISTERED, _FONT_REGULAR, _FONT_BOLD, _FONT_ITALIC, _FONT_BOLDITALIC
    if _FONTS_REGISTERED:
        return

    common_roots = [
        "/usr/share/fonts",                # Linux (RHEL, Debian, Arch...)
        "/usr/local/share/fonts",          # Linux custom
        "/Library/Fonts",                  # macOS
        "/System/Library/Fonts",           # macOS sistema
        "/System/Library/Fonts/Supplemental",  # macOS Catalina+
        "C:\\Windows\\Fonts",              # Windows
    ]
    # Búsqueda recursiva: encontramos los TTF de DejaVu/Liberation/Noto
    # sin importar en qué subdirectorio específico viva el paquete.
    target_names = {
        "regular":    ["DejaVuSans.ttf", "LiberationSans-Regular.ttf",
                       "NotoSans-Regular.ttf", "Arial.ttf", "arial.ttf"],
        "bold":       ["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf",
                       "NotoSans-Bold.ttf", "arialbd.ttf"],
        "italic":     ["DejaVuSans-Oblique.ttf", "LiberationSans-Italic.ttf",
                       "NotoSans-Italic.ttf", "ariali.ttf"],
        "bolditalic": ["DejaVuSans-BoldOblique.ttf", "LiberationSans-BoldItalic.ttf",
                       "NotoSans-BoldItalic.ttf", "arialbi.ttf"],
    }
    found = {"regular": None, "bold": None, "italic": None, "bolditalic": None}

    for root in common_roots:
        if not os.path.isdir(root):
            continue
        try:
            for dirpath, _dirs, files in os.walk(root):
                file_set = set(files)
                for variant, names in target_names.items():
                    if found[variant]:
                        continue
                    for name in names:
                        if name in file_set:
                            found[variant] = os.path.join(dirpath, name)
                            break
                if all(found.values()):
                    break
        except OSError:
            continue
        if all(found.values()):
            break

    fr = found["regular"]
    fb = found["bold"]
    fi = found["italic"]
    fbi = found["bolditalic"]

    if fr:
        try:
            pdfmetrics.registerFont(TTFont("BodyFont", fr))
            _FONT_REGULAR = "BodyFont"
            if fb:
                pdfmetrics.registerFont(TTFont("BodyFont-Bold", fb))
                _FONT_BOLD = "BodyFont-Bold"
            else:
                _FONT_BOLD = "BodyFont"
            if fi:
                pdfmetrics.registerFont(TTFont("BodyFont-Italic", fi))
                _FONT_ITALIC = "BodyFont-Italic"
            else:
                _FONT_ITALIC = "BodyFont"
            if fbi:
                pdfmetrics.registerFont(TTFont("BodyFont-BoldItalic", fbi))
                _FONT_BOLDITALIC = "BodyFont-BoldItalic"
            else:
                _FONT_BOLDITALIC = _FONT_BOLD

            from reportlab.pdfbase.pdfmetrics import registerFontFamily
            registerFontFamily(
                "BodyFont",
                normal="BodyFont",
                bold=_FONT_BOLD,
                italic=_FONT_ITALIC,
                boldItalic=_FONT_BOLDITALIC,
            )
            logger.info(f"Fuentes Unicode registradas desde {fr}")
        except Exception as e:
            logger.warning(f"Error registrando fuentes Unicode: {e}. Usando Helvetica.")
    else:
        logger.warning("No se encontraron fuentes Unicode. Los acentos pueden no renderizarse.")

    _FONTS_REGISTERED = True


# ============================================================
# UTILIDADES
# ============================================================

def _strip_html_for_pdf(text: str) -> str:
    """Limpia HTML inline para reportlab (mantiene <b>, <i>, <a> con atributos válidos).

    v0.6.1: reportlab paraparser solo acepta un conjunto limitado de atributos.
    Eliminamos los que no soporta (rel, target, class, style, data-*, etc.)
    aunque vengan dentro de <a>, <b>, etc. Si no, paraparser tira con
    "invalid attribute name rel".

    Atributos soportados por reportlab en <a>: href, name, color, fontname,
    fontsize, underline, etc. Eliminamos todo lo demás.
    """
    if not text:
        return ""
    import re
    s = re.sub(r"<strong\b[^>]*>", "<b>", text)
    s = re.sub(r"</strong>", "</b>", s)
    s = re.sub(r"<em\b[^>]*>", "<i>", s)
    s = re.sub(r"</em>", "</i>", s)
    s = re.sub(r"</?(span|p|div|figure|figcaption|cite|small|article|section)[^>]*>", "", s)

    # Limpiar atributos no soportados por reportlab dentro de cualquier tag.
    # Tags válidos para reportlab Paragraph: a, b, i, u, br, font, sub, sup
    # Atributos válidos en <a>: href, name, color, fontname, fontsize,
    #   underline, underlineColor, underlineGap, underlineKind, etc.
    # NO soportados: rel, target, class, style, id, data-*, onclick, etc.
    _UNSUPPORTED_ATTRS = {
        "rel", "target", "class", "style", "id",
        "aria-label", "aria-labelledby", "aria-describedby",
        "role", "title", "lang", "tabindex",
    }

    def _clean_tag(m):
        full = m.group(0)
        # Caer si es cierre </tag>
        if full.startswith("</"):
            return full
        # Encontrar el nombre del tag
        tag_match = re.match(r"<(\w+)(.*)>", full, re.DOTALL)
        if not tag_match:
            return full
        tag_name = tag_match.group(1)
        attrs_str = tag_match.group(2)
        # Conservar solo atributos válidos
        # Match: name="value" o name='value' o name=value (sin comillas)
        attr_pattern = re.compile(
            r'(\w[\w\-:]*)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|(\S+))'
        )
        kept = []
        for m2 in attr_pattern.finditer(attrs_str):
            name = m2.group(1).lower()
            # data-* y aria-* nunca soportados
            if name.startswith(("data-", "aria-")) or name in _UNSUPPORTED_ATTRS:
                continue
            val = m2.group(2) or m2.group(3) or m2.group(4) or ""
            # Escapar comillas en el valor
            val = val.replace('"', "&quot;")
            kept.append(f'{name}="{val}"')
        if kept:
            return f"<{tag_name} " + " ".join(kept) + ">"
        return f"<{tag_name}>"

    s = re.sub(r"<\w+[^>]*>", _clean_tag, s)
    # NBSP a espacio normal (reportlab parser tampoco le gusta a veces)
    s = s.replace("\xa0", " ")
    return s


def _compute_image_tint(theme) -> Optional[tuple]:
    """v0.8.2: calcula (hue_rotate_deg, saturate_factor) para retintar
    imágenes del DOCX hacia la paleta del tema. Misma lógica que
    `renderer._image_tint_css` para que SCORM y PDF salgan parecidos.

    Returns:
        (rotate_deg: int, sat_factor: float) o None si no procede tintar
        (paleta inválida o gris puro).
    """
    primary = (getattr(theme, "primary", "") or "").lstrip("#")
    if len(primary) != 6:
        return None
    try:
        r = int(primary[0:2], 16) / 255.0
        g = int(primary[2:4], 16) / 255.0
        b = int(primary[4:6], 16) / 255.0
    except ValueError:
        return None
    mx, mn = max(r, g, b), min(r, g, b)
    if mx == mn:
        return None
    if mx == r:
        h = ((g - b) / (mx - mn)) % 6
    elif mx == g:
        h = (b - r) / (mx - mn) + 2
    else:
        h = (r - g) / (mx - mn) + 4
    h_deg = round(h * 60)
    l = (mx + mn) / 2.0
    s = (mx - mn) / (1 - abs(2 * l - 1)) if l not in (0, 1) else 0
    rotate = (h_deg - 220) % 360  # DOCX azul base 220
    if rotate > 180:
        rotate -= 360
    sat_factor = max(0.5, min(1.8, s * 1.6 + 0.5))
    return rotate, sat_factor


def _retint_image_for_palette(img_path: Path, theme, cache_dir: Path) -> Path:
    """v0.8.2: aplica hue-rotate + saturate a una imagen vía Pillow.
    Guarda el resultado en `cache_dir` con sufijo `.tinted.png` y devuelve
    la nueva ruta. Si Pillow no está disponible o la imagen no es procesable,
    devuelve la ruta original sin tocar.

    El retintado se hace UNA VEZ por imagen+tema (se cachea por nombre).
    """
    tint = _compute_image_tint(theme)
    if tint is None:
        return img_path
    rotate_deg, sat_factor = tint
    try:
        from PIL import Image
        import colorsys
    except ImportError:
        return img_path
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        tinted_path = cache_dir / f"{img_path.stem}__tint_{rotate_deg}_{int(sat_factor*100)}.png"
        if tinted_path.exists():
            return tinted_path
        im = Image.open(img_path).convert("RGBA")
        pixels = im.load()
        w, h = im.size
        rot_norm = (rotate_deg % 360) / 360.0
        for y in range(h):
            for x in range(w):
                pr, pg, pb, pa = pixels[x, y]
                if pa == 0:
                    continue
                # RGB → HSV
                ph, ps, pv = colorsys.rgb_to_hsv(pr/255.0, pg/255.0, pb/255.0)
                # Rotar hue + ajustar saturación
                ph = (ph + rot_norm) % 1.0
                ps = max(0.0, min(1.0, ps * sat_factor))
                # HSV → RGB
                nr, ng, nb = colorsys.hsv_to_rgb(ph, ps, pv)
                pixels[x, y] = (int(nr*255), int(ng*255), int(nb*255), pa)
        im.save(tinted_path, format="PNG", optimize=True)
        return tinted_path
    except Exception as e:
        logger.warning(f"No se pudo retintar imagen {img_path.name}: {e}")
        return img_path


def _resolve_image_path(src: str, recursos_dir: Optional[Path]) -> Optional[Path]:
    """Resuelve la ruta real de una imagen para incluirla en el PDF.

    SEC: cuando se busca dentro de `recursos_dir`, se valida que la ruta
    resuelta esté efectivamente DENTRO de ese directorio (anti path-traversal
    vía `src = "recursos/../../etc/passwd.png"`).
    """
    if not src:
        return None
    if src.startswith(("http://", "https://", "data:")):
        return None
    p = Path(src)
    if p.is_absolute() and p.exists():
        return p
    if recursos_dir:
        base = Path(recursos_dir).resolve()
        # Caso 1: usar solo el basename (siempre seguro: Path.name strip rutas).
        candidate = (base / p.name).resolve()
        try:
            candidate.relative_to(base)
        except ValueError:
            candidate = None  # fuera de recursos_dir, descartar
        if candidate is not None and candidate.exists():
            return candidate
        # Caso 2: prefijo "recursos/...". Resolvemos y comprobamos containment.
        if src.startswith("recursos/"):
            inner = src.replace("recursos/", "", 1)
            candidate = (base / inner).resolve()
            try:
                candidate.relative_to(base)
            except ValueError:
                return None
            if candidate.exists():
                return candidate
    return None


# ============================================================
# CONVERSIÓN DE BLOQUES
# ============================================================

def _block_to_elements(
    block: Block, styles: dict, theme: Theme, recursos_dir: Optional[Path],
    available_width: float,
) -> List:
    out = []
    bt = block.type
    if isinstance(bt, str):
        bt = BlockType(bt)

    def _text(b):
        s = b.text_html if b.text_html else b.text
        return _strip_html_for_pdf(s or "")

    def _items(b):
        if b.items_html and len(b.items_html) == len(b.items):
            return [_strip_html_for_pdf(it) for it in b.items_html]
        return [_strip_html_for_pdf(it) for it in (b.items or [])]

    if bt == BlockType.PARAGRAPH:
        out.append(Paragraph(_text(block), styles["body"]))
    elif bt == BlockType.HEADING_3:
        out.append(Paragraph(_text(block), styles["h3"]))
    elif bt == BlockType.HEADING_4:
        out.append(Paragraph(_text(block), styles["h4"]))
    elif bt == BlockType.LIST_BULLET:
        for it in _items(block):
            out.append(Paragraph("• " + it, styles["li"]))
    elif bt == BlockType.LIST_NUMBER:
        for i, it in enumerate(_items(block), 1):
            out.append(Paragraph(f"{i}. {it}", styles["li"]))
    elif bt in (BlockType.CALLOUT_KEY, BlockType.CALLOUT_ALERT, BlockType.CALLOUT_SUCCESS, BlockType.CALLOUT_WARN):
        prefix = {
            BlockType.CALLOUT_KEY: "★ ",
            BlockType.CALLOUT_ALERT: "⚠ ",
            BlockType.CALLOUT_SUCCESS: "✓ ",
            BlockType.CALLOUT_WARN: "! ",
        }[bt]
        out.append(Paragraph(prefix + "<b>" + _text(block) + "</b>", styles["callout"]))
    elif bt == BlockType.QUOTE:
        out.append(Paragraph("<i>" + _text(block) + "</i>", styles["quote"]))
    elif bt == BlockType.EXAMPLE:
        out.append(Paragraph("<b>Ejemplo: </b>" + _text(block), styles["example"]))
    elif bt == BlockType.IMAGE:
        src = (block.extras or {}).get("src", "") or (block.extras or {}).get("file", "")
        img_path = _resolve_image_path(src, recursos_dir)
        if img_path:
            # v0.8.2: retintar la imagen hacia la paleta del tema (la misma
            # transformación que aplica el SCORM vía hue-rotate + saturate).
            # Cachea el resultado en `recursos/_tinted/` para no rehacer
            # el procesamiento en sucesivas generaciones del PDF.
            no_tint = bool((block.extras or {}).get("no_tint"))
            if not no_tint and recursos_dir:
                cache_dir = Path(recursos_dir) / "_tinted"
                img_path = _retint_image_for_palette(img_path, theme, cache_dir)
            try:
                from PIL import Image as PILImage
                with PILImage.open(img_path) as im:
                    iw, ih = im.size
                # v0.6.1: ancho máximo lógico = 85% del available para que
                # las imágenes nunca toquen los bordes laterales (visualmente
                # mejor y deja margen de respiración).
                max_w = available_width * 0.85
                max_h = 15 * cm
                # Asumimos imágenes a ~96 dpi del docx
                px_per_pt = 96 / 72
                native_pt_w = iw / px_per_pt
                native_pt_h = ih / px_per_pt
                if native_pt_w > max_w or native_pt_h > max_h:
                    # Downscale para caber
                    ratio = min(max_w / native_pt_w, max_h / native_pt_h)
                    w = native_pt_w * ratio
                    h = native_pt_h * ratio
                else:
                    # Cabe nativo. Si es demasiado pequeña, ampliar al 60%.
                    w = native_pt_w
                    h = native_pt_h
                    min_w = available_width * 0.6
                    if w < min_w:
                        scale = min(min_w / w, max_w / w, max_h / h)
                        w *= scale
                        h *= scale
                img_flow = RLImage(str(img_path), width=w, height=h)
                img_flow.hAlign = "CENTER"
                cap = block.text or ""
                if cap:
                    caption = Paragraph(f"<i>{_strip_html_for_pdf(cap)}</i>", styles["caption"])
                    out.append(KeepTogether([img_flow, Spacer(1, 0.15 * cm), caption]))
                else:
                    out.append(img_flow)
                    out.append(Spacer(1, 0.2 * cm))
            except Exception as e:
                logger.warning(f"No se pudo incluir imagen '{src}' en PDF: {e}")
                out.append(Paragraph(
                    f"<i>[Imagen no incluida: {_strip_html_for_pdf(block.text or src)}]</i>",
                    styles["caption"],
                ))
        else:
            label = block.text or src or "imagen"
            out.append(Paragraph(
                f"<i>[Imagen externa: {_strip_html_for_pdf(label)}]</i>",
                styles["caption"],
            ))
    elif bt == BlockType.VIDEO:
        src = (block.extras or {}).get("src", "")
        label = block.text or "Vídeo del tema"
        out.append(Paragraph(
            f"▶ <b>Vídeo:</b> {_strip_html_for_pdf(label)}"
            + (f' <i>({_strip_html_for_pdf(src)})</i>' if src else ""),
            styles["callout"],
        ))
    elif bt == BlockType.AUDIO:
        src = (block.extras or {}).get("src", "")
        label = block.text or "Audio del tema"
        out.append(Paragraph(
            f"🔊 <b>Audio:</b> {_strip_html_for_pdf(label)}"
            + (f' <i>({_strip_html_for_pdf(src)})</i>' if src else ""),
            styles["callout"],
        ))
    elif bt == BlockType.EMBED:
        src = (block.extras or {}).get("src", "")
        label = block.text or "Recurso embebido"
        out.append(Paragraph(
            f"<b>Recurso interactivo:</b> {_strip_html_for_pdf(label)}"
            + (f' <i>({_strip_html_for_pdf(src)})</i>' if src else ""),
            styles["callout"],
        ))
    elif bt == BlockType.TABLE:
        if block.rows:
            out.append(_build_table(block, theme, styles, available_width))
            out.append(Spacer(1, 0.3 * cm))

    return out


def _force_word_break(text: str, max_word_len: int = 30) -> str:
    """Inserta puntos de ruptura en palabras larguísimas (URLs, identificadores).

    ReportLab Paragraph no rompe palabras sin espacios y eso desborda la celda.
    Inserta espacio de ancho cero (ZWSP \\u200b) cada `max_word_len` caracteres
    en palabras que excedan ese tamaño. Preserva tags HTML inline (<b>, <i>, <a>).
    """
    if not text:
        return text
    import re

    def break_token(m):
        token = m.group(0)
        if len(token) <= max_word_len:
            return token
        # Insertar ZWSP cada `max_word_len` chars
        out = []
        for i in range(0, len(token), max_word_len):
            out.append(token[i:i + max_word_len])
        return "\u200b".join(out)

    # Separar en tags HTML y texto. Solo aplicar a texto fuera de tags.
    parts = re.split(r'(<[^>]+>)', text)
    for i, p in enumerate(parts):
        if p.startswith("<"):
            continue
        # Tokenizar por espacios y procesar cada palabra
        parts[i] = re.sub(r'\S+', break_token, p)
    return "".join(parts)


def _build_table(block: Block, theme: Theme, styles: dict, available_width: float):
    """Construye una tabla con los colores del theme y accesibilidad.

    v0.6: defensiva contra desbordes:
      - palabras larguísimas (URLs) reciben ZWSP cada 30 chars
      - colWidths siempre suman <= available_width (escalado si excede)
      - splitByRow=True para que tablas largas se partan entre páginas
      - LongTable cuando hay > 12 filas, por rendimiento
    """
    from reportlab.platypus import LongTable

    rows = block.rows_html if (block.rows_html and len(block.rows_html) == len(block.rows)) else block.rows
    if not rows:
        return Spacer(1, 0)

    cell_style = styles["table_cell"]
    head_style = styles["table_head"]

    import re as _re
    def _plain_len(c):
        s = c if isinstance(c, str) else str(c)
        return len(_re.sub(r"<[^>]+>", "", s).strip())
    first_col_is_header = (
        len(rows) > 1
        and all(row and _plain_len(row[0]) > 0 and _plain_len(row[0]) <= 80 for row in rows[1:])
    )

    data = []
    for ri, row in enumerate(rows):
        new_row = []
        for ci, cell in enumerate(row):
            raw = cell if isinstance(cell, str) else str(cell)
            txt = _strip_html_for_pdf(raw)
            # Romper palabras larguísimas para que no se salgan de la celda
            txt = _force_word_break(txt, max_word_len=30)
            if ri == 0 or (ci == 0 and first_col_is_header):
                new_row.append(Paragraph(f"<b>{txt}</b>", head_style))
            else:
                new_row.append(Paragraph(txt, cell_style))
        data.append(new_row)

    n_cols = len(rows[0])
    if first_col_is_header and n_cols > 1:
        first_col_w = available_width * 0.28
        rest_w = (available_width - first_col_w) / (n_cols - 1)
        col_widths = [first_col_w] + [rest_w] * (n_cols - 1)
    else:
        col_widths = [available_width / n_cols] * n_cols

    # Defensiva: asegurar que la suma cabe en available_width
    total = sum(col_widths)
    if total > available_width:
        factor = available_width / total
        col_widths = [w * factor for w in col_widths]

    # Elegir tabla normal o LongTable según número de filas
    TableCls = LongTable if len(rows) > 12 else Table
    t = TableCls(data, colWidths=col_widths, repeatRows=1, splitByRow=True)

    primary_pale = HexColor(theme.primary_pale)
    primary_mist = HexColor(theme.primary_mist)
    primary_deep = HexColor(theme.primary_deep)
    primary = HexColor(theme.primary)
    paper_warm = HexColor(theme.paper_warm)
    paper_deep = HexColor(theme.paper_deep)
    ink = HexColor(theme.ink)

    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), primary_pale),
        ("TEXTCOLOR", (0, 0), (-1, 0), primary_deep),
        ("LINEBELOW", (0, 0), (-1, 0), 1.5, primary),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.3, paper_deep),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TEXTCOLOR", (0, 1), (-1, -1), ink),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#FFFFFF"), paper_warm]),
    ]
    if first_col_is_header:
        style_cmds.append(("BACKGROUND", (0, 1), (0, -1), primary_mist))
        style_cmds.append(("TEXTCOLOR", (0, 1), (0, -1), primary_deep))
        style_cmds.append(("LINEAFTER", (0, 0), (0, -1), 1, paper_deep))

    t.setStyle(TableStyle(style_cmds))
    t.hAlign = "LEFT"
    return t


# ============================================================
# ESTILOS
# ============================================================

def _make_styles(theme: Theme):
    _register_unicode_fonts()
    primary_deep = HexColor(theme.primary_deep)
    primary = HexColor(theme.primary)
    ink = HexColor(theme.ink)
    ink_soft = HexColor(theme.ink_soft)
    paper_warm = HexColor(theme.paper_warm)

    base = getSampleStyleSheet()

    return {
        "h1": ParagraphStyle("h1", parent=base["Heading1"],
            fontSize=22, leading=26, textColor=primary_deep,
            spaceAfter=18, fontName=_FONT_BOLD),
        "h2": ParagraphStyle("h2", parent=base["Heading2"],
            fontSize=15, leading=18, textColor=primary,
            spaceAfter=10, spaceBefore=18, fontName=_FONT_BOLD),
        "h3": ParagraphStyle("h3", parent=base["Heading3"],
            fontSize=12, leading=15, textColor=ink,
            spaceAfter=6, spaceBefore=10, fontName=_FONT_BOLD),
        "h4": ParagraphStyle("h4", parent=base["Heading4"],
            fontSize=10, leading=13, textColor=primary_deep,
            spaceAfter=4, spaceBefore=8, fontName=_FONT_BOLD),
        "body": ParagraphStyle("body", parent=base["Normal"],
            fontSize=10.5, leading=15, textColor=ink_soft,
            alignment=TA_JUSTIFY, spaceAfter=8, fontName=_FONT_REGULAR),
        "lead": ParagraphStyle("lead", parent=base["Normal"],
            fontSize=11, leading=16, textColor=ink,
            alignment=TA_LEFT, leftIndent=10, fontName=_FONT_ITALIC,
            spaceAfter=12),
        "li": ParagraphStyle("li", parent=base["Normal"],
            fontSize=10.5, leading=14, textColor=ink_soft,
            alignment=TA_JUSTIFY, leftIndent=15, spaceAfter=4,
            fontName=_FONT_REGULAR),
        "callout": ParagraphStyle("callout", parent=base["Normal"],
            fontSize=10.5, leading=14, textColor=ink,
            backColor=paper_warm, borderColor=primary, borderWidth=0,
            leftIndent=10, rightIndent=10, borderPadding=8,
            spaceAfter=10, spaceBefore=10, fontName=_FONT_REGULAR),
        "example": ParagraphStyle("example", parent=base["Normal"],
            fontSize=10.5, leading=14, textColor=ink,
            backColor=HexColor(theme.primary_mist),
            leftIndent=10, rightIndent=10, borderPadding=8,
            spaceAfter=10, spaceBefore=10, fontName=_FONT_REGULAR),
        "quote": ParagraphStyle("quote", parent=base["Normal"],
            fontSize=10, leading=14, textColor=ink,
            leftIndent=20, rightIndent=20, fontName=_FONT_ITALIC,
            spaceAfter=10),
        "caption": ParagraphStyle("caption", parent=base["Normal"],
            fontSize=9, leading=11, textColor=ink_soft,
            alignment=TA_CENTER, fontName=_FONT_ITALIC,
            spaceAfter=12, spaceBefore=2),
        "table_head": ParagraphStyle("table_head", parent=base["Normal"],
            fontSize=9.5, leading=12, textColor=primary_deep,
            fontName=_FONT_BOLD, alignment=TA_LEFT),
        "table_cell": ParagraphStyle("table_cell", parent=base["Normal"],
            fontSize=9.5, leading=12, textColor=ink,
            fontName=_FONT_REGULAR, alignment=TA_LEFT),
    }


def _clean_course_title(title: str) -> str:
    """v0.8.3: quita el sufijo '(N unidades)' del título del curso para que
    los PDFs/SCORMs sirvan tanto si se sube el curso entero como en tandas.

    Ejemplos:
        'Ejecución, Control y Evaluación (6 unidades)' → 'Ejecución, Control y Evaluación'
        'Curso de Calidad (3 Unidades)'                → 'Curso de Calidad'
        'Mi Curso'                                      → 'Mi Curso'  (sin cambios)
    """
    if not title:
        return title
    import re as _re
    return _re.sub(r"\s*\(\s*\d+\s+unidades?\s*\)\s*$", "", title,
                   flags=_re.IGNORECASE).strip()


def _make_header_footer(course_title: str, topic_title: str, theme: Theme):
    primary_deep = HexColor(theme.primary_deep)
    accent = HexColor(theme.accent)
    ink = HexColor(theme.ink)

    # Truncado inteligente: si ambos textos son largos, recortar para que quepan
    # sin solaparse. Cada uno tiene como máximo la mitad menos un pequeño gap.
    # v0.8.3: terminamos en punto "." en lugar de elipsis "…" a petición del
    # cliente (más limpio en PDFs formativos).
    def _shorten(s: str, max_chars: int) -> str:
        s = (s or "").strip()
        if len(s) <= max_chars:
            return s
        return s[: max_chars - 1].rstrip().rstrip(",;:.") + "."

    course_short = _shorten(_clean_course_title(course_title), 45)
    topic_short = _shorten(topic_title, 45)

    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(primary_deep)
        canvas.rect(0, A4[1] - 1.5 * cm, A4[0], 1.5 * cm, fill=1, stroke=0)
        canvas.setFillColor(white)
        canvas.setFont(_FONT_BOLD, 9)
        # FIX: solo mostramos el título del curso a la izquierda. Antes había
        # `drawRightString(... topic_short)` a la derecha que duplicaba el
        # título del tema con el que ya aparece grande en la portada y en
        # cada cabecera de sección (h2). El topic_short queda comentado por
        # si se necesita reactivar en el futuro.
        canvas.drawString(2 * cm, A4[1] - 1 * cm, course_short)
        canvas.setFillColor(ink)
        canvas.setFont(_FONT_REGULAR, 8)
        canvas.drawString(2 * cm, 1.2 * cm, f"Página {doc.page}")
        canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, "Apuntes del tema")
        canvas.setStrokeColor(accent)
        canvas.setLineWidth(0.5)
        canvas.line(2 * cm, 1.6 * cm, A4[0] - 2 * cm, 1.6 * cm)
        canvas.restoreState()
    return draw


def build_pdf(
    topic: Topic,
    course: CourseStructure,
    theme: Theme,
    output_path: Path,
    recursos_dir: Optional[Path] = None,
) -> Path:
    """Genera un PDF de apuntes del tema.

    v0.6: añade `recursos_dir` para resolver imágenes embebidas.
    """
    _register_unicode_fonts()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    styles = _make_styles(theme)
    available_width = A4[0] - 4 * cm

    story = []

    # Portada
    story.append(Spacer(1, 4 * cm))
    # v0.8.3: limpiar "(N unidades)" del título antes de mostrarlo.
    _clean_title = _clean_course_title(course.metadata.title)
    story.append(Paragraph(_strip_html_for_pdf(_clean_title), styles["h1"]))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(
        f"<b>Tema {topic.number}:</b> {_strip_html_for_pdf(topic.title)}",
        styles["h2"],
    ))
    story.append(Spacer(1, 1 * cm))
    if topic.intro:
        story.append(Paragraph(_strip_html_for_pdf(topic.intro), styles["lead"]))
    story.append(Spacer(1, 1 * cm))
    if course.metadata.author:
        story.append(Paragraph(
            f"<b>Autor/entidad:</b> {_strip_html_for_pdf(course.metadata.author)}",
            styles["body"],
        ))
    # v0.8.2: quitado el subtítulo "Apuntes de consulta del tema. Material
    # formativo complementario al curso e-learning." a petición del usuario.
    # La portada queda con título grande + intro + autor, sin esa línea.
    story.append(PageBreak())

    # Índice
    story.append(Paragraph("Índice del tema", styles["h1"]))
    for sub in topic.subsections:
        story.append(Paragraph(
            f"{sub.number} {_strip_html_for_pdf(sub.title)}",
            styles["body"],
        ))
    if topic.quiz:
        story.append(Paragraph(
            f"{topic.number}.{len(topic.subsections)+1} Evaluación final",
            styles["body"],
        ))
    story.append(PageBreak())

    # Contenido
    for sub in topic.subsections:
        story.append(Paragraph(
            f"{sub.number} {_strip_html_for_pdf(sub.title)}",
            styles["h2"],
        ))
        for block in sub.blocks:
            elements = _block_to_elements(block, styles, theme, recursos_dir, available_width)
            for el in elements:
                story.append(el)
        story.append(Spacer(1, 0.3 * cm))

    # Quiz
    if topic.quiz:
        story.append(PageBreak())
        story.append(Paragraph("Evaluación final", styles["h2"]))
        story.append(Paragraph(
            f"Total de preguntas: {len(topic.quiz)}. "
            f"Aprobado mínimo: {course.metadata.mastery}%.",
            styles["body"],
        ))
        for i, q in enumerate(topic.quiz, 1):
            story.append(Paragraph(
                f"<b>Pregunta {i}.</b> {_strip_html_for_pdf(q.text)}",
                styles["body"],
            ))
            for idx, opt in enumerate(q.options):
                letter = chr(ord("A") + idx)
                marker = "▶" if idx == q.correct_index else "○"
                story.append(Paragraph(
                    f"&nbsp;&nbsp;&nbsp;{marker} <b>{letter}.</b> {_strip_html_for_pdf(opt)}",
                    styles["li"],
                ))
            if q.explanation:
                story.append(Paragraph(
                    f"<i>Explicación: {_strip_html_for_pdf(q.explanation)}</i>",
                    styles["quote"],
                ))
            story.append(Spacer(1, 0.3 * cm))

    hf = _make_header_footer(course.metadata.title, topic.title, theme)
    doc = SimpleDocTemplate(
        str(output_path), pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2.3 * cm, bottomMargin=2 * cm,
        title=f"{_clean_title} · Tema {topic.number}",
        author=course.metadata.author or "Curso e-learning",
    )
    doc.build(story, onFirstPage=hf, onLaterPages=hf)

    return output_path

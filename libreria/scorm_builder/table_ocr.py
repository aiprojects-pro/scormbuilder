"""Detector de tablas en imágenes (v0.6).

Cuando una imagen del DOCX es en realidad una tabla pegada como imagen
(captura, exportación de Excel, etc.), este módulo:

  1. Detecta si la imagen contiene una estructura de tabla (líneas
     horizontales + verticales o "fila-strip" sin verticales claros).
  2. Si la detecta, ejecuta OCR sobre cada celda y devuelve una matriz
     filas × columnas con el texto.
  3. Devuelve también un score de confianza (0–100) para que el caller
     decida si confiar y sustituir la imagen por la tabla.

Dependencias: opencv-python, pytesseract, Pillow. Las tres están
instaladas en el entorno del SCORM Builder. Tesseract con paquete `spa`.

Importante: este módulo NO sustituye la imagen automáticamente. Devuelve
la propuesta de tabla; es el parser (o un endpoint manual) quien decide
si reemplaza o no, en función del score y del feedback del usuario.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# Umbrales (ajustables)
MIN_TABLE_CONFIDENCE = 55   # debajo de este score no se considera tabla
MIN_LINE_LENGTH_RATIO = 0.30  # una línea válida cubre >= 30% del ancho/alto
MIN_TEXT_CONFIDENCE = 35    # confianza tesseract mínima por palabra


@dataclass
class TableExtraction:
    """Resultado de extraer una tabla de una imagen."""
    is_table: bool                            # True si se detectó tabla
    confidence: int                           # 0–100 de seguridad global
    rows: List[List[str]] = field(default_factory=list)  # matriz texto
    n_rows: int = 0
    n_cols: int = 0
    notes: List[str] = field(default_factory=list)        # diagnóstico


def _safe_imports():
    """Importa dependencias y devuelve módulos o None."""
    try:
        import cv2
        import numpy as np
        import pytesseract
        return cv2, np, pytesseract
    except ImportError as e:
        logger.warning(f"Falta dependencia para OCR de tablas: {e}")
        return None, None, None


def _detect_grid_lines(gray, cv2, np) -> Tuple[List[int], List[int], dict]:
    """Detecta líneas horizontales y verticales en una imagen en escala de grises.

    Devuelve:
      h_lines: lista de coordenadas Y de cada línea horizontal detectada
      v_lines: lista de coordenadas X de cada línea vertical detectada
      info: dict con detalle de cómo se detectó
    """
    h, w = gray.shape
    info = {"h": h, "w": w}

    # v0.6.1: usar Otsu (threshold global) en vez de adaptive. El adaptive con
    # blockSize pequeño genera falsos positivos en zonas uniformes blancas.
    _, thr = cv2.threshold(gray, 0, 255,
                            cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Detectar líneas horizontales mediante apertura morfológica
    h_kernel_len = max(40, w // 20)
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_kernel_len, 1))
    h_morph = cv2.morphologyEx(thr, cv2.MORPH_OPEN, h_kernel, iterations=1)

    # Detectar líneas verticales
    v_kernel_len = max(40, h // 20)
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_kernel_len))
    v_morph = cv2.morphologyEx(thr, cv2.MORPH_OPEN, v_kernel, iterations=1)

    # Agrupar filas activas en líneas (centros). El threshold es ahora más
    # estricto: solo cuentan filas con >60% del ancho activo (línea continua).
    h_row_active = (h_morph > 0).sum(axis=1)
    h_threshold = max(w * 0.60, 80)
    h_active_rows = np.where(h_row_active >= h_threshold)[0]
    h_lines = _cluster_coords(h_active_rows.tolist(), gap=8)

    v_col_active = (v_morph > 0).sum(axis=0)
    v_threshold = max(h * 0.60, 80)
    v_active_cols = np.where(v_col_active >= v_threshold)[0]
    v_lines_raw = _cluster_coords(v_active_cols.tolist(), gap=8)

    # Filtrar v_lines que están en los bordes (< 3% del ancho) — esos son el
    # marco del recuadro azul típico, no separadores de columna reales.
    border_margin = max(5, int(w * 0.03))
    v_lines = [
        v for v in v_lines_raw
        if v > border_margin and v < (w - border_margin)
    ]

    # v0.6.3: fusionar v-lines internas muy próximas entre sí. Los bordes
    # redondeados de etiquetas/cabeceras crean varios fragmentos de línea
    # vertical separados por unos píxeles que el detector ve como columnas
    # diferentes. Identificamos clusters y para cada cluster nos quedamos
    # con la POSICIÓN MÁS A LA DERECHA, porque el separador real está al
    # final del cluster de "ruido visual" (bordes redondeados a la izquierda
    # del separador real).
    if len(v_lines) > 1:
        merge_threshold = max(int(w * 0.10), 15)
        clusters = [[v_lines[0]]]
        for v in v_lines[1:]:
            if v - clusters[-1][-1] < merge_threshold:
                clusters[-1].append(v)
            else:
                clusters.append([v])
        # Quedarse con la posición MÁS A LA DERECHA de cada cluster
        v_lines = [max(c) for c in clusters]

    # v0.6.3: filtro adicional para tablas con UNA SOLA v-line interna.
    # Si esa única línea está muy pegada a un lateral (<15% del ancho desde
    # cualquier borde), probablemente es un artefacto (cambio de fondo,
    # cabecera flotante, etc.), no una separadora real.
    if len(v_lines) == 1:
        single = v_lines[0]
        too_close_to_left = single < w * 0.15
        too_close_to_right = single > w * 0.85
        if too_close_to_left or too_close_to_right:
            v_lines = []

    # v0.6.3: si NO hay v-lines internas claras pero hay h-lines bien
    # separadas, intentar localizar la separadora vertical por "análisis de
    # valle de blancura". Útil para tablas tipo "etiqueta + descripción"
    # donde la línea separadora es muy fina o de color suave.
    if len(v_lines) == 0 and len(h_lines) >= 2:
        valley = _find_vertical_text_valley(gray, h_lines, cv2, np)
        if valley is not None:
            v_lines = [valley]
            info["valley_detected"] = valley

    info["h_lines_count"] = len(h_lines)
    info["v_lines_count_raw"] = len(v_lines_raw)
    info["v_lines_count_internal"] = len(v_lines)
    return h_lines, v_lines, info


def _find_vertical_text_valley(gray, h_lines, cv2, np):
    """Busca la separadora vertical entre dos columnas de texto.

    Estrategia:
      1. Restringir a la región dentro de las h_lines (sin cabeceras flotantes).
      2. Binarizar invirtiendo y proyectar verticalmente (suma por columna).
      3. Buscar el "valle" más amplio entre dos zonas con texto, situado
         entre el 12% y 65% del ancho (donde típicamente está la separadora
         entre columna de etiquetas y columna de descripción).
      4. VALIDAR FILA POR FILA: en una separadora real, la mayoría de las
         filas tienen texto a AMBOS lados del valle. En una falsa (espacio
         entre líneas alineado), las "filas" no tienen contenido coherente
         a uno de los dos lados.
      5. Devolver el centro del valle si pasa todas las validaciones; None si no.

    v0.6.4: validación fila a fila para evitar falsos positivos en tablas
    de una sola columna donde un espacio vertical entre líneas se confunde
    con separadora real.
    """
    try:
        h, w = gray.shape
        y1, y2 = min(h_lines), max(h_lines)
        if y2 - y1 < 30:
            return None
        roi = gray[y1:y2, :]

        _, bin_img = cv2.threshold(
            roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
        )
        col_density = (bin_img > 0).sum(axis=0)
        max_d = col_density.max()
        if max_d == 0:
            return None
        normalized = col_density / max_d

        lo = int(w * 0.12)
        hi = int(w * 0.65)
        if hi <= lo:
            return None

        # Buscar candidatos a valle con distintos thresholds.
        # Cada threshold tiene un rango MIN-MAX de ancho válido:
        #   - Estricto (0.05): valles de 8-40 px (separadora muy fina)
        #   - Medio    (0.10): valles de 18-40 px (separadora media)
        #   - Permisivo(0.15): valles de 25-40 px (separadora ancha)
        # Un valle >40 px probablemente es un margen vacío, no una separadora;
        # un valle <min(thr) es solo espacio entre palabras alineado.
        threshold_to_range = {
            0.05: (8, 40),
            0.10: (18, 40),
            0.15: (25, 40),
        }
        candidates = []
        for thr, (min_w, max_w) in threshold_to_range.items():
            is_empty = normalized < thr
            best_start, best_end, best_len = -1, -1, 0
            cur_start = -1
            for x in range(lo, hi):
                if is_empty[x]:
                    if cur_start == -1:
                        cur_start = x
                else:
                    if cur_start != -1:
                        run_len = x - cur_start
                        if run_len > best_len:
                            best_len = run_len
                            best_start = cur_start
                            best_end = x
                        cur_start = -1
            if cur_start != -1:
                run_len = hi - cur_start
                if run_len > best_len:
                    best_len = run_len
                    best_start = cur_start
                    best_end = hi
            if min_w <= best_len <= max_w:
                candidates.append((best_start, best_end, best_len, thr))

        if not candidates:
            return None

        # Para validar fila por fila necesitamos saber dónde están las filas
        # de la tabla. Usamos las h_lines pasadas (relativas a la imagen
        # completa), restando y1 para convertir a coordenadas de roi.
        row_bounds = []
        h_sorted = sorted(set(h_lines))
        for ri in range(len(h_sorted) - 1):
            ry1 = max(0, h_sorted[ri] - y1)
            ry2 = min(roi.shape[0], h_sorted[ri + 1] - y1)
            if ry2 - ry1 >= 15:
                row_bounds.append((ry1, ry2))

        # Si no hay suficientes filas para validar, descartar (no es tabla)
        if len(row_bounds) < 2:
            return None

        for best_start, best_end, best_len, thr in candidates:
            valley_center = (best_start + best_end) // 2

            # VALIDACIÓN 1: la franja del valle debe estar SIGNIFICATIVAMENTE
            # más vacía que el resto de la imagen. En un valle real (separadora
            # vertical entre columnas), la densidad de la franja es <60% de la
            # densidad media de la imagen. En un valle falso (espacio entre
            # palabras alineado en texto justificado), la densidad de la franja
            # se acerca a la media (>80%).
            valley_strip = bin_img[:, best_start:best_end]
            full_density = (bin_img > 0).mean()
            if valley_strip.size == 0 or full_density == 0:
                continue
            strip_density = (valley_strip > 0).mean()
            ratio_to_full = strip_density / full_density
            if ratio_to_full > 0.6:
                continue  # la franja no está suficientemente vacía: valle falso

            # VALIDACIÓN 2: fila por fila, la mayoría debe tener texto a ambos
            # lados del valle (separadora real conecta dos columnas reales).
            rows_with_both = 0
            rows_total = 0
            for ry1, ry2 in row_bounds:
                row_strip = bin_img[ry1:ry2, :]
                if row_strip.size == 0:
                    continue
                left_pixels = (row_strip[:, :valley_center] > 0).sum()
                right_pixels = (row_strip[:, valley_center:] > 0).sum()
                left_area = row_strip[:, :valley_center].size
                right_area = row_strip[:, valley_center:].size
                has_left = left_area > 0 and (left_pixels / left_area) > 0.015
                has_right = right_area > 0 and (right_pixels / right_area) > 0.015
                rows_total += 1
                if has_left and has_right:
                    rows_with_both += 1

            if rows_total == 0:
                continue
            both_ratio = rows_with_both / rows_total
            if both_ratio < 0.7:
                continue

            # VALIDACIÓN 3: la columna izquierda no debe estar vacía
            left_zone = bin_img[:, :valley_center]
            if left_zone.size == 0:
                continue
            left_density = (left_zone > 0).mean()
            if left_density < 0.02:
                continue

            return valley_center

        return None
    except Exception:
        return None


def _cluster_coords(coords: List[int], gap: int = 3) -> List[int]:
    """Agrupa coordenadas próximas (dentro de `gap`) y devuelve sus centros."""
    if not coords:
        return []
    coords = sorted(coords)
    clusters = [[coords[0]]]
    for c in coords[1:]:
        if c - clusters[-1][-1] <= gap:
            clusters[-1].append(c)
        else:
            clusters.append([c])
    return [sum(c) // len(c) for c in clusters]


def _ocr_cell(cell_img, pytesseract, lang: str = "spa") -> str:
    """OCR de una celda. Devuelve el texto limpio.

    v0.6.3: añadido recorte por bounding-box del texto antes del OCR.

    Pipeline:
      1. Detectar bounding box del texto dentro de la celda (descartar blancos
         laterales/superiores enormes). Esto resuelve el caso de etiquetas
         laterales tipo "REQUISITO KO Nº8 DE IFS FOOD" centradas en celdas
         altas con mucho espacio blanco.
      2. Añadir padding blanco (10px) — ayuda a tesseract con bordes.
      3. Upscale adaptativo: 3x si la celda recortada es <200px, 2x si <400px.
      4. Binarización Otsu solo si la imagen no es ya casi binaria.
      5. Tesseract --psm 6 (bloque uniforme de texto).
    """
    try:
        import cv2 as _cv2
        import numpy as _np
        h, w = cell_img.shape[:2]
        if w == 0 or h == 0:
            return ""
        if len(cell_img.shape) == 3:
            cell_img = _cv2.cvtColor(cell_img, _cv2.COLOR_BGR2GRAY)

        # 1) Bounding box del texto dentro de la celda
        cell_img = _crop_to_text_bbox(cell_img, _cv2, _np)
        if cell_img is None or cell_img.size == 0:
            return ""
        h2, w2 = cell_img.shape[:2]
        if h2 < 8 or w2 < 8:
            return ""

        # 2) Padding blanco alrededor para que Tesseract respire
        pad = 10
        cell_img = _cv2.copyMakeBorder(
            cell_img, pad, pad, pad, pad,
            _cv2.BORDER_CONSTANT, value=255,
        )
        h3, w3 = cell_img.shape[:2]

        # 3) Upscale adaptativo basado en el TAMAÑO RECORTADO
        if w3 < 200:
            scale = 3
        elif w3 < 400:
            scale = 2
        else:
            scale = 1
        if scale > 1:
            cell_img = _cv2.resize(
                cell_img, (w3 * scale, h3 * scale),
                interpolation=_cv2.INTER_CUBIC,
            )

        # 4) Binarización solo si la imagen no es ya casi binaria
        mid_pixels = _np.sum((cell_img > 50) & (cell_img < 200))
        total_pixels = cell_img.size
        is_already_clean = mid_pixels / total_pixels < 0.1
        if not is_already_clean:
            _, cell_img = _cv2.threshold(
                cell_img, 0, 255, _cv2.THRESH_BINARY + _cv2.THRESH_OTSU,
            )
        # 5) Tesseract
        config = "--oem 1 --psm 6"
        text = pytesseract.image_to_string(cell_img, lang=lang, config=config)
        cleaned = " ".join(line.strip() for line in text.splitlines() if line.strip())
        # Limpiar "|" sueltos al inicio/final que provienen de bordes del marco
        import re as _re
        cleaned = _re.sub(r"^[\|\s]+", "", cleaned)
        cleaned = _re.sub(r"[\|\s]+$", "", cleaned)
        return cleaned
    except Exception as e:
        try:
            logger.debug(f"OCR celda falló: {e}")
        except Exception:
            pass
        return ""


def _crop_to_text_bbox(cell_img, cv2, np):
    """Recorta la celda al bounding-box donde hay contenido (texto).

    Estrategia:
      1. Binarizar invirtiendo (texto/contenido → blanco sobre negro).
      2. Hacer un closing morfológico horizontal para conectar caracteres de
         la misma línea en un único "blob".
      3. Encontrar los contornos no triviales (área > 0.5% del total).
      4. Calcular el bounding box que englobe todos los contornos.
      5. Si el bbox cubre menos del 10% de la celda, recortar; si cubre más,
         devolver la celda completa (recortar no aporta valor).

    Devuelve la celda recortada (o la original si no se puede recortar).
    """
    try:
        h, w = cell_img.shape[:2]
        if h < 20 or w < 20:
            return cell_img

        # Binarizar invirtiendo
        _, bin_img = cv2.threshold(
            cell_img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
        )
        # Si la celda es básicamente blanca (sin texto), devolver vacío
        white_ratio = (bin_img > 0).sum() / (h * w)
        if white_ratio < 0.001:
            return cell_img

        # Closing horizontal para unir caracteres de la misma palabra/línea.
        # El kernel debe ser pequeño en alto y mayor en ancho, proporcional al
        # tamaño de fuente esperado.
        kernel_w = max(5, w // 30)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_w, 1))
        closed = cv2.morphologyEx(bin_img, cv2.MORPH_CLOSE, kernel, iterations=1)

        # Encontrar todos los puntos no-cero y calcular bounding box global
        ys, xs = np.where(closed > 0)
        if len(ys) == 0 or len(xs) == 0:
            return cell_img

        ymin, ymax = int(ys.min()), int(ys.max())
        xmin, xmax = int(xs.min()), int(xs.max())

        # Verificar que el recorte realmente reduzca el área significativamente.
        # Si el bbox ocupa >80% del área de la celda, no recortar (no aporta).
        bbox_area = (ymax - ymin) * (xmax - xmin)
        cell_area = h * w
        if cell_area > 0 and bbox_area / cell_area > 0.80:
            return cell_img

        # Padding de seguridad alrededor del bbox.
        # v0.6.3: margen aumentado a 8 px porque tesseract pierde el último
        # carácter si el bbox está demasiado ajustado.
        margin = 8
        ymin = max(0, ymin - margin)
        ymax = min(h, ymax + margin)
        xmin = max(0, xmin - margin)
        xmax = min(w, xmax + margin)

        cropped = cell_img[ymin:ymax, xmin:xmax]
        if cropped.size == 0:
            return cell_img
        return cropped
    except Exception:
        return cell_img


def _detect_row_strips(gray, cv2, np) -> List[int]:
    """Fallback: detecta filas como bandas horizontales separadas por líneas finas.

    Estrategia mejorada (v0.6 fix):
      1. Aplicar morfología para resaltar líneas horizontales largas y delgadas.
      2. Sumar pixeles activos por fila.
      3. Tomar SOLO picos que correspondan a líneas reales (no a tipografía).
    """
    h, w = gray.shape
    # Binarizar (texto negro → blanco)
    _, thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    # Kernel horizontal grande para captar SOLO líneas largas
    kernel_len = max(w // 4, 60)
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_len, 1))
    h_lines_img = cv2.morphologyEx(thr, cv2.MORPH_OPEN, h_kernel, iterations=1)

    # Sumar por fila
    row_active = (h_lines_img > 0).sum(axis=1)
    # Threshold: la línea debe cubrir > 50% del ancho
    threshold = max(int(w * 0.5), 60)
    peaks_y = np.where(row_active >= threshold)[0].tolist()
    # Clustering tolerante (líneas dobles)
    return _cluster_coords(peaks_y, gap=8)


def extract_table_from_image(
    image_path: Path,
    lang: str = "spa",
    min_confidence: int = MIN_TABLE_CONFIDENCE,
) -> TableExtraction:
    """Extrae una tabla de una imagen, si la hay.

    Args:
        image_path: ruta al PNG/JPG.
        lang: idioma Tesseract ("spa", "eng", "spa+eng").
        min_confidence: por debajo de este score no se marca como tabla.

    Returns:
        TableExtraction con is_table, rows, confidence.
    """
    result = TableExtraction(is_table=False, confidence=0)
    cv2, np, pytesseract = _safe_imports()
    if cv2 is None:
        result.notes.append("OpenCV / pytesseract no disponibles.")
        return result

    try:
        img = cv2.imread(str(image_path))
        if img is None:
            result.notes.append(f"No se pudo leer la imagen: {image_path}")
            return result
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        H, W = gray.shape
        if H < 80 or W < 80:
            result.notes.append("Imagen demasiado pequeña para OCR fiable.")
            return result

        # FASE PREVIA — clasificación rápida: ¿es plausible que esto sea
        # una tabla? Si NO lo es, salimos rápido sin gastar tiempo en OCR.
        # Características que descartan: el "centro de masa" de la imagen
        # está muy fragmentado (diagrama de iconos), o no hay texto plano.
        if not _looks_like_a_table(gray, cv2, np, info_dict=result.notes):
            result.notes.append("Clasificación previa: no parece una tabla.")
            return result

        # 1) Detectar líneas (grid)
        h_lines, v_lines, info = _detect_grid_lines(gray, cv2, np)
        result.notes.append(
            f"Grid: {info['h_lines_count']} h-lines, "
            f"{info.get('v_lines_count_internal', 0)} v-lines internas "
            f"({info.get('v_lines_count_raw', 0)} brutas)"
        )

        # Validar: si las h_lines detectadas están demasiado próximas entre sí
        # (< 25px), no son separadores de fila reales sino líneas de texto.
        def _valid_separators(lines, min_gap=20):
            if len(lines) < 2:
                return lines
            valid = [lines[0]]
            for L in lines[1:]:
                if L - valid[-1] >= min_gap:
                    valid.append(L)
            return valid
        h_lines = _valid_separators(h_lines, min_gap=20)
        info["h_lines_after_filter"] = len(h_lines)
        result.notes.append(f"h-lines tras filtro de cercanía: {len(h_lines)}")

        # Caso A: grid completo — al menos 1 v_line INTERNA (= 2 columnas)
        # más h_lines bien separadas. La validación r.n_cols >= 2 al final
        # nos protege de falsos positivos donde la v_line interna era un
        # carácter "|" del texto.
        if len(h_lines) >= 3 and len(v_lines) >= 1:
            H, W = gray.shape
            v_lines_full = sorted(set([0] + list(v_lines) + [W]))
            r = _extract_with_grid(gray, h_lines, v_lines_full, pytesseract, lang, result)
            if r.is_table and r.n_cols >= 2:
                return r
            # Si no detecta 2+ columnas reales, caer a row_strips

        # Caso B: tabla tipo lista (1 columna) — separadores horizontales
        # claros pero sin columnas internas.
        row_strips = _detect_row_strips(gray, cv2, np)
        row_strips = _valid_separators(row_strips, min_gap=20)
        result.notes.append(f"row_strips tras filtro: {len(row_strips)}")
        if len(row_strips) >= 2:
            return _extract_row_strips(gray, row_strips, pytesseract, lang, result)

        # Caso C: la imagen no parece una tabla
        result.notes.append("No se detectó estructura de tabla suficiente.")
        return result

    except Exception as e:
        result.notes.append(f"Error procesando imagen: {e}")
        try:
            logger.warning(f"Error OCR de tabla {image_path}: {e}")
        except Exception:
            pass
        return result


def _looks_like_a_table(gray, cv2, np, info_dict=None) -> bool:
    """Clasificación previa rápida: ¿la imagen es plausiblemente una tabla?

    Descarta imágenes que claramente NO son tablas (diagramas con iconos,
    fotografías, figuras infográficas) ANTES de hacer OCR caro.

    Heurística:
      1. Tablas tienen TEXTO HORIZONTAL en líneas regulares → al binarizar
         y proyectar en eje X, las "filas" de píxeles activos se alternan
         con bandas claras (espacios entre líneas de texto).
      2. Diagramas/infografías tienen píxeles dispersos sin patrón fila.

    Métrica: ratio entre filas con muchos píxeles negros (texto) y filas
    vacías. Una tabla tiene este ratio entre 0.15 y 0.85. Las infografías
    o imágenes vacías quedan fuera.
    """
    h, w = gray.shape
    # Binarizar para que el texto sea negro (1) sobre blanco (0)
    _, thr = cv2.threshold(gray, 0, 255,
                            cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    # Suma por fila (proyección horizontal)
    row_density = (thr > 0).sum(axis=1) / w  # ratio [0, 1] por fila
    # Filas con "algo de texto": densidad > 5% pero < 70% (excluye líneas
    # sólidas y excluye fondos)
    text_rows = ((row_density > 0.05) & (row_density < 0.70)).sum()
    text_ratio = text_rows / h

    # Caso "infografía con iconos": densidad concentrada en blobs grandes
    # → mucha fila con > 70% (fondo de color sólido del icono) o casi todas
    # vacías
    saturated_rows = (row_density >= 0.70).sum()
    saturation_ratio = saturated_rows / h
    # Si más del 25% de las filas son densidad muy alta, es un blob/icono
    if saturation_ratio > 0.25:
        if info_dict is not None:
            info_dict.append(
                f"_looks_like_a_table: saturación alta ({saturation_ratio:.2f}) → no es tabla"
            )
        return False

    # Si casi no hay filas con texto, no es una tabla
    if text_ratio < 0.10:
        if info_dict is not None:
            info_dict.append(
                f"_looks_like_a_table: muy poco texto ({text_ratio:.2f}) → no es tabla"
            )
        return False

    if info_dict is not None:
        info_dict.append(
            f"_looks_like_a_table: text_ratio={text_ratio:.2f} OK"
        )
    return True


def _extract_with_grid(gray, h_lines, v_lines, pytesseract, lang, result):
    """Extrae celdas usando un grid completo."""
    h_lines = sorted(set(h_lines))
    v_lines = sorted(set(v_lines))
    rows = []
    for ri in range(len(h_lines) - 1):
        y1, y2 = h_lines[ri], h_lines[ri + 1]
        if y2 - y1 < 10:  # fila demasiado pequeña, separador doble
            continue
        row_cells = []
        for ci in range(len(v_lines) - 1):
            x1, x2 = v_lines[ci], v_lines[ci + 1]
            if x2 - x1 < 10:
                continue
            # Recortar con un pequeño padding hacia adentro
            pad = 2
            cell = gray[y1 + pad:y2 - pad, x1 + pad:x2 - pad]
            if cell.size == 0:
                row_cells.append("")
                continue
            txt = _ocr_cell(cell, pytesseract, lang=lang)
            row_cells.append(txt)
        if row_cells:
            rows.append(row_cells)

    if not rows:
        result.notes.append("Grid detectado pero no se pudieron extraer celdas.")
        return result

    n_rows = len(rows)
    n_cols = max(len(r) for r in rows)
    # Normalizar a la misma longitud
    rows = [r + [""] * (n_cols - len(r)) for r in rows]

    # Cálculo de confianza:
    # - +30 si grid completo (≥2 h y ≥2 v)
    # - +20 si todas las filas tienen el mismo nº de columnas y > 1
    # - +20 si > 50% de celdas tienen texto no vacío
    # - +20 si ratio filas/cols razonable (no 1×N ni N×1 sin sentido)
    # - +10 si la primera fila tiene texto en todas las columnas
    score = 30
    filled = sum(1 for r in rows for c in r if c.strip())
    total_cells = n_rows * n_cols
    if total_cells and filled / total_cells > 0.5:
        score += 20
    if n_cols > 1 and n_rows > 1:
        score += 20
    if n_rows >= 2 and n_cols >= 2 and n_rows <= 50 and n_cols <= 20:
        score += 20
    if rows and all(c.strip() for c in rows[0]):
        score += 10
    result.is_table = score >= MIN_TABLE_CONFIDENCE
    result.confidence = min(score, 100)
    result.rows = rows
    result.n_rows = n_rows
    result.n_cols = n_cols
    return result


def _extract_row_strips(gray, row_strips, pytesseract, lang, result):
    """Extrae filas como bandas horizontales (tabla de 1 columna estilo lista)."""
    row_strips = sorted(set(row_strips))
    H, W = gray.shape
    # Añadir bordes virtuales
    if row_strips[0] > 10:
        row_strips = [0] + row_strips
    if row_strips[-1] < H - 10:
        row_strips = row_strips + [H]

    rows = []
    for ri in range(len(row_strips) - 1):
        y1, y2 = row_strips[ri], row_strips[ri + 1]
        if y2 - y1 < 15:
            continue
        pad = 2
        strip = gray[y1 + pad:y2 - pad, 0 + pad:W - pad]
        if strip.size == 0:
            continue
        txt = _ocr_cell(strip, pytesseract, lang=lang)
        if txt:
            rows.append([txt])

    if len(rows) < 2:
        result.notes.append("Bandas detectadas pero contenido insuficiente.")
        return result

    score = 25
    if len(rows) >= 3:
        score += 15
    if all(r[0].strip() for r in rows):
        score += 25
    # Penalizar si la primera "fila" parece igual al resto en longitud (no es título)
    first_len = len(rows[0][0])
    avg_rest = sum(len(r[0]) for r in rows[1:]) / max(1, len(rows) - 1)
    if avg_rest > first_len * 1.4:
        score += 10  # bueno: primera fila más corta = parece título

    result.is_table = score >= MIN_TABLE_CONFIDENCE
    result.confidence = min(score, 100)
    result.rows = rows
    result.n_rows = len(rows)
    result.n_cols = 1
    return result


# ============================================================
# Función de conveniencia para integrar en el parser
# ============================================================

def analyze_image_for_table(
    image_path: Path,
    lang: str = "spa",
    min_confidence: int = MIN_TABLE_CONFIDENCE,
) -> Optional[TableExtraction]:
    """Como extract_table_from_image, pero devuelve None si la confianza es baja
    o si las dependencias no están disponibles. Útil para integración sencilla."""
    result = extract_table_from_image(image_path, lang=lang, min_confidence=min_confidence)
    if not result.is_table:
        return None
    return result

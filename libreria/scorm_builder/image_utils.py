"""Procesado de imágenes: upscaling automático y avisos de pixelado.

v0.6: cuando una imagen extraída del DOCX tiene menos de cierto ancho
mínimo, se hace upscale con LANCZOS para que no se vea pixelada en el
SCORM (donde se renderiza al ancho del contenido). El upscaling no
recupera detalle, pero suaviza los bordes y evita el aspecto serrado.

También se registra un warning para que el editor sepa qué imágenes
tienen baja resolución y conviene reemplazar.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)

# Anchura mínima recomendada para que una imagen se vea bien en pantalla
# desktop (>= 1024px) y móvil retina (>= 2x). 800px como compromiso entre
# tamaño de archivo y calidad.
MIN_RECOMMENDED_WIDTH = 600
TARGET_UPSCALE_WIDTH = 1200

# Formatos en los que podemos reescribir manteniendo el formato original
_SUPPORTED_FORMATS = {".png", ".jpg", ".jpeg", ".webp"}


def analyze_image(path: Path) -> Optional[dict]:
    """Devuelve metadatos relevantes de la imagen, o None si no se puede leer.

    Returns:
        dict con keys:
          - width, height: dimensiones en píxeles
          - is_small: True si está por debajo de MIN_RECOMMENDED_WIDTH
          - format: extensión normalizada
    """
    try:
        from PIL import Image
        with Image.open(path) as im:
            w, h = im.size
            fmt = (im.format or "").lower()
        return {
            "width": w,
            "height": h,
            "is_small": w < MIN_RECOMMENDED_WIDTH,
            "format": fmt,
        }
    except Exception as e:
        logger.debug(f"No se pudo analizar {path}: {e}")
        return None


def upscale_in_place(path: Path, target_width: int = TARGET_UPSCALE_WIDTH) -> bool:
    """Reescala una imagen IN-PLACE si es más pequeña que target_width.

    Usa LANCZOS (alta calidad). Mantiene la proporción. Solo procesa formatos
    en _SUPPORTED_FORMATS. No upscalea si la imagen ya es lo bastante grande
    o si es SVG/GIF (mejor dejarlos como están).

    Returns:
        True si se hizo upscale, False si no.
    """
    if path.suffix.lower() not in _SUPPORTED_FORMATS:
        return False
    try:
        from PIL import Image
        with Image.open(path) as im:
            iw, ih = im.size
            if iw >= target_width:
                return False
            # Calcular escalado proporcional
            ratio = target_width / iw
            new_w = target_width
            new_h = int(round(ih * ratio))
            # LANCZOS es lo que antes era ANTIALIAS, mejor calidad downsize/upsize
            resampling = getattr(Image, "Resampling", Image)
            lanczos = getattr(resampling, "LANCZOS", 1)
            # Conservar formato y modo
            fmt = im.format or "PNG"
            mode = im.mode
            im2 = im.resize((new_w, new_h), lanczos)
        # Guardar sobreescribiendo (ya cerramos el contexto)
        save_kwargs = {}
        if fmt.upper() == "JPEG":
            save_kwargs["quality"] = 88
            save_kwargs["optimize"] = True
            # JPEG no soporta alpha — convertir si hace falta
            if mode in ("RGBA", "LA", "P"):
                im2 = im2.convert("RGB")
        elif fmt.upper() == "PNG":
            save_kwargs["optimize"] = True
        im2.save(path, format=fmt, **save_kwargs)
        logger.info(f"Imagen upscaleada: {path.name} {iw}×{ih} → {new_w}×{new_h}")
        return True
    except Exception as e:
        logger.warning(f"No se pudo upscalear {path}: {e}")
        return False


def process_images_in_dir(
    directory: Path,
    upscale: bool = True,
) -> Tuple[List[str], List[str]]:
    """Procesa todas las imágenes de un directorio.

    Returns:
        Tuple (upscaled, warnings_small) con listas de nombres de archivo:
        - upscaled: imágenes a las que se les hizo upscale
        - warnings_small: imágenes que SIGUEN siendo pequeñas tras el proceso
          (formatos que no se pueden reescalar fácilmente, como SVG)
    """
    if not directory.exists() or not directory.is_dir():
        return [], []

    upscaled: List[str] = []
    warnings_small: List[str] = []

    for path in directory.iterdir():
        if not path.is_file():
            continue
        info = analyze_image(path)
        if info is None:
            continue
        if not info["is_small"]:
            continue
        # Imagen pequeña: intentar upscale
        if upscale and path.suffix.lower() in _SUPPORTED_FORMATS:
            if upscale_in_place(path):
                upscaled.append(path.name)
                continue
        # No se pudo upscalear (SVG, GIF, error) → solo warning
        warnings_small.append(
            f"{path.name} ({info['width']}×{info['height']}px) — "
            f"resolución por debajo de {MIN_RECOMMENDED_WIDTH}px de ancho. "
            f"Puede verse pixelada al ampliarse."
        )
    return upscaled, warnings_small

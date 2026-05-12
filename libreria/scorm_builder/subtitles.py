"""Generador de subtítulos automáticos para vídeos usando faster-whisper.

Es OPCIONAL: si la dependencia no está instalada o falla, devuelve None y se
emite un warning. No queremos que la herramienta deje de funcionar por esto.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def whisper_available() -> bool:
    """Devuelve True si faster-whisper está instalado y se puede importar."""
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def generate_subtitles(
    video_path: str | Path,
    output_vtt: str | Path,
    model_size: str = "tiny",
    language: Optional[str] = None,
) -> Optional[Path]:
    """Genera subtítulos en formato WebVTT para un vídeo.

    Args:
        video_path: ruta del vídeo (mp4, webm, etc.)
        output_vtt: ruta donde escribir el archivo .vtt
        model_size: 'tiny', 'base', 'small', 'medium', 'large-v3'.
            'tiny' es el más rápido (~30 MB) y suficiente para empezar.
        language: código ISO ('es', 'en'); None = auto-detectar.

    Returns:
        Path del .vtt generado, o None si falla.
    """
    video_path = Path(video_path)
    output_vtt = Path(output_vtt)
    if not video_path.exists():
        logger.warning(f"Vídeo no encontrado: {video_path}")
        return None
    if not whisper_available():
        logger.info("faster-whisper no instalado; se omite generación de subtítulos.")
        return None

    try:
        from faster_whisper import WhisperModel
        # CPU sin cuantización para máxima compatibilidad
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        segments, info = model.transcribe(
            str(video_path),
            language=language,
            beam_size=1,
            vad_filter=True,
        )
        # Escribir WebVTT
        lines = ["WEBVTT", ""]
        for i, seg in enumerate(segments, start=1):
            start = _format_vtt_time(seg.start)
            end = _format_vtt_time(seg.end)
            text = (seg.text or "").strip()
            if not text:
                continue
            lines.append(str(i))
            lines.append(f"{start} --> {end}")
            lines.append(text)
            lines.append("")
        output_vtt.parent.mkdir(parents=True, exist_ok=True)
        output_vtt.write_text("\n".join(lines), encoding="utf-8")
        return output_vtt
    except Exception as e:
        logger.warning(f"Error generando subtítulos para {video_path.name}: {e}")
        return None


def _format_vtt_time(seconds: float) -> str:
    """Convierte segundos a formato VTT HH:MM:SS.mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds - h * 3600 - m * 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"

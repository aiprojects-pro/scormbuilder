"""Generador de audio TTS para narración del curso. Opcional.

Usa pyttsx3 (offline, sin API keys) por defecto. Se puede sustituir por servicios
premium (ElevenLabs, OpenAI TTS) implementando una función con la misma firma.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def tts_available() -> bool:
    """Devuelve True si pyttsx3 está instalado."""
    try:
        import pyttsx3  # noqa: F401
        return True
    except ImportError:
        return False


def synthesize(
    text: str,
    output_audio: str | Path,
    language: str = "es",
    rate: int = 175,
) -> Optional[Path]:
    """Genera un archivo de audio a partir del texto.

    Args:
        text: el texto a sintetizar (limpiado de markdown).
        output_audio: ruta de salida (.wav o .mp3 dependiendo del backend).
        language: 'es' o 'en'.
        rate: palabras por minuto (175 = ritmo normal).

    Returns:
        Path del audio generado, o None si falla.
    """
    output_audio = Path(output_audio)
    text = (text or "").strip()
    if not text:
        return None
    if not tts_available():
        logger.info("pyttsx3 no instalado; se omite TTS.")
        return None

    try:
        import pyttsx3
        engine = pyttsx3.init()
        # Intentar elegir voz en el idioma deseado
        try:
            voices = engine.getProperty("voices")
            for v in voices:
                lang_match = False
                vid = (v.id or "").lower()
                vlang = " ".join((getattr(v, "languages", []) or [])).lower() if hasattr(v, "languages") else ""
                if language == "es" and ("spanish" in vid or "espa" in vid or "es" in vlang):
                    lang_match = True
                elif language == "en" and ("english" in vid or "en" in vlang):
                    lang_match = True
                if lang_match:
                    engine.setProperty("voice", v.id)
                    break
        except Exception:
            pass
        engine.setProperty("rate", rate)
        # pyttsx3 escribe en .wav o .aiff según plataforma
        output_audio.parent.mkdir(parents=True, exist_ok=True)
        engine.save_to_file(text, str(output_audio))
        engine.runAndWait()
        if output_audio.exists() and output_audio.stat().st_size > 0:
            return output_audio
        return None
    except Exception as e:
        logger.warning(f"TTS falló: {e}")
        return None


def subsection_to_text(subsection) -> str:
    """Aplana un subapartado a texto plano para narrar."""
    parts = []
    if subsection.title:
        parts.append(subsection.title + ".")
    for b in subsection.blocks:
        bt = getattr(b.type, "value", b.type)
        if bt in ("paragraph", "heading_3", "heading_4",
                  "callout_key", "callout_alert", "callout_success",
                  "callout_warn", "quote", "example"):
            if b.text:
                parts.append(b.text)
        elif bt in ("list_bullet", "list_number"):
            for it in (b.items or []):
                parts.append(it + ".")
    return " ".join(parts)

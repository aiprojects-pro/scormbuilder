"""Generador de audio TTS para narración del curso.

v0.5.17: motor principal cambiado a gTTS (Google Text-to-Speech).

gTTS funciona sin necesidad de drivers de audio del sistema (a diferencia de
pyttsx3, que requiere espeak/sapi5/nsss y suele fallar en servidores Linux
sin entorno gráfico). Genera archivos MP3 pequeños y de calidad razonable.

Necesita conexión a Internet para llamar al endpoint de Google Translate TTS.
Como fallback se usa pyttsx3 si está instalado.

Salida: archivos .mp3 (en lugar de .wav anterior). Los navegadores reproducen
MP3 de forma nativa, así que esto no cambia la experiencia.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def _gtts_available() -> bool:
    try:
        import gtts  # noqa: F401
        return True
    except ImportError:
        return False


def _pyttsx3_available() -> bool:
    try:
        import pyttsx3  # noqa: F401
        return True
    except ImportError:
        return False


def tts_available() -> bool:
    """Devuelve True si HAY al menos un motor TTS disponible."""
    return _gtts_available() or _pyttsx3_available()


def tts_engine_info() -> Tuple[str, str]:
    """Devuelve (engine_name, status_message) para diagnóstico."""
    if _gtts_available():
        return ("gtts", "gTTS disponible (requiere acceso a Internet)")
    if _pyttsx3_available():
        return ("pyttsx3", "gTTS no instalado; usando pyttsx3 (requiere espeak/sapi5 en el SO)")
    return ("none",
            "Ningún motor TTS disponible. Instala gtts en el servidor: "
            "pip install gtts")


def synthesize(
    text: str,
    output_audio: str | Path,
    language: str = "es",
    rate: int = 175,
) -> Optional[Path]:
    """Genera un archivo de audio a partir del texto.

    Intenta primero con gTTS (online, fiable). Si gTTS no está disponible,
    cae a pyttsx3 (offline, requiere drivers de audio del SO).

    Args:
        text: el texto a sintetizar (limpiado de markdown).
        output_audio: ruta de salida. La extensión se ajusta automáticamente
            (gTTS produce .mp3, pyttsx3 produce .wav).
        language: 'es' o 'en'.
        rate: palabras por minuto (solo aplica a pyttsx3).

    Returns:
        Path del audio generado (puede tener extensión distinta a la pedida),
        o None si falla.
    """
    output_audio = Path(output_audio)
    text = (text or "").strip()
    if not text:
        return None

    # 1) Intentar gTTS primero (motor preferido)
    if _gtts_available():
        try:
            from gtts import gTTS
            output_audio.parent.mkdir(parents=True, exist_ok=True)
            # gTTS siempre genera MP3. Ajustamos la extensión si hace falta.
            if output_audio.suffix.lower() != ".mp3":
                output_audio = output_audio.with_suffix(".mp3")
            tts = gTTS(text=text, lang=language, slow=False)
            tts.save(str(output_audio))
            if output_audio.exists() and output_audio.stat().st_size > 0:
                return output_audio
            logger.warning(f"gTTS escribió archivo vacío: {output_audio}")
        except Exception as e:
            logger.warning(f"gTTS falló: {e}; intentando pyttsx3...")

    # 2) Fallback a pyttsx3 (offline)
    if _pyttsx3_available():
        try:
            import pyttsx3
            engine = pyttsx3.init()
            try:
                voices = engine.getProperty("voices")
                for v in voices:
                    vid = (v.id or "").lower()
                    vlang = " ".join((getattr(v, "languages", []) or [])).lower() if hasattr(v, "languages") else ""
                    if language == "es" and ("spanish" in vid or "espa" in vid or "es" in vlang):
                        engine.setProperty("voice", v.id)
                        break
                    elif language == "en" and ("english" in vid or "en" in vlang):
                        engine.setProperty("voice", v.id)
                        break
            except Exception:
                pass
            engine.setProperty("rate", rate)
            output_audio.parent.mkdir(parents=True, exist_ok=True)
            # pyttsx3 escribe WAV
            if output_audio.suffix.lower() != ".wav":
                output_audio = output_audio.with_suffix(".wav")
            engine.save_to_file(text, str(output_audio))
            engine.runAndWait()
            if output_audio.exists() and output_audio.stat().st_size > 0:
                return output_audio
        except Exception as e:
            logger.warning(f"pyttsx3 falló: {e}")

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

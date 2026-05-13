"""Módulo de asistencia IA (v0.5 Fase 2).

Centraliza todas las llamadas a la API de Anthropic. Es OPCIONAL: si no hay
`ANTHROPIC_API_KEY` configurada, las funciones devuelven `None` o el valor
por defecto, pero el flujo del SCORM Builder no se rompe.

Funcionalidades expuestas:
- `is_available()`: ¿hay clave configurada y red disponible?
- `generate_tags(topic)`: 5-8 etiquetas temáticas para un tema.
- `generate_alt_text(image_path)`: alt-text descriptivo de una imagen.
- `generate_quiz(topic, config)`: preguntas (test/V-F/huecos) según config.
- `generate_extended_aiken(topic, n)`: banco amplio para evaluación externa.
- `suggest_titles_and_objectives(topic)`: título y objetivos del tema.

El backend HTTP es `urllib` (sin dependencias externas).
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-4-5"
DEFAULT_TIMEOUT = 90  # segundos


# ============================================================
# UTILIDADES BASE
# ============================================================

def is_available() -> bool:
    """True si hay clave configurada (no comprueba red)."""
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


def _call_api(
    prompt: str,
    *,
    max_tokens: int = 2048,
    model: str = DEFAULT_MODEL,
    system: Optional[str] = None,
    image_parts: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[bool, str]:
    """Llama a la API de Anthropic. Devuelve (ok, text_or_error).

    Si `image_parts` se pasa, se usa la API multimodal (Vision).
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return False, "ANTHROPIC_API_KEY no configurada"

    content: List[Dict[str, Any]] = []
    if image_parts:
        content.extend(image_parts)
    content.append({"type": "text", "text": prompt})

    body_dict: Dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": content}],
    }
    if system:
        body_dict["system"] = system
    body = json.dumps(body_dict).encode("utf-8")

    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="ignore")
        except Exception:
            pass
        return False, f"HTTP {e.code}: {err_body[:300]}"
    except Exception as e:
        return False, f"Error llamando a Anthropic: {e}"

    try:
        blocks = data.get("content", [])
        text_parts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
        return True, "\n".join(text_parts).strip()
    except Exception as e:
        return False, f"Respuesta inesperada: {e}"


def _parse_json_response(raw_text: str) -> Optional[Any]:
    """Parsea JSON de una respuesta de Claude, quitando los posibles ```fences."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Intentar extraer el primer bloque JSON balanceado
        match = re.search(r"(\{.*\}|\[.*\])", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                return None
        return None


# ============================================================
# UTILIDADES DE CONTENIDO
# ============================================================

def topic_to_plain_text(topic: Any, max_chars: int = 12000) -> str:
    """Convierte un Topic (objeto o dict) en texto plano para los prompts."""
    parts: List[str] = []

    if isinstance(topic, dict):
        title = topic.get("title", "")
        intro = topic.get("intro") or ""
        subs = topic.get("subsections", [])
    else:
        title = getattr(topic, "title", "")
        intro = getattr(topic, "intro", None) or ""
        subs = getattr(topic, "subsections", [])

    parts.append(f"# {title}")
    if intro:
        parts.append(intro)

    for sub in subs:
        if isinstance(sub, dict):
            sub_num = sub.get("number", "")
            sub_title = sub.get("title", "")
            blocks = sub.get("blocks", [])
        else:
            sub_num = getattr(sub, "number", "")
            sub_title = getattr(sub, "title", "")
            blocks = getattr(sub, "blocks", [])
        parts.append(f"\n## {sub_num} {sub_title}")
        for b in blocks:
            if isinstance(b, dict):
                btype = b.get("type", "paragraph")
                text = b.get("text", "")
                items = b.get("items", [])
            else:
                btype = getattr(b.type, "value", b.type) if hasattr(b, "type") else "paragraph"
                text = getattr(b, "text", "")
                items = getattr(b, "items", [])
            if btype in {"paragraph", "heading_3", "heading_4",
                         "callout_key", "callout_alert", "callout_success",
                         "callout_warn", "quote", "example"}:
                if text:
                    parts.append(text)
            elif btype in {"list_bullet", "list_number"}:
                parts.extend(f"- {it}" for it in items)

    full = "\n".join(parts)
    if len(full) > max_chars:
        full = full[:max_chars] + "\n\n[...contenido truncado...]"
    return full


# ============================================================
# TAGS
# ============================================================

def generate_tags(topic: Any, *, n: int = 6) -> Optional[List[str]]:
    """Genera entre 4 y 8 etiquetas temáticas para un tema. None si falla."""
    if not is_available():
        return None

    content = topic_to_plain_text(topic, max_chars=8000)
    prompt = f"""Eres un experto en clasificación de contenido educativo.

Analiza el siguiente tema de un curso e-learning y genera EXACTAMENTE {n} etiquetas
temáticas concisas (1-3 palabras cada una) en español, en minúscula, sin tildes ni signos.

Las etiquetas deben servir para:
- Indexar el curso en un LMS (Moodle) y facilitar su búsqueda.
- Que un alumno entienda de un vistazo de qué va el tema.

Incluye una mezcla de:
- 1-2 etiquetas del área temática general (ej: "gestion deportiva", "derecho laboral")
- 1-2 etiquetas de subtema específico (ej: "comite olimpico", "lopd")
- 1 etiqueta de nivel/dificultad si se deduce ("basico", "intermedio", "avanzado")
- 1 etiqueta de tipo de contenido si aplica ("normativa", "practico", "teorico", "caso practico")

Responde SOLO con JSON, sin texto antes ni después:
{{"tags": ["etiqueta1", "etiqueta2", ...]}}

Contenido del tema:
---
{content}
---"""

    ok, response = _call_api(prompt, max_tokens=400)
    if not ok:
        logger.warning(f"generate_tags falló: {response}")
        return None
    data = _parse_json_response(response)
    if not isinstance(data, dict):
        return None
    tags = data.get("tags", [])
    if not isinstance(tags, list):
        return None
    # Sanear: cadenas no vacías, en minúscula, sin duplicados
    clean: List[str] = []
    seen = set()
    for t in tags:
        if not isinstance(t, str):
            continue
        t = t.strip().lower()
        # Quitar caracteres raros, dejar letras + espacios + guiones + números
        t = re.sub(r"[^a-z0-9áéíóúñü\s\-]", "", t).strip()
        if t and t not in seen:
            clean.append(t)
            seen.add(t)
    return clean[:8] if clean else None


# ============================================================
# ALT-TEXT PARA IMÁGENES (VISION)
# ============================================================

def generate_alt_text(image_path: str | Path) -> Optional[str]:
    """Genera un alt-text descriptivo para una imagen. None si no disponible."""
    if not is_available():
        return None
    path = Path(image_path)
    if not path.exists() or not path.is_file():
        return None

    # Determinar mime
    ext = path.suffix.lower().lstrip(".")
    mime_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "gif": "image/gif", "webp": "image/webp"}
    mime = mime_map.get(ext)
    if not mime:
        return None

    try:
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    except Exception as e:
        logger.warning(f"No se pudo leer la imagen {path}: {e}")
        return None

    # Limitar a ~5MB por la API
    if len(b64) > 6_500_000:
        return None

    image_parts = [{
        "type": "image",
        "source": {"type": "base64", "media_type": mime, "data": b64},
    }]
    prompt = (
        "Describe esta imagen en una frase breve (máximo 20 palabras) en español, "
        "como texto alternativo accesible para lectores de pantalla. "
        "No empieces con 'Imagen de'. Sé concreto y descriptivo. "
        "Responde SOLO con la frase, sin comillas ni preámbulos."
    )
    ok, response = _call_api(prompt, max_tokens=120, image_parts=image_parts)
    if not ok:
        logger.warning(f"generate_alt_text falló: {response}")
        return None
    alt = response.strip().strip('"').strip("'")
    # Limpiar saltos de línea
    alt = re.sub(r"\s+", " ", alt)
    if len(alt) > 250:
        alt = alt[:250].rstrip() + "..."
    return alt or None


# ============================================================
# QUIZZES (TIPOS MIXTOS)
# ============================================================

@dataclass
class QuizConfig:
    """Configuración de generación de quiz para un tema.

    location:
        - "final": un único bloque de N preguntas al final del tema (modo clásico)
        - "per_subsection": una pregunta por subapartado, intercaladas
        - "mixed": una pregunta intercalada por subapartado + bloque final

    types: lista de tipos permitidos
        - "multiple_choice": test de 4 opciones (default)
        - "true_false": verdadero / falso
        - "fill_in": completar hueco
    """
    location: str = "final"             # "final" | "per_subsection" | "mixed"
    types: List[str] = field(default_factory=lambda: ["multiple_choice"])
    n_questions: int = 5                # total para 'final' o 'mixed' final; ignorado en 'per_subsection'


def generate_quiz(
    topic: Any,
    config: Optional[QuizConfig] = None,
) -> Optional[Dict[str, Any]]:
    """Genera preguntas según la configuración.

    Devuelve un dict:
      {
        "final": [Question, ...],            # preguntas del bloque final
        "by_subsection": {sub_id: [Question, ...]}  # preguntas intercaladas
      }
    Donde Question es {text, options[], correct_index, explanation, qtype}.

    None si la IA no está disponible o falla.
    """
    if not is_available():
        return None
    config = config or QuizConfig()
    content = topic_to_plain_text(topic, max_chars=10000)

    # Construir descripción de tipos para el prompt
    types_desc = []
    if "multiple_choice" in config.types:
        types_desc.append("opción múltiple de 4 opciones (qtype='multiple_choice')")
    if "true_false" in config.types:
        types_desc.append("verdadero/falso con 2 opciones (qtype='true_false')")
    if "fill_in" in config.types:
        types_desc.append("completar hueco (qtype='fill_in', el enunciado lleva '___' donde va la respuesta correcta y las opciones son alternativas)")
    types_block = "; ".join(types_desc)

    # Subapartados (para 'per_subsection' y 'mixed')
    if isinstance(topic, dict):
        subs = topic.get("subsections", [])
    else:
        subs = getattr(topic, "subsections", [])
    sub_info = []
    for s in subs:
        if isinstance(s, dict):
            sub_info.append({"id": s.get("id", ""), "number": s.get("number", ""), "title": s.get("title", "")})
        else:
            sub_info.append({"id": getattr(s, "id", ""), "number": getattr(s, "number", ""), "title": getattr(s, "title", "")})
    sub_list_str = "\n".join(f"- id={s['id']} · {s['number']} {s['title']}" for s in sub_info)

    if config.location == "final":
        location_desc = f"Genera {config.n_questions} preguntas para el bloque final del tema."
    elif config.location == "per_subsection":
        location_desc = (
            f"Para cada uno de los siguientes subapartados, genera UNA pregunta de repaso:\n{sub_list_str}\n"
            "Asocia cada pregunta a su subapartado mediante el campo 'subsection_id'."
        )
    else:  # mixed
        location_desc = (
            f"Genera dos cosas:\n"
            f"1) UNA pregunta de repaso por cada subapartado (campo 'subsection_id'):\n{sub_list_str}\n"
            f"2) {config.n_questions} preguntas adicionales para el bloque final (sin subsection_id)."
        )

    prompt = f"""Eres un experto pedagogo diseñando preguntas para un curso e-learning.

{location_desc}

Tipos de pregunta permitidos: {types_block}

REGLAS:
- Cada pregunta debe ser clara, sin trampas, basada SOLO en el contenido proporcionado.
- Para 'multiple_choice': 4 opciones (A-D), una correcta. Distractores plausibles.
- Para 'true_false': 2 opciones exactas ["Verdadero", "Falso"].
- Para 'fill_in': el campo 'text' lleva "___" donde va la palabra clave; 4 opciones, una correcta.
- Cada pregunta lleva una breve 'explanation' de por qué la correcta es correcta.
- Varía la dificultad (datos directos, aplicación, análisis).

Responde EXCLUSIVAMENTE con JSON válido, sin texto antes ni después:

{{
  "questions": [
    {{
      "qtype": "multiple_choice",
      "subsection_id": null,
      "text": "Enunciado...",
      "options": ["A...", "B...", "C...", "D..."],
      "correct_index": 0,
      "explanation": "..."
    }}
  ]
}}

Contenido del tema:
---
{content}
---"""

    ok, response = _call_api(prompt, max_tokens=6000)
    if not ok:
        logger.warning(f"generate_quiz falló: {response}")
        return None
    data = _parse_json_response(response)
    if not isinstance(data, dict):
        return None

    questions = data.get("questions", [])
    if not isinstance(questions, list):
        return None

    final: List[Dict[str, Any]] = []
    by_sub: Dict[str, List[Dict[str, Any]]] = {}
    valid_sub_ids = {s["id"] for s in sub_info}

    for q in questions:
        if not isinstance(q, dict):
            continue
        text = q.get("text", "").strip()
        options = q.get("options", [])
        qtype = q.get("qtype", "multiple_choice")
        if qtype not in {"multiple_choice", "true_false", "fill_in"}:
            qtype = "multiple_choice"
        if qtype == "true_false":
            options = ["Verdadero", "Falso"]
        try:
            ci = int(q.get("correct_index", 0))
        except (TypeError, ValueError):
            continue
        if not (text and isinstance(options, list) and len(options) >= 2 and 0 <= ci < len(options)):
            continue
        clean_q = {
            "qtype": qtype,
            "text": text,
            "options": [str(o) for o in options],
            "correct_index": ci,
            "explanation": str(q.get("explanation", "")).strip() or None,
        }
        sub_id = q.get("subsection_id")
        if sub_id and sub_id in valid_sub_ids:
            by_sub.setdefault(sub_id, []).append(clean_q)
        else:
            final.append(clean_q)

    return {"final": final, "by_subsection": by_sub}


# ============================================================
# BANCO AIKEN EXTENDIDO (con IA)
# ============================================================

def generate_extended_aiken(topic: Any, *, n_questions: int = 30) -> Optional[List[Dict[str, Any]]]:
    """Genera un banco amplio de preguntas (sólo multiple_choice) para evaluación externa.

    No las incrusta en el SCORM; se usa para generar un .txt Aiken adicional
    que el formador pueda importar en Moodle como banco de preguntas separado.
    """
    if not is_available():
        return None
    content = topic_to_plain_text(topic, max_chars=12000)

    prompt = f"""Eres un experto pedagogo diseñando un banco de preguntas para evaluación.

Genera EXACTAMENTE {n_questions} preguntas tipo test (opción múltiple, 4 opciones)
basadas en el contenido siguiente.

REGLAS:
- Una sola opción correcta por pregunta.
- Distractores plausibles, no absurdos.
- Distribución de dificultad: 40% fácil, 40% media, 20% difícil.
- Cubre TODOS los subapartados del tema proporcionalmente.
- Incluye breve explicación de la respuesta correcta.
- Las preguntas NO deben repetirse y deben variar en formulación (qué/cuál/cuándo/por qué/cómo).

Responde EXCLUSIVAMENTE con JSON, sin texto antes ni después:

{{
  "questions": [
    {{
      "text": "...",
      "options": ["A...", "B...", "C...", "D..."],
      "correct_index": 0,
      "explanation": "..."
    }}
  ]
}}

Contenido del tema:
---
{content}
---"""

    ok, response = _call_api(prompt, max_tokens=12000)
    if not ok:
        logger.warning(f"generate_extended_aiken falló: {response}")
        return None
    data = _parse_json_response(response)
    if not isinstance(data, dict):
        return None
    questions = data.get("questions", [])
    if not isinstance(questions, list):
        return None
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
        if text and isinstance(options, list) and len(options) >= 2 and 0 <= ci < len(options):
            valid.append({
                "text": text,
                "options": [str(o) for o in options],
                "correct_index": ci,
                "explanation": str(q.get("explanation", "")).strip() or None,
            })
    return valid or None


# ============================================================
# ENRIQUECIMIENTO DE WORD: callouts automáticos (v0.5 Fase 5)
# ============================================================

CALLOUT_TYPES_VALID = {"CLAVE", "ALERTA", "EXITO", "CUIDADO", "CITA"}


def enrich_topic_with_callouts(topic: Any) -> Optional[Dict[str, Any]]:
    """Analiza el contenido de un tema y propone convertir parrafos en callouts.

    No modifica nada: devuelve sugerencias para que el usuario las apruebe
    o las descarte. La IA identifica:
      - Definiciones de conceptos -> [CLAVE]
      - Avisos importantes / riesgos -> [ALERTA]
      - Precauciones suaves -> [CUIDADO]
      - Buenas practicas / casos de exito -> [EXITO]
      - Citas textuales y articulos de ley -> [CITA]

    Devuelve dict con clave "suggestions" (lista). Cada sugerencia tiene:
      subsection_id, block_index, current_type, suggested_type,
      current_text, suggested_text, reason
    None si no hay clave o falla la IA.
    """
    if not is_available():
        return None

    candidates: List[Dict[str, Any]] = []
    if isinstance(topic, dict):
        subs = topic.get("subsections", [])
    else:
        subs = getattr(topic, "subsections", [])
    for sub in subs:
        if isinstance(sub, dict):
            sub_id = sub.get("id", "")
            blocks = sub.get("blocks", [])
        else:
            sub_id = getattr(sub, "id", "")
            blocks = getattr(sub, "blocks", [])
        for bi, b in enumerate(blocks):
            if isinstance(b, dict):
                btype = b.get("type", "paragraph")
                text = b.get("text", "")
            else:
                btype = getattr(b.type, "value", b.type) if hasattr(b, "type") else "paragraph"
                text = getattr(b, "text", "")
            if btype != "paragraph":
                continue
            if not text or len(text.strip()) < 20:
                continue
            candidates.append({
                "subsection_id": sub_id,
                "block_index": bi,
                "text": text.strip(),
            })

    if not candidates:
        return {"suggestions": []}

    truncated = False
    if len(candidates) > 30:
        truncated = True
        candidates = candidates[:30]

    items_str = "\n".join(
        f"[{i}] (sub={c['subsection_id']}, block={c['block_index']}) {c['text'][:500]}"
        for i, c in enumerate(candidates)
    )

    prompt = (
        "Eres un editor pedagogico. Te paso N parrafos de un curso. "
        "Identifica cuales encajan claramente como uno de estos tipos visuales:\n\n"
        "- callout_key: definiciones, conceptos centrales que el alumno DEBE retener\n"
        "- callout_alert: riesgos serios, prohibiciones, errores graves a evitar\n"
        "- callout_warn: precauciones moderadas, advertencias suaves\n"
        "- callout_success: buenas practicas, recomendaciones, casos correctos\n"
        "- quote: texto literal de leyes, articulos, citas textuales con fuente\n\n"
        "NO transformes parrafos genericos: solo los que CLARAMENTE encajan.\n"
        "Puedes proponer una pequena reescritura del texto (mas conciso) o "
        "dejarlo igual.\n\n"
        "Responde EXCLUSIVAMENTE con JSON, sin texto antes ni despues:\n\n"
        "{\n"
        '  "suggestions": [\n'
        '    {\n'
        '      "candidate_index": 0,\n'
        '      "suggested_type": "callout_key",\n'
        '      "suggested_text": "Texto reescrito o el mismo",\n'
        '      "reason": "frase breve (max 15 palabras)"\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Si ninguno encaja, devuelve suggestions: [].\n\n"
        f"Parrafos candidatos:\n{items_str}"
    )

    ok, response = _call_api(prompt, max_tokens=4000)
    if not ok:
        logger.warning(f"enrich_topic_with_callouts fallo: {response}")
        return None
    data = _parse_json_response(response)
    if not isinstance(data, dict):
        return None
    raw_suggestions = data.get("suggestions", [])
    if not isinstance(raw_suggestions, list):
        return None

    valid_types = {
        "callout_key", "callout_alert", "callout_warn", "callout_success", "quote",
    }
    cleaned: List[Dict[str, Any]] = []
    for s in raw_suggestions:
        if not isinstance(s, dict):
            continue
        try:
            ci = int(s.get("candidate_index", -1))
        except (TypeError, ValueError):
            continue
        if ci < 0 or ci >= len(candidates):
            continue
        suggested_type = s.get("suggested_type", "")
        if suggested_type not in valid_types:
            continue
        suggested_text = (s.get("suggested_text") or candidates[ci]["text"]).strip()
        cleaned.append({
            "subsection_id": candidates[ci]["subsection_id"],
            "block_index": candidates[ci]["block_index"],
            "current_type": "paragraph",
            "suggested_type": suggested_type,
            "current_text": candidates[ci]["text"],
            "suggested_text": suggested_text,
            "reason": str(s.get("reason", "")).strip()[:200],
        })
    return {"suggestions": cleaned, "truncated": truncated}


# ============================================================
# DETECCION DE COPYRIGHT EN IMAGENES (v0.5 Fase 5, vision)
# ============================================================

def detect_copyright_risk(image_path: str | Path) -> Optional[Dict[str, Any]]:
    """Analiza una imagen con Claude Vision y evalua riesgo de copyright.

    Detecta: logos, capturas de webs/apps, personas identificables,
    obras de arte, marcas de agua, contenido editorial.

    Devuelve dict con risk_level, concerns, summary, recommendation.
    None si no hay clave.
    """
    if not is_available():
        return None
    path = Path(image_path)
    if not path.exists() or not path.is_file():
        return None
    ext = path.suffix.lower().lstrip(".")
    mime_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "gif": "image/gif", "webp": "image/webp"}
    mime = mime_map.get(ext)
    if not mime:
        return None
    try:
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    except Exception:
        return None
    if len(b64) > 6_500_000:
        return None

    image_parts = [{
        "type": "image",
        "source": {"type": "base64", "media_type": mime, "data": b64},
    }]
    prompt = (
        "Analiza esta imagen y evalua el riesgo de problemas de copyright "
        "si se usa en un curso e-learning de uso no estrictamente personal.\n\n"
        "Vectores de riesgo:\n"
        "1. Logos / marcas comerciales visibles\n"
        "2. Captura de pantalla de web, app o software reconocible\n"
        "3. Personas identificables (riesgo de derechos de imagen)\n"
        "4. Reproduccion de obra de arte, foto famosa o ilustracion profesional\n"
        "5. Marca de agua de bancos de imagenes (Shutterstock, Getty, Alamy...)\n"
        "6. Captura de libro, revista o medio editorial\n\n"
        "Nivel de riesgo:\n"
        "- low: imagen generica, dibujo simple, foto del autor sin elementos identificables\n"
        "- medium: foto con personas, logos pequenos, aspecto profesional no atribuible\n"
        "- high: logos prominentes, captura de web reconocible, foto editorial, marca de agua\n\n"
        "Responde SOLO con JSON, sin texto antes ni despues:\n\n"
        "{\n"
        '  "risk_level": "low",\n'
        '  "concerns": ["Lista de elementos detectados"],\n'
        '  "summary": "Frase breve (max 25 palabras) para mostrar al usuario.",\n'
        '  "recommendation": "Accion concreta sugerida (max 20 palabras)."\n'
        "}"
    )

    ok, response = _call_api(prompt, max_tokens=600, image_parts=image_parts)
    if not ok:
        logger.warning(f"detect_copyright_risk fallo: {response}")
        return None
    data = _parse_json_response(response)
    if not isinstance(data, dict):
        return None
    risk = data.get("risk_level", "").lower()
    if risk not in {"low", "medium", "high"}:
        risk = "medium"
    concerns = data.get("concerns", [])
    if not isinstance(concerns, list):
        concerns = []
    return {
        "risk_level": risk,
        "concerns": [str(c)[:150] for c in concerns][:5],
        "summary": str(data.get("summary", ""))[:300],
        "recommendation": str(data.get("recommendation", ""))[:300],
    }

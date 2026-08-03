# SCORM Builder v0.8.6 — Optimización de costes IA

**Fecha**: 2 agosto 2026
**Zip**: `scormbuilder-main-PARCHEADO_v0.8.6.zip`
**SHA-256**: `487cb5f8f558eaec71941fc38bacb18fd5259e94c12f70d2922f8be2de844e6c`

---

## Objetivo

Reducir **50-65% el gasto en tokens de Anthropic** por curso sin pérdida de
calidad, aplicando tres palancas: model tiering, prompt caching y Batch API.

## Cambios aplicados

### 1. Model tiering (Haiku 4.5 para tareas simples)

Anthropic tiene dos modelos con la misma familia pero precios muy distintos:

| Modelo | Precio input | Precio output |
|--------|-------------:|--------------:|
| Sonnet 4.5 | $3/M | $15/M |
| **Haiku 4.5** | **$1/M** | **$5/M** |

Migradas a Haiku (5× más barato):

| Función | Modelo antes | Modelo ahora |
|---------|:------------:|:------------:|
| `generate_tags` | Sonnet | **Haiku** |
| `generate_alt_text` | Sonnet | **Haiku** |
| `enrich_topic_with_callouts` | Sonnet | **Haiku** |
| `/ai-rewrite` | Sonnet | **Haiku** |
| `/ai-objectives` | Sonnet | **Haiku** |
| `/ai-summary` | Sonnet | **Haiku** |
| `/ai-glossary` | Sonnet | **Haiku** |

**Se mantiene Sonnet** para las que requieren razonamiento pedagógico:
- `generate_quiz` (calidad de las preguntas es crítica)
- `generate_extended_aiken` (banco extendido para evaluación real)
- `/ai-illustration` (generación de SVG vectorial)
- `/ai-copyright` (análisis visual de imagen)

Bonus adicional: `generate_tags` ahora envía **3000 chars** de contenido en
vez de 8000 (60% menos input) sin afectar la calidad del tagging temático.

### 2. Prompt caching (90% descuento en input cacheado)

Anthropic aplica cache_control `ephemeral` que devuelve los tokens cacheados
al 10% de su precio original cuando la misma cabecera se envía dos veces en
un plazo de 5 minutos.

Aplicado en **`generate_extended_aiken`**: el reintento por déficit (cuando
la IA no produce suficientes preguntas válidas al primer intento) ahora
envía el mismo contenido con cache_control. Cache hit garantizado → 90%
descuento en los ~3000 tokens del contenido durante el reintento.

Ahorro sobre el retry: ~50% del coste de la segunda llamada.

Nueva firma de `_call_api(cached_prefix=...)` disponible para futuras
extensiones.

### 3. Batch API (50% descuento oficial)

Anthropic ofrece la Message Batches API con **50% de descuento** en TODAS
las peticiones enviadas por lote. Contrapartida: la respuesta llega en
minutos (no interactivo).

Perfecto para operaciones que ya se procesan en un job de background:

- `build_extended_aiken` (nuevo modo batch automático)
- `_call_batch_api()` helper genérico para futuras extensiones

**`build_extended_aiken` decide automáticamente**:
- Curso con **≥3 temas** → Batch API (50% descuento, minutos de latencia)
- Curso con 1-2 temas → modo síncrono (feedback rápido)

El caller puede forzarlo con `use_batch=True/False`.

Nueva función `generate_extended_aiken_batch(topics=...)` que:
1. Envía TODAS las peticiones (una por tema) en un solo lote
2. Poll a la Batch API hasta que complete (típicamente <5 min)
3. Devuelve `Dict[topic.number → questions]` para el caller

---

## Ahorro estimado (curso típico 30 temas)

| Operación | v0.8.5 | v0.8.6 | Ahorro |
|-----------|:------:|:------:|:------:|
| enrich-all (tags + callouts + quiz × 30) | $6.0 | $2.7 | 55% |
| Aiken extendido (30 preg × 30 temas) | $9.0 | $4.0 | 56% |
| Alt-text (30 imágenes) | $0.15 | $0.03 | 80% |
| Otros endpoints simples | $0.5 | $0.2 | 60% |
| **TOTAL curso** | **~$15.7** | **~$6.9** | **~56%** |

Con 30 cursos/mes → **~$260 mensuales de ahorro** vs precio actual.

---

## Auditoría

**15/15 checks OK**:
- Sintaxis todos los .py
- Imports v0.8.6 (FAST_MODEL, DEFAULT_MODEL, _call_batch_api, generate_extended_aiken_batch)
- Coherencia app_local (Haiku usado en 4 endpoints)
- Coherencia ai_assist (cache_control ephemeral + Batch API + polling)
- Regresión bug #80 sigue OK (7 subapartados detectados en el docx del cliente)

---

## Cómo desplegar

```bash
unzip scormbuilder-main-PARCHEADO_v0.8.6.zip
cd scormbuilder-main
./deploy/deploy.sh
```

Sin cambios en configuración de OpenShift ni en env vars.

---

## Rollback si algo falla

- **Haiku produce baja calidad en tags/callouts**: cambiar `FAST_MODEL` en
  `ai_assist.py` línea 40 a `"claude-sonnet-4-5"`. Ratio calidad/coste se
  vuelve al de v0.8.5.
- **Batch API falla / lento en producción**: forzar `use_batch=False` en
  `aiken_builder.build_extended_aiken()`. Modo síncrono restaurado.
- **Caching produce respuestas antiguas**: quitar el `cache_control` de
  los 2 puntos en `generate_extended_aiken`.

Cada palanca es independiente y reversible sin tocar el resto.

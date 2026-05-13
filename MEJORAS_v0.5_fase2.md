# MEJORAS v0.5 — Fase 2 (cumplida)

> Esta fase añade el "cerebro IA" del SCORM Builder y dos formatos nuevos
> de salida. Todo es **opcional**: sin clave de API, las funciones IA se
> desactivan limpiamente; sin querer usar IMS CP, el SCORM 1.2 sigue siendo
> el formato por defecto.

## Resumen ejecutivo

La Fase 1 dejó los SCORMs publicables y accesibles. La Fase 2 los hace
**rápidos de producir**: la IA propone tags y quizzes, y aparece un formato
extra (IMS CP) para complementar el SCORM en Moodle. También se añade el
banco Aiken extendido para cuestionarios separados.

| Función | Sin clave IA | Con clave IA |
|---|---|---|
| Tags por tema | Vacíos por defecto, editables a mano en el JSON | La IA propone 5-8 etiquetas, las editas y se inyectan en manifest + chips |
| Alt-text de imágenes | El usuario lo escribe; el validador bloquea si falta | La IA lo sugiere a partir de la imagen (visión) |
| Quizzes mixtos (test/V-F/huecos) | Soporte de render presente; preguntas las escribes tú | La IA las genera según config (final / por subapartado / mixto) |
| Banco Aiken extendido | Solo las preguntas del quiz embebido | Banco amplio de 30-50 preguntas por tema |
| IMS Content Package | Disponible siempre | — |

---

## Qué se ha hecho

### 1. Módulo central `ai_assist.py`

Centraliza todas las llamadas a la API de Anthropic con `urllib` (cero
dependencias externas nuevas). Cinco funciones públicas:

- `is_available()` — ¿hay `ANTHROPIC_API_KEY`?
- `generate_tags(topic, n=6)` — 5-8 etiquetas temáticas.
- `generate_alt_text(image_path)` — alt-text descriptivo (vision API).
- `generate_quiz(topic, config)` — preguntas mixtas según `QuizConfig`.
- `generate_extended_aiken(topic, n=30)` — banco amplio para Moodle.

Si no hay clave, todas devuelven `None` sin romper nada.

### 2. Etiquetas (tags) por tema

`Topic.tags: List[str]` — entre 0 y 8 etiquetas.

Se inyectan **dos veces**:

- **En el manifest SCORM** como `<imsmd:keyword>` (Moodle las indexa para
  búsqueda):
  ```xml
  <imsmd:keyword>
    <imsmd:langstring xml:lang="es">gestion deportiva</imsmd:langstring>
  </imsmd:keyword>
  ```
- **En el HTML del SCORM** como chips visibles bajo el título del tema
  (con `aria-label="Etiquetas del tema"`).

**Cómo asignarlas**:

- **A mano**: editas la estructura JSON desde la app, campo `tags` del topic.
- **Con IA**: nuevo endpoint `POST /api/curso/<token>/ai-tags` con body
  `{"topic_index": 0, "n": 6}`. Devuelve y persiste.

### 3. Quizzes con tipos mixtos

`Question` ahora tiene `qtype`:

- `"multiple_choice"` — test de N opciones, una correcta (default, retrocompatible)
- `"true_false"` — verdadero / falso (`options=["Verdadero", "Falso"]`)
- `"fill_in"` — completar hueco (el `text` lleva `___` donde va la palabra,
  las `options` son las posibles)

El **renderer** los pinta correctamente:
- V/F: dos opciones grandes en fila, sin prefijo A/B.
- fill_in: muestra el enunciado con un `<span class="fill-blank">` visible
  donde va el hueco.

### 4. Preguntas intercaladas por subapartado

`Topic.inline_quiz: Dict[sub_id, List[Question]]`.

Una pregunta (o varias) **al final de cada subapartado**, con feedback inmediato
(sin afectar a la nota final). El alumno responde, pulsa "Comprobar" y le
aparece la explicación.

JS nuevo (`evaluarInline`) gestiona la lógica.

### 5. Configurador de quiz por tema

Nuevo endpoint `POST /api/curso/<token>/ai-quiz-config`:

```json
{
  "topic_index": 0,
  "location": "mixed",
  "types": ["multiple_choice", "true_false", "fill_in"],
  "n_questions": 8
}
```

Donde `location` es:
- `"final"` — bloque único al final del tema (clásico)
- `"per_subsection"` — una pregunta de repaso por cada subapartado
- `"mixed"` — repaso por subapartado + bloque final

La IA genera todo según la configuración y se persiste en `structure.json`.

### 6. Exporter IMS Content Package

Nueva función `export_ims_cp(course, htmls, output_zip, recursos_dir=None)`
en `exporters.py`.

Genera un ZIP con:
- `imsmanifest.xml` con namespace `imscp_v1p1` (no SCORM)
- Un HTML por tema, navegables entre sí
- `recursos/` con imágenes y PDFs si los hay
- Tags del curso como `<imsmd:keyword>`

Moodle lo carga como **recurso "Contenido IMS"** (no como SCORM): el alumno
ve el contenido bonito pero **no hay tracking** ni nota. Ideal como
complemento del SCORM real (que sí evalúa).

Endpoint: `POST /api/curso/<token>/export-imscp`.

### 7. Banco Aiken extendido con IA

Nueva función `build_extended_aiken(course, output_dir, n_questions_per_topic=30)`
en `aiken_builder.py`.

Por cada tema, llama a la IA y genera 30-50 preguntas (no las que ya tiene el
quiz embebido, sino MÁS). El resultado son ficheros `aiken_TNN_extendido.txt`
listos para importar en Moodle como **banco de preguntas separado**
(Cuestionario → Importar → formato Aiken).

Endpoint: `POST /api/curso/<token>/ai-aiken-extendido` con `{"n": 30}`.

### 8. Alt-text por IA (visión)

`ai_assist.generate_alt_text(image_path)` envía la imagen a Claude (vision)
y devuelve una frase descriptiva ≤ 20 palabras lista para el atributo `alt`.

Endpoint: `POST /api/curso/<token>/ai-alt-text` con `multipart/form-data`
campo `image`. Devuelve `{"alt": "..."}`.

---

## Endpoints añadidos a `app_local.py`

| Método | Ruta | Función |
|---|---|---|
| POST | `/api/curso/<token>/ai-tags` | Genera y guarda 5-8 etiquetas |
| POST | `/api/curso/<token>/ai-alt-text` | Devuelve alt-text para una imagen |
| POST | `/api/curso/<token>/ai-quiz-config` | Genera quiz por configuración |
| POST | `/api/curso/<token>/export-imscp` | Empaqueta el curso como IMS CP |
| POST | `/api/curso/<token>/ai-aiken-extendido` | Banco Aiken ampliado |

Todos requieren `ANTHROPIC_API_KEY` salvo el de IMS CP. Si falta, devuelven
400 con `{"error": "ANTHROPIC_API_KEY no configurada en el entorno"}`.

---

## Archivos modificados / añadidos

### Nuevos

- `libreria/scorm_builder/ai_assist.py` — módulo centralizado de IA.
- `libreria/tests/test_v05_phase2.py` — 16 tests de regresión de Fase 2.
- `MEJORAS_v0.5_fase2.md` — este documento.

### Modificados

- `libreria/scorm_builder/parser.py`:
  - `Topic.tags: List[str]` (default `[]`).
  - `Topic.inline_quiz: Dict[str, List[Question]]`.
  - `Question.qtype: str` (default `"multiple_choice"`).
  - `to_dict()` actualizado.
- `libreria/scorm_builder/renderer.py`:
  - Chips de tags bajo el título.
  - Render de `qtype` (multiple_choice / true_false / fill_in).
  - Render de `inline_quiz` por subapartado.
  - Nuevo JS `evaluarInline()` para feedback inmediato.
  - CSS para chips, inline-quiz, fill-blank, btn-inline-check.
- `libreria/scorm_builder/packager.py`:
  - `MANIFEST_TEMPLATE` con sección `{keywords}` opcional.
  - `build_scorm_package` inyecta `topic.tags` como `<imsmd:keyword>`.
- `libreria/scorm_builder/exporters.py`:
  - Nueva función `export_ims_cp()`.
- `libreria/scorm_builder/aiken_builder.py`:
  - Nueva función `build_extended_aiken()` que usa la IA.
- `libreria/scorm_builder/api.py`:
  - `course_from_dict()` preserva tags, inline_quiz y qtype.
- `instalador/app_local.py`:
  - 5 endpoints nuevos enumerados arriba.

---

## Tests automatizados

```bash
cd libreria
python -m pytest tests/ -q
# 35 passed in 0.87s
```

Cobertura nueva (Fase 2):
- Tags: serialización, round-trip, render como chips, inyección en manifest.
- Quiz qtypes: render de los tres tipos, fill-blank visible.
- Inline quiz: render, serialización, JS embebido.
- IMS CP: ZIP generado, manifest XML válido, sin namespace SCORM, tags incluidas.
- ai_assist: modo sin clave (devuelve None sin error), helper `topic_to_plain_text`.

---

## Cómo probarlo

### Sin API key (todo funciona menos las funciones IA)

```bash
cd libreria
python -c "
from scorm_builder.parser import parse_docx, Question
from scorm_builder.renderer import render_html
from scorm_builder.themes import get_theme
from scorm_builder.exporters import export_ims_cp
from pathlib import Path

# Carga + asigna tags y quizzes mixtos a mano (lo que haría la IA)
course = parse_docx('../plantilla/test_v05.docx')
course.topics[0].tags = ['demo', 'manual', 'sin ia']
course.topics[0].quiz.append(
    Question(text='V/F: la fase 2 ya está hecha.',
             options=['Verdadero','Falso'], correct_index=0, qtype='true_false')
)
htmls = render_html(course, get_theme('azul'))
export_ims_cp(course, htmls, Path('/tmp/curso_ims.zip'))
print('Listo: /tmp/curso_ims.zip')
"
```

### Con API key configurada

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
cd libreria
python -c "
from scorm_builder.parser import parse_docx
from scorm_builder.ai_assist import generate_tags, generate_quiz, QuizConfig

course = parse_docx('../plantilla/test_v05.docx')
topic = course.topics[0]
print('Generando tags...')
tags = generate_tags(topic, n=6)
print('Tags:', tags)
print('Generando quiz mixto...')
cfg = QuizConfig(location='mixed', types=['multiple_choice','true_false'], n_questions=5)
quiz = generate_quiz(topic, cfg)
print(f'Final: {len(quiz[\"final\"])} pregs, por subapartado: {sum(len(v) for v in quiz[\"by_subsection\"].values())}')
"
```

---

## Pendiente / Fase 3 (cuando lo decidas)

- **UI completa en la app** para los nuevos endpoints (ahora hay que llamarlos
  por API o desde un script). El "panel de configuración de quiz por tema"
  sería un formulario en el editor.
- **Reescritura IA del Word** desordenado para que cumpla la convención
  (`[CLAVE]`, `[ALERTA]`, etc.) antes de empaquetar.
- **TTS integrado** en el reproductor del SCORM.
- **Vista previa en iframe** del SCORM dentro de la app.
- **Plantilla Word "moderna"** descargable con la convención aplicada.
- **xAPI/cmi5** como exporter avanzado.

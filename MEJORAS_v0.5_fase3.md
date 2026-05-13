# MEJORAS v0.5 — Fase 3 (cumplida)

> Esta fase trae la **interfaz de usuario** del editor para los endpoints IA
> que ya implementamos en la Fase 2. Antes los endpoints estaban "ahí pero
> sin botones"; ahora cada uno tiene su lugar visible y usable en el editor.

## Resumen ejecutivo

La Fase 2 dejó los endpoints IA funcionando perfectamente vía API, pero solo
accesibles llamándolos a mano con `curl` o scripts. Esta Fase 3 los conecta
a botones reales en el editor de la app local, con UX coherente con lo que
ya había.

## Qué se ha hecho

### 1. Bloque de etiquetas (tags) por tema

Cada tema del editor muestra ahora un bloque destacado con:

- **Chips de etiquetas existentes**, cada una con su botón `×` para borrarlas
  individualmente (con confirmación visual, sin pop-ups).
- **Input de texto** para añadir etiquetas a mano: escribes, pulsas Enter y
  se añade. Se normaliza automáticamente a minúsculas y se quitan caracteres
  raros, para que coincida con el formato que la IA produce.
- **Botón "🏷 Generar tags con IA"** que llama a `/api/curso/<token>/ai-tags`,
  reemplaza las etiquetas existentes (con confirmación si las había) y
  refresca la vista.

Las etiquetas se guardan al pulsar "💾 Guardar y reempaquetar" y se inyectan
automáticamente como `<keyword>` en el manifest SCORM y como chips visibles
en el HTML del curso (todo esto ya estaba en Fase 2).

### 2. Panel "Asistente IA avanzado" colapsable

Una sección plegada por defecto al final de cada tema, con fondo violeta
claro para distinguirla del resto. Al abrirla aparecen:

#### Configurador de quiz por tipos

- **Ubicación**: select con tres opciones — *Bloque final*, *Una pregunta de
  repaso por subapartado*, *Mixto*.
- **Nº preguntas (bloque final)**: 1-15.
- **Tipos**: checkboxes para test, V/F y completar huecos.
- **Avisos contextuales**: si ya hay preguntas intercaladas, te dice cuántas
  vas a reemplazar.
- **Botón "🤖 Generar quiz con esta configuración"** que llama a
  `/api/curso/<token>/ai-quiz-config` con la config exacta, persiste el
  resultado y refresca la estructura.

### 3. Botones globales en la barra de acciones

Junto a los botones de Glosario y TTS aparecen:

- **"📚 Banco Aiken extendido con IA (30 pregs / tema)"** — confirmación
  previa (porque puede tardar), llama a `/api/curso/<token>/ai-aiken-extendido`
  y muestra al final la lista de ficheros generados.
- **"📦 Exportar como IMS CP (Moodle)"** — genera el paquete IMS Content
  Package y descarga automáticamente. Avisa si hay cambios sin guardar.

### 4. Ruta de descarga unificada

Se ha ampliado `/curso/<token>/export/<kind>` para soportar:

- `html` (ya existía)
- `scorm2004` (ya existía)
- **`imscp`** — devuelve el ZIP IMS CP
- **`aiken-ext`** — devuelve un ZIP con todos los `.txt` Aiken extendidos
  (se crea al vuelo si no existía, comprimiendo lo que haya en
  `aiken_extendido/`)

### 5. Modo "sin API key" funciona limpio

Si no hay `ANTHROPIC_API_KEY` configurada:

- Los botones IA aparecen pero al pulsarlos, el backend devuelve un 400 con
  mensaje claro (`"ANTHROPIC_API_KEY no configurada en el entorno"`).
- El JS muestra una `alert()` con ese error y restaura el botón.
- Lo demás (chips manuales, configurador, IMS CP) sigue funcionando porque
  no requiere IA.

---

## Archivos modificados

### `instalador/app_local.py` (único archivo tocado)

- **`course_edit()`** (renderiza la página del editor):
  - Añade el bloque `<div class="ed-tags-block">` con chips, input y botón IA
    bajo el título de cada tema.
  - Añade `<details class="ed-ai-advanced">` con el configurador de quiz
    (location + tipos + n) al final de cada tema.
  - Añade dos botones globales (Aiken extendido + IMS CP) en la barra final.
- **Handlers JS añadidos** en el `<script>` del editor:
  - `ed-tag-del` → borra una tag concreta.
  - `ed-tag-input` con `keydown Enter` → añade tag manual.
  - `[data-topic-ai="tags"]` → genera tags con IA.
  - `[data-topic-ai="quiz-config"]` → llama al endpoint configurable.
  - `#ed-aiken-ext` → banco Aiken extendido + alerta con lista.
  - `#ed-export-imscp` → genera IMS CP y descarga.
- **CSS añadido** (≈ 130 líneas) para chips, panel asistente, configurador.
- **`course_export_download()`** ampliada para aceptar `imscp` y `aiken-ext`.

### Tests

- `libreria/tests/test_v05_phase3_ui.py` — 9 tests nuevos:
  - El editor muestra el panel de tags, sus chips, input y botón IA.
  - El editor muestra el panel "Asistente IA avanzado" con los tres tipos
    y las tres ubicaciones.
  - Los botones globales (IMS CP + Aiken extendido) están en la barra.
  - Los handlers JS están presentes en el HTML.
  - Las rutas `/export/imscp` y `/export/aiken-ext` responden con 404 si no
    hay archivo aún (no 405 método no permitido).
  - Sin `ANTHROPIC_API_KEY`, el endpoint `ai-tags` devuelve 400 con error
    claro.
  - El endpoint `export-imscp` genera realmente el ZIP y se puede descargar.

---

## Cómo probarlo

```bash
cd scormbuilder-v05/libreria
pip install -e .
python -m pytest tests/ -q
# 44 passed in 2.85s
```

Y para usar la app:

```bash
cd ../instalador
python app_local.py
# Abrir http://localhost:5000
# Registrarse, subir un Word, ir a "Mi biblioteca" → "Editar curso"
# Verás los chips de tags y el panel "⚙️ Asistente IA avanzado"
```

## Capturas de los nuevos elementos

Al abrir el editor de un curso, en cada tema verás (de arriba a abajo):

1. Cabecera con título editable y botones estructurales.
2. Campo de introducción (si lo había).
3. **🆕 Bloque de etiquetas** — chips coloreados + input + botón generar IA.
4. Subapartados con sus bloques.
5. Botones "🎯 Objetivos" y "📝 Resumen" (ya existían).
6. **🆕 Detalles "⚙️ Asistente IA avanzado"** plegable.
7. Quiz (si existía) o botón "🤖 Generar 5 preguntas con IA" (ya existía).

Y abajo del todo, en la barra de acciones globales del curso, ahora hay:

- 💾 Guardar y reempaquetar
- ↺ Descartar cambios
- 📖 Glosario IA del curso
- 🔊 Narración TTS
- **🆕 📚 Banco Aiken extendido con IA**
- **🆕 📦 Exportar como IMS CP**

---

## Pendiente / Fase 4 (cuando lo decidas)

- **Sugerir alt-text con IA** desde el bloque imagen del editor (endpoint
  `ai-alt-text` ya existe en Fase 2, falta solo el botón al lado de cada
  imagen).
- **Reescritura IA del Word desordenado** para aplicar callouts
  automáticamente.
- **Vista previa en iframe** del SCORM dentro de la app, sin tener que
  descargarlo cada vez.
- **Plantilla Word "moderna"** descargable con la convención aplicada.
- **xAPI / cmi5** como exporter avanzado.
- **Validador WCAG bloqueante** como botón en el editor (ahora solo se puede
  activar pasando `strict_wcag=True` al builder).

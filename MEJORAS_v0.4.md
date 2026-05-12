# SCORM Builder v0.4 · Asistente IA, accesibilidad y exports

> Documento de cambios respecto a la v0.3.

---

## ✨ Bloque 1 — Asistente IA en el editor

Botones para reescritura de texto y generación automática de elementos pedagógicos. Todo opcional: si no hay `ANTHROPIC_API_KEY`, los botones aparecen pero responden con un mensaje claro.

### Reescritura inline (botón ✨ en cada bloque)

Cada bloque de texto largo (párrafo, callout, cita, ejemplo) tiene un menú ✨ con 7 modos:

- **Más práctico**: convierte teoría densa en pasos accionables, casos, ejemplos.
- **Más teórico**: contexto académico, marcos conceptuales, profundidad.
- **Más profesional**: tono corporativo neutro, vocabulario sectorial.
- **Lectura fácil**: frases cortas, vocabulario sencillo, accesibilidad cognitiva.
- **Mejorar redacción**: corrige sin cambiar tono ni sentido.
- **Resumir**: condensa en 2-3 frases.
- **Expandir**: desarrolla ideas, añade matices.

Antes de aplicar, se muestra preview con el texto reescrito y confirmación.

### Generación a nivel de tema

- **🎯 Generar objetivos de aprendizaje** — analiza el contenido del tema y propone 3-5 objetivos con verbos medibles ("Al finalizar, serás capaz de identificar…"). Se insertan al inicio del primer subapartado como heading + lista.
- **📝 Generar resumen final** — 4-6 frases que recapitulan el tema. Se inserta al final del último subapartado como callout.

### Generación a nivel de curso completo

- **📖 Generar glosario del curso con IA** — analiza todo el contenido, identifica 8-15 términos clave y los define con base solo en lo que aparece en el curso. Se inserta como un **tema final** ("Glosario") con cada término en su propio callout.

### Endpoints

```
POST /api/curso/<token>/ai-rewrite     {text, tone}
POST /api/curso/<token>/ai-objectives  {topic_index}
POST /api/curso/<token>/ai-summary     {topic_index}
POST /api/curso/<token>/ai-glossary    {}
```

---

## ♿ Bloque 2 — Subtítulos y validador de accesibilidad

### Subtítulos automáticos para vídeos

Nuevo checkbox "🎬 Generar subtítulos automáticos para los vídeos (Whisper)" en el bloque 6 del formulario. Si está activado y `faster-whisper` está instalado:

- Cada vídeo subido como recurso (`mp4`, `webm`, `mov`...) se transcribe automáticamente.
- Se genera un archivo `.vtt` con el mismo nombre base.
- El renderer añade `<track kind="captions" srclang="es" default>` al `<video>`.
- Si el vídeo ya tenía un `.vtt` manual subido por el usuario, no se sobrescribe.

**Activar**: `pip install faster-whisper`. Sin esa dependencia, el sistema lo omite con un aviso pero no rompe nada.

### Validador WCAG 2.1 AA

Nuevo checkbox "♿ Validar accesibilidad WCAG 2.1 AA antes de empaquetar". Comprueba:

- **1.1.1** — Imágenes sin texto alternativo (error).
- **1.2.2** — Vídeos locales sin archivo de subtítulos (warning).
- **1.3.1** — Saltos en jerarquía de encabezados, h3 → h4 sin h3 previo (warning).
- **1.4.3** — Contraste de la paleta: texto/cabecera y texto/cuerpo bajo 4.5:1 (error).
- **2.4.2** — Curso sin título (warning).
- **2.4.6** — Tema sin subapartados (warning).

Los issues se añaden a la lista de avisos del curso con emoji 🔴 (error) o 🟡 (warning). No bloquean la generación, solo informan.

Nuevo módulo: `libreria/scorm_builder/wcag.py` — exporta `validate_course()`, `WCAGReport` y `contrast_ratio()`. Usable también desde código sin la app.

---

## 🏗 Bloque 3 — Modo constructor en la app

El editor pasa de "tocar lo que ya hay" a "construir el curso entero":

### A nivel de bloque (cada elemento dentro de un subapartado)

- **↑ ↓** subir/bajar el bloque dentro del subapartado.
- **🗑** borrar el bloque (con confirmación).

### A nivel de subapartado

- **↑ ↓ 🗑** subir, bajar, borrar.
- **+ Añadir bloque** — desplegable con todos los tipos de bloque disponibles (párrafo, H3, H4, callouts, cita, listas).

### A nivel de tema

- **↑ ↓ 🗑** subir, bajar, borrar tema entero.
- **+ Añadir subapartado** debajo del último.

### A nivel de curso

- **+ Añadir tema nuevo** al final.

Las numeraciones (`1.1`, `1.2`, `2.1`, etc.) se renumeran automáticamente al reordenar/eliminar.

Esto convierte la herramienta de "convertidor de Word" en "creador completo": un usuario podría partir de un Word esqueleto y construir el resto desde la app.

---

## 🎨 Bloque 4 — Voz sintética e ilustraciones IA

### 🎨 Ilustraciones SVG por IA

Botón "🎨 Ilustrar con IA" en cada subapartado. La IA:

1. Lee el contenido del subapartado.
2. Genera un SVG vectorial conceptual con la **paleta del curso aplicada** (no fotografías genéricas).
3. Guarda el archivo en `recursos/ilustracion_T01_01.svg`.
4. Inserta un bloque `[IMAGEN]` al inicio del subapartado apuntando al SVG generado.

Tres estilos disponibles internamente: `flat` (default), `line`, `abstract`. El SVG es vectorial, escala perfectamente, no pesa nada y respeta la marca.

Endpoint: `POST /api/curso/<token>/ai-illustration {topic_index, sub_index, style}`.

### 🔊 Narración TTS

Botón "🔊 Generar narración TTS de todo el curso" en la barra de acciones del editor. La app:

1. Recorre todos los subapartados.
2. Aplana el texto a un guion limpio (título + párrafos + listas).
3. Genera un archivo `.wav` por subapartado usando **pyttsx3** (TTS local offline, sin API keys).
4. Inserta un bloque `[AUDIO]` al inicio de cada subapartado con el archivo correspondiente.

El alumno ve un control de audio integrado en cada subapartado del SCORM con la narración. Útil para accesibilidad y para alumnos que prefieren escuchar.

**Activar**: `pip install pyttsx3`. La calidad es mediocre (TTS clásico de sistema) pero suficiente para empezar y 100% offline. Para calidad premium, el módulo `tts.py` está preparado para sustituirse por ElevenLabs / OpenAI TTS / Azure cambiando una sola función.

Endpoint: `POST /api/curso/<token>/tts`.

---

## 📦 Bloque 5 — Export multi-formato

Dos botones nuevos en la página de detalle del curso:

### 🌐 Exportar como HTML

Empaqueta el curso como **sitio HTML standalone** sin dependencias SCORM:

- `index.html` con portada del curso y tabla de contenidos navegable.
- Un HTML por tema con la misma maquetación del SCORM.
- Llamadas a la API SCORM neutralizadas (no rompen pero no llaman a un LMS).
- Botón flotante "← Índice" para navegar.

Utilidad: subir el curso a una web propia, blog, intranet, sitio comercial, GitHub Pages, etc.

### 📦 Exportar como SCORM 2004

Genera un SCORM 2004 4ª edición:

- Manifest con namespaces 2004 (`adlcp_v1p3`, `imsss`, etc.).
- `<imsss:sequencing>` con `<imsss:objectives>` primarios.
- `mastery` en escala normalizada 0.0-1.0 (en vez del entero 0-100 de SCORM 1.2).

Algunos LMS modernos rechazan SCORM 1.2 — esto resuelve el problema sin tener que regenerar el curso desde cero.

### Endpoints

```
POST /api/curso/<token>/export-html       → genera y devuelve metadatos
POST /api/curso/<token>/export-scorm2004  → genera y devuelve metadatos
GET  /curso/<token>/export/html           → descarga
GET  /curso/<token>/export/scorm2004      → descarga
```

xAPI/cmi5 queda como roadmap para una v0.5 — requiere más infraestructura porque hay que firmar statements y enviarlos en lugar de empaquetar.

---

## 📄 Cambios en archivos

```
libreria/scorm_builder/
  wcag.py          ← NUEVO: validador WCAG 2.1 AA
  subtitles.py     ← NUEVO: TTS de vídeo con faster-whisper (opcional)
  tts.py           ← NUEVO: narración TTS con pyttsx3 (opcional)
  exporters.py     ← NUEVO: HTML standalone + SCORM 2004
  renderer.py      ← <track> de subtítulos en vídeos locales

instalador/
  app_local.py     ← +9 endpoints (4 IA contenido + 1 ilustración + 1 TTS +
                     2 export + 1 descarga export); modo constructor en editor;
                     toggles WCAG/subtítulos en formulario; botones export en detalle
```

---

## 🔌 Dependencias opcionales

Todas las nuevas funcionalidades son **opcionales** — la herramienta sigue funcionando sin ellas, solo dejan de aparecer las opciones correspondientes:

| Funcionalidad | Dependencia | Fallback |
|---|---|---|
| Reescritura, objetivos, resumen, glosario, quiz, ilustraciones | `ANTHROPIC_API_KEY` env var | Botones devuelven 400 con mensaje claro |
| Subtítulos automáticos | `pip install faster-whisper` | Aviso "Whisper no instalado" |
| Narración TTS | `pip install pyttsx3` | Botón muestra error explicativo |
| Validador WCAG | (incluido) | — |
| Exports HTML/SCORM 2004 | (incluido) | — |

---

## ⚠️ Compatibilidad

- Los SCORMs generados con v0.1, v0.2, v0.3 siguen funcionando.
- Los cursos creados antes de v0.3 (sin `structure.json`) no se pueden editar; regenéralos.
- La sintaxis del DOCX es 100% compatible hacia atrás.
- Cuando se exporta a SCORM 2004, el HTML interno sigue usando el SCORM helper de 1.2; en LMS 2004 algunas llamadas fallarán silenciosamente, pero `score.raw` y `lesson_status` se reportan vía la equivalencia común. **Para SCORM 2004 nativo completo (con `cmi.score.scaled`, `cmi.completion_status`, etc.), está pendiente una pasada al SCORM helper en v0.5.**

---

## ✅ Tests realizados

Tests E2E que pasan en `/tmp/test_v04.py`:

1. Endpoints IA bloque 1 sin API key responden 400 con mensaje claro.
2. Validador WCAG se ejecuta sin errores.
3. Export HTML genera ZIP con index + N archivos por tema, con SCORM neutralizado.
4. Export SCORM 2004 genera ZIPs con manifest correcto (sequencing, primaryObjective).
5. La página `/editar` contiene los 14 botones nuevos esperados.

Y los tests de versiones anteriores (`test_v03.py`, `test_bug_fix.py`, `test_scoring.py`) **siguen pasando sin regresiones**.

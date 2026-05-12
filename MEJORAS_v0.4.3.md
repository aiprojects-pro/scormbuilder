# Mejoras v0.4.3 — Rediseño del panel de generación

Esta versión rediseña por completo la pantalla principal tras el login,
añade subida masiva, selector de versión SCORM, panel de tracking y
selector de recursos auto-generables.

## Cambios en la interfaz (lo que ves al entrar)

Tras hacer login, la página principal ahora se divide en bloques numerados
del 0 al 9, en este orden:

**Bloque 0 — Cabecera "Crear un nuevo curso"**: lo primero que ves.
Contiene **título del curso** (obligatorio), **duración en horas** y
**autor/entidad**. Visualmente destacado con fondo claro y borde de color.

**Bloque 1 — Modo de subida**: dos tarjetas seleccionables:
- "Un único archivo Word" → un paquete SCORM.
- "Varios archivos (lote)" → un SCORM por archivo, usando el nombre del
  fichero como título de cada paquete. Permite arrastrar muchos .docx a la
  vez y los va apilando en una lista, con botón × para quitar cualquiera.

**Bloque 2 — Documento(s) Word**: zona de drop que alterna su
comportamiento (un archivo o varios) según el bloque anterior. En modo
lote muestra la lista de archivos cargados.

**Bloque 3 — Versión SCORM**: tres tarjetas con descripción breve:
- **SCORM 1.2** — Máxima compatibilidad, lo aceptan todos los LMS.
- **SCORM 2004 (4ª ed.)** — Más datos, informes pedagógicos detallados.
- **⭐ Ambas versiones** (preseleccionada, marcada como recomendada) —
  genera los dos paquetes en el mismo ZIP, sin coste adicional.

**Bloque 4 — Sistema de puntuación**: los sliders de peso visualización vs
quiz (existían ya), con el preview de cálculo en vivo.

**Bloque 5 — ¿Qué información rastrear en el LMS?**: panel completamente
nuevo con 11 checkboxes (los típicamente útiles vienen pre-marcados):
- Completado/no completado ✓
- Puntuación final (0–100%), con campo para el mínimo de aprobado (70 por defecto) ✓
- Aprobado/suspenso ✓
- Tiempo dedicado por sesión ✓
- Guardar progreso entre sesiones (resume) ✓
- Marcador de posición ✓
- Detalle pregunta a pregunta ✓
- Progreso granular (% de avance) — sólo SCORM 2004
- Objetivos de aprendizaje — sólo SCORM 2004
- Tiempo máximo permitido (con campo de minutos, 120 por defecto)
- Limitar intentos (con campo de número, 3 por defecto)

Cada ítem lleva una descripción explicando qué hace y, donde procede,
una etiqueta visual ("imprescindible", "recomendado", "2004 brilla aquí").

**Bloque 6 — Recursos multimedia**: drop zone para subir imágenes,
vídeos, audios, PDFs, etc. que tu Word referencie con `[IMAGEN]`,
`[VIDEO]`… (existía ya).

**Bloque 7 — Recursos extra a generar e incluir**: panel completamente
nuevo con 11 checkboxes (los seguros pre-marcados):
- 📄 PDF de apuntes por tema ✓
- 📝 Banco Aiken (.txt) — importable a Moodle/Canvas ✓
- 🌐 Versión HTML standalone (sin SCORM, para colgar en web propia)
- 📚 Glosario — extrae callouts tipo "concepto clave"
- 🧩 Estructura JSON — para re-importar o auditar ✓
- 📋 README dentro del SCORM con título/horas/autor/fecha/mastery ✓
- 🏆 Plantilla de certificado en PDF (requiere `pip install reportlab`)
- 🗂 Tarjetas Anki (.csv) — las preguntas del quiz como flashcards
- 🎬 Subtítulos auto para vídeos (Whisper, si está instalado)
- ♿ Validación WCAG 2.1 AA ✓
- 🔍 Vista del `imsmanifest.xml` fuera del ZIP para inspeccionar

**Bloque 8 — Marca y colores**: paleta y colores personalizados
(existía).

**Bloque 9 — Generar**: botón de vista previa + botón principal de
generación, con la barra de progreso y la tarjeta de resultado.

## Cambios en el backend

### Endpoint `/api/generar` reescrito

Ahora acepta los nuevos campos del formulario y soporta:

1. **Modo lote**: cuando `upload_mode=batch`, el endpoint itera sobre
   todos los archivos `docx` recibidos y procesa cada uno en su propia
   subcarpeta (`unidad_NN_<nombre_archivo>/`). En modo `single` procesa
   sólo el primero, en `curso/`.

2. **Versión SCORM por curso**: cuando `scorm_version=both` o `2004`,
   además del SCORM 1.2 estándar, llama a `export_scorm_2004` por cada
   tema y deja los ZIPs en `scorm_2004/`. Cuando es `both`, también
   renombra la carpeta de 1.2 a `scorm_1.2/` para que sea inequívoco.

3. **Subcarpeta `extras/` por curso** con los recursos auto-generados que
   pidas: README.txt, estructura_curso.json, glosario.md,
   flashcards_anki.csv, plantilla_certificado.pdf, html_standalone.zip,
   y los `*_manifest.xml` extraídos para inspección.

4. **Avisos contextuales**: si pides certificado y no tienes `reportlab`,
   o pides subtítulos y no tienes `faster-whisper`, te lo avisa por
   pantalla sin romper la generación.

### Nuevas funciones auxiliares

Añadidas a `instalador/app_local.py`:

- `_gen_readme(course_data, num_hours, target)` — ficha del curso en TXT.
- `_gen_json_export(course_data, target)` — volcado JSON completo.
- `_gen_glossary(course_data, target)` — extrae callouts tipo "concepto
  clave" en formato `Término: definición` como glosario markdown.
- `_gen_anki_csv(course_data, target)` — flashcards Anki separadas por
  tabuladores con front/back/tag.
- `_gen_certificate_pdf(course_data, num_hours, target)` — plantilla A4
  apaisada con título, hueco para nombre del alumno, horas y firma.
- `_gen_manifest_preview(scorm_dir, target_dir)` — extrae
  `imsmanifest.xml` de cada ZIP fuera del paquete.

### Nuevos estilos CSS

Añadidos al final de `HOME_EXTRA_CSS`:

- `.card-hero` — la cabecera "Crear un nuevo curso" con fondo gradado.
- `.radio-cards` / `.radio-card` / `.rc-title` / `.rc-desc` / `.rc-badge` —
  las tarjetas seleccionables que sustituyen a los radio buttons feos.
- `.track-grid` / `.track-item` / `.track-title` / `.track-desc` /
  `.track-tag` / `.track-extra` / `.track-inline-input` — la rejilla del
  panel de tracking, con sus inputs inline para mastery/minutos/intentos.
- `.res-grid` / `.res-item` / `.res-title` / `.res-desc` — la rejilla de
  recursos auto-generables.
- `.hint` — texto auxiliar pequeño bajo los campos.

## Limitaciones conocidas

1. **Los toggles de tracking son principalmente informativos.** El wrapper
   SCORM universal (introducido en v0.4.2) ya envía automáticamente todos
   los datos que el LMS acepta: completion, success, score, time, suspend,
   location, interactions, progress (2004). Desmarcarlos no impide que el
   wrapper los envíe, sólo que los pone como "información que decides no
   usar". Marcarlos sirve para que tú sepas qué espera ver en el LMS, no
   para configurar el SCO. `max_time` y `max_attempts` están reconocidos
   en el backend pero todavía no se inyectan en el manifest; queda como
   mejora futura.

2. **El certificado PDF necesita `reportlab`.** Si no lo tienes
   instalado, te aparecerá un aviso pero el resto de la generación
   continúa normalmente. Instálalo con: `pip install reportlab`.

3. **Los subtítulos automáticos necesitan `faster-whisper`.** Mismo
   patrón: aviso si no está, sin romper nada. Instálalo con:
   `pip install faster-whisper`.

4. **El glosario es básico.** Esta versión sólo recoge callouts del tipo
   "concepto clave" de tu Word con formato `Término: definición`. Para
   un glosario generado con IA, ya existe `/api/curso/<token>/ai-glossary`
   que se invoca desde el editor del curso.

5. **HTML standalone:** la función `export_html_standalone` ya existe en
   la librería, pero su comportamiento exacto puede variar; verifica el
   resultado en `extras/html_standalone.zip`.

## Cómo probarlo

1. Instala dependencias mínimas:
   ```bash
   pip install Flask werkzeug python-docx
   ```
   Opcionales para los extras más vistosos:
   ```bash
   pip install reportlab          # para el certificado PDF
   pip install faster-whisper     # para subtítulos automáticos
   ```

2. Arranca la app:
   ```bash
   cd instalador
   python app_local.py
   ```
   Se abre el navegador en `http://localhost:5000`.

3. Crea una cuenta y entra. Verás directamente el nuevo panel.

4. **Prueba modo single**: marca "Un único archivo", arrastra un `.docx`,
   pon título y horas, deja "Ambas versiones" y los recursos por defecto,
   pulsa "Crear paquete(s) SCORM". Te descargas un ZIP con `curso/`
   dentro que contiene `scorm_1.2/`, `scorm_2004/`, `extras/` y `pdfs/`.

5. **Prueba modo lote**: marca "Varios archivos (lote)", arrastra 3-4
   `.docx` distintos, cada uno con su nombre representativo (ej:
   `Tema_01_Politicas_Deportivas.docx`). Genera. El ZIP final contiene
   `unidad_01_*/`, `unidad_02_*/`, etc., y cada subcarpeta tiene su
   propio paquete SCORM con el título tomado del nombre del fichero.

## Archivos modificados

- `instalador/app_local.py`:
  - `HOME_BODY_TEMPLATE` reescrito de cero (cabecera + 9 bloques numerados).
  - `HOME_EXTRA_CSS` ampliado con estilos para los nuevos componentes.
  - 6 funciones auxiliares nuevas (README, JSON, glosario, Anki, certificado,
    manifest preview).
  - `api_generar` reescrito para soportar batch, versión SCORM, tracking y
    selector de recursos.

Ningún cambio en la librería (`libreria/scorm_builder/*`): las correcciones
de v0.4.2 (wrapper SCORM universal, manifest 2004 correcto, suspend bien
gestionado) siguen vigentes y son las que hacen que el SCORM funcione
realmente al subirlo a un LMS.

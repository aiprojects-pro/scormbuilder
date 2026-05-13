# MEJORAS v0.5 — Fase 1 (cumplida)

> Esta versión arregla los problemas críticos detectados en la herramienta
> anterior y prepara la base para las mejoras de IA y formatos que vendrán
> en la Fase 2.

## Resumen ejecutivo

El SCORM que generaba la v0.4 perdía piezas fundamentales del contenido del
Word: las **imágenes incrustadas** se ignoraban, los **hipervínculos** se
convertían en texto plano sin enlace, y el HTML **no cumplía WCAG 2.1 AA**
aunque hubiera un validador. Además, el **PDF de apuntes** se generaba pero
no había forma de descargarlo desde dentro del SCORM.

Esta v0.5 lo arregla todo y deja la base limpia para la Fase 2.

---

## Qué se ha hecho

### 1. Extracción real de imágenes incrustadas

Cuando pegas una imagen en el Word, ahora **se extrae al SCORM** y se muestra
en el sitio donde estaba. Antes solo aparecían las imágenes que llevaban el
prefijo `[IMAGEN]` y una referencia manual a un archivo en `recursos/`. Ahora
las dos formas funcionan:

- **Pegada directamente en el Word**: extracción automática, se vuelca a
  `recursos/docx_img_NNN.png` y se inserta como `<figure><img>` en el HTML.
- **Referenciada con `[IMAGEN] descripción | archivo.png`**: sigue funcionando
  como antes (compatibilidad total).

El **alt-text** se toma del campo "Texto alternativo" de la imagen en Word si
existe; si no, queda como genérico y el validador WCAG lo señala como error.

### 2. Hipervínculos del Word preservados como `<a>` clicables

Antes se perdían todos. Ahora:

- **Hipervínculo en una palabra/frase** (`"consulta el [BOE]"`) → `<a href>`
  con el texto del enlace.
- **URLs sueltas como texto plano** (`"https://wikipedia.org/..."`) →
  autolinking automático.
- **Negrita y cursiva** dentro de los enlaces se preservan.
- Sin doble anidamiento ni HTML roto (testado).

### 3. YouTube / Vimeo → reproductor embebido

Cuando hay un enlace a YouTube o Vimeo en el Word (sea como hipervínculo o
como URL suelta), **se convierte en un `<iframe>` con reproductor**. El
texto del enlace ("ver vídeo") pasa a ser la descripción/título del iframe.

Detecta:
- `youtube.com/watch?v=...`
- `youtu.be/...`
- `youtube.com/shorts/...`
- `vimeo.com/...`

### 4. Botón "Descargar PDF" en la cabecera del SCORM

Visible en la cabecera de cada tema, con icono de PDF y `aria-label`. El PDF
se sigue generando como antes (en `recursos/apuntes_TNN.pdf`) pero ahora **se
puede descargar** desde dentro del SCORM con un clic.

### 5. WCAG 2.1 AA aplicado de verdad al HTML

El validador WCAG ya existía como informe, pero el HTML que se generaba no
cumplía nada en realidad. Ahora sí cumple lo siguiente:

| Pauta WCAG | Implementación |
|---|---|
| **1.1.1** Texto alternativo | `alt` obligatorio en `<img>`; validador bloquea si falta |
| **1.3.1** Estructura semántica | `<main>`, `<nav>`, `<header>`, `<footer>`, `<aside>` |
| **1.4.3** Contraste | Validador comprueba los pares de la paleta |
| **2.1.1** Teclado | `tabindex` correctos, foco visible reforzado |
| **2.4.1** Saltar bloques | Skip-link "Saltar al contenido" |
| **2.4.6** Encabezados | Jerarquía validada y respetada |
| **2.4.7** Foco visible | `:focus-visible` con outline de 3px y offset |
| **3.3.2** Etiquetas en formularios | `<fieldset>/<legend>` en quiz, `<label for>` por opción |
| **4.1.2** Nombre y rol | `role="radiogroup"`, `aria-label`, `aria-live` |
| **2.3.3** Animaciones | `@media (prefers-reduced-motion: reduce)` |
| **1.4.11** Contraste no textual | `@media (forced-colors: active)` |

Además se añadió `title` a todos los `<iframe>`, `role="note"` y `aria-label`
a los callouts, y `aria-live="polite"` al feedback del quiz para que los
lectores de pantalla anuncien los resultados.

### 6. Validador bloqueante opcional

Nueva excepción `WCAGValidationError` y parámetro `strict_wcag=True` en
`build_complete_course`. Si está activo y hay errores bloqueantes (alt vacío,
contraste bajo), **el SCORM no se genera** y se devuelve el informe.

Por defecto sigue siendo `False` (no rompe nada existente), pero la app local
puede activarlo desde un checkbox.

---

## Archivos modificados / añadidos

### Nuevos

- `libreria/scorm_builder/inline.py` — módulo de procesamiento inline (runs,
  hipervínculos, imágenes, autolinking, detección YT/Vimeo).
- `libreria/tests/test_v05_phase1.py` — 19 tests de regresión.
- `plantilla/test_v05.docx` — Word de prueba con todos los casos críticos.
- `plantilla/generar_test_v05.py` — script generador del Word de prueba.
- `MEJORAS_v0.5.md` — este documento.

### Modificados

- `libreria/scorm_builder/parser.py`:
  - `Block` ahora tiene `text_html`, `items_html`, `rows_html`.
  - `CourseStructure` registra `extracted_images_dir` y
    `extracted_image_files`.
  - `parse_docx()` acepta `images_dir` y devuelve también el HTML
    enriquecido. Procesa párrafos, listas, tablas y callouts con
    `process_paragraph_inline()`.
- `libreria/scorm_builder/renderer.py`:
  - Usa `text_html`/`items_html`/`rows_html` cuando están presentes.
  - HTML con skip-link, `<main id="contenido">`, `<fieldset>/<legend>` en
    quiz, `aria-live` en feedback.
  - CSS añadido para foco visible, `prefers-reduced-motion`,
    `forced-colors`, botón PDF.
  - `render_topic()` y `render_html()` aceptan `pdf_filename` /
    `pdf_filenames` para insertar el botón de descarga.
- `libreria/scorm_builder/api.py`:
  - `build_complete_course()` genera los PDFs **antes** del render para
    poder pasar sus nombres al renderer.
  - Añade automáticamente las imágenes extraídas del DOCX a los recursos
    del SCORM.
  - Nuevo flag `strict_wcag`.
  - `course_from_dict()` preserva los campos HTML al deserializar.
- `libreria/scorm_builder/wcag.py`:
  - Nueva `WCAGValidationError` con resumen para mostrar al usuario.
  - `WCAGReport.summary()`.

---

## Compatibilidad con la app local existente

La librería sigue siendo compatible con `instalador/app_local.py` **sin
cambios obligatorios**. Funciona exactamente igual:

- El parser acepta DOCXs viejos sin extras (las imágenes simplemente serán
  cero si no hay).
- Los blocks viejos sin `text_html` se renderizan con escape normal.
- El editor de la app reabre `structure.json` y reescribe SCORMs sin perder
  el formato HTML enriquecido (round-trip testado).
- `strict_wcag` por defecto es `False`; el comportamiento sigue siendo
  "advertir pero no bloquear".

Si quieres aprovechar el flag bloqueante en la app, basta con leerlo de un
checkbox del formulario y pasarlo a `build_complete_course()`.

---

## Tests automatizados

```bash
cd libreria
python -m pytest tests/ -q
# 19 passed in 0.36s
```

Cubren imágenes, hipervínculos, YouTube, autolinking, WCAG (skip-link, main,
fieldset, aria-live, motion), botón PDF, validez del HTML y manifest XML,
round-trip de serialización y el flag `strict_wcag`.

---

## Cómo probarlo

```bash
cd libreria
pip install -e .
python -c "
from scorm_builder.api import build_complete_course
from pathlib import Path

result = build_complete_course(
    docx_path='../plantilla/test_v05.docx',
    output_dir=Path('/tmp/test_scorm'),
)
print(f'Generados {len(result.scorm_zips)} SCORMs')
"
```

Luego sube `/tmp/test_scorm/scorm/*.zip` a tu Moodle como paquete SCORM y
deberías ver:
- La imagen embebida del Word visible.
- Enlaces clicables al BOE y Wikipedia.
- Un reproductor de YouTube en lugar del enlace de texto.
- Un botón "Descargar apuntes (PDF)" en la cabecera.
- El foco se mueve correctamente con TAB (incluido el skip-link).

---

## Lo que viene en la Fase 2

- IA para etiquetas (5-8 por tema, en manifest como `<keyword>` + chips
  visibles, editables).
- IA para quizzes configurables por tema (test, V/F, huecos…).
- IA para alt-text automático de imágenes (resuelve el bloqueo WCAG de
  imágenes sin descripción).
- Exportador IMS Content Package para Moodle.
- Banco Aiken extendido (30-50 preguntas con IA).
- Botón "validación WCAG" en la app, con bloqueante opcional.

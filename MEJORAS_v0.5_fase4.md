# MEJORAS v0.5 — Fase 4 (cumplida)

> Esta fase cierra el ciclo del editor: añade las tres últimas piezas que
> faltaban para que producir un curso sea una experiencia *enteramente
> dentro de la app*, sin necesidad de descargar el SCORM para verlo, sin
> bloqueos por accesibilidad sin manera de resolverlos, y con feedback
> inmediato del validador.

## Resumen ejecutivo

Tras la Fase 3 el editor ya tenía la mayoría de funciones IA expuestas como
botones, pero quedaban tres lagunas importantes:

1. Si una imagen no tenía alt-text, **no había forma rápida** de generarlo
   desde el editor (había que descargar la imagen, subirla aparte al
   endpoint `ai-alt-text` y copiar la respuesta a mano).
2. Para ver cómo había quedado un cambio, había que **guardar, descargar el
   SCORM, subirlo a Moodle** o abrirlo localmente — lento e incómodo.
3. El validador WCAG estaba ahí pero solo se podía activar con
   `strict_wcag=True` al empaquetar; no había **informe visible en el
   editor** que te dijera qué arreglar antes de generar.

Esta Fase 4 lo resuelve.

---

## Qué se ha hecho

### 1. Botón "🤖 Sugerir alt con IA" en cada bloque imagen

Al lado del campo "Pie/Título" de los bloques `IMAGE` del editor aparece
un nuevo botón que:

- Se muestra **solo cuando el src es local** (un fichero en `recursos/`),
  no para imágenes externas con URL `https://`.
- Llama al nuevo endpoint `POST /api/curso/<token>/ai-alt-text-block` con
  el `filename` del bloque.
- El backend envía la imagen a Claude (visión) y devuelve un alt-text
  descriptivo ≤ 20 palabras.
- Si el bloque ya tiene texto, pide confirmación antes de reemplazar.
- Aplica el alt al campo "Pie/Título" y marca el editor como modificado.

### 2. Botón global "🔍 Validar WCAG 2.1 AA"

Junto a Glosario/TTS/Aiken/IMS CP, un nuevo botón que:

- Guarda primero los cambios pendientes (para validar la versión real).
- Llama al nuevo endpoint `POST /api/curso/<token>/wcag-check`.
- Recibe el informe completo (`passes`, `n_errors`, `n_warnings`, `issues[]`).
- Lo muestra en un **modal** con:
  - Resumen en cabecera (verde si pasa, rojo si no).
  - Issues agrupados por localización (Tema → subapartado).
  - Cada issue con su severidad (🔴 error / 🟡 warning / ℹ️ info),
    código WCAG, título y descripción detallada.

### 3. Botón global "👁 Vista previa del SCORM"

Junto a los anteriores, un nuevo botón que:

- Guarda primero los cambios pendientes.
- Abre un **modal grande con un iframe** que carga el HTML del tema
  renderizado directamente desde el servidor.
- Si el curso tiene varios temas, **incluye un selector** para cambiar de
  tema sin cerrar el modal.
- El HTML servido es el mismo que iría en el SCORM (CSS, JS, WCAG, todo),
  pero las rutas a `recursos/` se reescriben para apuntar a una ruta de la
  app que sirve los archivos del curso.

### 4. Endpoints nuevos

| Método | Ruta | Función |
|---|---|---|
| POST | `/api/curso/<token>/wcag-check` | Devuelve el informe WCAG completo en JSON |
| GET | `/api/curso/<token>/preview-html?topic_index=N` | HTML del tema renderizado (text/html) |
| GET | `/curso/<token>/preview-resource/<filename>` | Sirve cualquier fichero de `recursos/` del curso |
| POST | `/api/curso/<token>/ai-alt-text-block` | Alt-text para una imagen ya subida (por filename, no upload) |

### 5. Seguridad

- `preview-resource` valida **path traversal**: rechaza filenames con `/`,
  `..` o secuencias codificadas que intenten salir de la carpeta `recursos/`.
- Todos los endpoints están protegidos por `@login_required` y filtran por
  `user_id` en la consulta SQL.
- El alt-text por filename normaliza el input antes de buscarlo en disco.

---

## Archivos modificados

### `instalador/app_local.py`

- 4 endpoints nuevos (~150 líneas).
- 2 botones globales nuevos en la barra de acciones.
- Botón "Sugerir alt con IA" en el render del bloque imagen.
- 3 handlers JS nuevos (~150 líneas) incluyendo dos funciones que crean los
  modales (`showWcagModal`, `showPreviewModal`).
- ~120 líneas de CSS nuevo para los modales y el panel WCAG.

### `libreria/tests/test_v05_phase4_ui.py`

16 tests nuevos:

| Test | Verifica |
|---|---|
| `wcag_check_devuelve_informe` | El endpoint devuelve issues, marca 1.1.1 si hay imagen sin alt |
| `wcag_check_pasa_si_imagen_tiene_alt` | Tras añadir alt-text, el 1.1.1 desaparece |
| `preview_html_devuelve_html_completo` | El HTML servido tiene DOCTYPE, title y skip-link |
| `preview_html_reescribe_rutas_de_recursos` | `src="recursos/..."` se reescribe correctamente |
| `preview_resource_sirve_imagen` | Devuelve el binario PNG real |
| `preview_resource_404_si_no_existe` | 404 con archivos fantasma |
| `preview_resource_rechaza_path_traversal` | Múltiples vectores bloqueados |
| `preview_html_topic_fuera_de_rango` | 404 si pides tema 99 de un curso con 1 tema |
| `ai_alt_text_block_sin_apikey` | 400 con mensaje claro si no hay key |
| `ai_alt_text_block_rechaza_filename_invalido` | `../`, `\\`, `/` rechazados |
| `ai_alt_text_block_404_si_no_existe` | 404 si la imagen no está en recursos |
| `editor_tiene_boton_wcag_check` | Botón presente en el HTML |
| `editor_tiene_boton_preview` | Botón presente |
| `editor_tiene_boton_alt_ia_en_imagen` | Aparece para imágenes locales |
| `editor_no_muestra_boton_alt_si_url_externa` | Oculto si src empieza por https:// |
| `modal_css_presente` | Las clases del modal están en el CSS embebido |

---

## Tests automatizados

```bash
cd libreria
python -m pytest tests/ -q
# 60 passed in 7.95s
```

Cobertura por fase:

| Fase | Tests | Áreas |
|---|---|---|
| 1 | 19 | Imágenes, hipervínculos, WCAG, PDF, validador estricto |
| 2 | 16 | Tags, qtypes mixtos, inline_quiz, IMS CP, ai_assist sin key |
| 3 | 9 | UI de editor para los endpoints IA |
| **4** | **16** | **Alt-text por bloque, WCAG check, preview iframe, seguridad** |
| **Total** | **60** | |

---

## Cómo probarlo

```bash
cd scormbuilder-v05/instalador
python app_local.py
# Abre http://localhost:5000
# Sube un Word con imágenes, edita el curso, y prueba:
# - "👁 Vista previa del SCORM" → ves el curso renderizado en un modal
# - "🔍 Validar WCAG 2.1 AA" → informe con issues por subapartado
# - "🤖 Sugerir alt con IA" (en cada imagen) → alt descriptivo de Claude Vision
```

---

## Lo que queda para la Fase 5 (si quieres seguir)

- **Reescritura IA del Word desordenado**: la IA aplica `[CLAVE]`, `[ALERTA]`,
  etc. automáticamente a un Word que no sigue la convención. Coste alto pero
  reduciría mucho la fricción cuando el Word viene de terceros.
- **Plantilla Word "moderna" descargable**: un .docx ya formateado con los
  estilos y convenciones aplicados, listo para escribir contenido encima.
- **xAPI / cmi5** como exporter avanzado (alternativa moderna a SCORM, lo
  piden algunos LMS corporativos).
- **Comparador "antes/después" en preview**: ver lado a lado el SCORM antes
  y después de un cambio de la IA.
- **Detección automática de copyright** en las imágenes pegadas en el Word
  (con la IA de visión).

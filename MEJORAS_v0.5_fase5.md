# MEJORAS v0.5 — Fase 5 (cumplida)

> Esta fase añade las cinco últimas mejoras del roadmap. Cierra el ciclo
> del SCORM Builder en v0.5: la app cubre ahora desde la **plantilla
> Word inicial** hasta el **empaquetado cmi5/xAPI** moderno, con
> asistencia IA en cada paso y trazabilidad de cambios (snapshots).

## Resumen ejecutivo

| Mejora | Descripción |
|---|---|
| ✨ **Enriquecer con callouts IA** | La IA analiza párrafos genéricos y propone convertirlos en `[CLAVE]`, `[ALERTA]`, `[CUIDADO]`, `[EXITO]` o `[CITA]`. El usuario aprueba/rechaza una a una en un modal. |
| 📄 **Plantilla Word moderna descargable** | Plantilla `.docx` generada al vuelo con la convención completa: metadatos prellenados, ejemplo de los 5 callouts, imagen, vídeo, tabla, quiz, guía rápida al final. |
| ⚡ **Exporter cmi5 / xAPI** | Alternativa moderna a SCORM. Cada tema = un AU. JS de tracking xAPI integrado (initialized / completed / passed / failed / terminated). |
| 📸 **Comparador antes/después** | Sistema de snapshots: cada cambio destructivo de IA guarda una copia. El modal de Vista previa tiene selector "Versión actual / 📸 snapshot…". |
| ⚠️ **Detección de copyright** | Análisis con Claude Vision: logos, capturas web, personas, obras de arte, marcas de agua. Tres niveles (low / medium / high) con concerns y recomendación. |

---

## 1. Enriquecer con callouts IA

### Backend

- **`ai_assist.enrich_topic_with_callouts(topic)`** — analiza los párrafos
  del tema y devuelve sugerencias estructuradas:

  ```json
  {
    "suggestions": [
      {
        "subsection_id": "l1",
        "block_index": 3,
        "current_type": "paragraph",
        "suggested_type": "callout_alert",
        "current_text": "...",
        "suggested_text": "Texto reescrito (puede ser igual)",
        "reason": "frase breve explicando por qué"
      }
    ],
    "truncated": false
  }
  ```

  Solo sugiere cambios donde el párrafo encaja CLARAMENTE en uno de los
  5 tipos. Limita a 30 candidatos por llamada (marca `truncated: true`).

- **`POST /api/curso/<token>/ai-enrich`** — body: `{topic_index: N}`.
  No modifica nada, solo devuelve sugerencias.

- **`POST /api/curso/<token>/apply-enrich`** — body:
  ```json
  {
    "topic_index": 0,
    "accepted": [
      {"subsection_id": "l1", "block_index": 3,
       "suggested_type": "callout_alert", "suggested_text": "..."}
    ]
  }
  ```
  Aplica solo los cambios aceptados. **Crea snapshot ANTES de aplicar.**
  Devuelve `{"applied": N, "snapshot_id": "..."}`.

### Frontend

- Botón **"✨ Enriquecer con callouts IA"** en cada tema (junto a Objetivos / Resumen).
- Al pulsar, se llama a `ai-enrich` y aparece un modal con todas las sugerencias.
- Cada sugerencia muestra: tipo propuesto (chip de color), razón, texto original (fondo rojo) y propuesto (fondo verde), checkbox para aprobar.
- Botones del modal: "Marcar/desmarcar todas" y "Aplicar seleccionados".
- Al aplicar, recarga la estructura y muestra el `snapshot_id` para que el usuario sepa que puede revertir.

## 2. Plantilla Word moderna

### Backend

- Nuevo módulo **`libreria/scorm_builder/template_builder.py`** con la
  función `build_modern_template(output_path, course_title, author, sector, palette)`.

- Genera un `.docx` con:
  - **Portada de instrucciones** con 6 puntos clave a recordar.
  - **Sección de metadatos prellenada** entre `---` con todos los campos.
  - **Tema 1 de ejemplo** con texto, hipervínculo dentro de palabra
    ("consulta la WCAG 2.1"), los 5 callouts con sus colores, listas
    con viñetas y numeradas, imagen incrustada placeholder, vídeo
    de YouTube por URL plana, tabla con cabecera, y cita textual.
  - **Quiz de 2 preguntas de ejemplo**.
  - **Tema 2 mínimo** (para enseñar la separación entre temas).
  - **Guía rápida al final** con todos los formatos disponibles
    (estructura, callouts, multimedia, quiz, funciones IA disponibles).

- **`GET /plantilla/descargar`** — ruta pública (no requiere login)
  que genera la plantilla al vuelo y la sirve como descarga.

### Frontend

- Enlace **"📥 Descarga la plantilla Word"** en el hint del bloque de
  upload de la página principal: *"¿Sin plantilla? Descarga la plantilla
  Word con la convención aplicada."*

## 3. Exporter cmi5 / xAPI

### Backend

- Nueva función **`exporters.export_cmi5(course, htmls, output_zip, recursos_dir)`**.

- Genera un ZIP con:
  - **`cmi5.xml`** — courseStructure con un `<au>` por cada tema, con
    `moveOn="Passed"` si el tema tiene quiz (debe pasar la nota mínima)
    o `"Completed"` si no.
  - **`tema_NN_<slug>.html`** — uno por tema, con SCORM neutralizado y
    **JS de tracking xAPI integrado** que:
    - Lee parámetros estándar del query string (endpoint, fetch, actor, registration, activityId).
    - Envía `initialized` al cargar la página (con auth token del LRS).
    - Define `window.cmi5Complete(score, passed)` que se invoca desde
      `finalizarTema` y envía `completed` + `passed`/`failed`.
    - Envía `terminated` al cerrar la pestaña.
  - **`recursos/`** — recursos compartidos del curso.

- IDs cmi5 con esquema `urn:cmi5:course:<slug>` y `urn:cmi5:au:<slug>:tNN`
  (no requieren dominio propio).

- **`POST /api/curso/<token>/export-cmi5`** — genera el paquete y lo
  guarda como `curso_cmi5.zip` en la carpeta del curso.

- **`GET /curso/<token>/export/cmi5`** — descarga del paquete generado.

### Frontend

- Botón **"⚡ Exportar como cmi5 / xAPI"** en la barra de acciones
  globales (junto a IMS CP).

### LMS compatibles

Cualquier LMS cmi5-compliant: Moodle 4+ (con plugin), SCORM Cloud,
Watershed, Learning Locker, Saba Cloud, etc.

## 4. Comparador antes/después (snapshots)

### Backend

- Helper **`_save_snapshot(job_dir, label)`** — versiona `structure.json`
  en `snapshots/<timestamp>_<label>.json`. Limita a las 10 últimas.

- **`apply-enrich` crea snapshot** con label `pre_enrich` automáticamente.

- **`GET /api/curso/<token>/snapshots`** — lista las snapshots:
  ```json
  {"snapshots": [{"id": "20260513_115632_pre_enrich", "filename": "...", "size": 12345}]}
  ```

- **`GET /api/curso/<token>/preview-html/<snapshot_id>?topic_index=N`** —
  renderiza el HTML del tema **a partir de la snapshot indicada**, con un
  banner amarillo en la parte superior advirtiendo "📸 Vista de snapshot".
  Validación anti-traversal en el ID.

### Frontend

- El modal de **Vista previa** ahora tiene **dos selectores** en la
  cabecera:
  1. **Selector de tema** (ya existía).
  2. **Selector de versión**: "Versión actual" + lista de snapshots.

- Al cambiar el selector, el iframe se recarga con la URL apropiada.
  Permite ver lado a lado los cambios IA: abres el modal, ves la versión
  actual; cambias a snapshot pre_enrich; comparas.

## 5. Detección de copyright

### Backend

- Nueva función **`ai_assist.detect_copyright_risk(image_path)`** que
  envía la imagen a Claude Vision con un prompt entrenado para detectar:
  1. Logos / marcas comerciales visibles
  2. Capturas de pantalla de webs, apps o software reconocibles
  3. Personas identificables (derechos de imagen)
  4. Reproducciones de obras de arte / fotos famosas
  5. Marcas de agua de bancos de imágenes (Shutterstock, Getty…)
  6. Capturas de libros / revistas / medios editoriales

- Devuelve:
  ```json
  {
    "risk_level": "low" | "medium" | "high",
    "concerns": ["Logo de Adidas visible", "Marca de agua de Getty Images"],
    "summary": "Frase breve para mostrar al usuario.",
    "recommendation": "Acción concreta sugerida."
  }
  ```

- **`POST /api/curso/<token>/ai-copyright`** — body: `{filename: "img.png"}`.
  Valida path traversal (`/`, `..` rechazados).

### Frontend

- Botón **"⚠️ Comprobar copyright"** al lado del botón "Sugerir alt"
  en cada bloque imagen (solo si el src es local, no URL externa).

- Modal con:
  - Cabecera con el nivel de riesgo (verde / amarillo / rojo).
  - Resumen breve.
  - Lista de **elementos detectados** (concerns).
  - **Recomendación** concreta en caja con borde azul.

---

## Archivos modificados

| Archivo | Cambio |
|---|---|
| `libreria/scorm_builder/ai_assist.py` | +`enrich_topic_with_callouts`, +`detect_copyright_risk` (248 líneas) |
| `libreria/scorm_builder/exporters.py` | +`export_cmi5`, +`CMI5_XML_TEMPLATE`, +`CMI5_TRACKING_JS` (~200 líneas) |
| `libreria/scorm_builder/template_builder.py` | **NUEVO** — `build_modern_template` (~230 líneas) |
| `libreria/tests/test_v05_phase5.py` | **NUEVO** — 23 tests |
| `instalador/app_local.py` | +6 endpoints, +3 botones, +2 modales JS, ~120 líneas CSS |
| `MEJORAS_v0.5_fase5.md` | **NUEVO** — este documento |
| `README.md` | Actualizado |

---

## Endpoints nuevos

| Método | Ruta | Función |
|---|---|---|
| POST | `/api/curso/<token>/ai-enrich` | Sugerir callouts |
| POST | `/api/curso/<token>/apply-enrich` | Aplicar callouts aprobados + snapshot |
| POST | `/api/curso/<token>/ai-copyright` | Análisis copyright de imagen |
| POST | `/api/curso/<token>/export-cmi5` | Empaqueta cmi5 |
| GET | `/api/curso/<token>/snapshots` | Lista snapshots |
| GET | `/api/curso/<token>/preview-html/<snap_id>` | Preview de una snapshot |
| GET | `/plantilla/descargar` | Descarga plantilla Word (pública) |
| GET | `/curso/<token>/export/cmi5` | Descarga del paquete cmi5 |

---

## Tests automatizados

```bash
cd libreria
python -m pytest tests/ -q
# 83 passed in 12.25s
```

Cobertura por fase:

| Fase | Tests |
|---|---|
| 1 | 19 |
| 2 | 16 |
| 3 | 9 |
| 4 | 16 |
| **5** | **23** |
| **Total** | **83** |

Cobertura Fase 5:
- Plantilla genera DOCX válido, parseable, con los 5 callouts y endpoint
  de descarga.
- cmi5: genera ZIP válido, XML schema-correcto, HTML lleva tracking xAPI.
- Endpoints sin API key devuelven 400 limpio.
- apply-enrich modifica bloques y crea snapshot.
- apply-enrich rechaza tipos inválidos.
- Lista de snapshots funciona y refleja cambios.
- Preview de snapshot funciona y bloquea path traversal.
- Copyright rechaza path traversal.
- export-cmi5 genera y descarga.
- UI: botones presentes (enrich, copyright, cmi5, selector snapshot,
  enlace plantilla en home).
- ai_assist sin clave devuelve None.

---

## Estado final del proyecto

El SCORM Builder v0.5 es ahora un editor e-learning **completo**:

**Entrada**:
- Word con la convención (con plantilla descargable que la enseña).
- O Word desordenado: la IA lo enriquece automáticamente con callouts.

**Edición asistida**:
- Tags por tema (IA o manual).
- Quiz mixto configurable (test / V-F / huecos, 3 ubicaciones).
- Alt-text de imágenes por IA (visión).
- Detección de copyright en imágenes (visión).
- Reescritura de bloques con distintos tonos.
- Glosario del curso.
- Objetivos y resumen por tema.
- Narración TTS.
- Reversible: snapshots automáticos antes de cambios destructivos.

**Validación**:
- WCAG 2.1 AA con informe detallado por subapartado.
- Vista previa en iframe sin descargar.
- Comparador antes/después con selector de snapshot.

**Salida**:
- SCORM 1.2 (default)
- SCORM 2004
- HTML standalone (sin LMS)
- IMS Content Package (Moodle como contenido IMS)
- **cmi5 / xAPI** (LMS modernos)
- Banco Aiken (preguntas en Moodle)
- Banco Aiken extendido (IA, 30+ preguntas / tema)

---

## Conclusión

Con esta Fase 5 se cumple **todo el roadmap** propuesto al inicio de la
v0.5. La aplicación cubre la creación e-learning de extremo a extremo,
con IA opt-in en cada etapa, formatos de salida modernos y trazabilidad
de cambios. Quedan pulidos y mejoras posibles, pero el flujo principal
está completo.

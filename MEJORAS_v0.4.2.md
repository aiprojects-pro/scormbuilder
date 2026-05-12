# Mejoras v0.4.2 — Corrección crítica de empaquetado SCORM

Esta versión arregla los problemas que hacían que los paquetes no marcaran
completado ni guardaran progreso en el LMS, y hace que el export SCORM 2004
funcione realmente (en v0.4 el manifest era 2004 pero el JS interno hablaba 1.2,
así que silenciosamente no reportaba nada).

## Problemas corregidos

### 1. Wrapper SCORM ahora es universal (1.2 + 2004)

**Antes:** `renderer.py` contenía un wrapper que sólo buscaba `window.API`
(SCORM 1.2) y usaba `LMSInitialize`, `cmi.core.lesson_status`, etc.
Cuando el paquete se subía como SCORM 2004 a un LMS, el LMS exponía
`API_1484_11` (no `API`), el wrapper no encontraba nada, y el contenido
no reportaba nada al LMS. El alumno completaba el curso y el LMS no se
enteraba.

**Ahora:** el wrapper detecta automáticamente qué objeto expone la
ventana padre (`API_1484_11` primero, `API` como fallback) y traduce todas
las llamadas internamente. El mismo HTML funciona en LMS 1.2 y 2004 sin
modificación.

### 2. Mapeo correcto del modelo de datos por versión

| Concepto | SCORM 1.2 | SCORM 2004 |
|---|---|---|
| Estado de finalización | `cmi.core.lesson_status` | `cmi.completion_status` + `cmi.success_status` |
| Puntuación | `cmi.core.score.raw` | `cmi.score.scaled` (0–1) + raw |
| Ubicación | `cmi.core.lesson_location` | `cmi.location` |
| Tiempo de sesión | `cmi.core.session_time` (HHHH:MM:SS.ss) | `cmi.session_time` (ISO 8601 PT#H#M#S) |
| Modo de salida | `cmi.core.exit` | `cmi.exit` |
| Progreso granular | (no existe) | `cmi.progress_measure` |

El wrapper hace este mapeo de forma transparente.

### 3. `cmi.exit = "suspend"` antes de cerrar

**Antes:** se llamaba a `LMSFinish` directamente. Muchos LMS (Moodle entre
ellos) interpretan eso como "fin definitivo": el siguiente intento empieza
desde cero y `suspend_data` se descarta. Por eso "no guardaba el progreso".

**Ahora:** antes de `Terminate`/`LMSFinish`, el wrapper marca
`cmi.exit = "suspend"` si el alumno aún no ha terminado. Si el alumno
ya superó el tema, marca `"normal"` (o `""` en 1.2). El LMS guarda el
estado correctamente y la siguiente entrada retoma donde se quedó.

### 4. Reporte de `cmi.session_time`

El wrapper ahora cronometra el tiempo desde `Initialize` hasta `Terminate`
y lo envía al LMS en el formato apropiado para cada versión. Antes los
informes del LMS mostraban 0 minutos de actividad por alumno.

### 5. Interacciones del quiz reportadas pregunta a pregunta

**Antes:** sólo se reportaba el porcentaje global del quiz.
**Ahora:** cada respuesta del alumno se envía como `cmi.interactions.N.*`
con id, tipo, respuesta dada, respuesta correcta, resultado (correct/
incorrect) y enunciado. Esto permite que los informes del LMS muestren
qué pregunta acertó cada alumno, cuáles fallaron más, etc.

### 6. Búsqueda de API más robusta

`findAPI` ahora busca también en `window.top` y maneja mejor el caso de
`window.opener` cerrado. Funciona en LMS con iframes anidados.

### 7. Diagnóstico en consola

Si `Initialize` falla, el wrapper imprime el código de error en la
consola del navegador (`LMSGetLastError`). Esto facilita depurar por qué
un LMS rechaza la conexión (cuenta caducada, sesión expirada, etc.).

### 8. Manifest SCORM 2004 mejorado

- Añadido namespace `lom` (IEEE LOM) con metadatos básicos.
- Añadido `<adlcp:completionThreshold minProgressMeasure="0.8"/>` para que
  el LMS muestre la barra de progreso.
- Añadido `<imsss:controlMode choice="true" flow="true"/>` para permitir
  navegación libre dentro del SCO.
- Añadido `<imsss:deliveryControls completionSetByContent="true"
  objectiveSetByContent="true"/>` — necesario para que el LMS acepte
  que sea el contenido quien marque la finalización (no la sesión).

### 9. Manifest SCORM 1.2 mejorado

- LOM declarado con prefijo `imsmd:` (sintaxis recomendada en lugar de
  redeclarar default namespace dentro).
- Añadido `<imsmd:identifier>` para que algunos LMS antiguos no se quejen.
- `isvisible="true"` explícito en `<item>`.

## Cómo probar que funciona

1. Genera un paquete con la nueva versión (1.2 y 2004 a la vez):
   ```bash
   scorm-builder generar mi_curso.docx --output salida/
   ```

2. Sube el ZIP a **SCORM Cloud** (https://cloud.scorm.com — cuenta gratis,
   10 cursos/mes). SCORM Cloud es la referencia: muestra cada llamada API,
   qué dato se envía, qué responde el LMS. Es la mejor forma de validar
   un SCORM antes de subirlo a producción.

3. Verás en el panel "Runtime" eventos como:
   - `Initialize("")` → `true`
   - `SetValue("cmi.completion_status","completed")` → `true`
   - `SetValue("cmi.score.scaled","0.85")` → `true`
   - `SetValue("cmi.interactions.0.id","q0")` → `true`
   - `SetValue("cmi.exit","suspend")` → `true`
   - `Commit("")` → `true`
   - `Terminate("")` → `true`

4. Después de hacer el curso, vuelve a abrirlo: debe retomar exactamente
   donde lo dejaste (gracias a `suspend_data` + `cmi.exit=suspend`).

## Archivos modificados

- `libreria/scorm_builder/renderer.py` — wrapper SCORM_API_JS reescrito;
  función `evaluarFinal()` reporta interacciones.
- `libreria/scorm_builder/packager.py` — manifest 1.2 mejorado.
- `libreria/scorm_builder/exporters.py` — `export_scorm_2004` con manifest
  correcto y completionThreshold.

Ningún cambio en la API pública: el CLI y la interfaz web siguen
funcionando igual.

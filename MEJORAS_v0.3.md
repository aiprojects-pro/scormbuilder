# SCORM Builder v0.3 · Sistema de puntuación, edición y vista previa

> Documento de cambios respecto a la v0.2.

---

## 🎯 Sistema de puntuación ponderada

La nota final del SCORM se calcula combinando **dos componentes** con pesos configurables:

```
nota = (peso_visualización × % visto + peso_quiz × % quiz) / 100
```

Donde:

- **peso_visualización** y **peso_quiz** suman 100 (configurables desde la app o el DOCX).
- **% visto** se calcula sobre los subapartados del tema, repartidos equitativamente.
- **% quiz** es el porcentaje de respuestas correctas.

### Cómo se mide "visto"

Cada subapartado se considera visto cuando se cumplen los dos criterios (configurable):

1. **Scroll**: el alumno hace scroll hasta el final del subapartado (`IntersectionObserver`).
2. **Tiempo**: ha permanecido al menos N segundos en el subapartado (configurable, por defecto 10 s).

La estrategia se puede cambiar a "solo scroll" o "solo tiempo" en las opciones avanzadas.

### Cómo se configura

**Desde la app**, hay un nuevo bloque "Sistema de puntuación" con dos sliders sincronizados (mover uno desplaza el otro para que sumen 100), preview en vivo del cálculo y opciones avanzadas.

**Desde el DOCX**, en el bloque de metadatos:

```
---
TITULO: Mi curso
PESO_VISUALIZACION: 40
PESO_QUIZ: 60
TIEMPO_MINIMO: 10
ESTRATEGIA_VISTA: both
MASTERY: 70
---
```

### Casos especiales

- **Tema sin quiz**: el peso del quiz se redistribuye automáticamente al de visualización (100/0). La app emite un aviso.
- **Pesos que no suman 100**: se reescalan proporcionalmente y se emite un aviso.
- **Persistencia entre sesiones**: el progreso se guarda en `cmi.suspend_data` y `cmi.core.lesson_location`. El alumno cierra y al volver retoma exactamente donde estaba con su progreso intacto.

### En el LMS

El SCORM envía:

- `cmi.core.score.raw` — la nota ponderada (0-100).
- `cmi.core.lesson_status` — `passed` si supera mastery, `incomplete` si no, `failed` solo si el alumno se rinde.
- `cmi.core.lesson_location` — id del subapartado donde estaba.
- `cmi.suspend_data` — estado serializado para retomar.

### Barra de progreso para el alumno

El alumno ve una barra sticky arriba del curso con tres líneas:

- **Visualización** — % de subapartados completados.
- **Quiz** — % de aciertos (cuando lo haga).
- **Nota final** — el cálculo ponderado en vivo, en verde cuando supera el mastery.

---

## ✏️ Edición desde la app sin volver al Word

Al generar un curso, ahora se persiste su estructura en un JSON editable. En la página de detalle hay un botón **"Editar contenido"** que abre un editor donde puedes modificar:

- Metadatos (título, autor, mastery, pesos, tiempo mínimo).
- Título e introducción de cada tema.
- Título de cada subapartado.
- Texto de cualquier párrafo, callout, encabezado.
- Pies de imagen / título de vídeos / etc.
- Items de listas.
- **Preguntas del quiz**: enunciado, opciones, respuesta correcta y explicación.

Al guardar, el SCORM se reempaqueta automáticamente con los cambios — sin volver al Word, sin reabrir nada. El ZIP descargable se actualiza al instante.

**Lo que NO se puede editar desde la app** (de momento): tablas y la estructura jerárquica (añadir/borrar subapartados, reordenar). Para esto sigue siendo necesario el Word.

---

## 👁 Vista previa antes de empaquetar

Botón **"Vista previa"** en la página de generación. Sube tu Word, ajusta los parámetros y pulsa el botón: se abre una nueva pestaña con el primer tema ya renderizado, sin necesidad de empaquetar el SCORM ni descargar ZIPs.

Útil para iterar rápido en la paleta, los pesos del sistema de puntuación, los textos de cabecera, etc. Cambias algo, pulsas "Vista previa" otra vez, y ves el resultado en segundos.

---

## 🤖 Generación de quiz con IA *(opcional)*

Si tienes configurada la variable de entorno `ANTHROPIC_API_KEY`, en la página de edición aparecen dos botones:

- **🤖 Generar 5 preguntas con IA** (en temas sin quiz) — analiza el contenido del tema y propone 5 preguntas tipo test con 4 opciones, respuesta correcta y explicación.
- **+ Añadir 5 más con IA** (en temas que ya tienen quiz) — amplía el banco existente.

Las preguntas se inyectan en el editor como cualquier otra pregunta: las revisas, editas o borras a mano, y las guardas con el botón normal.

**Cómo activar**: añade `export ANTHROPIC_API_KEY=sk-...` antes de lanzar la app, o ponla en un `.env` que cargues. Sin API key, los botones de IA no aparecen y el resto de la app funciona igual.

---

## 🐛 Correcciones menores

- Detección de "Quiz", "Test", "Evaluación" como Heading 2 aunque no tengan estilo aplicado (palabra suelta en una línea corta).
- Aviso de redistribución automática para temas sin quiz, claro y por nombre.
- Limpieza del SCORM antiguo al reempaquetar (no se acumulan ZIPs huérfanos).

---

## 📦 Cambios en archivos

```
libreria/scorm_builder/
  parser.py        ← campos de pesos, _normalize_weights, detección de quiz como h2
  renderer.py      ← módulo ProgresoVista en JS, barra UI, IntersectionObserver,
                     setSuspendData, setLocation, setIncomplete, CSS de la barra
  api.py           ← rebuild_from_structure, course_from_dict, parámetros de pesos

instalador/
  app_local.py     ← bloque "Sistema de puntuación" con sliders, vista previa,
                     edición /curso/<token>/editar, /api/preview, /api/curso/<token>/save,
                     /api/curso/<token>/ai-quiz, /api/curso/<token>/structure

docs/
  02_convencion_docx.md  ← claves nuevas del bloque metadatos
```

Y este nuevo documento (`MEJORAS_v0.3.md`).

---

## ⚠️ Compatibilidad

- **Cursos generados con v0.1 o v0.2**: siguen funcionando, pero NO se pueden editar desde la app porque les falta el `structure.json` (que solo se guarda al generar con v0.3+). Para editarlos, regenéralos partiendo del DOCX.
- **DOCX antiguos**: compatibles. Las nuevas claves de metadatos (`PESO_VISUALIZACION`, etc.) son opcionales; si no están, se aplican los defaults.
- **API**: `build_complete_course()` añade nuevos parámetros con default sensato; código viejo sigue funcionando sin cambios.
- **SCORM 1.2**: sigue siendo el target. Los campos extra (`suspend_data`, `lesson_location`) son estándar SCORM 1.2 — funcionan en Moodle, Canvas, BlackBoard y cualquier LMS conforme.

---

## ✅ Tests realizados

Verificación matemática de la fórmula de puntuación con 5 escenarios distintos (pesos 40/60, 50/50, 100/0, 30/70, sin quiz). Todos pasan.

Verificación E2E completa del flujo:

1. Vista previa genera HTML del primer tema con banner, sin empaquetar.
2. Generar persiste estructura editable en JSON.
3. GET `/api/curso/<token>/structure` devuelve la estructura correcta.
4. Página `/curso/<token>/editar` renderiza con botones IA para temas sin quiz.
5. POST de la estructura editada reempaqueta el SCORM con los cambios.
6. Endpoint AI responde 400 con mensaje claro si no hay `ANTHROPIC_API_KEY`.

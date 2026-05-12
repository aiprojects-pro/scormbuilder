# SCORM Builder v0.4.1 · Revisión del modo constructor

> Auditoría y arreglos del modo constructor introducido en v0.4.

---

## 🔍 Problemas detectados

Tras una auditoría sistemática del modo constructor, se identificaron seis rough edges:

1. **Save aceptaba estructuras inválidas** — un curso sin temas, un tema sin subapartados, un subapartado sin bloques o una lista sin items pasaban el guardado y generaban SCORMs degenerados.
2. **Listas no eran completamente editables** — solo se podía cambiar el texto de items existentes; faltaban botones para añadir y borrar items individuales.
3. **`block-add` no incluía tipos multimedia** — image, video, audio, embed, download, resource y example no aparecían en el desplegable de "Añadir bloque".
4. **Sin protección contra pérdida de cambios** — si el usuario navegaba a otra página o cerraba la pestaña con cambios sin guardar, los perdía sin aviso.
5. **Sin botón de "deshacer"** — un click accidental en 🗑 borraba el bloque irreversiblemente.
6. **Bloques solo se añadían al final** — para insertar un bloque entre dos existentes había que añadir al final y subir N veces.

---

## ✅ Arreglos

### 1 · Validación al guardar (frontend + backend)

El endpoint `POST /api/curso/<token>/save` ahora valida:

- El curso debe tener al menos un tema.
- Cada tema debe tener título y al menos un subapartado.
- Cada subapartado debe tener al menos un bloque.
- Las listas (`list_bullet`/`list_number`) deben tener al menos un item con texto.

Si la estructura no cumple, devuelve **HTTP 400** con `validation_errors` (lista de problemas concretos por ubicación). El frontend muestra un diálogo con todos los errores: *"Tema 2 (Aspectos avanzados): debe tener al menos un subapartado"*. Esto lleva al usuario directo al sitio que tiene que corregir.

### 2 · Listas con add/del de items

Cada item de una lista ahora tiene su propio botón 🗑 para borrarlo. Al final de la lista hay un botón **"+ Item"** para añadir uno nuevo. Si se intenta borrar el último item, aparece un aviso pidiendo borrar el bloque entero.

### 3 · Multimedia en "Añadir bloque"

El desplegable de añadir bloque ahora está **agrupado por categorías**:

- **Texto**: párrafo, H3, H4, cita, ejemplo
- **Listas**: lista con puntos, lista numerada
- **Llamadas de atención**: clave, alerta, éxito, cuidado
- **Multimedia**: imagen, vídeo, audio, embed (YouTube/Vimeo), descargable, recurso

Al añadir un bloque multimedia, se crean dos campos: pie/título y URL/archivo. La lista de archivos disponibles está en la carpeta `recursos/` del curso.

### 4 · Aviso de cambios sin guardar

El editor mantiene un flag `dirty` que se activa al:
- Escribir en cualquier input/textarea
- Mover, borrar o añadir cualquier elemento (bloque, sub, tema, item)
- Aplicar una reescritura por IA, generar quiz/objetivos/resumen/glosario, ilustración o TTS

Cuando hay cambios sin guardar:
- Aparece un **indicador amarillo "● Cambios sin guardar"** en la barra de acciones
- Si el usuario intenta cerrar la pestaña o navegar fuera, el navegador muestra el diálogo de confirmación nativo

### 5 · Botón "↺ Descartar cambios"

En la barra de acciones, junto al botón "Guardar", hay un botón "↺ Descartar cambios" que restaura la estructura tal como estaba al cargar el editor (o tras el último guardado correcto). Pide confirmación antes de descartar.

### 6 · Insertar bloque entre dos existentes

Entre cada par de bloques aparece un separador discreto **"+ insertar aquí"** (visible al pasar el ratón). Al pulsarlo, se inserta un párrafo nuevo en esa posición exacta. Si necesitas otro tipo de bloque, lo añades como párrafo y luego cambias el tipo… o mejor, planeamos la mejora:

> **Roadmap**: que el separador "+ insertar aquí" sea también un desplegable con los tipos disponibles, igual que el "+ Añadir bloque" del final.

---

## 📋 Verificación

Tests E2E que pasan en `/tmp/test_constructor.py`:

- **Casos felices**: subir bloque, borrar subapartado, añadir bloque, añadir subapartado, añadir tema, mover tema al final, renumeración automática. El SCORM resultante refleja correctamente todos los cambios estructurales.
- **Casos límite**: borrar todos los subapartados de un tema, borrar todos los temas, lista vacía, tema sin título, subapartado sin bloques. Todos rechazados con HTTP 400 y mensaje específico.
- **UI**: 13 elementos nuevos verificados en el HTML/JS de la página `/editar`.

Sin regresiones en los tests anteriores (`test_v04.py`, `test_v04_ai.py`, `test_v03.py`, `test_bug_fix.py`, `test_scoring.py`).

---

## 🧐 Limitaciones conocidas (no arregladas)

Algunas cuestiones que se documentan honestamente porque arreglarlas a fondo requiere más trabajo del razonable para una revisión:

### IDs de subapartado basados en posición

Cuando se reordena un curso, los IDs de los subapartados (`l1`, `l2`, `l3`...) se reasignan a su nueva posición. Esto significa que si un alumno ya empezó el curso y tiene `cmi.core.lesson_location = "l3"` guardado en su LMS, tras la reedición ese ID puede apuntar a un contenido distinto.

**Recomendación**: si reeditas un curso que ya está en producción, avisa a los alumnos de que reseteen su progreso. Para v0.5 está previsto introducir IDs estables (UUID o slugs no posicionales).

### Tablas no editables

Las tablas se preservan al guardar pero no se pueden editar inline. Para cambiarlas hay que editar el Word original. La razón: una UI decente para tablas (añadir/borrar filas/columnas, edición por celda con tab-navigation, merge de celdas) es un editor en sí mismo. Por ahora el editor muestra "📊 Tabla con N filas. Edita la tabla en el Word original".

### Sin deshacer global (Ctrl+Z)

El botón "↺ Descartar cambios" restaura **todo** al último guardado, no acción por acción. Para un Ctrl+Z real se necesitaría un stack de undo/redo, que es trabajo no trivial cuando hay cambios async (IA, TTS).

### Renderizado completo en cada cambio

Cada acción estructural reescribe el DOM entero del editor. En cursos pequeños esto es invisible, pero en cursos con muchos subapartados puede haber un parpadeo de medio segundo. Para v0.5 está previsto pasar a renderizado incremental por componente.

---

## 📦 Cambios en archivos

```
instalador/app_local.py
  + Validación estructural en course_structure_save (backend)
  + Editor de listas con add/del de items
  + Tipos multimedia + agrupación en desplegable de añadir bloque
  + Insertar entre bloques con data-position
  + markDirty + courseSnapshot + restoreSnapshot
  + beforeunload listener
  + indicador "● Cambios sin guardar"
  + botón "↺ Descartar cambios"
  + Save: muestra validation_errors detallados, no redirige tras guardar (deja al usuario seguir editando)
  + CSS para los nuevos elementos
```

---

## ✏️ Resumen para el usuario

Para alguien que ya conoce el modo constructor de v0.4, los cambios visibles al abrir el editor son:

- En las **listas** ves un 🗑 al lado de cada item y un botón **"+ Item"** al final.
- El desplegable **"+ Añadir bloque"** ahora tiene 4 grupos de tipos (Texto / Listas / Llamadas / Multimedia).
- Entre cada par de bloques hay un separador suave que dice **"+ insertar aquí"** (aparece al pasar el ratón).
- Si tocas algo, aparece un indicador amarillo **"● Cambios sin guardar"** y el navegador te avisará si intentas salir.
- Junto al botón Guardar hay uno **"↺ Descartar cambios"** que revierte al último guardado.
- Si guardas algo inválido (por ejemplo, dejas un subapartado sin bloques), te aparece un diálogo enumerando exactamente qué tienes que arreglar.

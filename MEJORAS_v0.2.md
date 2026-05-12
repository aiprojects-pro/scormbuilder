# SCORM Builder v0.2 · Mejoras y correcciones

> Documento de cambios respecto a la v0.1. Léelo entero antes de actualizar.

---

## 🐛 Bug crítico corregido

### `'NoneType' object has no attribute 'name'`

**Síntoma:** al subir el Word la app mostraba ese error y, aunque después decía "Curso generado correctamente", el ZIP venía vacío y todos los temas aparecían como *"Texto fuera de un tema descartado"*.

**Causa:** el parser accedía a `parrafo.style.name` sin comprobar que `style` puede ser `None` cuando python-docx encuentra párrafos sin estilo asignado (algo común en documentos venidos de PDF o copy-paste). Una sola excepción rompía el bucle entero del parseo.

**Fix:** función helper `_safe_style_name()` que devuelve cadena vacía si el estilo es `None`. Se usa en todos los puntos donde antes se accedía directamente a `.style.name`.

---

## ✨ Funcionalidad nueva

### 1. Recursos multimedia completos en el SCORM

Antes el SCORM solo aceptaba imágenes pegadas en el Word y PDFs autogenerados. Ahora puedes incluir **cualquier recurso que SCORM admita**, referenciado en el Word con una sintaxis simple:

```
[IMAGEN] Pie de imagen | archivo.png
[VIDEO] Título del vídeo | video.mp4
[VIDEO] Charla TED | https://youtu.be/xxxxx
[AUDIO] Pista | audio.mp3
[EMBED] Mapa | https://...
[RECURSO] Plantilla | archivo.xlsx
```

**Lo que se renderiza en el HTML:**

- **`[IMAGEN]`** → `<figure><img src="recursos/archivo.png"><figcaption>Pie</figcaption></figure>`
- **`[VIDEO]` con archivo local** → `<video controls>` con el archivo en `recursos/`
- **`[VIDEO]` con URL de YouTube/Vimeo** → `<iframe>` 16:9 responsive (la URL se convierte automáticamente a embed)
- **`[AUDIO]`** → `<audio controls>`
- **`[EMBED]`** → `<iframe>` genérico
- **`[RECURSO]`** → enlace de descarga estilizado

**Formatos admitidos como recurso adicional:**

- Imágenes: `png`, `jpg`, `jpeg`, `gif`, `svg`, `webp`
- Vídeo: `mp4`, `webm`, `ogv`, `mov`, `m4v`
- Audio: `mp3`, `wav`, `ogg`, `m4a`, `aac`
- Documentos: `pdf`, `xlsx`, `xls`, `pptx`, `ppt`, `doc`, `docx`, `txt`, `csv`
- Otros: `zip`, `json`, `xml`

### 2. Zona de subida múltiple en la app

La página principal ahora tiene **dos zonas de drag & drop**:

1. **Documento Word** (arriba) — un único `.docx`.
2. **Recursos adicionales** (debajo) — múltiples archivos a la vez (arrastra varios o usa el explorador).

Los archivos seleccionados se muestran en una lista con su nombre y tamaño, con botón **×** para quitar cada uno individualmente. Límite total: **500 MB**.

Todos los recursos se empaquetan en una carpeta `recursos/` dentro del SCORM y se declaran automáticamente en el manifiesto `imsmanifest.xml`.

### 3. Sistema de cuentas de usuario

La app ya **no es de un solo usuario**. Ahora soporta múltiples usuarios trabajando en paralelo en la misma máquina:

- **Registro** con email, nombre y contraseña.
- **Login** con sesión persistente.
- **Datos aislados por usuario**: cada uno tiene su carpeta de jobs y su biblioteca propia. Un usuario no ve los cursos de otro.
- **Almacenamiento local**: SQLite en `~/Documentos/ScormBuilder/scormbuilder.sqlite3` con hashes de contraseña Werkzeug (PBKDF2). No sale nada de la máquina.

### 4. Biblioteca "Mis cursos"

Nueva sección **/biblioteca** accesible desde el menú superior. Muestra todos los cursos generados por el usuario en formato galería:

- Tarjeta por curso con título, autor, fecha, tamaño del ZIP y métricas (temas, preguntas, PDFs, recursos).
- Botones **Descargar**, **Detalle** y **Borrar**.
- Los avisos del parseo se conservan y son consultables en el detalle.

Esto resuelve el problema de "no aparece ningún sitio donde ver las descargas".

### 5. Detección automática de temas por patrón de texto

Si el Word no tiene aplicado el estilo `Heading 1`/`Heading 2` (caso del documento que provocó el bug), el parser ahora detecta:

- **Tema** por patrones: `Tema N.`, `Módulo N.`, `Unidad N.`, `Capítulo N.`, `Lección N.`.
- **Subapartado** por patrón `N.M.` (ej. `2.1.`, `3.4.`).

Esto reduce drásticamente los warnings *"Texto fuera de un tema descartado"*.

---

## 🔧 Cambios menores

- **Manifiesto SCORM**: ahora declara automáticamente todos los archivos de `recursos/` con `<file href="...">`. Antes solo declaraba los HTML.
- **Carpeta unificada `recursos/`** dentro del SCORM, en lugar de tener `descargas/` separada. Simplifica las rutas internas.
- **Resolución de colisiones de nombres**: si subes dos archivos con el mismo nombre, se renombra automáticamente con sufijo numérico (`mapa.png`, `mapa_1.png`).
- **Errores en PDFs no abortan el job**: si por algún motivo falla la generación de un PDF de apuntes, ahora se registra como warning y el resto del curso se genera igualmente.
- **Sintaxis `[CALLOUT]` ampliada** con los nuevos prefijos multimedia.

---

## 📦 Estructura del proyecto

Sin cambios en la estructura de carpetas. Los archivos modificados son:

```
libreria/scorm_builder/
  parser.py        ← reescrito (fix bug + multimedia + detección por texto)
  renderer.py      ← reescrito (HTML para los nuevos bloques)
  packager.py      ← reescrito (recursos extra + manifest)
  api.py           ← extendido (nuevos parámetros)

instalador/
  app_local.py     ← reescrito completo (auth + biblioteca + multi-archivo)

docs/
  02_convencion_docx.md  ← actualizado con sintaxis multimedia
```

Y este nuevo documento (`MEJORAS_v0.2.md`).

---

## 🚀 Cómo probarlo

1. **Reinstalar las dependencias** (la app ahora usa `werkzeug`, que viene con `flask`, así que basta con reejecutar el instalador):

   ```bash
   ./instalador/instalar.sh
   ```

2. **Abrir la app** (doble clic en el icono del escritorio o `./abrir_app.sh`).

3. **Registrarte** la primera vez. La pantalla de login te ofrece el enlace.

4. **Subir** el documento Word + arrastrar uno o varios recursos a la zona inferior.

5. **Generar** el curso. Aparecerá automáticamente en **Mis cursos** con botones para descargar/borrar.

---

## ✅ Tests realizados

Se ha verificado end-to-end con un DOCX que reproduce el bug original (sin estilos Heading aplicados, varios párrafos con `style=None`):

- Parser: detecta los 2 temas y subapartados por patrón de texto, no crashea.
- Bloques `[IMAGEN]`, `[VIDEO]`, `[AUDIO]`, `[RECURSO]` reconocidos.
- Registro de usuario, generación con 3 recursos extra y descarga del ZIP final: OK.
- SCORM resultante contiene `imsmanifest.xml`, `index.html`, archivos en `recursos/` y referencias HTML correctas a `<video>`, `<audio>`, `<figure>`.

---

## ⚠️ Compatibilidad

- Los SCORM generados con la v0.1 siguen funcionando igual.
- La sintaxis del Word es **compatible hacia atrás**: documentos que ya funcionaban en v0.1 funcionan igual en v0.2 (solo se han añadido bloques nuevos).
- La base de datos SQLite se crea automáticamente la primera vez que arranca la app.
- Si tenías cursos descargados en local de la v0.1, no se pierden: los archivos siguen donde estaban; simplemente no aparecerán en la nueva biblioteca (que solo lista los generados después del upgrade).

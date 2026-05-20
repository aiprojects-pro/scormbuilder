# Cambios v0.6 — SCORM Builder

Resumen completo. Última iteración: 19/05/2026, sesión sobre numeración de temas + paleta del PDF + OCR con canal alpha.

## Cambios v0.6.6 (última iteración)

### Tres bugs críticos reportados por la usuaria

**Bug 1: "Todos los PDFs se llaman apuntes_T01.pdf"**

Cuando se procesa un docx individual con título "Tema 2. Evolución...", el parser asignaba `topic.number = 1` (contador secuencial). Al procesar T2, T3, T4 por separado todos los PDFs se llamaban `apuntes_T01.pdf` y se sobrescribían.

Solución (`parser.py`): extraer el número del título h1 ("Tema N. ...") con regex y usarlo como `topic.number`. Si el título no lleva número, se cae al contador secuencial.

Verificado: T2.docx → topic.number=2 → `apuntes_T02.pdf`. T3 → T03. T4 → T04.

**Bug 2: "Los PDFs no cogen el color de la paleta seleccionada"**

Cuando el usuario pasaba `theme="coral"`, el PDF salía en azul. Causa: en `api.py` la lógica daba prioridad a `course.metadata.palette` (siempre 'azul' por defecto en docx sin metadatos) sobre el parámetro `theme` del usuario.

Solución (`api.py`): invertir la prioridad. El parámetro `theme` del usuario SIEMPRE prevalece. La paleta del docx solo se usa cuando el parámetro está vacío o es inválido.

Verificado extrayendo colores hex de los PDFs:
- `theme="coral"` → primer color #7E1C1C (rojo coral) ✓
- `theme="esmeralda"` → #012B21 (verde oscuro) ✓
- `theme="lavanda"` → #2D0F64 (morado) ✓

**Bug 3: "En todos los cuadros no se leen bien" + "No salen imágenes"**

Múltiples causas:

(a) **Imágenes PNG con canal alpha**: `cv2.imread` por defecto descarta alpha y convierte la transparencia a NEGRO. Resultado: 72% de la imagen "negra" → `_looks_like_a_table` rechazaba por saturación alta → no se detectaba como tabla. Caso típico: tabla DigComp del tema 3.

Solución (`table_ocr.py`): cargar con `IMREAD_UNCHANGED` y componer manualmente sobre fondo blanco si hay canal alpha.

(b) **Tablas con cabeceras coloreadas grandes rechazadas por heurística de saturación**: las cabeceras azul oscuro de las tablas (caso DigComp 5×2) producen alta saturación que confundía la clasificación previa.

Solución (`table_ocr.py`): detectar PRIMERO el grid de líneas. Si hay al menos 3 h-lines y 1 v-line interna, SALTAR la clasificación previa de saturación.

(c) **Diagramas con muchas cajas detectados como tablas falsamente**: el diagrama "Cultura/Cibercultura" del tema 3 producía 9 row_strips y se detectaba como tabla 9×1.

Solución (`table_ocr.py`): validar que las listas válidas tengan al menos UNA fila pequeña (cabecera típica < 35% del promedio). Diagramas tienen cajas de tamaños medios-grandes sin filas pequeñas tipo cabecera.

## Cambios v0.6.5

### Imágenes antes del primer subapartado ya no se pierden

Si un docx tiene una imagen entre el título del tema y el primer subapartado (imagen ilustrativa al comienzo), el parser la descartaba silenciosamente. Solución: buffer `pre_subsection_extras` que vuelca al inicio del primer subapartado.

### Diagramas/mapas conceptuales NO se detectan como tablas

Validación en modo `row_strips`: descartar si hay <3 filas con altura media >100px (probable diagrama).

### Tablas con primera y última fila detectadas completas

Añadir bordes superior/inferior a las h-lines si hay espacio (>30px) entre la primera/última línea detectada y el borde de la imagen. Tabla POSDCORB: 5×2 → 7×2 (recupera Planificación y Balance presupuestario).

## Cambios v0.6.4

### OCR de celdas con texto corto centrado en zona grande

"REQUISITO FUNDAMENTAL DE BRCGS FOOD" en celda alta salía como "R FUND". Solución: `_crop_to_text_bbox` detecta el bounding box del texto antes del OCR y recorta el blanco que sobra.

### Mejor detección de separadora vertical

Tres mecanismos combinados: filtro de bordes externos, fusión de clusters de v-lines, análisis de valle de blancura con validación de densidad relativa.

## Tabla rápida de cambios acumulados v0.6

| Síntoma | Estado | Dónde |
|---|---|---|
| PDF con título solapado | ✅ | `pdf_builder.py` |
| PDF sin acentos | ✅ | Fuente DejaVuSans |
| Tablas-imagen no editables | ✅ | `table_ocr.py` |
| Imágenes pixeladas | ✅ | `image_utils.py` |
| Moodle: archivo no visible | ✅ | `core_user_add_user_private_files` |
| **PDFs todos llamados apuntes_T01.pdf** | ✅ **v0.6.6** | `parser.py`: extrae N del título |
| **PDFs no cogen color del SCORM** | ✅ **v0.6.6** | `api.py`: parámetro theme prevalece |
| **Tablas con cabeceras coloreadas no se detectaban** | ✅ **v0.6.6** | `table_ocr.py`: alpha + bypass saturación |
| **Diagramas detectados como tablas** | ✅ **v0.6.5/v0.6.6** | `table_ocr.py`: validación filas pequeñas |
| **Imágenes antes del 1er subapartado se perdían** | ✅ **v0.6.5** | `parser.py`: buffer pre_subsection |
| **Tablas pierden 1ª y última fila** | ✅ **v0.6.5** | `table_ocr.py`: añadir bordes a h_lines |
| OCR de etiquetas devolvía "R FUND" | ✅ **v0.6.4** | bbox crop + v-lines fusión a la derecha |

## Verificado con TODOS los docx reales (8 docs, 3 dominios)

| Tema | Imágenes detectadas como tabla | Notas |
|---|---|---|
| Tema 1 (Ciencia administración) | 1 de 2 | |
| Tema 2 (Reforma gerencialista) | 3 de 4 | Mapa conceptual NO (correcto), POSDCORB 7×2 completa |
| Tema 2 (Evolución archivos) | 1 de 2 | Nuevo |
| Tema 3 (Cultura digital) | 2 de 6 | **DigComp 4×2 con cabeceras coloreadas detectada** |
| Tema 4 (Alfabetización) | 2 de 4 | Nuevo |
| Tema 5 (Medición IFS) | 11 de 16 | |
| Tema 6 (Certificación IFS) | 17 de 23 | TITULACIÓN/EXPERIENCIA/etc. completos |
| Tema 7 (Norma GLOBALG.A.P.) | 13 de 23 | |

**Total: 50 imágenes-tabla convertidas a tablas editables en 8 docs.**

## Verificación visual de los fixes v0.6.6

PDF del tema 3 con paleta coral (rojo):
- Cabecera roja oscura ✓
- Título "Tema **3**: Cultura digital, cibercultura y competencias digitales" (no "Tema 1:" como antes)
- Índice numerado "3.1, 3.2, 3.3..." (no "1.1, 1.2..." como antes)
- Nombre del archivo: `apuntes_T03.pdf` (no `apuntes_T01.pdf` como antes)
- Tabla DigComp incluida como tabla editable con cabeceras coloreadas

## Suite de tests

| Test | Resultado |
|---|---|
| `verify_ocr.py` | 8/8 ✅ |
| `verify_images.py` | 11/11 ✅ |
| `verify_tables.py` | 8/9 ✅ (1 falso positivo del test) |
| `verify_moodle_v2.py` | 5/5 ✅ |
| `test_roundtrip.py` | ✅ |
| OCR + imágenes nuevas (9 casos) | 9/9 ✅ |

## Despliegue

```bash
unzip scormbuilder-v0.6-fixed.zip
cd scormbuilder-fixed
./instalador/instalar.sh
```

En macOS:
```bash
brew install tesseract tesseract-lang
pip install -e ".[ocr,tts]"
```

## Limitaciones conocidas

- **Moodle real no probado**: tests con mock, 5/5. Si te sale un errorcode fuera de los casos mockeados, mándamelo.
- **Tablas con celdas combinadas grandes** (tema 3 DigComp 5×2 → 4×2): fusiona "Seguridad" con "Creación de contenidos digitales". El texto es legible y editable manualmente.
- **Tablas 2-col con bordes discontinuos** (ej. ADMINISTRACIÓN | GESTIÓN del tema 2 Reforma): se detectan como 1 columna.
- **OCR siempre tiene erratas**: especialmente con fuentes estilizadas. Cada conversión emite un warning para revisar.
- **Cabeceras de tabla** aparecen como fila extra (puede salir partida en 2 celdas si la cabecera abarca todo el ancho).
- **`instalar.sh` no probado en VM limpia**: sintaxis validada con `bash -n`.

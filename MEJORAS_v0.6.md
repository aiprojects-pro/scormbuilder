# Cambios v0.6 — SCORM Builder

Resumen completo. Última iteración: 19/05/2026, sesión sobre OCR de celdas con texto corto centrado.

## Cambios v0.6.4 (última iteración)

### OCR de celdas con texto corto centrado en zona grande

Problema: una celda como "REQUISITO FUNDAMENTAL DE BRCGS FOOD" centrada en una celda alta (mucho blanco arriba y abajo) salía como "R FUND" porque Tesseract perdía contexto.

Solución (`_crop_to_text_bbox` en `table_ocr.py`):
1. Binarizar la celda invirtiendo.
2. Closing morfológico horizontal para unir caracteres de la misma línea.
3. Detectar bounding box global del texto.
4. Recortar al bbox + 8px de margen.
5. Pasar la región recortada a Tesseract (con padding blanco + upscale adaptativo).

Resultado verificado en imagen 8 del tema 6:
- Antes: `5×6` "TITULA" / "EXPERIENCIA LAB" / "COMPETENCIAS E CATEGORÍ PRODU"
- Ahora: `5×2` confianza 100% — **"TITULACIÓN"** / **"EXPERIENCIA LABORAL"** / **"COMPETENCIAS EN LAS CATEGORÍAS DE PRODUCTOS"**

### Mejor detección de separadora vertical en tablas 2 columnas

Tres mecanismos combinados para detectar la separadora real:

1. **Filtro de bordes externos**: v-lines a menos del 3% del ancho desde un borde se consideran marco, no separadora.
2. **Fusión de cluster de v-lines próximas**: bordes redondeados generan 5 fragmentos de línea vertical seguidos. Se agrupan en un cluster y se queda con la **posición más a la derecha** (la separadora real, las anteriores son ruido).
3. **Análisis de valle de blancura** (cuando los métodos anteriores no detectan separadora): busca el espacio vertical más vacío, con 3 niveles de exigencia:
   - Threshold estricto (0.05): valles 8-40 px
   - Threshold medio (0.10): valles 18-40 px
   - Threshold permisivo (0.15): valles 25-40 px

   Validación final: la franja del valle debe tener **<60% de la densidad media** de la imagen (un valle real está muy vacío frente al resto). En cada fila debe haber texto a ambos lados (>=70% de las filas).

### Regresión cerrada

La imagen "Efectos del Estado social" (1 columna real) se detectaba como `4×2` falsamente por el valle de blancura. Ahora vuelve a `6×1` correctamente porque la franja del falso valle tenía 91% de la densidad media (>60%, descartada).

## Tabla rápida de qué arregla qué (acumulado v0.6)

| Síntoma | Estado | Dónde |
|---|---|---|
| PDF con título solapado en cabecera | ✅ | `pdf_builder.py`: truncado con elipsis a 45 chars |
| PDF sin acentos en algunos textos | ✅ | Fuente DejaVuSans con fallbacks |
| PDF: cabecera de tabla oscura sin texto legible | ✅ | `primary_pale` claro + texto `primary_deep` oscuro |
| PDF: filas de tabla truncadas al inicio | ✅ | Junto a OCR de tablas-imagen, ya no aplican |
| PDF: imágenes pequeñas se agigantaban | ✅ | Solo downscale, máximo 60-85% del ancho |
| PDF: tablas se salían de margen con URLs/identificadores | ✅ | `_force_word_break` + escalado defensivo |
| PDF no se generaba con `<a rel="noopener">` | ✅ | `_strip_html_for_pdf` limpia atributos no soportados |
| Imágenes pixeladas en SCORM | ✅ | `image_utils.py`: upscale auto <600px a 1200px |
| Tablas-imagen no editables | ✅ | `table_ocr.py`: OpenCV + Tesseract español |
| OCR de etiquetas laterales devolvía "R FUND" en vez de texto completo | ✅ | bbox crop + fusión de v-lines a la derecha |
| Detector confundía 1 columna con 2 (falsos positivos) | ✅ | Validación de franja del valle |
| SCORM 2004 no recibía mejoras IA | ✅ | Render con pdf_filenames y audio_filenames |
| Botón audio TTS no aparecía | ✅ | `renderer.py`: botón junto al PDF |
| TTS por subapartado → un audio por tema | ✅ | `tts.py`: `topic_to_text()` |
| Moodle: archivo no aparece en "Archivos privados" | ✅ | `core_user_add_user_private_files` |
| Vista previa sin imágenes tras IA | ✅ | `_resolve_course_resource` busca en 7 ubicaciones |

## Bugs cazados durante el desarrollo

1. **`logger` no definido** en `_moodle_promote_draft_to_private`. Habría petado en producción al primer error de permisos. Corregido.
2. **`_np` vs `np`** en `_detect_grid_lines`. Corregido.
3. **`adaptiveThreshold`** generaba ~250 falsos positivos en zonas blancas. Cambiado a Otsu.
4. **Clustering gap=12** encadenaba todas las líneas. Threshold 60% + gap=8.
5. **OCR perdía calidad con upscaling+Otsu agresivos**. Preprocesado conservador.
6. **Imagen mediana llenaba el ancho del PDF**. Limitado al 85%.
7. **"|" parásitos** al inicio/fin de celdas. Regex de limpieza.
8. **PDF petaba con `<a rel="noopener">`**. Limpieza de atributos no soportados.
9. **`_resolve_course_resource`** solo buscaba en 3 ubicaciones. Ampliado a 7.
10. **Cluster de v-lines fusionado a la media** → separadora en posición errónea. Cambiado a "posición más a la derecha".
11. **Valle de blancura sin validación** → falsos positivos en texto justificado. Validación de densidad de franja.

## Resultados verificados con docx reales del usuario

### Tema 5 (Medición, análisis y mejora)
- 11 de 16 imágenes detectadas como tablas
- Imagen 2 (Auditoría interna): `2×2` confianza 100% con "REQUISITO KO N28 DE IFS" + descripciones

### Tema 6 (Proceso de certificación)
- 17 de 23 imágenes detectadas como tablas
- Imagen 8 (Requisitos auditores): `5×2` con TITULACIÓN, EXPERIENCIA LABORAL, COMPETENCIAS EN LAS CATEGORÍAS DE PRODUCTOS, CUALIFICACIONES, EXPERIENCIA EN AUDITORÍAS — **todas completas**
- Imagen 13/15 (Categorías de producto): `7×5` con texto preciso
- Tablas grandes 10×3 y 11×2 también funcionan

### Tema 7 (Norma GLOBALG.A.P.)
- 16 de 23 imágenes detectadas como tablas
- Estructuras variadas: 7×3, 4×4, 5×2, 4×2

## Suite de tests

| Test | Resultado |
|---|---|
| `verify_ocr.py` | 8/8 ✅ |
| `verify_images.py` | 11/11 ✅ |
| `verify_tables.py` | 8/9 ✅ (1 falso positivo del test) |
| `verify_moodle_v2.py` | 5/5 ✅ |
| `test_roundtrip.py` | ✅ |

## Despliegue

```bash
unzip scormbuilder-v0.6-fixed.zip
cd scormbuilder-fixed
./instalador/instalar.sh   # auto-instala tesseract-ocr-spa, fonts-dejavu-core, extras Python
```

En macOS:
```bash
brew install tesseract tesseract-lang
pip install -e ".[ocr,tts]"
```

## Limitaciones conocidas (honestas)

- **Moodle real no probado**: tests con mock, 5/5. Si te sale un error fuera de los casos mockeados, mándame el `errorcode` exacto.
- **Imágenes con bullets/listas** (ej: tabla con `▶`): se quedan como imagen (no se convierten a tabla). Decisión consciente, riesgo de falsos positivos.
- **OCR siempre tiene erratas**: especialmente con fuentes estilizadas o colores claros sobre fondo claro. Cada conversión emite un warning para que se revise. Erratas típicas que he visto en los docx reales: "FOOD" → "01019)", "AUDITORÍAS" → "AUDITOSLA", "y" → "MM", espacios perdidos.
- **Variabilidad de heurísticas**: el detector está calibrado con tablas tipo Word/PowerPoint con fondo azul claro o blanco. Tablas con fondos muy contrastados, fotos de tablas escaneadas o tablas con celdas combinadas grandes pueden fallar.
- **`instalar.sh` no probado en VM limpia**: sintaxis validada con `bash -n`, ejecución completa no.

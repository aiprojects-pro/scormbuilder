# Guía de instalación

## Requisitos previos

- **Python 3.10 o superior** instalado en tu ordenador.

### Cómo comprobar si tienes Python

Abre tu terminal y escribe:

```bash
python --version
# o en algunos sistemas
python3 --version
```

Si te muestra `Python 3.10.x` o superior, todo bien. Si no:

- **Mac**: instala con Homebrew → `brew install python@3.12`
- **Windows**: descarga el instalador de python.org/downloads (marca la casilla "Add Python to PATH")
- **Linux**: `sudo apt install python3 python3-pip` (Ubuntu/Debian) o equivalente

## Instalación del motor

### Opción A · Desde la carpeta descomprimida (rápido)

1. Descomprime el ZIP del proyecto en una carpeta cualquiera.
2. Abre la terminal en esa carpeta.
3. Ejecuta:

```bash
cd libreria
pip install -e .
```

Esto instala el comando `scorm-builder` en tu sistema.

### Opción B · Desde GitHub (recomendado para mantenerlo actualizado)

```bash
git clone <URL-de-tu-repo>
cd scorm_builder_proyecto/libreria
pip install -e .
```

## Verificar que funciona

```bash
scorm-builder --help
scorm-builder paletas
```

Deberías ver la ayuda y la lista de paletas disponibles.

## Generar tu primer curso

1. Descarga la plantilla DOCX:

```bash
cp plantilla/Plantilla_Curso_SCORM.docx mi_curso.docx
```

2. Ábrela en Word, sustituye el contenido de ejemplo por el tuyo, guarda.

3. Genera el SCORM:

```bash
scorm-builder generar mi_curso.docx --tema azul --output ./mi_curso
```

Se creará una carpeta `mi_curso/` con:
- `scorm/` → archivos ZIP listos para subir al LMS
- `pdfs/` → apuntes descargables
- `aiken/` → bancos de preguntas para importar al LMS

## Validar antes de generar

Si quieres comprobar que el documento sigue la convención antes de generar:

```bash
scorm-builder validar mi_curso.docx
```

Te mostrará la estructura detectada y los avisos.

## Personalizar la paleta

Tres formas:

**1. Paleta predefinida** (más sencillo):

```bash
scorm-builder generar mi_curso.docx --tema crimson
```

Disponibles: `azul`, `crimson`, `teal`, `verde`, `morado`, `naranja`.

**2. Paleta en el documento** (en el bloque de metadatos al inicio del Word):

```
---
TITULO: Mi curso
PALETA: teal
---
```

**3. Colores personalizados desde la línea de comandos**:

```bash
scorm-builder generar mi_curso.docx \
  --color-deep "#1A1A2E" \
  --color-primary "#0F3460" \
  --color-bright "#E94560"
```

## Solución de problemas

### "Command not found: scorm-builder"

El comando no está en tu PATH. Soluciones:

- Cierra y vuelve a abrir la terminal después de instalar.
- En Mac/Linux: prueba con `python -m scorm_builder.cli` en lugar de `scorm-builder`.
- Verifica que estás en el entorno Python correcto.

### "ModuleNotFoundError: No module named 'docx'"

Faltan dependencias. Reinstala:

```bash
cd libreria
pip install -e . --upgrade
```

### El SCORM no funciona en mi LMS

- Comprueba que has subido el ZIP completo, no la carpeta descomprimida.
- Algunos LMS (Moodle viejo) requieren que `imsmanifest.xml` esté en la raíz del ZIP, no dentro de una subcarpeta. Nuestro empaquetador lo coloca correctamente.
- Para validar el SCORM en abstracto (independiente de LMS), usa SCORM Cloud (gratuito): https://cloud.scorm.com

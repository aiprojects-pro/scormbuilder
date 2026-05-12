# Convención DOCX → SCORM

> Este documento define cómo se interpreta un archivo Word para convertirlo en un curso SCORM.
> El cliente debe seguir estas reglas al redactar su contenido.
> La plantilla DOCX rellenable está en `plantilla/Plantilla_Curso_SCORM.docx`.

---

## Filosofía

La convención está diseñada para ser **natural**: el cliente no escribe código ni etiquetas raras. Solo usa los **estilos de Word** habituales (Título 1, Título 2, lista, negrita) y unas **palabras clave reservadas** sencillas.

El parser es **tolerante a fallos**: si algo no encaja con la convención, se incluye como texto plano en lugar de romperse.

---

## Estructura general del documento

Un documento Word puede contener:

1. **Un curso completo** con varios temas → se generan **varios SCORM** (uno por tema), o un único SCORM si se prefiere.
2. **Un único tema** → se genera **un único SCORM**.

El parser detecta automáticamente cuál es el caso según la presencia de varios `Título 1`.

### Niveles de jerarquía

| Estilo de Word | Significado | HTML resultante |
|----------------|-------------|------------------|
| `Título 1` | Título del curso o del tema | `<h1>` (cabecera del módulo) |
| `Título 2` | Subapartado (1.1, 1.2…) | `<h2 id="...">` (entrada del sidebar) |
| `Título 3` | Subsección dentro del subapartado | `<h3>` |
| `Título 4` | Encabezado menor / etiqueta | `<h4>` |
| `Normal` | Párrafo de texto | `<p>` |

**IMPORTANTE**: el cliente debe usar los estilos de Word, no formatear "a mano" con tamaños de letra. La galería de estilos está en la pestaña Inicio de Word.

---

## Formato de texto en línea

| Formato Word | Significado | HTML |
|--------------|-------------|------|
| **Negrita** | Énfasis fuerte | `<strong>` |
| *Cursiva* | Énfasis débil / cita | `<em>` |
| Enlaces | Enlaces externos | `<a>` |
| Listas con viñetas | Lista no ordenada | `<ul><li>` |
| Listas numeradas | Lista ordenada | `<ol><li>` |

---

## Bloques especiales (palabras clave reservadas)

El cliente puede insertar **bloques visuales especiales** escribiendo párrafos que comienzan con una palabra clave entre corchetes. La sintaxis es:

```
[TIPO] Texto del bloque que ocupará varias líneas si hace falta.
Sigue siendo el mismo bloque mientras no haya línea en blanco.
```

### Tipos de bloque disponibles

#### `[CLAVE]` · Concepto clave (azul)

```
[CLAVE] Aquí va una idea importante que el alumno debe retener.
```

→ Se renderiza como callout azul con icono de información.

#### `[ALERTA]` · Aviso o advertencia (rojo)

```
[ALERTA] Cuidado con esta práctica: puede generar consecuencias negativas.
```

→ Callout rojo con icono de exclamación.

#### `[EXITO]` · Buena práctica o confirmación (verde)

```
[EXITO] Esta es la forma correcta de actuar en este caso.
```

→ Callout verde con icono de check.

#### `[CUIDADO]` · Precaución (amarillo)

```
[CUIDADO] Conviene revisar este aspecto antes de continuar.
```

→ Callout amarillo con icono de aviso.

#### `[EJEMPLO]` · Caso práctico

```
[EJEMPLO] Título del caso
Descripción del caso o situación.
[REFLEXION] Pregunta de reflexión opcional.
[ANALISIS] Análisis o solución, que aparecerá desplegable.
```

→ Tarjeta destacada con número, título, descripción, pregunta y análisis colapsable.

#### `[CITA]` · Cita textual o legal

```
[CITA] FUENTE: Artículo 16 de la LOPIVI
"Texto literal de la cita..."
```

→ Bloque tipo cita con etiqueta de fuente.

#### `[DESCARGABLE]` · Recurso descargable

```
[DESCARGABLE] Nombre del recurso | nombre_del_archivo.pdf
```

→ Genera un enlace de descarga si el archivo existe en la carpeta `descargas/` del proyecto.

---

## Sección del Quiz

Al final del documento (o al final de cada tema, si hay varios), el cliente puede incluir las preguntas del test:

```
## Quiz del tema

1. ¿Cuál es la afirmación correcta sobre X?
A. Opción incorrecta primera
B. Opción correcta
C. Opción incorrecta tercera
D. Opción incorrecta cuarta
Correcta: B
Explicación: La opción B es correcta porque...

2. ¿Qué se debe hacer ante una situación Y?
A. Acción incorrecta
B. Acción correcta
C. Acción incorrecta
D. Acción incorrecta
Correcta: B
```

### Reglas del quiz

- Debe estar bajo un `Título 2` que contenga la palabra "Quiz", "Test", "Evaluación" o "Comprueba".
- Cada pregunta empieza con un número seguido de punto (`1.`, `2.`...).
- Las opciones empiezan con `A.`, `B.`, `C.`, `D.`.
- La línea `Correcta:` indica la letra correcta.
- La línea `Explicación:` es opcional.
- Mínimo 4 preguntas, recomendado 8-15.

### Si el cliente no escribe quiz

- Si elige "generar con IA": el motor llama al modelo y produce 10 preguntas a partir del contenido. El cliente las revisa después en la app.
- Si no incluye quiz y no pide IA: el SCORM se genera sin test de evaluación.

---

## Tablas

Las tablas de Word se preservan tal cual. El parser detecta:

- La primera fila como cabecera (`<thead>`).
- Las demás como cuerpo (`<tbody>`).
- Aplica los estilos del CSS automáticamente.

Las tablas no deben tener celdas combinadas complejas (limitación técnica común).

---

## Imágenes

Imágenes pegadas en el Word se extraen y se insertan en el SCORM. Recomendaciones:

- PNG o JPG.
- Resolución máxima 1920px de ancho.
- Peso máximo recomendado: 500 KB por imagen.
- El pie de imagen va en cursiva justo debajo, con el prefijo `Figura: `.

---

## Metadatos del curso

En la primera página del documento, antes del `Título 1`, el cliente puede incluir un bloque de metadatos:

```
---
TITULO: Curso de protección frente al ciberacoso
SUBTITULO: Formación obligatoria · personal docente
AUTOR: Asociación XYZ
SECTOR: educación
GRADO: básico
PALETA: azul
---
```

Si no se incluye, el motor toma valores por defecto y los pide después en la app.

### Paletas predefinidas

- `azul` (por defecto): #0A2540 / #2563EB / blanco
- `crimson`: #A8201A / #FAF6EF / dorado
- `teal`: #1F4E4D / #FAF6EF / dorado
- `verde`: #064E3B / #10B981 / blanco
- `morado`: #4C1D95 / #8B5CF6 / blanco
- `personalizada`: el cliente la configura en la app

---

## Errores comunes y cómo el parser los maneja

| Problema | Comportamiento del parser |
|----------|---------------------------|
| Estilo "Título 1" mal aplicado | Cae a `Normal`, se trata como párrafo |
| Lista anidada con más de 3 niveles | Se aplana a 3 niveles |
| Tabla con celdas combinadas | Se desfusiona automáticamente |
| Imagen rota | Se sustituye por placeholder y aviso |
| Quiz sin "Correcta:" | Pregunta descartada con warning |
| Bloque [TIPO] sin tipo válido | Se trata como párrafo normal |
| Documento sin `Título 1` | Se usa el nombre del archivo como título |
| Caracteres no UTF-8 | Conversión automática a UTF-8 |

El parser **siempre genera un SCORM válido**, aunque emita warnings sobre lo que no ha podido interpretar.

---

## Validación previa

Antes de generar el SCORM, el motor ejecuta un **validador** que muestra al cliente:

- Número de temas detectados.
- Número de subapartados por tema.
- Número de preguntas del quiz.
- Bloques especiales detectados.
- Imágenes encontradas.
- Warnings (cosas que no se han podido interpretar).

El cliente confirma antes de generar.

---

## Ejemplo mínimo válido

```
---
TITULO: Curso de prueba
PALETA: azul
---

# Tema 1. Introducción al concepto

## 1.1. Qué es esto

Este es un párrafo introductorio del subapartado.

[CLAVE] Idea principal que el alumno debe retener.

## 1.2. Cómo se aplica

[EJEMPLO] Caso práctico
Descripción del caso de ejemplo.
[ANALISIS] Análisis del caso.

## Quiz del tema

1. ¿Qué es esto?
A. Una piedra
B. Un curso de prueba
C. Una bicicleta
D. Una manzana
Correcta: B
Explicación: Es claramente un curso.
```

Esto produce un SCORM con 1 tema, 2 subapartados, 1 callout, 1 ejemplo y 1 pregunta de test.

# 🚀 Cómo usar SCORM Builder en 3 pasos

> **No hace falta saber programar ni usar la terminal.**

---

## Paso 1 · Descomprime el archivo

Haz doble clic en `scorm_builder_proyecto.zip` y descomprímelo donde quieras (por ejemplo, en tu carpeta de **Documentos** o en el **Escritorio**).

---

## Paso 2 · Ejecuta el instalador (una sola vez)

Abre la carpeta `scorm_builder_proyecto/instalador/` y haz **doble clic** en el archivo `instalar.sh`.

Se abrirá una ventana negra (terminal) que va mostrando todo lo que está haciendo. Tarda **1-2 minutos**. Cuando acaba, dice:

```
✓ Instalación completada
```

Y se cierra al pulsar Enter.

### ¿No funciona el doble clic?

Si al hacer doble clic no pasa nada, prueba lo siguiente:

1. Haz clic **derecho** sobre `instalar.sh` → **Propiedades** → marca la casilla **"Permitir ejecutar el archivo como un programa"**.
2. Vuelve a hacer doble clic. En algunos sistemas te preguntará si quieres "Ejecutar" o "Ejecutar en terminal". Elige **"Ejecutar en terminal"**.

### ¿Te pide que instales algo?

Si el script dice que falta Python o python3-venv, abre la terminal y ejecuta:

```
sudo apt install python3 python3-venv python3-pip
```

(introduce tu contraseña cuando lo pida) y luego repite el doble clic en `instalar.sh`.

---

## Paso 3 · Abre la app

Después de instalar, tienes **3 formas** de abrir la app:

### Opción A · Desde el escritorio (más fácil)

El instalador te ha creado un icono en el escritorio llamado **"SCORM Builder"**. Haz doble clic.

> Si la primera vez te sale un aviso de "Aplicación no confiable", haz clic derecho sobre el icono → **"Permitir lanzar"** → vuelve a hacer doble clic.

### Opción B · Desde la carpeta del proyecto

Dentro de la carpeta `scorm_builder_proyecto/` hay un archivo llamado `abrir_app.sh`. Haz doble clic en él.

### Opción C · Desde la terminal

```
cd ~/scorm_builder_proyecto
./abrir_app.sh
```

---

## Cómo es la app

Cuando abres la app, se abre **automáticamente** tu navegador en una página local. Verás un formulario con 5 pasos:

1. **Sube tu Word** (arrastrando o haciendo clic).
2. **Datos del curso** (título, autor, % aprobado).
3. **Marca y colores** (eliges una paleta o tus propios colores).
4. **Recursos adicionales** (PDFs descargables y banco de preguntas).
5. **Crear paquete SCORM** → un botón grande.

Pulsas el botón, esperas unos segundos, y aparece un enlace **"Descargar paquete completo (ZIP)"**.

Ese ZIP contiene:
- Una carpeta `scorm/` con un paquete SCORM por cada tema (subes esto a tu LMS o Moodle).
- Una carpeta `pdfs/` con los apuntes descargables.
- Una carpeta `aiken/` con los bancos de preguntas para importar al LMS.

---

## Dónde se guardan los archivos

Todos los cursos generados se guardan automáticamente en:

```
~/Documentos/ScormBuilder/
```

Con una carpeta por cada generación, así no pierdes ninguna.

---

## Para cerrar la app

Vuelve a la ventana de terminal que se abrió al lanzar la app y pulsa **Ctrl+C**.

O simplemente cierra la pestaña del navegador y la ventana de terminal.

---

## Si algo falla

1. **Captura de pantalla del error** o copia el mensaje completo.
2. Vuelve a esta conversación y pégalo.
3. Te ayudo a resolverlo en el momento.

Errores frecuentes y solución rápida:

| Error | Qué hacer |
|-------|-----------|
| "Python no encontrado" | `sudo apt install python3 python3-venv python3-pip` |
| "Puerto 5000 ocupado" | Cierra otras apps que usen ese puerto, o reinicia el ordenador |
| "El archivo Word no se procesa" | Comprueba que es `.docx` (no `.doc`). Si es viejo, ábrelo en LibreOffice y guárdalo como `.docx` |
| El sidebar no aparece | Tu Word no usa estilos "Título 2" para los subapartados. Aplica el estilo correcto desde Word |

---

## Lo que NO hace esta versión local

Esta es la **versión personal sin SaaS**. Por simplicidad no incluye:

- Login ni registro de usuarios
- Pago / planes de suscripción
- Editor visual del contenido (subes el Word ya escrito)
- Generación de preguntas con IA

Esas funciones forman parte del producto SaaS comercializable que se construye después.

---

## Cuando quieras dar el siguiente paso

Vuelve a esta conversación con tu experiencia probándolo. Te ayudo con:

- Mejoras al motor según los Words que hayas probado.
- Pasar de "app local en mi ordenador" a "app web en internet" para tus clientes.
- Añadir login y pagos para venderlo como SaaS.

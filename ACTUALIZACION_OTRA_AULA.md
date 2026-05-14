# Actualizacion para otra aula

Este proyecto contiene la version desplegada actualmente en el servidor de
`scormbuilder.aiprojects.pro`, incluyendo los ultimos parches aplicados sobre
`instalador/app_local.py`.

## Que se ha corregido al final

Los ultimos cambios corrigen dos problemas detectados en cursos generados en
modo lote, es decir, cuando se suben varios DOCX para crear un curso con varias
unidades.

1. El editor esperaba encontrar un archivo comun:

   ```text
   job_<TOKEN>/structure.json
   ```

   pero en modo lote solo se estaban creando archivos separados:

   ```text
   job_<TOKEN>/structure_1.json
   job_<TOKEN>/structure_2.json
   job_<TOKEN>/structure_3.json
   ...
   ```

   Ahora el sistema genera tambien un `structure.json` agregado con todos los
   temas/unidades del lote, manteniendo ademas los `structure_N.json`
   individuales.

2. Las imagenes extraidas del Word no estan en una unica carpeta global
   `recursos/`. En cursos en lote cada unidad tiene sus propios recursos:

   ```text
   job_<TOKEN>/salida/unidad_01_.../recursos/
   job_<TOKEN>/salida/unidad_02_.../recursos/
   job_<TOKEN>/salida/unidad_03_.../recursos/
   ```

   Esto era importante porque varias unidades pueden tener una imagen con el
   mismo nombre, por ejemplo `docx_img_007.png`. La vista previa ahora sirve los
   recursos indicando el tema/unidad:

   ```text
   /curso/<TOKEN>/preview-resource/__topic_5__/docx_img_007.png
   ```

   Asi la imagen se resuelve desde la carpeta `recursos/` de la unidad correcta.

## Archivos clave que deben copiarse

Para aplicar esta version en otra aula hay que desplegar el proyecto completo,
no solo la libreria. El archivo mas importante para estos ultimos parches es:

```text
instalador/app_local.py
```

Tambien debe mantenerse la carpeta:

```text
libreria/
```

## Aplicacion en otro servidor

Ejemplo suponiendo que el proyecto se instala en:

```text
/opt/scormbuilder/scorm_builder_proyecto
```

Pasos recomendados:

```bash
sudo systemctl stop scormbuilder

cd /opt/scormbuilder/scorm_builder_proyecto
git pull origin main

sudo -u scormbuilder /opt/scormbuilder/scorm_builder_proyecto/.venv/bin/pip install -e /opt/scormbuilder/scorm_builder_proyecto/libreria

sudo systemctl restart scormbuilder
sudo systemctl status scormbuilder --no-pager
```

Si el otro aula no usa Git, copiar el proyecto completo y luego ejecutar:

```bash
sudo -u scormbuilder /opt/scormbuilder/scorm_builder_proyecto/.venv/bin/pip install -e /opt/scormbuilder/scorm_builder_proyecto/libreria
sudo systemctl restart scormbuilder
```

## Variables de entorno

Para activar las funciones de IA, el servicio debe tener configurada:

```text
ANTHROPIC_API_KEY
```

En systemd puede configurarse con un drop-in, por ejemplo:

```bash
sudo systemctl edit scormbuilder
```

Contenido:

```ini
[Service]
Environment="ANTHROPIC_API_KEY=sk-ant-..."
```

Despues:

```bash
sudo systemctl daemon-reload
sudo systemctl restart scormbuilder
```

## Verificacion rapida

Crear un curso de prueba en modo lote con varios DOCX y comprobar:

```bash
TOKEN="TOKEN_DEL_CURSO"

sudo find /var/lib/scormbuilder -path "*${TOKEN}*" -name "structure*.json" | sort
```

Debe aparecer al menos:

```text
structure.json
structure_1.json
structure_2.json
...
```

Tambien debe cargar el editor:

```bash
curl -I http://localhost:5000/curso/${TOKEN}/editar
```

Si se prueba autenticado desde navegador, debe abrir el editor y verse el banner
de enriquecimiento IA.

Para verificar una imagen de una unidad concreta:

```bash
curl -I http://localhost:5000/curso/${TOKEN}/preview-resource/__topic_5__/docx_img_007.png
```

El resultado esperado es `200 OK` si esa imagen existe en la unidad 5.

## Commits relevantes

Los ultimos commits que deben estar presentes en el otro aula son:

```text
d02e628 Resolve batch preview resources by topic
8f4ad1b Create editable structure for batch uploads
05df922 Fix course detail template rendering
c73099e Fix editable structure generation for v0.5.1
```


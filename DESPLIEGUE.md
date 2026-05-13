# Guía de despliegue — SCORM Builder v0.5.1

> Esta guía está dirigida al administrador de sistemas que va a instalar el
> SCORM Builder en un servidor. Se ofrecen dos modos: **desarrollo local**
> (probar rápido en una máquina) y **producción** (servidor real con gunicorn
> + nginx + systemd).

---

## 1. Requisitos del sistema

### Mínimos
- **Python 3.11 o superior**
- **Linux** (Ubuntu 22.04+ / Debian 12+ / RHEL 9+ recomendado)
  *Funciona también en macOS y Windows pero la guía asume Linux.*
- **150 MB libres** para el código + paquete Python
- **1-5 GB** según volumen de cursos almacenados

### Recomendados
- **LibreOffice** (para conversión Word→PDF de los apuntes descargables; si
  no está instalado, esa función concreta devuelve error pero el resto
  funciona)
- **systemd** (para arrancar la app como servicio en producción)
- **nginx** (para servirla detrás de un dominio en producción)

### Opcionales
- `ffmpeg` (si se va a usar la función TTS de audio)
- Una clave de **API de Anthropic** (variable `ANTHROPIC_API_KEY`) si se
  quieren las funciones IA. Sin ella, los formatos, validación WCAG,
  edición manual e IMS CP siguen funcionando; los botones IA devuelven un
  error claro al pulsarlos.

---

## 2. Instalación rápida (modo desarrollo local)

Para probar la aplicación en una máquina local antes de llevarla a producción:

```bash
# 1. Descomprimir el ZIP entregado
unzip scormbuilder-v0.5.1.zip
cd scormbuilder-v05

# 2. Crear un entorno virtual e instalar dependencias
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e libreria/

# 3. (Opcional) Configurar la clave de Anthropic
export ANTHROPIC_API_KEY="sk-ant-..."

# 4. Lanzar el servidor de desarrollo de Flask
cd instalador
python app_local.py
```

La app queda en `http://localhost:5000`. Crea una cuenta, sube un Word de
prueba y genera tu primer curso.

### Verificar la instalación

```bash
cd libreria
python -m pytest tests/ -q
# Esperado: 93 passed
```

Si los 93 tests pasan, la instalación es correcta.

---

## 3. Despliegue en producción

### 3.1. Estructura recomendada en el servidor

```
/opt/scormbuilder/
├── app/                    # Código (contenido del ZIP)
│   ├── libreria/
│   ├── instalador/
│   ├── plantilla/
│   └── ...
├── data/                   # Datos persistentes (BD, cursos generados)
│   ├── scormbuilder.db
│   └── user_<id>/
│       └── job_<token>/...
├── venv/                   # Entorno Python
└── logs/
```

### 3.2. Usuario del sistema

```bash
# Crear usuario dedicado (sin login, sin shell)
sudo useradd --system --no-create-home --shell /usr/sbin/nologin scormbuilder

# Carpetas
sudo mkdir -p /opt/scormbuilder/{app,data,logs}
sudo chown -R scormbuilder:scormbuilder /opt/scormbuilder
```

### 3.3. Código + entorno

```bash
# Descomprimir el ZIP en /opt/scormbuilder/app
sudo -u scormbuilder unzip scormbuilder-v0.5.1.zip -d /tmp/
sudo -u scormbuilder cp -r /tmp/scormbuilder-v05/* /opt/scormbuilder/app/

# Entorno Python
cd /opt/scormbuilder
sudo -u scormbuilder python3 -m venv venv
sudo -u scormbuilder venv/bin/pip install --upgrade pip
sudo -u scormbuilder venv/bin/pip install -e app/libreria/
sudo -u scormbuilder venv/bin/pip install gunicorn
```

### 3.4. Variables de entorno

Crear `/opt/scormbuilder/app.env`:

```bash
# Dónde se guardan BD y cursos. APUNTAR A /opt/scormbuilder/data
SCORM_BUILDER_WORK_DIR=/opt/scormbuilder/data

# Opcional: clave de Anthropic para funciones IA
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Secreto de sesión Flask (generar uno aleatorio)
FLASK_SECRET_KEY=<genera_con_python_-c_"import_secrets;print(secrets.token_hex(32))">
```

Restringir permisos:
```bash
sudo chmod 600 /opt/scormbuilder/app.env
sudo chown scormbuilder:scormbuilder /opt/scormbuilder/app.env
```

### 3.5. Servicio systemd

Crear `/etc/systemd/system/scormbuilder.service`:

```ini
[Unit]
Description=SCORM Builder (Flask + gunicorn)
After=network.target

[Service]
Type=simple
User=scormbuilder
Group=scormbuilder
WorkingDirectory=/opt/scormbuilder/app/instalador
EnvironmentFile=/opt/scormbuilder/app.env
ExecStart=/opt/scormbuilder/venv/bin/gunicorn \
    --workers 3 \
    --threads 2 \
    --timeout 300 \
    --bind 127.0.0.1:8000 \
    --access-logfile /opt/scormbuilder/logs/access.log \
    --error-logfile /opt/scormbuilder/logs/error.log \
    app_local:app
Restart=on-failure
RestartSec=5

# Hardening básico
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/scormbuilder/data /opt/scormbuilder/logs

[Install]
WantedBy=multi-user.target
```

Notas:
- **`--timeout 300`** es importante: las llamadas IA pueden tardar 1-2 minutos
  cuando enriquecen un curso completo. Subir a 600 si los temas son muy largos.
- **`--workers 3 --threads 2`** asume 1-2 GB de RAM disponibles. Ajustar según
  el servidor.

Activar:
```bash
sudo systemctl daemon-reload
sudo systemctl enable scormbuilder
sudo systemctl start scormbuilder
sudo systemctl status scormbuilder
```

### 3.6. Nginx como proxy inverso

Crear `/etc/nginx/sites-available/scormbuilder`:

```nginx
server {
    listen 80;
    server_name scormbuilder.tu-dominio.es;

    # Si es solo intranet, omitir HTTPS. Si es público, usar certbot.
    # return 301 https://$host$request_uri;

    client_max_body_size 200M;   # Permitir Words con muchas imágenes

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts largos para llamadas IA
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }
}
```

Habilitar:
```bash
sudo ln -s /etc/nginx/sites-available/scormbuilder /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 3.7. HTTPS (si va a ser público)

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d scormbuilder.tu-dominio.es
```

---

## 4. Operación

### Backups

Lo único que hay que respaldar:

```bash
/opt/scormbuilder/data/
```

Contiene la BD SQLite y todos los cursos generados. Un `tar.gz` diario es
suficiente para la mayoría de casos:

```bash
# Cron de backup diario
0 3 * * * tar -czf /backup/scormbuilder-$(date +\%F).tar.gz -C /opt/scormbuilder data
```

### Actualizar a una versión nueva

Cuando se entregue una versión posterior (v0.5.2, v0.6.0, etc.):

```bash
sudo systemctl stop scormbuilder
sudo -u scormbuilder unzip nueva-version.zip -d /tmp/
sudo -u scormbuilder rsync -a --delete --exclude=data /tmp/scormbuilder-v05/ /opt/scormbuilder/app/
# Reinstalar el paquete por si las dependencias cambian
sudo -u scormbuilder /opt/scormbuilder/venv/bin/pip install -e /opt/scormbuilder/app/libreria/
sudo systemctl start scormbuilder
```

La BD SQLite se migra sola al arrancar (`init_db()`).

### Logs

- **Gunicorn**: `/opt/scormbuilder/logs/{access,error}.log`
- **systemd**: `journalctl -u scormbuilder -f`

### Diagnóstico de problemas comunes

**La app responde 502 Bad Gateway**
- Comprobar `systemctl status scormbuilder` y `journalctl -u scormbuilder -n 50`
- Lo más común: falta una dependencia Python (reinstalar con `pip install -e`)

**Las funciones IA devuelven "ANTHROPIC_API_KEY no configurada"**
- Verificar que `/opt/scormbuilder/app.env` tiene la línea `ANTHROPIC_API_KEY=...`
  y que systemd la lee (`systemctl show scormbuilder -p Environment`)
- Reiniciar el servicio tras cambiar la variable

**Timeout al pulsar "Aplicar mejoras IA al curso completo"**
- Subir `--timeout` en el servicio systemd (300 → 600 segundos)
- Subir `proxy_read_timeout` en nginx
- Confirmar que el servidor llega a `api.anthropic.com` (firewall, proxy
  corporativo, etc.)

**LibreOffice no convierte a PDF**
- Verificar que `libreoffice --headless --convert-to pdf` funciona como el
  usuario `scormbuilder`
- En servidores headless, añadir paquete `libreoffice-core libreoffice-writer`
  (no hace falta toda la suite)

---

## 5. Estructura del código

Para que tu administrador sepa qué tiene delante:

```
scormbuilder-v05/
├── libreria/                       # Paquete Python instalable
│   ├── scorm_builder/              # Módulos del core
│   │   ├── api.py                  # Punto de entrada de alto nivel
│   │   ├── parser.py               # Parser de Word .docx
│   │   ├── renderer.py             # Generador de HTML del SCORM
│   │   ├── packager.py             # Empaquetado SCORM 1.2
│   │   ├── exporters.py            # SCORM 2004, HTML, IMS CP, cmi5
│   │   ├── aiken_builder.py        # Banco de preguntas Aiken
│   │   ├── ai_assist.py            # Llamadas a Anthropic API
│   │   ├── template_builder.py     # Generador de plantilla Word
│   │   ├── wcag.py                 # Validador WCAG 2.1 AA
│   │   ├── themes.py               # Paletas de color
│   │   ├── tts.py                  # Narración con TTS
│   │   └── inline.py               # Procesamiento de runs/imágenes
│   ├── tests/                      # 93 tests pytest
│   ├── pyproject.toml              # Dependencias Python
│   └── setup.cfg
├── instalador/
│   └── app_local.py                # Aplicación Flask (~6000 líneas)
├── plantilla/                      # Plantillas Word de ejemplo
├── README.md
├── MEJORAS_v0.2.md .. MEJORAS_v0.5_fase5.md   # Histórico de cambios
└── DESPLIEGUE.md                   # Este documento
```

---

## 6. Soporte

- Para problemas con el código: contacta con quien te entrega el paquete
  (Rosario).
- Documentación de las funciones: ver `README.md` y los `MEJORAS_*.md` del
  proyecto.
- Documentación de la API de Anthropic: `https://docs.claude.com/`.

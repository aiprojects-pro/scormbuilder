"""Configuración Gunicorn para SCORM Builder en OpenShift.

Multi-worker SOPORTADO desde la migración de `_jobs` a SQLite con BEGIN
IMMEDIATE: el estado de los jobs vive en disco compartido, no en memoria.
Por defecto seguimos con 1 worker (suficiente para SNO single-node y
amortizado por threads), pero puedes subirlo con `GUNICORN_WORKERS=N`
sin perder jobs entre procesos.

Recomendación:
  - 1 worker / 8 threads → SNO con poca RAM (~512 MB). Default.
  - 2-4 workers / 4 threads → SNO con holgura, varios usuarios concurrentes.
"""
import os

# Bind a 0.0.0.0:PORT — OpenShift necesita que escuche en todas las interfaces
bind = f"0.0.0.0:{os.environ.get('PORT', '8080')}"

# Un worker. Ver docstring arriba.
workers = int(os.environ.get("GUNICORN_WORKERS", "1"))
worker_class = "gthread"
threads = int(os.environ.get("GUNICORN_THREADS", "8"))

# Timeouts altos: generar un SCORM con TTS o IA puede tardar varios minutos.
# Si el cliente cierra, el worker debe seguir hasta acabar.
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "600"))
graceful_timeout = 30
keepalive = 5

# Uploads: hasta 1 GB. Coherente con MAX_TOTAL_UPLOAD_MB de la app.
limit_request_line = 8190
limit_request_field_size = 0
forwarded_allow_ips = "*"   # confiamos en el Router de OpenShift para X-Forwarded-*

# Logging a stdout/stderr (kubernetes los recoge)
accesslog = "-"
errorlog = "-"
access_log_format = '%(h)s "%(r)s" %(s)s %(b)s %(L)s "%(f)s"'
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")

# Evitar que healthz/readyz contaminen los logs de acceso
def skip_health(record):
    msg = record.getMessage()
    return "/healthz" not in msg and "/readyz" not in msg


import logging as _logging
_logging.getLogger("gunicorn.access").addFilter(skip_health)

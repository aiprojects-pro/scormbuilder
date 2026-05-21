#!/bin/sh
# Entrypoint del contenedor SCORM Builder.
#
# - Compatible con UID arbitrario de OpenShift (no asumimos $HOME).
# - Crea subdirectorios esperados dentro del PVC montado en /data (idempotente).
# - Arranca gunicorn apuntando al objeto Flask `app` exportado por
#   `instalador.app_local`.

set -e

# Asegurar PYTHONPATH: necesitamos importar `instalador.app_local`
export PYTHONPATH="/opt/app:${PYTHONPATH:-}"

# El SCC de OpenShift puede asignar un UID arbitrario sin entrada en /etc/passwd.
# Para que herramientas como `whoami` o librerías que leen el username no fallen
# (p.ej. python-docx en ciertos paths), añadimos una entrada efímera.
if ! whoami >/dev/null 2>&1; then
    if [ -w /etc/passwd ]; then
        echo "scormbuilder:x:$(id -u):0:scormbuilder:/opt/app:/sbin/nologin" >> /etc/passwd
    fi
fi

# Inicializar carpetas del PVC. SCORM_BUILDER_WORK_DIR ya es /data en la imagen.
DATA_DIR="${SCORM_BUILDER_WORK_DIR:-/data}"
mkdir -p "$DATA_DIR/users" "$DATA_DIR/scratch" 2>/dev/null || true

# Si llega ANTHROPIC_API_KEY desde Secret, ya estará en el entorno.
# Validación temprana de la session key persistente: la propia app la crea
# automáticamente en $APP_DIR/.session_key si no existe.

echo "[entrypoint] arrancando gunicorn (data=$DATA_DIR, workers=${GUNICORN_WORKERS:-1}, threads=${GUNICORN_THREADS:-8})"
exec gunicorn \
    --config /opt/app/gunicorn.conf.py \
    "instalador.app_local:app"

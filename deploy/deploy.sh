#!/usr/bin/env bash
# Despliegue (o re-despliegue) de SCORM Builder en OKD 4.22 SNO.
#
# Prerequisitos:
#   - oc login --server=https://api.tu-cluster:6443
#   - StorageClass `lvms-vg1` disponible (`oc get sc`)
#   - Permisos para crear Namespace, BuildConfig y desplegar en el namespace.
#
# Idempotente: puedes ejecutarlo varias veces sin romper nada.

set -euo pipefail

# Configuración (sobreescribible con env vars)
NAMESPACE="${NAMESPACE:-scormbuilder}"
APP_NAME="${APP_NAME:-scormbuilder}"
MANIFESTS_DIR="${MANIFESTS_DIR:-$(dirname "$0")/openshift}"

# Raíz del proyecto: el directorio padre de deploy/
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cd "$PROJECT_ROOT"

# Comprobaciones previas
require() {
    command -v "$1" >/dev/null 2>&1 || { echo "ERROR: falta el comando '$1'"; exit 1; }
}
require oc

if ! oc whoami >/dev/null 2>&1; then
    echo "ERROR: no estás autenticado. Ejecuta primero: oc login --server=..."
    exit 1
fi

echo "===> Cluster: $(oc whoami --show-server)"
echo "===> Usuario: $(oc whoami)"
echo "===> Namespace: $NAMESPACE"
echo

# 1) Aplicar manifiestos (Namespace, IS, BC, ConfigMap, PVC, Deployment, etc.)
echo "===> Aplicando manifiestos OpenShift..."
oc apply -k "$MANIFESTS_DIR"
echo

# 2.0) Crear el Secret del cookie OAuth si no existe (necesario para el
#      sidecar oauth-proxy). Es una clave de 32 bytes aleatoria.
if ! oc -n "$NAMESPACE" get secret scormbuilder-oauth-cookie >/dev/null 2>&1; then
    echo "===> Creando cookie secret para oauth-proxy..."
    oc -n "$NAMESPACE" create secret generic scormbuilder-oauth-cookie \
        --from-literal=secret="$(openssl rand -base64 32 | head -c 32)"
fi

# 2) Comprobar que el Secret existe; si no, recordar al usuario que lo cree.
if ! oc -n "$NAMESPACE" get secret scormbuilder-secrets >/dev/null 2>&1; then
    cat <<EOF
ATENCIÓN: el Secret 'scormbuilder-secrets' no existe en el namespace.
Créalo ahora con tu API key de Anthropic:

  oc -n $NAMESPACE create secret generic scormbuilder-secrets \\
      --from-literal=ANTHROPIC_API_KEY='sk-ant-XXXXXXXX' \\
      --from-literal=SMTP_PASSWORD=''

El Deployment NO arrancará hasta que el Secret exista.
EOF
    read -p "¿Has creado ya el Secret? (s/N) " ans
    [[ "$ans" == "s" || "$ans" == "S" ]] || { echo "Aborto. Crea el Secret y vuelve a lanzar este script."; exit 1; }
fi

# 3) Build de la imagen (binary build desde el árbol local).
#    --exclude-dirs evita meter cosas innecesarias en el contexto.
echo "===> Lanzando build de la imagen (puede tardar ~5-10 min la 1ª vez)..."
oc -n "$NAMESPACE" start-build "$APP_NAME" \
    --from-dir=. \
    --exclude='(^|/)(\.git|\.github|\.idea|\.vscode|__pycache__|\.pytest_cache|node_modules|deploy/openshift)(/|$)' \
    --follow

# 4) Esperar a que el Deployment esté listo
echo
echo "===> Esperando a que el Deployment esté listo..."
oc -n "$NAMESPACE" rollout status deployment/"$APP_NAME" --timeout=10m

# 5) Mostrar la URL final
echo
ROUTE_HOST=$(oc -n "$NAMESPACE" get route "$APP_NAME" -o jsonpath='{.spec.host}' 2>/dev/null || true)
if [[ -n "$ROUTE_HOST" ]]; then
    echo "===> ✓ Aplicación disponible en: https://$ROUTE_HOST"
else
    echo "===> ⚠ Route no encontrada todavía. Revisa con: oc -n $NAMESPACE get route"
fi

echo
echo "Comandos útiles:"
echo "  oc -n $NAMESPACE get pods,svc,route,pvc"
echo "  oc -n $NAMESPACE logs -f deployment/$APP_NAME"
echo "  oc -n $NAMESPACE rsh deployment/$APP_NAME"

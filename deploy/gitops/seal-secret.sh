#!/usr/bin/env bash
# Genera (o regenera) deploy/gitops/scormbuilder-secrets.sealed.yaml a partir
# de los valores que te pida por stdin.
#
# Requiere:
#   - kubeseal cli instalado
#   - controller Sealed Secrets desplegado en kube-system
#   - oc autenticado al cluster destino

set -euo pipefail

OUT="$(dirname "$0")/scormbuilder-secrets.sealed.yaml"
NS="${NAMESPACE:-scormbuilder}"
CTRL_NS="${SEAL_CTRL_NS:-kube-system}"
CTRL_NAME="${SEAL_CTRL_NAME:-sealed-secrets-controller}"

command -v kubeseal >/dev/null 2>&1 \
    || { echo "ERROR: kubeseal no instalado. Ver deploy/gitops/README.md"; exit 1; }
command -v oc >/dev/null 2>&1 \
    || { echo "ERROR: oc no instalado"; exit 1; }

if ! oc whoami >/dev/null 2>&1; then
    echo "ERROR: no estás autenticado. oc login primero."
    exit 1
fi

# Verificar que el controller existe
if ! oc -n "$CTRL_NS" get deployment "$CTRL_NAME" >/dev/null 2>&1; then
    echo "ERROR: no encuentro el controller Sealed Secrets en $CTRL_NS/$CTRL_NAME"
    echo "       Instálalo primero (ver deploy/gitops/README.md sección A.1)."
    exit 1
fi

# Pedir los valores
read -r -s -p "ANTHROPIC_API_KEY (no se muestra): " ANTHROPIC
echo
read -r -s -p "SMTP_PASSWORD (Enter para vacío): " SMTP
echo

# Generar el sealed
oc -n "$NS" create secret generic scormbuilder-secrets \
    --from-literal=ANTHROPIC_API_KEY="$ANTHROPIC" \
    --from-literal=SMTP_PASSWORD="${SMTP:-}" \
    --dry-run=client -o yaml \
| kubeseal \
    --controller-namespace="$CTRL_NS" \
    --controller-name="$CTRL_NAME" \
    --format=yaml \
> "$OUT"

echo
echo "✓ Generado: $OUT"
echo "  Aplica con: oc apply -f $OUT"
echo "  Después: oc -n $NS rollout restart deployment/scormbuilder"

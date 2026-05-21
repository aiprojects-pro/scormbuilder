#!/usr/bin/env bash
# Restaurar SCORM Builder desde un backup del PVC scormbuilder-backups.
#
# Uso:
#   ./deploy/restore.sh                       # interactivo, lista backups
#   ./deploy/restore.sh scormbuilder-20260520-030000.tar.gz
#
# Estrategia:
#   1. Listar backups disponibles (o usar el indicado por argumento).
#   2. Confirmar con el usuario (es destructivo: sobrescribe /data).
#   3. Parar el Deployment (scale 0) para liberar el PVC.
#   4. Lanzar un Pod efímero que monte BOTH el PVC de datos y el de backups,
#      vacíe /data y descomprima el tar.
#   5. Levantar el Deployment de nuevo (scale 1).
#
# CUIDADO: borra TODOS los datos actuales antes de restaurar.

set -euo pipefail

NAMESPACE="${NAMESPACE:-scormbuilder}"
APP_NAME="${APP_NAME:-scormbuilder}"

if ! oc whoami >/dev/null 2>&1; then
    echo "ERROR: no estás autenticado en el cluster. oc login primero."
    exit 1
fi

# 1) Si no se pasa argumento, listar los backups disponibles
BACKUP_FILE="${1:-}"
if [ -z "$BACKUP_FILE" ]; then
    echo "Backups disponibles en el PVC scormbuilder-backups:"
    oc -n "$NAMESPACE" run scormbuilder-backup-list-$$ \
        --rm -i --tty --restart=Never \
        --image=registry.access.redhat.com/ubi9/ubi-minimal:latest \
        --overrides='{
          "apiVersion":"v1",
          "spec":{
            "containers":[{
              "name":"ls","image":"registry.access.redhat.com/ubi9/ubi-minimal:latest",
              "command":["ls","-lhrt","/backups"],
              "volumeMounts":[{"name":"backups","mountPath":"/backups"}]
            }],
            "volumes":[{"name":"backups","persistentVolumeClaim":{"claimName":"scormbuilder-backups"}}]
          }
        }'
    echo
    echo "Usa: $0 <nombre-del-fichero>"
    exit 0
fi

echo "Vas a RESTAURAR desde: $BACKUP_FILE"
echo "Esto SOBRESCRIBIRÁ todos los datos actuales (cursos, usuarios, sesiones)."
read -p "Escribe 'CONFIRMAR' para continuar: " ans
[ "$ans" = "CONFIRMAR" ] || { echo "Aborto."; exit 1; }

echo "[restore] Parando el Deployment..."
oc -n "$NAMESPACE" scale deployment/"$APP_NAME" --replicas=0
oc -n "$NAMESPACE" wait --for=delete pod -l app.kubernetes.io/name=scormbuilder,app.kubernetes.io/component=web --timeout=120s 2>/dev/null || true

echo "[restore] Lanzando pod de restauración..."
oc -n "$NAMESPACE" run scormbuilder-restore-$$ \
    --rm -i --tty --restart=Never \
    --image=registry.access.redhat.com/ubi9/ubi-minimal:latest \
    --overrides="{
      \"apiVersion\":\"v1\",
      \"spec\":{
        \"securityContext\":{\"runAsNonRoot\":true,\"fsGroup\":0},
        \"containers\":[{
          \"name\":\"restore\",\"image\":\"registry.access.redhat.com/ubi9/ubi-minimal:latest\",
          \"command\":[\"sh\",\"-c\",\"
            set -e;
            echo '[restore] vaciando /data ...';
            find /data -mindepth 1 -delete 2>/dev/null || true;
            echo '[restore] descomprimiendo $BACKUP_FILE ...';
            tar xzf /backups/$BACKUP_FILE -C /data;
            echo '[restore] hecho. Contenido de /data:';
            ls -la /data | head -20;
          \"],
          \"volumeMounts\":[
            {\"name\":\"data\",\"mountPath\":\"/data\"},
            {\"name\":\"backups\",\"mountPath\":\"/backups\",\"readOnly\":true}
          ],
          \"securityContext\":{
            \"allowPrivilegeEscalation\":false,
            \"runAsNonRoot\":true,
            \"capabilities\":{\"drop\":[\"ALL\"]}
          }
        }],
        \"volumes\":[
          {\"name\":\"data\",\"persistentVolumeClaim\":{\"claimName\":\"scormbuilder-data\"}},
          {\"name\":\"backups\",\"persistentVolumeClaim\":{\"claimName\":\"scormbuilder-backups\"}}
        ]
      }
    }"

echo "[restore] Levantando el Deployment..."
oc -n "$NAMESPACE" scale deployment/"$APP_NAME" --replicas=1
oc -n "$NAMESPACE" rollout status deployment/"$APP_NAME" --timeout=5m

echo "[restore] ✓ Restauración completada."

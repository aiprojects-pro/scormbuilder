# Despliegue de SCORM Builder en OKD 4.22 SNO (LVMS)

Guía paso a paso para llevar la aplicación a producción en un cluster de
OKD/OpenShift 4.22 Single-Node con almacenamiento LVMS.

## Arquitectura del despliegue

```
              Internet
                 │
                 ▼  HTTPS (TLS edge)
        ┌──────────────────┐
        │ OpenShift Router │  (HAProxy)
        │  scormbuilder    │
        │  .apps.<cluster> │
        └────────┬─────────┘
                 │ HTTP (cluster interno)
                 ▼
        ┌──────────────────┐
        │ Service          │  ClusterIP :8080
        │  scormbuilder    │
        └────────┬─────────┘
                 │
                 ▼
        ┌──────────────────┐         ┌─────────────────────┐
        │ Deployment       │         │ PVC scormbuilder-   │
        │  scormbuilder    │ ◄─────► │ data (100Gi, LVMS)  │
        │  - 1 réplica     │         │  /data en el pod    │
        │  - non-root      │         └─────────────────────┘
        │  - readOnlyFS    │
        │  - gunicorn 1w/8t│
        └────────┬─────────┘
                 │ HTTPS
                 ▼
         api.anthropic.com (IA)
         translate.google.com (TTS)
```

## Decisiones de seguridad aplicadas

| Aspecto | Decisión |
|---|---|
| Usuario del contenedor | UID 1001 declarado, UID aleatorio asignado por OpenShift (GID 0) |
| Capacidades Linux | `drop: ["ALL"]` |
| Escalada de privilegios | `allowPrivilegeEscalation: false` |
| Filesystem raíz | `readOnlyRootFilesystem: true` (solo `/data`, `/tmp` y `/opt/app/.cache` escribibles) |
| Seccomp | `RuntimeDefault` |
| Pod Security Standard | `restricted` enforced a nivel namespace |
| Service Account token | `automountServiceAccountToken: false` |
| Secretos | `Secret` separado, montado como env (no en imagen, no en git) |
| Red | NetworkPolicy default-deny + allow explícito de Router + DNS + 443 |
| Almacenamiento | PVC `lvms-vg1` ReadWriteOnce 100Gi |
| TLS | Edge termination en Router, HTTP → HTTPS redirect |
| Probes | `/healthz` (liveness) y `/readyz` (readiness con check DB + PVC) |

## Por qué 1 sola réplica (en SNO o no)

El código de `app_local.py` guarda el progreso de los jobs de generación en
un dict global de memoria (`_jobs`). Con más de un worker / réplica, una
petición de progreso podría caer en un proceso que no conoce el job. Si en
algún momento quieres escalar, hay que persistir esos jobs (SQLite, Redis,
etc.) y refactorizar. Por ahora: **1 worker en gunicorn, 1 réplica en el
Deployment, multi-thread para concurrencia I/O**.

## Despliegue inicial paso a paso

### 1. Pre-requisitos

```bash
oc login --server=https://api.tu-cluster:6443
oc get sc lvms-vg1                  # Verificar que LVMS está disponible
oc auth can-i create namespace      # Necesitas permisos
```

### 2. (Opcional) Revisar y editar manifiestos

```bash
# Edita el dominio si quieres uno custom en la Route:
$EDITOR deploy/openshift/51-route.yaml

# Ajusta recursos si tu SNO tiene poca RAM:
$EDITOR deploy/openshift/40-deployment.yaml      # limits.memory, limits.cpu

# Cambia el tamaño del PVC si necesitas algo distinto a 100Gi:
$EDITOR deploy/openshift/20-pvc.yaml
```

### 3. Crear el Secret con la API key (NO en git)

```bash
oc apply -f deploy/openshift/00-namespace.yaml

oc -n scormbuilder create secret generic scormbuilder-secrets \
    --from-literal=ANTHROPIC_API_KEY='sk-ant-XXXXXXXX' \
    --from-literal=SMTP_PASSWORD=''
```

> **Nota**: el `Secret` NO está en el `kustomization.yaml` para evitar que sus
> valores acaben en git. Si lo prefieres gestionado por GitOps (ArgoCD,
> Flux), usa Sealed Secrets / External Secrets Operator.

### 4. Despliegue automático

```bash
./deploy/deploy.sh
```

El script aplica los manifiestos, lanza el build, espera a que el Deployment
esté ready, y muestra la URL final.

### 5. Despliegue manual (si prefieres controlar cada paso)

```bash
# 4.a) Manifiestos
oc apply -k deploy/openshift/

# 4.b) Build de la imagen desde el árbol local
oc -n scormbuilder start-build scormbuilder --from-dir=. --follow

# 4.c) Esperar al rollout
oc -n scormbuilder rollout status deployment/scormbuilder --timeout=10m

# 4.d) URL final
oc -n scormbuilder get route scormbuilder \
    -o jsonpath='{"https://"}{.spec.host}{"\n"}'
```

## Operaciones del día a día

### Ver logs

```bash
oc -n scormbuilder logs -f deployment/scormbuilder
```

### Reiniciar el pod

```bash
oc -n scormbuilder rollout restart deployment/scormbuilder
```

### Entrar en el contenedor

```bash
oc -n scormbuilder rsh deployment/scormbuilder
# dentro:
ls /data
sqlite3 /data/scormbuilder.sqlite3 'select count(*) from users'
```

### Backup del PVC (manual)

LVMS no incluye snapshot automático en todas las versiones. Patrón sencillo:

```bash
# Volcar todo /data a un tar fuera del cluster
oc -n scormbuilder exec deployment/scormbuilder -- \
    tar czf - -C /data . > scormbuilder-backup-$(date +%F).tar.gz
```

Restaurar:

```bash
# Pod debe estar levantado primero. Vaciar /data y descomprimir.
oc -n scormbuilder cp scormbuilder-backup-FECHA.tar.gz \
    deployment/scormbuilder:/tmp/restore.tar.gz
oc -n scormbuilder rsh deployment/scormbuilder \
    sh -c 'rm -rf /data/* && tar xzf /tmp/restore.tar.gz -C /data'
```

### Rotar la session_key (sesiones de usuarios)

La session key vive en `/data/.session_key`. Borrarla invalida todas las
sesiones activas:

```bash
oc -n scormbuilder rsh deployment/scormbuilder rm /data/.session_key
oc -n scormbuilder rollout restart deployment/scormbuilder
```

### Cambiar ANTHROPIC_API_KEY

```bash
oc -n scormbuilder set data secret/scormbuilder-secrets \
    ANTHROPIC_API_KEY='sk-ant-NUEVA'
oc -n scormbuilder rollout restart deployment/scormbuilder
```

### Re-build tras cambios de código

```bash
./deploy/deploy.sh    # idempotente
# o solo el build:
oc -n scormbuilder start-build scormbuilder --from-dir=. --follow
```

OpenShift detecta el nuevo ImageStream tag y dispara el Deployment
automáticamente (gracias al annotation `image.openshift.io/triggers`).

## Activar OCR (conversión imagen→tabla)

Por defecto OCR está OFF (`detect_tables_in_images=False`) porque produce
muchos falsos positivos. Si necesitas activarlo:

1. Edita `deploy/requirements.txt` y descomenta las 3 líneas de OCR
   (`opencv-python-headless`, `pytesseract`, `numpy`).
2. Re-construye la imagen: `./deploy/deploy.sh`.
3. El endpoint manual `POST /api/curso/<token>/imagen-a-tabla` ya está
   disponible — solo necesita las dependencias instaladas.

## Troubleshooting

| Síntoma | Causa probable | Solución |
|---|---|---|
| Pod en `Pending` indefinidamente | PVC no se puede aprovisionar | `oc describe pvc scormbuilder-data` → ver evento del provisioner LVMS |
| Pod arranca y muere con `CrashLoopBackOff` | Falta `ANTHROPIC_API_KEY` Secret | Crear Secret como en el paso 3 |
| `/readyz` devuelve 503 | DB no inicializa o PVC no writable | `oc rsh` y `ls -la /data`; el GID debe ser 0 con permisos `g=u` |
| Build falla por timeout descargando wheels | Red lenta | Subir `resources.limits.cpu` del BuildConfig, o usar pip-cache local |
| 503 desde la Route | Pod no ready | `oc get endpoints scormbuilder` (debe haber al menos 1 IP) |
| Subidas grandes (>50 MB) fallan | Buffer-size del Router | Subir `haproxy.router.openshift.io/buffer-size` en `51-route.yaml` |

## Por qué LVMS y no otros tipos de almacenamiento

- **NFS/RWX**: dado que solo tenemos 1 réplica, no necesitamos RWX.
- **Bloque (RBD/Ceph)**: sobre-ingenieria para SNO.
- **HostPath**: no portable y rompe el modelo de PVC.
- **LVMS (LVM Storage Operator)**: idiomático en SNO, rendimiento bueno,
  snapshot básico, integración nativa con OpenShift.

## Backup automático

- CronJob `scormbuilder-backup` corre cada día a las 03:00 (Europe/Madrid).
- Hace `tar.gz` consistente (con `sqlite3 .backup` antes) del PVC de datos.
- Lo guarda en el PVC `scormbuilder-backups` (50 Gi).
- Retención automática: 30 días.

Restaurar desde un backup:

```bash
./deploy/restore.sh                        # lista los backups disponibles
./deploy/restore.sh scormbuilder-20260520-030000.tar.gz
```

## Métricas Prometheus

Endpoint `/metrics` expone (entre otras):

- `scormbuilder_courses_total` (gauge)
- `scormbuilder_users_total` (gauge)
- `scormbuilder_shares_total` (gauge)
- `scormbuilder_jobs_active` (gauge)
- `scormbuilder_jobs_started_total` (counter)
- `scormbuilder_data_dir_bytes` (gauge)
- `scormbuilder_build_duration_seconds` (histogram, instrumentar si se quiere)
- `scormbuilder_ai_calls_total{endpoint,outcome}` (counter, instrumentar si se quiere)

`ServiceMonitor` listo para OpenShift User Workload Monitoring. Requiere que
el cluster-admin lo habilite — ver `RECOMENDACIONES_ADMIN.md`.

## Roadmap pendiente

- [ ] Migrar `_jobs` global a SQLite/Redis para poder escalar horizontalmente.
- [ ] Sealed Secrets para gestionar `ANTHROPIC_API_KEY` por GitOps.
- [ ] OAuth (Keycloak/Dex) si quieres SSO en lugar del login propio.
- [ ] Sync de backups OFF-cluster (NAS / S3) — actualmente viven en el mismo
      disco LVMS.

# Handoff al administrador del cluster OpenShift

Documento único de entrega para desplegar **SCORM Builder** en OKD 4.22 SNO.
Este es el primer documento que el administrador debe leer; el resto de
documentación de `deploy/` profundiza en aspectos concretos.

---

## 1. Qué te entrego

Un único archivo: **`scormbuilder-main-PARCHEADO.zip`** (~470 KB).

Al descomprimirlo encontrarás:

```
scormbuilder-main/
├── libreria/                  # Motor SCORM (paquete Python instalable)
├── instalador/                # App Flask local + plantillas externas
└── deploy/                    # ← TODO lo relevante para ti vive aquí
    ├── HANDOFF.md             # este documento
    ├── README.md              # guía completa de despliegue
    ├── RECOMENDACIONES_ADMIN.md  # checklist técnica + troubleshooting
    ├── Containerfile          # imagen UBI9 non-root multi-stage
    ├── requirements.txt
    ├── gunicorn.conf.py
    ├── entrypoint.sh
    ├── deploy.sh              # script idempotente "todo en uno"
    ├── restore.sh             # restauración desde backup
    ├── openshift/             # manifiestos K8s/OpenShift (kustomize)
    │   ├── 00-namespace.yaml
    │   ├── 10..82-*.yaml      # 17 recursos en total
    │   └── kustomization.yaml
    └── gitops/                # gestión de secretos via Sealed Secrets / ESO
        ├── README.md
        └── seal-secret.sh
```

Y el diff respecto al código original (por si quieres ver qué cambió):
`scormbuilder-PARCHES.diff` (~400 KB).

---

## 2. Pre-requisitos del cluster (BLOQUEANTES)

Antes de aplicar nada, verifica:

```bash
# 2.1 LVMS instalado y storageClass operativa
oc get sc lvms-vg1
oc get lvmcluster -A
#   El VG debe tener al menos 200 Gi libres (100 datos + 50 backups + holgura)

# 2.2 Image Registry interno operativo
oc get co image-registry
#   Available=True, Progressing=False, Degraded=False

# 2.3 Capacidad del SNO
oc describe node | grep -E "Capacity|Allocatable" -A 3
#   Recomendado libre: 4 vCPU + 4 Gi RAM para los limits del Deployment
```

Si quieres el dashboard de métricas en la consola OpenShift, habilita
**User Workload Monitoring** (esto SOLO lo puede hacer cluster-admin):

```bash
oc apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: cluster-monitoring-config
  namespace: openshift-monitoring
data:
  config.yaml: |
    enableUserWorkload: true
EOF

# Verificar (espera ~2 min):
oc -n openshift-user-workload-monitoring get pods
```

Sin UWM el `/metrics` y el `ServiceMonitor`/`PrometheusRule` quedan inertes
pero la app funciona igual.

---

## 3. Lo que el cliente (yo) te tengo que dar

Pídele al cliente estos datos ANTES de desplegar. Sin ellos el sistema no
funciona en producción:

| Dato | Para qué | Dónde lo configuras |
|---|---|---|
| **`ANTHROPIC_API_KEY`** | Asistente IA, alt-text, quizzes IA | Secret `scormbuilder-secrets` |
| **`SMTP_PASSWORD`** (opcional) | Notificaciones por email | Secret `scormbuilder-secrets` |
| **Hora del backup** (default 03:00 Madrid) | Cron `scormbuilder-backup` | `82-backup-cronjob.yaml` |
| **Retención backups** (default 30 días) | Limpieza automática | env `RETENTION_DAYS` |
| **Dominio Route** (opcional) | URL pública custom | `51-route.yaml` `spec.host` |
| **Host/user/path SSH del backup OFF-cluster** | Sync de backups a NAS | ConfigMap `scormbuilder-backup-config` + Secret `scormbuilder-backup-ssh` |
| **¿Habilitar OAuth con OpenShift?** | SSO con cuentas del cluster | Ya viene activado por defecto; si NO se quiere, comentar el sidecar en `40-deployment.yaml` |
| **¿Activar Sealed Secrets?** | Gestionar secretos por git | Si sí: instalar controller; si no: `oc create secret generic` manual |

---

## 4. Despliegue paso a paso

### 4.1. Descomprimir y autenticarte

```bash
unzip scormbuilder-main-PARCHEADO.zip
cd scormbuilder-main
oc login --server=https://api.tu-cluster:6443
```

### 4.2. Crear namespace y secret de cookie OAuth

```bash
# Namespace primero (los manifiestos lo asumen creado)
oc apply -f deploy/openshift/00-namespace.yaml

# Cookie secret OAuth (lo necesita el sidecar oauth-proxy)
# El script deploy.sh lo crea automáticamente si no existe.
```

### 4.3. Crear el Secret con la API key

Opción A — **manual** (más simple, no GitOps):

```bash
oc -n scormbuilder create secret generic scormbuilder-secrets \
    --from-literal=ANTHROPIC_API_KEY='sk-ant-XXXXX' \
    --from-literal=SMTP_PASSWORD=''
```

Opción B — **Sealed Secrets** (recomendado si tienes GitOps):

```bash
# 1) Instalar controller (UNA VEZ, cluster-wide)
oc apply -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.27.1/controller.yaml

# 2) Generar el SealedSecret cifrado
deploy/gitops/seal-secret.sh
oc apply -f deploy/gitops/scormbuilder-secrets.sealed.yaml
```

Ver detalles en `deploy/gitops/README.md`.

### 4.4. Lanzar el script

```bash
./deploy/deploy.sh
```

Hace:
1. Aplica los 17 manifiestos OpenShift con `oc apply -k`.
2. Crea el cookie secret de OAuth si no existe.
3. Lanza el build de la imagen (`oc start-build --from-dir=.`).
4. Espera al `rollout`.
5. Imprime la URL HTTPS final.

Tiempo total esperado: **5–10 minutos** (la mayoría es el build inicial).

### 4.5. Validar

```bash
# Pod arriba
oc -n scormbuilder get pods,svc,route,pvc

# Probe responde
curl -sk https://$(oc -n scormbuilder get route scormbuilder \
    -o jsonpath='{.spec.host}')/healthz

# Métricas (port-forward porque /metrics está sin auth solo en cluster)
oc -n scormbuilder port-forward svc/scormbuilder 8080:8080 &
curl -s http://localhost:8080/metrics | grep scormbuilder_

# Backup manual de validación (ANTES de poner en producción)
oc -n scormbuilder create job --from=cronjob/scormbuilder-backup test-backup
oc -n scormbuilder logs -f job/test-backup
```

---

## 5. Decisiones de seguridad ya aplicadas

| Aspecto | Configuración |
|---|---|
| Pod Security | `restricted` enforced a nivel namespace |
| Usuario contenedor | UID 1001 declarado / arbitrario OpenShift, GID 0 |
| Capabilities | `drop: ["ALL"]` |
| `allowPrivilegeEscalation` | `false` |
| `readOnlyRootFilesystem` | `true` (emptyDirs en `/tmp`, `/opt/app/.cache`) |
| `seccompProfile` | `RuntimeDefault` |
| `automountServiceAccountToken` | `false` para `web`, `true` solo para backup CronJob |
| Secretos | en Secret, montados como env, no en imagen |
| TLS | edge en Router (público) + reencrypt al oauth-proxy interno |
| OAuth | sidecar `openshift-oauth-proxy` ante todo el tráfico (excepto health/metrics) |
| NetworkPolicy | default-deny + allow Router + DNS + Prometheus UWM + 443 saliente |
| Anti zip-bomb | parser valida límites antes de abrir el .docx |
| Anti prompt-injection | wrap `<USER_CONTENT>` + system prompt en TODAS las llamadas IA |
| Sanitización SVG | SVG generado por IA pasa por whitelist tag/attr antes de servirse |

---

## 6. Operaciones rutinarias

### Logs

```bash
oc -n scormbuilder logs -f deployment/scormbuilder
oc -n scormbuilder logs -l app.kubernetes.io/component=backup --tail=200
```

### Reiniciar la app

```bash
oc -n scormbuilder rollout restart deployment/scormbuilder
```

### Actualizar la API key

```bash
oc -n scormbuilder set data secret/scormbuilder-secrets \
    ANTHROPIC_API_KEY='sk-ant-NUEVA'
oc -n scormbuilder rollout restart deployment/scormbuilder
```

### Restaurar desde backup

```bash
./deploy/restore.sh            # lista backups disponibles
./deploy/restore.sh scormbuilder-20260520-030000.tar.gz
```

### Re-desplegar tras cambios en el código

```bash
./deploy/deploy.sh             # idempotente, solo re-builda y rollea
```

### Suspender backups temporalmente (mantenimiento)

```bash
oc -n scormbuilder patch cronjob scormbuilder-backup \
    -p '{"spec":{"suspend":true}}'
# Reactivar:
oc -n scormbuilder patch cronjob scormbuilder-backup \
    -p '{"spec":{"suspend":false}}'
```

### Ampliar el PVC de datos (LVMS soporta expansión online)

```bash
oc -n scormbuilder patch pvc scormbuilder-data --type merge \
    -p '{"spec":{"resources":{"requests":{"storage":"200Gi"}}}}'
```

---

## 7. Métricas y alertas disponibles

Métricas custom expuestas en `/metrics`:

| Métrica | Tipo | Significado |
|---|---|---|
| `scormbuilder_courses_total` | gauge | Cursos generados |
| `scormbuilder_users_total` | gauge | Usuarios registrados |
| `scormbuilder_jobs_active` | gauge | Jobs en ejecución |
| `scormbuilder_jobs_started_total` | counter | Total jobs arrancados |
| `scormbuilder_data_dir_bytes` | gauge | Tamaño del PVC de datos |
| `scormbuilder_ai_calls_total{endpoint,outcome}` | counter | Llamadas a IA |

Alertas configuradas en `83-prometheusrule.yaml` (12 alertas en 5 grupos):

- **availability**: `ScormBuilderDown`, `ScormBuilderReadinessFailing`
- **storage**: `PVCAlmostFull` 85%, `PVCCritical` 95%, `BackupPVCFull`, `DataGrowsFast`
- **backups**: `BackupOverdue` >25h, `BackupFailing`
- **application**: `ManyActiveJobs`, `HighErrorRate` IA
- **resources**: `MemoryHigh`, `CPUHigh`, `PodRestarting`

Las alertas se muestran en **Observe → Alerting** de la consola OpenShift
(requiere UWM habilitado, ver §2).

---

## 8. Limitaciones conocidas

| Limitación | Mitigación |
|---|---|
| Solo 1 réplica (SNO) | Multi-worker SOPORTADO (jobs en SQLite con BEGIN IMMEDIATE) — puedes subir `GUNICORN_WORKERS=2-4` en el ConfigMap si necesitas más concurrencia, pero NO HA |
| Backups dentro del cluster | Si el disco LVMS muere, los backups mueren con él. Activa sync OFF-cluster con `BACKUP_SSH_ENABLED=1` (sección 6 de `RECOMENDACIONES_ADMIN.md`) |
| OCR imagen→tabla desactivado por defecto | El detector tiene falsos positivos. Si quieres activarlo: descomenta `opencv-python-headless`, `pytesseract`, `numpy` en `deploy/requirements.txt`, re-builda |
| Login propio + OAuth coexisten | El sidecar oauth-proxy autentica primero (SSO OpenShift); la app crea/loguea automáticamente el usuario. El login propio existe como fallback |
| Sin sync a NAS/S3 automático | Hay receta para SSH; para S3 requeriría añadir un step `aws s3 cp` o `mc cp` al CronJob |

---

## 9. Cuándo escalar al cliente (yo)

- Cambios en la app (nueva versión del zip).
- Errores de aplicación que no se resuelven con un rollout.
- Solicitudes de nuevas funcionalidades.
- Auditorías de seguridad / compliance que requieran revisar el código.

Cualquier cosa de **infraestructura** (LVMS, network, OpenShift en sí,
DNS, certificados, registry) es trabajo del administrador.

---

## 10. Archivos para revisión adicional

| Documento | Cuándo leerlo |
|---|---|
| `deploy/RECOMENDACIONES_ADMIN.md` | Profundizar en decisiones operativas y troubleshooting |
| `deploy/README.md` | Guía técnica completa de despliegue |
| `deploy/gitops/README.md` | Si quieres GitOps con Sealed Secrets o External Secrets |
| `deploy/openshift/*.yaml` | Cada manifiesto comenta su propósito y los parámetros que puedes ajustar |

# Recomendaciones para el administrador del cluster

Documento para entregar a la persona responsable del cluster OKD 4.22 SNO.
Cubre lo que el equipo de aplicación **NO puede hacer** sin permisos
cluster-admin y lo que **debería revisar** antes y después del primer
despliegue.

---

## 1. Pre-requisitos cluster-admin (HACER ANTES DE DESPLEGAR)

### 1.1. LVMS Operator instalado y operativo

La aplicación usa el StorageClass `lvms-vg1` para sus 2 PVCs (datos y backups,
total 150 Gi). Verifica:

```bash
oc get sc lvms-vg1
oc get lvmcluster -A
oc get csidriver topolvm.io
```

Si el nombre del StorageClass es distinto (`lvms-vg1` es el default), avísanos
y editamos `deploy/openshift/20-pvc.yaml` y `21-backup-pvc.yaml`.

**Capacidad mínima libre en el VG**: 200 Gi (100 Gi data + 50 Gi backups + 50 Gi
de holgura para LVM thin-provisioning).

### 1.2. User Workload Monitoring (UWM) habilitado

Para que los `/metrics` de la app se scrapeen por el Prometheus de OpenShift y
aparezcan en la consola web, hay que habilitar UWM. Esto **solo lo puede hacer
cluster-admin**:

```bash
# Crear (o editar) el ConfigMap de monitoring
cat <<EOF | oc apply -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: cluster-monitoring-config
  namespace: openshift-monitoring
data:
  config.yaml: |
    enableUserWorkload: true
EOF

# Verificar que Prometheus UWM arranca (puede tardar 2-3 minutos)
oc -n openshift-user-workload-monitoring get pods
```

Si UWM **no se habilita**: la app sigue funcionando, el endpoint `/metrics`
sigue respondiendo, pero las métricas no acaban en el Prometheus del cluster.
El `ServiceMonitor` queda inerte (no rompe nada).

### 1.3. Capacidad del SNO

Comprueba que el nodo tiene suficientes recursos libres para los `requests` y
`limits` definidos en el Deployment:

| Recurso | Request | Limit |
|---|---|---|
| CPU | 250 m | 4 vCPU |
| RAM | 512 Mi | 4 Gi |
| Ephemeral storage | — | 2 Gi |
| PVC datos | 100 Gi | (mismo) |
| PVC backups | 50 Gi | (mismo) |

```bash
oc describe node | grep -E "Capacity|Allocatable|Allocated" -A 5
```

Si el SNO tiene poca RAM, baja `limits.memory` a `2Gi` en
`deploy/openshift/40-deployment.yaml` antes de aplicar — la generación SCORM
seguirá funcionando salvo cursos con TTS muy largos.

### 1.4. Política de Pod Security

El Namespace tiene la etiqueta `pod-security.kubernetes.io/enforce: restricted`.
Si tu cluster usa Pod Security Standards distinto (p.ej. la deprecada
`PodSecurityPolicy` o un `SecurityContextConstraints` custom), confirma que
la imagen cumple. Lo que la app **necesita** del SCC:

- UID arbitrario asignado por OpenShift (sí, default).
- GID 0 supplementary (sí, default).
- `fsGroup: 0` (la imagen está alineada con `chgrp -R 0`).
- Acceso a `emptyDir` (sí, default).

Con `restricted-v2` (default en OKD 4.22) funciona sin ajustes.

### 1.5. Acceso al registry interno desde el SNO

El BuildConfig usa el registry interno OpenShift
(`image-registry.openshift-image-registry.svc:5000`). En SNO suele estar
activo por defecto:

```bash
oc get co image-registry
# Debe estar Available=True, Progressing=False, Degraded=False
```

Si está desactivado (`managementState: Removed`), habilítalo:

```bash
oc patch configs.imageregistry.operator.openshift.io/cluster \
    --type merge -p '{"spec":{"managementState":"Managed"}}'
```

### 1.6. Solo si vas a usar HTTPS con dominio propio

El default es una Route con dominio autogenerado
`scormbuilder-scormbuilder.apps.<cluster>.<base>`, con certificado del
Router. Si quieres un dominio propio:

1. Editar `deploy/openshift/51-route.yaml` y añadir `spec.host:
   tu-dominio.com`.
2. Cargar el certificado wildcard del Router (o uno específico) en el Router
   default, o usar `spec.tls.certificate` + `spec.tls.key` en la Route.
3. Apuntar el DNS de `tu-dominio.com` a la IP del Router.

---

## 2. Comprobaciones POST-despliegue (HACER TRAS EL PRIMER DESPLIEGUE)

### 2.1. Pod y Probes

```bash
oc -n scormbuilder get pods,svc,route,pvc
oc -n scormbuilder logs deployment/scormbuilder | tail -50
curl -sk https://$(oc -n scormbuilder get route scormbuilder -o jsonpath='{.spec.host}')/healthz
# → "ok"
```

### 2.2. Métricas accesibles

```bash
# Desde DENTRO del cluster (port-forward o pod auxiliar)
oc -n scormbuilder port-forward svc/scormbuilder 8080:8080 &
curl -s http://localhost:8080/metrics | grep scormbuilder_
# → debe mostrar líneas con scormbuilder_courses_total, _users_total, etc.

# Desde Prometheus UWM (si está habilitado, esperar ~2 min tras desplegar)
oc -n openshift-user-workload-monitoring get servicemonitor -A | grep scormbuilder
# → debe aparecer el ServiceMonitor del namespace scormbuilder
```

En la consola web de OpenShift: **Observe → Metrics → Custom queries**.
Probar:

```promql
scormbuilder_users_total
scormbuilder_jobs_active
rate(scormbuilder_jobs_started_total[5m])
scormbuilder_data_dir_bytes / 1024 / 1024 / 1024  # GB
```

### 2.3. Backup CronJob

```bash
# Ver el CronJob (debe quedar SUSPEND=False)
oc -n scormbuilder get cronjob scormbuilder-backup

# Lanzar un backup MANUAL para validar el primer día:
oc -n scormbuilder create job --from=cronjob/scormbuilder-backup manual-test
oc -n scormbuilder logs -f job/manual-test

# Comprobar que el fichero se creó
oc -n scormbuilder run inspect-backups --rm -it --restart=Never \
    --image=registry.access.redhat.com/ubi9/ubi-minimal \
    --overrides='{"spec":{"containers":[{"name":"i","image":"registry.access.redhat.com/ubi9/ubi-minimal","command":["ls","-lh","/backups"],"volumeMounts":[{"name":"b","mountPath":"/backups"}]}],"volumes":[{"name":"b","persistentVolumeClaim":{"claimName":"scormbuilder-backups"}}]}}'
```

### 2.4. Restauración de prueba (recomendado)

Antes de poner la app en producción real, haz un **test de restauración**
en otro namespace para validar que los backups son recuperables. El script
`deploy/restore.sh` es el procedimiento documentado.

---

## 3. Decisiones operativas pendientes (responder con el equipo de la app)

| Decisión | Por qué importa |
|---|---|
| Política de retención de backups (default 30 días) | Si tu RPO permite menos, ajustar `RETENTION_DAYS` en el CronJob y bajar tamaño del PVC. |
| Hora del CronJob (default 03:00 Europe/Madrid) | Coincidir con ventana de baja carga / fuera del horario laboral. |
| Quién recibe alertas de backup fallido | El CronJob deja Jobs en estado Failed; configurar `PrometheusRule` para alertar tras N días sin backup OK. |
| Backups OFF-cluster (rsync/SSH) | Soporte INCLUIDO pero apagado por defecto. Para activar: edita `deploy/openshift/22-backup-config.yaml` con host/user/path remoto, crea el Secret `scormbuilder-backup-ssh` con la clave privada, pon `BACKUP_SSH_ENABLED: "1"`. Ver sección "Activar sync OFF-cluster" más abajo. |
| Rotación de `ANTHROPIC_API_KEY` | El Secret es estático. Definir periodicidad y procedimiento (`oc set data secret/...`). |
| Cifrado del PVC | LVMS sobre LUKS si la información es sensible. Configurar a nivel cluster (no en estos manifiestos). |

---

## 4. Operaciones rutinarias (cheatsheet)

```bash
# Ver estado general
oc -n scormbuilder get all,pvc,cm,sa,role,rolebinding,cronjob,servicemonitor

# Logs de la aplicación
oc -n scormbuilder logs -f deployment/scormbuilder

# Logs del último backup
oc -n scormbuilder logs -l app.kubernetes.io/component=backup --tail=200

# Métricas en formato Prometheus
oc -n scormbuilder exec deployment/scormbuilder -- curl -s http://localhost:8080/metrics

# Reiniciar la app sin perder datos
oc -n scormbuilder rollout restart deployment/scormbuilder

# Drenar y vaciar PVC de backups (si se llena)
oc -n scormbuilder run cleanup-backups --rm -it --restart=Never \
    --image=registry.access.redhat.com/ubi9/ubi-minimal \
    --overrides='{"spec":{"containers":[{"name":"c","image":"registry.access.redhat.com/ubi9/ubi-minimal","command":["sh","-c","find /backups -name scormbuilder-\\*.tar.gz -mtime +60 -delete && ls -lh /backups"],"volumeMounts":[{"name":"b","mountPath":"/backups"}]}],"volumes":[{"name":"b","persistentVolumeClaim":{"claimName":"scormbuilder-backups"}}]}}'

# Re-escalar PVC (LVMS soporta expansión online)
oc -n scormbuilder patch pvc scormbuilder-data --type merge -p '{"spec":{"resources":{"requests":{"storage":"200Gi"}}}}'

# Suspender el CronJob temporalmente (mantenimiento)
oc -n scormbuilder patch cronjob scormbuilder-backup -p '{"spec":{"suspend":true}}'
oc -n scormbuilder patch cronjob scormbuilder-backup -p '{"spec":{"suspend":false}}'
```

---

## 5. Indicadores de salud para monitorizar

Crear estos PrometheusRule (no incluidos por defecto — depende de tu política):

| Alerta | Query | Severidad |
|---|---|---|
| App caída | `up{job="scormbuilder"} == 0` | critical |
| PVC datos al 90% | `kubelet_volume_stats_used_bytes / kubelet_volume_stats_capacity_bytes{persistentvolumeclaim="scormbuilder-data"} > 0.9` | warning |
| Backup no se ejecuta en 25 h | `time() - max(kube_cronjob_status_last_successful_time{cronjob="scormbuilder-backup"}) > 90000` | warning |
| Jobs colgados | `scormbuilder_jobs_active > 5 for 1h` | info |
| Crecimiento brusco de datos | `delta(scormbuilder_data_dir_bytes[24h]) > 5e9` | info |

---

## 6. Activar sync de backups OFF-cluster (rsync/SSH)

Por defecto los backups se quedan en el PVC `scormbuilder-backups` dentro del
cluster. Si el disco LVMS falla, los backups se pierden con los datos. El
CronJob soporta empujar cada tarball a un host remoto vía SSH (sin necesidad
de rsync). Pasos:

### 6.1. Preparar el host remoto

```bash
# En el host destino, crear usuario dedicado y carpeta:
sudo useradd -m -s /bin/bash scormbuilder-backup
sudo mkdir -p /srv/backups/scormbuilder
sudo chown scormbuilder-backup:scormbuilder-backup /srv/backups/scormbuilder
```

### 6.2. Generar clave SSH dedicada (en tu máquina admin)

```bash
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_rsa_scormbuilder_backup \
           -C "scormbuilder-backup@cluster"

# Copiar la pública al host remoto (CON restricciones para minimizar daño
# en caso de filtración):
PUB=$(cat ~/.ssh/id_rsa_scormbuilder_backup.pub)
ssh root@backup-server.tu-empresa.com bash <<EOF
cat >> /home/scormbuilder-backup/.ssh/authorized_keys <<EOF2
command="cat > /srv/backups/scormbuilder/\$(date +%s).tar.gz",no-pty,no-port-forwarding,no-X11-forwarding,no-agent-forwarding $PUB
EOF2
EOF
```

(El `command=` fuerza que la sesión SSH solo pueda escribir un fichero; ni
shell, ni listar, ni nada más).

### 6.3. Crear el Secret en el cluster

```bash
oc -n scormbuilder create secret generic scormbuilder-backup-ssh \
    --from-file=id_rsa=$HOME/.ssh/id_rsa_scormbuilder_backup
```

### 6.4. Editar ConfigMap y activar

```bash
# Editar BACKUP_SSH_HOST/USER/PATH a los valores reales
oc -n scormbuilder edit configmap scormbuilder-backup-config

# Activar:
oc -n scormbuilder patch configmap scormbuilder-backup-config \
    --type merge -p '{"data":{"BACKUP_SSH_ENABLED":"1"}}'
```

### 6.5. Validar con backup manual

```bash
oc -n scormbuilder create job --from=cronjob/scormbuilder-backup test-sync
oc -n scormbuilder logs -f job/test-sync
# Debe terminar con: "[backup-sync] ✓ copia remota completada"
```

Verifica en el host remoto que el fichero llegó:

```bash
ssh root@backup-server.tu-empresa.com ls -lh /srv/backups/scormbuilder/
```

### 6.6. Rotación en el host remoto

El CronJob solo limpia el PVC local; **el host remoto guarda todos los
backups recibidos**. Configura un cron en el host remoto para purgar antiguos:

```cron
# En el host remoto, en /etc/cron.daily/purge-scormbuilder-backups:
#!/bin/sh
find /srv/backups/scormbuilder -name '*.tar.gz' -mtime +90 -delete
```

---

## 7. Contacto / handoff

- Repo / paquete entregado: ver el zip indicado en el README principal.
- Documentación de despliegue: `deploy/README.md`.
- Manifiestos: `deploy/openshift/*.yaml`.
- Scripts: `deploy/deploy.sh`, `deploy/restore.sh`.
- Cualquier cambio que requiera permisos cluster-admin (UWM, capacidad LVMS,
  expansión PVC global, política PSP/SCC) → contactar con el administrador.

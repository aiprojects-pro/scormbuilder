# GitOps de secretos — Sealed Secrets o External Secrets Operator

El `Secret` que contiene `ANTHROPIC_API_KEY` (y opcionalmente `SMTP_PASSWORD`)
NO debe vivir en git en claro. Hay dos patrones soportados, según lo que
tenga (o quiera instalar) tu cluster:

| Patrón | Cuándo usar | Quién lo instala |
|---|---|---|
| **Sealed Secrets** (Bitnami) | Self-contained, no requiere store externo. Recomendado para SNO. | cluster-admin (operador en el cluster) |
| **External Secrets Operator (ESO)** | Tienes Vault, AWS Secrets Manager, GCP Secret Manager u otro store gestionado. | cluster-admin + admin del store |

Si no sabes cuál, ve por **Sealed Secrets**.

---

## Opción A — Sealed Secrets

### A.1. Instalación del controller (cluster-admin)

```bash
# Versión LTS estable a la fecha de redacción — comprobar la última en
# https://github.com/bitnami-labs/sealed-secrets/releases
SEAL_VERSION=v0.27.1

oc apply -f https://github.com/bitnami-labs/sealed-secrets/releases/download/${SEAL_VERSION}/controller.yaml

# Verificar
oc -n kube-system get pods -l app.kubernetes.io/name=sealed-secrets
```

### A.2. Instalar `kubeseal` cli (en tu máquina)

```bash
# macOS
brew install kubeseal

# Linux / RHEL
SEAL_VERSION=0.27.1
curl -L "https://github.com/bitnami-labs/sealed-secrets/releases/download/v${SEAL_VERSION}/kubeseal-${SEAL_VERSION}-linux-amd64.tar.gz" \
    | tar xz -C /tmp kubeseal
sudo mv /tmp/kubeseal /usr/local/bin/
```

### A.3. Generar el SealedSecret cifrado

```bash
# 1) Construye un Secret EN MEMORIA (no lo aplica al cluster, --dry-run)
oc -n scormbuilder create secret generic scormbuilder-secrets \
    --from-literal=ANTHROPIC_API_KEY='sk-ant-XXXXXXXX' \
    --from-literal=SMTP_PASSWORD='' \
    --dry-run=client -o yaml \
| kubeseal \
    --controller-namespace=kube-system \
    --controller-name=sealed-secrets-controller \
    --format=yaml \
> deploy/gitops/scormbuilder-secrets.sealed.yaml
```

El fichero `scormbuilder-secrets.sealed.yaml` resultante:
- Es **commit-able a git** (los valores van cifrados con la clave pública del controller).
- Solo el controller en tu cluster puede descifrarlo.
- Cuando lo aplicas con `oc apply`, el controller crea automáticamente el
  `Secret` real con los valores descifrados.

### A.4. Aplicar y verificar

```bash
oc apply -f deploy/gitops/scormbuilder-secrets.sealed.yaml

# Comprobar que el SealedSecret se ha descifrado:
oc -n scormbuilder get secret scormbuilder-secrets -o yaml | grep -E "data:|ANTHROPIC"

# Reiniciar el Deployment para que coja el nuevo Secret
oc -n scormbuilder rollout restart deployment/scormbuilder
```

### A.5. Rotar la clave (ej. invalidación por seguridad)

```bash
# Re-generar el SealedSecret con la nueva key:
oc -n scormbuilder create secret generic scormbuilder-secrets \
    --from-literal=ANTHROPIC_API_KEY='sk-ant-NUEVA' \
    --from-literal=SMTP_PASSWORD='' \
    --dry-run=client -o yaml \
| kubeseal \
    --controller-namespace=kube-system \
    --controller-name=sealed-secrets-controller \
    --format=yaml \
> deploy/gitops/scormbuilder-secrets.sealed.yaml

# Aplicar + reiniciar
oc apply -f deploy/gitops/scormbuilder-secrets.sealed.yaml
oc -n scormbuilder rollout restart deployment/scormbuilder
```

### A.6. Recuperación ante pérdida de clave del controller

El controller genera una clave privada al instalarse, almacenada en un Secret
en `kube-system`. **Si pierdes ese Secret, todos los SealedSecrets quedan
inservibles** (los datos cifrados ya no se pueden descifrar).

Backup recomendado (cluster-admin):

```bash
oc get secret -n kube-system -l sealedsecrets.bitnami.com/sealed-secrets-key \
    -o yaml > sealed-secrets-master-key-backup.yaml
# Guardar en sitio seguro (NO en el mismo cluster, NO en git público).
```

Restauración tras desastre:

```bash
oc apply -f sealed-secrets-master-key-backup.yaml
oc -n kube-system rollout restart deployment/sealed-secrets-controller
```

---

## Opción B — External Secrets Operator (ESO)

Más complejo pero limpio si ya tienes Vault u otro store.

### B.1. Instalación del operator (cluster-admin)

OperatorHub UI o via CLI:

```bash
oc apply -f - <<EOF
apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata:
  name: external-secrets-operator
  namespace: openshift-operators
spec: {}
---
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: external-secrets-operator
  namespace: openshift-operators
spec:
  channel: stable
  name: external-secrets-operator
  source: community-operators
  sourceNamespace: openshift-marketplace
EOF
```

### B.2. Configurar SecretStore (apunta a tu Vault/AWS/...)

Ejemplo con Vault interno del cluster:

```yaml
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: vault-backend
  namespace: scormbuilder
spec:
  provider:
    vault:
      server: "https://vault.vault.svc:8200"
      path: "secret"
      version: "v2"
      auth:
        kubernetes:
          mountPath: "kubernetes"
          role: "scormbuilder"
          serviceAccountRef:
            name: scormbuilder-eso
```

### B.3. Definir el ExternalSecret

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: scormbuilder-secrets
  namespace: scormbuilder
spec:
  refreshInterval: 1h          # re-lectura periódica → rotación automática
  secretStoreRef:
    name: vault-backend
    kind: SecretStore
  target:
    name: scormbuilder-secrets  # nombre del Secret resultante
    creationPolicy: Owner
  data:
    - secretKey: ANTHROPIC_API_KEY
      remoteRef:
        key: scormbuilder/api-keys
        property: anthropic
    - secretKey: SMTP_PASSWORD
      remoteRef:
        key: scormbuilder/api-keys
        property: smtp_password
```

### B.4. Aplicar

```bash
oc apply -f deploy/gitops/secretstore.yaml
oc apply -f deploy/gitops/externalsecret.yaml
```

El ExternalSecret tira de Vault y materializa el `Secret`
`scormbuilder-secrets`. Cuando rotes la entrada en Vault, ESO la re-lee al
cabo de `refreshInterval` y reinicia el Deployment si su `secretRef` lo
referencia (depende de tu setup).

---

## Cuál elegir

- **SNO sin Vault y sin GitOps muy estructurado** → Sealed Secrets.
- **Cluster grande con Vault o AWS** → External Secrets.
- **Sin tiempo / sin ganas de operator** → seguir con `oc create secret` manual
  (lo que documenta `deploy/README.md`).

Cualquiera de las 3 funciona con los manifiestos generados — solo cambia cómo
materializas el `Secret scormbuilder-secrets` en el namespace.

## Ficheros relacionados

```
deploy/gitops/
├── README.md                                   # este documento
├── scormbuilder-secrets.sealed.yaml.example    # plantilla de salida (REEMPLAZA con tu kubeseal)
├── seal-secret.sh                              # helper para regenerar el sealed
└── externalsecret.example.yaml                 # plantilla para Opción B
```

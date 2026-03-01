# Kubernetes Security Patterns

## Overview

This guide covers Kubernetes security best practices including Pod Security Standards, PodDisruptionBudgets, NetworkPolicies, and runtime security. These patterns reflect 2025-2026 best practices with the deprecation of PodSecurityPolicies (removed in K8s 1.25).

## Pod Security Standards (PSS)

Pod Security Standards replaced PodSecurityPolicies (removed in K8s 1.25). They are enforced via the built-in Pod Security Admission controller.

### Three Security Levels

**Privileged** - Unrestricted (only for system-level workloads):
```yaml
# No restrictions applied
```

**Baseline** - Prevents known privilege escalations:
```yaml
# Blocks: hostNetwork, hostPID, hostIPC, privileged containers,
#         hostPath volumes, host ports, certain capabilities
```

**Restricted** - Hardened (recommended for all application workloads):
```yaml
# Requires: non-root, read-only root FS, drop ALL capabilities,
#           seccomp profile, no privilege escalation
```

### Namespace-Level Enforcement

**Apply via labels on namespaces:**
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: production
  labels:
    # Enforce restricted for all pods
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/enforce-version: latest
    # Warn on baseline violations (helps migration)
    pod-security.kubernetes.io/warn: restricted
    pod-security.kubernetes.io/audit: restricted
```

**Exempt system namespaces:**
```yaml
# kube-system typically needs privileged access
apiVersion: v1
kind: Namespace
metadata:
  name: kube-system
  labels:
    pod-security.kubernetes.io/enforce: privileged
```

### Compliant Pod Spec (Restricted Level)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-server
  namespace: production
spec:
  replicas: 3
  selector:
    matchLabels:
      app: api-server
  template:
    metadata:
      labels:
        app: api-server
    spec:
      automountServiceAccountToken: false  # Disable unless needed
      securityContext:
        runAsNonRoot: true
        runAsUser: 65534
        runAsGroup: 65534
        fsGroup: 65534
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: api
          image: ghcr.io/org/api-server:v1.0.0@sha256:abc123...
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 512Mi
          ports:
            - containerPort: 8080
              protocol: TCP
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir:
            sizeLimit: 100Mi
```

## PodDisruptionBudgets (PDB)

PDBs protect application availability during voluntary disruptions (node drains, upgrades, scaling).

### Basic PDB

**Ensure minimum availability:**
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: api-server-pdb
spec:
  minAvailable: 2        # At least 2 pods must be running
  selector:
    matchLabels:
      app: api-server
```

**Or use maxUnavailable:**
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: api-server-pdb
spec:
  maxUnavailable: 1      # At most 1 pod can be down at a time
  selector:
    matchLabels:
      app: api-server
```

### PDB Best Practices

```yaml
# For stateless services (3+ replicas): allow 1 unavailable
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: web-pdb
spec:
  maxUnavailable: 1
  selector:
    matchLabels:
      app: web-server

---
# For stateful services: use percentage
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: db-pdb
spec:
  maxUnavailable: "33%"   # Allow disrupting 1/3 of replicas
  selector:
    matchLabels:
      app: database

---
# For singletons: minAvailable 0 allows drain (or use unhealthyPodEvictionPolicy)
# K8s 1.31+: unhealthyPodEvictionPolicy is GA
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: singleton-pdb
spec:
  minAvailable: 0
  unhealthyPodEvictionPolicy: AlwaysAllow  # Evict unhealthy pods during drain
  selector:
    matchLabels:
      app: singleton-worker
```

### Common Mistakes

- **PDB blocking node drain**: `minAvailable` equals replica count prevents any eviction
- **No PDB at all**: Upgrades can take down all pods simultaneously
- **PDB on single-replica deployments**: Use `maxUnavailable: 1` or `minAvailable: 0`

## NetworkPolicies

### Default Deny All

**Start with deny-all, then allowlist:**
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: production
spec:
  podSelector: {}         # Applies to ALL pods in namespace
  policyTypes:
    - Ingress
    - Egress
```

### Allow Specific Traffic

**Frontend to backend:**
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-frontend-to-backend
spec:
  podSelector:
    matchLabels:
      app: backend
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: frontend
      ports:
        - port: 8080
          protocol: TCP
```

**Allow DNS egress (required for most pods):**
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns
spec:
  podSelector: {}
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
      ports:
        - port: 53
          protocol: UDP
        - port: 53
          protocol: TCP
```

## RBAC Best Practices

### Least-Privilege Service Accounts

```yaml
# Dedicated service account per workload
apiVersion: v1
kind: ServiceAccount
metadata:
  name: api-server-sa
  namespace: production
  annotations:
    # Disable auto-mounting (also set in pod spec)
    kubernetes.io/enforce-mountable-secrets: "true"

---
# Minimal role
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: api-server-role
  namespace: production
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "list"]
    resourceNames: ["api-server-config"]  # Specific resource

---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: api-server-binding
  namespace: production
subjects:
  - kind: ServiceAccount
    name: api-server-sa
roleRef:
  kind: Role
  name: api-server-role
  apiGroup: rbac.authorization.k8s.io
```

### Audit RBAC Permissions

```bash
# Check what a service account can do
kubectl auth can-i --list --as=system:serviceaccount:production:api-server-sa -n production

# Find over-privileged roles
kubectl get clusterrolebindings -o json | jq '.items[] | select(.roleRef.name == "cluster-admin")'
```

## Image Security

### Use Digests, Not Tags

```yaml
# Bad: Tags are mutable
image: myapp:latest

# Good: Digests are immutable
image: ghcr.io/org/myapp@sha256:abc123def456...
```

### Admission Control for Images

**Kyverno policy (allowlist registries):**
```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: restrict-image-registries
spec:
  validationFailureAction: Enforce
  rules:
    - name: validate-registries
      match:
        any:
          - resources:
              kinds:
                - Pod
      validate:
        message: "Images must be from approved registries"
        pattern:
          spec:
            containers:
              - image: "ghcr.io/org/* | registry.internal/*"
```

## Secret Management

### External Secrets Operator

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: api-credentials
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: api-credentials
  data:
    - secretKey: api-key
      remoteRef:
        key: secret/data/api
        property: key
```

### Encrypt Secrets at Rest

```yaml
# EncryptionConfiguration (kube-apiserver)
apiVersion: apiserver.config.k8s.io/v1
kind: EncryptionConfiguration
resources:
  - resources:
      - secrets
    providers:
      - aescbc:
          keys:
            - name: key1
              secret: <base64-encoded-key>
      - identity: {}
```

## Runtime Security

### Seccomp Profiles

```yaml
# Use RuntimeDefault (blocks dangerous syscalls)
securityContext:
  seccompProfile:
    type: RuntimeDefault

# Or custom profile for stricter control
securityContext:
  seccompProfile:
    type: Localhost
    localhostProfile: profiles/strict.json
```

### Falco Runtime Monitoring

```yaml
# Falco rule: detect shell in container
- rule: Terminal shell in container
  desc: Detect a shell spawned in a container
  condition: >
    spawned_process and
    container and
    proc.name in (bash, sh, zsh)
  output: >
    Shell spawned in container
    (user=%user.name container=%container.name
     image=%container.image.repository)
  priority: WARNING
```

## Resource Limits

### Always Set Limits

```yaml
resources:
  requests:
    cpu: 100m        # Scheduling guarantee
    memory: 128Mi
  limits:
    cpu: 500m        # Hard cap (throttled, not killed)
    memory: 512Mi    # Hard cap (OOM-killed if exceeded)
```

### LimitRange (Namespace Defaults)

```yaml
apiVersion: v1
kind: LimitRange
metadata:
  name: default-limits
  namespace: production
spec:
  limits:
    - default:
        cpu: 500m
        memory: 512Mi
      defaultRequest:
        cpu: 100m
        memory: 128Mi
      type: Container
```

### ResourceQuota (Namespace Total)

```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: namespace-quota
  namespace: production
spec:
  hard:
    requests.cpu: "10"
    requests.memory: 20Gi
    limits.cpu: "20"
    limits.memory: 40Gi
    pods: "50"
```

## Security Checklist

1. **Pod Security Standards**: Enforce `restricted` on all application namespaces
2. **NetworkPolicies**: Default deny-all, then explicit allowlist
3. **RBAC**: Dedicated service accounts, no cluster-admin for apps
4. **Image digests**: Pin to SHA256, not tags
5. **PDBs**: Protect availability during upgrades
6. **Resource limits**: Set on every container
7. **Secrets**: Use External Secrets Operator, encrypt at rest
8. **Seccomp**: RuntimeDefault at minimum
9. **automountServiceAccountToken: false**: Unless actually needed
10. **Read-only root filesystem**: With emptyDir for /tmp if needed

## References

- [Kubernetes Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/)
- [Pod Security Admission](https://kubernetes.io/docs/concepts/security/pod-security-admission/)
- [PodDisruptionBudget Documentation](https://kubernetes.io/docs/tasks/run-application/configure-pdb/)
- [NetworkPolicy Documentation](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- [NSA/CISA Kubernetes Hardening Guide](https://media.defense.gov/2022/Aug/29/2003066362/-1/-1/0/CTR_KUBERNETES_HARDENING_GUIDANCE_1.2_20220829.PDF)
- [Kyverno Policy Engine](https://kyverno.io/)
- [External Secrets Operator](https://external-secrets.io/)

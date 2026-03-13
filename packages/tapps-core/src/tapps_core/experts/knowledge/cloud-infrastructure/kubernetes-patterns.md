# Kubernetes Patterns

## Overview

Kubernetes is a container orchestration platform that automates deployment, scaling, and management of containerized applications. This guide covers deployment patterns, services, ingress, and operational patterns.

## Version Status (as of 2026)

- **Kubernetes 1.35** - Current latest release
- **Kubernetes 1.34** - Maintained
- **Kubernetes 1.33** - Maintained (sidecar containers GA)
- **Kubernetes 1.32** (Dec 2024) - Memory Manager GA, StatefulSet PVC auto-cleanup, Custom Resource Field Selectors
- Containerd is the default container runtime (dockershim removed since 1.24)

## Core Concepts

### Pods

**Smallest Deployable Unit:**
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: myapp
spec:
  containers:
    - name: app
      image: myapp:1.0.0
      ports:
        - containerPort: 8080
```

### Deployments

**Declarative Updates:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp
spec:
  replicas: 3
  selector:
    matchLabels:
      app: myapp
  template:
    metadata:
      labels:
        app: myapp
    spec:
      containers:
        - name: app
          image: myapp:1.0.0
          resources:
            requests:
              memory: "256Mi"
              cpu: "250m"
            limits:
              memory: "512Mi"
              cpu: "500m"
```

### Services

**ClusterIP (Internal):**
```yaml
apiVersion: v1
kind: Service
metadata:
  name: myapp-service
spec:
  selector:
    app: myapp
  ports:
    - protocol: TCP
      port: 80
      targetPort: 8080
  type: ClusterIP
```

**LoadBalancer (External):**
```yaml
spec:
  type: LoadBalancer
  ports:
    - port: 80
      targetPort: 8080
```

### Ingress (Legacy) and Gateway API

**Ingress (legacy - still supported but being superseded):**
```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: myapp-ingress
spec:
  rules:
    - host: myapp.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: myapp-service
                port:
                  number: 80
```

**Gateway API v1.2+ (recommended replacement for Ingress):**

Gateway API provides more expressive, role-oriented routing. It is the successor to the Ingress resource and supports advanced traffic management including header-based routing, traffic splitting, and cross-namespace references.

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: myapp-gateway
spec:
  gatewayClassName: istio  # or nginx, envoy, etc.
  listeners:
    - name: http
      port: 80
      protocol: HTTP
---
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: myapp-route
spec:
  parentRefs:
    - name: myapp-gateway
  hostnames:
    - "myapp.example.com"
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /
      backendRefs:
        - name: myapp-service
          port: 80
```

**When to use Gateway API vs Ingress:**
- New clusters: Use Gateway API
- Existing clusters: Ingress still works; migrate to Gateway API when convenient
- Advanced routing (header matching, traffic splitting, gRPC): Gateway API required

## Sidecar Containers (GA in 1.33+)

Native sidecar containers are init containers with `restartPolicy: Always`. They start before main containers and run alongside them, solving lifecycle ordering issues with the traditional multi-container pod pattern.

```yaml
spec:
  initContainers:
    - name: log-collector
      image: fluentbit:latest
      restartPolicy: Always  # Makes it a native sidecar
      resources:
        requests:
          cpu: 50m
          memory: 64Mi
  containers:
    - name: app
      image: myapp:1.0.0
```

**Benefits over traditional sidecars:**
- Guaranteed startup order (sidecar starts before main container)
- Sidecar survives main container restarts
- Clean shutdown ordering (sidecar stops after main container)
- Proper Job completion (Jobs complete when main container finishes, not sidecar)

## Deployment Patterns

### Rolling Updates

**Zero-Downtime Deployments:**
```yaml
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
```

### Blue/Green Deployment

**Instant Switch:**
- Deploy new version (green)
- Test green deployment
- Switch traffic to green
- Keep blue for rollback

### Canary Deployment

**Gradual Rollout:**
- Deploy small percentage to new version
- Monitor metrics
- Gradually increase percentage
- Complete rollout or rollback

## Configuration Management

### ConfigMaps

**Non-Sensitive Configuration:**
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
data:
  config.yaml: |
    database:
      host: db.example.com
      port: 5432
```

**Use in Pods:**
```yaml
spec:
  containers:
    - name: app
      volumeMounts:
        - name: config
          mountPath: /etc/config
  volumes:
    - name: config
      configMap:
        name: app-config
```

### Secrets

**Sensitive Data:**
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: db-secret
type: Opaque
stringData:
  password: mypassword
```

## Autoscaling

### Horizontal Pod Autoscaler

**Scale Based on Metrics:**
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: myapp-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: myapp
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

### Vertical Pod Autoscaler

**Adjust Resource Requests:**
- Analyzes resource usage
- Adjusts requests and limits
- Optimizes resource allocation

## Resource Management

### Requests and Limits

**Guaranteed Resources:**
```yaml
resources:
  requests:
    memory: "256Mi"
    cpu: "250m"
  limits:
    memory: "512Mi"
    cpu: "500m"
```

**Quality of Service Classes:**
- **Guaranteed:** Requests = Limits
- **Burstable:** Requests < Limits
- **BestEffort:** No requests or limits

### Namespaces

**Resource Isolation:**
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: production
```

## Best Practices

1. **Use Deployments** for stateless applications
2. **Set resource requests and limits** for all containers
3. **Implement health checks** (liveness and readiness)
4. **Use ConfigMaps and Secrets** for configuration
5. **Label resources** consistently
6. **Use namespaces** for organization
7. **Implement autoscaling** for variable workloads
8. **Use rolling updates** for zero-downtime
9. **Monitor resource usage** and adjust accordingly
10. **Document** deployment configurations


# Firecrawl Kubernetes Deployment

This directory contains Kubernetes manifests and Skaffold configuration for deploying Firecrawl to Kubernetes.

## Architecture

The deployment consists of the following components:

- **API Service** (`firecrawl-api`): Main Node.js application
- **Playwright Service** (`playwright-service`): Web scraping service using Playwright
- **Go HTML to Markdown Service** (`go-html-to-md-service`): HTML conversion service
- **Redis**: Caching and job queue
- **RabbitMQ**: Message broker
- **PostgreSQL**: Database with custom initialization

## Prerequisites

1. **Kubernetes cluster** (minikube, kind, GKE, EKS, AKS, etc.)
2. **kubectl** configured to connect to your cluster
3. **Skaffold** (optional, for easier development workflow)
4. **NGINX Ingress Controller** (for ingress)

## Quick Start

### Using Skaffold (Recommended)

1. **Development deployment**:
   ```bash
   skaffold run -p dev
   ```

2. **Production deployment**:
   ```bash
   skaffold run -p prod
   ```

3. **Development with hot reload**:
   ```bash
   skaffold dev -p dev
   ```

### Using kubectl directly

1. **Apply all manifests**:
   ```bash
   kubectl apply -f k8s/
   ```

2. **Check deployment status**:
   ```bash
   kubectl get pods -n firecrawl
   kubectl get svc -n firecrawl
   ```

### Using Kustomize

1. **Development environment**:
   ```bash
   kubectl apply -k k8s/overlays/development
   ```

2. **Production environment**:
   ```bash
   kubectl apply -k k8s/overlays/production
   ```

## Configuration

### Secrets

Update the secrets in [`k8s/02-secrets.yaml`](k8s/02-secrets.yaml):

```bash
# Encode your secrets in base64
echo -n "your-secret-value" | base64

# Update the secrets file
kubectl edit secret firecrawl-secrets -n firecrawl
```

### Environment Variables

Modify the ConfigMap in [`k8s/01-configmap.yaml`](k8s/01-configmap.yaml) to adjust configuration.

## Services and Ports

| Service | Port | Description |
|---------|------|-------------|
| firecrawl-api | 3002 | Main API service |
| firecrawl-api | 8000 | FastAPI service |
| playwright-service | 3000 | Web scraping service |
| go-html-to-md-service | 8080 | HTML to Markdown conversion |
| redis | 6379 | Redis cache |
| rabbitmq | 5672 | AMQP port |
| rabbitmq | 15672 | Management UI |
| nuq-postgres | 5432 | PostgreSQL database |

## Accessing the Application

### Via NodePort (Development)
```bash
# API Service
curl http://localhost:30002/health

# FastAPI Service
curl http://localhost:30000/health
```

### Via Ingress (Production)
```bash
# Configure your hosts file or DNS
echo "127.0.0.1 firecrawl.local" >> /etc/hosts

# Access the API
curl https://firecrawl.local/health
```

### Via Port Forward (Development)
```bash
# Forward API port
kubectl port-forward svc/firecrawl-api 3002:3002 -n firecrawl

# Forward FastAPI port
kubectl port-forward svc/firecrawl-api 8000:8000 -n firecrawl

# Access locally
curl http://localhost:3002/health
curl http://localhost:8000/health
```

## Monitoring

### Health Checks

All services include health checks:

```bash
# Check API health
kubectl exec -it deployment/firecrawl-api -n firecrawl -- curl localhost:3002/health

# Check Playwright service health
kubectl exec -it deployment/playwright-service -n firecrawl -- curl localhost:3000/health

# Check Go service health
kubectl exec -it deployment/go-html-to-md-service -n firecrawl -- curl localhost:8080/health
```

### Logs

```bash
# API logs
kubectl logs -f deployment/firecrawl-api -n firecrawl

# Playwright logs
kubectl logs -f deployment/playwright-service -n firecrawl

# Database logs
kubectl logs -f deployment/nuq-postgres -n firecrawl
```

## Scaling

### Manual Scaling

```bash
# Scale API service
kubectl scale deployment firecrawl-api --replicas=5 -n firecrawl

# Scale Playwright service
kubectl scale deployment playwright-service --replicas=3 -n firecrawl
```

### Horizontal Pod Autoscaling

HPA is configured automatically for `firecrawl-api` and `playwright-service`:

```bash
# Check HPA status
kubectl get hpa -n firecrawl

# View HPA details
kubectl describe hpa firecrawl-api-hpa -n firecrawl
```

## Backup and Persistence

### Database Backup

```bash
# Create database backup
kubectl exec -it deployment/nuq-postgres -n firecrawl -- pg_dump -U postgres postgres > backup.sql

# Restore database
kubectl exec -i deployment/nuq-postgres -n firecrawl -- psql -U postgres postgres < backup.sql
```

### Persistent Volumes

PostgreSQL uses persistent storage via PVC. To backup/restore PVCs:

```bash
# List PVCs
kubectl get pvc -n firecrawl

# Backup PVC data (using a backup tool like Velero)
velero backup create firecrawl-backup --include-namespaces=firecrawl
```

## Troubleshooting

### Common Issues

1. **Pods not starting**: Check resource limits and node capacity
   ```bash
   kubectl describe pods -n firecrawl
   kubectl top nodes
   ```

2. **Database connection issues**: Verify PostgreSQL is running and accessible
   ```bash
   kubectl logs deployment/nuq-postgres -n firecrawl
   kubectl exec -it deployment/nuq-postgres -n firecrawl -- psql -U postgres -c "SELECT 1"
   ```

3. **Service discovery issues**: Check DNS and service endpoints
   ```bash
   kubectl get endpoints -n firecrawl
   kubectl exec -it deployment/firecrawl-api -n firecrawl -- nslookup redis
   ```

4. **Ingress not working**: Verify ingress controller and SSL certificates
   ```bash
   kubectl get ingress -n firecrawl
   kubectl describe ingress firecrawl-ingress -n firecrawl
   ```

### Debug Commands

```bash
# Get all resources
kubectl get all -n firecrawl

# Describe a failing pod
kubectl describe pod <pod-name> -n firecrawl

# Get events
kubectl get events -n firecrawl --sort-by=.metadata.creationTimestamp

# Shell into a pod
kubectl exec -it deployment/firecrawl-api -n firecrawl -- /bin/bash
```

## Development Workflow with Skaffold

### File Sync
Skaffold supports file synchronization for faster development:

```bash
# Start development with file sync
skaffold dev -p dev

# Edit source files - changes will be synced automatically
# - Node.js files in apps/api/src/
# - TypeScript files in apps/playwright-service-ts/
# - Go files in apps/go-html-to-md-service/
```

### Profiles

- **dev**: Local development with file sync and reduced resources
- **prod**: Production build with optimizations and security
- **local**: Use pre-built images from registry

### Custom Commands

```bash
# Build only
skaffold build

# Deploy only (using existing images)
skaffold deploy

# Delete deployment
skaffold delete
```

## Security Considerations

### Production Security

1. **Update secrets**: Change default passwords and API keys
2. **Network policies**: Implement network segmentation
3. **Pod security**: Use security contexts and policies
4. **TLS**: Configure proper SSL/TLS certificates
5. **RBAC**: Implement role-based access control

### Security Patches

The production overlay includes:
- Non-root containers
- Read-only root filesystem where possible
- Dropped capabilities
- Security contexts

## Performance Tuning

### Resource Allocation

Adjust resource requests and limits based on your workload:

```yaml
resources:
  requests:
    memory: "4Gi"
    cpu: "2000m"
  limits:
    memory: "8Gi"
    cpu: "4000m"
```

### Database Optimization

Tune PostgreSQL settings in the deployment:

```yaml
env:
- name: POSTGRES_SHARED_BUFFERS
  value: "256MB"
- name: POSTGRES_MAX_CONNECTIONS
  value: "200"
```

### Redis Configuration

Optimize Redis for your use case:

```yaml
command:
- redis-server
- --maxmemory 512mb
- --maxmemory-policy allkeys-lru
```

## Upgrading

### Rolling Updates

Kubernetes supports rolling updates by default:

```bash
# Update image tag
kubectl set image deployment/firecrawl-api api=ghcr.io/firecrawl/firecrawl:v2.0.0 -n firecrawl

# Check rollout status
kubectl rollout status deployment/firecrawl-api -n firecrawl

# Rollback if needed
kubectl rollout undo deployment/firecrawl-api -n firecrawl
```

### Database Migrations

For database schema updates:

```bash
# Run migrations as a Kubernetes Job
kubectl apply -f k8s/migration-job.yaml
```

## Contributing

When adding new services:

1. Create deployment and service manifests
2. Add health checks and resource limits
3. Update Skaffold configuration
4. Add to both development and production overlays
5. Update this documentation

## License

This Kubernetes deployment configuration is part of the Firecrawl project and follows the same license terms.
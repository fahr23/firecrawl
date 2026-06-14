# Firecrawl Kubernetes & Skaffold Integration

## Overview

I've successfully added comprehensive Kubernetes deployments and Skaffold integration to the Firecrawl project. This enables easy deployment and development workflows on Kubernetes clusters with support for multiple environments.

## What's Been Added

### 🏗️ Kubernetes Manifests (`/k8s/`)

1. **Core Infrastructure**
   - `00-namespace.yaml` - Dedicated namespace for isolation
   - `01-configmap.yaml` - Environment configuration
   - `02-secrets.yaml` - Sensitive data management
   
2. **Data Layer**
   - `10-redis.yaml` - Redis cache with health checks
   - `11-rabbitmq.yaml` - RabbitMQ message broker
   - `12-postgres.yaml` - PostgreSQL with persistent storage
   
3. **Application Services**
   - `20-go-html-to-md.yaml` - HTML to Markdown service (2 replicas)
   - `21-playwright-service.yaml` - Web scraping service (2 replicas)
   - `30-api.yaml` - Main API service (3 replicas with init containers)
   
4. **Networking & Scaling**
   - `40-ingress.yaml` - NGINX ingress with TLS + NodePort fallback
   - `50-hpa.yaml` - Horizontal Pod Autoscaler for API and Playwright services

### 🚀 Skaffold Configuration (`/skaffold.yaml`)

- **Multi-image builds** for all custom services
- **File synchronization** for fast development
- **Multiple profiles**:
  - `dev` - Development with local builds and file sync
  - `prod` - Production optimized builds
  - `local` - Use pre-built registry images
- **Port forwarding** for local access
- **Health verification** checks

### 🔧 Kustomize Overlays (`/k8s/overlays/`)

**Development Environment** (`development/`):
- Reduced resource requirements
- Single replica deployments
- Debug logging enabled
- Development-specific configuration

**Production Environment** (`production/`):
- High resource limits (up to 12Gi RAM, 6 CPU cores)
- Multiple replicas (5 API, 4 Playwright, 3 Go service)
- Security contexts and policies
- Production-optimized settings

### 📋 Deployment Automation

- **`deploy.sh`** - Comprehensive deployment script with:
  - Environment selection (dev/prod)
  - Multiple deployment methods (Skaffold/kubectl)
  - Status checking and log viewing
  - Safe deletion with confirmation
  - Color-coded output and error handling

- **`k8s/README.md`** - Complete deployment documentation

- **`k8s/.env.example`** - Configuration template

## Key Features

### 🔄 Development Workflow
```bash
# Start development with hot reload
skaffold dev -p dev

# Quick deployment
./deploy.sh --environment dev

# Check status
./deploy.sh --action status
```

### 🏭 Production Deployment
```bash
# Deploy to production
skaffold run -p prod

# Or with script
./deploy.sh --environment prod --profile prod
```

### 📊 Monitoring & Scaling

- **Health checks** for all services
- **Resource limits** and requests defined
- **Horizontal Pod Autoscaling** based on CPU/memory
- **Persistent storage** for PostgreSQL
- **Service discovery** via Kubernetes DNS

### 🔒 Security

- **Security contexts** in production
- **Non-root containers** where possible
- **Secret management** for sensitive data
- **Network isolation** via namespaces
- **TLS termination** at ingress level

### 🔧 Flexibility

- **Multi-environment** support (dev/prod)
- **Kustomize overlays** for environment-specific configs
- **Skaffold profiles** for different workflows
- **NodePort fallback** when ingress isn't available
- **Init containers** to ensure proper startup order

## Resource Requirements

### Development Environment
- **Total CPU**: ~4.5 cores
- **Total Memory**: ~8Gi
- **Storage**: ~10Gi (PostgreSQL PVC)

### Production Environment  
- **Total CPU**: ~15 cores
- **Total Memory**: ~35Gi
- **Storage**: ~10Gi (PostgreSQL PVC)

## Quick Start Commands

```bash
# 1. Deploy to development
./deploy.sh --environment dev

# 2. Access services (port-forward method)
kubectl port-forward svc/firecrawl-api 3002:3002 -n firecrawl-dev
curl http://localhost:3002/health

# 3. Check status
./deploy.sh --action status --environment dev

# 4. View logs
kubectl logs -f deployment/firecrawl-api -n firecrawl-dev

# 5. Scale services
kubectl scale deployment firecrawl-api --replicas=5 -n firecrawl-dev

# 6. Clean up
./deploy.sh --action delete --environment dev
```

## Service Access Methods

1. **Port Forward** (Development):
   ```bash
   kubectl port-forward svc/firecrawl-api 3002:3002 -n firecrawl-dev
   ```

2. **NodePort** (Testing):
   ```bash
   curl http://<node-ip>:30002/health
   ```

3. **Ingress** (Production):
   ```bash
   curl https://firecrawl.local/health
   ```

## Architecture Benefits

- ✅ **Cloud-native** deployment ready
- ✅ **Scalable** with HPA and multiple replicas  
- ✅ **Resilient** with health checks and restart policies
- ✅ **Secure** with proper RBAC and security contexts
- ✅ **Observable** with comprehensive logging
- ✅ **Maintainable** with clear separation of concerns
- ✅ **Portable** across any Kubernetes cluster

This implementation provides a production-ready Kubernetes deployment that can scale from development to enterprise-grade production environments.
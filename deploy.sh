#!/bin/bash

# Firecrawl Kubernetes Deployment Script
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
ENVIRONMENT="dev"
NAMESPACE=""
PROFILE=""
ACTION="deploy"
WAIT="true"

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to show usage
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "OPTIONS:"
    echo "  -e, --environment ENV    Environment: dev, prod (default: dev)"
    echo "  -n, --namespace NS       Kubernetes namespace (default: firecrawl-ENV)"
    echo "  -a, --action ACTION      Action: deploy, delete, status (default: deploy)"
    echo "  -p, --profile PROFILE    Skaffold profile: dev, prod, local"
    echo "  -w, --wait BOOL          Wait for deployment (default: true)"
    echo "  -h, --help               Show this help message"
    echo ""
    echo "EXAMPLES:"
    echo "  $0 --environment dev                  # Deploy to development"
    echo "  $0 --environment prod --profile prod  # Deploy to production"
    echo "  $0 --action delete --environment dev  # Delete development deployment"
    echo "  $0 --action status                    # Check deployment status"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -e|--environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        -a|--action)
            ACTION="$2"
            shift 2
            ;;
        -p|--profile)
            PROFILE="$2"
            shift 2
            ;;
        -w|--wait)
            WAIT="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Set default namespace if not provided
if [ -z "$NAMESPACE" ]; then
    NAMESPACE="firecrawl-$ENVIRONMENT"
fi

# Set default profile if not provided
if [ -z "$PROFILE" ]; then
    PROFILE="$ENVIRONMENT"
fi

# Validate environment
if [[ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "prod" ]]; then
    print_error "Invalid environment: $ENVIRONMENT. Must be 'dev' or 'prod'"
    exit 1
fi

# Check if kubectl is installed
if ! command -v kubectl &> /dev/null; then
    print_error "kubectl is not installed or not in PATH"
    exit 1
fi

# Check if skaffold is installed for deploy action
if [[ "$ACTION" == "deploy" ]] && ! command -v skaffold &> /dev/null; then
    print_error "skaffold is not installed or not in PATH"
    print_info "You can install it from: https://skaffold.dev/docs/install/"
    exit 1
fi

# Function to check if namespace exists
namespace_exists() {
    kubectl get namespace "$1" &> /dev/null
}

# Function to deploy using Skaffold
deploy_skaffold() {
    print_info "Deploying Firecrawl to $ENVIRONMENT environment using Skaffold..."
    print_info "Profile: $PROFILE, Namespace: $NAMESPACE"
    
    if ! namespace_exists "$NAMESPACE"; then
        print_info "Creating namespace: $NAMESPACE"
        kubectl create namespace "$NAMESPACE"
    fi
    
    local skaffold_args="run --profile=$PROFILE"
    if [ "$WAIT" == "true" ]; then
        skaffold_args="$skaffold_args --wait-for-deployments"
    fi
    
    if skaffold $skaffold_args; then
        print_info "Deployment successful!"
        show_status
    else
        print_error "Deployment failed!"
        exit 1
    fi
}

# Function to deploy using kubectl and kustomize
deploy_kubectl() {
    print_info "Deploying Firecrawl to $ENVIRONMENT environment using kubectl..."
    
    if ! namespace_exists "$NAMESPACE"; then
        print_info "Creating namespace: $NAMESPACE"
        kubectl create namespace "$NAMESPACE"
    fi
    
    local overlay_path="k8s/overlays/$ENVIRONMENT"
    
    if [ -d "$overlay_path" ]; then
        kubectl apply -k "$overlay_path"
    else
        kubectl apply -f k8s/
    fi
    
    if [ "$WAIT" == "true" ]; then
        print_info "Waiting for deployments to be ready..."
        kubectl wait --for=condition=available deployment --all -n "$NAMESPACE" --timeout=600s
    fi
    
    print_info "Deployment completed!"
    show_status
}

# Function to delete deployment
delete_deployment() {
    print_warning "Deleting Firecrawl deployment from namespace: $NAMESPACE"
    read -p "Are you sure? This action cannot be undone. (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if command -v skaffold &> /dev/null; then
            print_info "Using Skaffold to delete deployment..."
            skaffold delete --profile="$PROFILE"
        else
            print_info "Using kubectl to delete deployment..."
            local overlay_path="k8s/overlays/$ENVIRONMENT"
            if [ -d "$overlay_path" ]; then
                kubectl delete -k "$overlay_path" --ignore-not-found=true
            else
                kubectl delete -f k8s/ --ignore-not-found=true
            fi
        fi
        print_info "Deployment deleted successfully!"
    else
        print_info "Deletion cancelled."
    fi
}

# Function to show deployment status
show_status() {
    print_info "Deployment Status for namespace: $NAMESPACE"
    echo ""
    
    if namespace_exists "$NAMESPACE"; then
        echo "=== PODS ==="
        kubectl get pods -n "$NAMESPACE" -o wide
        echo ""
        
        echo "=== SERVICES ==="
        kubectl get svc -n "$NAMESPACE"
        echo ""
        
        echo "=== DEPLOYMENTS ==="
        kubectl get deployments -n "$NAMESPACE"
        echo ""
        
        echo "=== INGRESS ==="
        kubectl get ingress -n "$NAMESPACE" 2>/dev/null || echo "No ingress found"
        echo ""
        
        echo "=== HPA ==="
        kubectl get hpa -n "$NAMESPACE" 2>/dev/null || echo "No HPA found"
        echo ""
        
        # Check if any pods are not running
        local failed_pods=$(kubectl get pods -n "$NAMESPACE" --field-selector=status.phase!=Running --no-headers 2>/dev/null | wc -l)
        if [ "$failed_pods" -gt 0 ]; then
            print_warning "Some pods are not in Running state:"
            kubectl get pods -n "$NAMESPACE" --field-selector=status.phase!=Running
        fi
    else
        print_warning "Namespace $NAMESPACE does not exist"
    fi
}

# Function to show logs
show_logs() {
    print_info "Recent logs from namespace: $NAMESPACE"
    echo ""
    
    if namespace_exists "$NAMESPACE"; then
        local deployments=$(kubectl get deployments -n "$NAMESPACE" -o jsonpath='{.items[*].metadata.name}')
        for deployment in $deployments; do
            print_info "Logs from $deployment:"
            kubectl logs deployment/"$deployment" -n "$NAMESPACE" --tail=10
            echo ""
        done
    else
        print_warning "Namespace $NAMESPACE does not exist"
    fi
}

# Main execution
case $ACTION in
    deploy)
        if command -v skaffold &> /dev/null; then
            deploy_skaffold
        else
            print_warning "Skaffold not found, falling back to kubectl"
            deploy_kubectl
        fi
        ;;
    delete)
        delete_deployment
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    *)
        print_error "Invalid action: $ACTION. Must be 'deploy', 'delete', 'status', or 'logs'"
        usage
        exit 1
        ;;
esac
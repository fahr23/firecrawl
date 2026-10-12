#!/bin/bash
echo "Waking up services in the firecrawl namespace..."
kubectl scale deployment --all --replicas=1 -n firecrawl
echo "Waiting for services to become ready..."
kubectl rollout status deployment/nuq-postgres -n firecrawl --timeout=60s
kubectl rollout status deployment/redis -n firecrawl --timeout=60s
kubectl rollout status deployment/rabbitmq -n firecrawl --timeout=60s
echo "Workspace is online and ready to use!"

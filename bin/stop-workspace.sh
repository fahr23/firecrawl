#!/bin/bash
echo "Scaling down all services in the firecrawl namespace to 0 to save resources..."
kubectl scale deployment --all --replicas=0 -n firecrawl
echo "Workspace is now fully hibernated."

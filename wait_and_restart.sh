#!/bin/bash
echo "Waiting for images to finish building..."
wait
echo "Restarting deployments..."
kubectl rollout restart deployment/turkish-financial-api -n firecrawl
kubectl rollout restart deployment/academic-search-api -n firecrawl
kubectl rollout restart deployment/firecrawl-api -n firecrawl
echo "Done!"

#!/usr/bin/env bash
# Build the Turkish Financial workspace images for the Hetzner node (linux/amd64)
# from this fork and push them to GHCR as private packages.
#
#   deploy/turkish-financial/build-push.sh [TAG]     (default TAG: git short SHA)
#
# Then set the same TAG in overlays/hetzner/kustomization.yaml.
set -euo pipefail

ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
TAG="${1:-$(git -C "$ROOT" rev-parse --short HEAD)}"
REGISTRY="${REGISTRY:-ghcr.io/fahr23}"
PLATFORM="${PLATFORM:-linux/amd64}"

build() {
  local name="$1" context="$2"; shift 2
  echo "==> $REGISTRY/$name:$TAG ($context)"
  docker buildx build --platform "$PLATFORM" --provenance=false \
    -t "$REGISTRY/$name:$TAG" "$@" --push "$ROOT/$context"
}

build turkish-financial-api        projects/turkish_financial --target runtime
build firecrawl-nuq-postgres       apps/nuq-postgres
build firecrawl-go-html-to-md      apps/go-html-to-md-service
build firecrawl-playwright-service apps/playwright-service-ts
build firecrawl-api                apps/api

echo "pushed tag: $TAG"

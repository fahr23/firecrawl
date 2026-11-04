#!/usr/bin/env bash
# Build Data Hub images locally (linux/amd64) and import them straight into the
# Hetzner node's k3s containerd over SSH — no GHCR push or pull. Use this when
# GHCR limits are reached.
#
#   deploy/data-hub/build-import.sh [TAG] [IMAGE...]
#     TAG     default: git short SHA
#     IMAGE   default: all; any of turkish-financial-api firecrawl-nuq-postgres
#             firecrawl-go-html-to-md firecrawl-playwright-service firecrawl-api
#
# Images keep their ghcr.io names, and every container uses
# imagePullPolicy: IfNotPresent, so k3s runs the imported copy. Then set the
# same TAG in overlays/hetzner/kustomization.yaml and run ./deploy-hetzner.sh.
set -euo pipefail

ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
TAG="${1:-$(git -C "$ROOT" rev-parse --short HEAD)}"
shift || true
REGISTRY="${REGISTRY:-ghcr.io/fahr23}"
PLATFORM="${PLATFORM:-linux/amd64}"
SSH_HOST="${SSH_HOST:-f23}"

# macOS bash 3.2 has no associative arrays.
context_for() {
  case "$1" in
    turkish-financial-api)        echo "projects/turkish_financial --target runtime" ;;
    firecrawl-nuq-postgres)       echo "apps/nuq-postgres" ;;
    firecrawl-go-html-to-md)      echo "apps/go-html-to-md-service" ;;
    firecrawl-playwright-service) echo "apps/playwright-service-ts" ;;
    firecrawl-api)                echo "apps/api" ;;
    *) echo "unknown image: $1" >&2; return 1 ;;
  esac
}

if [ $# -gt 0 ]; then
  IMAGES=("$@")
else
  IMAGES=(turkish-financial-api firecrawl-nuq-postgres firecrawl-go-html-to-md
          firecrawl-playwright-service firecrawl-api)
fi

for name in "${IMAGES[@]}"; do
  read -r context extra <<<"$(context_for "$name")"
  ref="$REGISTRY/$name:$TAG"
  echo "==> $ref ($context)"
  # shellcheck disable=SC2086
  docker buildx build --platform "$PLATFORM" --provenance=false \
    -t "$ref" $extra --load "$ROOT/$context"
  echo "--> importing into k3s on $SSH_HOST"
  docker save "$ref" | gzip -1 | ssh "$SSH_HOST" 'gunzip | k3s ctr -n k8s.io images import -'
done

echo "imported tag: $TAG"

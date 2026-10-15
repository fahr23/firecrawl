#!/usr/bin/env bash
# Deploy the Turkish Financial workspace to the Hetzner k3s node (f23).
# Idempotent: safe to re-run after changing manifests or image tags.
#
# Prerequisite: images pushed with ./build-push.sh <tag>, and the same tag set
# in overlays/hetzner/kustomization.yaml.
set -euo pipefail

CTX="${KUBE_CONTEXT:-hetzner-production}"
NS=turkish-financial
DIR="$(cd "$(dirname "$0")" && pwd)"
k() { kubectl --context "$CTX" "$@"; }

k apply -f "$DIR/overlays/hetzner/namespace.yaml"

# Private GHCR pull secret: reuse backtofuture-prod's (same GHCR account).
if ! k -n "$NS" get secret ghcr-pull-secret >/dev/null 2>&1; then
  k -n backtofuture-prod get secret ghcr-pull-secret -o json \
    | jq 'del(.metadata.namespace, .metadata.uid, .metadata.resourceVersion,
              .metadata.creationTimestamp, .metadata.ownerReferences,
              .metadata.managedFields, .metadata.annotations)' \
    | k -n "$NS" apply -f -
fi

# App secret: generated once, never committed. Postgres only reads it on first init.
if ! k -n "$NS" get secret turkish-financial-secrets >/dev/null 2>&1; then
  k -n "$NS" create secret generic turkish-financial-secrets \
    --from-literal=POSTGRES_PASSWORD="$(openssl rand -hex 24)"
fi

k apply -k "$DIR/overlays/hetzner"
k -n "$NS" rollout status deploy/postgres --timeout=5m
k -n "$NS" rollout status deploy/turkish-financial-api --timeout=5m
k -n "$NS" get pods

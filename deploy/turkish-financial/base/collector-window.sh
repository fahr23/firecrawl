#!/usr/bin/env bash
# Collector window for the Turkish Financial workspace.
#
#   collect.sh collect        wake the Firecrawl stack, run Firecrawl-backed
#                             collections, put the stack back to 0, then run the
#                             collections that do not need Firecrawl.
#   collect.sh sleep-if-idle  safety net: scale the stack to 0 when no collector
#                             pod is running (e.g. a collect pod was killed).
set -uo pipefail

NS="${POD_NAMESPACE:?POD_NAMESPACE is required}"
API="${FINANCE_API_URL:-http://turkish-financial-api:8000}"
# Dependencies first; firecrawl-api's init containers wait for them anyway.
DEPS="redis rabbitmq go-html-to-md-service playwright-service"
STACK="firecrawl-api $DEPS"

log() { echo "[$(date -u +%FT%TZ)] $*"; }

sleep_stack() {
  log "scaling Firecrawl stack to 0"
  # shellcheck disable=SC2086
  kubectl -n "$NS" scale deploy $STACK --replicas=0
}

wake_stack() {
  log "waking Firecrawl stack"
  # shellcheck disable=SC2086
  kubectl -n "$NS" scale deploy $DEPS --replicas=1 || return 1
  for d in $DEPS; do
    kubectl -n "$NS" rollout status "deploy/$d" --timeout=5m || return 1
  done
  kubectl -n "$NS" scale deploy firecrawl-api --replicas=1 || return 1
  kubectl -n "$NS" rollout status deploy/firecrawl-api --timeout=10m || return 1
}

failures=0

# post NAME PATH JSON_BODY TIMEOUT_SECONDS
post() {
  local name="$1" path="$2" body="$3" timeout="$4" code
  log "-> $name"
  code=$(curl -sS -o /tmp/out.json -w '%{http_code}' --max-time "$timeout" \
    -H 'Content-Type: application/json' -X POST "$API$path" -d "$body") || code=000
  log "<- $name HTTP $code: $(head -c 500 /tmp/out.json 2>/dev/null)"
  case "$code" in
    200|409) ;;  # 409: İş Yatırım collection already running
    *) failures=$((failures + 1)) ;;
  esac
}

collect() {
  local days="${DAYS_BACK:-2}"

  # The stack must never be left running, including on timeout/termination.
  trap 'exit 143' TERM INT
  trap sleep_stack EXIT

  if wake_stack; then
    post "KAP disclosures" /api/v1/scrapers/kap \
      "{\"days_back\": $days}" "${KAP_TIMEOUT_SECONDS:-3600}"
    post "news sentiment" /api/external/v1/news-sentiment/collect \
      "{\"days_back\": $days}" 1800
    if [ -n "${SOCIAL_TICKERS:-}" ]; then
      tickers=$(jq -cn --arg t "$SOCIAL_TICKERS" '$t | split(",") | map(gsub("\\s"; "")) | map(select(length > 0))')
      post "social sentiment" /api/external/v1/social-sentiment/collect \
        "{\"tickers\": $tickers, \"days_back\": $days, \"limit_per_ticker\": ${SOCIAL_LIMIT_PER_TICKER:-20}}" 1800
    fi
  else
    log "Firecrawl stack did not become ready; skipping Firecrawl-backed collections"
    failures=$((failures + 1))
  fi

  sleep_stack
  trap - EXIT

  # These run inside the finance pod and do not use Firecrawl.
  post "YouTube sentiment" /api/external/v1/youtube-sentiment/collect \
    "{\"days_back\": $days, \"limit_per_channel\": ${YOUTUBE_LIMIT_PER_CHANNEL:-10}}" 3600
  if [ "${ISYATIRIM_ENABLED:-true}" = "true" ]; then
    # Starts a paced background task in the finance pod; poll
    # GET /api/external/v1/isyatirim/fundamentals/collection-status for progress.
    post "İş Yatırım fundamentals" /api/external/v1/isyatirim/fundamentals/collect \
      '{"force": false}' 60
  fi

  log "done with $failures failure(s)"
  [ "$failures" -eq 0 ]
}

sleep_if_idle() {
  running=$(kubectl -n "$NS" get pods -l app=collector-window,mode=collect \
    --field-selector=status.phase=Running -o name)
  if [ -n "$running" ]; then
    log "collector running ($running); leaving the stack alone"
    return 0
  fi
  sleep_stack
}

case "${1:-collect}" in
  collect) collect ;;
  sleep-if-idle) sleep_if_idle ;;
  *) echo "usage: $0 [collect|sleep-if-idle]" >&2; exit 2 ;;
esac

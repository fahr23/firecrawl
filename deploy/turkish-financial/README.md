# Turkish Financial workspace

The Turkish Financial API with its own Firecrawl stack, in its own namespace.

| Cluster | Context | Namespace | API |
|---|---|---|---|
| Local (OrbStack) | `orbstack` | `turkish-financial` | `http://localhost:30080`, `http://turkish.localhost:32080` |
| Production (Hetzner k3s, node f23) | `hetzner-production` | `turkish-financial` | in-cluster only (see below) |

## How it runs

- **Always on:** `turkish-financial-api` and `postgres` (≈0.3 GiB used). They serve all
  `GET` endpoints from stored data.
- **Scaled to 0:** `firecrawl-api`, `playwright-service`, `go-html-to-md-service`, `redis`,
  `rabbitmq`. The `collector-window` CronJob (daily 07:00 Europe/Istanbul) wakes them
  with 1 replica each, collects KAP, news and (if `SOCIAL_TICKERS` is set) X, then
  scales them back to 0 before running the YouTube and İş Yatırım collections. Peak
  during the window is ≈2–3 GiB. `collector-window-sleeper` puts the stack back to 0
  hourly if a collect run died before cleaning up.
- One Postgres holds both the finance data (database `turkish_financial`) and
  Firecrawl's job queue (database `postgres`).

## Calling it from backtofuture (f23)

```
http://turkish-financial-api.turkish-financial.svc.cluster.local:8000/api/external/v1
```

Production has no Ingress and no NodePort. NetworkPolicies allow ingress to the API
only from `app: strategy-management` pods in `backtofuture-prod` (and from within this
namespace). The namespace is `turkish-financial` on both clusters, so F23's
`EXTERNAL_ANALYSIS_API_URL` is the same in every overlay. Endpoints are
documented in `backtofuture/docs/CLIENT_GUIDE.md`; replace its `localhost:8000` base.

## Deploy

Local (arm64 images built by skaffold / docker compose from this repo):

```
kubectl --context orbstack apply -k deploy/turkish-financial/overlays/local
```

Production:

```
deploy/turkish-financial/build-push.sh <tag>     # linux/amd64 images -> ghcr.io/fahr23 (private)
# set <tag> in overlays/hetzner/kustomization.yaml
deploy/turkish-financial/deploy-hetzner.sh
```

`deploy-hetzner.sh` creates the namespace, copies `ghcr-pull-secret` from
`backtofuture-prod`, generates `turkish-financial-secrets` (random Postgres password,
never committed) on first run, and applies the overlay. The namespace has a
ResourceQuota (2 GiB requests / 6 GiB limits) and the same Pod Security level as
`backtofuture-prod`.

## Operate

```
# run a collection now
kubectl -n <ns> create job --from=cronjob/collector-window collect-now
kubectl -n <ns> logs -f job/collect-now

# copy finance data between clusters (target API stopped while restoring)
kubectl --context <src> -n <src-ns> exec deploy/postgres -- \
  pg_dump -U postgres -d turkish_financial -n turkish_financial --clean --if-exists --no-owner \
| kubectl --context <dst> -n <dst-ns> exec -i deploy/postgres -- \
  psql -U postgres -d turkish_financial -v ON_ERROR_STOP=1 -q
```

Collector settings (`DAYS_BACK`, `SOCIAL_TICKERS`, `YOUTUBE_LIMIT_PER_CHANNEL`,
`ISYATIRIM_ENABLED`, schedule) are in `base/collector-window.yaml`.

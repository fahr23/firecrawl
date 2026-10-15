# Academic Search workspace

The Academic Search API (scholarly literature search) in its own namespace, laid out
like `deploy/data-hub/`.

| Cluster | Context | Namespace | API |
|---|---|---|---|
| Local (OrbStack) | `orbstack` | `academic-search` | `http://localhost:30081`, `http://academic.localhost:32080` |

## How it runs

- One pod, `academic-search-api` (port 8010, health `GET /api/v1/health`).
- Projects and saved searches are a SQLite file (`/data/projects.db`) on the
  `academic-project-data` PVC, so the deployment is **replicas: 1, strategy: Recreate**:
  two pods must never write the file at once.
- No Firecrawl. Firecrawl research is disabled (`ACADEMIC_ENABLE_FIRECRAWL_RESEARCH=false`);
  the API calls scholarly providers directly. To enable it, run a Firecrawl and set
  `FIRECRAWL_API_URL` in `base/config.yaml`.

## Deploy

```
docker compose build academic-search-api
kubectl --context orbstack apply -k deploy/academic-search/overlays/local
kubectl --context orbstack -n academic-search rollout restart deploy/academic-search-api
```

## Secrets

Optional provider keys go in a Secret the deployment reads if present:

```
kubectl --context orbstack -n academic-search create secret generic academic-search-secrets \
  --from-literal=SEMANTIC_SCHOLAR_API_KEY=... --from-literal=ACADEMIC_SEARCH_EMAIL=...
```

## Copy the project store from a previous namespace

```
kubectl --context orbstack -n <old-ns> exec deploy/academic-search-api -- cat /data/projects.db \
  > /tmp/projects.db
kubectl --context orbstack -n academic-search cp /tmp/projects.db \
  "$(kubectl --context orbstack -n academic-search get pod -l app=academic-search-api -o name | cut -d/ -f2)":/data/projects.db
kubectl --context orbstack -n academic-search rollout restart deploy/academic-search-api
```

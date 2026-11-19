# Academic Search workspace

The Academic Search API (scholarly literature search) in its own namespace, laid out
like `deploy/data-hub/`.

| Cluster | Context | Namespace | API |
|---|---|---|---|
| Local (OrbStack) | `orbstack` | `academic-search` | `http://localhost:30081`, `http://academic.localhost:32080` |

## How it runs

- One pod, `academic-search-api` (port 8010, health `GET /api/v1/health`).
- Projects, saved search evidence, and the local literature library use the SQLite
  file `/data/projects.db` on the
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
  --from-literal=CLARIVATE_API_KEY=... --from-literal=SEMANTIC_SCHOLAR_API_KEY=... \
  --from-literal=ACADEMIC_SEARCH_EMAIL=...
```

Web of Science also needs `ACADEMIC_ENABLE_CLARIVATE: "true"` in `base/config.yaml` (on by default).
The optional `OPENALEX_API_KEY` in `academic-search-secrets` increases the budget
for OpenAlex literature, journal, and topic discovery requests.
Set `CORE_API_KEY` in the same Secret to make authenticated CORE requests.
Without `SEMANTIC_SCHOLAR_API_KEY`, Semantic Scholar's shared anonymous quota often answers 429,
which the API reports as `rate_limited`.

For optional manuscript assistance, use `OPENAI_API_KEY` with
`ACADEMIC_OPENAI_MODEL`, or `ANTHROPIC_API_KEY` with
`ACADEMIC_ANTHROPIC_MODEL`. Use a model ID enabled for your account. Set the
pair in the local Compose environment (for example, an untracked `.env` file),
or add the variables to the existing `academic-search-secrets` in the local
OrbStack namespace. Restart the service after changing its environment.

## Back up the project store

Use SQLite's backup API to include committed changes from the write-ahead log.

```
kubectl --context orbstack -n academic-search exec deploy/academic-search-api -- python -c '
from pathlib import Path
import sqlite3, sys, tempfile
with sqlite3.connect("file:/data/projects.db?mode=ro", uri=True) as source:
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "projects.db"
        snapshot = sqlite3.connect(path)
        try:
            source.backup(snapshot)
            snapshot.execute("PRAGMA journal_mode = DELETE")
        finally:
            snapshot.close()
        sys.stdout.buffer.write(path.read_bytes())
' > academic-projects-backup.db
sqlite3 academic-projects-backup.db 'PRAGMA integrity_check;'
```

To restore into a deployment, stop the application before replacing the database
on its volume. Retain the previous database and its SQLite sidecar files as a
separate backup. Restore the snapshot as `projects.db` in a directory with no
sidecar files from the previous database, then start the application.

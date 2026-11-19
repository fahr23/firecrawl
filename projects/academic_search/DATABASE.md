# Academic Search database

The app stores projects, dated evidence, and an indexed literature library in one
SQLite database. The local deployment keeps it at `/data/projects.db` on the
academic data volume. A standalone installation can set
`ACADEMIC_PROJECT_DB_PATH` to another path. The SQLite build must have FTS5.

## Search behavior

| Request | Behavior |
| --- | --- |
| `GET /api/v1/search?mode=online&q=...` | Calls the selected providers and saves retrieved paper metadata. Live records come first. If a provider fails or is rate limited, saved matches from that provider can fill space on the results page. |
| `GET /api/v1/search?mode=cache&q=...` | Reads the most recent complete page for the same query, category, providers, year range, page, and page size. It uses the local index when no exact page is available. The web app uses this for the preview. |
| `GET /api/v1/search?mode=local&q=...` | Searches the shared library. Search by keywords, double-quoted phrases, or full DOI. Category and publication-year filters apply. Supply `providers` to filter observations by source. |
| `GET /api/v1/library/status` | Returns the work and provider observation counts and the last saved time. |

A successful empty response refreshes the exact cache page. A failed or partial
response leaves the last complete page available and still adds any papers it
did retrieve to the library. The response reports the current provider statuses
and labels any saved copies, with the observation timestamp on each copy.
Provider relevance and publication-year filters still apply to live search.
The **Discover** tab has a recent-paper feed ordered by publication date.

Saved-only search works with the app running locally while scholarly APIs are
unreachable. It covers metadata the app has retrieved, including abstracts when
supplied. It does not download or archive publishers' full text.

```bash
curl --get http://localhost:8010/api/v1/search \
  --data-urlencode 'mode=local' \
  --data-urlencode 'q="demand forecasting"' \
  --data-urlencode 'year_min=2023'
```

## Schema

| Table | Data and relationships |
| --- | --- |
| `literature_works` | A stable ID, normalized DOI where known, searchable bibliographic fields, publication year, derived category, and first and last observation times. |
| `literature_urls` | A unique normalized HTTP(S) URL linked to a work. DOI and URL are used to identify existing works. |
| `literature_observations` | Provider, source URL, latest observation time, and source-specific metadata JSON. Unique per work, provider, and source URL. |
| `literature_queries` and `literature_query_pages` | Search parameters and the timestamp and metadata of the most recent completely retrieved page for each page number and size. |
| `literature_query_hits` | Ordered references from a cached page to the provider observations. The membership and rank reflect that page's successful search. Metadata can incorporate later observations of the same source record. |
| `literature_fts` | Full-text index for title, abstract, authors, journal, and keywords. Database triggers maintain the index when works change. |
| `research_projects`, `search_runs`, `journal_search_runs`, `journal_fit_runs` | Topics and their dated search or assessment snapshots. Each snapshot retains the data used at the time, independently of changes to the library. |
| `workspace_revisions` | Versioned entries for discovery, shortlists, submissions, manuscripts, and the academic dossier. A saved shortlist entry retains a copy and its source reference. |
| `literature_migrations` | Applied data migration markers. The first library migration indexes paper metadata from previous searches and workspace evidence without altering those snapshots. |
| `research_watches` and `research_watch_hits` | Saved query and schedule per topic, provider coverage, last attempt and complete refresh, and deduplicated work memberships with discovery and seen times. |
| `paper_open_events` and `paper_reading` | One idempotent event per in-app link open, with the URL and UTC time. Explicit read markers live on the canonical work and follow it across topics. |
| `portfolio_activities` and `portfolio_activity_versions` | Shared evidence and its revision snapshots, with the source topic and activity ID when copied from an earlier dossier. A dossier criterion records the selected evidence and the versions it reviewed. |
| `daily_reading_schedules` | One configurable reading schedule per topic, with the source list, keywords, local time zone, start date, and daily paper count. |
| `daily_reading_editions` | One edition per topic and its local calendar date. Records the settings used for the edition, provider coverage, trend windows, check time, and retry state. |
| `daily_reading_papers` | Ranked paper snapshots retained by edition, with a unique work ID across all daily editions. Read markers come from the shared `paper_reading` table. |
| `manuscript_autosaves` | Latest recoverable edit for each manuscript, with its base revision and an optimistic write version. Saving a named manuscript version clears the recovery copy. |
| `special_issue_calls`, `special_issue_queries` | Official call snapshots and short-lived records of listing coverage by query. Dates, evidence, and last successful verification remain in the local catalog. |
| `special_issue_targets`, `special_issue_attempts`, `special_issue_alerts` | Links to saved submission opportunities, background check attempts, and changes to tracked publisher deadlines or status. |
| `journal_favorites`, `journal_favorite_aliases` | Shared followed journals, verified OpenAlex and ISSN identities, catalog aliases, and separate refresh outcomes for publications and publisher policies. Unfollowing pauses checks and keeps the history. |
| `journal_favorite_papers` | One entry for each followed journal and canonical library work, with a publication snapshot, first-seen time, and an optional acknowledgement time. Opens and read markers come from the shared library. |

Submission tracking stores each status, deadline, and reviewer-comment revision
in `workspace_revisions`. Calendar exports derive from the latest revision and
the saved official calls. Watching a query updates the shared paper index and
its inbox without replacing the exact interactive query cache.
Followed journals also populate the shared paper index and reuse the official
call catalog. A failed refresh keeps the last successfully retrieved feed and
publisher evidence alongside the latest source status.

SQLite foreign keys protect references and transactions keep each ranked cache
page and its paper observations consistent. The deployment runs a single
application replica against the persistent volume. Use a SQLite online backup to
copy the live database, since recent changes can still reside in its write-ahead
log. See [local deployment and backup instructions](../../deploy/academic-search/README.md).

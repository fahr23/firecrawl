# From literature search to an academic publishing workspace

Repository review, 18 November 2026

## What the project supports today

The strongest foundation is the saved research project. It already brings together a research question, literature searches, journal samples, and manuscript-fit reports in one SQLite project with dated evidence exports. Build the publishing workflow on that record so you can revisit the papers, search settings, and journal evidence behind each decision.

| Research task | What works now | What the workspace still needs |
| --- | --- | --- |
| Find related literature | Searches scholarly providers, merges duplicate records, filters by year and broad category, and records queries, provider coverage, and paper links. | A way to keep selected papers across searches, record inclusion decisions, and follow new work in a saved topic. The web API currently saves the first results page of a search. |
| Identify hot topics and research gaps | The Python package extracts frequent terms. Its optional LLM analyzer can suggest gaps from individual abstracts. | Publication trends, a recent-paper feed, and proposed research questions grounded in specific studies, contradictory findings, or limitations. |
| Write a manuscript | The package exports BibTeX and RIS. The web app compares a title, abstract, and keywords with one saved journal sample. | A reading matrix, claim-to-source links, a study plan, versioned manuscript outlines, and a draft review tailored to the target journal and study design. |
| Find venues accepting submissions | The journal catalog browses OpenAlex, Web of Science/JCR, Scopus, and TÜBİTAK UBYT, subject to provider access. Journal snapshots show related published papers. | A shortlist that verifies regular submission windows and special-issue deadlines on official pages and captures scope, accepted article types, fees, and submission instructions. |
| Plan for doçentlik or professorship | Project exports can serve as part of a research record. The UBYT catalog displays publication incentive information by journal. | A dossier tied to the target ÜAK field and application period or to a specific university’s appointment criteria, with evidence for each claimed activity. |

The relevant code is in [service.py](academic_search/service.py), [project_store.py](academic_search/project_store.py), [analyzers.py](academic_search/analyzers.py), and [journal_analysis.py](academic_search/journal_analysis.py). Manuscript fit measures vocabulary overlap with a saved sample and lists the closest articles. Treat the score as a reading aid and inspect the journal’s aims and scope to make the submission decision.

## What to fix before relying on the workflow

- **Provider failures can appear as a literature gap.** A mocked OpenAlex HTTP 429 came back from the general search API as `empty`. A failed journal search was cached and subsequently accepted as input for a successful fit report. Preserve the difference between a successful search with zero matches, a provider failure, and a sample too small to assess. Keep failure records in search history and exclude them from reusable fit evidence. Add current OpenAlex API key support for higher limits and cursor paging beyond the first page. [OpenAlex API authentication](https://help.openalex.org/api/authentication/)
- **A clean checkout has zero UBYT records.** The source workbook is tracked, but the generated CSV is ignored and the runtime reads that CSV. Generate it during a reproducible build or package a versioned catalog, and show its release date and record count. Verify that the installed image works with no host bind mount. [TÜBİTAK 2026 UBYT announcement](https://ulakbim.tubitak.gov.tr/tubitak-2026-ubyt-dergi-listesi-ilan-edildi/)
- **The current service assumes a trusted workspace.** The API stores manuscript text with fit reports and includes it in project evidence. The project routes have no app-level authentication. Require authenticated project access before exposing the workspace to collaborators, and let authors decide whether to include unpublished text in an export or send it to an external writing model.

## Features to build in order

### 1. Topic discovery and a reading shortlist

Start from a field, seed query, or saved project. Show the latest papers by publication date and quantify which subtopics are growing. For an initial implementation, use OpenAlex aggregate counts, comparing the share of the selected field in two comparable completed time windows. Display raw counts, both date ranges, the field denominator, and links to representative papers. Flag sparse samples and indexing lag. Keep preprints distinguishable from peer-reviewed papers. [OpenAlex grouping reference](https://help.openalex.org/api/grouping/)

Let the researcher save papers across searches and capture study design, region or population, datasets, methods, findings, and limitations. A proposed gap should show the papers that suggest it and any evidence that challenges it, plus a feasible question and what data or method could answer it. The researcher marks a candidate gap as reviewed after checking the underlying literature and recent reviews.

**First usable result.** Open a saved project, inspect a rising subtopic and its supporting papers, save a reading shortlist, and record a research question with a feasible method and data source.

### 2. Verified submission opportunities

Start with a project shortlist and allow researchers to save official URLs. Verify regular journal submissions on the journal’s official submission or author page. Verify special issues and collections on the official call page. Springer Nature and Sage provide publisher call listings, and DergiPark journal pages can show when a journal is closed for submissions. Extend to conferences or workshops when their proceedings fit the researcher’s goals. [Springer Nature collections](https://www.springernature.com/la/authors/publish-an-article/collections) · [Sage calls for papers](https://journals.sagepub.com/special-issue-calls-for-papers) · [DergiPark journal submission example](https://dergipark.org.tr/en/pub/bilimname)

For each opportunity, record the ISSN, article type, scope, official source and submission links, deadline and published time zone, fees, and last verification time. Capture searchable status as open, upcoming, closed, or unverified. Keep a regular submission that is open without a deadline distinct from a collection whose deadline could not be determined. Match journals by ISSN and show the source and relevant year for any index claim. Keep an independent status for each special issue, even if its parent journal has another open route. [Official TR Dizin journal list](https://search.trdizin.gov.tr/tr/dergi-listesi)

**First usable result.** Compare three candidate venues, see at least one officially verified submission route, and recheck the status before starting a submission. A changed or expired deadline updates the card and keeps a dated record of the earlier call.

### 3. Evidence-linked manuscript workspace

Turn the saved question, methodology, and reading shortlist into an editable outline for the selected article type. Link substantive claims to inspected sources and page, section, or figure locations where available. Make missing evidence visible in the draft. Verify citation metadata and check whether the cited source actually supports the claim. Use the author’s supplied data and results for the results section, and use version history to review suggested edits. Provide a journal-specific checklist for length, abstract format, required declarations, and applicable reporting guidance. Reuse BibTeX and RIS for reference-manager export and start with a Markdown outline. [EQUATOR reporting guidance](https://equator-network.org/about/reporting-guidelines.html) · [CRediT contributor roles](https://credit.niso.org/)

**First usable result.** Export an outline, evidence table, references, and a submission checklist. Each major literature claim can be traced to a paper, and requirements or missing evidence appear next to the relevant section.

### 4. Academic dossier and progression

For a Türkiye-based workflow, start with the researcher’s target bilim alanı and ÜAK application period. Store the official document and clause beside each checklist item, with dated evidence for article type, authorship, publication status, and index coverage in the relevant year. For professorship, use the institution and position to select applicable appointment criteria and record relevant teaching, supervision, research projects, and publications. Show publication incentives as a separate TÜBİTAK program benefit alongside the evidence for each appointment or title criterion. [ÜAK application guide, October 2025 example](https://www.uak.gov.tr/documents/documents/69089c461afac.pdf) · [Official faculty appointment regulation](https://www.resmigazete.gov.tr/eskiler/2018/06/20180612-6.htm) · [TÜBİTAK UBYT program announcement](https://ulakbim.tubitak.gov.tr/tubitak-2026-ubyt-dergi-listesi-ilan-edildi/)

**First usable result.** Export a dossier checklist for the selected route, with each item linked to dated evidence and each rule awaiting review visibly marked. Load the rules for the actual application period and institution before drawing eligibility conclusions.

## Validation and scope

- Built the Python 3.11 Compose test image and ran the full `academic_search/tests` directory. **69 passed, one live integration test skipped.**
- Served the UI and health route through FastAPI’s test client from a tracked-files-only snapshot in the container. Both returned HTTP 200 and health reported zero UBYT journals.
- Reproduced the OpenAlex rate-limit reporting and journal-cache findings with mocked provider responses and an in-memory database.
- The review covers the existing code and a proposed roadmap. Live provider access was outside the test run. Personalized topics and calls for papers depend on the researcher’s field or working manuscript title.

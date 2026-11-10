const form = document.querySelector("#search-form");
const queryInput = document.querySelector("#query");
const categorySelect = document.querySelector("#category");
const providerOptions = document.querySelector("#providers");
const selectAllSourcesButton = document.querySelector("#select-all-sources");
const unavailableSources = document.querySelector("#sources-unavailable");
const sourceCount = document.querySelector("#source-count");
const statusText = document.querySelector("#status");
const resultTitle = document.querySelector("#result-title");
const resultsList = document.querySelector("#results");
const emptyState = document.querySelector("#empty-state");
const categoryStrip = document.querySelector("#category-strip");
const resultsSection = document.querySelector(".results-section");
const submitButton = form.querySelector("button[type='submit']");
const projectSelect = document.querySelector("#project-select");
const newProjectButton = document.querySelector("#new-project");
const exportProjectButton = document.querySelector("#export-project");
const projectDialog = document.querySelector("#project-dialog");
const projectForm = document.querySelector("#project-form");
const cancelProjectButton = document.querySelector("#cancel-project");
const createProjectButton = projectForm.querySelector("button[type='submit']");
const projectError = document.querySelector("#project-error");
const historyPanel = document.querySelector("#history-panel");
const historyToggle = document.querySelector("#history-toggle");
const historyCount = document.querySelector("#history-count");
const searchHistory = document.querySelector("#search-history");
const coverage = document.querySelector("#coverage");
const journalForm = document.querySelector("#journal-form");
const journalProviderSelect = document.querySelector("#journal-provider");
const journalCategorySelect = document.querySelector("#journal-category");
const journalCatalogStatus = document.querySelector("#journal-catalog-status");
const journalNameInput = document.querySelector("#journal-name");
const journalTopicsInput = document.querySelector("#journal-topics");
const journalSuggestions = document.querySelector("#journal-suggestions");
const selectedJournalBox = document.querySelector("#selected-journal");
const journalStatus = document.querySelector("#journal-status");
const refreshJournalButton = document.querySelector("#refresh-journal");
const journalResults = document.querySelector("#journal-results");
const journalSnapshotStatus = document.querySelector("#journal-snapshot-status");
const journalResultTitle = document.querySelector("#journal-result-title");
const journalRefreshBadge = document.querySelector("#journal-refresh-badge");
const journalProfile = document.querySelector("#journal-profile");
const journalPapers = document.querySelector("#journal-papers");
const manuscriptPanel = document.querySelector("#manuscript-panel");
const manuscriptForm = document.querySelector("#manuscript-form");
const fitReport = document.querySelector("#fit-report");
const journalHistoryPanel = document.querySelector("#journal-history-panel");
const journalHistory = document.querySelector("#journal-history");

const journalCatalogCard = document.querySelector("#journal-catalog-card");
const journalPager = document.querySelector("#journal-pager");
const journalFirstButton = document.querySelector("#journal-first");
const journalPrevButton = document.querySelector("#journal-prev");
const journalNextButton = document.querySelector("#journal-next");
const journalLastButton = document.querySelector("#journal-last");
const journalPageInput = document.querySelector("#journal-page-input");
const journalPageLabel = document.querySelector("#journal-page-label");
const journalSortSelect = document.querySelector("#journal-sort");
const journalSortField = document.querySelector("#journal-sort-field");
const journalPageSizeSelect = document.querySelector("#journal-page-size");

const resultsPager = document.querySelector("#results-pager");
const resultsFirstButton = document.querySelector("#results-first");
const resultsPrevButton = document.querySelector("#results-prev");
const resultsNextButton = document.querySelector("#results-next");
const resultsLastButton = document.querySelector("#results-last");
const resultsPageInput = document.querySelector("#results-page-input");
const resultsPageLabel = document.querySelector("#results-page-label");

const state = {
  catalogQuery: "",
  catalogPage: 1,
  catalogPages: null,
  categories: new Map(),
  projects: new Map(),
  selectedJournal: null,
  journalSnapshot: null,
  journalProviders: new Map(),
  resultsPage: 1,
  resultsHasMore: false,
};
const PROVIDER_IDS = {
  "openalex": "openalex",
  "semantic scholar": "semantic-scholar",
  "arxiv": "arxiv",
  "pubmed": "pubmed",
  "core": "core",
  "web of science": "clarivate",
  "scopus": "scopus",
  "sciencedirect": "science-direct",
  "google scholar": "google-scholar",
  "firecrawl research": "firecrawl-research",
};

const SOURCES = [
  { id: "openalex", label: "OpenAlex" },
  { id: "semantic-scholar", label: "Semantic Scholar" },
  { id: "arxiv", label: "arXiv" },
  { id: "pubmed", label: "PubMed" },
  { id: "core", label: "CORE" },
  { id: "clarivate", label: "Web of Science", missing: "Clarivate API key" },
  { id: "scopus", label: "Scopus", missing: "Elsevier API key" },
  { id: "science-direct", label: "ScienceDirect", missing: "institutional Elsevier access" },
  { id: "google-scholar", label: "Google Scholar", missing: "Serper API key" },
  { id: "firecrawl-research", label: "Firecrawl Research", missing: "research proxy" },
];

const COVERAGE_LABELS = {
  responded: "results",
  empty: "no matches",
  rate_limited: "rate limited",
  failed: "failed",
  unavailable: "not set up",
};

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

const tryFormatter = new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY", maximumFractionDigits: 0 });
const numberFormatter = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 3 });

function ubytText(ubyt) {
  const indexes = [...(ubyt.indexes || []), ubyt.source].filter(Boolean).join(", ");
  return [
    ubyt.list,
    ubyt.payment_tl != null ? tryFormatter.format(ubyt.payment_tl) : null,
    ubyt.mep_score != null ? `MEP ${numberFormatter.format(ubyt.mep_score)}` : null,
    indexes || null,
  ].filter(Boolean).join(" · ");
}

function ubytSourceText(ubyt) {
  const file = (ubyt.provenance || "").replace(/^list:/, "");
  const match = ubyt.matched_by === "name"
    ? "Matched by exact journal title (no ISSN match) — verify before relying on it"
    : ubyt.matched_issn ? `Matched by ISSN ${ubyt.matched_issn}` : "Found by searching the list";
  return [
    `Source: ${ubyt.list} list${file ? ` (${file})` : ""}, published by TÜBİTAK`,
    `Listed as: ${ubyt.journal_name}`,
    `ISSN ${ubyt.issn || "—"} · eISSN ${ubyt.eissn || "—"}`,
    match,
    "Payment, MEP score and SCIE/SSCI/AHCI flags are copied from the list as published.",
  ].join("\n");
}

// Journal-level UBYT payment; papers matched only by title are flagged so they can be checked.
function ubytBadge(ubyt, { showMissing = false } = {}) {
  if (!ubyt) {
    return showMissing ? element("span", "ubyt-badge missing", "Not on the UBYT list") : null;
  }
  const badge = element("span", "ubyt-badge", ubytText(ubyt));
  badge.title = ubytSourceText(ubyt);
  if (ubyt.matched_by === "name") badge.append(element("small", "", " (title match)"));
  return badge;
}

function populateCategories(payload) {
  for (const category of payload.categories || []) {
    state.categories.set(category.id, category);
    const option = element("option", "", category.label);
    option.value = category.id;
    categorySelect.append(option);

    const chip = element("span", "category-chip", category.label);
    chip.title = category.description;
    categoryStrip.append(chip);
  }
}

function renderSourceOptions() {
  for (const source of SOURCES) {
    const option = element("label", "source-option");
    const checkbox = element("input");
    checkbox.type = "checkbox";
    checkbox.value = source.id;
    checkbox.checked = source.id === "openalex";
    option.append(checkbox, element("span", "", source.label));
    providerOptions.append(option);
  }
}

function sourceCheckboxes() {
  return [...providerOptions.querySelectorAll("input[type='checkbox']")];
}

function selectedProviders() {
  return sourceCheckboxes()
    .filter((checkbox) => checkbox.checked && !checkbox.disabled)
    .map((checkbox) => checkbox.value);
}

function setSelectedProviders(value) {
  const wanted = new Set(String(value || "openalex").split(",").filter(Boolean));
  for (const checkbox of sourceCheckboxes()) {
    checkbox.checked = wanted.has(checkbox.value) && !checkbox.disabled;
  }
  if (!selectedProviders().length) setSelectedProviders("openalex");
  updateSelectAllLabel();
}

function applyProviderAvailability(payload) {
  const missing = [];
  for (const checkbox of sourceCheckboxes()) {
    const source = SOURCES.find((candidate) => candidate.id === checkbox.value);
    const enabled = payload.providers?.[source.id] === true;
    checkbox.disabled = !enabled;
    if (!enabled) checkbox.checked = false;
    checkbox.closest(".source-option").hidden = !enabled;
    if (!enabled) missing.push(`${source.label} (${source.missing || "not configured"})`);
  }
  unavailableSources.textContent = missing.length ? `Not set up on this server: ${missing.join(", ")}.` : "";
  unavailableSources.hidden = !missing.length;
  if (!selectedProviders().length) setSelectedProviders("openalex");
  updateSelectAllLabel();
}

function updateSelectAllLabel() {
  const enabled = sourceCheckboxes().filter((checkbox) => !checkbox.disabled);
  const allSelected = enabled.every((checkbox) => checkbox.checked);
  selectAllSourcesButton.textContent = allSelected ? "Reset to OpenAlex" : "Select all";
  sourceCount.textContent = `${selectedProviders().length} of ${enabled.length} selected`;
}

function selectedProjectId() {
  return projectSelect.value || null;
}

function applyProjectDefaults(project) {
  categorySelect.value = project.default_category || "all";
  setSelectedProviders(project.default_providers);
  document.querySelector("#year-min").value = project.default_year_min || "";
  document.querySelector("#year-max").value = project.default_year_max || "";
}

function historyItem(search) {
  const item = element("li", "history-item");
  const title = element("strong", "", search.query);
  const detail = element(
    "span", "",
    `${search.returned_count} linked result${search.returned_count === 1 ? "" : "s"} · ${search.category} · ${new Date(search.retrieved_at).toLocaleString()}`
  );
  const repeat = element("button", "secondary", "Repeat search");
  repeat.type = "button";
  repeat.addEventListener("click", () => repeatSearch(search));
  item.append(title, detail, repeat);
  return item;
}

function repeatSearch(search) {
  const manifest = search.manifest || {};
  queryInput.value = search.query || "";
  categorySelect.value = search.category || "all";
  document.querySelector("#year-min").value = search.year_min || "";
  document.querySelector("#year-max").value = search.year_max || "";
  document.querySelector("#limit").value = search.limit_value || manifest.limit || "20";
  const requested = (search.providers || manifest.providers_requested || [])
    .map((provider) => PROVIDER_IDS[String(provider).toLowerCase()] || String(provider).toLowerCase());
  const available = new Set(
    sourceCheckboxes().filter((checkbox) => !checkbox.disabled).map((checkbox) => checkbox.value)
  );
  if (!requested.length || requested.some((provider) => !available.has(provider))) {
    statusText.textContent = "That search's source is not available here; pick a source and search again.";
    return;
  }
  setSelectedProviders(requested.join(","));
  runSearch();
}

function setHistoryExpanded(expanded) {
  historyToggle.setAttribute("aria-expanded", String(expanded));
  searchHistory.hidden = !expanded;
}

async function refreshHistory() {
  const projectId = selectedProjectId();
  searchHistory.replaceChildren();
  historyPanel.hidden = !projectId;
  if (!projectId) return;
  const response = await fetch(`/api/v1/projects/${projectId}/searches?limit=50`);
  if (!response.ok) return;
  const payload = await response.json();
  for (const search of payload.searches) searchHistory.append(historyItem(search));
  historyCount.textContent = payload.searches.length
    ? `(${payload.searches.length})`
    : "";
  setHistoryExpanded(false);
}

historyToggle.addEventListener("click", () => {
  setHistoryExpanded(historyToggle.getAttribute("aria-expanded") !== "true");
});

async function refreshProjects(preferredId) {
  const response = await fetch("/api/v1/projects");
  if (!response.ok) throw new Error("Projects could not be loaded");
  const payload = await response.json();
  state.projects = new Map(payload.projects.map((project) => [project.id, project]));
  const savedId = preferredId || localStorage.getItem("academic-search-current-project");
  projectSelect.replaceChildren(element("option", "", "No project — temporary search"));
  projectSelect.firstChild.value = "";
  for (const project of payload.projects) {
    const option = element("option", "", project.name);
    option.value = project.id;
    projectSelect.append(option);
  }
  if (savedId && state.projects.has(savedId)) projectSelect.value = savedId;
  exportProjectButton.disabled = !selectedProjectId();
  if (selectedProjectId()) applyProjectDefaults(state.projects.get(selectedProjectId()));
  await refreshHistory();
  await refreshJournalHistory();
}

function renderCoverage(entries, outcomes) {
  coverage.replaceChildren();
  const counts = new Map(
    (outcomes || []).map((outcome) => [String(outcome.provider).toLowerCase(), outcome.returned_count])
  );
  for (const entry of entries || []) {
    const count = counts.get(String(entry.provider).toLowerCase());
    const detail = entry.status === "responded" && count
      ? `${count} found`
      : COVERAGE_LABELS[entry.status] || entry.status;
    const item = element("span", `coverage-item ${entry.status}`);
    item.append(element("strong", "", entry.provider), element("span", "", detail));
    if (entry.error_code && entry.error_code !== entry.status) item.title = entry.error_code;
    coverage.append(item);
  }
  coverage.hidden = !entries?.length;
}

function paperCard(paper) {
  const item = element("li", "paper");
  const content = element("article");
  const source = element(
    "span",
    "source-tag",
    `${paper.category_label} · ${paper.source || "Unknown source"}`
  );
  source.title = `Paper record from ${paper.source || "an unknown source"}. `
    + "The category is derived from keyword rules, not supplied by the provider.";
  const title = element("h3", "", paper.title || "Untitled paper");
  const metaParts = [paper.authors, paper.journal, paper.year, paper.doi ? `DOI ${paper.doi}` : null].filter(Boolean);
  const meta = element("p", "meta", metaParts.join(" · "));

  content.append(source, title);
  if (metaParts.length) content.append(meta);
  const ubyt = ubytBadge(paper.ubyt);
  if (ubyt) content.append(ubyt);
  if (paper.abstract) {
    const abstract = paper.abstract.length > 360
      ? `${paper.abstract.slice(0, 357)}…`
      : paper.abstract;
    content.append(element("p", "abstract", abstract));
  }
  if (paper.alignment) {
    const matched = paper.alignment.matched_terms?.length
      ? ` · ${paper.alignment.matched_terms.join(", ")}`
      : "";
    content.append(element(
      "span", "alignment-score", `Topic alignment ${paper.alignment.score}/100${matched}`
    ));
  }

  const link = element("a", "paper-link", paper.doi ? "Open DOI ↗" : "Open paper ↗");
  link.href = paper.url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.setAttribute("aria-label", `Open ${paper.title || "paper"} in a new tab`);
  item.append(content, link);
  return item;
}

function renderResultsPager(payload) {
  const page = payload.page || 1;
  const hasMore = Boolean(payload.has_more);
  state.resultsPage = page;
  state.resultsHasMore = hasMore;
  resultsPager.hidden = page <= 1 && !hasMore;
  resultsFirstButton.disabled = resultsPrevButton.disabled = page <= 1;
  resultsNextButton.disabled = resultsLastButton.disabled = !hasMore;
  resultsPageInput.value = page;
  resultsPageInput.removeAttribute("max");
  resultsPageLabel.textContent = "";
}

function goToResultsPage(page) {
  const target = Math.max(1, Math.trunc(page) || 1);
  if (target !== state.resultsPage) runSearch(target);
  else resultsPageInput.value = target;
}

resultsFirstButton.addEventListener("click", () => goToResultsPage(1));
resultsPrevButton.addEventListener("click", () => goToResultsPage(state.resultsPage - 1));
resultsNextButton.addEventListener("click", () => goToResultsPage(state.resultsPage + 1));
resultsLastButton.addEventListener("click", () => goToResultsPage(state.resultsPage + 1));
resultsPageInput.addEventListener("change", () => goToResultsPage(Number(resultsPageInput.value)));
resultsPageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    goToResultsPage(Number(resultsPageInput.value));
  }
});

async function runSearch(page = 1) {
  const formData = new FormData(form);
  const params = new URLSearchParams();
  for (const [key, value] of formData.entries()) {
    if (String(value).trim()) params.set(key, value);
  }
  const providers = selectedProviders();
  if (!providers.length) {
    statusText.textContent = "Pick at least one source.";
    return;
  }
  params.set("providers", providers.join(","));
  params.set("page", String(page));
  if (selectedProjectId()) params.set("project_id", selectedProjectId());

  resultsSection.setAttribute("aria-busy", "true");
  submitButton.disabled = true;
  statusText.textContent = `Searching ${providers.length} source${providers.length === 1 ? "" : "s"}…`;
  coverage.hidden = true;
  resultTitle.textContent = "Paper links";
  resultsList.replaceChildren();
  emptyState.hidden = true;
  resultsPager.hidden = true;

  try {
    const response = await fetch(`/api/v1/search?${params.toString()}`);
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Search request failed");
    }

    const category = state.categories.get(payload.category);
    resultTitle.textContent = category ? category.label : "Paper links";
    const answered = payload.sources_responded.length;
    const asked = payload.provider_coverage.length;
    const rangeStart = payload.results.length ? (payload.page - 1) * payload.limit + 1 : 0;
    const rangeEnd = rangeStart ? rangeStart + payload.results.length - 1 : 0;
    statusText.textContent = [
      rangeEnd ? `${rangeStart}–${rangeEnd} linked result${rangeEnd === 1 ? "" : "s"}` : "0 linked results",
      asked > 1 ? `${answered} of ${asked} sources answered` : null,
      payload.search_time ? `${payload.search_time.toFixed(1)} s` : null,
    ].filter(Boolean).join(" · ");
    renderCoverage(payload.provider_coverage, payload.provider_outcomes);

    for (const paper of payload.results) {
      resultsList.append(paperCard(paper));
    }
    if (!payload.results.length) {
      emptyState.hidden = false;
      emptyState.textContent = page > 1
        ? "No more results on this page. Go back to the previous page."
        : "No linked papers matched this query and category. Try All fields, another source, or a broader query.";
    }
    renderResultsPager(payload);
    if (payload.project_id) await refreshProjects(payload.project_id);
  } catch (error) {
    statusText.textContent = "Search unavailable";
    emptyState.hidden = false;
    emptyState.textContent = error.message;
  } finally {
    submitButton.disabled = false;
    resultsSection.setAttribute("aria-busy", "false");
  }
}

function journalMeta(journal) {
  const provider = state.journalProviders.get(journal.catalog_provider)?.label;
  return [provider, journal.publisher, journal.issn_l ? `ISSN-L ${journal.issn_l}` : null]
    .filter(Boolean)
    .join(" · ");
}

function identifierChips(journal) {
  const wrapper = element("span", "journal-identifiers");
  const identifiers = journal.identifiers || {};
  const values = [
    identifiers.openalex ? [`OpenAlex ${identifiers.openalex}`, "OpenAlex Source ID — paper search runs against this source"] : null,
    identifiers.web_of_science ? [`WoS ${identifiers.web_of_science}`, "Web of Science Journals API identifier"] : null,
    identifiers.scopus ? [`Scopus ${identifiers.scopus}`, "Scopus Serial Title identifier"] : null,
    journal.issn_l ? [`ISSN-L ${journal.issn_l}`, `Linking ISSN as supplied by ${journal.source || "the catalog"}`] : null,
  ].filter(Boolean);
  for (const [value, tooltip] of values) {
    const chip = element("span", "journal-identifier", value);
    chip.title = tooltip;
    wrapper.append(chip);
  }
  return wrapper;
}

function journalOriginText(journal) {
  const provider = state.journalProviders.get(journal.catalog_provider)?.label || journal.catalog_provider || "catalog";
  const records = journal.provider_records || [];
  if (records.length > 1) {
    return records.map((record) => {
      const label = state.journalProviders.get(record.provider)?.label || record.provider;
      return `${label}: ${record.id}`;
    }).join(" → ") + `\nSelected from ${provider}; linked by ISSN. Paper search uses OpenAlex.`;
  }
  return `Journal record from ${journal.source || provider}.`;
}

function selectJournal(journal) {
  state.selectedJournal = journal;
  journalNameInput.value = journal.display_name;
  const change = element("button", "link-button", "Change journal");
  change.type = "button";
  change.addEventListener("click", () => {
    state.selectedJournal = null;
    selectedJournalBox.hidden = true;
    journalCatalogCard.hidden = false;
    journalNameInput.focus();
  });
  const details = element("div", "selected-details");
  details.append(
    element("strong", "", journal.display_name),
    element("span", "", journalMeta(journal) || `OpenAlex ${journal.id}`),
    identifierChips(journal),
    ubytBadge(journal.ubyt, { showMissing: true }),
  );
  selectedJournalBox.replaceChildren(details, change);
  selectedJournalBox.title = journalOriginText(journal);
  selectedJournalBox.hidden = false;
  journalCatalogCard.hidden = true;
  const supported = journal.search_supported !== false;
  journalForm.querySelector("button[type='submit']").disabled = !supported;
  journalStatus.textContent = supported
    ? "Journal resolved by ISSN/source ID. Add topics and search."
    : journal.resolution_note || "Journal metadata resolved, but paper search is unavailable without an OpenAlex ISSN crosswalk.";
}

let suggestionTimer;
let suggestionController;

async function resolveCatalogJournal(journal) {
  journalStatus.textContent = "Resolving journal identifiers and paper-search support…";
  const params = new URLSearchParams({
    provider: journal.catalog_provider || journalProviderSelect.value,
    journal_id: journal.provider_id || journal.id,
  });
  try {
    const response = await fetch(`/api/v1/journal-catalog/resolve?${params}`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Journal identity could not be resolved");
    selectJournal(payload.journal);
  } catch (error) {
    journalStatus.textContent = error.message;
  }
}

function journalIssnText(journal) {
  if (journal.ubyt) {
    return [journal.ubyt.issn ? `ISSN ${journal.ubyt.issn}` : null, journal.ubyt.eissn ? `eISSN ${journal.ubyt.eissn}` : null]
      .filter(Boolean).join(" · ");
  }
  return (journal.issns || []).length ? `ISSN ${journal.issns.join(", ")}` : "";
}

function journalTags(journal) {
  const tags = element("span", "jr-tags");
  const labels = journal.ubyt
    ? [...(journal.ubyt.indexes || []), journal.ubyt.source].filter(Boolean)
    : (journal.categories || []).slice(0, 2).map((item) => item.label);
  for (const label of labels) {
    const tag = element("span", "jr-tag", label);
    tag.title = journal.ubyt
      ? `${label} flag as published in the ${journal.ubyt.list} list`
      : `${label} field from ${state.journalProviders.get(journal.catalog_provider)?.label || "the catalog"}`;
    tags.append(tag);
  }
  return tags;
}

function catalogRow(journal, providerLabel) {
  const row = element("button", "journal-row");
  row.type = "button";
  row.setAttribute("role", "option");
  row.title = `From ${providerLabel}. ` + (journal.search_supported === false
    ? "Select to link it to OpenAlex by ISSN for paper search."
    : "Paper search uses this OpenAlex source.");

  const main = element("span", "jr-main");
  main.append(element("span", "jr-name", journal.display_name));
  const meta = [journal.publisher, journalIssnText(journal)].filter(Boolean).join(" · ");
  if (meta) main.append(element("span", "jr-meta", meta));

  const ubyt = journal.ubyt;
  const mep = element("span", "jr-num jr-mep", ubyt?.mep_score != null ? numberFormatter.format(ubyt.mep_score) : "—");
  mep.dataset.label = "MEP";
  const pay = element("span", "jr-num jr-pay", ubyt?.payment_tl != null ? tryFormatter.format(ubyt.payment_tl) : "—");
  pay.dataset.label = "Payment";
  pay.title = ubyt ? ubytSourceText(ubyt) : "Not on the UBYT list (no ISSN or exact title match).";
  if (ubyt?.matched_by === "name") pay.classList.add("title-match");

  row.append(main, journalTags(journal), mep, pay);
  row.addEventListener("click", () => resolveCatalogJournal(journal));
  return row;
}

function renderCatalogJournals(payload) {
  const providerLabel = state.journalProviders.get(payload.provider)?.label || payload.provider;
  journalSuggestions.replaceChildren(...(payload.journals || []).map((journal) => catalogRow(journal, providerLabel)));
  journalSuggestions.parentElement.scrollTop = 0;
  journalCatalogCard.hidden = false;
  renderJournalPager(payload);
  const providerStatus = payload.provider_status?.status;
  const count = payload.journals?.length || 0;
  const first = (payload.page - 1) * payload.limit + 1;
  const range = `${first.toLocaleString()}–${(first + count - 1).toLocaleString()}`;
  journalCatalogStatus.textContent = count
    ? payload.total != null
      ? `${range} of ${payload.total.toLocaleString()} journals · ${providerLabel}`
      : `${range} · ${providerLabel}`
    : `${providerLabel}: ${providerStatus === "empty" ? "no journals matched" : payload.provider_status?.message || providerStatus || "unavailable"}.`;
  journalCatalogStatus.title = state.journalProviders.get(payload.provider)?.access_note || "";
}

function renderJournalPager(payload) {
  const pages = payload.total != null ? Math.max(1, Math.ceil(payload.total / payload.limit)) : null;
  state.catalogPages = pages;
  journalPager.hidden = payload.page <= 1 && !payload.has_more;
  journalFirstButton.disabled = journalPrevButton.disabled = payload.page <= 1;
  journalNextButton.disabled = !payload.has_more;
  journalLastButton.disabled = !payload.has_more || !pages;
  journalPageInput.value = payload.page;
  journalPageInput.max = pages || "";
  journalPageLabel.textContent = pages ? `of ${pages.toLocaleString()}` : "";
}

function goToCatalogPage(page) {
  const last = state.catalogPages || Number.MAX_SAFE_INTEGER;
  const target = Math.min(Math.max(1, Math.trunc(page) || 1), last);
  if (target !== state.catalogPage) loadCatalogJournals(state.catalogQuery, target);
  else journalPageInput.value = target;
}

journalFirstButton.addEventListener("click", () => goToCatalogPage(1));
journalPrevButton.addEventListener("click", () => goToCatalogPage(state.catalogPage - 1));
journalNextButton.addEventListener("click", () => goToCatalogPage(state.catalogPage + 1));
journalLastButton.addEventListener("click", () => goToCatalogPage(state.catalogPages));
journalPageInput.addEventListener("change", () => goToCatalogPage(Number(journalPageInput.value)));
journalPageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    goToCatalogPage(Number(journalPageInput.value));
  }
});
journalSortSelect.addEventListener("change", () => loadCatalogJournals(state.catalogQuery));
journalPageSizeSelect.addEventListener("change", () => loadCatalogJournals(state.catalogQuery));

async function loadCatalogJournals(query = "", page = 1) {
  suggestionController?.abort();
  suggestionController = new AbortController();
  state.catalogQuery = query;
  state.catalogPage = page;
  const params = new URLSearchParams({
    provider: journalProviderSelect.value,
    q: query,
    limit: journalPageSizeSelect.value,
    page: String(page),
  });
  if (journalProviderSelect.value === "ubyt") params.set("sort", journalSortSelect.value);
  if (journalCategorySelect.value) params.set("category_id", journalCategorySelect.value);
  journalCatalogStatus.textContent = "Loading journals…";
  journalCatalogCard.classList.add("loading");
  try {
    const response = await fetch(`/api/v1/journal-catalog/journals?${params}`, {
      signal: suggestionController.signal,
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Journal catalog failed");
    renderCatalogJournals(payload);
  } catch (error) {
    if (error.name !== "AbortError") journalCatalogStatus.textContent = error.message;
  } finally {
    journalCatalogCard.classList.remove("loading");
  }
}

async function loadJournalCategories() {
  journalCategorySelect.replaceChildren(element("option", "", "All categories"));
  journalCategorySelect.firstChild.value = "";
  const params = new URLSearchParams({ provider: journalProviderSelect.value, limit: "100" });
  try {
    const response = await fetch(`/api/v1/journal-catalog/categories?${params}`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Categories could not be loaded");
    for (const category of payload.categories || []) {
      const option = element("option", "", category.label);
      option.value = category.id;
      option.title = category.description || `${category.label} category from ${journalProviderSelect.selectedOptions[0]?.textContent}`;
      journalCategorySelect.append(option);
    }
    await loadCatalogJournals(journalNameInput.value.trim());
  } catch (error) {
    journalCatalogStatus.textContent = error.message;
  }
}

function initializeJournalCatalog(payload) {
  state.journalProviders = new Map((payload.providers || []).map((item) => [item.id, item]));
  journalProviderSelect.replaceChildren();
  for (const provider of payload.providers || []) {
    const option = element(
      "option", "", provider.available ? provider.label : `${provider.label} · API access required`
    );
    option.value = provider.id;
    option.title = provider.access_note || provider.label;
    option.disabled = !provider.available;
    journalProviderSelect.append(option);
  }
  // The bundled UBYT list is the default journal catalog: it needs no API entitlement.
  journalProviderSelect.value = state.journalProviders.get("ubyt")?.available ? "ubyt" : "openalex";
  journalProviderSelect.title = state.journalProviders.get(journalProviderSelect.value)?.access_note || "";
  syncSortField();
  loadJournalCategories();
}

function syncSortField() {
  journalSortField.hidden = journalProviderSelect.value !== "ubyt";
}

journalProviderSelect.addEventListener("change", () => {
  syncSortField();
  journalProviderSelect.title = state.journalProviders.get(journalProviderSelect.value)?.access_note || "";
  state.selectedJournal = null;
  selectedJournalBox.hidden = true;
  journalNameInput.value = "";
  loadJournalCategories();
});

journalCategorySelect.addEventListener("change", () => {
  state.selectedJournal = null;
  selectedJournalBox.hidden = true;
  loadCatalogJournals(journalNameInput.value.trim());
});

journalNameInput.addEventListener("input", () => {
  state.selectedJournal = null;
  state.journalSnapshot = null;
  selectedJournalBox.hidden = true;
  refreshJournalButton.disabled = true;
  clearTimeout(suggestionTimer);
  const query = journalNameInput.value.trim();
  if (query.length === 1) {
    return;
  }
  suggestionTimer = setTimeout(() => loadCatalogJournals(query), 250);
});

function splitCommaValues(value) {
  return [...new Set(value.split(",").map((item) => item.trim()).filter(Boolean))];
}

function profileCard(title, text) {
  const card = element("div", "profile-card");
  card.append(element("strong", "", title), element("p", "", text));
  return card;
}

function ubytProfileCard(ubyt) {
  const card = profileCard("UBYT payment", ubyt ? ubytText(ubyt) : "Not on the UBYT list");
  card.title = ubyt ? ubytSourceText(ubyt) : "No ISSN or exact title match in the bundled UBYT list.";
  return card;
}

function renderJournalSnapshot(snapshot) {
  state.journalSnapshot = snapshot;
  state.selectedJournal = snapshot.journal;
  journalResults.hidden = false;
  manuscriptPanel.hidden = !snapshot.id;
  refreshJournalButton.disabled = !snapshot.project_id;
  journalResultTitle.textContent = snapshot.journal.display_name;
  const retrieved = new Date(snapshot.retrieved_at).toLocaleString();
  const sourceState = snapshot.cache_status === "saved"
    ? "Loaded saved evidence"
    : snapshot.cache_status === "refreshed" ? "Refreshed from OpenAlex" : "Saved new evidence";
  journalSnapshotStatus.textContent = `${sourceState} · retrieved ${retrieved}`;
  journalRefreshBadge.textContent = snapshot.refresh_recommended ? "Refresh recommended" : "Snapshot current";

  const topics = (snapshot.profile.top_topics || []).slice(0, 8)
    .map((item) => item.term).join(", ") || "Not enough keyword metadata";
  const years = (snapshot.profile.publications_by_year || [])
    .map((item) => `${item.year}: ${item.count}`).join(" · ") || "No year metadata";
  journalProfile.replaceChildren(
    profileCard("Saved sample", `${snapshot.papers.length} linked papers`),
    profileCard("Frequent topics", topics),
    profileCard("Papers by year", years),
    ubytProfileCard(snapshot.journal.ubyt),
  );
  journalPapers.replaceChildren();
  for (const paper of snapshot.papers) journalPapers.append(paperCard(paper));
  if (!snapshot.papers.length) {
    journalPapers.append(profileCard(
      "No matching papers",
      "The provider responded but returned no linked papers for this journal, topic, and year range.",
    ));
  }
  fitReport.hidden = true;
}

async function runJournalSearch(refresh = false) {
  const projectId = selectedProjectId();
  if (!projectId) {
    journalStatus.textContent = "Create or select a research project first so this evidence can be saved.";
    newProjectButton.focus();
    return;
  }
  if (!state.selectedJournal) {
    journalStatus.textContent = "Choose a verified journal from the suggestions first.";
    journalNameInput.focus();
    return;
  }
  const topics = splitCommaValues(journalTopicsInput.value);
  if (!topics.length) {
    journalStatus.textContent = "Enter at least one topic.";
    journalTopicsInput.focus();
    return;
  }
  const submit = journalForm.querySelector("button[type='submit']");
  submit.disabled = true;
  refreshJournalButton.disabled = true;
  journalStatus.textContent = refresh ? "Refreshing from OpenAlex…" : "Checking saved evidence…";
  try {
    const response = await fetch("/api/v1/journals/search", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        project_id: projectId,
        journal: state.selectedJournal,
        topics,
        year_min: document.querySelector("#journal-year-min").value || null,
        year_max: document.querySelector("#journal-year-max").value || null,
        limit: 20,
        refresh,
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Journal search failed");
    renderJournalSnapshot(payload);
    journalStatus.textContent = payload.cache_status === "saved"
      ? "Loaded without contacting the provider. Use Refresh when you want newer results."
      : "Journal evidence saved to this project.";
    await refreshJournalHistory();
  } catch (error) {
    journalStatus.textContent = error.message;
  } finally {
    submit.disabled = false;
    refreshJournalButton.disabled = !state.journalSnapshot?.project_id;
  }
}

journalForm.addEventListener("submit", (event) => {
  event.preventDefault();
  runJournalSearch(false);
});
refreshJournalButton.addEventListener("click", () => runJournalSearch(true));

function loadJournalHistory(search) {
  selectJournal(search.journal);
  journalTopicsInput.value = search.topics.join(", ");
  document.querySelector("#journal-year-min").value = search.year_min || "";
  document.querySelector("#journal-year-max").value = search.year_max || "";
  runJournalSearch(false);
}

async function refreshJournalHistory() {
  const projectId = selectedProjectId();
  journalHistory.replaceChildren();
  journalHistoryPanel.hidden = !projectId;
  if (!projectId) {
    journalStatus.textContent = "Select a research project to save journal evidence.";
    return;
  }
  const response = await fetch(`/api/v1/projects/${projectId}/journal-searches`);
  if (!response.ok) return;
  const payload = await response.json();
  for (const search of payload.searches || []) {
    const item = element("li", "history-item");
    item.append(
      element("strong", "", search.journal.display_name),
      element("span", "", `${search.topics.join(", ")} · ${search.paper_count} papers · ${new Date(search.retrieved_at).toLocaleString()}`),
    );
    const load = element("button", "secondary", "Load saved snapshot");
    load.type = "button";
    load.addEventListener("click", () => loadJournalHistory(search));
    item.append(load);
    journalHistory.append(item);
  }
  journalHistoryPanel.hidden = !payload.searches?.length;
}

manuscriptForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.journalSnapshot?.id || !selectedProjectId()) return;
  const button = manuscriptForm.querySelector("button[type='submit']");
  button.disabled = true;
  try {
    const response = await fetch(
      `/api/v1/journal-searches/${state.journalSnapshot.id}/fit`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          project_id: selectedProjectId(),
          title: document.querySelector("#manuscript-title").value,
          abstract: document.querySelector("#manuscript-abstract").value,
          keywords: splitCommaValues(document.querySelector("#manuscript-keywords").value),
        }),
      },
    );
    const report = await response.json();
    if (!response.ok) throw new Error(report.detail || "Fit analysis failed");
    fitReport.replaceChildren(
      element("p", "fit-score", `${report.overall_score}/100`),
      element("strong", "", report.summary),
      element("p", "", `Matched terms: ${report.matched_terms.join(", ") || "none in this sample"}`),
      element("p", "", `Potential vocabulary gaps: ${report.potential_gaps.join(", ") || "none identified"}`),
      element("p", "", report.disclaimer),
    );
    const heading = element("h4", "", "Closest papers in the saved snapshot");
    const list = element("ul");
    for (const paper of report.closest_papers) {
      const item = element("li");
      const link = element("a", "paper-link", `${paper.title} — ${paper.score}/100`);
      link.href = paper.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      item.append(link);
      list.append(item);
    }
    fitReport.append(heading, list);
    fitReport.hidden = false;
  } catch (error) {
    fitReport.replaceChildren(element("p", "", error.message));
    fitReport.hidden = false;
  } finally {
    button.disabled = false;
  }
});

selectAllSourcesButton.addEventListener("click", () => {
  const enabled = sourceCheckboxes().filter((checkbox) => !checkbox.disabled);
  const selectAll = !enabled.every((checkbox) => checkbox.checked);
  for (const checkbox of enabled) checkbox.checked = selectAll || checkbox.value === "openalex";
  updateSelectAllLabel();
});

providerOptions.addEventListener("change", (event) => {
  if (!selectedProviders().length) event.target.checked = true;
  updateSelectAllLabel();
});

form.addEventListener("submit", (event) => {
  event.preventDefault();
  runSearch();
});

projectSelect.addEventListener("change", async () => {
  const projectId = selectedProjectId();
  state.journalSnapshot = null;
  journalResults.hidden = true;
  manuscriptPanel.hidden = true;
  fitReport.hidden = true;
  refreshJournalButton.disabled = true;
  if (projectId) {
    localStorage.setItem("academic-search-current-project", projectId);
    applyProjectDefaults(state.projects.get(projectId));
  } else {
    localStorage.removeItem("academic-search-current-project");
  }
  exportProjectButton.disabled = !projectId;
  await refreshHistory();
  await refreshJournalHistory();
});

newProjectButton.addEventListener("click", () => projectDialog.showModal());
cancelProjectButton.addEventListener("click", () => projectDialog.close());
projectForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (createProjectButton.disabled) return;
  createProjectButton.disabled = true;
  projectError.hidden = true;
  const formData = new FormData(projectForm);
  try {
    const response = await fetch("/api/v1/projects", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        name: formData.get("name"),
        research_question: formData.get("research_question"),
        default_category: categorySelect.value,
        default_providers: selectedProviders().join(","),
        default_year_min: document.querySelector("#year-min").value || null,
        default_year_max: document.querySelector("#year-max").value || null,
      }),
    });
    const payload = await response.json();
    if (!response.ok) {
      projectError.textContent = typeof payload.detail === "string"
        ? payload.detail
        : "Project could not be created";
      projectError.hidden = false;
      return;
    }
    projectForm.reset();
    projectDialog.close();
    localStorage.setItem("academic-search-current-project", payload.id);
    await refreshProjects(payload.id);
  } catch {
    projectError.textContent = "Project could not be created";
    projectError.hidden = false;
  } finally {
    createProjectButton.disabled = false;
  }
});

exportProjectButton.addEventListener("click", () => {
  if (selectedProjectId()) window.location.href = `/api/v1/projects/${selectedProjectId()}/evidence?format=markdown`;
});

renderSourceOptions();

Promise.all([
  fetch("/api/v1/categories").then((response) => response.json()),
  fetch("/api/v1/health").then((response) => response.json()),
  fetch("/api/v1/journal-catalog/providers").then((response) => response.json()),
])
  .then(async ([categories, health, journalCatalog]) => {
    populateCategories(categories);
    applyProviderAvailability(health);
    initializeJournalCatalog(journalCatalog);
    await refreshProjects();
  })
  .catch(() => {
    statusText.textContent = "Categories could not be loaded.";
  });

queryInput.focus();

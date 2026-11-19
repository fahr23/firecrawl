const form = document.querySelector("#search-form");
const queryInput = document.querySelector("#query");
const categorySelect = document.querySelector("#category");
const providerOptions = document.querySelector("#providers");
const selectAllSourcesButton = document.querySelector("#select-all-sources");
const unavailableSources = document.querySelector("#sources-unavailable");
const unavailableSourceList = document.querySelector("#unavailable-source-list");
const unavailableSourceSummary = document.querySelector("#unavailable-source-summary");
const sourceCount = document.querySelector("#source-count");
const onlineSources = document.querySelector("#online-sources");
const libraryCount = document.querySelector("#library-count");
const watchSearchButton = document.querySelector("#watch-search");
const watchSearchStatus = document.querySelector("#watch-search-status");
const inboxCount = document.querySelector("#inbox-count");
const statusText = document.querySelector("#status");
const resultTitle = document.querySelector("#result-title");
const resultsList = document.querySelector("#results");
const emptyState = document.querySelector("#empty-state");
const resultsSection = document.querySelector(".results-section");
const submitButton = form.querySelector("button[type='submit']");
const topicList = document.querySelector("#topic-list");
const topicFilter = document.querySelector("#topic-filter");
const topicMessage = document.querySelector("#topic-message");
const topicToggle = document.querySelector("#topic-toggle");
const topicMenu = document.querySelector("#topic-menu");
const temporaryTopic = document.querySelector("#temporary-topic");
const retryTopicsButton = document.querySelector("#retry-topics");
const workspaceTitle = document.querySelector("#workspace-title");
const workspaceLabel = document.querySelector("#workspace-label");
const workspaceQuestion = document.querySelector("#workspace-question");
const workspaceActions = document.querySelector("#workspace-actions");
const workspaceTabs = [...document.querySelectorAll(".workspace-tabs [role='tab']")];
const compactWorkspace = window.matchMedia("(max-width: 960px)");
const savedTopicKey = "academic-search-current-project";
const newProjectButton = document.querySelector("#new-project");
const editProjectButton = document.querySelector("#edit-project");
const exportProjectButton = document.querySelector("#export-project");
const projectDialog = document.querySelector("#project-dialog");
const projectForm = document.querySelector("#project-form");
const cancelProjectButton = document.querySelector("#cancel-project");
const createProjectButton = projectForm.querySelector("button[type='submit']");
const projectError = document.querySelector("#project-error");
const projectDialogTitle = document.querySelector("#project-dialog-title");
const historyPanel = document.querySelector("#history-panel");
const historyToggle = document.querySelector("#history-toggle");
const historyCount = document.querySelector("#history-count");
const searchHistory = document.querySelector("#search-history");
const coverage = document.querySelector("#coverage");
const journalForm = document.querySelector("#journal-form");
const journalSubmitButton = journalForm.querySelector("button[type='submit']");
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
const manuscriptSubmitButton = manuscriptForm.querySelector("button[type='submit']");
const manuscriptTitle = document.querySelector("#manuscript-title");
const manuscriptAbstract = document.querySelector("#manuscript-abstract");
const manuscriptKeywords = document.querySelector("#manuscript-keywords");
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
const resultsPageInput = document.querySelector("#results-page-input");
const resultsPageLabel = document.querySelector("#results-page-label");

const state = {
  catalogQuery: "",
  catalogPage: 1,
  catalogPages: null,
  categories: new Map(),
  projects: new Map(),
  unreadByTopic: new Map(),
  projectId: null,
  manuscriptDrafts: new Map(),
  requests: new Map(),
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

function jsonOptions(data, method = "POST", signal) {
  return { method, signal, headers: { "content-type": "application/json" }, body: JSON.stringify(data) };
}

const paperActivityQueue = [];
let paperActivityScheduled = false;

function paperRef(paper) {
  return { url: paper.url, doi: paper.doi || null };
}

function paperKey(paper) {
  return paper.doi?.trim().toLowerCase().replace(/^(?:https?:\/\/(?:dx\.)?doi\.org\/|doi:\s*)/, "") || paper.url;
}

function updatePaperActivity(control, activity) {
  if (!activity) return;
  if (control.updatedAt && (!activity.updated_at || activity.updated_at < control.updatedAt)) return;
  control.updatedAt = activity.updated_at;
  control.libraryId = activity.library_id;
  control.read = Boolean(activity.read_at);
  control.dataset.read = String(control.read);
  const label = control.querySelector("span");
  label.textContent = [
    control.read ? "Read" : null,
    activity.open_count ? `Opened ${activity.open_count}×` : "Unopened",
  ].filter(Boolean).join(" · ");
  label.title = activity.last_opened_at ? `Last opened ${new Date(activity.last_opened_at).toLocaleString()}` : "";
  control.querySelector("button").textContent = control.read ? "Mark unread" : "Mark read";
  control.hidden = false;
}

function handlePaperActivity(paper, activity) {
  const key = paperKey(paper);
  for (const control of document.querySelectorAll(".paper-activity")) {
    if (control.libraryId === activity.library_id || control.paperKey === key) {
      control.changed = true;
      updatePaperActivity(control, activity);
    }
  }
  void refreshWatchCounts();
  document.dispatchEvent(new CustomEvent("academic-paper-activity", { detail: activity }));
}

async function loadPaperActivity() {
  paperActivityScheduled = false;
  const pending = paperActivityQueue.splice(0);
  for (let i = 0; i < pending.length; i += 100) {
    const batch = pending.slice(i, i + 100).filter(({ control }) => control.isConnected);
    if (!batch.length) continue;
    try {
      const { items } = await requestJson("/api/v1/library/activity/lookup",
        jsonOptions({ papers: batch.map(({ paper }) => paperRef(paper)) }), "Reading activity unavailable.");
      batch.forEach(({ control }, index) => {
        if (!control.changed) updatePaperActivity(control, items[index]);
      });
    } catch {
      // Paper links remain usable when the activity service is unavailable.
    }
  }
}

function trackPaperLink(link, paper, control) {
  const record = (event) => {
    if (event.defaultPrevented || (event.type === "auxclick" && event.button !== 1)) return;
    const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
    const eventId = [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16), hex.slice(16, 20), hex.slice(20)].join("-");
    const opts = jsonOptions({ ...paperRef(paper), event_id: eventId });
    requestJson("/api/v1/library/activity/open", { ...opts, keepalive: true }, "Open could not be recorded.")
      .then((activity) => handlePaperActivity(paper, activity))
      .catch(() => {
        if (control?.isConnected && !control.hidden) control.querySelector("span").textContent = "Open could not be recorded";
      });
  };
  link.addEventListener("click", record);
  link.addEventListener("auxclick", record);
}

function paperActivityControls(paper, link) {
  const control = element("div", "paper-activity");
  control.paperKey = paperKey(paper);
  control.hidden = true;
  const label = element("span");
  label.setAttribute("aria-live", "polite");
  const action = element("button", "link-button", "Mark read");
  action.type = "button";
  action.addEventListener("click", async () => {
    action.disabled = true;
    try {
      const status = await requestJson("/api/v1/library/activity/read",
        jsonOptions({ ...paperRef(paper), read: !control.read }), "Reading status could not be saved.");
      handlePaperActivity(paper, status);
    } catch (error) {
      label.textContent = error.message;
    } finally {
      action.disabled = false;
    }
  });
  control.append(label, action);
  trackPaperLink(link, paper, control);
  paperActivityQueue.push({ paper, control });
  if (!paperActivityScheduled) {
    paperActivityScheduled = true;
    queueMicrotask(loadPaperActivity);
  }
  return control;
}

function startRequest(key) {
  state.requests.get(key)?.abort();
  const controller = new AbortController();
  state.requests.set(key, controller);
  return controller.signal;
}

async function requestJson(url, options, fallback) {
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : fallback);
  return payload;
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
  if (!selectedProviders().length) {
    const enabled = sourceCheckboxes().find((checkbox) => !checkbox.disabled);
    if (enabled) enabled.checked = true;
  }
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
  unavailableSources.textContent = missing.join(" · ");
  unavailableSourceSummary.textContent = `${missing.length} ${missing.length === 1 ? "source needs" : "sources need"} setup`;
  unavailableSourceList.hidden = !missing.length;
  if (!selectedProviders().length) setSelectedProviders("openalex");
  updateSelectAllLabel();
}

function updateSelectAllLabel() {
  const enabled = sourceCheckboxes().filter((checkbox) => !checkbox.disabled);
  const allSelected = enabled.every((checkbox) => checkbox.checked);
  selectAllSourcesButton.disabled = !enabled.length;
  selectAllSourcesButton.textContent = allSelected ? "Reset to OpenAlex" : "Select all";
  sourceCount.textContent = `${selectedProviders().length} of ${enabled.length} selected`;
}

function selectedProjectId() {
  return state.projectId;
}

function applySearchSettings(query, category, providers, yearMin, yearMax, limit = 20) {
  queryInput.value = query || "";
  form.elements.mode.value = "online";
  updatePaperScope();
  categorySelect.value = state.categories.has(category) ? category : "all";
  setSelectedProviders(providers);
  form.elements.year_min.value = yearMin ?? "";
  form.elements.year_max.value = yearMax ?? "";
  const limitSelect = form.elements.limit;
  limitSelect.querySelector("[data-saved-limit]")?.remove();
  if (![...limitSelect.options].some((option) => option.value === String(limit))) {
    const option = element("option", "", String(limit));
    option.dataset.savedLimit = "";
    limitSelect.append(option);
  }
  limitSelect.value = String(limit);
}

function setTopicMenu(expanded) {
  topicToggle.setAttribute("aria-expanded", String(expanded));
  topicMenu.hidden = !expanded;
}

function selectView(selected, focus = false) {
  for (const tab of workspaceTabs) {
    const active = tab === selected;
    tab.setAttribute("aria-selected", String(active));
    tab.tabIndex = active ? 0 : -1;
    document.getElementById(tab.getAttribute("aria-controls")).hidden = !active;
  }
  if (focus) selected.focus();
  document.dispatchEvent(new Event("academic-workspace-change"));
}

for (const [index, tab] of workspaceTabs.entries()) {
  tab.addEventListener("click", () => selectView(tab));
  tab.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const last = workspaceTabs.length - 1;
    const direction = event.key === "ArrowLeft" ? -1 : 1;
    const next = event.key === "Home" ? 0 : event.key === "End" ? last
      : (index + direction + workspaceTabs.length) % workspaceTabs.length;
    selectView(workspaceTabs[next], true);
  });
}

function renderActiveTopic() {
  const project = state.projects.get(selectedProjectId());
  workspaceLabel.textContent = project ? "Research topic" : "Temporary workspace";
  workspaceTitle.textContent = project?.name || "Search the literature";
  workspaceQuestion.textContent = project
    ? project.research_question || ""
    : "Create a topic to keep your searches and journal evidence together.";
  workspaceQuestion.hidden = !workspaceQuestion.textContent;
  workspaceActions.hidden = !project;
  for (const button of topicList.querySelectorAll("button")) {
    button.setAttribute("aria-current", String(button.dataset.projectId === project?.id));
  }
  temporaryTopic.setAttribute("aria-current", String(!project));
}

function renderTopics() {
  const query = topicFilter.value.trim().toLocaleLowerCase();
  const visible = [...state.projects.values()].filter((project) =>
    `${project.name} ${project.research_question || ""}`.toLocaleLowerCase().includes(query)
  );
  topicList.replaceChildren(...visible.map((project) => {
    const item = element("li");
    const button = element("button", "topic-button", project.name);
    button.type = "button";
    button.dataset.projectId = project.id;
    const unread = state.unreadByTopic.get(project.id);
    if (unread) {
      const count = element("span", "unread-badge", String(unread));
      count.setAttribute("aria-label", `${unread} new papers`);
      button.append(count);
    }
    button.addEventListener("click", () => chooseTopic(project.id));
    item.append(button);
    return item;
  }));
  topicMessage.textContent = visible.length ? "" : query ? "No topics match your filter." : "Create your first research topic.";
  topicMessage.hidden = Boolean(visible.length);
  renderActiveTopic();
}

async function refreshWatchCounts() {
  try {
    const { unread_by_topic: counts } = await requestJson("/api/v1/watches", { cache: "no-store" }, "Inbox count unavailable.");
    state.unreadByTopic = new Map(Object.entries(counts));
    const total = [...state.unreadByTopic.values()].reduce((sum, count) => sum + count, 0);
    inboxCount.hidden = !total;
    inboxCount.textContent = String(total);
    inboxCount.setAttribute("aria-label", `${total} new papers`);
    for (const item of topicList.querySelectorAll(".topic-button")) {
      const count = state.unreadByTopic.get(item.dataset.projectId);
      item.querySelector(".unread-badge")?.remove();
      if (count) {
        const badge = element("span", "unread-badge", String(count));
        badge.setAttribute("aria-label", `${count} new papers`);
        item.append(badge);
      }
    }
  } catch {
    // A temporary failure leaves the last known counts visible.
  }
}

function chooseTopic(projectId) {
  switchTopic(projectId);
  if (compactWorkspace.matches) {
    setTopicMenu(false);
    workspaceTitle.focus();
  }
}

async function loadProjects() {
  retryTopicsButton.hidden = true;
  topicMessage.hidden = false;
  topicMessage.textContent = "Loading topics…";
  try {
    const { projects } = await requestJson("/api/v1/projects", {}, "Topics could not be loaded.");
    state.projects = new Map(projects.map((project) => [project.id, project]));
    renderTopics();
    const savedId = localStorage.getItem(savedTopicKey);
    const projectId = savedId === null ? projects[0]?.id : savedId;
    switchTopic(state.projects.has(projectId) ? projectId : null);
  } catch {
    topicMessage.textContent = "Topics could not be loaded.";
    retryTopicsButton.hidden = false;
  }
}

function switchTopic(projectId) {
  if (projectId === selectedProjectId()) return;
  for (const controller of state.requests.values()) controller.abort();
  state.requests.clear();
  state.projectId = projectId;
  state.paperSearch = null;
  state.paperFormEdited = false;
  state.journalFormEdited = false;
  localStorage.setItem(savedTopicKey, projectId || "");
  renderActiveTopic();

  const project = state.projects.get(projectId);
  applySearchSettings("", project?.default_category, project?.default_providers,
    project?.default_year_min, project?.default_year_max);
  setPaperLoading(project ? "Loading saved papers…" : "Enter a query to begin.", false);
  emptyState.hidden = Boolean(project);
  emptyState.textContent = "Enter a query to see papers and source links.";
  resetJournalWorkspace();

  setHistoryExpanded(false);
  searchHistory.replaceChildren();
  historyPanel.hidden = true;
  if (project) {
    void refreshHistory(true);
    void refreshJournalHistory(true);
  }
  document.dispatchEvent(new Event("academic-workspace-change"));
}

function historyItem(search) {
  const item = element("li", "history-item");
  const title = element("strong", "", search.query);
  const category = state.categories.get(search.category)?.label || "All fields";
  const detail = element(
    "span", "",
    `${search.returned_count} linked ${search.returned_count === 1 ? "paper" : "papers"} · ${category} · ${new Date(search.retrieved_at).toLocaleString()}`
  );
  const open = element("button", "secondary", "Open saved results");
  open.type = "button";
  open.addEventListener("click", () => loadSavedSearch(search.id));
  item.append(title, detail, open);
  return item;
}

function setHistoryExpanded(expanded) {
  historyToggle.setAttribute("aria-expanded", String(expanded));
  searchHistory.hidden = !expanded;
}

async function refreshHistory(restore = false) {
  const projectId = selectedProjectId();
  if (!projectId) return;
  const signal = startRequest("paper-history");
  try {
    const { searches } = await requestJson(
      `/api/v1/projects/${projectId}/searches?limit=50`, { signal }, "Saved searches could not be loaded."
    );
    if (signal.aborted) return;
    searchHistory.replaceChildren(...searches.map(historyItem));
    historyPanel.hidden = !searches.length;
    historyCount.textContent = String(searches.length);
    if (restore && !state.requests.has("papers")) {
      if (searches.length) await loadSavedSearch(searches[0].id, true);
      else showPaperMessage("No saved searches", "Search for papers to start building this topic’s evidence.");
    }
  } catch (error) {
    if (!signal.aborted && restore && !state.requests.has("papers")) {
      showPaperMessage("Saved searches unavailable", error.message);
    }
  }
}

historyToggle.addEventListener("click", () => {
  setHistoryExpanded(historyToggle.getAttribute("aria-expanded") !== "true");
});

topicFilter.addEventListener("input", renderTopics);
temporaryTopic.addEventListener("click", () => chooseTopic(null));
retryTopicsButton.addEventListener("click", loadProjects);
topicToggle.addEventListener("click", () => setTopicMenu(topicMenu.hidden));
compactWorkspace.addEventListener("change", () => setTopicMenu(!compactWorkspace.matches));
setTopicMenu(!compactWorkspace.matches);

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

function paperCard(paper, origin) {
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
  const metaParts = [paper.authors, paper.journal, paper.publication_date || paper.year, paper.doi ? `DOI ${paper.doi}` : null].filter(Boolean);
  const meta = element("p", "meta", metaParts.join(" · "));

  content.append(source, title);
  if (metaParts.length) content.append(meta);
  if (paper.retrieval_kind === "saved") {
    const date = paper.library_observed_at && new Date(paper.library_observed_at).toLocaleDateString();
    content.append(element("span", "library-paper-tag", date ? `Saved copy · ${date}` : "Saved copy"));
  }
  const ubyt = ubytBadge(paper.ubyt);
  if (ubyt) content.append(ubyt);
  if (paper.abstract) {
    const abstract = paper.abstract.length > 360
      ? `${paper.abstract.slice(0, 357)}…`
      : paper.abstract;
    content.append(element("p", "abstract", abstract));
  } else if (paper.search_snippet) {
    content.append(element("p", "abstract", `Search snippet · ${paper.search_snippet}`));
  }
  if (paper.alignment) {
    const matched = paper.alignment.matched_terms?.length
      ? ` · ${paper.alignment.matched_terms.join(", ")}`
      : "";
    content.append(element(
      "span", "alignment-score", `Topic alignment ${paper.alignment.score}/100${matched}`
    ));
  }

  const label = /^https?:\/\/(?:dx\.)?doi\.org\//i.test(paper.url) ? "Open DOI ↗" : "Open paper ↗";
  const link = element("a", "paper-link", label);
  link.href = paper.url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.setAttribute("aria-label", `Open ${paper.title || "paper"} in a new tab`);
  const actions = element("div", "paper-actions");
  actions.append(link);
  const doi = paperKey(paper);
  if (paper.doi && /^10\.\d{4,9}\/\S+$/.test(doi) && !/^https?:\/\/(?:dx\.)?doi\.org\//i.test(paper.url)) {
    const alternate = element("a", "paper-link", "DOI ↗");
    alternate.href = `https://doi.org/${doi.split("/").map(encodeURIComponent).join("/")}`;
    alternate.target = "_blank";
    alternate.rel = "noopener noreferrer";
    alternate.setAttribute("aria-label", `Open DOI for ${paper.title || "paper"}`);
    trackPaperLink(alternate, { ...paper, url: alternate.href });
    actions.append(alternate);
  }
  content.append(paperActivityControls(paper, link));
  if (origin && typeof window.shortlistWorkspacePaper === "function") {
    const button = element("button", "secondary save-paper", "Save to shortlist");
    button.type = "button";
    button.addEventListener("click", () => window.shortlistWorkspacePaper(origin, paper, button));
    actions.append(button);
    if (typeof window.startWorkspaceBrief === "function") {
      const develop = element("button", "link-button", "Start research brief");
      develop.type = "button";
      develop.addEventListener("click", () => window.startWorkspaceBrief(origin, paper, develop));
      actions.append(develop);
    }
  }
  item.append(content, actions);
  return item;
}

function renderResultsPager(payload) {
  const page = payload.page || 1;
  const hasMore = Boolean(payload.has_more);
  state.resultsPage = page;
  state.resultsHasMore = hasMore;
  state.resultsMaxPage = payload.pagination?.max_page || 10;
  resultsPager.hidden = page <= 1 && !hasMore;
  resultsFirstButton.disabled = resultsPrevButton.disabled = page <= 1;
  resultsNextButton.disabled = !hasMore;
  resultsPageInput.value = page;
  resultsPageInput.max = hasMore ? state.resultsMaxPage : page;
  resultsPageLabel.textContent = "";
}

function goToResultsPage(page) {
  if (!state.paperSearch) return;
  const max = state.resultsHasMore ? state.resultsMaxPage : state.resultsPage;
  const target = Math.min(max, Math.max(1, Math.trunc(page) || 1));
  if (target !== state.resultsPage) runSearch(target, state.paperSearch);
  else resultsPageInput.value = target;
}

resultsFirstButton.addEventListener("click", () => goToResultsPage(1));
resultsPrevButton.addEventListener("click", () => goToResultsPage(state.resultsPage - 1));
resultsNextButton.addEventListener("click", () => goToResultsPage(state.resultsPage + 1));
resultsPageInput.addEventListener("change", () => goToResultsPage(Number(resultsPageInput.value)));
resultsPageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    goToResultsPage(Number(resultsPageInput.value));
  }
});

function setPaperLoading(message, busy = true) {
  resultsSection.setAttribute("aria-busy", String(busy));
  submitButton.disabled = busy;
  statusText.textContent = message;
  resultTitle.textContent = "Papers";
  coverage.hidden = true;
  resultsList.replaceChildren();
  emptyState.hidden = true;
  renderResultsPager({});
}

function showPaperMessage(status, message) {
  statusText.textContent = status;
  emptyState.hidden = false;
  emptyState.textContent = message;
}

function showPaperResults(payload, saved = false, preview = false) {
  const page = payload.page || 1;
  const rangeStart = payload.results.length ? (page - 1) * payload.limit + 1 : 0;
  const rangeEnd = rangeStart ? rangeStart + payload.results.length - 1 : 0;
  const count = payload.results.length;
  const paperCount = !count || saved ? String(count) : `${rangeStart}–${rangeEnd}`;
  const delivery = payload.cache || payload.manifest?.delivery;
  const label = preview ? "Saved results · checking live sources…"
    : delivery?.kind === "local" ? "Saved library"
    : delivery?.kind === "mixed" ? "Live + saved results"
    : delivery?.kind === "fallback" ? "Saved results · live sources unavailable"
    : delivery?.kind === "live" && !payload.pagination?.partial ? "Live results"
    : null;
  resultTitle.textContent = payload.query || "Papers";
  statusText.textContent = [
    saved ? `Saved ${new Date(payload.retrieved_at).toLocaleString()}` : null,
    label,
    `${paperCount} linked ${count === 1 ? "paper" : "papers"}`,
    payload.provider_coverage.length > 1 ? `${payload.sources_responded.length} sources returned results` : null,
    payload.pagination?.partial ? "Some source results unavailable" : null,
    payload.pagination?.window_limited ? "Search window limit reached" : null,
  ].filter(Boolean).join(" · ");
  renderCoverage(payload.provider_coverage, payload.provider_outcomes || payload.manifest?.provider_outcomes);
  const runId = saved ? payload.id : payload.search_run_id || payload.reading_source_id;
  const origin = runId ? { kind: payload.reading_source_id ? "search-page" : "search", run_id: runId } : null;
  resultsList.replaceChildren(...payload.results.map((paper) => paperCard(paper,
    selectedProjectId() && paper.retrieval_kind === "saved" && paper.library_id
      ? { kind: "library", run_id: paper.library_id }
      : origin)));
  emptyState.hidden = Boolean(count);
  if (!count) {
    const failed = payload.provider_coverage.some((entry) => ["failed", "rate_limited", "unavailable"].includes(entry.status));
    emptyState.hidden = false;
    emptyState.textContent = failed ? "Some sources could not be searched. Check coverage or try again."
      : page > 1 ? "This page has no linked papers. Use the pager to go back."
      : delivery?.kind === "local" ? "No saved papers match. Try different keywords or switch to Live + saved."
      : "No linked papers matched. Broaden the query, change the field, or try another source.";
  }
  if (!preview) renderResultsPager(payload);
}

function updatePaperScope() {
  const savedOnly = form.elements.mode.value === "local";
  onlineSources.hidden = savedOnly;
  queryInput.placeholder = savedOnly ? "Search saved papers by keywords or DOI" : "Search by topic, method, or keywords";
  updateWatchButton();
}

function updateWatchButton() {
  watchSearchButton.hidden = !selectedProjectId() || form.elements.mode.value === "local" || queryInput.value.trim().length < 2;
  watchSearchStatus.hidden = true;
}

watchSearchButton.addEventListener("click", async () => {
  const projectId = selectedProjectId();
  if (!projectId || !form.reportValidity()) return;
  const providers = selectedProviders();
  if (!providers.length) {
    watchSearchStatus.textContent = "Pick a source to watch this search.";
    watchSearchStatus.hidden = false;
    return;
  }
  const fields = Object.fromEntries(new FormData(form));
  watchSearchButton.disabled = true;
  try {
    await requestJson(`/api/v1/projects/${projectId}/watches`, jsonOptions({
      q: fields.q, category: fields.category, providers: providers.join(","), limit: Number(fields.limit),
      year_min: fields.year_min ? Number(fields.year_min) : null, year_max: fields.year_max ? Number(fields.year_max) : null,
    }), "The search could not be saved.");
    watchSearchStatus.textContent = "Saved to Inbox.";
    void refreshWatchCounts();
  } catch (error) {
    watchSearchStatus.textContent = error.message;
  } finally {
    watchSearchButton.disabled = false;
    if (selectedProjectId() === projectId) watchSearchStatus.hidden = false;
  }
});

async function refreshLibraryCount() {
  try {
    const { works } = await requestJson("/api/v1/library/status", { cache: "no-store" }, "Library count unavailable.");
    libraryCount.textContent = `${works.toLocaleString()} saved ${works === 1 ? "paper" : "papers"}`;
  } catch {
    libraryCount.textContent = "";
  }
}

function finishPaperRequest(signal) {
  if (signal.aborted) return;
  submitButton.disabled = false;
  resultsSection.setAttribute("aria-busy", "false");
}

async function loadSavedSearch(runId, restoring = false) {
  const projectId = selectedProjectId();
  if (!projectId) return;
  state.paperSearch = null;
  const signal = startRequest("papers");
  setPaperLoading("Loading saved papers…");
  try {
    const saved = await requestJson(
      `/api/v1/projects/${projectId}/searches/${runId}`, { signal }, "Saved results could not be loaded."
    );
    if (signal.aborted) return;
    if (!restoring || !state.paperFormEdited) {
      const requested = saved.providers_requested.map((source) => PROVIDER_IDS[String(source).toLowerCase()] || source);
      applySearchSettings(saved.query, saved.category, requested.join(","), saved.year_min, saved.year_max, saved.limit_value);
    }
    showPaperResults(saved, true);
    if (!restoring) {
      setHistoryExpanded(false);
      resultTitle.focus();
    }
  } catch (error) {
    if (!signal.aborted) showPaperMessage("Saved results unavailable", error.message);
  } finally {
    finishPaperRequest(signal);
  }
}

async function runSearch(page = 1, previous = null) {
  let search = previous;
  if (!search) {
    const params = new URLSearchParams();
    for (const [key, value] of new FormData(form)) {
      if (String(value).trim()) params.set(key, value);
    }
    const mode = params.get("mode") || "online";
    if (mode === "online") {
      const providers = selectedProviders();
      if (!providers.length) {
        statusText.textContent = "Pick at least one source.";
        return;
      }
      params.set("providers", providers.join(","));
    }
    const projectId = selectedProjectId();
    if (projectId) params.set("project_id", projectId);
    search = { params, mode, pages: new Map() };
  }
  const cached = search.pages.get(page);
  if (cached) {
    emptyState.hidden = true;
    showPaperResults(cached);
    return;
  }
  const priorPage = state.resultsPage;
  const params = new URLSearchParams(search.params);
  params.set("page", String(page));
  const signal = startRequest("papers");
  const local = search.mode === "local";
  setPaperLoading(previous ? `Loading page ${page}…` : local ? "Searching saved papers…" : "Checking live sources…");
  let liveSettled = false;
  const request = (searchParams) => requestJson(
    `/api/v1/search?${searchParams}`, { signal, cache: "no-store" }, "Search request failed."
  );
  const cachePreview = !local && !previous
    ? request(new URLSearchParams({ ...Object.fromEntries(params), mode: "cache" }))
        .then((payload) => {
          if (!signal.aborted && !liveSettled && payload.results.length) showPaperResults(payload, false, true);
          return payload;
        }).catch(() => null)
    : null;
  try {
    const payload = await request(params);
    liveSettled = true;
    if (signal.aborted) return;
    if (!payload.pagination?.partial) search.pages.set(page, payload);
    state.paperSearch = search;
    showPaperResults(payload);
    if (!local) void refreshLibraryCount();
    if (payload.search_run_id) void refreshHistory();
  } catch (error) {
    liveSettled = true;
    const preview = await cachePreview;
    if (!signal.aborted) {
      const prior = previous?.pages.get(priorPage);
      if (preview?.results.length) {
        showPaperResults(preview, false, true);
        statusText.textContent = "Saved results · live search unavailable";
      } else if (prior) {
        showPaperResults(prior);
        statusText.textContent += ` · Page ${page} could not be loaded`;
      } else {
        showPaperMessage("Search unavailable", error.message);
      }
    }
  } finally {
    finishPaperRequest(signal);
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
    clearJournalSelection();
    journalNameInput.focus();
  });
  const details = element("div", "selected-details");
  details.append(
    element("strong", "", journal.display_name),
    element("span", "", journalMeta(journal) || `OpenAlex ${journal.id}`),
    identifierChips(journal),
    ubytBadge(journal.ubyt, { showMissing: true }),
  );
  const actions = element("div", "work-actions journal-selection-actions");
  if (window.journalFollowAction) actions.append(window.journalFollowAction(journal));
  actions.append(change);
  selectedJournalBox.replaceChildren(details, actions);
  selectedJournalBox.title = journalOriginText(journal);
  selectedJournalBox.hidden = false;
  journalCatalogCard.hidden = true;
  const supported = journal.search_supported !== false;
  updateJournalControls();
  journalStatus.textContent = supported
    ? "Journal resolved by ISSN/source ID. Add topics and search."
    : journal.resolution_note || "Journal metadata resolved, but paper search is unavailable without an OpenAlex ISSN crosswalk.";
}

let suggestionTimer;
let suggestionController;

async function resolveCatalogJournal(journal) {
  clearJournalSelection();
  const signal = startRequest("journal-identity");
  journalStatus.textContent = "Resolving journal identifiers and paper-search support…";
  const params = new URLSearchParams({
    provider: journal.catalog_provider || journalProviderSelect.value,
    journal_id: journal.provider_id || journal.id,
  });
  try {
    const payload = await requestJson(`/api/v1/journal-catalog/resolve?${params}`, { signal }, "Journal identity could not be resolved.");
    if (!signal.aborted) selectJournal(payload.journal);
  } catch (error) {
    if (!signal.aborted) journalStatus.textContent = error.message;
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
  journalCatalogCard.hidden = Boolean(state.selectedJournal);
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
  const controller = new AbortController();
  suggestionController = controller;
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
      signal: controller.signal,
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Journal catalog failed");
    if (!controller.signal.aborted) renderCatalogJournals(payload);
  } catch (error) {
    if (error.name !== "AbortError") journalCatalogStatus.textContent = error.message;
  } finally {
    if (controller === suggestionController) journalCatalogCard.classList.remove("loading");
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
  clearJournalSelection();
  journalNameInput.value = "";
  loadJournalCategories();
});

journalCategorySelect.addEventListener("change", () => {
  clearJournalSelection();
  loadCatalogJournals(journalNameInput.value.trim());
});

journalNameInput.addEventListener("input", () => {
  clearJournalSelection();
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

function updateJournalControls(busy = false) {
  journalSubmitButton.disabled = busy || !selectedProjectId() || !state.selectedJournal
    || state.selectedJournal.search_supported === false;
  refreshJournalButton.disabled = busy || !state.journalSnapshot?.project_id;
}

function clearJournalSelection() {
  state.journalFormEdited = true;
  for (const key of ["journal-identity", "journal", "fit"]) state.requests.get(key)?.abort();
  state.selectedJournal = null;
  state.journalSnapshot = null;
  selectedJournalBox.hidden = true;
  journalResults.hidden = true;
  journalCatalogCard.hidden = false;
  journalStatus.textContent = selectedProjectId()
    ? "Choose a journal from the catalog." : "Choose a topic to save journal evidence.";
  updateJournalControls();
}

function applyManuscript(manuscript) {
  manuscriptTitle.value = manuscript?.title || "";
  manuscriptAbstract.value = manuscript?.abstract || "";
  const keywords = manuscript?.keywords;
  manuscriptKeywords.value = Array.isArray(keywords) ? keywords.join(", ") : keywords || "";
}

function manuscriptInput() {
  return {
    title: manuscriptTitle.value,
    abstract: manuscriptAbstract.value,
    keywords: manuscriptKeywords.value,
  };
}

function resetJournalWorkspace() {
  state.selectedJournal = null;
  state.journalSnapshot = null;
  journalNameInput.value = "";
  journalTopicsInput.value = "";
  document.querySelector("#journal-year-min").value = "";
  document.querySelector("#journal-year-max").value = "";
  selectedJournalBox.hidden = true;
  journalCatalogCard.hidden = false;
  if (state.catalogQuery) {
    suggestionController?.abort();
    state.catalogQuery = "";
    journalSuggestions.replaceChildren();
    journalPager.hidden = true;
    journalCatalogStatus.textContent = "Search by journal name or ISSN.";
  }
  clearTimeout(suggestionTimer);
  journalResults.hidden = true;
  manuscriptPanel.hidden = true;
  manuscriptSubmitButton.disabled = false;
  fitReport.hidden = true;
  applyManuscript(state.manuscriptDrafts.get(selectedProjectId()));
  journalHistory.replaceChildren();
  journalHistoryPanel.open = false;
  journalHistoryPanel.hidden = true;
  journalStatus.textContent = selectedProjectId()
    ? "Loading saved journal evidence…" : "Choose a topic to save journal evidence.";
  updateJournalControls();
}

function renderJournalSnapshot(snapshot) {
  state.requests.get("fit")?.abort();
  state.journalSnapshot = snapshot;
  journalResults.hidden = false;
  manuscriptPanel.hidden = !snapshot.id || !snapshot.papers.length;
  manuscriptSubmitButton.disabled = false;
  journalResultTitle.textContent = snapshot.journal.display_name;
  const retrieved = new Date(snapshot.retrieved_at).toLocaleString();
  const sourceState = snapshot.cache_status === "saved"
    ? "Saved snapshot" : snapshot.cache_status === "refreshed" ? "Refreshed from OpenAlex" : "New snapshot";
  journalSnapshotStatus.textContent = `${sourceState} · retrieved ${retrieved}`;
  journalRefreshBadge.textContent = snapshot.refresh_recommended ? "Refresh recommended" : "Snapshot current";

  const topics = (snapshot.profile.top_topics || []).slice(0, 8)
    .map((item) => item.term).join(", ") || "No topic metadata";
  const years = (snapshot.profile.publications_by_year || [])
    .map((item) => `${item.year}: ${item.count}`).join(" · ") || "No year metadata";
  journalProfile.replaceChildren(
    profileCard("Saved sample", `${snapshot.papers.length} linked papers`),
    profileCard("Frequent topics", topics),
    profileCard("Papers by year", years),
    ubytProfileCard(snapshot.journal.ubyt),
  );
  const origin = snapshot.id ? { kind: "journal", run_id: snapshot.id } : null;
  journalPapers.replaceChildren(...snapshot.papers.map((paper) => paperCard(paper, origin)));
  if (!snapshot.papers.length) {
    const failed = snapshot.provider_outcomes?.some((outcome) => ["failed", "rate_limited"].includes(outcome.status));
    journalPapers.append(element("li", "empty-state", failed
      ? "The source could not be searched. Refresh from source to try again."
      : "No linked papers matched this journal, topic, and year range."));
  }

  fitReport.hidden = true;
  if (snapshot.latest_fit && snapshot.papers.length) {
    const draft = state.manuscriptDrafts.get(selectedProjectId());
    applyManuscript(draft || snapshot.latest_fit.manuscript);
    renderFitReport(snapshot.latest_fit);
  }
}

async function runJournalSearch(refresh = false) {
  const projectId = selectedProjectId();
  const previous = refresh ? state.journalSnapshot : null;
  const journal = previous?.journal || state.selectedJournal;
  if (!projectId || !journal) return;
  const yearMin = previous ? previous.year_min : document.querySelector("#journal-year-min").value || null;
  const yearMax = previous ? previous.year_max : document.querySelector("#journal-year-max").value || null;
  const topics = previous?.topics || splitCommaValues(journalTopicsInput.value);
  if (!topics.length) {
    journalStatus.textContent = "Enter at least one topic.";
    journalTopicsInput.focus();
    return;
  }
  const signal = startRequest("journal");
  updateJournalControls(true);
  journalStatus.textContent = refresh ? "Refreshing from OpenAlex…" : "Checking for saved evidence…";
  try {
    const payload = await requestJson("/api/v1/journals/search", {
      method: "POST",
      signal,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        project_id: projectId,
        journal,
        topics,
        year_min: yearMin,
        year_max: yearMax,
        limit: previous?.limit || 20,
        refresh,
      }),
    }, "Journal search failed.");
    if (signal.aborted) return;
    renderJournalSnapshot(payload);
    journalStatus.textContent = payload.cache_status === "saved" ? "Saved journal evidence loaded." : "Journal evidence saved.";
    void refreshJournalHistory();
  } catch (error) {
    if (!signal.aborted) journalStatus.textContent = error.message;
  } finally {
    if (!signal.aborted) updateJournalControls();
  }
}

journalForm.addEventListener("input", () => { state.journalFormEdited = true; });
journalForm.addEventListener("submit", (event) => {
  event.preventDefault();
  runJournalSearch();
});
refreshJournalButton.addEventListener("click", () => runJournalSearch(true));

async function loadJournalHistory(runId, restoring = false) {
  const projectId = selectedProjectId();
  if (!projectId) return;
  const signal = startRequest("journal");
  journalStatus.textContent = "Loading saved journal evidence…";
  try {
    const snapshot = await requestJson(
      `/api/v1/projects/${projectId}/journal-searches/${runId}`, { signal }, "Saved journal snapshot could not be loaded."
    );
    if (signal.aborted || (restoring && state.journalFormEdited)) return;
    selectJournal(snapshot.journal);
    journalTopicsInput.value = snapshot.topics.join(", ");
    document.querySelector("#journal-year-min").value = snapshot.year_min ?? "";
    document.querySelector("#journal-year-max").value = snapshot.year_max ?? "";
    renderJournalSnapshot(snapshot);
    journalStatus.textContent = "Saved journal evidence loaded.";
    if (!restoring) {
      journalHistoryPanel.open = false;
      journalResultTitle.focus();
    }
  } catch (error) {
    if (!signal.aborted) journalStatus.textContent = error.message;
  } finally {
    if (!signal.aborted) updateJournalControls();
  }
}

async function refreshJournalHistory(restore = false) {
  const projectId = selectedProjectId();
  if (!projectId) return;
  const signal = startRequest("journal-history");
  try {
    const { searches } = await requestJson(
      `/api/v1/projects/${projectId}/journal-searches`, { signal }, "Saved journal history could not be loaded."
    );
    if (signal.aborted) return;
    journalHistory.replaceChildren(...searches.map((search) => {
      const item = element("li", "history-item");
      const open = element("button", "secondary", "Open snapshot");
      open.type = "button";
      open.addEventListener("click", () => loadJournalHistory(search.id));
      item.append(
        element("strong", "", search.journal.display_name),
        element("span", "", `${search.topics.join(", ")} · ${search.paper_count} papers · ${new Date(search.retrieved_at).toLocaleString()}`),
        open,
      );
      return item;
    }));
    journalHistoryPanel.hidden = !searches.length;
    if (restore && !state.requests.has("journal") && !state.journalFormEdited) {
      if (searches.length) await loadJournalHistory(searches[0].id, true);
      else journalStatus.textContent = "Choose a journal to start a snapshot for this topic.";
    }
  } catch (error) {
    if (!signal.aborted && restore && !state.journalFormEdited) journalStatus.textContent = error.message;
  }
}

function renderFitReport(report) {
  fitReport.replaceChildren(
    element("p", "fit-score", `${report.overall_score}/100`),
    element("strong", "", report.summary),
    element("p", "", `Matched terms · ${report.matched_terms.join(", ") || "none in this sample"}`),
    element("p", "", `Potential vocabulary gaps · ${report.potential_gaps.join(", ") || "none identified"}`),
    element("p", "", report.disclaimer),
  );
  if (report.manuscript) {
    fitReport.prepend(element("p", "status", `Saved report · ${new Date(report.created_at).toLocaleString()}`));
  }
  const heading = element("h4", "", "Closest papers in the saved snapshot");
  const list = element("ul");
  for (const paper of report.closest_papers) {
    const item = element("li");
    const link = element("a", "paper-link", `${paper.title} — ${paper.score}/100`);
    link.href = paper.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    item.append(link, paperActivityControls(paper, link));
    list.append(item);
  }
  fitReport.append(heading, list);
  fitReport.hidden = false;
}

manuscriptForm.addEventListener("input", () => {
  state.manuscriptDrafts.set(selectedProjectId(), manuscriptInput());
});

manuscriptForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const projectId = selectedProjectId();
  const runId = state.journalSnapshot?.id;
  if (!projectId || !runId) return;
  const signal = startRequest("fit");
  manuscriptSubmitButton.disabled = true;
  try {
    const manuscript = manuscriptInput();
    const report = await requestJson(`/api/v1/journal-searches/${runId}/fit`, {
      method: "POST",
      signal,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        project_id: projectId, ...manuscript, keywords: splitCommaValues(manuscript.keywords),
      }),
    }, "Fit analysis failed.");
    if (!signal.aborted) renderFitReport(report);
  } catch (error) {
    if (!signal.aborted) {
      fitReport.replaceChildren(element("p", "", error.message));
      fitReport.hidden = false;
    }
  } finally {
    if (!signal.aborted) manuscriptSubmitButton.disabled = false;
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

function editTopic(project) {
  projectForm.reset();
  projectForm.dataset.projectId = project?.id || "";
  projectForm.elements.name.value = project?.name || "";
  projectForm.elements.research_question.value = project?.research_question || "";
  projectDialogTitle.textContent = project ? "Edit topic" : "New topic";
  createProjectButton.textContent = project ? "Save changes" : "Create topic";
  projectError.hidden = true;
  projectDialog.showModal();
}

newProjectButton.addEventListener("click", () => editTopic());
editProjectButton.addEventListener("click", () => editTopic(state.projects.get(selectedProjectId())));
cancelProjectButton.addEventListener("click", () => projectDialog.close());

projectForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (createProjectButton.disabled) return;
  const nameField = projectForm.elements.name;
  const name = nameField.value.trim();
  if (!name) {
    projectError.textContent = "Enter a topic name.";
    projectError.hidden = false;
    nameField.focus();
    return;
  }
  createProjectButton.disabled = true;
  cancelProjectButton.disabled = true;
  projectError.hidden = true;
  const projectId = projectForm.dataset.projectId;
  const formData = new FormData(projectForm);
  const path = projectId ? `/api/v1/projects/${projectId}` : "/api/v1/projects";
  const fallback = projectId ? "Topic could not be updated." : "Topic could not be created.";
  try {
    const project = await requestJson(path, {
      method: projectId ? "PATCH" : "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        name,
        research_question: formData.get("research_question"),
      }),
    }, fallback);
    if (projectId) state.projects.set(project.id, project);
    else state.projects = new Map([[project.id, project], ...state.projects]);
    topicFilter.value = "";
    renderTopics();
    projectDialog.close();
    if (!projectId) {
      selectView(workspaceTabs[0]);
      chooseTopic(project.id);
      queryInput.focus();
    }
  } catch (error) {
    projectError.textContent = error.message;
    projectError.hidden = false;
  } finally {
    createProjectButton.disabled = false;
    cancelProjectButton.disabled = false;
  }
});

projectDialog.addEventListener("cancel", (event) => {
  if (createProjectButton.disabled) event.preventDefault();
});

exportProjectButton.addEventListener("click", () => {
  if (selectedProjectId()) window.location.href = `/api/v1/projects/${selectedProjectId()}/evidence?format=markdown`;
});

form.addEventListener("input", () => {
  state.paperFormEdited = true;
  updateWatchButton();
});
for (const mode of form.elements.mode) mode.addEventListener("change", updatePaperScope);

renderSourceOptions();
updateSelectAllLabel();
updateJournalControls();
updatePaperScope();
void refreshLibraryCount();
void refreshWatchCounts();
window.setInterval(() => { if (!document.hidden) void refreshWatchCounts(); }, 45000);

Promise.allSettled([
  requestJson("/api/v1/categories", {}, "Fields could not be loaded.").then(populateCategories),
  requestJson("/api/v1/health", {}, "Source availability could not be loaded.").then(applyProviderAvailability),
]).then(loadProjects);

requestJson("/api/v1/journal-catalog/providers", {}, "Journal catalogs could not be loaded.")
  .then(initializeJournalCatalog)
  .catch((error) => { journalCatalogStatus.textContent = error.message; });

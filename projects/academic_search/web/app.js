const form = document.querySelector("#search-form");
const queryInput = document.querySelector("#query");
const categorySelect = document.querySelector("#category");
const providerSelect = document.querySelector("#providers");
const statusText = document.querySelector("#status");
const resultTitle = document.querySelector("#result-title");
const resultsList = document.querySelector("#results");
const emptyState = document.querySelector("#empty-state");
const categoryStrip = document.querySelector("#category-strip");
const resultsSection = document.querySelector(".results-section");
const submitButton = form.querySelector("button[type='submit']");
const documentForm = document.querySelector("#document-form");
const documentFile = document.querySelector("#document-file");
const documentStatus = document.querySelector("#document-status");
const documentResult = document.querySelector("#document-result");
const documentResultTitle = document.querySelector("#document-result-title");
const documentMeta = document.querySelector("#document-meta");
const documentMarkdown = document.querySelector("#document-markdown");
const documentSubmit = documentForm.querySelector("button[type='submit']");
const projectSelect = document.querySelector("#project-select");
const newProjectButton = document.querySelector("#new-project");
const exportProjectButton = document.querySelector("#export-project");
const projectDialog = document.querySelector("#project-dialog");
const projectForm = document.querySelector("#project-form");
const cancelProjectButton = document.querySelector("#cancel-project");
const historyPanel = document.querySelector("#history-panel");
const searchHistory = document.querySelector("#search-history");
const coverage = document.querySelector("#coverage");

const state = { categories: new Map(), projects: new Map() };

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
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

function applyProviderAvailability(payload) {
  const clarivate = providerSelect.querySelector("option[value='clarivate']");
  const enabled = payload.providers?.clarivate === true;
  clarivate.disabled = !enabled;
  clarivate.textContent = enabled
    ? "Web of Science (Clarivate)"
    : "Web of Science (Clarivate · key required)";
  if (!enabled && providerSelect.value === "clarivate") {
    providerSelect.value = "openalex";
  }
}

function selectedProjectId() {
  return projectSelect.value || null;
}

function applyProjectDefaults(project) {
  categorySelect.value = project.default_category || "all";
  providerSelect.value = project.default_providers || "openalex";
  document.querySelector("#year-min").value = project.default_year_min || "";
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
  document.querySelector("#limit").value = search.limit_value || manifest.limit || "20";
  const requested = (search.providers || manifest.providers_requested || [])
    .map((provider) => String(provider).toLowerCase().replace(" ", "-"));
  const option = [...providerSelect.options].find((candidate) =>
    requested.length === 1 && candidate.value === requested[0]
  );
  if (option && !option.disabled) providerSelect.value = option.value;
  runSearch();
}

async function refreshHistory() {
  const projectId = selectedProjectId();
  searchHistory.replaceChildren();
  historyPanel.hidden = !projectId;
  if (!projectId) return;
  const response = await fetch(`/api/v1/projects/${projectId}/searches`);
  if (!response.ok) return;
  const payload = await response.json();
  for (const search of payload.searches) searchHistory.append(historyItem(search));
  if (!payload.searches.length) searchHistory.hidden = true;
  else searchHistory.hidden = false;
}

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
}

function renderCoverage(entries) {
  coverage.replaceChildren();
  for (const entry of entries || []) {
    const label = entry.error_code
      ? `${entry.provider}: ${entry.status} (${entry.error_code})`
      : `${entry.provider}: ${entry.status}`;
    const item = element("span", `coverage-item ${entry.status}`, label);
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
  const title = element("h3", "", paper.title || "Untitled paper");
  const metaParts = [paper.authors, paper.journal, paper.year].filter(Boolean);
  const meta = element("p", "meta", metaParts.join(" · "));

  content.append(source, title);
  if (metaParts.length) content.append(meta);
  if (paper.abstract) {
    const abstract = paper.abstract.length > 360
      ? `${paper.abstract.slice(0, 357)}…`
      : paper.abstract;
    content.append(element("p", "abstract", abstract));
  }

  const link = element("a", "paper-link", paper.doi ? "Open DOI ↗" : "Open paper ↗");
  link.href = paper.url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.setAttribute("aria-label", `Open ${paper.title || "paper"} in a new tab`);
  item.append(content, link);
  return item;
}

async function runSearch() {
  const formData = new FormData(form);
  const params = new URLSearchParams();
  for (const [key, value] of formData.entries()) {
    if (String(value).trim()) params.set(key, value);
  }
  if (selectedProjectId()) params.set("project_id", selectedProjectId());

  resultsSection.setAttribute("aria-busy", "true");
  submitButton.disabled = true;
  statusText.textContent = "Searching scholarly sources…";
  resultTitle.textContent = "Paper links";
  resultsList.replaceChildren();
  emptyState.hidden = true;

  try {
    const response = await fetch(`/api/v1/search?${params.toString()}`);
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Search request failed");
    }

    const category = state.categories.get(payload.category);
    resultTitle.textContent = category ? category.label : "Paper links";
    statusText.textContent =
      `${payload.returned} linked result${payload.returned === 1 ? "" : "s"} · ` +
      `${payload.sources_responded.join(", ") || "No source responded"}`;
    renderCoverage(payload.provider_coverage);

    for (const paper of payload.results) {
      resultsList.append(paperCard(paper));
    }
    if (!payload.results.length) {
      emptyState.hidden = false;
      emptyState.textContent =
        "No linked papers matched this query and category. Try All fields, another source, or a broader query.";
    }
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

form.addEventListener("submit", (event) => {
  event.preventDefault();
  runSearch();
});

documentForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = documentFile.files[0];
  if (!file) return;
  if (file.size > 50 * 1024 * 1024) {
    documentStatus.textContent = "This document exceeds the 50 MB parser limit.";
    return;
  }

  documentSubmit.disabled = true;
  documentResult.hidden = true;
  documentStatus.textContent = `Parsing ${file.name} with local Firecrawl…`;
  try {
    const response = await fetch(`/api/v1/documents/parse?filename=${encodeURIComponent(file.name)}`, {
      method: "POST",
      headers: { "content-type": file.type || "application/octet-stream" },
      body: await file.arrayBuffer(),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Document parsing failed");

    const metadata = payload.metadata || {};
    documentResultTitle.textContent = payload.filename;
    documentMeta.textContent = [metadata.title, metadata.contentType, payload.source]
      .filter(Boolean)
      .join(" · ");
    documentMarkdown.textContent = payload.markdown || payload.summary || "No readable text was returned.";
    documentResult.hidden = false;
    documentStatus.textContent = "Document parsed. Review the extracted text alongside the original file.";
  } catch (error) {
    documentStatus.textContent = error.message;
  } finally {
    documentSubmit.disabled = false;
  }
});

projectSelect.addEventListener("change", async () => {
  const projectId = selectedProjectId();
  if (projectId) {
    localStorage.setItem("academic-search-current-project", projectId);
    applyProjectDefaults(state.projects.get(projectId));
  } else {
    localStorage.removeItem("academic-search-current-project");
  }
  exportProjectButton.disabled = !projectId;
  await refreshHistory();
});

newProjectButton.addEventListener("click", () => projectDialog.showModal());
cancelProjectButton.addEventListener("click", () => projectDialog.close());
projectForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(projectForm);
  const response = await fetch("/api/v1/projects", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      name: formData.get("name"),
      research_question: formData.get("research_question"),
      default_category: categorySelect.value,
      default_providers: providerSelect.value,
      default_year_min: document.querySelector("#year-min").value || null,
    }),
  });
  const payload = await response.json();
  if (!response.ok) {
    statusText.textContent = payload.detail || "Project could not be created";
    return;
  }
  projectForm.reset();
  projectDialog.close();
  await refreshProjects(payload.id);
});

exportProjectButton.addEventListener("click", () => {
  if (selectedProjectId()) window.location.href = `/api/v1/projects/${selectedProjectId()}/evidence?format=markdown`;
});

Promise.all([
  fetch("/api/v1/categories").then((response) => response.json()),
  fetch("/api/v1/health").then((response) => response.json()),
])
  .then(async ([categories, health]) => {
    populateCategories(categories);
    applyProviderAvailability(health);
    await refreshProjects();
  })
  .catch(() => {
    statusText.textContent = "Categories could not be loaded.";
  });

queryInput.focus();

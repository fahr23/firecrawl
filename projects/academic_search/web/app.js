const form = document.querySelector("#search-form");
const queryInput = document.querySelector("#query");
const categorySelect = document.querySelector("#category");
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

const state = { categories: new Map() };

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

    for (const paper of payload.results) {
      resultsList.append(paperCard(paper));
    }
    if (!payload.results.length) {
      emptyState.hidden = false;
      emptyState.textContent =
        "No linked papers matched this query and category. Try All fields, another source, or a broader query.";
    }
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

fetch("/api/v1/categories")
  .then((response) => response.json())
  .then(populateCategories)
  .catch(() => {
    statusText.textContent = "Categories could not be loaded.";
  });

queryInput.focus();

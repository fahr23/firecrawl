const serviceStatus = document.querySelector("#service-status");
const firecrawlStatus = document.querySelector("#firecrawl-status");
const form = document.querySelector("#lookup-form");
const instrument = document.querySelector("#instrument");
const kind = document.querySelector("#kind");
const lookupStatus = document.querySelector("#lookup-status");
const result = document.querySelector("#result");
const resultKicker = document.querySelector("#result-kicker");
const resultTitle = document.querySelector("#result-title");
const resultStatus = document.querySelector("#result-status");
const summary = document.querySelector("#summary");
const rawResponse = document.querySelector("#raw-response");

function label(value) {
  return String(value ?? "—").replaceAll("_", " ");
}

function appendFact(name, value) {
  const term = document.createElement("dt");
  term.textContent = label(name);
  const definition = document.createElement("dd");
  definition.textContent = Array.isArray(value) ? value.join(", ") : label(value);
  summary.append(term, definition);
}

function showResult(payload, selectedKind) {
  const data = payload.payload || {};
  result.hidden = false;
  resultKicker.textContent = `${label(selectedKind)} · ${payload.market || "bist"}`;
  resultTitle.textContent = payload.instrument || instrument.value.toUpperCase();
  resultStatus.textContent = payload.status || "unknown";
  resultStatus.className = `pill ${payload.status || "unknown"}`;
  summary.replaceChildren();
  appendFact("Provider", payload.provider);
  appendFact("Source", payload.source);
  appendFact("As of", payload.as_of);
  appendFact("Freshness seconds", payload.freshness_seconds);
  if (payload.status === "unavailable") appendFact("Availability", "No matching record is currently available.");
  for (const [key, value] of Object.entries(data)) appendFact(key, value);
  rawResponse.textContent = JSON.stringify(payload, null, 2);
}

async function loadStatus() {
  try {
    const [healthResponse, capabilitiesResponse] = await Promise.all([
      fetch("/api/external/v1/health"), fetch("/api/external/v1/capabilities"),
    ]);
    const health = await healthResponse.json();
    const capabilities = await capabilitiesResponse.json();
    serviceStatus.textContent = health.status || "unavailable";
    const firecrawl = capabilities.firecrawl || {};
    firecrawlStatus.textContent = firecrawl.status === "ok"
      ? `ready · ${(firecrawl.operations || []).join(", ")}`
      : "unavailable";
  } catch {
    serviceStatus.textContent = "unavailable";
    firecrawlStatus.textContent = "unavailable";
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const ticker = instrument.value.trim().toUpperCase();
  if (!ticker) return;
  const selectedKind = kind.value;
  const button = form.querySelector("button");
  button.disabled = true;
  result.hidden = true;
  lookupStatus.textContent = `Loading ${selectedKind} data for ${ticker}…`;
  try {
    const response = await fetch(`/api/external/v1/${selectedKind}/${encodeURIComponent(ticker)}?market=bist`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "The service could not load this record.");
    showResult(payload, selectedKind);
    lookupStatus.textContent = payload.status === "ok" ? "Current service response loaded." : "The service returned an honest partial or unavailable result.";
  } catch (error) {
    lookupStatus.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

loadStatus();

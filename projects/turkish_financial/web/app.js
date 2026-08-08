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
const instrumentOptions = document.querySelector("#instrument-options");
const catalogStatus = document.querySelector("#catalog-status");
const rankingSort = document.querySelector("#ranking-sort");
const rankingWindow = document.querySelector("#ranking-window");
const loadRankingButton = document.querySelector("#load-ranking");
const rankingList = document.querySelector("#ranking-list");
const refreshWindow = document.querySelector("#refresh-window");
const refreshScoresButton = document.querySelector("#refresh-scores");
const refreshStatus = document.querySelector("#refresh-status");
const isyatirimWindow = document.querySelector("#isyatirim-window");
const loadIsyatirimButton = document.querySelector("#load-isyatirim");
const isyatirimStatus = document.querySelector("#isyatirim-status");
const isyatirimResult = document.querySelector("#isyatirim-result");
const isyatirimSummary = document.querySelector("#isyatirim-summary");
const isyatirimRows = document.querySelector("#isyatirim-rows");
const isyatirimRaw = document.querySelector("#isyatirim-raw");
const loadIsyatirimFundamentalsButton = document.querySelector("#load-isyatirim-fundamentals");
const isyatirimFundamentalsStatus = document.querySelector("#isyatirim-fundamentals-status");
const isyatirimFundamentalsResult = document.querySelector("#isyatirim-fundamentals-result");
const isyatirimFundamentalsSummary = document.querySelector("#isyatirim-fundamentals-summary");
const isyatirimFundamentalsRaw = document.querySelector("#isyatirim-fundamentals-raw");
const collectIsyatirimFundamentalsButton = document.querySelector("#collect-isyatirim-fundamentals");
const isyatirimCollectionStatus = document.querySelector("#isyatirim-collection-status");
const isyatirimFundamentalsSearch = document.querySelector("#isyatirim-fundamentals-search");
const isyatirimFundamentalsQuery = document.querySelector("#isyatirim-fundamentals-query");
const isyatirimFundamentalsList = document.querySelector("#isyatirim-fundamentals-list");
const isyatirimFundamentalsListRows = document.querySelector("#isyatirim-fundamentals-list-rows");
const localYouTubeBrowser = document.querySelector("#local-youtube-browser");
const localTranscriptionButton = document.querySelector("#run-local-transcription");
const stopLocalTranscriptionButton = document.querySelector("#stop-local-transcription");
const localTranscriptionStatus = document.querySelector("#local-transcription-status");
const localYouTubeSources = document.querySelector("#local-youtube-sources");
const addLocalYouTubeSourceForm = document.querySelector("#add-local-youtube-source");
const localYouTubeSourceUrl = document.querySelector("#local-youtube-source-url");
const resetLocalYouTubeSourcesButton = document.querySelector("#reset-local-youtube-sources");
const localYouTubeSourcesStatus = document.querySelector("#local-youtube-sources-status");
const localRunnerUrl = "http://127.0.0.1:8765";

function label(value) {
  return String(value ?? "—").replaceAll("_", " ");
}

function datasetLabel(value) {
  return {
    sentiment: "KAP disclosure sentiment",
    "combined-sentiment": "Combined sentiment",
    "news-sentiment": "News-portal sentiment",
    "social-sentiment": "Social sentiment",
    "youtube-sentiment": "YouTube sentiment",
    fundamental: "KAP fundamentals",
  }[value] || label(value);
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
  resultKicker.textContent = `${datasetLabel(selectedKind)} · ${payload.market || "bist"}`;
  resultTitle.textContent = payload.instrument || instrument.value.toUpperCase();
  resultStatus.textContent = payload.status || "unknown";
  resultStatus.className = `pill ${payload.status || "unknown"}`;
  summary.replaceChildren();
  const tradingView = document.createElement("a");
  tradingView.href = `https://www.tradingview.com/symbols/BIST-${encodeURIComponent(payload.instrument || instrument.value.toUpperCase())}/`;
  tradingView.target = "_blank";
  tradingView.rel = "noopener noreferrer";
  tradingView.textContent = "Open TradingView chart ↗";
  appendFact("Provider", payload.provider);
  appendFact("Source", payload.source);
  appendFact("As of", payload.as_of);
  appendFact("Freshness seconds", payload.freshness_seconds);
  if (payload.status === "unavailable") appendFact("Availability", "No matching record is currently available.");
  for (const [key, value] of Object.entries(data)) appendFact(key, value);
  summary.append(tradingView);
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

async function loadInstrumentCatalog() {
  try {
    const response = await fetch("/api/external/v1/instruments?market=bist");
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Instrument catalogue unavailable");
    for (const item of payload.items || []) {
      const option = document.createElement("option");
      option.value = item.ticker;
      option.label = item.company_name ? `${item.ticker} — ${item.company_name}` : item.ticker;
      instrumentOptions.append(option);
    }
    catalogStatus.textContent = `${payload.total || 0} BIST instruments available for lookup. Names are a database catalogue or clearly labelled built-in starter catalogue.`;
  } catch {
    catalogStatus.textContent = "Instrument catalogue is unavailable; you can still enter a BIST ticker.";
  }
}

async function loadRanking() {
  loadRankingButton.disabled = true;
  rankingList.replaceChildren();
  try {
    const response = await fetch(`/api/external/v1/combined-sentiment/ranking?market=bist&sort=${rankingSort.value}&window_days=${rankingWindow.value}`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Ranking is unavailable");
    for (const item of payload.items || []) {
      const row = document.createElement("li");
      const score = item.payload?.score;
      const header = document.createElement("div");
      header.className = "rank-header";
      const title = document.createElement("strong");
      title.textContent = item.instrument;
      const label = document.createElement("span");
      label.className = `sentiment-label ${item.payload?.overall_sentiment || "unavailable"}`;
      label.textContent = item.payload?.overall_sentiment || "unavailable";
      header.append(title, label);
      const metrics = document.createElement("div");
      metrics.className = "rank-metrics";
      for (const [name, value] of [
        ["Raw", typeof score === "number" ? score.toFixed(3) : "—"],
        ["Adjusted", (item.payload?.adjusted_score ?? 0).toFixed(3)],
        ["Evidence", (item.payload?.evidence_quality ?? 0).toFixed(2)],
        ["Samples", item.payload?.sample_size || 0],
      ]) {
        const metric = document.createElement("span");
        metric.innerHTML = `<small>${name}</small>${value}`;
        metrics.append(metric);
      }
      const provenance = document.createElement("p");
      provenance.className = "provenance";
      provenance.textContent = `Sources: ${(item.payload?.source_types || []).join(" + ") || "none"} · as of ${item.as_of || "unknown"}`;
      const tradingView = document.createElement("a");
      tradingView.href = `https://www.tradingview.com/symbols/BIST-${encodeURIComponent(item.instrument)}/`;
      tradingView.target = "_blank";
      tradingView.rel = "noopener noreferrer";
      tradingView.textContent = "TradingView ↗";
      const sources = document.createElement("button");
      sources.type = "button";
      sources.className = "source-links";
      sources.textContent = "Show source links";
      const sourcePanel = document.createElement("div");
      sourcePanel.className = "source-panel";
      sourcePanel.hidden = true;
      let sourceLinksLoaded = false;
      sources.addEventListener("click", async () => {
        if (!sourcePanel.hidden) {
          sourcePanel.hidden = true;
          sources.textContent = "Show source links";
          return;
        }
        sourcePanel.hidden = false;
        sources.textContent = "Hide source links";
        if (sourceLinksLoaded) return;
        sourcePanel.textContent = "Loading stored source links…";
        try {
          const response = await fetch(`/api/external/v1/combined-sentiment/${encodeURIComponent(item.instrument)}/evidence?market=bist&window_days=${rankingWindow.value}`);
          const evidence = await response.json();
          const links = evidence.items || [];
          sourcePanel.replaceChildren(...links.map((entry) => {
            const link = document.createElement("a");
            link.href = entry.url; link.target = "_blank"; link.rel = "noopener noreferrer";
            link.textContent = `${entry.source}: ${entry.title || "source"} ↗`;
            return link;
          }));
          if (!links.length) sourcePanel.textContent = "No stored direct source URL for this window.";
          sourceLinksLoaded = true;
        } catch { sourcePanel.textContent = "Stored source links unavailable"; }
      });
      const actions = document.createElement("div");
      actions.className = "rank-actions";
      actions.append(tradingView, sources);
      row.append(header, metrics, provenance, actions, sourcePanel);
      row.className = `sentiment-${item.payload?.overall_sentiment || "unavailable"}`;
      rankingList.append(row);
    }
    if (!payload.items?.length) rankingList.textContent = "No stored combined-sentiment records are available yet.";
  } catch (error) {
    rankingList.textContent = error.message;
  } finally {
    loadRankingButton.disabled = false;
  }
}

async function loadLookup() {
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
}

async function refreshLatestScores() {
  const ticker = instrument.value.trim().toUpperCase();
  if (!ticker) {
    refreshStatus.textContent = "Enter a ticker before collecting source data.";
    return;
  }
  refreshScoresButton.disabled = true;
  refreshStatus.textContent = "Fetching the latest configured source data. This can take several minutes…";
  try {
    const response = await fetch("/api/external/v1/scores/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ticker, days_back: Number(refreshWindow.value) }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Source refresh failed.");
    const completed = (payload.sources || []).map((source) => `${source.source}: ${source.status}`).join(" · ");
    refreshStatus.textContent = payload.status === "ok"
      ? `Latest source data ready. ${completed}`
      : `Latest source data updated with partial results. ${completed}`;
    await Promise.all([loadRanking(), loadLookup()]);
  } catch (error) {
    refreshStatus.textContent = error.message || "Source refresh failed.";
  } finally {
    refreshScoresButton.disabled = false;
  }
}

function number(value, options = {}) {
  return typeof value === "number" ? new Intl.NumberFormat("tr-TR", options).format(value) : "—";
}

function appendIsyatirimFact(name, value, target = isyatirimSummary) {
  const term = document.createElement("dt");
  term.textContent = name;
  const definition = document.createElement("dd");
  definition.textContent = value;
  target.append(term, definition);
}

function showIsyatirimMarketData(response) {
  const payload = response.payload || {};
  const latest = payload.latest || {};
  const metrics = payload.metrics || {};
  isyatirimResult.hidden = false;
  isyatirimSummary.replaceChildren();
  appendIsyatirimFact("As of", latest.trading_date || response.as_of || "—");
  appendIsyatirimFact("Close (TRY)", number(latest.close_try, { maximumFractionDigits: 4 }));
  appendIsyatirimFact("Daily change", metrics.daily_change_percent == null ? "—" : `%${number(metrics.daily_change_percent, { maximumFractionDigits: 2 })}`);
  appendIsyatirimFact("Window change", metrics.window_change_percent == null ? "—" : `%${number(metrics.window_change_percent, { maximumFractionDigits: 2 })}`);
  appendIsyatirimFact("Average price", number(latest.average_price_try, { maximumFractionDigits: 4 }));
  appendIsyatirimFact("USD close", number(latest.close_usd, { maximumFractionDigits: 4 }));
  appendIsyatirimFact("USD/TRY", number(latest.usd_try, { maximumFractionDigits: 4 }));
  appendIsyatirimFact("Index value", number(latest.index_value, { maximumFractionDigits: 2 }));
  appendIsyatirimFact("Market value", number(latest.market_cap_try, { notation: "compact", maximumFractionDigits: 2 }));
  appendIsyatirimFact("Free-float value", number(latest.free_float_market_cap_try, { notation: "compact", maximumFractionDigits: 2 }));
  isyatirimRows.replaceChildren();
  for (const row of (payload.series || []).slice(-10).reverse()) {
    const item = document.createElement("tr");
    for (const value of [
      row.trading_date,
      number(row.close_try, { maximumFractionDigits: 4 }),
      `${number(row.low_try, { maximumFractionDigits: 4 })} – ${number(row.high_try, { maximumFractionDigits: 4 })}`,
      number(row.volume_try, { notation: "compact", maximumFractionDigits: 2 }),
      number(row.market_cap_try, { notation: "compact", maximumFractionDigits: 2 }),
    ]) {
      const cell = document.createElement("td");
      cell.textContent = value;
      item.append(cell);
    }
    isyatirimRows.append(item);
  }
  isyatirimRaw.textContent = JSON.stringify(response, null, 2);
}

async function loadIsyatirimMarketData() {
  const ticker = instrument.value.trim().toUpperCase();
  if (!ticker) {
    isyatirimStatus.textContent = "Enter a BIST ticker first.";
    return;
  }
  loadIsyatirimButton.disabled = true;
  isyatirimStatus.textContent = `Loading public İş Yatırım daily data for ${ticker}…`;
  try {
    const response = await fetch(`/api/external/v1/isyatirim/${encodeURIComponent(ticker)}/market-history?market=bist&days=${isyatirimWindow.value}`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "İş Yatırım data is unavailable.");
    showIsyatirimMarketData(payload);
    const cacheStatus = payload.payload?.cache?.status === "database_cache" ? "from the local database cache" : "from İş Yatırım's public JSON";
    isyatirimStatus.textContent = `${payload.payload?.metrics?.trading_days || 0} trading days loaded ${cacheStatus}. Review the raw fields below; this is not an investment recommendation.`;
  } catch (error) {
    isyatirimStatus.textContent = error.message || "İş Yatırım data is unavailable.";
  } finally {
    loadIsyatirimButton.disabled = false;
  }
}

function showIsyatirimFundamentals(response) {
  const payload = response.payload || {};
  const statement = payload.statement_snapshot || {};
  const valuation = payload.current_valuation || {};
  isyatirimFundamentalsResult.hidden = false;
  isyatirimFundamentalsSummary.replaceChildren();
  appendIsyatirimFact("Reported period", (payload.reported_periods || []).join(" vs ") || "—", isyatirimFundamentalsSummary);
  appendIsyatirimFact("Statement unit", payload.statement_unit || "—", isyatirimFundamentalsSummary);
  appendIsyatirimFact("Equity", number(statement.equity_million_try, { maximumFractionDigits: 1 }) + " mn TRY", isyatirimFundamentalsSummary);
  appendIsyatirimFact("Net income", number(statement.net_income_million_try, { maximumFractionDigits: 1 }) + " mn TRY", isyatirimFundamentalsSummary);
  appendIsyatirimFact("P/E (F/K)", number(valuation.price_to_earnings, { maximumFractionDigits: 2 }), isyatirimFundamentalsSummary);
  appendIsyatirimFact("EV / EBITDA", number(valuation.enterprise_value_to_ebitda, { maximumFractionDigits: 2 }), isyatirimFundamentalsSummary);
  appendIsyatirimFact("P/B (PD/DD)", number(valuation.price_to_book, { maximumFractionDigits: 2 }), isyatirimFundamentalsSummary);
  appendIsyatirimFact("EV / Sales", number(valuation.enterprise_value_to_sales, { maximumFractionDigits: 2 }), isyatirimFundamentalsSummary);
  appendIsyatirimFact("Net debt", number(valuation.net_debt_million_try, { maximumFractionDigits: 1 }) + " mn TRY", isyatirimFundamentalsSummary);
  appendIsyatirimFact("Free float", number(valuation.free_float_percent, { maximumFractionDigits: 2 }) + "%", isyatirimFundamentalsSummary);
  isyatirimFundamentalsRaw.textContent = JSON.stringify(response, null, 2);
}

async function loadIsyatirimFundamentals() {
  const ticker = instrument.value.trim().toUpperCase();
  if (!ticker) {
    isyatirimFundamentalsStatus.textContent = "Enter a BIST ticker first.";
    return;
  }
  loadIsyatirimFundamentalsButton.disabled = true;
  isyatirimFundamentalsStatus.textContent = `Loading İş Yatırım fundamentals for ${ticker}…`;
  try {
    const response = await fetch(`/api/external/v1/isyatirim/${encodeURIComponent(ticker)}/fundamentals?market=bist`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "İş Yatırım fundamentals are unavailable.");
    showIsyatirimFundamentals(payload);
    const cacheStatus = payload.payload?.cache?.status === "database_cache" ? "from the local database cache" : "from İş Yatırım's public company card";
    isyatirimFundamentalsStatus.textContent = `Fundamentals loaded ${cacheStatus}. Values are informational source data, not an investment recommendation.`;
  } catch (error) {
    isyatirimFundamentalsStatus.textContent = error.message || "İş Yatırım fundamentals are unavailable.";
  } finally {
    loadIsyatirimFundamentalsButton.disabled = false;
  }
}

function showCollectionStatus(payload) {
  const status = payload.status || "idle";
  const total = payload.total || 0;
  isyatirimCollectionStatus.textContent = status === "running"
    ? `Collecting ${payload.completed || 0}/${total}: ${payload.fetched || 0} fetched, ${payload.cached || 0} cached, ${payload.failed || 0} unavailable.`
    : status === "completed"
      ? `Completed ${total}: ${payload.fetched || 0} fetched, ${payload.cached || 0} reused from database, ${payload.failed || 0} unavailable.`
      : "Not running. This can take several minutes on the first collection.";
  collectIsyatirimFundamentalsButton.disabled = status === "running";
}

async function loadFundamentalsCollectionStatus() {
  const response = await fetch("/api/external/v1/isyatirim/fundamentals/collection-status");
  const payload = await response.json();
  showCollectionStatus(payload);
  if (payload.status === "running") window.setTimeout(loadFundamentalsCollectionStatus, 3000);
}

async function collectAllIsyatirimFundamentals() {
  collectIsyatirimFundamentalsButton.disabled = true;
  try {
    const response = await fetch("/api/external/v1/isyatirim/fundamentals/collect", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ force: false }) });
    const payload = await response.json();
    if (!response.ok && response.status !== 409) throw new Error(payload.detail || "Collection could not start.");
    showCollectionStatus({ ...payload, status: "running" });
    window.setTimeout(loadFundamentalsCollectionStatus, 1000);
  } catch (error) {
    isyatirimCollectionStatus.textContent = error.message || "Collection could not start.";
    collectIsyatirimFundamentalsButton.disabled = false;
  }
}

async function searchStoredFundamentals(event) {
  event.preventDefault();
  const response = await fetch(`/api/external/v1/isyatirim/fundamentals?query=${encodeURIComponent(isyatirimFundamentalsQuery.value)}&limit=50`);
  const payload = await response.json();
  if (!response.ok) {
    isyatirimCollectionStatus.textContent = payload.detail || "Database search failed.";
    return;
  }
  isyatirimFundamentalsListRows.replaceChildren();
  for (const item of payload.items || []) {
    const row = document.createElement("tr");
    for (const value of [item.ticker, item.report_period || "—", number(item.price_to_earnings, { maximumFractionDigits: 2 }), number(item.price_to_book, { maximumFractionDigits: 2 }), number(item.net_income_million_try, { maximumFractionDigits: 1 }) + " mn TRY"]) {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.append(cell);
    }
    isyatirimFundamentalsListRows.append(row);
  }
  isyatirimFundamentalsList.hidden = (payload.items || []).length === 0;
  isyatirimCollectionStatus.textContent = `${payload.total || 0} stored fundamental snapshots found. Select a ticker above to inspect its full one-year JSON.`;
}

async function loadLocalTranscriptionStatus() {
  try {
    const response = await fetch(localRunnerUrl + "/status");
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Local runner unavailable.");
    if (payload.running) {
      localTranscriptionButton.disabled = true;
      stopLocalTranscriptionButton.disabled = Boolean(payload.stopping);
      stopLocalTranscriptionButton.textContent = payload.stopping ? "Stopping…" : "Stop safely";
      localTranscriptionStatus.textContent = payload.stopping
        ? "Stopping after the current tool process exits; incomplete video text is not saved."
        : "Local transcription is running. Whisper is loaded only for this job.";
      return true;
    }
    localTranscriptionButton.disabled = false;
    stopLocalTranscriptionButton.disabled = true;
    stopLocalTranscriptionButton.textContent = "Stop safely";
    const result = payload.last_result;
    const analysis = result?.analysis;
    localTranscriptionStatus.textContent = payload.last_was_stopped
      ? "The local transcription was stopped safely. Completed videos remain cached; the incomplete video was not saved."
      : payload.last_exit_code === 0 && result
      ? `Last run: ${result.stored} stored, ${result.cached} already cached, ${result.deferred} deferred, ${result.failed} unavailable.${analysis ? ` ${analysis.analyzed || 0} ticker mentions analyzed; ${analysis.aggregated_tickers || 0} score rows updated.` : ""}`
      : payload.last_exit_code === 0
        ? "Last local transcription completed. New videos remain cached by video ID."
        : "Ready to transcribe only new videos on this Mac.";
    return false;
  } catch {
    localTranscriptionButton.disabled = true;
    stopLocalTranscriptionButton.disabled = true;
    localTranscriptionStatus.textContent = "Local runner is not installed. Run install_youtube_runner_macos.sh once, then reload this page.";
    return false;
  }
}

function showLocalYouTubeSources(payload) {
  localYouTubeSources.replaceChildren();
  for (const source of payload.sources || []) {
    const item = document.createElement("li");
    const link = document.createElement("a");
    link.href = source;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = source.replace("https://www.youtube.com/", "");
    link.title = source;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "secondary-action";
    remove.textContent = "Remove";
    remove.addEventListener("click", () => removeLocalYouTubeSource(source));
    item.append(link, remove);
    localYouTubeSources.append(item);
  }
  if (!payload.sources?.length) localYouTubeSourcesStatus.textContent = "No YouTube channels are configured.";
  else localYouTubeSourcesStatus.textContent = payload.using_local_override
    ? "These local channels override the project defaults for the next transcription run."
    : "Using the project’s configured YouTube channels. Add or remove a channel to create a local override.";
}

async function requestLocalSources(path = "/sources", options = {}) {
  const response = await fetch(localRunnerUrl + path, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || "YouTube sources could not be updated.");
  showLocalYouTubeSources(payload);
}

async function loadLocalYouTubeSources() {
  try {
    await requestLocalSources();
  } catch (error) {
    localYouTubeSourcesStatus.textContent = error.message || "YouTube source list is unavailable.";
  }
}

async function addLocalYouTubeSource(event) {
  event.preventDefault();
  const channel = localYouTubeSourceUrl.value.trim();
  if (!channel) return;
  localYouTubeSourcesStatus.textContent = "Adding YouTube channel…";
  try {
    await requestLocalSources("/sources", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ channel }),
    });
    localYouTubeSourceUrl.value = "";
  } catch (error) {
    localYouTubeSourcesStatus.textContent = error.message || "Channel could not be added.";
  }
}

async function removeLocalYouTubeSource(channel) {
  localYouTubeSourcesStatus.textContent = "Removing YouTube channel…";
  try {
    await requestLocalSources("/sources", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ channel }),
    });
  } catch (error) {
    localYouTubeSourcesStatus.textContent = error.message || "Channel could not be removed.";
  }
}

async function resetLocalYouTubeSources() {
  localYouTubeSourcesStatus.textContent = "Restoring project defaults…";
  try {
    await requestLocalSources("/sources/reset", { method: "POST", headers: { "Content-Type": "application/json" } });
  } catch (error) {
    localYouTubeSourcesStatus.textContent = error.message || "Project defaults could not be restored.";
  }
}

async function runLocalTranscription() {
  localTranscriptionButton.disabled = true;
  localTranscriptionStatus.textContent = "Starting the local YouTube-to-text run…";
  try {
    const response = await fetch(localRunnerUrl + "/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cookies_from_browser: localYouTubeBrowser.value }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Local transcription could not start.");
    localTranscriptionStatus.textContent = "Local transcription started. You can keep this page open or return later.";
    window.setTimeout(loadLocalTranscriptionStatus, 1200);
  } catch (error) {
    localTranscriptionButton.disabled = false;
    localTranscriptionStatus.textContent = error.message || "Local transcription could not start.";
  }
}

async function stopLocalTranscription() {
  stopLocalTranscriptionButton.disabled = true;
  localTranscriptionStatus.textContent = "Stopping local transcription…";
  try {
    const response = await fetch(localRunnerUrl + "/stop", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Local transcription could not be stopped.");
    window.setTimeout(loadLocalTranscriptionStatus, 500);
  } catch (error) {
    localTranscriptionStatus.textContent = error.message || "Local transcription could not be stopped.";
    window.setTimeout(loadLocalTranscriptionStatus, 500);
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  loadLookup();
});

loadStatus();
loadInstrumentCatalog();
loadRankingButton.addEventListener("click", loadRanking);
rankingSort.addEventListener("change", loadRanking);
rankingWindow.addEventListener("change", loadRanking);
refreshScoresButton.addEventListener("click", refreshLatestScores);
loadIsyatirimButton.addEventListener("click", loadIsyatirimMarketData);
loadIsyatirimFundamentalsButton.addEventListener("click", loadIsyatirimFundamentals);
collectIsyatirimFundamentalsButton.addEventListener("click", collectAllIsyatirimFundamentals);
isyatirimFundamentalsSearch.addEventListener("submit", searchStoredFundamentals);
localTranscriptionButton.addEventListener("click", runLocalTranscription);
stopLocalTranscriptionButton.addEventListener("click", stopLocalTranscription);
addLocalYouTubeSourceForm.addEventListener("submit", addLocalYouTubeSource);
resetLocalYouTubeSourcesButton.addEventListener("click", resetLocalYouTubeSources);
loadRanking();
loadLocalTranscriptionStatus();
loadLocalYouTubeSources();
loadFundamentalsCollectionStatus();
window.setInterval(loadLocalTranscriptionStatus, 15000);

"use strict";

(() => {
  const views = {
    "discover-view": ["Discover", "Compare publication trends, review recent papers, and build a reading shortlist."],
    "today-view": ["Today", "Pick up your research, reading, and manuscript tasks across topics."],
    "inbox-view": ["Research inbox", "Check saved searches and revisit papers you’ve opened or read."],
    "daily-view": ["Daily reading", "Read a fresh set of studies and explore research trends on your own schedule."],
    "submissions-view": ["Submission opportunities", "Find calls for papers and track the submission routes that fit this topic."],
    "manuscript-view": ["Manuscript workspace", "Build your outline, review evidence, and prepare the draft for your target journal."],
    "dossier-view": ["Academic portfolio", "Reuse evidence across topics and track the criteria for each application."],
  };
  const readingStates = { saved: "Saved", reading: "Reading", included: "Included", excluded: "Excluded" };
  const opportunityStates = { open: "Open", upcoming: "Upcoming", closed: "Closed", unverified: "Unverified" };
  const opportunityKinds = { regular: "Regular journal submission", special_issue: "Special issue", conference: "Conference", workshop: "Workshop" };
  const manuscriptKinds = { original: "Original research", review: "Review", methods: "Methods paper", case_report: "Case report" };
  const watchIntervals = [["0", "Manual"], ["24", "Daily"], ["168", "Weekly"]];
  const submissionStates = { planned: "Planned", submitted: "Submitted", in_review: "In review",
    revision_requested: "Revision requested", resubmitted: "Resubmitted", accepted: "Accepted",
    rejected: "Rejected", withdrawn: "Withdrawn", published: "Published" };
  let activeView = null;

  function route(projectId, path) {
    return `/api/v1/projects/${projectId}/workspace/${path}`;
  }

  function request(ctx, path, method = "GET", data) {
    const options = { method, signal: ctx.signal };
    if (data !== undefined) {
      options.headers = { "content-type": "application/json" };
      options.body = JSON.stringify(data);
    }
    return requestJson(route(ctx.id, path), options, "This request could not be completed.");
  }

  function workflow(ctx, path, method = "GET", data) {
    const options = data === undefined ? { method, signal: ctx.signal } : jsonOptions(data, method, ctx.signal);
    return requestJson(`/api/v1/${path}`, { ...options, cache: "no-store" }, "This request could not be completed.");
  }

  async function items(ctx, section, limit = 100) {
    return (await request(ctx, `${section}?limit=${limit}`)).items;
  }

  async function save(ctx, section, data, entry) {
    const path = entry ? `${section}/${entry.id}` : section;
    return request(ctx, path, entry ? "PUT" : "POST", { revision: entry?.revision || 0, data });
  }

  window.shortlistWorkspacePaper = async (origin, paper, button) => {
    const projectId = selectedProjectId();
    if (!projectId) return;
    button.disabled = true;
    button.textContent = "Saving…";
    try {
      const item = await request({ id: projectId }, "reading/from-source", "POST", { ...origin, paper_url: paper.url });
      button.textContent = "Saved to shortlist";
      document.dispatchEvent(new CustomEvent("academic-shortlist-save", { detail: { projectId, item } }));
    } catch (error) {
      button.textContent = "Retry saving";
      button.title = error.message;
      button.disabled = false;
    }
  };

  function link(url, label) {
    const anchor = element("a", "work-link", label);
    anchor.href = url;
    anchor.target = "_blank";
    anchor.rel = "noopener noreferrer";
    return anchor;
  }

  function download(ctx, path, label) {
    const anchor = element("a", "work-link", label);
    anchor.href = route(ctx.id, path);
    return anchor;
  }

  function jump(id, label) {
    const anchor = element("a", "work-link", label);
    anchor.href = `#${id}`;
    return anchor;
  }

  function row(...children) {
    const node = element("div", "work-actions");
    node.append(...children);
    return node;
  }

  function button(label, action, secondary = true) {
    const node = element("button", secondary ? "secondary" : "", label);
    node.type = "button";
    node.addEventListener("click", action);
    return node;
  }

  function note(text) {
    return element("p", "work-note", text);
  }

  function status(text = "") {
    const node = element("p", "work-status", text);
    node.setAttribute("role", "status");
    node.hidden = !text;
    return node;
  }

  function show(node, text, failed = false) {
    node.textContent = text;
    node.hidden = !text;
    node.classList.toggle("work-error", failed);
  }

  function dateOf(value) {
    return value ? new Date(value).toLocaleString() : "";
  }

  function section(title, description) {
    const node = element("section", "work-section");
    node.append(element("h3", "", title));
    if (description) node.append(note(description));
    return node;
  }

  function details(title, child) {
    const node = element("details", "work-details");
    node.append(element("summary", "", title), child);
    return node;
  }

  function pill(label, tone = "") {
    return element("span", `work-pill ${tone}`, label);
  }

  function selectOptions(options) {
    return Object.entries(options).map(([value, label]) => [value, label]);
  }

  function field(name, label, options = {}) {
    const { type = "text", choices, value, required = false, multiple = false, hint, wide, placeholder } = options;
    const tag = choices ? "select" : type === "textarea" ? "textarea" : "input";
    const holder = element("label", `work-field ${wide || tag === "textarea" || multiple ? "span-two" : ""}`);
    const control = element(tag);
    holder.append(element("span", "", label), control);
    control.name = name;
    control.required = required;
    if (type === "checkbox") holder.classList.add("work-checkbox");
    if (tag === "input") control.type = type;
    if (tag === "textarea") control.rows = options.rows || 3;
    if (placeholder) control.placeholder = placeholder;
    if (options.maxLength) control.maxLength = options.maxLength;
    if (type === "number") {
      control.min = options.min ?? 1;
      if (options.max) control.max = options.max;
    }
    if (choices) {
      control.multiple = multiple;
      if (multiple) control.size = Math.min(5, Math.max(3, choices.length));
      for (const [key, title] of choices) {
        const option = element("option", "", title);
        option.value = key;
        option.selected = multiple ? (value || []).includes(key) : value === key;
        control.append(option);
      }
    } else if (type === "checkbox") {
      control.checked = Boolean(value);
    } else {
      control.value = Array.isArray(value) ? value.join("\n") : value ?? "";
    }
    if (options.lines) control.dataset.lines = "";
    if (hint) holder.append(element("small", "", hint));
    return holder;
  }

  function values(container) {
    const data = {};
    for (const control of container.querySelectorAll("[name]")) {
      if (control.multiple) data[control.name] = [...control.selectedOptions].map((option) => option.value);
      else if (control.type === "checkbox") data[control.name] = control.checked;
      else if (control.type === "number") data[control.name] = control.value ? Number(control.value) : null;
      else if (control.type === "date") data[control.name] = control.value || null;
      else if ("lines" in control.dataset) data[control.name] = control.value.split(/[,\n]/).map((line) => line.trim()).filter(Boolean);
      else data[control.name] = control.value;
    }
    return data;
  }

  function editor(fields) {
    const form = element("form", "work-form");
    const grid = element("div", "work-fields");
    grid.append(...fields);
    form.append(grid);
    return form;
  }

  function handleSubmit(ctx, form, label, action, success = "Saved.") {
    const submit = element("button", "", label);
    const message = status();
    submit.type = "submit";
    form.append(row(submit), message);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      submit.disabled = true;
      show(message, "Working…");
      try {
        await action();
        if (!ctx.signal.aborted && message.isConnected) show(message, success);
      } catch (error) {
        if (!ctx.signal.aborted) show(message, error.message, true);
      } finally {
        submit.disabled = false;
      }
    });
  }

  function optionsFrom(entries, label) {
    return entries.map((entry) => [entry.id, label(entry.data)]);
  }

  function recordCard(title, description, stateLabel) {
    const card = element("article", "work-card");
    const heading = element("div", "work-card-heading");
    heading.append(element("h4", "", title));
    if (stateLabel) heading.append(stateLabel);
    card.append(heading);
    if (description) card.append(note(description));
    return card;
  }

  let inboxScope = "topic";

  async function loadInbox(ctx, panel) {
    const controls = element("div", "work-actions");
    const scope = field("inbox_scope", "Research inbox", {
      choices: [["topic", "Current topic"], ["all", "All topics"]], value: ctx.id ? inboxScope : "all",
    });
    if (ctx.id) controls.append(scope);
    const onlyNew = field("only_new", "Show unread only", { type: "checkbox", value: true });
    controls.append(onlyNew);
    const watchesSection = section("Watched searches", "Choose Manual, Daily, or Weekly. Automatic checks run while the local app is on.");
    const notices = status();
    const watches = element("div", "work-stack");
    const feed = section("Papers from watched searches");
    const feedList = element("div", "work-stack");
    feed.append(feedList);
    watchesSection.append(controls, notices, watches);
    const history = section("Reading activity", "Opens and read markers follow the same paper across topics. Each URL has its own open count.");
    watchesSection.id = "watched-searches";
    feed.id = "watch-feed";
    history.id = "reading-activity";
    const historyList = element("div", "work-stack");
    const historySearch = field("history_query", "Find by title, DOI, or URL", { type: "search", maxLength: 4000 });
    const historyInput = historySearch.querySelector("input");
    const more = button("Load older activity", () => renderHistory(true));
    more.hidden = true;
    history.append(historySearch, historyList, row(more));
    panel.append(row(jump("watched-searches", "Watched searches"), jump("watch-feed", "New papers"),
      jump("reading-activity", "Reading activity")), watchesSection, feed, history);
    let nextOffset = 0;
    let historyVersion = 0;

    async function renderHistory(append = false) {
      const version = ++historyVersion;
      more.disabled = true;
      try {
        const offset = append ? nextOffset : 0;
        const query = historyInput.value.trim();
        const params = new URLSearchParams({ limit: "10", offset: String(offset), q: query });
        const { items: records } = await workflow(ctx, `library/activity?${params}`);
        if (ctx.signal.aborted || version !== historyVersion) return;
        if (!append) historyList.replaceChildren();
        if (!records.length && !append) {
          historyList.append(note(query ? "No reading activity matches this search."
            : "Open a paper link or mark a paper as read to start your reading history."));
        }
        for (const record of records) {
          const card = recordCard(record.title, [
            record.doi && `DOI ${record.doi}`, `Opened ${record.open_count}×`,
            record.read_at && `Marked read ${dateOf(record.read_at)}`,
          ].filter(Boolean).join(" · "));
          if (record.urls.length) {
            const urls = element("ul", "reading-urls");
            for (const visited of record.urls) {
              const li = element("li");
              const address = link(visited.url, visited.url);
              trackPaperLink(address, { url: visited.url, doi: record.doi });
              li.append(address, note(`${visited.open_count} ${visited.open_count === 1 ? "open" : "opens"} · Last ${dateOf(visited.last_opened_at)}`));
              urls.append(li);
            }
            card.append(urls);
          }
          historyList.append(card);
        }
        nextOffset = offset + records.length;
        more.hidden = records.length < 10;
      } catch (error) {
        if (!ctx.signal.aborted && version === historyVersion) historyList.replaceChildren(status(error.message));
      } finally {
        if (version === historyVersion) more.disabled = false;
      }
    }
    let historyTimer;
    historyInput.addEventListener("input", () => {
      window.clearTimeout(historyTimer);
      historyTimer = window.setTimeout(() => void renderHistory(), 200);
    });
    ctx.signal.addEventListener("abort", () => window.clearTimeout(historyTimer), { once: true });

    const scopeControl = scope.querySelector("select");
    const onlyNewControl = onlyNew.querySelector("input");
    let loadVersion = 0;

    async function renderFeed() {
      const version = ++loadVersion;
      const projectId = ctx.id && scopeControl.value === "topic" ? ctx.id : "";
      const params = new URLSearchParams(projectId ? { project_id: projectId } : {});
      try {
        const [saved, results] = await Promise.all([
          workflow(ctx, `watches?${params}`),
          workflow(ctx, `inbox?${params}&unread_only=${onlyNewControl.checked}`),
        ]);
        if (ctx.signal.aborted || version !== loadVersion) return;
        watches.replaceChildren();
        feedList.replaceChildren();
        for (const watch of saved.items) {
          const base = `projects/${watch.project_id}/watches/${watch.id}`;
          const project = state.projects.get(watch.project_id);
          const card = recordCard(watch.label, [project?.name,
            watch.filters.q === watch.label ? null : watch.filters.q, watch.filters.provider_names.join(", "),
          ].filter(Boolean).join(" · "), pill(`${watch.unread} unread`, watch.unread ? "positive" : ""));
          card.append(note(watch.last_success_at ? `Last successful check ${dateOf(watch.last_success_at)}` : "Waiting for first successful check"));
          const failures = watch.coverage.filter((source) => ["rate_limited", "failed", "unavailable"].includes(source.status));
          if (failures.length) card.append(note(`Last attempt ${dateOf(watch.last_attempt_at)} · ${failures.map((source) =>
            `${source.provider} ${source.status.replaceAll("_", " ")}`).join(", ")}`));
          const check = button("Check for new papers", async () => {
            check.disabled = true;
            show(notices, `Checking ${watch.label}…`);
            try {
              const run = await workflow(ctx, `${base}/refresh`, "POST");
              const incomplete = run.watch.coverage.some((source) => ["rate_limited", "failed", "unavailable"].includes(source.status));
              show(notices, `${run.added} new ${run.added === 1 ? "paper" : "papers"} found${incomplete ? " · Some sources were unavailable" : ""}.`);
              await renderFeed();
              void refreshWatchCounts();
              void refreshLibraryCount();
            } catch (error) {
              if (!ctx.signal.aborted) show(notices, error.message, true);
            } finally {
              check.disabled = false;
            }
          }, false);
          const schedule = editor([
            field("label", "Search label", { value: watch.label, maxLength: 120, required: true }),
            field("interval_hours", "Refresh frequency", { value: String(watch.interval_hours), choices: watchIntervals }),
          ]);
          handleSubmit(ctx, schedule, "Save schedule", async () => {
            const settings = values(schedule);
            await workflow(ctx, base, "PATCH", { ...settings, interval_hours: Number(settings.interval_hours) });
            show(notices, "Search settings saved.");
            await renderFeed();
          });
          const mark = button("Mark results seen", async () => {
            try {
              await workflow(ctx, `${base}/seen`, "POST", {});
              await renderFeed();
              void refreshWatchCounts();
            } catch (error) {
              show(notices, error.message, true);
            }
          });
          mark.disabled = !watch.unread;
          schedule.append(row(button("Remove watch", async () => {
            if (!window.confirm(`Remove the watch for “${watch.label}”?`)) return;
            try {
              await workflow(ctx, base, "DELETE");
              await renderFeed();
              void refreshWatchCounts();
            } catch (error) {
              show(notices, error.message, true);
            }
          })));
          card.append(row(check, mark), details("Label and schedule", schedule));
          watches.append(card);
        }
        if (!saved.items.length) {
          watches.append(note("In Papers, enter a query and choose Watch this search."));
        }
        if (!results.items.length) {
          feedList.append(note(onlyNewControl.checked ? "No unread papers in this view." : "No new results have been found yet."));
        }
        for (const entry of results.items) {
          const freshnessLabels = { recent: "Dated in the last 30 days", discovered: "New to your library", known: "Already in your library" };
          const card = recordCard(entry.paper.title, `${entry.project_name} · ${entry.label}`,
            pill(freshnessLabels[entry.freshness], entry.seen_at ? "" : "positive"));
          const origin = ctx.id ? { kind: "library", run_id: entry.paper.library_id } : null;
          // The paper card also offers the current topic’s shortlist and reading controls.
          const list = element("ol", "results");
          const item = paperCard(entry.paper, origin);
          item.querySelector("h3")?.remove();
          list.append(item);
          card.append(list);
          if (!entry.seen_at) {
            card.append(row(button("Mark seen", async () => {
              try {
                await workflow(ctx, `projects/${entry.project_id}/watches/${entry.watch_id}/seen`, "POST",
                  { library_id: Number(entry.paper.library_id) });
                await renderFeed();
                void refreshWatchCounts();
              } catch (error) {
                show(notices, error.message, true);
              }
            })));
          }
          feedList.append(card);
        }
      } catch (error) {
        if (!ctx.signal.aborted) show(notices, error.message, true);
      }
    }

    scopeControl.addEventListener("change", () => { inboxScope = scopeControl.value; void renderFeed(); });
    onlyNewControl.addEventListener("change", () => void renderFeed());
    document.addEventListener("academic-paper-activity", () => {
      void renderHistory();
      void renderFeed();
    }, { signal: ctx.signal });
    await Promise.all([renderFeed(), renderHistory()]);
  }

  const manuscriptStages = { outline: "Outline", drafting: "Drafting", review: "In review",
    ready: "Ready to submit", submitted: "Submitted", published: "Published" };
  const briefPresets = new Map();
  const outlinePresets = new Map();

  function browserRead(key) {
    try { return JSON.parse(localStorage.getItem(key)); } catch { return null; }
  }

  function browserWrite(key, value) {
    try {
      if (value === null) localStorage.removeItem(key);
      else localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // The server autosave can still work when browser storage is unavailable.
    }
  }

  function openWorkspace(projectId, tabId, draftId = "") {
    if (draftId) browserWrite(`academic-open-draft:${projectId}`, draftId);
    if (projectId !== selectedProjectId()) chooseTopic(projectId);
    selectView(document.getElementById(tabId), true);
  }

  function startBrief(projectId, preset) {
    briefPresets.set(projectId, preset);
    openWorkspace(projectId, "discover-tab");
  }

  window.startWorkspaceBrief = async (origin, paper, action) => {
    const projectId = selectedProjectId();
    if (!projectId) return;
    action.disabled = true;
    try {
      const saved = await request({ id: projectId }, "reading/from-source", "POST", { ...origin, paper_url: paper.url });
      if (selectedProjectId() === projectId) startBrief(projectId, { evidence: [saved.id], starting_point: paper.title });
    } catch (error) {
      action.textContent = "Try starting brief again";
      action.title = error.message;
    } finally {
      action.disabled = false;
    }
  };

  function assistantPanel(ctx, label, settings) {
    const root = element("div", "work-stack");
    const disclosure = details(label, root);
    disclosure.addEventListener("toggle", async () => {
      if (!disclosure.open || root.childElementCount) return;
      const loading = status("Checking configured models…");
      root.append(loading);
      try {
        const { items: providers } = await workflow(ctx, "assistant/providers");
        if (ctx.signal.aborted) return;
        const enabled = providers.filter((item) => item.available);
        if (!enabled.length) {
          root.replaceChildren(note("Configure a model and its API key in the local service to use the assistant."));
          return;
        }
        const form = editor([
          field("provider", "Model provider", { choices: enabled.map((item) => [item.id, `${item.label} · ${item.model}`]) }),
          field("question", "What should the assistant focus on?", { maxLength: 600, wide: true }),
        ]);
        const result = element("div", "work-stack");
        root.replaceChildren(note("Running this action sends the selected saved material to your chosen model provider."), form, result);
        handleSubmit(ctx, form, "Run assistant", async () => {
          const payload = await settings();
          const response = await workflow(ctx, `projects/${ctx.id}/assistant`, "POST", { ...payload, ...values(form) });
          if (ctx.signal.aborted) return;
          result.replaceChildren(note(`Suggestions for review · ${response.model}`));
          const sources = new Map(response.sources.map((source) => [source.id, source]));
          for (const idea of response.suggestions) {
            const card = element("article", "work-card");
            card.append(note(idea.text));
            const citations = idea.source_ids.map((key) => sources.get(key)).filter(Boolean);
            if (citations.length) card.append(row(...citations.map((source) =>
              source.url ? link(source.url, source.title) : pill(source.title))));
            result.append(card);
          }
          if (response.gaps.length) {
            const gaps = element("ul", "work-checklist");
            gaps.append(...response.gaps.map((gap) => element("li", "", gap)));
            result.append(element("strong", "", "Evidence still needed"), gaps);
          }
        }, "");
      } catch (error) {
        if (!ctx.signal.aborted) show(loading, error.message, true);
      }
    });
    return disclosure;
  }

  function issueAlerts(ctx, items) {
    if (!items.length) return null;
    const sectionNode = section("Special-issue updates");
    for (const alert of items) {
      const changes = Object.entries(alert.changes).map(([key, value]) =>
        `${key.replaceAll("_", " ")} · ${value.before || "unlisted"} → ${value.after || "unlisted"}`);
      const card = recordCard(alert.call.title, [alert.project_name, ...changes].join("\n"));
      const message = status();
      card.append(row(link(alert.call.source_url, "Official call"), button("Dismiss update", async () => {
        try {
          await workflow(ctx, `special-issue-alerts/${alert.id}/dismiss`, "POST");
          for (const entry of sectionNode.querySelectorAll("[data-alert-id]")) {
            if (entry.dataset.alertId === String(alert.id)) entry.remove();
          }
          sectionNode.hidden = !sectionNode.querySelector("[data-alert-id]");
        } catch (error) {
          if (!ctx.signal.aborted) show(message, error.message, true);
        }
      })), message);
      card.dataset.alertId = alert.id;
      sectionNode.append(card);
    }
    return sectionNode;
  }

  async function loadToday(ctx, panel) {
    const data = await workflow(ctx, "today");
    if (ctx.signal.aborted) return;
    const plan = section("Next manuscript actions");
    if (!data.manuscripts.length) plan.append(note("Create an outline in Manuscript to add your first writing task."));
    for (const draft of data.manuscripts) {
      const card = recordCard(draft.title, [draft.project_name, draft.next_action, draft.due && `Due ${draft.due}`]
        .filter(Boolean).join(" · "), pill(manuscriptStages[draft.stage] || draft.stage));
      card.append(row(button("Open this draft", () => openWorkspace(draft.project_id, "manuscript-tab", draft.id))));
      plan.append(card);
    }
    const grid = element("div", "today-grid");
    const reading = section("Today’s reading");
    if (!data.reading.length) reading.append(note("Set up a topic in Daily reading to see your progress here."));
    for (const today of data.reading) {
      const card = recordCard(today.name, `${today.read} of ${today.total} read today`);
      card.append(row(button("Open reading list", () => openWorkspace(today.project_id, "daily-tab"))));
      reading.append(card);
    }
    for (const [projectId, unread] of Object.entries(data.unread_by_topic)) {
      const project = state.projects.get(projectId);
      if (project) reading.append(row(button(`${project.name} · ${unread} new watched papers`,
        () => openWorkspace(projectId, "inbox-tab"))));
    }
    const deadlines = section("Deadlines in the next 30 days");
    if (!data.deadlines.length) deadlines.append(note("No upcoming calls or outstanding revisions in this window."));
    for (const deadline of data.deadlines) {
      const card = recordCard(deadline.title, [deadline.project_name, deadline.date, deadline.time, deadline.timezone]
        .filter(Boolean).join(" · "), pill(deadline.days_left < 0 ? "Overdue" : deadline.kind === "revision" ? "Revision" : "Call for papers"));
      card.append(row(button("Open submissions", () => openWorkspace(deadline.project_id, "submissions-tab"))));
      deadlines.append(card);
    }
    grid.append(reading, deadlines);
    const updates = issueAlerts(ctx, data.alerts);
    panel.append(plan, grid);
    if (updates) panel.append(updates);
    if (data.followed_journals?.length) {
      const followed = section("Followed journals");
      for (const journal of data.followed_journals) {
        const card = recordCard(journal.name, "", journal.unread ? pill(`${journal.unread} new`, "positive") : null);
        card.append(row(button("Open journal feed", () => window.openFollowedJournal(journal.id))));
        followed.append(card);
      }
      panel.append(followed);
    }
  }

  function specialIssueFinder(ctx, drafts, refreshSavedCalls) {
    const box = section("Find special issues");
    const journalPreset = state.journalCallFilter || "";
    delete state.journalCallFilter;
    const defaultPublisher = [["", "All publishers"], ["springer", "Springer Nature"], ["sage", "Sage"],
      ["taylor", "Taylor & Francis"], ["elsevier", "Elsevier"], ["dergipark", "DergiPark"]];
    const form = editor([
      field("q", "Call topic or keywords", { maxLength: 160, placeholder: "Energy forecasting" }),
      field("journal", "Journal name or ISSN", { maxLength: 160, value: journalPreset }),
      field("deadline_from", "Deadline from", { type: "date" }),
      field("deadline_to", "Deadline through", { type: "date" }),
      field("publisher", "Publisher", { choices: defaultPublisher }),
      field("open_only", "Open calls only", { type: "checkbox", value: true }),
    ]);
    const results = element("div", "work-stack");
    const output = status();
    let version = 0;
    async function find(refresh = false) {
      const messageId = ++version;
      const params = new URLSearchParams();
      for (const [key, value] of Object.entries(values(form))) {
        if (value !== null && value !== "") params.set(key, String(value));
      }
      if (refresh) params.set("refresh", "true");
      const index = await workflow(ctx, `special-issues?${params}`);
      if (ctx.signal.aborted || messageId !== version) return;
      renderCalls(index);
    }
    function renderCalls(index) {
      show(output, `${index.items.length} matching ${index.items.length === 1 ? "call" : "calls"}`);
      const labels = { checked: "Checked", partial: "Some calls unavailable", unavailable: "Unavailable", manual: "Open publisher listing" };
      const providers = row(...index.sources.map((source) => link(source.url, `${source.label} · ${labels[source.status]}`)));
      results.replaceChildren(providers);
      if (!index.items.length) results.append(note("Try broader keywords or check the official publisher listings."));
      for (const call of index.items) {
        const card = recordCard(call.title, [
          call.venue, call.issn, call.deadline ? `Manuscript deadline ${call.deadline}` : "Manuscript deadline unlisted",
          call.abstract_deadline && `Abstract due ${call.abstract_deadline}`,
        ].filter(Boolean).join(" · "), pill(opportunityStates[call.status] || call.status, call.status === "open" ? "positive" : ""));
        const meta = [call.article_types, call.fees, `${call.cached ? "Saved check" : "Checked"} ${dateOf(call.checked_at)}`];
        if (call.evidence) card.append(note(call.evidence));
        card.append(note(meta.filter(Boolean).join(" · ")));
        const actions = row(link(call.source_url, "Official call"));
        if (call.guidelines_url) actions.append(link(call.guidelines_url, "Author guidelines"));
        if (call.submission_url) actions.append(link(call.submission_url, "Submission portal"));
        card.append(actions);
        if (ctx.id) {
          const choose = field("draft", "Target manuscript", {
            choices: [["", "Save without a draft"], ...optionsFrom(drafts, (draft) => draft.title)],
          });
          const draftSelect = choose.querySelector("select");
          const saved = status();
          const targetAction = button("Save and watch this call", async () => {
            targetAction.disabled = true;
            try {
              const id = draftSelect.value;
              await workflow(ctx, `special-issues/${call.id}/save`, "POST", { project_id: ctx.id, draft_id: id });
              targetAction.textContent = "Saved and watched";
              if (id) openDraft.onclick = () => openWorkspace(ctx.id, "manuscript-tab", id);
              openDraft.hidden = !id;
              show(saved, id ? "The call is linked to this draft." : "Saved in this topic’s submissions.");
              try {
                await refreshSavedCalls();
              } catch {
                if (!ctx.signal.aborted) show(saved, "Call saved. Reopen Submissions to update the shortlist and calendar.", true);
              }
            } catch (error) {
              if (!ctx.signal.aborted) show(saved, error.message, true);
            } finally {
              targetAction.disabled = false;
            }
          });
          const openDraft = element("button", "secondary", "Open target draft");
          openDraft.type = "button";
          openDraft.hidden = true;
          card.append(choose, row(targetAction, openDraft), saved);
          if (drafts.length) card.append(assistantPanel(ctx, "Ask assistant about fit", () => {
            if (!draftSelect.value) throw new Error("Choose a draft for the fit review.");
            return { action: "call", draft_id: draftSelect.value, call_id: call.id };
          }));
        }
        results.append(card);
      }
    }
    handleSubmit(ctx, form, "Find special issues", () => find(), "");
    form.append(row(button("Next 90 days", () => {
      const now = new Date();
      form.elements.deadline_from.value = localReadingDay(Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC");
      now.setDate(now.getDate() + 90);
      form.elements.deadline_to.value = now.toISOString().slice(0, 10);
    }), button("Recheck publishers", async () => {
      try { await find(true); } catch (error) { if (!ctx.signal.aborted) show(output, error.message, true); }
    })));
    const verify = editor([field("url", "Official call URL", { type: "url", required: true, maxLength: 1500 })]);
    handleSubmit(ctx, verify, "Verify call", async () => {
      const messageId = ++version;
      const call = await workflow(ctx, "special-issues/verify", "POST", values(verify));
      if (!ctx.signal.aborted && messageId === version) renderCalls({ items: [call], sources: [] });
    });
    box.append(form, details("Verify an official call by URL", verify), output, results);
    if (journalPreset) void find().catch((error) => { if (!ctx.signal.aborted) show(output, error.message, true); });
    return box;
  }

  function evidenceTable(ctx, reading) {
    const root = section("Compare evidence", "Choose studies from this topic and compare the notes you recorded.");
    if (!reading.length) {
      root.append(note("Save a paper to the reading shortlist to start comparing evidence."));
      return root;
    }
    const picker = field("evidence_selection", "Studies to compare", {
      multiple: true, choices: optionsFrom(reading, (item) => item.paper.title),
      value: reading.slice(0, 4).map((entry) => entry.id),
    });
    const select = picker.querySelector("select");
    const selected = () => [...select.selectedOptions].map((item) => item.value);
    const wrapper = element("div", "evidence-scroll");
    wrapper.tabIndex = 0;
    wrapper.setAttribute("aria-label", "Evidence comparison");
    const fields = [["method", "Method"], ["dataset", "Dataset"], ["findings", "Findings"],
      ["limitations", "Limitations"], ["locator", "Source location"]];
    const render = () => {
      const table = element("table", "evidence-table");
      const head = element("thead");
      const rowNode = element("tr");
      for (const label of ["Study", ...fields.map(([, title]) => title)]) {
        const cell = element("th", "", label);
        cell.scope = "col";
        rowNode.append(cell);
      }
      head.append(rowNode);
      const body = element("tbody");
      for (const record of reading.filter((item) => selected().includes(item.id))) {
        const row = element("tr");
        const study = element("th");
        study.scope = "row";
        const paper = record.data.paper;
        const address = link(paper.url, paper.title);
        trackPaperLink(address, paper);
        study.append(address, note([paper.year, record.data.notes.status].filter(Boolean).join(" · ")));
        row.append(study, ...fields.map(([key]) => element("td", "", record.data.notes[key] || "—")));
        body.append(row);
      }
      table.append(head, body);
      wrapper.replaceChildren(table);
    };
    select.addEventListener("change", render);
    render();
    root.append(picker, wrapper, row(button("Start brief with selected studies", () => {
      const ids = selected().slice(0, 30);
      if (ids.length) startBrief(ctx.id, { evidence: ids });
    })), assistantPanel(ctx, "Ask assistant to compare studies", () => {
      const reading_ids = selected().slice(0, 12);
      if (!reading_ids.length) throw new Error("Select at least one study to compare.");
      return { action: "evidence", reading_ids };
    }));
    return root;
  }

  async function loadDiscovery(ctx, panel) {
    const controls = section("Publication trends");
    const project = state.projects.get(ctx.id);
    const [snapshots, reading, ideas] = await Promise.all([
      items(ctx, "discovery", 1), items(ctx, "reading", 250), items(ctx, "ideas"),
    ]);
    const snapshot = snapshots[0];
    const query = snapshot?.data.query || project?.research_question || project?.name || "";
    const fieldSelector = field("field", "OpenAlex field", { choices: [["", "All OpenAlex fields"]] });
    const form = editor([
      field("query", "Research keywords", { value: query.slice(0, 300), required: true, maxLength: 300 }),
      fieldSelector,
      field("include_preprints", "Include preprints in recent papers", { type: "checkbox", value: snapshot?.data.include_preprints }),
    ]);
    controls.append(form);
    const results = element("div", "work-stack");
    const refreshIdeas = element("div", "work-stack");
    const list = section("Reading shortlist", "Save papers from Discover, Papers, or Journals. Record what each source contributes.");
    const ideaSection = section("Research briefs", "Record the question, the data you can access, and evidence for and against it.");
    const readingList = element("div", "work-stack");
    list.id = "reading-shortlist";
    ideaSection.id = "research-questions";
    list.append(readingList);
    let comparison = evidenceTable(ctx, reading);
    panel.append(row(jump(list.id, "Reading shortlist"), jump(ideaSection.id, "Research briefs")), controls, results, list, comparison, ideaSection);
    fillFieldOptions(ctx, fieldSelector.querySelector("select"), snapshot?.data.field);
    if (snapshot) showDiscovery(ctx, results, snapshot);
    else results.append(note("Run discovery to compare two completed publication years and see the newest papers."));
    handleSubmit(ctx, form, "Run discovery", async () => {
      const latest = await request(ctx, "discover", "POST", values(form));
      if (!ctx.signal.aborted) showDiscovery(ctx, results, latest);
    });
    renderReading(ctx, readingList, reading);
    document.addEventListener("academic-shortlist-save", (event) => {
      const { projectId, item } = event.detail;
      if (projectId !== ctx.id || reading.some((entry) => entry.id === item.id)) return;
      if (!reading.length) readingList.replaceChildren();
      reading.unshift(item);
      readingList.prepend(readingEditor(ctx, item, reading));
      const updatedComparison = evidenceTable(ctx, reading);
      comparison.replaceWith(updatedComparison);
      comparison = updatedComparison;
      for (const select of ideaSection.querySelectorAll("select[name=evidence], select[name=counterevidence]")) {
        const option = element("option", "", item.data.paper.title);
        option.value = item.id;
        select.append(option);
      }
    }, { signal: ctx.signal });
    const suggestions = button("Suggest questions from notes", async () => {
      suggestions.disabled = true;
      try {
        const result = await request(ctx, "discover/gaps");
        if (ctx.signal.aborted) return;
        refreshIdeas.replaceChildren();
        for (const candidate of result.items) {
          const { source_title, source_url, locator, ...idea } = candidate;
          const card = recordCard(idea.question, idea.rationale, pill("Candidate"));
          card.append(row(link(source_url, source_title)));
          if (locator) card.append(note(locator));
          card.append(details("Develop this question", ideaEditor(ctx, reading, idea, null)));
          refreshIdeas.append(card);
        }
        if (!result.items.length) refreshIdeas.append(note("Add a documented limitation to a shortlist paper to get a candidate question."));
      } catch (error) {
        if (!ctx.signal.aborted) refreshIdeas.replaceChildren(status(error.message));
      } finally {
        suggestions.disabled = false;
      }
    });
    const preset = briefPresets.get(ctx.id);
    briefPresets.delete(ctx.id);
    const addBrief = details("Add a research brief", ideaEditor(ctx, reading, preset || {}));
    addBrief.open = Boolean(preset);
    ideaSection.append(row(suggestions), refreshIdeas, addBrief);
    if (preset) requestAnimationFrame(() => addBrief.querySelector("textarea")?.focus());
    for (const entry of ideas) {
      ideaSection.append(details(`${entry.data.question} · ${entry.data.status}`, ideaEditor(ctx, reading, entry.data, entry)));
    }
  }

  async function fillFieldOptions(ctx, select, selected) {
    try {
      const payload = await requestJson("/api/v1/journal-catalog/categories?provider=openalex&limit=100",
        { signal: ctx.signal }, "OpenAlex fields could not be loaded.");
      for (const entry of payload.categories || []) {
        if (!/^\d+$/.test(entry.id)) continue;
        const option = element("option", "", entry.label);
        option.value = entry.id;
        select.append(option);
      }
    } catch {
      // The seed query also works without a field filter.
    }
    if (selected && ![...select.options].some((option) => option.value === selected)) {
      const saved = element("option", "", `Saved OpenAlex field ${selected}`);
      saved.value = selected;
      select.append(saved);
    }
    select.value = selected || "";
  }

  function showDiscovery(ctx, root, snapshot) {
    const data = snapshot.data;
    const trends = section("Momentum by subtopic", data.method);
    const dates = data.periods.map((period) => `${period.from} to ${period.to} · ${period.total ?? "unavailable"} works`);
    trends.append(note(dates.join(" compared with ")), note(`${data.coverage} Indexed ${dateOf(data.retrieved_at)}.`));
    if (data.periods.some((period) => period.truncated)) {
      trends.append(note("The comparison is limited to the most common groups returned by OpenAlex."));
    }
    for (const [part, error] of Object.entries(data.errors)) {
      trends.append(status(`${part === "latest" ? "Recent papers" : `${part} period`} · ${error.message}`));
    }
    for (const trend of data.trends) {
      const movement = `${trend.change_pp > 0 ? "+" : ""}${trend.change_pp} pp`;
      const card = recordCard(trend.name,
        `${trend.baseline_count} → ${trend.recent_count} papers · ${trend.baseline_share}% → ${trend.recent_share}% of this corpus`,
        pill(movement, trend.change_pp > 0 ? "positive" : ""));
      if (trend.sparse) card.append(note("Small sample"));
      const samples = element("div", "work-stack");
      const open = button("View representative papers", async () => {
        open.disabled = true;
        samples.replaceChildren(status("Loading papers…"));
        try {
          const result = await request(ctx, `discover/${snapshot.id}/topics/${trend.id}`, "POST");
          if (!ctx.signal.aborted) samples.replaceChildren(discoveryPapers(result, "discovery-papers"));
        } catch (error) {
          if (!ctx.signal.aborted) samples.replaceChildren(status(error.message));
        } finally {
          open.disabled = false;
        }
      });
      card.append(row(open, button("Start brief from this trend", () => startBrief(ctx.id, {
        starting_point: `${trend.name} · OpenAlex trend checked ${dateOf(data.retrieved_at)}`,
      }))), samples);
      trends.append(card);
    }
    if (!data.trends.length) trends.append(note("No comparable subtopics were found for both years."));
    const recent = section("Recent papers", "Sorted by publication date using OpenAlex records.");
    recent.append(discoveryPapers(snapshot, "discovery"));
    root.replaceChildren(trends, recent);
  }

  function discoveryPapers(entry, kind) {
    if (entry.data.error) return status(entry.data.error.message);
    if (!entry.data.papers.length) return note("No linked papers were returned.");
    const list = element("ol", "results discovery-papers");
    for (const paper of entry.data.papers) {
      const dateLabel = [paper.publication_date, paper.work_type?.replaceAll("_", " ")].filter(Boolean).join(" · ");
      const item = paperCard(paper, { kind, run_id: entry.id });
      if (dateLabel) item.querySelector("article").prepend(pill(dateLabel));
      list.append(item);
    }
    return list;
  }

  function renderReading(ctx, root, records) {
    if (!records.length) root.append(note("Your shortlist is empty."));
    for (const entry of records) root.append(readingEditor(ctx, entry, records));
  }

  function readingEditor(ctx, entry, records) {
    const options = optionsFrom(records, (entry) => entry.paper.title);
    const { paper, notes } = entry.data;
    const form = editor([
      field("status", "Reading status", { choices: selectOptions(readingStates), value: notes.status }),
      field("locator", "Page, section, or figure", { value: notes.locator }),
      field("design", "Study design", { value: notes.design }),
      field("population", "Region or population", { value: notes.population }),
      field("dataset", "Dataset", { value: notes.dataset }),
      field("method", "Methods", { type: "textarea", value: notes.method }),
      field("findings", "Findings", { type: "textarea", value: notes.findings }),
      field("limitations", "Documented limitations", { type: "textarea", value: notes.limitations }),
      field("conflicts", "Other saved papers with conflicting evidence", {
        choices: options.filter(([value]) => value !== entry.id), multiple: true, value: notes.conflicts,
      }),
    ]);
    handleSubmit(ctx, form, "Save reading notes", async () => {
      await save(ctx, "reading", values(form), entry);
      refreshView();
    });
    const body = element("div", "work-stack");
    const paperLink = link(paper.url, "Open paper");
    body.append(row(paperLink, paperActivityControls(paper, paperLink), button("Develop a research brief", () => startBrief(ctx.id, {
      starting_point: paper.title, rationale: notes.limitations, evidence: [entry.id], counterevidence: notes.conflicts,
    }))), form);
    return details(`${paper.title} · ${readingStates[notes.status]}`, body);
  }

  function ideaEditor(ctx, reading, data, entry) {
    const sources = optionsFrom(reading, (value) => value.paper.title);
    const form = editor([
      field("question", "Research question", { type: "textarea", value: data.question, required: true, maxLength: 1000 }),
      field("rationale", "Gap or motivation", { type: "textarea", value: data.rationale }),
      field("data_source", "Feasible data source", { value: data.data_source }),
      field("method", "Proposed method", { value: data.method }),
      field("data_access", "Data access", { value: data.data_access, choices: [
        ["to_check", "To verify"], ["confirmed", "Access confirmed"], ["blocked", "Access blocked"],
      ] }),
      field("constraints", "Feasibility and constraints", { type: "textarea", value: data.constraints, maxLength: 2000 }),
      field("next_step", "Next investigation step", { value: data.next_step, maxLength: 750 }),
      field("starting_point", "Starting paper or trend", { value: data.starting_point, maxLength: 1000 }),
      field("status", "Review status", {
        choices: [["candidate", "Candidate"], ["reviewed", "Reviewed"], ["selected", "Selected for this topic"]],
        value: data.status,
      }),
      field("evidence", "Supporting papers", { choices: sources, multiple: true, value: data.evidence }),
      field("counterevidence", "Challenging or conflicting papers", { choices: sources, multiple: true, value: data.counterevidence }),
    ]);
    handleSubmit(ctx, form, "Save research brief", async () => {
      await save(ctx, "ideas", values(form), entry);
      refreshView();
    });
    const block = element("div", "work-stack");
    block.append(form);
    if (entry) {
      block.append(row(button("Start manuscript from this brief", () => {
        outlinePresets.set(ctx.id, entry);
        openWorkspace(ctx.id, "manuscript-tab");
      })), assistantPanel(ctx, "Ask assistant about this brief", () => ({ action: "brief", idea_id: entry.id })));
    }
    return block;
  }

  const submissionDefaults = {
    title: "", venue: "", kind: "regular", source_url: "", submission_url: "", guidelines_url: "",
    scope: "", article_types: "", issn: "", status: "unverified", evidence: "", opens: null,
    deadline: null, deadline_time: "", timezone: "", fees: "", fees_url: "", index_name: "",
    index_year: null, index_url: "", verify_from_source: false,
  };

  function editableSubmission(data) {
    return Object.fromEntries(Object.entries(submissionDefaults).map(([key, value]) => [key, data[key] ?? value]));
  }

  async function loadSubmissions(ctx, panel) {
    const { items: deadlines } = await workflow(ctx, "submission-calendar");
    const calendar = section("Submission calendar");
    const scope = field("deadline_scope", "Show deadlines for", {
      choices: [["", "All topics"], ...(ctx.id ? [[ctx.id, "Current topic"]] : [])],
    });
    const calendarList = element("div", "work-stack");
    const exportLink = link("/api/v1/submission-calendar/export", "Download calendar reminders (.ics)");
    exportLink.removeAttribute("target");
    const scopeControl = scope.querySelector("select");
    const showDeadlines = () => {
      const entries = deadlines.filter((item) => !scopeControl.value || item.project_id === scopeControl.value);
      exportLink.href = "/api/v1/submission-calendar/export"
        + (scopeControl.value ? `?project_id=${encodeURIComponent(scopeControl.value)}` : "");
      calendarList.replaceChildren();
      if (!entries.length) calendarList.append(note("Verified calls and revision deadlines will appear here."));
      for (const item of entries) {
        const urgency = item.days_left < 0 ? "Overdue"
          : item.days_left === 0 ? "Due today"
          : item.days_left <= 7 ? `Due in ${item.days_left} ${item.days_left === 1 ? "day" : "days"}`
          : item.kind === "revision" ? "Revision" : "Call for papers";
        const badge = pill(urgency);
        if (item.days_left <= 7) badge.classList.add("deadline-urgent");
        const card = recordCard(item.title, [
          item.project_name, item.date, item.time, item.timezone, item.needs_recheck && "Recheck official deadline",
        ].filter(Boolean).join(" · "), badge);
        if (item.source_url) card.append(row(link(item.source_url, "Official page")));
        calendarList.append(card);
      }
    };
    scopeControl.addEventListener("change", showDeadlines);
    calendar.append(row(scope, exportLink), calendarList);
    showDeadlines();
    const drafts = ctx.id ? await items(ctx, "manuscripts") : [];
    const finder = element("div");
    panel.append(finder);
    const { items: updates } = await workflow(ctx, `special-issue-alerts${ctx.id ? `?project_id=${ctx.id}` : ""}`);
    const alerts = issueAlerts(ctx, updates);
    if (alerts) panel.append(alerts);
    panel.append(calendar);
    if (!ctx.id) {
      finder.append(specialIssueFinder(ctx, drafts));
      panel.append(section("Choose a topic", "Select a topic to shortlist venues or track a manuscript."));
      return;
    }
    const [saved, tracking] = await Promise.all([
      items(ctx, "submissions"), items(ctx, "submission-tracking"),
    ]);
    const tracker = section("Manuscript submissions", "Log editorial decisions, reviewer comments, and revision deadlines.");
    tracker.append(details("Track a submission", trackingEditor(ctx, {}, null, drafts, saved)));
    for (const attempt of tracking) {
      const data = attempt.data;
      const card = recordCard(data.title, [
        drafts.find((draft) => draft.id === data.manuscript_id)?.data.title,
        saved.find((entry) => entry.id === data.opportunity_id)?.data.title,
        data.submitted_on && `Submitted ${data.submitted_on}`,
        data.status === "revision_requested" && data.revision_due && `Revision due ${data.revision_due}`,
        data.reference,
      ].filter(Boolean).join(" · "), pill(submissionStates[data.status], data.status === "accepted" ? "positive" : ""));
      card.append(details("Edit submission", trackingEditor(ctx, data, attempt, drafts, saved)));
      const history = element("div", "work-stack");
      const disclosure = details("Submission history", history);
      disclosure.addEventListener("toggle", async () => {
        if (!disclosure.open || history.childElementCount) return;
        try {
          const { items: versions } = await request(ctx, `submission-tracking/${attempt.id}/history`);
          for (const version of versions) {
            const prior = version.data;
            history.append(recordCard(submissionStates[prior.status], [
              dateOf(version.updated_at), prior.revision_due && `Revision deadline ${prior.revision_due}`,
              prior.reviewer_comments, prior.notes,
            ].filter(Boolean).join("\n")));
          }
        } catch (error) {
          if (!ctx.signal.aborted) history.replaceChildren(status(error.message));
        }
      });
      card.append(disclosure);
      tracker.append(card);
    }
    panel.append(tracker);
    const project = state.projects.get(ctx.id);
    const find = section("Find journals and calls", "Find journals that publish on this topic and check supported official pages for open submissions.");
    const form = editor([field("query", "Topic or keywords", {
      value: (project?.name || "").slice(0, 160), required: true, wide: true, maxLength: 160,
    })]);
    const results = element("div", "work-stack");
    find.append(form, results);
    handleSubmit(ctx, form, "Find venues", async () => {
      const response = await request(ctx, `submission-search?q=${encodeURIComponent(values(form).query)}`);
      if (ctx.signal.aborted) return;
      const portals = row(...response.sources.map((source) => link(source.url, source.name)));
      results.replaceChildren(portals);
      if (response.error) results.append(status(response.error));
      else if (!response.items.length) results.append(note("No related venues were found in the publication sample."));
      for (const candidate of response.items) {
        const description = [candidate.scope, candidate.sample_count && `${candidate.sample_count} papers in this OpenAlex sample`].filter(Boolean).join(" · ");
        const card = recordCard(candidate.title, description,
          pill(opportunityStates[candidate.status], candidate.status === "open" ? "positive" : ""));
        card.append(note(candidate.deadline ? `Deadline ${candidate.deadline}` : "Deadline not provided"));
        if (candidate.evidence) card.append(note(candidate.evidence));
        const add = button("Add to shortlist", async () => {
          add.disabled = true;
          try {
            const candidateData = editableSubmission({
              ...candidate, status: "unverified", verify_from_source: candidate.verification === "publisher_page",
            });
            await save(ctx, "submissions", candidateData);
            if (!ctx.signal.aborted) add.textContent = "Added to shortlist";
            await refreshSubmissionList();
          } catch (error) {
            add.textContent = "Retry adding";
            add.title = error.message;
            add.disabled = false;
          }
        }, false);
        const actions = row();
        if (candidate.metadata_url) actions.append(link(candidate.metadata_url, "OpenAlex record"));
        if (candidate.source_url) actions.append(link(candidate.source_url, "Official page"), add);
        if (!candidate.source_url) card.append(note("Add the publisher’s URL to shortlist this venue."));
        card.append(actions);
        results.append(card);
      }
    });
    const shortlist = section("Submission shortlist", "Keep separate entries for regular submissions and individual special issues.");
    const filterField = field("status_filter", "Filter by status", {
      choices: [["", "All statuses"], ...selectOptions(opportunityStates)],
    });
    const filter = filterField.querySelector("select");
    const cards = element("div", "work-stack");
    let current = saved;
    function showShortlist() {
      const filtered = current.filter((entry) => !filter.value || filter.value === entry.display_status);
      cards.replaceChildren(...filtered.map((entry) => opportunityCard(ctx, entry, refreshSubmissionList)));
      if (!filtered.length) cards.append(note("No entries match this view."));
    }
    async function refreshSubmissionList() {
      const [submissions, updated] = await Promise.all([items(ctx, "submissions"), workflow(ctx, "submission-calendar")]);
      if (ctx.signal.aborted) return;
      current = submissions;
      showShortlist();
      for (const select of tracker.querySelectorAll('select[name="opportunity_id"]')) {
        const selected = select.value;
        select.replaceChildren(select.options[0], ...optionsFrom(current, (item) => item.title)
          .map(([id, title]) => new Option(title, id)));
        select.value = selected;
      }
      deadlines.splice(0, deadlines.length, ...updated.items);
      showDeadlines();
    }
    filter.addEventListener("change", showShortlist);
    shortlist.append(filterField, details("Add an official submission link", submissionEditor(ctx, {}, null, refreshSubmissionList)), cards);
    showShortlist();
    panel.append(find, shortlist);
    finder.append(specialIssueFinder(ctx, drafts, refreshSubmissionList));
  }

  function trackingEditor(ctx, data, entry, drafts, opportunities) {
    const form = editor([
      field("title", "Submission title", { value: data.title, required: true, maxLength: 280 }),
      field("status", "Submission status", { value: data.status, choices: selectOptions(submissionStates) }),
      field("manuscript_id", "Manuscript", { value: data.manuscript_id,
        choices: [["", "Choose if saved in this topic"], ...optionsFrom(drafts, (record) => record.title)] }),
      field("opportunity_id", "Journal or call", { value: data.opportunity_id,
        choices: [["", "Choose if shortlisted"], ...optionsFrom(opportunities, (record) => record.title)] }),
      field("submitted_on", "Submitted on", { type: "date", value: data.submitted_on }),
      field("revision_due", "Revision deadline", { type: "date", value: data.revision_due }),
      field("reference", "Editorial reference or submission ID", { value: data.reference, maxLength: 350 }),
      field("reviewer_comments", "Reviewer comments", { type: "textarea", value: data.reviewer_comments, maxLength: 16000 }),
      field("notes", "Version or decision notes", { type: "textarea", value: data.notes, maxLength: 5000 }),
    ]);
    handleSubmit(ctx, form, "Save submission", async () => {
      await save(ctx, "submission-tracking", values(form), entry);
      refreshView("Submission saved.");
    });
    return form;
  }

  function opportunityCard(ctx, entry, refreshList) {
    const data = entry.data;
    const state = entry.display_status;
    const info = [opportunityKinds[data.kind], data.venue, data.issn && `ISSN ${data.issn}`].filter(Boolean).join(" · ");
    const card = recordCard(data.title, info, pill(opportunityStates[state], state === "open" ? "positive" : ""));
    const deadline = data.deadline
      ? `${data.deadline} ${data.deadline_time || ""} ${data.timezone || ""}`.trim()
      : data.kind === "regular" && state === "open" ? "No deadline listed" : "Deadline unconfirmed";
    card.append(note([deadline, data.article_types, data.fees || "Fees unconfirmed"].filter(Boolean).join(" · ")));
    if (data.scope) card.append(note(data.scope));
    if (data.checked_at) card.append(note(
      `${data.verification === "researcher" ? "Researcher check" : "Publisher check"} · ${dateOf(data.checked_at)}${data.evidence ? ` · ${data.evidence}` : ""}`
    ));
    if (entry.needs_recheck && state !== "closed") card.append(pill("Status needs recheck"));
    if (data.index_name) card.append(row(link(data.index_url, `${data.index_name} · ${data.index_year}`)));
    if (data.verification_error) card.append(status(data.verification_error));
    const actions = row(link(data.source_url, "Official page"));
    if (data.submission_url) actions.append(link(data.submission_url, "Submission portal"));
    if (data.guidelines_url) actions.append(link(data.guidelines_url, "Author guidelines"));
    if (data.fees_url) actions.append(link(data.fees_url, "Fee policy"));
    const checkStatus = status();
    const check = button("Recheck official page", async () => {
      check.disabled = true;
      show(checkStatus, "Checking the publisher page…");
      try {
        await request(ctx, `submissions/${entry.id}/verify`, "POST");
        await refreshList();
      } catch (error) {
        if (!ctx.signal.aborted) show(checkStatus, error.message, true);
      } finally {
        check.disabled = false;
      }
    });
    actions.append(check);
    card.append(actions, checkStatus, details("Edit opportunity", submissionEditor(ctx, data, entry, refreshList)));
    const history = element("div", "work-stack");
    const disclosure = details("Verification history", history);
    disclosure.addEventListener("toggle", async () => {
      if (!disclosure.open || history.childElementCount) return;
      try {
        const { items: versions } = await request(ctx, `submissions/${entry.id}/history`);
        for (const version of versions) {
          const old = version.data;
          history.append(note([`Version ${version.revision}`, dateOf(version.updated_at), opportunityStates[old.status],
            old.deadline, old.evidence, old.verification_error].filter(Boolean).join(" · ")));
        }
      } catch (error) {
        if (!ctx.signal.aborted) history.replaceChildren(status(error.message));
      }
    });
    card.append(disclosure);
    return card;
  }

  function submissionEditor(ctx, data, entry, refreshList) {
    const current = editableSubmission(data);
    const form = editor([
      field("title", "Opportunity title", { value: current.title, required: true }),
      field("venue", "Journal or venue", { value: current.venue }),
      field("kind", "Submission route", { value: current.kind, choices: selectOptions(opportunityKinds) }),
      field("issn", "ISSN", { value: current.issn, placeholder: "1234-567X" }),
      field("source_url", "Official source URL", { type: "url", value: current.source_url, required: true }),
      field("submission_url", "Submission portal URL", { type: "url", value: current.submission_url }),
      field("guidelines_url", "Author guidelines URL", { type: "url", value: current.guidelines_url }),
      field("article_types", "Accepted article types", { value: current.article_types }),
      field("scope", "Aims and scope", { type: "textarea", value: current.scope }),
      field("status", "Status observed on the official page", { choices: selectOptions({ unverified: "Unverified", ...opportunityStates }), value: current.status }),
      field("verify_from_source", "Check supported publisher automatically", { type: "checkbox" }),
      field("evidence", "Wording that confirms the status", { type: "textarea", value: current.evidence }),
      field("opens", "Opening date", { type: "date", value: current.opens }),
      field("deadline", "Deadline", { type: "date", value: current.deadline }),
      field("deadline_time", "Published closing time", { type: "time", value: current.deadline_time }),
      field("timezone", "Published time zone", { value: current.timezone, placeholder: "Europe/Istanbul" }),
      field("fees", "Published fees", { value: current.fees }),
      field("fees_url", "Official fee page URL", { type: "url", value: current.fees_url }),
      field("index_name", "Index", { value: current.index_name }),
      field("index_year", "Index coverage year", { type: "number", value: current.index_year, min: 1800, max: 2200 }),
      field("index_url", "Official index record URL", { type: "url", value: current.index_url }),
    ]);
    handleSubmit(ctx, form, "Save opportunity", async () => {
      await save(ctx, "submissions", values(form), entry);
      await refreshList();
      if (!entry) form.reset();
    });
    return form;
  }

  async function loadManuscript(ctx, panel) {
    const [drafts, reading, ideas, submissions] = await Promise.all([
      items(ctx, "manuscripts"), items(ctx, "reading", 250), items(ctx, "ideas"), items(ctx, "submissions"),
    ]);
    if (ctx.signal.aborted) return;
    const references = optionsFrom(reading, (data) => data.paper.title);
    const questions = [["", "Choose a saved question"], ...optionsFrom(ideas, (data) => data.question)];
    const targets = [["", "Choose a shortlisted venue"], ...optionsFrom(submissions, (data) => data.title)];
    const list = section("Drafts");
    if (!drafts.length) list.append(note("Start with an outline for your article type."));
    const editPane = element("div", "work-stack");
    const openKey = `academic-open-draft:${ctx.id}`;
    const draftStatus = status();
    async function openDraft(draft, moveFocus = false) {
      const token = Symbol();
      editPane.openToken = token;
      browserWrite(openKey, draft.id);
      show(draftStatus, "Loading draft…");
      try {
        const { item: buffer } = await request(ctx, `manuscripts/${draft.id}/autosave`);
        if (ctx.signal.aborted || editPane.openToken !== token) return;
        show(draftStatus, "");
        showDraft(ctx, editPane, draft, references, questions, targets, submissions, ideas, buffer);
        if (moveFocus) editPane.querySelector("h3")?.scrollIntoView({ block: "start" });
      } catch (error) {
        if (!ctx.signal.aborted && editPane.openToken === token) show(draftStatus, error.message, true);
      }
    }
    const preset = outlinePresets.get(ctx.id);
    outlinePresets.delete(ctx.id);
    const form = editor([
      field("title", "Working title", { required: true, value: preset?.data.question }),
      field("article_type", "Article type", { choices: selectOptions(manuscriptKinds) }),
      field("idea_id", "Research question", { choices: questions, value: preset?.id }),
      field("submission_id", "Target submission route", { choices: targets }),
    ]);
    const newDraft = details("Create an outline", form);
    newDraft.open = !drafts.length || Boolean(preset);
    handleSubmit(ctx, form, "Create outline", async () => {
      const draft = await save(ctx, "manuscripts", values(form));
      browserWrite(openKey, draft.id);
      refreshView("Outline created.");
    });
    list.append(newDraft);
    for (const draft of drafts) {
      const card = recordCard(draft.data.title, `${manuscriptKinds[draft.data.article_type]} · Version ${draft.revision}`);
      card.append(row(button("Open draft", () => openDraft(draft, true))));
      list.append(card);
    }
    panel.append(list, draftStatus, editPane);
    const resume = drafts.find((draft) => draft.id === browserRead(openKey)) || drafts[0];
    if (resume && !preset) await openDraft(resume);
  }

  function claimFields(claim, headings, references) {
    const box = element("fieldset", "claim-fields");
    box.append(element("legend", "", "Claim"),
      field("section", "Draft section", { choices: headings, value: claim.section }),
      field("locator", "Page, section, or figure", { value: claim.locator }),
      field("text", "Claim", { type: "textarea", value: claim.text, required: true }),
      field("references", "Reading shortlist references", { choices: references, value: claim.references, multiple: true }),
      field("review", "Evidence review", { choices: [["unreviewed", "Unreviewed"], ["supported", "Supported"],
        ["mixed", "Mixed evidence"], ["needs_evidence", "Needs evidence"]], value: claim.review }),
      row(button("Remove claim", () => {
        box.remove();
        document.querySelector("#draft-editor")?.dispatchEvent(new Event("input"));
      })),
    );
    return box;
  }

  function showDraft(ctx, root, draft, references, questions, targets, submissions, ideas, buffer, restored) {
    const recoveryKey = `academic-draft-buffer:${ctx.id}:${draft.id}`;
    const focusKey = `academic-draft-section:${ctx.id}:${draft.id}`;
    const restoredBuffer = buffer?.base_revision === draft.revision ? buffer : null;
    let bufferVersion = restoredBuffer?.version || 0;
    const local = browserRead(recoveryKey);
    const useLocal = local?.revision === draft.revision && local?.version === bufferVersion;
    const data = restored || (useLocal ? local.data : null) || restoredBuffer?.data || draft.data;
    const inline = { ...(data.inline_citations || {}) };
    const draftForm = editor([
      field("title", "Working title", { value: data.title, required: true }),
      field("article_type", "Article type", { choices: selectOptions(manuscriptKinds), value: data.article_type }),
      field("idea_id", "Research question", { choices: questions, value: data.idea_id }),
      field("submission_id", "Target submission route", { choices: targets, value: data.submission_id }),
      field("stage", "Manuscript stage", { choices: selectOptions(manuscriptStages), value: data.stage }),
      field("next_action", "Next action", { value: data.next_action, maxLength: 350 }),
      field("action_due", "Next action due", { type: "date", value: data.action_due }),
    ]);
    draftForm.id = "draft-editor";
    const header = draftForm.firstElementChild;
    const target = submissions.find((entry) => entry.id === data.submission_id)?.data;
    const idea = ideas.find((entry) => entry.id === data.idea_id)?.data;
    const workingPlan = idea ? [idea.question, idea.method && `Method · ${idea.method}`,
      idea.data_source && `Data · ${idea.data_source}`].filter(Boolean).join("\n") : "";
    if (workingPlan) draftForm.append(details("Research question and study plan", note(workingPlan)));
    const sectionFields = element("div", "work-stack");
    const textareas = new Map();
    for (const part of data.sections) {
      const area = field(part.heading, part.heading, { type: "textarea", value: part.text, rows: 6 });
      const input = area.querySelector("textarea");
      textareas.set(part.heading, input);
      input.addEventListener("focus", () => browserWrite(focusKey, part.heading));
      sectionFields.append(area);
    }
    const claimList = element("div", "work-stack");
    const headings = data.sections.map((part) => [part.heading, part.heading]);
    for (const claim of data.claims) claimList.append(claimFields(claim, headings, references));
    const claims = element("div", "work-stack");
    claims.append(element("h4", "", "Claims and evidence"), claimList,
      row(button("Add claim", () => {
        const entry = claimFields({}, headings, references);
        claimList.append(entry);
        entry.querySelector("textarea").focus();
        queueDraft();
      })));
    const requirements = element("div", "work-fields");
    const req = data.requirements;
    requirements.append(
      field("guideline_url", "Official author guidelines URL", { type: "url", value: req.guideline_url || target?.guidelines_url, wide: true }),
      field("word_limit", "Main text word limit", { type: "number", value: req.word_limit }),
      field("abstract_limit", "Abstract word limit", { type: "number", value: req.abstract_limit }),
      field("abstract_headings", "Required abstract headings", { type: "textarea", value: req.abstract_headings, lines: true }),
      field("declarations_required", "Required declarations", { type: "textarea", value: req.declarations_required, lines: true }),
      field("declarations_done", "Declarations reviewed", { type: "textarea", value: req.declarations_done, lines: true }),
      field("reporting_guideline", "Applicable reporting guideline", { value: req.reporting_guideline }),
      field("reporting_url", "Reporting guideline URL", { type: "url", value: req.reporting_url }),
      field("reporting_checked", "Reporting checklist reviewed", { type: "checkbox", value: req.reporting_checked }),
    );
    const citationField = field("citation_source", "Cite a shortlisted paper", {
      choices: [["", "Select a paper"], ...references],
    });
    const citationSection = field("citation_section", "Section to cite in", {
      choices: headings, value: browserRead(focusKey) || headings[0]?.[0],
    });
    const citationList = element("div", "work-stack");
    const renderCitations = () => {
      const labels = new Map(references);
      const cited = Object.entries(inline).filter(([key]) =>
        [...textareas.values()].some((input) => input.value.includes(`[@${key}]`)));
      citationList.replaceChildren(...cited.map(([key, id]) => note(`${key} · ${labels.get(id) || "Saved reference"}`)));
    };
    const citationTools = row(citationField, citationSection, button("Insert citation", () => {
      const id = citationField.querySelector("select").value;
      const input = textareas.get(citationSection.querySelector("select").value);
      if (!id || !input) return;
      let key = Object.keys(inline).find((name) => inline[name] === id);
      if (!key) {
        let num = 1;
        while (inline[`ref${num}`]) num++;
        key = `ref${num}`;
        inline[key] = id;
      }
      input.setRangeText(` [@${key}]`, input.selectionStart, input.selectionEnd, "end");
      input.focus();
      queueDraft();
    }));
    renderCitations();
    draftForm.append(citationTools, citationList, sectionFields, claims, details("Target journal requirements", requirements));
    function collect() {
      const fields = values(sectionFields);
      return {
        ...values(header), sections: data.sections.map((part) => ({ heading: part.heading, text: fields[part.heading] })),
        claims: [...claimList.children].map(values), requirements: values(requirements), inline_citations: inline,
      };
    }
    const autosaveStatus = status(restoredBuffer ? "Autosave restored." : "");
    let queued = null;
    let inFlight = null;
    let timer;
    function queueDraft(event) {
      if (event?.target?.name?.startsWith("citation_")) return;
      renderCitations();
      queued = JSON.parse(JSON.stringify(collect()));
      browserWrite(recoveryKey, { revision: draft.revision, version: bufferVersion, data: queued });
      show(autosaveStatus, "Saving changes…");
      window.clearTimeout(timer);
      timer = window.setTimeout(() => { void flushDraft().catch(() => {}); }, 650);
    }
    async function flushDraft() {
      window.clearTimeout(timer);
      while (inFlight || queued) {
        if (!inFlight) {
          const payload = queued;
          queued = null;
          inFlight = request({ id: ctx.id }, `manuscripts/${draft.id}/autosave`, "PUT", {
            revision: draft.revision, autosave_version: bufferVersion, data: payload,
          }).then((saved) => {
            bufferVersion = saved.version;
            const browserCopy = browserRead(recoveryKey);
            if (browserCopy?.revision === draft.revision && JSON.stringify(browserCopy.data) === JSON.stringify(queued || payload)) {
              browserWrite(recoveryKey, queued ? { revision: draft.revision, version: bufferVersion, data: queued } : null);
            }
            show(autosaveStatus, queued ? "Saving changes…" : "Autosaved locally.");
          }).catch((error) => {
            queued ||= payload;
            show(autosaveStatus, `Browser copy retained. ${error.message}`, true);
            throw error;
          }).finally(() => { inFlight = null; });
        }
        await inFlight;
      }
    }
    draftForm.addEventListener("input", queueDraft);
    draftForm.addEventListener("change", (event) => {
      if (event.target.matches("select,input[type=checkbox],input[type=date]")) queueDraft(event);
    });
    const checks = section("Draft review");
    checks.id = "draft-review";
    const reviewStatus = status();
    const issueList = element("ul", "work-checklist");
    checks.append(reviewStatus, issueList);
    async function displayReview(entry) {
      const report = await request(ctx, `manuscripts/${entry.id}/review`);
      if (ctx.signal.aborted) return;
      show(reviewStatus, `${report.word_count} main-text words · ${report.abstract_words} abstract words · ${report.issues.length} review items`);
      issueList.replaceChildren(...report.issues.map((issue) => {
        const line = element("li", "", [issue.section, issue.message, issue.claim].filter(Boolean).join(" · "));
        if (textareas.has(issue.section)) line.append(row(button("Go to section", () => textareas.get(issue.section).focus())));
        return line;
      }));
      checks.querySelector(".draft-guideline")?.remove();
      if (report.guideline_url) {
        const guideline = row(link(report.guideline_url, "Official author guidelines"));
        guideline.classList.add("draft-guideline");
        checks.append(guideline);
      }
    }
    handleSubmit(ctx, draftForm, "Save version and review", async () => {
      await flushDraft();
      await request(ctx, `manuscripts/${draft.id}`, "PUT", {
        revision: draft.revision, autosave_version: bufferVersion, data: collect(),
      });
      browserWrite(recoveryKey, null);
      refreshView("Draft version saved.");
    });
    const editorSection = section("Draft editor");
    const exports = row(
      download(ctx, `manuscripts/${draft.id}/export`, "Export outline and review"),
      download(ctx, `manuscripts/${draft.id}/export?format=bibtex`, "BibTeX"),
      download(ctx, `manuscripts/${draft.id}/export?format=ris`, "RIS"),
      button("Download Word", async () => {
        try {
          await flushDraft();
          window.location.href = route(ctx.id, `manuscripts/${draft.id}/export?format=docx`);
        } catch (error) {
          show(autosaveStatus, error.message, true);
        }
      }),
      jump(checks.id, "Go to draft review")
    );
    const history = element("div", "work-stack");
    const revisionHistory = details("Version history", history);
    revisionHistory.addEventListener("toggle", async () => {
      if (!revisionHistory.open || history.childElementCount) return;
      try {
        const { items: versions } = await request(ctx, `manuscripts/${draft.id}/history`);
        for (const version of versions) {
          const card = recordCard(`Version ${version.revision}`, dateOf(version.updated_at));
          const preview = element("div", "work-stack");
          for (const part of version.data.sections) if (part.text) preview.append(element("strong", "", part.heading), note(part.text));
          card.append(details("Read version", preview));
          if (version.revision !== draft.revision) {
            card.append(row(button("Use as a new draft version", () => {
              showDraft(ctx, root, draft, references, questions, targets, submissions, ideas,
                { base_revision: draft.revision, version: bufferVersion, data: collect() }, version.data);
            })));
          }
          history.append(card);
        }
      } catch (error) {
        if (!ctx.signal.aborted) history.replaceChildren(status(error.message));
      }
    });
    const lastSection = browserRead(focusKey);
    if (textareas.has(lastSection)) exports.append(button(`Resume ${lastSection}`, () => textareas.get(lastSection).focus()));
    if (local && !useLocal && !restored) {
      editorSection.append(row(button("Recover browser copy", () => showDraft(ctx, root, draft, references,
        questions, targets, submissions, ideas, restoredBuffer, local.data))));
    }
    editorSection.append(exports, autosaveStatus, revisionHistory, draftForm);
    checks.prepend(row(button("Refresh draft review", async () => {
      try {
        await flushDraft();
        await displayReview(draft);
      } catch (error) {
        if (!ctx.signal.aborted) show(reviewStatus, error.message, true);
      }
    })), assistantPanel(ctx, "Ask assistant to review this draft", async () => {
      await flushDraft();
      return { action: "draft", draft_id: draft.id };
    }));
    root.replaceChildren(editorSection, checks);
    if (restored || useLocal) queueDraft();
    void displayReview(draft).catch((error) => { if (!ctx.signal.aborted) show(reviewStatus, error.message, true); });
  }

  async function loadDossier(ctx, panel) {
    const [portfolioData, targetData] = await Promise.all([
      workflow(ctx, "portfolio/activities"), workflow(ctx, "portfolio/targets"),
    ]);
    const shared = portfolioData.items;
    const portfolio = section("Shared evidence", "Add publications, teaching, supervision, research projects, and service once, then link them to any application.");
    portfolio.append(details("Add portfolio activity", activityEditor(ctx, [], {}, null, true)));
    const activityKind = field("activity_kind", "Filter evidence by activity", { choices: [
      ["", "All activities"], ["publication", "Publications"], ["teaching", "Teaching"],
      ["supervision", "Supervision"], ["project", "Research projects"], ["service", "Service"], ["other", "Other"],
    ] });
    const cards = element("div", "work-stack");
    const kindControl = activityKind.querySelector("select");
    const showActivities = () => {
      const shown = shared.filter((entry) => !kindControl.value || kindControl.value === entry.data.kind);
      cards.replaceChildren();
      if (!shown.length) cards.append(note("No portfolio activities match this view."));
      for (const entry of shown) {
        const data = entry.data;
        const card = recordCard(data.title, [
          data.kind, data.evidence_date, data.publication_status,
          state.projects.get(entry.source_project_id)?.name,
        ].filter(Boolean).join(" · "));
        if (data.evidence_url) card.append(row(link(data.evidence_url, "Evidence")));
        if (data.paper?.url) {
          const paperLink = link(data.paper.url, "Linked paper");
          card.append(row(paperLink, paperActivityControls(data.paper, paperLink)));
        }
        card.append(details("Edit portfolio evidence", activityEditor(ctx, [], data, entry, true)));
        const revisions = element("div", "work-stack");
        const disclosure = details("Evidence history", revisions);
        disclosure.addEventListener("toggle", async () => {
          if (!disclosure.open || revisions.childElementCount) return;
          try {
            const { items } = await workflow(ctx, `portfolio/activities/${entry.id}/history`);
            for (const version of items) {
              const activity = version.data;
              const card = recordCard(activity.title, [dateOf(version.updated_at), activity.evidence_date,
                activity.publication_status, activity.notes].filter(Boolean).join(" · "),
                pill(`Version ${version.revision}`));
              if (activity.evidence_url) card.append(row(link(activity.evidence_url, "Evidence")));
              revisions.append(card);
            }
          } catch (error) {
            if (!ctx.signal.aborted) revisions.replaceChildren(status(error.message));
          }
        });
        card.append(disclosure);
        cards.append(card);
      }
    };
    kindControl.addEventListener("change", showActivities);
    portfolio.append(activityKind, cards);
    showActivities();
    const applications = section("Applications across topics");
    if (!targetData.items.length) applications.append(note("Choose a topic to set up an application target and its checklist."));
    for (const entry of targetData.items) {
      const data = entry.data;
      const card = recordCard(data.field, [
        data.route === "docentlik" ? "Doçentlik" : "Professorship",
        data.period, data.institution, entry.project_name,
      ].filter(Boolean).join(" · "), pill(`${entry.reviewed_count} of ${entry.criteria_count} reviewed`));
      if (entry.needs_evidence) card.append(note(`${entry.needs_evidence} ${entry.needs_evidence === 1 ? "criterion needs" : "criteria need"} evidence`));
      const actions = row(link(data.criteria_url, "Official criteria"));
      if (entry.project_id !== ctx.id) actions.append(button("Open topic checklist", () => chooseTopic(entry.project_id)));
      else actions.append(jump("application-criteria", "Go to checklist"));
      card.append(actions);
      applications.append(card);
    }
    panel.append(portfolio, applications);
    if (!ctx.id) return;
    const [profiles, activities, rules, reading] = await Promise.all([
      items(ctx, "dossier-profile", 1), items(ctx, "dossier-activities"), items(ctx, "dossier-rules"), items(ctx, "reading", 250),
    ]);
    const profile = profiles[0];
    const target = section("Application target", "Use the official criteria for your field, application period, and institution.");
    const data = profile?.data || {};
    const form = editor([
      field("route", "Application route", { choices: [["docentlik", "Doçentlik · ÜAK"], ["professorship", "Professorship"]], value: data.route }),
      field("field", "Field or bilim alanı", { value: data.field, required: true }),
      field("period", "Application period", { value: data.period, required: true, placeholder: "e.g. March 2027" }),
      field("institution", "Target institution", { value: data.institution }),
      field("position", "Position", { value: data.position }),
      field("criteria_url", "Official criteria URL", { type: "url", value: data.criteria_url, required: true }),
    ]);
    handleSubmit(ctx, form, "Save application target", async () => {
      await save(ctx, "dossier-profile", values(form), profile);
      refreshView("Application target saved.");
    });
    if (profile) {
      target.append(note([data.field, data.period, data.institution, data.position].filter(Boolean).join(" · ")));
      target.append(row(link(data.criteria_url, "Official criteria"), download(ctx, "dossier/export", "Export dossier")));
      target.append(details("Edit application target", form));
    } else {
      target.append(form);
    }
    const criteria = section("Criteria checklist");
    criteria.id = "application-criteria";
    if (!profile) {
      criteria.append(note("Save the application target to add checklist items."));
    } else {
      criteria.append(details("Add official criterion", ruleEditor(ctx, activities, shared, { official_url: data.criteria_url })));
      for (const rule of rules) {
        const previous = rule.data.profile_revision !== profile.revision;
        const reviewState = rule.display_status || rule.data.status;
        const label = previous ? "Previous target" : reviewState.replaceAll("_", " ");
        criteria.append(details(`${rule.data.title} · ${label}`, ruleEditor(ctx, activities, shared,
          { ...rule.data, status: reviewState }, rule, previous)));
      }
    }
    panel.append(target, criteria);
    if (activities.length) {
      const legacy = element("div", "work-stack");
      for (const activity of activities) {
        legacy.append(details(activity.data.title, activityEditor(ctx, reading, activity.data, activity)));
      }
      criteria.append(details("Earlier topic evidence", legacy));
    }
  }

  function activityEditor(ctx, reading, data, entry, shared = false) {
    const paperChoices = [["", "Use an evidence URL"], ...optionsFrom(reading, (value) => value.paper.title)];
    const form = editor([
      field("title", "Activity or publication title", { value: data.title, required: true }),
      field("kind", "Activity type", { value: data.kind, choices: [
        ["publication", "Publication"], ["teaching", "Teaching"], ["supervision", "Supervision"],
        ["project", "Research project"], ["service", "Academic service"], ["other", "Other"],
      ] }),
      field("evidence_url", "Evidence URL", { value: data.evidence_url, type: "url" }),
      field("evidence_date", "Evidence date", { value: data.evidence_date, type: "date" }),
      ...(!shared ? [field("reading_id", "Linked paper", { value: data.reading_id, choices: paperChoices })] : []),
      field("publication_type", "Publication type", { value: data.publication_type }),
      field("author_role", "Author role", { value: data.author_role }),
      field("publication_status", "Publication status", { value: data.publication_status, choices: [
        ["", "Select when applicable"], ["submitted", "Submitted"], ["accepted", "Accepted"],
        ["published", "Published"], ["indexed", "Indexed"],
      ] }),
      field("index_name", "Index", { value: data.index_name }),
      field("index_year", "Index coverage year", { type: "number", value: data.index_year, min: 1800, max: 2200 }),
      field("index_url", "Official index record URL", { type: "url", value: data.index_url }),
      field("notes", "Notes", { type: "textarea", value: data.notes }),
    ]);
    handleSubmit(ctx, form, "Save activity", async () => {
      if (shared) {
        const path = entry ? `portfolio/activities/${entry.id}?revision=${entry.revision}` : "portfolio/activities";
        await workflow(ctx, path, entry ? "PUT" : "POST", values(form));
      } else {
        await save(ctx, "dossier-activities", values(form), entry);
      }
      refreshView("Activity saved.");
    });
    return form;
  }

  function ruleEditor(ctx, activities, shared, data, entry, previous) {
    const existing = activities.filter((activity) => data.activity_ids?.includes(activity.id));
    const form = editor([
      field("title", "Criterion", { value: data.title, required: true }),
      field("clause", "Clause or table reference", { value: data.clause, required: true }),
      field("official_url", "Official criterion URL", { value: data.official_url, type: "url", required: true }),
      field("status", "Review status", { value: previous ? "in_review" : data.status, choices: [
        ["needs_evidence", "Needs evidence"], ["in_review", "In review"], ["reviewed", "Reviewed by researcher"],
      ] }),
      field("portfolio_activity_ids", "Shared portfolio evidence", {
        choices: optionsFrom(shared, (value) => value.title), multiple: true, value: data.portfolio_activity_ids,
      }),
      ...(existing.length ? [field("activity_ids", "Earlier topic evidence", {
        choices: optionsFrom(existing, (value) => value.title), multiple: true, value: data.activity_ids,
      })] : []),
      field("notes", "Review notes", { type: "textarea", value: data.notes }),
    ]);
    handleSubmit(ctx, form, previous ? "Save for current target" : "Save criterion", async () => {
      await save(ctx, "dossier-rules", values(form), entry);
      refreshView("Criterion saved.");
    });
    return form;
  }

  function localReadingDay(timezone) {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit",
    }).formatToParts(new Date());
    const date = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
    return `${date.year}-${date.month}-${date.day}`;
  }

  function readingTime(value, zone) {
    return value ? new Date(value).toLocaleString(undefined, { timeZone: zone, dateStyle: "medium", timeStyle: "short" }) : "";
  }

  function dailyScheduleForm(ctx, schedule, saveSchedule) {
    const zone = schedule?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
    const sources = new Set((schedule?.providers || "openalex").split(","));
    const available = new Set(sourceCheckboxes().filter((checkbox) => !checkbox.disabled).map((checkbox) => checkbox.value));
    const choices = SOURCES.filter((source) => available.has(source.id) || sources.has(source.id))
      .map((source) => [source.id, available.has(source.id) ? source.label : `${source.label} · needs setup`]);
    const timezone = field("timezone", "Time zone", { value: zone, required: true, maxLength: 120 });
    const zoneInput = timezone.querySelector("input");
    const zones = element("datalist");
    zones.id = "daily-reading-timezones";
    zoneInput.setAttribute("list", zones.id);
    for (const value of new Set([zone, "Europe/Istanbul", "UTC", ...(Intl.supportedValuesOf?.("timeZone") || [])])) {
      const option = element("option");
      option.value = value;
      zones.append(option);
    }
    const form = editor([
      field("q", "Reading keywords", { value: schedule?.q || state.projects.get(ctx.id)?.name,
        required: true, maxLength: 300, wide: true }),
      field("start_on", "Start date", { type: "date", value: schedule?.start_on || localReadingDay(zone), required: true }),
      field("local_time", "Daily time", { type: "time", value: schedule?.local_time || "08:00", required: true }),
      timezone,
      field("papers_per_day", "Papers per day", { type: "number", value: schedule?.papers_per_day || 3, min: 1, max: 10, required: true }),
      field("providers", "Paper sources", {
        choices, value: [...sources], multiple: true, required: true,
        hint: "OpenAlex supplies trend suggestions.",
      }),
      field("enabled", "Run automatically", { type: "checkbox", value: schedule?.enabled ?? true }),
    ]);
    form.append(zones);
    form.elements.q.minLength = 2;
    handleSubmit(ctx, form, "Save daily schedule", () => {
      const data = values(form);
      try {
        new Intl.DateTimeFormat("en", { timeZone: data.timezone });
      } catch {
        throw new Error("Use a time zone such as Europe/Istanbul or UTC.");
      }
      return saveSchedule({ ...data, providers: data.providers.join(",") });
    });
    return form;
  }

  async function loadDailyReading(ctx, panel) {
    const topicSelect = field("daily_topic", "Reading topic", {
      choices: [["", "All topics"], ...[...state.projects.values()].map((project) => [project.id, project.name])],
      value: ctx.id || "",
    });
    const topicControl = topicSelect.querySelector("select");
    topicControl.addEventListener("change", () => chooseTopic(topicControl.value || null));
    panel.append(row(topicSelect));

    if (!ctx.id) {
      const { items: schedules } = await workflow(ctx, "daily-reading");
      const overview = section("Daily schedules");
      if (!schedules.length) overview.append(note("Choose a topic to set up its daily reading and trend suggestions."));
      for (const entry of schedules) {
        const s = entry.settings;
        const card = recordCard(entry.name, [s.q, `${s.local_time} · ${s.timezone}`,
          entry.next_run_at && `Next check ${readingTime(entry.next_run_at, s.timezone)}`,
        ].filter(Boolean).join(" · "), pill(s.enabled ? `${entry.read} of ${entry.total} read today` : "Automatic checks paused"));
        card.append(row(button("Open daily reading", () => chooseTopic(entry.project_id))));
        overview.append(card);
      }
      panel.append(overview);
      const highlights = section("Trending across your topics", "Today’s OpenAlex suggestions from your scheduled topics.");
      const ranked = schedules.flatMap((entry) => entry.trends.map((trend) => ({ entry, trend })));
      ranked.sort((a, b) => Number(a.trend.sparse) - Number(b.trend.sparse) || b.trend.change_pp - a.trend.change_pp);
      const shown = new Set();
      for (const { entry, trend } of ranked) {
        if (shown.has(trend.id)) continue;
        shown.add(trend.id);
        const card = recordCard(trend.name, [entry.name, trend.sparse && "Limited sample"].filter(Boolean).join(" · "),
          pill(`+${trend.change_pp} pp`, "positive"));
        card.append(row(button("Open trend edition", () => chooseTopic(entry.project_id))));
        highlights.append(card);
        if (shown.size === 6) break;
      }
      if (!shown.size) highlights.append(note("Trend suggestions appear after your topics’ first daily checks."));
      panel.append(highlights);
      return;
    }

    const endpoint = `projects/${ctx.id}/daily-reading`;
    let data = await workflow(ctx, endpoint);
    let selectedDay = "";
    let loading = false;
    let generation = 0;

    const schedule = section("Reading schedule");
    const scheduleInfo = note("");
    schedule.append(scheduleInfo);
    const editor = dailyScheduleForm(ctx, data.settings, async (settings) => {
      await workflow(ctx, endpoint, "PUT", settings);
      refreshView("Daily schedule saved.");
    });
    if (data.settings) schedule.append(details("Edit schedule", editor));
    else schedule.append(editor);
    panel.append(schedule);
    if (!data.settings) {
      scheduleInfo.textContent = "Set a start date and time for this topic. You can give each topic a different schedule.";
      return;
    }

    const reading = section("Reading list");
    const editionSelect = field("daily_edition", "Edition", { choices: [["", "Today"]] });
    const editionControl = editionSelect.querySelector("select");
    const onlyUnread = field("daily_unread", "Show unread only", { type: "checkbox" });
    const unreadControl = onlyUnread.querySelector("input");
    const feedback = status();
    const check = button("Get today’s papers", async () => {
      loading = true;
      ++generation;
      render();
      show(feedback, "Checking for studies and trends…");
      try {
        data = await workflow(ctx, `${endpoint}/check`, "POST");
        show(feedback, "");
      } catch (error) {
        if (!ctx.signal.aborted) show(feedback, error.message, true);
      } finally {
        loading = false;
        if (!ctx.signal.aborted) render();
        void refreshLibraryCount();
      }
    }, false);
    const toolbar = row(editionSelect, onlyUnread, check);
    toolbar.classList.add("daily-controls");
    const progress = note("");
    progress.classList.add("daily-progress");
    const papers = element("div", "work-stack");
    reading.append(toolbar, feedback, progress, papers);
    const trends = section("Trending research topics");
    const trendContent = element("div", "work-stack");
    trends.append(trendContent);
    panel.append(reading, trends);

    function render() {
      const s = data.settings;
      const edition = data.edition;
      const completed = data.history.find((day) => day.day === data.today);
      scheduleInfo.textContent = [`Daily at ${s.local_time} · ${s.timezone}`, `Starts ${s.start_on}`,
        s.enabled ? `Next check ${readingTime(data.next_run_at, s.timezone)}` : "Automatic checks paused",
      ].filter(Boolean).join(" · ");
      const dates = [element("option", "", `Today · ${data.today}`)];
      dates[0].value = "";
      for (const day of data.history) {
        if (day.day === data.today && selectedDay !== day.day) continue;
        const option = element("option", "", `${day.day} · ${day.read} of ${day.total} read`);
        option.value = day.day;
        dates.push(option);
      }
      editionControl.replaceChildren(...dates);
      editionControl.value = selectedDay;
      check.hidden = Boolean(selectedDay && selectedDay !== data.today);
      check.disabled = loading || Boolean(edition?.checking) || data.today < s.start_on || Boolean(edition && !edition.can_retry);
      check.textContent = edition?.checked_at
        ? (edition.status === "partial" ? "Retry today’s check" : "Find more for today") : "Get today’s papers";
      editionControl.disabled = loading;

      papers.replaceChildren();
      trendContent.replaceChildren();
      if (!edition || !edition.checked_at) {
        progress.textContent = completed ? "" : data.today < s.start_on ? `Your first edition starts ${s.start_on}.`
          : edition?.checking || loading ? "Building today’s edition…" : "Today’s reading list is waiting for its first check.";
        trendContent.append(note("Trend suggestions appear with the daily edition."));
        return;
      }
      const read = edition.papers.filter((entry) => entry.read_at).length;
      progress.textContent = `${read} of ${edition.papers.length} read · ${edition.day}`;
      const failures = edition.coverage.filter((entry) => ["failed", "rate_limited", "unavailable"].includes(entry.status));
      if (failures.length) papers.append(note(`Paper sources · ${failures.map((item) => `${item.provider} ${item.status.replaceAll("_", " ")}`).join(", ")}`));
      const shown = edition.papers.filter((entry) => !unreadControl.checked || !entry.read_at);
      if (!edition.papers.length) papers.append(note("No new, unread matches were available for this edition."));
      else if (!shown.length) papers.append(note("You’ve read every paper in this edition."));
      for (const entry of shown) {
        const item = element("article", "work-card daily-paper-entry");
        const summary = element("div", "daily-paper-heading");
        summary.append(pill(entry.read_at ? "Read" : "Unread", entry.read_at ? "positive" : ""));
        if (entry.source === "library") summary.append(pill("From your library"));
        const list = element("ol", "results");
        list.append(paperCard(entry.paper, { kind: "library", run_id: entry.paper.library_id }));
        item.append(summary, list);
        if (entry.paper.abstract?.length > 360) item.append(details("Full abstract", note(entry.paper.abstract)));
        papers.append(item);
      }

      const trend = edition.trend;
      if (!trend || Object.keys(trend.errors).length) {
        const codes = [...new Set(Object.values(trend?.errors || {}).map((error) =>
          String(error?.code || "provider error").replaceAll("_", " ")))];
        trendContent.append(note(`Trend suggestions are temporarily unavailable${codes.length ? ` · ${codes.join(", ")}` : ""}.`));
        return;
      }
      trendContent.append(note(`OpenAlex · Share of matching articles and reviews · ${trend.periods.map((period) => `${period.from} to ${period.to}`).join(" compared with ")}`));
      if (!trend.topics.length) trendContent.append(note("No topics gained publication share in this comparison."));
      for (const topic of trend.topics) {
        const card = recordCard(topic.name,
          `${topic.baseline_count} → ${topic.recent_count} papers · ${topic.baseline_share}% → ${topic.recent_share}% of matches`,
          pill(`+${topic.change_pp} pp`, "positive"));
        if (topic.sparse) card.append(note("Limited sample"));
        const explore = button("Explore papers", () => {
          selectView(workspaceTabs[0]);
          applySearchSettings(topic.name, "all", s.providers, null, null);
          void runSearch();
        });
        card.append(row(explore, button("Start research brief", () => startBrief(ctx.id, {
          starting_point: `${topic.name} · OpenAlex daily trend · ${edition.day}`,
        }))));
        trendContent.append(card);
      }
    }

    async function loadEdition() {
      if (loading) return;
      const requestId = ++generation;
      try {
        const next = await workflow(ctx, endpoint + (selectedDay ? `?day=${encodeURIComponent(selectedDay)}` : ""));
        if (!ctx.signal.aborted && requestId === generation) {
          data = next;
          render();
        }
      } catch (error) {
        if (!ctx.signal.aborted && requestId === generation) show(feedback, error.message, true);
      }
    }
    editionControl.addEventListener("change", () => { selectedDay = editionControl.value; void loadEdition(); });
    unreadControl.addEventListener("change", render);
    document.addEventListener("academic-paper-activity", (event) => {
      if (data.edition?.papers.some((entry) => entry.paper.library_id === event.detail.library_id)) void loadEdition();
    }, { signal: ctx.signal });
    const poll = window.setInterval(() => { if (!document.hidden) void loadEdition(); }, 40000);
    ctx.signal.addEventListener("abort", () => window.clearInterval(poll), { once: true });
    render();
  }

  const loaders = {
    "discover-view": loadDiscovery,
    "inbox-view": loadInbox,
    "daily-view": loadDailyReading,
    "today-view": loadToday,
    "submissions-view": loadSubmissions,
    "manuscript-view": loadManuscript,
    "dossier-view": loadDossier,
  };

  async function refreshView(message) {
    activeView?.abort();
    const controller = new AbortController();
    activeView = controller;
    const view = workspaceTabs.find((tab) => tab.getAttribute("aria-selected") === "true")?.getAttribute("aria-controls");
    if (!loaders[view]) return;
    const panel = document.getElementById(view);
    const [title, description] = views[view];
    const intro = element("header", "work-intro");
    intro.append(element("h2", "", title), note(description));
    panel.replaceChildren(intro);
    const ctx = { id: selectedProjectId(), signal: controller.signal };
    if (!ctx.id && !["inbox-view", "daily-view", "today-view", "submissions-view", "dossier-view"].includes(view)) {
      panel.append(section("Choose a topic", "Select or create a topic to save your publishing work."));
      return;
    }
    if (typeof message === "string" && message) panel.append(status(message));
    const indicator = status("Loading workspace…");
    const content = element("div", "work-stack");
    panel.append(indicator, content);
    try {
      await loaders[view](ctx, content);
      indicator.remove();
    } catch (error) {
      if (!ctx.signal.aborted) show(indicator, error.message, true);
    }
  }

  document.addEventListener("academic-workspace-change", () => refreshView());
})();

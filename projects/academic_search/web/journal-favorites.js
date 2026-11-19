"use strict";

(() => {
  const panel = document.querySelector("#journals-view");
  const root = document.querySelector("#followed-journals-body");
  const savedKey = "academic-followed-journal";
  const pageSize = 12;
  let favorites = [];
  let selected = localStorage.getItem(savedKey) || "";
  let offset = 0;
  let unreadOnly = false;
  let listGeneration = 0;
  let feedGeneration = 0;
  let shownPapers = [];
  const refreshing = new Set();

  function itemApi(path = "", data, method = "POST") {
    const options = data === undefined ? { method: "GET", cache: "no-store" } : jsonOptions(data, method);
    return requestJson(`/api/v1/journal-favorites${path}`, options, "Journal tracking request could not be completed.");
  }

  function action(label, callback, primary = false) {
    const node = element("button", primary ? "" : "secondary", label);
    node.type = "button";
    node.addEventListener("click", callback);
    return node;
  }

  function row(...children) {
    const node = element("div", "work-actions");
    node.append(...children.filter(Boolean));
    return node;
  }

  function link(url, label) {
    if (!url || !/^https?:\/\//i.test(url)) return null;
    const node = element("a", "work-link", label);
    node.href = url;
    node.target = "_blank";
    node.rel = "noopener noreferrer";
    return node;
  }

  function note(value) {
    return element("p", "work-note", value);
  }

  function status(value = "") {
    const node = element("p", "work-status", value);
    node.setAttribute("role", "status");
    node.hidden = !value;
    return node;
  }

  function updateStatus(node, value, failed = false) {
    node.textContent = value;
    node.hidden = !value;
    node.classList.toggle("work-error", failed);
  }

  function dateOf(value) {
    return value ? new Date(value).toLocaleString() : "";
  }

  function journalId(journal) {
    if (journal.search_supported === false) return "";
    const candidate = (journal.identifiers?.openalex || journal.id || "").split("/").at(-1).toUpperCase();
    return /^S\d+$/.test(candidate) ? candidate : "";
  }

  function issns(journal) {
    return new Set([journal.issn_l, ...(journal.issns || [])].filter(Boolean)
      .map((issn) => issn.replaceAll("-", "").toUpperCase()));
  }

  function match(journal) {
    const openalex = journalId(journal);
    const identifiers = issns(journal);
    return favorites.find((item) => (openalex && item.openalex_id)
      ? openalex === item.openalex_id
      : (item.journal.catalog_id && item.journal.catalog_id === journal.catalog_id)
        || [...issns(item.journal)].some((value) => identifiers.has(value)));
  }

  function syncActions() {
    for (const button of document.querySelectorAll("[data-follow-journal]")) {
      const favorite = match(button.journal);
      button.textContent = favorite ? "★ View followed journal" : "☆ Follow journal";
    }
  }

  function chooseFavorite(id) {
    if (selected !== id) {
      offset = 0;
      unreadOnly = false;
    }
    selected = id;
    if (id) localStorage.setItem(savedKey, id);
    else localStorage.removeItem(savedKey);
  }

  window.journalFollowAction = (journal) => {
    const button = action("☆ Follow journal", async () => {
      button.disabled = true;
      try {
        const existing = match(journal);
        if (existing) {
          chooseFavorite(existing.id);
          await loadFavorites();
          root.scrollIntoView({ block: "nearest" });
          return;
        }
        const payload = await itemApi("", { provider: journal.catalog_provider || "openalex",
          journal_id: journal.provider_id || journal.id });
        chooseFavorite(payload.id);
        await loadFavorites();
        root.scrollIntoView({ block: "nearest" });
        if (!payload.last_attempt_at) await refreshJournal(payload.id);
      } catch (error) {
        journalStatus.textContent = error.message;
      } finally {
        button.disabled = false;
      }
    });
    button.journal = journal;
    button.dataset.followJournal = "";
    if (match(journal)) button.textContent = "★ View followed journal";
    return button;
  };

  window.openFollowedJournal = (id) => {
    chooseFavorite(id);
    selectView(document.querySelector("#journals-tab"), true);
    root.scrollIntoView({ block: "nearest" });
  };

  async function refreshJournal(id, message) {
    if (refreshing.has(id)) return;
    refreshing.add(id);
    if (message) updateStatus(message, "Checking publications and submission sources…");
    try {
      await itemApi(`/${id}/refresh`, {});
      await loadFavorites();
    } catch (error) {
      if (message?.isConnected) updateStatus(message, error.message, true);
      else if (id === selected) journalStatus.textContent = error.message;
    } finally {
      refreshing.delete(id);
    }
  }

  async function loadFavorites() {
    const generation = ++listGeneration;
    try {
      const { items } = await itemApi();
      if (generation !== listGeneration || panel.hidden) return;
      favorites = items;
      syncActions();
      if (!favorites.some((item) => item.id === selected)) chooseFavorite(favorites[0]?.id || "");
      if (!selected) {
        shownPapers = [];
        root.replaceChildren(note("Choose a journal in Journal explorer and select Follow journal."));
        return;
      }
      await loadFeed();
    } catch (error) {
      if (generation === listGeneration && !panel.hidden) root.replaceChildren(status(error.message));
    }
  }

  async function loadFeed() {
    const generation = ++feedGeneration;
    const id = selected;
    try {
      const params = new URLSearchParams({ limit: pageSize, offset, unread_only: unreadOnly });
      const feed = await itemApi(`/${id}?${params}`);
      if (generation !== feedGeneration || id !== selected || panel.hidden) return;
      if (!feed.papers.length && offset) {
        offset = Math.max(0, offset - pageSize);
        await loadFeed();
        return;
      }
      favorites = favorites.map((item) => item.id === id ? feed.favorite : item);
      shownPapers = feed.papers;
      render(feed);
    } catch (error) {
      if (generation === feedGeneration && id === selected && !panel.hidden) root.replaceChildren(status(error.message));
    }
  }

  function render(feed) {
    const favorite = feed.favorite;
    const journal = favorite.journal;
    const header = element("div", "journal-follow-toolbar");
    const label = element("label", "", "Followed journal");
    const select = element("select");
    label.append(select);
    for (const entry of favorites) {
      const option = element("option", "", `${entry.journal.display_name}${entry.unread ? ` · ${entry.unread} new` : ""}`);
      option.value = entry.id;
      select.append(option);
    }
    select.value = favorite.id;
    select.addEventListener("change", () => {
      chooseFavorite(select.value);
      void loadFeed();
    });
    const message = status();
    const refresh = action("Refresh journal", async () => {
      refresh.disabled = true;
      await refreshJournal(favorite.id, message);
      refresh.disabled = false;
    }, true);
    if (favorite.refreshing) refresh.disabled = true;
    const unfollow = action("Unfollow", async () => {
      unfollow.disabled = true;
      try {
        await itemApi(`/${favorite.id}`, {}, "DELETE");
        if (selected === favorite.id) chooseFavorite("");
        await loadFavorites();
      } catch (error) {
        if (message.isConnected) updateStatus(message, error.message, true);
      } finally {
        unfollow.disabled = false;
      }
    });
    header.append(label, row(refresh, unfollow));
    const split = element("div", "journal-follow-grid");
    split.append(publications(feed, message), submissions(feed));
    const identity = note([journal.publisher, journal.issn_l && `ISSN-L ${journal.issn_l}`].filter(Boolean).join(" · "));
    root.replaceChildren(header, identity, message, split);
  }

  function publications(feed, message) {
    const favorite = feed.favorite;
    const area = element("section", "work-stack journal-follow-publications");
    area.append(element("h3", "", "Latest papers"));
    const coverage = favorite.paper_status;
    if (favorite.papers_checked_at) area.append(note(`OpenAlex · Last successful check ${dateOf(favorite.papers_checked_at)}`));
    if (coverage && !["responded", "empty"].includes(coverage.status)) {
      area.append(note(coverage.status === "rate_limited" ? "OpenAlex rate limited the latest check. Saved papers remain available."
        : coverage.message || "The latest publication check was unavailable."));
    }
    const filter = element("label", "work-checkbox journal-unread-filter", "Show new only");
    const checkbox = element("input");
    checkbox.type = "checkbox";
    checkbox.checked = unreadOnly;
    checkbox.addEventListener("change", () => {
      unreadOnly = checkbox.checked;
      offset = 0;
      void loadFeed();
    });
    filter.append(checkbox);
    const mark = action("Mark all seen", async () => {
      mark.disabled = true;
      try {
        await itemApi(`/${favorite.id}/seen`, {});
        offset = 0;
        await loadFeed();
      } catch (error) {
        if (message.isConnected) updateStatus(message, error.message, true);
      } finally {
        mark.disabled = false;
      }
    });
    mark.disabled = !favorite.unread;
    area.append(row(filter, mark));
    const list = element("ol", "results followed-paper-list");
    for (const paper of feed.papers) {
      const origin = selectedProjectId() ? { kind: "library", run_id: paper.library_id } : null;
      const card = paperCard(paper, origin);
      const labels = row(...[
        paper.followed_unread ? "New to your feed" : "",
        paper.work_type?.replaceAll("-", " "),
        paper.primary_topic,
        paper.is_retracted ? "Retraction flagged by the source" : "",
      ].filter(Boolean).map((text) => element("span", "work-pill", text)));
      if (labels.childElementCount) card.querySelector("article").append(labels);
      list.append(card);
    }
    if (!feed.papers.length) {
      area.append(note(unreadOnly ? "No new papers in this feed."
        : favorite.last_attempt_at ? "No saved publications are available for this journal yet."
          : "Refresh the journal to load its latest papers."));
    } else area.append(list);
    if (offset || feed.has_more) {
      const previous = action("Previous papers", () => {
        offset = Math.max(0, offset - pageSize);
        void loadFeed();
      });
      previous.disabled = offset === 0;
      const next = action("More papers", () => {
        offset += pageSize;
        void loadFeed();
      });
      next.disabled = !feed.has_more;
      area.append(row(previous, note(`Page ${offset / pageSize + 1}`), next));
    }
    return area;
  }

  function submissions(feed) {
    const favorite = feed.favorite;
    const journal = favorite.journal;
    const data = favorite.submission || {};
    const area = element("section", "work-stack journal-follow-submissions");
    area.append(element("h3", "", "Submission opportunities"));
    const links = row(link(data.homepage_url || feed.homepage_url || journal.source_url, "Journal page"),
      link(data.guidelines_url, "Author guidelines"), link(data.scope_url, "Aims and scope"),
      link(data.submission_url, "Submission portal"), link(data.fees_url, "Fees"), link(data.calls_url, "Publisher calls"));
    if (links.childElementCount) area.append(links);
    if (favorite.publisher_checked_at) area.append(note(`Publisher checked ${dateOf(favorite.publisher_checked_at)}`));
    if (favorite.publisher_status?.message) area.append(note(favorite.publisher_status.message));
    const label = { open: "Regular submissions open", upcoming: "Regular submissions upcoming",
      closed: "Regular submissions closed", unverified: "Regular submission status unverified" };
    area.append(element("span", `work-pill${data.status === "open" ? " positive" : ""}`, label[data.status] || label.unverified));
    if (data.article_types) area.append(note(`Accepted article types · ${data.article_types}`));
    if (data.fees) area.append(note(data.fees));
    if (data.scope) area.append(note(data.scope));
    if (data.evidence) area.append(note(data.evidence));
    area.append(element("h4", "", "Verified open calls"));
    if (!feed.calls.length) area.append(note("No verified open special issues are saved for this journal."));
    for (const call of feed.calls) {
      const card = element("article", "work-card");
      card.append(element("strong", "", call.title));
      if (call.deadline) card.append(note(`Manuscript deadline · ${call.deadline}`));
      card.append(row(link(call.source_url, "Official call")));
      area.append(card);
    }
    const find = action("Find calls for this journal", () => {
      state.journalCallFilter = journal.issn_l || journal.display_name;
      selectView(document.querySelector("#submissions-tab"), true);
    });
    const fit = favorite.openalex_id ? action("Compare with my manuscript", () => {
      selectJournal({ ...journal, id: favorite.openalex_id });
      journalNameInput.scrollIntoView({ block: "center" });
      document.querySelector("#journal-topics").focus();
    }) : null;
    area.append(row(find, fit));
    return area;
  }

  document.addEventListener("academic-workspace-change", () => {
    if (!panel.hidden) void loadFavorites();
  });
  document.addEventListener("academic-paper-activity", (event) => {
    if (!panel.hidden && shownPapers.some((paper) => paper.library_id === event.detail.library_id)) void loadFeed();
  });
  window.setInterval(() => {
    if (!panel.hidden && !document.hidden && !refreshing.size) void loadFavorites();
  }, 60000);
})();

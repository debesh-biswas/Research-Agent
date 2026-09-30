/* Reading desk. Sample data in data.js. Ask previews cards and does not call NIM. */

const STATUS_LABEL = {
  completed: "Complete",
  degraded: "Degraded",
  failed: "Failed",
  running: "Running",
};

const ACTION_LABEL = {
  deep_read: "Deep read",
  summarize: "Summary",
};

const state = {
  topicId: null,
  runId: null,
  filter: "all",
  query: "",
  draft: "",
  threads: {},
  moveFocus: false,
  live: false,
  pending: false,
  newTopic: {
    step: "form",
    id: "",
    name: "",
    description: "",
    keywords: [],
    pending: false,
    status: "",
    tone: null,
  },
};

function slugify(name) {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function topics() {
  return (window.DESK && window.DESK.topics) || [];
}

function topicById(id) {
  const all = topics();
  return all.find((topic) => topic.id === id) || all[0] || null;
}

function runById(topic, id) {
  if (!topic || !topic.runs || !topic.runs.length) return null;
  return topic.runs.find((run) => run.id === id) || topic.runs[0];
}

function paperById(run, id) {
  return run.papers.find((paper) => paper.id === id) || null;
}

function current() {
  const topic = topicById(state.topicId);
  const run = runById(topic, state.runId);
  if (topic) state.topicId = topic.id;
  state.runId = run ? run.id : null;
  return { topic, run };
}

function parseRoute() {
  const raw = (location.hash || "#/week").replace(/^#/, "");
  const [path, query = ""] = raw.split("?");
  const parts = path.split("/").filter(Boolean);
  return { parts, params: new URLSearchParams(query) };
}

function formatDay(iso) {
  const date = new Date(`${iso}T00:00:00Z`);
  return date.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
}

function formatPeriod(run) {
  const start = new Date(`${run.periodStart}T00:00:00Z`);
  const end = new Date(`${run.periodEnd}T00:00:00Z`);
  const year = end.getUTCFullYear();
  if (start.getUTCMonth() === end.getUTCMonth()) {
    return `${start.getUTCDate()}–${end.getUTCDate()} ${end.toLocaleDateString("en-GB", {
      month: "short",
      timeZone: "UTC",
    })} ${year}`;
  }
  return `${formatDay(run.periodStart)} – ${formatDay(run.periodEnd)} ${year}`;
}

function formatDuration(seconds) {
  const minutes = Math.max(1, Math.round(seconds / 60));
  return `${minutes} min`;
}

function authors(paper) {
  if (paper.authors.length <= 3) return paper.authors.join(", ");
  return `${paper.authors.slice(0, 2).join(", ")} and ${paper.authors.length - 2} more`;
}

function paperMeta(paper) {
  const bits = [authors(paper), paper.venue, ACTION_LABEL[paper.action] || paper.action];
  return bits.filter(Boolean).join(" · ");
}

function stamp(status, landed) {
  const label = STATUS_LABEL[status] || status;
  const motion = landed ? " stamp-land" : "";
  return `<span class="stamp stamp-${esc(status)}${motion}">${esc(label)}</span>`;
}

function paperLinks(run, ids) {
  const items = ids
    .map((id) => paperById(run, id))
    .filter(Boolean)
    .map((paper) => `<a href="#/papers/${esc(paper.id)}">${esc(paper.title)}</a>`);
  if (!items.length) return "";
  return `<p class="from">From ${items.join(", ")}</p>`;
}

function findings(run, items) {
  if (!items.length) return "";
  return items
    .map(
      (item) => `<article class="finding"><p>${esc(item.text)}</p>${paperLinks(run, item.paperIds)}</article>`,
    )
    .join("");
}

function stringList(items) {
  if (!items.length) return "";
  return `<ul>${items.map((item) => `<li>${esc(item)}</li>`).join("")}</ul>`;
}

function reportSection(title, body, id) {
  if (!body) return "";
  const anchor = id ? ` id="${esc(id)}"` : "";
  return `<section${anchor}><h2>${esc(title)}</h2>${body}</section>`;
}

function matchesFilter(paper) {
  if (state.filter === "deep_read" || state.filter === "summarize") {
    return paper.action === state.filter;
  }
  if (state.filter === "abstract") return paper.abstractOnly;
  return true;
}

function visiblePapers(run) {
  const query = state.query.trim().toLowerCase();
  return run.papers
    .map((paper, index) => ({ paper, index }))
    .filter(({ paper }) => matchesFilter(paper))
    .filter(({ paper }) => !query || paper.title.toLowerCase().includes(query));
}

function renderPaperList(run) {
  const rows = visiblePapers(run);
  if (!rows.length) {
    return `<p class="empty">No papers match. Clear the search or show every paper.</p>`;
  }
  return `<ul class="paper-list">${rows
    .map(({ paper, index }) => {
      const mark = paper.abstractOnly ? ` <span class="mark">Abstract only</span>` : "";
      return `<li><a class="paper-row" href="#/papers/${esc(paper.id)}">
        <span class="idx">${String(index + 1).padStart(2, "0")}</span>
        <span>
          <span class="paper-row-title">${esc(paper.title)}</span>
          <span class="paper-row-meta">${esc(paperMeta(paper))}${mark}</span>
          <span class="paper-row-dek">${esc(paper.contribution)}</span>
        </span>
      </a></li>`;
    })
    .join("")}</ul>`;
}

function filterButton(id, label) {
  const pressed = state.filter === id ? "true" : "false";
  return `<button type="button" data-filter="${esc(id)}" aria-pressed="${pressed}">${esc(label)}</button>`;
}

function shelf(run, ids) {
  const items = ids
    .map((id) => paperById(run, id))
    .filter(Boolean)
    .map((paper) => `<li><a href="#/papers/${esc(paper.id)}">${esc(paper.title)}</a></li>`)
    .join("");
  return items ? `<ul class="shelf">${items}</ul>` : "";
}

function readingOrder(run) {
  const groups = [
    ["Essential", run.readingOrder.essential],
    ["Useful", run.readingOrder.useful],
    ["Peripheral", run.readingOrder.peripheral],
  ];
  return groups
    .map(([label, ids]) => {
      const list = shelf(run, ids);
      if (!list) return "";
      return `<p class="shelf-label">${esc(label)}</p>${list}`;
    })
    .join("");
}

function funnel(summary) {
  const items = [
    [summary.candidatesDiscovered, "found"],
    [summary.papersClassified, "screened"],
    [summary.papersSelected, "kept"],
    [summary.deepReads, "read"],
  ];
  return `<ul class="funnel">${items
    .map(([count, label]) => `<li><strong>${esc(count)}</strong> ${esc(label)}</li>`)
    .join("")}</ul>`;
}

function errorBlock(run) {
  if (!run.errors.length) return "";
  const noun = run.errors.length === 1 ? "isolated error" : "isolated errors";
  const items = run.errors
    .map(
      (error) =>
        `<li><strong>${esc(error.category)}</strong> ${esc(error.message)}</li>`,
    )
    .join("");
  return `<details class="errors"><summary>${run.errors.length} ${noun}. The week still finished.</summary><ul class="error-list">${items}</ul></details>`;
}

function viewWeek(run) {
  const gaps = run.gaps
    .map(
      (gap) =>
        `<article class="gap"><p>${esc(gap.description)}</p>${paperLinks(run, gap.paperIds)}</article>`,
    )
    .join("");
  const ideas = run.ideas
    .map(
      (idea) =>
        `<article class="idea"><p><a href="#/report?section=ideas">${esc(idea.title)}</a></p></article>`,
    )
    .join("");
  return `<p class="kicker">This week</p>
    <div class="week-head">
      <h1>${esc(formatPeriod(run))}</h1>
      <div class="week-actions">
        ${stamp(run.status, true)}
        <button class="button" type="button" data-clear-run="${esc(run.id)}">Clear this run</button>
      </div>
    </div>
    ${funnel(run.summary)}
    <p class="quiet">${esc(formatDuration(run.durationSeconds))} · ${esc(run.models.join(" · "))}</p>
    <div class="desk-grid">
      <div>
        <p class="lede">${esc(run.executiveSummary)}</p>
        ${reportSection("What changed", findings(run, run.developments))}
        ${reportSection("Since last time", stringList(run.changes))}
        ${reportSection("Open problems", gaps)}
        ${ideas ? reportSection("Worth trying", ideas) : ""}
        ${errorBlock(run)}
      </div>
      <aside class="side">
        <p class="kicker">Reading order</p>
        ${readingOrder(run)}
        <p class="shelf-label"><a href="#/papers">All papers</a></p>
      </aside>
    </div>`;
}

function viewPapers(run) {
  const deep = run.papers.filter((paper) => paper.action === "deep_read").length;
  const summaries = run.papers.filter((paper) => paper.action === "summarize").length;
  const abstracts = run.papers.filter((paper) => paper.abstractOnly).length;
  return `<div class="page-head"><h1>Papers</h1>${stamp(run.status, false)}</div>
    <p class="quiet">${esc(formatPeriod(run))} · ${esc(run.papers.length)} kept</p>
    <div class="filters">
      ${filterButton("all", `All ${run.papers.length}`)}
      ${filterButton("deep_read", `Deep reads ${deep}`)}
      ${filterButton("summarize", `Summaries ${summaries}`)}
      ${abstracts ? filterButton("abstract", `Abstract only ${abstracts}`) : ""}
      <input class="search" id="paper-search" type="search" placeholder="Search titles" value="${esc(state.query)}" aria-label="Search titles" />
    </div>
    <div id="paper-list">${renderPaperList(run)}</div>`;
}

function linkPair(label, href) {
  if (!href) return "";
  return `<a href="${esc(href)}">${esc(label)}</a>`;
}

function viewPaper(run, paperId) {
  const paper = paperById(run, paperId);
  if (!paper) {
    return `<a class="back" href="#/papers">Papers</a>
      <h1>Not in this run</h1>
      <p class="empty">That paper is not on the shelf for ${esc(formatPeriod(run))}.</p>`;
  }
  const skim = paper.abstractOnly
    ? `<p class="mark">Abstract only. This card is a skim, not a deep read.</p>`
    : "";
  const block = (title, body) => (body ? `<section class="card-block"><h2>${esc(title)}</h2>${body}</section>` : "");
  const claims = paper.claims
    .map((claim) => {
      const place = [claim.section, claim.page ? `page ${claim.page}` : ""].filter(Boolean).join(" · ");
      const footer = place ? `<footer>${esc(place)}</footer>` : "";
      return `<blockquote class="claim"><p>${esc(claim.text)}</p>${footer}</blockquote>`;
    })
    .join("");
  const sourceLinks = [
    linkPair("DOI", paper.doi ? `https://doi.org/${paper.doi}` : ""),
    linkPair("arXiv", paper.arxivId ? `https://arxiv.org/abs/${paper.arxivId}` : ""),
  ]
    .filter(Boolean)
    .join("");
  return `<a class="back" href="#/papers">Papers</a>
    <p class="kicker">${esc(paper.venue || "Paper")} · ${esc(ACTION_LABEL[paper.action] || "")}</p>
    <h1>${esc(paper.title)}</h1>
    <p class="meta">${esc(paperMeta(paper))}${paper.date ? ` · ${esc(formatDay(paper.date))}` : ""}</p>
    ${skim}
    <p class="links">${sourceLinks}<a href="#/ask?paper=${esc(paper.id)}">Ask about this paper</a></p>
    ${block("Research problem", `<p>${esc(paper.problem)}</p>`)}
    ${block("Main contribution", `<p>${esc(paper.contribution)}</p>`)}
    ${block("Method", `<p>${esc(paper.method)}</p>`)}
    ${block("Datasets", stringList(paper.datasets))}
    ${block("Benchmarks", stringList(paper.benchmarks))}
    ${block("Main results", stringList(paper.results))}
    ${block("Key claims", claims)}
    ${block("Strengths", stringList(paper.strengths))}
    ${block("Limitations", stringList(paper.limitations))}
    ${block("Relevance to the topic", `<p>${esc(paper.relevance)}</p>`)}`;
}

function viewReport(run) {
  const names = (items) => (items.length ? `<ul>${items.map((item) => `<li>${esc(item)}</li>`).join("")}</ul>` : "");
  const gaps = run.gaps
    .map(
      (gap) =>
        `<article class="gap"><h3>${esc(gap.title)}</h3><p>${esc(gap.description)}</p>${paperLinks(run, gap.paperIds)}</article>`,
    )
    .join("");
  const ideas = run.ideas
    .map(
      (idea) => `<article class="idea">
        <h3>${esc(idea.title)}</h3>
        <p>${esc(idea.hypothesis)}</p>
        <p>${esc(idea.direction)}</p>
        ${paperLinks(run, idea.paperIds)}
      </article>`,
    )
    .join("");
  const history =
    run.historyPeriods > 0
      ? `Compared with ${run.historyPeriods} earlier ${run.historyPeriods === 1 ? "week" : "weeks"}.`
      : "No earlier week was on file.";
  return `<p class="kicker">Weekly report</p>
    <div class="page-head"><h1>${esc(formatPeriod(run))}</h1>${stamp(run.status, false)}</div>
    <p class="quiet">${esc(history)}</p>
    <div class="prose">
      ${reportSection("Executive summary", `<p class="lede">${esc(run.executiveSummary)}</p>`)}
      ${reportSection("Most important developments", findings(run, run.developments))}
      ${reportSection("Emerging directions", findings(run, run.directions))}
      ${reportSection("Methods gaining attention", findings(run, run.methods))}
      ${reportSection("New datasets and benchmarks", names([...run.datasets, ...run.benchmarks]))}
      ${reportSection("Contradictory findings", findings(run, run.contradictions))}
      ${reportSection("Changes from previous weeks", stringList(run.changes))}
      ${reportSection("Research gaps", gaps)}
      ${reportSection("Research ideas", ideas, "ideas")}
      ${reportSection("Recommended reading", readingOrder(run))}
    </div>`;
}

function viewRuns(topic, run) {
  const rows = topic.runs
    .map((item) => {
      const currentMark = run && item.id === run.id ? "On the desk" : "Read";
      return `<li class="run-item">
        <a class="run-row" href="#/week" data-open-run="${esc(item.id)}">
          <span class="run-period">${esc(formatPeriod(item))}</span>
          <span class="run-meta">${esc(item.summary.papersSelected)} kept · ${esc(item.summary.deepReads)} read · ${esc(formatDuration(item.durationSeconds))}</span>
          <span>${stamp(item.status, false)} <span class="quiet">${esc(currentMark)}</span></span>
        </a>
        <button class="run-clear" type="button" data-clear-run="${esc(item.id)}" aria-label="Clear this run">Clear</button>
      </li>`;
    })
    .join("");
  const clearAll = topic.runs.length
    ? `<button class="button" type="button" id="clear-topic-runs">Clear all runs</button>`
    : "";
  return `<div class="page-head"><h1>Runs</h1>${clearAll}</div>
    <p class="quiet">${esc(topic.name)}</p>
    ${rows ? `<ul class="run-list">${rows}</ul>` : `<p class="empty">No runs yet for this topic.</p>`}`;
}

function threadKey(paperId) {
  return paperId ? `paper:${paperId}` : `week:${state.runId}`;
}

function suggestions(paper) {
  if (paper) {
    return ["What is the contribution?", "Where is this weak?", "What is the evidence?"];
  }
  return ["What changed this week?", "Where do the papers disagree?", "What should I read first?"];
}

function replyTo(question, run, paper) {
  const q = question.toLowerCase();
  if (paper) {
    if (/weak|limit|fail|risk/.test(q)) {
      return {
        paragraphs: paper.limitations.length ? paper.limitations : [paper.contribution],
        cites: [{ paperId: paper.id, note: "Limitations" }],
      };
    }
    if (/evidence|claim|page|result/.test(q)) {
      const lines = paper.claims.map((claim) => claim.text);
      return {
        paragraphs: lines.length ? lines : ["This card has no page-level claim."],
        cites: paper.claims.map((claim) => ({
          paperId: paper.id,
          note: [claim.section, claim.page ? `p. ${claim.page}` : ""].filter(Boolean).join(", "),
        })),
      };
    }
    if (/method|how/.test(q)) {
      return { paragraphs: [paper.method], cites: [{ paperId: paper.id, note: "Method" }] };
    }
    return {
      paragraphs: [paper.contribution],
      cites: [{ paperId: paper.id, note: "Contribution" }],
    };
  }
  if (/disagree|contradict|compet/.test(q)) {
    const items = run.contradictions;
    return {
      paragraphs: items.length ? items.map((item) => item.text) : ["This week has no recorded disagreement."],
      cites: items.flatMap((item) => item.paperIds.map((paperId) => ({ paperId, note: "" }))),
    };
  }
  if (/read first|reading|start/.test(q)) {
    return {
      paragraphs: ["Start with the essential shelf, then the useful papers if you want the counter-result."],
      cites: run.readingOrder.essential.map((paperId) => ({ paperId, note: "Essential" })),
    };
  }
  if (/change|history|last|previous/.test(q)) {
    return { paragraphs: run.changes, cites: [] };
  }
  return {
    paragraphs: [run.executiveSummary],
    cites: run.developments.flatMap((item) => item.paperIds.map((paperId) => ({ paperId, note: "" }))),
  };
}

function uniqueCites(cites) {
  const seen = new Set();
  return cites.filter((cite) => {
    const key = `${cite.paperId}:${cite.note}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function renderCites(run, cites) {
  const items = uniqueCites(cites)
    .map((cite) => {
      const paper = paperById(run, cite.paperId);
      if (!paper) return "";
      const note = cite.note ? ` <span class="quiet">${esc(cite.note)}</span>` : "";
      return `<li><a href="#/papers/${esc(paper.id)}">${esc(paper.title)}</a>${note}</li>`;
    })
    .filter(Boolean);
  if (!items.length) return "";
  return `<ul class="cites">${items.join("")}</ul>`;
}

function renderThread(run, turns) {
  if (!turns.length) return "";
  return `<ol class="thread">${turns
    .map((turn) => {
      if (turn.role === "you") {
        return `<li class="turn you"><p class="turn-label">You</p><p>${esc(turn.text)}</p></li>`;
      }
      const paragraphs = turn.paragraphs.map((paragraph) => `<p>${esc(paragraph)}</p>`).join("");
      const aside = turn.note ? `<p class="quiet">${esc(turn.note)}</p>` : "";
      return `<li class="turn"><p class="turn-label">From the cards</p>${paragraphs}${renderCites(run, turn.cites)}${aside}</li>`;
    })
    .join("")}</ol>`;
}

function viewAsk(run, paperId) {
  const paper = paperId ? paperById(run, paperId) : null;
  const key = threadKey(paper ? paper.id : null);
  const turns = state.threads[key] || [];
  const context = paper
    ? `<p class="ask-context">Asking about <a href="#/papers/${esc(paper.id)}">${esc(paper.title)}</a>. <a href="#/ask">Ask about the week instead</a>.</p>`
    : `<p class="ask-context">Asking about ${esc(formatPeriod(run))}. Open a paper to narrow the question.</p>`;
  const prompts = suggestions(paper)
    .map((prompt) => `<button type="button" data-suggest="${esc(prompt)}">${esc(prompt)}</button>`)
    .join("");
  return `<p class="kicker">Ask</p>
    <h1>${paper ? "This paper" : "This week"}</h1>
    ${context}
    <div class="suggest">${prompts}</div>
    ${renderThread(run, turns)}
    <form class="composer" id="ask-form">
      <textarea id="ask-input" name="question" rows="2" placeholder="Ask a question the card can answer" aria-label="Question">${esc(state.draft)}</textarea>
      <button class="primary" type="submit">Ask</button>
    </form>
    <p class="note">${
      state.live
        ? "Answers stay inside the cards on this shelf. NVIDIA NIM answers when it is configured; otherwise the local model does."
        : "Can't reach the desk server, so this can't ask anything right now."
    }</p>`;
}

function viewNewTopic() {
  const nt = state.newTopic;
  const statusLine = nt.status
    ? `<p class="status-line" data-tone="${esc(nt.tone || "")}">${esc(nt.status)}</p>`
    : "";

  if (nt.step === "review") {
    const chips = nt.keywords.length
      ? nt.keywords.map((keyword) => `<li class="keyword-chip">${esc(keyword)}</li>`).join("")
      : `<li class="keyword-chip" data-empty="true">No keywords suggested; the topic will start with none.</li>`;
    return `<p class="kicker">New topic</p>
      <h1>New topic</h1>
      <div class="panel">
        <div class="keyword-review">
          <h2>Suggested keywords</h2>
          <ul class="keyword-chips">${chips}</ul>
          <div class="form-actions">
            <button class="primary" id="confirm-topic-button" type="button"${nt.pending ? " disabled" : ""}>Create topic and start pipeline</button>
            <button class="button" id="cancel-topic-button" type="button"${nt.pending ? " disabled" : ""}>Back</button>
          </div>
        </div>
        ${statusLine}
      </div>`;
  }

  return `<p class="kicker">New topic</p>
    <h1>New topic</h1>
    <p class="empty">
      Name it and, optionally, describe it. The local model will suggest keywords to review
      before the topic is created and its pipeline starts.
    </p>
    <div class="panel">
      <form id="new-topic-form" class="topic-form" novalidate>
        <div class="field">
          <label for="new-topic-name">Name</label>
          <input
            type="text"
            id="new-topic-name"
            name="name"
            required
            placeholder="e.g. Quantum Error Correction"
            autocomplete="off"
            value="${esc(nt.name)}"
          />
          <p class="quiet" id="new-topic-id-preview">${nt.name ? `Topic id: ${esc(slugify(nt.name)) || "—"}` : "The topic id is derived from the name."}</p>
        </div>
        <div class="field">
          <label for="new-topic-description">Description <span class="quiet">(optional)</span></label>
          <textarea
            id="new-topic-description"
            name="description"
            rows="3"
            placeholder="What this topic covers, to guide the keyword suggestions"
          >${esc(nt.description || "")}</textarea>
        </div>
        <div class="form-actions">
          <button class="primary" type="submit" id="suggest-topic-button"${nt.pending ? " disabled" : ""}>${
            nt.pending ? "Asking the model…" : "Suggest keywords"
          }</button>
        </div>
      </form>
      ${statusLine}
    </div>`;
}

function pageName(parts) {
  return parts[0] || "week";
}

function render() {
  const { topic, run } = current();
  const route = parseRoute();
  const name = pageName(route.parts);
  let body = "";
  if (name === "new") {
    body = viewNewTopic();
  } else if (!topic) {
    body = state.live
      ? `<h1>No topic</h1><p class="empty">Add a topic, then run a week. It will show up here.</p>`
      : `<h1>Can't reach the desk server</h1><p class="empty">Start it with <code>research-agent desk</code>, then reload this page.</p>`;
  } else if (name === "runs") {
    if (route.parts[1]) state.runId = route.parts[1];
    const selected = runById(topic, state.runId);
    state.runId = selected ? selected.id : null;
    body = viewRuns(topic, selected);
  } else if (!run) {
    body = `<h1>${esc(topic.name)}</h1><p class="empty">No run is stored for this topic yet.</p>`;
  } else if (name === "papers" && route.parts[1]) body = viewPaper(run, route.parts[1]);
  else if (name === "papers") body = viewPapers(run);
  else if (name === "report") body = viewReport(run);
  else if (name === "ask") body = viewAsk(run, route.params.get("paper"));
  else body = viewWeek(run);

  const nav = [
    ["week", "This week", "#/week"],
    ["papers", "Papers", "#/papers"],
    ["report", "Report", "#/report"],
    ["runs", "Runs", "#/runs"],
    ["ask", "Ask", "#/ask"],
  ]
    .map(([id, label, href]) => {
      const currentPage = name === id ? ' aria-current="page"' : "";
      return `<a href="${href}"${currentPage}>${label}</a>`;
    })
    .join("");

  const topicOptions = topics()
    .map(
      (item) =>
        `<option value="${esc(item.id)}"${topic && item.id === topic.id ? " selected" : ""}>${esc(item.name)}</option>`,
    )
    .join("");
  const hasRuns = Boolean(topic && topic.runs.length);
  const runOptions = hasRuns
    ? topic.runs
        .map(
          (item) =>
            `<option value="${esc(item.id)}"${item.id === state.runId ? " selected" : ""}>${esc(formatPeriod(item))}</option>`,
        )
        .join("")
    : "";
  const runSwitcher = hasRuns
    ? `<label class="quiet" for="run">Run</label>
        <select class="switcher" id="run" aria-label="Run">${runOptions}</select>`
    : "";

  const titles = {
    week: "This week",
    papers: "Papers",
    report: "Report",
    runs: "Runs",
    ask: "Ask",
    new: "New topic",
  };
  document.title = `Desk · ${titles[name] || "This week"}`;

  document.getElementById("app").innerHTML = `<header class="topbar">
      <div class="brand-group">
        <a class="brand" href="#/week">Desk</a>
        <a class="brand-action" href="#/new"${name === "new" ? ' aria-current="page"' : ""}>New topic</a>
      </div>
      <nav class="nav" aria-label="Desk">${nav}</nav>
      <div class="tools">
        <label class="quiet" for="topic">Topic</label>
        <select class="switcher" id="topic" aria-label="Topic">${topicOptions}</select>
        ${runSwitcher}
      </div>
    </header>
    <main id="main">${body}</main>
    <footer class="footer">${
      state.live
        ? "Reading the local library."
        : "Can't reach the desk server right now."
    }</footer>`;

  persist();
  const section = route.params.get("section");
  if (section) document.getElementById(section)?.scrollIntoView();
  const main = document.getElementById("main");
  if (state.moveFocus && main) {
    main.tabIndex = -1;
    main.focus();
    state.moveFocus = false;
  }
}

function persist() {
  const payload = {
    topicId: state.topicId,
    runId: state.runId,
    threads: state.threads,
  };
  sessionStorage.setItem("desk-state", JSON.stringify(payload));
}

async function ask(question, paperId) {
  const text = question.trim();
  if (!text || state.pending) return;
  const { run } = current();
  if (!run) return;
  const paper = paperId ? paperById(run, paperId) : null;
  const key = threadKey(paper ? paper.id : null);
  const turns = state.threads[key] || [];
  const you = { role: "you", text };
  if (!state.live) {
    const answer = replyTo(text, run, paper);
    state.threads[key] = turns.concat(you, {
      role: "desk",
      paragraphs: answer.paragraphs,
      cites: answer.cites,
    });
    state.draft = "";
    return;
  }
  state.pending = true;
  state.draft = "";
  state.threads[key] = turns.concat(you, {
    role: "desk",
    paragraphs: ["Asking the cards…"],
    cites: [],
  });
  render();
  try {
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: text,
        topicId: state.topicId,
        runId: state.runId,
        paperId: paper ? paper.id : null,
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "The model did not answer.");
    state.threads[key] = turns.concat(you, {
      role: "desk",
      paragraphs: payload.paragraphs,
      cites: payload.cites || [],
      note: payload.note || "",
    });
  } catch (error) {
    state.threads[key] = turns.concat(you, {
      role: "desk",
      paragraphs: [error instanceof Error ? error.message : "The model did not answer."],
      cites: [],
    });
  } finally {
    state.pending = false;
  }
}

async function suggestTopicKeywords(name, description) {
  state.newTopic = { ...state.newTopic, name, description, pending: true, status: "", tone: null };
  render();
  try {
    const response = await fetch("/api/topics/suggest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, description }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || "Keyword suggestion failed.");
    state.newTopic = {
      ...state.newTopic,
      step: "review",
      id: slugify(name),
      keywords: payload.keywords || [],
      pending: false,
      status: "",
      tone: null,
    };
  } catch (error) {
    state.newTopic = {
      ...state.newTopic,
      pending: false,
      status: error instanceof Error ? error.message : "Could not reach the desk server.",
      tone: "error",
    };
  }
  render();
}

async function refreshShelf() {
  try {
    const response = await fetch("/api/shelf");
    if (response.ok) {
      const shelf = await response.json();
      if (shelf.live && Array.isArray(shelf.topics)) {
        window.DESK = shelf;
        state.live = true;
      }
    }
  } catch {
    // Keep whatever was loaded before; the footer already reflects reachability.
  }
  state.runId = null;
  location.hash = "#/runs";
  render();
}

async function deleteRun(runId) {
  try {
    await fetch(`/api/runs/${encodeURIComponent(runId)}`, { method: "DELETE" });
  } catch {
    // The shelf refetch below reflects whatever actually happened server-side.
  }
  await refreshShelf();
}

async function clearTopicRuns(topicId) {
  try {
    await fetch(`/api/topics/${encodeURIComponent(topicId)}/runs`, { method: "DELETE" });
  } catch {
    // The shelf refetch below reflects whatever actually happened server-side.
  }
  await refreshShelf();
}

async function createTopic() {
  const nt = state.newTopic;
  state.newTopic = { ...nt, pending: true, status: "", tone: null };
  render();
  try {
    const response = await fetch("/api/topics", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: nt.id, name: nt.name, keywords: nt.keywords }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || "Could not create the topic.");
    state.newTopic = {
      ...nt,
      pending: false,
      status: `Started. "${nt.name}" is running in the background; check "This week" shortly.`,
      tone: "success",
    };
  } catch (error) {
    state.newTopic = {
      ...nt,
      pending: false,
      status: error instanceof Error ? error.message : "Could not reach the desk server.",
      tone: "error",
    };
  }
  render();
}

function onClick(event) {
  if (event.target.id === "confirm-topic-button") {
    void createTopic();
    return;
  }
  if (event.target.id === "cancel-topic-button") {
    state.newTopic = {
      step: "form",
      id: "",
      name: state.newTopic.name,
      description: state.newTopic.description,
      keywords: [],
      pending: false,
      status: "",
      tone: null,
    };
    render();
    return;
  }
  if (event.target.id === "clear-topic-runs") {
    const { topic } = current();
    if (!topic) return;
    if (!confirm(`Clear all runs for ${topic.name}? This cannot be undone.`)) return;
    void clearTopicRuns(topic.id);
    return;
  }
  const clearRun = event.target.closest("[data-clear-run]");
  if (clearRun) {
    if (!confirm("Clear this run? This cannot be undone.")) return;
    void deleteRun(clearRun.dataset.clearRun);
    return;
  }
  if (event.target.closest("a[href^='#/']")) state.moveFocus = true;
  const opener = event.target.closest("[data-open-run]");
  if (opener) state.runId = opener.dataset.openRun;
  const filter = event.target.closest("[data-filter]");
  if (filter) {
    state.filter = filter.dataset.filter;
    render();
    return;
  }
  const suggest = event.target.closest("[data-suggest]");
  if (suggest) {
    const paperId = parseRoute().params.get("paper");
    void ask(suggest.dataset.suggest, paperId).then(() => {
      state.moveFocus = false;
      render();
      document.getElementById("ask-input")?.focus();
    });
  }
}

function onSubmit(event) {
  const form = event.target;
  if (form.id === "new-topic-form") {
    event.preventDefault();
    const data = new FormData(form);
    const name = String(data.get("name") || "").trim();
    const description = String(data.get("description") || "").trim();
    if (!name) return;
    void suggestTopicKeywords(name, description);
    return;
  }
  if (form.id !== "ask-form") return;
  event.preventDefault();
  const paperId = parseRoute().params.get("paper");
  void ask(new FormData(form).get("question") || "", paperId).then(() => {
    render();
    document.getElementById("ask-input")?.focus();
  });
}

function onInput(event) {
  if (event.target.id === "paper-search") {
    state.query = event.target.value;
    const { run } = current();
    const list = document.getElementById("paper-list");
    if (list) list.innerHTML = renderPaperList(run);
    return;
  }
  if (event.target.id === "ask-input") {
    state.draft = event.target.value;
    return;
  }
  if (event.target.id === "new-topic-name") {
    const slug = slugify(event.target.value);
    const preview = document.getElementById("new-topic-id-preview");
    if (preview) preview.textContent = slug ? `Topic id: ${slug}` : "The topic id is derived from the name.";
    return;
  }
  if (event.target.id === "new-topic-description") state.newTopic.description = event.target.value;
}

function onChange(event) {
  if (event.target.id === "topic") {
    state.topicId = event.target.value;
    state.runId = null;
    state.filter = "all";
    state.query = "";
    location.hash = "#/week";
    render();
    return;
  }
  if (event.target.id === "run") {
    state.runId = event.target.value;
    const route = parseRoute();
    if (pageName(route.parts) === "runs") location.hash = `#/runs/${state.runId}`;
    render();
  }
}

function restore() {
  try {
    const saved = JSON.parse(sessionStorage.getItem("desk-state") || "{}");
    state.topicId = saved.topicId || null;
    state.runId = saved.runId || null;
    state.threads = saved.threads || {};
  } catch {
    state.threads = {};
  }
}

restore();
window.addEventListener("hashchange", () => {
  state.moveFocus = true;
  render();
});
document.addEventListener("click", onClick);
document.addEventListener("submit", onSubmit);
document.addEventListener("input", onInput);
document.addEventListener("change", onChange);

async function boot() {
  try {
    const response = await fetch("/api/shelf");
    if (response.ok) {
      const shelf = await response.json();
      if (shelf.live && Array.isArray(shelf.topics)) {
        window.DESK = shelf;
        state.live = true;
      }
    }
  } catch {
    state.live = false;
  }
  if (!location.hash) location.hash = "#/week";
  else render();
}

void boot();

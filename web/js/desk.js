/* Reading desk: renders the shelf from /api/shelf and asks through /api/ask. */

const STATUS_LABEL = {
  completed: "Complete",
  degraded: "Degraded",
  failed: "Failed",
  running: "Running",
  paused: "Paused",
};

const STAGE_LABEL = {
  plan_queries: "Planning searches",
  discover: "Searching sources",
  broaden: "Broadening the search",
  classify: "Screening papers",
  select: "Choosing papers",
  acquire: "Downloading PDFs",
  parse: "Reading PDFs",
  analyze: "Analysing papers",
  synthesize: "Writing the synthesis",
  ideate: "Finding gaps and ideas",
  report: "Writing the report",
  persist: "Saving",
};

const DECISION_LABEL = {
  selected_deep_read: "Kept for a deep read",
  selected_summarize: "Kept for a summary",
  action_ignore: "Dropped: the screener judged it off-topic",
  below_threshold: "Dropped: relevance below the threshold",
  already_analyzed: "Skipped: already read in an earlier run",
  limit_reached: "Dropped: over this run's paper limit",
};

const POLL_MS = 5000;
const AWAIT_RUN_MS = 5 * 60 * 1000;

const SOURCES = [
  ["openalex", "OpenAlex"],
  ["semantic_scholar", "Semantic Scholar"],
  ["arxiv", "arXiv"],
];

const LIMITS = [
  ["max_candidates", "Candidates found", 1],
  ["max_classified", "Papers screened", 1],
  ["max_downloads", "PDFs downloaded", 0],
  ["max_deep_reads", "Deep reads", 0],
];


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
  topicsPending: false,
  topicsStatus: null,
  awaitingRun: null,
  health: null,
  screened: null,
  screenedFilter: "all",
  finishedNotice: null,
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
    <p class="quiet">${esc(runProgress(run) || [formatDuration(run.durationSeconds), ...run.models].join(" · "))}</p>
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
    <p class="quiet">${esc(formatPeriod(run))} · ${esc(run.papers.length)} kept${
      run.summary.papersClassified > run.papers.length
        ? ` · <a href="#/screened">See all ${esc(run.summary.papersClassified)} screened, including the dropped ones</a>`
        : ""
    }</p>
    <div class="filters">
      ${filterButton("all", `All ${run.papers.length}`)}
      ${filterButton("deep_read", `Deep reads ${deep}`)}
      ${filterButton("summarize", `Summaries ${summaries}`)}
      ${abstracts ? filterButton("abstract", `Abstract only ${abstracts}`) : ""}
      <input class="search" id="paper-search" type="search" placeholder="Search titles" value="${esc(state.query)}" aria-label="Search titles" />
    </div>
    <div id="paper-list">${renderPaperList(run)}</div>`;
}

function screeningLine(screening) {
  const decision = DECISION_LABEL[screening.decision] || "";
  const score = typeof screening.score === "number" ? `relevance ${screening.score.toFixed(2)}` : "";
  return [decision, score].filter(Boolean).join(" · ");
}

function whyKept(screening) {
  if (!screening || !screening.decision) return "";
  const reason = screening.reason ? `<p class="quiet">${esc(screening.reason)}</p>` : "";
  return `<section class="card-block"><h2>Why it's on the shelf</h2><p>${esc(screeningLine(screening))}</p>${reason}</section>`;
}

function sourceHref(paper) {
  if (paper.doi) return `https://doi.org/${paper.doi}`;
  if (paper.arxivId) return `https://arxiv.org/abs/${paper.arxivId}`;
  return "";
}

async function loadScreened(runId) {
  state.screened = { runId, pending: true, papers: [] };
  try {
    const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/screened`);
    const payload = await response.json();
    if (!response.ok || !Array.isArray(payload.papers)) throw new Error("bad response");
    state.screened = { runId, papers: payload.papers };
  } catch {
    state.screened = { runId, papers: [], error: "Can't load the screened papers right now." };
  }
  if (pageName(parseRoute().parts) === "screened") render();
}

function viewScreened(run) {
  const screened = state.screened && state.screened.runId === run.id ? state.screened : { pending: true, papers: [] };
  const all = screened.papers;
  const kept = all.filter((paper) => paper.selected);
  const shown = state.screenedFilter === "kept" ? kept : state.screenedFilter === "dropped" ? all.filter((paper) => !paper.selected) : all;
  const filter = (id, label) =>
    `<button type="button" data-screen-filter="${id}" aria-pressed="${state.screenedFilter === id}">${esc(label)}</button>`;
  const rows = shown
    .map((paper) => {
      const href = paper.selected ? `#/papers/${paper.id}` : sourceHref(paper);
      const external = !paper.selected && href ? ' target="_blank" rel="noopener"' : "";
      const title = href ? `<a href="${esc(href)}"${external}>${esc(paper.title)}</a>` : esc(paper.title);
      const score = typeof paper.score === "number" ? paper.score.toFixed(2) : "–";
      return `<li class="screen-row" data-kept="${paper.selected}">
        <span class="screen-score" aria-label="Relevance ${esc(score)}">${esc(score)}</span>
        <div>
          <p class="screen-title">${title}</p>
          <p class="paper-row-meta">${esc(DECISION_LABEL[paper.decision] || paper.decision || "")}</p>
          ${paper.reason ? `<p class="paper-row-dek">${esc(paper.reason)}</p>` : ""}
        </div>
      </li>`;
    })
    .join("");
  const body = screened.pending
    ? `<p class="empty">Loading the screened papers…</p>`
    : screened.error
      ? statusMessage(screened.error, "error")
      : rows
        ? `<ul class="screen-list">${rows}</ul>`
        : `<p class="empty">No papers match.</p>`;
  return `<a class="back" href="#/papers">Papers</a>
    <h1>Screened papers</h1>
    <p class="quiet">${esc(formatPeriod(run))} · ${esc(all.length)} screened · ${esc(kept.length)} kept. Highest relevance first.</p>
    <div class="filters">
      ${filter("all", `All ${all.length}`)}
      ${filter("kept", `Kept ${kept.length}`)}
      ${filter("dropped", `Dropped ${all.length - kept.length}`)}
    </div>
    ${body}`;
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
    paper.hasPdf
      ? `<a href="/api/papers/${encodeURIComponent(paper.id)}/pdf" target="_blank" rel="noopener">Open PDF</a>`
      : "",
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
    ${block("Experimental setup", paper.setup ? `<p>${esc(paper.setup)}</p>` : "")}
    ${block("Datasets", stringList(paper.datasets))}
    ${block("Benchmarks", stringList(paper.benchmarks))}
    ${block("Main results", stringList(paper.results))}
    ${block("Key claims", claims)}
    ${block("Strengths", stringList(paper.strengths))}
    ${block("Limitations", stringList(paper.limitations))}
    ${block("Related work", stringList(paper.relatedWork || []))}
    ${block("Relevance to the topic", `<p>${esc(paper.relevance)}</p>`)}
    ${whyKept(paper.screening)}`;
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

function minutesSince(iso) {
  const minutes = Math.floor((Date.now() - Date.parse(iso)) / 60000);
  if (minutes < 1) return "under a minute";
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}

/* Wait for a topic's next run: done once its newest run differs from the one seen now. */
function awaitRun(topicId) {
  const latestId = topics().find((topic) => topic.id === topicId)?.runs[0]?.id;
  state.awaitingRun = { topicId, latestId, since: Date.now() };
}

/* Where a run is, or where a failed run stopped; empty for a finished one. */
function runProgress(run) {
  const stage = STAGE_LABEL[run.stage] || "Starting";
  if (run.status === "running") return `${stage} · ${minutesSince(run.startedAt)} so far`;
  if (run.status === "failed" && run.stage) return `Stopped while ${stage.toLowerCase()}`;
  return "";
}

function runningRuns() {
  return topics().flatMap((topic) =>
    topic.runs.filter((run) => run.status === "running").map((run) => ({ topic, run })),
  );
}

function bannerHtml() {
  const items = runningRuns().map(
    ({ topic, run }) => `<p><strong>${esc(topic.name)}</strong> · ${esc(runProgress(run))}</p>`,
  );
  if (!items.length && state.awaitingRun) items.push("<p>Starting the run…</p>");
  const notice = state.finishedNotice;
  if (notice) {
    items.push(`<p class="banner-notice" data-tone="${esc(notice.tone)}">${esc(notice.text)}
      <button class="banner-dismiss" type="button" id="dismiss-notice" aria-label="Dismiss">×</button></p>`);
  }
  return items.length ? `<div class="run-banner">${items.join("")}</div>` : "";
}

function updateBanner() {
  const banner = document.getElementById("run-banner");
  if (banner) banner.innerHTML = bannerHtml();
}

function onFormPage() {
  const route = parseRoute();
  return pageName(route.parts) === "new" || (pageName(route.parts) === "topics" && Boolean(route.parts[1]));
}

let pollTimer = null;

function schedulePoll() {
  if (pollTimer || (!runningRuns().length && !state.awaitingRun)) return;
  pollTimer = setTimeout(() => void poll(), POLL_MS);
}

async function poll() {
  pollTimer = null;
  const before = new Map(runningRuns().map(({ topic, run }) => [run.id, topic.name]));
  await loadShelf();
  let changed = false;
  for (const topic of topics()) {
    for (const run of topic.runs) {
      if (before.has(run.id) && run.status !== "running") {
        const label = STATUS_LABEL[run.status] || run.status;
        state.finishedNotice = {
          text: `${topic.name} finished: ${label}.`,
          tone: run.status === "failed" ? "error" : "success",
        };
        changed = true;
      } else if (!before.has(run.id) && run.status === "running") {
        changed = true;
      }
    }
  }
  const awaited = state.awaitingRun;
  if (awaited) {
    const latest = topics().find((topic) => topic.id === awaited.topicId)?.runs[0]?.id;
    if (latest !== awaited.latestId || Date.now() - awaited.since > AWAIT_RUN_MS) state.awaitingRun = null;
  }
  // A full render would wipe what is being typed in a form, so those pages only refresh the banner.
  if (changed && !onFormPage()) render();
  else updateBanner();
  schedulePoll();
}

function viewRuns(topic, run) {
  const rows = topic.runs
    .map((item) => {
      const currentMark = run && item.id === run.id ? "On the desk" : "Read";
      return `<li class="run-item">
        <a class="run-row" href="#/week" data-open-run="${esc(item.id)}">
          <span class="run-period">${esc(formatPeriod(item))}</span>
          <span class="run-meta">${esc(runProgress(item) || `${item.summary.papersSelected} kept · ${item.summary.deepReads} read · ${formatDuration(item.durationSeconds)}`)}</span>
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
    <p class="note">Answers stay inside the cards on this shelf. NVIDIA NIM answers when it is configured; otherwise the local model does.</p>`;
}

function statusMessage(text, tone) {
  return text ? `<p class="status-line" data-tone="${esc(tone || "")}" role="status">${esc(text)}</p>` : "";
}

function topicMeta(topic) {
  const settings = topic.settings;
  const sources = SOURCES.filter(([key]) => settings.discovery[key]).map(([, label]) => label);
  const runs = `${topic.runs.length} ${topic.runs.length === 1 ? "run" : "runs"}`;
  return [`${settings.lookback_days}-day lookback`, sources.join(", "), runs].join(" · ");
}

function viewTopics() {
  const all = topics();
  const busy = state.topicsPending ? " disabled" : "";
  const rows = all
    .map((topic) => {
      const settings = topic.settings;
      const running = topic.runs.some((run) => run.status === "running");
      const canRun = settings.enabled && !running;
      const why = !settings.enabled ? "Enable the topic to run it" : running ? "A run is already in progress" : "";
      const keywords = settings.keywords.length ? settings.keywords.join(", ") : "No keywords";
      return `<li class="run-item">
        <div class="run-row topic-row">
          <span>
            <span class="run-period">${esc(topic.name)}</span>
            <span class="run-meta">${esc(topicMeta(topic))}</span>
            <span class="run-meta">${esc(keywords)}</span>
          </span>
          <span>${settings.enabled ? "" : stamp("paused", false)}${running ? stamp("running", false) : ""}</span>
          <span class="topic-actions">
            <button class="button" type="button" data-run-topic="${esc(topic.id)}" aria-label="Run ${esc(topic.name)} now"${canRun ? busy : " disabled"}${why ? ` title="${esc(why)}"` : ""}>Run now</button>
            <button class="button" type="button" data-toggle-topic="${esc(topic.id)}" aria-label="${settings.enabled ? "Pause" : "Enable"} ${esc(topic.name)}"${busy}>${settings.enabled ? "Pause" : "Enable"}</button>
            <a class="button" href="#/topics/${esc(topic.id)}" aria-label="Edit ${esc(topic.name)}">Edit</a>
            <button class="run-clear" type="button" data-delete-topic="${esc(topic.id)}" aria-label="Delete ${esc(topic.name)}"${busy}>Delete</button>
          </span>
        </div>
      </li>`;
    })
    .join("");
  const status = state.topicsStatus || {};
  return `<div class="page-head"><h1>Topics</h1><a class="button" href="#/new">New topic</a></div>
    <p class="quiet">Runs start only when you press Run now. Paused topics can't be run until enabled.</p>
    ${statusMessage(status.text, status.tone)}
    ${rows ? `<ul class="run-list">${rows}</ul>` : `<p class="empty">No topics yet. Create one to start a weekly run.</p>`}`;
}

function settingsFields(settings) {
  const sources = SOURCES.map(
    ([key, label]) =>
      `<label class="check"><input type="checkbox" name="${key}"${settings.discovery[key] ? " checked" : ""} /> ${esc(label)}</label>`,
  ).join("");
  const limits = LIMITS.map(
    ([key, label, min]) => `<div class="field">
        <label for="limit-${key}">${esc(label)}</label>
        <input type="number" id="limit-${key}" name="${key}" min="${min}" required value="${esc(settings.limits[key])}" />
      </div>`,
  ).join("");
  return `<div class="field">
      <label for="topic-lookback">Lookback (days)</label>
      <input type="number" id="topic-lookback" name="lookback_days" min="1" required value="${esc(settings.lookback_days)}" />
    </div>
    <fieldset class="field">
      <legend>Sources</legend>
      <div class="checks">${sources}</div>
    </fieldset>
    <fieldset class="field">
      <legend>Limits per run</legend>
      <div class="field-row">${limits}</div>
    </fieldset>`;
}

const HEALTH_LABEL = { ok: "OK", warn: "Warning", fail: "Problem" };

function healthSummary(checks) {
  const problems = checks.filter((check) => check.status === "fail").length;
  const warnings = checks.filter((check) => check.status === "warn").length;
  if (problems) return `${problems} ${problems === 1 ? "problem" : "problems"} to fix before a run.`;
  if (warnings) return `Ready to run, with ${warnings} ${warnings === 1 ? "warning" : "warnings"}.`;
  return "All set: a run has everything it needs.";
}

function viewSetup() {
  const health = state.health || { pending: true };
  const rows = (health.checks || [])
    .map(
      (check) => `<li class="health-item">
        <span class="health-status" data-status="${esc(check.status)}">${esc(HEALTH_LABEL[check.status] || check.status)}</span>
        <div>
          <p class="health-name">${esc(check.name)}</p>
          <p class="quiet">${esc(check.detail)}</p>
          ${check.fix ? `<p class="health-fix">${esc(check.fix)}</p>` : ""}
        </div>
      </li>`,
    )
    .join("");
  const summary = health.pending
    ? statusMessage("Checking the library folder, models and sources. This can take up to a minute.", "")
    : health.error
      ? statusMessage(health.error, "error")
      : statusMessage(healthSummary(health.checks), health.checks.some((check) => check.status === "fail") ? "error" : "success");
  const firstTopic = topics().length ? "" : `<a class="primary" href="#/new">Create your first topic</a>`;
  return `<p class="kicker">Setup</p>
    <h1>Setup check</h1>
    <p class="quiet">What a weekly run needs, checked on this machine.</p>
    ${summary}
    ${rows ? `<ul class="health-list">${rows}</ul>` : ""}
    <div class="form-actions">
      <button class="button" type="button" id="recheck-health"${health.pending ? " disabled" : ""}>Check again</button>
      ${firstTopic}
    </div>`;
}

async function checkHealth() {
  state.health = { pending: true };
  render();
  try {
    const response = await fetch("/api/health");
    const payload = await response.json();
    if (!response.ok || !Array.isArray(payload.checks)) throw new Error("bad response");
    state.health = { checks: payload.checks };
  } catch {
    state.health = { checks: [], error: "Can't reach the desk server, so nothing could be checked." };
  }
  if (pageName(parseRoute().parts) === "setup") render();
}

function viewTopicEdit(topicId) {
  const topic = topics().find((item) => item.id === topicId);
  if (!topic) {
    return `<a class="back" href="#/topics">Topics</a>
      <h1>Not found</h1>
      <p class="empty">There is no topic called ${esc(topicId)}.</p>`;
  }
  const settings = topic.settings;
  const status = state.topicsStatus || {};
  return `<a class="back" href="#/topics">Topics</a>
    <h1>${esc(topic.name)}</h1>
    <p class="quiet">Topic id: ${esc(topic.id)}. The id stays fixed; everything else can change.</p>
    <div class="panel">
      <form id="topic-edit-form" class="topic-form" data-topic="${esc(topic.id)}">
        <div class="field">
          <label for="edit-name">Name</label>
          <input type="text" id="edit-name" name="name" required value="${esc(settings.name)}" />
        </div>
        <label class="check"><input type="checkbox" name="enabled"${settings.enabled ? " checked" : ""} /> Enabled</label>
        <div class="field">
          <label for="edit-keywords">Keywords <span class="quiet">(one per line)</span></label>
          <textarea id="edit-keywords" name="keywords" rows="4">${esc(settings.keywords.join("\n"))}</textarea>
        </div>
        ${settingsFields(settings)}
        <div class="form-actions">
          <button class="primary" type="submit"${state.topicsPending ? " disabled" : ""}>${state.topicsPending ? "Saving…" : "Save"}</button>
          <a class="button" href="#/topics">Cancel</a>
        </div>
      </form>
      ${statusMessage(status.text, status.tone)}
    </div>`;
}

function keywordChips(keywords) {
  if (!keywords.length) {
    return `<li class="keyword-chip" data-empty="true">No keywords yet; add some, or the topic name alone is searched.</li>`;
  }
  return keywords
    .map(
      (keyword, index) =>
        `<li class="keyword-chip">${esc(keyword)}<button type="button" class="chip-remove" data-remove-keyword="${index}" aria-label="Remove ${esc(keyword)}">×</button></li>`,
    )
    .join("");
}

function refreshChips() {
  const list = document.getElementById("keyword-chips");
  if (list) list.innerHTML = keywordChips(state.newTopic.keywords);
}

function addKeyword() {
  const input = document.getElementById("new-keyword");
  const keyword = input ? input.value.trim() : "";
  if (!keyword) return;
  const known = state.newTopic.keywords.some((item) => item.toLowerCase() === keyword.toLowerCase());
  if (!known) state.newTopic.keywords = [...state.newTopic.keywords, keyword];
  input.value = "";
  refreshChips();
  input.focus();
}

function viewNewTopic() {
  const nt = state.newTopic;
  const statusLine = statusMessage(nt.status, nt.tone);

  if (nt.step === "review") {
    const settings = nt.settings || (window.DESK && window.DESK.defaults);
    return `<p class="kicker">New topic</p>
      <h1>${esc(nt.name)}</h1>
      <p class="quiet">Topic id: ${esc(nt.id)}</p>
      <div class="panel">
        <form id="new-topic-review" class="topic-form">
          <div class="field">
            <label for="new-keyword">Keywords</label>
            <ul class="keyword-chips" id="keyword-chips">${keywordChips(nt.keywords)}</ul>
            <div class="keyword-add">
              <input type="text" id="new-keyword" autocomplete="off" placeholder="Add a keyword and press Enter" />
              <button class="button" type="button" id="add-keyword-button">Add</button>
            </div>
          </div>
          <details class="advanced"${nt.settings ? " open" : ""}>
            <summary>Advanced settings</summary>
            <div class="topic-form">${settingsFields(settings)}</div>
          </details>
          <div class="form-actions">
            <button class="primary" type="submit"${nt.pending ? " disabled" : ""}>${nt.pending ? "Creating…" : "Create topic and start pipeline"}</button>
            <button class="button" id="cancel-topic-button" type="button"${nt.pending ? " disabled" : ""}>Back</button>
          </div>
        </form>
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
  } else if (name === "setup" && state.live) {
    body = viewSetup();
  } else if (name === "topics" && state.live) {
    body = route.parts[1] ? viewTopicEdit(route.parts[1]) : viewTopics();
  } else if (!topic) {
    body = state.live
      ? `<p class="kicker">Welcome</p>
        <h1>Set up your desk</h1>
        <p class="empty">Two steps before your first weekly run.</p>
        <div class="form-actions">
          <a class="button" href="#/setup">1. Check setup</a>
          <a class="primary" href="#/new">2. Create a topic</a>
        </div>`
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
  else if (name === "screened") body = viewScreened(run);
  else if (name === "report") body = viewReport(run);
  else if (name === "ask") body = viewAsk(run, route.params.get("paper"));
  else body = viewWeek(run);

  const nav = [
    ["week", "This week", "#/week"],
    ["papers", "Papers", "#/papers"],
    ["report", "Report", "#/report"],
    ["runs", "Runs", "#/runs"],
    ["ask", "Ask", "#/ask"],
    ["topics", "Topics", "#/topics"],
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
    topics: "Topics",
    setup: "Setup check",
    screened: "Screened papers",
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
    <div id="run-banner" aria-live="polite">${bannerHtml()}</div>
    <main id="main">${body}</main>
    <footer class="footer">${
      state.live
        ? `Reading the local library. <a href="#/setup">Setup check</a>`
        : "Can't reach the desk server right now."
    }</footer>`;

  persist();
  schedulePoll();
  if (name === "setup" && state.live && !state.health) void checkHealth();
  if (name === "screened" && run && (!state.screened || state.screened.runId !== run.id)) {
    void loadScreened(run.id);
  }
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

async function loadShelf() {
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
}

async function refreshShelf() {
  await loadShelf();
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

/* Returns null on success, or the message to show. */
async function topicRequest(method, path, body) {
  try {
    const response = await fetch(path, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (response.ok) return null;
    const payload = await response.json().catch(() => ({}));
    return payload.error || "The desk server refused that change.";
  } catch {
    return "Can't reach the desk server.";
  }
}

async function topicAction(method, path, body, success) {
  state.topicsPending = true;
  state.topicsStatus = null;
  render();
  const problem = await topicRequest(method, path, body);
  await loadShelf();
  state.topicsPending = false;
  state.topicsStatus = problem ? { text: problem, tone: "error" } : { text: success, tone: "success" };
  return !problem;
}

function runSettingsFromData(data) {
  return {
    lookback_days: Number(data.get("lookback_days")),
    discovery: Object.fromEntries(SOURCES.map(([key]) => [key, data.has(key)])),
    limits: Object.fromEntries(LIMITS.map(([key]) => [key, Number(data.get(key))])),
  };
}

function settingsFromForm(form) {
  const data = new FormData(form);
  return {
    name: String(data.get("name") || "").trim(),
    enabled: data.has("enabled"),
    keywords: String(data.get("keywords") || "")
      .split("\n")
      .map((keyword) => keyword.trim())
      .filter(Boolean),
    ...runSettingsFromData(data),
  };
}

async function createTopic(form) {
  const nt = { ...state.newTopic, settings: runSettingsFromData(new FormData(form)) };
  state.newTopic = { ...nt, pending: true, status: "", tone: null };
  render();
  try {
    const response = await fetch("/api/topics", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: nt.id, name: nt.name, keywords: nt.keywords, ...nt.settings }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || "Could not create the topic.");
    await loadShelf();
    state.topicId = nt.id;
    state.runId = null;
    if (!runningRuns().some((item) => item.topic.id === nt.id)) awaitRun(nt.id);
    state.newTopic = {
      ...nt,
      pending: false,
      status: `Created "${nt.name}" and started its first run. Its progress shows at the top of the page.`,
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
  const screenFilter = event.target.closest("[data-screen-filter]");
  if (screenFilter) {
    state.screenedFilter = screenFilter.dataset.screenFilter;
    render();
    return;
  }
  if (event.target.id === "recheck-health") {
    void checkHealth();
    return;
  }
  if (event.target.id === "dismiss-notice") {
    state.finishedNotice = null;
    updateBanner();
    return;
  }
  const runTopic = event.target.closest("[data-run-topic]");
  if (runTopic) {
    const topic = topicById(runTopic.dataset.runTopic);
    void topicAction(
      "POST",
      `/api/topics/${encodeURIComponent(topic.id)}/run`,
      {},
      `Started ${topic.name}. Its progress shows at the top of the page.`,
    ).then((started) => {
      if (started && !runningRuns().some((item) => item.topic.id === topic.id)) awaitRun(topic.id);
      render();
    });
    return;
  }
  const toggleTopic = event.target.closest("[data-toggle-topic]");
  if (toggleTopic) {
    const topic = topicById(toggleTopic.dataset.toggleTopic);
    const settings = { ...topic.settings, enabled: !topic.settings.enabled };
    delete settings.id;
    void topicAction(
      "PUT",
      `/api/topics/${encodeURIComponent(topic.id)}`,
      settings,
      `${topic.name} is ${settings.enabled ? "enabled" : "paused"}.`,
    ).then(render);
    return;
  }
  const deleteTopic = event.target.closest("[data-delete-topic]");
  if (deleteTopic) {
    const topic = topicById(deleteTopic.dataset.deleteTopic);
    if (!confirm(`Delete ${topic.name} and all of its runs? Files on disk are kept. This cannot be undone.`)) return;
    void topicAction("DELETE", `/api/topics/${encodeURIComponent(topic.id)}`, undefined, `Deleted ${topic.name}.`).then(
      () => {
        if (state.topicId === topic.id) state.topicId = null;
        render();
      },
    );
    return;
  }
  const removeKeyword = event.target.closest("[data-remove-keyword]");
  if (removeKeyword) {
    const index = Number(removeKeyword.dataset.removeKeyword);
    state.newTopic.keywords = state.newTopic.keywords.filter((_, position) => position !== index);
    refreshChips();
    document.getElementById("new-keyword")?.focus();
    return;
  }
  if (event.target.id === "add-keyword-button") {
    addKeyword();
    return;
  }
  if (event.target.id === "cancel-topic-button") {
    state.newTopic = {
      step: "form",
      id: "",
      name: state.newTopic.name,
      description: state.newTopic.description,
      keywords: [],
      settings: null,
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
  if (form.id === "new-topic-review") {
    event.preventDefault();
    void createTopic(form);
    return;
  }
  if (form.id === "topic-edit-form") {
    event.preventDefault();
    const topicId = form.dataset.topic;
    // Runs are manual, so the form has no run day; keep the stored one rather than reset it.
    const settings = { ...settingsFromForm(form), scheduling: topicById(topicId).settings.scheduling };
    void topicAction("PUT", `/api/topics/${encodeURIComponent(topicId)}`, settings, `Saved ${settings.name}.`).then(
      (saved) => {
        if (saved) location.hash = "#/topics";
        else render();
      },
    );
    return;
  }
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
  if (!location.hash.startsWith("#/topics")) state.topicsStatus = null;
  render();
});
document.addEventListener("click", onClick);
document.addEventListener("submit", onSubmit);
document.addEventListener("input", onInput);
document.addEventListener("change", onChange);
document.addEventListener("keydown", (event) => {
  if (event.target.id === "new-keyword" && event.key === "Enter") {
    event.preventDefault();
    addKeyword();
  }
});

async function boot() {
  await loadShelf();
  if (!location.hash) location.hash = "#/week";
  else render();
}

void boot();

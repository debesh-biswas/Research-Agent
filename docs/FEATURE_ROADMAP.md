# Feature Roadmap

## Purpose

This roadmap converts the product and technical requirements into bounded, sequential feature
branches. It is the implementation order for the Personal Weekly AI Research Intelligence Agent
v1 and should be read with the PRD, TRD, `AGENTS.md`, and `UPDATES.md`.

Each feature must follow the repository workflow: start from clean `main`, create only its named
branch, implement and verify the bounded scope, update `UPDATES.md`, commit, merge into `main`,
re-verify, and push before the next feature begins. All commits use the configured human identity
without agent authorship or co-authorship metadata.

## Roadmap Summary

| Feature | Branch | Outcome | Depends on |
|---|---|---|---|
| F1 | `F1-project-scaffold` | Runnable Python project foundation | — |
| F2 | `F2-topic-management` | Persistent topic configuration and CLI management | F1 |
| F3 | `F3-paper-normalization-deduplication` | Canonical paper models, normalization, and deduplication | F2 |
| F4 | `F4-metadata-artifact-persistence` | Complete local metadata and artifact persistence boundaries | F2–F3 |
| F5 | `F5-academic-discovery` | Resilient OpenAlex, Semantic Scholar, and arXiv discovery | F3–F4 |
| F6 | `F6-model-provider-routing` | Local/NIM provider abstraction and capability routing | F1, F4 |
| F7 | `F7-search-query-planning` | Semantic query expansion and bounded query plans | F2, F5–F6 |
| F8 | `F8-classifier-a-integration` | Classifier A behind the shared classifier contract | F3–F4 |
| F9 | `F9-classifier-b-shadow-mode` | Classifier B, switching, shadow mode, and comparison | F6, F8 |
| F10 | `F10-paper-selection` | Deterministic triage, limits, and seen-paper handling | F4, F9 |
| F11 | `F11-pdf-acquisition` | Legal, validated, failure-isolated PDF downloads | F4, F10 |
| F12 | `F12-pdf-parsing` | Docling parsing and cached structured paper artifacts | F11 |
| F13 | `F13-paper-analysis` | Evidence-backed structured analyses and paper cards | F6, F10, F12 |
| F14 | `F14-weekly-synthesis` | Cross-paper and historical comparison | F4, F13 |
| F15 | `F15-research-ideation` | Supported research gaps and research ideas | F14 |
| F16 | `F16-report-generation` | Reproducible weekly Markdown reports | F4, F13–F15 |
| F17 | `F17-langgraph-workflow` | Complete conditional LangGraph workflow | F5–F16 |
| F18 | `F18-run-operations-scheduling` | Operational CLI, run-all, retrieval, and local scheduling | F2, F16–F17 |
| F19 | `F19-mvp-reliability-hardening` | End-to-end resilience, caching, and acceptance validation | F17–F18 |
| F20 | `F20-aws-portability-validation` | Demonstrated AWS-compatible boundaries and deployment plan | F19 |

The future branch names above are reserved by this roadmap. If requirements materially change,
update this document and `UPDATES.md` before renumbering or inserting work. Bug fixes,
documentation, tests, chores, and refactors continue to use their independent prefixes.

## F1 — Project Scaffold

- **Status:** Completed and merged.
- **Branch:** `F1-project-scaffold`.
- **Goal:** Establish the runnable, local-first Python foundation without pretending later product
  behavior exists.
- **Deliverables:** `uv` project and lockfile; `research_agent` package; Typer CLI; validated YAML,
  `.env`, and environment configuration; JSON logging; architectural package boundaries; safe
  ignore rules; README; offline tests and quality tooling.
- **Public surface:** `research-agent --help`, `research-agent --version`, and
  `research-agent config validate`.
- **Verification:** Ruff formatting/lint, strict mypy, 21 passing tests with 89.77% coverage,
  package build, CLI smoke tests, and configuration validation.
- **Acceptance:** A new contributor can sync, validate configuration, run tests, build the package,
  and understand the architecture without credentials, Docker, external APIs, or models.
- **Git:** Feature `5bcd38a`; merge `46af966`; handoff `a2cfff2`.

## F2 — Topic Management

- **Branch:** `F2-topic-management`.
- **Depends on:** F1.
- **Goal:** Make topic definitions persistent and manageable without editing YAML by hand.
- **Deliverables:** SQLite migration foundation; `topics` repository interface and SQLite adapter;
  fields for ID, name, enabled state, lookback, schedule, active/shadow classifier, source toggles,
  limits, and UTC timestamps; deterministic YAML bootstrap/import; topic add, list, enable, and
  disable services.
- **CLI:** Implement `research-agent topic add` and `research-agent topic list`; include enable and
  disable subcommands because the PRD requires them. Commands must reject duplicates and invalid
  combinations with actionable errors.
- **Tests:** Repository contract tests against temporary SQLite databases; migration idempotency;
  CLI success/error cases; duplicate IDs; enable/disable; ordering; YAML bootstrap; rollback after
  failed writes.
- **Acceptance:** A topic can be created once, listed predictably, enabled or disabled, reopened in
  a new process, and reconstructed as the existing validated topic model.
- **Out of scope:** Papers, runs, graph execution, live scheduling, and AWS persistence.
- **Git:** `feat(topics): add persistent topic management`; merge with
  `merge: F2-topic-management add persistent topic management`.

## F3 — Paper Normalization and Deduplication

- **Branch:** `F3-paper-normalization-deduplication`.
- **Depends on:** F2.
- **Goal:** Create provider-neutral paper identities and deterministic duplicate handling before
  network adapters or LLMs are introduced.
- **Deliverables:** `PaperCandidate` and source-reference schemas; Unicode, whitespace, date, URL,
  DOI, arXiv ID, title, and author normalization; stable canonical-ID policy; deduplication in the
  required priority order; configurable RapidFuzz threshold with author overlap; deterministic
  merge rules that preserve all source identifiers and the best available metadata.
- **Tests:** DOI/arXiv variants; Unicode and punctuation; missing identifiers; exact and fuzzy
  title matches; author overlap; conflicting source metadata; false-positive boundaries;
  deterministic ordering and canonical IDs.
- **Acceptance:** The same paper returned by multiple sources becomes one canonical candidate with
  auditable source provenance, while similar but distinct papers remain separate.
- **Out of scope:** Live search, database persistence beyond fixtures, and seen-paper policy.
- **Git:** `feat(papers): add normalization and deduplication`; merge with
  `merge: F3-paper-normalization-deduplication canonicalize candidate papers`.

## F4 — Metadata and Artifact Persistence

- **Branch:** `F4-metadata-artifact-persistence`.
- **Depends on:** F2–F3.
- **Goal:** Implement the complete local persistence boundary required by downstream features.
- **Deliverables:** Versioned SQLite migrations for runs, papers, paper sources, classifications,
  files, analyses, syntheses, gaps, ideas, and errors; typed repository protocols; transactional
  SQLite adapters; local artifact-storage protocol and safe topic/run paths; deterministic
  filenames; run/error models and summaries; UTC timestamps; idempotent upserts and read APIs for
  history and cache lookups.
- **Tests:** Migration upgrades and repeat runs; repository contract suite; transaction rollback;
  foreign keys; idempotent paper/source upserts; artifact path traversal rejection; atomic writes;
  run summaries; historical synthesis lookup; storage failures.
- **Acceptance:** All minimum TRD entities can be persisted and retrieved through interfaces, and
  graph code will never need direct SQL or local-path assumptions.
- **Out of scope:** S3/DynamoDB implementations, document downloading, and orchestration.
- **Git:** `feat(storage): add metadata and artifact persistence`; merge with
  `merge: F4-metadata-artifact-persistence establish local persistence boundaries`.

## F5 — Academic Discovery

- **Branch:** `F5-academic-discovery`.
- **Depends on:** F3–F4.
- **Goal:** Search the three required academic sources through one resilient async interface.
- **Deliverables:** `ResearchSource` protocol; OpenAlex, Semantic Scholar, and arXiv adapters;
  provider payload translation into `PaperCandidate`; date/limit enforcement; source-specific
  pacing; 429 and `Retry-After` handling; three-retry exponential backoff; bounded concurrency;
  per-run search cache; aggregator with partial-source failure isolation and structured errors.
- **Tests:** Static response fixtures for each adapter; pagination and date boundaries; rate limits;
  malformed records; timeouts; retry ceilings; one-source failure; all-source failure; cache hits;
  concurrency limits. Live smoke tests must be optional and excluded from the default suite.
- **Acceptance:** A query returns one normalized combined candidate set from all enabled sources,
  and failure of one source does not discard successful results from the others.
- **Out of scope:** Query generation, deduplication changes, classifiers, and broad web crawling.
- **Git:** `feat(discovery): add academic source adapters`; merge with
  `merge: F5-academic-discovery search required academic sources`.

## F6 — Model Provider Routing

- **Branch:** `F6-model-provider-routing`.
- **Depends on:** F1 and F4.
- **Goal:** Provide capability-based semantic inference without coupling application code to one
  runtime or paid endpoint.
- **Deliverables:** Async `ModelProvider` protocol; typed request/result metadata; configurable
  local provider adapter for one Apple-Silicon-friendly runtime; optional NVIDIA NIM adapter;
  capability router for cheap text, deep reasoning, synthesis, ideation, and report writing;
  structured-output validation; token/latency metadata where available; two NIM retries followed
  by local fallback; secret-safe configuration and logs.
- **Tests:** Fake-provider contract suite; capability mapping; structured output; timeouts; NIM
  retries; local fallback; missing optional credentials; unknown capability; cancellation; no
  secret leakage. Real model/NIM smoke tests remain opt-in.
- **Acceptance:** Callers request a capability rather than a vendor/model, optional NIM failure
  degrades to local inference, and the default test suite needs no model or credentials.
- **Out of scope:** Classifier-specific behavior, prompts for research products, and model training.
- **Git:** `feat(models): add capability-based provider routing`; merge with
  `merge: F6-model-provider-routing add local and optional NIM inference`.

## F7 — Search Query Planning

- **Branch:** `F7-search-query-planning`.
- **Depends on:** F2 and F5–F6.
- **Goal:** Expand a configured topic into a bounded, reproducible academic search plan.
- **Deliverables:** Query-planner interface; versioned prompt; local semantic expansion using topic
  name, known keywords, and available historical summary; validation, normalization, and stable
  deduplication of approximately 5–20 queries; deterministic base query and fallback when local
  inference is unavailable; persisted query plan and model/prompt provenance.
- **Tests:** Narrow and broad topics; duplicate/empty model output; output bounds; deterministic
  fallback; Unicode; historical context; invalid structured responses; persisted provenance.
- **Acceptance:** Every enabled topic produces a validated bounded query list even when semantic
  expansion fails, and the exact resolved plan can be audited later.
- **Out of scope:** Running searches and automatic second-pass broadening in the graph.
- **Git:** `feat(queries): add semantic search planning`; merge with
  `merge: F7-search-query-planning generate bounded topic queries`.

## F8 — Classifier A Integration

- **Branch:** `F8-classifier-a-integration`.
- **Depends on:** F3–F4.
- **Goal:** Integrate the pre-existing lightweight/Jev-style classifier through a stable
  application contract.
- **Deliverables:** `PaperClassifier` protocol; shared `ClassificationResult` with validated
  relevance, paper type, action, scores, confidence, reason, latency, and optional raw response;
  Classifier A adapter translating native outputs; batch support when the supplied implementation
  supports it; local execution; persistence with model/version provenance.
- **Prerequisite:** Locate or obtain the actual Classifier A implementation, weights, and usage
  terms before this branch begins. Do not invent, retrain, or silently substitute a classifier.
- **Tests:** Adapter translation; schema bounds; missing confidence; batch/single parity; malformed
  native output; deterministic fake classifier; persistence; latency metadata.
- **Acceptance:** Classifier A processes a candidate through `PaperClassifier` and stores only the
  normalized contract expected by downstream code.
- **Out of scope:** Classifier B, factory switching, shadow mode, and training.
- **Git:** `feat(classifiers): integrate classifier A`; merge with
  `merge: F8-classifier-a-integration add lightweight paper triage`.

## F9 — Classifier B and Shadow Mode

- **Branch:** `F9-classifier-b-shadow-mode`.
- **Depends on:** F6 and F8.
- **Goal:** Complete dual-classifier operation, configuration-only switching, and isolated shadow
  evaluation.
- **Deliverables:** Qwen-style Classifier B adapter using the configured local provider; versioned
  structured prompt; Pydantic output validation and one repair retry; classifier factory; active
  and optional shadow executor; `is_active` persistence; shadow-failure isolation; CLI classifier
  selection; comparison command/script reporting agreement, disagreement, latency, confidence,
  action, and relevance distributions.
- **CLI:** Implement `research-agent classifier set A`, `research-agent classifier set B`, and
  `research-agent compare-classifiers <topic_id>`; retain
  `python scripts/compare_classifiers.py` as the evaluation-script entry point required by the TRD.
- **Prerequisite:** Confirm the intended pre-existing Qwen model/runtime and local availability;
  keep the model configurable and do not commit model weights.
- **Tests:** Factory A/B selection; unsupported classifier; malformed B output and repair ceiling;
  active A/shadow B and reverse; no shadow; shadow failure; active failure; routing determined only
  by active output; comparison metrics.
- **Acceptance:** A configuration change switches the active classifier without changing workflow
  code or schemas, and a failing shadow classifier cannot fail or alter the primary decision.
- **Out of scope:** Paper selection thresholds and model training/fine-tuning.
- **Git:** `feat(classifiers): add classifier B and shadow execution`; merge with
  `merge: F9-classifier-b-shadow-mode complete dual-classifier operation`.

## F10 — Paper Selection

- **Branch:** `F10-paper-selection`.
- **Depends on:** F4 and F9.
- **Goal:** Turn normalized active-classifier results into a reproducible, resource-bounded paper
  set.
- **Deliverables:** Deterministic ranking and tie-breaking; configurable relevance/action
  thresholds; enforcement of candidate, classification, download, and deep-read limits;
  persistent seen-paper lookup using first/last seen/analyzed timestamps; changed-metadata and
  explicit reanalysis policy; selection-reason records; stable ordering.
- **Tests:** Threshold boundaries; ties; missing scores; all-ignore and over-limit sets; previously
  seen papers; changed metadata; explicit reanalysis; active versus shadow decisions; idempotency.
- **Acceptance:** The selected set is reproducible, only active results control routing, resource
  caps are never exceeded, and skipped papers remain auditable.
- **Out of scope:** PDF acquisition and graph query broadening.
- **Git:** `feat(selection): add bounded paper selection`; merge with
  `merge: F10-paper-selection select reproducible reading sets`.

## F11 — PDF Acquisition

- **Branch:** `F11-pdf-acquisition`.
- **Depends on:** F4 and F10.
- **Goal:** Acquire only legally accessible PDFs while preserving useful metadata-only progress.
- **Deliverables:** Async downloader behind a document-acquisition interface; open-access URL
  policy; redirects; content-type and signature validation; configurable size limit; safe
  deterministic filenames; atomic artifact writes; bounded concurrency; two-download retry
  ceiling; HTTP metadata; unavailable and failed outcomes that retain abstract/metadata.
- **Tests:** Valid PDF; redirects; HTML masquerading as PDF; oversize response; timeout; retryable
  and non-retryable statuses; duplicate/cached download; path safety; partial file cleanup;
  per-paper failure isolation.
- **Acceptance:** Valid open PDFs are stored once with metadata, unavailable or invalid documents
  never abort the run, and no paywall bypass behavior exists.
- **Out of scope:** PDF parsing and analysis.
- **Git:** `feat(documents): add legal PDF acquisition`; merge with
  `merge: F11-pdf-acquisition store validated open-access papers`.

## F12 — PDF Parsing

- **Branch:** `F12-pdf-parsing`.
- **Depends on:** F11.
- **Goal:** Convert downloaded papers into reusable structured text and Markdown artifacts.
- **Deliverables:** Document-parser interface and Docling adapter; `ParsedPaper`, section, table,
  figure, and reference schemas; parser name/version provenance; normalized Markdown storage;
  cached result lookup keyed by unchanged source artifact; parse-failure record and explicit
  abstract-only fallback marker.
- **Tests:** Representative sanitized PDF fixtures; section/table/figure/reference translation;
  parser metadata; cache hits; corrupt/encrypted PDFs; missing files; partial extraction; failure
  isolation. Large or platform-specific Docling tests may be separately marked but not silently
  skipped in CI.
- **Acceptance:** A valid downloaded PDF produces structured persisted output, and any parse failure
  leaves the paper eligible for clearly marked abstract-only analysis.
- **Out of scope:** Semantic paper analysis and OCR tuning beyond initial Docling support.
- **Git:** `feat(documents): add structured PDF parsing`; merge with
  `merge: F12-pdf-parsing persist reusable paper text`.

## F13 — Paper Analysis

- **Branch:** `F13-paper-analysis`.
- **Depends on:** F6, F10, and F12.
- **Goal:** Produce validated, evidence-backed analysis for each selected paper.
- **Deliverables:** `PaperAnalysis` and `Claim` schemas; versioned analysis prompt; full-text input
  with abstract-only fallback; extraction of problem, contribution, method, datasets, benchmarks,
  experiment, results, strengths, limitations, related work, topic relevance, and links; best-
  effort section/page/excerpt provenance; bounded parallelism; cached analysis reuse; JSON artifact
  and repository persistence; Markdown paper-card renderer.
- **Tests:** Structured output validation; full-text and abstract-only modes; claim provenance;
  missing optional fields; provider fallback; one-paper failure among many; concurrency; cache
  invalidation; deterministic paper-card layout.
- **Acceptance:** Every successfully analyzed paper has a validated stored analysis tied to its
  paper, model, prompt, and evidence; unsupported claims cannot silently lose paper provenance.
- **Out of scope:** Cross-paper synthesis and report prose.
- **Git:** `feat(analysis): add evidence-backed paper analysis`; merge with
  `merge: F13-paper-analysis generate structured paper cards`.

## F14 — Weekly Synthesis

- **Branch:** `F14-weekly-synthesis`.
- **Depends on:** F4 and F13.
- **Goal:** Compare the week's evidence across papers and against recent topic history.
- **Deliverables:** `WeeklySynthesis` and supported-finding schemas; versioned synthesis prompt;
  themes, developments, emerging directions, repeated methods, datasets, benchmarks,
  contradictions, limitations, and changes from history; retrieval of the previous four
  syntheses by default; required supporting paper IDs; provider/model provenance; persisted JSON.
- **Tests:** One and many analyses; contradictory papers; repeated evidence; no history; four-week
  history limit; invalid or unknown paper references; provider fallback; deterministic ordering of
  stored references.
- **Acceptance:** The weekly synthesis distinguishes current evidence from historical change and
  every substantive finding references known supporting papers.
- **Out of scope:** Gap/idea generation and final report rendering.
- **Git:** `feat(synthesis): add historical weekly synthesis`; merge with
  `merge: F14-weekly-synthesis compare weekly research evidence`.

## F15 — Research Gaps and Ideas

- **Branch:** `F15-research-ideation`.
- **Depends on:** F14.
- **Goal:** Turn supported synthesis findings into explicit, traceable research opportunities.
- **Deliverables:** `ResearchGap` and `ResearchIdea` schemas; versioned gap and ideation prompts;
  confidence, motivation, hypothesis, proposed direction, evaluation plan, risks, and required
  supporting paper IDs; reference validation against the selected corpus; provider/model
  provenance; persisted records and artifacts.
- **Tests:** Supported and unsupported gap references; duplicate ideas; empty synthesis; malformed
  model output; provider fallback; confidence bounds; deterministic reference ordering.
- **Acceptance:** Every stored gap and idea is schema-valid, explicitly uncertain where appropriate,
  and traceable to real papers in the run rather than unsupported generic brainstorming.
- **Out of scope:** Experiment execution and autonomous publication activity.
- **Git:** `feat(ideation): generate supported research directions`; merge with
  `merge: F15-research-ideation derive evidence-backed gaps and ideas`.

## F16 — Report Generation

- **Branch:** `F16-report-generation`.
- **Depends on:** F4 and F13–F15.
- **Goal:** Produce the complete reproducible weekly Markdown deliverable from structured records.
- **Deliverables:** Deterministic report assembly and optional model-assisted prose; every PRD report
  section; reporting period, resolved topic/configuration, sources, active/shadow classifier, and
  model/provider provenance; essential/useful/peripheral reading order; source links; safe
  `YYYY-MM-DD_weekly_report.md` naming; empty-week and degraded-report templates; atomic storage;
  latest-report lookup.
- **CLI:** Implement `research-agent report latest <topic_id>`.
- **Tests:** Full report snapshot; filename generation; empty week; abstract-only analyses; partial
  provider/source failures; escaping untrusted content; missing optional sections; provenance links;
  latest report selection; atomic overwrite protection.
- **Acceptance:** A human-readable report contains all required sections and provenance, remains
  useful under supported degraded modes, and can be retrieved deterministically.
- **Out of scope:** Graph orchestration and web/email delivery.
- **Git:** `feat(reports): generate weekly research reports`; merge with
  `merge: F16-report-generation produce reproducible Markdown intelligence`.

## F17 — LangGraph Workflow

- **Branch:** `F17-langgraph-workflow`.
- **Depends on:** F5–F16.
- **Goal:** Orchestrate the complete research run without moving provider or storage details into
  graph nodes.
- **Deliverables:** Validated `ResearchState` using IDs/paths rather than binary content; graph
  builder; injectable nodes for topic loading, query planning, discovery, normalization,
  deduplication, classification, selection, acquisition, parsing, analysis, synthesis, gap
  detection, ideation, reporting, and persistence; conditional empty-week route; exactly one
  automatic query-broadening pass; abstract-only and provider-fallback routes; node-level
  structured logs and recoverable errors; optional checkpoints only where justified.
- **Tests:** Fully mocked end-to-end run; empty discovery; one-pass broadening ceiling; one-source,
  one-paper, shadow, download, parse, and NIM failures; local fallback; state-size guard; node
  dependency isolation; deterministic rerun behavior.
- **Acceptance:** LangGraph executes the complete v1 flow from a topic ID to persisted report and
  run summary while preserving partial progress and all specified failure branches.
- **Out of scope:** Scheduler ownership, direct API/provider logic in nodes, and AWS execution.
- **Git:** `feat(workflow): orchestrate the complete research graph`; merge with
  `merge: F17-langgraph-workflow execute resilient weekly research runs`.

## F18 — Run Operations and Scheduling

- **Branch:** `F18-run-operations-scheduling`.
- **Depends on:** F2 and F16–F17.
- **Goal:** Make the complete workflow practical to invoke, inspect, and schedule locally.
- **Deliverables:** `research-agent run <topic_id>` and `research-agent run-all`; enabled-topic
  filtering; overlap/lock protection; nonzero exit codes for fatal run failures while preserving
  partial artifacts; concise terminal summaries; launchd and cron generation/install guidance;
  scheduler interface outside LangGraph; schedule validation; graceful interruption and final run
  status; documented local operations.
- **Tests:** Single run; run-all with mixed enabled states; unknown/disabled topic; overlapping
  invocation; partial success; fatal failure; interruption; deterministic scheduler output;
  no-secret command rendering.
- **Acceptance:** The user can run one topic or all enabled topics manually and configure a weekly
  local trigger without editing application code or placing scheduling inside the graph.
- **Out of scope:** Always-on services, GUI, notifications, and AWS EventBridge deployment.
- **Git:** `feat(operations): add run commands and local scheduling`; merge with
  `merge: F18-run-operations-scheduling operate weekly research locally`.

## F19 — MVP Reliability Hardening

- **Branch:** `F19-mvp-reliability-hardening`.
- **Depends on:** F17–F18.
- **Goal:** Prove the complete local MVP meets the PRD/TRD acceptance criteria under normal and
  degraded conditions.
- **Deliverables:** End-to-end static fixture corpus; cache/idempotency enforcement for search,
  metadata, PDFs, parsed artifacts, and analyses; consistent error taxonomy; complete run-summary
  counts, timing, providers, classifiers, and final status; reproducibility manifest; recovery from
  interrupted/partial runs where safe; resource-limit audit; security/log-redaction audit;
  operator troubleshooting guide.
- **Tests:** Fully mocked complete run; repeated unchanged run; empty week; all documented partial
  failures; retry ceilings; concurrency caps; cache reuse; interruption/restart; corrupt cache;
  deterministic report references; no secrets in logs/artifacts; PRD acceptance checklist.
- **Acceptance:** A full one-topic run completes without paid infrastructure, every MVP criterion is
  demonstrated, failures remain diagnosable and isolated, and unchanged reruns avoid unnecessary
  expensive work.
- **Out of scope:** Live-service uptime guarantees, performance at multi-tenant scale, and custom
  model training.
- **Git:** `feat(reliability): harden end-to-end MVP execution`; merge with
  `merge: F19-mvp-reliability-hardening satisfy local MVP acceptance`.

## F20 — AWS Portability Validation

- **Branch:** `F20-aws-portability-validation`.
- **Depends on:** F19.
- **Goal:** Demonstrate that local-first boundaries map cleanly to AWS without forcing the complete
  long-running graph into Lambda or incurring paid infrastructure by default.
- **Deliverables:** Local/AWS configuration profile schema; interface conformance tests proving
  filesystem→S3, SQLite repository→DynamoDB-style repository, launchd/cron→EventBridge, local
  logs→CloudWatch, and environment secrets→Parameter Store/Secrets Manager substitutions; AWS
  execution design for lightweight Lambda/API tasks versus a long-running Python worker; IAM and
  secret-handling guidance; free-plan cost guardrails; deployment/runbook documentation. Thin AWS
  adapters may be added only when they can be tested safely and do not become required locally.
- **Tests:** Backend factory selection; no local paths in workflow nodes; fake S3/DynamoDB contract
  adapters; AWS profile validation; secret redaction; missing optional AWS dependencies; local
  regression suite unchanged.
- **Acceptance:** The same workflow and domain services run against interface-compatible backends,
  local execution remains the default, and the documented design avoids EKS, NAT Gateway,
  OpenSearch, paid GPU endpoints, and other prohibited expensive defaults.
- **Out of scope:** Creating cloud resources, production deployment, multi-region operation, paid
  infrastructure, and forcing long research runs into one Lambda invocation.
- **Git:** `feat(portability): validate AWS-compatible boundaries`; merge with
  `merge: F20-aws-portability-validation demonstrate cloud portability`.

## Cross-Feature Rules

- Each feature includes the lowest useful unit tests and any required integration tests; the full
  supported suite runs before every merge.
- Default tests never depend on live APIs, credentials, paid services, local model downloads, or
  mutable external data. Live/model smoke tests are explicit and optional.
- Every external payload and model response is untrusted, translated at an adapter boundary, and
  validated before routing or persistence.
- Every important synthesis, gap, idea, and report statement retains supporting paper IDs or source
  metadata. Page/section evidence remains best-effort where parser output permits it.
- A failure in one source, paper, shadow classifier, download, parse, or optional provider must not
  terminate an otherwise useful run.
- No feature may add training/fine-tuning, paywall bypassing, large-scale crawling, multi-tenant
  SaaS, Kubernetes/EKS, paid GPU infrastructure, or another classifier path.
- AWS compatibility means replaceable interfaces and verified contracts; it does not override the
  local-first, near-zero-cost default.

## Known Planning Gates

- Before F6, select and document the supported local runtime/model combination based on current
  Apple Silicon compatibility; keep the adapter configurable.
- Before F8, the actual pre-existing Classifier A implementation or artifact must be supplied or
  located. Its absence is a real blocker, not permission to create a replacement.
- Before F9, confirm the intended pre-existing Qwen model/runtime for Classifier B and its usage
  terms. Model weights remain outside Git.
- Before F12, confirm the supported Docling/Python combination on the target machine and lock a
  compatible version.
- Before any optional live NIM or AWS validation, the user must provide/configure credentials
  through approved secret mechanisms; credentials must never enter Git, logs, or handoff files.

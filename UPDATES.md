# Project Updates

This is the append-at-top handoff log for the Personal Weekly AI Research Intelligence Agent. Follow the required entry format and workflow in `AGENTS.md`. Never record secrets.

## 2026-09-28 — F21 quality-aware paper ranking (complete, merged)

- **Feature/branch:** `F21-quality-paper-ranking` (allocated after F20).
- **Commits:** `91fa8c5` feat(ranking): prioritize relevant recent quality papers; merged as `94c1613`.
- **Status:** Complete, merged, and re-verified on `main`.

**Behavior added**

- Classifier A lexical scoring is now `classifier_a.v2`: an exact topic phrase in an abstract is
  scored on the evidence that matched instead of being diluted by every optional keyword. This
  fixes the observed Computer Vision run where 50 classified papers all scored `low/ignore`.
- Selection now ranks eligible papers with deterministic recency, preferred-venue, citation, and
  source-metadata signals. Relevance remains the eligibility gate; quality ordering only decides
  which papers fit download/deep-read limits. Defaults include CVPR, ICCV, ECCV, NeurIPS, ICML,
  ICLR, AAAI, IJCAI, SIGGRAPH, TPAMI, JMLR, Nature, and Science, all configurable in settings.
- Discovery shares each query's candidate budget across enabled sources so one provider cannot fill
  the entire candidate set and starve the others.
- Full workflow runs now persist their resolved query plan and include the queries in the run
  manifest for auditability.

**Files and interfaces**

- New: `src/research_agent/selection/quality.py`, `tests/unit/test_selection_quality.py`.
- Modified: Classifier A lexical scoring, selection ordering/configuration, discovery source quotas,
  workflow query-plan persistence, manifests, README, and local operations documentation.
- No schema migration or new dependency.

**Verification**

- `.venv/bin/ruff check src/research_agent tests` → clean.
- `.venv/bin/mypy` → success, no issues in 160 source files.
- `.venv/bin/python -m pytest` → **603 passed, 3 deselected**, coverage 94.10%.

**Known issues and next step**

- The live Computer Vision run should be rerun after merge; this branch does not mutate the user's
  existing database or report artifacts.
- Venue metadata is best-effort from providers; papers without a venue remain eligible when topical
  relevance is sufficient but rank below recent papers with known preferred venues.
- Next step: rerun `research-agent run computer_vision` and inspect the selected papers/report.

## 2026-09-27 — F20 AWS portability validation (complete, merged)

- **Feature/branch:** `F20-aws-portability-validation`.
- **Commits:** `ca1cad5` feat(portability): validate AWS-compatible boundaries; merged as `7cddfdf`.
- **Status:** Complete, merged, and re-verified on `main`. **This is the last feature on the roadmap: F1-F20 are all merged.**

**Behavior added**

- `DeploymentProfile` names one backend per replaceable boundary — artifacts, metadata, scheduler, logs, secrets, worker — and validates the combination. A local profile cannot quietly point at S3; an AWS profile cannot quietly keep cron and must replace at least one backend; `LOCAL_PROFILE` is what `DeploymentProfile()` gives you.
- **Cost guardrails are code, not prose.** `free_plan_only` defaults true and the profile refuses EKS/Kubernetes, NAT Gateway, OpenSearch/Elasticsearch, SageMaker, Fargate, RDS/Aurora, MSK and GPU endpoints. Waiving it takes an explicit `free_plan_only=False`.
- **`worker="lambda"` is refused for an AWS target**, encoding TRD section 51: a weekly run is long and holds a per-topic lock, so Lambda serves the trigger and the API, never the whole graph.
- `SecretResolver` with `EnvironmentSecrets` (local) and `ParameterStoreSecrets` (Parameter Store / Secrets Manager shaped, over an **injected fetcher**, so no dependency and nothing untestable). A remote backend without a fetcher raises rather than falling back to the environment — a silent fallback is how a deployment reads the wrong secrets. `SecretMapping` names the only three secrets the application uses, which is what a least-privilege policy grants.
- `EventBridgeScheduler` joins launchd and cron behind the same `Scheduler` Protocol and renders a deterministic schedule JSON for the same `research-agent run <topic_id>` command, with `MaximumRetryAttempts: 0` because a retry would collide with the per-topic lock. `research-agent schedule generate --backend eventbridge` prints it and the `aws scheduler create-schedule` line.
- `docs/AWS_PORTABILITY.md`: the boundary map, the execution design, what the conformance tests prove, a least-privilege IAM policy, secret handling, the cost guardrails and a six-step runbook with a rollback that needs no code change.

**Files and interfaces**

- New: `src/research_agent/portability/{__init__,profiles,secrets}.py`, `docs/AWS_PORTABILITY.md`, `tests/unit/test_portability_{conformance,boundaries}.py`.
- Modified: `src/research_agent/operations/scheduling.py` (`EventBridgeScheduler`, the backend Literal, EventBridge day names); `src/research_agent/cli.py` (accepts the new backend).
- **No new dependency.** A test asserts `pyproject.toml` declares no `boto3`/`botocore`/`aws`, and another asserts the portability package imports none.

**What the conformance suite proves (58 new tests, all in the default suite)**

- Substituting an object store for the filesystem needs no application change: a card is written and a parsed paper is read back through the real `load_parsed` over S3-shaped flat keys, and `ReportService.latest`'s lookup works from an object listing. The fake still refuses a key that escapes its topic prefix.
- `PaperCandidate` and `PaperAnalysis` round-trip through a partition/sort-keyed document table via the same Pydantic models the SQLite repositories use — the domain model is the contract, not the SQL.
- The EventBridge schedule is deterministic, targets the same command, and carries no credential.
- Remote secret resolution maps the same logical names to `/research-agent/<env>/<name>` and never falls back to the environment; a missing secret names the secret, never a value.
- Logs are one JSON object per line with a timezone-aware timestamp, which is the whole CloudWatch contract — no adapter needed.
- **Statically:** no module under `workflow/` names `sqlite3`, `pathlib`, `boto3`, a `Sqlite*` repository, `LocalArtifactStore`, `DoclingParser`, `PdfDownloader` or a model provider; the AST check also rejects importing `models.chat` or the Docling adapter; no domain model mentions a provider or a backend; and a topic's serialized form contains no bucket, ARN, path or backend name.

**Decisions and why**

- **No thin AWS adapters were shipped.** The roadmap allows them "only when they can be tested safely and do not become required locally". A real S3 or DynamoDB adapter needs credentials and a live account to test honestly; the in-memory stand-ins prove the boundary is sufficient, which is what F20 is actually for. The injected-fetcher seam is where a `boto3` adapter would attach.
- **The guards are static tests, not documentation.** "No local paths in workflow nodes" is a property of the source, so a test that reads the source is the only thing that can keep it true.
- **`EventBridgeScheduler` lives beside launchd and cron** rather than in `portability/`, because it is an implementation of an existing Protocol and the CLI already resolves backends there.

**Verification**

- `uv run ruff format --check .` → 155 files already formatted; `uv run ruff check .` → clean.
- `uv run mypy` → Success: no issues found in 158 source files, exit status 0.
- `uv run pytest` → **598 passed, 3 deselected**; coverage 94.05% (gate 85%).
- `uv run research-agent config validate` → valid.
- `uv run research-agent schedule generate --topic embodied_spatial_intelligence --backend eventbridge` → a valid weekly schedule (`cron(0 7 ? * SUN *)`, UTC) invoking `research-agent run embodied_spatial_intelligence`, with the create-schedule command.
- The local regression suite is unchanged in behaviour: same commands, same defaults, no new required configuration.

**Known issues and next step**

- The AWS path is validated, not deployed: no resources exist, and nothing has run on AWS. That is deliberate and in the roadmap's out-of-scope list.
- **Roadmap complete.** The remaining known items are all recorded above and none belong to a roadmap feature: a shadow-classifier ceiling, one repair retry for analysis (a TRD deviation that would need recording), the arXiv HTTP 406 (server-side), Semantic Scholar's 429s without a key, Classifier A's thresholds producing `summarize` rather than `deep_read` on a real corpus, moving `discovery/http.py` to `utils/http.py` now that it has three consumers, and the F2-era `ResourceWarning: unclosed database` in tests.

## 2026-09-27 — FIX3 acceptance test typing (complete, merged)

- **Feature/branch:** `FIX3-acceptance-test-typing`.
- **Commits:** `9e4e3dd` fix(tests): type the acceptance suite's transport; merged as `092fdb9`.
- **Status:** Complete, merged, and re-verified on `main`.

**What happened**

F19 was merged with `mypy` failing: 16 `arg-type` errors in `tests/integration/test_acceptance.py`, because `counted()` was annotated `tuple[object, ...]` while `services()` wants a `Handler`. The merge went ahead because the verification command piped mypy into `tail`, and a pipeline reports the exit status of its last stage — so a red type check looked green. That is a process defect as much as a typing one.

**The fix**

- `counted()` returns `tuple[Handler, dict[str, int]]`, reusing the alias the graph tests already define.
- The resource-limit test now builds its bounded services with `dataclasses.replace` instead of reconstructing the frozen dataclass from `__dict__` behind a `type: ignore`.
- **Verification habit corrected:** run `uv run mypy` on its own and check its exit status. Never `uv run mypy | tail`.

**Verification**

- `uv run ruff format --check .` → 150 files already formatted; `uv run ruff check .` → clean.
- `uv run mypy` → Success: no issues found in 153 source files, **exit status 0** (checked explicitly).
- `uv run pytest` → 540 passed, 3 deselected; coverage 93.87%.

## 2026-09-27 — F19 MVP reliability hardening (complete, merged)

- **Feature/branch:** `F19-mvp-reliability-hardening`.
- **Commits:** `44aa7d0` feat(reliability): harden end-to-end MVP execution; merged as `263231d`.
- **Status:** Complete, merged, and re-verified on `main`. A full live `run` completed end to end for the first time: 994s, 471 candidates, 250 classified, 11 selected, 9 PDFs, 0 parse failures, 8 analyses, 5 gaps, 5 ideas, one report, status `degraded` with 10 isolated errors.

**Behavior added**

- **Reproducibility manifest.** Every completed run writes `<run_id>-manifest.json` under the topic's `runs` artifacts: period and status, the resolved topic configuration and limits, enabled sources, active/shadow classifier, provider and model names, prompt versions, the relevant settings blocks, and the run's counts. Names only — a manifest is safe to attach to a bug report.
- **Log redaction.** `SecretRedactingFilter` removes credentials before a record is formatted: known vendor key shapes, `Authorization: Bearer …`, `?api_key=…` parameters, and the literal value of any `RESEARCH_AGENT_*` variable whose name mentions `API_KEY`, `TOKEN`, `SECRET` or `PASSWORD`. Exception tracebacks go through it too, which is where a request URL most often leaks.
- **Structured logging is actually on.** `_open_connection` calls `configure_logging` with the settings file's own `log_level`, closing a gap that had been open since F1: the CLI emitted no structured logs at all. `httpx`/`httpcore`/`urllib3` are pinned to `WARNING`, because their INFO lines print full request URLs.
- **The run summary is complete.** `persist` now records `models_used` from the run's analyses alongside the existing counts, so a run row carries counts, models, classifiers, timing and final status.
- `docs/OPERATIONS.md` gained a Logs section, a Reproducibility section, and seven more troubleshooting rows covering the slow-shadow-classifier case, arXiv 406, Semantic Scholar 429, Docling's first-run download, empty-week reruns and post-interrupt recovery.

**Files and interfaces**

- New: `src/research_agent/observability/manifest.py`, `tests/unit/test_logging_redaction.py`, `tests/integration/test_acceptance.py`, `tests/integration/conftest.py`.
- Modified: `src/research_agent/observability/logging.py` (redaction, third-party levels); `src/research_agent/workflow/{nodes,services}.py` (`store` on the services, manifest written by `persist`, `models_used`); `src/research_agent/operations/wiring.py` (supplies the store); `src/research_agent/cli.py` (configures logging); `docs/OPERATIONS.md`; `tests/integration/test_{workflow_graph,run_cli}.py`.
- No schema change: the manifest is an artifact and `models_used` already existed on `RunSummary`.
- Also carried here: `config/topics.yaml` now has `semantic_scholar: false` for the live topic, with the reason inline — without an API key that source answers 429 on every query.

**The acceptance sweep**

`tests/integration/test_acceptance.py` drives one fully mocked stack and asserts the PRD's promises directly: a complete run produces a report with every required section; an unchanged rerun performs **zero** analyses and **zero** downloads; the run summary carries counts, models, timing and classifiers; the manifest records the inputs and contains no credential; the four resource limits are respected; every recorded error category is a member of the documented `ErrorCategory`; a corrupt parsed artifact degrades to abstract-only instead of ending the run; an abandoned run does not block the next one and is kept for diagnosis; **no file a run writes contains the configured key**; the same run renders identical references whenever the report is rebuilt; and the reporting period matches the run.

**Decisions and why**

- **The fixture corpus is the mock transport, not a new directory of files.** The graph tests already drive every stage from one switchable transport plus a committed sample PDF; adding a parallel fixture corpus would have duplicated it without testing anything more.
- **Redaction reads the environment at log time** rather than caching values at import, so a key set after start-up is still redacted, and a short placeholder such as `none` is not treated as a secret.
- **The manifest is an artifact, not a table.** It is write-once, read-by-a-human, and belongs beside the report it explains.
- **An unchanged rerun reporting an empty week is correct, not a bug**, and is now asserted as such: caching means nothing was selected, so there is nothing new to report. `classify --reanalyze` is the escape hatch.

**Verification**

- `uv run ruff format --check .` / `uv run ruff check .` → clean.
- `uv run mypy` → Success: no issues found in 151 source files.
- `uv run pytest` → 540 passed, 3 deselected; coverage 93.87% (gate 85%).

**What the first complete live run showed**

- `degraded  embodied_spatial_intelligence  8 paper(s)  10 error(s)` in 994s, with a report on disk. The ten errors were all isolated and all recorded with the documented taxonomy: 5 `DISCOVERY_ERROR` (arXiv HTTP 406, one per query), 2 `PDF_DOWNLOAD_ERROR` (no open-access PDF), 3 `MODEL_API_ERROR` in analysis. Every other stage completed. This is exactly the degraded-but-useful behaviour the PRD asks for.
- The three analysis failures had two distinct causes, both worth recording: one reply omitted the required `topic_relevance` field, and one was truncated mid-string. The truncation was a token ceiling, so `models.*.max_output_tokens` moved 4096 → 8192 in `config/settings.yaml` with the reason inline. The missing field is the model, not the code: analysis deliberately has no repair retry (the TRD gives that to Classifier B alone), so the paper is skipped and recorded. If it recurs often, granting analysis one repair retry is the change to make, and it is a TRD deviation that needs recording.
- `deep_reads` was 0 while 11 papers were selected: the lexical Classifier A scored them all `summarize` rather than `deep_read`. Worth a threshold review, not a defect.
- That run began before this branch's own changes were saved, so its summary shows `models_used: []` and it wrote no manifest. **Confirmed on the next live run** (after F20 merged, 213s, `degraded`, 7 isolated errors): `models_used: ["openai/gpt-oss-20b"]` in the summary and `43c1474b…-manifest.json` on disk carrying the period, sources, classifier, models, prompt versions and counts — with no `nvapi` string and no `api_key` anywhere in it. The run took 213s rather than 994s because caching skipped the papers already analysed.

**Known issues and next step**

- Shadow-mode cost is still unbounded: with `shadow=B` a run sends up to `max_classified` papers to an LLM whose verdicts never route, which is what made the first live `run` appear to hang. The operator workaround is documented; a dedicated shadow ceiling would be the real fix and is not in any roadmap feature.
- **Next recommended step:** F20 AWS portability validation — interface conformance for filesystem→S3, SQLite→DynamoDB-style repositories, launchd/cron→EventBridge, local logs→CloudWatch and env secrets→Parameter Store, plus the profile schema and the runbook, with local execution staying the default.

## 2026-09-27 — FIX2 arXiv pagination bound (complete, merged)

- **Feature/branch:** `FIX2-arxiv-pagination`.
- **Commits:** `5cb5b54` fix(discovery): bound source pagination; merged as `4819e64`.
- **Status:** Complete, merged, and re-verified on `main`.

**The defect**

`ArxivSource.search` requests results `sortBy=submittedDate&sortOrder=descending` but applies the date window in `_translate`, client-side. It paged until it had `limit` candidates, so for a 10-day window against `max_candidates=500` it walked the entire arXiv result set at one request every three seconds, discarding almost everything. A live `run` sat in discovery for 88 minutes with 3.4s of CPU.

**The fix**

- arXiv stops as soon as a whole page predates the window. The results are newest-first, so every later page is older too — this is exact, not a heuristic.
- `SourceSettings.max_pages` (default 10) caps pages per query for every source. OpenAlex honours it as well, so a cursor that keeps returning itself cannot loop for ever.
- Three regression tests: the early stop (asserting the third request is never made), the arXiv ceiling when every page is in-window, and the OpenAlex ceiling against a never-ending cursor.

**Two diagnoses this branch settled, neither a defect in it**

- **The 31-minute stall after the fix was the shadow classifier**, not discovery. The live topic has `active=A, shadow=B`, so every run sent up to `max_classified=250` papers to the LLM at `concurrency.analysis=2` purely to store non-routing verdicts. Shadow mode is working as specified — the TRD only requires that it never fail the run — but it makes a live run impractical, so the shadow was switched off for the live topic. **Recommendation for F19:** give shadow classification its own, much smaller ceiling; the point of shadow mode is comparison, which a sample satisfies.
- **The arXiv HTTP 406 is server-side and not fixable here.** Probed directly: `all:electron` returns 200, while `ti:electron`, `cat:cs.AI`, and *any* multi-word query return 406 with zero bytes, with or without `User-Agent`/`Accept`, over HTTP or HTTPS, on `export.arxiv.org` and `arxiv.org`, with the space encoded as `+` or `%20`. No client change fixes it. The behaviour is already correct: 406 is not retried, the source error is recorded, and the run continues on OpenAlex alone. OpenAlex returns 474 candidates for the live topic in 4.3s.

**Verification**

- `uv run ruff format --check .` / `uv run ruff check .` → clean.
- `uv run mypy` → Success: no issues found in 149 source files.
- `uv run pytest` → 519 passed, 3 deselected; coverage 93.77% (gate 85%).

**Next step**

- A live end-to-end `run` with the shadow classifier off, then F19 MVP reliability hardening.

## 2026-09-27 — F18 run operations and scheduling (complete, merged)

- **Feature/branch:** `F18-run-operations-scheduling`.
- **Commits:** `192a1b1` feat(operations): add run commands and local scheduling; merged as `f9fa0c1`.
- **Status:** Complete, merged, and re-verified on `main`. Verified offline in full; the live end-to-end `run` is blocked by an F5 discovery defect this branch's first live run exposed (see below), fixed next on `FIX2-arxiv-pagination`.

**Behavior added**

- `research-agent run <topic_id>` executes the whole F17 graph for one topic, and `research-agent run-all` does it for every enabled topic in turn, printing one line per topic plus a count summary.
- **One lock per topic** (`data/locks/<topic_id>.lock`, created with `O_EXCL`), so a scheduled run and a manual one cannot collide. A lock whose process no longer exists is reclaimed; an unreadable one is treated as held, which fails safe.
- **Exit codes an operator can script against:** `completed` and `degraded` exit 0 — a degraded run still delivered a report — while `failed` (no report), `skipped` (disabled topic) and `locked` exit 1.
- Ctrl-C closes the open run as `failed`, releases the lock and keeps every artifact already written, so an interrupted run never reads as still running.
- `research-agent schedule generate --topic <id> [--backend launchd|cron] [--at HH:MM] [--output path]` renders a launchd agent or a crontab line for the topic's configured day, ending with the one command that installs it. The rendering is deterministic and contains a command and paths only — `ScheduleRequest` rejects an executable carrying shell syntax or an inline environment assignment, so a credential cannot be smuggled into a schedule.
- `operations/wiring.py` is now the single place that knows how each service is constructed, with a `parser` injection point so a test never loads Docling.
- `docs/OPERATIONS.md` documents the per-stage commands, whole runs, exit codes, where artifacts land, scheduling, and a troubleshooting table.

**Files and interfaces**

- New: `src/research_agent/operations/{__init__,wiring,locks,runner,scheduling}.py`, `docs/OPERATIONS.md`, `tests/unit/test_operations_{locks,runner,scheduling}.py`, `tests/integration/test_run_cli.py`.
- Modified: `src/research_agent/cli.py` (`run`, `run-all`, `schedule generate`).
- No new dependency, no schema change: locks are files and schedules are text.

**Decisions and why**

- **A lock file, not a database row.** The run's own artifacts are files, the tool is single-user, and a file lock survives a crashed process in a way a row does not.
- **`Scheduler` is a Protocol with two implementations**, so the AWS EventBridge equivalent in F20 slots in without touching the workflow, and scheduling stays outside LangGraph as the TRD requires.
- **The scheduled command is the operator command.** A schedule runs `research-agent run <topic_id>` verbatim: anything an operator can debug by hand is exactly what runs weekly.
- **Degraded is a success.** Exiting non-zero on a degraded run would make a paywalled PDF look like a broken installation to cron.

**Verification**

- `uv run ruff format --check .` / `uv run ruff check .` → clean.
- `uv run mypy` → Success: no issues found in 148 source files.
- `uv run pytest` → 513 passed, 3 deselected; coverage 93.71% (gate 85%).
- Tests cover: a single run completing and reporting; the lock released afterwards; an overlapping invocation refused without starting a run; a partial failure exiting 0 as degraded; a disabled topic skipped; an unknown topic; `run-all` over mixed enabled states; deterministic and secret-free launchd and cron rendering; a schedule written to a file; an invalid time; an unsupported backend; interruption closing the run as failed; and a stale lock reclaimed.
- `uv run research-agent schedule generate --topic embodied_spatial_intelligence` → a valid launchd plist with the topic's weekly day and install/removal commands.
- **Interruption verified live, twice.** Ctrl-C on a real `run` printed `failed  embodied_spatial_intelligence  0 paper(s)  0 error(s)  interrupted: CancelledError`, exited non-zero, closed the run row as `failed` and left no lock behind.

**Three defects the live runs exposed, two fixed here**

- **Fixed:** the run used one HTTP client with the NIM timeout (300s) for everything, so a stalled search could block for five minutes. `services_for` now opens one client per timeout class — searches, downloads and inference — and `build_services` takes all three.
- **Fixed:** `queries.max_per_run` (default 5) now bounds how many of a plan's queries one run actually searches. A plan holds up to twenty for reproducibility, but the slowest source is paced at one request every few seconds, so searching all of them made a run take an hour.
- **Fixed:** the `discover` node keyed its cross-query deduplication on the `canonical_id` *field*, which an adapter may not have set, so candidates could collapse to one. It now keys through `canonical_id()`, the same function persistence uses.
- **Not fixed here — the blocker:** `ArxivSource.search` sorts by `submittedDate descending` but applies the date window client-side, and pages until it has `limit` candidates. For a 10-day window against `max_candidates=500` that means paging through the whole arXiv result set at 0.33 requests/second: the live run sat in discovery for 88 minutes with zero classifications and 3.4s of CPU. It belongs to F5, not to this branch, so it goes to `FIX2-arxiv-pagination` rather than being smuggled into a feature merge.

**Known issues and next step**

- Semantic Scholar was disabled for the live topic (`source_semantic_scholar = 0`) because without an API key it answers 429 with `Retry-After` up to 60s on every query, and its limiter serializes at 0.2 requests/second. That is the previously recorded discovery defect, not a new one.
- **Next recommended step:** `FIX2-arxiv-pagination` — stop paging once a page is entirely older than the window (the results are date-sorted, so everything after it is older too) plus a hard page ceiling, with a regression test. Then the live end-to-end `run`, then F19 MVP reliability hardening — the acceptance sweep over this now-complete pipeline: idempotency, cache reuse, the error taxonomy, a reproducibility manifest, the resource-limit audit and the log-redaction audit.

## 2026-09-27 — F17 LangGraph workflow (complete, merged)

- **Feature/branch:** `F17-langgraph-workflow`.
- **Commits:** `1eea57f` feat(workflow): orchestrate the complete research graph; merged as `8ae5fc5`.
- **Status:** Complete, merged, and re-verified on `main`. Verified by a fully mocked end-to-end graph run plus one test per failure branch. No live run yet: the operator entry point is F18's.

**Behavior added**

- `ResearchState` is the graph's validated state and carries identifiers, paths and counts only. A `model_validator` rejects a value in `pdf_paths`/`parsed_paths` that is document content rather than a path, so the graph cannot start carrying papers between nodes.
- `WorkflowServices` is a frozen dataclass of already-constructed collaborators. Nodes hold no provider, endpoint, URL or SQL knowledge; the whole graph runs against fakes in tests because of it.
- Thirteen nodes — `load_topic`, `plan_queries`, `discover`, `broaden`, `classify`, `select`, `acquire`, `parse`, `analyze`, `synthesize`, `ideate`, `report`, `persist` — each a coroutine returning only the fields it changed, and none of them raising: a failed stage appends an `ErrorRecord` and the run continues with less.
- Conditional routes, all pure functions of state and unit-tested on their own: empty discovery broadens **exactly once** and then reports an empty week; nothing selected goes straight to the report; no acquired PDF skips parsing entirely and analysis runs abstract-only; no analysis skips synthesis; no synthesis skips ideation.
- `persist` records every tolerated error, then closes the run with its summary and a status of `completed`, `degraded` (any error) or `failed` (no report produced).

**Files and interfaces**

- New: `src/research_agent/workflow/{__init__,state,services,nodes,graph}.py`, `tests/unit/test_workflow_{state,routes}.py`, `tests/integration/test_workflow_graph.py`.
- Modified: `pyproject.toml` (`langgraph>=1.0,<2`, resolving 1.2.12, and a mypy override for it).
- No migration and no schema change: the graph reuses the repositories and services the earlier branches built.

**Decisions and why**

- **Dependency:** `langgraph>=1.0,<2` (1.2.12, with `langchain-core`, `langgraph-checkpoint`, `langgraph-prebuilt`, `langgraph-sdk` and their transitive packages). The PRD/TRD name LangGraph for orchestration, and it is used for orchestration only — state propagation, conditional routing and failure branching. No LangChain chain, agent, tool or provider abstraction is used anywhere.
- **mypy deviation, documented:** `follow_imports = "skip"` for `langgraph.*`. `StateGraph.add_node`'s overloads do not accept a plainly typed async node function, and its generics are not resolvable against a Pydantic state here. Our nodes, state and routes stay strictly typed; only the builder call is opaque. Recorded in `pyproject.toml` with that reason.
- **Normalization and deduplication are inside `DiscoveryAggregator`** (since F5) rather than separate nodes. Splitting them out would have meant reimplementing them; the flow the TRD describes is preserved, one node deep.
- **Checkpoints are not enabled.** The TRD allows them "only where justified", and a single-user weekly run that is cheap to repeat does not justify the extra state store. The state is checkpoint-shaped (small, path-only) if that changes.
- **No CLI in this branch.** `research-agent run` is F18's deliverable; adding it here would have split that feature across two branches.

**Two real defects the graph found**

- The `acquire` node was matching download statuses `("downloaded", "cached")`, but `DownloadStatus` is `("stored", "cached", "unavailable", "failed")`. Every download was being discarded silently. Now matched correctly.
- `DiscoveryAggregator` stamps its error records with `run_id="unscheduled"` because it does not know the run. Persisting one violated the `errors.run_id` foreign key and failed the whole `persist` step. The `discover` node now re-stamps them with the real run id.

**Verification**

- `uv run ruff format --check .` / `uv run ruff check .` → clean.
- `uv run mypy` → Success: no issues found in 139 source files.
- `uv run pytest` → 484 passed, 3 deselected; coverage 93.78% (gate 85%).
- The graph integration test runs the real services over mock transports and covers: a complete run producing a report and a closed run; the report containing the findings; empty discovery broadening once then reporting an empty week; a failed download leaving papers abstract-only; a parse failure isolated and recorded; a dead model provider still producing a report; a failing source not ending the run; a planner-driven plan reaching the state; and a second run reusing stored analyses and therefore selecting nothing.
- Retry ceilings are set to zero in that test's settings deliberately — the ceilings and their backoff are covered by the F5/F6 tests, and here they only made the failure branches slow (43s → 8.5s).

**Known issues and next step**

- The graph has never run against live providers; every live stage so far has been exercised through its own CLI command. F18's `run` command is what will do that.
- **Next recommended step:** F18 run operations and scheduling — `research-agent run <topic_id>` and `run-all` over this graph, with overlap protection and launchd/cron generation.

## 2026-09-27 — F16 report generation (complete, merged)

- **Feature/branch:** `F16-report-generation`.
- **Commits:** `1ae6cf7` feat(reports): generate weekly research reports; merged as `0f57c73`.
- **Status:** Complete, merged, and re-verified on `main`. The first end-to-end weekly deliverable exists on disk, produced from real papers.

**Behavior added**

- `build_report` assembles every PRD section 13 section as a pure function of stored records, so the same run always renders byte-identical Markdown: topic, period, executive summary, developments, directions, methods, datasets/benchmarks, contradictions, changes from previous weeks, open problems, papers, reading order, gaps, ideas, sources and run provenance.
- **Only the executive summary is model-written**, through the `report_writing` capability. A provider failure, or `--no-prose`, degrades that one paragraph to an assembled sentence; the report itself is never lost.
- The reading order tiers come from the classifier's own action (`deep_read` → Essential, `summarize` → Useful, otherwise Peripheral), so the order is reproducible rather than a second judgement.
- Degradation is stated in the document: a run with errors or a non-clean status carries a degraded banner and lists its recorded errors, and an abstract-only analysis is counted in a banner and marked on its own entry.
- Empty weeks render a short honest report — the run record and provenance, with no invented sections and no model call at all.
- Reports are stored as `YYYY-MM-DD_weekly_report.md` under the topic's `reports` artifacts, written atomically by `LocalArtifactStore`, one per period, so regenerating replaces in place.
- `research-agent report generate --topic <id> [--run] [--days] [--no-prose]` and `research-agent report latest <topic_id>`; `latest` picks by filename, which is why the name starts with the date.

**Files and interfaces**

- New: `src/research_agent/reports/{__init__,naming,prompts,builder,service}.py`, `src/research_agent/utils/markdown.py`, `tests/unit/test_reports_{builder,service}.py`, `tests/integration/test_report_cli.py`.
- Modified: `src/research_agent/storage/artifacts.py` (`ArtifactStore.names`, needed for a deterministic latest-report lookup); `src/research_agent/config.py` (`ReportSettings`); `src/research_agent/cli.py` (`report generate`, `report latest`); `analysis/cards.py` and `ideation/cards.py` now import the shared escaping helpers instead of keeping their own copies.
- No migration: the report is derived from existing records and stored as an artifact.

**Decisions and why**

- **Deterministic assembly, not a model-written report.** The PRD wants a reproducible deliverable with provenance; a model writing the whole document could not guarantee that. Prose is confined to one paragraph, and the report reads correctly without it.
- **`ArtifactStore.names` rather than a database table of reports.** The filesystem already is the artifact index, and the date-first filename makes "newest" a sort, not a query.
- **A third copy of the escaping helpers was not written.** `utils/markdown.py` now holds `inline` and `block`, and both existing card renderers use it. This is reuse of what the feature needed, not an opportunistic refactor.
- Untrusted content is escaped everywhere it enters the document, including the model-written summary, which is treated exactly like any other model output.

**Verification**

- `uv run ruff format --check .` / `uv run ruff check .` → clean.
- `uv run mypy` → Success: no issues found in 131 source files.
- `uv run pytest` → 465 passed, 3 deselected; coverage 93.77% (gate 85%).
- `uv run research-agent report generate --topic embodied_spatial_intelligence` → a 156-line report for the live run, all 16 sections present, with the model-written summary, the degraded banner (2 recorded errors), the abstract-only banner (2 of 4), DOI links in Sources, and the reading order populated from the stored verdicts.
- `uv run research-agent report latest embodied_spatial_intelligence` → returns that same path.
- The integration test drives classify → acquire → parse → analyze → synthesize → ideate → report over mock transports, including the provider-failure path still producing a report.

**Known issues and next step**

- The live report is marked degraded because two of four selected papers had no acquirable PDF (arXiv 406 and a paywalled DOI). That is the acquisition defect already recorded below, not a report defect.
- **Next recommended step:** F17 LangGraph workflow — every stage now exists as an injectable service with a CLI entry point, which is exactly the set of nodes the graph has to wire together.

## 2026-09-27 — F15 research ideation (complete, merged)

- **Feature/branch:** `F15-research-ideation`.
- **Commits:** `1a5293e` feat(ideation): generate supported research directions; merged as `dc96d68`.
- **Status:** Complete, merged, and re-verified on `main`. Verified offline and live against the strong provider over the stored synthesis.

**Behavior added**

- `IdeationService` makes two bounded calls: gaps from the week's stored synthesis, then ideas from the gaps that survived validation. Both stages route through the `ideation` capability, so the router's retry-then-fallback applies unchanged.
- **Traceability is enforced, not requested.** A gap or idea citing a paper outside the run's corpus is dropped; surviving references are pruned, deduplicated and sorted. An idea whose `identified_gap` does not match a gap actually offered is dropped, so no idea can invent the problem it claims to solve.
- Duplicate ideas are collapsed on the normalized title, reusing the F3 `normalize_title` rather than a second notion of sameness.
- `max_gaps` and `max_ideas` are enforced in code as well as stated in the prompt; anything past the ceiling counts as dropped.
- A failure in ideation after gaps were stored keeps the gaps and reports the partial outcome, rather than discarding work that was already validated and persisted.
- `research-agent ideate --topic <id> [--run]` prints each gap and idea with its supporting papers and the dropped counts, writes `<run_id>-ideation.md` under the topic's `runs` artifacts, and exits non-zero with a `MODEL_API_ERROR` when nothing was supported.

**Files and interfaces**

- New: `src/research_agent/ideation/{__init__,prompts,generator,cards}.py`, `tests/unit/test_ideation_{generator,cards}.py`, `tests/integration/test_ideate_cli.py`.
- Modified: `src/research_agent/domain/analysis.py` (`GapDraft`/`IdeaDraft`, with `ResearchGap`/`ResearchIdea` extending them with provider, model and prompt version); `src/research_agent/config.py` (`IdeationSettings`); `src/research_agent/cli.py` (`ideate`).
- No migration: `research_gaps` and `research_ideas` store their models as `payload_json`, and both tables were empty before this branch.

**Decisions and why**

- **Two calls, not one.** Gaps must be validated against the corpus before ideas are built on them; a single call would let an idea rest on a gap that was about to be dropped.
- **The reply is an envelope (`{"gaps": [...]}`)**, because JSON mode requires a top-level object and a bare list is not one.
- **Prompt ceilings are filled in with `str.replace`, not `str.format`.** The prompts contain literal JSON braces, which `format` reads as fields — it raised `KeyError: '"gaps"'` on the first run. A one-line comment on `gap_system_prompt` records why.
- **Confidence stays optional but bounded** by the schema (0-1). A reply with an out-of-range confidence fails validation outright rather than being silently clamped, which is the F6 contract.

**Verification**

- `uv run ruff format --check .` / `uv run ruff check .` → clean.
- `uv run mypy` → Success: no issues found in 122 source files.
- `uv run pytest` → 438 passed, 3 deselected; coverage 93.53% (gate 85%).
- `uv run research-agent ideate --topic embodied_spatial_intelligence` → 5 gaps and 1 idea from the live synthesis, none dropped, every one citing a real paper of the run; artifact written under `data/topics/embodied_spatial_intelligence/runs/`.
- The integration test drives classify → acquire → parse → analyze → synthesize → ideate over mock transports, including a gap citing a non-existent paper being dropped and kept out of the artifact.

**Known issues and next step**

- The live model produced five gaps but only one idea. The prompt allows up to five; whether that is the model or the prompt is worth a look once F16 shows the ideas in a report.
- **Next recommended step:** F16 report generation — every input it needs (analyses, synthesis, gaps, ideas, run summaries) is now persisted.

## 2026-09-27 — F14 weekly synthesis (complete, merged)

- **Feature/branch:** `F14-weekly-synthesis`.
- **Commits:** `caef913` feat(synthesis): add historical weekly synthesis; merged as `c84bf86`.
- **Status:** Complete, merged, and re-verified on `main`. Verified offline and against the real strong provider over four live analyses.

**Behavior added**

- `WeeklySynthesizer` compares a run's analyses with each other and with the topic's recent syntheses, then persists one `WeeklySynthesis` per run. It never raises: a provider failure or malformed output returns a `SynthesisOutcome` carrying the reason and stores nothing.
- `SupportedFinding` makes evidence mandatory rather than optional. `major_developments`, `emerging_directions`, `methods_gaining_attention`, `contradictions` and `common_limitations` are lists of findings, each with the paper ids that support it; `new_datasets`, `new_benchmarks` and `changes_from_history` stay plain strings because they are not per-paper claims.
- **References are validated against the run's own corpus.** An id the run did not analyse is removed; a finding left with no valid id is dropped and counted in `SynthesisOutcome.dropped_findings`. Surviving references are deduplicated and sorted, so the same inputs store byte-identical output.
- History is the previous `synthesis.history_window` syntheses (default four, matching the PRD). With no history the prompt says so explicitly and `changes_from_history` is expected to stay empty; `history_periods` records how many periods were actually compared.
- `research-agent synthesize --topic <id> [--run] [--days]` prints each finding with its supporting ids, plus how many were dropped, and records a `MODEL_API_ERROR` and exits non-zero when no synthesis could be produced.

**Files and interfaces**

- New: `src/research_agent/synthesis/{__init__,prompts,synthesizer}.py`, `tests/unit/test_synthesis_synthesizer.py`, `tests/integration/test_synthesize_cli.py`.
- Modified: `src/research_agent/domain/analysis.py` (`SupportedFinding`, `SynthesisDraft`, and `WeeklySynthesis` now extending the draft with `paper_ids`, provider/model, `prompt_version` and `history_periods`); `src/research_agent/config.py` (`SynthesisSettings`); `src/research_agent/cli.py` (`synthesize`); `src/research_agent/queries/prompts.py` (history bullets now read `finding.text`).
- No migration: `weekly_syntheses` stores the model as `payload_json`, and the table was empty before this branch.

**Decisions and why**

- **`WeeklySynthesis` extends `SynthesisDraft`** rather than duplicating its fields, mirroring the F13 split: the model supplies the draft, the synthesizer adds everything a reader has to be able to trust.
- **An unsupported finding is dropped, not stored with a warning.** The acceptance criterion is that every substantive finding references known supporting papers, and a finding that survives with no reference would quietly break that guarantee in the F16 report.
- **The prompt carries paper ids, not indices**, so a citation can be checked literally against the corpus, and each paper's `abstract_only` depth is stated so the model can hedge on the shallow ones.
- The one consumer of the old `list[str]` history — the F7 query-expansion prompt — was updated in place; it is the only caller, so no compatibility shim was needed.

**Verification**

- `uv run ruff format --check .` / `uv run ruff check .` → clean.
- `uv run mypy` → Success: no issues found in 115 source files.
- `uv run pytest` → 417 passed, 3 deselected; coverage 93.41% (gate 85%).
- `uv run research-agent synthesize --topic embodied_spatial_intelligence` → one synthesis over the four live analyses, served by `nvidia_nim/openai/gpt-oss-20b`: 3 developments, 5 directions, 4 methods, 4 contradictions, 5 limitations, 1 dataset, 4 benchmarks, 0 history periods, every finding citing real paper ids from the run.
- The integration test drives the whole local pipeline — classify, acquire, parse, analyze, synthesize — over mock transports, including a finding citing a non-existent paper being dropped.

**Known issues and next step**

- `changes_from_history` has only ever been exercised with synthetic history (the live topic has one period so far). A second live weekly run is what will show whether the model uses it well.
- **Next recommended step:** F15 research ideation — `ResearchGap` and `ResearchIdea` have existed since F4 with no producer, and the supported findings this branch stores are their input.

## 2026-09-27 — F13 paper analysis (complete, merged)

- **Feature/branch:** `F13-paper-analysis`.
- **Commits:** `40629ba` feat(analysis): add evidence-backed paper analysis; merged as `515a32d`.
- **Status:** Complete, merged, and re-verified on `main`. This is the first feature whose strong/local provider split ran against a real endpoint.

**Behavior added**

- `PaperAnalyzer` turns each selected paper into a validated `PaperAnalysis` and a Markdown paper card. The model supplies only an `AnalysisDraft`; the analyzer adds `paper_id`, `model_provider`, `model_name`, `prompt_version` and `abstract_only`, so nothing a reader has to trust comes from the model.
- Parsed full text is preferred; without it the prompt falls back to title plus abstract and the stored analysis records `abstract_only=True`, which the card states in a banner.
- Claim provenance is validated, not trusted: a claim naming a section the parsed paper does not contain keeps its text and loses `source_section` and `page` rather than persisting a fabricated citation. TRD section 28 makes page/section provenance best-effort.
- `mark_analyzed` is now called on success, closing the gap F10 left open: the next run skips an unchanged paper unless `--force` or `classify --reanalyze` is used.
- `research-agent analyze --topic <id> [--run] [--limit] [--force]` analyses a run's selected papers under `concurrency.analysis`, prints status and depth per paper, and records a `MODEL_API_ERROR` per failure. A stored analysis short-circuits; `--force` re-runs it.
- `analysis/cards.py` renders the PRD section 12 card with a deterministic field order, omitting sections the analysis has nothing to say about. Every value is model- or provider-supplied, so all of it is collapsed to one line and stripped of backticks before rendering.

**Files and interfaces**

- New: `src/research_agent/analysis/{__init__,prompts,analyzer,cards}.py`, `tests/unit/test_analysis_{analyzer,cards}.py`, `tests/integration/test_analyze_cli.py`.
- Modified: `src/research_agent/domain/analysis.py` (`AnalysisDraft`; `prompt_version` and `abstract_only` on `PaperAnalysis`); `src/research_agent/config.py` (`AnalysisSettings`, and the NIM model default); `src/research_agent/cli.py` (`analyze`); `src/research_agent/documents/parser.py` (`load_parsed`); `config/settings.yaml`.
- No migration: `paper_analyses` stores the model as `payload_json`, so the two new fields need no schema change. `prompt_version` is required, which is safe because no analysis row existed before this branch.
- `ParsingService.load` now delegates to a module-level `load_parsed(store, paper_id, topic_id)`, so `analyze` reads stored parses without constructing a parser it would never use — and therefore without importing Docling.

**Decisions and why**

- **The NIM slot is configured properly, not stubbed.** `strong_model_provider: nvidia_nim` in `config/settings.yaml`. Analysis requests `deep_reasoning`, which TRD section 26 fixes to the strong provider, so this finally exercises the real split rather than a mock, and a card now records `nvidia_nim/openai/gpt-oss-20b` as its author.
- **Which model, and why it took four tries.** The strong model had to answer and honour JSON mode. Probed on this account: `meta/llama-3.1-70b-instruct` → HTTP 410 Gone (the old baked-in default, now dead); `deepseek-ai/deepseek-v4.1-flash` → no response within 180s on even a trivial prompt; `nvidia/nemotron-3.5-lightning-30b-a3b` → answers in 8s but writes its chain of thought into `content` and ignores `response_format`, so its reply is never valid JSON; `z-ai/glm-5.3-flash` → valid JSON but ~95s on a trivial prompt and it failed the real analysis prompt. `openai/gpt-oss-20b` answers, honours JSON mode, and keeps its reasoning in the separate `reasoning_content` field the adapter already ignores, so it is configured in both slots for now. `NimEndpointSettings.model` was corrected from the 410 default to the same model; a dead default is not behavior, so it did not warrant its own branch.
- **`max_output_tokens` raised to 4096 in both slots.** A full paper analysis does not fit in the 2048-token default, and a truncated reply is invalid JSON, so the run failed validation rather than producing a short analysis. This is a correctness setting, not tuning, and it is recorded in `config/settings.yaml` with that comment.
- **Repair is not retried here.** The TRD gives the single repair retry to Classifier B alone; analysis uses the F6 contract, so malformed output raises `ModelValidationError` on the first call and becomes a failed outcome without a second request. Verified by asserting exactly one request was sent.
- **Every failure is an outcome, never an exception**, matching F11 acquisition and F12 parsing: one paper's provider failure leaves the rest analyzed and records one error row.

**Verification**

- `uv run ruff format --check .` / `uv run ruff check .` → clean.
- `uv run mypy` → Success: no issues found in 110 source files.
- `uv run pytest` → 400 passed, 3 deselected; coverage 93.50% (gate 85%).
- `uv run research-agent config validate` → valid.
- `uv run research-agent model check` → local `openai/gpt-oss-20b` ready; `nvidia_nim` reports its key as configured (presence only, never the value).
- `uv run research-agent analyze --topic embodied_spatial_intelligence` → 4 of 4 papers analyzed: 2 from parsed full text, 2 abstract-only (no PDF was acquired for those), with cards on disk and four `paper_analyses` rows. Cards run 2.7-4.3 KB.
- **The fallback path ran for real, not against a mock.** During the first live pass the strong provider timed out, the router retried it twice per paper and then degraded to local inference, and all four analyses still completed. That is the first genuine exercise of the NIM-retry-then-local-fallback branch.
- After the strong slot was pointed at a JSON-capable model, `analyze --force --limit 1` produced an analysis served by the strong provider itself: `paper_analyses.model_provider = nvidia_nim`.

**Known issues and next step**

- NIM currently fills both the local and the strong slot, because no local runtime is installed. The fallback branch did run for real (see above), but only because the strong model was temporarily unreachable; installing Ollama and reverting the four `MODELS__LOCAL__*` lines in `.env` is what would make the split genuine rather than incidental.
- `.env` holds the only copy of the API key; it is gitignored and no key material reached the repository, the log, this file, or any card.
- **Next recommended step:** F14 cross-paper synthesis — `WeeklySynthesis` has existed since F4 with no producer, `recent_syntheses` supplies the four-period history window the PRD asks to compare against, and the stored analyses this branch writes are its input.

## 2026-09-24 — F12 PDF parsing (complete, merged)

- **Feature/branch:** `F12-pdf-parsing`.
- **Commits:** `3675650` feat(documents): add structured PDF parsing; merged as `ec86cc5`.
- **Status:** Complete, merged, and re-verified on `main`. Verified offline, under `-m slow`, and against both real arXiv papers.

**Behavior added**

- `ParsedPaper` and its `ParsedSection` / `ParsedTable` / `ParsedFigure` / `ParsedReference` parts (TRD §22), with a `text` property that renders body text as Markdown headings for F13's prompt.
- `DoclingParser` is the only module that imports Docling, and it imports lazily inside the constructor so the rest of the suite never loads torch. It folds body text under the heading that precedes it, routes anything under a references heading into `ParsedReference` instead of body text, and records `parser_name`/`parser_version`.
- `ParsingService` owns everything backend-independent: caching, storage, and failure isolation. A parse failure becomes a `ParseOutcome` with status `failed` and never raises, leaving the paper eligible for abstract-only analysis in F13.
- Each parse writes two artifacts through `LocalArtifactStore`: `<paper_id>.md` for a human and `<paper_id>.json` for the analyzer, and records the Markdown in `paper_files` as `FileKind="parsed"`. `ParsingService.load` reads the JSON back.
- `research-agent parse --topic <id> [--run] [--limit] [--force]` parses the run's acquired PDFs, prints status, section count and path per paper, and records a `PDF_PARSE_ERROR` per failure.

**Files and interfaces**

- New: `src/research_agent/domain/documents.py`, `src/research_agent/documents/{parser,docling_parser}.py`, `tests/unit/test_documents_parser.py`, `tests/integration/test_{docling_parser,parse_cli}.py`, `tests/fixtures/documents/sample.pdf`.
- Modified: `pyproject.toml` (Docling, the Python floor, the `slow` marker); `src/research_agent/cli.py` (`parse`).
- Modified: `.gitignore` — one negation, `!tests/fixtures/documents/*.pdf`, so the deliberately approved sanitized fixture is committed while `*.pdf` stays ignored everywhere else.
- No migration: `paper_files` and `FileKind="parsed"` have existed since F4.

**Decisions and why**

- **Dependency:** `docling>=2.130,<3`, resolving 2.130.0 plus 80 packages including `torch` 2.14 (~2.5 GB). Accepted deliberately: the roadmap names Docling, and the structure it recovers (sections, tables, figures, references) is what F13's claim provenance and the PRD's paper cards need. `docling-slim` (25 packages, no torch) and `pypdf` (1 package, no structure) were the alternatives considered.
- **Deviation, documented:** `requires-python` moved from `>=3.11` to `>=3.12`, and mypy's target with it. Docling's transitive numpy stubs use 3.12-only `type` syntax and cannot be parsed at a 3.11 target; `follow_imports = "skip"` did not suppress it. AGENTS.md allows deviating from the 3.11 baseline with a documented constraint, and this is that constraint. The 3.11 floor was never exercised here anyway — the venv has been 3.14 since F1.
- Docling's `typer` downgrade (0.27.2 → 0.26.8) was verified harmless before any parser code was written: the full suite passed on it.
- Real Docling tests are **deselected, not skipped**: `addopts` carries `-m 'not slow'` and the marker is registered, so `uv run pytest -m slow` runs them explicitly and the default suite never pretends they ran.
- Two defects were found by running a real paper and fixed: `export_to_dataframe()` was called without the document (a deprecation warning per table), and the title fell back to `None` because Docling labels a paper's title as the first `section_header` rather than a `title` item.

**Verification**

- `uv run ruff format --check .` / `uv run ruff check .` → clean.
- `uv run mypy` → Success: no issues found in 103 source files.
- `uv run pytest` → 378 passed, 3 deselected; coverage 93.33% (gate 85%).
- `uv run pytest -m slow` → 3 passed (the real Docling adapter over the committed fixture).
- `uv run research-agent parse --topic embodied_spatial_intelligence` → both real arXiv papers parsed: 61 and 36 sections, 94 KB and 60 KB of Markdown, 175 KB and 91 KB of JSON. An earlier direct run of the larger paper also recovered 28 tables, 6 figures and 72 references.

**Known issues, risks, and unavailable validation**

- **Docling downloads model weights on first use** (~20 MB of RapidOCR models) into the virtualenv. `pytest -m slow` therefore needs network the first time it runs on a fresh checkout. Nothing is committed; the weights live under `.venv`.
- Parsing is slow: roughly 60–90 seconds per full paper on this machine, single-threaded. `ParsingService` is deliberately synchronous and sequential; if that becomes a bottleneck, bounding it with `concurrency.analysis` is the obvious next step.
- The committed fixture PDF is minimal and has no real font hierarchy, so Docling flattens it into one section. It exercises the adapter's plumbing, not its structure recovery; structure was verified by hand against the real papers instead.
- `record_file` stores an empty sha256 for parsed artifacts. The PDF's hash is what caching keys on, so this is unused today, but it is a placeholder rather than a real value.
- Only 2 of 4 selected papers have PDFs at all (F11's open-access reality), so F13 will analyze two full texts and two abstracts.

**Next recommended step:** F13 (`F13-paper-analysis`) as planned: versioned analysis prompt, full-text input from `ParsingService.load` with abstract-only fallback, claim provenance validated against real sections, `mark_analyzed` finally called, and the Markdown paper card. Configure the NIM slot properly first (`strong_model_provider: nvidia_nim` with `deepseek-ai/deepseek-v4.1-flash` or `nvidia/nemotron-3.5-lightning-30b-a3b`) so analysis exercises the real strong/local split.


## 2026-09-24 — FIX1 test environment isolation (complete, merged)

- **Feature/branch:** `FIX1-test-env-isolation`.
- **Commits:** `383bf36` fix(tests): isolate the suite from ambient settings; merged as `610f8ff`.
- **Status:** Complete, merged, and re-verified on `main`.

**The defect**

`ApplicationSettings` reads `.env` and the process environment ahead of any YAML a caller supplies (`settings_customise_sources`, F1). Correct for the application, wrong for the suite: creating the first real `.env` in this repository redirected 27 tests at the developer's own `data/` directory, endpoints, and credentials. Latent since F1; it surfaced only because no `.env` had ever existed here. Any contributor with one would have seen the same failures.

Found while starting `F12-pdf-parsing`: the Docling install was initially suspected, but with `.env` moved aside all 359 tests passed, which isolated the real cause. F12 was parked and this fix taken on its own branch per the AGENTS.md workflow.

**The fix**

- New `tests/conftest.py` with an autouse fixture that deletes every `RESEARCH_AGENT_*` variable for the duration of a test and sets `ApplicationSettings.model_config["env_file"] = None`, disabling the dotenv source. Test-side only; no production code changed.
- `tests/unit/test_environment_isolation.py` asserts the contract directly: no prefixed variables visible, the dotenv source disabled, a supplied `data_directory` not overridden, and `models.local.api_key` unset despite a real key sitting in `.env`.
- `tests/{,unit/,integration/}__init__.py` added, because two `conftest.py` files collided on the module name under strict mypy. Imports changed from `from conftest import ...` to `from tests.unit.conftest import ...` across 18 modules — mechanical, no behavior change.

**Decisions and why**

- Neutralizing the env sources beats `monkeypatch.chdir`: two tests legitimately read the repository's own `config/settings.yaml`, and changing the working directory would have broken them.
- `explicit_package_bases`/`mypy_path` were tried first for the conftest collision and rejected — they broke `src`-layout resolution and produced 311 spurious errors. Package markers are the standard answer.
- The fixture is autouse and unconditional. An opt-in fixture would leave the next new test file exposed to the same failure.

**Verification**

- `uv run ruff format --check .` / `uv run ruff check .` → clean.
- `uv run mypy` → Success: no issues found in 97 source files.
- `uv run pytest` → 363 passed (4 new), coverage 96.79% (gate 85%) — **with the real `.env` present**, which is the condition that failed before.
- Confirmed the same suite passes with `.env` moved aside, so the fix is not merely masking the ordering.

**Known issues, risks, and unavailable validation**

- The fixture reaches into `ApplicationSettings.model_config`, which is pydantic-settings internal structure. It is asserted directly by a regression test, so a library change that breaks it fails loudly rather than silently restoring the leak.
- `.env` itself remains uncommitted and gitignored; no key material reached the repository, the log, or this file.

**Next recommended step:** resume `F12-pdf-parsing` from clean `main`, re-adding `docling>=2.130,<3`. The earlier install was verified harmless: with `.env` aside, the full suite passed on Docling's `typer` 0.26.8 downgrade, so that dependency is not blocked. Note the venv currently holds no Docling (it was reverted with `uv sync`).


## 2026-09-24 — Live inference validation (no code change)

- **Task:** first real end-to-end validation of F6, F7, and F9 against a hosted OpenAI-compatible endpoint. No branch, no commit; this entry records verification and the defects it surfaced.
- **Setup:** NVIDIA NIM standing in for the local runtime. Because TRD §26 routes `cheap_text` and `classification` to the *local* provider, `models.local.base_url` was pointed at `https://integrate.api.nvidia.com/v1` in the uncommitted `.env`. Model: `openai/gpt-oss-20b`, 1 request/second.

**What was validated for the first time**

- **F6 router:** `model check` → `local openai/gpt-oss-20b 668ms`, reply "ready". The `/chat/completions` wire format, bearer auth, latency capture, and token parsing all work against a real endpoint.
- **F6 structured output:** `response_format={"type":"json_object"}` is honoured and returns clean JSON in `message.content`. The model's reasoning trace arrives in a separate `reasoning_content` field, which `_content()` ignores, so no thinking text leaks into validation. This was the single biggest unverified assumption.
- **F7 query expansion:** produced 12 distinct queries with no fallback, base query first, sorted and deduplicated. Previously only the degraded path had ever run.
- **F9 Classifier B:** 5 real verdicts in shadow mode, no repair retries needed, all schema-valid on the first reply. Average latency 7331 ms per paper against 0 ms for lexical Classifier A.
- **F9 comparison:** first run over genuine paired verdicts — **agreement rate 1.00 across 5 papers** (identical action and relevance on every one). Classifier B's `reason_short` values are specific and correct, e.g. rejecting an organisational-transformation paper as "not spatial intelligence".

**Defects and findings**

- **`NimEndpointSettings.model` default is dead.** `meta/llama-3.1-70b-instruct` returns HTTP 410 Gone; the platform retired it. Worth a `FIX` branch to change the default and document that model ids must be checked against the account.
- Most ids returned by `/v1/models` are not entitled to a given account and return 404 with a "Function ... not found for account" body. Four of the twelve ids probed answered: `openai/gpt-oss-20b`, `z-ai/glm-5.3-flash`, `deepseek-ai/deepseek-v4.1-flash`, and `nvidia/nemotron-3.5-lightning-30b-a3b`. The listing is not a capability list, so any model id must be probed before it is configured. The latter two are candidates for the strong-capability slot in F13.
- Classifier A's confidence is visibly cruder than B's: A gave 0.1 confidence to a paper it scored 0.625 (near its own threshold) where B gave 0.92. The F8 note about uncalibrated confidence is confirmed by real data.
- Classifier A's reported average latency is 0 ms because lexical scoring times a whole batch in under a millisecond. Accurate, but it makes the latency column in `compare-classifiers` uninformative for A.

**Still not validated**

- **The local fallback branch.** With NIM in both the local and strong slots, "fall back to local" means falling back to NIM. That route remains mock-only.
- **A genuinely small model.** `gpt-oss-20b` is far stronger than the `qwen3:8b`-class model the TRD specifies for Classifier B. Prompts that succeeded first-try here may still need the repair retry, or tuning, on a small local model.
- The repair retry, provider-failure, and cancellation paths remain mock-only; nothing failed during this sweep.
- Classifier A's embedding half is still unexercised; no embedding model is configured.

**Next recommended step:** unchanged — F12 (`F12-pdf-parsing`), gated on locking a Docling version compatible with this machine's Python 3.14.6. Note that NIM also exposes `nvidia/nemotron-parse` and `nvidia/nemotron-parse-2.0`, which may be worth comparing against Docling before committing to a heavy local dependency. A `FIX` branch for the dead NIM default model is small and can be done at any time.


## 2026-09-24 — F11 PDF acquisition (complete, merged)

- **Feature/branch:** `F11-pdf-acquisition`.
- **Commits:** `507e122` feat(documents): add legal PDF acquisition; merged as `f964d99`.
- **Status:** Complete, merged, and re-verified on `main`. Verified offline and against live arXiv: two real PDFs downloaded and stored.

**Behavior added**

- `PdfDownloader` implements the `DocumentAcquirer` protocol, so F12 and the graph depend on an interface rather than on httpx.
- `pdf_candidates(paper)` is pure and ordered: arXiv derived from `arxiv_id` first, then each source's reported `pdf_url` in a fixed source order (`openalex`, `semantic_scholar`, `arxiv`), deduplicated, `http` upgraded to `https`, and every other scheme dropped. Two runs over the same paper request the same URL first.
- Only open-access locations the sources themselves reported, plus arXiv's public PDF endpoint, are ever requested. There is no publisher-page scraping, no paywall probing, and no bypass fallback of any kind.
- Every response is validated before it can reach disk: status, content type (`application/pdf` or an octet-stream), the `%PDF-` signature, and a size cap. The body is streamed in 64 KiB chunks and abandoned the moment `documents.max_pdf_bytes` is exceeded, so an oversize or mislabeled file is never fully buffered.
- Four outcomes, and nothing raises into the caller: `stored`, `cached` (a file already exists, no request made), `unavailable` (no legal URL — not a failure), `failed` (every candidate exhausted). A failing paper keeps its metadata and stays in the run.
- Retries follow `retries.pdf_download` (2) with exponential backoff, applied only to 429/5xx and transport errors; 4xx is never retried. Downloads run under `concurrency.downloads` with a shared `RateLimiter`.
- Storage is deterministic: `<canonical_id>.pdf` under `data/topics/<topic>/papers/`, written atomically by `LocalArtifactStore`, recorded in `paper_files` with size and sha256.
- `research-agent acquire --topic <id> [--run <id>] [--limit]` reads the selected set from the run's `selections` rows (defaulting to the most recent run), prints a per-paper line plus a status summary, and records one `ErrorRecord` per failure so failures stay visible in the run.

**Files and interfaces**

- New: `src/research_agent/documents/{urls,downloader}.py`, `tests/unit/test_documents_{urls,downloader}.py`, `tests/integration/test_acquire_cli.py`.
- Modified: `src/research_agent/config.py` (`DocumentSettings`); `src/research_agent/cli.py` (`acquire`, `_acquire`, `_latest_run`); `config/settings.yaml`; `tests/unit/test_config.py`.
- No migration: `paper_files` and `FileKind = "pdf"` have existed since F4.

**Decisions and why**

- The downloader is new code under `documents/` rather than an extension of `discovery/http.py`: PDFs need streamed bytes with an early abort, which a text helper capped at 8 MiB cannot express. `RateLimiter` is reused by import. That module is now a fourth consumer, which is exactly the trigger its own `ponytail:` note names for moving it to `utils/http.py` — still deliberately deferred to a `REFACTOR` branch, because AGENTS.md forbids mixing a refactor into a feature.
- `unavailable` and `failed` are distinct statuses. A paper with no open-access URL is a legal outcome, not an error, and should not pollute the run's error count.
- Acquisition is its own command rather than a fourth stage of `classify`: a triage preview should not hit publisher sites, and a rate-limited attempt can be re-run without re-discovering.
- The cached check is a filesystem check, so a re-run after a partial pass costs nothing.

**Verification**

- `uv run ruff format --check .` / `uv run ruff check .` → clean.
- `uv run mypy` → Success: no issues found in 92 source files.
- `uv run pytest` → 359 passed; total coverage 96.79% (gate 85%).
- `uv run research-agent config validate` → Configuration valid: 1 topic(s), 1 enabled.
- `uv run research-agent acquire --topic embodied_spatial_intelligence` → "4 paper(s) for run 13cc5d33562643c5bed348aad70483da: stored 2, unavailable 2". Both arXiv papers downloaded (4.4 MB and 6.5 MB), verified to start with `%PDF-1.7`, and recorded in `paper_files` with their byte sizes. The two publisher DOIs reported no open-access URL and were correctly marked `unavailable`.

**Known issues, risks, and unavailable validation**

- No live download has yet exercised the retry, redirect, or oversize paths; those are covered only by `httpx.MockTransport`. The arXiv downloads succeeded on the first attempt.
- `documents.max_pdf_bytes` is 25 MiB. The two real PDFs were well under it, so the cap has not been hit in practice.
- OpenAlex reports no `pdf_url` for the two publisher papers in this topic, so roughly half a real selection currently yields no document. That is the expected open-access reality, not a defect, but it means F12 will parse fewer papers than are selected.
- Downloaded PDFs live under `data/`, which is gitignored; nothing was committed.
- Classifier B remains unproven against a real model (F9), and nothing calls `mark_analyzed` until F13 (F10).
- The CLI still never calls `observability.logging.configure_logging`, so the downloader's per-candidate warnings print as plain text. Still a `CHORE` candidate.
- The pre-existing `ResourceWarning: unclosed database` from the F2-era tests remains unowned.

**Next recommended step:** F12 (`F12-pdf-parsing`): a document-parser interface with a Docling adapter, `ParsedPaper`/section/table/figure/reference schemas, parser name and version provenance, normalized Markdown written through the artifact store as `FileKind = "parsed"`, cache lookup keyed on the unchanged source PDF, and an explicit abstract-only fallback marker when parsing fails. Note that Docling is a new, heavy dependency — confirm it is acceptable before that branch begins, and keep any large or platform-specific tests marked rather than silently skipped.


## 2026-09-24 — F10 paper selection (complete, merged)

- **Feature/branch:** `F10-paper-selection`.
- **Commits:** `2cbc90b` feat(selection): add bounded paper selection; merged as `8edcfcd`.
- **Status:** Complete, merged, and re-verified on `main`. Verified offline and against live OpenAlex.

**Behavior added**

- `select(verdicts, limits, settings, analyzed, reanalyze) -> SelectionPlan` is pure: no clock, no database, no network, so the same verdicts and limits always produce the same reading set.
- Ranking is a total order: action (`deep_read` > `summarize` > `ignore`), then relevance, then `relevance_score` descending, then `confidence` descending, then `paper_id` ascending. The final key is an identifier, so ties can never reorder between runs.
- Every classified paper gets exactly one `SelectionDecision` with a rank, a selected flag, its action, and a `SelectionReason` value (`selected_deep_read`, `selected_summarize`, `action_ignore`, `below_threshold`, `already_analyzed`, `limit_reached`). Skipped papers stay auditable.
- Limits are enforced: `max_deep_reads` bounds deep reads and `max_downloads` bounds the whole selection. A deep-read paper past the deep-read cap is downgraded to `selected_summarize` rather than dropped, and the decision keeps both its action and its reason so the downgrade is visible.
- Seen-paper policy (TRD §20): `papers` gained `content_hash`, `analyzed_hash`, `first_analyzed_at`, and `last_analyzed_at`. `mark_analyzed` freezes the hash that was analyzed; `analyzed_unchanged` returns papers already analyzed whose content still matches. A revision or an edited abstract changes `content_hash`, which makes the paper eligible again, as does `classify --reanalyze`.
- `classify` now prints `selected N of M: D deep read, S summarize.` plus a rank/decision/reason line per paper, persists the plan to `selections`, and records `papers_selected` and `deep_reads` on the run.

**Files and interfaces**

- New: `src/research_agent/domain/selection.py`, `src/research_agent/selection/{__init__,selector}.py`, `src/research_agent/storage/selections.py`, `tests/unit/test_selection_selector.py`, `tests/unit/test_storage_selections.py`.
- Modified: `src/research_agent/storage/database.py` (schema 18 → 22: four `papers` columns and the `selections` table, one statement per `MIGRATIONS` entry); `src/research_agent/discovery/normalize.py` (`content_hash`); `src/research_agent/storage/papers.py` (`content_hash` stored on upsert, `mark_analyzed`, `analyzed_unchanged`); `src/research_agent/config.py` (`SelectionSettings`); `src/research_agent/cli.py` (`classify --reanalyze`, selection output, plan persistence); `config/settings.yaml`; `tests/unit/test_storage_{papers,migrations}.py`, `tests/unit/test_config.py`, `tests/integration/test_classify_cli.py`.

**Decisions and why**

- A `selections` table rather than run-summary JSON: a threshold change must not silently rewrite what a past run did, and "why was this paper dropped" has to be answerable per paper. F11 reads its input from `selected_for(run_id)`.
- **Deviation from the approved plan:** the plan listed three new `papers` columns; a fourth, `analyzed_hash`, was needed. Comparing `content_hash` to itself can never detect a change, so the hash at analysis time is frozen separately and compared against the current one. Schema is 22 rather than the planned 21.
- Selection folds into `classify` rather than getting its own command: a run is already closed when it is written, so a separate `select --run` would mean either mutating a finished run or inventing a second one.
- Thresholds are configuration (`selection.min_relevance_score`, `selection.require_action`) while the caps stay per topic in `ResourceLimits`, which is where the PRD puts them.
- Only active-classifier verdicts reach `select`; shadow rows are persisted but never passed in.

**Verification**

- `uv run ruff format --check .` / `uv run ruff check .` → clean.
- `uv run mypy` → Success: no issues found in 87 source files.
- `uv run pytest` → 332 passed; total coverage 96.91% (gate 85%).
- `uv run research-agent config validate` → Configuration valid: 1 topic(s), 1 enabled.
- `uv run research-agent classify --topic embodied_spatial_intelligence --limit 5` → 5 live OpenAlex papers classified, "selected 4 of 5: 1 deep read, 3 summarize", the fifth skipped as `action_ignore`, run `13cc5d33562643c5bed348aad70483da` saved with the plan.

**Known issues, risks, and unavailable validation**

- The seen-paper path has been exercised only through the integration test and unit tests; no real run has yet called `mark_analyzed`, because nothing analyzes papers until F13. Until then `analyzed_unchanged` always returns empty in practice.
- `min_relevance_score` (0.3) interacts with Classifier A's untuned thresholds from F8. On the live run every non-ignored paper cleared it, so the gate has not actually excluded anything yet.
- Classifier B remains unproven against a real model, unchanged from F9; shadow verdicts are still never produced locally.
- Semantic Scholar 429 and arXiv 406 persist from F5; OpenAlex answered.
- The CLI still never calls `observability.logging.configure_logging`; the "classification failed; the paper is skipped" line in the live run is a plain-text warning for exactly this reason. Still a `CHORE` candidate.
- The pre-existing `ResourceWarning: unclosed database` from the F2-era tests remains unowned.

**Next recommended step:** F11 (`F11-pdf-acquisition`): an async downloader behind a document-acquisition interface, reading its input from `SqliteSelectionRepository.selected_for(run_id)`, with open-access URL policy, content-type and signature validation, a configurable size cap, deterministic filenames, atomic writes through the F4 artifact store, two download retries, and per-paper failure isolation that keeps metadata-only papers in the run.


## 2026-09-23 — F9 classifier B and shadow mode (complete, merged)

- **Feature/branch:** `F9-classifier-b-shadow-mode`.
- **Commits:** `2d5cf41` feat(classifiers): add classifier B and shadow execution; merged as `d6758af`.
- **Status:** Complete, merged, and re-verified on `main`. Classifier B has not run against a real model; see known issues.

**Behavior added**

- `ClassifierB` classifies through `ModelRouter.generate("classification", ..., ClassifierVerdict)` and never touches a provider. Malformed structured output is repaired exactly once with `REPAIR_INSTRUCTION`; a second failure raises `ClassifierError` with `INVALID_CLASSIFIER_OUTPUT` and costs no further calls.
- `ClassifierVerdict` is the six-field schema a model may produce. `paper_id`, `classifier_name`, and `latency_ms` are filled in by the adapter, so a model can never supply its own provenance.
- Batches run with bounded concurrency (`concurrency.analysis`); a paper that fails is logged and skipped rather than ending the batch.
- Prompts are versioned (`classification.v1`) and the abstract is truncated at `classifier_b.max_abstract_chars` (default 2000) with the truncation stated in the prompt.
- `build_classifier(name, client, settings)` (TRD §13) is the only place either implementation is constructed; `"A"`/`"B"` are case-insensitive and anything else raises.
- `ClassifierRunner` runs the active classifier, then the shadow inside a catch-all. A shadow failure is logged, recorded on `ClassifierOutcome.shadow_error`, and never reaches routing. Shadow verdicts persist with `is_active = 0`.
- `research-agent classifier set A|B --topic <id> [--shadow A|B|none]` switches a topic's classifiers; validation reuses `ClassifierSettings`, so a shadow equal to the active one is rejected before the write.
- `research-agent compare-classifiers <topic_id> [--runs N]` and `python scripts/compare_classifiers.py <topic_id> [runs]` report agreement rate, disagreement count, average latency and confidence, and action/relevance distributions from stored verdicts. Both call the same pure `compare`/`render`.

**Files and interfaces**

- New: `src/research_agent/classifiers/{prompts,classifier_b,factory,runner,comparison}.py`, `scripts/compare_classifiers.py`, `tests/unit/test_classifiers_{b,factory,runner,comparison}.py`, `tests/integration/test_classifier_cli.py`.
- Modified: `src/research_agent/classifiers/base.py` (`Provenance`, `explain_many` promoted into the protocol); `src/research_agent/domain/analysis.py` (`ClassifierVerdict`); `src/research_agent/config.py` (`ClassifierBSettings`); `src/research_agent/storage/results.py` (`classification_pairs`); `src/research_agent/storage/topics.py` (`set_classifier`); `src/research_agent/cli.py` (`classify` now runs through the factory and runner and saves shadow rows; two new commands); `config/settings.yaml`; the three affected test modules.
- No migration: `classifications.is_active` and the topics classifier columns have existed since F2/F4.

**Decisions and why**

- The repair retry lives in Classifier B, not the router. `ModelRouter._validated` raises `ModelValidationError` and deliberately never retries (F6), which is exactly what lets the classifier own the one repair the TRD allows.
- `compare-classifiers` reads stored verdicts rather than re-classifying: the numbers were already recorded by shadow mode, so the report needs no model and is reproducible. Agreement is measured on `action`, because that is what controls the run.
- Agreement is computed only over papers both classifiers judged; comparing different sets would not be a comparison.
- `explain_many` was promoted into the protocol so the runner and the CLI persist provenance without knowing which implementation they hold.
- Shadow isolation lives in the runner alone, so no call site can forget it.
- `classifier set` is per topic and requires `--topic`, because that is where the setting already lives; no application-level duplicate was introduced.

**Verification**

- `uv run ruff format --check .` / `uv run ruff check .` → clean.
- `uv run mypy` → Success: no issues found in 81 source files.
- `uv run pytest` → 302 passed; total coverage 96.74% (gate 85%).
- `uv run research-agent config validate` → Configuration valid: 1 topic(s), 1 enabled.
- `uv run research-agent classifier set A --topic embodied_spatial_intelligence --shadow B` → "active A, shadow B", persisted.
- `uv run research-agent classify --topic embodied_spatial_intelligence --limit 3` → **3 real OpenAlex papers classified by Classifier A** (`high/deep_read` for one, `medium/summarize` for two), run `8b97ab13d9a14aedb1a55c0ffc0c7a7a` saved. This closes F8's open item: Classifier A has now scored live discovery results.
- `compare-classifiers` and `scripts/compare_classifiers.py` both exit 1 with "No shadow verdicts stored", which is correct: Classifier B produced nothing without a local model.

**Known issues, risks, and unavailable validation**

- **Classifier B has never run against a real model.** Every path is covered by `httpx.MockTransport`, but no local runtime is installed here, so prompt wording, repair behavior, and verdict quality are unproven. Install one (`ollama serve` plus a `qwen3:8b`-class model) and re-run `classify` with a shadow before trusting B.
- Because per-paper failures are isolated inside `ClassifierB`, a completely unavailable model yields "shadow classifier B: 0 verdict(s)" rather than a single loud error; the reason appears in the per-paper warnings. `ClassifierOutcome.shadow_error` only fires for a batch-level failure.
- The comparison has therefore never been produced from real paired verdicts — only from mocked ones in tests.
- Semantic Scholar 429 and arXiv 406 persist from F5. OpenAlex answered this time.
- The CLI still never calls `observability.logging.configure_logging`, so classifier warnings print as plain text. Unchanged since F6; still a `CHORE` candidate, and it matters more now that shadow failures are only visible in logs.
- `discovery/http.py` still holds the shared retry helper with its `ponytail:` note; moving it to `utils/http.py` remains a `REFACTOR` branch.
- The pre-existing `ResourceWarning: unclosed database` from the F2-era tests remains unowned.

**Next recommended step:** F10 (`F10-paper-selection`): deterministic ranking and tie-breaking over active-classifier verdicts, configurable relevance/action thresholds, enforcement of the candidate/classification/download/deep-read limits, seen-paper lookup with first/last seen and analyzed timestamps, and auditable selection reasons. It depends only on F4 and F9, both of which are now merged.


## 2026-09-22 — F8 classifier A integration (complete, merged)

- **Feature/branch:** `F8-classifier-a-integration`.
- **Commits:** `63731c6` feat(classifiers): integrate classifier A; merged as `a43fede`.
- **Status:** Complete, merged, and re-verified on `main`. Live discovery was rate-limited during the manual check; see known issues.

**Behavior added**

- `PaperClassifier` protocol (TRD §10) with `classify` / `classify_many`, plus `ClassifierError` carrying the `CLASSIFIER_ERROR` / model error categories.
- `ClassifierA` produces only the normalized `ClassificationResult`: relevance, relevance score, paper type, action, confidence, reason, and latency. It is deterministic and offline by default.
- Scoring is lexical: topic name (weight 2) and each keyword (weight 1) matched against the normalized title and abstract, exact title > fuzzy title > exact abstract > fuzzy abstract, with individual name tokens contributing to the numerator only so a long topic name does not raise the bar for matching it. RapidFuzz supplies the near-match floor; no new dependency.
- When `classifier_a.embedding_model` is set, `EmbeddingClient` embeds the topic and the whole batch in one `/embeddings` request and the score becomes `(1 - w) * lexical + w * cosine`. Any embedding failure logs one structured warning and falls back to the lexical verdict — it never fails a paper or a run.
- `paper_type` comes from an ordered cue table (`survey` → `benchmark` → `dataset` → `application` → `method`, else `other`); first match wins, so it is reproducible.
- `explain_many` returns each verdict with the audit payload (`version`, `lexical_score`, `embedding_score`, `embedding_weight`, `matched_terms`) that is stored in the existing `classifications.raw_response_json`.
- `research-agent classify --topic <id> [--query] [--days] [--limit] [--no-save]` discovers and triages in one command. With `--save` it starts a run, upserts each paper, stores every verdict, and completes the run as `degraded` when any source failed.

**Files and interfaces**

- New: `src/research_agent/classifiers/{base,lexical,embeddings,classifier_a}.py`, `tests/unit/test_classifiers_{lexical,embeddings,a}.py`, `tests/integration/test_classify_cli.py`.
- Modified: `src/research_agent/config.py` (`ClassifierASettings` and the `classifier_a` field); `src/research_agent/cli.py` (`classify`, `_classify`, `_embedder`, `_save_classifications`); `config/settings.yaml`; `tests/unit/test_config.py`; `tests/unit/test_storage_results.py`.
- No migration: `classifications` has existed since F4 and `SqliteResultRepository.save_classification` was already the right seam.

**Decisions and why**

- **Deviation from the roadmap prerequisite, recorded deliberately.** `docs/FEATURE_ROADMAP.md` F8 requires obtaining the pre-existing Jev-style Classifier A before the branch begins and forbids inventing one. It is not available in this repository, and the user directed me to implement it instead. Nothing here is trained or fine-tuned, which the product guardrails forbid; it is a deterministic decision classifier. Per TRD §11, swapping in a real implementation should change only `classifier_a.py`.
- **The protocol is async**, unlike the synchronous sketch in TRD §10. Classifier B must await `ModelRouter` in F9 and Classifier A awaits embeddings; one async contract serves both, and a sync protocol serves neither.
- **Relevance and action share two thresholds** (`summarize_at`, `deep_read_at`). Two independent knob sets can contradict each other and there is no evidence yet to separate them.
- **Confidence is the distance to the nearest decision boundary**, saturating at 0.25. It is honest about certainty near a threshold; a calibrated probability would need labelled data that v1 does not collect. Marked with a `ponytail:` comment.
- **Provenance goes in `raw_response`, not `classifier_name`**, so a stored verdict can be re-read and re-tuned without parsing a name string.
- **Batch embeddings, not per-paper.** One request per batch keeps the optional path cheap and preserves the TRD's batch-support requirement.

**Verification**

- `uv run ruff format --check .` / `uv run ruff check .` → clean (72 files).
- `uv run mypy` → Success: no issues found in 71 source files.
- `uv run pytest` → 257 passed; total coverage 96.66% (gate 85%).
- `uv run research-agent config validate` → Configuration valid: 1 topic(s), 1 enabled.
- `uv run research-agent classify --topic embodied_spatial_intelligence --limit 5 --days 30` → exit 0, run `12176160b9f1464ea8f3163399602d93` persisted with status `degraded`, `models_used: ["lexical"]`, `errors: 3`. All three sources were rate-limited at the time (OpenAlex 429, Semantic Scholar 429, arXiv 406), so zero candidates reached the classifier.

**Known issues, risks, and unavailable validation**

- **Classifier A has never scored a live discovery result.** Every source returned 429/406 during the manual check, so real-paper triage is covered only by the mocked integration test. Re-run `research-agent classify` when OpenAlex is not rate-limiting this machine before trusting the thresholds.
- The embedding path has never run against a real embedding server; only `httpx.MockTransport` has exercised it. `classifier_a.embedding_model` is unset by default, so the shipped behavior is purely lexical.
- The default thresholds (0.3 / 0.6) are untuned guesses. They are configuration, so tuning needs no code change, but they should be revisited against real verdicts in F10.
- OpenAlex now also returns 429 for this machine's usage pattern, which is new since F7; the arXiv 406 and Semantic Scholar 429 are unchanged from F5.
- The CLI still never calls `observability.logging.configure_logging`, so the classifier's degradation warning prints as plain text rather than JSON. Unchanged since F6 and still worth a `CHORE` branch.
- `discovery/http.py` now has its third consumer, which is the trigger its own `ponytail:` note names for moving it to `utils/http.py`. That is a `REFACTOR` branch, deliberately not mixed into this feature.
- The pre-existing `ResourceWarning: unclosed database` from the F2-era tests remains unowned.

**Next recommended step:** F9 (`F9-classifier-b-shadow-mode`): the Qwen-style classifier over `ModelRouter.generate("classification", ...)` with a versioned structured prompt, Pydantic validation and the one repair retry the TRD allows, the A/B factory, shadow execution persisted with `is_active=false`, and `compare-classifiers`. It needs a local runtime to be exercised, so install one (`ollama serve` plus a `qwen3:8b`-class model) first. Alternatively, F10 (`F10-paper-selection`) is unblocked by Classifier A alone.


## 2026-09-22 — F7 search query planning (complete, merged)

- **Feature/branch:** `F7-search-query-planning`.
- **Commits:** `53a6cd4` feat(queries): add semantic search planning; merged as `8c2b6d2`.
- **Status:** Complete, merged, and re-verified on `main`. Verified end to end offline and against live OpenAlex.

**Behavior added**

- `QueryPlanner.plan(topic, history)` expands a topic through `ModelRouter.generate("cheap_text", ..., ExpandedQueries)` and never touches a provider directly. Any `ModelProviderError`, including `ModelValidationError`, degrades to the deterministic plan with `fell_back=True` and one structured warning; the planner cannot fail a run.
- `base_query(topic)` is pure: normalized topic name plus its first two keywords, always the first entry of a plan, with the topic id as a last resort so a plan is never empty.
- Determinism lives in the planner, not the model: expansions are normalized with `normalize_text`, stripped of anything shorter than three characters, deduplicated case-insensitively, sorted, padded from topic keywords up to `min_queries`, and truncated at `max_queries`. Two runs with the same inputs produce identical plans regardless of the order the model answered in.
- `QueryPlan` records `prompt_version`, provider, model, and `fell_back`, and `SqliteQueryPlanRepository.save(plan, run_id=None)` persists it; `run_id` is nullable so a CLI preview is auditable before F14 exists.
- Topics now carry `keywords`, settable with `research-agent topic add --keyword` (repeatable).
- `research-agent queries plan --topic <id> [--no-save]` prints the plan header and one query per line.

**Files and interfaces**

- New: `src/research_agent/domain/queries.py` (`ExpandedQueries`, `QueryPlan`), `src/research_agent/queries/{__init__,prompts,planner}.py`, `src/research_agent/storage/queries.py`, `tests/unit/test_queries_planner.py`, `tests/unit/test_storage_queries.py`, `tests/integration/test_queries_cli.py`.
- Modified: `src/research_agent/storage/database.py` (schema 15 → 18: `topics.keywords_json`, the `query_plans` table, and `query_plans_topic_idx`, one statement per `MIGRATIONS` entry as before); `src/research_agent/config.py` (`TopicSettings.keywords`, `QuerySettings`, `queries` on `ApplicationSettings`); `src/research_agent/storage/topics.py` (keywords round-trip); `src/research_agent/cli.py` (`_open_connection` split out of `_open_repository`, `topic add --keyword`, the `queries` sub-app).

**Decisions and why**

- A `query_plans` table rather than deferring persistence to F14: the acceptance criterion is that the resolved plan can be audited later, and a nullable `run_id` lets that hold today without inventing a run.
- Keywords were added to the topic schema now because TRD §17 names them as planner input; deferring would have meant reopening the topics table, repository, and CLI in a later branch.
- The prompt is a module constant with `PROMPT_VERSION = "query_expansion.v1"`. A wording change means a new version string, and every persisted plan names the prompt that produced it.
- Padding from keywords applies in the fallback path too, so an offline run still issues more than one search when the topic defines keywords.

**Verification**

- `uv run ruff format --check .` / `uv run ruff check .` → clean.
- `uv run mypy` → Success: no issues found in 63 source files.
- `uv run pytest` → 205 passed; total coverage 96.86% (gate 85%).
- `uv run research-agent config validate` → Configuration valid: 1 topic(s), 1 enabled.
- `uv run research-agent queries plan --topic embodied_spatial_intelligence` → fell back (nothing serving localhost:11434) and printed the base query, exit 0.
- Feeding that query into `research-agent discover --limit 3` returned 3 real OpenAlex candidates, with Semantic Scholar 429 and arXiv 406 tolerated as source errors.

**Known issues, risks, and unavailable validation**

- Semantic expansion has still never run against a real model; only the fallback path has been exercised end to end. Install a local OpenAI-compatible runtime and re-run `queries plan` before trusting the expansion quality or the prompt wording.
- The CLI never calls `observability.logging.configure_logging`, so planner and router warnings print as plain text rather than structured JSON. Pre-existing since F6; worth a `CHORE` branch when the graph starts emitting real run logs.
- The arXiv HTTP 406 and Semantic Scholar 429 from F5 are unchanged and still visible in live runs.
- The pre-existing `ResourceWarning: unclosed database` from the F2-era tests remains unowned.

**Next recommended step:** F8 (`F8-classifier-a-integration`) is blocked on a prerequisite the roadmap states explicitly: locate or obtain the actual Classifier A implementation, weights, and usage terms before creating the branch. Do not invent or substitute a classifier. If Classifier A is not available, the next unblocked work is `F13-report-generation` or a `CHORE` branch for the structured-logging gap above.

## 2026-09-22 — F6 model provider routing (complete, merged)

- **Feature/branch:** `F6-model-provider-routing`.
- **Commits:** `a3be3c9` feat(models): add capability-based provider routing; merged as `9e4e398`.
- **Status:** Complete, merged, and re-verified on `main`. Live inference was not exercised (no local runtime is installed on this machine and no NIM key is configured); see known issues.

**Behavior added**

- `ModelProvider` protocol (TRD §23) with `ModelMessage`, `ModelResult` (provider, model, text, token counts, latency, `fell_back`, validated `parsed`), `ModelProviderError` carrying `MODEL_API_ERROR` / `MODEL_TIMEOUT`, and `ModelValidationError` for schema failures.
- `ChatCompletionsProvider` speaking the OpenAI-compatible `/chat/completions` shape, with `LocalModelProvider` (any local server: Ollama, LM Studio, llama.cpp) and `NvidiaNIMProvider` (`configured` only with an API key) as configured subclasses.
- `ModelRouter.generate(capability, messages, response_schema=None)` per TRD §26: `cheap_text` and `classification` run locally; `deep_reasoning`, `synthesis`, `ideation`, `report_writing` run on the strong provider with `retries.nim` retries (default 2) then a local fallback marked `fell_back=True`. An unknown capability raises `ValueError`; a local failure propagates.
- Structured output is parsed and validated against the caller's Pydantic model. Validation failures raise `ModelValidationError` and are never retried or fallen back on, because the TRD gives the single repair retry to Classifier B (F9).
- `research-agent model check [--capability] [--prompt]` prints the configured endpoints (key presence only, never the value), routes one small prompt, and prints `provider model latency`, exiting 1 on failure.

**Files and interfaces**

- New: `src/research_agent/models/{base,chat,router}.py`, `tests/unit/test_models_{chat,router}.py`, `tests/integration/test_model_cli.py`.
- Modified: `src/research_agent/config.py` (`ModelEndpointSettings`, `NimEndpointSettings`, `ModelSettings`, and the `models` field on `ApplicationSettings`); `src/research_agent/discovery/http.py` (POST/JSON-body support plus `error_category` / `transient_category` overrides — existing call sites unchanged); `src/research_agent/cli.py` (`model check`); `config/settings.yaml` and `.env.example` (endpoints only; the NIM key is env-only and redacted).

**Decisions and why**

- One OpenAI-compatible adapter for both providers: NIM speaks the same wire format, so a second adapter would have been duplicate code, and no new dependency was needed (`httpx` arrived in F5).
- The capability table is code, not configuration: TRD §26 fixes it, and a settings table for a value with one correct answer buys nothing.
- The F5 retry loop was extended in place rather than copied. It still lives under `discovery/` with a `ponytail:` comment; it should move to `utils/http.py` once a third consumer appears, which would be a refactor branch of its own rather than part of this feature.
- NIM defaults live on `NimEndpointSettings` rather than a field default. A test caught that with the previous shape, setting only `RESEARCH_AGENT_MODELS__NIM__API_KEY` silently reset the NIM base URL and model to the local defaults.
- Model calls are not persisted; no table exists for them and `RunSummary.models_used` covers provenance in F14.

**Verification**

- `uv run ruff format --check .` → 55 files already formatted.
- `uv run ruff check .` → All checks passed.
- `uv run mypy` → Success: no issues found in 55 source files.
- `uv run pytest` → 181 passed; total coverage 96.75% (gate 85%).
- `uv run research-agent config validate` → Configuration valid: 1 topic(s), 1 enabled.
- `uv run research-agent model check` → reported both endpoints, then exited 1 with "transport error: All connection attempts failed" because nothing is serving `localhost:11434` here. That is the correct degraded behavior, but it is not a successful inference.

**Known issues, risks, and unavailable validation**

- No real completion has been produced end to end. Install a local OpenAI-compatible runtime (`ollama serve` plus a `qwen3:8b`-class model) and re-run `research-agent model check` before relying on F7 or F9.
- `max_tokens` is the legacy OpenAI field name; some newer endpoints prefer `max_completion_tokens`. Ollama and NIM both accept `max_tokens` today.
- HTTP 5xx from a model endpoint is categorized `MODEL_TIMEOUT` because the shared helper treats every retryable status as transient. It is accurate about recoverability, coarse about cause.
- The pre-existing `ResourceWarning: unclosed database` from the F2-era tests is still present and still unowned.

**Next recommended step:** Create `F7-search-query-planning` and add the query planner: a versioned prompt, local semantic expansion over topic name, keywords, and the available historical summary, validation and stable deduplication down to roughly 5–20 queries, a deterministic base query used when inference is unavailable, and persisted plan provenance. It should call `ModelRouter.generate("cheap_text", ...)` with a Pydantic response schema rather than any provider directly.

## 2026-09-22 — F5 academic discovery (complete, merged)

- **Feature/branch:** `F5-academic-discovery`.
- **Commits:** `2a212cd` feat(discovery): add academic source adapters; merged as `2f9c7a1`.
- **Status:** Complete, merged, and re-verified on `main`; one live-API limitation documented below.

**Behavior added**

- `ResearchSource` protocol (TRD §15) plus `OpenAlexSource`, `SemanticScholarSource`, and
  `ArxivSource`, each translating provider payloads into `PaperCandidate` through the F3
  normalizers. Malformed records are skipped individually and logged; they never fail a page.
- Shared resilience layer `discovery/http.py`: per-provider `RateLimiter`, `request_text` /
  `request_json` with the configured retry ceiling (default 3), exponential backoff, `Retry-After`
  honored on 429/503, no retry on non-429 4xx, and an 8 MiB response cap before parsing.
- `DiscoveryAggregator`: bounded concurrency (`concurrency.discovery`), `asyncio.gather` with
  failure isolation into `ErrorRecord`s, a per-run cache keyed on
  `(source, query, start, end, limit)`, and a final `deduplicate(...)` so callers get one merged
  set with per-source counts.
- `research-agent discover --topic <id> --query <text> [--days] [--limit]` prints per-source
  counts, tolerated source errors, and the candidate table.

**Files and interfaces**

- New: `src/research_agent/discovery/{http,sources,openalex,semantic_scholar,arxiv,aggregator}.py`.
- Modified: `src/research_agent/config.py` (`SourceSettings`, `DiscoveryClientSettings`, and the
  `sources` field on `ApplicationSettings`), `src/research_agent/cli.py` (`discover` plus the
  `_http_client` factory tests replace), `pyproject.toml` (`httpx>=0.27,<1`), `.env.example`
  (commented, redacted `RESEARCH_AGENT_SOURCES__*` lines).
- New tests: `tests/unit/test_discovery_{http,sources,aggregator}.py`,
  `tests/integration/test_discovery_cli.py`, static fixtures in `tests/fixtures/discovery/`.

**Decisions**

- **httpx** is the second runtime dependency (user decision): real async I/O and
  `httpx.MockTransport`, so every test runs offline with no extra test dependency.
- **No `pytest-asyncio`** — tests drive coroutines with `asyncio.run`, so no new dev dependency.
- **Discovery never writes to SQLite** (user decision). The aggregator returns candidates; the F14
  graph node will call `SqlitePaperRepository.upsert`. This **corrects** the F4 entry below, which
  said F5 would persist via `upsert`.
- Semantic Scholar filters by year only, so the exact date window is applied client-side; arXiv is
  filtered client-side on `published` for the same reason.
- arXiv Atom is parsed with stdlib `ElementTree` under the response cap, with a `ponytail:` note
  naming `defusedxml` as the upgrade path if hardening is ever needed.
- Default pacing after live testing: OpenAlex 5/s (polite pool), Semantic Scholar 0.2/s (the
  unauthenticated pool 429s at 1/s), arXiv 0.33/s (their published one-request-per-three-seconds
  guidance).

**Verification**

- `uv run ruff format --check .` / `uv run ruff check .` → clean; `uv run mypy` → no issues in 49
  source files; `uv run pytest` → 145 passed, coverage 96.47% (gate 85%).
- `uv run research-agent config validate` → Configuration valid: 1 topic(s), 1 enabled.
- **Live smoke test** (`discover --topic embodied_spatial_intelligence --days 30 --limit 6`):
  returned 6 real OpenAlex candidates while Semantic Scholar 429'd and arXiv failed — exactly the
  designed degraded behavior, with both failures reported as source errors and exit code 0. This
  is how the arXiv and pacing issues below were found.

**Known issues / assumptions**

- **arXiv returned HTTP 406 to httpx while `curl` and stdlib `urllib` got 200 for the same URL**,
  and began answering 429 under repeated probing from this machine. A descriptive `User-Agent`,
  an `application/atom+xml` accept header, HTTPS, and 0.33 req/s are now sent, but the 406 was not
  fully root-caused before the rate limit made further isolation unproductive. Adapter logic is
  covered by fixtures; worth a `FIX1-arxiv-406` branch that retests from a cold IP and, if it
  persists, compares the exact wire headers httpx and curl send.
- Semantic Scholar without an API key is heavily throttled; set
  `RESEARCH_AGENT_SOURCES__SEMANTIC_SCHOLAR_API_KEY` in `.env` for reliable use. Never committed.
- Live smoke tests are deliberately absent from the default suite, per the roadmap.
- Pre-existing `ResourceWarning: unclosed database` from the F2 tests remains (13 warnings).

**Next recommended step:** Create `F6-model-provider-routing` and add the capability-based model
router with the local provider first, the optional NVIDIA NIM provider behind it, two-retry NIM
handling then local fallback, and no hardcoded model names or endpoints in workflow logic. Git:
`feat(models): add capability-based model routing` / `merge: F6-model-provider-routing route model
work by capability`.

## 2026-09-22 — F4 metadata and artifact persistence (complete, merged)

- **Feature/branch:** `F4-metadata-artifact-persistence`.
- **Commits:** `c36f9b7` feat(storage): add metadata and artifact persistence; merged as `2aded5b`.
- **Status:** Complete, merged, and re-verified on `main`.

**Behavior added**

- Schema version 1 → 15. New tables: `runs`, `papers`, `paper_sources`, `paper_files`,
  `classifications`, `paper_analyses`, `weekly_syntheses`, `research_gaps`, `research_ideas`,
  `errors`, plus indexes on `papers(doi)`, `papers(arxiv_id)`, `runs(topic_id, started_at)`, and
  `weekly_syntheses(topic_id, created_at)`. Every migration entry is a single statement, so the
  existing `apply_migrations` transaction and `PRAGMA user_version` logic are unchanged.
- `SqlitePaperRepository`: idempotent `upsert` (one `INSERT ... ON CONFLICT` that refreshes
  `last_seen_at`, fills previously-missing metadata via `COALESCE`, and keeps the larger citation
  count), `get` rebuilding a full `PaperCandidate` with its sources, `seen` for cache lookups, and
  `record_file` / `files_for` for stored artifacts.
- `SqliteRunRepository`: `start` / `complete` (duration derived from the stored start time),
  `get`, `recent`, `record_error`, `errors_for`. Error rows accept a `paper_id` that has no paper
  row, so a failure is never lost because its paper was not persisted.
- `SqliteResultRepository`: save/read pairs for classifications (active and shadow), analyses,
  syntheses, gaps, and ideas, plus `recent_syntheses(topic_id, limit=4)` — the TRD §44 history
  window — and `analysis_for(paper_id)` as the re-read cache lookup.
- `LocalArtifactStore`: the TRD §35 layout `data/topics/<topic_id>/{papers,parsed,analyses,
  reports,runs}/`, deterministic `safe_name` filenames, containment-checked paths, and atomic
  writes (temp file in the destination directory then `os.replace`).

**Files and interfaces**

- New: `src/research_agent/domain/runs.py` (`RunStatus`, `ErrorCategory` per TRD §39, `RunRecord`,
  `RunSummary`, `ErrorRecord`), `src/research_agent/domain/analysis.py` (`ClassificationResult`
  per TRD §10, `Claim`, `PaperAnalysis`, `WeeklySynthesis`, `ResearchGap`, `ResearchIdea` per
  TRD §27–31).
- New: `src/research_agent/storage/papers.py`, `runs.py`, `results.py`, `artifacts.py`, each
  exposing a `Protocol` plus its SQLite/local implementation, mirroring `storage/topics.py`.
- Modified: `src/research_agent/storage/database.py` (10 tables + 4 indexes appended to
  `MIGRATIONS`; new `now_iso()` helper shared by the new repositories).
- New tests: `tests/unit/conftest.py` (migrated database seeded with one topic, closed on
  teardown) and `test_storage_{migrations,papers,runs,results,artifacts}.py`.
- No configuration change; `ApplicationSettings.data_directory` is the `LocalArtifactStore` root.

**Decisions**

- **Indexed columns + `payload_json`** for the five model-produced entities (user decision).
  Repositories still take and return validated Pydantic models, so the interface is unchanged, but
  F11/F12 can extend a schema without a migration and F4 avoids ~60 columns of hand mapping. The
  cost is that those fields are not directly queryable in SQL; nothing in the PRD/TRD requires it.
- **All 10 TRD §33 entities implemented now** (user decision), so F8–F12 need no storage work.
- **`papers.id` is the F3 `canonical_id`**, which makes upserts naturally idempotent and lets
  artifact filenames derive from the same stable value.
- **Four storage modules, not ten repositories**, grouped by write path rather than by table.
- Timestamps are UTC ISO-8601 strings in every column, matching the F2 `topics` convention.
- `safe_name` sanitizes rather than rejects most hostile names (`../../x.pdf` → `x.pdf`); genuinely
  unusable names (`..`, empty, `///`) raise `ArtifactPathError`, and the resolved path is still
  containment-checked against the topic directory. Tested both ways.

**Verification**

- `uv run ruff format .` → 39 files left unchanged; `uv run ruff check .` → All checks passed.
- `uv run mypy` → Success: no issues found in 39 source files.
- `uv run pytest` → 117 passed, 13 warnings; total coverage 97.12% (gate 85%).
- `uv run research-agent config validate` → Configuration valid: 1 topic(s), 1 enabled.
- A genuine schema-version-1 database (only `topics`, `user_version = 1`) upgrades in place with
  its rows intact — covered by `test_a_version_one_database_upgrades_in_place`.

**Known issues / assumptions**

- Pre-existing `ResourceWarning: unclosed database` from the F2 tests remains (13 warnings); the
  new `connection` fixture closes its handle, so no new warnings were added. Still worth a chore.
- No CLI surface for the new repositories yet; they are wired up by F5 and later features.
- `paper_files` enforces one file per `(paper_id, kind)`; a second PDF for the same paper replaces
  the first. That matches the deterministic-filename rule and can be relaxed if F10 needs versions.

**Next recommended step:** Create `F5-academic-discovery` and add the `ResearchSource` protocol
with the OpenAlex, Semantic Scholar, and arXiv adapters, translating provider payloads into
`PaperCandidate` and persisting via `SqlitePaperRepository.upsert`, with per-source pacing,
429/`Retry-After` handling, three-retry backoff, bounded concurrency, and partial-source failure
isolation. Git: `feat(discovery): add academic source adapters` / `merge: F5-academic-discovery
search required academic sources`.

## 2026-09-22 — F3 paper normalization and deduplication (complete, merged)

- **Feature/branch:** `F3-paper-normalization-deduplication`.
- **Commits:** `81edc66` feat(papers): add normalization and deduplication; merged as `53dda16`.
- **Status:** Complete and verified.

**Behavior added**

- Provider-neutral paper schema: `PaperCandidate` plus `SourceReference`, with no network or LLM
  involvement anywhere in this feature.
- Deterministic normalization of Unicode, whitespace, DOI, arXiv identifiers, dates, URLs, titles,
  and author names.
- Stable canonical-ID policy: DOI first (`doi_10_1234_abcd`), then arXiv (`arxiv_2401_12345`), then
  a 12-hex SHA-256 of the normalized title plus first author (`title_<hash>`). Filename-safe and
  stable across runs.
- Deduplication in the TRD order — exact DOI, exact arXiv ID, exact normalized title, then a
  RapidFuzz `token_sort_ratio` fuzzy pass requiring author overlap. Merged output is sorted by
  canonical id, so a shuffled input produces an identical result.

**Files and interfaces**

- `src/research_agent/domain/papers.py` (new): `SourceReference`, `PaperCandidate`, `SourceName`.
- `src/research_agent/discovery/normalize.py` (new): `normalize_text`, `normalize_title`,
  `normalize_doi`, `normalize_arxiv_id`, `normalize_author(s)`, `normalize_url`, `normalize_date`,
  `canonical_id`, `normalize_candidate`. All pure.
- `src/research_agent/discovery/deduplicate.py` (new): `deduplicate(candidates, settings)` and
  `merge(existing, incoming)`.
- `src/research_agent/config.py`: added `DeduplicationSettings` (`title_similarity` 95.0,
  `require_author_overlap` true) and `ApplicationSettings.deduplication`.
- `pyproject.toml`: added `rapidfuzz>=3.9,<4` (resolved to 3.14.6).

**Decisions**

- **New dependency: RapidFuzz.** TRD section 19 names it and it ships typed stubs. `difflib` was
  considered and rejected: it cannot match titles whose words are reordered, which is the common
  cross-source duplicate shape.
- **TRD deviation:** `PaperCandidate` carries `sources: list[SourceReference]` instead of the flat
  `source` / `source_id` pair in TRD section 16. The F3 deliverable requires merge rules that
  preserve *all* source identifiers, which a single pair cannot express. Everything else in the
  schema matches the TRD.
- Dedup threshold lives on `ApplicationSettings`, not `TopicSettings`: it is a global matching
  policy, and per-topic placement would have forced a schema migration and four more CLI flags for
  a value that does not vary by topic.
- Merge rules are deterministic: first non-null identifier, earliest publication date, longest
  abstract, longest author list, larger citation count, union of sources sorted by
  `(source, source_id)`.
- The fuzzy pass is an O(n^2) scan over accepted candidates. Acceptable at the 500-candidate limit;
  the code carries a comment naming the upgrade path (bucket titles by prefix or token).

**Verification**

- `uv run ruff check .` — All checks passed.
- `uv run ruff format .` — 27 files unchanged.
- `uv run mypy` — Success: no issues found in 27 source files.
- `uv run pytest` — 80 passed, coverage 96.69% (threshold 85%).
- `uv run research-agent config validate` — "Configuration valid: 1 topic(s), 1 enabled."

**Known issues / risks**

- Pre-existing `ResourceWarning: unclosed database` from the F2 SQLite tests still appears under
  `-W error`. Not introduced here; a future chore can close connections in the test helpers.
- `normalize_date` accepts partial date strings, but `PaperCandidate.publication_date` is typed
  `date | None`, so adapters must call `normalize_date` on raw provider strings before building a
  candidate. That is the intended F5 usage.
- Nothing persists papers yet; F4 adds the tables.

**Next recommended step:** Create `F4-metadata-artifact-persistence` and add the papers, paper
sources, runs, and errors tables plus the artifact storage boundary, reusing the migration
foundation in `src/research_agent/storage/database.py`.

## 2026-09-22 — F2 topic management (complete, merged)

- **Feature/branch:** `F2-topic-management` (merged into `main`).
- **Commits:** `52c62d2` feat(topics): add persistent topic management; merged as `95e578e`.
- **Status:** Complete and verified.

**Behavior added**

- Topics are now persisted in SQLite instead of living only in `config/topics.yaml`.
- New CLI group `research-agent topic` with `add`, `list`, `enable`, and `disable`.
- `topic add` exposes every topic field as a flag (id, name, lookback, active/shadow classifier,
  each discovery source toggle, all four limits, enabled state, schedule frequency/day).
- Opening the store runs migrations and, when the `topics` table is empty, auto-seeds from the
  topics YAML. Seeding is idempotent; a missing or invalid YAML leaves the store empty rather than
  failing, so `topic add` still works on a bare machine.

**Files and interfaces**

- `src/research_agent/storage/database.py` (new): `MIGRATIONS`, `connect()`, `apply_migrations()`.
  Schema version is tracked with `PRAGMA user_version`; migration 1 creates `topics`.
- `src/research_agent/storage/topics.py` (new): `TopicRepository` Protocol,
  `SqliteTopicRepository`, `bootstrap()`, and `TopicStoreError` / `DuplicateTopicError` /
  `TopicNotFoundError`.
- `src/research_agent/config.py`: added `SchedulingSettings` (frequency `weekly`, day `sunday`) and
  `TopicSettings.scheduling`, matching TRD section 9.
- `src/research_agent/cli.py`: `topic` sub-typer plus the private `_open_repository()` helper.
- Database path: `ApplicationSettings.data_directory / "research_agent.db"` (`data/` is gitignored).

**Decisions**

- stdlib `sqlite3` and hand-rolled migrations; no Alembic and no new dependency.
- `TopicSettings` remains the single validated topic model — the repository returns it directly, so
  the acceptance criterion "reconstructed as the existing validated topic model" holds without a
  parallel record type.
- Flat explicit columns rather than JSON blobs, so rows are queryable and readable in any client.
- `created_at`/`updated_at` are written but not yet read; no accessor was added (YAGNI).
- Auto-bootstrap was chosen over an explicit `topic import` command at the user's request.

**Verification**

- `uv run ruff format --check .` — 22 files already formatted.
- `uv run ruff check .` — All checks passed.
- `uv run mypy` — no issues in 22 source files.
- `uv run pytest` — 39 passed, total coverage 94.86% (threshold 85%).
- Manual: `topic list` seeded the committed topic, `topic add`/`disable` persisted, and a new
  process saw the same rows.

**Known issues / assumptions**

- `topic` commands import `_load_yaml_mapping` from `config.py`; if more modules need it, promote it
  to a public helper.
- There is no `topic remove` or `topic edit` yet; editing means YAML plus a fresh database, or a
  future feature.
- `UPDATES.md` is untracked, so this entry is local only and never appears in a commit.

**Next recommended step:** Create `F3-paper-normalization-deduplication` and implement the
`PaperCandidate` schema, normalization, and the required deduplication priority order.


## 2026-09-22 — Handoff log kept local

- **Status:** Completed, merged into `main`.
- **Task:** Stop distributing the handoff log and remove the README references to the local-only agent files.
- **Branch:** `CHORE2-untrack-handoff-log` (second chore allocation).
- **Summary:** Added `UPDATES.md` to `.gitignore` and untracked it with `git rm --cached`; the file stays on disk and remains the required append-at-top handoff log for local work. Removed the closing README paragraph that pointed at `AGENTS.md` and `UPDATES.md`, since neither is in the repository any more.
- **Decision:** Agent conventions and engineering handoff notes are working-copy context, not published artifacts. The README now describes only what a clone actually contains.
- **Files affected:** `.gitignore`, `README.md`, `UPDATES.md`; `UPDATES.md` removed from version control while remaining present locally.
- **Verification:** `git check-ignore -v` confirms the path is ignored and `git ls-files` lists no agent/handoff file; `README.md` contains no reference to either file. Ruff format/lint, strict mypy, and the 21-test suite pass unchanged. No source code was touched.
- **Git references:** Chore commit on `CHORE2-untrack-handoff-log`; merge commit on `main`. Both use `Debesh Biswas <mail2debesh@gmail.com>` with no agent attribution or commit trailers.
- **Known issues/risks:** The published repository no longer carries conventions or engineering history, so a fresh clone has neither; both files exist only in this working copy and in Git history up to commit `025ce91`. Losing the working copy loses all later handoff entries. Switching branches across the untracking commit deletes the working file — back it up first and restore afterwards.
- **Next recommended step:** Unchanged — create `F2-topic-management` and implement persistent topic add/list/enable/disable behind a repository interface.

## 2026-09-22 — Agent instruction files kept local

- **Status:** Completed, merged into `main`.
- **Task:** Treat `AGENTS.md` as local-only agent instructions and expose the same content as `CLAUDE.md`.
- **Branch:** `CHORE1-ignore-agent-instructions` (first chore allocation).
- **Summary:** Added `CLAUDE.md` as a symlink to `AGENTS.md` so Claude Code loads the existing conventions without a second copy to keep in sync. Added both filenames to `.gitignore` and untracked `AGENTS.md` with `git rm --cached`; the file remains on disk and remains authoritative for local work.
- **Decision:** One file, two names, via symlink rather than duplicated content — duplicated instruction files drift. Conventions are now a working-copy concern, not a distributed artifact.
- **Files affected:** `.gitignore`, `README.md`, `UPDATES.md`; `AGENTS.md` removed from version control (still present locally); `CLAUDE.md` created locally and ignored.
- **Verification:** `git check-ignore -v` confirms both paths are ignored; `git ls-files` no longer lists `AGENTS.md`; the file and symlink both resolve on disk. Ruff format/lint, strict mypy, and the 21-test suite pass unchanged. No source code was touched.
- **Known issues/risks:** `AGENTS.md` no longer reaches anyone cloning from GitHub, so a fresh clone has no conventions file; historical `UPDATES.md` entries still reference it as a repository file and were deliberately left unedited as a log. The `README.md` reference was reworded to state the file is local and untracked.
- **Next recommended step:** Unchanged — create `F2-topic-management` and implement persistent topic add/list/enable/disable behind a repository interface.

## 2026-09-22 — Complete v1 feature roadmap

- **Status:** Completed, merged into `main`, and re-verified on the merged tree.
- **Task:** Translate the full PRD/TRD into a sequential, branch-ready implementation roadmap covering every planned v1 product feature.
- **Branch:** `DOC2-feature-roadmap` (second numbered documentation task).
- **Summary:** Added `docs/FEATURE_ROADMAP.md` with a dependency-ordered F1–F20 plan. Each feature records its branch, prerequisites, goal, bounded deliverables, public/CLI surface where applicable, tests, acceptance gate, exclusions, and exact feature/merge commit-message convention. F1 is marked complete with its Git references; F2 remains the next product branch. The README now links directly to the roadmap.
- **Roadmap decisions:** The sequence establishes topic/domain/persistence foundations before network and model integrations; completes discovery, provider, query, classifier, and selection layers before document processing; builds analysis, synthesis, ideation, and reporting before LangGraph integration; then adds local operations, MVP hardening, and AWS portability validation. The roadmap reserves F2–F20 names but does not begin those features. AWS work proves replaceable contracts and documents deployment rather than creating paid infrastructure.
- **Important gates:** F8 cannot start until the actual pre-existing Classifier A implementation is located or supplied; F9 must confirm the intended Qwen model/runtime; F6 and F12 must select currently compatible local-model and Docling stacks when those branches begin. The roadmap explicitly forbids silently inventing replacement classifiers or committing model weights/secrets.
- **Files affected:** `docs/FEATURE_ROADMAP.md`, `README.md`, and `UPDATES.md`.
- **Verification:** Reviewed the PRD and TRD in full; mapped all in-scope requirements, CLI commands, database entities, workflow nodes, failure routes, testing obligations, local scheduling, and AWS compatibility constraints to at least one feature; confirmed F1–F20 numbering is unique and ordered. Before and after merge, Ruff formatting/linting, strict mypy, the 21-test suite with 89.77% coverage, and Markdown whitespace checks all passed.
- **Git references:** Documentation commit `dc8ae78`; merge commit `1df9db1`. Both use `Debesh Biswas <mail2debesh@gmail.com>` with no agent attribution or commit trailers.
- **Known issues/risks:** Future library/model selections may change as compatibility evolves; the roadmap therefore fixes required behavior and boundaries while deferring time-sensitive implementation choices to the named planning gates. Classifier A/B artifacts remain absent from the repository.
- **Next recommended step:** Publish the merged DOC2 state, then create `F2-topic-management`; do not begin F3 or any later branch until F2 is complete and merged.

## 2026-09-22 — F1 Python project scaffold

- **Status:** Completed, committed on the feature branch, merged into `main`, and re-verified on the merged tree.
- **Feature:** Establish the runnable, local-first Python project foundation required before product features.
- **Branch:** `F1-project-scaffold` (first allocation in the product-feature sequence).
- **Summary:** Added a Python 3.11+ `src` package managed by `uv`, the `research-agent` Typer CLI, typed YAML/environment configuration, strict topic validation, standard-library JSON logging, importable architecture boundaries, safe local defaults, repository hygiene rules, developer documentation, and an offline unit/integration test foundation. The CLI currently supports `--help`, `--version`, and `config validate`; remaining TRD commands are intentionally deferred until they have real behavior.
- **Important interfaces and files:** `research_agent.config.load_configuration()` resolves application settings and topic definitions into Pydantic models; process `RESEARCH_AGENT_*` variables override `.env`, which overrides `config/settings.yaml`, which overrides model defaults. `research_agent.observability.configure_logging()` emits UTC JSON records with optional workflow context. `pyproject.toml` defines the console script, Ruff, strict mypy, pytest, and coverage configuration; `uv.lock` captures the resolved environment. `.env.example` contains only non-secret examples, while `.gitignore` excludes credentials, runtime data, databases, PDFs, reports, logs, model artifacts, environments, caches, builds, and coverage output.
- **Configuration defaults:** Local artifact storage, SQLite metadata, launchd scheduling, local strong-model provider, 10-day topic lookback, active Classifier A with shadow B in the example topic, candidate/classification/download/deep-read limits of 500/250/50/15, discovery/download/analysis concurrency of 3/4/2, and TRD retry ceilings of 3/2/1/2. Validation rejects unknown keys, invalid classifiers, equal active/shadow classifiers, duplicate or malformed topic IDs, disabled discovery, and inconsistent or non-positive limits.
- **Dependency decision:** Added only dependencies used by F1: Typer, Pydantic, Pydantic Settings, and PyYAML at runtime; Ruff, mypy, pytest, pytest-cov, and PyYAML type stubs for development. LangGraph, HTTP clients, database layers, PDF tooling, and model runtimes remain deferred until the features that use them, preventing unused or premature infrastructure.
- **Verification:** On Apple Silicon with CPython 3.14.6 and uv 0.11.26, `uv lock` and `uv sync --all-groups` succeeded; `uv run ruff format --check .` and `uv run ruff check .` passed; strict `uv run mypy` passed across 18 source/test files; `uv run pytest` passed 21 tests with 89.77% branch-aware coverage against an 85% threshold; CLI version and committed-config validation passed; `python -m research_agent --version` passed; `uv build` produced both sdist and wheel; `git diff --check` passed. Formatting, linting, typing, tests, configuration validation, and whitespace checks were repeated successfully on `main` after the merge. Tests are offline and require no credentials, APIs, paid services, Docker, or model downloads.
- **Decisions and assumptions:** The distribution and command are `research-agent`, while imports use `research_agent`. `config/settings.yaml` is the local v1 profile; AWS configuration and Docker are out of scope. The authoritative `docs/` specifications are excluded from Ruff formatting so code snippets are not mechanically rewritten. Architectural subpackages are intentionally empty boundaries rather than misleading placeholder implementations.
- **Git references:** Feature commit `5bcd38a`; merge commit `46af966`. Both were authored/committed as `Debesh Biswas <mail2debesh@gmail.com>` with no agent attribution or commit trailers.
- **Known issues/risks:** Verification used Python 3.14.6 rather than the minimum Python 3.11; package metadata supports 3.11+, but a multi-version CI matrix is not part of F1. The PRD/TRD describe pre-existing Classifier A/B implementations, but their concrete code or model assets are still not present in this repository.
- **Next recommended step:** After publishing this merged state, allocate `F2-topic-management` to implement persistent topic add/list behavior behind a repository interface without beginning workflow orchestration.

## 2026-09-22 — Specifications organized under `docs/`

- **Status:** Completed, merged into `main`, and published to GitHub.
- **Task:** Move the project specifications into a documentation directory while preserving root-level agent discovery and handoff files.
- **Branch:** `DOC1-organize-specifications` (renamed from the pre-convention working name `docs/organize-specifications`).
- **Summary:** Moved the PRD and TRD from the repository root into `docs/` and updated all live convention/handoff references to their new paths. Kept `AGENTS.md` and `UPDATES.md` at the root because coding agents discover repository instructions there and the handoff log should remain immediately visible. Added numbered branch naming (`F1-...`, `DOC1-...`, and other task prefixes), Conventional Commit/merge-message rules, and a strict prohibition on agent/AI authorship or co-authorship metadata.
- **Files affected:** `docs/research_agent_PRD.md`, `docs/research_agent_TRD.md`, `AGENTS.md`, and `UPDATES.md`.
- **Decision:** Use `docs/` rather than `documentation/` for a concise, conventional path. Preserve file contents and Git history through tracked renames. Reserve the `F<number>-...` sequence for product features; use independently numbered task prefixes for non-feature work. Existing history remains unchanged, and all future Git metadata uses only the configured human identity.
- **Verification:** Confirmed both moved files are non-empty; searched tracked Markdown for stale root-path references; ran `git diff --check`. No application test suite exists yet.
- **Git/GitHub:** Documentation commit `fdcc402`; merge commit `8537fb7`. Configured `origin` as `https://github.com/debesh-biswas/Research-Agent.git`, created remote `main`, and set local `main` to track `origin/main`. HTTPS authentication succeeded for the repository owned by `debesh-biswas` using the machine's configured Git credentials. All commits use `Debesh Biswas <mail2debesh@gmail.com>` with no agent co-author metadata.
- **Known issues:** GitHub CLI is unavailable locally; Git transport and the configured credential helper are used for remote operations instead. No application code or test suite exists yet.
- **Next recommended step:** Start project scaffolding as the first product feature on `F1-project-scaffold`; complete, verify, commit, and merge it before allocating `F2`.

## 2026-09-22 — Repository conventions established

- **Status:** Completed pre-implementation setup.
- **Task:** Review the product and technical specifications and establish coding-agent conventions before project scaffolding.
- **Branch:** `docs/repository-conventions` (repository initialization uses a separate baseline specification commit; no product feature implemented).
- **Summary:** Added `AGENTS.md` with project-specific product guardrails, architecture boundaries, classifier/model behavior, persistence and security rules, reliability and observability requirements, coding conventions, test expectations, a mandatory per-feature Git workflow, and detailed handoff-log requirements.
- **Specifications reviewed:** `docs/research_agent_PRD.md` v1.0 and `docs/research_agent_TRD.md` v1.0 in full (paths updated after the documentation reorganization).
- **Key decisions captured:** Python 3.11+ and local-first operation; LangGraph limited to orchestration; deterministic mechanics separated from semantic LLM work; provider-neutral interfaces for discovery, classifiers, models, storage, repositories, and scheduling; Classifier A/B schema parity with active/shadow isolation; optional NIM with local fallback; SQLite plus local artifact storage; evidence provenance; bounded retries/concurrency; structured logs; AWS-compatible boundaries without premature AWS implementation.
- **Files added:** `AGENTS.md`, `UPDATES.md`.
- **Verification:** Confirmed both specification files are present and reviewed their complete contents; inspected the rendered source structure and required sections in both new Markdown files. No application test suite exists yet.
- **Git references:** Baseline specifications commit `b91b55f`; conventions commit `d8a903c`; merged into `main` as `7bb5677`.
- **Known state:** No application scaffold or runtime code exists yet. Classifier A and Classifier B are described as pre-existing in the specifications, but their concrete implementations/assets have not yet been located or supplied. No feature branch has started.
- **Next recommended step:** Initialize the Python project on `F1-project-scaffold`, add the baseline package/config/test structure and secret-safe `.gitignore`, run its verification, update this log, commit, merge into `main`, and only then allocate `F2`.

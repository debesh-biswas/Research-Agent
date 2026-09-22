# Project Updates

This is the append-at-top handoff log for the Personal Weekly AI Research Intelligence Agent. Follow the required entry format and workflow in `AGENTS.md`. Never record secrets.

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

# Project Updates

This is the append-at-top handoff log for the Personal Weekly AI Research Intelligence Agent. Follow the required entry format and workflow in `AGENTS.md`. Never record secrets.

## 2026-09-22 — Specifications organized under `docs/`

- **Status:** Completed and ready to merge.
- **Task:** Move the project specifications into a documentation directory while preserving root-level agent discovery and handoff files.
- **Branch:** `DOC1-organize-specifications` (renamed from the pre-convention working name `docs/organize-specifications`).
- **Summary:** Moved the PRD and TRD from the repository root into `docs/` and updated all live convention/handoff references to their new paths. Kept `AGENTS.md` and `UPDATES.md` at the root because coding agents discover repository instructions there and the handoff log should remain immediately visible. Added numbered branch naming (`F1-...`, `DOC1-...`, and other task prefixes), Conventional Commit/merge-message rules, and a strict prohibition on agent/AI authorship or co-authorship metadata.
- **Files affected:** `docs/research_agent_PRD.md`, `docs/research_agent_TRD.md`, `AGENTS.md`, and `UPDATES.md`.
- **Decision:** Use `docs/` rather than `documentation/` for a concise, conventional path. Preserve file contents and Git history through tracked renames. Reserve the `F<number>-...` sequence for product features; use independently numbered task prefixes for non-feature work. Existing history remains unchanged, and all future Git metadata uses only the configured human identity.
- **Verification:** Confirmed both moved files are non-empty; searched tracked Markdown for stale root-path references; ran `git diff --check`. No application test suite exists yet.
- **Git/GitHub:** The local target remote is `https://github.com/debesh-biswas/Research-Agent.git`. Commit, merge, remote verification, and push references will be recorded after completion.
- **Known issues:** GitHub CLI is unavailable locally, so remote authentication/account resolution relies on the configured Git transport/credential helper during push.
- **Next recommended step:** After this documentation branch is merged and pushed, start project scaffolding on `chore/project-scaffold`; do not begin another feature on this branch.

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
- **Next recommended step:** Initialize the Python project on a dedicated `chore/project-scaffold` branch (or define the first bounded feature), add the baseline package/config/test structure and secret-safe `.gitignore`, run its verification, update this log, commit, merge into `main`, and only then begin the next feature branch.

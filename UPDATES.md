# Project Updates

This is the append-at-top handoff log for the Personal Weekly AI Research Intelligence Agent. Follow the required entry format and workflow in `AGENTS.md`. Never record secrets.

## 2026-09-22 — Repository conventions established

- **Status:** Completed pre-implementation setup.
- **Task:** Review the product and technical specifications and establish coding-agent conventions before project scaffolding.
- **Branch:** `docs/repository-conventions` (repository initialization uses a separate baseline specification commit; no product feature implemented).
- **Summary:** Added `AGENTS.md` with project-specific product guardrails, architecture boundaries, classifier/model behavior, persistence and security rules, reliability and observability requirements, coding conventions, test expectations, a mandatory per-feature Git workflow, and detailed handoff-log requirements.
- **Specifications reviewed:** `research_agent_PRD.md` v1.0 and `research_agent_TRD.md` v1.0 in full.
- **Key decisions captured:** Python 3.11+ and local-first operation; LangGraph limited to orchestration; deterministic mechanics separated from semantic LLM work; provider-neutral interfaces for discovery, classifiers, models, storage, repositories, and scheduling; Classifier A/B schema parity with active/shadow isolation; optional NIM with local fallback; SQLite plus local artifact storage; evidence provenance; bounded retries/concurrency; structured logs; AWS-compatible boundaries without premature AWS implementation.
- **Files added:** `AGENTS.md`, `UPDATES.md`.
- **Verification:** Confirmed both specification files are present and reviewed their complete contents; inspected the rendered source structure and required sections in both new Markdown files. No application test suite exists yet.
- **Git references:** Baseline specifications commit `b91b55f`; conventions commit `d8a903c`; merged into `main` as `7bb5677`.
- **Known state:** No application scaffold or runtime code exists yet. Classifier A and Classifier B are described as pre-existing in the specifications, but their concrete implementations/assets have not yet been located or supplied. No feature branch has started.
- **Next recommended step:** Initialize the Python project on a dedicated `chore/project-scaffold` branch (or define the first bounded feature), add the baseline package/config/test structure and secret-safe `.gitignore`, run its verification, update this log, commit, merge into `main`, and only then begin the next feature branch.

# AGENTS.md

## Purpose

This repository implements the Personal Weekly AI Research Intelligence Agent described in `research_agent_PRD.md` and `research_agent_TRD.md`. Treat both documents as authoritative product and technical specifications. This file summarizes the rules agents must apply while working; if it conflicts with an explicit requirement in the PRD or TRD, follow the PRD/TRD and record the discrepancy in `UPDATES.md`.

The v1 product is a single-user, local-first Python application that discovers recent research, triages papers with one of two interchangeable classifiers, acquires and parses legal open-access PDFs, performs evidence-backed analysis and cross-paper synthesis, creates research ideas, writes weekly Markdown reports, and preserves historical context. It must run on a 24 GB Apple Silicon MacBook at zero or near-zero recurring cost and remain portable to an AWS deployment without rewriting the core workflow.

## Read Before Working

Before planning or changing code:

1. Read this file completely.
2. Read the relevant sections of `research_agent_PRD.md` and `research_agent_TRD.md`; read both documents completely when changing architecture, workflow, persistence, schemas, model routing, or scope.
3. Read `UPDATES.md` from newest to oldest until the current state, recent decisions, open issues, and next steps are clear.
4. Inspect `git status`, the current branch, recent commits, and existing tests. Never discard unrelated or user-authored changes.

## Product Guardrails

- Keep v1 single-user, local-first, free/open-source/student-plan friendly, and operable without paid infrastructure.
- Do not add custom classifier training or fine-tuning, a custom foundation model, unauthorized paywall bypassing, large-scale crawling, multi-tenant SaaS features, Kubernetes/EKS, or paid GPU infrastructure.
- Search OpenAlex, Semantic Scholar, and arXiv through source adapters. A failure in one source or one paper must not abort the whole run.
- Default to a 10-day lookback for weekly runs and deduplicate against previously seen papers.
- Respect configurable resource limits. Specification examples are 500 candidates, 250 classifications, 50 downloads, and 15 deep reads.
- Download only legally accessible PDFs. If a PDF is unavailable, retain metadata and abstract; if parsing fails, support abstract-only analysis and mark the degradation.
- Every important finding, gap, contradiction, and research idea must link back to supporting paper identifiers or metadata. Page/section evidence is best-effort where parser output permits it.
- Preserve historical topic context so reports identify changes rather than treating each week as a fresh corpus. The suggested comparison window is the previous four syntheses.
- Produce a useful degraded report when optional providers or individual stages fail whenever safely possible.

## Required Architecture

- Use Python 3.11+ and `uv` for dependency management unless a documented constraint requires otherwise. Docker must not be required for local development.
- Use LangGraph only for workflow orchestration: state propagation, conditional routing, retry-aware branching, failure handling, and optional checkpoints.
- Keep academic APIs, classifiers, model providers, metadata persistence, artifact storage, and scheduling behind interfaces. LangGraph nodes must depend on those interfaces and must not contain provider-specific API code.
- Keep graph state structured and validated with Pydantic. Store paths or object references in state; never place PDF bytes or other large payloads in graph state.
- Use async I/O and bounded, configurable concurrency for network and independent paper operations. Honor provider-specific pacing, HTTP 429 responses, and `Retry-After`.
- Use deterministic code for retrieval mechanics, normalization, identifier matching, deduplication, date filtering, downloading, persistence, filenames, scheduling, and schema validation. Use LLMs for semantic query expansion, analysis, comparison, synthesis, gap detection, ideation, and report prose.
- Do not encode local filesystem assumptions in graph nodes. Use storage and repository abstractions so local filesystem/SQLite implementations can later map to S3/DynamoDB.
- Scheduling is external to LangGraph. Local scheduling may use `launchd` or cron; the future AWS equivalent is EventBridge Scheduler.

The intended flow is:

```text
load topic -> generate queries -> discover -> normalize -> deduplicate
-> classify -> select -> acquire PDFs -> parse -> analyze -> synthesize
-> detect gaps -> generate ideas -> report -> persist
```

Required branches in that flow include an empty-week report, at most one automatic query-broadening pass, metadata/abstract fallback for unavailable or unparseable PDFs, and local-model fallback after NIM retries.

## Classifier and Model Rules

- Support exactly the two v1 classifier paths: Classifier A (the pre-existing lightweight/Jev-style classifier) and Classifier B (the pre-existing Qwen-style small LLM classifier).
- Both classifiers implement one `PaperClassifier` interface and return the same validated `ClassificationResult` schema. LangGraph obtains implementations through a factory; switching A/B must require configuration only.
- In shadow mode, the active classifier alone controls routing. The shadow result is persisted with `is_active=false`; shadow failure never fails the primary run.
- Classifier B should use a configurable local Apple-Silicon-friendly runtime/model, require structured output, validate it with Pydantic, and allow one repair retry for malformed output.
- Keep model providers behind a capability-based router. Prefer local inference for cheap text, classification, extraction, and fallback work. Use optional NVIDIA NIM for deep analysis, synthesis, ideation, and report writing when available.
- Retry NIM at most twice before local fallback. Never make NIM availability a requirement for a successful local run.
- Never hardcode model names, provider URLs, API keys, or implementation-specific classifier output into workflow logic.

## Data, Persistence, and Security

- Normalize Unicode, whitespace, dates, URLs, DOI values, arXiv identifiers, and author names where feasible. Store DOI values without the `https://doi.org/` prefix.
- Deduplicate in this order: exact DOI, exact arXiv ID, exact normalized title, then configurable fuzzy title similarity (default 95+) with author overlap.
- Cache search results within a run and reuse stored metadata, parsed PDFs, and completed analyses for unchanged papers.
- SQLite is the v1 structured metadata store. The minimum domain coverage is topics, runs, papers, paper sources, classifications, files, analyses, syntheses, gaps, ideas, and errors.
- The local filesystem stores PDFs, parsed Markdown/text, JSON analysis artifacts, reports, per-run summaries, and structured logs beneath topic-specific paths.
- Persist raw provider/classifier responses only when useful for audit/debugging and handle them as potentially sensitive or untrusted data.
- Secrets belong in environment variables loaded from an uncommitted `.env`. Commit only a redacted `.env.example`. Ignore `.env`, runtime `data/`, database files, credentials, caches, model weights, and generated artifacts unless a sanitized fixture is deliberately approved.
- Never log secrets. Validate downloaded content type and size, use deterministic safe filenames, and treat all external text/PDF content as untrusted input.

## Reliability and Observability

- Prefer partial progress over run-wide failure. Categorize errors using the TRD taxonomy and record whether each is recoverable.
- Default retry ceilings: academic APIs 3 with exponential backoff; NIM 2 then local fallback; Classifier B repair 1; PDF download 2. Do not retry deterministic validation failures indefinitely.
- Emit structured JSON logs. Include timestamp, run/topic/node identifiers and, where relevant, paper, provider, model, classifier, duration, status, and error type.
- Persist run summaries with counts for discovery, deduplication, classification, selection, downloads, parse failures, and deep reads, plus models used, errors, active/shadow classifier, timing, and final status.
- Make runs reproducible by recording the reporting period, resolved topic configuration, enabled sources, classifier selection, and model/provider choices.

## Coding Conventions

- Use explicit type annotations and Pydantic models at system boundaries. Prefer small cohesive modules and dependency injection over global singletons.
- Keep domain models provider-neutral. Translate external payloads inside adapters and do not leak source-specific fields into orchestration logic.
- Prefer pure functions for normalization, selection, deduplication, filenames, and routing predicates.
- Keep network, filesystem, database, model, and clock dependencies injectable so tests remain deterministic.
- Use UTC-aware datetimes internally; convert only at user/report boundaries. Use stable IDs and deterministic ordering wherever output could otherwise vary.
- Validate configuration at startup and fail early with actionable messages for invalid required settings. Optional integrations must fail gracefully.
- Use structured logging rather than `print` in application code. Include context without logging full paper bodies or secrets.
- Keep prompts versioned or centralized, require structured model outputs where schemas exist, and validate all model-produced data before persistence or routing.
- Add docstrings when behavior, invariants, fallback rules, or a public interface are not obvious. Comments should explain why, not restate code.
- Avoid premature AWS-specific code. Preserve replaceable boundaries, but implement and test the local path first.
- Do not add dependencies without a concrete need. Prefer standard-library or already-approved packages and record material dependency decisions in `UPDATES.md`.

## Testing and Verification

- Every behavior change requires tests at the lowest useful layer. Bug fixes require a regression test whenever practical.
- Unit coverage is required for DOI/arXiv normalization, deduplication, classifier factory/output validation, storage repositories, and report filenames.
- Integration coverage is required for each discovery adapter, active classifier A/B switching, shadow mode, and a fully mocked end-to-end local run.
- Use static fixtures for routine tests; the default test suite must not depend on live APIs, paid services, local model downloads, or secrets.
- Explicitly test failure isolation, retry ceilings, fallbacks, caching/idempotency, empty-result routing, and the one-pass query broadening limit.
- Before committing, run formatting, linting/type checks, and the narrowest relevant tests. Before merging a feature branch, run the full locally supported verification suite and record results in `UPDATES.md`.
- Do not weaken assertions or skip tests merely to make a build pass. Document unavailable verification and its reason.

## Git and Feature Workflow

All implementation work is feature-isolated. Complete the full sequence below before starting another feature:

1. Start from a clean, up-to-date `main` branch.
2. Define one bounded feature and its acceptance criteria from the PRD/TRD.
3. Create a dedicated branch named `feat/<short-kebab-name>`. Use `fix/`, `docs/`, `test/`, `chore/`, or `refactor/` for work that is not a product feature.
4. Implement only that bounded change, including tests and relevant documentation.
5. Verify the change and update `UPDATES.md` on the same branch.
6. Commit all feature-owned changes with a clear imperative/Conventional Commit message such as `feat: add OpenAlex discovery adapter`.
7. Merge the completed branch into `main` before creating or starting the next feature branch. Do not stack feature branches or leave completed work unmerged.
8. Verify the merge on `main` and ensure `UPDATES.md` accurately records the merged commit and repository state. If the final commit hash was not known on the branch, a small post-merge docs commit on `main` may fill it in.

Do not commit directly to `main` for product features. Never rewrite shared history, force-push, or discard unrelated work. Keep commits focused; do not mix opportunistic refactors with a feature. If unfinished work must be handed off, leave it on its branch and clearly document the exact state in `UPDATES.md` rather than merging incomplete behavior.

## `UPDATES.md` Handoff Log

`UPDATES.md` is a required, append-at-top engineering handoff log and must stay current. Update it as work progresses and always before a feature commit/merge. Each entry must include:

- date/time and status;
- feature/task and branch;
- concise summary of behavior added or changed;
- important files, schemas, interfaces, migrations, and configuration affected;
- decisions made and why;
- verification commands and results;
- commit and merge references when available;
- known issues, risks, assumptions, or unavailable validation;
- precise next recommended step so another agent can resume without rediscovery.

Do not use `UPDATES.md` as a raw transcript. Keep enough concrete detail to reconstruct the current implementation and outstanding work. Never include secrets, tokens, private endpoints, or full sensitive payloads.

## Definition of Done for a Feature

A feature is done only when its PRD/TRD acceptance criteria are met, interfaces and schemas remain consistent, tests and documentation are updated, relevant verification passes, failures remain observable and isolated, `UPDATES.md` contains a useful handoff entry, the feature is committed on its dedicated branch, and that branch is merged into `main`.


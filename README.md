# Research Agent

Research Agent is a local-first Python application for producing evidence-backed weekly AI
research intelligence. The product and technical specifications are maintained in
[`docs/research_agent_PRD.md`](docs/research_agent_PRD.md) and
[`docs/research_agent_TRD.md`](docs/research_agent_TRD.md).

The sequential implementation plan, branch names, acceptance gates, and dependencies are tracked
in [`docs/FEATURE_ROADMAP.md`](docs/FEATURE_ROADMAP.md).

The current v1 implementation includes discovery adapters and one semantic paper-screening service,
quality-aware paper ranking, LangGraph orchestration, SQLite/filesystem persistence, legal PDF
acquisition and parsing, evidence-backed analysis, synthesis, ideation, Markdown reports, local
scheduling, structured logs, and AWS portability seams.

## Requirements

- Python 3.12 or newer
- [`uv`](https://docs.astral.sh/uv/)
- No Docker, paid service, API key, or local model is required for development

## Setup

```bash
uv sync --all-groups
cp .env.example .env
uv run research-agent --help
uv run research-agent config validate
```

The committed YAML files provide safe local defaults. Application settings are resolved in this
order, from highest to lowest precedence:

1. `RESEARCH_AGENT_*` process environment variables
2. values in an uncommitted `.env`
3. `config/settings.yaml`
4. model defaults

Commands read `config/settings.yaml` and `config/topics.yaml` from the current folder unless
`--settings` and `--topics` say otherwise, and a relative `data_directory` is relative to it too.
To use the command outside a checkout, install it with `uv tool install .` and run it from a
folder that holds your `config/`; the desk's page ships inside the package.

Nested environment fields use a double underscore, such as
`RESEARCH_AGENT_CONCURRENCY__DISCOVERY=2`. `config/topics.yaml` seeds a new library once, on
the first command; after that, topics live in the library and change through the `topic`
commands or the desk.

## Commands

```bash
uv run research-agent --version
uv run research-agent config validate
uv run research-agent config validate \
  --settings config/settings.yaml \
  --topics config/topics.yaml
```

Everyday commands:

```bash
uv run research-agent topic new --id quantum_error_correction --name "Quantum Error Correction"
uv run research-agent topic list
uv run research-agent topic edit <topic_id> --lookback-days 7 --keyword "surface codes"
uv run research-agent topic delete <topic_id>    # asks first; deletes its runs too
uv run research-agent run <topic_id>         # one topic's full weekly run
uv run research-agent run-all                # every enabled topic
uv run research-agent report latest <topic_id>
uv run research-agent model check
uv run research-agent doctor                 # check folder, models and sources, with fixes
uv run research-agent backup                 # the whole library to one .zip
uv run research-agent restore <backup.zip>   # asks for --yes; moves the current library aside
```

Use `backup` rather than copying the data folder by hand: the database runs in SQLite's WAL
mode, so recent writes can sit in `research_agent.db-wal` until the last connection closes.

Each pipeline stage also has its own command (`discover`, `classify`, `acquire`, `parse`,
`analyze`, `synthesize`, `ideate`, `report generate`); `uv run research-agent --help` lists them.

## Reading desk

`research-agent desk` serves the reading desk on this machine. It reads topics, runs, papers,
and the weekly report from the local library. Ask sends the question to NVIDIA NIM when that
provider is configured, and to the local model otherwise. The answer is limited to the cards
on the shelf. Each run and each paper keeps its own conversation in the library, so a follow-up
question sees the last few turns; "Start over" deletes it. A question about the week also sees
short summaries of up to four earlier runs of the topic, so it can say what changed.

```bash
uv run research-agent desk
```

Open `http://127.0.0.1:8765`. The page needs the desk server; opened as a file it only says so.
The Topics page edits, pauses, deletes and runs topics; New topic creates one. Setup check (in the
footer, and the first page of a new library) runs the same checks as `research-agent doctor`.

## Quality checks

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
```

All default tests are offline and must not require credentials, live APIs, paid providers, local
model downloads, or generated runtime data.

## Architecture boundaries

Runtime code uses the `src/research_agent` package. The initial package boundaries reserve clear
homes for domain models, workflow orchestration, discovery adapters, screening, model
providers, documents, storage, observability, and deterministic utilities. Provider-specific
logic must remain behind interfaces, and LangGraph will be used only for orchestration.

## Licences

The project is MIT-licensed (`LICENSE`). Its direct dependencies are MIT (Docling, LangGraph,
Pydantic, pydantic-settings, PyYAML, RapidFuzz, Typer) or BSD-3-Clause (HTTPX). Nothing in the
installed tree is GPL-family; certifi, orjson, pathspec and tqdm are MPL-2.0, used unmodified.
The desk's fonts (IBM Plex Mono, Literata, Schibsted Grotesk) are under the SIL Open Font License
1.1, with each licence beside the font files in `web/fonts/`. Docling downloads its layout and
table models on first use; those carry their own licences from their publishers.

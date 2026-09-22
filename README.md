# Research Agent

Research Agent is a local-first Python application for producing evidence-backed weekly AI
research intelligence. The product and technical specifications are maintained in
[`docs/research_agent_PRD.md`](docs/research_agent_PRD.md) and
[`docs/research_agent_TRD.md`](docs/research_agent_TRD.md).

The sequential implementation plan, branch names, acceptance gates, and dependencies are tracked
in [`docs/FEATURE_ROADMAP.md`](docs/FEATURE_ROADMAP.md).

This repository currently contains the project foundation: validated configuration, a CLI,
structured JSON logging, package boundaries, and an offline test suite. Discovery providers,
classifiers, LangGraph orchestration, persistence, document processing, and report generation
will be added as separately reviewed features.

## Requirements

- Python 3.11 or newer
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

Nested environment fields use a double underscore, such as
`RESEARCH_AGENT_CONCURRENCY__DISCOVERY=2`. Topic definitions are loaded from
`config/topics.yaml` and validated independently.

## Commands

```bash
uv run research-agent --version
uv run research-agent config validate
uv run research-agent config validate \
  --settings config/settings.yaml \
  --topics config/topics.yaml
```

The broader CLI described by the TRD will be exposed feature by feature, when each command has a
real implementation.

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
homes for domain models, workflow orchestration, discovery adapters, classifiers, model
providers, documents, storage, observability, and deterministic utilities. Provider-specific
logic must remain behind interfaces, and LangGraph will be used only for orchestration.

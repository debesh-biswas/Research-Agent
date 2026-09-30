"""Command-line interface for Research Agent."""

import asyncio
import sqlite3
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Annotated, cast

import httpx
import typer
from pydantic import ValidationError

from research_agent import __version__
from research_agent.analysis.analyzer import AnalysisOutcome, PaperAnalyzer
from research_agent.config import (
    ApplicationSettings,
    ConfigurationError,
    TopicSettings,
    _load_yaml_mapping,
    load_configuration,
)
from research_agent.discovery.aggregator import (
    DiscoveryAggregator,
    DiscoveryResult,
    build_sources,
)
from research_agent.documents.docling_parser import DoclingParser
from research_agent.documents.downloader import DownloadOutcome, PdfDownloader
from research_agent.documents.parser import ParsingService, load_parsed
from research_agent.domain.analysis import ClassificationResult, PaperAnalysis, WeeklySynthesis
from research_agent.domain.documents import ParsedPaper
from research_agent.domain.papers import PaperCandidate
from research_agent.domain.queries import QueryPlan
from research_agent.domain.runs import ErrorRecord, RunRecord, RunSummary
from research_agent.domain.selection import SelectionPlan
from research_agent.ideation.cards import render_ideation
from research_agent.ideation.generator import IdeationOutcome, IdeationService
from research_agent.models.base import (
    Capability,
    ModelMessage,
    ModelProviderError,
    ModelResult,
)
from research_agent.models.router import build_router
from research_agent.observability.logging import configure_logging
from research_agent.operations.runner import RunOutcome, execute_run
from research_agent.operations.scheduling import SchedulerBackend, render_schedule
from research_agent.queries.planner import QueryPlanner, base_query
from research_agent.reports.service import ReportOutcome, ReportService
from research_agent.screening.service import PaperScreener, ScreeningFailure
from research_agent.selection.selector import select
from research_agent.storage.artifacts import LocalArtifactStore
from research_agent.storage.database import apply_migrations, connect
from research_agent.storage.papers import SqlitePaperRepository
from research_agent.storage.queries import SqliteQueryPlanRepository
from research_agent.storage.results import SqliteResultRepository
from research_agent.storage.runs import SqliteRunRepository
from research_agent.storage.selections import SqliteSelectionRepository
from research_agent.storage.topics import (
    SqliteTopicRepository,
    TopicStoreError,
    bootstrap,
)
from research_agent.synthesis.synthesizer import SynthesisOutcome, WeeklySynthesizer

app = typer.Typer(
    name="research-agent",
    help="Build evidence-backed weekly AI research intelligence.",
    no_args_is_help=True,
)
config_app = typer.Typer(help="Inspect and validate application configuration.")
app.add_typer(config_app, name="config")
topic_app = typer.Typer(help="Create and manage persistent topics.")
app.add_typer(topic_app, name="topic")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"research-agent {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the installed version and exit.",
        ),
    ] = None,
) -> None:
    """Build evidence-backed weekly AI research intelligence."""


@config_app.command("validate")
def validate_config(
    settings: Annotated[
        Path,
        typer.Option(help="Path to application settings YAML."),
    ] = Path("config/settings.yaml"),
    topics: Annotated[
        Path,
        typer.Option(help="Path to topic definitions YAML."),
    ] = Path("config/topics.yaml"),
) -> None:
    """Validate settings and topic configuration without starting a run."""
    try:
        configuration = load_configuration(settings_path=settings, topics_path=topics)
    except (ConfigurationError, ValidationError) as error:
        typer.echo(f"Configuration invalid: {error}", err=True)
        raise typer.Exit(code=1) from error

    enabled_count = sum(topic.enabled for topic in configuration.topics.topics)
    typer.echo(
        "Configuration valid: "
        f"{len(configuration.topics.topics)} topic(s), {enabled_count} enabled."
    )


def _open_connection(settings_path: Path, topics_path: Path) -> sqlite3.Connection:
    configuration = ApplicationSettings(**_load_yaml_mapping(settings_path))
    # Every command that touches the database gets structured, redacted logging. Configuring it
    # here rather than in the callback uses the level from the settings file actually in use.
    configure_logging(configuration.log_level)
    connection = connect(configuration.data_directory / "research_agent.db")
    apply_migrations(connection)
    bootstrap(SqliteTopicRepository(connection), topics_path)
    return connection


def _open_repository(settings_path: Path, topics_path: Path) -> SqliteTopicRepository:
    return SqliteTopicRepository(_open_connection(settings_path, topics_path))


SettingsOption = Annotated[
    Path, typer.Option("--settings", help="Path to application settings YAML.")
]
TopicsOption = Annotated[Path, typer.Option("--topics", help="Path to topic definitions YAML.")]


@topic_app.command("add")
def add_topic(
    topic_id: Annotated[str, typer.Option("--id", help="Unique topic identifier.")],
    name: Annotated[str, typer.Option("--name", help="Human-readable topic name.")],
    lookback_days: Annotated[int, typer.Option(help="Discovery lookback window in days.")] = 10,
    keyword: Annotated[
        list[str] | None, typer.Option("--keyword", help="Known keyword; repeat for more.")
    ] = None,
    openalex: Annotated[bool, typer.Option(help="Enable the OpenAlex source.")] = True,
    semantic_scholar: Annotated[
        bool, typer.Option(help="Enable the Semantic Scholar source.")
    ] = True,
    arxiv: Annotated[bool, typer.Option(help="Enable the arXiv source.")] = True,
    max_candidates: Annotated[int, typer.Option(help="Maximum discovered candidates.")] = 500,
    max_classified: Annotated[int, typer.Option(help="Maximum classified papers.")] = 250,
    max_downloads: Annotated[int, typer.Option(help="Maximum PDF downloads.")] = 50,
    max_deep_reads: Annotated[int, typer.Option(help="Maximum deep reads.")] = 15,
    enabled: Annotated[bool, typer.Option(help="Enable the topic immediately.")] = True,
    frequency: Annotated[str, typer.Option(help="Run frequency.")] = "weekly",
    day: Annotated[str, typer.Option(help="Scheduled weekday.")] = "sunday",
    settings: SettingsOption = Path("config/settings.yaml"),
    topics: TopicsOption = Path("config/topics.yaml"),
) -> None:
    """Create a persistent topic definition."""
    try:
        topic = TopicSettings.model_validate(
            {
                "id": topic_id,
                "name": name,
                "enabled": enabled,
                "lookback_days": lookback_days,
                "keywords": keyword or [],
                "discovery": {
                    "openalex": openalex,
                    "semantic_scholar": semantic_scholar,
                    "arxiv": arxiv,
                },
                "limits": {
                    "max_candidates": max_candidates,
                    "max_classified": max_classified,
                    "max_downloads": max_downloads,
                    "max_deep_reads": max_deep_reads,
                },
                "scheduling": {"frequency": frequency, "day": day},
            }
        )
        _open_repository(settings, topics).add(topic)
    except (ConfigurationError, ValidationError, TopicStoreError) as error:
        typer.echo(f"Unable to add topic: {error}", err=True)
        raise typer.Exit(code=1) from error

    typer.echo(f"Added topic {topic.id}.")


@topic_app.command("list")
def list_topics(
    settings: SettingsOption = Path("config/settings.yaml"),
    topics: TopicsOption = Path("config/topics.yaml"),
) -> None:
    """List stored topics in deterministic order."""
    try:
        stored = _open_repository(settings, topics).list()
    except (ConfigurationError, ValidationError) as error:
        typer.echo(f"Unable to list topics: {error}", err=True)
        raise typer.Exit(code=1) from error

    if not stored:
        typer.echo("No topics stored. Add one with 'research-agent topic add'.")
        return

    for topic in stored:
        state = "enabled" if topic.enabled else "disabled"
        typer.echo(f"{topic.id}\t{state}\t{topic.lookback_days}d\tsemantic-screening\t{topic.name}")


def _set_enabled(topic_id: str, enabled: bool, settings: Path, topics: Path) -> None:
    try:
        _open_repository(settings, topics).set_enabled(topic_id, enabled)
    except (ConfigurationError, ValidationError, TopicStoreError) as error:
        typer.echo(f"Unable to update topic: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"{'Enabled' if enabled else 'Disabled'} topic {topic_id}.")


@topic_app.command("enable")
def enable_topic(
    topic_id: Annotated[str, typer.Argument(help="Topic identifier.")],
    settings: SettingsOption = Path("config/settings.yaml"),
    topics: TopicsOption = Path("config/topics.yaml"),
) -> None:
    """Enable a stored topic."""
    _set_enabled(topic_id, True, settings, topics)


@topic_app.command("disable")
def disable_topic(
    topic_id: Annotated[str, typer.Argument(help="Topic identifier.")],
    settings: SettingsOption = Path("config/settings.yaml"),
    topics: TopicsOption = Path("config/topics.yaml"),
) -> None:
    """Disable a stored topic."""
    _set_enabled(topic_id, False, settings, topics)


def _http_client(timeout: float) -> httpx.AsyncClient:
    """Build the HTTP client used for discovery; tests replace this with a mock transport."""
    return httpx.AsyncClient(timeout=timeout, follow_redirects=True)


@app.command("discover")
def discover(
    topic_id: Annotated[str, typer.Option("--topic", help="Topic identifier.")],
    query: Annotated[str, typer.Option("--query", help="Search query to send to each source.")],
    days: Annotated[
        int | None, typer.Option(help="Lookback window; defaults to the topic setting.")
    ] = None,
    limit: Annotated[
        int | None, typer.Option(help="Maximum candidates; defaults to the topic limit.")
    ] = None,
    settings: SettingsOption = Path("config/settings.yaml"),
    topics: TopicsOption = Path("config/topics.yaml"),
) -> None:
    """Search the enabled academic sources for one topic and print the merged candidates."""
    try:
        application = ApplicationSettings(**_load_yaml_mapping(settings))
        topic = _open_repository(settings, topics).get(topic_id)
    except (ConfigurationError, ValidationError, TopicStoreError) as error:
        typer.echo(f"Unable to run discovery: {error}", err=True)
        raise typer.Exit(code=1) from error
    if topic is None:
        typer.echo(f"Unknown topic: {topic_id}", err=True)
        raise typer.Exit(code=1)

    end_date = datetime.now(UTC).date()
    start_date = end_date - timedelta(days=days or topic.lookback_days)
    result = asyncio.run(
        _discover(
            application, topic, query, start_date, end_date, limit or topic.limits.max_candidates
        )
    )

    counts = ", ".join(f"{name} {count}" for name, count in sorted(result.counts.items()))
    typer.echo(f"{len(result.candidates)} candidate(s) from {start_date} to {end_date} ({counts}).")
    for error_record in result.errors:
        typer.echo(f"source error: {error_record.category} {error_record.message}", err=True)
    for candidate in result.candidates:
        published = candidate.publication_date or "unknown"
        sources = "+".join(reference.source for reference in candidate.sources)
        typer.echo(f"{candidate.canonical_id}\t{published}\t{sources}\t{candidate.title}")


async def _discover(
    application: ApplicationSettings,
    topic: TopicSettings,
    query: str,
    start_date: date,
    end_date: date,
    limit: int,
) -> DiscoveryResult:
    timeout = max(
        application.sources.openalex.timeout_seconds,
        application.sources.semantic_scholar.timeout_seconds,
        application.sources.arxiv.timeout_seconds,
    )
    async with _http_client(timeout) as client:
        aggregator = DiscoveryAggregator(
            build_sources(client, application, topic.discovery),
            concurrency=application.concurrency.discovery,
            settings=application,
        )
        return await aggregator.search(query, start_date, end_date, limit)


model_app = typer.Typer(help="Inspect configured inference providers.")
app.add_typer(model_app, name="model")


@model_app.command("check")
def model_check(
    capability: Annotated[
        str, typer.Option("--capability", help="Capability to route the probe through.")
    ] = "cheap_text",
    prompt: Annotated[
        str, typer.Option("--prompt", help="Prompt sent to the resolved provider.")
    ] = "Reply with the single word: ready.",
    settings: SettingsOption = Path("config/settings.yaml"),
) -> None:
    """Route one small prompt through the configured providers and report what answered."""
    try:
        application = ApplicationSettings(**_load_yaml_mapping(settings))
    except (ConfigurationError, ValidationError) as error:
        typer.echo(f"Unable to load settings: {error}", err=True)
        raise typer.Exit(code=1) from error

    typer.echo(
        f"local: {application.models.local.model} at {application.models.local.base_url}\n"
        f"nvidia_nim: {application.models.nim.model} "
        f"({'api key configured' if application.models.nim.api_key else 'no api key'}), "
        f"strong provider {application.strong_model_provider}"
    )

    try:
        result = asyncio.run(_model_check(application, capability, prompt))
    except ValueError as error:
        typer.echo(f"Unknown capability: {capability}", err=True)
        raise typer.Exit(code=1) from error
    except ModelProviderError as error:
        typer.echo(f"Inference failed: {error}", err=True)
        raise typer.Exit(code=1) from error

    fallback = " (fell back to local)" if result.fell_back else ""
    typer.echo(f"{result.provider}\t{result.model}\t{result.latency_ms}ms{fallback}")
    typer.echo(result.text)


async def _model_check(
    application: ApplicationSettings, capability: str, prompt: str
) -> ModelResult:
    timeout = max(application.models.local.timeout_seconds, application.models.nim.timeout_seconds)
    async with _http_client(timeout) as client:
        router = build_router(client, application)
        return await router.generate(
            cast(Capability, capability), [ModelMessage(role="user", content=prompt)]
        )


queries_app = typer.Typer(help="Plan the searches a topic should run.")
app.add_typer(queries_app, name="queries")


@queries_app.command("plan")
def plan_queries(
    topic_id: Annotated[str, typer.Option("--topic", help="Topic identifier.")],
    save: Annotated[bool, typer.Option(help="Persist the resolved plan for later audit.")] = True,
    settings: SettingsOption = Path("config/settings.yaml"),
    topics: TopicsOption = Path("config/topics.yaml"),
) -> None:
    """Expand one topic into a bounded search plan, falling back when inference is unavailable."""
    try:
        application = ApplicationSettings(**_load_yaml_mapping(settings))
        connection = _open_connection(settings, topics)
        topic = SqliteTopicRepository(connection).get(topic_id)
    except (ConfigurationError, ValidationError, TopicStoreError) as error:
        typer.echo(f"Unable to plan queries: {error}", err=True)
        raise typer.Exit(code=1) from error
    if topic is None:
        typer.echo(f"Unknown topic: {topic_id}", err=True)
        raise typer.Exit(code=1)

    history = SqliteResultRepository(connection).recent_syntheses(
        topic_id, limit=application.queries.history_syntheses
    )
    plan = asyncio.run(_plan_queries(application, topic, history))

    if save:
        SqliteQueryPlanRepository(connection).save(plan)
    provider = plan.model_provider or "none"
    typer.echo(
        f"{len(plan.queries)} query(s) for {topic.id} "
        f"[{plan.prompt_version} via {provider}/{plan.model_name or 'fallback'}"
        f"{', fell back to the base query' if plan.fell_back else ''}]"
    )
    for query in plan.queries:
        typer.echo(query)


async def _plan_queries(
    application: ApplicationSettings,
    topic: TopicSettings,
    history: list[WeeklySynthesis],
) -> QueryPlan:
    async with _http_client(application.models.local.timeout_seconds) as client:
        planner = QueryPlanner(build_router(client, application), application.queries)
        return await planner.plan(topic, history)


@app.command("classify")
def classify(
    topic_id: Annotated[str, typer.Option("--topic", help="Topic identifier.")],
    query: Annotated[
        str | None, typer.Option("--query", help="Search query; defaults to the topic base query.")
    ] = None,
    days: Annotated[
        int | None, typer.Option(help="Lookback window; defaults to the topic setting.")
    ] = None,
    limit: Annotated[
        int | None, typer.Option(help="Maximum candidates; defaults to the topic limit.")
    ] = None,
    save: Annotated[bool, typer.Option(help="Persist a run with the resulting verdicts.")] = True,
    reanalyze: Annotated[
        bool, typer.Option(help="Reconsider papers that were already analyzed.")
    ] = False,
    settings: SettingsOption = Path("config/settings.yaml"),
    topics: TopicsOption = Path("config/topics.yaml"),
) -> None:
    """Discover papers for one topic, triage them, and select a bounded reading set."""
    try:
        application = ApplicationSettings(**_load_yaml_mapping(settings))
        connection = _open_connection(settings, topics)
        topic = SqliteTopicRepository(connection).get(topic_id)
    except (ConfigurationError, ValidationError, TopicStoreError) as error:
        typer.echo(f"Unable to classify: {error}", err=True)
        raise typer.Exit(code=1) from error
    if topic is None:
        typer.echo(f"Unknown topic: {topic_id}", err=True)
        raise typer.Exit(code=1)

    # The base query is the deterministic first entry of any plan, so no inference is needed here.
    search = query or base_query(topic)
    end_date = datetime.now(UTC).date()
    start_date = end_date - timedelta(days=days or topic.lookback_days)
    discovered, outcome, screening_failures = asyncio.run(
        _classify(
            application, topic, search, start_date, end_date, limit or topic.limits.max_candidates
        )
    )

    typer.echo(
        f"{len(outcome)} screening verdict(s) for {topic.id} on '{search}' "
        f"({start_date} to {end_date})."
    )
    verdicts = [result for result, _ in outcome]
    analyzed = SqlitePaperRepository(connection).analyzed_unchanged(
        result.paper_id for result in verdicts
    )
    plan = select(verdicts, topic.limits, application.selection, analyzed, reanalyze)

    typer.echo(
        f"selected {len(plan.selected_ids)} of {len(plan.decisions)}: "
        f"{len(plan.deep_reads)} deep read, {len(plan.summaries)} summarize."
    )
    for error_record in discovered.errors:
        typer.echo(f"source error: {error_record.category} {error_record.message}", err=True)
    for failure in screening_failures:
        typer.echo(f"screening error: {failure.category} {failure.paper_id}", err=True)
    for decision in plan.decisions:
        typer.echo(
            f"{decision.rank}\t{'select' if decision.selected else 'skip'}\t"
            f"{decision.action}\t{decision.reason}\t{decision.paper_id}"
        )

    if save:
        run_id = _save_classifications(connection, application, topic, discovered, outcome, plan)
        typer.echo(f"saved as run {run_id}")


async def _classify(
    application: ApplicationSettings,
    topic: TopicSettings,
    query: str,
    start_date: date,
    end_date: date,
    limit: int,
) -> tuple[
    DiscoveryResult, list[tuple[ClassificationResult, dict[str, object]]], list[ScreeningFailure]
]:
    discovered = await _discover(application, topic, query, start_date, end_date, limit)
    candidates = discovered.candidates[: topic.limits.max_classified]
    timeout = application.models.local.timeout_seconds
    async with _http_client(timeout) as client:
        outcome, failures = await PaperScreener(
            build_router(client, application), application
        ).screen_many(candidates, topic)
        return discovered, outcome, failures


def _save_classifications(
    connection: sqlite3.Connection,
    application: ApplicationSettings,
    topic: TopicSettings,
    discovered: DiscoveryResult,
    outcome: list[tuple[ClassificationResult, dict[str, object]]],
    plan: SelectionPlan,
) -> str:
    """Persist one run and semantic screening verdicts."""
    runs = SqliteRunRepository(connection)
    papers = SqlitePaperRepository(connection)
    results = SqliteResultRepository(connection)
    record = runs.start(topic.id, "semantic_screening", None)
    by_id = {candidate.canonical_id: candidate for candidate in discovered.candidates}
    for result, provenance in outcome:
        candidate = by_id.get(result.paper_id)
        if candidate is not None:
            papers.upsert(candidate)
        results.save_classification(record.id, result, raw_response=provenance)
    SqliteSelectionRepository(connection).save(record.id, plan)
    runs.complete(
        record.id,
        RunSummary(
            candidates_discovered=sum(discovered.counts.values()),
            candidates_deduplicated=len(discovered.candidates),
            papers_classified=len(outcome),
            papers_selected=len(plan.selected_ids),
            deep_reads=len(plan.deep_reads),
            models_used=[application.models.nim.model],
            errors=len(discovered.errors),
        ),
        status="degraded" if discovered.errors else "completed",
    )
    return record.id


@app.command("acquire")
def acquire(
    topic_id: Annotated[str, typer.Option("--topic", help="Topic identifier.")],
    run: Annotated[
        str | None, typer.Option("--run", help="Run to acquire; defaults to the most recent.")
    ] = None,
    limit: Annotated[int | None, typer.Option(help="Maximum papers to download this pass.")] = None,
    settings: SettingsOption = Path("config/settings.yaml"),
    topics: TopicsOption = Path("config/topics.yaml"),
) -> None:
    """Download the open-access PDFs for the papers one run selected."""
    try:
        application = ApplicationSettings(**_load_yaml_mapping(settings))
        connection = _open_connection(settings, topics)
        topic = SqliteTopicRepository(connection).get(topic_id)
    except (ConfigurationError, ValidationError, TopicStoreError) as error:
        typer.echo(f"Unable to acquire: {error}", err=True)
        raise typer.Exit(code=1) from error
    if topic is None:
        typer.echo(f"Unknown topic: {topic_id}", err=True)
        raise typer.Exit(code=1)

    run_id = run or _latest_run(connection, topic_id)
    if run_id is None:
        typer.echo(f"No run found for {topic_id}. Run 'classify' first.", err=True)
        raise typer.Exit(code=1)

    papers = SqlitePaperRepository(connection)
    selected = SqliteSelectionRepository(connection).selected_for(run_id)[
        : limit or topic.limits.max_downloads
    ]
    candidates = [paper for paper in (papers.get(paper_id) for paper_id in selected) if paper]
    if not candidates:
        typer.echo(f"Run {run_id} selected no papers to acquire.", err=True)
        raise typer.Exit(code=1)

    outcomes = asyncio.run(_acquire(application, topic.id, run_id, candidates, papers))

    counts: dict[str, int] = {}
    for outcome in outcomes:
        counts[outcome.status] = counts.get(outcome.status, 0) + 1
    typer.echo(
        f"{len(outcomes)} paper(s) for run {run_id}: "
        + ", ".join(f"{status} {count}" for status, count in sorted(counts.items()))
    )
    runs = SqliteRunRepository(connection)
    for outcome in outcomes:
        typer.echo(f"{outcome.status}\t{outcome.path or outcome.reason}\t{outcome.paper_id}")
        if outcome.status == "failed":
            runs.record_error(
                ErrorRecord(
                    run_id=run_id,
                    node="acquire",
                    category="PDF_DOWNLOAD_ERROR",
                    message=outcome.reason or "download failed",
                    paper_id=outcome.paper_id,
                )
            )


def _latest_run(connection: sqlite3.Connection, topic_id: str) -> str | None:
    recent = SqliteRunRepository(connection).recent(topic_id, limit=1)
    return recent[0].id if recent else None


async def _acquire(
    application: ApplicationSettings,
    topic_id: str,
    run_id: str,
    papers: list[PaperCandidate],
    repository: SqlitePaperRepository,
) -> list[DownloadOutcome]:
    store = LocalArtifactStore(application.data_directory)
    async with _http_client(application.documents.timeout_seconds) as client:
        downloader = PdfDownloader(
            client,
            store,
            repository,
            application.documents,
            retries=application.retries.pdf_download,
            concurrency=application.concurrency.downloads,
        )
        return await downloader.acquire_many(papers, topic_id, run_id)


@app.command("parse")
def parse(
    topic_id: Annotated[str, typer.Option("--topic", help="Topic identifier.")],
    run: Annotated[
        str | None, typer.Option("--run", help="Run to parse; defaults to the most recent.")
    ] = None,
    limit: Annotated[int | None, typer.Option(help="Maximum papers to parse this pass.")] = None,
    force: Annotated[bool, typer.Option(help="Re-parse papers that already have output.")] = False,
    settings: SettingsOption = Path("config/settings.yaml"),
    topics: TopicsOption = Path("config/topics.yaml"),
) -> None:
    """Convert the PDFs a run acquired into structured, reusable text."""
    try:
        application = ApplicationSettings(**_load_yaml_mapping(settings))
        connection = _open_connection(settings, topics)
        topic = SqliteTopicRepository(connection).get(topic_id)
    except (ConfigurationError, ValidationError, TopicStoreError) as error:
        typer.echo(f"Unable to parse: {error}", err=True)
        raise typer.Exit(code=1) from error
    if topic is None:
        typer.echo(f"Unknown topic: {topic_id}", err=True)
        raise typer.Exit(code=1)

    run_id = run or _latest_run(connection, topic_id)
    if run_id is None:
        typer.echo(f"No run found for {topic_id}. Run 'classify' first.", err=True)
        raise typer.Exit(code=1)

    papers = SqlitePaperRepository(connection)
    selected = SqliteSelectionRepository(connection).selected_for(run_id)
    acquired = [paper_id for paper_id in selected if "pdf" in papers.files_for(paper_id)]
    if not acquired:
        typer.echo(f"Run {run_id} has no stored PDFs. Run 'acquire' first.", err=True)
        raise typer.Exit(code=1)

    service = ParsingService(
        DoclingParser(), LocalArtifactStore(application.data_directory), papers
    )
    outcomes = service.parse_many(acquired[: limit or len(acquired)], topic.id, run_id, force)

    counts: dict[str, int] = {}
    for outcome in outcomes:
        counts[outcome.status] = counts.get(outcome.status, 0) + 1
    typer.echo(
        f"{len(outcomes)} paper(s) for run {run_id}: "
        + ", ".join(f"{status} {count}" for status, count in sorted(counts.items()))
    )
    runs = SqliteRunRepository(connection)
    for outcome in outcomes:
        detail = outcome.path or outcome.reason
        typer.echo(f"{outcome.status}\t{outcome.sections} section(s)\t{detail}\t{outcome.paper_id}")
        if outcome.status == "failed":
            runs.record_error(
                ErrorRecord(
                    run_id=run_id,
                    node="parse",
                    category="PDF_PARSE_ERROR",
                    message=outcome.reason or "parse failed",
                    paper_id=outcome.paper_id,
                )
            )


@app.command("analyze")
def analyze(
    topic_id: Annotated[str, typer.Option("--topic", help="Topic identifier.")],
    run: Annotated[
        str | None, typer.Option("--run", help="Run to analyze; defaults to the most recent.")
    ] = None,
    limit: Annotated[int | None, typer.Option(help="Maximum papers to analyze this pass.")] = None,
    force: Annotated[
        bool, typer.Option(help="Re-analyze papers that already have output.")
    ] = False,
    settings: SettingsOption = Path("config/settings.yaml"),
    topics: TopicsOption = Path("config/topics.yaml"),
) -> None:
    """Read the papers a run selected and write an evidence-backed analysis and card for each."""
    try:
        application = ApplicationSettings(**_load_yaml_mapping(settings))
        connection = _open_connection(settings, topics)
        topic = SqliteTopicRepository(connection).get(topic_id)
    except (ConfigurationError, ValidationError, TopicStoreError) as error:
        typer.echo(f"Unable to analyze: {error}", err=True)
        raise typer.Exit(code=1) from error
    if topic is None:
        typer.echo(f"Unknown topic: {topic_id}", err=True)
        raise typer.Exit(code=1)

    run_id = run or _latest_run(connection, topic_id)
    if run_id is None:
        typer.echo(f"No run found for {topic_id}. Run 'classify' first.", err=True)
        raise typer.Exit(code=1)

    papers = SqlitePaperRepository(connection)
    selected = SqliteSelectionRepository(connection).selected_for(run_id)[
        : limit or topic.limits.max_deep_reads
    ]
    candidates = [paper for paper in (papers.get(paper_id) for paper_id in selected) if paper]
    if not candidates:
        typer.echo(f"Run {run_id} selected no papers to analyze.", err=True)
        raise typer.Exit(code=1)

    store = LocalArtifactStore(application.data_directory)
    parsed = {
        paper_id: document
        for paper_id in selected
        if (document := load_parsed(store, paper_id, topic.id)) is not None
    }
    outcomes = asyncio.run(
        _analyze(application, topic, run_id, candidates, parsed, papers, store, connection, force)
    )

    counts: dict[str, int] = {}
    for outcome in outcomes:
        counts[outcome.status] = counts.get(outcome.status, 0) + 1
    typer.echo(
        f"{len(outcomes)} paper(s) for run {run_id}: "
        + ", ".join(f"{status} {count}" for status, count in sorted(counts.items()))
    )
    runs = SqliteRunRepository(connection)
    for outcome in outcomes:
        depth = "abstract-only" if outcome.abstract_only else "full text"
        detail = outcome.path or outcome.reason or ""
        typer.echo(f"{outcome.status}\t{depth}\t{detail}\t{outcome.paper_id}")
        if outcome.status == "failed":
            runs.record_error(
                ErrorRecord(
                    run_id=run_id,
                    node="analyze",
                    category="MODEL_API_ERROR",
                    message=outcome.reason or "analysis failed",
                    paper_id=outcome.paper_id,
                )
            )


async def _analyze(
    application: ApplicationSettings,
    topic: TopicSettings,
    run_id: str,
    candidates: list[PaperCandidate],
    parsed: dict[str, ParsedPaper],
    papers: SqlitePaperRepository,
    store: LocalArtifactStore,
    connection: sqlite3.Connection,
    force: bool,
) -> list[AnalysisOutcome]:
    async with _http_client(application.models.nim.timeout_seconds) as client:
        analyzer = PaperAnalyzer(
            build_router(client, application),
            SqliteResultRepository(connection),
            papers,
            store,
            application.analysis,
            concurrency=application.concurrency.analysis,
        )
        return await analyzer.analyze_many(candidates, parsed, topic, run_id, force)


@app.command("synthesize")
def synthesize(
    topic_id: Annotated[str, typer.Option("--topic", help="Topic identifier.")],
    run: Annotated[
        str | None, typer.Option("--run", help="Run to synthesize; defaults to the most recent.")
    ] = None,
    days: Annotated[
        int | None, typer.Option(help="Reporting period length; defaults to the topic lookback.")
    ] = None,
    settings: SettingsOption = Path("config/settings.yaml"),
    topics: TopicsOption = Path("config/topics.yaml"),
) -> None:
    """Compare a run's analyses with each other and with the topic's recent history."""
    try:
        application = ApplicationSettings(**_load_yaml_mapping(settings))
        connection = _open_connection(settings, topics)
        topic = SqliteTopicRepository(connection).get(topic_id)
    except (ConfigurationError, ValidationError, TopicStoreError) as error:
        typer.echo(f"Unable to synthesize: {error}", err=True)
        raise typer.Exit(code=1) from error
    if topic is None:
        typer.echo(f"Unknown topic: {topic_id}", err=True)
        raise typer.Exit(code=1)

    run_id = run or _latest_run(connection, topic_id)
    if run_id is None:
        typer.echo(f"No run found for {topic_id}. Run 'classify' first.", err=True)
        raise typer.Exit(code=1)

    papers = SqlitePaperRepository(connection)
    results = SqliteResultRepository(connection)
    selected = SqliteSelectionRepository(connection).selected_for(run_id)
    analyses = [
        analysis
        for analysis in (results.analysis_for(paper_id) for paper_id in selected)
        if analysis
    ]
    if not analyses:
        typer.echo(f"Run {run_id} has no analyses. Run 'analyze' first.", err=True)
        raise typer.Exit(code=1)
    titles = {
        analysis.paper_id: paper.title
        for analysis in analyses
        if (paper := papers.get(analysis.paper_id)) is not None
    }

    end_date = datetime.now(UTC).date()
    start_date = end_date - timedelta(days=days or topic.lookback_days)
    outcome = asyncio.run(
        _synthesize(application, topic, run_id, analyses, titles, start_date, end_date, results)
    )

    if outcome.synthesis is None:
        typer.echo(f"No synthesis for run {run_id}: {outcome.reason}", err=True)
        SqliteRunRepository(connection).record_error(
            ErrorRecord(
                run_id=run_id,
                node="synthesize",
                category="MODEL_API_ERROR",
                message=outcome.reason or "synthesis failed",
            )
        )
        raise typer.Exit(code=1)

    synthesis = outcome.synthesis
    typer.echo(
        f"synthesis for run {run_id} over {len(analyses)} analysis(es), "
        f"{synthesis.history_periods} previous period(s), "
        f"{outcome.dropped_findings} unsupported finding(s) dropped."
    )
    for label, findings in (
        ("development", synthesis.major_developments),
        ("direction", synthesis.emerging_directions),
        ("method", synthesis.methods_gaining_attention),
        ("contradiction", synthesis.contradictions),
        ("limitation", synthesis.common_limitations),
    ):
        for finding in findings:
            typer.echo(f"{label}\t{', '.join(finding.supporting_paper_ids)}\t{finding.text}")
    for change in synthesis.changes_from_history:
        typer.echo(f"change\t\t{change}")


async def _synthesize(
    application: ApplicationSettings,
    topic: TopicSettings,
    run_id: str,
    analyses: list[PaperAnalysis],
    titles: dict[str, str],
    start_date: date,
    end_date: date,
    results: SqliteResultRepository,
) -> SynthesisOutcome:
    async with _http_client(application.models.nim.timeout_seconds) as client:
        synthesizer = WeeklySynthesizer(
            build_router(client, application), results, application.synthesis
        )
        return await synthesizer.synthesize(topic, run_id, analyses, titles, start_date, end_date)


@app.command("ideate")
def ideate(
    topic_id: Annotated[str, typer.Option("--topic", help="Topic identifier.")],
    run: Annotated[
        str | None, typer.Option("--run", help="Run to work from; defaults to the most recent.")
    ] = None,
    settings: SettingsOption = Path("config/settings.yaml"),
    topics: TopicsOption = Path("config/topics.yaml"),
) -> None:
    """Turn a run's synthesis into supported research gaps and concrete research ideas."""
    try:
        application = ApplicationSettings(**_load_yaml_mapping(settings))
        connection = _open_connection(settings, topics)
        topic = SqliteTopicRepository(connection).get(topic_id)
    except (ConfigurationError, ValidationError, TopicStoreError) as error:
        typer.echo(f"Unable to ideate: {error}", err=True)
        raise typer.Exit(code=1) from error
    if topic is None:
        typer.echo(f"Unknown topic: {topic_id}", err=True)
        raise typer.Exit(code=1)

    run_id = run or _latest_run(connection, topic_id)
    if run_id is None:
        typer.echo(f"No run found for {topic_id}. Run 'classify' first.", err=True)
        raise typer.Exit(code=1)

    results = SqliteResultRepository(connection)
    history = results.recent_syntheses(topic_id, limit=1)
    if not history:
        typer.echo(f"Topic {topic_id} has no synthesis. Run 'synthesize' first.", err=True)
        raise typer.Exit(code=1)

    outcome = asyncio.run(_ideate(application, topic, run_id, history[0], results))

    if not outcome.gaps:
        typer.echo(f"No gaps for run {run_id}: {outcome.reason}", err=True)
        SqliteRunRepository(connection).record_error(
            ErrorRecord(
                run_id=run_id,
                node="ideate",
                category="MODEL_API_ERROR",
                message=outcome.reason or "ideation failed",
            )
        )
        raise typer.Exit(code=1)

    path = LocalArtifactStore(application.data_directory).write_text(
        topic.id, "runs", f"{run_id}-ideation.md", render_ideation(outcome.gaps, outcome.ideas)
    )
    typer.echo(
        f"{len(outcome.gaps)} gap(s) and {len(outcome.ideas)} idea(s) for run {run_id}; "
        f"{outcome.dropped_gaps} gap(s) and {outcome.dropped_ideas} idea(s) dropped as unsupported."
    )
    for gap in outcome.gaps:
        typer.echo(f"gap\t{', '.join(gap.supporting_paper_ids)}\t{gap.title}")
    for idea in outcome.ideas:
        typer.echo(f"idea\t{', '.join(idea.supporting_paper_ids)}\t{idea.title}")
    typer.echo(f"written to {path}")
    if outcome.reason is not None:
        typer.echo(f"partial: {outcome.reason}", err=True)


async def _ideate(
    application: ApplicationSettings,
    topic: TopicSettings,
    run_id: str,
    synthesis: WeeklySynthesis,
    results: SqliteResultRepository,
) -> IdeationOutcome:
    async with _http_client(application.models.nim.timeout_seconds) as client:
        service = IdeationService(build_router(client, application), results, application.ideation)
        return await service.generate(topic, run_id, synthesis)


report_app = typer.Typer(help="Generate and retrieve weekly reports.")
app.add_typer(report_app, name="report")


@report_app.command("generate")
def generate_report(
    topic_id: Annotated[str, typer.Option("--topic", help="Topic identifier.")],
    run: Annotated[
        str | None, typer.Option("--run", help="Run to report on; defaults to the most recent.")
    ] = None,
    days: Annotated[
        int | None, typer.Option(help="Reporting period length; defaults to the topic lookback.")
    ] = None,
    prose: Annotated[bool, typer.Option(help="Ask a model for the executive summary.")] = True,
    settings: SettingsOption = Path("config/settings.yaml"),
    topics: TopicsOption = Path("config/topics.yaml"),
) -> None:
    """Assemble the weekly Markdown report for one run from its persisted records."""
    try:
        application = ApplicationSettings(**_load_yaml_mapping(settings))
        connection = _open_connection(settings, topics)
        topic = SqliteTopicRepository(connection).get(topic_id)
    except (ConfigurationError, ValidationError, TopicStoreError) as error:
        typer.echo(f"Unable to report: {error}", err=True)
        raise typer.Exit(code=1) from error
    if topic is None:
        typer.echo(f"Unknown topic: {topic_id}", err=True)
        raise typer.Exit(code=1)

    run_id = run or _latest_run(connection, topic_id)
    record = None if run_id is None else SqliteRunRepository(connection).get(run_id)
    if record is None:
        typer.echo(f"No run found for {topic_id}. Run 'classify' first.", err=True)
        raise typer.Exit(code=1)

    end_date = datetime.now(UTC).date()
    start_date = end_date - timedelta(days=days or topic.lookback_days)
    selected = SqliteSelectionRepository(connection).selected_for(record.id)
    outcome = asyncio.run(
        _report(application, topic, record, selected, start_date, end_date, connection, prose)
    )

    kind = "empty-week" if outcome.empty_week else f"{outcome.papers} paper(s)"
    typer.echo(
        f"{kind} report for run {record.id}"
        + (" (degraded)" if outcome.degraded else "")
        + (" with model-written summary" if outcome.prose else " with assembled summary")
    )
    typer.echo(outcome.path)


@report_app.command("latest")
def latest_report(
    topic_id: Annotated[str, typer.Argument(help="Topic identifier.")],
    settings: SettingsOption = Path("config/settings.yaml"),
    topics: TopicsOption = Path("config/topics.yaml"),
) -> None:
    """Print the path of the newest stored report for one topic."""
    try:
        application = ApplicationSettings(**_load_yaml_mapping(settings))
        connection = _open_connection(settings, topics)
    except (ConfigurationError, ValidationError, TopicStoreError) as error:
        typer.echo(f"Unable to read reports: {error}", err=True)
        raise typer.Exit(code=1) from error

    service = ReportService(
        LocalArtifactStore(application.data_directory),
        SqliteResultRepository(connection),
        SqlitePaperRepository(connection),
        SqliteRunRepository(connection),
    )
    path = service.latest(topic_id)
    if path is None:
        typer.echo(f"No report stored for {topic_id}.", err=True)
        raise typer.Exit(code=1)
    typer.echo(path)


async def _report(
    application: ApplicationSettings,
    topic: TopicSettings,
    run: RunRecord,
    paper_ids: list[str],
    start_date: date,
    end_date: date,
    connection: sqlite3.Connection,
    prose: bool,
) -> ReportOutcome:
    async with _http_client(application.models.nim.timeout_seconds) as client:
        service = ReportService(
            LocalArtifactStore(application.data_directory),
            SqliteResultRepository(connection),
            SqlitePaperRepository(connection),
            SqliteRunRepository(connection),
            build_router(client, application) if prose else None,
            application.reports,
        )
        return await service.generate(topic, run, paper_ids, start_date, end_date)


def _run_one(
    connection: sqlite3.Connection,
    application: ApplicationSettings,
    topic: TopicSettings,
) -> RunOutcome:
    return asyncio.run(execute_run(connection, application, topic, client_factory=_http_client))


def _echo_outcome(outcome: RunOutcome) -> None:
    detail = outcome.reason or outcome.report_path or ""
    typer.echo(
        f"{outcome.conclusion}\t{outcome.topic_id}\t"
        f"{outcome.papers_analyzed} paper(s)\t{outcome.errors} error(s)\t{detail}"
    )


@app.command("run")
def run_topic(
    topic_id: Annotated[str, typer.Argument(help="Topic identifier.")],
    settings: SettingsOption = Path("config/settings.yaml"),
    topics: TopicsOption = Path("config/topics.yaml"),
) -> None:
    """Run the complete weekly workflow for one topic."""
    try:
        application = ApplicationSettings(**_load_yaml_mapping(settings))
        connection = _open_connection(settings, topics)
        topic = SqliteTopicRepository(connection).get(topic_id)
    except (ConfigurationError, ValidationError, TopicStoreError) as error:
        typer.echo(f"Unable to run: {error}", err=True)
        raise typer.Exit(code=1) from error
    if topic is None:
        typer.echo(f"Unknown topic: {topic_id}", err=True)
        raise typer.Exit(code=1)

    outcome = _run_one(connection, application, topic)
    _echo_outcome(outcome)
    if outcome.conclusion in ("skipped", "locked"):
        raise typer.Exit(code=1)
    if outcome.fatal:
        typer.echo("the run produced no report; partial artifacts are kept", err=True)
        raise typer.Exit(code=1)


@app.command("run-all")
def run_all(
    settings: SettingsOption = Path("config/settings.yaml"),
    topics: TopicsOption = Path("config/topics.yaml"),
) -> None:
    """Run every enabled topic in turn, reporting each outcome; disabled topics are skipped."""
    try:
        application = ApplicationSettings(**_load_yaml_mapping(settings))
        connection = _open_connection(settings, topics)
        stored = SqliteTopicRepository(connection).list()
    except (ConfigurationError, ValidationError, TopicStoreError) as error:
        typer.echo(f"Unable to run: {error}", err=True)
        raise typer.Exit(code=1) from error

    outcomes = [_run_one(connection, application, topic) for topic in stored]
    for outcome in outcomes:
        _echo_outcome(outcome)
    counts: dict[str, int] = {}
    for outcome in outcomes:
        counts[outcome.conclusion] = counts.get(outcome.conclusion, 0) + 1
    typer.echo(
        f"{len(outcomes)} topic(s): "
        + ", ".join(f"{name} {count}" for name, count in sorted(counts.items()))
    )
    if any(outcome.fatal for outcome in outcomes):
        raise typer.Exit(code=1)


schedule_app = typer.Typer(
    help="Generate local weekly schedules; scheduling stays outside the graph."
)
app.add_typer(schedule_app, name="schedule")


@schedule_app.command("generate")
def generate_schedule(
    topic_id: Annotated[str, typer.Option("--topic", help="Topic identifier.")],
    backend: Annotated[
        str | None,
        typer.Option(help="launchd, cron or eventbridge; defaults to the configured backend."),
    ] = None,
    at: Annotated[str, typer.Option(help="Local time of day, HH:MM.")] = "07:00",
    output: Annotated[
        Path | None, typer.Option(help="Write the schedule here instead of printing it.")
    ] = None,
    settings: SettingsOption = Path("config/settings.yaml"),
    topics: TopicsOption = Path("config/topics.yaml"),
) -> None:
    """Render this topic's weekly trigger for launchd or cron, with how to install it."""
    try:
        application = ApplicationSettings(**_load_yaml_mapping(settings))
        connection = _open_connection(settings, topics)
        topic = SqliteTopicRepository(connection).get(topic_id)
        chosen = backend or application.scheduler_backend
        if chosen not in ("launchd", "cron", "eventbridge"):
            raise ConfigurationError(f"unsupported scheduler backend: {chosen}")
        moment = time.fromisoformat(at)
    except (ConfigurationError, ValidationError, TopicStoreError, ValueError) as error:
        typer.echo(f"Unable to schedule: {error}", err=True)
        raise typer.Exit(code=1) from error
    if topic is None:
        typer.echo(f"Unknown topic: {topic_id}", err=True)
        raise typer.Exit(code=1)

    try:
        artifact = render_schedule(
            topic,
            cast(SchedulerBackend, chosen),
            at=moment,
            working_directory=Path.cwd(),
            log_directory=application.data_directory / "logs",
        )
    except ValidationError as error:
        typer.echo(f"Unable to schedule: {error}", err=True)
        raise typer.Exit(code=1) from error

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(artifact.content, encoding="utf-8")
        typer.echo(f"{artifact.backend} schedule written to {output}")
    else:
        typer.echo(artifact.content)
    typer.echo(artifact.install_hint)

"""Command-line interface for Research Agent."""

import asyncio
import sqlite3
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated, cast

import httpx
import typer
from pydantic import ValidationError

from research_agent import __version__
from research_agent.classifiers.comparison import compare, render
from research_agent.classifiers.factory import build_classifier
from research_agent.classifiers.runner import ClassifierOutcome, ClassifierRunner
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
from research_agent.domain.analysis import WeeklySynthesis
from research_agent.domain.queries import QueryPlan
from research_agent.domain.runs import RunSummary
from research_agent.domain.selection import SelectionPlan
from research_agent.models.base import (
    Capability,
    ModelMessage,
    ModelProviderError,
    ModelResult,
)
from research_agent.models.router import build_router
from research_agent.queries.planner import QueryPlanner, base_query
from research_agent.selection.selector import select
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
    active_classifier: Annotated[str, typer.Option(help="Active classifier (A or B).")] = "A",
    shadow_classifier: Annotated[
        str | None, typer.Option(help="Optional shadow classifier (A or B).")
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
                "classifier": {"active": active_classifier, "shadow": shadow_classifier},
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
        shadow = topic.classifier.shadow or "none"
        typer.echo(
            f"{topic.id}\t{state}\t{topic.lookback_days}d\t"
            f"classifier={topic.classifier.active}/shadow={shadow}\t{topic.name}"
        )


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
    discovered, outcome = asyncio.run(
        _classify(
            application, topic, search, start_date, end_date, limit or topic.limits.max_candidates
        )
    )

    typer.echo(
        f"{len(outcome.active)} verdict(s) for {topic.id} via classifier "
        f"{topic.classifier.active} on '{search}' ({start_date} to {end_date})."
    )
    if topic.classifier.shadow is not None:
        shadow = (
            f"shadow classifier {topic.classifier.shadow} failed: {outcome.shadow_error}"
            if outcome.shadow_error
            else f"shadow classifier {topic.classifier.shadow}: {len(outcome.shadow)} verdict(s)"
        )
        typer.echo(shadow)
    verdicts = [result for result, _ in outcome.active]
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
) -> tuple[DiscoveryResult, ClassifierOutcome]:
    discovered = await _discover(application, topic, query, start_date, end_date, limit)
    candidates = discovered.candidates[: topic.limits.max_classified]
    timeout = application.models.local.timeout_seconds
    async with _http_client(timeout) as client:
        runner = ClassifierRunner(
            build_classifier(topic.classifier.active, client, application),
            None
            if topic.classifier.shadow is None
            else build_classifier(topic.classifier.shadow, client, application),
        )
        return discovered, await runner.run(candidates, topic)


def _save_classifications(
    connection: sqlite3.Connection,
    application: ApplicationSettings,
    topic: TopicSettings,
    discovered: DiscoveryResult,
    outcome: ClassifierOutcome,
    plan: SelectionPlan,
) -> str:
    """Persist one run, its papers, and every verdict; shadow rows are stored but never route."""
    runs = SqliteRunRepository(connection)
    papers = SqlitePaperRepository(connection)
    results = SqliteResultRepository(connection)
    record = runs.start(topic.id, topic.classifier.active, topic.classifier.shadow)
    by_id = {candidate.canonical_id: candidate for candidate in discovered.candidates}
    for result, provenance in outcome.active:
        candidate = by_id.get(result.paper_id)
        if candidate is not None:
            papers.upsert(candidate)
        results.save_classification(record.id, result, raw_response=provenance)
    for result, provenance in outcome.shadow:
        if result.paper_id in {active.paper_id for active, _ in outcome.active}:
            results.save_classification(record.id, result, is_active=False, raw_response=provenance)
    SqliteSelectionRepository(connection).save(record.id, plan)
    runs.complete(
        record.id,
        RunSummary(
            candidates_discovered=sum(discovered.counts.values()),
            candidates_deduplicated=len(discovered.candidates),
            papers_classified=len(outcome.active),
            papers_selected=len(plan.selected_ids),
            deep_reads=len(plan.deep_reads),
            models_used=[application.classifier_a.embedding_model or "lexical"],
            errors=len(discovered.errors) + (1 if outcome.shadow_error else 0),
        ),
        status="degraded" if discovered.errors or outcome.shadow_error else "completed",
    )
    return record.id


classifier_app = typer.Typer(help="Choose which classifier routes a topic.")
app.add_typer(classifier_app, name="classifier")


@classifier_app.command("set")
def set_classifier(
    active: Annotated[str, typer.Argument(help="Classifier that controls routing: A or B.")],
    topic_id: Annotated[str, typer.Option("--topic", help="Topic identifier.")],
    shadow: Annotated[
        str | None,
        typer.Option("--shadow", help="Classifier to run for comparison only, or 'none'."),
    ] = None,
    settings: SettingsOption = Path("config/settings.yaml"),
    topics: TopicsOption = Path("config/topics.yaml"),
) -> None:
    """Switch a topic's active and shadow classifiers; no workflow code changes."""
    resolved = None if shadow is None or shadow.lower() == "none" else shadow.upper()
    try:
        repository = _open_repository(settings, topics)
        repository.set_classifier(topic_id, active.upper(), resolved)
    except (ConfigurationError, ValidationError, TopicStoreError) as error:
        typer.echo(f"Unable to set classifier: {error}", err=True)
        raise typer.Exit(code=1) from error

    typer.echo(f"{topic_id}: active {active.upper()}, shadow {resolved or 'none'}")


@app.command("compare-classifiers")
def compare_classifiers(
    topic_id: Annotated[str, typer.Argument(help="Topic identifier.")],
    runs: Annotated[int, typer.Option(help="How many recent runs to compare.")] = 4,
    settings: SettingsOption = Path("config/settings.yaml"),
    topics: TopicsOption = Path("config/topics.yaml"),
) -> None:
    """Report how the active and shadow classifiers differ on the papers they both judged."""
    try:
        connection = _open_connection(settings, topics)
    except (ConfigurationError, ValidationError, TopicStoreError) as error:
        typer.echo(f"Unable to compare classifiers: {error}", err=True)
        raise typer.Exit(code=1) from error

    active, shadow = SqliteResultRepository(connection).classification_pairs(topic_id, runs)
    if not shadow:
        typer.echo(
            f"No shadow verdicts stored for {topic_id}. "
            "Set a shadow classifier and run 'classify' first.",
            err=True,
        )
        raise typer.Exit(code=1)

    typer.echo(render(compare(active, shadow)))

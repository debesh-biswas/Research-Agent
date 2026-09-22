"""Command-line interface for Research Agent."""

from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from research_agent import __version__
from research_agent.config import (
    ApplicationSettings,
    ConfigurationError,
    TopicSettings,
    _load_yaml_mapping,
    load_configuration,
)
from research_agent.storage.database import apply_migrations, connect
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


def _open_repository(settings_path: Path, topics_path: Path) -> SqliteTopicRepository:
    configuration = ApplicationSettings(**_load_yaml_mapping(settings_path))
    connection = connect(configuration.data_directory / "research_agent.db")
    apply_migrations(connection)
    repository = SqliteTopicRepository(connection)
    bootstrap(repository, topics_path)
    return repository


SettingsOption = Annotated[
    Path, typer.Option("--settings", help="Path to application settings YAML.")
]
TopicsOption = Annotated[Path, typer.Option("--topics", help="Path to topic definitions YAML.")]


@topic_app.command("add")
def add_topic(
    topic_id: Annotated[str, typer.Option("--id", help="Unique topic identifier.")],
    name: Annotated[str, typer.Option("--name", help="Human-readable topic name.")],
    lookback_days: Annotated[int, typer.Option(help="Discovery lookback window in days.")] = 10,
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

"""Command-line interface for Research Agent."""

from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from research_agent import __version__
from research_agent.config import ConfigurationError, load_configuration

app = typer.Typer(
    name="research-agent",
    help="Build evidence-backed weekly AI research intelligence.",
    no_args_is_help=True,
)
config_app = typer.Typer(help="Inspect and validate application configuration.")
app.add_typer(config_app, name="config")


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

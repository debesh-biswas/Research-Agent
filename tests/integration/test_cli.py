from pathlib import Path

from typer.testing import CliRunner

from research_agent import __version__
from research_agent.cli import app

runner = CliRunner()


def test_help_lists_configuration_command() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "config" in result.stdout


def test_version_reports_installed_package_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == f"research-agent {__version__}"


def test_committed_configuration_is_valid() -> None:
    result = runner.invoke(app, ["config", "validate"])

    assert result.exit_code == 0
    assert "1 topic(s), 1 enabled" in result.stdout


def test_validation_reports_missing_file(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "config",
            "validate",
            "--settings",
            str(tmp_path / "missing.yaml"),
            "--topics",
            "config/topics.yaml",
        ],
    )

    assert result.exit_code == 1
    assert "Configuration invalid" in result.stderr
    assert "configuration file not found" in result.stderr


def test_validation_reports_schema_error(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.yaml"
    settings_path.write_text("concurrency:\n  discovery: 0\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "config",
            "validate",
            "--settings",
            str(settings_path),
            "--topics",
            "config/topics.yaml",
        ],
    )

    assert result.exit_code == 1
    assert "Configuration invalid" in result.stderr
    assert "discovery" in result.stderr

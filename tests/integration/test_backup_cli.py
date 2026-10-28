from pathlib import Path

import yaml
from typer.testing import CliRunner

from research_agent.cli import app

runner = CliRunner()


def test_backup_then_restore_needs_yes_to_replace_a_library(tmp_path: Path) -> None:
    settings = tmp_path / "settings.yaml"
    settings.write_text(yaml.safe_dump({"data_directory": str(tmp_path / "data")}), "utf-8")
    topics = tmp_path / "topics.yaml"
    topics.write_text(yaml.safe_dump({"topics": [{"id": "spatial", "name": "S"}]}), "utf-8")
    common = ["--settings", str(settings)]
    assert runner.invoke(app, ["topic", "list", *common, "--topics", str(topics)]).exit_code == 0
    archive = tmp_path / "backup.zip"

    made = runner.invoke(app, ["backup", "--output", str(archive), *common])
    refused = runner.invoke(app, ["restore", str(archive), *common])
    replaced = runner.invoke(app, ["restore", str(archive), "--yes", *common])

    assert made.exit_code == 0 and "Backed up the library" in made.stdout
    assert refused.exit_code == 1 and "--yes" in refused.stderr
    assert replaced.exit_code == 0 and "previous library was moved to" in replaced.stdout

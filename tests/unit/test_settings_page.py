"""Desk-edited settings: what the page shows, what it saves, and how commands load them."""

from pathlib import Path

import pytest
import yaml

from research_agent.config import ApplicationSettings
from research_agent.desk.server import LocalDesk
from research_agent.desk.settings_page import SettingsProblem, overrides_for, page
from research_agent.storage.app_settings import (
    SqliteSettingsOverrides,
    load_settings,
    read_overrides,
)
from research_agent.storage.database import apply_migrations, connect


@pytest.fixture
def settings_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)  # no stray .env from the checkout
    for name in ("RESEARCH_AGENT_MODELS__LOCAL__MODEL", "RESEARCH_AGENT_RETRIES__NIM"):
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / "settings.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "data_directory": str(tmp_path / "data"),
                "models": {"local": {"model": "file-model"}},
                "retries": {"nim": 2},
            }
        ),
        encoding="utf-8",
    )
    connection = connect(tmp_path / "data" / "research_agent.db")
    apply_migrations(connection)
    connection.close()
    return path


def save(tmp_path: Path, overrides: dict[str, object]) -> None:
    connection = connect(tmp_path / "data" / "research_agent.db")
    SqliteSettingsOverrides(connection).save(overrides)
    connection.close()


def test_desk_changes_sit_between_the_environment_and_the_file(
    settings_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert load_settings(settings_file).models.local.model == "file-model"
    save(tmp_path, {"models": {"local": {"model": "desk-model"}}, "retries": {"nim": 0}})

    loaded = load_settings(settings_file)
    assert (loaded.models.local.model, loaded.retries.nim) == ("desk-model", 0)
    assert loaded.models.local.base_url == ApplicationSettings().models.local.base_url

    monkeypatch.setenv("RESEARCH_AGENT_MODELS__LOCAL__MODEL", "env-model")
    assert load_settings(settings_file).models.local.model == "env-model"


def test_a_saved_change_that_no_longer_validates_is_ignored(
    settings_file: Path, tmp_path: Path
) -> None:
    save(tmp_path, {"retries": {"nim": -5}})

    assert load_settings(settings_file).retries.nim == 2


def test_a_library_without_the_table_or_database_has_no_changes(tmp_path: Path) -> None:
    assert read_overrides(tmp_path / "missing.db") == {}
    connection = connect(tmp_path / "old.db")
    connection.execute("CREATE TABLE topics (id TEXT)")
    connection.close()
    assert read_overrides(tmp_path / "old.db") == {}


def test_only_values_that_differ_from_the_file_are_saved(settings_file: Path) -> None:
    defaults = ApplicationSettings()
    values: dict[str, object] = {
        "models.local.model": "file-model",
        "retries.nim": 4,
        "selection.preferred_venues": ["CVPR"],
        "selection.min_relevance_score": defaults.selection.min_relevance_score,
    }

    assert overrides_for(values, settings_file) == {
        "retries": {"nim": 4},
        "selection": {"preferred_venues": ["CVPR"]},
    }


def test_a_bad_value_is_refused_by_its_label_and_unknown_fields_are_refused(
    settings_file: Path,
) -> None:
    with pytest.raises(SettingsProblem, match="NIM retries before the local model"):
        overrides_for({"retries.nim": -1}, settings_file)
    with pytest.raises(SettingsProblem, match="Unknown setting: data_directory"):
        overrides_for({"data_directory": "/elsewhere"}, settings_file)


def test_a_field_set_in_dotenv_is_locked_on_the_page_and_never_saved(
    settings_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "# RESEARCH_AGENT_RETRIES__NIM=9\nexport RESEARCH_AGENT_MODELS__NIM__MODEL=glm\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("RESEARCH_AGENT_MODELS__NIM__API_KEY", "s3cr3t-value")
    effective = load_settings(settings_file)

    shown = page(effective, settings_file, {"retries": {"nim": 1}}, dotenv)

    by_path = {field["path"]: field for field in shown["fields"]}  # type: ignore[attr-defined]
    assert by_path["models.nim.model"]["environment"] == "RESEARCH_AGENT_MODELS__NIM__MODEL"
    assert by_path["models.local.model"]["environment"] is None
    assert by_path["retries.nim"]["changed"] is True
    assert by_path["retries.nim"]["environment"] is None, "a commented line does not count"
    assert "s3cr3t-value" not in str(shown)
    secrets = {item["label"]: item["set"] for item in shown["secrets"]}  # type: ignore[attr-defined]
    assert secrets["NVIDIA NIM API key"] is True
    assert overrides_for({"models.nim.model": "other"}, settings_file, dotenv) == {}


def test_the_desk_saves_resets_and_uses_its_settings(settings_file: Path, tmp_path: Path) -> None:
    database = tmp_path / "data" / "research_agent.db"
    desk = LocalDesk(database, load_settings(settings_file), settings_file=settings_file)

    shown = desk.save_settings({"models.local.model": "desk-model", "retries.nim": 2})

    assert desk._settings.models.local.model == "desk-model"
    assert load_settings(settings_file).models.local.model == "desk-model", "commands see it"
    changed = {f["path"] for f in shown["fields"] if f["changed"]}  # type: ignore[attr-defined]
    assert changed == {"models.local.model"}
    desk.save_settings(None)
    assert load_settings(settings_file).models.local.model == "file-model"
    with pytest.raises(SettingsProblem, match="without a settings file"):
        LocalDesk(database, load_settings(settings_file)).save_settings({})

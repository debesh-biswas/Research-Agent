from pathlib import Path

import pytest
from pydantic import ValidationError

from research_agent.config import (
    ApplicationSettings,
    ClassifierSettings,
    ConcurrencySettings,
    ConfigurationError,
    ResourceLimits,
    load_configuration,
)


def _write_valid_configuration(tmp_path: Path) -> tuple[Path, Path]:
    settings_path = tmp_path / "settings.yaml"
    settings_path.write_text(
        "storage_backend: local\n"
        "metadata_backend: sqlite\n"
        "scheduler_backend: launchd\n"
        "strong_model_provider: local\n",
        encoding="utf-8",
    )
    topics_path = tmp_path / "topics.yaml"
    topics_path.write_text(
        "topics:\n"
        "  - id: test_topic\n"
        "    name: Test Topic\n"
        "    classifier:\n"
        "      active: A\n"
        "      shadow: B\n",
        encoding="utf-8",
    )
    return settings_path, topics_path


def test_load_configuration_uses_defaults(tmp_path: Path) -> None:
    settings_path, topics_path = _write_valid_configuration(tmp_path)

    configuration = load_configuration(settings_path, topics_path)

    assert configuration.settings.concurrency.discovery == 3
    assert configuration.topics.topics[0].lookback_days == 10
    assert configuration.topics.topics[0].discovery.openalex is True


def test_environment_overrides_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEARCH_AGENT_CONCURRENCY__DISCOVERY", "7")

    settings = ApplicationSettings(concurrency=ConcurrencySettings(discovery=2))

    assert settings.concurrency.discovery == 7


def test_active_and_shadow_classifiers_must_differ() -> None:
    with pytest.raises(ValidationError, match="shadow classifier must differ"):
        ClassifierSettings(active="A", shadow="A")


def test_resource_limits_are_monotonic() -> None:
    with pytest.raises(ValidationError, match="max_downloads cannot exceed"):
        ResourceLimits(max_candidates=10, max_classified=5, max_downloads=6)


def test_missing_configuration_file_has_actionable_error(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yaml"

    with pytest.raises(ConfigurationError, match="configuration file not found"):
        load_configuration(missing, missing)


def test_malformed_yaml_has_actionable_error(tmp_path: Path) -> None:
    settings_path, topics_path = _write_valid_configuration(tmp_path)
    settings_path.write_text("value: [unterminated", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="invalid YAML"):
        load_configuration(settings_path, topics_path)

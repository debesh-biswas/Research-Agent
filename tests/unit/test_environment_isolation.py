"""Regression tests for the ambient-settings leak that broke the suite when a `.env` existed."""

import os
from pathlib import Path

from research_agent.config import ApplicationSettings

ENV_PREFIX = "RESEARCH_AGENT_"


def test_no_ambient_settings_variables_are_visible() -> None:
    assert [name for name in os.environ if name.startswith(ENV_PREFIX)] == []


def test_the_dotenv_source_is_disabled_during_tests() -> None:
    assert ApplicationSettings.model_config["env_file"] is None


def test_a_repository_dotenv_cannot_override_supplied_settings(tmp_path: Path) -> None:
    # The real .env in the repository root sets data_directory; a test must not inherit it.
    settings = ApplicationSettings(data_directory=tmp_path / "isolated")

    assert settings.data_directory == tmp_path / "isolated"
    assert settings.models.local.api_key is None


def test_isolation_does_not_stop_a_test_supplying_its_own_values() -> None:
    assert ApplicationSettings(log_level="DEBUG").log_level == "DEBUG"

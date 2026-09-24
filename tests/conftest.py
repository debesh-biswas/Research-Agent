"""Isolation that applies to every test.

Settings resolve environment variables and a `.env` file ahead of any YAML a test passes in
(`ApplicationSettings.settings_customise_sources`). That is correct for the application and wrong
for a test: a developer with a real `.env`, or an exported `RESEARCH_AGENT_*` variable, would
otherwise silently redirect the suite at their own database, endpoints, and credentials.
"""

import os
from collections.abc import Iterator

import pytest

from research_agent.config import ApplicationSettings

ENV_PREFIX = "RESEARCH_AGENT_"


@pytest.fixture(autouse=True)
def isolated_settings_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Hide every ambient settings source, so only what a test supplies can reach the code."""
    for name in list(os.environ):
        if name.startswith(ENV_PREFIX):
            monkeypatch.delenv(name, raising=False)
    # The path is read per instantiation, so replacing it here disables the dotenv source for
    # the duration of one test without touching the application's own configuration.
    monkeypatch.setitem(ApplicationSettings.model_config, "env_file", None)
    yield

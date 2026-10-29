"""The desk's Settings page: which settings it edits, where each value comes from, and saving.

Only settings a reader is likely to change are listed. The library folder is shown, not edited,
because moving it would leave the library behind. Secrets are never sent to the page; it only
learns whether each one is set.
"""

import os
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, ValidationError

from research_agent.config import ApplicationSettings, StrictModel, _load_yaml_mapping
from research_agent.storage.app_settings import merged

Kind = Literal["text", "number", "select", "list"]


class SettingField(StrictModel):
    path: str
    group: str
    label: str
    kind: Kind
    help: str = ""
    options: list[str] = Field(default_factory=list)
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None


FIELDS: tuple[SettingField, ...] = (
    SettingField(
        path="strong_model_provider",
        group="Models",
        label="Model for deep reads and reports",
        kind="select",
        options=["nvidia_nim", "local"],
        help="nvidia_nim needs an API key; without one everything runs on the local model.",
    ),
    SettingField(
        path="models.local.base_url", group="Models", label="Local model address", kind="text"
    ),
    SettingField(path="models.local.model", group="Models", label="Local model name", kind="text"),
    SettingField(
        path="models.local.timeout_seconds",
        group="Models",
        label="Local model timeout (seconds)",
        kind="number",
        minimum=1,
        step=1,
    ),
    SettingField(
        path="models.nim.model", group="Models", label="NVIDIA NIM model name", kind="text"
    ),
    SettingField(
        path="models.nim.timeout_seconds",
        group="Models",
        label="NIM timeout (seconds)",
        kind="number",
        minimum=1,
        step=1,
    ),
    SettingField(
        path="selection.min_relevance_score",
        group="Choosing papers",
        label="Lowest relevance score to keep",
        kind="number",
        minimum=0,
        maximum=1,
        step=0.05,
        help="Papers the screener scores below this are dropped.",
    ),
    SettingField(
        path="selection.quality_weight",
        group="Choosing papers",
        label="Weight of venue, recency and citations",
        kind="number",
        minimum=0,
        maximum=1,
        step=0.05,
        help="0 orders kept papers by relevance alone.",
    ),
    SettingField(
        path="selection.recency_window_days",
        group="Choosing papers",
        label="Recency window (days)",
        kind="number",
        minimum=1,
        step=1,
    ),
    SettingField(
        path="selection.preferred_venues",
        group="Choosing papers",
        label="Preferred venues",
        kind="list",
        help="Comma-separated, e.g. CVPR, NeurIPS.",
    ),
    SettingField(
        path="concurrency.downloads",
        group="Speed and retries",
        label="Downloads at once",
        kind="number",
        minimum=1,
        step=1,
    ),
    SettingField(
        path="concurrency.analysis",
        group="Speed and retries",
        label="Model calls at once",
        kind="number",
        minimum=1,
        step=1,
    ),
    SettingField(
        path="retries.academic_apis",
        group="Speed and retries",
        label="Retries for a search source",
        kind="number",
        minimum=0,
        step=1,
    ),
    SettingField(
        path="retries.nim",
        group="Speed and retries",
        label="NIM retries before the local model",
        kind="number",
        minimum=0,
        step=1,
    ),
    SettingField(
        path="retries.local_model",
        group="Speed and retries",
        label="Retries for a brief local-model failure",
        kind="number",
        minimum=0,
        step=1,
    ),
    SettingField(
        path="retries.pdf_download",
        group="Speed and retries",
        label="Retries for a PDF download",
        kind="number",
        minimum=0,
        step=1,
    ),
)
_BY_PATH = {field.path: field for field in FIELDS}
_SECRETS = (
    ("NVIDIA NIM API key", "models.nim.api_key"),
    ("Semantic Scholar API key", "sources.semantic_scholar_api_key"),
    ("OpenAlex contact email", "sources.openalex_mailto"),
)


class SettingsProblem(ValueError):
    """A submitted value the settings model rejects, worded for the page."""


def env_name(path: str) -> str:
    return "RESEARCH_AGENT_" + "__".join(path.split(".")).upper()


def page(
    effective: ApplicationSettings,
    settings_file: Path | None,
    overrides: dict[str, Any],
    dotenv: Path = Path(".env"),
) -> dict[str, object]:
    """Every listed field with its value now, and whether the environment or the desk set it."""
    from_environment = _environment_names(dotenv)
    fields = []
    for field in FIELDS:
        name = env_name(field.path)
        fields.append(
            {
                **field.model_dump(),
                "value": _get(effective.model_dump(mode="json"), field.path),
                "changed": _get(overrides, field.path) is not None,
                "environment": name if name in from_environment else None,
            }
        )
    return {
        "editable": settings_file is not None,
        "fields": fields,
        "dataDirectory": str(effective.data_directory),
        "settingsFile": str(settings_file) if settings_file else None,
        "secrets": [
            {"label": label, "set": bool(_get(effective.model_dump(), path)), "env": env_name(path)}
            for label, path in _SECRETS
        ],
    }


def overrides_for(
    values: dict[str, object], settings_file: Path, dotenv: Path = Path(".env")
) -> dict[str, Any]:
    """The desk changes that would give these values: only fields that differ from the file.

    A field the environment sets is skipped, since the environment would win anyway. Raises
    SettingsProblem when the result does not validate, naming the field.
    """
    unknown = sorted(set(values) - set(_BY_PATH))
    if unknown:
        raise SettingsProblem(f"Unknown setting: {unknown[0]}")
    file_values = _load_yaml_mapping(settings_file)
    file_settings = ApplicationSettings.model_validate(file_values).model_dump(mode="json")
    locked = _environment_names(dotenv)
    changes: dict[str, Any] = {}
    for path, value in values.items():
        if env_name(path) not in locked and value != _get(file_settings, path):
            changes = merged(changes, _nested(path, value))
    try:
        ApplicationSettings.model_validate(merged(file_values, changes))
    except ValidationError as error:
        problem = error.errors()[0]
        path = ".".join(str(part) for part in problem["loc"])
        label = _BY_PATH[path].label if path in _BY_PATH else path
        raise SettingsProblem(f"{label}: {problem['msg']}") from error
    return changes


def _environment_names(dotenv: Path) -> set[str]:
    names = {name.upper() for name in os.environ if name.upper().startswith("RESEARCH_AGENT_")}
    if dotenv.is_file():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            key = line.strip().removeprefix("export ").split("=", 1)[0].strip()
            if "=" in line and not line.lstrip().startswith("#"):
                names.add(key.upper())
    return names


def _get(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _nested(path: str, value: object) -> dict[str, Any]:
    result: Any = value
    for part in reversed(path.split(".")):
        result = {part: result}
    return dict(result)

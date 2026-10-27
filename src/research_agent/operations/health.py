"""Check that a run has what it needs, before a user finds out halfway through one.

Each check says what it found and, when something is wrong, the one thing to do about it. Nothing
here changes state beyond a probe file in the data directory.
"""

import shutil
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

import httpx
from pydantic import Field

from research_agent.config import ApplicationSettings, DiscoverySettings, StrictModel
from research_agent.discovery.aggregator import build_sources
from research_agent.discovery.http import SourceRequestError
from research_agent.models.base import ModelMessage, ModelProviderError
from research_agent.models.chat import (
    ChatCompletionsProvider,
    LocalModelProvider,
    NvidiaNIMProvider,
)

CheckStatus = Literal["ok", "warn", "fail"]

MIN_FREE_BYTES = 2 * 1024**3
"""A run downloads up to fifty PDFs and Docling's models; below this, warn."""

_PROBE = [ModelMessage(role="user", content="Reply with the single word: ready.")]


class HealthCheck(StrictModel):
    """One thing a run depends on, how it looks now, and what to do if it is wrong."""

    name: str = Field(min_length=1)
    status: CheckStatus
    detail: str
    fix: str = ""


async def run_checks(settings: ApplicationSettings, client: httpx.AsyncClient) -> list[HealthCheck]:
    """Every check, in the order a run meets them. `client` should carry a short timeout."""
    checks = [_data_directory(settings)]
    checks.append(await _model("Local model", LocalModelProvider(client, settings.models.local)))
    nim = NvidiaNIMProvider(client, settings.models.nim)
    if nim.configured:
        checks.append(await _model("NVIDIA NIM", nim))
    else:
        checks.append(
            HealthCheck(
                name="NVIDIA NIM",
                status="warn",
                detail="No API key, so deep analysis and synthesis run on the local model.",
                fix="Optional: set RESEARCH_AGENT_MODELS__NIM__API_KEY in .env for stronger reads.",
            )
        )
    checks.extend(await _sources(settings, client))
    return checks


def _data_directory(settings: ApplicationSettings) -> HealthCheck:
    directory = settings.data_directory
    name = "Library folder"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / f".health-{uuid.uuid4().hex}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        free = shutil.disk_usage(directory).free
    except OSError as error:
        return HealthCheck(
            name=name,
            status="fail",
            detail=f"{directory} cannot be written: {error.strerror or error}.",
            fix="Point data_directory in config/settings.yaml at a folder you can write to.",
        )
    gigabytes = free / 1024**3
    if free < MIN_FREE_BYTES:
        return HealthCheck(
            name=name,
            status="warn",
            detail=f"{directory} has {gigabytes:.1f} GB free.",
            fix="Free up space: a run stores PDFs, parsed text and Docling's models.",
        )
    return HealthCheck(name=name, status="ok", detail=f"{directory} ({gigabytes:.0f} GB free)")


async def _model(name: str, provider: ChatCompletionsProvider) -> HealthCheck:
    endpoint = f"{provider.model} at {provider.base_url}"
    try:
        result = await provider.generate("health_check", _PROBE, capability="cheap_text")
    except ModelProviderError as error:
        return HealthCheck(
            name=name,
            status="fail",
            detail=f"{endpoint} did not answer: {error}",
            fix=(
                f"Start the model server at {provider.base_url} (see config/settings.yaml)."
                if name == "Local model"
                else "Check RESEARCH_AGENT_MODELS__NIM__API_KEY and the NIM model name."
            ),
        )
    return HealthCheck(
        name=name, status="ok", detail=f"{endpoint} answered in {result.latency_ms} ms"
    )


async def _sources(settings: ApplicationSettings, client: httpx.AsyncClient) -> list[HealthCheck]:
    """One small search per source, without retries: the check must stay quick."""
    quick = settings.model_copy(
        update={"retries": settings.retries.model_copy(update={"academic_apis": 0})}
    )
    end = datetime.now(UTC).date()
    checks: list[HealthCheck] = []
    for source in build_sources(client, quick, DiscoverySettings()):
        label = {"openalex": "OpenAlex", "semantic_scholar": "Semantic Scholar"}.get(
            source.name, "arXiv"
        )
        try:
            found = await source.search("machine learning", end - timedelta(days=30), end, 1)
        except Exception as error:  # any source failure is a finding here, never a crash
            limited = isinstance(error, SourceRequestError) and error.category == "RATE_LIMIT"
            checks.append(
                HealthCheck(
                    name=label,
                    status="warn" if limited else "fail",
                    detail=f"{'Rate-limited right now' if limited else 'Unreachable'}: {error}",
                    fix=_source_fix(source.name, limited),
                )
            )
            continue
        detail = "answered" if found else "answered, but returned nothing for a test search"
        checks.append(HealthCheck(name=label, status="ok", detail=detail.capitalize() + "."))
    return checks


def _source_fix(name: str, limited: bool) -> str:
    if not limited:
        return "Check this machine's internet connection; runs continue without this source."
    if name == "semantic_scholar":
        return "Set RESEARCH_AGENT_SOURCES__SEMANTIC_SCHOLAR_API_KEY in .env for a higher limit."
    if name == "openalex":
        return "Set RESEARCH_AGENT_SOURCES__OPENALEX_MAILTO in .env to join OpenAlex's polite pool."
    return "Runs retry and continue without this source; try again in a few minutes."

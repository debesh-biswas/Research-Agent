"""The health checks report each dependency and what to do about it, without crashing."""

import asyncio
from pathlib import Path

import httpx

from research_agent.config import ApplicationSettings
from research_agent.operations.health import HealthCheck, run_checks

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "discovery"


def _network(model_up: bool) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host == "localhost":
            if not model_up:
                raise httpx.ConnectError("connection refused", request=request)
            body = {"choices": [{"message": {"role": "assistant", "content": "ready"}}]}
            return httpx.Response(200, json=body)
        if host == "api.openalex.org":
            return httpx.Response(200, text=(FIXTURES / "openalex_page.json").read_text())
        if host == "api.semanticscholar.org":
            return httpx.Response(429, headers={"Retry-After": "0"})
        if "arxiv" in host:
            return httpx.Response(200, text=(FIXTURES / "arxiv_page.xml").read_text())
        return httpx.Response(404)

    return httpx.MockTransport(handle)


def _check(settings: ApplicationSettings, model_up: bool = True) -> dict[str, HealthCheck]:
    async def run() -> list[HealthCheck]:
        async with httpx.AsyncClient(transport=_network(model_up)) as client:
            return await run_checks(settings, client)

    return {check.name: check for check in asyncio.run(run())}


def test_a_healthy_setup_reports_ok_with_warnings_for_optional_parts(tmp_path: Path) -> None:
    checks = _check(ApplicationSettings(data_directory=tmp_path / "data"))

    assert {name: check.status for name, check in checks.items()} == {
        "Library folder": "ok",
        "Local model": "ok",
        "NVIDIA NIM": "warn",
        "OpenAlex": "ok",
        "Semantic Scholar": "warn",
        "arXiv": "ok",
    }
    assert "SEMANTIC_SCHOLAR_API_KEY" in checks["Semantic Scholar"].fix
    assert list((tmp_path / "data").iterdir()) == [], "the write probe is removed"


def test_problems_fail_with_a_fix_instead_of_raising(tmp_path: Path) -> None:
    blocker = tmp_path / "a-file"
    blocker.write_text("not a folder", encoding="utf-8")

    checks = _check(ApplicationSettings(data_directory=blocker / "data"), model_up=False)

    assert checks["Library folder"].status == "fail"
    assert checks["Local model"].status == "fail"
    assert "Start the model server at http://localhost" in checks["Local model"].fix

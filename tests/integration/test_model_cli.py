from pathlib import Path

import httpx
import pytest
import yaml
from typer.testing import CliRunner, Result

from research_agent import cli
from research_agent.cli import app

runner = CliRunner()
API_KEY = "nvapi-secret-value"
_COMPLETION = {
    "choices": [{"message": {"role": "assistant", "content": "ready."}}],
    "usage": {"prompt_tokens": 9, "completion_tokens": 2},
}


@pytest.fixture
def settings_path(tmp_path: Path) -> Path:
    path = tmp_path / "settings.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "data_directory": str(tmp_path / "data"),
                "strong_model_provider": "nvidia_nim",
                "models": {"local": {"model": "qwen3:8b"}},
            }
        ),
        encoding="utf-8",
    )
    return path


def run_check(
    monkeypatch: pytest.MonkeyPatch,
    settings_path: Path,
    handler: object,
    *extra: str,
) -> Result:
    monkeypatch.setattr(
        cli,
        "_http_client",
        lambda timeout: httpx.AsyncClient(transport=httpx.MockTransport(handler)),  # type: ignore[arg-type]
    )
    return runner.invoke(app, ["model", "check", "--settings", str(settings_path), *extra])


def test_model_check_reports_the_answering_provider(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path
) -> None:
    monkeypatch.setenv("RESEARCH_AGENT_MODELS__NIM__API_KEY", API_KEY)

    result = run_check(
        monkeypatch, settings_path, lambda request: httpx.Response(200, json=_COMPLETION)
    )

    assert result.exit_code == 0, result.output
    assert "nvidia_nim" in result.output
    assert "api key configured" in result.output
    assert "ready." in result.output
    assert API_KEY not in result.output


def test_model_check_falls_back_to_local_when_the_strong_provider_fails(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path
) -> None:
    monkeypatch.setenv("RESEARCH_AGENT_MODELS__NIM__API_KEY", API_KEY)

    def handler(request: httpx.Request) -> httpx.Response:
        if "nvidia" in str(request.url):
            return httpx.Response(500)
        return httpx.Response(200, json=_COMPLETION)

    result = run_check(monkeypatch, settings_path, handler, "--capability", "synthesis")

    assert result.exit_code == 0, result.output
    assert "fell back to local" in result.output


def test_model_check_exits_non_zero_when_inference_fails(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path
) -> None:
    result = run_check(monkeypatch, settings_path, lambda request: httpx.Response(503))

    assert result.exit_code == 1
    assert "Inference failed" in result.output


def test_model_check_rejects_an_unknown_capability(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path
) -> None:
    result = run_check(
        monkeypatch,
        settings_path,
        lambda request: httpx.Response(200, json=_COMPLETION),
        "--capability",
        "telepathy",
    )

    assert result.exit_code == 1
    assert "Unknown capability" in result.output

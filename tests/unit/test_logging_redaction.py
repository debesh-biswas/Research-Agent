"""The log-redaction audit: a credential must never reach a log line."""

import json
import logging
from io import StringIO

import pytest

from research_agent.observability.logging import (
    REDACTED,
    JsonFormatter,
    SecretRedactingFilter,
    configure_logging,
    configured_secrets,
    redact,
)

KEY = "nvapi-3f9Qz7LmT2xWv8pR4sKd6BhN1cYgE5jA0uZoI7"


def test_a_vendor_key_shape_is_redacted() -> None:
    assert KEY not in redact(f"provider rejected the key {KEY}")
    assert REDACTED in redact(f"provider rejected the key {KEY}")


def test_a_bearer_header_keeps_its_label_and_loses_its_value() -> None:
    line = redact("Authorization: Bearer abcdef1234567890")

    assert "Bearer " in line and "abcdef1234567890" not in line


def test_a_key_in_a_query_string_is_redacted() -> None:
    line = redact("GET https://example.org/v1/works?api_key=abcdef1234567890&page=2")

    assert "abcdef1234567890" not in line
    assert "api_key=[redacted]" in line
    assert "page=2" in line, "only the credential is removed"


def test_a_configured_environment_secret_is_redacted_even_in_an_unknown_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESEARCH_AGENT_MODELS__NIM__API_KEY", "totally-opaque-value-1234")

    assert "totally-opaque-value-1234" not in redact("sent totally-opaque-value-1234 upstream")
    assert configured_secrets() == ["totally-opaque-value-1234"]


def test_a_short_environment_value_is_not_treated_as_a_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESEARCH_AGENT_MODELS__NIM__API_KEY", "none")

    assert configured_secrets() == [], "a placeholder is not a credential"


def test_a_non_secret_environment_variable_is_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEARCH_AGENT_MODELS__NIM__MODEL", "openai/gpt-oss-20b")

    assert configured_secrets() == []
    assert "openai/gpt-oss-20b" in redact("using openai/gpt-oss-20b")


def test_the_filter_redacts_the_message_and_the_context(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEARCH_AGENT_MODELS__NIM__API_KEY", KEY)
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(SecretRedactingFilter())
    logger = logging.getLogger("redaction-test")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    logger.warning("call failed for %s", f"https://example.org?api_key={KEY}", extra={"model": KEY})

    payload = json.loads(stream.getvalue())
    assert KEY not in stream.getvalue()
    assert payload["model"] == REDACTED


def test_an_exception_traceback_is_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEARCH_AGENT_MODELS__NIM__API_KEY", KEY)
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(SecretRedactingFilter())
    logger = logging.getLogger("redaction-exception-test")
    logger.handlers = [handler]
    logger.propagate = False

    try:
        raise RuntimeError(f"request to https://example.org?api_key={KEY} failed")
    except RuntimeError:
        logger.exception("inference failed")

    assert KEY not in stream.getvalue()


def test_configure_logging_installs_the_filter() -> None:
    configure_logging("INFO")
    root = logging.getLogger()

    try:
        assert root.handlers
        assert any(
            isinstance(log_filter, SecretRedactingFilter)
            for handler in root.handlers
            for log_filter in handler.filters
        )
    finally:
        root.handlers.clear()

"""Standard-library JSON logging for local and portable execution.

Log records pass through a redaction filter before formatting, because an exception string or an
error message can carry a URL with a key in it and a log file is the easiest place to leak one.
"""

import json
import logging
import os
import re
from datetime import UTC, datetime
from typing import Final

CONTEXT_FIELDS: Final = (
    "run_id",
    "topic_id",
    "node_name",
    "paper_id",
    "provider",
    "model",
    "classifier",
    "duration_ms",
    "status",
    "error_type",
)


REDACTED: Final = "[redacted]"
_THIRD_PARTY_LOGGERS: Final = ("httpx", "httpcore", "urllib3")
_ENV_PREFIX: Final = "RESEARCH_AGENT_"
_SECRET_ENV_MARKERS: Final = ("API_KEY", "TOKEN", "SECRET", "PASSWORD")
_MIN_SECRET_CHARS: Final = 8

# Vendor key shapes, and the two places a credential normally travels: a bearer header and a query
# parameter. Value-based redaction below covers keys this does not know about.
_PATTERNS: Final = (
    re.compile(r"\bnvapi-[A-Za-z0-9_\-]{8,}", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{8,}"),
    re.compile(r"(?i)([?&](?:api_?key|access_?token|key)=)[^&\s\"']+"),
)


def configured_secrets() -> list[str]:
    """Secret values present in this process's environment, longest first.

    Read at log time rather than cached, so a value set after start-up is still redacted.
    """
    values = [
        value
        for name, value in os.environ.items()
        if name.startswith(_ENV_PREFIX)
        and any(marker in name.upper() for marker in _SECRET_ENV_MARKERS)
        and len(value) >= _MIN_SECRET_CHARS
    ]
    return sorted(set(values), key=len, reverse=True)


def redact(text: str) -> str:
    """Remove anything that looks like a credential from one line of log text."""
    for secret in configured_secrets():
        text = text.replace(secret, REDACTED)
    for pattern in _PATTERNS:
        text = pattern.sub(
            lambda match: (match.group(1) + REDACTED) if match.groups() else REDACTED, text
        )
    return text


class SecretRedactingFilter(logging.Filter):
    """Redact credentials from a record's message, arguments and context fields."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(str(record.msg))
        if record.args:
            record.args = tuple(
                redact(argument) if isinstance(argument, str) else argument
                for argument in (record.args if isinstance(record.args, tuple) else (record.args,))
            )
        for field in CONTEXT_FIELDS:
            value = getattr(record, field, None)
            if isinstance(value, str):
                setattr(record, field, redact(value))
        return True


class JsonFormatter(logging.Formatter):
    """Serialize log records as single-line JSON with stable context fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in CONTEXT_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, separators=(",", ":"), default=str)


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger to emit redacted structured JSON to standard error."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(SecretRedactingFilter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level.upper())
    for noisy in _THIRD_PARTY_LOGGERS:
        # Their per-request INFO lines are not this application's log stream, and one of them prints
        # full request URLs, which is exactly what should not be routine output.
        logging.getLogger(noisy).setLevel(logging.WARNING)

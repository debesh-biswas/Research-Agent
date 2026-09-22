"""Standard-library JSON logging for local and portable execution."""

import json
import logging
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
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"), default=str)


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger to emit structured JSON to standard error."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level.upper())

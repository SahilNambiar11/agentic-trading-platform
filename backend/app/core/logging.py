import json
import logging
from datetime import UTC, datetime
from typing import Literal

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
OPERATIONAL_FIELDS = (
    "event",
    "component",
    "job_id",
    "queue",
    "previous_status",
    "new_status",
    "reconciliation_action",
    "attempt",
    "max_attempts",
    "duration_ms",
    "dependency",
    "outcome",
    "reconciliation_scanned",
    "reconciliation_recovered",
    "reconciliation_failed",
)


class JsonFormatter(logging.Formatter):
    """Format log records as one-line JSON for containers and log collectors."""

    def format(self, record: logging.LogRecord) -> str:
        """Convert a Python log record into a structured JSON string."""
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info is not None:
            payload["exception"] = self.formatException(record.exc_info)
        for field_name in OPERATIONAL_FIELDS:
            if hasattr(record, field_name):
                payload[field_name] = getattr(record, field_name)
        return json.dumps(payload, ensure_ascii=True)


def configure_logging(level: LogLevel) -> None:
    """Replace default logging with the app's JSON console logger."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

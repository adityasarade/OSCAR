"""Structured logging setup for OSCAR."""

from datetime import datetime, timezone
import json
import logging
import os


class JsonFormatter(logging.Formatter):
    """Format log records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(
                record.created, timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        return json.dumps(payload)


def configure_logging(
    level: str | None = None, default_level: str = "INFO"
) -> None:
    """Configure process logging with OSCAR's JSON formatter.

    Precedence: explicit `level` arg > OSCAR_LOG_LEVEL env var > default_level.
    """
    if level is not None:
        level_name = level.upper()
    else:
        level_name = os.getenv("OSCAR_LOG_LEVEL", default_level).upper()
    resolved = getattr(logging, level_name, logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(resolved)

    handler = next(
        (
            existing
            for existing in root_logger.handlers
            if getattr(existing, "_oscar_json_handler", False)
        ),
        None,
    )
    if handler is None:
        handler = logging.StreamHandler()
        handler._oscar_json_handler = True
        root_logger.addHandler(handler)

    handler.setLevel(resolved)
    handler.setFormatter(JsonFormatter())

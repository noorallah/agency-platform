"""Logging setup for application processes."""

import logging.config
from pathlib import Path
from typing import Any

from app.core.config.settings import Settings
from app.core.context import get_request_context


class RequestContextFilter(logging.Filter):
    """Attach request-scoped identifiers to records emitted during a request."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Add a safe request identifier for structured log formatting."""
        context = get_request_context()
        record.request_id = context.request_id if context is not None else "-"
        return True


def configure_logging(settings: Settings) -> None:
    """Configure process logging from application settings.

    Args:
        settings: Typed application configuration.

    """
    if settings.log_file_enabled:
        settings.log_directory.mkdir(parents=True, exist_ok=True)
    logging.config.dictConfig(_build_logging_config(settings))


def _build_logging_config(settings: Settings) -> dict[str, Any]:
    """Build the standard-library logging configuration dictionary.

    Args:
        settings: Typed application configuration.

    Returns:
        A logging configuration usable by ``logging.config.dictConfig``.

    """
    log_file: Path = settings.log_directory / settings.log_file_name

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": (
                    "%(asctime)s %(levelname)s [%(name)s] "
                    "request_id=%(request_id)s %(message)s"
                )
            }
        },
        "filters": {"request_context": {"()": RequestContextFilter}},
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "standard",
                "filters": ["request_context"],
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(log_file),
                "maxBytes": settings.log_max_bytes,
                "backupCount": settings.log_backup_count,
                "encoding": "utf-8",
                "formatter": "standard",
                "filters": ["request_context"],
            },
        },
        "root": {
            "handlers": ["console"] + (["file"] if settings.log_file_enabled else []),
            "level": settings.log_level.upper(),
        },
    }

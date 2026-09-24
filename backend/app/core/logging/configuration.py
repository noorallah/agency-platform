"""Logging setup for application processes."""

import logging.config
from typing import Any

from app.core.config.settings import Settings
from app.core.context import get_request_context
from app.core.logging.retention import (
    ERROR_LOG_PREFIX,
    SERVER_LOG_FOLDER,
    SERVER_LOG_PREFIX,
)


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
        (settings.log_directory / SERVER_LOG_FOLDER).mkdir(parents=True, exist_ok=True)
    logging.config.dictConfig(_build_logging_config(settings))


def _build_logging_config(settings: Settings) -> dict[str, Any]:
    """Build the standard-library logging configuration dictionary.

    Two files under ``<AGENCY_LOG_DIRECTORY>/server``: ``server-<day>.log``
    with everything at the configured level, and ``errors-<day>.log`` with
    WARNING and above, each rolled at midnight and at ``AGENCY_LOG_MAX_BYTES``
    (see ``rotation.py``). Retention is ``retention.py``'s job, not the
    handler's.

    Args:
        settings: Typed application configuration.

    Returns:
        A logging configuration usable by ``logging.config.dictConfig``.

    """
    folder = str(settings.log_directory / SERVER_LOG_FOLDER)

    def daily_file(prefix: str, level: str) -> dict[str, Any]:
        """Return the handler entry for one day-named log file."""
        return {
            "()": "app.core.logging.rotation.DailyRotatingFileHandler",
            "directory": folder,
            "prefix": prefix,
            "max_bytes": settings.log_max_bytes,
            "level": level,
            "formatter": "standard",
            "filters": ["request_context"],
        }

    handlers: dict[str, Any] = {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "filters": ["request_context"],
        }
    }
    if settings.log_file_enabled:
        handlers["file"] = daily_file(SERVER_LOG_PREFIX, "NOTSET")
        handlers["errors"] = daily_file(ERROR_LOG_PREFIX, "WARNING")

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
        "handlers": handlers,
        "root": {
            "handlers": ["console"]
            + (["file", "errors"] if settings.log_file_enabled else []),
            "level": settings.log_level.upper(),
        },
    }

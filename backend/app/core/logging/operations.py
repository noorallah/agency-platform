"""Recording business-critical operations in the application log.

An audit row answers "who changed this record". It does not answer "did the
posting run, how long did it take, and what did it decide" -- and it is written
inside the transaction, so a failure rolls the evidence back with the work. The
operation log is the other half: it is written whichever way the operation ends,
so a failed run leaves a trace rather than silence.

Use it for the operations whose outcome someone will be asked about later:
posting, approving, provisioning, imports, retention runs, tax evaluation.
"""

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager

logger = logging.getLogger("app.operations")

# Never write these into a log line, whatever a caller passes.
_REDACTED_KEYS = frozenset(
    {
        "password",
        "new_password",
        "current_password",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "api_key",
        "authorization",
    }
)


def _format_details(details: dict[str, object]) -> str:
    """Render details as stable ``key=value`` pairs, with secrets removed."""
    parts: list[str] = []
    for key in sorted(details):
        value = "<redacted>" if key.lower() in _REDACTED_KEYS else details[key]
        parts.append(f"{key}={value}")
    return " ".join(parts)


def log_operation(
    name: str,
    *,
    outcome: str = "succeeded",
    level: int = logging.INFO,
    **details: object,
) -> None:
    """Record one business-critical operation and how it ended.

    Args:
        name: Dotted operation name, for example ``sales_invoice.approve``.
        outcome: ``succeeded``, ``failed``, ``skipped`` -- whatever happened.
        level: Severity; failures should raise this to ``logging.ERROR``.
        **details: Identifiers worth having later (document, firm, counts).
            Never pass a credential; recognised secret keys are redacted anyway.

    """
    _emit(name, outcome=outcome, level=level, details=details)


def _emit(
    name: str,
    *,
    outcome: str,
    level: int,
    details: dict[str, object],
) -> None:
    """Write the line.

    Separate from :func:`log_operation` so the context manager can forward a
    collected dict without splatting it back through keyword parameters, where
    a detail named ``level`` or ``outcome`` would hijack the call.
    """
    suffix = _format_details(details)
    logger.log(
        level,
        "operation=%s outcome=%s%s",
        name,
        outcome,
        f" {suffix}" if suffix else "",
    )


@contextmanager
def operation(name: str, **details: object) -> Iterator[dict[str, object]]:
    """Record an operation's start, duration and outcome around a block.

    Yields a mutable dict so the body can add what it learned -- a document
    number, a row count -- before the closing line is written.

    A failure is logged and re-raised: this observes an operation, it does not
    change whether it succeeds.

        with operation("purchase.receive", firm=firm.code) as record:
            record["document"] = document.number

    """
    started = time.monotonic()
    collected: dict[str, object] = dict(details)
    _emit(name, outcome="started", level=logging.INFO, details=collected)
    try:
        yield collected
    except Exception as error:
        _emit(
            name,
            outcome="failed",
            level=logging.ERROR,
            details={
                **collected,
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
                "error": type(error).__name__,
            },
        )
        raise
    _emit(
        name,
        outcome="succeeded",
        level=logging.INFO,
        details={
            **collected,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
        },
    )

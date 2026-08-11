"""Operation logging tests.

An audit row answers "who changed this record", and it is written inside the
transaction -- so a failed posting rolls its own evidence back. The operation log
is the other half: it is written whichever way the operation ends, which is the
only reason a failure leaves a trace at all.
"""

import logging

import pytest

from app.core.logging.operations import log_operation, operation


def test_operation_records_name_and_outcome(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A single call names the operation and how it ended."""
    with caplog.at_level(logging.INFO, logger="app.operations"):
        log_operation("sales_invoice.approve", document="INV-001", firm="WHOLE01")

    assert (
        "operation=sales_invoice.approve outcome=succeeded "
        "document=INV-001 firm=WHOLE01" in caplog.text
    )


def test_details_are_ordered_so_lines_can_be_compared(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Keys are sorted; two runs of the same operation read the same."""
    with caplog.at_level(logging.INFO, logger="app.operations"):
        log_operation("stock.post", zebra=1, alpha=2)

    assert "alpha=2 zebra=1" in caplog.text


def test_credentials_never_reach_the_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A caller that passes a secret does not get it written to disk."""
    with caplog.at_level(logging.INFO, logger="app.operations"):
        log_operation(
            "user.reset_password",
            user="alice",
            password="Hunter2!",
            refresh_token="rt-secret",
        )

    assert "Hunter2!" not in caplog.text
    assert "rt-secret" not in caplog.text
    assert "password=<redacted>" in caplog.text
    assert "user=alice" in caplog.text


def test_context_manager_reports_start_duration_and_success(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The block brackets the work and records what the body learned."""
    with (
        caplog.at_level(logging.INFO, logger="app.operations"),
        operation("purchase.receive", firm="WHOLE01") as record,
    ):
        record["document"] = "GRN-004"

    assert "operation=purchase.receive outcome=started firm=WHOLE01" in caplog.text
    assert "outcome=succeeded" in caplog.text
    assert "document=GRN-004" in caplog.text
    assert "duration_ms=" in caplog.text


def test_a_failure_is_logged_at_error_and_re_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Observing an operation must not change whether it succeeds."""
    with (
        caplog.at_level(logging.INFO, logger="app.operations"),
        pytest.raises(ValueError),
        operation("finance.post") as record,
    ):
        record["period"] = "2026-08"
        raise ValueError("period is closed")

    assert "outcome=failed" in caplog.text
    assert "error=ValueError" in caplog.text
    # What the body had already established survives into the failure line.
    assert "period=2026-08" in caplog.text
    assert any(
        record.levelno == logging.ERROR for record in caplog.records
    ), "a failed operation must not be logged at INFO"

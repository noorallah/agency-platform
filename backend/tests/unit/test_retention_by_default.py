"""Retention runs every night unless the platform switches it off (PLT-6).

The nightly task calls ``purge-retention --yes --scheduled`` after its
backup; ``AGENCY_RETENTION_AUTO_PURGE=false`` makes that call a no-op, and a
hand-run ``purge-retention`` is never skipped.
"""

from pathlib import Path

import pytest

from app import cli
from app.core.config.settings import Settings

_SETUP = Path(__file__).resolve().parents[3] / "packaging" / "server_setup.ps1"


def test_retention_is_on_unless_switched_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """The default prunes; the setting turns it off."""
    monkeypatch.delenv("AGENCY_RETENTION_AUTO_PURGE", raising=False)
    assert Settings().retention_auto_purge is True
    monkeypatch.setenv("AGENCY_RETENTION_AUTO_PURGE", "false")
    assert Settings().retention_auto_purge is False


def test_a_switched_off_night_prunes_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The scheduled run returns before touching a store."""
    monkeypatch.setenv("AGENCY_RETENTION_AUTO_PURGE", "false")

    def refuse(**_: object) -> int:
        """Fail the test if a store would be pruned."""
        raise AssertionError("pruned while switched off")

    monkeypatch.setattr("app.core.tenancy.retention.purge_every_store", refuse)
    args = cli.build_parser().parse_args(["purge-retention", "--yes", "--scheduled"])
    assert args.handler(args) == 0
    assert "switched off" in capsys.readouterr().out


def test_the_nightly_task_prunes_after_its_backup() -> None:
    """server_setup.ps1 runs retention at the end of the daily backup."""
    text = _SETUP.read_text(encoding="utf-8")
    daily = text[text.index("function Invoke-DailyBackup") :]
    daily = daily[: daily.index("\nfunction ", 10)]
    assert "Invoke-Retention" in daily
    assert "'purge-retention', '--yes', '--scheduled'" in text

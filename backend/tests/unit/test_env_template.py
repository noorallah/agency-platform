"""`config/.env.example` is the installer's template, not only a developer's.

`install.ps1` copies it into every customer's `config/.env`, rewriting a handful
of keys and keeping every other live line as it stands. Two development lines
rode along that way until 2026-09-18: `AGENCY_APP_VERSION=0.1.0`, which beat the
real version in `settings.py`, and a `REMOTE_A` connection profile with the
password `CHANGE_ME`. The profile line began with a space, which reads as
commented to a person and as live to the dotenv parser.
"""

import re
from pathlib import Path

from dotenv import dotenv_values

_TEMPLATE = Path(__file__).resolve().parents[2] / "config" / ".env.example"


def test_the_template_does_not_set_the_version() -> None:
    """The version is the build's; a value in the template overrides it."""
    assert "AGENCY_APP_VERSION" not in dotenv_values(_TEMPLATE)


def test_the_template_names_no_other_database_server() -> None:
    """A second server is a firm's decision, so every example stays commented."""
    live = [
        key
        for key in dotenv_values(_TEMPLATE)
        if key == "AGENCY_TENANCY_CONNECTION_PROFILES"
        or re.fullmatch(r"AGENCY_DATABASE\d+_\w+", key)
    ]
    assert live == []


def test_no_setting_hides_behind_leading_whitespace() -> None:
    """An indented line looks commented and is not."""
    indented = [
        line
        for line in _TEMPLATE.read_text(encoding="utf-8").splitlines()
        if re.match(r"\s+[A-Z_]+=", line)
    ]
    assert indented == []

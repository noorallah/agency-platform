"""Every preference field the desktop sends is one the server accepts.

The desktop split appearance into palette, mode and contrast on 2026-08-10
and sent all three to ``PATCH /api/v1/me/preferences``. The server declared
two. ``ApiSchema`` forbids an unknown field, so **every** appearance save was
refused with 422 -- palette, mode and contrast alike, since they rode in one
request -- and the next sign-in handed the client the row's untouched defaults,
which it wrote over its own correct local copy. A theme chosen on Monday was
gone on Tuesday.

It survived a month of green suites because the two suites never meet: the
desktop's fake API accepts whatever it is given, and the backend's tests build
their own requests. This file reads what the desktop actually sends and asks
the schema whether it would take it -- the question neither suite asked.
"""

import re
from pathlib import Path

import pytest

from app.identity.schemas.api import UserPreferencesResponse, UserPreferencesUpdate

_DESKTOP = Path(__file__).resolve().parents[3] / "desktop" / "lib"
_SESSION = _DESKTOP / "core" / "auth" / "session_controller.dart"
_MODEL = _DESKTOP / "core" / "preferences" / "user_preferences.dart"


def _keys_sent() -> set[str]:
    """Return every key the desktop puts in a preferences update."""
    source = _SESSION.read_text(encoding="utf-8")
    keys: set[str] = set()
    for body in re.findall(
        r"updateUserPreferences\(\s*\{(.*?)\}\s*,?\s*\)", source, re.S
    ):
        keys.update(re.findall(r"'([a-z_]+)'\s*:", body))
    return keys


def _keys_read() -> set[str]:
    """Return every key the desktop reads off a preferences response."""
    source = _MODEL.read_text(encoding="utf-8")
    return (
        set(re.findall(r"json\['([a-z_]+)'\]", source))
        | set(re.findall(r"requiredString\('([a-z_]+)'\)", source))
        | set(re.findall(r"object\('([a-z_]+)'\)", source))
    )


@pytest.mark.skipif(not _SESSION.exists(), reason="desktop tree not present")
def test_every_key_the_desktop_sends_is_a_field_the_server_accepts() -> None:
    """The contract, checked from the client's side of it."""
    sent = _keys_sent()
    assert sent, "no preference update found in the desktop -- regex drifted?"
    accepted = set(UserPreferencesUpdate.model_fields)

    unknown = sorted(sent - accepted)
    assert not unknown, (
        "the desktop sends preference fields the server refuses, and because "
        "the schema forbids unknown fields the whole request fails with it:\n  "
        + "\n  ".join(unknown)
        + "\n\nDeclare each on `UserPreferencesUpdate` (and the model, with a "
        "migration), or stop sending it."
    )


@pytest.mark.skipif(not _MODEL.exists(), reason="desktop tree not present")
def test_every_key_the_desktop_reads_is_a_field_the_server_returns() -> None:
    """The other direction: a key read off the response must be one it carries.

    A missing key is not an error on the client -- it falls back or reads null
    -- which is exactly how a preference stops round-tripping without anything
    saying so.
    """
    read = _keys_read()
    assert read, "no preference reads found in the desktop -- regex drifted?"
    returned = set(UserPreferencesResponse.model_fields)

    missing = sorted(read - returned)
    assert not missing, (
        "the desktop reads preference fields the server never returns, so they "
        "silently read as absent:\n  " + "\n  ".join(missing)
    )

"""Fixtures every unit test gets.

The unit suite has no database server: each test builds its own SQLite store.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from app.document_framework.services import print_support


class _NoFirms:
    """A platform store holding no firms, for the printed seller block."""

    def get(self, *_: object) -> None:
        """Find nothing, as a platform store without the test's firm would."""
        return None


@contextmanager
def _no_platform_store() -> Iterator[_NoFirms]:
    """Stand in for ``platform_reader`` on the print path."""
    yield _NoFirms()


@pytest.fixture(autouse=True)
def _prints_without_a_platform_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let ``firm_party`` name no seller instead of dialling PostgreSQL.

    ``firm_party`` reads ``firms`` through ``platform_reader``, a real
    connection to the configured server. On a developer's machine that
    quietly succeeds against a local PostgreSQL and finds no such firm; in CI
    the unit job has no server, and every print test that did not stub the
    seller itself failed with ``Connection refused``. Tests about the seller
    block still patch ``firm_party`` or ``_seller`` themselves, which wins.
    """
    monkeypatch.setattr(print_support, "platform_reader", _no_platform_store)

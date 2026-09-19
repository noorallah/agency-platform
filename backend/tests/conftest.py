"""Shared pytest configuration for the backend test suite.

Unit tests build their own SQLite engines and call ``Base.metadata.create_all``.
That only emits the tables whose model modules have already been imported, so a
test file that touches one module used to fail when run on its own while
passing inside the full suite, purely because a sibling test had imported the
missing models first.

Importing every model module here removes that ordering dependency: by the time
any test runs, ``Base.metadata`` describes the whole schema. This list must stay
in step with the equivalent imports in ``alembic/env.py``.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapper

# One list of model modules, shared with alembic and the seed scripts.
# A module missing from it is invisible to autogenerate, to
# `create_all` and to the sample-data reset alike.
import app.core.database.all_models  # noqa: F401
from app.document_framework.models import DocumentNumberingRule

TYPED_DOCUMENT_NUMBERS = "typed_document_numbers"


def pytest_configure(config: pytest.Config) -> None:
    """Register the markers this suite defines."""
    config.addinivalue_line(
        "markers",
        f"{TYPED_DOCUMENT_NUMBERS}: the file's fixtures type their document "
        "numbers, so every numbering series its tests create allows typed "
        "numbers. A series refuses them by default (D-CFG-2).",
    )


@pytest.fixture(autouse=True)
def _typed_document_numbers(request: pytest.FixtureRequest) -> Iterator[None]:
    """Let a marked file's series accept the numbers its fixtures type.

    A numbering series takes a typed number only when ``manual_allowed`` is on,
    and the series each module bootstraps on its first document has it off --
    the default a firm gets (D-CFG-2). Most of this suite types numbers into
    its fixtures so the assertions read ``PO-GRN1`` rather than whatever the
    counter issued; those files say so with the marker, and only their series
    are created with typed numbers allowed. A test about numbering itself
    lives in an unmarked file, where the series is exactly as shipped.
    """
    if request.node.get_closest_marker(TYPED_DOCUMENT_NUMBERS) is None:
        yield
        return

    def allow(
        _mapper: Mapper[DocumentNumberingRule],
        _connection: Connection,
        target: DocumentNumberingRule,
    ) -> None:
        """Create the series with typed numbers allowed."""
        target.manual_allowed = True

    event.listen(DocumentNumberingRule, "before_insert", allow)
    try:
        yield
    finally:
        event.remove(DocumentNumberingRule, "before_insert", allow)

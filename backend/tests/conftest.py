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

# One list of model modules, shared with alembic and the seed scripts.
# A module missing from it is invisible to autogenerate, to
# `create_all` and to the sample-data reset alike.
import app.core.database.all_models  # noqa: F401

"""A database clock that advances within a transaction.

``func.now()`` is PostgreSQL's ``transaction_timestamp()``: every statement in a
transaction reads the same instant. That is the right default for ``created_at``
on a business record -- the six rows a purchase order writes were created
together and saying so is honest -- but it makes rows written in one request
**unorderable by time**, because they all carry the same value to the
microsecond.

A stock ledger is read as a chronology, so that matters there. Posting a
delivery note writes UNRESERVE and then DISPATCH; both got the same
``created_at``, and the list endpoint sorting on it could return them either way
round, so a running-balance column read 90 then 72 then 90 again.

``clock_timestamp()`` reads the wall clock per statement instead, which orders
them. It stays a value the *database* evaluates -- the codebase's rule against
reading the application server's clock is untouched, and the column is still
UTC.

SQLite has no ``clock_timestamp()``; ``CURRENT_TIMESTAMP`` is the closest it
offers, so the unit suite keeps working. Its one-second resolution cannot order
rows written in the same second, which is why the ledger's total ordering ends
with an id tiebreaker rather than relying on time alone.
"""

from typing import Any

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.compiler import SQLCompiler
from sqlalchemy.sql.expression import FunctionElement
from sqlalchemy.types import DateTime


class statement_now(FunctionElement[Any]):  # noqa: N801
    """The instant this statement runs, not the instant the transaction began."""

    type = DateTime()
    name = "statement_now"
    inherit_cache = True


@compiles(statement_now)
def _default_statement_now(
    element: statement_now, compiler: SQLCompiler, **kw: object
) -> str:
    """Fall back to the transaction clock on a dialect without a better one."""
    return "CURRENT_TIMESTAMP"


@compiles(statement_now, "postgresql")
def _postgresql_statement_now(
    element: statement_now, compiler: SQLCompiler, **kw: object
) -> str:
    """Read PostgreSQL's wall clock, which advances between statements."""
    return "clock_timestamp()"

"""The search's ILIKE is answered by a trigram index on PostgreSQL (PLT-3).

The search used to wrap every column in ``CAST(... AS VARCHAR)``, and the
migration names the operator class in ``public``. Both are the kind of detail
that leaves an index built and never used, so this asks the planner.
"""

from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import Engine, create_engine, text


@pytest.fixture
def scratch(engine: Engine) -> Iterator[tuple[Engine, str]]:
    """Give a disposable schema on its own engine, dropped afterwards."""
    own = create_engine(engine.url)
    name = f"it_{uuid4().hex[:12]}"
    try:
        with own.begin() as db:
            db.execute(text(f'CREATE SCHEMA "{name}"'))
        yield own, name
    finally:
        with own.begin() as db:
            db.execute(text(f'DROP SCHEMA IF EXISTS "{name}" CASCADE'))
        own.dispose()


def test_a_middle_of_the_value_match_uses_the_trigram_index(
    scratch: tuple[Engine, str],
) -> None:
    """``ILIKE '%text%'`` on the indexed column is an index scan."""
    own, schema = scratch
    with own.begin() as db:
        db.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public"))
        db.execute(text(f'SET search_path TO "{schema}"'))
        db.execute(text("CREATE TABLE sales_invoices (invoice_number varchar(60))"))
        db.execute(
            text(
                "INSERT INTO sales_invoices "
                "SELECT 'SI-26-27-' || lpad(g::text, 6, '0') "
                "FROM generate_series(1, 2000) g"
            )
        )
        db.execute(
            text(
                'CREATE INDEX "IX_sales_invoices_invoice_number_trgm" ON '
                "sales_invoices USING gin (invoice_number public.gin_trgm_ops)"
            )
        )
        db.execute(text("ANALYZE sales_invoices"))
        db.execute(text("SET LOCAL enable_seqscan = off"))
        plan = "\n".join(
            row[0]
            for row in db.execute(
                text(
                    "EXPLAIN SELECT * FROM sales_invoices "
                    "WHERE invoice_number ILIKE '%0815%'"
                )
            )
        )
    assert "IX_sales_invoices_invoice_number_trgm" in plan, plan

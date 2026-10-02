"""GST document numbers kept to 16 characters (backlog GST-2, §77 row 13).

``document_numbering_rules`` gains ``short_financial_year``: the year prints
as ``26-27`` rather than ``2026-2027``. The platform's own default series of
the six GST documents printed ``SI-2026-2027-000001`` -- 19 characters, past
the 16 CGST rule 46(b) allows and the IRP accepts -- and the delivery
challan's added the firm and branch codes as well.

Each such series a firm has not changed -- still the module's
``<TYPE>_DEFAULT`` or the demo seeder's ``<TYPE>_STD``, no format pattern,
the year printed in full, no suffix -- moves to the short year and stops
printing the firm and branch codes, where the result fits. Its
counter is keyed on the full year label either way, so numbering carries on
consecutively from the last number issued. A series a firm made or reshaped
itself is left alone; the next edit of it is judged against the limit.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: the column is
added only where it is missing, and the update touches only series still
printing the full year.

Revision ID: 20261002_0235
Revises: 20261002_0234
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261002_0235"
down_revision: str | Sequence[str] | None = "20261002_0234"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "document_numbering_rules"
_COLUMN = "short_financial_year"
_GST_TYPES = (
    "SALES_INVOICE",
    "CREDIT_NOTE",
    "SALES_RETURN",
    "CUSTOMER_DEBIT_NOTE",
    "DELIVERY_NOTE",
    "RCM_SELF_INVOICE",
)


def upgrade() -> None:
    """Add the column, then shorten the untouched GST default series."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE) or not inspector.has_table(
        "document_type_definitions"
    ):
        return
    present = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN not in present:
        op.add_column(
            _TABLE,
            sa.Column(
                _COLUMN,
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
    # prefix + separator + "26-27" + separator + digits must fit in 16.
    op.get_bind().execute(
        sa.text(
            f"""
            UPDATE {_TABLE} AS series
            SET short_financial_year = TRUE,
                include_branch_code = FALSE,
                include_company_code = FALSE,
                version = series.version + 1,
                updated_at = CURRENT_TIMESTAMP
            FROM document_type_definitions AS kind
            WHERE kind.id = series.document_type_id
              AND kind.code IN :types
              AND (
                  series.code = kind.code || '_DEFAULT'
                  OR series.code = kind.code || '_STD'
              )
              AND series.is_deleted = FALSE
              AND series.format_pattern IS NULL
              AND series.suffix IS NULL
              AND series.include_financial_year = TRUE
              AND series.short_financial_year = FALSE
              AND COALESCE(LENGTH(series.prefix), 0)
                  + 2 * LENGTH(series.separator) + 5 + series.sequence_padding <= 16
            """
        ).bindparams(sa.bindparam("types", expanding=True)),
        {"types": list(_GST_TYPES)},
    )


def downgrade() -> None:
    """Drop the column; the series print the full year again."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    present = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN in present:
        op.drop_column(_TABLE, _COLUMN)

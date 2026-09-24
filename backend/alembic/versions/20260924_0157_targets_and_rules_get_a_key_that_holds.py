"""A target's scope and a rule's window get a key that actually holds (D-TER-16).

Two guards on this pair were reads followed by inserts, with nothing behind
them, and the one key that did exist held in neither direction it was meant to.

``UQ_sales_targets_scope_period`` was plain, over
(firm_id, salesman_id, territory_id, period_start). Both scope columns are
nullable and neither PostgreSQL nor SQLite equates two NULLs, so it held
**nothing** for a target with a blank scope -- most of them. It covered deleted
rows, so a withdrawn target kept its period for ever while the service, which
filters ``is_deleted``, let the replacement through to the database's bare 409.
And it left ``basis`` out, while the service deliberately allows one INVOICED
and one COLLECTED target over the same days.

``commission_rules`` had no such key at all: ``_assert_window_is_free`` reads
and then ``create_rule`` writes, so two requests that both check before either
commits both pass -- and two live rules over one person's days leave the rate to
whichever row a query returns first.

Both replacements ``coalesce`` the nullable scope columns onto the nil UUID so
the key can compare them, and both are partial on live rows. Neither can express
an **overlapping** window, only a shared start date; the service checks stay
authoritative for that, and for the message. The same division
``UQ_commission_payouts_period_active`` already draws.

PostgreSQL only, as with ``UQ_firms_code_active`` and the rest: the service
checks remain the enforcement, and MySQL has no partial index.

Idempotent: each index is created only where its table exists and the index is
missing, because firm stores are partly built by ``create_all``. Firm-owned, so
run it through ``scripts/migrate_all_stores.py``.

Revision ID: 20260924_0157
Revises: 20260924_0156
Create Date: 2026-09-24

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260924_0157"
down_revision: str | Sequence[str] | None = "20260924_0156"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The nil UUID, standing in for "this scope is blank" so a unique key can
#: compare two of them. No row can legitimately hold it.
_NIL = "'00000000-0000-0000-0000-000000000000'"

_TARGETS = "sales_targets"
_TARGETS_OLD = "UQ_sales_targets_scope_period"
_TARGETS_NEW = "UQ_sales_targets_scope_period_active"
_TARGETS_COLUMNS = [
    sa.text("firm_id"),
    sa.text(f"coalesce(salesman_id, {_NIL})"),
    sa.text(f"coalesce(territory_id, {_NIL})"),
    sa.text("basis"),
    sa.text("period_start"),
]

_RULES = "commission_rules"
_RULES_NEW = "UQ_commission_rules_scope_start_active"
_RULES_COLUMNS = [
    sa.text("firm_id"),
    sa.text(f"coalesce(salesman_id, {_NIL})"),
    sa.text(f"coalesce(product_id, {_NIL})"),
    sa.text(f"coalesce(product_category_id, {_NIL})"),
    sa.text("effective_from"),
]


def _has_index(inspector: sa.Inspector, table: str, name: str) -> bool:
    """Report whether one index is already on the table."""
    return any(index["name"] == name for index in inspector.get_indexes(table))


def _has_constraint(inspector: sa.Inspector, table: str, name: str) -> bool:
    """Report whether one unique constraint is already on the table."""
    return any(
        constraint["name"] == name
        for constraint in inspector.get_unique_constraints(table)
    )


def upgrade() -> None:
    """Replace the target key and add the rule key, where the tables exist."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    inspector = sa.inspect(bind)
    if inspector.has_table(_TARGETS):
        if _has_constraint(inspector, _TARGETS, _TARGETS_OLD):
            op.drop_constraint(_TARGETS_OLD, _TARGETS, type_="unique")
        if not _has_index(inspector, _TARGETS, _TARGETS_NEW):
            op.create_index(
                _TARGETS_NEW,
                _TARGETS,
                _TARGETS_COLUMNS,
                unique=True,
                postgresql_where=sa.text("NOT is_deleted"),
            )
    if inspector.has_table(_RULES) and not _has_index(inspector, _RULES, _RULES_NEW):
        op.create_index(
            _RULES_NEW,
            _RULES,
            _RULES_COLUMNS,
            unique=True,
            postgresql_where=sa.text("NOT is_deleted AND status = 'ACTIVE'"),
        )


def downgrade() -> None:
    """Drop both indexes and put the plain target key back."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    inspector = sa.inspect(bind)
    if inspector.has_table(_RULES) and _has_index(inspector, _RULES, _RULES_NEW):
        op.drop_index(_RULES_NEW, table_name=_RULES)
    if not inspector.has_table(_TARGETS):
        return
    if _has_index(inspector, _TARGETS, _TARGETS_NEW):
        op.drop_index(_TARGETS_NEW, table_name=_TARGETS)
    if not _has_constraint(inspector, _TARGETS, _TARGETS_OLD):
        op.create_unique_constraint(
            _TARGETS_OLD,
            _TARGETS,
            ["firm_id", "salesman_id", "territory_id", "period_start"],
        )

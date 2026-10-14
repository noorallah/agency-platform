"""Move the salesman columns onto the firm's own list (P2, build step 2).

Section 4 of ``docs/design/SALESMAN_LIST_DESIGN.md``, steps 3 and 4:

* ``territory_salesman_assignments.user_id`` becomes ``salesman_id``: the
  column added, copied, the unique key and the index moved onto it under
  names saying ``salesman``, and ``user_id`` dropped.
* **Every row names an entry of its own firm.** In the shared store an id may
  be the entry of another firm (`20261014_0380`'s "one id, two firms"): such a
  row is pointed at this firm's own entry for the same user. An id with no
  entry at all -- written by the old code after `0380` ran -- is given one,
  of its own id where that id is free, tied to that user and named as `0380`
  names one. A territory assignment takes its firm from its territory. Rows
  soft-deleted or not, since the key holds against both.
* ``FK_<table>_salesman_id`` declared to ``salesmen.id`` (``RESTRICT``) on the
  twelve tables and on the assignment column, after dropping any key those
  columns held to ``users`` -- found by inspecting the store, since `users`
  is reachable only where the platform's tables are.

Firm-owned data: run ``scripts/migrate_all_stores.py``. Idempotent: every
add, drop and key is inspected first, and a row already naming its own
firm's entry is left alone.

Revision ID: 20261014_0382
Revises: 20261014_0381
Create Date: 2026-10-14

"""

from collections import defaultdict
from collections.abc import Sequence
from uuid import UUID, uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.salesmen.naming import NAME_LENGTH, free_name, placeholder_name

revision: str = "20261014_0382"
down_revision: str | Sequence[str] | None = "20261014_0381"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SALESMEN = "salesmen"
_ASSIGNMENTS = "territory_salesman_assignments"
_TERRITORIES = "sales_territories"
_UNIQUE = "UQ_territory_salesman_assignments_territory_salesman"
_INDEX = "IX_territory_salesman_assignments_salesman"
_OLD_UNIQUE = "UQ_territory_salesman_assignments_territory_user"
_OLD_INDEX = "IX_territory_salesman_assignments_user"

#: The tables whose ``salesman_id`` names a salesman, each with a ``firm_id``.
_SALESMAN_COLUMNS = (
    "sales_invoices",
    "sales_orders",
    "delivery_notes",
    "sales_quotations",
    "enquiries",
    "credit_notes",
    "customer_debit_notes",
    "sales_returns",
    "customers",
    "commission_rules",
    "commission_payouts",
    "sales_targets",
)

_salesmen = sa.table(
    _SALESMEN,
    sa.column("id", UUIDType()),
    sa.column("firm_id", UUIDType()),
    sa.column("name", sa.String()),
    sa.column("user_id", UUIDType()),
    sa.column("earns_commission", sa.Boolean()),
    sa.column("is_active", sa.Boolean()),
    sa.column("is_deleted", sa.Boolean()),
    sa.column("version", sa.Integer()),
)


def _uuid(value: object) -> UUID:
    """Read an id the driver returned as text or as a UUID."""
    return value if isinstance(value, UUID) else UUID(str(value))


def _columns(inspector: sa.Inspector, table: str) -> set[str]:
    """Return the store's columns of ``table``, or none where it is missing."""
    if not inspector.has_table(table):
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def _user_names(bind: sa.Connection, inspector: sa.Inspector) -> dict[UUID, str]:
    """Read the users' names, where ``platform.users`` is reachable from here."""
    if bind.dialect.name != "postgresql":
        return {}
    if bind.scalar(sa.text("SELECT current_schema()")) == "platform":
        return {}
    if not inspector.has_table("users", schema="platform"):
        return {}
    return {
        _uuid(user_id): (full_name or "").strip()
        for user_id, full_name in bind.execute(
            sa.text("SELECT id, full_name FROM platform.users")
        ).all()
        if (full_name or "").strip()
    }


def _named(bind: sa.Connection, inspector: sa.Inspector) -> set[tuple[UUID, UUID]]:
    """Return every ``(firm, salesman id)`` the columns hold."""
    pairs: set[tuple[UUID, UUID]] = set()
    for table in _SALESMAN_COLUMNS:
        if not {"salesman_id", "firm_id"} <= _columns(inspector, table):
            continue
        for salesman_id, firm_id in bind.execute(
            sa.text(
                f'SELECT DISTINCT salesman_id, firm_id FROM "{table}" '  # noqa: S608
                "WHERE salesman_id IS NOT NULL"
            )
        ).all():
            pairs.add((_uuid(firm_id), _uuid(salesman_id)))
    if "salesman_id" in _columns(inspector, _ASSIGNMENTS) and inspector.has_table(
        _TERRITORIES
    ):
        for salesman_id, firm_id in bind.execute(
            sa.text(
                "SELECT DISTINCT a.salesman_id, t.firm_id "
                "FROM territory_salesman_assignments a "
                "JOIN sales_territories t ON t.id = a.territory_id "
                "WHERE a.salesman_id IS NOT NULL"
            )
        ).all():
            pairs.add((_uuid(firm_id), _uuid(salesman_id)))
    return pairs


def _settle(
    bind: sa.Connection, inspector: sa.Inspector
) -> dict[tuple[UUID, UUID], UUID]:
    """Make sure every named id is an entry of its row's firm.

    Returns ``{(firm, id the rows hold): the firm's own entry}`` for every
    pair whose rows must be pointed elsewhere; an entry is made where the
    firm has none for that user.
    """
    entries: dict[UUID, tuple[UUID, UUID | None]] = {}
    tied: dict[tuple[UUID, UUID], UUID] = {}
    taken: dict[UUID, set[str]] = defaultdict(set)
    # Live entries last, so a live one wins the tie over a deleted one.
    for row_id, firm_id, user_id, name, is_deleted in bind.execute(
        sa.select(
            _salesmen.c.id,
            _salesmen.c.firm_id,
            _salesmen.c.user_id,
            _salesmen.c.name,
            _salesmen.c.is_deleted,
        ).order_by(_salesmen.c.is_deleted.desc())
    ):
        entry, firm = _uuid(row_id), _uuid(firm_id)
        user = None if user_id is None else _uuid(user_id)
        entries[entry] = (firm, user)
        if user is not None:
            tied[(firm, user)] = entry
        if not is_deleted:
            taken[firm].add(str(name).lower())

    moves: dict[tuple[UUID, UUID], UUID] = {}
    names: dict[UUID, str] | None = None
    for firm, held in sorted(_named(bind, inspector), key=str):
        owner = entries.get(held)
        if owner is not None and owner[0] == firm:
            continue
        # The user the id stands for: the other firm's entry's, or the id
        # itself, which the old code only ever wrote as a user's.
        user = held if owner is None else owner[1]
        target = None if user is None else tied.get((firm, user))
        if target is None:
            if names is None:
                names = _user_names(bind, inspector)
            target = held if held not in entries else uuid4()
            source = user if user is not None else held
            name = (
                free_name(
                    names.get(source, placeholder_name(source)), target, taken[firm]
                )
                or f"Salesman {target}"[:NAME_LENGTH]
            )
            bind.execute(
                _salesmen.insert().values(
                    id=target,
                    firm_id=firm,
                    name=name,
                    user_id=user,
                    earns_commission=True,
                    is_active=True,
                    is_deleted=False,
                    version=1,
                )
            )
            entries[target] = (firm, user)
            if user is not None:
                tied[(firm, user)] = target
            taken[firm].add(name.lower())
        if target != held:
            moves[(firm, held)] = target
    return moves


def _repoint(bind: sa.Connection, inspector: sa.Inspector) -> None:
    """Point every row at an entry of its own firm (step a)."""
    moves = _settle(bind, inspector)
    for (firm, held), target in moves.items():
        for table in _SALESMAN_COLUMNS:
            if not {"salesman_id", "firm_id"} <= _columns(inspector, table):
                continue
            bind.execute(
                sa.text(
                    f'UPDATE "{table}" SET salesman_id = :target '  # noqa: S608
                    "WHERE firm_id = :firm AND salesman_id = :held"
                ).bindparams(
                    sa.bindparam("target", type_=UUIDType()),
                    sa.bindparam("firm", type_=UUIDType()),
                    sa.bindparam("held", type_=UUIDType()),
                ),
                {"target": target, "firm": firm, "held": held},
            )
        if "salesman_id" in _columns(inspector, _ASSIGNMENTS):
            bind.execute(
                sa.text(
                    "UPDATE territory_salesman_assignments "
                    "SET salesman_id = :target WHERE salesman_id = :held "
                    "AND territory_id IN "
                    "(SELECT id FROM sales_territories WHERE firm_id = :firm)"
                ).bindparams(
                    sa.bindparam("target", type_=UUIDType()),
                    sa.bindparam("firm", type_=UUIDType()),
                    sa.bindparam("held", type_=UUIDType()),
                ),
                {"target": target, "firm": firm, "held": held},
            )


def _drop_keys_on(inspector: sa.Inspector, table: str, column: str) -> None:
    """Drop every foreign key on ``table.column`` that is not to ``salesmen``."""
    for key in inspector.get_foreign_keys(table):
        if key["constrained_columns"] != [column] or not key.get("name"):
            continue
        if key["referred_table"] == _SALESMEN and column == "salesman_id":
            continue
        op.drop_constraint(op.f(key["name"]), table, type_="foreignkey")


def _add_assignment_column(bind: sa.Connection, inspector: sa.Inspector) -> None:
    """Add ``salesman_id`` beside ``user_id`` and copy it across (step b)."""
    columns = _columns(inspector, _ASSIGNMENTS)
    if not columns:
        return
    if "salesman_id" not in columns:
        op.add_column(_ASSIGNMENTS, sa.Column("salesman_id", UUIDType(), nullable=True))
    if "user_id" in columns:
        bind.execute(
            sa.text(
                "UPDATE territory_salesman_assignments SET salesman_id = user_id "
                "WHERE salesman_id IS NULL"
            )
        )


def _finish_assignments(bind: sa.Connection) -> None:
    """Move the keys onto ``salesman_id`` and drop ``user_id`` (step b)."""
    inspector = sa.inspect(bind)
    columns = _columns(inspector, _ASSIGNMENTS)
    if not columns:
        return
    for unique in inspector.get_unique_constraints(_ASSIGNMENTS):
        if "user_id" in unique["column_names"] and unique.get("name"):
            op.drop_constraint(op.f(unique["name"]), _ASSIGNMENTS, type_="unique")
    # Read again: dropping a unique constraint drops the index behind it.
    inspector = sa.inspect(bind)
    for index in inspector.get_indexes(_ASSIGNMENTS):
        if "user_id" in index["column_names"] and index.get("name"):
            op.drop_index(op.f(index["name"]), table_name=_ASSIGNMENTS)
    if "user_id" in columns:
        _drop_keys_on(inspector, _ASSIGNMENTS, "user_id")
        op.drop_column(_ASSIGNMENTS, "user_id")
    inspector = sa.inspect(bind)
    nullable = {
        column["name"]: column["nullable"]
        for column in inspector.get_columns(_ASSIGNMENTS)
    }
    if nullable.get("salesman_id") and bind.dialect.name == "postgresql":
        op.alter_column(
            _ASSIGNMENTS, "salesman_id", existing_type=UUIDType(), nullable=False
        )
    uniques = {
        unique["name"] for unique in inspector.get_unique_constraints(_ASSIGNMENTS)
    }
    indexes = {index["name"] for index in inspector.get_indexes(_ASSIGNMENTS)}
    if _UNIQUE not in uniques and _UNIQUE not in indexes:
        op.create_unique_constraint(
            op.f(_UNIQUE), _ASSIGNMENTS, ["territory_id", "salesman_id"]
        )
    if _INDEX not in indexes:
        op.create_index(op.f(_INDEX), _ASSIGNMENTS, ["salesman_id"])


def _drop_user_keys(bind: sa.Connection) -> None:
    """Drop the keys the salesman columns hold to ``users`` (step c, first half).

    Before any row is pointed at another entry: an entry made here takes a
    new id where the user's is held, and a key to ``users`` would refuse it.
    Only where a key was declared, which is only where ``users`` was in reach.
    """
    inspector = sa.inspect(bind)
    for table in _SALESMAN_COLUMNS:
        if "salesman_id" in _columns(inspector, table):
            _drop_keys_on(inspector, table, "salesman_id")
    if "user_id" in _columns(inspector, _ASSIGNMENTS):
        _drop_keys_on(inspector, _ASSIGNMENTS, "user_id")


def _declare_keys(bind: sa.Connection) -> None:
    """Point every salesman column at ``salesmen.id`` (step c)."""
    inspector = sa.inspect(bind)
    for table in (*_SALESMAN_COLUMNS, _ASSIGNMENTS):
        if "salesman_id" not in _columns(inspector, table):
            continue
        _drop_keys_on(inspector, table, "salesman_id")
        held = {
            key["name"]
            for key in sa.inspect(bind).get_foreign_keys(table)
            if key["constrained_columns"] == ["salesman_id"]
            and key["referred_table"] == _SALESMEN
        }
        if not held:
            op.create_foreign_key(
                op.f(f"FK_{table}_salesman_id"),
                table,
                _SALESMEN,
                ["salesman_id"],
                ["id"],
                ondelete="RESTRICT",
            )


def upgrade() -> None:
    """Rename the assignment column, settle every row, and declare the keys."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # `0380` built the list in every store holding sales documents.
    if not inspector.has_table(_SALESMEN):
        return
    # SQLite can neither drop nor add a key on a table that exists; the unit
    # suite builds its schema from the models, which declare the new ones.
    postgres = bind.dialect.name == "postgresql"
    if postgres:
        _drop_user_keys(bind)
    _add_assignment_column(bind, sa.inspect(bind))
    _repoint(bind, sa.inspect(bind))
    _finish_assignments(bind)
    if postgres:
        _declare_keys(bind)


def downgrade() -> None:
    """Drop the keys and bring ``user_id`` back from ``salesman_id``.

    ``user_id`` is the user each assignment's entry is tied to, or the entry's
    id where it is tied to nobody. A document row pointed at another entry of
    its own firm stays pointed there.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_SALESMEN):
        return
    for table in (*_SALESMAN_COLUMNS, _ASSIGNMENTS):
        if "salesman_id" not in _columns(inspector, table):
            continue
        for key in inspector.get_foreign_keys(table):
            if (
                key["constrained_columns"] == ["salesman_id"]
                and key["referred_table"] == _SALESMEN
                and key.get("name")
            ):
                op.drop_constraint(op.f(key["name"]), table, type_="foreignkey")
    columns = _columns(inspector, _ASSIGNMENTS)
    if not columns:
        return
    if "user_id" not in columns:
        op.add_column(_ASSIGNMENTS, sa.Column("user_id", UUIDType(), nullable=True))
        bind.execute(
            sa.text(
                "UPDATE territory_salesman_assignments SET user_id = "
                "COALESCE((SELECT s.user_id FROM salesmen s "
                "WHERE s.id = territory_salesman_assignments.salesman_id), "
                "salesman_id)"
            )
        )
    inspector = sa.inspect(bind)
    for unique in inspector.get_unique_constraints(_ASSIGNMENTS):
        if "salesman_id" in unique["column_names"] and unique.get("name"):
            op.drop_constraint(op.f(unique["name"]), _ASSIGNMENTS, type_="unique")
    inspector = sa.inspect(bind)
    for index in inspector.get_indexes(_ASSIGNMENTS):
        if "salesman_id" in index["column_names"] and index.get("name"):
            op.drop_index(op.f(index["name"]), table_name=_ASSIGNMENTS)
    if "salesman_id" in _columns(inspector, _ASSIGNMENTS):
        op.drop_column(_ASSIGNMENTS, "salesman_id")
    op.create_unique_constraint(
        op.f(_OLD_UNIQUE), _ASSIGNMENTS, ["territory_id", "user_id"]
    )
    op.create_index(op.f(_OLD_INDEX), _ASSIGNMENTS, ["user_id"])

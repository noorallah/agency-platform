"""Give every firm with open books Petty Cash, Capital, Transport and Fuel.

Backlog 106, the first customer's list (S1): five accounts a small firm looks
for on its first day. *Drawings* has been in every firm's books since
``20261003_0276``; the other four were not in the chart at all, so the owner's
money put in had only *Opening Balance Equity* to go to and diesel was booked
under *Travel and Conveyance*. New firms open with them (``CHART`` in
``app/finance/services/opening_setup.py``); this gives an existing firm the
same.

Only where missing, never overwriting:

* a firm that already has a live account of the same name and kind keeps it,
  under whatever number it gave it, and gets no second one;
* a firm that renamed the account under the number keeps that too;
* a number the firm used for an account of another kind stays with it, and
  the new account takes the next number free;
* a firm whose books were never opened is left alone -- opening them seeds
  the lot.

None of the four is mapped to a control purpose: a person chooses them, and
no document posts to them by itself. *Petty Cash* is opened in the group of
the account the firm mapped to Cash, so the cash book and a contra voucher
read it as cash whether that firm keeps cash under *Cash-in-Hand* or, as the
firms opened before decision A22 do, straight under *Current Assets*.

Firm-owned: run ``scripts/migrate_all_stores.py``.

Revision ID: 20261012_0355
Revises: 20261008_0354
Create Date: 2026-10-12

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "20261012_0355"
down_revision: str | Sequence[str] | None = "20261008_0354"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (code, name, account type, group code, group name, parent group code,
#: purpose whose account it is opened beside). Kept in step with ``CHART``,
#: written out so this migration means the same thing whatever the seed says
#: later.
_ACCOUNTS = (
    ("1005", "Petty Cash", "ASSET", "CA-CASH", "Cash-in-Hand", "CA", "CASH"),
    ("3200", "Capital", "EQUITY", "EQ", "Equity", None, None),
    ("6450", "Transport", "EXPENSE", "IEXP", "Indirect Expenses", None, None),
    ("6460", "Fuel", "EXPENSE", "IEXP", "Indirect Expenses", None, None),
)


def _group_for(
    bind: sa.Connection,
    firm_id: object,
    *,
    code: str,
    kind: str,
    name: str,
    parent_code: str | None,
) -> object:
    """Return the firm's group for an account, creating it only if it has none."""
    group_id = bind.execute(
        sa.text(
            "SELECT id FROM account_groups WHERE firm_id = :firm "
            "AND code = :code AND is_deleted = false"
        ),
        {"firm": firm_id, "code": code},
    ).scalar()
    if group_id is not None:
        return group_id
    parent_id = None
    if parent_code is not None:
        parent_id = bind.execute(
            sa.text(
                "SELECT id FROM account_groups WHERE firm_id = :firm "
                "AND code = :code AND is_deleted = false"
            ),
            {"firm": firm_id, "code": parent_code},
        ).scalar()
    group_id = uuid4()
    bind.execute(
        sa.text(
            "INSERT INTO account_groups (id, firm_id, code, name, "
            "account_type, parent_group_id, is_active, is_deleted, version, "
            "created_at, updated_at) VALUES (:id, :firm, :code, :name, "
            ":kind, :parent, true, false, 1, now(), now())"
        ),
        {
            "id": group_id,
            "firm": firm_id,
            "code": code,
            "name": name,
            "kind": kind,
            "parent": parent_id,
        },
    )
    return group_id


def _group_beside(
    bind: sa.Connection, firm_id: object, purpose: str | None, *, mapped: bool
) -> object | None:
    """Return the group of the account the firm mapped to a purpose, if any."""
    if purpose is None or not mapped:
        return None
    return bind.execute(
        sa.text(
            "SELECT a.account_group_id FROM firm_control_accounts c "
            "JOIN ledger_accounts a ON a.id = c.ledger_account_id "
            "WHERE c.firm_id = :firm AND c.purpose = :purpose "
            "AND c.is_deleted = false AND a.is_deleted = false"
        ),
        {"firm": firm_id, "purpose": purpose},
    ).scalar()


def upgrade() -> None:
    """Add the four accounts to every firm whose books are open."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("account_groups") or not inspector.has_table(
        "ledger_accounts"
    ):
        return
    has_mappings = inspector.has_table("firm_control_accounts")
    # A firm's books are open once its Direct Expenses group exists: that is
    # what opening them creates first.
    firms = (
        bind.execute(
            sa.text(
                "SELECT DISTINCT firm_id FROM account_groups "
                "WHERE code = 'EXP' AND is_deleted = false"
            )
        )
        .scalars()
        .all()
    )
    for firm_id in firms:
        held = bind.execute(
            sa.text(
                "SELECT code, lower(name), account_type FROM ledger_accounts "
                "WHERE firm_id = :firm AND is_deleted = false"
            ),
            {"firm": firm_id},
        ).all()
        kind_of = {row[0]: row[2] for row in held}
        named = {(row[1], row[2]) for row in held}
        for code, name, kind, group, group_name, parent, beside in _ACCOUNTS:
            if (name.lower(), kind) in named or kind_of.get(code) == kind:
                continue
            number = code
            while number in kind_of:
                number = str(int(number) + 1)
            group_id = _group_beside(bind, firm_id, beside, mapped=has_mappings)
            if group_id is None:
                group_id = _group_for(
                    bind,
                    firm_id,
                    code=group,
                    kind=kind,
                    name=group_name,
                    parent_code=parent,
                )
            bind.execute(
                sa.text(
                    "INSERT INTO ledger_accounts (id, firm_id, "
                    "account_group_id, code, name, account_type, "
                    "is_balance_sheet, is_profit_loss, "
                    "requires_cost_center, requires_profit_center, "
                    "is_active, is_deleted, version, created_at, "
                    "updated_at) VALUES (:id, :firm, :group, :code, :name, "
                    ":kind, :balance_sheet, :profit_loss, false, false, "
                    "true, false, 1, now(), now())"
                ),
                {
                    "id": uuid4(),
                    "firm": firm_id,
                    "group": group_id,
                    "code": number,
                    "name": name,
                    "kind": kind,
                    "balance_sheet": kind != "EXPENSE",
                    "profit_loss": kind == "EXPENSE",
                },
            )
            kind_of[number] = kind
            named.add((name.lower(), kind))


def downgrade() -> None:
    """Leave the accounts in place.

    They may already carry postings, and a downgrade that deleted accounts
    with journal lines against them would be refused by the database or,
    worse, orphan the lines.
    """

"""Give every GST-template firm its inward interstate rules (D-CMP-14).

The GST template carried three interstate rules, ``INTERSTATE_GST_5/12/18``,
each conditioned on ``transaction_type = SALES_INTERSTATE``. Nothing on the
purchase side could ever match them, so a purchase from a supplier in another
state was charged CGST and SGST -- an input credit the return cannot claim
as IGST, and a supplier's invoice that disagrees with the firm's books.

Purchase documents now ask ``inward_transaction_type`` and send
``PURCHASE_INTERSTATE`` for a supplier in another state (IGST Act s.7), and the
template carries ``PURCHASE_INTERSTATE_GST_5/12/18``. A firm that applied the
template before this revision has only the sales rules, so this inserts the
purchase twins **only where missing**:

- Only a firm that has the sales rule of that slab -- the latest live version
  of ``INTERSTATE_GST_n`` -- gets the purchase rule, and it is copied from that
  version: the same country and profile scope, effective window and
  conditions (whatever shape they now have -- ``20260809_0049`` rewrote some to
  the group code), with ``SALES_INTERSTATE`` read as ``PURCHASE_INTERSTATE``,
  and the same actions plus ``INPUT_CREDIT_ALLOWED``, because the rule outranks
  ``PURCHASE_INPUT_CREDIT`` and evaluation stops at the first match.
- A sales rule a firm has rewritten so that it no longer tests
  ``transaction_type = SALES_INTERSTATE`` is not guessed at: nothing is copied.
- A firm holding **any** row coded ``PURCHASE_INTERSTATE_GST_n`` -- deleted
  included, since a deleted rule was somebody's decision -- is left alone, so a
  replay adds nothing and nothing is ever overwritten.

Idempotent and firm-owned: run it through ``scripts/migrate_all_stores.py``.
The platform schema holds no tax rules once pruned, and is skipped.

Revision ID: 20260919_0148
Revises: 20260919_0146
Create Date: 2026-09-19

"""

from collections.abc import Sequence
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260919_0148"
down_revision: str | Sequence[str] | None = "20260919_0146"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Sales rule -> (purchase twin, its priority). The template's sales rules sit
#: at 10-12; the purchase ones follow them, still ahead of EXEMPT_PROFILE (20)
#: and PURCHASE_INPUT_CREDIT (30).
_TWINS: dict[str, tuple[str, int]] = {
    "INTERSTATE_GST_5": ("PURCHASE_INTERSTATE_GST_5", 13),
    "INTERSTATE_GST_12": ("PURCHASE_INTERSTATE_GST_12", 14),
    "INTERSTATE_GST_18": ("PURCHASE_INTERSTATE_GST_18", 15),
}

_RULES = sa.table(
    "tax_rules",
    sa.column("id", UUIDType()),
    sa.column("firm_id", UUIDType()),
    sa.column("country_id", UUIDType()),
    sa.column("business_profile_id", UUIDType()),
    sa.column("tax_profile_id", UUIDType()),
    sa.column("code", sa.String()),
    sa.column("name", sa.String()),
    sa.column("description", sa.Text()),
    sa.column("priority", sa.Integer()),
    sa.column("status", sa.String()),
    sa.column("version_group_id", UUIDType()),
    sa.column("version_number", sa.Integer()),
    sa.column("supersedes_rule_id", UUIDType()),
    sa.column("effective_from", sa.Date()),
    sa.column("effective_to", sa.Date()),
    sa.column("is_deleted", sa.Boolean()),
    sa.column("version", sa.Integer()),
)
_CONDITIONS = sa.table(
    "tax_rule_conditions",
    sa.column("id", UUIDType()),
    sa.column("firm_id", UUIDType()),
    sa.column("tax_rule_id", UUIDType()),
    sa.column("sequence", sa.Integer()),
    sa.column("field_key", sa.String()),
    sa.column("operator", sa.String()),
    sa.column("value_text", sa.Text()),
    sa.column("value_number", sa.Numeric()),
    sa.column("value_date", sa.Date()),
    sa.column("value_boolean", sa.Boolean()),
    sa.column("value_json", sa.JSON()),
    sa.column("is_deleted", sa.Boolean()),
    sa.column("version", sa.Integer()),
)
_ACTIONS = sa.table(
    "tax_rule_actions",
    sa.column("id", UUIDType()),
    sa.column("firm_id", UUIDType()),
    sa.column("tax_rule_id", UUIDType()),
    sa.column("sequence", sa.Integer()),
    sa.column("action_type", sa.String()),
    sa.column("target_tax_profile_id", UUIDType()),
    sa.column("target_tax_component_id", UUIDType()),
    sa.column("percentage_override", sa.Numeric()),
    sa.column("parameters", sa.JSON()),
    sa.column("is_deleted", sa.Boolean()),
    sa.column("version", sa.Integer()),
)


def _is_sales_interstate(condition: Any) -> bool:  # noqa: ANN401 -- a Row
    """Whether a condition is the sales rule's ``transaction_type`` test."""
    return (
        condition.field_key == "transaction_type"
        and (condition.value_text or "").strip().upper() == "SALES_INTERSTATE"
    )


def insert_inward_rules(bind: Connection) -> int:
    """Insert the missing purchase twins in this store, and return how many."""
    inserted = 0
    for sales_code, (purchase_code, priority) in _TWINS.items():
        sources = bind.execute(
            sa.select(_RULES)
            .where(
                _RULES.c.code == sales_code,
                _RULES.c.is_deleted.is_(False),
                _RULES.c.status == "ACTIVE",
            )
            .order_by(_RULES.c.firm_id, _RULES.c.version_number.desc())
        ).all()
        taken: set[UUID] = {
            row[0]
            for row in bind.execute(
                sa.select(_RULES.c.firm_id).where(_RULES.c.code == purchase_code)
            )
        }
        for source in sources:
            if source.firm_id in taken:
                continue
            # The first row per firm is its latest live version.
            taken.add(source.firm_id)
            conditions = bind.execute(
                sa.select(_CONDITIONS)
                .where(
                    _CONDITIONS.c.tax_rule_id == source.id,
                    _CONDITIONS.c.is_deleted.is_(False),
                )
                .order_by(_CONDITIONS.c.sequence)
            ).all()
            if not any(_is_sales_interstate(row) for row in conditions):
                continue
            actions = bind.execute(
                sa.select(_ACTIONS)
                .where(
                    _ACTIONS.c.tax_rule_id == source.id,
                    _ACTIONS.c.is_deleted.is_(False),
                )
                .order_by(_ACTIONS.c.sequence)
            ).all()
            rule_id = uuid4()
            bind.execute(
                _RULES.insert().values(
                    id=rule_id,
                    firm_id=source.firm_id,
                    country_id=source.country_id,
                    business_profile_id=source.business_profile_id,
                    tax_profile_id=source.tax_profile_id,
                    code=purchase_code,
                    name=(source.name or sales_code).replace("sale", "purchase", 1),
                    description=(
                        "Interstate purchase switches local GST to IGST; added "
                        f"beside {sales_code} for purchases from another state."
                    ),
                    priority=priority,
                    status="ACTIVE",
                    version_group_id=uuid4(),
                    version_number=1,
                    supersedes_rule_id=None,
                    effective_from=source.effective_from,
                    effective_to=source.effective_to,
                    is_deleted=False,
                    version=1,
                )
            )
            for condition in conditions:
                bind.execute(
                    _CONDITIONS.insert().values(
                        id=uuid4(),
                        firm_id=source.firm_id,
                        tax_rule_id=rule_id,
                        sequence=condition.sequence,
                        field_key=condition.field_key,
                        operator=condition.operator,
                        value_text=(
                            "PURCHASE_INTERSTATE"
                            if _is_sales_interstate(condition)
                            else condition.value_text
                        ),
                        value_number=condition.value_number,
                        value_date=condition.value_date,
                        value_boolean=condition.value_boolean,
                        value_json=condition.value_json,
                        is_deleted=False,
                        version=1,
                    )
                )
            sequence = 0
            for action in actions:
                sequence = max(sequence, action.sequence)
                bind.execute(
                    _ACTIONS.insert().values(
                        id=uuid4(),
                        firm_id=source.firm_id,
                        tax_rule_id=rule_id,
                        sequence=action.sequence,
                        action_type=action.action_type,
                        target_tax_profile_id=action.target_tax_profile_id,
                        target_tax_component_id=action.target_tax_component_id,
                        percentage_override=action.percentage_override,
                        parameters=action.parameters or {},
                        is_deleted=False,
                        version=1,
                    )
                )
            if not any(row.action_type == "INPUT_CREDIT_ALLOWED" for row in actions):
                bind.execute(
                    _ACTIONS.insert().values(
                        id=uuid4(),
                        firm_id=source.firm_id,
                        tax_rule_id=rule_id,
                        sequence=sequence + 1,
                        action_type="INPUT_CREDIT_ALLOWED",
                        target_tax_profile_id=None,
                        target_tax_component_id=None,
                        percentage_override=None,
                        parameters={},
                        is_deleted=False,
                        version=1,
                    )
                )
            inserted += 1
    return inserted


def upgrade() -> None:
    """Insert the purchase interstate rules each template firm lacks."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not all(
        inspector.has_table(name)
        for name in ("tax_rules", "tax_rule_conditions", "tax_rule_actions")
    ):
        return
    insert_inward_rules(bind)


def downgrade() -> None:
    """Leave the rules in place.

    Removing them would put every interstate purchase back on CGST and SGST,
    and by then some may carry edits or later versions of their own; an
    administrator can switch one off on the tax screens.
    """

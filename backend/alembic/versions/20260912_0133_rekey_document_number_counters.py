"""Re-key every document number counter under the key its rule uses today.

What goes into a counter's ``scope_signature`` has changed twice: the year
became conditional on ``auto_reset``, then the branch and the company on
whether the number actually prints them (2026-09-12). Neither change moved the
existing rows, so a series a firm had been issuing for two years sat under a
key nothing would look for again. The next document found no counter, started
at one, and was refused as a duplicate of a number already issued -- the first
purchase return raised after the second change, found in manual testing that
afternoon, and the same shape waiting on every sales invoice, sales order,
quotation, purchase invoice, credit note, proforma and sales return in every
seeded firm.

Each live counter is re-keyed the way ``_scope_signature`` would key it now:
the year kept only under ``auto_reset``, the branch and company only when the
rule prints them. Counters that collapse onto one key are merged onto the
highest ``next_sequence`` -- a series continues from wherever it had got to --
and the rest are soft-deleted. The rule's ``last_scope_signature`` is re-keyed
beside them. Re-running finds every row already under its key and changes
nothing.

Counters are firm-owned and live in every firm store, so run this through
``scripts/migrate_all_stores.py``. The service also adopts a legacy counter on
first use, so a store this migration has not reached still continues its
series; this puts every store right in one pass instead of one series at a
time.
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "20260912_0133"
down_revision: str | Sequence[str] | None = "20260908_0132"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RULES = "document_numbering_rules"
_COUNTERS = "document_number_sequences"


def _carries(part: str, flag: bool, pattern: str | None) -> bool:
    """Whether a rule's numbers print ``part`` -- the flag, or the pattern."""
    return bool(flag) or ("{" + part + "}") in (pattern or "")


def _rekey(
    signature: str,
    *,
    auto_reset: bool,
    branch: bool,
    company: bool,
) -> str:
    """Return ``signature`` under the key the rule would give it today."""
    year, branch_code, company_code = (signature.split("|") + ["", "", ""])[:3]
    return "|".join(
        [
            year if auto_reset else "",
            branch_code if branch else "",
            company_code if company else "",
        ]
    )


def upgrade() -> None:
    """Move every live counter under its rule's current key, merging on max."""
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(_COUNTERS):
        # The platform schema holds no firm-owned tables once pruned.
        return
    rules = sa.table(
        _RULES,
        sa.column("id"),
        sa.column("auto_reset"),
        sa.column("include_branch_code"),
        sa.column("include_company_code"),
        sa.column("format_pattern"),
        sa.column("last_scope_signature"),
        sa.column("is_deleted"),
    )
    counters = sa.table(
        _COUNTERS,
        sa.column("id"),
        sa.column("numbering_rule_id"),
        sa.column("scope_signature"),
        sa.column("next_sequence"),
        sa.column("is_deleted"),
        sa.column("deleted_at"),
        sa.column("updated_at"),
    )
    now = datetime.now(UTC)
    for rule in bind.execute(
        sa.select(rules).where(rules.c.is_deleted.is_(False))
    ).all():
        branch = _carries("branch_code", rule.include_branch_code, rule.format_pattern)
        company = _carries(
            "company_code", rule.include_company_code, rule.format_pattern
        )

        def key(
            signature: str,
            *,
            branch: bool = branch,
            company: bool = company,
            auto_reset: bool = rule.auto_reset,
        ) -> str:
            return _rekey(
                signature, auto_reset=auto_reset, branch=branch, company=company
            )

        rows = bind.execute(
            sa.select(counters)
            .where(
                counters.c.numbering_rule_id == rule.id,
                counters.c.is_deleted.is_(False),
            )
            .order_by(counters.c.next_sequence.desc())
        ).all()
        groups: dict[str, list[sa.Row[object]]] = {}
        for row in rows:
            groups.setdefault(key(row.scope_signature), []).append(row)
        for target, members in groups.items():
            highest = max(member.next_sequence for member in members)
            # Prefer a row already under the key; otherwise the highest one
            # takes it. Every other member is retired.
            keeper = next(
                (m for m in members if m.scope_signature == target), members[0]
            )
            if keeper.scope_signature != target or keeper.next_sequence != highest:
                bind.execute(
                    sa.update(counters)
                    .where(counters.c.id == keeper.id)
                    .values(
                        scope_signature=target,
                        next_sequence=highest,
                        updated_at=now,
                    )
                )
            retired = [m.id for m in members if m.id != keeper.id]
            if retired:
                bind.execute(
                    sa.update(counters)
                    .where(counters.c.id.in_(retired))
                    .values(is_deleted=True, deleted_at=now, updated_at=now)
                )
        if rule.last_scope_signature:
            rekeyed = key(rule.last_scope_signature)
            if rekeyed != rule.last_scope_signature:
                bind.execute(
                    sa.update(rules)
                    .where(rules.c.id == rule.id)
                    .values(last_scope_signature=rekeyed)
                )


def downgrade() -> None:
    """Nothing to undo: the old keys were ones nothing reads any more."""

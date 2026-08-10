"""Give each numbering scope its own counter.

``document_numbering_rules`` carried one ``next_sequence`` and a
``last_scope_signature``, and reset the counter to 1 whenever the scope
changed. That is correct only if documents are created in scope order and the
order is never revisited. It is not:

* enter a missed invoice dated in the previous financial year -- ordinary
  accounting -- and the counter resets to 1 for that year;
* create the next current-year document and the counter resets again, to 1,
  handing out a number that year already used.

The document number is unique per firm, so the second document fails outright.
The user's only route back is to stop back-dating.

This moves the counter into ``document_number_sequences``, one row per rule and
scope, so the two years number independently and neither disturbs the other.
Existing state is carried across exactly: each rule's current counter becomes
the row for the scope it was last used in, so no document renumbers and the
next number issued is the one that would have been issued anyway.

``document_numbering_rules`` is firm-owned, so this runs in every firm store.
``next_sequence`` and ``last_scope_signature`` stay on the rule -- the first is
still the configured starting number for a scope nobody has used yet.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260810_0061"
down_revision: str | Sequence[str] | None = "20260810_0060"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "document_number_sequences"
_RULES = "document_numbering_rules"


def upgrade() -> None:
    """Create the per-scope counters and seed them from the rules."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Firm-owned: the numbering rules live in firm stores, not in platform.
    if not inspector.has_table(_RULES):
        return
    if not inspector.has_table(_TABLE):
        op.create_table(
            _TABLE,
            sa.Column("id", UUIDType(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column(
                "is_deleted",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deleted_by", UUIDType(), nullable=True),
            sa.Column("created_by", UUIDType(), nullable=True),
            sa.Column("updated_by", UUIDType(), nullable=True),
            sa.Column(
                "version", sa.Integer(), server_default=sa.text("0"), nullable=False
            ),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("numbering_rule_id", UUIDType(), nullable=False),
            sa.Column("scope_signature", sa.String(length=200), nullable=False),
            sa.Column(
                "next_sequence",
                sa.Integer(),
                server_default=sa.text("1"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id", name="PK_document_number_sequences"),
            sa.ForeignKeyConstraint(
                ["numbering_rule_id"],
                [f"{_RULES}.id"],
                name="FK_document_number_sequences_numbering_rule_id",
                ondelete="CASCADE",
            ),
            sa.UniqueConstraint(
                "numbering_rule_id",
                "scope_signature",
                name="UQ_document_number_sequences_rule_scope",
            ),
        )
        op.create_index("IX_document_number_sequences_firm_id", _TABLE, ["firm_id"])
        op.create_index(
            "IX_document_number_sequences_numbering_rule_id",
            _TABLE,
            ["numbering_rule_id"],
        )

    # Carry each rule's counter into the scope it was last used in, so the next
    # number issued is exactly the one that would have been issued before.
    bind.execute(
        sa.text(
            f"""
            INSERT INTO {_TABLE} (
                id, firm_id, numbering_rule_id, scope_signature, next_sequence,
                is_deleted, version
            )
            SELECT
                gen_random_uuid(), r.firm_id, r.id, r.last_scope_signature,
                r.next_sequence, false, 0
            FROM {_RULES} r
            WHERE r.last_scope_signature IS NOT NULL
              AND r.is_deleted = false
              AND NOT EXISTS (
                  SELECT 1 FROM {_TABLE} s
                  WHERE s.numbering_rule_id = r.id
                    AND s.scope_signature = r.last_scope_signature
              )
            """  # noqa: S608
        )
    )


def downgrade() -> None:
    """Drop the per-scope counters; the rule keeps the value it already has."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table(_TABLE):
        op.drop_table(_TABLE)

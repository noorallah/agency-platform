"""Give date and quantity attribute definitions their real data types.

Every seeded definition was created as TEXT, including four that are plainly not
text. An expiry date held in ``value_text`` cannot answer "what expires in the
next 30 days", and a shelf life held as text cannot be compared or summed —
which defeats the typed value columns those fields exist for.

``product_attribute_values`` holds no rows, so retyping costs nothing. Any
definition an administrator has since created is left alone; this only corrects
the seeded set, and only where the intent is unambiguous from the code.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260809_0048"
down_revision: str | Sequence[str] | None = "20260809_0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: definition code -> the type it should have carried from the start.
_RETYPED = {
    "EXPIRY_DATE": "DATE",
    "SHELF_LIFE_DAYS": "NUMBER",
    "WARRANTY_MONTHS": "NUMBER",
    "WEIGHT": "NUMBER",
}

_definitions = sa.table(
    "attribute_definitions",
    sa.column("id", sa.Uuid()),
    sa.column("code", sa.String()),
    sa.column("data_type", sa.String()),
)


def _apply(bind: sa.Connection, mapping: dict[str, str]) -> None:
    """Set the data type of each named definition, if it exists."""
    for code, data_type in mapping.items():
        bind.execute(
            _definitions.update()
            .where(_definitions.c.code == code)
            .values(data_type=data_type)
        )


def upgrade() -> None:
    """Retype the seeded date and quantity attributes."""
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("attribute_definitions"):
        return
    # Retyping a definition that already holds values would strand them in the
    # wrong column, so refuse rather than corrupt.
    if sa.inspect(bind).has_table("product_attribute_values"):
        held = bind.execute(
            sa.text(
                "SELECT count(*) FROM product_attribute_values v "
                "JOIN attribute_definitions d ON d.id = v.attribute_definition_id "
                "WHERE d.code IN :codes AND v.is_deleted = false"
            ).bindparams(sa.bindparam("codes", tuple(_RETYPED), expanding=True))
        ).scalar()
        if held:
            raise RuntimeError(
                f"Cannot retype attribute definitions: {held} value(s) exist for "
                f"{', '.join(sorted(_RETYPED))}. Migrate them into the correct "
                "typed column first."
            )
    _apply(bind, _RETYPED)


def downgrade() -> None:
    """Return the corrected definitions to TEXT."""
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("attribute_definitions"):
        return
    _apply(bind, dict.fromkeys(_RETYPED, "TEXT"))

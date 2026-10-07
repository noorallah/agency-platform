"""Extra fields follow the kind of record, never the firm's profile.

Backlog 89, step 5. A custom field was offered by the firm's business
profile, and made compulsory by a profile and a category. The profile leaves
both:

* ``firm_attribute_switches``: a firm's on or off for a field of the shared
  catalogue. No row means on; off hides the field and keeps its values.
* ``category_attribute_rules`` gains ``goods_type_id``, ``customer_group_id``
  and ``vendor_type_id``, and ``category_code`` becomes optional: a rule
  names exactly one of the four. A rule on one of the three kinds ties its
  field to records of that kind, and ``is_mandatory`` says whether it must be
  filled there. One live rule per firm, kind and field.

What is kept before anything is dropped, each only where still to do:

* a shared field scoped to a profile is switched off for every firm that is
  assigned another profile, so no firm starts seeing a field it did not; a
  firm's **own** field scoped to a profile the firm is not on is made
  inactive for the same reason;
* a shared rule whose category code is the code of a shared goods type --
  the seeded MEDICINE, FOOD and ELECTRONICS rules -- becomes a rule on that
  goods type. It used to bite only in a firm on the matching profile, which
  is the fault this entry ends: food sold by a pharmacy-profile firm is
  food. The rule now **shows** its field on that type's products and no
  longer makes it compulsory: it was compulsory for one category code in
  one profile, and carried over as written it would demand an IMEI of every
  television and refuse a product import that gives only the category. A
  firm that wants one compulsory says so in a rule of its own;
* rules left identical once the profile no longer tells them apart are
  folded into one, the compulsory one where they differ.

Then ``attribute_definitions.applicable_business_profile_id`` and
``category_attribute_rules.business_profile_id`` are dropped, last, with the
unique constraint that named the profile.

Per store: run ``scripts/migrate_all_stores.py``. A key to a table this store
does not hold is left out. Idempotent.

Revision ID: 20261008_0352
Revises: 20261008_0351
Create Date: 2026-10-08

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261008_0352"
down_revision: str | Sequence[str] | None = "20261008_0351"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FIELDS = "attribute_definitions"
_RULES = "category_attribute_rules"
_SWITCHES = "firm_attribute_switches"

#: A rule's kind column, and the table it points at.
_KINDS: tuple[tuple[str, str], ...] = (
    ("goods_type_id", "goods_types"),
    ("customer_group_id", "customer_groups"),
    ("vendor_type_id", "vendor_types"),
)
#: The four things a rule can name; one live rule per firm, field and each.
_RULE_KEYS: tuple[tuple[str, str], ...] = (
    ("category_code", "UQ_category_attribute_rules_category_code_active"),
    ("goods_type_id", "UQ_category_attribute_rules_goods_type_active"),
    ("customer_group_id", "UQ_category_attribute_rules_customer_group_active"),
    ("vendor_type_id", "UQ_category_attribute_rules_vendor_type_active"),
)

_fields = sa.table(
    _FIELDS,
    sa.column("id", UUIDType()),
    sa.column("firm_id", UUIDType()),
    sa.column("entity_type", sa.String()),
    sa.column("applicable_business_profile_id", UUIDType()),
    sa.column("is_active", sa.Boolean()),
    sa.column("is_deleted", sa.Boolean()),
)
_rules = sa.table(
    _RULES,
    sa.column("id", UUIDType()),
    sa.column("firm_id", UUIDType()),
    sa.column("category_code", sa.String()),
    sa.column("goods_type_id", UUIDType()),
    sa.column("customer_group_id", UUIDType()),
    sa.column("vendor_type_id", UUIDType()),
    sa.column("attribute_definition_id", UUIDType()),
    sa.column("is_mandatory", sa.Boolean()),
    sa.column("is_deleted", sa.Boolean()),
    sa.column("deleted_at", sa.DateTime(timezone=True)),
    sa.column("created_at", sa.DateTime(timezone=True)),
)
_switches = sa.table(
    _SWITCHES,
    sa.column("id", UUIDType()),
    sa.column("firm_id", UUIDType()),
    sa.column("attribute_definition_id", UUIDType()),
    sa.column("is_enabled", sa.Boolean()),
)
_firm_profiles = sa.table(
    "firm_business_profiles",
    sa.column("firm_id", UUIDType()),
    sa.column("business_profile_id", UUIDType()),
    sa.column("is_deleted", sa.Boolean()),
)
_goods_types = sa.table(
    "goods_types",
    sa.column("id", UUIDType()),
    sa.column("firm_id", UUIDType()),
    sa.column("code", sa.String()),
    sa.column("is_deleted", sa.Boolean()),
)


def _columns(table: str) -> set[str]:
    """Return the names of a table's columns as the store holds them now."""
    return {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str | None]:
    """Return the names of a table's indexes as the store holds them now."""
    return {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}


def _create_switches() -> None:
    """Create ``firm_attribute_switches``, one live row per firm and field."""
    op.create_table(
        _SWITCHES,
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
            "is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", UUIDType(), nullable=True),
        sa.Column("created_by", UUIDType(), nullable=True),
        sa.Column("updated_by", UUIDType(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("attribute_definition_id", UUIDType(), nullable=False),
        sa.Column(
            "is_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="PK_firm_attribute_switches"),
        sa.ForeignKeyConstraint(
            ["attribute_definition_id"],
            [f"{_FIELDS}.id"],
            name="FK_firm_attribute_switches_attribute_definition_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("IX_firm_attribute_switches_firm_id", _SWITCHES, ["firm_id"])
    op.create_index(
        "IX_firm_attribute_switches_attribute_definition_id",
        _SWITCHES,
        ["attribute_definition_id"],
    )
    op.create_index(
        "UQ_firm_attribute_switches_firm_field_active",
        _SWITCHES,
        ["firm_id", "attribute_definition_id"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )


def _add_kind_columns() -> None:
    """Give a rule its three kinds, and let it name no category."""
    inspector = sa.inspect(op.get_bind())
    held = _columns(_RULES)
    keys = {item["name"] for item in inspector.get_foreign_keys(_RULES)}
    indexes = _indexes(_RULES)
    for column, target in _KINDS:
        if column not in held:
            op.add_column(_RULES, sa.Column(column, UUIDType(), nullable=True))
        key = f"FK_{_RULES}_{column}"
        # The kind's table is firm-owned: a store without it gets the column,
        # so the model and the table agree, and no key.
        if key not in keys and inspector.has_table(target):
            op.create_foreign_key(
                key, _RULES, target, [column], ["id"], ondelete="CASCADE"
            )
        index = f"IX_{_RULES}_{column}"
        if index not in indexes:
            op.create_index(index, _RULES, [column])
    op.alter_column(
        _RULES, "category_code", existing_type=sa.String(length=100), nullable=True
    )


def _keep_what_the_profile_hid() -> None:
    """Record, per firm, the fields its profile kept from it."""
    bind = op.get_bind()
    if "applicable_business_profile_id" not in _columns(_FIELDS):
        return
    scoped = bind.execute(
        sa.select(
            _fields.c.id,
            _fields.c.firm_id,
            _fields.c.applicable_business_profile_id,
        ).where(
            _fields.c.applicable_business_profile_id.is_not(None),
            _fields.c.is_deleted.is_(False),
        )
    ).all()
    if not scoped or not sa.inspect(bind).has_table("firm_business_profiles"):
        return
    assigned = bind.execute(
        sa.select(_firm_profiles.c.firm_id, _firm_profiles.c.business_profile_id).where(
            _firm_profiles.c.is_deleted.is_(False)
        )
    ).all()
    profile_of = dict(assigned)
    switched = {
        (firm_id, field_id)
        for firm_id, field_id in bind.execute(
            sa.select(_switches.c.firm_id, _switches.c.attribute_definition_id)
        ).all()
    }
    for field_id, owner, profile_id in scoped:
        if owner is not None:
            # A firm's own field, scoped to a profile the firm is not on, was
            # offered on no form. Inactive says the same thing from now on.
            if owner in profile_of and profile_of[owner] != profile_id:
                bind.execute(
                    _fields.update()
                    .where(_fields.c.id == field_id, _fields.c.is_active.is_(True))
                    .values(is_active=False)
                )
            continue
        for firm_id, firm_profile in assigned:
            if firm_profile == profile_id or (firm_id, field_id) in switched:
                continue
            bind.execute(
                _switches.insert().values(
                    id=uuid4(),
                    firm_id=firm_id,
                    attribute_definition_id=field_id,
                    is_enabled=False,
                )
            )


def _rekey_shared_rules() -> None:
    """Turn a shared rule on a goods type's code into a rule on the type."""
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("goods_types"):
        return
    shared_types = dict(
        bind.execute(
            sa.select(_goods_types.c.code, _goods_types.c.id).where(
                _goods_types.c.firm_id.is_(None),
                _goods_types.c.is_deleted.is_(False),
            )
        ).all()
    )
    product_fields = sa.select(_fields.c.id).where(_fields.c.entity_type == "PRODUCT")
    for code, goods_type_id in shared_types.items():
        bind.execute(
            _rules.update().where(
                _rules.c.firm_id.is_(None),
                _rules.c.category_code == code,
                _rules.c.goods_type_id.is_(None),
                _rules.c.is_deleted.is_(False),
                _rules.c.attribute_definition_id.in_(product_fields),
            )
            # Shown on that type's products, no longer compulsory: see
            # the module docstring.
            .values(
                goods_type_id=goods_type_id,
                category_code=None,
                is_mandatory=False,
            )
        )


def _fold_identical_rules() -> None:
    """Leave one live rule where the profile was all that told several apart."""
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(
            _rules.c.id,
            _rules.c.firm_id,
            _rules.c.category_code,
            _rules.c.goods_type_id,
            _rules.c.customer_group_id,
            _rules.c.vendor_type_id,
            _rules.c.attribute_definition_id,
            _rules.c.is_mandatory,
        ).where(_rules.c.is_deleted.is_(False))
        # The compulsory one first, so it is the one kept; then the oldest.
        .order_by(_rules.c.is_mandatory.desc(), _rules.c.created_at.asc())
    ).all()
    kept: set[tuple[object, ...]] = set()
    for rule_id, *what, _is_mandatory in rows:
        key = tuple(what)
        if key not in kept:
            kept.add(key)
            continue
        bind.execute(
            _rules.update()
            .where(_rules.c.id == rule_id)
            .values(is_deleted=True, deleted_at=sa.func.now())
        )


def _create_rule_keys() -> None:
    """Hold one live rule per firm, field and thing named."""
    indexes = _indexes(_RULES)
    for column, name in _RULE_KEYS:
        if name in indexes:
            continue
        op.create_index(
            name,
            _RULES,
            ["firm_id", column, "attribute_definition_id"],
            unique=True,
            postgresql_where=sa.text(f"is_deleted = false AND {column} IS NOT NULL"),
        )


def _drop_profile_column(table: str, column: str) -> None:
    """Drop a profile column with every constraint that names it."""
    inspector = sa.inspect(op.get_bind())
    if column not in _columns(table):
        return
    for constraint in inspector.get_unique_constraints(table):
        if column in constraint["column_names"] and constraint["name"]:
            op.drop_constraint(constraint["name"], table, type_="unique")
    for key in inspector.get_foreign_keys(table):
        if column in key["constrained_columns"] and key["name"]:
            op.drop_constraint(key["name"], table, type_="foreignkey")
    for index in inspector.get_indexes(table):
        if index.get("duplicates_constraint"):
            continue
        if column in index["column_names"] and index["name"]:
            op.drop_index(index["name"], table_name=table)
    op.drop_column(table, column)


def upgrade() -> None:
    """Move field rules onto the kind of record, then drop the profile."""
    inspector = sa.inspect(op.get_bind())
    if not (inspector.has_table(_FIELDS) and inspector.has_table(_RULES)):
        return
    if not inspector.has_table(_SWITCHES):
        _create_switches()
    _add_kind_columns()
    _keep_what_the_profile_hid()
    _rekey_shared_rules()
    _fold_identical_rules()
    _create_rule_keys()
    # Last: nothing above reads these again, and nothing below does.
    _drop_profile_column(_RULES, "business_profile_id")
    _drop_profile_column(_FIELDS, "applicable_business_profile_id")


def downgrade() -> None:
    """Put the two profile columns back, empty, and take the kinds out.

    Which profile a field or a rule once named is not kept, so both columns
    return null: every field offered to every profile. A rule on a kind
    names no category and is removed with its column.
    """
    inspector = sa.inspect(op.get_bind())
    if not (inspector.has_table(_FIELDS) and inspector.has_table(_RULES)):
        return
    if "applicable_business_profile_id" not in _columns(_FIELDS):
        op.add_column(
            _FIELDS,
            sa.Column("applicable_business_profile_id", UUIDType(), nullable=True),
        )
    if "business_profile_id" not in _columns(_RULES):
        op.add_column(
            _RULES, sa.Column("business_profile_id", UUIDType(), nullable=True)
        )
    indexes = _indexes(_RULES)
    for _column, name in _RULE_KEYS:
        if name in indexes:
            op.drop_index(name, table_name=_RULES)
    op.execute(_rules.delete().where(_rules.c.category_code.is_(None)))
    op.alter_column(
        _RULES, "category_code", existing_type=sa.String(length=100), nullable=False
    )
    keys = {item["name"] for item in inspector.get_foreign_keys(_RULES)}
    for column, _target in _KINDS:
        if column not in _columns(_RULES):
            continue
        if f"FK_{_RULES}_{column}" in keys:
            op.drop_constraint(f"FK_{_RULES}_{column}", _RULES, type_="foreignkey")
        if f"IX_{_RULES}_{column}" in indexes:
            op.drop_index(f"IX_{_RULES}_{column}", table_name=_RULES)
        op.drop_column(_RULES, column)
    if inspector.has_table(_SWITCHES):
        op.drop_table(_SWITCHES)

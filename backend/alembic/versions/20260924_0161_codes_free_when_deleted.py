"""Codes are unique among live rows; designation-only codes leave every role.

Four changes, each guarded so the revision is safe on every store.

**Role codes (D-IDN-9).** ``UQ_roles_code`` was a plain key over every role in
every firm, so a deleted role's code was never released and one firm was told
another already had a role by that name. It becomes two partial keys: one over
the live platform-wide roles, system roles included, and one per firm.
``roles`` lives only in the platform schema.

**Master codes (D-MST-11).** The plain keys over each master's code -- and the
customer's GST and PAN, the vendor's GSTIN, the category and type names, the
storage node's code and name -- become keys over live rows, the shape
``UQ_products_firm_barcode_active`` already had. Masters live in every firm
store.

**Designation-only permission codes (D-IDN-10).** Eleven seeded codes name acts
only the platform designation performs, so granting one to a role granted
nothing. Every role's live assignment of one is retired.

**Firm registry tidy-up (D-IDN-10).** ``firms.status`` now mirrors ``is_active``,
so a row whose free-text status disagreed is set to match; and the copies of
``user_templates`` / ``user_template_roles`` that firm stores kept, and nothing
read, are dropped where the store is a firm's (it has no ``firms`` table).

PostgreSQL only for the keys: MySQL has no partial index, and there the
services' checks stay the enforcement. Every step is idempotent: a key is
dropped only where it is still present (as a constraint or an index, because
``create_all`` builds some stores) and created only where missing, and the
updates touch only rows still out of line. Run it through
``scripts/migrate_all_stores.py``.

Revision ID: 20260924_0161
Revises: 20260924_0160
Create Date: 2026-09-24

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260924_0161"
down_revision: str | Sequence[str] | None = "20260924_0160"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LIVE = "is_deleted = false"

#: (table, old plain key, new partial key, columns, extra predicate)
_Key = tuple[str, str, str, tuple[str, ...], str | None]


def _master(table: str, old: str, *columns: str) -> _Key:
    """Name a master key: its partial twin is the old name plus ``_active``."""
    return (table, old, f"{old}_active", columns, None)


_KEYS: tuple[_Key, ...] = (
    (
        "roles",
        "UQ_roles_code",
        "UQ_roles_platform_code_active",
        ("code",),
        "firm_id IS NULL",
    ),
    (
        "roles",
        "UQ_roles_code",
        "UQ_roles_firm_code_active",
        ("firm_id", "code"),
        "firm_id IS NOT NULL",
    ),
    _master("customer_groups", "UQ_customer_groups_firm_code", "firm_id", "code"),
    _master("customer_groups", "UQ_customer_groups_firm_name", "firm_id", "name"),
    _master("customers", "UQ_customers_firm_code", "firm_id", "code"),
    _master("customers", "UQ_customers_firm_gst_number", "firm_id", "gst_number"),
    _master("customers", "UQ_customers_firm_pan_number", "firm_id", "pan_number"),
    _master("vendor_categories", "UQ_vendor_categories_firm_code", "firm_id", "code"),
    _master("vendor_categories", "UQ_vendor_categories_firm_name", "firm_id", "name"),
    _master("vendor_types", "UQ_vendor_types_firm_code", "firm_id", "code"),
    _master("vendor_types", "UQ_vendor_types_firm_name", "firm_id", "name"),
    _master("vendors", "UQ_vendors_firm_code", "firm_id", "code"),
    _master("vendors", "UQ_vendors_firm_gstin", "firm_id", "gstin"),
    _master("product_categories", "UQ_product_categories_firm_code", "firm_id", "code"),
    _master(
        "product_categories",
        "UQ_product_categories_firm_name_parent",
        "firm_id",
        "name",
        "parent_id",
    ),
    _master("products", "UQ_products_firm_code", "firm_id", "code"),
    _master("branch_types", "UQ_branch_types_firm_code", "firm_id", "code"),
    _master("branch_types", "UQ_branch_types_firm_name", "firm_id", "name"),
    _master("branches", "UQ_branches_firm_code", "firm_id", "code"),
    _master("warehouse_types", "UQ_warehouse_types_firm_code", "firm_id", "code"),
    _master("warehouse_types", "UQ_warehouse_types_firm_name", "firm_id", "name"),
    _master("warehouses", "UQ_warehouses_firm_code", "firm_id", "code"),
    _master(
        "warehouse_storage_nodes",
        "UQ_warehouse_storage_nodes_warehouse_code",
        "warehouse_id",
        "code",
    ),
    _master(
        "warehouse_storage_nodes",
        "UQ_warehouse_storage_nodes_warehouse_name_parent",
        "warehouse_id",
        "name",
        "parent_id",
    ),
)

#: Mirrors ``DESIGNATION_ONLY_PERMISSION_CODES`` as it stood at this revision;
#: a migration must not change meaning when the constant does.
_DESIGNATION_ONLY = (
    "FIRM_CREATE",
    "FIRM_UPDATE",
    "FIRM_DELETE",
    "FIRM_ACTIVATE",
    "FIRM_DEACTIVATE",
    "PERMISSION_CREATE",
    "PERMISSION_UPDATE",
    "PERMISSION_DELETE",
    "USER_RESET_PASSWORD",
    "USER_LOCK",
    "USER_UNLOCK",
)


def _has_index(inspector: sa.Inspector, table: str, name: str) -> bool:
    """Report whether one index is already on the table."""
    return any(index["name"] == name for index in inspector.get_indexes(table))


def _has_constraint(inspector: sa.Inspector, table: str, name: str) -> bool:
    """Report whether one unique constraint is already on the table."""
    return any(
        constraint["name"] == name
        for constraint in inspector.get_unique_constraints(table)
    )


def _swap_keys(bind: sa.Connection) -> None:
    """Replace each plain key with its partial twin, where the table exists."""
    inspector = sa.inspect(bind)
    for table, old, new, columns, extra in _KEYS:
        if not inspector.has_table(table):
            continue
        if _has_constraint(inspector, table, old):
            op.drop_constraint(old, table, type_="unique")
            inspector = sa.inspect(bind)
        elif _has_index(inspector, table, old):
            op.drop_index(old, table_name=table)
            inspector = sa.inspect(bind)
        if not _has_index(inspector, table, new):
            predicate = _LIVE if extra is None else f"{extra} AND {_LIVE}"
            op.create_index(
                new,
                table,
                list(columns),
                unique=True,
                postgresql_where=sa.text(predicate),
            )


def _retire_designation_only_grants(bind: sa.Connection) -> None:
    """Retire every role's live grant of a designation-only code."""
    inspector = sa.inspect(bind)
    if not (
        inspector.has_table("role_permissions") and inspector.has_table("permissions")
    ):
        return
    bind.execute(
        sa.text(
            "UPDATE role_permissions SET is_deleted = true, "
            "deleted_at = CURRENT_TIMESTAMP "
            "WHERE is_deleted = false AND permission_id IN "
            "(SELECT id FROM permissions WHERE code IN :codes)"
        ).bindparams(sa.bindparam("codes", expanding=True)),
        {"codes": list(_DESIGNATION_ONLY)},
    )


def _align_firm_status(bind: sa.Connection) -> None:
    """Make each firm's status say what its active flag says."""
    if not sa.inspect(bind).has_table("firms"):
        return
    bind.execute(
        sa.text(
            "UPDATE firms SET status = CASE WHEN is_active THEN 'ACTIVE' "
            "ELSE 'INACTIVE' END "
            "WHERE status IS DISTINCT FROM "
            "(CASE WHEN is_active THEN 'ACTIVE' ELSE 'INACTIVE' END)"
        )
    )


def _drop_firm_store_template_copies(bind: sa.Connection) -> None:
    """Drop the job-template tables from a store that is a firm's.

    A store without ``firms`` is a firm store: the registry lives only in the
    platform schema. There the two tables were stray copies nothing read.
    """
    inspector = sa.inspect(bind)
    if inspector.has_table("firms") or inspector.has_table("users"):
        return
    for table in ("user_template_roles", "user_templates"):
        if inspector.has_table(table):
            op.drop_table(table)


def upgrade() -> None:
    """Swap the keys, retire the grants, and tidy the registry."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    _swap_keys(bind)
    _retire_designation_only_grants(bind)
    _align_firm_status(bind)
    _drop_firm_store_template_copies(bind)


def downgrade() -> None:
    """Restore the plain keys, which fails if a retired code has been reused.

    The retired grants and the dropped template copies are not brought back:
    neither conferred or held anything.
    """
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    inspector = sa.inspect(bind)
    for table, old, new, columns, _ in _KEYS:
        if not inspector.has_table(table):
            continue
        if _has_index(inspector, table, new):
            op.drop_index(new, table_name=table)
        inspector = sa.inspect(bind)
        if not _has_constraint(inspector, table, old) and not _has_index(
            inspector, table, old
        ):
            # The old role key was over the code alone, in every scope.
            plain = ["code"] if table == "roles" else list(columns)
            op.create_unique_constraint(old, table, plain)
            inspector = sa.inspect(bind)

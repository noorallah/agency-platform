"""Keep a register of trade licences (backlog 54, step 1).

* ``trade_licence_types`` and ``trade_licences`` in every firm store.
* ``TRADE_LICENCE_VIEW`` / ``TRADE_LICENCE_MANAGE`` in the platform store,
  with every system role's grants reconciled -- the shape of ``20260928_0164``.
* The numbers already typed into the old fields are copied into the register,
  only where missing and never overwriting: a vendor's ``fssai`` and
  ``drug_license`` (as FSSAI and a wholesale drug licence), and a vendor's or
  branch's free-text ``license_number`` (as *Other*, since nothing recorded
  what it was). None has a validity date; the register shows them as "no
  expiry recorded" until somebody enters one. The old columns are left alone.

Idempotent throughout; firm-owned parts run per store
(``scripts/migrate_all_stores.py``).
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import ROLE_PERMISSION_CODES, SYSTEM_PERMISSION_CODES

revision: str = "20260930_0167"
down_revision: str | Sequence[str] | None = "20260930_0166"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Written out rather than imported, so this migration means the same thing
#: whatever the service seeds later.
_DEFAULT_TYPES = (
    ("DRUG_WHOLESALE", "Drug licence, wholesale", "20B / 21B", True),
    ("DRUG_RETAIL", "Drug licence, retail", "20 / 21", True),
    ("DRUG_SCHEDULE_X", "Drug licence, Schedule X", "20C / 21C", True),
    ("FSSAI", "FSSAI licence or registration", None, True),
    ("INSECTICIDE", "Insecticide licence", None, True),
    ("FERTILISER", "Fertiliser authorisation", None, True),
    ("SEED", "Seed licence", None, True),
    ("OTHER", "Other licence", None, False),
)


def _audit_columns() -> list[sa.Column[object]]:
    """Return the ``BaseEntity`` columns, timestamps defaulted by the server."""
    return [
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
        sa.Column("version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
    ]


def _create_tables(inspector: sa.Inspector) -> None:
    """Create the two tables in a firm store that lacks them."""
    # Firm-owned: customers exist in firm stores only.
    if not inspector.has_table("customers"):
        return
    if not inspector.has_table("trade_licence_types"):
        op.create_table(
            "trade_licence_types",
            *_audit_columns(),
            sa.Column("code", sa.String(40), nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("form_numbers", sa.String(120), nullable=True),
            sa.Column(
                "expires", sa.Boolean(), server_default=sa.text("true"), nullable=False
            ),
            sa.Column(
                "is_active",
                sa.Boolean(),
                server_default=sa.text("true"),
                nullable=False,
            ),
            sa.Column("description", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id", name="PK_trade_licence_types"),
        )
        op.create_index(
            "IX_trade_licence_types_firm_id", "trade_licence_types", ["firm_id"]
        )
        op.create_index(
            "UQ_trade_licence_types_firm_code_active",
            "trade_licence_types",
            ["firm_id", "code"],
            unique=True,
            postgresql_where=sa.text("NOT is_deleted"),
            sqlite_where=sa.text("NOT is_deleted"),
        )
    if not inspector.has_table("trade_licences"):
        op.create_table(
            "trade_licences",
            *_audit_columns(),
            sa.Column("licence_type_id", UUIDType(), nullable=False),
            sa.Column("holder_type", sa.String(20), nullable=False),
            sa.Column("branch_id", UUIDType(), nullable=True),
            sa.Column("customer_id", UUIDType(), nullable=True),
            sa.Column("vendor_id", UUIDType(), nullable=True),
            sa.Column("licence_number", sa.String(80), nullable=False),
            sa.Column("issued_by", sa.String(200), nullable=True),
            sa.Column("valid_from", sa.Date(), nullable=True),
            sa.Column("valid_to", sa.Date(), nullable=True),
            sa.Column("premises", sa.String(250), nullable=True),
            sa.Column("remarks", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id", name="PK_trade_licences"),
            sa.ForeignKeyConstraint(
                ["licence_type_id"],
                ["trade_licence_types.id"],
                name="FK_trade_licences_licence_type_id",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["branch_id"],
                ["branches.id"],
                name="FK_trade_licences_branch_id",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["customer_id"],
                ["customers.id"],
                name="FK_trade_licences_customer_id",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["vendor_id"],
                ["vendors.id"],
                name="FK_trade_licences_vendor_id",
                ondelete="RESTRICT",
            ),
            sa.CheckConstraint(
                "holder_type IN ('FIRM', 'CUSTOMER', 'VENDOR')",
                name="CK_trade_licences_holder_type",
            ),
            sa.CheckConstraint(
                "(holder_type = 'FIRM' AND customer_id IS NULL AND vendor_id IS NULL)"
                " OR (holder_type = 'CUSTOMER' AND customer_id IS NOT NULL"
                " AND vendor_id IS NULL AND branch_id IS NULL)"
                " OR (holder_type = 'VENDOR' AND vendor_id IS NOT NULL"
                " AND customer_id IS NULL AND branch_id IS NULL)",
                name="CK_trade_licences_holder",
            ),
            sa.CheckConstraint(
                "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
                name="CK_trade_licences_validity",
            ),
        )
        for name, columns in (
            ("IX_trade_licences_firm_id", ["firm_id"]),
            ("IX_trade_licences_licence_type_id", ["licence_type_id"]),
            ("IX_trade_licences_branch_id", ["branch_id"]),
            ("IX_trade_licences_customer_id", ["customer_id"]),
            ("IX_trade_licences_vendor_id", ["vendor_id"]),
            ("IX_trade_licences_firm_valid_to", ["firm_id", "valid_to"]),
            ("IX_trade_licences_firm_holder", ["firm_id", "holder_type"]),
        ):
            op.create_index(name, "trade_licences", columns)


def _type_id(bind: sa.Connection, firm_id: object, code: str) -> object:
    """Return the firm's type of one code, creating the default if missing."""
    found = bind.execute(
        sa.text(
            "SELECT id FROM trade_licence_types WHERE firm_id = :firm "
            "AND code = :code AND is_deleted = false"
        ),
        {"firm": firm_id, "code": code},
    ).scalar()
    if found is not None:
        return found
    _, name, forms, expires = next(row for row in _DEFAULT_TYPES if row[0] == code)
    new_id = uuid4()
    bind.execute(
        sa.text(
            "INSERT INTO trade_licence_types (id, firm_id, code, name, "
            "form_numbers, expires, is_active, is_deleted, version) VALUES "
            "(:id, :firm, :code, :name, :forms, :expires, true, false, 1)"
        ),
        {
            "id": new_id,
            "firm": firm_id,
            "code": code,
            "name": name,
            "forms": forms,
            "expires": expires,
        },
    )
    return new_id


def _copy(
    bind: sa.Connection,
    *,
    firm_id: object,
    code: str,
    number: str,
    holder_type: str,
    branch_id: object = None,
    vendor_id: object = None,
) -> None:
    """Register one old number unless the holder already has it registered."""
    type_id = _type_id(bind, firm_id, code)
    held = bind.execute(
        sa.text(
            "SELECT id FROM trade_licences WHERE firm_id = :firm "
            "AND licence_type_id = :type AND licence_number = :number "
            "AND holder_type = :holder AND is_deleted = false "
            "AND (branch_id = :branch OR (branch_id IS NULL AND :branch IS NULL)) "
            "AND (vendor_id = :vendor OR (vendor_id IS NULL AND :vendor IS NULL))"
        ),
        {
            "firm": firm_id,
            "type": type_id,
            "number": number,
            "holder": holder_type,
            "branch": branch_id,
            "vendor": vendor_id,
        },
    ).scalar()
    if held is not None:
        return
    bind.execute(
        sa.text(
            "INSERT INTO trade_licences (id, firm_id, licence_type_id, "
            "holder_type, branch_id, vendor_id, licence_number, remarks, "
            "is_deleted, version) VALUES (:id, :firm, :type, :holder, :branch, "
            ":vendor, :number, :remarks, false, 1)"
        ),
        {
            "id": uuid4(),
            "firm": firm_id,
            "type": type_id,
            "holder": holder_type,
            "branch": branch_id,
            "vendor": vendor_id,
            "number": number,
            "remarks": "Copied from the old licence field; enter its validity.",
        },
    )


def _copy_old_numbers(inspector: sa.Inspector) -> None:
    """Carry the numbers typed into the old free-text fields into the register."""
    if not inspector.has_table("trade_licences"):
        return
    bind = op.get_bind()
    if inspector.has_table("vendor_tax_details"):
        rows = bind.execute(
            sa.text(
                "SELECT v.firm_id, v.id, t.fssai, t.drug_license "
                "FROM vendor_tax_details t JOIN vendors v ON v.id = t.vendor_id "
                "WHERE t.is_deleted = false AND v.is_deleted = false"
            )
        ).all()
        for firm_id, vendor_id, fssai, drug in rows:
            for code, number in (("FSSAI", fssai), ("DRUG_WHOLESALE", drug)):
                if number and number.strip():
                    _copy(
                        bind,
                        firm_id=firm_id,
                        code=code,
                        number=number.strip().upper(),
                        holder_type="VENDOR",
                        vendor_id=vendor_id,
                    )
    if inspector.has_table("vendors"):
        rows = bind.execute(
            sa.text(
                "SELECT firm_id, id, license_number FROM vendors "
                "WHERE is_deleted = false AND license_number IS NOT NULL"
            )
        ).all()
        for firm_id, vendor_id, number in rows:
            if number.strip():
                _copy(
                    bind,
                    firm_id=firm_id,
                    code="OTHER",
                    number=number.strip().upper(),
                    holder_type="VENDOR",
                    vendor_id=vendor_id,
                )
    if inspector.has_table("branches"):
        rows = bind.execute(
            sa.text(
                "SELECT firm_id, id, license_number FROM branches "
                "WHERE is_deleted = false AND license_number IS NOT NULL"
            )
        ).all()
        for firm_id, branch_id, number in rows:
            if number.strip():
                _copy(
                    bind,
                    firm_id=firm_id,
                    code="OTHER",
                    number=number.strip().upper(),
                    holder_type="FIRM",
                    branch_id=branch_id,
                )


_permissions = sa.table(
    "permissions",
    sa.column("id", UUIDType()),
    sa.column("code", sa.String()),
    sa.column("name", sa.String()),
    sa.column("description", sa.Text()),
    sa.column("is_system", sa.Boolean()),
    sa.column("is_active", sa.Boolean()),
    sa.column("is_deleted", sa.Boolean()),
)
_roles = sa.table("roles", sa.column("id", UUIDType()), sa.column("code", sa.String()))
_role_permissions = sa.table(
    "role_permissions",
    sa.column("id", UUIDType()),
    sa.column("role_id", UUIDType()),
    sa.column("permission_id", UUIDType()),
    sa.column("is_deleted", sa.Boolean()),
)


def _seed_permissions(inspector: sa.Inspector) -> None:
    """Insert missing system permissions and reconcile system role grants."""
    if not inspector.has_table("permissions") or not inspector.has_table("roles"):
        return
    bind = op.get_bind()
    existing = {
        code: permission_id
        for permission_id, code in bind.execute(
            sa.select(_permissions.c.id, _permissions.c.code)
        ).all()
    }
    for code in SYSTEM_PERMISSION_CODES:
        if code in existing:
            continue
        existing[code] = uuid4()
        bind.execute(
            _permissions.insert().values(
                id=existing[code],
                code=code,
                name=code.replace("_", " ").title(),
                description="System-defined permission.",
                is_system=True,
                is_active=True,
                is_deleted=False,
            )
        )
    role_ids = {
        code: role_id
        for role_id, code in bind.execute(sa.select(_roles.c.id, _roles.c.code)).all()
    }
    granted = set(
        bind.execute(
            sa.select(
                _role_permissions.c.role_id, _role_permissions.c.permission_id
            ).where(_role_permissions.c.is_deleted.is_(False))
        )
        .tuples()
        .all()
    )
    for role_code, codes in ROLE_PERMISSION_CODES.items():
        role_id = role_ids.get(role_code)
        if role_id is None:
            continue
        for code in codes:
            permission_id = existing.get(code)
            if permission_id is None or (role_id, permission_id) in granted:
                continue
            bind.execute(
                _role_permissions.insert().values(
                    id=uuid4(),
                    role_id=role_id,
                    permission_id=permission_id,
                    is_deleted=False,
                )
            )


def upgrade() -> None:
    """Create the register, seed its permissions, and copy the old numbers."""
    inspector = sa.inspect(op.get_bind())
    _create_tables(inspector)
    inspector = sa.inspect(op.get_bind())
    _copy_old_numbers(inspector)
    _seed_permissions(inspector)


def downgrade() -> None:
    """Drop the register; the old fields were never touched.

    Permissions stay, as every permission migration here leaves them: removing
    them would strip grants administrators may since have made.
    """
    inspector = sa.inspect(op.get_bind())
    for table in ("trade_licences", "trade_licence_types"):
        if inspector.has_table(table):
            op.drop_table(table)

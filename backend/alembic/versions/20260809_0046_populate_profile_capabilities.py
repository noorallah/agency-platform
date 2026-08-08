"""Populate the feature and module configuration for each business profile.

Only GENERIC had a real configuration; every other profile carried a single
mapping row with nothing enabled. A firm assigned PHARMACY therefore got no
batch tracking, no expiry tracking and no drug-licence capture — the profile
classified the firm but changed nothing.

The mappings below are the industry defaults. They are starting points an
administrator can change per profile through the business-framework API; nothing
here is hardcoded into module behaviour.
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260809_0046"
down_revision: str | Sequence[str] | None = "20260809_0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COMMON = ("BARCODE", "ATTACHMENTS")

#: profile code -> feature codes enabled for that industry.
PROFILE_FEATURES: dict[str, tuple[str, ...]] = {
    "GENERIC": _COMMON,
    "PHARMACY": (
        *_COMMON,
        "BATCH_TRACKING",
        "EXPIRY_TRACKING",
        "MANUFACTURING_DATE",
        "SHELF_LIFE",
        "DRUG_LICENSE",
        "PRESCRIPTION_REQUIRED",
    ),
    "FOOD": (
        *_COMMON,
        "BATCH_TRACKING",
        "EXPIRY_TRACKING",
        "MANUFACTURING_DATE",
        "SHELF_LIFE",
    ),
    "RESTAURANT": (
        "ATTACHMENTS",
        "RECIPE_MANAGEMENT",
        "KITCHEN_MANAGEMENT",
        "EXPIRY_TRACKING",
        "SHELF_LIFE",
    ),
    "ELECTRONICS": (
        *_COMMON,
        "SERIAL_NUMBER",
        "IMEI",
        "WARRANTY",
        "SERVICE_CONTRACTS",
    ),
    "GARMENTS": (*_COMMON, "QR_CODE"),
    "WHOLESALE": (
        *_COMMON,
        "MULTIPLE_WAREHOUSES",
        "TERRITORY",
        "COMMISSION",
        "BATCH_TRACKING",
    ),
    "AGENCY": (
        *_COMMON,
        "TERRITORY",
        "COMMISSION",
        "MULTIPLE_WAREHOUSES",
    ),
    "MANUFACTURING": (
        *_COMMON,
        "BATCH_TRACKING",
        "MANUFACTURING_DATE",
        "RECIPE_MANAGEMENT",
        "MULTIPLE_WAREHOUSES",
        "APPROVAL_WORKFLOW",
    ),
    "SERVICE": (
        "ATTACHMENTS",
        "SERVICE_CONTRACTS",
        "PROJECT_MANAGEMENT",
        "APPROVAL_WORKFLOW",
    ),
    "RETAIL": (*_COMMON, "QR_CODE", "EXPIRY_TRACKING"),
    # CUSTOM is intentionally left for the administrator to configure.
    "CUSTOM": (),
}

#: Modules every profile operates unless an administrator disables them.
_CORE_MODULES = (
    "DASHBOARD",
    "ADMINISTRATION",
    "SETTINGS",
    "MASTERS",
    "PRODUCTS",
    "PURCHASES",
    "SALES",
    "INVENTORY",
    "REPORTS",
    "ACCOUNTING",
)

#: Modules that only some industries operate.
PROFILE_MODULES: dict[str, tuple[str, ...]] = {
    "RESTAURANT": (*_CORE_MODULES, "KITCHEN", "RECIPES"),
    "MANUFACTURING": (*_CORE_MODULES, "RECIPES"),
    "SERVICE": (*_CORE_MODULES, "PROJECTS", "CONTRACTS"),
    "ELECTRONICS": (*_CORE_MODULES, "CONTRACTS"),
}

_profiles = sa.table(
    "business_profiles",
    sa.column("id", UUIDType()),
    sa.column("code", sa.String()),
    sa.column("is_deleted", sa.Boolean()),
)
_features = sa.table(
    "business_features",
    sa.column("id", UUIDType()),
    sa.column("code", sa.String()),
    sa.column("is_deleted", sa.Boolean()),
)
_modules = sa.table(
    "business_modules",
    sa.column("id", UUIDType()),
    sa.column("code", sa.String()),
    sa.column("is_deleted", sa.Boolean()),
)
_profile_features = sa.table(
    "profile_features",
    sa.column("id", UUIDType()),
    sa.column("business_profile_id", UUIDType()),
    sa.column("feature_id", UUIDType()),
    sa.column("is_enabled", sa.Boolean()),
    sa.column("is_deleted", sa.Boolean()),
)
_profile_modules = sa.table(
    "profile_modules",
    sa.column("id", UUIDType()),
    sa.column("business_profile_id", UUIDType()),
    sa.column("module_id", UUIDType()),
    sa.column("is_enabled", sa.Boolean()),
    sa.column("is_deleted", sa.Boolean()),
)


def upgrade() -> None:
    """Enable the industry-default features and modules for each profile."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("business_profiles"):
        return

    profiles = {
        code: pid
        for pid, code in bind.execute(
            sa.select(_profiles.c.id, _profiles.c.code).where(
                _profiles.c.is_deleted.is_(False)
            )
        ).all()
    }
    features = {
        code: fid
        for fid, code in bind.execute(
            sa.select(_features.c.id, _features.c.code).where(
                _features.c.is_deleted.is_(False)
            )
        ).all()
    }
    modules = {
        code: mid
        for mid, code in bind.execute(
            sa.select(_modules.c.id, _modules.c.code).where(
                _modules.c.is_deleted.is_(False)
            )
        ).all()
    }

    _apply(
        bind,
        table=_profile_features,
        target_column="feature_id",
        profiles=profiles,
        targets=features,
        wanted=PROFILE_FEATURES,
    )
    _apply(
        bind,
        table=_profile_modules,
        target_column="module_id",
        profiles=profiles,
        targets=modules,
        wanted={code: PROFILE_MODULES.get(code, _CORE_MODULES) for code in profiles},
    )


def _apply(
    bind: sa.Connection,
    *,
    table: sa.TableClause,
    target_column: str,
    profiles: dict[str, object],
    targets: dict[str, object],
    wanted: dict[str, tuple[str, ...]],
) -> None:
    """Upsert one profile-to-capability mapping table."""
    existing = {
        (profile_id, target_id): row_id
        for row_id, profile_id, target_id in bind.execute(
            sa.select(
                table.c.id,
                table.c.business_profile_id,
                sa.column(target_column),
            ).select_from(table)
        ).all()
    }
    for profile_code, codes in wanted.items():
        profile_id = profiles.get(profile_code)
        if profile_id is None:
            continue
        for code in codes:
            target_id = targets.get(code)
            if target_id is None:
                continue
            key = (profile_id, target_id)
            row_id = existing.get(key)
            if row_id is None:
                bind.execute(
                    table.insert().values(
                        {
                            "id": uuid4(),
                            "business_profile_id": profile_id,
                            target_column: target_id,
                            "is_enabled": True,
                            "is_deleted": False,
                        }
                    )
                )
            else:
                bind.execute(
                    table.update()
                    .where(table.c.id == row_id)
                    .values(is_enabled=True, is_deleted=False)
                )


def downgrade() -> None:
    """Leave the configuration in place.

    Disabling capabilities again would block writes for firms that have since
    started relying on them, which is worse than leaving the mappings enabled.
    """

"""Withdraw the business features a profile no longer decides.

Backlog 89, step 6. A product's behaviour follows its own switches, which
its goods type fills; no check reads the firm's profile for them any more.
The catalogue rows that said otherwise are removed, with every profile's
mapping to them:

* what goods look like -- batch, expiry, serial number, warranty,
  manufacturing date, shelf life, and barcode and QR code, which are plain
  product fields;
* territory, multiple warehouses and approval workflow, listed on some
  profiles and enforced nowhere, so every firm already used them;
* the six with no code behind them -- IMEI, kitchen, prescription, project,
  recipe and service contracts;
* ``SERIAL_TRACKING``, a code only the demo seeder ever wrote.

What stays is what is about the firm and is really enforced: attachments,
vehicle details, the drug licence, commission and batch PTR / PTS.

A profile's ``default_settings`` also loses ``inventory_tracking``,
``batch_required`` and ``expiry_required``: three notes about goods that
nothing read, now untrue of a firm that sells a medicine and a paint.

Per store: run ``scripts/migrate_all_stores.py``. Idempotent: a store that
holds no catalogue is passed over, and a second run finds nothing to remove.

Revision ID: 20261008_0353
Revises: 20261008_0352
Create Date: 2026-10-08

"""

import json
from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261008_0353"
down_revision: str | Sequence[str] | None = "20261008_0352"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: code -> (the id `20260801_0011` gave it, whether anything implemented it).
WITHDRAWN: dict[str, tuple[str, bool]] = {
    "BATCH_TRACKING": ("20000000-0000-0000-0000-000000000001", True),
    "EXPIRY_TRACKING": ("20000000-0000-0000-0000-000000000002", True),
    "MANUFACTURING_DATE": ("20000000-0000-0000-0000-000000000003", True),
    "WARRANTY": ("20000000-0000-0000-0000-000000000004", True),
    "SERIAL_NUMBER": ("20000000-0000-0000-0000-000000000005", True),
    "IMEI": ("20000000-0000-0000-0000-000000000006", False),
    "PRESCRIPTION_REQUIRED": ("20000000-0000-0000-0000-000000000008", False),
    "SHELF_LIFE": ("20000000-0000-0000-0000-000000000009", True),
    "RECIPE_MANAGEMENT": ("20000000-0000-0000-0000-00000000000A", False),
    "KITCHEN_MANAGEMENT": ("20000000-0000-0000-0000-00000000000B", False),
    "PROJECT_MANAGEMENT": ("20000000-0000-0000-0000-00000000000D", False),
    "TERRITORY": ("20000000-0000-0000-0000-00000000000F", True),
    "SERVICE_CONTRACTS": ("20000000-0000-0000-0000-000000000010", False),
    "BARCODE": ("20000000-0000-0000-0000-000000000011", True),
    "QR_CODE": ("20000000-0000-0000-0000-000000000012", True),
    "APPROVAL_WORKFLOW": ("20000000-0000-0000-0000-000000000014", True),
    "MULTIPLE_WAREHOUSES": ("20000000-0000-0000-0000-000000000015", True),
}
#: Written by the demo seeder alone; removed, and not put back by a downgrade.
_SEEDER_ONLY = ("SERIAL_TRACKING",)
_GOODS_SETTINGS = ("inventory_tracking", "batch_required", "expiry_required")

_features = sa.table(
    "business_features",
    sa.column("id", UUIDType()),
    sa.column("code", sa.String()),
    sa.column("name", sa.String()),
    sa.column("description", sa.Text()),
    sa.column("category", sa.String()),
    sa.column("default_enabled", sa.Boolean()),
    sa.column("is_active", sa.Boolean()),
    sa.column("is_implemented", sa.Boolean()),
    sa.column("version", sa.Integer()),
)
_profile_features = sa.table(
    "profile_features",
    sa.column("feature_id", UUIDType()),
)
_profiles = sa.table(
    "business_profiles",
    sa.column("id", UUIDType()),
    sa.column("default_settings", sa.JSON()),
)


def upgrade() -> None:
    """Remove the withdrawn features, their mappings and the three notes."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("business_features"):
        gone = list(
            bind.execute(
                sa.select(_features.c.id).where(
                    _features.c.code.in_([*WITHDRAWN, *_SEEDER_ONLY])
                )
            ).scalars()
        )
        if gone:
            # The mappings first: they hold the key to the catalogue row.
            if inspector.has_table("profile_features"):
                bind.execute(
                    _profile_features.delete().where(
                        _profile_features.c.feature_id.in_(gone)
                    )
                )
            bind.execute(_features.delete().where(_features.c.id.in_(gone)))
    if inspector.has_table("business_profiles"):
        _strip_goods_settings(bind)


def _strip_goods_settings(bind: sa.Connection) -> None:
    """Take the three notes about goods out of each profile that holds one."""
    rows = bind.execute(sa.select(_profiles.c.id, _profiles.c.default_settings)).all()
    for profile_id, settings in rows:
        held = json.loads(settings) if isinstance(settings, str) else settings
        if not isinstance(held, dict) or not any(k in held for k in _GOODS_SETTINGS):
            continue
        kept = {k: v for k, v in held.items() if k not in _GOODS_SETTINGS}
        bind.execute(
            _profiles.update()
            .where(_profiles.c.id == profile_id)
            .values(default_settings=kept)
        )


def downgrade() -> None:
    """Put the seventeen catalogue rows back, mapped to no profile.

    Which profile had which feature switched on is not kept, and the three
    notes on a profile are not written again: nothing read either.
    """
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("business_features"):
        return
    held = set(bind.execute(sa.select(_features.c.code)).scalars())
    for code, (raw_id, implemented) in WITHDRAWN.items():
        if code in held:
            continue
        title = code.replace("_", " ").title()
        bind.execute(
            _features.insert().values(
                id=UUID(raw_id),
                code=code,
                name=title,
                description=f"{title} control.",
                category="OPERATIONS",
                default_enabled=False,
                is_active=True,
                is_implemented=implemented,
                version=1,
            )
        )

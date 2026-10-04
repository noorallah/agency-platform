"""The asset classes every firm starts with (PG-13).

Useful lives are Schedule II's (Companies Act 2013) for the common case, with
a 5% residual value; the block rates are the Income-tax Rules' Appendix I
rates. All five depreciate on the straight line in the Companies Act book;
a firm that prefers WDV changes the class. None names its own accounts, so
each posts to the firm's fixed-asset control accounts until it does.

Seeded with the books (``seed_finance_setup``) and, for firms whose books were
already open, by migration ``20261005_0315``. Only a missing code is added,
so a class the firm changed or removed is left as it is.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.fixed_assets.models import AssetClass

#: (code, name, useful life in years, Income-tax block rate %)
DEFAULT_CLASSES: tuple[tuple[str, str, Decimal, Decimal], ...] = (
    ("PLANT", "Plant and Machinery", Decimal("15"), Decimal("15")),
    ("FURNITURE", "Furniture and Fittings", Decimal("10"), Decimal("10")),
    ("COMPUTERS", "Computers", Decimal("3"), Decimal("40")),
    ("VEHICLES", "Motor Vehicles", Decimal("8"), Decimal("15")),
    ("OFFICE_EQUIPMENT", "Office Equipment", Decimal("5"), Decimal("15")),
)
RESIDUAL_PERCENT = Decimal("5")


def seed_asset_classes(session: Session, *, firm_id: UUID, actor_id: UUID) -> int:
    """Add the default classes the firm has never had; return how many.

    A code the firm ever used -- removed ones included -- is not added back,
    so deleting a seeded class is a decision that stands.
    """
    used = set(
        session.scalars(
            select(AssetClass.code).where(AssetClass.firm_id == firm_id)
        ).all()
    )
    added = 0
    for code, name, life, block_rate in DEFAULT_CLASSES:
        if code in used:
            continue
        session.add(
            AssetClass(
                firm_id=firm_id,
                code=code,
                name=name,
                depreciation_method="SLM",
                useful_life_years=life,
                residual_percent=RESIDUAL_PERCENT,
                it_block_rate_percent=block_rate,
                is_active=True,
                created_by=actor_id,
                updated_by=actor_id,
            )
        )
        added += 1
    if added:
        session.flush()
    return added

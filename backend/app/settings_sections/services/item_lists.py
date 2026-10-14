"""The Item lists subject: the lists a firm's products are described by.

Every reader selects and nothing else, like the Tax subject's. One step can be
owed: **Units of Measure**, because a UOM group holds units and a conversion
rule converts one unit into another, so neither can be saved before a unit
exists. Every other step is OPTIONAL -- a product needs no category, brand or
packaging.

Units, UOM groups and packaging types carry no firm column: they are the
store's own reference lists, seeded with the store and shared by every firm in
it, so they are counted for the store. The rest are the firm's.

The hard orders are units before groups and conversion rules, a packaging type
before the levels that name it, and a principal before the brands it owns; the
rest of the order is **decided by the loop**: a new firm sets its units first.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.products.models.brand import Brand, Principal
from app.products.models.product import ProductCategory
from app.settings_sections.services.steps import (
    DONE,
    NONE_YET,
    OPTIONAL,
    TODO,
    SettingsStep,
    counted,
    counted_step,
)
from app.uom.models.uom import (
    ConversionRule,
    PackagingType,
    ProductPackagingLevel,
    Uom,
    UomGroup,
)


def _store_count(session: Session, model: type[Any]) -> int:
    """Count the store's live, active rows of a list that has no firm column."""
    return (
        session.scalar(
            select(func.count())
            .select_from(model)
            .where(model.is_deleted.is_(False), model.status == "ACTIVE")
        )
        or 0
    )


def _units_step(session: Session) -> SettingsStep:
    """Say whether the store holds any unit, which groups and rules need."""
    count = _store_count(session, Uom)
    if not count:
        return SettingsStep("uoms", TODO, NONE_YET)
    return SettingsStep("uoms", DONE, counted(count, "unit", "units"))


def _store_step(
    session: Session, model: type[Any], code: str, nouns: tuple[str, str]
) -> SettingsStep:
    """Count an optional store-wide list, or say it holds none."""
    count = _store_count(session, model)
    return SettingsStep(code, OPTIONAL, counted(count, *nouns) if count else NONE_YET)


def _packaging_levels_step(session: Session, firm_id: UUID) -> SettingsStep:
    """Count the firm's packaging levels and the products they belong to."""
    levels, products = session.execute(
        select(
            func.count(),
            func.count(func.distinct(ProductPackagingLevel.product_id)),
        ).where(
            ProductPackagingLevel.firm_id == firm_id,
            ProductPackagingLevel.is_deleted.is_(False),
            ProductPackagingLevel.status == "ACTIVE",
        )
    ).one()
    if not levels:
        return SettingsStep("packaging-levels", OPTIONAL, NONE_YET)
    detail = (
        f"{counted(levels, 'level', 'levels')} on "
        f"{counted(products, 'product', 'products')}"
    )
    return SettingsStep("packaging-levels", OPTIONAL, detail)


def item_lists_section(session: Session, firm_id: UUID) -> list[SettingsStep]:
    """Return the eight steps of the Item lists subject, in set-up order."""
    return [
        _units_step(session),
        _store_step(session, UomGroup, "uom-groups", ("group", "groups")),
        counted_step(
            session,
            ConversionRule,
            firm_id,
            "conversion-rules",
            ("rule", "rules"),
            ConversionRule.status == "ACTIVE",
        ),
        _store_step(session, PackagingType, "packaging-types", ("type", "types")),
        _packaging_levels_step(session, firm_id),
        counted_step(
            session,
            ProductCategory,
            firm_id,
            "product-categories",
            ("category", "categories"),
            ProductCategory.is_active.is_(True),
        ),
        counted_step(
            session,
            Principal,
            firm_id,
            "principals",
            ("principal", "principals"),
            Principal.is_active.is_(True),
        ),
        counted_step(
            session,
            Brand,
            firm_id,
            "brands",
            ("brand", "brands"),
            Brand.is_active.is_(True),
        ),
    ]


__all__ = ["item_lists_section"]

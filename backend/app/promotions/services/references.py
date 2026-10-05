"""Check that every master an offer names is one of this firm's (D-PRC-5).

An offer names masters in two places: the id-typed **conditions** (a product,
a category, a customer, a customer group, a branch, a territory, a route) and
the **benefits** (the product a `FREE_PRODUCT` gives away, the products of a
`COMBO_PRICE` set). None of them was looked up when the offer was written, so
an ACTIVE offer could give away a product id that did not exist, or another
firm's product, and every quotation and order it matched then answered 500:
the engine handed the document a gift line for a product the firm does not
hold. A condition on such an id only never matched; the benefit broke the
order screen.

The rule is the one `app/common/master_references.py` keeps for the masters:
the row must be **live** and **this firm's**, and one that is not is reported
as not found, which is all another firm's row should ever look like. It is
read off the *stored* shape -- a field key with its `value_text` /
`value_json`, an action type with its `parameters` -- so writing an offer,
revising it and copying it all ask through one function.

A salesman condition is not checked: `users` lives in the platform store and
the offer is written on the firm's own.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.branches.models import Branch
from app.core.database.entity import BaseEntity
from app.core.exceptions import ValidationError
from app.customers.models import Customer, CustomerGroup
from app.products.models import Product, ProductCategory
from app.promotions.schemas import (
    PromotionActionType,
    PromotionConditionOperator,
    PromotionField,
)
from app.sales.models import SalesTerritoryNode, TerritoryRouteProfile

#: ``{condition field: (master model, what to call it in a refusal)}``.
_CONDITION_MASTERS: Mapping[str, tuple[type[BaseEntity], str]] = {
    PromotionField.PRODUCT_ID.value: (Product, "product"),
    PromotionField.PRODUCT_CATEGORY_ID.value: (ProductCategory, "product category"),
    PromotionField.CUSTOMER_ID.value: (Customer, "customer"),
    PromotionField.CUSTOMER_GROUP_ID.value: (CustomerGroup, "customer group"),
    PromotionField.BRANCH_ID.value: (Branch, "branch"),
    PromotionField.TERRITORY_ID.value: (SalesTerritoryNode, "territory"),
    PromotionField.ROUTE_ID.value: (TerritoryRouteProfile, "route"),
}

_LIST_OPERATORS = frozenset(
    {
        PromotionConditionOperator.IN.value,
        PromotionConditionOperator.NOT_IN.value,
    }
)
_VALUELESS_OPERATORS = frozenset(
    {
        PromotionConditionOperator.EXISTS.value,
        PromotionConditionOperator.NOT_EXISTS.value,
    }
)


def live_row_ids(
    session: Session,
    model: type[BaseEntity],
    ids: Iterable[object],
    *,
    firm_id: UUID,
) -> set[UUID]:
    """Return which of ``ids`` are live rows of ``model`` belonging to the firm.

    An entry that is not a UUID at all is simply not among the answers.
    """
    wanted: set[UUID] = set()
    for item in ids:
        try:
            wanted.add(UUID(str(item).strip()))
        except ValueError:
            continue
    if not wanted:
        return set()
    statement = select(model.id).where(
        model.id.in_(wanted), model.is_deleted.is_(False)
    )
    if model is TerritoryRouteProfile:
        # A route carries no firm of its own; its territory does.
        statement = statement.join(
            SalesTerritoryNode,
            SalesTerritoryNode.id == TerritoryRouteProfile.territory_id,
        ).where(
            SalesTerritoryNode.firm_id == firm_id,
            SalesTerritoryNode.is_deleted.is_(False),
        )
    else:
        statement = statement.where(model.firm_id == firm_id)  # type: ignore[attr-defined]
    return set(session.scalars(statement))


def _is_live(found: set[UUID], value: object) -> bool:
    """Whether one stored id is among the rows that were found."""
    try:
        return UUID(str(value).strip()) in found
    except ValueError:
        return False


def assert_offer_references(
    session: Session,
    *,
    firm_id: UUID,
    conditions: Iterable[object],
    actions: Iterable[tuple[int, str, Mapping[str, object]]],
    offer: str | None = None,
) -> None:
    """Refuse an offer naming a master that is not a live row of this firm.

    ``conditions`` are objects carrying ``sequence``, ``field_key``,
    ``operator``, ``value_text`` and ``value_json`` -- a write schema or a
    stored row. ``actions`` are ``(sequence, action type, parameters)`` in the
    stored shape. ``offer`` prefixes the refusal with the offer's code where
    several are being written at once (a copy).

    Raises:
        ValidationError: Naming the condition or benefit, what it names, and
            that it was not found in this firm.

    """
    prefix = "" if offer is None else f"{offer}: "
    for condition in conditions:
        # Both are `StrEnum` on a write schema and plain text on a stored row.
        master = _CONDITION_MASTERS.get(str(getattr(condition, "field_key", "")))
        operator = str(getattr(condition, "operator", ""))
        if master is None or operator in _VALUELESS_OPERATORS:
            continue
        model, label = master
        if operator in _LIST_OPERATORS:
            named = list(getattr(condition, "value_json", None) or [])
        else:
            text = getattr(condition, "value_text", None)
            named = [] if text is None else [text]
        found = live_row_ids(session, model, named, firm_id=firm_id)
        if any(not _is_live(found, item) for item in named):
            raise ValidationError(
                f"{prefix}Condition {getattr(condition, 'sequence', 1)}: the "
                f"{label} was not found in this firm."
            )
    for sequence, kind, parameters in actions:
        if kind == PromotionActionType.FREE_PRODUCT.value:
            gift = parameters.get("free_product_id")
            if gift in (None, "None"):
                continue
            if not live_row_ids(session, Product, [gift], firm_id=firm_id):
                raise ValidationError(
                    f"{prefix}Benefit {sequence}: the free product was not "
                    "found in this firm."
                )
        elif kind == PromotionActionType.COMBO_PRICE.value:
            raw = parameters.get("items")
            items = raw if isinstance(raw, list) else []
            named = [
                item.get("product_id") for item in items if isinstance(item, Mapping)
            ]
            found = live_row_ids(session, Product, named, firm_id=firm_id)
            if any(not _is_live(found, item) for item in named):
                raise ValidationError(
                    f"{prefix}Benefit {sequence}: a product of the combo was "
                    "not found in this firm."
                )

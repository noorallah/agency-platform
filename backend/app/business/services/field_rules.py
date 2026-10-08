"""What a field rule may name, and how a screen reads it (backlog 89).

A rule in ``category_attribute_rules`` names one thing: a product category by
its code, a goods type, a customer group or a supplier type. The platform
keeps the shared rules and each firm its own; both pass through the checks
here, so the two screens cannot come to accept different rules.

The three kinds live in other modules, which import this package's services,
so their models are imported inside the functions that read them.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.business.models import (
    RULE_KIND_COLUMNS,
    AttributeDefinition,
    CategoryAttributeRule,
)
from app.business.schemas import CategoryAttributeRuleCreate
from app.core.exceptions import ConflictError, ValidationError

#: What a person calls each kind.
_KIND_LABELS = {
    "goods_type_id": "Goods type",
    "customer_group_id": "Customer group",
    "vendor_type_id": "Supplier type",
}


def assert_rule_target(
    session: Session,
    data: CategoryAttributeRuleCreate,
    field: AttributeDefinition,
    *,
    firm_id: UUID | None,
) -> None:
    """Refuse a rule whose kind does not exist, or does not suit its field.

    ``firm_id`` is the firm whose own rule this is, or None for a shared one.
    A shared rule can only name what is itself shared: a category code or a
    goods type of the shared catalogue. Customer groups and supplier types
    are each firm's own.

    Raises:
        ValidationError: If the kind is not one this firm can name, or the
            field belongs to another sort of record.

    """
    from app.customers.models import CustomerGroup
    from app.products.models import GoodsType
    from app.vendors.models import VendorType

    if data.category_code is not None:
        # A code, checked against nothing, as it always was: it bites where a
        # save passes that category and nowhere else.
        return
    if data.goods_type_id is not None:
        _assert_entity(field, RULE_KIND_COLUMNS["goods_type_id"], "a goods type")
        goods_type = session.get(GoodsType, data.goods_type_id)
        if (
            goods_type is None
            or goods_type.is_deleted
            or goods_type.firm_id not in (None, firm_id)
        ):
            raise ValidationError("That goods type is not one this rule can name.")
        return
    if firm_id is None:
        raise ValidationError(
            "A shared rule names a category or a shared goods type. Customer "
            "groups and supplier types are each firm's own: the firm's "
            "administrator keeps those rules."
        )
    if data.customer_group_id is not None:
        _assert_entity(
            field, RULE_KIND_COLUMNS["customer_group_id"], "a customer group"
        )
        group = session.get(CustomerGroup, data.customer_group_id)
        if group is None or group.is_deleted or group.firm_id != firm_id:
            raise ValidationError("That customer group is not this firm's.")
        return
    _assert_entity(field, RULE_KIND_COLUMNS["vendor_type_id"], "a supplier type")
    vendor_type = session.get(VendorType, data.vendor_type_id)
    if vendor_type is None or vendor_type.is_deleted or vendor_type.firm_id != firm_id:
        raise ValidationError("That supplier type is not this firm's.")


def assert_rule_new(
    session: Session,
    data: CategoryAttributeRuleCreate,
    *,
    firm_id: UUID | None,
    current: UUID | None = None,
) -> None:
    """Refuse a second live rule for the same field and the same thing.

    The partial unique keys hold a firm's own rules against a race; this is
    the message, and the only guard for a shared rule, whose null ``firm_id``
    no key compares.

    Raises:
        ConflictError: If such a rule already exists.

    """
    statement = select(CategoryAttributeRule.id).where(
        CategoryAttributeRule.attribute_definition_id == data.attribute_definition_id,
        CategoryAttributeRule.is_deleted.is_(False),
        (
            CategoryAttributeRule.firm_id.is_(None)
            if firm_id is None
            else CategoryAttributeRule.firm_id == firm_id
        ),
    )
    for column in ("category_code", *RULE_KIND_COLUMNS):
        value = getattr(data, column)
        attribute = getattr(CategoryAttributeRule, column)
        statement = statement.where(
            attribute.is_(None) if value is None else attribute == value
        )
    if current is not None:
        statement = statement.where(CategoryAttributeRule.id != current)
    if session.scalar(statement) is not None:
        raise ConflictError("A rule for this field and this kind already exists.")


def describe_rules(
    session: Session, rows: list[CategoryAttributeRule]
) -> dict[UUID, tuple[str | None, str | None, str | None]]:
    """Return each rule's field code, field name and what it applies to.

    Read once per table for the whole page rather than once per row: a rules
    grid is the shape that turns into a query per line without anybody
    noticing.
    """
    from app.customers.models import CustomerGroup
    from app.products.models import GoodsType
    from app.vendors.models import VendorType

    field_ids = {row.attribute_definition_id for row in rows}
    fields = (
        {
            field_id: (code, name)
            for field_id, code, name in session.execute(
                select(
                    AttributeDefinition.id,
                    AttributeDefinition.code,
                    AttributeDefinition.name,
                ).where(AttributeDefinition.id.in_(field_ids))
            ).all()
        }
        if field_ids
        else {}
    )
    names: dict[str, dict[UUID, str]] = {
        column: _names(session, model, {getattr(row, column) for row in rows} - {None})
        for column, model in (
            ("goods_type_id", GoodsType),
            ("customer_group_id", CustomerGroup),
            ("vendor_type_id", VendorType),
        )
    }
    described: dict[UUID, tuple[str | None, str | None, str | None]] = {}
    for row in rows:
        applies_to = (
            f"Category: {row.category_code}" if row.category_code is not None else None
        )
        for column, label in _KIND_LABELS.items():
            value = getattr(row, column)
            if value is not None:
                applies_to = f"{label}: {names[column].get(value, 'removed')}"
        code, name = fields.get(row.attribute_definition_id, (None, None))
        described[row.id] = (code, name, applies_to)
    return described


def _names(session: Session, model: type, ids: set[UUID]) -> dict[UUID, str]:
    """Return the names of some rows of one table, in one statement."""
    if not ids:
        return {}
    return {
        row_id: name
        for row_id, name in session.execute(
            select(model.id, model.name).where(model.id.in_(ids))  # type: ignore[attr-defined]
        ).all()
    }


def _assert_entity(field: AttributeDefinition, entity_type: str, kind: str) -> None:
    """Refuse a rule that names a kind its field's records do not have."""
    if field.entity_type != entity_type:
        raise ValidationError(
            f"{field.code} is a field on {field.entity_type.lower()} records, "
            f"so a rule for it cannot name {kind}."
        )

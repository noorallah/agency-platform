"""A firm's own fields on its documents (MST-6, decision A132).

Masters gained custom fields through ``AttributeService``; documents use
the same service, one small value table each. This module is the one place
the document services call, so six of them do not each grow a copy:

* :func:`store` -- replace a document's values from its write body;
* :func:`responses_for_many` -- every value of a page of documents, one read;
* :func:`carry` -- copy a source document's values onto a document raised from
  it, field by field where the target has a field of the same name (an order
  raised from a quotation keeps the site name);
* :func:`printed` -- the fields marked *show on print*, label and text, for the
  print services' references block.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.business.models.document_attributes import (
    DeliveryNoteAttributeValue,
    PurchaseInvoiceAttributeValue,
    PurchaseOrderAttributeValue,
    QuotationAttributeValue,
    SalesInvoiceAttributeValue,
    SalesOrderAttributeValue,
)
from app.business.models.framework import (
    AttributeDefinition,
    AttributeEntityType,
    AttributeValueBase,
)
from app.business.schemas import AttributeValueInput, AttributeValueResponse
from app.business.services.attribute_service import AttributeInput, AttributeService

VALUE_MODELS: dict[AttributeEntityType, type[AttributeValueBase]] = {
    AttributeEntityType.QUOTATION: QuotationAttributeValue,
    AttributeEntityType.SALES_ORDER: SalesOrderAttributeValue,
    AttributeEntityType.DELIVERY_NOTE: DeliveryNoteAttributeValue,
    AttributeEntityType.SALES_INVOICE: SalesInvoiceAttributeValue,
    AttributeEntityType.PURCHASE_ORDER: PurchaseOrderAttributeValue,
    AttributeEntityType.PURCHASE_INVOICE: PurchaseInvoiceAttributeValue,
}


def store(
    session: Session,
    entity: AttributeEntityType,
    owner_id: UUID,
    attributes: Sequence[AttributeValueInput],
    *,
    firm_id: UUID,
    actor_id: UUID,
) -> None:
    """Replace a document's values; the caller commits.

    Raises:
        ValidationError: If a field does not apply, a value is of the wrong
            type, or a mandatory field is missing.

    """
    AttributeService(session).replace_values(
        VALUE_MODELS[entity],
        owner_id,
        [
            AttributeInput(
                attribute_definition_id=item.attribute_definition_id,
                value=item.value,
            )
            for item in attributes
        ],
        firm_id=firm_id,
        actor_id=actor_id,
    )


def responses_for_many(
    session: Session, entity: AttributeEntityType, owner_ids: Sequence[UUID]
) -> dict[UUID, list[AttributeValueResponse]]:
    """Return every value of these documents, by document, in one read."""
    rows = AttributeService(session).value_rows_for_many(
        VALUE_MODELS[entity], list(owner_ids)
    )
    return {
        owner_id: [AttributeValueResponse.model_validate(row) for row in values]
        for owner_id, values in rows.items()
    }


def _value(row: AttributeValueBase) -> str | Decimal | date | bool | None:
    """Return whichever typed column a value row fills."""
    for column in ("value_text", "value_number", "value_date", "value_boolean"):
        held = getattr(row, column)
        if held is not None:
            return held  # type: ignore[no-any-return]
    return None


def carry(
    session: Session,
    source: AttributeEntityType,
    source_id: UUID,
    target: AttributeEntityType,
    target_id: UUID,
    *,
    firm_id: UUID,
    actor_id: UUID,
) -> None:
    """Copy a source document's values to the document raised from it.

    Matched on the field's name, ignoring case: a code is unique within a
    firm across every record, so a firm that wants the buyer's PO on the
    order and the invoice defines a "Buyer PO" field on each. A field the
    target does not have is left behind; a value it already holds is kept.
    Stages; the caller commits.
    """
    model = VALUE_MODELS[source]
    held = list(
        session.execute(
            select(AttributeDefinition.name, model)
            .join(
                AttributeDefinition,
                AttributeDefinition.id == model.attribute_definition_id,
            )
            .where(model.owner_column() == source_id, model.is_deleted.is_(False))
        ).all()
    )
    if not held:
        return
    service = AttributeService(session)
    targets = {
        definition.name.strip().lower(): definition
        for definition in service.definitions_for(target, firm_id=firm_id)
    }
    already = {
        row.attribute_definition_id: row
        for row in service.value_rows(VALUE_MODELS[target], target_id)
    }
    inputs = [
        AttributeInput(attribute_definition_id=definition_id, value=_value(row))
        for definition_id, row in already.items()
        if _value(row) is not None
    ]
    for name, row in held:
        definition = targets.get(str(name).strip().lower())
        value = _value(row)
        if definition is None or definition.id in already or value is None:
            continue
        inputs.append(
            AttributeInput(attribute_definition_id=definition.id, value=value)
        )
    if inputs:
        service.replace_values(
            VALUE_MODELS[target],
            target_id,
            inputs,
            firm_id=firm_id,
            actor_id=actor_id,
        )


def printed(
    session: Session, entity: AttributeEntityType, owner_id: UUID
) -> list[tuple[str, str]]:
    """Return the fields marked to print, as (label, text), in label order."""
    model = VALUE_MODELS[entity]
    rows = session.execute(
        select(AttributeDefinition.name, model)
        .join(
            AttributeDefinition, AttributeDefinition.id == model.attribute_definition_id
        )
        .where(
            model.owner_column() == owner_id,
            model.is_deleted.is_(False),
            AttributeDefinition.show_on_print.is_(True),
        )
        .order_by(AttributeDefinition.name)
    ).all()
    answer: list[tuple[str, str]] = []
    for name, row in rows:
        value = _value(row)
        if value is None or value == "":
            continue
        if isinstance(value, bool):
            text = "Yes" if value else "No"
        elif isinstance(value, date):
            text = value.strftime("%d-%m-%Y")
        elif isinstance(value, Decimal):
            text = f"{value.normalize():f}"
        else:
            text = str(value)
        answer.append((name, text))
    return answer


#: How a line names its source document, and which fields it carries.
_SOURCE_ENTITIES: dict[str, AttributeEntityType] = {
    "SALES_QUOTATION": AttributeEntityType.QUOTATION,
    "QUOTATION": AttributeEntityType.QUOTATION,
    "SALES_ORDER": AttributeEntityType.SALES_ORDER,
    "DELIVERY_NOTE": AttributeEntityType.DELIVERY_NOTE,
    "PURCHASE_ORDER": AttributeEntityType.PURCHASE_ORDER,
}


def carry_from_sources(
    session: Session,
    target: AttributeEntityType,
    target_id: UUID,
    sources: Sequence[tuple[str, UUID]],
    *,
    firm_id: UUID,
    actor_id: UUID,
) -> None:
    """Carry fields from every document a new one was raised from, in order.

    The first source to hold a field gives it; a goods receipt passes on its
    purchase order's. Stages; the caller commits.
    """
    from app.goods_receipt.models import GoodsReceipt

    seen: set[tuple[str, UUID]] = set()
    for kind, source_id in sources:
        if kind == "GOODS_RECEIPT":
            order_id = session.scalar(
                select(GoodsReceipt.purchase_order_id).where(
                    GoodsReceipt.id == source_id
                )
            )
            if order_id is None:
                continue
            kind, source_id = "PURCHASE_ORDER", order_id
        entity = _SOURCE_ENTITIES.get(kind)
        if entity is None or (kind, source_id) in seen:
            continue
        seen.add((kind, source_id))
        carry(
            session,
            entity,
            source_id,
            target,
            target_id,
            firm_id=firm_id,
            actor_id=actor_id,
        )

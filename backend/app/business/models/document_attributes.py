"""Custom field values on documents (MST-6, decision A132).

One small table per document, as the masters have, so a value carries a
real foreign key to its document and can be indexed for list filters; the
behaviour is ``AttributeService``'s, parameterised by the model.
"""

from typing import ClassVar
from uuid import UUID

from sqlalchemy import ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.business.models.framework import AttributeEntityType, AttributeValueBase
from app.core.database.types import UUIDType


class QuotationAttributeValue(AttributeValueBase):
    """Store one custom field value for a quotation."""

    __tablename__ = "quotation_attribute_values"
    __table_args__ = (
        UniqueConstraint(
            "quotation_id",
            "attribute_definition_id",
            name="UQ_quotation_attribute_values_owner_attribute",
        ),
        Index("IX_quotation_attribute_values_firm_text", "firm_id", "value_text"),
    )

    ENTITY_TYPE: ClassVar[AttributeEntityType] = AttributeEntityType.QUOTATION
    OWNER_COLUMN: ClassVar[str] = "quotation_id"

    quotation_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_quotations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class SalesOrderAttributeValue(AttributeValueBase):
    """Store one custom field value for a sales order."""

    __tablename__ = "sales_order_attribute_values"
    __table_args__ = (
        UniqueConstraint(
            "sales_order_id",
            "attribute_definition_id",
            name="UQ_sales_order_attribute_values_owner_attribute",
        ),
        Index("IX_sales_order_attribute_values_firm_text", "firm_id", "value_text"),
    )

    ENTITY_TYPE: ClassVar[AttributeEntityType] = AttributeEntityType.SALES_ORDER
    OWNER_COLUMN: ClassVar[str] = "sales_order_id"

    sales_order_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class DeliveryNoteAttributeValue(AttributeValueBase):
    """Store one custom field value for a delivery note."""

    __tablename__ = "delivery_note_attribute_values"
    __table_args__ = (
        UniqueConstraint(
            "delivery_note_id",
            "attribute_definition_id",
            name="UQ_delivery_note_attribute_values_owner_attribute",
        ),
        Index("IX_delivery_note_attribute_values_firm_text", "firm_id", "value_text"),
    )

    ENTITY_TYPE: ClassVar[AttributeEntityType] = AttributeEntityType.DELIVERY_NOTE
    OWNER_COLUMN: ClassVar[str] = "delivery_note_id"

    delivery_note_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("delivery_notes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class SalesInvoiceAttributeValue(AttributeValueBase):
    """Store one custom field value for a sales invoice."""

    __tablename__ = "sales_invoice_attribute_values"
    __table_args__ = (
        UniqueConstraint(
            "sales_invoice_id",
            "attribute_definition_id",
            name="UQ_sales_invoice_attribute_values_owner_attribute",
        ),
        Index("IX_sales_invoice_attribute_values_firm_text", "firm_id", "value_text"),
    )

    ENTITY_TYPE: ClassVar[AttributeEntityType] = AttributeEntityType.SALES_INVOICE
    OWNER_COLUMN: ClassVar[str] = "sales_invoice_id"

    sales_invoice_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class PurchaseOrderAttributeValue(AttributeValueBase):
    """Store one custom field value for a purchase order."""

    __tablename__ = "purchase_order_attribute_values"
    __table_args__ = (
        UniqueConstraint(
            "purchase_order_id",
            "attribute_definition_id",
            name="UQ_purchase_order_attribute_values_owner_attribute",
        ),
        Index("IX_purchase_order_attribute_values_firm_text", "firm_id", "value_text"),
    )

    ENTITY_TYPE: ClassVar[AttributeEntityType] = AttributeEntityType.PURCHASE_ORDER
    OWNER_COLUMN: ClassVar[str] = "purchase_order_id"

    purchase_order_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class PurchaseInvoiceAttributeValue(AttributeValueBase):
    """Store one custom field value for a purchase invoice."""

    __tablename__ = "purchase_invoice_attribute_values"
    __table_args__ = (
        UniqueConstraint(
            "purchase_invoice_id",
            "attribute_definition_id",
            name="UQ_purchase_invoice_attribute_values_owner_attribute",
        ),
        Index(
            "IX_purchase_invoice_attribute_values_firm_text", "firm_id", "value_text"
        ),
    )

    ENTITY_TYPE: ClassVar[AttributeEntityType] = AttributeEntityType.PURCHASE_INVOICE
    OWNER_COLUMN: ClassVar[str] = "purchase_invoice_id"

    purchase_invoice_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("purchase_invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


__all__ = [
    "QuotationAttributeValue",
    "SalesOrderAttributeValue",
    "DeliveryNoteAttributeValue",
    "SalesInvoiceAttributeValue",
    "PurchaseOrderAttributeValue",
    "PurchaseInvoiceAttributeValue",
]

"""Validated contracts for delivery notes."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.batch_serial.schemas import PickedSerial
from app.business.schemas import AttributeValueInput, AttributeValueResponse
from app.core.validation import NumberedOnce
from app.core.validation.common import normalize_gstin

#: How goods can travel, as an e-way bill names it.
TransportModeValue = Literal["ROAD", "RAIL", "AIR", "SHIP"]
#: Who pays the carrier (backlog 87 #5).
FreightTermsValue = Literal["PAID", "TO_PAY", "TO_BE_BILLED"]
#: Why a delivery note's goods go out (backlog 77 row 3, decision A35).
ChallanReasonValue = Literal[
    "SALE", "ROUTE_SALE", "ON_APPROVAL", "QUANTITY_UNKNOWN", "JOB_WORK", "OTHER"
]


class DeliveryNoteSchema(BaseModel):
    """Apply strict input and ORM response behavior."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class DeliveryNoteStatus(StrEnum):
    """Supported delivery note lifecycle statuses."""

    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    DISPATCHED = "DISPATCHED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"


class DeliveryNoteAttachmentWrite(DeliveryNoteSchema):
    """Carry one delivery note attachment into a request."""

    file_name: str = Field(min_length=1, max_length=260)
    mime_type: str | None = Field(default=None, max_length=120)
    file_path: str = Field(min_length=1, max_length=1024)
    attachment_kind: str = Field(
        default="DELIVERY_NOTE_FILE", min_length=1, max_length=40
    )


class DeliveryNoteNoteWrite(DeliveryNoteSchema):
    """Carry one delivery note note into a request."""

    note_type: str = Field(default="INTERNAL", min_length=1, max_length=30)
    note: str = Field(min_length=1)


class DeliveryNoteBatchPick(DeliveryNoteSchema):
    """One batch a delivery line takes, and how much of it (79)."""

    batch_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)


class DeliveryNoteLineWrite(DeliveryNoteSchema):
    """Carry one delivery note line into a request."""

    sales_order_line_id: UUID
    line_number: int = Field(ge=1)
    description: str | None = Field(default=None, max_length=500)
    current_delivery_quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    #: None means the caller said nothing, so the line ships the order line's
    #: free goods in proportion to the quantity it ships. Zero is an answer:
    #: none are shipped (D-PRC-4).
    free_quantity: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=4
    )
    damaged_quantity: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    #: None means the caller said nothing, so the price is inherited from the
    #: order line being shipped. Zero is an answer: goods given away.
    unit_price: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=4
    )
    #: None means the caller said nothing, so the customer's standing
    #: discount applies. Zero means they said no discount.
    discount_percent: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=9, decimal_places=4
    )
    discount_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=4
    )
    tax_profile_id: UUID | None = None
    packaging_type_id: UUID | None = None
    sales_uom_id: UUID | None = None
    inventory_uom_id: UUID | None = None
    warehouse_id: UUID | None = None
    storage_node_id: UUID | None = None
    batch_number: str | None = Field(default=None, max_length=120)
    serial_numbers: str | None = None
    #: Which serialised units this line ships, for a serial-tracked product:
    #: the storekeeper picks them from the product's AVAILABLE serials in the
    #: line's warehouse, and dispatch refuses until there is one per unit
    #: leaving. None (or absent) leaves the line's picks as they are; an empty
    #: list clears them. A product nobody tracks by serial takes none.
    serial_ids: list[UUID] | None = Field(default=None, max_length=10000)
    #: Which batches this line takes, in stock units (backlog 79, A38). None
    #: leaves the line's choice as it was -- none means earliest expiry first
    #: at dispatch -- and an empty list clears it back to that.
    batches: list[DeliveryNoteBatchPick] | None = Field(default=None, max_length=200)
    manufacturing_date: date | None = None
    expiry_date: date | None = None
    remarks: str | None = None

    @model_validator(mode="after")
    def _ships_something(self) -> "DeliveryNoteLineWrite":
        """Refuse a line that delivers nothing at all (D-SELL-53).

        A quantity of 0 stands where the line carries free goods, or records
        goods that arrived damaged. With neither it ships nothing, and a bill
        of it could never be approved. A line silent about free goods may
        inherit some from its order line, so the service judges that one.
        """
        if (
            self.current_delivery_quantity <= 0
            and self.free_quantity is not None
            and self.free_quantity <= 0
            and self.damaged_quantity <= 0
        ):
            raise ValueError(
                f"Line {self.line_number} delivers a quantity of 0 and supplies "
                "nothing free. Type a quantity, or leave the line off the note."
            )
        return self


class DeliveryNoteCreate(DeliveryNoteSchema):
    """Create one delivery note."""

    #: The firm's own fields on the document (MST-6). Replaced whole when
    #: sent; an update that omits them leaves them alone.
    attributes: list[AttributeValueInput] = Field(default_factory=list, max_length=100)

    sales_order_id: UUID
    delivery_date: date
    #: Where this dispatch goes (backlog 67 row 3). None inherits the order's
    #: ship-to; a note may name another of the customer's addresses when a
    #: part goes elsewhere. On an update, leaving it out keeps the note's own.
    shipping_address_id: UUID | None = None
    vehicle: str | None = Field(default=None, max_length=120)
    driver: str | None = Field(default=None, max_length=120)
    #: How the goods travel (backlog 67 row 5). On an update, leaving any of
    #: these out keeps the note's own.
    #: The carrier from the transporter master (backlog 87 #5). Naming
    #: one fills the name, the id and the mode below wherever this
    #: request leaves them blank.
    transporter_id: UUID | None = None
    #: Who pays the carrier. Absent on an update keeps the note's own.
    freight_terms: FreightTermsValue | None = None
    transporter_name: str | None = Field(default=None, max_length=200)
    transporter_gstin: str | None = Field(default=None, max_length=20)
    transport_mode: TransportModeValue | None = None
    lr_number: str | None = Field(default=None, max_length=60)
    lr_date: date | None = None
    distance_km: int | None = Field(default=None, ge=0, le=4000)
    #: Why the goods go out (backlog 77 row 3). Absent on a new note is SALE;
    #: absent on an update keeps the note's own.
    challan_reason: ChallanReasonValue | None = None
    #: Required with OTHER, ignored with any other reason.
    challan_reason_note: str | None = Field(default=None, max_length=200)
    remarks: str | None = None
    additional_charges: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    round_off: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=4)
    delivery_note_number: str | None = Field(default=None, max_length=60)
    #: A discount on the whole document, taken off what the lines discounted
    #: to and split across them so the tax is charged on the reduced value.
    #: An amount beats a rate, exactly as on a line.
    bill_discount_percent: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=9, decimal_places=4
    )
    bill_discount_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=4
    )
    #: What the customer is charged for delivery. Part of the taxable value:
    #: it is split across the lines and taxed with them, because delivery
    #: charged by the seller is ancillary to the supply of the goods.
    #: `additional_charges` stays outside the tax, for additions that really
    #: are outside it.
    freight_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=4
    )
    #: Each line numbered once (D-PRC-60).
    lines: Annotated[list[DeliveryNoteLineWrite], NumberedOnce] = Field(
        min_length=1, max_length=1000
    )
    attachments: list[DeliveryNoteAttachmentWrite] = Field(
        default_factory=list, max_length=500
    )
    notes: list[DeliveryNoteNoteWrite] = Field(default_factory=list, max_length=500)

    @field_validator("delivery_note_number", mode="before")
    @classmethod
    def _normalize_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        token = value.strip().upper()
        return token or None

    @field_validator("transporter_gstin", mode="before")
    @classmethod
    def _normalize_transporter_gstin(cls, value: str | None) -> str | None:
        """Refuse a transporter GSTIN that is not the shape of one."""
        return normalize_gstin(value)

    @field_validator("transport_mode", mode="before")
    @classmethod
    def _normalize_mode(cls, value: str | None) -> str | None:
        """Accept the mode in any case; a blank is no mode."""
        if value is None:
            return None
        token = value.strip().upper()
        return token or None


class DeliveryProofAttachmentWrite(DeliveryNoteSchema):
    """The photo or signed copy a proof of delivery carries."""

    file_name: str = Field(min_length=1, max_length=260)
    mime_type: str | None = Field(default=None, max_length=120)
    file_path: str = Field(min_length=1, max_length=1024)


class DeliveryProofWrite(DeliveryNoteSchema):
    """Record that the customer received a dispatched note (backlog 67 row 6)."""

    #: When the goods were received, as the proof says. A naive value is
    #: read as UTC, like every timestamp here.
    delivered_at: datetime
    received_by: str = Field(min_length=1, max_length=120)
    remarks: str | None = None
    #: A photo of the signed challan or the signature itself, kept with the
    #: note's attachments as ``PROOF_OF_DELIVERY``.
    attachment: DeliveryProofAttachmentWrite | None = None

    @field_validator("received_by")
    @classmethod
    def _named(cls, value: str) -> str:
        """Refuse a name that is only spaces."""
        token = value.strip()
        if not token:
            raise ValueError("Name who received the goods.")
        return token


class DeliveryNoteUpdate(DeliveryNoteCreate):
    """Replace one delivery note."""

    pass


class DeliveryNoteImportRequest(DeliveryNoteSchema):
    """Import a validated batch of delivery notes."""

    records: list[DeliveryNoteCreate] = Field(min_length=1, max_length=500)


class DeliveryNoteAttachmentResponse(DeliveryNoteSchema):
    """Return one delivery note attachment."""

    id: UUID
    delivery_note_id: UUID
    file_name: str
    mime_type: str | None
    file_path: str
    attachment_kind: str
    created_at: datetime
    updated_at: datetime


class DeliveryNoteNoteResponse(DeliveryNoteSchema):
    """Return one delivery note note."""

    id: UUID
    note_type: str
    note: str
    created_at: datetime
    updated_at: datetime


class DeliveryNoteLineResponse(DeliveryNoteSchema):
    """Return one delivery note line."""

    id: UUID
    delivery_note_id: UUID
    line_number: int
    sales_order_line_id: UUID
    product_id: UUID
    # As on the sales invoice line: `description` is nullable and the seeded
    # documents leave it null, so a client holding a line otherwise has only
    # a UUID to label it with.
    product_code: str | None = None
    product_name: str | None = None
    description: str | None
    ordered_quantity: Decimal
    reserved_quantity: Decimal
    previously_delivered_quantity: Decimal
    current_delivery_quantity: Decimal
    free_quantity: Decimal
    delivered_quantity: Decimal
    remaining_quantity: Decimal
    damaged_quantity: Decimal
    short_shipment_quantity: Decimal
    sales_uom_id: UUID | None
    inventory_uom_id: UUID | None
    packaging_type_id: UUID | None
    conversion_factor: Decimal
    conversion_version: int | None
    unit_price: Decimal
    discount_percent: Decimal
    discount_amount: Decimal
    gross_amount: Decimal
    tax_profile_id: UUID | None
    tax_amount: Decimal
    #: This line's share of the document's bill discount.
    bill_discount_amount: Decimal
    #: This line's share of the document's freight.
    freight_amount: Decimal = Decimal("0")
    net_amount: Decimal
    warehouse_id: UUID | None
    storage_node_id: UUID | None
    batch_number: str | None
    serial_numbers: str | None
    manufacturing_date: date | None
    expiry_date: date | None
    released_reservation_transaction_id: UUID | None
    inventory_transaction_id: UUID | None
    remarks: str | None
    #: The serialised units this line names -- picked while it is a draft,
    #: gone once it is dispatched.
    serials: list[PickedSerial] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    #: The batches the line takes, as chosen; empty means earliest expiry
    #: first at dispatch (backlog 79).
    batches: list[DeliveryNoteBatchPick] = Field(default_factory=list)
    #: The tax rule that decided the line and its version; null when the
    #: profile alone did (GST-8).
    tax_rule_code: str | None = None
    tax_rule_version: int | None = None


class DeliveryNoteResponse(DeliveryNoteSchema):
    """Return one delivery note."""

    #: The firm's own fields on the document (MST-6).
    attributes: list[AttributeValueResponse] = Field(default_factory=list)
    #: How many uploaded files the note carries (SG-6), so a list can show a
    #: paper clip without asking per row. Counted once for the page.
    attached_file_count: int = 0

    id: UUID
    #: The optimistic-concurrency version, published so a client can send
    #: it back as ``If-Match``. It rides in the body as well as the ETag
    #: header because a list carries many records and a header carries
    #: one — and this desktop edits from list rows.
    version: int
    firm_id: UUID
    sales_order_id: UUID
    customer_id: UUID
    #: Who the note is for, by name. A return's "Returned against" picker
    #: listed every customer's notes by number and date alone, so a note of
    #: the wrong customer was chosen and credited them instead (plan item
    #: 9.22, 2026-09-13).
    customer_name: str = ""
    branch_id: UUID
    warehouse_id: UUID
    business_profile_id: UUID | None
    salesman_id: UUID | None
    territory_id: UUID | None
    route_id: UUID | None
    delivery_note_number: str
    delivery_date: date
    sales_order_reference: str
    #: The ship-to address the note names, inherited from the order.
    shipping_address_id: UUID | None = None
    vehicle: str | None
    driver: str | None
    #: How the goods travel (backlog 67 row 5).
    transporter_id: UUID | None = None
    freight_terms: str | None = None
    transporter_name: str | None = None
    transporter_gstin: str | None = None
    transport_mode: str | None = None
    lr_number: str | None = None
    #: Why the goods go out, and the firm's words for OTHER (backlog 77).
    challan_reason: str = "SALE"
    challan_reason_note: str | None = None
    lr_date: date | None = None
    distance_km: int | None = None
    remarks: str | None
    status: DeliveryNoteStatus
    total_ordered_quantity: Decimal
    total_previously_delivered_quantity: Decimal
    total_current_delivery_quantity: Decimal
    total_free_quantity: Decimal
    #: The customer's standing discount on the day this was raised.
    customer_discount_percent: Decimal
    #: What was taken off the whole document, and the rate it represents.
    bill_discount_percent: Decimal
    bill_discount_amount: Decimal
    #: What was charged for delivery, split across the lines and taxed there.
    freight_amount: Decimal = Decimal("0")
    line_discount_total: Decimal
    subtotal: Decimal
    tax_total: Decimal
    additional_charges: Decimal
    round_off: Decimal
    grand_total: Decimal
    approved_at: datetime | None
    dispatched_at: datetime | None
    completed_at: datetime | None
    closed_at: datetime | None
    cancel_reason: str | None
    close_reason: str | None
    #: Proof of delivery (backlog 67 row 6): a flag beside the status.
    is_delivered: bool = False
    delivered_at: datetime | None = None
    delivery_received_by: str | None = None
    delivery_remarks: str | None = None
    delivery_recorded_at: datetime | None = None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    lines: list[DeliveryNoteLineResponse] = Field(default_factory=list)
    attachments: list[DeliveryNoteAttachmentResponse] = Field(default_factory=list)
    notes: list[DeliveryNoteNoteResponse] = Field(default_factory=list)
    duplicate_warning: str | None = None


class DeliveryNoteListFilters(DeliveryNoteSchema):
    """Narrow a delivery note list to the rows a caller asked for."""

    sales_order_id: UUID | None = None
    customer_id: UUID | None = None
    branch_id: UUID | None = None
    warehouse_id: UUID | None = None
    status: DeliveryNoteStatus | None = None
    delivery_from: date | None = None
    delivery_to: date | None = None
    #: Only notes whose goods have left with no proof of delivery yet.
    awaiting_delivery_proof: bool = False
    include_deleted: bool = False


class DeliveryNoteSummary(DeliveryNoteSchema):
    """Aggregate delivery note counts for the visible firm scope."""

    total: int
    draft: int
    approved: int
    dispatched: int
    completed: int
    cancelled: int
    closed: int
    total_value: Decimal
    pending_orders: int
    partial_orders: int
    #: Dispatched or completed, with no proof of delivery (67 row 6).
    awaiting_delivery_proof: int = 0


class DeliveryNoteRegisterRecord(DeliveryNoteSchema):
    """One row of the delivery note register report."""

    delivery_note_id: UUID
    delivery_note_number: str
    delivery_date: date
    sales_order_id: UUID
    sales_order_number: str
    customer_id: UUID
    #: Each id keeps a name beside it: the grid derives its columns from the
    #: row, so a register of ids alone showed three columns of UUIDs
    #: (D-RPT-17).
    customer_name: str
    branch_id: UUID
    branch_name: str
    warehouse_id: UUID
    warehouse_name: str
    status: DeliveryNoteStatus
    grand_total: Decimal


class DeliveryNoteByDimensionRecord(DeliveryNoteSchema):
    """One row of the delivery note by dimension report."""

    dimension_id: UUID | None
    dimension_name: str
    note_count: int
    delivered_quantity: Decimal
    total_value: Decimal


class DeliveryNoteOrderProgressRecord(DeliveryNoteSchema):
    """One row of the delivery note order progress report."""

    sales_order_id: UUID
    sales_order_number: str
    ordered_quantity: Decimal
    delivered_quantity: Decimal
    pending_quantity: Decimal
    status: str

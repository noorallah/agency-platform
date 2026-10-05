"""Rate contracts (blanket orders) with a supplier (PG-9, backlog 86 #2).

A rate contract agrees, for a period, the rate and discount a supplier will
charge for a list of products, and optionally how much of each. It is typed
as a DRAFT and approved to ACTIVE, which needs ``PURCHASE_APPROVE``; from then
on a purchase order on that supplier dated inside the period takes the
contract's rate for a line with no typed price, ahead of the supplier's price
list and catalogue (``resolve_supplier_unit_price``). Those orders are the
contract's *releases*.

Nothing about what has been drawn is stored. The drawn quantity of a line is
the sum of the approved, uncancelled order lines that name it, so cancelling a
release gives its quantity back with nothing to reverse. Drawing past the
contracted quantity warns -- on the order and in its approval -- and never
refuses.

*Expired* is not a status anybody sets: an active contract whose ``valid_to``
has passed reads as ``EXPIRED`` and prices nothing. A contract is ended early
by closing it, or called off by cancelling it.

Only one active contract line may cover a supplier and product on any day.
Activation refuses an overlap, under a lock on the supplier's contracts:
overlapping periods are a fact about a set of rows, which no key can express.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.common.firm_metadata import firm_today
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.document_framework.services.transactional_document_service import (
    DocumentStateSpec,
    DocumentTypeSpec,
    TransactionalDocumentService,
)
from app.products.models import Product
from app.rate_contracts.models import RateContract, RateContractLine
from app.rate_contracts.repositories import RateContractRepository
from app.rate_contracts.schemas import (
    RateContractCreate,
    RateContractLineResponse,
    RateContractLineWrite,
    RateContractReleaseResponse,
    RateContractResponse,
    RateContractUpdate,
)
from app.rate_contracts.services.rates import DRAWING_STATUSES, drawn_quantities
from app.vendors.models import Vendor

ZERO = Decimal("0")


def display_status(row: RateContract, today: date) -> str:
    """Return the status as read on ``today``: ``EXPIRED`` is derived, not stored."""
    if row.status == "ACTIVE" and row.valid_to < today:
        return "EXPIRED"
    return row.status


class RateContractService(TransactionalDocumentService):
    """Type, approve, close and cancel rate contracts, and read their releases."""

    DOCUMENT = DocumentTypeSpec(
        code="RATE_CONTRACT",
        name="Rate Contract",
        description="Rates agreed with a supplier for a period.",
        category="PURCHASE",
        module="rate_contracts",
        # Its own, not the customer receipt's ``RC``: a contract posts no
        # journal under its number, so the next receipt took the same one
        # (D-BUY-57).
        prefix="RTC",
        rule_code="RATE_CONTRACT_DEFAULT",
        rule_name="Rate Contract Default Numbering",
        states=(
            DocumentStateSpec("DRAFT", "Draft", 10, allows_edit=True),
            DocumentStateSpec("ACTIVE", "Active", 20),
            DocumentStateSpec("CLOSED", "Closed", 80, is_terminal=True),
            DocumentStateSpec("CANCELLED", "Cancelled", 90, is_terminal=True),
        ),
    )

    def __init__(self, session: Session) -> None:
        """Bind the service and its repository to a session it does not own."""
        super().__init__(session)
        self._rows = RateContractRepository(self._session)

    # -- writing --------------------------------------------------------
    def create(
        self, data: RateContractCreate, *, firm_id: UUID, actor_id: UUID
    ) -> RateContract:
        """Type a draft contract and commit.

        Raises:
            ValidationError: If the period runs backwards, the supplier is not
                the firm's, or a product is unknown or named twice.

        """
        self._check_period(data.valid_from, data.valid_to)
        self._check_vendor(data.vendor_id, firm_id)
        _, rule = self._ensure_document_setup(firm_id=firm_id, actor_id=actor_id)
        _, company_code = self._scope_codes(firm_id=firm_id, branch_id=None)
        number = self._issue_number(
            rule,
            typed=None,
            number_column=RateContract.contract_number,
            firm_id=firm_id,
            document_date=data.valid_from,
            actor_id=actor_id,
            branch_code=None,
            company_code=company_code,
        )
        row = RateContract(
            firm_id=firm_id,
            contract_number=number,
            vendor_id=data.vendor_id,
            valid_from=data.valid_from,
            valid_to=data.valid_to,
            reference=data.reference,
            notes=data.notes,
            status="DRAFT",
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._flush_or_conflict("Rate contract number already exists in this firm.")
        self._write_lines(row, data.lines, actor_id=actor_id)
        self._audit("rate_contract.created", row, actor_id)
        self._session.commit()
        return row

    def update(
        self,
        contract_id: UUID,
        data: RateContractUpdate,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> RateContract:
        """Change a draft contract; a field left out is left alone.

        Raises:
            ValidationError: If the contract is no longer a draft, or the
                change leaves it invalid.

        """
        row = self.get(contract_id, firm_id=firm_id)
        self._require(row, "DRAFT", "Only a draft rate contract can be changed.")
        values = data.model_dump(exclude_unset=True)
        for field in ("vendor_id", "valid_from", "valid_to"):
            if field in values and values[field] is None:
                raise ValidationError(f"{field} cannot be blank.")
        vendor_id = values.get("vendor_id", row.vendor_id)
        if vendor_id != row.vendor_id:
            self._check_vendor(vendor_id, firm_id)
        valid_from = values.get("valid_from", row.valid_from)
        valid_to = values.get("valid_to", row.valid_to)
        self._check_period(valid_from, valid_to)
        row.vendor_id = vendor_id
        row.valid_from = valid_from
        row.valid_to = valid_to
        row.reference = values.get("reference", row.reference)
        row.notes = values.get("notes", row.notes)
        row.updated_by = actor_id
        if "lines" in data.model_fields_set and data.lines is not None:
            self._write_lines(row, data.lines, actor_id=actor_id)
        self._audit("rate_contract.updated", row, actor_id)
        self._session.commit()
        return row

    def delete(self, contract_id: UUID, *, firm_id: UUID, actor_id: UUID) -> None:
        """Remove a draft contract; one ever approved is closed or cancelled.

        Raises:
            ValidationError: If the contract is not a draft.

        """
        row = self.get(contract_id, firm_id=firm_id)
        self._require(
            row,
            "DRAFT",
            "Only a draft rate contract can be deleted; close or cancel it instead.",
        )
        now = utc_now()
        row.is_deleted = True
        row.deleted_at = now
        row.deleted_by = actor_id
        row.updated_by = actor_id
        for line in self._rows.lines([row.id]).get(row.id, []):
            line.is_deleted = True
            line.deleted_at = now
            line.deleted_by = actor_id
        self._audit("rate_contract.deleted", row, actor_id)
        self._session.commit()

    # -- the lifecycle --------------------------------------------------
    def approve(
        self, contract_id: UUID, *, firm_id: UUID, actor_id: UUID
    ) -> RateContract:
        """Make a draft contract active, so orders take its rates.

        The supplier's contracts are locked first, so two approvals for one
        supplier cannot each miss the other's overlap.

        Raises:
            ValidationError: If it is not a draft, has already ended, or a
                product is on another active contract with the supplier for
                an overlapping period.

        """
        row = self.get(contract_id, firm_id=firm_id)
        self._require(row, "DRAFT", "Only a draft rate contract can be approved.")
        if row.valid_to < firm_today(self._session, firm_id):
            raise ValidationError(
                f"{row.contract_number} ended on {row.valid_to.isoformat()}; "
                "change its period before approving it."
            )
        siblings = [
            other
            for other in self._rows.lock_vendor_contracts(firm_id, row.vendor_id)
            if other.id != row.id
            and other.status == "ACTIVE"
            and other.valid_from <= row.valid_to
            and row.valid_from <= other.valid_to
        ]
        lines = self._rows.lines([row.id] + [other.id for other in siblings])
        mine = {line.product_id for line in lines.get(row.id, [])}
        if not mine:
            raise ValidationError("Add at least one line before approving.")
        clashes: list[str] = []
        products = self._rows.products(mine)
        for other in siblings:
            shared = sorted(
                products[line.product_id].code
                for line in lines.get(other.id, [])
                if line.product_id in mine
            )
            if shared:
                clashes.append(
                    f"{', '.join(shared)} on {other.contract_number} "
                    f"({other.valid_from.isoformat()} to "
                    f"{other.valid_to.isoformat()})"
                )
        if clashes:
            raise ValidationError(
                "Another active rate contract with this supplier covers the "
                "same product for an overlapping period: "
                + "; ".join(clashes)
                + ". Close it, or change the period."
            )
        row.status = "ACTIVE"
        row.approved_at = utc_now()
        row.approved_by = actor_id
        row.updated_by = actor_id
        self._audit("rate_contract.approved", row, actor_id)
        self._session.commit()
        return row

    def close(
        self, contract_id: UUID, *, firm_id: UUID, actor_id: UUID
    ) -> RateContract:
        """End an active contract: orders stop taking its rates.

        Orders already drawn keep their prices; nothing is repriced.

        Raises:
            ValidationError: If the contract is not active.

        """
        row = self.get(contract_id, firm_id=firm_id)
        self._require(row, "ACTIVE", "Only an active rate contract can be closed.")
        row.status = "CLOSED"
        row.closed_at = utc_now()
        row.updated_by = actor_id
        self._audit("rate_contract.closed", row, actor_id)
        self._session.commit()
        return row

    def cancel(
        self, contract_id: UUID, reason: str, *, firm_id: UUID, actor_id: UUID
    ) -> RateContract:
        """Call off a draft or active contract, saying why.

        Raises:
            ValidationError: If it is closed or cancelled, or no reason is given.

        """
        row = self.get(contract_id, firm_id=firm_id)
        if row.status not in ("DRAFT", "ACTIVE"):
            raise ValidationError(
                f"A {row.status.lower()} rate contract cannot be cancelled."
            )
        if not reason.strip():
            raise ValidationError("Say why the rate contract is cancelled.")
        row.status = "CANCELLED"
        row.cancel_reason = reason.strip()
        row.updated_by = actor_id
        self._audit("rate_contract.cancelled", row, actor_id)
        self._session.commit()
        return row

    # -- reading --------------------------------------------------------
    def get(self, contract_id: UUID, *, firm_id: UUID) -> RateContract:
        """Return one of the firm's contracts."""
        row = self._rows.get(contract_id, firm_id=firm_id)
        if row is None:
            raise ResourceNotFoundError("Rate contract not found.")
        return row

    def page(
        self,
        firm_id: UUID,
        *,
        vendor_id: UUID | None,
        status: str | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[RateContract], int]:
        """Return one page of the firm's contracts and the total."""
        return self._rows.page(
            firm_id,
            today=firm_today(self._session, firm_id),
            vendor_id=vendor_id,
            status=status,
            search=search,
            page=page,
            page_size=page_size,
        )

    def responses(self, rows: list[RateContract]) -> list[RateContractResponse]:
        """Shape contracts with their lines, reading each table once."""
        if not rows:
            return []
        lines = self._rows.lines([row.id for row in rows])
        every_line = [line for group in lines.values() for line in group]
        products = self._rows.products(line.product_id for line in every_line)
        vendors = self._rows.vendors(row.vendor_id for row in rows)
        drawn = drawn_quantities(self._session, [line.id for line in every_line])
        today = firm_today(self._session, rows[0].firm_id)
        answer: list[RateContractResponse] = []
        for row in rows:
            vendor = vendors.get(row.vendor_id)
            answer.append(
                RateContractResponse(
                    id=row.id,
                    contract_number=row.contract_number,
                    vendor_id=row.vendor_id,
                    vendor_code=vendor.code if vendor else "",
                    vendor_name=(vendor.display_name or vendor.name) if vendor else "",
                    valid_from=row.valid_from,
                    valid_to=row.valid_to,
                    reference=row.reference,
                    notes=row.notes,
                    status=display_status(row, today),
                    approved_at=row.approved_at,
                    closed_at=row.closed_at,
                    cancel_reason=row.cancel_reason,
                    version=row.version,
                    lines=[
                        self._line_response(line, products.get(line.product_id), drawn)
                        for line in lines.get(row.id, [])
                    ],
                )
            )
        return answer

    def releases(
        self, contract_id: UUID, *, firm_id: UUID
    ) -> list[RateContractReleaseResponse]:
        """Return every order line priced from the contract, oldest first."""
        row = self.get(contract_id, firm_id=firm_id)
        lines = self._rows.lines([row.id]).get(row.id, [])
        return [
            RateContractReleaseResponse(
                purchase_order_id=order.id,
                po_number=order.po_number,
                purchase_date=order.purchase_date,
                order_status=order.status,
                counts_as_drawn=order.status in DRAWING_STATUSES,
                purchase_order_line_id=line.id,
                line_number=line.line_number,
                rate_contract_line_id=line.rate_contract_line_id,
                product_id=line.product_id,
                ordered_quantity=line.ordered_quantity,
                unit_price=line.unit_price,
            )
            for order, line in self._rows.releases(item.id for item in lines)
            if order.firm_id == firm_id
        ]

    # -- helpers --------------------------------------------------------
    @staticmethod
    def _line_response(
        line: RateContractLine,
        product: Product | None,
        drawn: dict[UUID, Decimal],
    ) -> RateContractLineResponse:
        """Shape one line with its drawn and remaining quantities."""
        taken = drawn.get(line.id, ZERO)
        contracted = line.contracted_quantity
        return RateContractLineResponse(
            id=line.id,
            line_number=line.line_number,
            product_id=line.product_id,
            product_code=product.code if product else "",
            product_name=product.name if product else "",
            uom_id=line.uom_id,
            rate=line.rate,
            discount_percent=line.discount_percent,
            contracted_quantity=contracted,
            drawn_quantity=taken,
            remaining_quantity=(
                max(Decimal(str(contracted)) - taken, ZERO)
                if contracted is not None
                else None
            ),
            notes=line.notes,
        )

    @staticmethod
    def _require(row: RateContract, status: str, message: str) -> None:
        """Refuse unless the contract is in ``status``."""
        if row.status != status:
            raise ValidationError(message)

    @staticmethod
    def _check_period(valid_from: date, valid_to: date) -> None:
        """Refuse a period that ends before it starts."""
        if valid_to < valid_from:
            raise ValidationError("valid_to cannot be before valid_from.")

    def _check_vendor(self, vendor_id: UUID, firm_id: UUID) -> None:
        """Refuse a supplier that is not the firm's."""
        vendor = self._session.get(Vendor, vendor_id)
        if vendor is None or vendor.is_deleted or vendor.firm_id != firm_id:
            raise ValidationError("Unknown supplier.")

    def _write_lines(
        self,
        row: RateContract,
        lines: list[RateContractLineWrite],
        *,
        actor_id: UUID,
    ) -> None:
        """Reconcile the lines on their line number.

        Raises:
            ValidationError: If a product is unknown or named twice.

        """
        products = self._rows.products(line.product_id for line in lines)
        missing = [
            str(line.product_id)
            for line in lines
            if line.product_id not in products
            or products[line.product_id].firm_id != row.firm_id
            or products[line.product_id].is_deleted
        ]
        if missing:
            raise ValidationError("Unknown product(s): " + ", ".join(missing) + ".")
        seen_products: set[UUID] = set()
        for line in lines:
            if line.product_id in seen_products:
                raise ValidationError(
                    f"{products[line.product_id].code} is on the contract twice."
                )
            seen_products.add(line.product_id)
        existing = {
            line.line_number: line for line in self._rows.lines([row.id])[row.id]
        }
        numbers: set[int] = set()
        for number, line in enumerate(lines, start=1):
            numbers.add(number)
            current = existing.get(number)
            if current is None:
                current = RateContractLine(
                    contract_id=row.id,
                    firm_id=row.firm_id,
                    line_number=number,
                    created_by=actor_id,
                )
                self._session.add(current)
            current.product_id = line.product_id
            current.uom_id = line.uom_id or products[line.product_id].purchase_uom_id
            current.rate = line.rate
            current.discount_percent = line.discount_percent
            current.contracted_quantity = line.contracted_quantity
            current.notes = line.notes
            current.updated_by = actor_id
        # Only a draft is edited, and a draft was never active, so nothing
        # draws on a line dropped here.
        for number, obsolete in existing.items():
            if number not in numbers:
                self._session.delete(obsolete)
        self._session.flush()

    def _audit(self, action: str, row: RateContract, actor_id: UUID) -> None:
        """Write one audit row for a contract."""
        record_audit(
            self._session,
            action=action,
            entity_type="rate_contract",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=row.firm_id,
            after_data={
                "contract_number": row.contract_number,
                "vendor_id": str(row.vendor_id),
                "valid_from": row.valid_from.isoformat(),
                "valid_to": row.valid_to.isoformat(),
                "status": row.status,
            },
        )

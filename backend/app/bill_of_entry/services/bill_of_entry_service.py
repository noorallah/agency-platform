"""Bills of Entry: the customs side of an import (PG-12 part B, backlog 86 #5).

A supplier abroad bills in its own currency (PG-12 part A); the goods clear
customs on a **Bill of Entry**, which assesses on each item

* basic customs duty (BCD) on the assessable value,
* the social welfare surcharge (SWS), 10% of BCD by default,
* IGST on assessable value + BCD + SWS, and
* compensation cess where the goods attract it.

The document is typed as a ``DRAFT`` and posted, which needs
``PURCHASE_APPROVE``. Posting books the duty, the way Tally and ERPNext treat
an import:

* BCD and SWS are a **cost** of the goods, with no credit. They are spread
  over the linked goods receipts' lines of the same product by quantity and
  landed through the landed-cost mechanism (BUY-16): the share on stock still
  held revalues it, the share on goods already sold goes to cost of goods
  sold. A line no linked receipt carries is booked to *Customs Duty* expense,
  because there is no stock to revalue.
* IGST is **input tax**, debited to the IGST input account a purchase claims
  through; cess to input tax.
* The whole is credited to *Customs Duty Payable*, which an ordinary payment
  or journal clears.

The receipts are those named on the Bill of Entry plus every receipt the
linked bills reach -- named as a source, or raised by the bill itself where the
firm types only the bill. Cancelling a posted Bill of Entry reverses its
journal and takes the duty back off the stock. GSTR-3B reads the IGST and cess
of posted Bills of Entry into 4(A)(1) by ``boe_date`` on every read; nothing is
stored for the return.
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.bill_of_entry.models import (
    BillOfEntry,
    BillOfEntryAllocation,
    BillOfEntryDocument,
    BillOfEntryLine,
)
from app.bill_of_entry.repositories import INVOICE, RECEIPT, BillOfEntryRepository
from app.bill_of_entry.schemas import (
    BillOfEntryCreate,
    BillOfEntryInvoiceLink,
    BillOfEntryLineResponse,
    BillOfEntryLineWrite,
    BillOfEntryReceiptLink,
    BillOfEntryResponse,
    BillOfEntryUpdate,
)
from app.bill_of_entry.services.duty import compute_line_duty
from app.branches.models import Branch
from app.common.audit.services import record_audit
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO
from app.core.utils.pricing import apportion
from app.document_framework.services.transactional_document_service import (
    DocumentStateSpec,
    DocumentTypeSpec,
    TransactionalDocumentService,
)
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.landed_costs.services import (
    land_on_receipt_lines,
    stock_quantity,
    take_off_receipt_lines,
)
from app.products.models import Product
from app.vendors.models import Vendor

#: A receipt whose goods are in: only such a receipt carries duty.
_RECEIVED = ("COMPLETED", "CLOSED")
_RUPEE = "INR"


class BillOfEntryService(TransactionalDocumentService):
    """Type, post and cancel Bills of Entry."""

    DOCUMENT = DocumentTypeSpec(
        code="BILL_OF_ENTRY",
        name="Bill of Entry",
        description="Customs duty and IGST assessed on imported goods.",
        category="PURCHASE",
        module="bill_of_entry",
        prefix="BOE",
        rule_code="BILL_OF_ENTRY_DEFAULT",
        rule_name="Bill of Entry Default Numbering",
        states=(
            DocumentStateSpec("DRAFT", "Draft", 10, allows_edit=True),
            DocumentStateSpec("POSTED", "Posted", 20),
            DocumentStateSpec("CANCELLED", "Cancelled", 90, is_terminal=True),
        ),
    )

    def __init__(self, session: Session) -> None:
        """Bind the service and its repository to a session it does not own."""
        super().__init__(session)
        self._rows = BillOfEntryRepository(self._session)

    # -- writing --------------------------------------------------------
    def create(
        self, data: BillOfEntryCreate, *, firm_id: UUID, actor_id: UUID
    ) -> BillOfEntry:
        """Type a draft Bill of Entry and commit."""
        row = self.stage_create(data, firm_id=firm_id, actor_id=actor_id)
        self._session.commit()
        return row

    def stage_create(
        self, data: BillOfEntryCreate, *, firm_id: UUID, actor_id: UUID
    ) -> BillOfEntry:
        """Type a draft Bill of Entry; flush, do not commit.

        Raises:
            ValidationError: If the supplier, branch, a bill, a receipt or a
                product is not the firm's, or the currency and rate disagree.

        """
        self._check_vendor(data.vendor_id, firm_id)
        self._check_branch(data.branch_id, firm_id)
        currency, rate = _currency(data.currency_code, data.exchange_rate)
        _, rule = self._ensure_document_setup(firm_id=firm_id, actor_id=actor_id)
        branch_code, company_code = self._scope_codes(
            firm_id=firm_id, branch_id=data.branch_id
        )
        number = self._issue_number(
            rule,
            typed=None,
            number_column=BillOfEntry.document_number,
            firm_id=firm_id,
            document_date=data.boe_date,
            actor_id=actor_id,
            branch_code=branch_code,
            company_code=company_code,
        )
        row = BillOfEntry(
            firm_id=firm_id,
            document_number=number,
            boe_number=data.boe_number.strip(),
            boe_date=data.boe_date,
            port_code=data.port_code.strip().upper(),
            vendor_id=data.vendor_id,
            branch_id=data.branch_id,
            currency_code=currency,
            exchange_rate=rate,
            remarks=data.remarks,
            status="DRAFT",
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._flush_or_conflict("Bill of Entry number already exists in this firm.")
        self._write_links(
            row,
            data.purchase_invoice_ids,
            data.goods_receipt_ids,
            actor_id=actor_id,
        )
        self._write_lines(row, data.lines, actor_id=actor_id)
        self._audit("bill_of_entry.created", row, actor_id)
        return row

    def update(
        self,
        boe_id: UUID,
        data: BillOfEntryUpdate,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> BillOfEntry:
        """Change a draft; a field left out is left alone; commit.

        Raises:
            ValidationError: If it is no longer a draft, or the change leaves
                it invalid.

        """
        row = self.get(boe_id, firm_id=firm_id)
        self._require(row, "DRAFT", "Only a draft Bill of Entry can be changed.")
        values = data.model_dump(exclude_unset=True)
        for field in ("boe_number", "boe_date", "port_code", "vendor_id"):
            if field in values and values[field] is None:
                raise ValidationError(f"{field} cannot be blank.")
        vendor_id = values.get("vendor_id", row.vendor_id)
        vendor_changed = vendor_id != row.vendor_id
        if vendor_changed:
            self._check_vendor(vendor_id, firm_id)
        branch_id = values.get("branch_id", row.branch_id)
        if branch_id != row.branch_id:
            self._check_branch(branch_id, firm_id)
        code = values.get("currency_code", row.currency_code)
        kept_rate = row.exchange_rate
        if "currency_code" in values and (code or "").strip().upper() != (
            row.currency_code or ""
        ):
            # The old rate goes with the old currency.
            kept_rate = None
        currency, rate = _currency(code, values.get("exchange_rate", kept_rate))
        row.boe_number = str(values.get("boe_number", row.boe_number)).strip()
        row.boe_date = values.get("boe_date", row.boe_date)
        row.port_code = str(values.get("port_code", row.port_code)).strip().upper()
        row.vendor_id = vendor_id
        row.branch_id = branch_id
        row.currency_code = currency
        row.exchange_rate = rate
        row.remarks = values.get("remarks", row.remarks)
        row.updated_by = actor_id
        fields = data.model_fields_set
        if (
            "purchase_invoice_ids" in fields
            or "goods_receipt_ids" in fields
            or vendor_changed
        ):
            current = self._rows.documents([row.id]).get(row.id, [])
            self._write_links(
                row,
                (
                    data.purchase_invoice_ids or []
                    if "purchase_invoice_ids" in fields
                    else [d.document_id for d in current if d.document_type == INVOICE]
                ),
                (
                    data.goods_receipt_ids or []
                    if "goods_receipt_ids" in fields
                    else [d.document_id for d in current if d.document_type == RECEIPT]
                ),
                actor_id=actor_id,
            )
        if "lines" in fields and data.lines is not None:
            self._write_lines(row, data.lines, actor_id=actor_id)
        self._audit("bill_of_entry.updated", row, actor_id)
        self._session.commit()
        return row

    def delete(self, boe_id: UUID, *, firm_id: UUID, actor_id: UUID) -> None:
        """Remove a draft; a posted one is cancelled instead; commit.

        Raises:
            ValidationError: If it is not a draft.

        """
        row = self.get(boe_id, firm_id=firm_id)
        self._require(
            row,
            "DRAFT",
            "Only a draft Bill of Entry can be deleted; cancel a posted one.",
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
        self._audit("bill_of_entry.deleted", row, actor_id)
        self._session.commit()

    # -- the lifecycle --------------------------------------------------
    def post(self, boe_id: UUID, *, firm_id: UUID, actor_id: UUID) -> BillOfEntry:
        """Book the duty, land it on the receipts, claim the IGST; commit."""
        row = self.stage_post(boe_id, firm_id=firm_id, actor_id=actor_id)
        self._session.commit()
        return row

    def stage_post(self, boe_id: UUID, *, firm_id: UUID, actor_id: UUID) -> BillOfEntry:
        """Post a draft: spread the duty, revalue stock, journal; flush only.

        Raises:
            ValidationError: If it is not a draft, customs already has a live
                Bill of Entry under that number, port and date, or a linked
                receipt has not been completed.

        """
        row = self.get(boe_id, firm_id=firm_id)
        self._require(row, "DRAFT", "Only a draft Bill of Entry can be posted.")
        clash = self._rows.duplicate(
            firm_id,
            boe_number=row.boe_number,
            port_code=row.port_code,
            boe_date=row.boe_date,
        )
        if clash is not None and clash.id != row.id:
            raise ValidationError(
                f"Bill of Entry {row.boe_number} at {row.port_code} on "
                f"{row.boe_date.isoformat()} is already {clash.document_number}."
            )
        lines = self._rows.lines([row.id]).get(row.id, [])
        if not lines:
            raise ValidationError("Add at least one line before posting.")
        receipts = self._receipts_for(row)
        receipt_lines = self._receipt_lines(list(receipts))
        by_product: dict[UUID, list[tuple[GoodsReceiptLine, Decimal]]] = defaultdict(
            list
        )
        for receipt_line, quantity in receipt_lines:
            by_product[receipt_line.product_id].append((receipt_line, quantity))

        shares: list[tuple[GoodsReceiptLine, Decimal, Decimal]] = []
        owners: list[BillOfEntryLine] = []
        for line in lines:
            cost = Decimal(str(line.bcd_amount)) + Decimal(str(line.sws_amount))
            line.inventory_amount = line.cogs_amount = line.expense_amount = ZERO
            targets = by_product.get(line.product_id, [])
            if not targets:
                line.expense_amount = cost
                continue
            spread = apportion(cost, [quantity for _, quantity in targets])
            for (receipt_line, quantity), share in zip(targets, spread, strict=True):
                shares.append((receipt_line, quantity, share))
                owners.append(line)
        landed = land_on_receipt_lines(
            self._session,
            firm_id=firm_id,
            receipts=receipts,
            shares=shares,
            reference_number=row.document_number,
            on=row.boe_date,
            label=f"Customs duty {row.document_number}",
            actor_id=actor_id,
        )
        for owner, piece in zip(owners, landed, strict=True):
            owner.inventory_amount = (
                Decimal(str(owner.inventory_amount)) + piece.inventory_amount
            )
            owner.cogs_amount = Decimal(str(owner.cogs_amount)) + piece.cogs_amount
            self._session.add(
                BillOfEntryAllocation(
                    bill_of_entry_id=row.id,
                    bill_of_entry_line_id=owner.id,
                    firm_id=firm_id,
                    goods_receipt_id=piece.line.goods_receipt_id,
                    goods_receipt_line_id=piece.line.id,
                    quantity=piece.quantity,
                    amount=piece.amount,
                    inventory_amount=piece.inventory_amount,
                    cogs_amount=piece.cogs_amount,
                    inventory_transaction_id=piece.inventory_transaction_id,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        row.inventory_amount = sum(
            (Decimal(str(line.inventory_amount)) for line in lines), ZERO
        )
        row.cogs_amount = sum((Decimal(str(line.cogs_amount)) for line in lines), ZERO)
        row.expense_amount = sum(
            (Decimal(str(line.expense_amount)) for line in lines), ZERO
        )
        if Decimal(str(row.total_duty)) > ZERO:
            entry = DocumentPostingService(self._session).post_bill_of_entry(
                firm_id=firm_id,
                bill_of_entry_id=row.id,
                reference_number=row.document_number,
                boe_date=row.boe_date,
                inventory_amount=row.inventory_amount,
                cogs_amount=row.cogs_amount,
                expense_amount=row.expense_amount,
                igst_amount=row.igst_amount,
                cess_amount=row.cess_amount,
                actor_id=actor_id,
            )
            row.journal_entry_id = entry.id
        row.status = "POSTED"
        row.posted_at = utc_now()
        row.posted_by = actor_id
        row.updated_by = actor_id
        self._audit("bill_of_entry.posted", row, actor_id)
        self._session.flush()
        return row

    def cancel(
        self, boe_id: UUID, reason: str, *, firm_id: UUID, actor_id: UUID
    ) -> BillOfEntry:
        """Withdraw a draft or posted Bill of Entry, saying why; commit.

        A posted one has its journal reversed and its duty taken back off the
        stock at today's quantity: what was sold since keeps the cost it was
        sold at, as a cancelled landed cost voucher does.

        Raises:
            ValidationError: If already cancelled, or no reason is given.

        """
        row = self.get(boe_id, firm_id=firm_id)
        if row.status not in ("DRAFT", "POSTED"):
            raise ValidationError("This Bill of Entry was already cancelled.")
        if not reason.strip():
            raise ValidationError("Say why the Bill of Entry is cancelled.")
        if row.status == "POSTED":
            take_off_receipt_lines(
                self._session,
                firm_id=firm_id,
                held=[
                    (allocation.goods_receipt_line_id, allocation.inventory_amount)
                    for allocation in self._rows.allocations(row.id)
                ],
                reference_number=row.document_number,
                on=row.boe_date,
                remarks=f"Customs duty {row.document_number} cancelled",
                actor_id=actor_id,
            )
            if row.journal_entry_id is not None:
                JournalEntryEngine(self._session).reverse_entry(
                    row.journal_entry_id,
                    firm_id=firm_id,
                    reference_number=f"BOE-{row.document_number}-REV",
                    actor_id=actor_id,
                )
        row.status = "CANCELLED"
        row.cancel_reason = reason.strip()
        row.updated_by = actor_id
        self._audit("bill_of_entry.cancelled", row, actor_id)
        self._session.commit()
        return row

    # -- reading --------------------------------------------------------
    def get(self, boe_id: UUID, *, firm_id: UUID) -> BillOfEntry:
        """Return one of the firm's Bills of Entry."""
        row = self._rows.get(boe_id, firm_id=firm_id)
        if row is None:
            raise ResourceNotFoundError("Bill of Entry not found.")
        return row

    def page(
        self,
        firm_id: UUID,
        *,
        status: str | None,
        vendor_id: UUID | None,
        from_date: date | None,
        to_date: date | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[BillOfEntry], int]:
        """Return one page of the firm's Bills of Entry and the total."""
        return self._rows.page(
            firm_id,
            status=status,
            vendor_id=vendor_id,
            from_date=from_date,
            to_date=to_date,
            search=search,
            page=page,
            page_size=page_size,
        )

    def responses(self, rows: list[BillOfEntry]) -> list[BillOfEntryResponse]:
        """Shape Bills of Entry with lines and links, reading each table once."""
        if not rows:
            return []
        ids = [row.id for row in rows]
        lines = self._rows.lines(ids)
        links = self._rows.documents(ids)
        products = self._rows.products(
            line.product_id for group in lines.values() for line in group
        )
        vendors = self._rows.vendors(row.vendor_id for row in rows)
        invoice_ids = {
            link.document_id
            for group in links.values()
            for link in group
            if link.document_type == INVOICE
        }
        invoices = self._rows.invoices(invoice_ids)
        reached = self._rows.receipts_of_invoices(invoice_ids)
        named_receipts = {
            link.document_id
            for group in links.values()
            for link in group
            if link.document_type == RECEIPT
        }
        receipts = self._rows.receipts(named_receipts | set(reached))
        answer: list[BillOfEntryResponse] = []
        for row in rows:
            vendor = vendors.get(row.vendor_id)
            mine = links.get(row.id, [])
            my_invoices = [
                invoices[link.document_id]
                for link in mine
                if link.document_type == INVOICE and link.document_id in invoices
            ]
            my_named = [
                link.document_id for link in mine if link.document_type == RECEIPT
            ]
            my_reached = [
                receipt_id
                for receipt_id, invoice_id in reached.items()
                if invoice_id in {invoice.id for invoice in my_invoices}
                and receipt_id not in my_named
            ]
            answer.append(
                BillOfEntryResponse(
                    id=row.id,
                    document_number=row.document_number,
                    boe_number=row.boe_number,
                    boe_date=row.boe_date,
                    port_code=row.port_code,
                    vendor_id=row.vendor_id,
                    vendor_code=vendor.code if vendor else "",
                    vendor_name=(vendor.display_name or vendor.name) if vendor else "",
                    branch_id=row.branch_id,
                    currency_code=row.currency_code,
                    exchange_rate=row.exchange_rate,
                    assessable_value=row.assessable_value,
                    basic_customs_duty=row.basic_customs_duty,
                    social_welfare_surcharge=row.social_welfare_surcharge,
                    customs_duty=Decimal(str(row.basic_customs_duty))
                    + Decimal(str(row.social_welfare_surcharge)),
                    igst_amount=row.igst_amount,
                    cess_amount=row.cess_amount,
                    total_duty=row.total_duty,
                    inventory_amount=row.inventory_amount,
                    cogs_amount=row.cogs_amount,
                    expense_amount=row.expense_amount,
                    status=row.status,
                    posted_at=row.posted_at,
                    journal_entry_id=row.journal_entry_id,
                    remarks=row.remarks,
                    cancel_reason=row.cancel_reason,
                    version=row.version,
                    purchase_invoices=[
                        BillOfEntryInvoiceLink(
                            purchase_invoice_id=invoice.id,
                            invoice_number=invoice.invoice_number,
                            supplier_invoice_number=invoice.supplier_invoice_number,
                            invoice_date=invoice.invoice_date,
                            status=invoice.status,
                            currency_code=invoice.currency_code,
                            exchange_rate=invoice.exchange_rate,
                            grand_total=invoice.grand_total,
                            base_grand_total=invoice.base_grand_total,
                        )
                        for invoice in my_invoices
                    ],
                    goods_receipts=[
                        BillOfEntryReceiptLink(
                            goods_receipt_id=receipt.id,
                            grn_number=receipt.grn_number,
                            receipt_date=receipt.receipt_date,
                            status=receipt.status,
                            via_invoice=receipt.id not in my_named,
                        )
                        for receipt in (
                            receipts[receipt_id]
                            for receipt_id in [*my_named, *my_reached]
                            if receipt_id in receipts
                        )
                    ],
                    lines=[
                        self._line_response(line, products)
                        for line in lines.get(row.id, [])
                    ],
                )
            )
        return answer

    # -- helpers --------------------------------------------------------
    @staticmethod
    def _line_response(
        line: BillOfEntryLine, products: dict[UUID, Product]
    ) -> BillOfEntryLineResponse:
        """Shape one line."""
        product = products.get(line.product_id)
        return BillOfEntryLineResponse(
            id=line.id,
            line_number=line.line_number,
            product_id=line.product_id,
            product_code=product.code if product else "",
            product_name=product.name if product else "",
            quantity=line.quantity,
            assessable_value=line.assessable_value,
            bcd_rate=line.bcd_rate,
            bcd_amount=line.bcd_amount,
            sws_rate=line.sws_rate,
            sws_amount=line.sws_amount,
            igst_base=Decimal(str(line.assessable_value))
            + Decimal(str(line.bcd_amount))
            + Decimal(str(line.sws_amount)),
            igst_rate=line.igst_rate,
            igst_amount=line.igst_amount,
            cess_amount=line.cess_amount,
            total_duty=line.total_duty,
            inventory_amount=line.inventory_amount,
            cogs_amount=line.cogs_amount,
            expense_amount=line.expense_amount,
        )

    @staticmethod
    def _require(row: BillOfEntry, status: str, message: str) -> None:
        """Refuse unless the Bill of Entry is in ``status``."""
        if row.status != status:
            raise ValidationError(message)

    def _check_vendor(self, vendor_id: UUID, firm_id: UUID) -> None:
        """Refuse a supplier that is not the firm's."""
        vendor = self._session.get(Vendor, vendor_id)
        if vendor is None or vendor.is_deleted or vendor.firm_id != firm_id:
            raise ValidationError("Unknown supplier.")

    def _check_branch(self, branch_id: UUID | None, firm_id: UUID) -> None:
        """Refuse a branch that is not the firm's."""
        if branch_id is None:
            return
        branch = self._session.get(Branch, branch_id)
        if branch is None or branch.is_deleted or branch.firm_id != firm_id:
            raise ValidationError("Unknown branch.")

    def _write_links(
        self,
        row: BillOfEntry,
        invoice_ids: list[UUID],
        receipt_ids: list[UUID],
        *,
        actor_id: UUID,
    ) -> None:
        """Replace the bills and receipts the Bill of Entry names.

        Raises:
            ValidationError: If one is named twice, is not the firm's, is
                cancelled, or a bill is from another supplier.

        """
        if len(set(invoice_ids)) != len(invoice_ids):
            raise ValidationError("A bill is named twice.")
        if len(set(receipt_ids)) != len(receipt_ids):
            raise ValidationError("A goods receipt is named twice.")
        invoices = self._rows.invoices(invoice_ids)
        for invoice_id in invoice_ids:
            invoice = invoices.get(invoice_id)
            if invoice is None or invoice.is_deleted or invoice.firm_id != row.firm_id:
                raise ValidationError("A bill is not one of this firm's.")
            if invoice.status == "CANCELLED":
                raise ValidationError(f"Bill {invoice.invoice_number} is cancelled.")
            if invoice.vendor_id != row.vendor_id:
                raise ValidationError(
                    f"Bill {invoice.invoice_number} is from another supplier."
                )
        receipts = self._rows.receipts(receipt_ids)
        for receipt_id in receipt_ids:
            receipt = receipts.get(receipt_id)
            if receipt is None or receipt.is_deleted or receipt.firm_id != row.firm_id:
                raise ValidationError("A goods receipt is not one of this firm's.")
            if receipt.status == "CANCELLED":
                raise ValidationError(f"Receipt {receipt.grn_number} is cancelled.")
        for link in self._rows.documents([row.id]).get(row.id, []):
            self._session.delete(link)
        self._session.flush()
        for kind, ids in ((INVOICE, invoice_ids), (RECEIPT, receipt_ids)):
            for document_id in ids:
                self._session.add(
                    BillOfEntryDocument(
                        bill_of_entry_id=row.id,
                        firm_id=row.firm_id,
                        document_type=kind,
                        document_id=document_id,
                        created_by=actor_id,
                        updated_by=actor_id,
                    )
                )
        self._session.flush()

    def _write_lines(
        self,
        row: BillOfEntry,
        lines: list[BillOfEntryLineWrite],
        *,
        actor_id: UUID,
    ) -> None:
        """Reconcile the lines on their line number and total the header.

        Raises:
            ValidationError: If a product is unknown.

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
        existing = {
            line.line_number: line
            for line in self._rows.lines([row.id]).get(row.id, [])
        }
        totals = dict.fromkeys(("assessable", "bcd", "sws", "igst", "cess"), ZERO)
        numbers: set[int] = set()
        for number, write in enumerate(lines, start=1):
            numbers.add(number)
            duty = compute_line_duty(
                assessable_value=write.assessable_value,
                bcd_rate=write.bcd_rate,
                bcd_amount=write.bcd_amount,
                sws_rate=write.sws_rate,
                sws_amount=write.sws_amount,
                igst_rate=write.igst_rate,
                igst_amount=write.igst_amount,
                cess_amount=write.cess_amount,
            )
            current = existing.get(number)
            if current is None:
                current = BillOfEntryLine(
                    bill_of_entry_id=row.id,
                    firm_id=row.firm_id,
                    line_number=number,
                    created_by=actor_id,
                )
                self._session.add(current)
            current.product_id = write.product_id
            current.quantity = write.quantity
            current.assessable_value = write.assessable_value
            current.bcd_rate = write.bcd_rate
            current.bcd_amount = duty.bcd_amount
            current.sws_rate = duty.sws_rate
            current.sws_amount = duty.sws_amount
            current.igst_rate = write.igst_rate
            current.igst_amount = duty.igst_amount
            current.cess_amount = duty.cess_amount
            current.total_duty = duty.total_duty
            current.updated_by = actor_id
            totals["assessable"] += Decimal(str(write.assessable_value))
            totals["bcd"] += duty.bcd_amount
            totals["sws"] += duty.sws_amount
            totals["igst"] += duty.igst_amount
            totals["cess"] += duty.cess_amount
        # Only a draft is edited, and a draft has landed nothing, so nothing
        # refers to a line dropped here.
        for number, obsolete in existing.items():
            if number not in numbers:
                self._session.delete(obsolete)
        row.assessable_value = totals["assessable"]
        row.basic_customs_duty = totals["bcd"]
        row.social_welfare_surcharge = totals["sws"]
        row.igst_amount = totals["igst"]
        row.cess_amount = totals["cess"]
        row.total_duty = totals["bcd"] + totals["sws"] + totals["igst"] + totals["cess"]
        self._session.flush()

    def _receipts_for(self, row: BillOfEntry) -> dict[UUID, GoodsReceipt]:
        """Return the receipts the duty lands on: named, and reached by a bill.

        Raises:
            ValidationError: If one has not been completed.

        """
        links = self._rows.documents([row.id]).get(row.id, [])
        named = {link.document_id for link in links if link.document_type == RECEIPT}
        reached = self._rows.receipts_of_invoices(
            link.document_id for link in links if link.document_type == INVOICE
        )
        receipts = {
            receipt.id: receipt
            for receipt in self._rows.receipts(named | set(reached)).values()
            if not receipt.is_deleted and receipt.status != "CANCELLED"
        }
        waiting = sorted(
            receipt.grn_number
            for receipt in receipts.values()
            if receipt.status not in _RECEIVED
        )
        if waiting:
            raise ValidationError(
                "Duty lands only on goods received: complete "
                + ", ".join(waiting)
                + " first."
            )
        return receipts

    def _receipt_lines(
        self, receipt_ids: list[UUID]
    ) -> list[tuple[GoodsReceiptLine, Decimal]]:
        """Return each receipt line that brought stock in, with its quantity."""
        if not receipt_ids:
            return []
        rows = self._session.scalars(
            select(GoodsReceiptLine)
            .where(
                GoodsReceiptLine.goods_receipt_id.in_(receipt_ids),
                GoodsReceiptLine.is_deleted.is_(False),
            )
            .order_by(GoodsReceiptLine.goods_receipt_id, GoodsReceiptLine.line_number)
        ).all()
        stocked = [(line, stock_quantity(line)) for line in rows]
        return [(line, quantity) for line, quantity in stocked if quantity > ZERO]

    def _audit(self, action: str, row: BillOfEntry, actor_id: UUID) -> None:
        """Write one audit row for a Bill of Entry."""
        record_audit(
            self._session,
            action=action,
            entity_type="bill_of_entry",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=row.firm_id,
            after_data={
                "document_number": row.document_number,
                "boe_number": row.boe_number,
                "boe_date": row.boe_date.isoformat(),
                "port_code": row.port_code,
                "vendor_id": str(row.vendor_id),
                "total_duty": str(row.total_duty),
                "igst_amount": str(row.igst_amount),
                "status": row.status,
                "cancel_reason": row.cancel_reason,
            },
        )


def _currency(
    code: str | None, rate: Decimal | None
) -> tuple[str | None, Decimal | None]:
    """Normalise the assessed currency and refuse a rate that does not fit it.

    Raises:
        ValidationError: If a foreign currency has no rate, or rupees carry one.

    """
    currency = code.strip().upper() if code and code.strip() else None
    if currency is None or currency == _RUPEE:
        if rate is not None and rate != Decimal("1"):
            raise ValidationError("A rupee Bill of Entry carries no exchange rate.")
        return currency, None
    if rate is None:
        raise ValidationError(
            f"Give the rate customs assessed {currency} at, in rupees per unit."
        )
    return currency, rate

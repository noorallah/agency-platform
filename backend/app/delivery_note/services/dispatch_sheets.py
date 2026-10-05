"""The pick list and the loading sheet over a set of delivery notes (SEL-13).

Two pieces of paper a distributor's godown runs on every morning, the way Marg
and the DMS apps print them (decision A92):

* **Pick list** -- what the storeman takes off the shelves for the chosen
  notes, summed by product, and by batch where the note chose one. In stock
  units, free goods included, because that is what leaves the shelf. A line
  whose batch is left to dispatch says so (earliest expiry first) rather than
  guessing a batch the dispatch may not take.
* **Loading sheet** -- what goes on each vehicle, one drop per note, in the
  order the van reaches the shops: the round's ``visit_sequence`` for the
  customer, then the customer's name for a shop the round does not order. Each
  drop shows the note's value and what its bills still owe -- the money the
  driver is to collect.

Both read the notes as they stand and write nothing.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from io import BytesIO
from uuid import UUID

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.batch_serial.models.batch_serial import BatchRecord
from app.common.firm_metadata import FirmMetadataReader, firm_today
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.customers.models import Customer
from app.delivery_note.models import (
    DeliveryNote,
    DeliveryNoteLine,
    DeliveryNoteLineBatch,
)
from app.products.models import Product

#: How many notes one sheet may cover: a morning's dispatch, not a year's.
MAX_NOTES = 300
#: Statuses whose goods still have to be picked or carried.
_LIVE = ("DRAFT", "APPROVED", "PARTIALLY_DISPATCHED", "DISPATCHED")
NO_VEHICLE = "No vehicle named"


def _money(value: Decimal) -> str:
    """Write an amount the way the sheets print it."""
    return f"{value:,.2f}"


def _quantity(value: Decimal) -> str:
    """Write a quantity without trailing zeros."""
    text = f"{value:,.4f}".rstrip("0").rstrip(".")
    return text or "0"


@dataclass(frozen=True, slots=True)
class PickRow:
    """One product, or one batch of it, to take off the shelves."""

    product_code: str
    product_name: str
    batch: str
    expiry: date | None
    quantity: Decimal


@dataclass(frozen=True, slots=True)
class Drop:
    """One note's stop on a vehicle's round."""

    sequence: int | None
    customer_name: str
    note_number: str
    value: Decimal
    to_collect: Decimal


class DispatchSheetService:
    """Build the pick list and the loading sheet for chosen notes."""

    def __init__(self, session: Session) -> None:
        """Bind to the firm's store."""
        self._session = session

    # ---- the figures -------------------------------------------------------

    def pick_rows(self, firm_id: UUID, note_ids: list[UUID]) -> list[PickRow]:
        """Return what to pick, by product and batch, in product order."""
        notes = self._notes(firm_id, note_ids)
        lines = list(
            self._session.scalars(
                select(DeliveryNoteLine).where(
                    DeliveryNoteLine.delivery_note_id.in_([n.id for n in notes]),
                    DeliveryNoteLine.is_deleted.is_(False),
                )
            ).all()
        )
        chosen: dict[UUID, list[tuple[UUID, Decimal]]] = defaultdict(list)
        for pick in self._session.scalars(
            select(DeliveryNoteLineBatch).where(
                DeliveryNoteLineBatch.delivery_note_line_id.in_(
                    [line.id for line in lines]
                ),
                DeliveryNoteLineBatch.is_deleted.is_(False),
            )
        ).all():
            chosen[pick.delivery_note_line_id].append(
                (pick.batch_id, Decimal(str(pick.quantity)))
            )
        totals: dict[tuple[UUID, UUID | None], Decimal] = defaultdict(Decimal)
        for line in lines:
            picks = chosen.get(line.id)
            if picks:
                for batch_id, quantity in picks:
                    totals[(line.product_id, batch_id)] += quantity
            else:
                totals[(line.product_id, None)] += Decimal(str(line.delivered_quantity))
        products = self._by_id(Product, {key[0] for key in totals})
        batches = self._by_id(BatchRecord, {key[1] for key in totals if key[1]})
        rows = [
            PickRow(
                product_code=(
                    products[product_id].code if product_id in products else ""
                ),
                product_name=(
                    products[product_id].name if product_id in products else "?"
                ),
                batch=(
                    batches[batch_id].batch_number
                    if batch_id is not None and batch_id in batches
                    else "Earliest expiry at dispatch"
                ),
                expiry=(
                    batches[batch_id].expiry_date
                    if batch_id is not None and batch_id in batches
                    else None
                ),
                quantity=quantity,
            )
            for (product_id, batch_id), quantity in totals.items()
            if quantity > 0
        ]
        return sorted(
            rows,
            key=lambda row: (
                row.product_code,
                row.expiry is None,
                row.expiry or date.max,
                row.batch,
            ),
        )

    def drops(self, firm_id: UUID, note_ids: list[UUID]) -> dict[str, list[Drop]]:
        """Return each vehicle's drops, in the order the round reaches them."""
        notes = self._notes(firm_id, note_ids)
        customers = self._by_id(Customer, {note.customer_id for note in notes})
        sequences = self._sequences(notes)
        owed = self._owed(firm_id, notes)
        vehicles: dict[str, list[Drop]] = defaultdict(list)
        for note in notes:
            customer = customers.get(note.customer_id)
            vehicles[(note.vehicle or "").strip() or NO_VEHICLE].append(
                Drop(
                    sequence=sequences.get(note.id),
                    customer_name=customer.name if customer else "?",
                    note_number=note.delivery_note_number,
                    value=Decimal(str(note.grand_total)),
                    to_collect=owed.get(note.id, Decimal("0")),
                )
            )
        return {
            vehicle: sorted(
                stops,
                key=lambda drop: (
                    drop.sequence is None,
                    drop.sequence or 0,
                    drop.customer_name,
                    drop.note_number,
                ),
            )
            for vehicle, stops in sorted(vehicles.items())
        }

    # ---- the paper ---------------------------------------------------------

    def pick_list_pdf(self, firm_id: UUID, note_ids: list[UUID]) -> bytes:
        """Return the pick list as an A4 PDF."""
        rows = self.pick_rows(firm_id, note_ids)
        table = [["Code", "Product", "Batch", "Expiry", "Quantity"]] + [
            [
                row.product_code,
                Paragraph(row.product_name, self._styles["BodyText"]),
                row.batch,
                row.expiry.strftime("%d-%m-%Y") if row.expiry else "",
                _quantity(row.quantity),
            ]
            for row in rows
        ]
        return self._render(
            firm_id,
            "Pick list",
            f"{len(note_ids)} delivery note(s)",
            [self._table(table, [22 * mm, 80 * mm, 38 * mm, 22 * mm, 22 * mm], 4)],
        )

    def loading_sheet_pdf(self, firm_id: UUID, note_ids: list[UUID]) -> bytes:
        """Return the loading sheet as an A4 PDF, one table per vehicle."""
        parts: list[object] = []
        for vehicle, stops in self.drops(firm_id, note_ids).items():
            parts.append(Paragraph(f"Vehicle: {vehicle}", self._styles["Heading3"]))
            table = [["#", "Customer", "Note", "Value", "To collect"]] + [
                [
                    str(index),
                    Paragraph(drop.customer_name, self._styles["BodyText"]),
                    drop.note_number,
                    _money(drop.value),
                    _money(drop.to_collect),
                ]
                for index, drop in enumerate(stops, start=1)
            ]
            table.append(
                [
                    "",
                    "Total",
                    f"{len(stops)} drop(s)",
                    _money(sum((d.value for d in stops), Decimal("0"))),
                    _money(sum((d.to_collect for d in stops), Decimal("0"))),
                ]
            )
            parts.append(
                self._table(table, [10 * mm, 78 * mm, 38 * mm, 29 * mm, 29 * mm], 3)
            )
            parts.append(Spacer(1, 6 * mm))
        return self._render(
            firm_id, "Loading sheet", f"{len(note_ids)} delivery note(s)", parts
        )

    # ---- helpers -----------------------------------------------------------

    _styles = getSampleStyleSheet()

    def _render(
        self, firm_id: UUID, title: str, subtitle: str, parts: list[object]
    ) -> bytes:
        """Lay out a titled A4 page around the given flowables."""
        firm = FirmMetadataReader(self._session).get(firm_id)
        buffer = BytesIO()
        document = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=12 * mm,
            rightMargin=12 * mm,
            topMargin=12 * mm,
            bottomMargin=12 * mm,
            title=title,
        )
        header = [
            Paragraph(firm.name or "", self._styles["Title"]),
            Paragraph(
                f"{title} -- {subtitle} -- printed "
                f"{firm_today(self._session, firm_id).strftime('%d-%m-%Y')}",
                self._styles["Normal"],
            ),
            Spacer(1, 4 * mm),
        ]
        document.build([*header, *parts])
        return buffer.getvalue()

    @staticmethod
    def _table(rows: list[list[object]], widths: list[float], right_from: int) -> Table:
        """Return a ruled table, numbers right-aligned from ``right_from``."""
        table = Table(rows, colWidths=widths, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
                    ("GRID", (0, 1), (-1, -1), 0.25, colors.grey),
                    ("ALIGN", (right_from, 0), (-1, -1), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        return table

    def _notes(self, firm_id: UUID, note_ids: list[UUID]) -> list[DeliveryNote]:
        """Return the firm's live notes named, refusing any it cannot find."""
        wanted = list(dict.fromkeys(note_ids))
        if not wanted:
            raise ValidationError("Choose at least one delivery note.")
        if len(wanted) > MAX_NOTES:
            raise ValidationError(f"A sheet covers at most {MAX_NOTES} notes.")
        notes = list(
            self._session.scalars(
                select(DeliveryNote).where(
                    DeliveryNote.firm_id == firm_id,
                    DeliveryNote.id.in_(wanted),
                    DeliveryNote.is_deleted.is_(False),
                )
            ).all()
        )
        if len(notes) != len(wanted):
            raise ResourceNotFoundError("One of those delivery notes was not found.")
        dead = [note.delivery_note_number for note in notes if note.status not in _LIVE]
        if dead:
            raise ValidationError(
                "These notes have nothing left to pick or carry: " + ", ".join(dead)
            )
        return notes

    def _by_id[ModelT](self, model: type[ModelT], ids: set[UUID]) -> dict[UUID, ModelT]:
        """Read rows of ``model`` by id, once."""
        if not ids:
            return {}
        return {
            row.id: row  # type: ignore[attr-defined]
            for row in self._session.scalars(
                select(model).where(model.id.in_(ids))  # type: ignore[attr-defined]
            ).all()
        }

    def _sequences(self, notes: list[DeliveryNote]) -> dict[UUID, int]:
        """Return each note's place on its round, where the round orders it.

        A note's round is its territory, or the territory of the route it
        names; the place is the customer's ``visit_sequence`` on that round.
        """
        from app.sales.models.territory import (
            TerritoryCustomerAssignment,
            TerritoryRouteProfile,
        )

        route_ids = {note.route_id for note in notes if note.route_id}
        route_territory: dict[UUID, UUID] = (
            {
                route.id: route.territory_id
                for route in self._session.scalars(
                    select(TerritoryRouteProfile).where(
                        TerritoryRouteProfile.id.in_(route_ids)
                    )
                ).all()
            }
            if route_ids
            else {}
        )
        rounds: dict[UUID, UUID] = {}
        for note in notes:
            territory = note.territory_id or (
                route_territory.get(note.route_id) if note.route_id else None
            )
            if territory is not None:
                rounds[note.id] = territory
        if not rounds:
            return {}
        order: dict[tuple[UUID, UUID], int] = {
            (row.territory_id, row.customer_id): int(row.visit_sequence)
            for row in self._session.scalars(
                select(TerritoryCustomerAssignment).where(
                    TerritoryCustomerAssignment.territory_id.in_(set(rounds.values())),
                    TerritoryCustomerAssignment.is_deleted.is_(False),
                    TerritoryCustomerAssignment.visit_sequence.is_not(None),
                )
            ).all()
            if row.visit_sequence is not None
        }
        return {
            note.id: order[(rounds[note.id], note.customer_id)]
            for note in notes
            if note.id in rounds and (rounds[note.id], note.customer_id) in order
        }

    def _owed(self, firm_id: UUID, notes: list[DeliveryNote]) -> dict[UUID, Decimal]:
        """Return what the bills raised against each note still owe."""
        from app.sales_invoice.models import SalesInvoiceSource
        from app.settlements.services import ReceiptService

        billed: dict[UUID, set[UUID]] = defaultdict(set)
        for source in self._session.scalars(
            select(SalesInvoiceSource).where(
                SalesInvoiceSource.firm_id == firm_id,
                SalesInvoiceSource.source_document_id.in_([n.id for n in notes]),
                SalesInvoiceSource.is_deleted.is_(False),
            )
        ).all():
            billed[source.source_document_id].add(source.sales_invoice_id)
        if not billed:
            return {}
        outstanding: dict[UUID, Decimal] = {}
        receipts = ReceiptService(self._session)
        for customer_id in {note.customer_id for note in notes}:
            for bill in receipts.outstanding_invoices(
                firm_id=firm_id, party_id=customer_id
            ):
                outstanding[bill.invoice_id] = Decimal(str(bill.outstanding_amount))
        return {
            note_id: sum(
                (outstanding.get(i, Decimal("0")) for i in bills), Decimal("0")
            )
            for note_id, bills in billed.items()
        }


__all__ = ["DispatchSheetService", "Drop", "PickRow"]

"""The PAN reports: customers and suppliers whose PAN needs attention (PLT-11).

A deductee with no PAN costs the higher TDS rate (section 206AA); a customer
with none cannot be matched to the TDS it deducts from the firm's bills; and a
PAN that is not characters 3 to 12 of the party's GSTIN is wrong on one side
or the other. `settle_pan` refuses both
on every write since backlog 53 item 2, but records typed or imported before
it -- and never edited since -- still hold them. These two lists find them,
one per side, each row naming what is wrong (`pan_problem`).

Only the four columns a row shows are read, for every live party: the format
check is a pattern no SQL dialect here shares, so the narrowing is done on
the plain values rather than by loading whole rows.
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.validation import pan_in_gstin, pan_problem
from app.customers.models import Customer
from app.vendors.models import Vendor


class PanReportRow(BaseModel):
    """One party whose PAN needs attention, and what is wrong with it."""

    model_config = ConfigDict(extra="forbid")

    party_id: UUID
    code: str
    name: str
    status: str
    gstin: str | None
    pan: str | None
    #: Characters 3 to 12 of the GSTIN, where they are a PAN.
    pan_in_gstin: str | None
    problem: str


def _rows(
    found: list[tuple[UUID, str, str, str, str | None, str | None]],
) -> list[PanReportRow]:
    """Keep the parties whose PAN has a problem, in code order."""
    rows: list[PanReportRow] = []
    for party_id, code, name, status, gstin, pan in found:
        problem = pan_problem(pan, gstin)
        if problem is None:
            continue
        rows.append(
            PanReportRow(
                party_id=party_id,
                code=code,
                name=name,
                status=status,
                gstin=gstin,
                pan=pan,
                pan_in_gstin=pan_in_gstin(gstin),
                problem=problem,
            )
        )
    return rows


def customer_pan_report(session: Session, *, firm_id: UUID) -> list[PanReportRow]:
    """Return the firm's live customers whose PAN needs attention."""
    found = session.execute(
        select(
            Customer.id,
            Customer.code,
            Customer.display_name,
            Customer.status,
            Customer.gst_number,
            Customer.pan_number,
        )
        .where(Customer.firm_id == firm_id, Customer.is_deleted.is_(False))
        .order_by(Customer.code)
    ).all()
    return _rows([tuple(row) for row in found])


def vendor_pan_report(session: Session, *, firm_id: UUID) -> list[PanReportRow]:
    """Return the firm's live suppliers whose PAN needs attention."""
    found = session.execute(
        select(
            Vendor.id,
            Vendor.code,
            Vendor.display_name,
            Vendor.status,
            Vendor.gstin,
            Vendor.pan,
        )
        .where(Vendor.firm_id == firm_id, Vendor.is_deleted.is_(False))
        .order_by(Vendor.code)
    ).all()
    return _rows([tuple(row) for row in found])

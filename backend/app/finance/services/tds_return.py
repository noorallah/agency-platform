"""The quarterly TDS return, Form 26Q: what the firm deducted, laid out to file.

Backlog 53.1, the 26Q export. Form 26Q is the quarterly statement of tax
deducted at source on everything except salary (salary is Form 24Q). It is
prepared in the Protean (NSDL) Return Preparation Utility (RPU), which checks
it with the File Validation Utility (FVU) and writes the ``.fvu`` file that is
uploaded.

**Why a workbook and not the FVU text file.** The FVU's input is a caret-
separated text file whose every deductee row hangs off a challan row, and a
challan row needs the challan's BSR code, its serial number, the date the bank
received it and the amount it carried. This product records each deduction
but not the challan it was paid by -- that is still a journal (53.1, "Left: a
challan screen"). A text file with those fields blank fails the FVU on its
first row, and one with them guessed is worse. So the export is the part the
firm's books know, in the shape the RPU asks for:

* **Deductor** -- the firm's name, TAN and PAN, the year, quarter and the
  assessment year, with the totals and anything that will stop the return
  (no TAN, deductees without a PAN).
* **Deductees** -- Annexure I, one row per deduction, in the RPU deductee
  sheet's order: section, deductee code, PAN, name, date paid, amount paid,
  tax deducted, the rate and the reason code for a higher rate. The challan
  serial is left for the person filing to match, which the RPU does by
  pasting these rows under the challan.
* **Challans due** -- what should have been deposited, by section and month
  of deduction, with the due date, to tick against the challans actually paid.
* **Not in this return** -- deductions on a reversed payment or cancelled
  expense, and salary, so the accountant sees them rather than wondering
  where they went.

``format=csv`` answers the deductee sheet alone, for a CA whose own software
imports a flat file.

The quarter is the return's -- April to June is Q1 -- whatever the firm's own
financial year, because the return is filed on the government's calendar. A
period is named by financial year and quarter, so it is always exactly one
quarter; a longer span is a different return.
"""

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.orm import Session

from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import ValidationError
from app.core.pagination.reports import ReportWindow
from app.finance.services.tds_register import NO_PAN, TdsRegisterService, TdsRow

if TYPE_CHECKING:
    from openpyxl.styles import Font  # type: ignore[import-untyped]
    from openpyxl.worksheet.worksheet import (  # type: ignore[import-untyped]
        Worksheet,
    )

ZERO = Decimal("0")
#: What the return says in place of a PAN the deductee never gave.
PAN_NOT_AVAILABLE = "PANNOTAVBL"
#: The return's code for a deduction at the higher rate because the deductee
#: gave no PAN (section 206AA).
HIGHER_RATE_NO_PAN = "C"
#: The sections filed on another form: salary is Form 24Q.
_NOT_26Q = frozenset({"192"})
#: The states of a document whose deduction stands.
_LIVE = frozenset({"POSTED"})
_FINANCIAL_YEAR = re.compile(r"^(\d{4})-(\d{2}|\d{4})$")
_QUARTER = re.compile(r"^Q?([1-4])$")

DEDUCTEE_HEADINGS: tuple[str, ...] = (
    "Sr No",
    "Challan Serial No",
    "Section",
    "Deductee Code",
    "Deductee PAN",
    "Deductee Name",
    "Date of Payment or Credit",
    "Amount Paid or Credited",
    "TDS",
    "Surcharge",
    "Education Cess",
    "Total Tax Deducted",
    "Date of Deduction",
    "Rate of Deduction (%)",
    "Reason for Higher Deduction",
    "Our Document",
    "Party Code",
)


@dataclass(frozen=True)
class ReturnQuarter:
    """One quarter of one financial year, as the return names it."""

    financial_year: str
    quarter: int
    start: date
    end: date

    @property
    def label(self) -> str:
        """``Q1 2026-27``, as the TDS register names a quarter."""
        return f"Q{self.quarter} {self.financial_year}"

    @property
    def assessment_year(self) -> str:
        """The assessment year the return belongs to: the year after."""
        first = int(self.financial_year[:4]) + 1
        return f"{first}-{(first + 1) % 100:02d}"

    @property
    def file_stem(self) -> str:
        """``26Q-2026-27-Q1``, for the file name."""
        return f"26Q-{self.financial_year}-Q{self.quarter}"


def return_quarter(financial_year: str, quarter: str) -> ReturnQuarter:
    """Read a financial year (``2026-27``) and a quarter (``Q1``).

    Raises:
        ValidationError: If either is not in that form, or the two years of
            the financial year are not consecutive.

    """
    year_match = _FINANCIAL_YEAR.fullmatch(financial_year.strip())
    if year_match is None:
        raise ValidationError(
            "Name the financial year as 2026-27: the year it starts and the "
            "year it ends.",
            details={"field": "financial_year"},
        )
    first = int(year_match.group(1))
    second = year_match.group(2)
    if int(second) != ((first + 1) % 100 if len(second) == 2 else first + 1):
        raise ValidationError(
            f"{financial_year} is not a financial year: it runs April to March, "
            f"so {first} is followed by {first + 1}.",
            details={"field": "financial_year"},
        )
    quarter_match = _QUARTER.fullmatch(quarter.strip().upper())
    if quarter_match is None:
        raise ValidationError(
            "A TDS return covers one quarter: Q1 (April to June), Q2 (July to "
            "September), Q3 (October to December) or Q4 (January to March).",
            details={"field": "quarter"},
        )
    number = int(quarter_match.group(1))
    start_month = 4 + (number - 1) * 3
    start_year = first if start_month <= 12 else first + 1
    start_month = (start_month - 1) % 12 + 1
    start = date(start_year, start_month, 1)
    after = (
        date(start_year + 1, 1, 1)
        if start_month + 3 > 12
        else date(start_year, start_month + 3, 1)
    )
    return ReturnQuarter(
        financial_year=f"{first}-{(first + 1) % 100:02d}",
        quarter=number,
        start=start,
        end=after - timedelta(days=1),
    )


@dataclass(frozen=True)
class DeducteeRow:
    """One deduction as Annexure I of Form 26Q states it."""

    serial: int
    section: str
    section_name: str
    #: ``01`` a company, ``02`` anybody else, read off the PAN's fourth
    #: letter; blank when there is no PAN to read it from.
    deductee_code: str
    pan: str
    party_name: str
    party_code: str | None
    payment_date: date
    amount_paid: Decimal
    tds_amount: Decimal
    #: The rate actually deducted at, to four places, as the return states it.
    rate_percent: Decimal
    #: ``C`` where no PAN was given (deducted at the higher rate); blank else.
    higher_rate_reason: str
    document_type: str
    document_number: str


@dataclass(frozen=True)
class ChallanDue:
    """The tax deducted under one section in one month, and when it was due."""

    section: str
    section_name: str
    month: str
    deductions: int
    tds_amount: Decimal
    due_date: date


@dataclass(frozen=True)
class ExcludedRow:
    """A deduction in the quarter that this return does not carry, and why."""

    row: TdsRow
    reason: str


@dataclass(frozen=True)
class TdsReturn:
    """Everything the 26Q export holds for one quarter."""

    period: ReturnQuarter
    firm_name: str
    tan: str | None
    pan: str | None
    deductees: list[DeducteeRow]
    challans: list[ChallanDue]
    excluded: list[ExcludedRow]

    @property
    def problems(self) -> list[str]:
        """What will stop, or change, the return, in the accountant's words."""
        found: list[str] = []
        if not self.tan:
            found.append(
                "The firm has no TAN. A TDS return is filed under the "
                "deductor's TAN: enter it under Firm Settings."
            )
        missing = sum(1 for row in self.deductees if row.pan == PAN_NOT_AVAILABLE)
        if missing:
            found.append(
                f"{missing} deduction(s) name no PAN. They are filed as "
                f"{PAN_NOT_AVAILABLE} with reason {HIGHER_RATE_NO_PAN}: the "
                "deduction must be at the higher rate (section 206AA)."
            )
        return found


def deductee_code(pan: str) -> str:
    """``01`` for a company's PAN, ``02`` for anybody else's, blank for none."""
    if pan == PAN_NOT_AVAILABLE:
        return ""
    return "01" if pan[3:4] == "C" else "02"


def due_date(deducted_on: date) -> date:
    """When tax deducted on ``deducted_on`` has to reach the government.

    The seventh of the next month; for a deduction in March, the thirtieth of
    April (rule 30 of the Income-tax Rules, a deductor other than the
    government).
    """
    if deducted_on.month == 3:
        return date(deducted_on.year, 4, 30)
    if deducted_on.month == 12:
        return date(deducted_on.year + 1, 1, 7)
    return date(deducted_on.year, deducted_on.month + 1, 7)


class TdsReturnService:
    """Build the 26Q export for a firm and a quarter. Reads; stores nothing."""

    def __init__(self, session: Session) -> None:
        """Bind to the firm's store."""
        self._session = session

    def build(self, firm_id: UUID, period: ReturnQuarter) -> TdsReturn:
        """Read the quarter's deductions and lay them out as the return does."""
        rows = TdsRegisterService(self._session).deducted_by_firm(
            firm_id, ReportWindow(period.start, period.end)
        )
        deductees: list[DeducteeRow] = []
        excluded: list[ExcludedRow] = []
        for row in rows:
            if row.section in _NOT_26Q:
                excluded.append(ExcludedRow(row, "Salary is filed on Form 24Q."))
                continue
            if row.status not in _LIVE:
                excluded.append(
                    ExcludedRow(
                        row,
                        f"The {row.document_type.lower()} is {row.status.lower()}. "
                        "If the tax was already deposited, claim it back or "
                        "carry it in the next challan.",
                    )
                )
                continue
            deductees.append(self._deductee(len(deductees) + 1, row))
        firm = FirmMetadataReader(self._session).get(firm_id)
        return TdsReturn(
            period=period,
            firm_name=firm.name or "",
            tan=firm.tan_number,
            pan=firm.pan_number,
            deductees=deductees,
            challans=_challans(deductees),
            excluded=excluded,
        )

    @staticmethod
    def _deductee(serial: int, row: TdsRow) -> DeducteeRow:
        pan = PAN_NOT_AVAILABLE if row.pan == NO_PAN else row.pan
        rate = (
            (row.tds_amount * 100 / row.gross_amount).quantize(Decimal("0.0001"))
            if row.gross_amount
            else ZERO
        )
        return DeducteeRow(
            serial=serial,
            section=row.section,
            section_name=row.section_name,
            deductee_code=deductee_code(pan),
            pan=pan,
            party_name=row.party_name,
            party_code=row.party_code,
            payment_date=row.date,
            amount_paid=row.gross_amount,
            tds_amount=row.tds_amount,
            rate_percent=rate,
            higher_rate_reason=(HIGHER_RATE_NO_PAN if pan == PAN_NOT_AVAILABLE else ""),
            document_type=row.document_type,
            document_number=row.document_number,
        )


def _challans(rows: list[DeducteeRow]) -> list[ChallanDue]:
    """Total the deductions by section and month: one challan each is due."""
    totals: dict[tuple[str, date], tuple[str, int, Decimal]] = {}
    for row in rows:
        month = row.payment_date.replace(day=1)
        name, count, amount = totals.get(
            (row.section, month), (row.section_name, 0, ZERO)
        )
        totals[(row.section, month)] = (name, count + 1, amount + row.tds_amount)
    return [
        ChallanDue(
            section=section,
            section_name=name,
            month=month.strftime("%B %Y"),
            deductions=count,
            tds_amount=amount,
            due_date=due_date(month),
        )
        for (section, month), (name, count, amount) in sorted(
            totals.items(), key=lambda item: (item[0][1], item[0][0])
        )
    ]


def _deductee_cells(row: DeducteeRow) -> list[object]:
    """One deductee row in the order of ``DEDUCTEE_HEADINGS``."""
    return [
        row.serial,
        "",
        row.section,
        row.deductee_code,
        row.pan,
        row.party_name,
        row.payment_date,
        row.amount_paid,
        row.tds_amount,
        ZERO,
        ZERO,
        row.tds_amount,
        row.payment_date,
        row.rate_percent,
        row.higher_rate_reason,
        f"{row.document_type} {row.document_number}",
        row.party_code or "",
    ]


def deductees_csv(tds_return: TdsReturn) -> str:
    """Write the deductee sheet alone as CSV, dates as ``dd-mm-yyyy``."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(DEDUCTEE_HEADINGS)
    for row in tds_return.deductees:
        writer.writerow(
            [
                cell.strftime("%d-%m-%Y") if isinstance(cell, date) else cell
                for cell in _deductee_cells(row)
            ]
        )
    return buffer.getvalue()


def return_workbook(tds_return: TdsReturn) -> bytes:
    """Write the four-sheet workbook the module docstring describes.

    Raises:
        ValidationError: If the XLSX library is not installed.

    """
    try:
        from openpyxl import Workbook  # type: ignore[import-untyped]
        from openpyxl.styles import Font
    except ImportError as error:
        raise ValidationError(
            "XLSX export dependency is unavailable. Install openpyxl."
        ) from error
    period = tds_return.period
    workbook = Workbook()
    deductor = workbook.active
    deductor.title = "Deductor"
    deductees = tds_return.deductees
    for line in (
        ("Form", "26Q (TDS on payments other than salary)"),
        ("Deductor", tds_return.firm_name),
        ("TAN", tds_return.tan or "NOT ENTERED"),
        ("PAN", tds_return.pan or "NOT ENTERED"),
        ("Financial year", period.financial_year),
        ("Quarter", f"Q{period.quarter}"),
        ("Assessment year", period.assessment_year),
        ("Period", f"{period.start:%d-%m-%Y} to {period.end:%d-%m-%Y}"),
        ("Deductions", len(deductees)),
        ("Amount paid or credited", sum((r.amount_paid for r in deductees), ZERO)),
        ("Tax deducted", sum((r.tds_amount for r in deductees), ZERO)),
    ):
        deductor.append(list(line))
    deductor.append([])
    deductor.append(["To check before filing"])
    deductor.cell(row=deductor.max_row, column=1).font = Font(bold=True)
    for problem in tds_return.problems or ["Nothing found."]:
        deductor.append([problem])
    deductor.append([])
    deductor.append(["How to use this file"])
    deductor.cell(row=deductor.max_row, column=1).font = Font(bold=True)
    for note in (
        "This is not an FVU file. Prepare the return in the Protean (NSDL) "
        "Return Preparation Utility, or hand this file to whoever files it.",
        "Enter each challan in the RPU from its counterfoil -- BSR code, date "
        "deposited, challan serial and amount -- then paste the Deductees "
        "rows under the challan that paid them, filling Challan Serial No.",
        "Challans due totals the tax by section and month, to tick against "
        "the challans actually paid.",
        "Not in this return lists deductions this return leaves out, and why.",
    ):
        deductor.append([note])
    deductor.column_dimensions["A"].width = 26
    deductor.column_dimensions["B"].width = 50

    sheet = workbook.create_sheet("Deductees")
    sheet.append(list(DEDUCTEE_HEADINGS))
    for row in deductees:
        sheet.append(_deductee_cells(row))
    _style(sheet, Font)

    challans = workbook.create_sheet("Challans due")
    challans.append(
        ["Section", "Covers", "Month deducted", "Deductions", "TDS", "Due by"]
    )
    for due in tds_return.challans:
        challans.append(
            [
                due.section,
                due.section_name,
                due.month,
                due.deductions,
                due.tds_amount,
                due.due_date,
            ]
        )
    _style(challans, Font)

    left_out = workbook.create_sheet("Not in this return")
    left_out.append(
        ["Date", "Document", "Deductee", "PAN", "Section", "TDS", "Status", "Why"]
    )
    for item in tds_return.excluded:
        left_out.append(
            [
                item.row.date,
                f"{item.row.document_type} {item.row.document_number}",
                item.row.party_name,
                item.row.pan,
                item.row.section,
                item.row.tds_amount,
                item.row.status,
                item.reason,
            ]
        )
    _style(left_out, Font)

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _style(sheet: "Worksheet", font: type["Font"]) -> None:
    """Bold the heading row, freeze it, and widen the columns to fit."""
    for cell in next(sheet.iter_rows(), ()):
        cell.font = font(bold=True)
        sheet.column_dimensions[cell.column_letter].width = max(
            12, len(str(cell.value)) + 4
        )
    sheet.freeze_panes = "A2"
    for column in sheet.iter_cols(min_row=2):
        for cell in column:
            if isinstance(cell.value, date):
                cell.number_format = "DD-MM-YYYY"

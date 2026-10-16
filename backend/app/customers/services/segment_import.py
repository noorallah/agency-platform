"""Bring a firm's customer segments (outlet types) in from a spreadsheet.

Swathi gap G3. The rules every master import keeps -- check every row, write
all or nothing, match headings loosely, update on request -- live in
``app.common.file_import``. What is particular to segments:

* **A segment's code is its key.** A row whose code is already a segment
  updates it when the caller asks to update, and is refused otherwise.
* **The file does not make price levels.** The level a segment buys at is a
  choice, and a guessed one is wrong silently, so a *PriceLevel* must already
  exist.
* **Every row goes through** ``CustomerGroupService.stage_create_group`` or
  ``stage_update_group`` -- the same code and name clash, price-level check
  and audit row as the form -- and the file commits once.
"""

# ruff: noqa: D102, D107

from decimal import Decimal
from uuid import UUID

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common import file_import
from app.common.file_import import (
    Column,
    FileImporter,
    ImportIssue,
    ImportReport,
    ImportRow,
    RowReader,
    schema_issues,
    service_issue,
)
from app.core.exceptions import ApplicationError
from app.customers.models import CustomerGroup
from app.customers.schemas import CustomerGroupWrite
from app.customers.services.customer_group_service import CustomerGroupService
from app.customers.services.customer_import import firm_segments
from app.pricing.models import PriceLevel

#: The template, in the order it is laid out.
COLUMNS: tuple[Column, ...] = (
    Column(
        "Code",
        ("segmentcode", "groupcode", "outlettypecode", "typecode"),
        True,
        "The segment's code; unique among the firm's segments.",
        "RETAIL",
    ),
    Column(
        "Name",
        (
            "segmentname",
            "segment",
            "groupname",
            "group",
            "outlettype",
            "outlettypename",
        ),
        False,
        "The segment's name; unique among the firm's segments. Needed for a "
        "new segment.",
        "Retailer",
    ),
    Column(
        "Description",
        ("details", "remarks", "notes"),
        False,
        "Anything worth saying about the segment. May be blank.",
        "Kirana and general stores",
    ),
    Column(
        "Discount",
        ("discountpercent", "defaultdiscount", "rate"),
        False,
        "The percentage everyone in the segment is normally given, 0 to 100. "
        "Blank means 0 for a new segment.",
        "2.5",
    ),
    Column(
        "PriceLevel",
        ("level", "pricelevelcode", "pricelevelname", "pricecategory"),
        False,
        "The price level everyone in the segment buys at, by code or name (see "
        "the Lists sheet). May be blank.",
        "",
    ),
    Column(
        "Active",
        ("isactive", "enabled", "inuse"),
        False,
        "Yes or No. Blank means Yes for a new segment.",
        "Yes",
    ),
)

#: The write-schema field each heading fills, for naming a schema refusal.
_FIELD_HEADINGS: dict[str, str] = {
    "code": "Code",
    "name": "Name",
    "description": "Description",
    "default_discount_percent": "Discount",
    "price_level_id": "PriceLevel",
    "is_active": "Active",
}


class SegmentFileImporter(FileImporter[CustomerGroup]):
    """Check a segment file row by row, and import it whole or not at all."""

    COLUMNS = COLUMNS
    NOUN = "segment"

    def __init__(self, session: Session, service: CustomerGroupService) -> None:
        super().__init__(session)
        self._service = service
        self._levels: list[PriceLevel] = []

    def _prepare(self, firm_id: UUID) -> None:
        self._levels = firm_price_levels(self._session, firm_id)

    def _stored(self, firm_id: UUID) -> dict[str, CustomerGroup]:
        return {
            group.code.strip().upper(): group
            for group in firm_segments(self._session, firm_id)
        }

    def _commit(self) -> None:
        self._session.commit()

    def _stage(
        self,
        row: ImportRow,
        code: str,
        current: CustomerGroup | None,
        firm_id: UUID,
        actor_id: UUID,
        report: ImportReport[CustomerGroup],
    ) -> None:
        issues: list[ImportIssue] = []
        values = self._values(RowReader(row, code, issues), code, current)
        if issues:
            report.issues.extend(issues)
            return
        try:
            data = CustomerGroupWrite.model_validate(values)
        except PydanticValidationError as error:
            report.issues.extend(schema_issues(error, row, code, _FIELD_HEADINGS))
            return
        try:
            if current is None:
                group = self._service.stage_create_group(
                    data, firm_id=firm_id, actor_id=actor_id
                )
            else:
                group = self._service.stage_update_group(
                    current.id, data, firm_id=firm_id, actor_id=actor_id
                )
        except ApplicationError as error:
            # Every guard runs before the row is written, so the session is
            # still sound and the rest of the file can be checked.
            report.issues.append(service_issue(error, row, code, _FIELD_HEADINGS))
            return
        if current is None:
            report.to_create += 1
        else:
            report.to_update += 1
        report.records.append(group)

    def _values(
        self, reader: RowReader, code: str, current: CustomerGroup | None
    ) -> dict[str, object]:
        """Turn one row's cells into write-schema values.

        The write replaces the whole segment, so on an update a blank cell, or
        a column the file does not have, is filled from what it already holds.
        """
        values: dict[str, object] = {"code": code}
        name = reader.text("Name").strip()
        if name:
            values["name"] = name
        elif current is not None:
            values["name"] = current.name
        else:
            reader.fail("Name", "is needed for a new segment.")
        description = reader.text("Description").strip()
        if description:
            values["description"] = description
        elif current is not None:
            values["description"] = current.description
        discount = reader.number("Discount")
        if discount is not None:
            values["default_discount_percent"] = discount
        else:
            values["default_discount_percent"] = (
                Decimal("0") if current is None else current.default_discount_percent
            )
        level = reader.text("PriceLevel").strip()
        if level:
            found = find_price_level(self._levels, level)
            if found is None:
                reader.fail(
                    "PriceLevel",
                    f"'{level}' is not one of the firm's price levels; add it "
                    "first, or name one on the Lists sheet.",
                )
            else:
                values["price_level_id"] = found.id
        elif current is not None:
            values["price_level_id"] = current.price_level_id
        active = reader.flag("Active")
        if active is not None:
            values["is_active"] = active
        elif current is not None:
            values["is_active"] = current.is_active
        return values


def firm_price_levels(session: Session, firm_id: UUID) -> list[PriceLevel]:
    """Return the firm's live price levels by code."""
    return list(
        session.scalars(
            select(PriceLevel)
            .where(PriceLevel.firm_id == firm_id, PriceLevel.is_deleted.is_(False))
            .order_by(PriceLevel.code)
        ).all()
    )


def find_price_level(pool: list[PriceLevel], value: str) -> PriceLevel | None:
    """Find a price level by code, then by name, ignoring case."""
    wanted = value.strip().lower()
    for item in pool:
        if item.code.lower() == wanted:
            return item
    for item in pool:
        if item.name.strip().lower() == wanted:
            return item
    return None


def template_workbook(session: Session, firm_id: UUID) -> bytes:
    """Build the XLSX template: the sheet to fill, the notes, and the lists."""
    segments = firm_segments(session, firm_id)
    levels = firm_price_levels(session, firm_id)
    return file_import.template_workbook(
        sheet_title="Segments",
        columns=COLUMNS,
        notes=[
            "One row is one customer segment (outlet type). Its code is its "
            "key: a row whose code is already a segment updates it when you "
            "choose to update.",
            "A price level must already exist; the file does not make them.",
        ],
        lists_header=[
            "Segment code",
            "Segment name",
            "Price level code",
            "Price level",
        ],
        lists=[
            [item.code for item in segments],
            [item.name for item in segments],
            [item.code for item in levels],
            [item.name for item in levels],
        ],
    )


def template_csv() -> str:
    """Build the CSV template: the headings and one example row."""
    return file_import.template_csv(COLUMNS)

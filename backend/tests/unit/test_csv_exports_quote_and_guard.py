"""A hand-built CSV export quotes a comma and never hands over a formula.

D-MST-22 (c): several exports built each record with ``",".join``, so a name
holding a comma shifted every column after it and a name beginning with ``=``
arrived in the spreadsheet as a formula. They now build the record with
``csv_line`` (``app/core/utils/csv_text.py``); the last test here fails the
build when an export goes back to joining by hand.
"""

import ast
import csv
import io
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.file_import import read_grid
from app.core.database.base import Base
from app.core.utils.csv_text import (
    SheetWriter,
    csv_line,
    read_records,
    sheet_cell,
    unsheet,
)
from app.firms.models import Firm
from app.goods_receipt.models import GoodsReceipt
from app.goods_receipt.services import GoodsReceiptService
from app.sales.models import (
    SalesTerritoryNode,
    TerritoryCustomerAssignment,
    TerritorySalesmanAssignment,
)
from app.sales.services.territory_service import SalesTerritoryService

_APP = Path(__file__).resolve().parents[2] / "app"


def _session() -> tuple[Session, Firm]:
    """Return a session over an empty schema, and one firm in it."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    firm = Firm(
        name="Export Firm",
        code="EXPORT",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(firm)
    session.commit()
    return session, firm


def _records(text: str) -> list[list[str]]:
    """Read an export the way a spreadsheet does, heading left off."""
    return list(csv.reader(text.splitlines()))[1:]


def test_a_record_keeps_its_cells_and_a_number_stays_a_number() -> None:
    """A comma is one cell, a formula is text, and minus five is minus five."""
    line = csv_line(["Tea, gold", "=1+1", Decimal("-5.0000"), -3, None, "plain", 'a"b'])

    assert line == '"Tea, gold",\'=1+1,-5.0000,-3,,plain,"a""b"'
    assert next(csv.reader([line])) == [
        "Tea, gold",
        "'=1+1",
        "-5.0000",
        "-3",
        "",
        "plain",
        'a"b',
    ]
    # Text that only looks like a number is still guarded.
    assert csv_line(["-5", "+91 98"]) == "'-5,'+91 98"


def test_the_sheet_writer_guards_text_and_leaves_a_number_alone() -> None:
    """D-MST-23: what ``csv.writer`` wrote as it was, ``SheetWriter`` guards.

    A figure an export formatted itself (``-150.00``) is a number, not a
    formula, and stays one; ``+91 98400 12345`` is text a spreadsheet would
    run, and is guarded.
    """
    buffer = io.StringIO()
    writer = SheetWriter(buffer, lineterminator="\n")
    writer.writerow(
        ["=1+1", "-150.00", "1,250.5", "+919876543210", "+91 98400 12345", 5, None]
    )
    writer.writerows([["@cmd", Decimal("-2.5"), "Tea, gold"]])

    assert list(csv.reader(buffer.getvalue().splitlines())) == [
        ["'=1+1", "-150.00", "1,250.5", "+919876543210", "'+91 98400 12345", "5", ""],
        ["'@cmd", "-2.5", "Tea, gold"],
    ]
    assert sheet_cell("-") == "'-"
    assert sheet_cell(Decimal("-1")) == Decimal("-1")


def test_an_import_takes_the_guard_off_again() -> None:
    """A file exported here and read back holds what was typed."""
    assert unsheet("'=1+1") == "=1+1"
    assert unsheet("'+91 98400 12345") == "+91 98400 12345"
    # Only the guard: a name that begins with an apostrophe keeps it.
    assert unsheet("'Sri Ram's") == "'Sri Ram's"
    assert unsheet("'") == "'"

    buffer = io.StringIO()
    writer = SheetWriter(buffer, lineterminator="\n")
    writer.writerow(["Name", "Phone"])
    writer.writerow(["=HYPERLINK(1)", "+91 98400 12345"])
    exported = buffer.getvalue()

    assert list(read_records(exported)) == [
        {"Name": "=HYPERLINK(1)", "Phone": "+91 98400 12345"}
    ]
    headings, rows = read_grid(exported.encode("utf-8"), "csv")
    assert headings == ["Name", "Phone"]
    assert rows == [["=HYPERLINK(1)", "+91 98400 12345"]]


#: Writers that keep the bare ``csv.writer``: ``path`` and why.
_BARE_WRITER: dict[str, str] = {
    "core/utils/csv_text.py": "SheetWriter itself wraps it",
    "finance/services/tds_return.py": (
        "the TDS deductee sheet, taken into the return utility as written"
    ),
    "settlements/services/payment_runs.py": (
        "the bank's payment file, read by the bank's software as written"
    ),
    "common/file_import.py": (
        "remap_headings rewrites an uploaded file for the import that reads "
        "it next, which takes any guard off; nobody opens it"
    ),
}


def test_every_export_writes_through_the_sheet_writer() -> None:
    """A new export with the bare ``csv.writer`` would hand over a formula."""
    found = sorted(
        path.relative_to(_APP).as_posix()
        for path in _APP.rglob("*.py")
        if "csv.writer(" in path.read_text(encoding="utf-8")
    )

    assert found == sorted(_BARE_WRITER), (
        "These write CSV with the bare csv.writer, which runs a cell that "
        "begins with '=': write with SheetWriter (app/core/utils/csv_text.py) "
        f"{sorted(set(found) - set(_BARE_WRITER))}"
    )


def test_the_territory_assignment_exports_quote_and_guard() -> None:
    """A territory called ``North, upper`` is one cell; ``=SUM(A1)`` is text."""
    session, firm = _session()
    comma = SalesTerritoryNode(
        firm_id=firm.id,
        hierarchy_level_id=uuid4(),
        code="N-1",
        name="North, upper",
        path="/N-1",
    )
    formula = SalesTerritoryNode(
        firm_id=firm.id,
        hierarchy_level_id=uuid4(),
        code="N-2",
        name="=SUM(A1)",
        path="/N-2",
    )
    session.add_all([comma, formula])
    session.flush()
    customers_of = {comma.id: uuid4(), formula.id: uuid4()}
    users_of = {comma.id: uuid4(), formula.id: uuid4()}
    for node in (comma, formula):
        session.add_all(
            [
                TerritoryCustomerAssignment(
                    territory_id=node.id,
                    customer_id=customers_of[node.id],
                    visit_sequence=2,
                ),
                TerritorySalesmanAssignment(
                    territory_id=node.id,
                    salesman_id=users_of[node.id],
                    is_primary=True,
                ),
            ]
        )
    session.commit()
    service = SalesTerritoryService(session)

    customers = _records(service.export_customer_assignments_csv(firm_scope=firm.id))
    salesmen = _records(service.export_salesman_assignments_csv(firm_scope=firm.id))

    assert customers == [
        ["N-1", "North, upper", str(customers_of[comma.id]), "2", "false"],
        ["N-2", "'=SUM(A1)", str(customers_of[formula.id]), "2", "false"],
    ]
    assert salesmen == [
        ["N-1", "North, upper", str(users_of[comma.id]), "false", "true"],
        ["N-2", "'=SUM(A1)", str(users_of[formula.id]), "false", "true"],
    ]


def test_the_goods_receipt_export_quotes_and_guards() -> None:
    """A supplier's order number with a comma, and a receipt number that runs."""
    session, firm = _session()
    for number, order_number in (("GRN-1", "PO, 7"), ("=GRN-2", "PO-8")):
        session.add(
            GoodsReceipt(
                firm_id=firm.id,
                purchase_order_id=uuid4(),
                purchase_order_number=order_number,
                vendor_id=uuid4(),
                branch_id=uuid4(),
                warehouse_id=uuid4(),
                grn_number=number,
                receipt_date=date(2026, 9, 1),
                status="DRAFT",
                subtotal=Decimal("100.00"),
                tax_total=Decimal("18.00"),
                grand_total=Decimal("118.00"),
            )
        )
    session.commit()

    text = GoodsReceiptService(session).export_receipts_csv(
        firm_scope=firm.id, search=None
    )

    rows = {row[2]: row for row in _records(text)}
    assert set(rows) == {"PO, 7", "PO-8"}
    assert rows["PO, 7"][0] == "GRN-1"
    assert rows["PO-8"][0] == "'=GRN-2"
    for row in rows.values():
        assert len(row) == 10
        assert row[6] == "DRAFT"
        assert [Decimal(cell) for cell in row[7:]] == [
            Decimal("100"),
            Decimal("18"),
            Decimal("118"),
        ]


def _joins_by_hand(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Say whether ``function`` builds something with ``",".join``."""
    for node in ast.walk(function):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "join"
            and isinstance(node.func.value, ast.Constant)
            and node.func.value.value == ","
        ):
            return True
    return False


#: Functions named like an export that join with a comma for another reason:
#: ``path::function`` and why.
_DELIBERATE: dict[str, str] = {
    "sales/services/territory_service.py::_export_rows": (
        "joins a territory's shop codes inside ONE cell, which csv.writer "
        "then quotes; the importer splits that cell back on the comma"
    ),
}


def test_no_export_joins_its_cells_by_hand() -> None:
    """``csv_line`` builds the record; ``",".join`` quotes and guards nothing."""
    found: list[str] = []
    for path in sorted(_APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            name = node.name.lower()
            if "csv" not in name and "export" not in name:
                continue
            if name == "csv_line":
                continue
            if _joins_by_hand(node):
                found.append(f"{path.relative_to(_APP).as_posix()}::{node.name}")

    assert sorted(found) == sorted(_DELIBERATE), (
        "These exports join their cells with a bare comma, which neither "
        "quotes a comma inside a value nor guards a leading '='. Build the "
        "record with csv_line (app/core/utils/csv_text.py): "
        f"{sorted(set(found) - set(_DELIBERATE))}"
    )

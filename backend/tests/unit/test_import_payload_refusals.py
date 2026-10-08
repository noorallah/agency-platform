"""D-PRC-76: an import its schema refuses answers 422 by name, never 500.

Eight of the nine JSON import routes validated their form field by hand with
``model_validate_json``; pydantic's own error is not FastAPI's request
validation error, so it reached the unhandled-exception handler and the
person importing was told "An unexpected error occurred." for two lines
numbered 1. Every handler now reads such text through `parse_payload`.
"""

import ast
import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.core.error_codes import ErrorCode
from app.core.exceptions import ValidationError
from app.core.validation.payloads import parse_payload, stage_records
from app.sales_order.api.router import import_sales_orders
from app.sales_order.schemas import SalesOrderImportRequest

_APP = Path(__file__).resolve().parents[2] / "app"
#: A request model, by the way this codebase names them.
_REQUEST_SUFFIXES = ("Request", "Create", "Update", "Write", "Payload")


def _order(*line_numbers: int) -> dict[str, object]:
    """Return one order record whose lines carry these numbers."""
    return {
        "customer_id": str(uuid4()),
        "branch_id": str(uuid4()),
        "warehouse_id": str(uuid4()),
        "order_date": "2026-10-06",
        "lines": [
            {
                "line_number": number,
                "product_id": str(uuid4()),
                "quantity": "2",
            }
            for number in line_numbers
        ],
    }


def _refusal(payload: str) -> ValidationError:
    """Return what reading the payload as an order import raises."""
    with pytest.raises(ValidationError) as refusal:
        parse_payload(SalesOrderImportRequest, payload)
    return refusal.value


def test_a_good_payload_is_read() -> None:
    """The control: one sound record comes back as the model."""
    read = parse_payload(
        SalesOrderImportRequest, json.dumps({"records": [_order(1, 2)]})
    )
    assert len(read.records) == 1
    assert len(read.records[0].lines) == 2


def test_two_lines_numbered_alike_are_refused_naming_the_record() -> None:
    """The second record of two repeats line 1: 422, in the single save's words."""
    refusal = _refusal(json.dumps({"records": [_order(1), _order(1, 1)]}))

    assert refusal.status_code == 422
    assert refusal.code == ErrorCode.VALIDATION_ERROR
    assert refusal.message == (
        "Record 2 of 2: Lines 1 and 2 of the request are both numbered 1. "
        "Number each line once."
    )
    assert refusal.details == [
        {
            "field": "records.1.lines",
            "message": refusal.message,
            "code": "value_error",
        }
    ]


def test_a_missing_field_names_the_record_and_the_field() -> None:
    """Pydantic's own message is given its field; the rest go in the details."""
    record = _order(1)
    del record["customer_id"]
    lines = record["lines"]
    assert isinstance(lines, list)
    lines[0]["quantity"] = "many"
    refusal = _refusal(json.dumps({"records": [record]}))

    assert refusal.message.startswith("Record 1 of 1: customer_id: Field required")
    assert refusal.message.endswith("(1 more problem in the details.)")
    assert isinstance(refusal.details, list)
    assert [detail["field"] for detail in refusal.details] == [
        "records.0.customer_id",
        "records.0.lines.0.quantity",
    ]
    assert refusal.details[1]["message"].startswith(
        "Record 1 of 1: lines[1].quantity: "
    )


@pytest.mark.parametrize(
    "payload", ['{"records": []}', '{"records": [{"surprise": 1}]}', "{}"]
)
def test_other_refusals_are_422_too(payload: str) -> None:
    """No records, an unknown field, nothing at all: each a validation error."""
    assert _refusal(payload).status_code == 422


def test_text_that_is_not_json_says_so() -> None:
    """Not JSON: said plainly, with the parser's complaint in the details."""
    refusal = _refusal("customer,product\nC01,P01")

    assert refusal.message.startswith("The import is not valid JSON")
    assert isinstance(refusal.details, list)
    assert refusal.details[0]["code"] == "json_invalid"


def test_the_import_route_refuses_before_anything_is_touched() -> None:
    """The handler itself raises the 422, and never reaches its session."""
    session = MagicMock()
    with pytest.raises(ValidationError, match="Record 1 of 1: Lines 1 and 2"):
        asyncio.run(
            import_sales_orders(
                scope=MagicMock(),
                db=session,
                format="json",
                payload=json.dumps({"records": [_order(1, 1)]}),
                file=None,
            )
        )
    session.commit.assert_not_called()
    session.add.assert_not_called()


def _hand_validations(source: str) -> list[tuple[int, str]]:
    """Return the request models a module validates without `parse_payload`."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        method = node.func.attr
        owner = node.func.value
        name = owner.id if isinstance(owner, ast.Name) else ""
        if method == "model_validate_json" or (
            method == "model_validate" and name.endswith(_REQUEST_SUFFIXES)
        ):
            found.append((node.lineno, f"{name}.{method}"))
    return found


def test_no_router_validates_a_request_by_hand() -> None:
    """A handler that validates text itself turns a refusal into a 500.

    FastAPI answers 422 only for what it validated. Anything a handler reads
    out of a form field or an uploaded file goes through `parse_payload`.
    """
    offenders = [
        f"{path.relative_to(_APP.parent).as_posix()}:{line} {call}"
        for path in sorted(_APP.glob("*/api/router.py"))
        for line, call in _hand_validations(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        "These handlers validate a request model by hand, so a payload the "
        "schema refuses answers 500. Use parse_payload from "
        "app/core/validation/payloads.py:\n  " + "\n  ".join(offenders)
    )


def test_the_guard_sees_a_hand_validation() -> None:
    """The guard is not vacuous: it finds both spellings and passes a response."""
    source = (
        "a = OrderImportRequest.model_validate_json(payload)\n"
        "b = OrderCreate.model_validate(values)\n"
        "c = OrderResponse.model_validate(row)\n"
    )
    assert _hand_validations(source) == [
        (1, "OrderImportRequest.model_validate_json"),
        (2, "OrderCreate.model_validate"),
    ]


# ---- D-PRC-85: a record the *service* refuses is named too ------------------

#: The selling imports, by service file and method.
_SELLING_IMPORTS = {
    "sales_order/services/sales_order_service.py": "import_orders",
    "quotation/services/quotation_service.py": "import_quotations",
    "delivery_note/services/delivery_note_service.py": "import_notes",
    "sales_invoice/services/sales_invoice_service.py": "import_invoices",
    "sales_return/services/sales_return_service.py": "import_returns",
}

#: The buying imports that loop over records the same way (D-BUY-73).
_BUYING_IMPORTS = {
    "purchase/services/purchase_service.py": "import_orders",
    "goods_receipt/services/goods_receipt_service.py": "import_receipts",
    "purchase_invoice/services/purchase_invoice_service.py": "import_invoices",
}


def test_a_record_the_service_refuses_is_named_and_everything_is_undone() -> None:
    """The second of three is refused: named, rolled back, the third not tried."""
    undone: list[str] = []
    tried: list[int] = []

    def stage(record: int) -> int:
        """Refuse the second record as a single save would."""
        tried.append(record)
        if record == 2:
            raise ValidationError("Line 1: no stock.", details={"field": "lines"})
        return record * 10

    with pytest.raises(ValidationError) as refused:
        stage_records([1, 2, 3], stage, rollback=lambda: undone.append("rollback"))

    assert refused.value.message == (
        "Record 2 of 3: Line 1: no stock. Nothing was imported."
    )
    assert str(refused.value) == refused.value.message
    assert refused.value.details == {"field": "lines"}
    assert (tried, undone) == ([1, 2], ["rollback"])
    assert stage_records([1, 3], stage, rollback=lambda: None) == [10, 30]


def test_a_failure_that_is_no_refusal_is_undone_and_left_as_it_is() -> None:
    """A fault is rolled back and raised unchanged: it is nobody's record."""
    undone: list[str] = []

    def stage(record: int) -> int:
        """Fail as a fault would."""
        raise RuntimeError("the database went away")

    with pytest.raises(RuntimeError, match="the database went away"):
        stage_records([1], stage, rollback=lambda: undone.append("rollback"))

    assert undone == ["rollback"]


@pytest.mark.parametrize(
    ("path", "method"), sorted((_SELLING_IMPORTS | _BUYING_IMPORTS).items())
)
def test_every_document_import_names_the_record_it_refuses(
    path: str, method: str
) -> None:
    """Each stages its records through `stage_records`, never a bare loop."""
    tree = ast.parse((_APP / path).read_text(encoding="utf-8"))
    (found,) = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == method
    ]
    calls = {
        node.func.id
        for node in ast.walk(found)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "stage_records" in calls, f"{path}::{method}"

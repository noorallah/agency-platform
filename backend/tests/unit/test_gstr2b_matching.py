"""Backlog 78 row 3 (§42.5): GSTR-2B against the purchase bills.

Credit is claimable only on what the supplier reported, and nothing compared
the bills with GSTR-2B. A month's 2B JSON is now imported and each supplier
invoice matched to the firm's bill by GSTIN and the supplier's number, read
loosely; the date and every head of tax must agree within the firm's tolerance.
A firm may have 3B claim only matched bills (A36; the default claims all and
lists what 2B lacks).
"""

import json
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.gst_returns.api.router import (
    gstr2b_reconciliation,
    import_gstr2b,
    match_gstr2b_document,
)
from app.gst_returns.schemas import Gstr2bImportCreate, Gstr2bMatchRequest
from app.gst_returns.services.gstr2b import normalise_number, parse_gstr2b
from app.tax.schemas.gst_compliance import GstComplianceSettingsWrite
from app.tax.services.gst_compliance import GstComplianceService
from tests.unit.test_input_credit_eligibility import _bill, _table4

GSTIN = "33AABCU9603R1ZM"


def _file(
    *invoices: dict[str, object], period: str = "082026", **sections: object
) -> str:
    """Return a 2B file holding these invoices from the one supplier."""
    return json.dumps(
        {
            "data": {
                "gstin": "33AAAAA0000A1Z5",
                "rtnprd": period,
                "docdata": {
                    "b2b": [
                        {"ctin": GSTIN, "trdnm": "Car Dealer", "inv": list(invoices)}
                    ],
                    **sections,
                },
            }
        }
    )


def _invoice(number: str = "car/1", **overrides: object) -> dict[str, object]:
    """Return the bill the fixture approved, as the supplier filed it."""
    return {
        "inum": number,
        "dt": "02-08-2026",
        "val": 472,
        "txval": 400,
        "igst": 0,
        "cgst": 36,
        "sgst": 36,
        "cess": 0,
        "itcavl": "Y",
        "rev": "N",
        **overrides,
    }


def _scope(firm_id: UUID) -> object:
    """Build the scope a request carries."""
    return SimpleNamespace(firm_id=firm_id, actor_id=uuid4())


def _import(session: Session, firm_id: UUID, content: str) -> dict[str, object]:
    """Import a file for August and return the month's reconciliation."""
    import_gstr2b(
        data=Gstr2bImportCreate(return_period="2026-08", content=content),
        scope=_scope(firm_id),  # type: ignore[arg-type]
        db=session,
    )
    found = gstr2b_reconciliation(
        scope=_scope(firm_id),  # type: ignore[arg-type]
        return_period="2026-08",
        db=session,
    ).data
    assert found is not None
    return found


def _statuses(found: dict[str, object]) -> list[tuple[object, object]]:
    """Return (number, status) for each 2B row."""
    rows = found["documents"]
    assert isinstance(rows, list)
    return [(row["document_number"], row["match_status"]) for row in rows]


def _bill_from_supplier() -> tuple[Session, UUID, UUID]:
    """Approve CAR-1 from a regular supplier: 400 + CGST 36 + SGST 36."""
    session, firm_id, bill_id, _, _ = _bill(
        supplier_type="REGULAR", supplier_gstin=GSTIN
    )
    return session, firm_id, bill_id


def test_numbers_are_read_loosely() -> None:
    """Case, punctuation and leading zeros do not make two numbers."""
    assert normalise_number("INV/0001") == normalise_number("inv-1") == "INV1"
    assert normalise_number("CAR-1") == normalise_number("car / 01")
    assert normalise_number("A10") != normalise_number("A1")


def test_a_filed_bill_matches_and_one_never_filed_is_listed() -> None:
    """The bill is matched; another 2B invoice is not in the books."""
    session, firm_id, _ = _bill_from_supplier()
    found = _import(session, firm_id, _file(_invoice(), _invoice("X-9")))
    assert _statuses(found) == [("car/1", "MATCHED"), ("X-9", "NOT_IN_BOOKS")]
    assert found["in_books_only"] == []
    assert found["counts"] == {"MATCHED": 1, "NOT_IN_BOOKS": 1, "IN_BOOKS_ONLY": 0}


def test_a_bill_the_supplier_did_not_file_is_in_books_only() -> None:
    """2B lacks the bill: the credit at risk is listed."""
    session, firm_id, bill_id = _bill_from_supplier()
    found = _import(session, firm_id, _file(_invoice("X-9")))
    missing = found["in_books_only"]
    assert isinstance(missing, list)
    assert [row["purchase_invoice_id"] for row in missing] == [str(bill_id)]


def test_a_difference_beyond_the_tolerance_is_named() -> None:
    """CGST 40 against 36 is DIFFERENT; 36.50 is within the rupee."""
    session, firm_id, _ = _bill_from_supplier()
    found = _import(session, firm_id, _file(_invoice(cgst=40)))
    rows = found["documents"]
    assert isinstance(rows, list)
    assert rows[0]["match_status"] == "DIFFERENT"
    assert "CGST 40.00 in 2B, 36.00 in the books" in str(rows[0]["match_note"])

    found = _import(session, firm_id, _file(_invoice(cgst=36.5)))
    assert _statuses(found) == [("car/1", "MATCHED")]


def test_a_reimport_replaces_the_month_and_says_what_it_skipped() -> None:
    """One statement per month; unread sections are named, never hidden."""
    session, firm_id, _ = _bill_from_supplier()
    _import(session, firm_id, _file(_invoice("X-9")))
    found = _import(session, firm_id, _file(_invoice(), impg=[{"refdt": "01-08-2026"}]))
    assert _statuses(found) == [("car/1", "MATCHED")]
    assert found["skipped_sections"] == "impg"


def test_a_wrong_file_is_refused_by_name() -> None:
    """Not JSON, not a 2B, or another month."""
    with pytest.raises(ValidationError, match="not JSON"):
        parse_gstr2b("not json")
    with pytest.raises(ValidationError, match="not a GSTR-2B"):
        parse_gstr2b('{"data": {}}')
    session, firm_id, _ = _bill_from_supplier()
    with pytest.raises(ValidationError, match="for 2026-07, not 2026-08"):
        _import(session, firm_id, _file(_invoice(), period="072026"))


def test_a_row_can_be_matched_by_hand_and_undone() -> None:
    """A number typed beyond recognition is matched by a person."""
    session, firm_id, bill_id = _bill_from_supplier()
    found = _import(session, firm_id, _file(_invoice("DEALER-INV-7781")))
    rows = found["documents"]
    assert isinstance(rows, list)
    row_id = UUID(str(rows[0]["id"]))
    assert rows[0]["match_status"] == "NOT_IN_BOOKS"

    result = match_gstr2b_document(
        document_id=row_id,
        data=Gstr2bMatchRequest(purchase_invoice_id=bill_id),
        scope=_scope(firm_id),  # type: ignore[arg-type]
        db=session,
    ).data
    assert result is not None and result["match_status"] == "MANUAL"

    result = match_gstr2b_document(
        document_id=row_id,
        data=Gstr2bMatchRequest(purchase_invoice_id=None),
        scope=_scope(firm_id),  # type: ignore[arg-type]
        db=session,
    ).data
    assert result is not None and result["match_status"] == "NOT_IN_BOOKS"


def test_a_firm_that_claims_only_matched_credit_waits_for_2b() -> None:
    """MATCHED_ONLY holds the bill's credit back until 2B shows it."""
    session, firm_id, _ = _bill_from_supplier()
    GstComplianceService(session).update_settings(
        GstComplianceSettingsWrite(
            einvoice_applicable_from=None,
            thirty_day_rule_from=None,
            dispatch_without_invoice="WARN",
            route_sale_needs_invoice=False,
            itc_claim_basis="MATCHED_ONLY",
        ),
        firm_id=firm_id,
        actor_id=uuid4(),
    )
    assert _table4(session, firm_id)["4A5"] == 0.0
    _import(session, firm_id, _file(_invoice()))
    assert _table4(session, firm_id)["4A5"] == 36.0


def test_a_bill_in_another_currency_is_matched_in_rupees() -> None:
    """D-CMP-23: 400 USD + 72 USD of tax at 83 is what the supplier filed."""
    from tests.unit.test_rule37 import _in_usd

    session, firm_id, bill_id = _bill_from_supplier()
    _in_usd(session, bill_id)

    filed = _invoice(val=39176, txval=33200, cgst=2988, sgst=2988)
    found = _import(session, firm_id, _file(filed))

    assert _statuses(found) == [("car/1", "MATCHED")]

    # Left out of 2B, its credit at risk is listed in rupees too.
    found = _import(session, firm_id, _file(_invoice("X-9")))
    missing = found["in_books_only"]
    assert isinstance(missing, list)
    assert [row["tax_total"] for row in missing] == [5976.0]

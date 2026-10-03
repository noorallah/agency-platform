"""Branches with a GSTIN of their own (STK-2, decision A127).

The firm is registered in Karnataka; its Pune branch holds a Maharashtra
GSTIN. Each GSTIN files its own return off its own branches' bills, a
Pune bill prints and supplies under the Pune number, and goods cannot move
between the two on a transfer -- that is a sale.
"""

# ruff: noqa: D103

from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError as SchemaError

from app.branches.models import Branch, Warehouse
from app.branches.schemas import BranchCreate, BranchUpdate
from app.branches.services.branch_warehouse_service import BranchWarehouseService
from app.branches.services.registration import BranchRegistration
from app.core.exceptions import ValidationError
from app.core.validation.common import gstin_check_character
from app.document_framework.services.print_support import firm_party, seller_party
from app.inventory.services.stock_transfers import (
    StockTransferService,
    StockTransferWrite,
)
from app.sales.models.territory import GeoCountry, GeoState
from app.tax.services.place_of_supply import SupplyPlaceResolver
from tests.unit.test_gst_returns import (
    APRIL,
    SELLER,
    GstReturnService,
    _Books,
    _session_factory,
)


def _gstin(body: str) -> str:
    """Complete a 14-character GSTIN body with its check character."""
    return body + gstin_check_character(body + "0")


PUNE = _gstin("27AABCU9603R1Z")


def _with_pune(books: _Books) -> Branch:
    pune = Branch(
        firm_id=books.firm.id,
        code="BR-PUNE",
        name="Pune",
        display_name="Pune",
        currency_code="INR",
        working_hours={},
        status="ACTIVE",
        gstin=PUNE,
        gst_registration=True,
        address_line1="12 FC Road, Pune",
    )
    books.session.add(pune)
    books.session.commit()
    return pune


def _billed_at(books: _Books, branch: Branch, number: str) -> None:
    invoice = books.invoice(number)
    invoice.branch_id = branch.id
    books.session.commit()


def test_each_gstin_files_only_its_own_branches_bills() -> None:
    books = _Books(_session_factory()())
    pune = _with_pune(books)
    books.invoice("KA-1")
    _billed_at(books, pune, "MH-1")

    service = GstReturnService(books.session)
    home = service.gstr1(firm_scope=books.firm.id, from_date=APRIL[0], to_date=APRIL[1])
    away = service.gstr1(
        firm_scope=books.firm.id, from_date=APRIL[0], to_date=APRIL[1], gstin=PUNE
    )

    def numbers(data: dict[str, object]) -> list[str]:
        return [
            invoice["invoice_number"]
            for party in data["b2b"]  # type: ignore[attr-defined]
            for invoice in party["invoices"]
        ]

    assert (home["gstin"], numbers(home)) == (SELLER, ["KA-1"])
    assert (away["gstin"], numbers(away)) == (PUNE, ["MH-1"])
    summary = service.gstr3b(
        firm_scope=books.firm.id, from_date=APRIL[0], to_date=APRIL[1], gstin=PUNE
    )
    assert summary["gstin"] == PUNE


def test_a_firm_with_one_gstin_reads_every_bill() -> None:
    books = _Books(_session_factory()())
    books.invoice("KA-1")
    scope = BranchRegistration(books.session).scope(books.firm.id, None)
    assert scope.branch_ids is None


def test_the_registrations_list_the_firm_first_and_refuse_a_stranger() -> None:
    books = _Books(_session_factory()())
    _with_pune(books)
    registration = BranchRegistration(books.session)
    rows = registration.registrations(books.firm.id)
    assert [(row.gstin, row.is_firm) for row in rows] == [
        (SELLER, True),
        (PUNE, False),
    ]
    assert rows[1].branch_names == ("Pune",)
    with pytest.raises(ValidationError, match="not one of this firm's"):
        registration.scope(books.firm.id, _gstin("07AABCU9603R1Z"))


def test_a_branch_bill_supplies_and_prints_under_the_branch_gstin() -> None:
    books = _Books(_session_factory()())
    pune = _with_pune(books)
    registration = BranchRegistration(books.session)
    assert registration.gstin_for(books.firm.id, pune.id) == PUNE
    assert registration.gstin_for(books.firm.id, books.branch.id) == SELLER
    resolver = SupplyPlaceResolver(books.session)
    assert resolver.supplier_state(firm_id=books.firm.id, branch_id=pune.id) == "27"

    printed = seller_party(books.session, books.firm.id, pune.id)
    assert printed.gstin == PUNE
    assert printed.address_lines == ["12 FC Road, Pune"]
    assert seller_party(books.session, books.firm.id, books.branch.id) == firm_party(
        books.firm.id
    )


def test_goods_cannot_move_between_two_gstins_on_a_transfer() -> None:
    books = _Books(_session_factory()())
    pune = _with_pune(books)
    home = Warehouse(
        firm_id=books.firm.id,
        branch_id=books.branch.id,
        code="WH-BLR",
        name="Bengaluru",
        display_name="Bengaluru",
        status="ACTIVE",
        is_default=True,
    )
    away = Warehouse(
        firm_id=books.firm.id,
        branch_id=pune.id,
        code="WH-PUNE",
        name="Pune",
        display_name="Pune",
        status="ACTIVE",
        is_default=True,
    )
    books.session.add_all([home, away])
    books.session.commit()
    with pytest.raises(ValidationError, match="raise a sales invoice"):
        StockTransferService(books.session).create(
            StockTransferWrite(
                transfer_date=date(2026, 4, 10),
                from_warehouse_id=home.id,
                to_warehouse_id=away.id,
                lines=[{"product_id": books.product.id, "quantity": "1"}],  # type: ignore[list-item]
            ),
            firm_id=books.firm.id,
            actor_id=uuid4(),
        )


def test_a_branch_gstin_must_be_valid_and_in_the_branch_s_state() -> None:
    with pytest.raises(SchemaError, match="check character"):
        BranchCreate(code="BR-X", name="X", gstin="27AABCU9603R1ZZ")

    books = _Books(_session_factory()())
    india = GeoCountry(code="IND", name="India", iso2="IN")
    books.session.add(india)
    books.session.flush()
    karnataka = GeoState(country_id=india.id, code="KA", name="Karnataka")
    books.session.add(karnataka)
    books.session.commit()
    service = BranchWarehouseService(books.session)
    with pytest.raises(ValidationError, match="registered in state 27"):
        service.create_branch(
            BranchCreate(
                code="BR-MIS",
                name="Mismatch",
                country_id=india.id,
                state_id=karnataka.id,
                gstin=PUNE,
            ),
            firm_id=books.firm.id,
            actor_id=uuid4(),
        )
    books.session.rollback()
    created = service.create_branch(
        BranchCreate(code="BR-OK", name="Pune", gstin=PUNE),
        firm_id=books.firm.id,
        actor_id=uuid4(),
    )
    assert (created.gstin, created.gst_registration) == (PUNE, True)
    with pytest.raises(ValidationError, match="registered in state 27"):
        service.update_branch(
            created.id,
            BranchUpdate(
                code="BR-OK",
                name="Pune",
                country_id=india.id,
                state_id=karnataka.id,
            ),
            firm_scope=books.firm.id,
            actor_id=uuid4(),
        )

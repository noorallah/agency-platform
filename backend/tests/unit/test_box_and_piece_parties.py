"""The two switches and the party's mark for boxes and pieces (L5, step 9).

Each side of the firm has one switch, off until the firm turns it on, and an
edit of the settings that never showed it leaves it alone. A customer is
marked *Bills in boxes and pieces* and a supplier *Buys in boxes and pieces*;
the mark is written on the form and through the import, an edit that does not
name it keeps it, and the lists can be filtered by it
(``docs/design/BOX_AND_PIECE_LINE_DESIGN.md``, section 4).
"""

from uuid import uuid4

from sqlalchemy import select

from app.customers.models import Customer
from app.customers.schemas import CustomerCreate, CustomerUpdate
from app.customers.schemas.customer import CustomerListFilters
from app.customers.services import CustomerService
from app.purchase.schemas import PurchaseWorkflowSettingsWrite
from app.purchase.services.workflow_settings_service import PurchaseWorkflowService
from app.sales_order.schemas import SalesWorkflowSettingsWrite
from app.sales_order.services.workflow_settings_service import SalesWorkflowService
from app.vendors.models import Vendor
from app.vendors.schemas import VendorCreate, VendorListFilters, VendorUpdate
from app.vendors.services import VendorService
from tests.unit import test_customer_import_file as customer_files
from tests.unit import test_vendor_import_file as vendor_files

STAGES = {
    "quotation_stage": True,
    "sales_order_stage": True,
    "delivery_note_stage": True,
}


def _customer(code: str, **fields: object) -> CustomerCreate:
    """Describe a business customer with only what the test names."""
    return CustomerCreate.model_validate(
        {
            "code": code,
            "customer_type": "BUSINESS",
            "name": f"Customer {code}",
            "currency_code": "INR",
            **fields,
        }
    )


def test_the_selling_switch_is_off_until_turned_on_and_an_omission_keeps_it() -> None:
    """No row reads off; a write that does not name the switch leaves it."""
    factory = customer_files._factory()
    with factory() as session:
        firm = customer_files._firm(session, books=False)
        service = SalesWorkflowService(session)
        assert service.settings_response(firm.id).box_and_piece_entry is False

        first = service.update_settings(
            SalesWorkflowSettingsWrite(**STAGES),
            firm_id=firm.id,
            actor_id=uuid4(),
        )
        assert first.box_and_piece_entry is False

        on = service.update_settings(
            SalesWorkflowSettingsWrite(**STAGES, box_and_piece_entry=True),
            firm_id=firm.id,
            actor_id=uuid4(),
        )
        assert on.box_and_piece_entry is True

        kept = service.update_settings(
            SalesWorkflowSettingsWrite(**STAGES),
            firm_id=firm.id,
            actor_id=uuid4(),
        )
        assert kept.box_and_piece_entry is True
        assert service.settings_response(firm.id).box_and_piece_entry is True


def test_the_buying_switch_is_off_until_turned_on_and_an_omission_keeps_it() -> None:
    """The purchase settings carry their own switch, read the same way."""
    factory = vendor_files._factory()
    with factory() as session:
        firm = vendor_files._firm(session)
        service = PurchaseWorkflowService(session)
        stages = {"purchase_order_stage": True, "goods_receipt_stage": True}
        assert service.settings_response(firm.id).box_and_piece_entry is False

        first = service.update_settings(
            PurchaseWorkflowSettingsWrite(**stages),
            firm_id=firm.id,
            actor_id=uuid4(),
        )
        assert first.box_and_piece_entry is False

        on = service.update_settings(
            PurchaseWorkflowSettingsWrite(**stages, box_and_piece_entry=True),
            firm_id=firm.id,
            actor_id=uuid4(),
        )
        assert on.box_and_piece_entry is True

        kept = service.update_settings(
            PurchaseWorkflowSettingsWrite(**stages),
            firm_id=firm.id,
            actor_id=uuid4(),
        )
        assert kept.box_and_piece_entry is True


def test_a_customer_keeps_the_mark_through_an_edit_that_does_not_name_it() -> None:
    """Create writes it, an edit without it keeps it, the list filters by it."""
    factory = customer_files._factory()
    with factory() as session:
        firm = customer_files._firm(session, books=False)
        service = CustomerService(session)
        actor = uuid4()
        boxed = service.create(
            _customer("BOXED", box_and_piece_entry=True),
            firm_id=firm.id,
            actor_id=actor,
        )
        plain = service.create(_customer("PLAIN"), firm_id=firm.id, actor_id=actor)
        assert boxed.box_and_piece_entry is True
        assert plain.box_and_piece_entry is False

        service.update(
            boxed.id,
            CustomerUpdate.model_validate(
                {
                    "code": "BOXED",
                    "customer_type": "BUSINESS",
                    "name": "Renamed",
                    "currency_code": "INR",
                }
            ),
            firm_scope=firm.id,
            actor_id=actor,
        )
        session.refresh(boxed)
        assert (boxed.name, boxed.box_and_piece_entry) == ("Renamed", True)

        for wanted, codes in ((True, ["BOXED"]), (False, ["PLAIN"])):
            rows, total = service.list_customers(
                firm_scope=firm.id,
                filters=CustomerListFilters(box_and_piece_entry=wanted),
                page=1,
                page_size=20,
                search=None,
                sort_by="code",
                descending=False,
            )
            assert [row.code for row in rows] == codes
            assert total == 1


def test_the_customer_import_reads_the_mark_and_a_blank_cell_keeps_it() -> None:
    """Yes marks a new customer; a blank cell on an update leaves the mark."""
    factory = customer_files._factory()
    session = factory()
    firm = customer_files._firm(session)

    report = customer_files._run(
        session,
        firm.id,
        customer_files._csv(
            "Code,Name,BoxesAndPieces", "BOXED,Boxed,Yes", "PLAIN,Plain,"
        ),
        apply=True,
    )
    assert report.imported, [issue.describe() for issue in report.issues]

    again = customer_files._run(
        session,
        firm.id,
        customer_files._csv("Code,Name,BoxesAndPieces", "BOXED,Boxed Again,"),
        apply=True,
        existing="update",
    )
    assert again.imported, [issue.describe() for issue in again.issues]
    with factory() as fresh:
        marks = dict(
            fresh.execute(select(Customer.code, Customer.box_and_piece_entry)).all()
        )
    assert marks == {"BOXED": True, "PLAIN": False}


def test_the_customer_import_refuses_a_mark_that_is_not_yes_or_no() -> None:
    """A cell that is neither Yes nor No is named by row and column."""
    factory = customer_files._factory()
    session = factory()
    firm = customer_files._firm(session)

    report = customer_files._run(
        session,
        firm.id,
        customer_files._csv("Code,Name,BoxesAndPieces", "BOXED,Boxed,Maybe"),
        apply=False,
    )

    assert not report.imported
    assert any("BoxesAndPieces" in issue.describe() for issue in report.issues)


def test_a_supplier_keeps_the_mark_and_the_list_filters_by_it() -> None:
    """Create writes it, an edit without it keeps it, the list filters by it."""
    factory = vendor_files._factory()
    with factory() as session:
        firm = vendor_files._firm(session)
        service = VendorService(session)
        actor = uuid4()
        boxed = service.create(
            VendorCreate.model_validate(
                {"code": "BOXED", "name": "Boxed", "box_and_piece_entry": True}
            ),
            firm_id=firm.id,
            actor_id=actor,
        )
        service.create(
            VendorCreate.model_validate({"code": "PLAIN", "name": "Plain"}),
            firm_id=firm.id,
            actor_id=actor,
        )

        service.update(
            boxed.id,
            VendorUpdate.model_validate({"code": "BOXED", "name": "Renamed"}),
            firm_scope=firm.id,
            actor_id=actor,
        )
        stored = session.scalars(select(Vendor).where(Vendor.code == "BOXED")).one()
        assert (stored.name, stored.box_and_piece_entry) == ("Renamed", True)

        rows, total = service.list_vendors(
            firm_scope=firm.id,
            filters=VendorListFilters(box_and_piece_entry=True),
            page=1,
            page_size=20,
            search=None,
            sort_by="code",
            descending=False,
        )
        assert [row.code for row in rows] == ["BOXED"]
        assert total == 1


def test_the_supplier_import_reads_the_mark() -> None:
    """Yes marks a new supplier; a blank cell is no mark."""
    factory = vendor_files._factory()
    session = factory()
    firm = vendor_files._firm(session)

    report = vendor_files._run(
        session,
        firm.id,
        vendor_files._csv(
            "Code,Name,BoxesAndPieces", "BOXED,Boxed,Yes", "PLAIN,Plain,"
        ),
        apply=True,
    )

    assert report.imported, [issue.describe() for issue in report.issues]
    with factory() as fresh:
        marks = dict(
            fresh.execute(select(Vendor.code, Vendor.box_and_piece_entry)).all()
        )
    assert marks == {"BOXED": True, "PLAIN": False}

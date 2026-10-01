"""A customer's GST registration type and what it changes (backlog 75 row 2).

The return and the e-invoice sides are in ``test_gst_returns.py``; this pins
the rules on the customer itself, the interstate decision and the e-invoice
supply type.
"""

from decimal import Decimal

import pytest

from app.core.exceptions import ValidationError
from app.customers.gst_registration import assert_consistent, effective_type
from app.einvoice.services.payload import _supply_type
from app.tax.services.place_of_supply import SupplyPlaceResolver
from tests.unit.test_gst_returns import _Books, _session_factory


def test_blank_is_read_off_the_gstin() -> None:
    """Every customer saved before the field keeps behaving as it did."""
    assert effective_type(None, "33AAAPL1234C1Z5") == "REGULAR"
    assert effective_type(None, None) == "UNREGISTERED"
    assert effective_type("SEZ_WITH_PAYMENT", "33AAAPL1234C1Z5") == "SEZ_WITH_PAYMENT"


@pytest.mark.parametrize(
    ("kind", "gstin", "refused"),
    [
        ("SEZ_WITH_PAYMENT", None, "must have a GST number"),
        ("DEEMED_EXPORT", "", "must have a GST number"),
        ("COMPOSITION", None, "must have a GST number"),
        ("OVERSEAS", "33AAAPL1234C1Z5", "cannot have a GST number"),
        ("UNREGISTERED", "33AAAPL1234C1Z5", "cannot have a GST number"),
    ],
)
def test_a_type_the_gstin_contradicts_is_refused(
    kind: str, gstin: str | None, refused: str
) -> None:
    """A registered type needs a GSTIN; an unregistered one cannot carry one."""
    with pytest.raises(ValidationError, match=refused):
        assert_consistent(kind, gstin)


def test_a_consistent_type_passes() -> None:
    """Nothing to refuse."""
    assert_consistent("SEZ_WITHOUT_PAYMENT", "33AAAPL1234C1Z5")
    assert_consistent("OVERSEAS", None)
    assert_consistent(None, None)


def test_an_sez_buyer_in_the_firm_s_own_state_is_interstate() -> None:
    """IGST Act section 7(5)(b): IGST wherever the SEZ unit is."""
    books = _Books(_session_factory()())
    resolver = SupplyPlaceResolver(books.session)
    same_state = dict(
        firm_id=books.firm.id, branch_id=None, customer_id=books.registered.id
    )
    before = resolver.is_interstate(**same_state)  # type: ignore[arg-type]
    books.registered.gst_registration_type = "SEZ_WITHOUT_PAYMENT"
    books.session.commit()

    assert before is False
    assert resolver.is_interstate(**same_state) is True  # type: ignore[arg-type]


def test_an_overseas_buyer_is_place_96_without_a_foreign_address() -> None:
    """Declared abroad is enough; no address has to say so."""
    books = _Books(_session_factory()())
    books.walk_in.gst_registration_type = "OVERSEAS"
    books.session.commit()

    assert SupplyPlaceResolver(books.session).buyer_state(books.walk_in.id) == "96"


@pytest.mark.parametrize(
    ("kind", "igst", "expected"),
    [
        ("REGULAR", "18", "B2B"),
        ("COMPOSITION", "18", "B2B"),
        ("SEZ_WITH_PAYMENT", "18", "SEZWP"),
        ("SEZ_WITHOUT_PAYMENT", "0", "SEZWOP"),
        ("DEEMED_EXPORT", "18", "DEXP"),
        ("OVERSEAS", "18", "EXPWP"),
        ("OVERSEAS", "0", "EXPWOP"),
    ],
)
def test_the_e_invoice_supply_type_follows_the_buyer(
    kind: str, igst: str, expected: str
) -> None:
    """The marker the e-invoice builder said no customer carried."""
    assert _supply_type(export=False, igst=Decimal(igst), gst_type=kind) == expected


def test_a_bill_stamps_the_buyer_s_type_and_warns_on_tax_under_an_lut() -> None:
    """Stamped when raised; an SEZ-under-LUT bill that charges tax is warned."""
    from app.sales_invoice.services import SalesInvoiceService
    from tests.unit.test_price_floor import _Shop

    shop = _Shop()
    shop.stages(quotation=False, sales_order=False, delivery_note=False)
    shop.customer.gst_number = "33AAAPL1234C1Z5"
    shop.customer.gst_registration_type = "SEZ_WITHOUT_PAYMENT"
    shop.session.commit()
    bills = SalesInvoiceService(shop.session)
    draft = bills.create_invoice(
        shop.bare_bill(), firm_id=shop.firm.id, actor_id=shop.actor_id
    )
    assert draft.buyer_gst_registration_type == "SEZ_WITHOUT_PAYMENT"

    approved = bills.approve_invoice(
        draft.id, firm_scope=shop.firm.id, actor_id=shop.actor_id
    )
    event = shop.event(approved.id)
    # This firm's rules charge nothing, so there is nothing to warn about.
    assert Decimal(str(approved.tax_total)) == 0
    assert "sez_tax_warning" not in (event.details_json or {})


def test_tax_on_an_sez_bill_under_an_lut_is_warned_not_refused() -> None:
    """The warning names the buyer and the tax; other buyers get none."""
    from types import SimpleNamespace

    from app.customers.gst_registration import sez_tax_warning

    sez = SimpleNamespace(
        gst_registration_type="SEZ_WITHOUT_PAYMENT", display_name="Zone Unit"
    )
    remark, details = sez_tax_warning(sez, Decimal("18.00"))
    assert remark is not None and "Zone Unit" in remark and "18.00" in remark
    assert details == {"sez_tax_warning": {"tax_total": "18.00"}}
    assert sez_tax_warning(sez, Decimal("0")) == (None, None)
    paid = SimpleNamespace(gst_registration_type="SEZ_WITH_PAYMENT")
    assert sez_tax_warning(paid, Decimal("18")) == (None, None)
    assert sez_tax_warning(None, Decimal("18")) == (None, None)

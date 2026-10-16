"""A bill series per company (backlog 157, PRT-7).

`docs/design/BILL_SERIES_BY_COMPANY_DESIGN.md` section 11 names the guards;
this file holds items 1, 3 to 10 -- 7 as the migration's backfill run on a
store as it looked before. Item 2, the race, needs a real lock and lives in
`tests/integration/test_bill_series_race.py`.

The sales bill's default layout is ``SI-26-27-000001``: a short year and six
digits. With it a company prefix of up to three characters fits the sixteen
CGST rule 46(b) allows, so the prefixes here are short.
"""

import importlib.util
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import delete, select, update

from app.core.exceptions import ValidationError
from app.credit_note.services.credit_note_service import CreditNoteService
from app.document_framework.models import (
    BillSeriesCounter,
    DocumentNumberingRule,
    DocumentNumberSequence,
)
from app.document_framework.schemas import DocumentNumberingRuleUpdate
from app.document_framework.services import DocumentFrameworkService, bill_series
from app.document_framework.services.bill_series import (
    BillSeriesService,
    BillSeriesSettingsWrite,
)
from app.inventory.schemas import InventoryAdjustmentCreate
from app.inventory.services import InventoryService
from app.products.models import Product
from app.products.models.brand import Brand, Principal
from app.products.services.brands import BrandService, PrincipalWrite
from app.proforma.services.proforma_service import ProformaService
from app.sales_invoice.models import SalesInvoice
from app.sales_invoice.schemas import SalesInvoiceCreate, SalesInvoiceLineWrite
from app.sales_invoice.services import SalesInvoiceService
from app.sales_return.services.sales_return_service import SalesReturnService
from tests.unit.test_sales_chain_synthesis import _Firm, _session_factory

ACTOR = uuid4()


class _Shop:
    """A counter firm selling the goods of a few companies."""

    def __init__(self) -> None:
        """Build the firm with every stage of the chain left to the services."""
        self.setup = _Firm(_session_factory()())
        self.setup.stages(quotation=False, sales_order=False, delivery_note=False)
        self.session = self.setup.session
        self.firm_id = self.setup.firm.id

    def company(self, code: str, prefix: str | None) -> Principal:
        """Add a company, with or without a bill series prefix."""
        row = Principal(
            firm_id=self.firm_id,
            code=code,
            name=f"{code} Ltd",
            bill_series_prefix=prefix,
        )
        self.session.add(row)
        self.session.commit()
        return row

    def product(
        self,
        code: str,
        company: Principal | None,
        *,
        product_type: str = "STOCK_ITEM",
    ) -> Product:
        """Add a product under a brand of ``company`` (none when it is None)."""
        brand_id: UUID | None = None
        if company is not None:
            brand = Brand(
                firm_id=self.firm_id, name=f"{code} brand", principal_id=company.id
            )
            self.session.add(brand)
            self.session.commit()
            brand_id = brand.id
        row = Product(
            firm_id=self.firm_id,
            code=code,
            name=f"Product {code}",
            product_type=product_type,
            status="ACTIVE",
            brand_id=brand_id,
        )
        self.session.add(row)
        self.session.commit()
        if product_type != "SERVICE":
            InventoryService(self.session).create_adjustment(
                InventoryAdjustmentCreate(
                    branch_id=self.setup.branch.id,
                    warehouse_id=self.setup.warehouse.id,
                    product_id=row.id,
                    quantity=Decimal("100"),
                    reference_number=f"ADJ-{code}",
                    reference_type="ADJUSTMENT",
                    transaction_date=date(2026, 8, 1),
                ),
                firm_scope=self.firm_id,
                actor_id=ACTOR,
            )
        return row

    def by_company(self, driver: str = "BY_COMPANY") -> None:
        """Switch the firm's bills to a series per company (or another level)."""
        BillSeriesService(self.session).save_settings(
            BillSeriesSettingsWrite(series_driver=driver),
            firm_id=self.firm_id,
            actor_id=ACTOR,
        )
        self.session.commit()

    def bill(self, *products: Product, on: date = date(2026, 8, 4)) -> SalesInvoice:
        """Raise a counter bill of one unit of each product."""
        return SalesInvoiceService(self.session).create_invoice(
            SalesInvoiceCreate(
                customer_id=self.setup.customer.id,
                invoice_date=on,
                lines=[
                    SalesInvoiceLineWrite(
                        product_id=product.id,
                        line_number=index,
                        current_invoice_quantity=Decimal("1"),
                        unit_price=Decimal("100"),
                        discount_percent=Decimal("0"),
                    )
                    for index, product in enumerate(products, start=1)
                ],
            ),
            firm_id=self.firm_id,
            actor_id=ACTOR,
        )

    def bill_rule(self) -> DocumentNumberingRule:
        """Return the firm's sales-bill series, made on first use."""
        _, rule = SalesInvoiceService(self.session)._ensure_document_setup(
            firm_id=self.firm_id, actor_id=ACTOR
        )
        self.session.commit()
        return rule


@pytest.fixture
def shop() -> Iterator[_Shop]:
    """Yield a fresh firm for one test."""
    built = _Shop()
    yield built
    built.session.close()


# -- 1. never twice -----------------------------------------------------------
def test_two_companies_sharing_a_prefix_share_one_running_number(shop: _Shop) -> None:
    """Bills of two companies under one prefix never repeat a number."""
    asian = shop.product("A1", shop.company("ASIAN", "AS"))
    other = shop.product("B1", shop.company("ASIANB", "AS"))
    shop.by_company()

    numbers = [
        shop.bill(asian).invoice_number,
        shop.bill(other).invoice_number,
        shop.bill(asian).invoice_number,
    ]

    assert numbers == ["AS-26-27-000001", "AS-26-27-000002", "AS-26-27-000003"]


def test_the_list_names_the_company_behind_each_series(shop: _Shop) -> None:
    """A list row says whose series numbered it; GENERAL names nobody."""
    asian = shop.product("A1", shop.company("ASIAN", "AS"))
    shop.company("ASIANB", "AS")
    pidi = shop.product("P1", shop.company("PIDI", "PD"))
    shop.by_company()
    bills = [shop.bill(asian), shop.bill(pidi), shop.bill(asian, pidi)]
    rows = [shop.session.get(SalesInvoice, bill.id) for bill in bills]

    answer = SalesInvoiceService(shop.session).invoice_responses(
        [row for row in rows if row is not None]
    )

    # Two companies share AS, so both are named.
    assert [item.series_company_name for item in answer] == [
        "ASIAN Ltd, ASIANB Ltd",
        "PIDI Ltd",
        None,
    ]


# -- 3. resolver --------------------------------------------------------------
def test_the_series_follows_the_goods_on_the_bill(shop: _Shop) -> None:
    """One company gives its prefix; anything else gives GENERAL."""
    asian = shop.product("A1", shop.company("ASIAN", "AS"))
    pidi = shop.product("P1", shop.company("PIDI", "PD"))
    nameless = shop.product("N1", shop.company("NOPREFIX", None))
    orphan = shop.product("O1", None)
    freight = shop.product("FRT", shop.company("CARRIER", "FR"), product_type="SERVICE")
    service = BillSeriesService(shop.session)

    # On one series the principals' prefixes do nothing.
    assert service.resolve(shop.firm_id, [asian.id]).prefix is None
    assert service.resolve(shop.firm_id, [asian.id]).reason == "ONE_SERIES"

    shop.by_company()
    one = service.resolve(shop.firm_id, [asian.id, asian.id])
    assert (one.prefix, one.reason) == ("AS", "ONE_COMPANY")
    mixed = service.resolve(shop.firm_id, [asian.id, pidi.id])
    assert (mixed.prefix, mixed.reason) == (None, "MIXED")
    # A goods line with no company, or a company with no prefix: GENERAL.
    assert service.resolve(shop.firm_id, [asian.id, orphan.id]).prefix is None
    assert service.resolve(shop.firm_id, [nameless.id]).prefix is None
    # A service line is not goods and is not counted.
    assert service.resolve(shop.firm_id, [asian.id, freight.id]).prefix == "AS"
    assert service.resolve(shop.firm_id, [freight.id]).reason == "NO_GOODS"


def test_a_mixed_bill_is_numbered_general_and_never_refused(shop: _Shop) -> None:
    """A bill of two companies takes the firm's own series."""
    asian = shop.product("A1", shop.company("ASIAN", "AS"))
    pidi = shop.product("P1", shop.company("PIDI", "PD"))
    shop.by_company()

    mixed = shop.bill(asian, pidi)
    single = shop.bill(pidi)

    assert mixed.invoice_number == "SI-26-27-000001"
    assert mixed.series_prefix == "GENERAL"
    assert single.invoice_number == "PD-26-27-000001"
    assert single.series_prefix == "PD"


# -- 4. restart ---------------------------------------------------------------
def test_each_series_restarts_each_year_and_a_back_dated_bill_carries_on(
    shop: _Shop,
) -> None:
    """A new year starts at 1; last year's counter carries on where it was."""
    rule = shop.bill_rule()
    numbers = DocumentFrameworkService(shop.session)

    def issue(on: date) -> str:
        return numbers.reserve_number(
            rule.id,
            firm_id=shop.firm_id,
            document_date=on,
            actor_id=ACTOR,
            series_prefix="AS",
        )

    assert issue(date(2026, 8, 4)) == "AS-26-27-000001"
    assert issue(date(2026, 9, 4)) == "AS-26-27-000002"
    assert issue(date(2027, 4, 2)) == "AS-27-28-000001"
    assert issue(date(2027, 3, 30)) == "AS-26-27-000003"
    assert issue(date(2027, 4, 3)) == "AS-27-28-000002"


# -- 5. limit -----------------------------------------------------------------
def test_a_prefix_that_cannot_fit_sixteen_characters_is_refused_at_save(
    shop: _Shop,
) -> None:
    """The longest number a prefix could print is judged when it is saved."""
    brands = BrandService(shop.session)
    with pytest.raises(ValidationError, match="up to 3 characters"):
        brands.save_principal(
            PrincipalWrite(code="ASIAN", name="Asian", bill_series_prefix="ASIA"),
            firm_id=shop.firm_id,
            actor_id=ACTOR,
        )
    shop.session.rollback()

    saved = brands.save_principal(
        PrincipalWrite(code="ASIAN", name="Asian", bill_series_prefix=" asn "),
        firm_id=shop.firm_id,
        actor_id=ACTOR,
    )
    assert saved.bill_series_prefix == "ASN"
    assert BillSeriesService(shop.session).settings(shop.firm_id).longest_prefix == 3


def test_a_prefix_holds_letters_and_digits_only() -> None:
    """A character GST refuses never reaches the column."""
    with pytest.raises(PydanticValidationError):
        PrincipalWrite(code="X", name="X", bill_series_prefix="AS/1")


def test_widening_the_layout_past_a_prefix_in_use_is_refused(shop: _Shop) -> None:
    """More digits on the bill series are refused if a prefix would not fit."""
    rule = shop.bill_rule()
    shop.company("ASIAN", "ASN")

    with pytest.raises(ValidationError, match="prefix ASN"):
        DocumentFrameworkService(shop.session).update_numbering_rule(
            shop.firm_id,
            rule.id,
            DocumentNumberingRuleUpdate(
                document_type_id=rule.document_type_id,
                code=rule.code,
                name=rule.name,
                sequence_padding=7,
            ),
            ACTOR,
        )


def test_a_change_that_leaves_the_prefix_out_leaves_it_alone(shop: _Shop) -> None:
    """Absent means leave alone on a change; an explicit null clears it."""
    brands = BrandService(shop.session)
    saved = brands.save_principal(
        PrincipalWrite(code="ASIAN", name="Asian", bill_series_prefix="AS"),
        firm_id=shop.firm_id,
        actor_id=ACTOR,
    )
    renamed = brands.save_principal(
        PrincipalWrite(code="ASIAN", name="Asian Paints"),
        firm_id=shop.firm_id,
        actor_id=ACTOR,
        principal_id=saved.id,
    )
    assert renamed.bill_series_prefix == "AS"
    cleared = brands.save_principal(
        PrincipalWrite(code="ASIAN", name="Asian Paints", bill_series_prefix=None),
        firm_id=shop.firm_id,
        actor_id=ACTOR,
        principal_id=saved.id,
    )
    assert cleared.bill_series_prefix is None


# -- 6. switching -------------------------------------------------------------
def test_switching_on_off_and_on_again_resets_and_reuses_nothing(shop: _Shop) -> None:
    """GENERAL and each company carry on wherever they were."""
    asian = shop.product("A1", shop.company("ASIAN", "AS"))

    first = shop.bill(asian).invoice_number
    shop.by_company()
    second = shop.bill(asian).invoice_number
    shop.by_company("ONE_SERIES")
    third = shop.bill(asian).invoice_number
    shop.by_company()
    fourth = shop.bill(asian).invoice_number

    assert [first, second, third, fourth] == [
        "SI-26-27-000001",
        "AS-26-27-000001",
        "SI-26-27-000002",
        "AS-26-27-000002",
    ]


def test_an_unknown_setting_is_refused(shop: _Shop) -> None:
    """Only the levels this build numbers by may be chosen."""
    with pytest.raises(ValidationError, match="BY_BRAND"):
        shop.by_company("BY_BRAND")


# -- 8. other documents -------------------------------------------------------
@pytest.mark.parametrize(
    "service_type", [SalesReturnService, CreditNoteService, ProformaService]
)
def test_returns_notes_and_proformas_keep_their_own_series(
    shop: _Shop, service_type: type[SalesReturnService]
) -> None:
    """Only the sales bill takes a company series; the rest number as before."""
    shop.company("ASIAN", "AS")
    shop.by_company()
    _, rule = service_type(shop.session)._ensure_document_setup(
        firm_id=shop.firm_id, actor_id=ACTOR
    )
    expected = DocumentFrameworkService(shop.session).preview_number(
        rule.id, firm_id=shop.firm_id, document_date=date(2026, 8, 4)
    )

    number = DocumentFrameworkService(shop.session).reserve_number(
        rule.id,
        firm_id=shop.firm_id,
        document_date=date(2026, 8, 4),
        actor_id=ACTOR,
        series_prefix="AS",
    )

    assert number == expected
    assert not number.startswith("AS-")
    assert shop.session.scalars(select(BillSeriesCounter)).all() == []


# -- 9. preview ---------------------------------------------------------------
def test_the_preview_names_the_number_the_saved_bill_gets(shop: _Shop) -> None:
    """The series text the form shows is what the bill is numbered."""
    asian = shop.product("A1", shop.company("ASIAN", "AS"))
    pidi = shop.product("P1", shop.company("PIDI", "PD"))
    shop.by_company()
    service = BillSeriesService(shop.session)
    on = date(2026, 8, 4)

    shop.bill(asian)
    preview = service.preview(shop.firm_id, [asian.id], on=on)
    assert (preview.series_prefix, preview.reason) == ("AS", "ONE_COMPANY")
    assert preview.number == shop.bill(asian).invoice_number == "AS-26-27-000002"

    mixed = service.preview(shop.firm_id, [asian.id, pidi.id], on=on)
    assert (mixed.series_prefix, mixed.reason) == ("GENERAL", "MIXED")
    assert mixed.number == shop.bill(asian, pidi).invoice_number


def test_the_preview_writes_nothing_for_a_firm_that_never_billed(shop: _Shop) -> None:
    """A firm with no series yet is shown the one its first bill makes."""
    preview = BillSeriesService(shop.session).preview(
        shop.firm_id, [shop.setup.product.id], on=date(2026, 8, 4)
    )
    assert preview.number == "SI-26-27-000001"
    assert shop.session.scalars(select(DocumentNumberingRule)).all() == []


# -- 7. the backfill ----------------------------------------------------------
def test_the_backfill_starts_general_past_the_last_bill_issued(shop: _Shop) -> None:
    """GENERAL follows the last number printed, even where the rule fell behind."""
    shop.bill(shop.setup.product)
    shop.bill(shop.setup.product)
    # As a store looked before the migration: no bill series counters, and a
    # rule counter that fell behind the bills (a number typed ahead of it).
    shop.session.execute(delete(BillSeriesCounter))
    shop.session.execute(update(DocumentNumberSequence).values(next_sequence=1))
    shop.session.commit()

    path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "20261017_0395_bill_series_by_company.py"
    )
    spec = importlib.util.spec_from_file_location("bill_series_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    connection = shop.session.connection()
    with Operations.context(MigrationContext.configure(connection)):
        migration.upgrade()
        migration.upgrade()  # a replay overwrites and duplicates nothing
    shop.session.commit()

    counters = shop.session.scalars(select(BillSeriesCounter)).all()
    assert [
        (row.prefix, row.financial_year, row.next_sequence) for row in counters
    ] == [("GENERAL", "2026-2027", 3)]
    assert shop.bill(shop.setup.product).invoice_number == "SI-26-27-000003"


# -- 10. later levels ---------------------------------------------------------
def test_a_later_level_is_an_entry_in_the_table_of_drivers(
    shop: _Shop, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fake level is added by one entry and numbers bills with no rewrite."""

    def every_product_is_zz(
        session: object, firm_id: UUID, product_ids: object
    ) -> dict[UUID, str | None]:
        assert isinstance(product_ids, list)
        return dict.fromkeys(product_ids, "ZZ")

    monkeypatch.setitem(bill_series.SERIES_DRIVERS, "BY_TEST", every_product_is_zz)
    shop.by_company("BY_TEST")

    assert "BY_TEST" in BillSeriesService(shop.session).settings(shop.firm_id).drivers
    assert shop.bill(shop.setup.product).invoice_number == "ZZ-26-27-000001"

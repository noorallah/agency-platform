"""PG-13 (§86 #7): fixed assets -- the register, depreciation and disposal.

A firm typing only the bill buys a machine for 1,00,000 on 10 August 2026 and
marks the line capital goods in *Plant and Machinery* (SLM over 15 years, 5%
residual, 15% Income-tax block): approving the bill raises asset FA-00001 and
debits *Fixed Assets* 1,00,000 -- nothing enters stock and nothing is left to
the receipt accrual. A depreciation run charges it pro rata by days, a
disposal charges it to the day and books the gain or loss, and the
Income-tax block schedule halves the rate on what was put to use for less
than 180 days.

Sessions are shaped like a request's (no autoflush), as in the purchase-chain
tests.
"""

# ruff: noqa: D103

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import Response
from fastapi.routing import APIRoute
from sqlalchemy import event, select

from app.business.models import BusinessProfile
from app.common.scope import ResolvedFirmScope
from app.core.exceptions import AuthorizationError, ValidationError
from app.finance.models import FinancialYear
from app.finance.services.control_accounts import ControlAccountPurpose
from app.fixed_assets.api.router import list_fixed_assets, run_depreciation
from app.fixed_assets.api.router import router as fixed_assets_router
from app.fixed_assets.models import AssetClass, FixedAsset
from app.fixed_assets.schemas import (
    AssetClassCreate,
    DepreciationRunCreate,
    FixedAssetCreate,
    FixedAssetDispose,
)
from app.fixed_assets.services import (
    BlockAsset,
    ChargeBasis,
    FixedAssetService,
    charge_for,
    it_block_schedule,
)
from app.gst_returns.services.gstr_service import GstReturnService
from app.identity.system_seed import PERMISSION_GROUPS, ROLE_PERMISSION_CODES
from app.purchase_invoice.models import PurchaseInvoice
from app.purchase_invoice.schemas import PurchaseInvoiceCreate
from app.purchase_invoice.services.gst_purchase_register import (
    GstPurchaseRegisterService,
)
from app.sales.models import GeoCountry
from app.tax.schemas import (
    TaxComponentWrite,
    TaxProfileWrite,
    TaxRuleWrite,
    TaxSystemWrite,
)
from app.tax.services.tax_framework_service import TaxFrameworkService
from app.tax.services.tax_rule_service import TaxRuleService
from tests.unit.test_cash_purchase import _chain_firm
from tests.unit.test_purchase_chain_synthesis import _Firm

pytestmark = pytest.mark.typed_document_numbers

D = Decimal
CENT = D("0.01")
BOUGHT = date(2026, 8, 10)


def _q(value: Decimal) -> Decimal:
    return value.quantize(CENT)


def _class(firm: _Firm, code: str = "PLANT") -> AssetClass:
    row = firm.session.scalar(
        select(AssetClass).where(
            AssetClass.firm_id == firm.firm.id, AssetClass.code == code
        )
    )
    assert row is not None, f"class {code} was not seeded"
    return row


def _service(firm: _Firm) -> FixedAssetService:
    return FixedAssetService(firm.session)


def _capital_bill(
    firm: _Firm, *, price: str = "100000", number: str = "M-1", capital: bool = True
) -> PurchaseInvoice:
    data = PurchaseInvoiceCreate.model_validate(
        {
            "vendor_id": firm.vendor.id,
            "invoice_date": BOUGHT.isoformat(),
            "supplier_invoice_number": number,
            "supplier_invoice_date": BOUGHT.isoformat(),
            "lines": [
                {
                    "line_number": 1,
                    "product_id": firm.product.id,
                    "current_invoice_quantity": "1",
                    "unit_price": price,
                    "is_capital_goods": capital,
                    "asset_class_id": str(_class(firm).id) if capital else None,
                }
            ],
        }
    )
    bills = firm.bills()
    bill = bills.create_invoice(data, firm_id=firm.firm.id, actor_id=firm.actor_id)
    return bills.approve_invoice(
        bill.id, firm_scope=firm.firm.id, actor_id=firm.actor_id
    )


def _assets(firm: _Firm) -> list[FixedAsset]:
    return list(
        firm.session.scalars(
            select(FixedAsset).where(
                FixedAsset.firm_id == firm.firm.id, FixedAsset.is_deleted.is_(False)
            )
        ).all()
    )


def _run(firm: _Firm, first: date, last: date) -> object:
    return _service(firm).run(
        DepreciationRunCreate(period_from=first, period_to=last),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )


def _manual(firm: _Firm, **fields: object) -> FixedAsset:
    data = FixedAssetCreate.model_validate(
        {
            "name": "Old lathe",
            "asset_class_id": str(_class(firm).id),
            "acquisition_date": "2026-04-01",
            "cost": "100000",
            **fields,
        }
    )
    return _service(firm).create(data, firm_id=firm.firm.id, actor_id=firm.actor_id)


# -- from a bill ---------------------------------------------------------------


def test_a_capital_goods_line_raises_an_asset_and_puts_nothing_in_stock() -> None:
    firm = _chain_firm()
    bill = _capital_bill(firm)

    (asset,) = _assets(firm)
    assert asset.asset_number == "FA-00001"
    assert asset.purchase_invoice_id == bill.id
    assert asset.cost == D("100000.00")
    assert asset.residual_value == D("5000.00")
    assert (asset.acquisition_date, asset.put_to_use_date) == (BOUGHT, BOUGHT)
    assert asset.status == "ACTIVE"
    # Dr Fixed Assets, Cr the supplier: no stock, no accrual, no variance.
    assert firm.stock() == D("0")
    assert firm.balance(ControlAccountPurpose.FIXED_ASSET_COST) == D("100000")
    assert firm.balance(ControlAccountPurpose.ACCOUNTS_PAYABLE) == D("-100000")
    assert firm.balance(ControlAccountPurpose.INVENTORY) == 0
    assert firm.balance(ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED) == 0
    assert firm.balance(ControlAccountPurpose.PURCHASE_PRICE_VARIANCE) == 0
    _, receipt = firm.raised(bill)
    assert receipt.status == "COMPLETED"


def test_an_ordinary_line_still_goes_into_stock() -> None:
    firm = _chain_firm()
    _capital_bill(firm, capital=False)
    assert _assets(firm) == []
    assert firm.stock() == D("1")
    assert firm.balance(ControlAccountPurpose.INVENTORY) == D("100000")


def test_a_capital_line_needs_a_class() -> None:
    firm = _chain_firm()
    data = PurchaseInvoiceCreate.model_validate(
        {
            "vendor_id": firm.vendor.id,
            "invoice_date": BOUGHT.isoformat(),
            "supplier_invoice_number": "M-9",
            "supplier_invoice_date": BOUGHT.isoformat(),
            "lines": [
                {
                    "line_number": 1,
                    "product_id": firm.product.id,
                    "current_invoice_quantity": "1",
                    "unit_price": "100",
                    "is_capital_goods": True,
                }
            ],
        }
    )
    with pytest.raises(ValidationError, match="choose its asset class"):
        firm.bills().create_invoice(data, firm_id=firm.firm.id, actor_id=firm.actor_id)


def test_cancelling_the_bill_takes_its_asset_off_until_it_is_depreciated() -> None:
    firm = _chain_firm()
    bill = _capital_bill(firm)
    _run(firm, date(2026, 8, 1), date(2026, 9, 30))
    with pytest.raises(ValidationError, match="depreciated or disposed"):
        firm.bills().cancel_invoice(
            bill.id, firm_scope=firm.firm.id, actor_id=firm.actor_id, reason="x"
        )
    firm.session.rollback()

    other = _chain_firm()
    second = _capital_bill(other)
    other.bills().cancel_invoice(
        second.id, firm_scope=other.firm.id, actor_id=other.actor_id, reason="x"
    )
    assert _assets(other) == []
    assert other.balance(ControlAccountPurpose.FIXED_ASSET_COST) == 0


# -- GST -----------------------------------------------------------------------


def _gst_18_local(firm: _Firm) -> None:
    """Charge 9% CGST + 9% SGST on every purchase of the firm's product."""
    session = firm.session
    country = GeoCountry(
        code="IN",
        name="India",
        iso2="IN",
        iso3="IND",
        phone_code="+91",
        is_active=True,
    )
    session.add(country)
    session.commit()
    profile_row = session.scalars(
        select(BusinessProfile).where(BusinessProfile.code == "GENERIC")
    ).one()
    framework = TaxFrameworkService(session)
    system = framework.create_system(
        TaxSystemWrite(country_id=country.id, code="GST", name="GST"),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    components = [
        framework.create_component(
            TaxComponentWrite(
                tax_system_id=system.id,
                code=code,
                name=code,
                label=code,
                percentage="9",
            ),
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )
        for code in ("CGST", "SGST")
    ]
    profile = framework.create_profile(
        TaxProfileWrite(
            tax_system_id=system.id,
            business_profile_id=profile_row.id,
            code="GST_18_LOCAL",
            name="GST 18 local",
            components=[
                {
                    "tax_component_id": component.id,
                    "percentage": "9",
                    "calculation_order": order,
                    "recoverable": True,
                }
                for order, component in enumerate(components, start=1)
            ],
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    TaxRuleService(session).create_rule(
        TaxRuleWrite(
            country_id=country.id,
            business_profile_id=profile_row.id,
            code="PURCHASE_DEFAULT",
            name="Purchase default",
            priority=50,
            status="ACTIVE",
            actions=[
                {
                    "sequence": 1,
                    "action_type": "APPLY_TAX_PROFILE",
                    "target_tax_profile_id": profile.id,
                }
            ],
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    firm.product.tax_profile_group_code = "GST_18_LOCAL"
    firm.firm.gst_number = "33AABCU9603R1ZM"
    session.commit()


def test_the_gst_on_capital_goods_is_claimed_in_full_and_shown_apart() -> None:
    firm = _chain_firm()
    _gst_18_local(firm)
    bill = _capital_bill(firm)
    assert bill.tax_total == D("18000.0000")

    (asset,) = _assets(firm)
    assert asset.cost == D("100000.00"), "the tax is credit, not cost"
    assert firm.balance(ControlAccountPurpose.FIXED_ASSET_COST) == D("100000")
    claimed = firm.balance(ControlAccountPurpose.INPUT_TAX_CGST) + firm.balance(
        ControlAccountPurpose.INPUT_TAX_SGST
    )
    assert claimed == D("18000")
    assert firm.balance(ControlAccountPurpose.ACCOUNTS_PAYABLE) == D("-118000")
    summary = GstReturnService(firm.session).gstr3b(
        firm_scope=firm.firm.id, from_date=date(2026, 8, 1), to_date=date(2026, 8, 31)
    )
    eligible = summary["eligible_itc"]
    assert isinstance(eligible, dict)
    assert float(eligible["central_tax"]) == pytest.approx(9000)
    (row,) = GstPurchaseRegisterService(firm.session).register(firm.firm.id)
    assert row.capital_goods_tax == D("18000.00")
    assert row.total_tax == D("18000.00")


# -- depreciation --------------------------------------------------------------


def test_slm_and_wdv_charge_a_part_year_by_days() -> None:
    slm = ChargeBasis(
        method="SLM",
        cost=D("100000"),
        residual_value=D("5000"),
        rate_percent=None,
        useful_life_years=D("10"),
    )
    # 9,500 a year for 183 days (1 April to 30 September).
    assert charge_for(slm, book_value=D("100000"), days=183) == D("4763.01")
    wdv = ChargeBasis(
        method="WDV",
        cost=D("100000"),
        residual_value=D("5000"),
        rate_percent=D("15"),
        useful_life_years=None,
    )
    assert charge_for(wdv, book_value=D("100000"), days=183) == D("7520.55")
    # WDV is on what is left, and never below the residual value.
    assert charge_for(wdv, book_value=D("80000"), days=365) == D("12000.00")
    assert charge_for(wdv, book_value=D("5100"), days=365) == D("100.00")
    assert charge_for(slm, book_value=D("5000"), days=365) == D("0")


def test_a_run_charges_each_asset_from_its_put_to_use_day_and_posts() -> None:
    firm = _chain_firm()
    _capital_bill(firm)  # PLANT, SLM 15 years, put to use 10 August
    service = _service(firm)
    wdv = service.create_class(
        AssetClassCreate(
            code="WDV15",
            name="Machinery at 15% WDV",
            depreciation_method="WDV",
            rate_percent=D("15"),
            it_block_rate_percent=D("15"),
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    manual = _manual(firm, asset_class_id=str(wdv.id))

    run = _run(firm, date(2026, 4, 1), date(2026, 9, 30))
    (view,) = service.run_responses([run])  # type: ignore[list-item]
    charged = {line.asset_number: line for line in view.lines}
    bought = charged["FA-00001"]
    assert (bought.from_date, bought.days) == (BOUGHT, 52)
    assert bought.amount == _q(D("95000") / 15 * 52 / 365)
    held = charged[manual.asset_number]
    assert (held.from_date, held.days) == (date(2026, 4, 1), 183)
    assert held.amount == D("7520.55")
    assert view.total_amount == bought.amount + held.amount
    assert firm.balance(ControlAccountPurpose.DEPRECIATION_EXPENSE) == (
        view.total_amount
    )
    assert firm.balance(ControlAccountPurpose.ACCUMULATED_DEPRECIATION) == (
        -view.total_amount
    )
    # The next run starts where this one stopped; WDV is on what is left.
    second = _run(firm, date(2026, 10, 1), date(2027, 3, 31))
    (later,) = service.run_responses([second])  # type: ignore[list-item]
    again = {line.asset_number: line for line in later.lines}[manual.asset_number]
    assert again.opening_book_value == D("92479.45")
    assert again.amount == _q(D("92479.45") * D("0.15") * 182 / 365)


def test_an_overlapping_or_earlier_run_is_refused() -> None:
    firm = _chain_firm()
    _capital_bill(firm)
    _run(firm, date(2026, 8, 1), date(2026, 9, 30))
    with pytest.raises(ValidationError, match="already charged"):
        _run(firm, date(2026, 9, 1), date(2026, 12, 31))
    with pytest.raises(ValidationError, match="Runs go forward"):
        _run(firm, date(2026, 4, 1), date(2026, 7, 31))
    with pytest.raises(ValidationError, match="ends before it starts"):
        _run(firm, date(2026, 12, 31), date(2026, 10, 1))


def test_cancelling_a_run_reverses_it_and_frees_the_period() -> None:
    firm = _chain_firm()
    _capital_bill(firm)
    service = _service(firm)
    first = _run(firm, date(2026, 8, 1), date(2026, 9, 30))
    later = _run(firm, date(2026, 10, 1), date(2026, 12, 31))
    with pytest.raises(ValidationError, match="later run"):
        service.cancel_run(
            first.id,  # type: ignore[attr-defined]
            "wrong rate",
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )
    firm.session.rollback()
    for run in (later, first):
        cancelled = service.cancel_run(
            run.id,  # type: ignore[attr-defined]
            "wrong rate",
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )
        assert cancelled.status == "CANCELLED"
        assert cancelled.reversal_journal_entry_id is not None
    assert firm.balance(ControlAccountPurpose.DEPRECIATION_EXPENSE) == 0
    assert firm.balance(ControlAccountPurpose.ACCUMULATED_DEPRECIATION) == 0
    rerun = _run(firm, date(2026, 8, 1), date(2026, 9, 30))
    assert rerun.status == "POSTED"  # type: ignore[attr-defined]


# -- disposal ------------------------------------------------------------------


def _dispose(firm: _Firm, asset: FixedAsset, sale: str, on: date) -> FixedAsset:
    return _service(firm).dispose(
        asset.id,
        FixedAssetDispose(
            disposal_date=on, sale_amount=D(sale), method="CASH", reason="Sold"
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )


def test_disposal_charges_to_the_day_then_books_a_gain() -> None:
    firm = _chain_firm()
    _capital_bill(firm)
    (asset,) = _assets(firm)
    on = date(2026, 12, 31)
    charge = _q(D("95000") / 15 * 144 / 365)

    sold = _dispose(firm, asset, "100000", on)

    assert sold.status == "DISPOSED"
    assert sold.disposed_on == on
    assert sold.disposal_gain_loss == charge  # 1,00,000 less (1,00,000 - charge)
    assert firm.balance(ControlAccountPurpose.DEPRECIATION_EXPENSE) == charge
    # Cost and accumulated depreciation both leave the books.
    assert firm.balance(ControlAccountPurpose.FIXED_ASSET_COST) == 0
    assert firm.balance(ControlAccountPurpose.ACCUMULATED_DEPRECIATION) == 0
    assert firm.balance(ControlAccountPurpose.CASH) == D("100000")
    assert firm.balance(ControlAccountPurpose.ASSET_DISPOSAL_GAIN_LOSS) == -charge
    with pytest.raises(ValidationError, match="already disposed"):
        _dispose(firm, sold, "1", on)
    firm.session.rollback()
    # Disposed assets are left out of later runs.
    with pytest.raises(ValidationError, match="No asset is due"):
        _run(firm, date(2027, 1, 1), date(2027, 3, 31))


def test_disposal_below_book_value_books_a_loss() -> None:
    firm = _chain_firm()
    _capital_bill(firm)
    (asset,) = _assets(firm)
    _run(firm, date(2026, 8, 1), date(2026, 9, 30))
    charged = _q(D("95000") / 15 * 52 / 365)
    on = date(2026, 9, 30)  # the day the run charged to: nothing more to charge

    sold = _dispose(firm, asset, "50000", on)

    book_value = D("100000") - charged
    assert sold.disposal_gain_loss == D("50000") - book_value
    assert firm.balance(ControlAccountPurpose.ASSET_DISPOSAL_GAIN_LOSS) == (
        book_value - D("50000")
    )
    assert firm.balance(ControlAccountPurpose.FIXED_ASSET_COST) == 0
    assert firm.balance(ControlAccountPurpose.ACCUMULATED_DEPRECIATION) == 0
    with pytest.raises(ValidationError, match="disposed"):
        _service(firm).cancel_run(
            _service(firm)
            .run_page(
                firm.firm.id, status="POSTED", run_type=None, page=1, page_size=5
            )[0][0]
            .id,
            "x",
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )


def test_a_disposal_before_depreciation_already_charged_is_refused() -> None:
    firm = _chain_firm()
    _capital_bill(firm)
    (asset,) = _assets(firm)
    _run(firm, date(2026, 8, 1), date(2026, 9, 30))
    with pytest.raises(ValidationError, match="charged to 2026-09-30"):
        _dispose(firm, asset, "1000", date(2026, 9, 1))


# -- opening assets ------------------------------------------------------------


def test_an_opening_asset_carries_its_depreciation_and_charges_on_from_there() -> None:
    firm = _chain_firm()
    asset = _manual(
        firm,
        acquisition_date="2023-04-01",
        opening_accumulated_depreciation="30000",
        opening_as_of="2026-03-31",
    )
    service = _service(firm)
    (view,) = service.responses([asset])
    assert view.accumulated_depreciation == D("30000.00")
    assert view.net_book_value == D("70000.00")
    assert view.depreciated_to == date(2026, 3, 31)
    # Typing an asset by hand books nothing: its cost came with the opening
    # balances.
    assert firm.balance(ControlAccountPurpose.FIXED_ASSET_COST) == 0

    _run(firm, date(2026, 4, 1), date(2026, 9, 30))
    charge = _q(D("95000") / 15 * 183 / 365)
    (after,) = service.responses([asset])
    assert after.accumulated_depreciation == D("30000.00") + charge
    assert after.depreciated_to == date(2026, 9, 30)
    schedule = service.schedule(asset.id, firm_id=firm.firm.id)
    (charged,) = schedule.charged
    assert charged.amount == charge
    first = schedule.projected[0]
    assert (first.from_date, first.to_date) == (date(2026, 10, 1), date(2027, 3, 31))
    assert schedule.projected[-1].closing_book_value == D("5000.00")
    with pytest.raises(ValidationError, match="opening_as_of"):
        _manual(firm, opening_accumulated_depreciation="1000")


# -- the Income-tax block schedule ---------------------------------------------


def test_the_block_halves_the_rate_on_additions_used_under_180_days() -> None:
    year = date(2026, 4, 1)
    assets = [
        BlockAsset(
            block_rate=D("15"),
            class_name="Plant",
            put_to_use_date=date(2020, 4, 1),
            cost=D("150000"),
            opening_from=year,
            opening_wdv=D("100000"),
        ),
        # 1 June to 31 March: 304 days, the full rate.
        BlockAsset(
            block_rate=D("15"),
            class_name="Plant",
            put_to_use_date=date(2026, 6, 1),
            cost=D("200000"),
        ),
        # 1 December to 31 March: 121 days, half the rate.
        BlockAsset(
            block_rate=D("15"),
            class_name="Plant",
            put_to_use_date=date(2026, 12, 1),
            cost=D("100000"),
        ),
        # Sold for 50,000 in the year.
        BlockAsset(
            block_rate=D("15"),
            class_name="Plant",
            put_to_use_date=date(2026, 5, 1),
            cost=D("0"),
            disposed_on=date(2027, 1, 15),
            sale_amount=D("50000"),
        ),
    ]
    (row,) = it_block_schedule(assets, year_starts_on=year)
    assert row.opening_wdv == D("100000.00")
    assert row.additions_full_rate == D("200000.00")
    assert row.additions_half_rate == D("100000.00")
    assert row.disposals == D("50000.00")
    # 15% of (1,00,000 + 2,00,000 - 50,000) and 7.5% of 1,00,000.
    assert row.depreciation_full_rate == D("37500.00")
    assert row.depreciation_half_rate == D("7500.00")
    assert row.closing_wdv == D("305000.00")
    # The next year opens where this one closed, at the full rate.
    (following,) = it_block_schedule(assets, year_starts_on=date(2027, 4, 1))
    assert following.opening_wdv == D("305000.00")
    assert following.depreciation == D("45750.00")
    # Proceeds beyond the block leave it nil, as a short-term capital gain.
    (nil,) = it_block_schedule(
        [
            BlockAsset(
                block_rate=D("40"),
                class_name="Computers",
                put_to_use_date=date(2026, 5, 1),
                cost=D("60000"),
                disposed_on=date(2026, 9, 1),
                sale_amount=D("80000"),
            )
        ],
        year_starts_on=year,
    )
    assert (nil.closing_wdv, nil.short_term_capital_gain) == (D("0"), D("20000.00"))


def test_the_block_schedule_reads_the_register_for_the_firms_year() -> None:
    firm = _chain_firm()
    _capital_bill(firm)  # PLANT, 15%, used 234 days: full rate
    _manual(
        firm,
        acquisition_date="2022-04-01",
        opening_accumulated_depreciation="20000",
        opening_as_of="2026-03-31",
        opening_it_wdv="60000",
    )
    year = firm.session.scalar(
        select(FinancialYear).where(FinancialYear.firm_id == firm.firm.id)
    )
    assert year is not None
    schedule = _service(firm).it_block_schedule(year.id, firm_id=firm.firm.id)
    (block,) = schedule.blocks
    assert block.block_rate == D("15.0000")
    assert block.class_names == ["Plant and Machinery"]
    assert block.opening_wdv == D("60000.00")
    assert block.additions_full_rate == D("100000.00")
    assert block.depreciation == D("24000.00")
    assert block.closing_wdv == D("136000.00")
    # A view: nothing posted.
    assert firm.balance(ControlAccountPurpose.DEPRECIATION_EXPENSE) == 0


# -- permissions ---------------------------------------------------------------


def _route_codes(method: str, suffix: str) -> set[str]:
    route = next(
        item
        for item in fixed_assets_router.routes
        if isinstance(item, APIRoute)
        and method in item.methods
        and item.path.endswith(suffix)
    )
    assert isinstance(route, APIRoute)
    codes: set[str] = set()
    pending = list(route.dependant.dependencies)
    while pending:
        dependency = pending.pop()
        code = getattr(dependency.call, "permission_code", None)
        if code:
            codes.add(code)
        pending.extend(dependency.dependencies)
    return codes


def test_the_register_is_the_accountants_and_posting_needs_journal_post() -> None:
    assert {"FIXED_ASSET_VIEW", "FIXED_ASSET_MANAGE"} <= set(
        PERMISSION_GROUPS["accounting"]
    )
    for role in ("ACCOUNTANT", "FIRM_ADMIN", "FIRM_MANAGER"):
        assert {"FIXED_ASSET_VIEW", "FIXED_ASSET_MANAGE"} <= ROLE_PERMISSION_CODES[role]
    assert _route_codes("GET", "/fixed-assets") == {"FIXED_ASSET_VIEW"}
    assert _route_codes("POST", "/depreciation-runs") == {"FIXED_ASSET_MANAGE"}
    assert _route_codes("POST", "/{asset_id}/dispose") == {"FIXED_ASSET_MANAGE"}
    assert _route_codes("GET", "/reports/it-block-schedule") == {"FIXED_ASSET_VIEW"}

    firm = _chain_firm()
    _capital_bill(firm)
    principal = SimpleNamespace(has_permission=lambda code: code != "JOURNAL_POST")
    scope = cast(
        ResolvedFirmScope,
        SimpleNamespace(firm_id=firm.firm.id, principal=principal, actor_id=None),
    )
    with pytest.raises(AuthorizationError, match="JOURNAL_POST"):
        run_depreciation(
            data=DepreciationRunCreate(
                period_from=date(2026, 8, 1), period_to=date(2026, 9, 30)
            ),
            scope=scope,
            response=cast(Response, SimpleNamespace(headers={})),
            db=firm.session,
        )


# -- the list ------------------------------------------------------------------


@contextmanager
def _counted(firm: _Firm) -> Iterator[list[str]]:
    statements: list[str] = []
    engine = firm.session.get_bind()

    def count(*args: object) -> None:
        statements.append(str(args[2]))

    event.listen(engine, "before_cursor_execute", count)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", count)


def test_the_register_page_costs_the_same_at_any_length() -> None:
    firm = _chain_firm()
    _capital_bill(firm)
    scope = cast(ResolvedFirmScope, SimpleNamespace(firm_id=firm.firm.id))

    def page_cost() -> tuple[int, int]:
        firm.session.expire_all()
        with _counted(firm) as statements:
            answer = list_fixed_assets(
                scope=scope,
                page=1,
                page_size=50,
                search=None,
                status_filter=None,
                asset_class_id=None,
                branch_id=None,
                as_of=None,
                db=firm.session,
            )
        return len(statements), len(answer.data)

    for number in range(2):
        _manual(firm, name=f"Desk {number}")
    small, rows = page_cost()
    assert rows == 3
    for number in range(2, 8):
        _manual(firm, name=f"Desk {number}")
    _run(firm, date(2026, 8, 1), date(2026, 9, 30))
    large, rows = page_cost()
    assert rows == 9
    assert large <= small + 1
    found = list_fixed_assets(
        scope=scope,
        page=1,
        page_size=50,
        search="Desk 5",
        status_filter="active",
        asset_class_id=_class(firm).id,
        branch_id=None,
        as_of=None,
        db=firm.session,
    )
    assert [row.name for row in found.data] == ["Desk 5"]
    assert found.data[0].net_book_value == found.data[0].cost - (
        found.data[0].accumulated_depreciation
    )

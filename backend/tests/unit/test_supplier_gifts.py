"""The supplier gifts register (BUY-2, decision A112).

A supplier gives a television worth 30,000, kept by the business as an
asset, and a gold coin worth 5,000 the owner takes. Each posts one journal
against supplier incentive income -- the coin to drawings. The 194R summary
shows the supplier past 20,000; taking the television back reverses its
journal and the total falls under the limit. An expense account cannot hold
an asset.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.finance.models import LedgerAccount
from app.finance.services.control_accounts import ControlAccountPurpose
from app.vendors.models.supplier_gift import SupplierGift
from app.vendors.schemas.supplier_gift import SupplierGiftWrite
from app.vendors.services.supplier_gifts import SupplierGiftService
from tests.unit.test_purchase_chain_synthesis import _Firm

D = Decimal


@pytest.fixture
def firm() -> _Firm:
    """Build a firm with open books."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return _Firm(sessionmaker(bind=engine, expire_on_commit=False)(), code="GIFTS")


def _account(firm: _Firm, kind: str) -> UUID:
    account = firm.session.scalar(
        select(LedgerAccount.id).where(
            LedgerAccount.firm_id == firm.firm.id, LedgerAccount.account_type == kind
        )
    )
    assert account is not None
    return account


def _gift(
    firm: _Firm, item: str, value: str, kept_by: str, account: UUID | None
) -> SupplierGift:
    return SupplierGiftService(firm.session).create(
        SupplierGiftWrite(
            gift_date=date(2026, 8, 10),
            vendor_id=firm.vendor.id,
            item=item,
            value=D(value),
            kept_by=kept_by,  # type: ignore[arg-type]
            debit_account_id=account,
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )


def test_gifts_post_by_who_keeps_them_and_total_for_194r(firm: _Firm) -> None:
    television = _gift(firm, "Television", "30000", "ASSET", _account(firm, "ASSET"))
    _gift(firm, "Gold coin", "5000", "OWNER", None)
    assert firm.balance(ControlAccountPurpose.SUPPLIER_INCENTIVE_INCOME) == D("-35000")
    assert firm.balance(ControlAccountPurpose.DRAWINGS) == D("5000")

    service = SupplierGiftService(firm.session)
    (row,) = service.summary_194r(firm.firm.id, on=date(2026, 9, 1))
    assert (row.total_value, row.over_threshold) == (D("35000"), True)
    assert (row.year_from, row.year_to) == (date(2026, 4, 1), date(2027, 3, 31))

    service.cancel(
        television.id, "Returned it", firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    assert firm.balance(ControlAccountPurpose.SUPPLIER_INCENTIVE_INCOME) == D("-5000")
    (row,) = service.summary_194r(firm.firm.id, on=date(2026, 9, 1))
    assert (row.total_value, row.over_threshold) == (D("5000"), False)


def test_an_asset_needs_an_asset_account(firm: _Firm) -> None:
    with pytest.raises(ValidationError, match="asset accounts"):
        _gift(firm, "Television", "30000", "ASSET", _account(firm, "EXPENSE"))

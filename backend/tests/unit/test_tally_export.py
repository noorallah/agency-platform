"""Export to Tally (MSG-5, decision A135).

A supplier bill is approved, posting its journal. The export for the month
is Tally import XML: a Purchase voucher numbered by the journal, whose
ledger entries balance and name the supplier's own ledger in place of the
payables control account, and a master for that supplier under Sundry
Creditors. A mapped account is exported under the CA's name and group.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from xml.etree import ElementTree

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.finance.models import FirmControlAccount
from app.finance.services.control_accounts import ControlAccountPurpose
from app.finance.services.tally_export import TallyExportService, TallyMappingsWrite
from tests.unit.test_purchase_chain_synthesis import _Firm

AUGUST = (date(2026, 8, 1), date(2026, 8, 31))


@pytest.fixture
def firm() -> _Firm:
    """Approve one supplier bill in August."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    built = _Firm(sessionmaker(bind=engine, expire_on_commit=False)(), code="TLY")
    built.stages(order=False, receipt=False)
    bills = built.bills()
    bill = bills.create_invoice(
        built.product_bill("10", "100"), firm_id=built.firm.id, actor_id=built.actor_id
    )
    bills.approve_invoice(bill.id, firm_scope=built.firm.id, actor_id=built.actor_id)
    return built


def _export(firm: _Firm) -> ElementTree.Element:
    data = TallyExportService(firm.session).export(
        firm.firm.id, from_date=AUGUST[0], to_date=AUGUST[1]
    )
    return ElementTree.fromstring(data)


def test_a_bill_becomes_a_balanced_purchase_voucher_naming_the_supplier(
    firm: _Firm,
) -> None:
    root = _export(firm)
    vouchers = root.findall(".//VOUCHER")
    purchase = [v for v in vouchers if v.get("VCHTYPE") == "Purchase"]
    assert purchase, [v.get("VCHTYPE") for v in vouchers]
    voucher = purchase[0]
    amounts = [
        Decimal(entry.findtext("AMOUNT") or "0")
        for entry in voucher.findall("ALLLEDGERENTRIES.LIST")
    ]
    assert sum(amounts, Decimal("0")) == Decimal("0")
    names = [
        entry.findtext("LEDGERNAME")
        for entry in voucher.findall("ALLLEDGERENTRIES.LIST")
    ]
    assert firm.vendor.name in names
    assert voucher.findtext("PARTYLEDGERNAME") == firm.vendor.name
    masters = {
        ledger.get("NAME"): ledger.findtext("PARENT")
        for ledger in root.findall(".//LEDGER")
    }
    assert masters[firm.vendor.name] == "Sundry Creditors"


def test_a_mapped_account_goes_out_under_the_cas_name(firm: _Firm) -> None:
    inventory = firm.session.scalar(
        select(FirmControlAccount.ledger_account_id).where(
            FirmControlAccount.firm_id == firm.firm.id,
            FirmControlAccount.purpose == ControlAccountPurpose.INVENTORY.value,
        )
    )
    assert inventory is not None
    service = TallyExportService(firm.session)
    rows = service.replace_mappings(
        firm.firm.id,
        TallyMappingsWrite.model_validate(
            {
                "mappings": [
                    {
                        "ledger_account_id": inventory,
                        "tally_name": "Stock in Godown",
                        "tally_parent": "Stock-in-Hand",
                    }
                ]
            }
        ),
        actor_id=firm.actor_id,
    )
    assert [r.tally_name for r in rows if r.mapped] == ["Stock in Godown"]
    masters = {
        ledger.get("NAME"): ledger.findtext("PARENT")
        for ledger in _export(firm).findall(".//LEDGER")
    }
    assert masters.get("Stock in Godown") == "Stock-in-Hand"


def test_two_accounts_cannot_share_a_tally_name(firm: _Firm) -> None:
    rows = TallyExportService(firm.session).mappings(firm.firm.id)
    first, second = rows[0], rows[1]
    with pytest.raises(ValidationError, match="share one Tally ledger name"):
        TallyExportService(firm.session).replace_mappings(
            firm.firm.id,
            TallyMappingsWrite.model_validate(
                {
                    "mappings": [
                        {
                            "ledger_account_id": first.ledger_account_id,
                            "tally_name": "X",
                        },
                        {
                            "ledger_account_id": second.ledger_account_id,
                            "tally_name": "x",
                        },
                    ]
                }
            ),
            actor_id=firm.actor_id,
        )

"""A firm that holds a TAN can record it, and has TDS accounts (backlog 53.1).

Before go-live, items 1 and 2: the TAN on the firm and on customers, checked
for its format; and *TDS Payable* and *TDS Receivable* in every firm's chart,
each mapped to its control purpose so the posting that follows in 1.1 has an
account to name rather than an error.
"""

from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError as SchemaError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.customers.schemas import CustomerCreate
from app.finance.models import LedgerAccount
from app.finance.services.control_accounts import (
    ControlAccountPurpose,
    ControlAccountService,
)
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from app.firms.schemas import FirmCreate


def _firm_payload(**extra: object) -> dict[str, object]:
    """Return the fewest fields a firm is created with."""
    return {
        "name": "TAN Traders",
        "code": "TANT",
        "country": "IN",
        "currency_code": "INR",
        "financial_year_start": "2026-04-01",
        **extra,
    }


def _customer(tan: str) -> CustomerCreate:
    """Validate the fewest fields a customer is created with, and a TAN."""
    return CustomerCreate.model_validate(
        {
            "code": "C1",
            "name": "Shop",
            "customer_type": "BUSINESS",
            "currency_code": "INR",
            "tan_number": tan,
        }
    )


def test_a_tan_is_kept_in_capitals_and_a_blank_one_is_none() -> None:
    """Typed in lower case it is stored as issued; an empty box is no TAN."""
    assert FirmCreate.model_validate(
        _firm_payload(tan_number=" dela12345b ")
    ).tan_number == ("DELA12345B")
    assert FirmCreate.model_validate(_firm_payload(tan_number="")).tan_number is None
    customer = _customer("mumk01234c")
    assert customer.tan_number == "MUMK01234C"


@pytest.mark.parametrize(
    "typed",
    ["DEL12345B", "DELA1234AB", "1ELA12345B", "DELA123456", "ABCDE1234F"],
)
def test_a_malformed_tan_is_refused_naming_the_format(typed: str) -> None:
    """Four letters, five digits, a letter -- a PAN in the box is refused too."""
    with pytest.raises(SchemaError, match="four letters, five digits"):
        FirmCreate.model_validate(_firm_payload(tan_number=typed))
    with pytest.raises(SchemaError, match="four letters, five digits"):
        _customer(typed)


def test_opening_the_books_maps_tds_payable_and_receivable() -> None:
    """A new firm's chart has both, each mapped to its purpose."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    firm = Firm(
        name="TDS Firm",
        code="TDSF",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(firm)
    session.commit()
    seed_finance_setup(
        session, firm_id=firm.id, year_starts_on=date(2026, 4, 1), actor_id=uuid4()
    )

    controls = ControlAccountService(session)
    payable = session.get(
        LedgerAccount,
        controls.resolve(firm.id, ControlAccountPurpose.TDS_PAYABLE),
    )
    receivable = session.get(
        LedgerAccount,
        controls.resolve(firm.id, ControlAccountPurpose.TDS_RECEIVABLE),
    )
    assert payable is not None and receivable is not None
    assert (payable.code, payable.name, payable.account_type) == (
        "2700",
        "TDS Payable",
        "LIABILITY",
    )
    assert (receivable.code, receivable.name, receivable.account_type) == (
        "1400",
        "TDS Receivable",
        "ASSET",
    )
    # Distinct from TCS: a different return on a different challan.
    tcs = controls.resolve(firm.id, ControlAccountPurpose.TCS_PAYABLE)
    assert tcs != payable.id
    assert (
        session.scalar(
            select(LedgerAccount.code).where(
                LedgerAccount.firm_id == firm.id, LedgerAccount.code == "2700"
            )
        )
        == "2700"
    )

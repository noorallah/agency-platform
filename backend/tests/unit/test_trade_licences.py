"""The trade licence register (backlog 54, step 1).

Types are a master seeded with the usual ones; a licence belongs to the firm
(or one branch), a customer or a vendor; where it stands is derived from the
day asked about; the expiry list puts the firm's own first; and what prints
is only what is valid on the document's date.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError as SchemaError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import ConflictError, ValidationError
from app.customers.models import Customer
from app.trade_licences.schemas import (
    LicenceHolderType,
    LicenceStanding,
    TradeLicenceTypeWrite,
    TradeLicenceWrite,
)
from app.trade_licences.services import TradeLicenceService
from tests.unit.test_purchase_chain_synthesis import _Firm

TODAY = date(2026, 9, 30)


class _Shop(_Firm):
    """The stage-switch test firm, plus a customer."""

    def __init__(self) -> None:
        """Build the firm on a fresh store and add one customer."""
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        super().__init__(
            sessionmaker(bind=engine, expire_on_commit=False)(), code="LIC"
        )
        self.customer = Customer(
            firm_id=self.firm.id,
            code="CUS-LIC",
            customer_type="BUSINESS",
            name="City Chemists",
            display_name="City Chemists",
            currency_code="INR",
            status="ACTIVE",
            credit_limit=Decimal("0"),
            opening_balance=Decimal("0"),
        )
        self.session.add(self.customer)
        self.session.commit()
        self.service = TradeLicenceService(self.session)
        self.types = {
            row.code: row
            for row in self.service.list_types(self.firm.id, self.actor_id)
        }

    def record(self, code: str, **fields: object) -> object:
        """Record one licence of a type, by code."""
        payload: dict[str, object] = {
            "licence_type_id": self.types[code].id,
            "holder_type": "FIRM",
            "licence_number": "LIC-1",
            "valid_to": TODAY + timedelta(days=365),
            **fields,
        }
        return self.service.create_licence(
            TradeLicenceWrite.model_validate(payload),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )


@pytest.fixture
def shop() -> _Shop:
    """Build a firm with a branch, a vendor and a customer."""
    return _Shop()


def test_the_usual_types_are_seeded_once(shop: _Shop) -> None:
    """Every trade's types, the drug forms named; reading again adds nothing."""
    assert {"DRUG_WHOLESALE", "FSSAI", "INSECTICIDE", "SEED", "OTHER"} <= set(
        shop.types
    )
    assert shop.types["DRUG_WHOLESALE"].form_numbers == "20B / 21B"
    assert shop.types["OTHER"].expires is False
    again = shop.service.list_types(shop.firm.id, shop.actor_id)
    assert len(again) == len(shop.types)


def test_a_type_code_is_unique_and_a_used_type_cannot_be_deleted(
    shop: _Shop,
) -> None:
    """A second FSSAI is refused; a type on a licence is deactivated instead."""
    with pytest.raises(ConflictError):
        shop.service.create_type(
            TradeLicenceTypeWrite(code="fssai", name="Dup"),
            firm_id=shop.firm.id,
            actor_id=shop.actor_id,
        )
    shop.record("FSSAI")
    with pytest.raises(ConflictError, match="Deactivate it instead"):
        shop.service.delete_type(
            shop.types["FSSAI"].id, firm_id=shop.firm.id, actor_id=shop.actor_id
        )


def test_a_licence_that_runs_out_needs_its_valid_to(shop: _Shop) -> None:
    """A drug licence without an end date is refused; an Other one is not."""
    with pytest.raises(ValidationError, match="valid-to date"):
        shop.record("DRUG_WHOLESALE", valid_to=None)
    shop.record("OTHER", valid_to=None)


def test_the_holder_is_the_one_the_type_names() -> None:
    """A customer's licence names a customer and nobody else."""
    with pytest.raises(SchemaError, match="names the customer"):
        TradeLicenceWrite.model_validate(
            {
                "licence_type_id": "00000000-0000-0000-0000-000000000001",
                "holder_type": "CUSTOMER",
                "licence_number": "X",
            }
        )
    with pytest.raises(SchemaError, match="run out before it starts"):
        TradeLicenceWrite.model_validate(
            {
                "licence_type_id": "00000000-0000-0000-0000-000000000001",
                "holder_type": "FIRM",
                "licence_number": "X",
                "valid_from": "2026-09-30",
                "valid_to": "2026-09-01",
            }
        )


def test_a_holder_from_another_firm_is_refused(shop: _Shop) -> None:
    """A customer id this firm does not hold is not found in this firm."""
    other = _Shop()
    with pytest.raises(ValidationError, match="Customer not found"):
        shop.service.create_licence(
            TradeLicenceWrite.model_validate(
                {
                    "licence_type_id": shop.types["DRUG_RETAIL"].id,
                    "holder_type": "CUSTOMER",
                    "customer_id": other.customer.id,
                    "licence_number": "20-1",
                    "valid_to": "2027-01-01",
                }
            ),
            firm_id=shop.firm.id,
            actor_id=shop.actor_id,
        )


def test_the_expiry_list_puts_the_firms_own_first(shop: _Shop) -> None:
    """Expired and expiring within 30 days listed, the firm's before a customer's."""
    shop.record(
        "DRUG_RETAIL",
        holder_type="CUSTOMER",
        customer_id=shop.customer.id,
        licence_number="CUST-EXP",
        valid_to=TODAY - timedelta(days=3),
    )
    shop.record(
        "DRUG_WHOLESALE", licence_number="OWN-SOON", valid_to=TODAY + timedelta(days=10)
    )
    shop.record(
        "FSSAI", licence_number="OWN-LATER", valid_to=TODAY + timedelta(days=200)
    )
    listed = shop.service.list_licences(
        firm_id=shop.firm.id, expiring_within_days=30, on=TODAY
    )
    assert [(item.licence_number, item.standing) for item in listed] == [
        ("OWN-SOON", LicenceStanding.EXPIRING),
        ("CUST-EXP", LicenceStanding.EXPIRED),
    ]
    assert listed[1].holder_name == "City Chemists"
    assert listed[1].days_to_expiry == -3
    assert listed[0].holder_type is LicenceHolderType.FIRM


def test_only_what_is_valid_on_the_day_prints(shop: _Shop) -> None:
    """The firm's and its branch's valid numbers; an expired one is left off."""
    shop.record("FSSAI", licence_number="FSSAI-OK")
    shop.record(
        "DRUG_WHOLESALE",
        branch_id=shop.branch.id,
        licence_number="DL-BRANCH",
    )
    shop.record(
        "INSECTICIDE",
        licence_number="GONE",
        valid_from=TODAY - timedelta(days=400),
        valid_to=TODAY - timedelta(days=1),
    )
    printed = shop.service.valid_numbers(
        firm_id=shop.firm.id, on=TODAY, branch_id=shop.branch.id
    )
    assert printed == [
        ("Drug licence, wholesale", "DL-BRANCH"),
        ("FSSAI licence or registration", "FSSAI-OK"),
    ]
    # Another branch's licence does not print on this one's documents.
    assert shop.service.valid_numbers(firm_id=shop.firm.id, on=TODAY) == [
        ("FSSAI licence or registration", "FSSAI-OK")
    ]

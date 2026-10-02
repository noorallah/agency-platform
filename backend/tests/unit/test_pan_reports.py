"""The PAN reports: parties whose PAN needs attention (PLT-11, decision A53).

`settle_pan` refuses a malformed or mismatched PAN on every write, so the
parties these reports find are ones typed or imported before it and never
edited since. The rows are written straight to the table here for exactly
that reason: through the service they could not exist.
"""

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.core.validation import pan_problem
from app.core.validation.common import (
    PAN_MALFORMED,
    PAN_MISMATCH,
    PAN_NOT_FILLED,
    PAN_NOT_HELD,
)
from app.customers.api.router import customer_pan_check
from app.customers.models import Customer
from app.firms.models import Firm
from app.vendors.api.router import vendor_pan_check
from app.vendors.models import Vendor

GSTIN = "29ABCDE1234F1Z5"


def test_a_pan_problem_is_named_and_a_sound_pan_has_none() -> None:
    """Each of the four problems, and the cases that are not one."""
    assert pan_problem("ABCDE1234F", GSTIN) is None
    assert pan_problem("abcde1234f ", GSTIN) is None
    assert pan_problem("ABCDE1234F", None) is None
    # A UIN is not built on a PAN, so it says nothing about the PAN.
    assert pan_problem("ABCDE1234F", "2917UNO00001UNO") is None
    assert pan_problem(None, None) == PAN_NOT_HELD
    assert pan_problem("  ", None) == PAN_NOT_HELD
    assert pan_problem(None, GSTIN) == PAN_NOT_FILLED
    assert pan_problem("ABCD1234F", None) == PAN_MALFORMED
    assert pan_problem("ZZZZZ9999Z", GSTIN) == PAN_MISMATCH


def _session() -> Session:
    """Create an in-memory store with every table."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _firm(session: Session) -> Firm:
    """Add one firm."""
    firm = Firm(
        name="Acme Firm",
        code="ACME",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(firm)
    session.commit()
    return firm


def test_the_customer_report_lists_only_customers_needing_attention() -> None:
    """Sound, deleted and other firms' customers stay off the list."""
    session = _session()
    firm = _firm(session)
    other = Firm(
        name="Other",
        code="OTHR",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(other)
    session.commit()
    actor = uuid4()

    def customer(
        code: str,
        pan: str | None,
        gstin: str | None,
        *,
        firm_id: object = firm.id,
        deleted: bool = False,
    ) -> None:
        session.add(
            Customer(
                firm_id=firm_id,
                code=code,
                customer_type="BUSINESS",
                name=f"Customer {code}",
                display_name=f"Customer {code}",
                currency_code="INR",
                status="ACTIVE",
                pan_number=pan,
                gst_number=gstin,
                is_deleted=deleted,
                created_by=actor,
                updated_by=actor,
            )
        )

    customer("C1", "ABCDE1234F", GSTIN)
    customer("C2", None, None)
    customer("C3", None, GSTIN)
    customer("C4", "ZZZZZ9999Z", GSTIN)
    customer("C5", None, None, deleted=True)
    customer("C6", None, None, firm_id=other.id)
    session.commit()

    rows = customer_pan_check(
        scope=SimpleNamespace(firm_id=firm.id),  # type: ignore[arg-type]
        db=session,
    ).data

    assert rows is not None
    assert [(row.code, row.problem, row.pan_in_gstin) for row in rows] == [
        ("C2", PAN_NOT_HELD, None),
        ("C3", PAN_NOT_FILLED, "ABCDE1234F"),
        ("C4", PAN_MISMATCH, "ABCDE1234F"),
    ]
    assert rows[0].name == "Customer C2"


def test_the_supplier_report_lists_only_suppliers_needing_attention() -> None:
    """A supplier with no PAN, a malformed one and a mismatched one."""
    session = _session()
    firm = _firm(session)
    actor = uuid4()
    for code, pan, gstin in (
        ("V1", "ABCDE1234F", GSTIN),
        ("V2", None, None),
        ("V3", "BAD", None),
        ("V4", "ZZZZZ9999Z", "27ABCDE1234F1Z3"),
    ):
        session.add(
            Vendor(
                firm_id=firm.id,
                code=code,
                name=f"Vendor {code}",
                display_name=f"Vendor {code}",
                pan=pan,
                gstin=gstin,
                created_by=actor,
                updated_by=actor,
            )
        )
    session.commit()

    rows = vendor_pan_check(
        scope=SimpleNamespace(firm_id=firm.id),  # type: ignore[arg-type]
        db=session,
    ).data

    assert rows is not None
    assert [(row.code, row.problem) for row in rows] == [
        ("V2", PAN_NOT_HELD),
        ("V3", PAN_MALFORMED),
        ("V4", PAN_MISMATCH),
    ]


def test_the_reports_need_a_firm() -> None:
    """Without X-Firm-ID there is no firm's parties to read."""
    session = _session()
    for report in (customer_pan_check, vendor_pan_check):
        with pytest.raises(ValidationError, match="X-Firm-ID"):
            report(
                scope=SimpleNamespace(firm_id=None),  # type: ignore[arg-type]
                db=session,
            )

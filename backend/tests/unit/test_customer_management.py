"""Customer validation, service, tenancy, audit, and API tests."""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi import Response
from pydantic import ValidationError as SchemaValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.audit.models import AuditLog
from app.common.scope import (
    ResolvedFirmScope,
    optional_firm_scope,
    required_firm_scope,
)
from app.core.concurrency import parse_if_match
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import (
    AuthorizationError,
    BusinessRuleError,
    ConflictError,
    ResourceNotFoundError,
    ValidationError,
)
from app.core.security.authorization import Principal, require_permission
from app.core.security.jwt import TokenClaims
from app.customers.api.router import (
    create_customer,
    customer_credit_status,
    delete_customer,
    get_credit_settings,
    get_customer,
    list_customers,
    restore_customer,
    update_credit_settings,
    update_customer,
)
from app.customers.models import (
    CreditControlSettings,
    Customer,
    CustomerAddress,
    CustomerContact,
    CustomerReceivableTransaction,
)
from app.customers.schemas import (
    CreditControlSettingsWrite,
    CreditEnforcement,
    CreditStatus,
    CustomerCreate,
    CustomerUpdate,
)
from app.customers.schemas.customer import (
    CustomerListFilters,
    CustomerReceivableTransactionCreate,
    CustomerReceivableTransactionType,
)
from app.customers.services import CreditControlService, CustomerService
from app.customers.services.credit_control import DEFAULT_SETTINGS
from app.finance.models import JournalEntry
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from app.identity.models import UserFirm


def _firm_scope(
    principal: Principal, session: Session, firm_id: UUID | None
) -> ResolvedFirmScope:
    """Resolve firm scope exactly as a request does, through the shared helper.

    Routers no longer carry a private resolver; membership is validated once in
    ``app.common.scope`` against the platform store.
    """
    return required_firm_scope(
        optional_firm_scope(principal=principal, db=session, x_firm_id=firm_id)
    )


def _session_factory() -> sessionmaker[Session]:
    """Create one shared in-memory database for API and service tests."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _firm(session: Session, code: str) -> Firm:
    firm = Firm(
        name=f"{code} Firm",
        code=code,
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(firm)
    session.commit()
    # A customer here opens with a balance, and an opening balance is money
    # owed: it posts to the receivable against opening balance equity, so the
    # firm needs its chart of accounts and an open period the way a real one
    # would before anybody starts keying customers in.
    seed_finance_setup(
        session,
        firm_id=firm.id,
        year_starts_on=date(2026, 4, 1),
        actor_id=uuid4(),
    )
    session.commit()
    return firm


def _customer_data(code: str = "CUST-001") -> CustomerCreate:
    return CustomerCreate.model_validate(
        {
            "code": code,
            "customer_type": "BUSINESS",
            "name": "Acme Customer",
            "gst_number": "GST-001",
            "pan_number": "PAN-001",
            "email": "BILLING@ACME.TEST",
            "phone": "+91 9876543210",
            "credit_limit": "25000.00",
            "opening_balance": "-150.00",
            "payment_terms_days": 30,
            "currency_code": "inr",
            "status": "ACTIVE",
            "addresses": [
                {
                    "address_type": "BILLING",
                    "address_line1": "1 Main Street",
                    "city": "Chennai",
                    "state": "Tamil Nadu",
                    "country": "in",
                    "postal_code": "600001",
                    "is_default_billing": True,
                }
            ],
            "contacts": [
                {
                    "name": "Accounts",
                    "email": "accounts@acme.test",
                    "mobile": "+919876543211",
                    "is_primary": True,
                }
            ],
        }
    )


def _principal(user_id: UUID, permissions: set[str]) -> Principal:
    return Principal(
        subject=user_id,
        roles=frozenset(),
        permissions=frozenset(permissions),
        claims=TokenClaims(
            sub=str(user_id),
            type=TokenType.ACCESS,
            iat=1,
            exp=4_102_444_800,
            permissions=sorted(permissions),
        ),
    )


def test_customer_schema_normalizes_and_validates_nested_defaults() -> None:
    """Normalize business fields and reject ambiguous child defaults."""
    data = _customer_data()

    assert data.code == "CUST-001"
    assert data.email == "billing@acme.test"
    assert data.phone == "+919876543210"
    assert data.currency_code == "INR"
    assert data.opening_balance == Decimal("-150.00")

    invalid = data.model_dump(mode="json")
    invalid["addresses"].append(
        {
            **invalid["addresses"][0],
            "id": None,
            "address_line1": "Second address",
        }
    )
    with pytest.raises(ValueError, match="default billing"):
        CustomerCreate.model_validate(invalid)


def test_customer_service_enforces_firm_uniqueness_scope_and_audit() -> None:
    """Keep identifiers firm-local while auditing each lifecycle mutation."""
    factory = _session_factory()
    session = factory()
    first_firm = _firm(session, "FIRST")
    second_firm = _firm(session, "SECOND")
    actor_id = uuid4()
    service = CustomerService(session)

    customer = service.create(
        _customer_data(), firm_id=first_firm.id, actor_id=actor_id
    )
    assert customer.display_name == "Acme Customer"
    assert customer.addresses[0].city == "Chennai"
    assert customer.contacts[0].is_primary is True

    with pytest.raises(ConflictError):
        service.create(_customer_data(), firm_id=first_firm.id, actor_id=actor_id)

    other_firm_customer = service.create(
        _customer_data(), firm_id=second_firm.id, actor_id=actor_id
    )
    assert other_firm_customer.firm_id == second_firm.id
    with pytest.raises(ResourceNotFoundError, match="Customer not found"):
        service.get(customer.id, firm_scope=second_firm.id)

    update = CustomerUpdate.model_validate(
        {
            **_customer_data().model_dump(mode="json"),
            "name": "Acme Customer Updated",
            "gst_number": "GST-UPDATED",
            "pan_number": "PAN-UPDATED",
        }
    )
    service.update(
        customer.id,
        update,
        firm_scope=first_firm.id,
        actor_id=actor_id,
    )
    service.delete(customer.id, firm_scope=first_firm.id, actor_id=actor_id)
    restored = service.restore(customer.id, firm_scope=first_firm.id, actor_id=actor_id)

    assert restored.is_deleted is False
    assert [
        audit.action
        for audit in session.scalars(
            select(AuditLog)
            .where(AuditLog.entity_id == customer.id)
            .order_by(AuditLog.created_at)
        )
    ] == [
        "customer.created",
        "customer.updated",
        "customer.deleted",
        "customer.restored",
    ]


def test_customer_search_filters_summary_and_soft_delete() -> None:
    """Search nested cities, filter statuses, and exclude deleted rows."""
    session = _session_factory()()
    firm = _firm(session, "SEARCH")
    actor_id = uuid4()
    service = CustomerService(session)
    customer = service.create(_customer_data(), firm_id=firm.id, actor_id=actor_id)

    rows, total = service.list_customers(
        firm_scope=firm.id,
        filters=CustomerListFilters(city="Chennai", status="ACTIVE"),
        page=1,
        page_size=20,
        search="Chennai",
        sort_by="code",
        descending=False,
    )
    assert total == 1
    assert rows[0].id == customer.id
    assert service.summary(
        firm_scope=firm.id, filters=CustomerListFilters()
    ).total_credit_limit == Decimal("25000.00")

    service.delete(customer.id, firm_scope=firm.id, actor_id=actor_id)
    _, visible_total = service.list_customers(
        firm_scope=firm.id,
        filters=CustomerListFilters(),
        page=1,
        page_size=20,
        search=None,
        sort_by="created_at",
        descending=True,
    )
    _, all_total = service.list_customers(
        firm_scope=firm.id,
        filters=CustomerListFilters(include_deleted=True),
        page=1,
        page_size=20,
        search=None,
        sort_by="created_at",
        descending=True,
    )
    assert visible_total == 0
    assert all_total == 1


def test_customer_receivable_transactions_track_outstanding_and_advance() -> None:
    """Track positive outstanding and unapplied advance from customer transactions."""
    session = _session_factory()()
    firm = _firm(session, "AR")
    actor_id = uuid4()
    service = CustomerService(session)
    payload = _customer_data("CUST-AR-001").model_copy(
        update={"opening_balance": Decimal("0.00")}
    )
    customer = service.create(payload, firm_id=firm.id, actor_id=actor_id)

    tx = service.post_receivable_transaction(
        customer.id,
        CustomerReceivableTransactionCreate(
            transaction_type=CustomerReceivableTransactionType.INVOICE,
            transaction_date=date(2026, 8, 8),
            amount=Decimal("1000.00"),
            reference_type="TEST",
            reference_number="INV-001",
        ),
        firm_scope=firm.id,
        actor_id=actor_id,
    )
    assert tx.outstanding_after == Decimal("1000.00")

    tx = service.post_receivable_transaction(
        customer.id,
        CustomerReceivableTransactionCreate(
            transaction_type=CustomerReceivableTransactionType.RECEIPT,
            transaction_date=date(2026, 8, 8),
            amount=Decimal("1200.00"),
            reference_type="TEST",
            reference_number="RCT-001",
        ),
        firm_scope=firm.id,
        actor_id=actor_id,
    )
    assert tx.outstanding_after == Decimal("0.00")
    assert tx.advance_after == Decimal("200.00")

    summary = service.receivable_summary(customer.id, firm_scope=firm.id)
    assert summary.outstanding == Decimal("0.00")
    assert summary.unapplied_advance == Decimal("200.00")


def test_nested_customer_removal_is_soft_deleted_and_audit_is_immutable() -> None:
    """Preserve removed child rows and reject audit mutation or deletion."""
    session = _session_factory()()
    firm = _firm(session, "CHILDREN")
    actor_id = uuid4()
    service = CustomerService(session)
    customer = service.create(_customer_data(), firm_id=firm.id, actor_id=actor_id)
    address_id = customer.addresses[0].id
    contact_id = customer.contacts[0].id
    update_data = _customer_data().model_dump(mode="json")
    update_data["addresses"] = []
    update_data["contacts"] = []

    updated = service.update(
        customer.id,
        CustomerUpdate.model_validate(update_data),
        firm_scope=firm.id,
        actor_id=actor_id,
    )

    assert updated.addresses == []
    assert updated.contacts == []
    assert session.get(CustomerAddress, address_id).is_deleted is True
    assert session.get(CustomerContact, contact_id).is_deleted is True
    audit = session.scalar(select(AuditLog).where(AuditLog.entity_id == customer.id))
    assert audit is not None
    audit.action = "tampered"
    with pytest.raises(BusinessRuleError, match="append-only"):
        session.commit()
    session.rollback()
    session.delete(audit)
    with pytest.raises(BusinessRuleError, match="append-only"):
        session.commit()


def test_customer_api_enforces_membership_permissions_and_restore() -> None:
    """Exercise API envelopes, permission checks, and active-firm scope."""
    factory = _session_factory()
    setup = factory()
    firm = _firm(setup, "API")
    other_firm = _firm(setup, "OTHER")
    user_id = uuid4()
    other_firm.is_active = False
    setup.add_all(
        [
            UserFirm(user_id=user_id, firm_id=firm.id, is_active=True),
            UserFirm(user_id=user_id, firm_id=other_firm.id, is_active=True),
        ]
    )
    setup.commit()
    setup.close()

    permissions = {
        "CUSTOMER_CREATE",
        "CUSTOMER_VIEW",
        "CUSTOMER_UPDATE",
        "CUSTOMER_DELETE",
        "CUSTOMER_RESTORE",
        "CUSTOMER_EXPORT",
    }
    principal = _principal(user_id, permissions)
    session = factory()
    scope = _firm_scope(principal, session, firm.id)
    created = create_customer(_customer_data(), scope, session)
    customer_id = created.data.id

    listed = list_customers(
        scope=scope,
        page=1,
        page_size=20,
        search="Chennai",
        sort_by="created_at",
        sort_direction="desc",
        status_value=None,
        customer_type=None,
        firm_id=None,
        city="Chennai",
        state_value=None,
        created_from=None,
        created_to=None,
        include_deleted=False,
        db=session,
    )
    assert listed.pagination.total_records == 1

    with pytest.raises(AuthorizationError):
        _firm_scope(principal, session, other_firm.id)

    delete_customer(customer_id, scope, session)
    restored = restore_customer(customer_id, scope, session)
    assert restored.data.is_deleted is False

    view_only = _principal(user_id, {"CUSTOMER_VIEW"})
    with pytest.raises(AuthorizationError):
        require_permission("CUSTOMER_CREATE")(view_only)

    assert session.query(Customer).count() == 1


def test_a_reader_is_told_the_version_it_must_send_back() -> None:
    """The precondition is only usable if the version is published somewhere.

    ``If-Match`` was accepted by five routers from the day it was written while
    no response carried the version at all, so the only value a client could
    honestly send was ``*`` -- which means no precondition. A customer update
    replaces the whole address and contact collections, so the loser of a
    concurrent edit loses every row they entered; this is the endpoint where
    that matters most.
    """
    factory = _session_factory()
    setup = factory()
    firm = _firm(setup, "ETAG")
    user_id = uuid4()
    setup.add(UserFirm(user_id=user_id, firm_id=firm.id, is_active=True))
    setup.commit()
    setup.close()

    session = factory()
    principal = _principal(
        user_id, {"CUSTOMER_CREATE", "CUSTOMER_VIEW", "CUSTOMER_UPDATE"}
    )
    scope = _firm_scope(principal, session, firm.id)
    created = create_customer(_customer_data(), scope, session)
    customer_id = created.data.id

    read = Response()
    get_customer(customer_id, scope, read, False, session)
    stale = parse_if_match(read.headers["ETag"])
    assert stale is not None, "the ETag must carry a version, not be absent or *"

    revised = CustomerUpdate.model_validate(
        {**_customer_data().model_dump(mode="json"), "name": "Renamed Once"}
    )
    first = Response()
    update_customer(customer_id, revised, scope, first, session, stale)
    fresh = parse_if_match(first.headers["ETag"])
    assert fresh is not None and fresh > stale, "an update must advance the version"

    # The version read before that update is now stale, and saying so is the
    # whole point: without the ETag the client could not have known either one.
    with pytest.raises(ConflictError):
        update_customer(customer_id, revised, scope, Response(), session, stale)

    again = CustomerUpdate.model_validate(
        {**_customer_data().model_dump(mode="json"), "name": "Renamed Twice"}
    )
    accepted = Response()
    result = update_customer(customer_id, again, scope, accepted, session, fresh)
    assert result.data.name == "Renamed Twice"
    assert parse_if_match(accepted.headers["ETag"]) == fresh + 1


def _customer_with_credit(
    session: Session,
    firm_id: UUID,
    *,
    limit: str,
    outstanding: str = "0.00",
    advance: str = "0.00",
) -> Customer:
    """Create a customer sitting at a known point against a known limit."""
    row = Customer(
        firm_id=firm_id,
        code=f"CUST-CR-{limit}-{outstanding}",
        customer_type="BUSINESS",
        name="Credit Customer",
        display_name="Credit Customer",
        currency_code="INR",
        status="ACTIVE",
        credit_limit=Decimal(limit),
        current_outstanding=Decimal(outstanding),
        unapplied_advance_balance=Decimal(advance),
    )
    session.add(row)
    session.commit()
    return row


def test_a_customer_well_inside_the_limit_passes_quietly() -> None:
    """No warning below the threshold, so the warning means something."""
    session = _session_factory()()
    firm = _firm(session, "CR1")
    customer = _customer_with_credit(session, firm.id, limit="1000", outstanding="100")

    assessment = CreditControlService(session).assess(
        customer, additional_amount=Decimal("100")
    )

    assert assessment.status is CreditStatus.OK
    assert assessment.message is None
    assert assessment.exposure == Decimal("200.0000")
    assert assessment.available == Decimal("800.0000")


def test_the_document_being_saved_counts_toward_the_limit() -> None:
    """The point is to catch the breach before it happens.

    A customer at 700 of 1000 is fine until you add the 200 order in front of
    you, which takes them to 90%.
    """
    session = _session_factory()()
    firm = _firm(session, "CR2")
    customer = _customer_with_credit(session, firm.id, limit="1000", outstanding="700")
    service = CreditControlService(session)

    assert service.assess(customer).status is CreditStatus.OK
    warned = service.assess(customer, additional_amount=Decimal("200"))
    assert warned.status is CreditStatus.WARNING
    assert warned.used_percent == Decimal("90.0000")


def test_money_paid_in_advance_does_not_consume_the_limit() -> None:
    """An advance is money received; it cannot count against available credit."""
    session = _session_factory()()
    firm = _firm(session, "CR3")
    customer = _customer_with_credit(
        session, firm.id, limit="1000", outstanding="900", advance="500"
    )

    assessment = CreditControlService(session).assess(customer)

    assert assessment.exposure == Decimal("400.0000")
    assert assessment.status is CreditStatus.OK


def test_warning_is_the_default_and_never_blocks() -> None:
    """A firm that has configured nothing warns and keeps trading."""
    session = _session_factory()()
    firm = _firm(session, "CR4")
    customer = _customer_with_credit(session, firm.id, limit="1000", outstanding="2000")
    service = CreditControlService(session)

    assessment = service.assert_within_limit(customer)

    assert assessment.status is CreditStatus.WARNING
    assert assessment.blocks is False
    assert "200" in (assessment.message or "")


def test_a_firm_can_choose_to_block() -> None:
    """BLOCK refuses the document once the block threshold is reached."""
    session = _session_factory()()
    firm = _firm(session, "CR5")
    session.add(
        CreditControlSettings(
            firm_id=firm.id,
            enforcement=CreditEnforcement.BLOCK.value,
            warn_at_percent=Decimal("80"),
            block_at_percent=Decimal("100"),
        )
    )
    session.commit()
    customer = _customer_with_credit(session, firm.id, limit="1000", outstanding="850")
    service = CreditControlService(session)

    # Still only a warning below the block threshold.
    assert service.assert_within_limit(customer).status is CreditStatus.WARNING

    with pytest.raises(ValidationError, match="credit limit"):
        service.assert_within_limit(customer, additional_amount=Decimal("200"))


def test_a_firm_can_switch_credit_control_off() -> None:
    """OFF means silent, even for a customer far past their limit."""
    session = _session_factory()()
    firm = _firm(session, "CR6")
    session.add(
        CreditControlSettings(firm_id=firm.id, enforcement=CreditEnforcement.OFF.value)
    )
    session.commit()
    customer = _customer_with_credit(session, firm.id, limit="100", outstanding="9000")

    assessment = CreditControlService(session).assert_within_limit(customer)

    assert assessment.status is CreditStatus.OK
    assert assessment.message is None


def test_a_zero_limit_means_unset_not_no_credit() -> None:
    """Every customer starts at a limit of zero.

    Reading that as "no credit allowed" would have blocked or warned on every
    customer in every firm the moment this shipped.
    """
    session = _session_factory()()
    firm = _firm(session, "CR7")
    session.add(
        CreditControlSettings(
            firm_id=firm.id, enforcement=CreditEnforcement.BLOCK.value
        )
    )
    session.commit()
    customer = _customer_with_credit(session, firm.id, limit="0", outstanding="5000")

    assessment = CreditControlService(session).assert_within_limit(
        customer, additional_amount=Decimal("1000")
    )

    assert assessment.status is CreditStatus.OK


def _credit_endpoint_setup(
    code: str, permissions: set[str]
) -> tuple[Session, Firm, ResolvedFirmScope]:
    """Build a firm, a member, and the scope a request would resolve."""
    session = _session_factory()()
    firm = _firm(session, code)
    user_id = uuid4()
    session.add(UserFirm(user_id=user_id, firm_id=firm.id, is_active=True))
    session.commit()
    scope = _firm_scope(_principal(user_id, permissions), session, firm.id)
    return session, firm, scope


def test_credit_status_endpoint_answers_before_the_document_is_saved() -> None:
    """A client can ask "would this order breach?" rather than find out after."""
    session, firm, scope = _credit_endpoint_setup("CRE1", {"CUSTOMER_VIEW"})
    customer = _customer_with_credit(session, firm.id, limit="1000", outstanding="700")

    quiet = customer_credit_status(customer.id, scope, Decimal("0"), session).data
    loaded = customer_credit_status(customer.id, scope, Decimal("200"), session).data

    assert quiet.status is CreditStatus.OK
    assert loaded.status is CreditStatus.WARNING
    assert loaded.exposure == Decimal("900.0000")
    assert loaded.available == Decimal("100.0000")
    assert loaded.customer_name == customer.display_name
    # The thresholds ride along so a form can explain the warning without a
    # second call for the policy.
    assert loaded.warn_at_percent == Decimal("80")
    assert loaded.block_at_percent == Decimal("100")
    assert loaded.would_block is False


def test_credit_status_reports_the_block_without_raising() -> None:
    """Asking is not saving: the query reports a breach, it does not refuse."""
    session, firm, scope = _credit_endpoint_setup("CRE2", {"CUSTOMER_VIEW"})
    session.add(
        CreditControlSettings(
            firm_id=firm.id, enforcement=CreditEnforcement.BLOCK.value
        )
    )
    session.commit()
    customer = _customer_with_credit(session, firm.id, limit="1000", outstanding="900")

    report = customer_credit_status(customer.id, scope, Decimal("200"), session).data

    assert report.status is CreditStatus.BREACH
    assert report.would_block is True
    assert report.message is not None


def test_credit_status_refuses_a_customer_outside_the_firm() -> None:
    """Credit position is customer data and obeys the same firm boundary."""
    session, _, scope = _credit_endpoint_setup("CRE3", {"CUSTOMER_VIEW"})
    other = _firm(session, "CRE3X")
    stranger = _customer_with_credit(session, other.id, limit="1000", outstanding="0")

    with pytest.raises(ResourceNotFoundError):
        customer_credit_status(stranger.id, scope, Decimal("0"), session)


def test_credit_settings_report_the_default_until_a_firm_chooses_one() -> None:
    """An unconfigured firm still warns, and is told the choice is not its own."""
    session, firm, scope = _credit_endpoint_setup(
        "CRE4", {"CUSTOMER_VIEW", "CUSTOMER_MANAGE_SETTINGS"}
    )

    before = get_credit_settings(scope, session).data
    assert before.enforcement is CreditEnforcement.WARN
    assert before.warn_at_percent == Decimal("80")
    assert before.is_configured is False

    after = update_credit_settings(
        CreditControlSettingsWrite(
            enforcement=CreditEnforcement.BLOCK,
            warn_at_percent=Decimal("70"),
            block_at_percent=Decimal("110"),
        ),
        scope,
        session,
    ).data

    assert after.enforcement is CreditEnforcement.BLOCK
    assert after.is_configured is True
    assert get_credit_settings(scope, session).data.block_at_percent == Decimal("110")
    # The shared fallback must survive a firm writing its own policy.
    assert DEFAULT_SETTINGS.enforcement == CreditEnforcement.WARN.value
    assert DEFAULT_SETTINGS.block_at_percent == Decimal("100")
    stored = session.scalar(
        select(CreditControlSettings).where(CreditControlSettings.firm_id == firm.id)
    )
    assert stored is not None


def test_updating_credit_settings_twice_keeps_one_row_and_audits_the_change() -> None:
    """The policy is a financial control, so every change leaves a trail."""
    session, firm, scope = _credit_endpoint_setup(
        "CRE5", {"CUSTOMER_MANAGE_SETTINGS", "CUSTOMER_VIEW"}
    )
    write = CreditControlSettingsWrite(
        enforcement=CreditEnforcement.WARN,
        warn_at_percent=Decimal("60"),
        block_at_percent=Decimal("100"),
    )
    update_credit_settings(write, scope, session)
    update_credit_settings(
        CreditControlSettingsWrite(
            enforcement=CreditEnforcement.OFF,
            warn_at_percent=Decimal("90"),
            block_at_percent=Decimal("100"),
        ),
        scope,
        session,
    )

    rows = session.scalars(
        select(CreditControlSettings).where(CreditControlSettings.firm_id == firm.id)
    ).all()
    assert len(rows) == 1

    actions = session.scalars(
        select(AuditLog.action).where(AuditLog.entity_type == "CreditControlSettings")
    ).all()
    assert list(actions) == ["CREATE", "UPDATE"]


def test_a_warning_threshold_above_the_block_is_rejected() -> None:
    """A warning that can never fire is a policy the firm would misread."""
    with pytest.raises(SchemaValidationError):
        CreditControlSettingsWrite(
            enforcement=CreditEnforcement.BLOCK,
            warn_at_percent=Decimal("120"),
            block_at_percent=Decimal("100"),
        )


def test_an_opening_balance_reaches_the_ledger() -> None:
    """A day-one receivable is money owed, and it has to be booked as such.

    `verify_sample_data.py` found the gap: customers owing 885,000.00 against a
    receivable control account of zero, because this wrote the balance and the
    receivable transaction and stopped there.
    """
    session_factory = _session_factory()
    session = session_factory()
    firm = _firm(session, "OB-FIRM")
    service = CustomerService(session)
    actor_id = uuid4()

    customer = service.create(
        _customer_data("CUST-OB"),
        firm_id=firm.id,
        actor_id=actor_id,
    )

    # The customer data opens 150.00 in credit, so the firm owes them: the
    # legs swap and equity is debited.
    assert customer.unapplied_advance_balance == Decimal("150.00")
    transaction = session.scalar(
        select(CustomerReceivableTransaction).where(
            CustomerReceivableTransaction.customer_id == customer.id
        )
    )
    assert transaction is not None
    assert transaction.journal_entry_id is not None
    entry = session.get(JournalEntry, transaction.journal_entry_id)
    assert entry is not None
    assert entry.reference_number == "CUST-OB-OB"
    assert entry.total_debit == Decimal("150.00")
    assert entry.total_credit == Decimal("150.00")


def test_revising_an_opening_balance_mirrors_the_one_it_replaces() -> None:
    """The old entry asserted a figure the customer no longer carries."""
    session_factory = _session_factory()
    session = session_factory()
    firm = _firm(session, "OB-FIRM2")
    service = CustomerService(session)
    actor_id = uuid4()
    customer = service.create(
        _customer_data("CUST-OB2"), firm_id=firm.id, actor_id=actor_id
    )

    service.update(
        customer.id,
        _customer_data("CUST-OB2").model_copy(
            update={"opening_balance": Decimal("400.00")}
        ),
        firm_scope=firm.id,
        actor_id=actor_id,
    )

    references = sorted(
        row
        for row in session.scalars(
            select(JournalEntry.reference_number).where(JournalEntry.firm_id == firm.id)
        ).all()
    )
    # The original, its mirror, and the revised figure -- each on its own
    # reference, because a firm's journal references are unique.
    assert references == ["CUST-OB2-OB", "CUST-OB2-OB-REV", "CUST-OB2-OB2"]
    session.refresh(customer)
    assert customer.current_outstanding == Decimal("400.00")


def test_a_firm_with_no_chart_of_accounts_says_so() -> None:
    """Refused, rather than recorded somewhere the ledger cannot see."""
    session_factory = _session_factory()
    session = session_factory()
    firm = Firm(
        name="Bare Firm",
        code="BARE",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(firm)
    session.commit()
    service = CustomerService(session)

    with pytest.raises(ValidationError, match="chart of accounts"):
        service.create(_customer_data("CUST-BARE"), firm_id=firm.id, actor_id=uuid4())
    # The customer was staged before the posting ran, and a request that gets
    # this error rolls back with it.
    session.rollback()

    # The customer itself is fine -- it is the balance that cannot be booked.
    without = service.create(
        _customer_data("CUST-BARE").model_copy(
            update={"opening_balance": Decimal("0.00")}
        ),
        firm_id=firm.id,
        actor_id=uuid4(),
    )
    assert without.code == "CUST-BARE"


def test_deleting_a_customer_takes_its_opening_balance_with_it() -> None:
    """Found by driving the API: two probe customers left 50,000 in the ledger.

    The balance leaves the customer's account on delete, so an entry left
    standing puts the receivable control account above what anybody is
    recorded as owing -- the same drift, in the other direction.
    """
    session_factory = _session_factory()
    session = session_factory()
    firm = _firm(session, "OB-FIRM3")
    service = CustomerService(session)
    actor_id = uuid4()
    customer = service.create(
        _customer_data("CUST-OB3").model_copy(
            update={"opening_balance": Decimal("25000.00")}
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    posted = session.scalar(
        select(CustomerReceivableTransaction.journal_entry_id).where(
            CustomerReceivableTransaction.customer_id == customer.id
        )
    )
    assert posted is not None

    service.delete(customer.id, firm_scope=firm.id, actor_id=actor_id)

    references = sorted(
        row
        for row in session.scalars(
            select(JournalEntry.reference_number).where(JournalEntry.firm_id == firm.id)
        ).all()
    )
    assert references == ["CUST-OB3-OB", "CUST-OB3-OB-REV"]
    # Both legs still exist, and they cancel: the ledger records that the
    # balance was claimed and then withdrawn, rather than pretending neither.
    entries = list(
        session.scalars(
            select(JournalEntry).where(JournalEntry.firm_id == firm.id)
        ).all()
    )
    assert sum(entry.total_debit for entry in entries) == Decimal("50000.00")
    assert sum(entry.total_credit for entry in entries) == Decimal("50000.00")

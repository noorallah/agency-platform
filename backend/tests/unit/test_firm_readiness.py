"""A firm's readiness, and the action that opens its books.

Until 2026-09-08 a firm created in the product could not be finished in the
product: its chart of accounts, financial year and control-account mappings
were written only by `scripts/seed_finance_defaults.py`, and nothing said they
were missing until the first invoice approval was refused. These pin the two
halves -- the readiness read that says what a firm still needs, and the
open-books action that closes the one step with no other screen.
"""

# ruff: noqa: D101,D102,D103

from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.models import Branch, Warehouse
from app.common.audit.models import AuditLog
from app.core.database.base import Base
from app.core.exceptions import BusinessRuleError
from app.core.tenancy import DeploymentMode
from app.finance.models import AccountingPeriod, FinancialYear, LedgerAccount
from app.finance.services.control_accounts import ControlAccountService
from app.finance.services.opening_setup import CHART
from app.firms.models import Firm, FirmStorageMapping
from app.firms.services.readiness import (
    ALL_PURPOSES,
    FirmReadinessService,
    ReadinessStatus,
    current_year_start,
    storage_is_ready,
)
from app.identity.models import User, UserFirm

_ACTOR = UUID("00000000-0000-0000-0000-0000000000a1")


def _session() -> Session:
    """One SQLite schema holding every table, so both stores are one session."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _firm(
    session: Session,
    *,
    mode: DeploymentMode = DeploymentMode.SHARED,
    provisioned: bool = False,
    year_start: date = date(2026, 4, 1),
) -> Firm:
    firm = Firm(
        name="Acme Distributors",
        code="ACME",
        country="IN",
        currency_code="INR",
        financial_year_start=year_start,
    )
    session.add(firm)
    session.flush()
    session.add(
        FirmStorageMapping(
            firm_id=firm.id,
            deployment_mode=mode.value,
            database_type="postgresql",
            database_name=None if mode is DeploymentMode.SHARED else "erp_acme",
            schema_name=None if mode is DeploymentMode.SHARED else "firm_acme",
            provisioned_at=datetime(2026, 1, 1, tzinfo=UTC) if provisioned else None,
        )
    )
    session.commit()
    session.expire_all()
    return session.get(Firm, firm.id) or firm


def _step(service_result: object, key: str) -> object:
    steps = getattr(service_result, "steps")  # noqa: B009
    return next(step for step in steps if step.key == key)


class TestReadiness:
    def test_a_new_shared_firm_has_storage_and_nothing_else(self) -> None:
        session = _session()
        firm = _firm(session)

        readiness = FirmReadinessService(session).readiness(firm, session)

        by_key = {step.key: step for step in readiness.steps}
        assert list(by_key) == [
            "storage",
            "business_profile",
            "books",
            "tax",
            "geography",
            "branches",
            "members",
        ]
        assert by_key["storage"].status is ReadinessStatus.DONE
        assert by_key["books"].status is ReadinessStatus.MISSING
        assert "No chart of accounts" in by_key["books"].detail
        assert by_key["tax"].status is ReadinessStatus.MISSING
        assert by_key["members"].status is ReadinessStatus.MISSING
        # Only storage and books are required: a firm with no tax profiles
        # prices every line at no tax, which is wrong but not a refusal.
        assert {key for key, step in by_key.items() if step.required} == {
            "storage",
            "books",
        }
        assert readiness.can_post is False
        assert readiness.ready is False

    def test_an_unprovisioned_dedicated_firm_cannot_be_read(self) -> None:
        session = _session()
        firm = _firm(session, mode=DeploymentMode.SCHEMA)
        assert storage_is_ready(firm) is False

        # The router passes None for the store it cannot open.
        readiness = FirmReadinessService(session).readiness(firm, None)

        by_key = {step.key: step for step in readiness.steps}
        assert by_key["storage"].status is ReadinessStatus.MISSING
        assert "has not been provisioned" in by_key["storage"].detail
        # Every store-side step is blocked, never reported as merely missing:
        # nothing was counted, so nothing can be said to be absent.
        for key in ("business_profile", "books", "tax", "geography", "branches"):
            assert by_key[key].status is ReadinessStatus.BLOCKED, key
        # The membership count lives on the platform side and is still read.
        assert by_key["members"].status is ReadinessStatus.MISSING
        assert readiness.storage_provisioned is False

    def test_a_provisioned_dedicated_firm_is_read_like_a_shared_one(self) -> None:
        session = _session()
        firm = _firm(session, mode=DeploymentMode.DATABASE, provisioned=True)
        assert storage_is_ready(firm) is True

        readiness = FirmReadinessService(session).readiness(firm, session)

        assert _step(readiness, "storage").status is ReadinessStatus.DONE
        assert "DATABASE storage provisioned" in _step(readiness, "storage").detail
        assert _step(readiness, "books").status is ReadinessStatus.MISSING

    def test_members_branches_and_warehouses_are_counted(self) -> None:
        session = _session()
        firm = _firm(session)
        user = User(
            email="asha@example.com",
            full_name="Asha",
            password_hash="x",
            is_active=True,
        )
        session.add(user)
        session.flush()
        session.add(
            UserFirm(user_id=user.id, firm_id=firm.id, is_active=True, is_primary=True)
        )
        session.add(
            Branch(firm_id=firm.id, code="HO", name="Head office", display_name="HO")
        )
        session.commit()

        readiness = FirmReadinessService(session).readiness(firm, session)

        assert _step(readiness, "members").status is ReadinessStatus.DONE
        assert "1 member" in _step(readiness, "members").detail
        # A branch without a warehouse is not enough: stock needs somewhere
        # to be.
        branches = _step(readiness, "branches")
        assert branches.status is ReadinessStatus.MISSING
        assert "1 branch, 0 warehouses" in branches.detail

        branch = session.scalar(select(Branch).where(Branch.firm_id == firm.id))
        assert branch is not None
        session.add(
            Warehouse(
                firm_id=firm.id,
                branch_id=branch.id,
                code="W1",
                name="Main",
                display_name="Main",
            )
        )
        session.commit()
        readiness = FirmReadinessService(session).readiness(firm, session)
        assert _step(readiness, "branches").status is ReadinessStatus.DONE


class TestOpenBooks:
    def test_opens_the_chart_the_year_and_every_mapping(self) -> None:
        session = _session()
        firm = _firm(session)
        service = FirmReadinessService(session)

        created, starts_on = service.open_books(
            firm, session, _ACTOR, year_starts_on=date(2026, 4, 1)
        )

        assert starts_on == date(2026, 4, 1)
        assert created["accounts"] == len(CHART)
        assert created["periods"] == 12
        assert created["mappings"] == len(
            ALL_PURPOSES
        ), "the default chart maps every purpose, or the firm still cannot post"
        assert created["types"] == 2
        assert ControlAccountService(session).missing(firm.id, ALL_PURPOSES) == ()
        assert session.scalar(
            select(FinancialYear).where(FinancialYear.firm_id == firm.id)
        )
        assert (
            len(
                session.scalars(
                    select(AccountingPeriod).where(AccountingPeriod.firm_id == firm.id)
                ).all()
            )
            == 12
        )

    def test_readiness_then_reports_the_books_open(self) -> None:
        session = _session()
        firm = _firm(session)
        service = FirmReadinessService(session)
        # The year that contains today, so the "period open today" check
        # is judged against a calendar that actually covers it.
        today = date.today()  # noqa: DTZ011 -- a test choosing its own year
        service.open_books(
            firm,
            session,
            _ACTOR,
            year_starts_on=current_year_start(firm.financial_year_start, today),
        )

        readiness = service.readiness(firm, session)

        books = _step(readiness, "books")
        assert books.status is ReadinessStatus.DONE, books.detail
        assert f"all {len(ALL_PURPOSES)} control accounts mapped" in books.detail
        assert readiness.can_post is True
        # Recommended steps are still open, so the firm is postable but not
        # finished -- the two verdicts have to differ or one is redundant.
        assert readiness.ready is False

    def test_a_year_that_does_not_cover_today_leaves_the_books_shut(self) -> None:
        session = _session()
        firm = _firm(session)
        service = FirmReadinessService(session)
        service.open_books(firm, session, _ACTOR, year_starts_on=date(2019, 4, 1))

        books = _step(service.readiness(firm, session), "books")

        assert books.status is ReadinessStatus.MISSING
        assert "no accounting period is open today" in books.detail

    def test_is_idempotent_and_says_so(self) -> None:
        session = _session()
        firm = _firm(session)
        service = FirmReadinessService(session)
        service.open_books(firm, session, _ACTOR, year_starts_on=date(2026, 4, 1))

        again, _ = service.open_books(
            firm, session, _ACTOR, year_starts_on=date(2026, 4, 1)
        )

        assert not any(again.values()), again
        assert len(
            session.scalars(
                select(LedgerAccount).where(LedgerAccount.firm_id == firm.id)
            ).all()
        ) == len(CHART)

    def test_defaults_to_the_year_running_now(self) -> None:
        session = _session()
        # A firm founded in 2019 does not want 2019 opened.
        firm = _firm(session, year_start=date(2019, 4, 1))

        _, starts_on = FirmReadinessService(session).open_books(firm, session, _ACTOR)

        assert starts_on == current_year_start(
            date(2019, 4, 1), date.today()
        )  # noqa: DTZ011
        assert starts_on.month == 4 and starts_on.day == 1
        assert starts_on <= date.today()  # noqa: DTZ011

    def test_refuses_a_firm_whose_store_does_not_exist(self) -> None:
        session = _session()
        firm = _firm(session, mode=DeploymentMode.SCHEMA)

        with pytest.raises(BusinessRuleError, match="Provision the firm's storage"):
            FirmReadinessService(session).open_books(firm, session, _ACTOR)

    def test_is_recorded_on_the_platform_trail_with_what_it_did(self) -> None:
        session = _session()
        firm = _firm(session)

        FirmReadinessService(session).open_books(
            firm, session, _ACTOR, year_starts_on=date(2026, 4, 1)
        )

        row = session.scalar(
            select(AuditLog).where(
                AuditLog.action == "firm.books_opened", AuditLog.entity_id == firm.id
            )
        )
        assert row is not None
        assert row.actor_id == _ACTOR
        assert row.firm_id == firm.id
        assert row.after_data is not None
        assert row.after_data["year_starts_on"] == "2026-04-01"
        assert row.after_data["accounts"] == len(CHART)

        # A second call creates nothing and records nothing: a row saying
        # the books were opened with every count at zero is a lie.
        FirmReadinessService(session).open_books(
            firm, session, _ACTOR, year_starts_on=date(2026, 4, 1)
        )
        rows = session.scalars(
            select(AuditLog).where(AuditLog.action == "firm.books_opened")
        ).all()
        assert len(rows) == 1


class TestCurrentYearStart:
    def test_after_the_anniversary_it_is_this_year(self) -> None:
        assert current_year_start(date(2019, 4, 1), date(2026, 9, 8)) == date(
            2026, 4, 1
        )
        assert current_year_start(date(2019, 4, 1), date(2026, 4, 1)) == date(
            2026, 4, 1
        )

    def test_before_the_anniversary_it_is_last_year(self) -> None:
        # 31 March still belongs to the year that began the previous April.
        assert current_year_start(date(2019, 4, 1), date(2026, 3, 31)) == date(
            2025, 4, 1
        )

    def test_a_calendar_year_firm(self) -> None:
        assert current_year_start(date(2020, 1, 1), date(2026, 9, 8)) == date(
            2026, 1, 1
        )

    def test_an_anchor_in_the_future_still_opens_the_year_running_now(self) -> None:
        assert current_year_start(date(2030, 4, 1), date(2026, 9, 8)) == date(
            2026, 4, 1
        )


def test_the_two_routes_are_platform_only() -> None:
    """Pinned in `test_platform_only_routes.py`; this names the reason here."""
    from tests.unit.test_platform_only_routes import _EXPECTED

    assert ("GET", "/api/v1/firms/{firm_id}/readiness") in _EXPECTED
    assert ("POST", "/api/v1/firms/{firm_id}/open-books") in _EXPECTED


def test_open_books_route_refuses_before_opening_a_store() -> None:
    """The route checks storage itself, so it never asks the resolver.

    `firm_store_session` also refuses an unprovisioned firm, but with the
    provisioning message; this one names the step the caller is on.
    """
    from types import SimpleNamespace

    from app.firms.api.router import open_firm_books

    session = _session()
    firm = _firm(session, mode=DeploymentMode.SCHEMA)
    principal = SimpleNamespace(subject=_ACTOR)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))

    with pytest.raises(BusinessRuleError, match="Provision the firm's storage"):
        open_firm_books(firm.id, principal, request, None, session)  # type: ignore[arg-type]


class TestTaxTemplate:
    """The Indian GST template, applied from the platform side."""

    def test_gives_a_new_firm_its_whole_tax_setup_and_a_country(self) -> None:
        from app.sales.models import GeoCountry
        from app.tax.models import TaxComponent, TaxProfile, TaxRule, TaxSystem

        session = _session()
        firm = _firm(session)
        service = FirmReadinessService(session)

        created = service.apply_tax_template(firm, session, _ACTOR, template="IN_GST")

        assert created == {
            "countries": 1,
            "systems": 1,
            "components": 4,
            "profiles": 8,
            "rules": 6,
        }
        assert session.scalar(select(GeoCountry).where(GeoCountry.code == "IN"))
        assert (
            session.scalar(select(TaxSystem).where(TaxSystem.firm_id == firm.id)).code
            == "GST"
        )
        codes = {
            row.code
            for row in session.scalars(
                select(TaxComponent).where(TaxComponent.firm_id == firm.id)
            )
        }
        assert codes == {"CGST", "SGST", "IGST", "CESS"}
        profiles = {
            row.code
            for row in session.scalars(
                select(TaxProfile).where(TaxProfile.firm_id == firm.id)
            )
        }
        assert {"GST_18_LOCAL", "GST_18_INTERSTATE", "EXEMPT", "GST_0"} <= profiles
        assert len(profiles) == 8
        assert (
            len(
                session.scalars(select(TaxRule).where(TaxRule.firm_id == firm.id)).all()
            )
            == 6
        )

        # Readiness now reports tax and geography done.
        readiness = service.readiness(firm, session)
        assert _step(readiness, "tax").status is ReadinessStatus.DONE
        assert "8 profiles, 6 rules" in _step(readiness, "tax").detail
        assert _step(readiness, "geography").status is ReadinessStatus.DONE

    def test_is_idempotent_and_records_only_the_first(self) -> None:
        session = _session()
        firm = _firm(session)
        service = FirmReadinessService(session)
        service.apply_tax_template(firm, session, _ACTOR, template="IN_GST")

        again = service.apply_tax_template(firm, session, _ACTOR, template="IN_GST")

        assert not any(again.values()), again
        rows = session.scalars(
            select(AuditLog).where(AuditLog.action == "firm.tax_template_applied")
        ).all()
        assert len(rows) == 1
        assert rows[0].after_data is not None
        assert rows[0].after_data["template"] == "IN_GST"
        assert rows[0].after_data["profiles"] == 8

    def test_reuses_a_country_the_store_already_has(self) -> None:
        from app.sales.models import GeoCountry

        session = _session()
        firm = _firm(session)
        session.add(GeoCountry(code="IN", name="India", iso2="IN", iso3="IND"))
        session.commit()

        created = FirmReadinessService(session).apply_tax_template(
            firm, session, _ACTOR, template="IN_GST"
        )

        assert created["countries"] == 0
        assert created["systems"] == 1

    def test_refuses_an_unknown_template_and_an_unbuilt_store(self) -> None:
        session = _session()
        firm = _firm(session)
        with pytest.raises(BusinessRuleError, match="Unknown tax template"):
            FirmReadinessService(session).apply_tax_template(
                firm, session, _ACTOR, template="US_SALES_TAX"
            )
        other = _session()
        unbuilt = _firm(other, mode=DeploymentMode.SCHEMA)
        with pytest.raises(BusinessRuleError, match="Provision the firm's storage"):
            FirmReadinessService(other).apply_tax_template(
                unbuilt, other, _ACTOR, template="IN_GST"
            )


def test_the_tax_and_catalogue_routes_are_platform_only() -> None:
    from tests.unit.test_platform_only_routes import _EXPECTED

    assert ("POST", "/api/v1/firms/{firm_id}/apply-tax-template") in _EXPECTED
    assert ("GET", "/api/v1/business-framework/firms/{firm_id}/profiles") in _EXPECTED


class TestDefaultBranch:
    """A head office and a main warehouse, with default names."""

    def test_creates_both_and_readiness_reports_them(self) -> None:
        session = _session()
        firm = _firm(session)
        service = FirmReadinessService(session)

        created = service.create_default_branch(firm, session, _ACTOR)

        assert created == {"branch": "HO", "warehouse": "MAIN"}
        branch = session.scalar(select(Branch).where(Branch.firm_id == firm.id))
        assert branch is not None and branch.is_default is True
        warehouse = session.scalar(
            select(Warehouse).where(Warehouse.firm_id == firm.id)
        )
        assert warehouse is not None and warehouse.branch_id == branch.id
        assert _step(service.readiness(firm, session), "branches").status is (
            ReadinessStatus.DONE
        )
        rows = session.scalars(
            select(AuditLog).where(AuditLog.action == "firm.default_branch_created")
        ).all()
        assert len(rows) == 1

    def test_keeps_a_branch_the_firm_already_named(self) -> None:
        session = _session()
        firm = _firm(session)
        session.add(
            Branch(
                firm_id=firm.id,
                code="MUM",
                name="Mumbai",
                display_name="Mumbai",
                is_default=True,
            )
        )
        session.commit()

        created = FirmReadinessService(session).create_default_branch(
            firm, session, _ACTOR
        )

        assert created == {"branch": None, "warehouse": "MAIN"}
        warehouse = session.scalar(
            select(Warehouse).where(Warehouse.firm_id == firm.id)
        )
        assert warehouse is not None
        mumbai = session.scalar(select(Branch).where(Branch.code == "MUM"))
        assert mumbai is not None and warehouse.branch_id == mumbai.id

    def test_is_idempotent_and_records_only_the_first(self) -> None:
        session = _session()
        firm = _firm(session)
        service = FirmReadinessService(session)
        service.create_default_branch(firm, session, _ACTOR)

        again = service.create_default_branch(firm, session, _ACTOR)

        assert again == {"branch": None, "warehouse": None}
        rows = session.scalars(
            select(AuditLog).where(AuditLog.action == "firm.default_branch_created")
        ).all()
        assert len(rows) == 1

    def test_refuses_an_unbuilt_store(self) -> None:
        session = _session()
        firm = _firm(session, mode=DeploymentMode.SCHEMA)
        with pytest.raises(BusinessRuleError, match="Provision the firm's storage"):
            FirmReadinessService(session).create_default_branch(firm, session, _ACTOR)


def test_the_default_branch_route_is_platform_only() -> None:
    from tests.unit.test_platform_only_routes import _EXPECTED

    assert ("POST", "/api/v1/firms/{firm_id}/create-default-branch") in _EXPECTED

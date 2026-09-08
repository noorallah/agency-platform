"""Whether a firm can trade yet, and what opens its books.

Creating a firm records the intent. Everything that makes it usable -- its
storage, its business profile, its chart of accounts, its tax, its first
branch -- lives in the firm's own store and is a separate act, and until
2026-09-08 two of those acts existed only as scripts: nothing in the product
could open a firm's books, and nothing in the product said they were shut.
The refusal arrived at the first invoice approval, far from the setup step
that was skipped, and read as a broken firm rather than an unfinished one.

This is the one list of what a firm needs, read by ``GET
/api/v1/firms/{id}/readiness`` and by ``scripts/check_firm_readiness.py`` so
the screen and the shell cannot disagree about what "finished" means. A step
is **required** when the platform refuses to post without it and
**recommended** when trading merely goes wrong without it -- a firm with no
tax profiles prices every line with no tax, which is not a refusal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import cast
from uuid import UUID

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from app.branches.models import Branch, Warehouse
from app.branches.schemas import BranchCreate, WarehouseCreate
from app.branches.services import BranchWarehouseService
from app.business.models import BusinessProfile, FirmBusinessProfile
from app.common.audit.services import record_audit
from app.core.database.entity import BaseEntity
from app.core.exceptions import BusinessRuleError
from app.core.tenancy import DeploymentMode
from app.core.utils.dates import utc_now
from app.finance.models import (
    AccountingPeriod,
    FinancialYear,
    LedgerAccount,
    PeriodStatus,
)
from app.finance.services.control_accounts import (
    ControlAccountPurpose,
    ControlAccountService,
)
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from app.identity.models import UserFirm
from app.sales.models import GeoCountry
from app.tax.models import TaxProfile, TaxRule, TaxSystem
from app.tax.services.gst_template import INDIA_GST, apply_india_gst_template


class ReadinessStatus(StrEnum):
    """Where one setup step stands."""

    DONE = "DONE"
    MISSING = "MISSING"
    #: Cannot be checked yet: the firm's store does not exist, so nothing in
    #: it can be counted. Only an unprovisioned dedicated firm reports this.
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class ReadinessStep:
    """One thing a firm needs, and whether it has it."""

    key: str
    label: str
    status: ReadinessStatus
    detail: str
    required: bool


@dataclass(frozen=True, slots=True)
class FirmReadiness:
    """A firm's setup, step by step, with the verdict the steps add up to."""

    firm_id: UUID
    code: str
    name: str
    deployment_mode: DeploymentMode
    storage_provisioned: bool
    steps: list[ReadinessStep] = field(default_factory=list)

    @property
    def can_post(self) -> bool:
        """Whether every required step is done, so documents can post."""
        return all(
            step.status is ReadinessStatus.DONE for step in self.steps if step.required
        )

    @property
    def ready(self) -> bool:
        """Whether every step, required or recommended, is done."""
        return all(step.status is ReadinessStatus.DONE for step in self.steps)


#: The 24 posting purposes, in the order the enum declares them.
ALL_PURPOSES: tuple[ControlAccountPurpose, ...] = tuple(ControlAccountPurpose)


def storage_is_ready(firm: Firm) -> bool:
    """Whether the firm's store exists and can be read."""
    return (
        DeploymentMode(firm.deployment_mode) is DeploymentMode.SHARED
        or firm.provisioned_at is not None
    )


def current_year_start(anchor: date, today: date) -> date:
    """Return the start of the financial year ``today`` falls in.

    ``anchor`` is the firm's own ``financial_year_start`` -- which for a firm
    founded years ago may be years in the past, and for one recorded ahead of
    time may be in the future. Only its month and day matter: the year opened
    is the one running now, so a firm set up in September 2026 with an April
    year end gets April 2026 to March 2027, and one set up in February gets
    the year that began the previous April.
    """
    candidate = date(today.year, anchor.month, anchor.day)
    if candidate > today:
        candidate = date(today.year - 1, anchor.month, anchor.day)
    return candidate


def _count(session: Session, model: type[BaseEntity], firm_id: UUID) -> int:
    """Count a firm's live rows in one of its own tables."""
    firm_column = cast("ColumnElement[UUID]", getattr(model, "firm_id"))  # noqa: B009
    return int(
        session.scalar(
            select(func.count())
            .select_from(model)
            .where(firm_column == firm_id, model.is_deleted.is_(False))
        )
        or 0
    )


def _plural(count: int, noun: str) -> str:
    if count == 1:
        return f"1 {noun}"
    if noun.endswith("y"):
        return f"{count} {noun[:-1]}ies"
    if noun.endswith("ch"):
        return f"{count} {noun}es"
    return f"{count} {noun}s"


def store_steps(session: Session, firm_id: UUID, today: date) -> list[ReadinessStep]:
    """Read every step that lives in the firm's own store.

    Args:
        session: A session bound to the firm's store.
        firm_id: The firm.
        today: The day to judge the accounting calendar against, so a firm
            whose only year ended last March is reported as shut.

    """
    steps: list[ReadinessStep] = []

    assignment = session.scalar(
        select(BusinessProfile.code)
        .join(
            FirmBusinessProfile,
            FirmBusinessProfile.business_profile_id == BusinessProfile.id,
        )
        .where(
            FirmBusinessProfile.firm_id == firm_id,
            FirmBusinessProfile.is_deleted.is_(False),
        )
    )
    steps.append(
        ReadinessStep(
            key="business_profile",
            label="Business profile",
            status=ReadinessStatus.DONE if assignment else ReadinessStatus.MISSING,
            detail=(
                f"Assigned: {assignment}."
                if assignment
                else "None assigned. The firm runs as GENERIC, with the features "
                "and modules of no particular industry, until one is."
            ),
            required=False,
        )
    )

    accounts = _count(session, LedgerAccount, firm_id)
    years = _count(session, FinancialYear, firm_id)
    periods = _count(session, AccountingPeriod, firm_id)
    open_today = session.scalar(
        select(func.count())
        .select_from(AccountingPeriod)
        .where(
            AccountingPeriod.firm_id == firm_id,
            AccountingPeriod.is_deleted.is_(False),
            AccountingPeriod.status == PeriodStatus.OPEN.value,
            AccountingPeriod.starts_on <= today,
            AccountingPeriod.ends_on >= today,
        )
    )
    unmapped = ControlAccountService(session).missing(firm_id, ALL_PURPOSES)
    books_open = accounts > 0 and years > 0 and bool(open_today) and not unmapped
    if books_open:
        books_detail = (
            f"{_plural(accounts, 'account')}, {_plural(years, 'financial year')}, "
            f"{_plural(periods, 'period')}, all {len(ALL_PURPOSES)} control "
            "accounts mapped, and a period open today."
        )
    elif accounts == 0:
        books_detail = (
            "No chart of accounts. Nothing can post until the books are opened."
        )
    elif not open_today:
        books_detail = (
            f"{_plural(accounts, 'account')} and {_plural(years, 'financial year')}, "
            "but no accounting period is open today."
        )
    else:
        books_detail = (
            f"{len(unmapped)} of {len(ALL_PURPOSES)} control accounts unmapped: "
            + ", ".join(purpose.value for purpose in unmapped[:4])
            + ("…" if len(unmapped) > 4 else "")
            + "."
        )
    steps.append(
        ReadinessStep(
            key="books",
            label="Books",
            status=ReadinessStatus.DONE if books_open else ReadinessStatus.MISSING,
            detail=books_detail,
            required=True,
        )
    )

    systems = _count(session, TaxSystem, firm_id)
    profiles = _count(session, TaxProfile, firm_id)
    rules = _count(session, TaxRule, firm_id)
    tax_ready = profiles > 0 and rules > 0
    steps.append(
        ReadinessStep(
            key="tax",
            label="Tax",
            status=ReadinessStatus.DONE if tax_ready else ReadinessStatus.MISSING,
            detail=(
                f"{_plural(systems, 'tax system')}, {_plural(profiles, 'profile')}, "
                f"{_plural(rules, 'rule')}."
                if tax_ready
                else "No tax profiles or rules. Every line is priced with no tax "
                "until the tax framework is set up."
            ),
            required=False,
        )
    )

    countries = int(
        session.scalar(
            select(func.count())
            .select_from(GeoCountry)
            .where(GeoCountry.is_deleted.is_(False))
        )
        or 0
    )
    steps.append(
        ReadinessStep(
            key="geography",
            label="Geography",
            status=ReadinessStatus.DONE if countries else ReadinessStatus.MISSING,
            detail=(
                f"{_plural(countries, 'country')} in the store."
                if countries
                else "No country in the store. Addresses and tax rules need one."
            ),
            required=False,
        )
    )

    branches = _count(session, Branch, firm_id)
    warehouses = _count(session, Warehouse, firm_id)
    steps.append(
        ReadinessStep(
            key="branches",
            label="Branches and warehouses",
            status=(
                ReadinessStatus.DONE
                if branches and warehouses
                else ReadinessStatus.MISSING
            ),
            detail=(
                f"{_plural(branches, 'branch')}, {_plural(warehouses, 'warehouse')}."
                if branches and warehouses
                else "Stock needs a warehouse, and a warehouse needs a branch. "
                f"{_plural(branches, 'branch')}, "
                f"{_plural(warehouses, 'warehouse')} so far."
            ),
            required=False,
        )
    )
    return steps


def _blocked(key: str, label: str, *, required: bool) -> ReadinessStep:
    return ReadinessStep(
        key=key,
        label=label,
        status=ReadinessStatus.BLOCKED,
        detail="Cannot be checked until the firm's storage is provisioned.",
        required=required,
    )


#: What `store_steps` reports, for the blocked case where it cannot run.
_STORE_STEP_SHAPE: tuple[tuple[str, str, bool], ...] = (
    ("business_profile", "Business profile", False),
    ("books", "Books", True),
    ("tax", "Tax", False),
    ("geography", "Geography", False),
    ("branches", "Branches and warehouses", False),
)


class FirmReadinessService:
    """Answer whether a firm is set up, and open its books.

    Two sessions because the facts live in two places: the firm record and
    its memberships in the platform store, everything else in the firm's own.
    """

    def __init__(self, platform_session: Session) -> None:
        """Bind to the platform store, where the firm and its people live."""
        self._platform = platform_session

    def readiness(self, firm: Firm, store: Session | None) -> FirmReadiness:
        """Report every step for one firm.

        Args:
            firm: The firm, read from the platform store.
            store: A session on the firm's own store, or None when it has
                none yet -- every store-side step is then BLOCKED.

        """
        provisioned = storage_is_ready(firm)
        mode = DeploymentMode(firm.deployment_mode)
        steps: list[ReadinessStep] = [
            ReadinessStep(
                key="storage",
                label="Storage",
                status=(
                    ReadinessStatus.DONE if provisioned else ReadinessStatus.MISSING
                ),
                detail=(
                    "Shared store; nothing to provision."
                    if mode is DeploymentMode.SHARED
                    else (
                        f"{mode.value} storage provisioned."
                        if provisioned
                        else f"{mode.value} storage has not been provisioned. "
                        "Nothing can be read or written until it is."
                    )
                ),
                required=True,
            )
        ]
        if store is not None and provisioned:
            steps.extend(store_steps(store, firm.id, utc_now().date()))
        else:
            steps.extend(
                _blocked(key, label, required=required)
                for key, label, required in _STORE_STEP_SHAPE
            )
        members = int(
            self._platform.scalar(
                select(func.count())
                .select_from(UserFirm)
                .where(
                    UserFirm.firm_id == firm.id,
                    UserFirm.is_active.is_(True),
                    UserFirm.is_deleted.is_(False),
                )
            )
            or 0
        )
        steps.append(
            ReadinessStep(
                key="members",
                label="People",
                status=ReadinessStatus.DONE if members else ReadinessStatus.MISSING,
                detail=(
                    f"{_plural(members, 'member')}."
                    if members
                    else "Nobody belongs to this firm yet. Only a platform "
                    "administrator can open it."
                ),
                required=False,
            )
        )
        return FirmReadiness(
            firm_id=firm.id,
            code=firm.code,
            name=firm.name,
            deployment_mode=mode,
            storage_provisioned=provisioned,
            steps=steps,
        )

    def open_books(
        self,
        firm: Firm,
        store: Session,
        actor_id: UUID,
        *,
        year_starts_on: date | None = None,
    ) -> tuple[dict[str, int], date]:
        """Give the firm the finance setup its documents need.

        The default chart of accounts, the financial year ``today`` falls in
        with twelve monthly periods, the journal and voucher types, and all 24
        control-account mappings -- the same seed the demo firms are built
        with, and idempotent, so a second call creates nothing and says so.

        The year opened defaults to the one running now, aligned to the
        firm's own year start; a firm founded years ago does not want its
        founding year opened. Pass ``year_starts_on`` to open a different one.

        Args:
            firm: The firm, read from the platform store.
            store: A session on the firm's own store.
            actor_id: Who is opening them.
            year_starts_on: First day of the year to open, or None for the
                current one.

        Returns:
            What was created, and the first day of the year that was opened.

        Raises:
            BusinessRuleError: If the firm's storage does not exist yet.

        """
        if not storage_is_ready(firm):
            raise BusinessRuleError(
                "Provision the firm's storage before opening its books."
            )
        starts_on = year_starts_on or current_year_start(
            firm.financial_year_start, utc_now().date()
        )
        created = seed_finance_setup(
            store, firm_id=firm.id, year_starts_on=starts_on, actor_id=actor_id
        )
        store.commit()
        if any(created.values()):
            # The record lands in the platform trail beside the firm's
            # creation and provisioning: it is a platform administrator's act
            # on a firm, like those, and the firm's own trail merges platform
            # rows carrying its id on the read. A call that created nothing
            # writes nothing -- "books opened" with every count at zero is a
            # row that says something happened when it did not.
            record_audit(
                self._platform,
                action="firm.books_opened",
                entity_type="firm",
                entity_id=firm.id,
                actor_id=actor_id,
                firm_id=firm.id,
                after_data={"year_starts_on": starts_on.isoformat(), **created},
            )
            self._platform.commit()
        return created, starts_on

    def apply_tax_template(
        self, firm: Firm, store: Session, actor_id: UUID, *, template: str
    ) -> dict[str, int]:
        """Give the firm a whole tax setup from a named template.

        Only Indian GST exists today: one system, four components, the 0, 5,
        12 and 18 percent slabs as local and interstate profiles plus exempt,
        and the six rules that make interstate, export, exempt and purchase
        behave. The country is created in the store if it has none. It is a
        starting point, edited afterwards on the tax screens.

        Idempotent: a firm that already holds a tax system gets nothing, and
        nothing is recorded, so the same action is the repair.

        Raises:
            BusinessRuleError: If the template is unknown or the store does
                not exist yet.

        """
        if template != INDIA_GST:
            raise BusinessRuleError(f"Unknown tax template '{template}'.")
        if not storage_is_ready(firm):
            raise BusinessRuleError(
                "Provision the firm's storage before applying a tax template."
            )
        created = apply_india_gst_template(store, firm_id=firm.id, actor_id=actor_id)
        store.commit()
        if any(created.values()):
            record_audit(
                self._platform,
                action="firm.tax_template_applied",
                entity_type="firm",
                entity_id=firm.id,
                actor_id=actor_id,
                firm_id=firm.id,
                after_data={"template": template, **created},
            )
            self._platform.commit()
        return created

    def create_default_branch(
        self, firm: Firm, store: Session, actor_id: UUID
    ) -> dict[str, str | None]:
        """Give the firm a head office and a main warehouse to start with.

        A branch and a warehouse are the firm's own to name, so the panel
        offers this as a default rather than deciding it: code ``HO``,
        "Head Office", as the default branch, and ``MAIN``, "Main
        Warehouse", under it -- both renamed afterwards on their own
        screens like anything else. Stock cannot move until a warehouse
        exists, and a warehouse needs a branch, which is why the panel
        treats them as one step.

        Idempotent per half: a firm that already has a branch keeps it and
        gets only the warehouse, under its default branch; a firm with both
        gets nothing and is told so.

        Returns:
            The branch code and warehouse code created, each None when that
            half already existed.

        Raises:
            BusinessRuleError: If the firm's storage does not exist yet.

        """
        if not storage_is_ready(firm):
            raise BusinessRuleError(
                "Provision the firm's storage before creating its first branch."
            )
        service = BranchWarehouseService(store)
        created: dict[str, str | None] = {"branch": None, "warehouse": None}
        branch = store.scalar(
            select(Branch)
            .where(Branch.firm_id == firm.id, Branch.is_deleted.is_(False))
            .order_by(Branch.is_default.desc(), Branch.created_at.asc())
        )
        if branch is None:
            branch = service.create_branch(
                BranchCreate(
                    code="HO",
                    name="Head Office",
                    display_name="Head Office",
                    currency_code=firm.currency_code,
                    is_default=True,
                ),
                firm_id=firm.id,
                actor_id=actor_id,
            )
            created["branch"] = branch.code
        has_warehouse = store.scalar(
            select(Warehouse.id).where(
                Warehouse.firm_id == firm.id, Warehouse.is_deleted.is_(False)
            )
        )
        if has_warehouse is None:
            warehouse = service.create_warehouse(
                WarehouseCreate(
                    branch_id=branch.id,
                    code="MAIN",
                    name="Main Warehouse",
                    display_name="Main Warehouse",
                ),
                firm_id=firm.id,
                actor_id=actor_id,
            )
            created["warehouse"] = warehouse.code
        store.commit()
        if any(created.values()):
            record_audit(
                self._platform,
                action="firm.default_branch_created",
                entity_type="firm",
                entity_id=firm.id,
                actor_id=actor_id,
                firm_id=firm.id,
                after_data={key: value for key, value in created.items() if value},
            )
            self._platform.commit()
        return created

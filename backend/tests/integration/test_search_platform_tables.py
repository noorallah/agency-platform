"""Global search from inside a firm must not 503.

`users`, `roles`, `permissions` and `firms` exist only in the platform schema.
A request carrying `X-Firm-ID` runs on a tenant session whose `search_path` is
that firm's schema and nothing else, so `SearchService` reading them there
raised ``relation "<firm schema>.users" does not exist``. One definition
failing aborts the whole search, so **every** global search from inside a firm
answered 503 -- Ctrl+K was broken for every firm user, on every query, for as
long as the feature has existed.

This is the suite that can see it. The unit tests build one SQLite schema
holding every table, so `users` is always reachable there and the defect is
invisible; `tests/unit/test_search_platform_store.py` can only check that the
flag agrees with `_PLATFORM_TABLES`.
"""

from collections.abc import Iterator
from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config.settings import Settings
from app.core.enums import TokenType
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.core.tenancy.lifecycle import _PLATFORM_TABLES
from app.customers.models import Customer
from app.firms.models import Firm
from app.search.services.search_service import SearchService


def _principal(permissions: set[str], firm_id: UUID | None = None) -> Principal:
    subject = uuid4()
    return Principal(
        subject=subject,
        roles=frozenset(),
        permissions=frozenset(permissions),
        claims=TokenClaims(
            sub=str(subject), type=TokenType.ACCESS, iat=1, exp=4_102_444_800
        ),
        firm_id=firm_id,
    )


@pytest.fixture
def pruned_schema(engine: Engine, temp_schema: str) -> Iterator[str]:
    """Build a firm schema shaped the way provisioning leaves one.

    `temp_schema` is built by `Base.metadata.create_all`, which gives it every
    table including `users` -- and that is precisely the difference that hid
    this defect. `prune_platform_objects` drops those from a real firm store,
    so the test drops them too. Without this the search would succeed for the
    wrong reason.
    """
    with engine.begin() as connection:
        for table in _PLATFORM_TABLES:
            connection.execute(
                text(f'DROP TABLE IF EXISTS "{temp_schema}"."{table}" CASCADE')
            )
    yield temp_schema


@pytest.fixture
def tenant_session(engine: Engine, pruned_schema: str) -> Iterator[Session]:
    """Yield a session shaped like a request carrying `X-Firm-ID`."""
    bind = engine.execution_options(schema_translate_map={None: pruned_schema})
    session = sessionmaker(bind=bind, expire_on_commit=False)()
    session.execute(text(f'SET search_path TO "{pruned_schema}"'))
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def test_a_firm_scoped_search_does_not_reach_for_users(
    tenant_session: Session, pruned_schema: str
) -> None:
    """The defect, and the whole point of the fix.

    `users` is genuinely absent from this schema -- asserted first, so a
    passing test cannot mean the pruning silently did nothing.
    """
    with pytest.raises(ProgrammingError):
        tenant_session.execute(text("select id from users limit 1"))
    tenant_session.rollback()

    firm_id = uuid4()
    customer = Customer(
        firm_id=firm_id,
        code=f"C{uuid4().hex[:8]}".upper(),
        customer_type="BUSINESS",
        name="Findable Trading",
        display_name="Findable Trading",
        currency_code="INR",
        status="ACTIVE",
    )
    tenant_session.add(customer)
    tenant_session.commit()

    principal = _principal({"CUSTOMER_VIEW", "USER_VIEW", "ROLE_VIEW"}, firm_id=firm_id)
    page = SearchService(tenant_session).search(
        query="Findable",
        principal=principal,
        category="all",
        page=1,
        page_size=20,
    )

    # It returns rather than raising, and it finds the firm-owned record.
    assert any(item.entity_type == "customers" for item in page.results)


def test_users_are_still_searchable_from_inside_a_firm(
    tenant_session: Session, engine: Engine
) -> None:
    """Reaching the platform store is the fix, not skipping the entity.

    A search that quietly dropped `users` would also make this pass if the
    assertion were only "no exception", so it looks for a real platform row.
    """
    settings = Settings()
    platform = sessionmaker(bind=engine, expire_on_commit=False)()
    platform.execute(text(f'SET search_path TO "{settings.database_schema}"'))
    suffix = uuid4().hex[:8]
    firm = Firm(
        name=f"Search Probe {suffix}",
        code=f"SP{suffix[:6]}".upper(),
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    platform.add(firm)
    platform.commit()
    try:
        page = SearchService(tenant_session).search(
            query=f"Search Probe {suffix}",
            principal=_principal({"FIRM_VIEW"}),
            category="all",
            page=1,
            page_size=20,
        )
        assert [item.entity_type for item in page.results] == ["firms"]
        assert page.results[0].title == firm.name
    finally:
        platform.delete(platform.get(Firm, firm.id))
        platform.commit()
        platform.close()

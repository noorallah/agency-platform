"""Multi-schema behaviour that SQLite cannot express.

These are the checks that would have caught the tenant-session firm-scope
defect: on PostgreSQL a tenant session runs ``SET search_path TO "<firm>"`` with
no fallback, so anything the platform owns is simply not visible to it.
"""

from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from app.common.scope import optional_firm_scope
from app.core.config.settings import Settings
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import AuthorizationError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.customers.models import Customer
from app.firms.models import Firm
from app.identity.models import User, UserFirm


def _principal(user_id: object, permissions: set[str]) -> Principal:
    """Build a principal carrying globally granted permissions."""
    return Principal(
        subject=user_id,
        roles=frozenset(),
        permissions=frozenset(permissions),
        claims=TokenClaims(
            sub=str(user_id), type=TokenType.ACCESS, iat=1, exp=4_102_444_800
        ),
    )


def test_platform_tables_are_invisible_to_a_deployed_firm_schema(
    engine: Engine,
) -> None:
    """A tenant session cannot see the firm registry.

    This is the property the old per-router scope resolvers violated: they ran
    ``select(Firm)`` on the tenant session, which raises UndefinedTable for any
    firm whose data does not live in the platform schema.

    The check runs against a migrated firm schema on purpose. A schema built by
    ``Base.metadata.create_all`` gets every table including ``firms``, which is
    part of why create_all-built firm stores do not match migrated ones.
    """
    deployed = [
        name
        for name in inspect(engine).get_schema_names()
        if name in {"firm_shared", "wholesale_hub"}
    ]
    if not deployed:
        pytest.skip("no migrated firm schema deployed in this database")
    with engine.connect() as connection:
        connection.execute(text(f'SET search_path TO "{deployed[0]}"'))
        with pytest.raises(ProgrammingError):
            connection.execute(text("select id from firms limit 1"))


def test_firm_scope_resolves_membership_on_the_platform_session(
    engine: Engine,
) -> None:
    """The shared resolver works while the request session is a firm schema."""
    settings = Settings()
    platform = sessionmaker(bind=engine, expire_on_commit=False)()
    platform.execute(text(f'SET search_path TO "{settings.database_schema}"'))
    suffix = uuid4().hex[:8]
    try:
        member_firm = Firm(
            name=f"Scope Firm {suffix}",
            code=f"SC{suffix[:6]}".upper(),
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
        )
        other_firm = Firm(
            name=f"Other Firm {suffix}",
            code=f"OT{suffix[:6]}".upper(),
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
        )
        user = User(
            email=f"scope-{suffix}@example.test",
            full_name="Scope Probe",
            password_hash="x",
            is_active=True,
        )
        platform.add_all([member_firm, other_firm, user])
        platform.flush()
        platform.add(
            UserFirm(
                user_id=user.id,
                firm_id=member_firm.id,
                is_active=True,
                is_primary=True,
            )
        )
        platform.commit()

        principal = _principal(user.id, {"CUSTOMER_VIEW"})
        scope = optional_firm_scope(
            principal=principal, db=platform, x_firm_id=member_firm.id
        )
        assert scope.firm_id == member_firm.id

        # A globally granted permission must not reach a firm the user is not
        # a member of.
        with pytest.raises(AuthorizationError):
            optional_firm_scope(
                principal=principal, db=platform, x_firm_id=other_firm.id
            )
    finally:
        platform.rollback()
        platform.execute(
            text(
                "delete from user_firms where user_id in "
                "(select id from users where email like :p)"
            ),
            {"p": f"scope-{suffix}@%"},
        )
        platform.execute(
            text("delete from users where email like :p"), {"p": f"scope-{suffix}@%"}
        )
        platform.execute(
            text("delete from firms where code like :p"),
            {"p": f"SC{suffix[:6].upper()}%"},
        )
        platform.execute(
            text("delete from firms where code like :p"),
            {"p": f"OT{suffix[:6].upper()}%"},
        )
        platform.commit()
        platform.close()


def test_two_firm_schemas_do_not_share_rows(engine: Engine) -> None:
    """The same table in two schemas holds independent data."""
    names = [f"it_{uuid4().hex[:12]}" for _ in range(2)]
    sessions: list[Session] = []
    try:
        for name in names:
            with engine.begin() as connection:
                connection.execute(text(f'CREATE SCHEMA "{name}"'))
            Base.metadata.create_all(
                engine.execution_options(schema_translate_map={None: name})
            )
            bind = engine.execution_options(schema_translate_map={None: name})
            session = sessionmaker(bind=bind, expire_on_commit=False)()
            session.execute(text(f'SET search_path TO "{name}"'))
            sessions.append(session)

        # create_all puts a firms table in each schema and the FK is enforced,
        # so the owning row has to exist locally.
        firm_id = uuid4()
        for session in sessions:
            session.add(
                Firm(
                    id=firm_id,
                    name="Isolation Firm",
                    code="ISO-001",
                    country="IN",
                    currency_code="INR",
                    financial_year_start=date(2026, 4, 1),
                )
            )
            session.commit()
        sessions[0].add(
            Customer(
                firm_id=firm_id,
                code="CUS-ISO",
                customer_type="RETAIL",
                name="Only In First",
                display_name="Only In First",
                currency_code="INR",
                status="ACTIVE",
            )
        )
        sessions[0].commit()

        assert sessions[0].scalar(select(Customer.name)) == "Only In First"
        assert sessions[1].scalar(select(Customer.name)) is None
    finally:
        for session in sessions:
            session.close()
        for name in names:
            with engine.begin() as connection:
                connection.execute(text(f'DROP SCHEMA IF EXISTS "{name}" CASCADE'))


def test_live_firm_schemas_match_the_orm(engine: Engine) -> None:
    """Every ORM column exists in the deployed firm schemas.

    Migrations run per schema, so a firm store silently falls behind when only
    the default schema is upgraded. That drift had already broken every product
    read in all three firm schemas once before it was noticed.
    """
    inspector = inspect(engine)
    schemas = [
        name
        for name in inspector.get_schema_names()
        if name in {"firm_shared", "wholesale_hub"}
    ]
    if not schemas:
        pytest.skip("no firm schemas deployed in this database")

    missing: list[str] = []
    for schema in schemas:
        present = set(inspector.get_table_names(schema=schema))
        for table in Base.metadata.sorted_tables:
            if table.name not in present:
                continue
            columns = {
                column["name"]
                for column in inspector.get_columns(table.name, schema=schema)
            }
            for column in table.columns:
                if column.name not in columns:
                    missing.append(f"{schema}.{table.name}.{column.name}")
    assert not missing, f"schema drift against the ORM: {sorted(missing)}"


def test_every_deployed_table_can_be_inserted_into(engine: Engine) -> None:
    """`created_at` and `updated_at` carry a default in the deployed schemas.

    `Base.metadata.create_all` supplies one from the ORM and a hand-written
    ``op.create_table`` does not, so a migration that spells the two timestamp
    columns out without ``server_default`` builds a table that **cannot be
    inserted into at all** -- the first write raises NotNullViolation. The
    unit suite cannot see it: it builds its schema from the ORM, so the
    columns it tests against always have the default the migration forgot.

    That shipped once, in `commission_rule_slabs`, and was found by driving a
    real firm rather than by any test. This is the guard, and it costs one
    query.
    """
    inspector = inspect(engine)
    schemas = [
        name
        for name in inspector.get_schema_names()
        if name in {"firm_shared", "wholesale_hub"}
    ]
    if not schemas:
        pytest.skip("no firm schemas deployed in this database")

    undefaulted: list[str] = []
    for schema in schemas:
        present = set(inspector.get_table_names(schema=schema))
        for table in Base.metadata.sorted_tables:
            if table.name not in present:
                continue
            for column in inspector.get_columns(table.name, schema=schema):
                if column["name"] not in {"created_at", "updated_at"}:
                    continue
                if not column["nullable"] and column["default"] is None:
                    undefaulted.append(f"{schema}.{table.name}.{column['name']}")
    assert not undefaulted, (
        "these columns are NOT NULL with no default, so the first insert "
        f"fails: {sorted(undefaulted)}"
    )

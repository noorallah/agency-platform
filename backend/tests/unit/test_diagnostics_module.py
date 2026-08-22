"""Error reporting tests.

The product ships to machines nobody here can reach, so a failure that leaves no
record cannot be fixed. These cover the two halves: what a client is allowed to
send, and that the server records its own unhandled failures against the request
id it already handed back to the caller.
"""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.context import RequestContext
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions.handlers import request_id_for
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.core.utils.dates import utc_now
from app.diagnostics.api.router import (
    list_error_groups,
    list_error_occurrences,
    report_client_errors,
)
from app.diagnostics.models import ErrorReport
from app.diagnostics.schemas import ClientErrorReportBatch, ClientErrorReportCreate
from app.diagnostics.services import ErrorReportService, fingerprint_for
from app.identity.system_seed import PERMISSION_GROUPS


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _principal(subject: object) -> Principal:
    return Principal(
        subject=subject,
        roles=frozenset({"firm_user"}),
        permissions=frozenset({"DIAGNOSTICS_VIEW"}),
        claims=TokenClaims(
            sub=str(subject),
            type=TokenType.ACCESS,
            iat=1,
            exp=4_102_444_800,
        ),
    )


def _report(**overrides: object) -> ClientErrorReportCreate:
    payload: dict[str, object] = {
        "fingerprint": "abc123",
        "error_type": "StateError",
        "message": "Bad state: boom",
        "stack_trace": "#0 ProductPage.build",
        "app_version": "1.0.0",
        "build_number": "128",
        "platform_info": "windows 11",
        "breadcrumbs": ["opened products", "tapped save"],
    }
    payload.update(overrides)
    return ClientErrorReportCreate(**payload)  # type: ignore[arg-type]


def test_the_permission_code_is_seeded() -> None:
    """An enforced but unseeded code silently becomes platform-admin-only."""
    assert "DIAGNOSTICS_VIEW" in PERMISSION_GROUPS["system_administration"]


def test_a_client_batch_is_stored_against_the_caller() -> None:
    """Firm and user come from the token, never from the payload."""
    session = _session()
    user_id = uuid4()
    firm_id = uuid4()

    report_client_errors(
        ClientErrorReportBatch(reports=[_report(), _report(fingerprint="def456")]),
        _principal(user_id),
        db=session,
        x_firm_id=firm_id,
    )

    rows = session.scalars(select(ErrorReport)).all()
    assert len(rows) == 2
    assert {row.source for row in rows} == {"CLIENT"}
    assert {row.user_id for row in rows} == {user_id}
    assert {row.firm_id for row in rows} == {firm_id}


def test_a_report_from_a_client_that_never_signed_in_still_records() -> None:
    """A crash before a firm is chosen is still worth having."""
    session = _session()

    report_client_errors(
        ClientErrorReportBatch(reports=[_report()]),
        _principal(uuid4()),
        db=session,
        x_firm_id=None,
    )

    stored = session.scalars(select(ErrorReport)).one()
    assert stored.firm_id is None
    assert stored.breadcrumbs == ["opened products", "tapped save"]


def test_oversized_input_is_refused_at_the_boundary() -> None:
    """The client is the least trusted input the server takes."""
    with pytest.raises(ValueError):
        _report(message="x" * 9000)
    with pytest.raises(ValueError):
        ClientErrorReportBatch(reports=[])


def test_one_oversized_breadcrumb_cannot_carry_an_unbounded_payload() -> None:
    """Each line is capped, so a batch cannot smuggle a megabyte through."""
    report = _report(breadcrumbs=["y" * 5000])

    assert len(report.breadcrumbs[0]) == 500


def test_the_same_fault_fingerprints_the_same_across_builds() -> None:
    """Line numbers and paths move every release; the identity must not."""
    first = fingerprint_for(
        "ValueError", "  File 'app/x.py', line 12, in post\n    raise ValueError"
    )
    second = fingerprint_for(
        "ValueError", "  File 'app/x.py', line 998, in post\n    raise ValueError"
    )

    assert first == second
    assert first != fingerprint_for("KeyError", "  File 'app/x.py', line 12, in post")


def test_groups_collapse_occurrences_and_report_counts() -> None:
    """A thousand copies of one crash is one problem, not a thousand rows."""
    session = _session()
    service = ErrorReportService(session)
    for _ in range(3):
        service.record_client_report(_report(), firm_id=None, user_id=None)
    service.record_client_report(
        _report(fingerprint="other", error_type="RangeError"),
        firm_id=None,
        user_id=None,
    )

    groups, total = service.list_groups(1, 20)

    assert total == 2
    counts = {group["fingerprint"]: group["occurrences"] for group in groups}
    assert counts == {"abc123": 3, "other": 1}


def test_the_group_list_is_readable_through_the_router() -> None:
    """The endpoint returns groups, and detail returns the occurrences."""
    session = _session()
    service = ErrorReportService(session)
    service.record_client_report(_report(), firm_id=None, user_id=None)

    listed = list_error_groups(_principal(uuid4()), db=session)
    detail = list_error_occurrences("abc123", _principal(uuid4()), db=session)

    assert listed.pagination.total_records == 1
    assert listed.data[0].occurrences == 1
    assert listed.data[0].app_versions == ["1.0.0"]
    assert detail.data[0].message == "Bad state: boom"


def test_a_server_failure_is_recorded_against_its_request_id() -> None:
    """The id the caller was shown is what joins their report to this row."""
    session = _session()

    ErrorReportService(session).record_server_error(
        error_type="IntegrityError",
        message="duplicate key",
        stack_trace="Traceback...",
        request_id="req-42",
        context_label="POST /api/v1/products",
    )

    stored = session.scalars(select(ErrorReport)).one()
    assert stored.source == "SERVER"
    assert stored.request_id == "req-42"
    assert stored.context_label == "POST /api/v1/products"


def test_recording_a_server_failure_never_raises() -> None:
    """It runs while the request is already failing; it must not make it worse."""
    session = _session()
    session.close()

    ErrorReportService(session).record_server_error(
        error_type="RuntimeError",
        message="boom",
        stack_trace=None,
        request_id=None,
    )


def test_retention_removes_only_what_is_older_than_the_cutoff() -> None:
    """These grow unbounded exactly as the tax execution logs did."""
    session = _session()
    service = ErrorReportService(session)
    service.record_client_report(_report(), firm_id=None, user_id=None)
    old = session.scalars(select(ErrorReport)).one()
    old.received_at = utc_now() - timedelta(days=120)
    session.commit()
    service.record_client_report(
        _report(fingerprint="fresh"), firm_id=None, user_id=None
    )

    removed = service.purge_before(utc_now() - timedelta(days=90))

    assert removed == 1
    remaining = session.scalars(select(ErrorReport)).all()
    assert [row.fingerprint for row in remaining] == ["fresh"]


class _StubState:
    """Hold the parts of `request.state` a handler reads."""

    def __init__(self, context: RequestContext | None) -> None:
        self.context = context


class _StubRequest:
    """Stand in for a request that has left the middleware behind."""

    def __init__(self, context: RequestContext | None) -> None:
        self.state = _StubState(context)


def test_the_request_id_survives_the_middleware_that_set_it() -> None:
    """The handler runs after the context variable has been reset.

    A handler registered for bare `Exception` is served by Starlette's
    `ServerErrorMiddleware`, the outermost layer -- outside
    `CoreRequestMiddleware`, whose `finally` resets the context variable. So by
    the time a 500 arrives, the variable is empty, and reading it stored NULL as
    the request id on **every** server fault: 28 out of 28 on the deployment
    this was found on. The screenshot-to-traceback join the module exists for
    could not be made.
    """
    context = RequestContext(
        request_id="req-77",
        correlation_id="corr-77",
        client_ip="10.0.0.9",
        requested_at=utc_now(),
    )
    # No context variable is set here, which is the situation exactly.
    assert request_id_for(_StubRequest(context)) == "req-77"


def test_a_request_that_never_had_a_context_reads_as_none() -> None:
    """A caller with neither is not a crash; it is one report with no join."""
    assert request_id_for(_StubRequest(None)) is None


def test_the_exception_handler_runs_outside_the_middleware_that_sets_context() -> None:
    """Pin the ordering the fix depends on, so a re-order cannot un-fix it.

    If `CoreRequestMiddleware` is ever moved outside `ServerErrorMiddleware`,
    the context variable would be live again and this whole trap disappears --
    but the reverse move is what would silently restore the defect.
    """
    from app.main import create_app

    stack = create_app().build_middleware_stack()
    order: list[str] = []
    node: object | None = stack
    while node is not None and len(order) < 12:
        order.append(type(node).__name__)
        node = getattr(node, "app", None)

    assert "ServerErrorMiddleware" in order
    assert "CoreRequestMiddleware" in order
    assert order.index("ServerErrorMiddleware") < order.index("CoreRequestMiddleware")


def _server_trace(router: str, *, library: str = "main.py", line: int = 91) -> str:
    """Build a traceback shaped like the ones this deployment recorded.

    Four real ones were compared while writing this: the leading frames are
    always the ASGI plumbing and the trailing frames are always the library
    that raised, so neither end says which endpoint failed.
    """
    return "\n".join(
        [
            "Traceback (most recent call last):",
            '  File "/venv/starlette/middleware/errors.py", line 164, in __call__',
            "    await self.app(scope, receive, _send)",
            '  File "/venv/starlette/middleware/base.py", line 176, in __call__',
            "    with recv_stream, send_stream:",
            f'  File "/repo/backend/app/{router}/api/router.py", '
            f"line {line}, in list_rows",
            "    params = PaginationParams(page=page, page_size=page_size)",
            f'  File "/venv/pydantic/{library}", line 253, in __init__',
            "    validated_self = self.__pydantic_validator__.validate_python(data)",
            "pydantic_core.ValidationError: 1 validation error",
        ]
    )


def test_two_endpoints_failing_the_same_way_are_two_faults() -> None:
    """The fingerprint has to say *where*, and the top of a stack never does.

    Hashing the first five frames grouped every server fault of one exception
    type together, because the leading lines of a Python traceback are the ASGI
    plumbing every request shares. Measured on real data: 28 ``ValidationError``
    reports from **four** endpoints carried one fingerprint, and the triage
    screen showed whichever context happened to come first -- so fixing that one
    endpoint would have looked like fixing all four.
    """
    products = fingerprint_for("ValidationError", _server_trace("products"))
    warehouses = fingerprint_for("ValidationError", _server_trace("branches"))

    assert products != warehouses, "two endpoints, two faults"
    # The same endpoint failing twice is still one fault, which is the property
    # the grouping exists for in the first place.
    assert products == fingerprint_for("ValidationError", _server_trace("products"))


def test_the_identity_is_this_codebase_s_frames_not_the_library_s() -> None:
    """A library upgrade must not rename every fault that passes through it."""
    same_handler_other_library = fingerprint_for(
        "ValidationError", _server_trace("products", library="other.py")
    )

    assert same_handler_other_library == fingerprint_for(
        "ValidationError", _server_trace("products")
    )


def test_a_line_number_moving_does_not_rename_the_fault() -> None:
    """An edit above the failure must not hand it a new identity."""
    assert fingerprint_for("ValidationError", _server_trace("products", line=91)) == (
        fingerprint_for("ValidationError", _server_trace("products", line=140))
    )

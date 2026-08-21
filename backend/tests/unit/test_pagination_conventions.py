"""Guard the rule that a list endpoint bounds its own page parameters.

``PaginationParams`` enforces ``1 <= page_size <= MAX_PAGE_SIZE`` -- but a
handler that takes a bare ``page_size: int = 20`` and *builds the model in its
body* validates after routing, so an over-cap request surfaces as a **500**
rather than a 422 naming the limit. FastAPI can only refuse it properly when the
bound is declared on the query parameter.

That is not hypothetical. The diagnostics triage screen, on its first run
against real data, found 28 stored ``ValidationError``s from
``GET /api/v1/products`` between 2026-08-15 and 2026-08-17 -- every one a
``page_size=200`` request answered with a 500. Two desktop screens had already
shipped asking for 500 and were broken against every real backend while their
tests, whose fakes ignore the value, stayed green.

Forty-four handlers were in that state when this guard was written. The bound is
cheap; finding the next one from a 500 in a crash log is not.
"""

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"

#: The parameters that must carry a bound, and the bounds each one needs.
REQUIRED_BOUNDS: dict[str, tuple[str, ...]] = {
    "page": ("ge",),
    "page_size": ("ge", "le"),
}

# Endpoints permitted to take an unbounded page parameter, with the reason.
# Empty on purpose: nothing here has a reason to accept an unbounded page size.
ALLOWED: dict[str, str] = {}


def _query_bounds(annotation: ast.expr | None, default: ast.expr | None) -> set[str]:
    """Return the bound names a parameter declares through ``Query``.

    Both spellings count. ``Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]`` is
    the shape to copy, and ``= Query(default=20, ge=1, le=100)`` is the older
    one four endpoints already used -- refusing the second would be a style
    opinion dressed up as a defect, since FastAPI enforces both identically.
    """
    calls: list[ast.Call] = []
    if isinstance(annotation, ast.Subscript):
        # Annotated[int, Query(...)] -- the metadata sits in the slice tuple.
        slice_node = annotation.slice
        parts = slice_node.elts if isinstance(slice_node, ast.Tuple) else [slice_node]
        calls.extend(part for part in parts if isinstance(part, ast.Call))
    if isinstance(default, ast.Call):
        calls.append(default)
    bounds: set[str] = set()
    for call in calls:
        name = call.func
        if isinstance(name, ast.Name) and name.id != "Query":
            continue
        if isinstance(name, ast.Attribute) and name.attr != "Query":
            continue
        bounds.update(
            keyword.arg for keyword in call.keywords if keyword.arg is not None
        )
    return bounds


#: The decorators that make a function reachable over HTTP.
HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head"})


def _is_route_handler(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return whether a function is registered on a router.

    Only a handler takes its arguments from the query string. A private helper
    three handlers share -- ``app/settlements`` has one -- receives values they
    have already validated, and demanding ``Query`` metadata there would be
    asking a plain function to describe an HTTP contract it never sees.
    """
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        target = decorator.func
        if not isinstance(target, ast.Attribute) or target.attr not in HTTP_METHODS:
            continue
        owner = target.value
        if isinstance(owner, ast.Name) and owner.id.lower().endswith("router"):
            return True
    return False


def _unbounded_parameters(source: str) -> dict[str, list[str]]:
    """Return each route handler's page parameters that declare no bound."""
    tree = ast.parse(source)
    offenders: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if not _is_route_handler(node):
            continue
        arguments = node.args
        defaults: dict[str, ast.expr | None] = {}
        positional = arguments.posonlyargs + arguments.args
        padding: list[ast.expr | None] = [None] * (
            len(positional) - len(arguments.defaults)
        )
        for argument, default in zip(
            positional, padding + list(arguments.defaults), strict=True
        ):
            defaults[argument.arg] = default
        for argument, default in zip(
            arguments.kwonlyargs, arguments.kw_defaults, strict=True
        ):
            defaults[argument.arg] = default
        for argument in positional + arguments.kwonlyargs:
            required = REQUIRED_BOUNDS.get(argument.arg)
            if required is None:
                continue
            declared = _query_bounds(argument.annotation, defaults[argument.arg])
            missing = [bound for bound in required if bound not in declared]
            if missing:
                offenders.setdefault(node.name, []).extend(
                    f"{argument.arg} ({', '.join(missing)})" for _ in [0]
                )
    return offenders


def test_every_list_endpoint_bounds_its_page_parameters() -> None:
    """A page parameter is bounded where FastAPI can refuse it: on the query."""
    offenders: dict[str, dict[str, list[str]]] = {}
    for path in sorted(APP.rglob("api/*.py")):
        relative = path.relative_to(APP.parent).as_posix()
        if relative in ALLOWED:
            continue
        found = _unbounded_parameters(path.read_text(encoding="utf-8"))
        if found:
            offenders[relative] = found

    assert not offenders, (
        "these handlers take an unbounded page parameter: "
        f"{offenders}. Declare it as "
        "Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)], or the model's own "
        "check runs after routing and an over-cap request answers 500 instead "
        "of a 422 naming the limit."
    )


def test_the_guard_sees_a_bare_parameter_and_accepts_both_bounded_spellings() -> None:
    """A guard that cannot fail is not a guard, and one that cries wolf is worse.

    The older ``= Query(default=20, ge=1, le=100)`` form has to pass: FastAPI
    enforces it identically, and reporting it would make this a style rule
    rather than a defect guard.
    """
    bare = _unbounded_parameters(
        "@router.get('')\n"
        "def list_things(page: int = 1, page_size: int = 20) -> None: ...\n"
    )
    assert bare == {"list_things": ["page (ge)", "page_size (ge, le)"]}

    annotated = _unbounded_parameters(
        "@router.get('')\n"
        "def list_things(\n"
        "    page: Annotated[int, Query(ge=1)] = 1,\n"
        "    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,\n"
        ") -> None: ...\n"
    )
    assert annotated == {}

    older = _unbounded_parameters(
        "@receipts_router.get('')\n"
        "def list_things(\n"
        "    page: int = Query(default=1, ge=1),\n"
        "    page_size: int = Query(default=20, ge=1, le=100),\n"
        ") -> None: ...\n"
    )
    assert older == {}

    # A page size bounded below and not above is the exact defect: it passes
    # ge and still lets 500 through to the model.
    half = _unbounded_parameters(
        "@router.get('')\n"
        "def list_things(page_size: Annotated[int, Query(ge=1)] = 20) -> None: ...\n"
    )
    assert half == {"list_things": ["page_size (le)"]}

    # A shared helper is not a handler: it takes what a handler already
    # validated, and `app/settlements` has one that the first version of this
    # guard reported as a defect.
    helper = _unbounded_parameters(
        "def _list(*, page: int, page_size: int) -> None: ...\n"
    )
    assert helper == {}

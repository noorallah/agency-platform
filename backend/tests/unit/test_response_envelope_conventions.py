"""Guard the rule that every endpoint answers in the standard envelope.

`ApiResponse` and `PaginatedResponse` carry more than the record: `success`, a
`timestamp`, and the `requestId` a user quotes when something goes wrong. A
handler that returns the bare model drops all three, and a client reading
`body["data"]` gets nothing at all.

`app/sales_invoice` did exactly that on seven endpoints -- create, get, update,
approve, cancel, close and import -- while every other module wrapped. It went
unseen for months because the desktop's `_unwrapMap` falls back to the raw body
when there is no `data` key, so the one client anybody exercised could not tell
the difference. It surfaced on 2026-08-22 when a probe script read `["data"]`
and got a KeyError.

The reports in the same module had the same break and were fixed on 2026-08-14.
Whoever fixed them did not check the lifecycle endpoints beside them, which is
the argument for a test rather than a third pass.
"""

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"

#: Response models that are the envelope, or extend it.
ENVELOPES = {"ApiResponse", "PaginatedResponse"}

#: Names that resolve to an envelope subclass, with where to look.
ALLOWED_SUBCLASSES = {
    "ConversionResult": (
        "app/quotation/api/router.py -- extends ApiResponse[QuotationResponse] "
        "to carry the order the quotation became alongside it"
    ),
}

#: The decorators that put a function on the wire.
HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head"})


def _model_name(node: ast.expr) -> str | None:
    """Return the outermost name of a response model expression."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Subscript):
        return _model_name(node.value)
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _unwrapped_handlers(source: str) -> dict[str, str]:
    """Return each handler whose response model is not an envelope."""
    tree = ast.parse(source)
    offenders: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            target = decorator.func
            if not isinstance(target, ast.Attribute) or target.attr not in HTTP_METHODS:
                continue
            owner = target.value
            if not isinstance(owner, ast.Name) or not owner.id.lower().endswith(
                "router"
            ):
                continue
            for keyword in decorator.keywords:
                if keyword.arg != "response_model":
                    continue
                name = _model_name(keyword.value)
                if name is None or name in ENVELOPES or name in ALLOWED_SUBCLASSES:
                    continue
                offenders[node.name] = name
    return offenders


def test_every_endpoint_answers_in_the_envelope() -> None:
    """A response model is `ApiResponse[...]` or `PaginatedResponse[...]`."""
    offenders: dict[str, dict[str, str]] = {}
    for path in sorted(APP.rglob("api/*.py")):
        found = _unwrapped_handlers(path.read_text(encoding="utf-8"))
        if found:
            offenders[path.relative_to(APP.parent).as_posix()] = found

    assert not offenders, (
        f"these answer with a bare model: {offenders}. Wrap them in "
        "ApiResponse -- the envelope carries the requestId a user quotes, and "
        "a client reading body['data'] gets nothing without it."
    )


def test_the_guard_sees_a_bare_model_and_accepts_the_envelope() -> None:
    """A guard that cannot fail is not a guard.

    An endpoint with no response model at all is left alone on purpose: a 204
    delete and a streaming export both declare none, and neither has a body to
    wrap.
    """
    bare = _unwrapped_handlers(
        "@router.get('/x', response_model=SalesInvoiceResponse)\n"
        "def get_one() -> SalesInvoiceResponse: ...\n"
    )
    assert bare == {"get_one": "SalesInvoiceResponse"}

    bare_list = _unwrapped_handlers(
        "@router.post('/import', response_model=list[SalesInvoiceResponse])\n"
        "def import_many() -> list[SalesInvoiceResponse]: ...\n"
    )
    assert bare_list == {"import_many": "list"}

    wrapped = _unwrapped_handlers(
        "@router.get('/x', response_model=ApiResponse[SalesInvoiceResponse])\n"
        "def get_one() -> ApiResponse[SalesInvoiceResponse]: ...\n"
        "@router.get('/xs', response_model=PaginatedResponse[SalesInvoiceResponse])\n"
        "def list_them() -> PaginatedResponse[SalesInvoiceResponse]: ...\n"
        "@router.get('/f', response_class=StreamingResponse)\n"
        "def export() -> StreamingResponse: ...\n"
    )
    assert wrapped == {}

    # A named subclass of the envelope is fine, and has to say why it exists.
    allowed = _unwrapped_handlers(
        "@router.post('/convert', response_model=ConversionResult)\n"
        "def convert() -> ConversionResult: ...\n"
    )
    assert allowed == {}
    assert "ConversionResult" in ALLOWED_SUBCLASSES

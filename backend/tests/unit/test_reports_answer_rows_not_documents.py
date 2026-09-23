"""A report answers flat rows, never whole documents.

Seven report routes answered the full ``…Response`` -- lines, attachments,
notes and, for receipts and bills, a duplicate-check query per row -- while the
desktop showed five or six columns of it, so time and payload scaled with the
history rather than with what was shown (D-RPT-16). The two overdue reports went
flat with D-RPT-2 and D-RPT-3; the five pending and completed ones here answer
their module's register record.
"""

from collections.abc import Iterator

#: The routes, and the record each must answer.
_ROUTES = {
    "/api/v1/delivery-notes/reports/pending": "DeliveryNoteRegisterRecord",
    "/api/v1/sales-invoices/reports/pending": "SalesInvoiceRegisterRecord",
    "/api/v1/sales-invoices/reports/overdue": "SalesInvoiceOverdueRecord",
    "/api/v1/purchase-invoices/reports/pending": "PurchaseInvoiceRegisterRecord",
    "/api/v1/purchase-invoices/reports/overdue": "PurchaseInvoiceOverdueRecord",
    "/api/v1/goods-receipts/reports/pending": "GoodsReceiptRegisterRecord",
    "/api/v1/goods-receipts/reports/completed": "GoodsReceiptRegisterRecord",
}


def _endpoints(routes: object) -> Iterator[object]:
    """Yield the leaf endpoints of a built application (see test_document_framework)."""
    for route in routes:  # type: ignore[attr-defined]
        inner = getattr(route, "original_router", None)
        if inner is not None:
            yield from _endpoints(inner.routes)
            continue
        nested = getattr(route, "routes", None)
        if nested:
            yield from _endpoints(nested)
            continue
        yield route


def test_no_report_route_answers_a_whole_document() -> None:
    """Every ``/reports/`` route's response model is a record, not a ``…Response``."""
    from app.main import create_app

    by_path = {
        getattr(route, "path", ""): route
        for route in _endpoints(create_app().routes)
        if "/reports/" in getattr(route, "path", "")
    }
    assert by_path, "no report routes found"
    documents = (
        "GoodsReceiptResponse]",
        "DeliveryNoteResponse]",
        "SalesInvoiceResponse]",
        "PurchaseInvoiceResponse]",
    )
    offenders = {
        path: repr(getattr(route, "response_model", None))
        for path, route in by_path.items()
        if any(
            name in repr(getattr(route, "response_model", None)) for name in documents
        )
    }
    assert not offenders, f"reports answering whole documents: {offenders}"
    for path, record in _ROUTES.items():
        assert path in by_path, path
        assert record in repr(by_path[path].response_model), path  # type: ignore[attr-defined]

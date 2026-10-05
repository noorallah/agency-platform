"""Files uploaded onto the five sales documents (SG-6, backlog 87 #6).

The quotation, the sales order, the delivery note, the sales invoice and the
sales return each gained the four routes the purchase bill has, over the same
``app/document_files`` service. Every case here runs once per document, so
what is proved is that each one *reaches* the shared rules: the round trip,
refusal by size and by type, another firm's document and file refused, a
removal audited, the paper-clip count on the list row and on the document
alone, and a list page that costs the same however many of its rows carry
files.
"""

import asyncio
import io
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.datastructures import Headers, UploadFile

from app.common.audit.models import AuditLog
from app.common.scope import ResolvedFirmScope
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.delivery_note.api.router import (
    delete_delivery_note_file,
    download_delivery_note_file,
    list_delivery_note_files,
    upload_delivery_note_file,
)
from app.delivery_note.models import DeliveryNote
from app.document_files.models import PARENT_COLUMNS, DocumentFile
from app.document_files.services import (
    _PARENTS,
    MAX_FILE_BYTES,
    FileParent,
    document_file_counts,
)
from app.quotation.api.router import (
    delete_quotation_file,
    download_quotation_file,
    list_quotation_files,
    upload_quotation_file,
)
from app.quotation.models import SalesQuotation
from app.sales_invoice.api.router import (
    delete_sales_invoice_file,
    download_sales_invoice_file,
    list_sales_invoice_files,
    upload_sales_invoice_file,
)
from app.sales_invoice.models import SalesInvoice
from app.sales_order.api.router import (
    delete_sales_order_file,
    download_sales_order_file,
    list_sales_order_files,
    upload_sales_order_file,
)
from app.sales_order.models import SalesOrder
from app.sales_return.api.router import (
    delete_sales_return_file,
    download_sales_return_file,
    list_sales_return_files,
    upload_sales_return_file,
)
from app.sales_return.models import SalesReturn
from tests.unit.test_document_summaries_in_sql import _session
from tests.unit.test_list_pages_are_batched import (
    CASES,
    _counting,
    _scope,
    _World,
    _world,
)

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
EXE = b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 64


@dataclass(frozen=True)
class _Document:
    """One kind of sales document: its rows, its routes, and its list page."""

    #: The name of its list page in ``test_list_pages_are_batched.CASES``.
    page: str
    model: type[Any]
    parent: FileParent
    #: The key on ``document_files`` that names it.
    column: str
    list_files: Callable[..., Any]
    upload: Callable[..., Any]
    download: Callable[..., Any]
    delete: Callable[..., Any]


DOCUMENTS: dict[str, _Document] = {
    "quotation": _Document(
        "quotations",
        SalesQuotation,
        FileParent.SALES_QUOTATION,
        "sales_quotation_id",
        list_quotation_files,
        upload_quotation_file,
        download_quotation_file,
        delete_quotation_file,
    ),
    "sales order": _Document(
        "sales orders",
        SalesOrder,
        FileParent.SALES_ORDER,
        "sales_order_id",
        list_sales_order_files,
        upload_sales_order_file,
        download_sales_order_file,
        delete_sales_order_file,
    ),
    "delivery note": _Document(
        "delivery notes",
        DeliveryNote,
        FileParent.DELIVERY_NOTE,
        "delivery_note_id",
        list_delivery_note_files,
        upload_delivery_note_file,
        download_delivery_note_file,
        delete_delivery_note_file,
    ),
    "sales invoice": _Document(
        "sales invoices",
        SalesInvoice,
        FileParent.SALES_INVOICE,
        "sales_invoice_id",
        list_sales_invoice_files,
        upload_sales_invoice_file,
        download_sales_invoice_file,
        delete_sales_invoice_file,
    ),
    "sales return": _Document(
        "sales returns",
        SalesReturn,
        FileParent.SALES_RETURN,
        "sales_return_id",
        list_sales_return_files,
        upload_sales_return_file,
        download_sales_return_file,
        delete_sales_return_file,
    ),
}
EVERY_DOCUMENT = pytest.mark.parametrize("name", list(DOCUMENTS))


@dataclass
class _Firm:
    """One firm, somebody acting in it, and the documents it holds."""

    world: _World
    scope: ResolvedFirmScope
    ids: list[UUID]


def _firm(session: Session, document: _Document, rows: int = 1) -> _Firm:
    """Seed a firm holding ``rows`` documents of one kind, oldest id first."""
    world = _world(session)
    CASES[document.page].seed(session, world, rows)
    session.commit()
    ids = sorted(
        session.scalars(
            select(document.model.id).where(document.model.firm_id == world.firm)
        ),
        key=str,
    )
    assert len(ids) == rows
    return _Firm(world, _scope(world.firm), ids)


def _part(content: bytes, name: str, content_type: str | None) -> UploadFile:
    """Build a multipart file part as a request would carry it."""
    headers = Headers({"content-type": content_type}) if content_type else None
    return UploadFile(io.BytesIO(content), filename=name, headers=headers)


def _upload(
    session: Session,
    document: _Document,
    firm: _Firm,
    document_id: UUID,
    content: bytes = PDF,
    name: str = "paper.pdf",
    content_type: str | None = "application/pdf",
) -> UUID:
    """Upload one file through the document's own route; return the file's id."""
    answer = asyncio.run(
        document.upload(
            document_id,
            firm.scope,
            _part(content, name, content_type),
            "customer PO 77",
            session,
        )
    )
    assert answer.data is not None
    file_id: UUID = answer.data.id
    return file_id


def _listed(session: Session, document: _Document, firm: _Firm) -> list[UUID]:
    """Return the ids of the files on the firm's first document."""
    answer = document.list_files(firm.ids[0], firm.scope, session)
    assert answer.data is not None
    return [found.id for found in answer.data]


@EVERY_DOCUMENT
def test_a_file_round_trips_byte_for_byte(name: str) -> None:
    """What is downloaded is exactly what was uploaded, on that document only."""
    document = DOCUMENTS[name]
    session = _session()
    firm = _firm(session, document)
    file_id = _upload(session, document, firm, firm.ids[0])

    listed = document.list_files(firm.ids[0], firm.scope, session).data
    assert [(f.id, f.file_name, f.content_type, f.size_bytes) for f in listed] == [
        (file_id, "paper.pdf", "application/pdf", len(PDF))
    ]
    assert listed[0].caption == "customer PO 77"
    # It names this document and no other kind.
    named = {column: getattr(listed[0], column) for column in PARENT_COLUMNS}
    assert named.pop(document.column) == firm.ids[0]
    assert set(named.values()) == {None}

    response = document.download(firm.ids[0], file_id, firm.scope, session)
    assert response.body == PDF
    assert response.media_type == "application/pdf"
    assert 'filename="paper.pdf"' in response.headers["content-disposition"]
    assert response.headers["x-content-type-options"] == "nosniff"


@EVERY_DOCUMENT
def test_a_photo_is_accepted_too(name: str) -> None:
    """A PNG goes on beside the PDF, and both are listed oldest first."""
    document = DOCUMENTS[name]
    session = _session()
    firm = _firm(session, document)
    _upload(session, document, firm, firm.ids[0])
    photo = _upload(
        session, document, firm, firm.ids[0], PNG, "challan.png", "image/png"
    )
    assert len(_listed(session, document, firm)) == 2
    body = document.download(firm.ids[0], photo, firm.scope, session)
    assert body.body == PNG
    assert body.media_type == "image/png"


@EVERY_DOCUMENT
def test_a_file_over_ten_megabytes_is_refused(name: str) -> None:
    """The shared limit is refused by name on every document, and nothing kept."""
    document = DOCUMENTS[name]
    session = _session()
    firm = _firm(session, document)
    with pytest.raises(ValidationError, match="10 MB"):
        _upload(session, document, firm, firm.ids[0], PDF + b"\x00" * MAX_FILE_BYTES)
    assert _listed(session, document, firm) == []


@EVERY_DOCUMENT
@pytest.mark.parametrize(
    ("content", "file_name", "content_type"),
    [
        # An executable renamed and labelled as a PDF: its bytes give it away.
        (EXE, "paper.pdf", "application/pdf"),
        # Not one of the three types, by name and by declaration.
        (b"PK\x03\x04", "paper.docx", "application/zip"),
        # A PNG named as a PDF.
        (PNG, "paper.pdf", None),
        (b"", "paper.pdf", "application/pdf"),
    ],
)
def test_anything_but_a_pdf_jpg_or_png_is_refused(
    name: str, content: bytes, file_name: str, content_type: str | None
) -> None:
    """Name, declared type and first bytes must agree, on every document."""
    document = DOCUMENTS[name]
    session = _session()
    firm = _firm(session, document)
    with pytest.raises(ValidationError):
        _upload(session, document, firm, firm.ids[0], content, file_name, content_type)
    assert _listed(session, document, firm) == []


@EVERY_DOCUMENT
def test_another_firms_document_and_file_are_refused(name: str) -> None:
    """A firm can neither list, upload to, download nor delete another's."""
    document = DOCUMENTS[name]
    session = _session()
    mine = _firm(session, document)
    theirs = _firm(session, document)
    their_file = _upload(session, document, theirs, theirs.ids[0])

    with pytest.raises(ResourceNotFoundError):
        document.list_files(theirs.ids[0], mine.scope, session)
    with pytest.raises(ResourceNotFoundError):
        _upload(session, document, mine, theirs.ids[0])
    with pytest.raises(ResourceNotFoundError):
        document.download(theirs.ids[0], their_file, mine.scope, session)
    with pytest.raises(ResourceNotFoundError):
        document.delete(theirs.ids[0], their_file, mine.scope, session)
    # Their file named under my own document is not found either.
    with pytest.raises(ResourceNotFoundError):
        document.download(mine.ids[0], their_file, mine.scope, session)
    with pytest.raises(ResourceNotFoundError):
        document.delete(mine.ids[0], their_file, mine.scope, session)

    assert _listed(session, document, theirs) == [their_file]
    assert _listed(session, document, mine) == []


@EVERY_DOCUMENT
def test_a_file_belongs_to_one_document_of_its_kind(name: str) -> None:
    """A sibling document of the same firm does not carry or serve the file."""
    document = DOCUMENTS[name]
    session = _session()
    firm = _firm(session, document, rows=2)
    file_id = _upload(session, document, firm, firm.ids[0])

    assert document.list_files(firm.ids[1], firm.scope, session).data == []
    with pytest.raises(ResourceNotFoundError):
        document.download(firm.ids[1], file_id, firm.scope, session)
    with pytest.raises(ResourceNotFoundError):
        document.delete(firm.ids[1], file_id, firm.scope, session)
    assert _listed(session, document, firm) == [file_id]


def test_one_kinds_file_is_not_found_under_another_kind() -> None:
    """An order's file asked for through the invoice routes is not found."""
    session = _session()
    order = DOCUMENTS["sales order"]
    invoice = DOCUMENTS["sales invoice"]
    world = _world(session)
    CASES[order.page].seed(session, world, 1)
    CASES[invoice.page].seed(session, world, 1)
    session.commit()
    scope = _scope(world.firm)
    order_id = session.scalars(select(SalesOrder.id)).one()
    invoice_id = session.scalars(select(SalesInvoice.id)).one()
    firm = _Firm(world, scope, [order_id])
    file_id = _upload(session, order, firm, order_id)

    with pytest.raises(ResourceNotFoundError):
        invoice.download(invoice_id, file_id, scope, session)
    with pytest.raises(ResourceNotFoundError):
        invoice.delete(invoice_id, file_id, scope, session)
    # The order's id is not an invoice's id.
    with pytest.raises(ResourceNotFoundError):
        invoice.list_files(order_id, scope, session)
    assert invoice.list_files(invoice_id, scope, session).data == []


@EVERY_DOCUMENT
def test_removing_a_file_is_audited_and_hides_it(name: str) -> None:
    """A removed file leaves the list and the download, and the trail says so."""
    document = DOCUMENTS[name]
    session = _session()
    firm = _firm(session, document)
    file_id = _upload(session, document, firm, firm.ids[0])
    attached = session.scalar(
        select(AuditLog).where(
            AuditLog.action == "document_file.attached", AuditLog.entity_id == file_id
        )
    )
    assert attached is not None and attached.after_data is not None
    assert attached.after_data["document_type"] == document.parent.value
    assert attached.after_data["document_id"] == str(firm.ids[0])

    response = document.delete(firm.ids[0], file_id, firm.scope, session)
    assert response.status_code == 204
    assert _listed(session, document, firm) == []
    with pytest.raises(ResourceNotFoundError):
        document.download(firm.ids[0], file_id, firm.scope, session)
    removed = session.scalar(
        select(AuditLog).where(
            AuditLog.action == "document_file.removed", AuditLog.entity_id == file_id
        )
    )
    assert removed is not None and removed.before_data is not None
    assert removed.firm_id == firm.world.firm
    assert removed.actor_id == firm.scope.actor_id
    assert removed.before_data["document_type"] == document.parent.value
    assert removed.before_data["file_name"] == "paper.pdf"
    # Gone once: a second removal finds nothing to remove.
    with pytest.raises(ResourceNotFoundError):
        document.delete(firm.ids[0], file_id, firm.scope, session)


@EVERY_DOCUMENT
def test_the_list_row_and_the_document_carry_the_paper_clip_count(name: str) -> None:
    """Live files are counted per document; a removed one is not."""
    document = DOCUMENTS[name]
    case = CASES[document.page]
    session = _session()
    firm = _firm(session, document, rows=3)
    first = _upload(session, document, firm, firm.ids[0])
    _upload(session, document, firm, firm.ids[0], PNG, "photo.png", "image/png")
    _upload(session, document, firm, firm.ids[0], PDF, "second.pdf")
    _upload(session, document, firm, firm.ids[1])
    document.delete(firm.ids[0], first, firm.scope, session)
    session.expunge_all()

    page = case.page(session, firm.world).data
    assert {row.id: row.attached_file_count for row in page} == {
        firm.ids[0]: 2,
        firm.ids[1]: 1,
        firm.ids[2]: 0,
    }
    # The document on its own says the same as its row in the list.
    for row in page:
        assert case.alone(session, row).attached_file_count == row.attached_file_count


@EVERY_DOCUMENT
def test_a_page_costs_the_same_however_many_rows_carry_files(name: str) -> None:
    """The count is one read for the page: files on six rows cost what one does."""
    document = DOCUMENTS[name]
    case = CASES[document.page]

    def statements(with_files: int) -> int:
        """List six documents, ``with_files`` of them carrying two files each."""
        session = _session()
        firm = _firm(session, document, rows=6)
        for document_id in firm.ids[:with_files]:
            _upload(session, document, firm, document_id)
            _upload(session, document, firm, document_id, PNG, "p.png", "image/png")
        session.expunge_all()
        with _counting(session) as seen:
            page = case.page(session, firm.world).data
        assert sum(row.attached_file_count for row in page) == 2 * with_files
        counted = [text for text in seen if "FROM document_files" in text]
        assert len(counted) == 1, counted
        return len(seen)

    assert statements(0) == statements(1) == statements(6)


def test_no_file_is_read_to_count_a_page() -> None:
    """The count never touches the table that holds the bytes."""
    document = DOCUMENTS["sales invoice"]
    session = _session()
    firm = _firm(session, document, rows=2)
    _upload(session, document, firm, firm.ids[0])
    session.expunge_all()
    with _counting(session) as seen:
        counts = document_file_counts(session, document.parent, firm.ids)
    assert counts == {firm.ids[0]: 1}
    assert len(seen) == 1
    assert "document_file_contents" not in seen[0]


def test_every_kind_of_document_has_its_own_key() -> None:
    """Each ``FileParent`` names one distinct key, and no key goes unnamed."""
    columns = [kind.column for kind in _PARENTS.values()]
    assert set(_PARENTS) == set(FileParent)
    assert sorted(columns) == sorted(PARENT_COLUMNS)
    assert len(set(columns)) == len(columns)
    for column in columns:
        assert hasattr(DocumentFile, column)


@pytest.mark.parametrize("parents", [(), ("sales_order_id", "sales_invoice_id")])
def test_a_file_names_exactly_one_document(parents: tuple[str, ...]) -> None:
    """The store itself refuses a file with no document, or with two."""
    session = _session()
    world = _world(session)
    row = DocumentFile(
        firm_id=world.firm,
        file_name="paper.pdf",
        content_type="application/pdf",
        size_bytes=len(PDF),
        sha256="0" * 64,
    )
    for column in parents:
        setattr(row, column, world.branch)
    session.add(row)
    with pytest.raises(IntegrityError):
        session.flush()

"""The supplier's bill uploaded onto a purchase bill and a goods receipt (PG-4).

Covers the round trip (the bytes that come back are the bytes that went in),
refusal by size and by type -- including an executable renamed ``.pdf`` --
another firm's document and file refused, a removal audited and gone from the
list, and the paper-clip count on the list rows.
"""

import asyncio
import io
from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.datastructures import Headers, UploadFile

from app.common.audit.models import AuditLog
from app.common.scope import (
    ResolvedFirmScope,
    optional_firm_scope,
    required_firm_scope,
)
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.document_files.services import MAX_FILE_BYTES
from app.firms.models import Firm
from app.goods_receipt.api.router import (
    delete_goods_receipt_file,
    download_goods_receipt_file,
    list_goods_receipt_files,
    upload_goods_receipt_file,
)
from app.goods_receipt.models import GoodsReceipt
from app.goods_receipt.services import GoodsReceiptService
from app.identity.models import UserFirm
from app.purchase_invoice.api.router import (
    delete_purchase_invoice_file,
    download_purchase_invoice_file,
    list_purchase_invoice_files,
    upload_purchase_invoice_file,
)
from app.purchase_invoice.models import PurchaseInvoice
from app.purchase_invoice.services import PurchaseInvoiceService

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
EXE = b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 64


def _session() -> Session:
    """Build an isolated in-memory schema for one test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _principal(user_id: UUID) -> Principal:
    """Build a principal holding the purchase codes the routes ask for."""
    permissions = {"PURCHASE_VIEW", "PURCHASE_UPDATE", "PURCHASE_RECEIVE"}
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


class _Firm:
    """One firm, a member of it, and one bill and one receipt it owns."""

    def __init__(self, session: Session, code: str) -> None:
        """Create the firm and the two documents, bypassing their services."""
        self.firm = Firm(
            name=f"{code} Firm",
            code=code,
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
        )
        session.add(self.firm)
        session.flush()
        self.user_id = uuid4()
        session.add(
            UserFirm(user_id=self.user_id, firm_id=self.firm.id, is_active=True)
        )
        self.bill = PurchaseInvoice(
            firm_id=self.firm.id,
            vendor_id=uuid4(),
            branch_id=uuid4(),
            invoice_number=f"{code}-PI-1",
            invoice_date=date(2026, 10, 1),
            supplier_invoice_number="SUP-4412",
            supplier_invoice_date=date(2026, 9, 30),
        )
        self.receipt = GoodsReceipt(
            firm_id=self.firm.id,
            purchase_order_id=uuid4(),
            purchase_order_number=f"{code}-PO-1",
            vendor_id=uuid4(),
            branch_id=uuid4(),
            warehouse_id=uuid4(),
            grn_number=f"{code}-GRN-1",
            receipt_date=date(2026, 10, 1),
        )
        session.add_all([self.bill, self.receipt])
        session.commit()
        self.scope: ResolvedFirmScope = required_firm_scope(
            optional_firm_scope(
                principal=_principal(self.user_id), db=session, x_firm_id=self.firm.id
            )
        )


def _upload(content: bytes, name: str, content_type: str | None) -> UploadFile:
    """Build a multipart file part as a request would carry it."""
    headers = Headers({"content-type": content_type}) if content_type else None
    return UploadFile(io.BytesIO(content), filename=name, headers=headers)


def _bill_upload(
    session: Session,
    firm: _Firm,
    content: bytes,
    name: str = "bill.pdf",
    content_type: str | None = "application/pdf",
    bill_id: UUID | None = None,
) -> UUID:
    """Upload a file onto a bill through the route; return the file's id."""
    answer = asyncio.run(
        upload_purchase_invoice_file(
            bill_id or firm.bill.id,
            firm.scope,
            _upload(content, name, content_type),
            "supplier bill 4412",
            session,
        )
    )
    assert answer.data is not None
    return answer.data.id


def test_a_bill_file_round_trips_byte_for_byte() -> None:
    """What is downloaded is exactly what was uploaded, under its own name."""
    session = _session()
    firm = _Firm(session, "ONE")
    file_id = _bill_upload(session, firm, PDF)

    listed = list_purchase_invoice_files(firm.bill.id, firm.scope, session).data
    assert listed is not None
    assert [(f.id, f.file_name, f.content_type, f.size_bytes) for f in listed] == [
        (file_id, "bill.pdf", "application/pdf", len(PDF))
    ]
    assert listed[0].caption == "supplier bill 4412"

    response = download_purchase_invoice_file(
        firm.bill.id, file_id, firm.scope, session
    )
    assert response.body == PDF
    assert response.media_type == "application/pdf"
    assert 'filename="bill.pdf"' in response.headers["content-disposition"]


def test_a_receipt_takes_a_photo_too() -> None:
    """The goods receipt has the same four routes, and a PNG is accepted."""
    session = _session()
    firm = _Firm(session, "ONE")
    answer = asyncio.run(
        upload_goods_receipt_file(
            firm.receipt.id,
            firm.scope,
            _upload(PNG, "challan.png", "image/png"),
            None,
            session,
        )
    )
    assert answer.data is not None
    file_id = answer.data.id
    assert answer.data.goods_receipt_id == firm.receipt.id
    assert answer.data.purchase_invoice_id is None

    listed = list_goods_receipt_files(firm.receipt.id, firm.scope, session).data
    assert listed is not None and [f.id for f in listed] == [file_id]
    body = download_goods_receipt_file(firm.receipt.id, file_id, firm.scope, session)
    assert body.body == PNG
    assert body.media_type == "image/png"

    delete_goods_receipt_file(firm.receipt.id, file_id, firm.scope, session)
    assert list_goods_receipt_files(firm.receipt.id, firm.scope, session).data == []
    # A file on the receipt is not a file on the bill.
    assert list_purchase_invoice_files(firm.bill.id, firm.scope, session).data == []


def test_a_file_over_ten_megabytes_is_refused() -> None:
    """The limit is refused by name, and nothing is kept."""
    session = _session()
    firm = _Firm(session, "ONE")
    with pytest.raises(ValidationError, match="10 MB"):
        _bill_upload(session, firm, PDF + b"\x00" * MAX_FILE_BYTES)
    assert list_purchase_invoice_files(firm.bill.id, firm.scope, session).data == []


@pytest.mark.parametrize(
    ("content", "name", "content_type"),
    [
        # An executable renamed and labelled as a PDF: its bytes give it away.
        (EXE, "bill.pdf", "application/pdf"),
        (EXE, "bill.pdf", None),
        # Not one of the three types, by name and by declaration.
        (b"PK\x03\x04", "bill.docx", "application/zip"),
        (PDF, "bill.exe", "application/octet-stream"),
        # A real PDF declared as something else.
        (PDF, "bill.pdf", "image/png"),
        # A PNG named as a PDF.
        (PNG, "bill.pdf", None),
        (b"", "bill.pdf", "application/pdf"),
    ],
)
def test_anything_but_a_pdf_jpg_or_png_is_refused(
    content: bytes, name: str, content_type: str | None
) -> None:
    """Name, declared type and first bytes must all agree on an accepted type."""
    session = _session()
    firm = _Firm(session, "ONE")
    with pytest.raises(ValidationError):
        _bill_upload(session, firm, content, name=name, content_type=content_type)
    assert list_purchase_invoice_files(firm.bill.id, firm.scope, session).data == []


def test_another_firms_document_and_file_are_refused() -> None:
    """A firm can neither list, upload to, download nor delete another's."""
    session = _session()
    mine = _Firm(session, "ONE")
    theirs = _Firm(session, "TWO")
    their_file = _bill_upload(session, theirs, PDF)

    with pytest.raises(ResourceNotFoundError):
        list_purchase_invoice_files(theirs.bill.id, mine.scope, session)
    with pytest.raises(ResourceNotFoundError):
        _bill_upload(session, mine, PDF, bill_id=theirs.bill.id)
    with pytest.raises(ResourceNotFoundError):
        download_purchase_invoice_file(theirs.bill.id, their_file, mine.scope, session)
    # Their file named under my own bill is not found either.
    with pytest.raises(ResourceNotFoundError):
        download_purchase_invoice_file(mine.bill.id, their_file, mine.scope, session)
    with pytest.raises(ResourceNotFoundError):
        delete_purchase_invoice_file(mine.bill.id, their_file, mine.scope, session)
    with pytest.raises(ResourceNotFoundError):
        list_goods_receipt_files(theirs.receipt.id, mine.scope, session)

    listed = list_purchase_invoice_files(theirs.bill.id, theirs.scope, session).data
    assert listed is not None and [f.id for f in listed] == [their_file]


def test_removing_a_file_is_audited_and_hides_it() -> None:
    """A removed file leaves the list and the download, and the trail says so."""
    session = _session()
    firm = _Firm(session, "ONE")
    file_id = _bill_upload(session, firm, PDF)
    attached = session.scalar(
        select(AuditLog).where(
            AuditLog.action == "document_file.attached", AuditLog.entity_id == file_id
        )
    )
    assert attached is not None

    response = delete_purchase_invoice_file(firm.bill.id, file_id, firm.scope, session)
    assert response.status_code == 204
    assert list_purchase_invoice_files(firm.bill.id, firm.scope, session).data == []
    with pytest.raises(ResourceNotFoundError):
        download_purchase_invoice_file(firm.bill.id, file_id, firm.scope, session)
    removed = session.scalar(
        select(AuditLog).where(
            AuditLog.action == "document_file.removed", AuditLog.entity_id == file_id
        )
    )
    assert removed is not None
    assert removed.firm_id == firm.firm.id
    with pytest.raises(ResourceNotFoundError):
        delete_purchase_invoice_file(firm.bill.id, file_id, firm.scope, session)


def test_list_rows_carry_the_paper_clip_count() -> None:
    """A bill and a receipt say how many live files they carry."""
    session = _session()
    firm = _Firm(session, "ONE")
    first = _bill_upload(session, firm, PDF)
    _bill_upload(session, firm, PNG, name="photo.png", content_type="image/png")
    asyncio.run(
        upload_goods_receipt_file(
            firm.receipt.id,
            firm.scope,
            _upload(PDF, "challan.pdf", "application/pdf"),
            None,
            session,
        )
    )
    delete_purchase_invoice_file(firm.bill.id, first, firm.scope, session)

    bills = PurchaseInvoiceService(session).invoice_responses([firm.bill])
    receipts = GoodsReceiptService(session).receipt_responses([firm.receipt])
    assert bills[0].attached_file_count == 1
    assert receipts[0].attached_file_count == 1

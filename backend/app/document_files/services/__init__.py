"""Upload, list, download and remove files on documents (PG-4, SG-6).

One implementation for every document that takes uploads: the purchase bill
and the goods receipt (PG-4), and the sales quotation, order, delivery note,
invoice and return (SG-6). A new kind of document joins ``FileParent`` and
``_PARENTS`` and gains a nullable key on ``document_files``.

Decision recorded in ``docs/API_AND_PERSISTENCE_CONVENTIONS.md``: the bytes
live in the firm's own store, at most 10 MB a file, and only PDF, JPG and PNG.
A file's type is the one its first bytes name; the declared content type and
the file name's extension must both agree with it, so an ``.exe`` renamed
``.pdf`` is refused by its contents however it is labelled.
"""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePath
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.business.gating import assert_feature_fields
from app.common.audit.services import record_audit
from app.core.database.entity import BaseEntity
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.chunks import over_chunks
from app.core.utils.dates import utc_now
from app.delivery_note.models import DeliveryNote
from app.document_files.models import DocumentFile, DocumentFileContent
from app.goods_receipt.models import GoodsReceipt
from app.purchase_invoice.models import PurchaseInvoice
from app.quotation.models import SalesQuotation
from app.sales_invoice.models import SalesInvoice
from app.sales_order.models import SalesOrder
from app.sales_return.models import SalesReturn

#: The most one file may be. A phone photo of a bill is 2-5 MB; a scanned
#: multi-page PDF rarely passes 10.
MAX_FILE_BYTES = 10 * 1024 * 1024

#: What each accepted type's first bytes are.
_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)
_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}
#: Declared types that say nothing, so the extension is the declaration.
_UNSPECIFIC = {"", "application/octet-stream", "binary/octet-stream"}
_ALIASES = {"image/jpg": "image/jpeg", "image/pjpeg": "image/jpeg"}
_ENTITY = "document_file"


class FileParent(StrEnum):
    """The documents a file may be kept with."""

    PURCHASE_INVOICE = "PURCHASE_INVOICE"
    GOODS_RECEIPT = "GOODS_RECEIPT"
    SALES_QUOTATION = "SALES_QUOTATION"
    SALES_ORDER = "SALES_ORDER"
    DELIVERY_NOTE = "DELIVERY_NOTE"
    SALES_INVOICE = "SALES_INVOICE"
    SALES_RETURN = "SALES_RETURN"


@dataclass(frozen=True)
class _Parent:
    """How one kind of document is named on a file and found in the store."""

    #: The nullable key on ``document_files`` that points at it.
    column: str
    model: type[BaseEntity]
    #: What a refusal calls it.
    label: str


_PARENTS: dict[FileParent, _Parent] = {
    FileParent.PURCHASE_INVOICE: _Parent(
        "purchase_invoice_id", PurchaseInvoice, "Purchase invoice"
    ),
    FileParent.GOODS_RECEIPT: _Parent(
        "goods_receipt_id", GoodsReceipt, "Goods receipt"
    ),
    FileParent.SALES_QUOTATION: _Parent(
        "sales_quotation_id", SalesQuotation, "Quotation"
    ),
    FileParent.SALES_ORDER: _Parent("sales_order_id", SalesOrder, "Sales order"),
    FileParent.DELIVERY_NOTE: _Parent(
        "delivery_note_id", DeliveryNote, "Delivery note"
    ),
    FileParent.SALES_INVOICE: _Parent(
        "sales_invoice_id", SalesInvoice, "Sales invoice"
    ),
    FileParent.SALES_RETURN: _Parent("sales_return_id", SalesReturn, "Sales return"),
}


def _parent_column(parent: FileParent) -> InstrumentedAttribute[UUID | None]:
    """Name the foreign key that points at this kind of document."""
    column: InstrumentedAttribute[UUID | None] = getattr(
        DocumentFile, _PARENTS[parent].column
    )
    return column


def file_content_type(
    content: bytes, *, file_name: str, declared_type: str | None
) -> str:
    """Name the file's type from its bytes, refusing anything not agreed on.

    Args:
        content: The whole upload.
        file_name: The name the client gave; its extension must match.
        declared_type: The multipart part's content type, if any.

    Returns:
        The content type to store and serve the file under.

    Raises:
        ValidationError: The file is empty, too large, or not a PDF, JPG or
            PNG by its name, its declared type or its contents.

    """
    if not content:
        raise ValidationError("The file is empty.")
    if len(content) > MAX_FILE_BYTES:
        raise ValidationError(
            f"The file is {len(content) / (1024 * 1024):.1f} MB; the most a file "
            "may be is 10 MB."
        )
    extension = PurePath(file_name).suffix.lower()
    named = _EXTENSIONS.get(extension)
    if named is None:
        raise ValidationError(
            "Only PDF, JPG and PNG files may be attached; "
            f"'{file_name}' is not one by its name."
        )
    declared = (declared_type or "").split(";")[0].strip().lower()
    declared = _ALIASES.get(declared, declared)
    if declared not in _UNSPECIFIC and declared != named:
        raise ValidationError(
            f"'{file_name}' was sent as {declared}, which does not match its name."
        )
    found = next(
        (kind for magic, kind in _SIGNATURES if content.startswith(magic)), None
    )
    if found is None:
        raise ValidationError(
            f"'{file_name}' is not a PDF, JPG or PNG file by its contents."
        )
    if found != named:
        raise ValidationError(
            f"'{file_name}' is named as {named} but its contents are {found}."
        )
    return found


@over_chunks("document_ids")
def document_file_counts(
    session: Session, parent: FileParent, document_ids: Sequence[UUID]
) -> dict[UUID, int]:
    """Count the live uploaded files on each document, in one grouped read.

    This is what puts ``attached_file_count`` on a list page: one statement
    for the page, whatever its length and however many rows carry files.
    """
    if not document_ids:
        return {}
    column = _parent_column(parent)
    rows = session.execute(
        select(column, func.count(DocumentFile.id))
        .where(column.in_(document_ids), DocumentFile.is_deleted.is_(False))
        .group_by(column)
    )
    return {found: int(count) for found, count in rows if found is not None}


def purchase_invoice_file_counts(
    session: Session, purchase_invoice_ids: Sequence[UUID]
) -> dict[UUID, int]:
    """Count the live uploaded files on each bill, in one grouped read."""
    return document_file_counts(
        session, FileParent.PURCHASE_INVOICE, purchase_invoice_ids
    )


def goods_receipt_file_counts(
    session: Session, goods_receipt_ids: Sequence[UUID]
) -> dict[UUID, int]:
    """Count the live uploaded files on each goods receipt, in one grouped read."""
    return document_file_counts(session, FileParent.GOODS_RECEIPT, goods_receipt_ids)


class DocumentFileService:
    """Keep uploaded files with their documents, in the firm's own store."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request's firm store."""
        self._session = session

    def list_files(
        self, parent: FileParent, document_id: UUID, *, firm_id: UUID
    ) -> list[DocumentFile]:
        """Return the live files on one document, oldest first."""
        self._parent_id(parent, document_id, firm_id=firm_id)
        return list(
            self._session.scalars(
                select(DocumentFile)
                .where(
                    _parent_column(parent) == document_id,
                    DocumentFile.firm_id == firm_id,
                    DocumentFile.is_deleted.is_(False),
                )
                .order_by(DocumentFile.created_at.asc(), DocumentFile.id.asc())
            )
        )

    def attach(
        self,
        parent: FileParent,
        document_id: UUID,
        *,
        file_name: str,
        declared_type: str | None,
        content: bytes,
        caption: str | None,
        firm_id: UUID,
        actor_id: UUID,
    ) -> DocumentFile:
        """Check, store and audit one uploaded file, then commit."""
        name = PurePath((file_name or "").replace("\\", "/")).name.strip()
        if not name:
            raise ValidationError("The file has no name.")
        if len(name) > 260:
            raise ValidationError("The file name is longer than 260 characters.")
        cleaned_caption = (caption or "").strip() or None
        if cleaned_caption is not None and len(cleaned_caption) > 200:
            raise ValidationError("The caption is longer than 200 characters.")
        assert_feature_fields(
            self._session, firm_id, feature="ATTACHMENTS", values={"file": name}
        )
        self._parent_id(parent, document_id, firm_id=firm_id)
        content_type = file_content_type(
            content, file_name=name, declared_type=declared_type
        )
        row = DocumentFile(
            firm_id=firm_id,
            file_name=name,
            content_type=content_type,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            caption=cleaned_caption,
            created_by=actor_id,
            updated_by=actor_id,
        )
        setattr(row, _PARENTS[parent].column, document_id)
        self._session.add(row)
        self._session.flush()
        self._session.add(DocumentFileContent(file_id=row.id, content=content))
        record_audit(
            self._session,
            action="document_file.attached",
            entity_type=_ENTITY,
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data=self._snapshot(row, parent, document_id),
        )
        self._session.commit()
        return row

    def download(
        self,
        parent: FileParent,
        document_id: UUID,
        file_id: UUID,
        *,
        firm_id: UUID,
    ) -> tuple[DocumentFile, bytes]:
        """Return one live file and its bytes."""
        row = self._file(parent, document_id, file_id, firm_id=firm_id)
        content = self._session.scalar(
            select(DocumentFileContent.content).where(
                DocumentFileContent.file_id == row.id
            )
        )
        if content is None:
            raise ResourceNotFoundError("The file's contents were not found.")
        return row, bytes(content)

    def remove(
        self,
        parent: FileParent,
        document_id: UUID,
        file_id: UUID,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> None:
        """Soft-delete one file and audit it, then commit.

        The bytes stay, as a soft-deleted row's columns do everywhere else, so
        the trail's record that the file was there can still be followed.
        """
        row = self._file(parent, document_id, file_id, firm_id=firm_id)
        before = self._snapshot(row, parent, document_id)
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="document_file.removed",
            entity_type=_ENTITY,
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
        )
        self._session.commit()

    # ---- internals -------------------------------------------------------

    def _parent_id(
        self, parent: FileParent, document_id: UUID, *, firm_id: UUID
    ) -> UUID:
        """Find the document in this firm, or refuse as not found.

        Another firm's document is "not found" rather than "forbidden", so the
        answer does not confirm that the id exists anywhere.
        """
        kind = _PARENTS[parent]
        columns = kind.model.__table__.c
        found: UUID | None = self._session.scalar(
            select(columns.id).where(
                columns.id == document_id,
                columns.firm_id == firm_id,
                columns.is_deleted.is_(False),
            )
        )
        if found is None:
            raise ResourceNotFoundError(f"{kind.label} not found.")
        return found

    def _file(
        self,
        parent: FileParent,
        document_id: UUID,
        file_id: UUID,
        *,
        firm_id: UUID,
    ) -> DocumentFile:
        """Return one live file on this firm's document, or refuse."""
        self._parent_id(parent, document_id, firm_id=firm_id)
        row = self._session.scalar(
            select(DocumentFile).where(
                DocumentFile.id == file_id,
                _parent_column(parent) == document_id,
                DocumentFile.firm_id == firm_id,
                DocumentFile.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("File not found.")
        return row

    @staticmethod
    def _snapshot(
        row: DocumentFile, parent: FileParent, document_id: UUID
    ) -> dict[str, object]:
        """Describe a file for the trail; the bytes are named by their hash."""
        return {
            "document_type": parent.value,
            "document_id": str(document_id),
            "file_name": row.file_name,
            "content_type": row.content_type,
            "size_bytes": row.size_bytes,
            "sha256": row.sha256,
            "caption": row.caption,
        }


__all__ = [
    "MAX_FILE_BYTES",
    "DocumentFileService",
    "FileParent",
    "document_file_counts",
    "file_content_type",
    "goods_receipt_file_counts",
    "purchase_invoice_file_counts",
]

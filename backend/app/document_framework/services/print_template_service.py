"""Read and write the per-firm print template."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.document_framework.models import DocumentPrintTemplate
from app.document_framework.schemas import (
    DocumentPrintTemplateResponse,
    DocumentPrintTemplateWrite,
)

#: What a firm gets before it configures anything. Kept here rather than in the
#: database so a new firm needs no seeding to print a correct bill.
PLATFORM_DEFAULTS = DocumentPrintTemplateWrite(
    declaration=(
        "Certified that the particulars given above are true, and that the "
        "amount charged is the price actually payable."
    )
)


class DocumentPrintTemplateService:
    """One template per firm per document type."""

    def __init__(self, session: Session) -> None:
        """Keep the tenant session the template lives on."""
        self._session = session

    def get(
        self, document_type: str, *, firm_scope: UUID
    ) -> DocumentPrintTemplateResponse:
        """Return the firm's template, falling back to the platform default."""
        row = self._row(document_type, firm_scope=firm_scope)
        if row is None:
            return DocumentPrintTemplateResponse(
                document_type=document_type.upper(),
                is_customised=False,
                **PLATFORM_DEFAULTS.model_dump(),
            )
        return self._response(row)

    def set(
        self,
        document_type: str,
        data: DocumentPrintTemplateWrite,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> DocumentPrintTemplateResponse:
        """Create or replace the firm's template for one document type."""
        code = document_type.upper()
        row = self._row(code, firm_scope=firm_scope)
        values = data.model_dump()
        if row is None:
            row = DocumentPrintTemplate(
                firm_id=firm_scope,
                document_type=code,
                created_by=actor_id,
                updated_by=actor_id,
                **values,
            )
            self._session.add(row)
            action = "document_print_template.created"
        else:
            for field, value in values.items():
                setattr(row, field, value)
            row.updated_by = actor_id
            action = "document_print_template.updated"
        self._session.flush()
        record_audit(
            self._session,
            action=action,
            entity_type="document_print_template",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={"document_type": code},
        )
        return self._response(row)

    # ------------------------------------------------------------------
    def _row(
        self, document_type: str, *, firm_scope: UUID
    ) -> DocumentPrintTemplate | None:
        """Return the stored template, if the firm has saved one."""
        return self._session.scalar(
            select(DocumentPrintTemplate).where(
                DocumentPrintTemplate.firm_id == firm_scope,
                DocumentPrintTemplate.document_type == document_type.upper(),
                DocumentPrintTemplate.is_deleted.is_(False),
            )
        )

    @staticmethod
    def _response(row: DocumentPrintTemplate) -> DocumentPrintTemplateResponse:
        """Build the response for a stored template."""
        return DocumentPrintTemplateResponse(
            id=row.id,
            document_type=row.document_type,
            is_customised=True,
            title_text=row.title_text,
            accent_color=row.accent_color,
            header_note=row.header_note,
            show_bank_details=row.show_bank_details,
            bank_details=row.bank_details,
            terms=row.terms,
            declaration=row.declaration,
            jurisdiction=row.jurisdiction,
            footer_note=row.footer_note,
            signatory_text=row.signatory_text,
            show_discount_column=row.show_discount_column,
            show_batch_column=row.show_batch_column,
            show_expiry_column=row.show_expiry_column,
            copy_labels=list(row.copy_labels or []),
            page_size=row.page_size,
            margin_mm=row.margin_mm,
        )

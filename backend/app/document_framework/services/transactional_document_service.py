"""Shared base for the transactional document modules.

The seven document services (purchase order, goods receipt, purchase invoice,
purchase return, sales order, delivery note, sales invoice) are ~18,000 lines
that overlap heavily: purchase_invoice and purchase_return are ~90% identical,
purchase_invoice and sales_invoice ~83%. Each carried its own copy of the same
lifecycle plumbing, and the copies drifted — different rounding, three financial
year formats, four ``_flush_or_conflict`` variants of which three left the
session unusable after a failure.

This base holds the parts that are genuinely the same, parameterised by a
``DocumentTypeSpec`` describing what the module's document *is*. Behaviour that
differs per module — line construction, totals, source matching, reports — stays
in the module.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.branches.models import Branch
from app.core.exceptions import ConflictError, ResourceNotFoundError
from app.core.utils.dates import financial_year_label
from app.core.utils.money import quantize_money
from app.document_framework.models import (
    DocumentNumberingRule,
    DocumentStateDefinition,
    DocumentTypeDefinition,
)
from app.document_framework.schemas import (
    DocumentLifecycleEventCreate,
    DocumentNumberingRuleCreate,
    DocumentStateCreate,
    DocumentTypeCreate,
)
from app.document_framework.services.document_framework_service import (
    DocumentFrameworkService,
)
from app.firms.models import Firm


@dataclass(frozen=True, slots=True)
class DocumentStateSpec:
    """One lifecycle state a document type may occupy."""

    code: str
    name: str
    sort_order: int
    is_terminal: bool = False
    allows_edit: bool = False


@dataclass(frozen=True, slots=True)
class DocumentTypeSpec:
    """Everything the framework needs to bootstrap a module's document type."""

    code: str
    name: str
    description: str
    category: str
    module: str
    prefix: str
    states: tuple[DocumentStateSpec, ...]
    include_branch_code: bool = False
    sequence_padding: int = 6
    rule_code: str = field(default="")
    rule_name: str = field(default="")

    @property
    def numbering_code(self) -> str:
        """Return the numbering rule code, defaulted from the type code."""
        return self.rule_code or f"{self.code}_DEFAULT"

    @property
    def numbering_name(self) -> str:
        """Return the numbering rule name, defaulted from the type name."""
        return self.rule_name or f"{self.name} Default"

    @property
    def default_state(self) -> str:
        """Return the state a new document starts in."""
        return self.states[0].code


class TransactionalDocumentService:
    """Lifecycle plumbing shared by every transactional document module."""

    DOCUMENT: DocumentTypeSpec

    def __init__(self, session: Session) -> None:
        """Bind the service to a session it does not own."""
        self._session = session
        self._documents = DocumentFrameworkService(session)

    # ---- money and dates -------------------------------------------------

    @staticmethod
    def _q(value: Decimal | int | str | None) -> Decimal:
        """Round a monetary amount to the shared storage scale.

        Args:
            value: The amount to round; ``None`` is treated as zero.

        Returns:
            The amount quantized by :func:`quantize_money`.

        """
        return quantize_money(value)

    def _financial_year_label(self, on: date, firm_id: UUID) -> str:
        """Return the firm's financial-year label for a document date.

        Args:
            on: The document date.
            firm_id: The owning firm, whose ``financial_year_start`` decides
                when the year begins.

        Returns:
            The shared ``YYYY-YYYY`` label.

        """
        start_month = self._session.scalar(
            select(Firm.financial_year_start).where(Firm.id == firm_id)
        )
        return financial_year_label(
            on, start_month=start_month.month if start_month is not None else 4
        )

    # ---- scope codes -----------------------------------------------------

    def _scope_code(self, branch_id: UUID | None) -> str | None:
        """Return the branch's own code for document numbering.

        Several modules fabricated this from the first eight characters of the
        branch UUID, which made their document numbers incomparable with the
        modules that used the real code.

        Args:
            branch_id: The branch to resolve, if any.

        Returns:
            The upper-cased branch code, or None.

        """
        if branch_id is None:
            return None
        code = self._session.scalar(select(Branch.code).where(Branch.id == branch_id))
        return code.upper() if code else None

    def _company_code(self, firm_id: UUID) -> str | None:
        """Return the firm's own code for document numbering."""
        code = self._session.scalar(select(Firm.code).where(Firm.id == firm_id))
        return code.upper() if code else None

    # ---- persistence helpers ---------------------------------------------

    def _flush_or_conflict(self, message: str) -> None:
        """Flush pending work, converting a unique-key clash into a conflict.

        The rollback matters: without it a failed flush leaves the session
        unusable for every statement that follows.

        Args:
            message: The conflict message surfaced to the caller.

        Raises:
            ConflictError: If the flush violates a database constraint.

        """
        try:
            self._session.flush()
        except IntegrityError as error:
            self._session.rollback()
            raise ConflictError(message) from error

    # ---- document type bootstrap -----------------------------------------

    def _document_type(self, firm_id: UUID) -> DocumentTypeDefinition:
        """Return this module's document type for a firm.

        Raises:
            ResourceNotFoundError: If the type has not been created yet.

        """
        row = self._session.scalar(
            select(DocumentTypeDefinition).where(
                DocumentTypeDefinition.firm_id == firm_id,
                DocumentTypeDefinition.code == self.DOCUMENT.code,
                DocumentTypeDefinition.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError(
                f"{self.DOCUMENT.name} document type is not configured."
            )
        return row

    def _state_exists(
        self, *, firm_id: UUID, document_type_id: UUID, code: str
    ) -> bool:
        """Return whether a lifecycle state is already defined."""
        return (
            self._session.scalar(
                select(DocumentStateDefinition.id).where(
                    DocumentStateDefinition.firm_id == firm_id,
                    DocumentStateDefinition.document_type_id == document_type_id,
                    DocumentStateDefinition.code == code,
                    DocumentStateDefinition.is_deleted.is_(False),
                )
            )
            is not None
        )

    def _ensure_document_setup(
        self, *, firm_id: UUID, actor_id: UUID
    ) -> tuple[DocumentTypeDefinition, DocumentNumberingRule]:
        """Create this module's document type, states and numbering on demand.

        Each module bootstrapped these lazily on first create with its own
        ~84-line copy of this method. Seeding them per firm would be better
        still, but that is a data-migration question; this at least makes the
        behaviour single-sourced.

        Args:
            firm_id: The owning firm.
            actor_id: The user whose action triggered the bootstrap.

        Returns:
            The document type and its default numbering rule.

        """
        spec = self.DOCUMENT
        document_type = self._session.scalar(
            select(DocumentTypeDefinition).where(
                DocumentTypeDefinition.firm_id == firm_id,
                DocumentTypeDefinition.code == spec.code,
                DocumentTypeDefinition.is_deleted.is_(False),
            )
        )
        if document_type is None:
            document_type = self._documents.create_type(
                firm_id,
                DocumentTypeCreate(
                    code=spec.code,
                    name=spec.name,
                    description=spec.description,
                    category=spec.category,
                    is_active=True,
                    configuration={"module": spec.module},
                ),
                actor_id,
            )
        for state in spec.states:
            if self._state_exists(
                firm_id=firm_id, document_type_id=document_type.id, code=state.code
            ):
                continue
            self._documents.create_state(
                firm_id,
                DocumentStateCreate(
                    document_type_id=document_type.id,
                    code=state.code,
                    name=state.name,
                    sort_order=state.sort_order,
                    is_default=state.code == spec.default_state,
                    is_terminal=state.is_terminal,
                    allows_edit=state.allows_edit,
                    allows_print=True,
                    allows_email=True,
                    allows_export_pdf=True,
                    transition_rules={"module": spec.module, "state": state.code},
                    is_active=True,
                ),
                actor_id,
            )
        numbering_rule = self._session.scalar(
            select(DocumentNumberingRule).where(
                DocumentNumberingRule.firm_id == firm_id,
                DocumentNumberingRule.document_type_id == document_type.id,
                DocumentNumberingRule.is_deleted.is_(False),
            )
        )
        if numbering_rule is None:
            numbering_rule = self._documents.create_numbering_rule(
                firm_id,
                DocumentNumberingRuleCreate(
                    document_type_id=document_type.id,
                    code=spec.numbering_code,
                    name=spec.numbering_name,
                    prefix=spec.prefix,
                    suffix=None,
                    separator="-",
                    include_financial_year=True,
                    include_branch_code=spec.include_branch_code,
                    include_company_code=False,
                    auto_reset=True,
                    manual_allowed=False,
                    sequence_padding=spec.sequence_padding,
                    next_sequence=1,
                    is_default=True,
                    is_active=True,
                    configuration={"module": spec.module},
                ),
                actor_id,
            )
        return document_type, numbering_rule

    # ---- lifecycle events -------------------------------------------------

    def _record_lifecycle_event(
        self,
        *,
        firm_id: UUID,
        document_type: DocumentTypeDefinition,
        document_id: UUID,
        document_number: str,
        action: str,
        from_state: str | None,
        to_state: str | None,
        actor_id: UUID,
        remarks: str | None = None,
        details: dict[str, object] | None = None,
        snapshot: dict[str, object] | None = None,
    ) -> None:
        """Append one lifecycle event for a document."""
        self._documents.record_event(
            firm_id,
            DocumentLifecycleEventCreate(
                document_type_id=document_type.id,
                source_document_id=document_id,
                source_module_code=self.DOCUMENT.code,
                document_number=document_number,
                action=action,
                from_state=from_state,
                to_state=to_state,
                remarks=remarks,
                details_json=details or {},
                snapshot_json=snapshot or {},
                actor_id=actor_id,
            ),
            actor_id,
        )

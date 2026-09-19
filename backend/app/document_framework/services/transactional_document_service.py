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
from sqlalchemy.orm import InstrumentedAttribute, Session, class_mapper

from app.branches.models import Branch
from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
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
    include_company_code: bool = False
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
        self._firms = FirmMetadataReader(session)

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
        starts_on = self._firms.get(firm_id).financial_year_start
        return financial_year_label(
            on, start_month=starts_on.month if starts_on is not None else 4
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
        code = self._firms.get(firm_id).code
        return code.upper() if code else None

    def _scope_codes(
        self, *, firm_id: UUID, branch_id: UUID | None
    ) -> tuple[str | None, str | None]:
        """Return the branch and company codes, checking branch ownership.

        The branch must belong to the firm: a document number must never be
        stamped with another firm's branch code.

        Args:
            firm_id: The owning firm.
            branch_id: The branch to resolve, if any.

        Returns:
            A ``(branch_code, company_code)`` pair, either of which may be None.

        """
        branch_code: str | None = None
        if branch_id is not None:
            code = self._session.scalar(
                select(Branch.code).where(
                    Branch.id == branch_id,
                    Branch.firm_id == firm_id,
                    Branch.is_deleted.is_(False),
                )
            )
            branch_code = code.upper() if code else None
        return branch_code, self._company_code(firm_id)

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
                    include_company_code=spec.include_company_code,
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

    # ---- document numbers -------------------------------------------------

    #: How many already-used numbers one save steps over before giving up. A
    #: handful is a collision; hundreds would be a misconfigured series, and
    #: the refusal then says so rather than spinning.
    MAX_NUMBER_SKIPS = 50

    def _issue_number(
        self,
        numbering_rule: DocumentNumberingRule,
        *,
        typed: str | None,
        number_column: InstrumentedAttribute[str],
        firm_id: UUID,
        document_date: date,
        actor_id: UUID,
        branch_code: str | None = None,
        company_code: str | None = None,
    ) -> str:
        """Return the number a new document is created under.

        A number typed by the caller is taken only when the series says one
        may be (``manual_allowed``, off by default); otherwise it is refused
        by name. Every create used to accept whatever it was sent, so the
        switch meant nothing (D-CFG-2).

        A number the series issues steps over any number already held -- by a
        document of this type (deleted ones included, since the unique keys
        count them) or by a journal, whose references are unique per firm. A
        number typed ahead of the counter used to be issued again when the
        counter reached it; the insert failed, the failure rolled the
        reservation back, and every retry was handed the same number. The
        series now keeps a gap there instead, as a cancelled voucher leaves
        one. This is the step-over #500 gave settlements, for every module.

        Args:
            numbering_rule: The series this document type is numbered from.
            typed: The number the caller sent, already normalised the way the
                module stores it, or ``None`` when it sent none.
            number_column: The column holding this document type's numbers.
            firm_id: The owning firm.
            document_date: The document's own date, which picks the year.
            actor_id: The user creating the document.
            branch_code: The branch code, for a series that prints it.
            company_code: The firm code, for a series that prints it.

        Returns:
            The document number.

        Raises:
            ValidationError: A number was typed into a series that does not
                allow it, or the next ``MAX_NUMBER_SKIPS`` numbers are all
                taken.

        """
        if typed:
            if not numbering_rule.manual_allowed:
                raise ValidationError(
                    f"The numbering series {numbering_rule.code} does not allow a "
                    "number to be typed in. Leave the number blank and the next "
                    "number in the series is issued, or allow typed numbers on "
                    "the series first."
                )
            return typed
        label = self._financial_year_label(document_date, firm_id)
        for _ in range(self.MAX_NUMBER_SKIPS):
            number = self._documents.reserve_number(
                numbering_rule.id,
                firm_id=firm_id,
                financial_year_label=label,
                branch_code=branch_code,
                company_code=company_code,
                document_date=document_date,
                actor_id=actor_id,
            )
            if not self._number_taken(number_column, number, firm_id=firm_id):
                return number
        raise ValidationError(
            f"The next {self.MAX_NUMBER_SKIPS} numbers of the series "
            f"{numbering_rule.code} are all in use already. Check the series: "
            "its counter is behind numbers the firm has already used."
        )

    def _number_taken(
        self, number_column: InstrumentedAttribute[str], number: str, *, firm_id: UUID
    ) -> bool:
        """Say whether a document or a journal of the firm already holds a number.

        Deleted documents count: the unique keys on document numbers are not
        partial. Journals count because documents post under their own
        numbers, and a journal reference is unique per firm.
        """
        # Imported here: finance is a domain this framework otherwise does not
        # depend on, and finance depends on the document modules.
        from app.finance.models import JournalEntry

        owner = number_column.class_
        document = self._session.scalar(
            select(number_column)
            .where(owner.firm_id == firm_id, number_column == number)
            .limit(1)
        )
        if document is not None:
            return True
        journal = self._session.scalar(
            select(JournalEntry.id)
            .where(
                JournalEntry.firm_id == firm_id,
                JournalEntry.reference_number == number,
            )
            .limit(1)
        )
        return journal is not None

    # ---- child rows -------------------------------------------------------

    def _apply_line_values(
        self,
        target: object,
        source: object,
        *,
        actor_id: UUID,
        preserve: tuple[str, ...] = (),
    ) -> None:
        """Copy a freshly built line's values onto the persisted row.

        Document updates used to delete every line and re-insert it, which minted
        a new UUID per line on every save. Downstream documents record
        ``source_document_line_id`` as a bare UUID with no foreign key, so those
        references silently dangled after an upstream edit.

        Callers still build a transient line exactly as before; this transfers
        its column values onto the existing row so the identity survives.

        Args:
            target: The persisted line to update.
            source: A transient line carrying the new values.
            actor_id: The user performing the edit.
            preserve: Columns on ``target`` that must not be overwritten, such
                as quantities the document accrues rather than restates.

        """
        skip = {
            "id",
            "created_at",
            "created_by",
            "updated_at",
            "updated_by",
            "is_deleted",
            "deleted_at",
            "deleted_by",
            "version",
            *preserve,
        }
        for attribute in class_mapper(type(target)).column_attrs:
            if attribute.key in skip:
                continue
            setattr(target, attribute.key, getattr(source, attribute.key))
        target.updated_by = actor_id  # type: ignore[attr-defined]

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

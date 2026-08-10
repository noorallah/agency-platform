"""Reusable document lifecycle framework services."""

# ruff: noqa: D102, D107

from datetime import date
from typing import Protocol
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ConflictError, ResourceNotFoundError
from app.core.utils.dates import utc_now
from app.document_framework.models import (
    DocumentLifecycleEvent,
    DocumentNumberingRule,
    DocumentNumberSequence,
    DocumentStateDefinition,
    DocumentTypeDefinition,
)
from app.document_framework.schemas import (
    DocumentLifecycleEventCreate,
    DocumentNumberingRuleCreate,
    DocumentNumberingRuleUpdate,
    DocumentStateCreate,
    DocumentStateUpdate,
    DocumentTypeCreate,
    DocumentTypeUpdate,
)


class DocumentApprovalEngine(Protocol):
    """Placeholder approval engine interface for future orchestration."""

    def request_approval(self, document_id: UUID) -> None: ...

    def approve(self, document_id: UUID, actor_id: UUID) -> None: ...

    def reject(
        self, document_id: UUID, actor_id: UUID, remarks: str | None = None
    ) -> None: ...


class DocumentPrintService(Protocol):
    """Placeholder print service interface."""

    def record_print(
        self, document_id: UUID, actor_id: UUID, printer_name: str | None = None
    ) -> None: ...


class DocumentEmailService(Protocol):
    """Placeholder email service interface."""

    def prepare_email(
        self, document_id: UUID, recipient: str | None = None
    ) -> None: ...


class DocumentPdfService(Protocol):
    """Placeholder PDF service interface."""

    def generate_pdf(
        self, document_id: UUID, template_code: str | None = None
    ) -> None: ...


class DocumentFrameworkService:
    """Manage reusable document catalogs, numbering, and lifecycle history."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_types(
        self,
        firm_id: UUID,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
    ) -> tuple[list[DocumentTypeDefinition], int]:
        columns = {
            "code": DocumentTypeDefinition.code,
            "name": DocumentTypeDefinition.name,
            "created_at": DocumentTypeDefinition.created_at,
        }
        statement = select(DocumentTypeDefinition).where(
            DocumentTypeDefinition.firm_id == firm_id,
            DocumentTypeDefinition.is_deleted.is_(False),
        )
        count = (
            select(func.count())
            .select_from(DocumentTypeDefinition)
            .where(
                DocumentTypeDefinition.firm_id == firm_id,
                DocumentTypeDefinition.is_deleted.is_(False),
            )
        )
        if search:
            token = search.strip()
            condition = or_(
                DocumentTypeDefinition.code.ilike(f"%{token}%"),
                DocumentTypeDefinition.name.ilike(f"%{token}%"),
                DocumentTypeDefinition.category.ilike(f"%{token}%"),
            )
            statement = statement.where(condition)
            count = count.where(condition)
        ordering = columns[sort_by].desc() if descending else columns[sort_by].asc()
        rows = self._session.scalars(
            statement.order_by(ordering).offset((page - 1) * page_size).limit(page_size)
        ).all()
        return list(rows), int(self._session.scalar(count) or 0)

    def create_type(
        self, firm_id: UUID, data: DocumentTypeCreate, actor_id: UUID
    ) -> DocumentTypeDefinition:
        self._assert_unique_type(firm_id, data.code)
        row = DocumentTypeDefinition(
            firm_id=firm_id,
            **data.model_dump(),
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        record_audit(
            self._session,
            action="document_type.created",
            entity_type="document_type_definition",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"code": row.code, "name": row.name},
        )
        return row

    def get_type(self, firm_id: UUID, type_id: UUID) -> DocumentTypeDefinition:
        row = self._session.scalar(
            select(DocumentTypeDefinition).where(
                DocumentTypeDefinition.id == type_id,
                DocumentTypeDefinition.firm_id == firm_id,
                DocumentTypeDefinition.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Document type not found.")
        return row

    def update_type(
        self, firm_id: UUID, type_id: UUID, data: DocumentTypeUpdate, actor_id: UUID
    ) -> DocumentTypeDefinition:
        row = self.get_type(firm_id, type_id)
        self._assert_unique_type(firm_id, data.code, current_id=row.id)
        before: dict[str, object] = {
            "code": row.code,
            "name": row.name,
            "category": row.category,
        }
        for field, value in data.model_dump().items():
            setattr(row, field, value)
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="document_type.updated",
            entity_type="document_type_definition",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
        )
        return row

    def delete_type(self, firm_id: UUID, type_id: UUID, actor_id: UUID) -> None:
        row = self.get_type(firm_id, type_id)
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="document_type.deleted",
            entity_type="document_type_definition",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
        )

    def list_states(
        self,
        firm_id: UUID,
        page: int,
        page_size: int,
        search: str | None,
        document_type_id: UUID | None,
        sort_by: str,
        descending: bool,
    ) -> tuple[list[DocumentStateDefinition], int]:
        columns = {
            "code": DocumentStateDefinition.code,
            "name": DocumentStateDefinition.name,
            "sort_order": DocumentStateDefinition.sort_order,
            "created_at": DocumentStateDefinition.created_at,
        }
        statement = select(DocumentStateDefinition).where(
            DocumentStateDefinition.firm_id == firm_id,
            DocumentStateDefinition.is_deleted.is_(False),
        )
        count = (
            select(func.count())
            .select_from(DocumentStateDefinition)
            .where(
                DocumentStateDefinition.firm_id == firm_id,
                DocumentStateDefinition.is_deleted.is_(False),
            )
        )
        if document_type_id is not None:
            statement = statement.where(
                DocumentStateDefinition.document_type_id == document_type_id
            )
            count = count.where(
                DocumentStateDefinition.document_type_id == document_type_id
            )
        if search:
            token = search.strip()
            condition = or_(
                DocumentStateDefinition.code.ilike(f"%{token}%"),
                DocumentStateDefinition.name.ilike(f"%{token}%"),
                DocumentStateDefinition.description.ilike(f"%{token}%"),
            )
            statement = statement.where(condition)
            count = count.where(condition)
        ordering = columns[sort_by].desc() if descending else columns[sort_by].asc()
        rows = self._session.scalars(
            statement.order_by(ordering).offset((page - 1) * page_size).limit(page_size)
        ).all()
        return list(rows), int(self._session.scalar(count) or 0)

    def create_state(
        self, firm_id: UUID, data: DocumentStateCreate, actor_id: UUID
    ) -> DocumentStateDefinition:
        self._assert_unique_state(firm_id, data.document_type_id, data.code)
        row = DocumentStateDefinition(
            firm_id=firm_id,
            **data.model_dump(),
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        record_audit(
            self._session,
            action="document_state.created",
            entity_type="document_state_definition",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "code": row.code,
                "document_type_id": str(row.document_type_id),
            },
        )
        return row

    def get_state(self, firm_id: UUID, state_id: UUID) -> DocumentStateDefinition:
        row = self._session.scalar(
            select(DocumentStateDefinition).where(
                DocumentStateDefinition.id == state_id,
                DocumentStateDefinition.firm_id == firm_id,
                DocumentStateDefinition.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Document state not found.")
        return row

    def update_state(
        self, firm_id: UUID, state_id: UUID, data: DocumentStateUpdate, actor_id: UUID
    ) -> DocumentStateDefinition:
        row = self.get_state(firm_id, state_id)
        self._assert_unique_state(
            firm_id, data.document_type_id, data.code, current_id=row.id
        )
        before = {"code": row.code, "name": row.name, "sort_order": row.sort_order}
        for field, value in data.model_dump().items():
            setattr(row, field, value)
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="document_state.updated",
            entity_type="document_state_definition",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
        )
        return row

    def delete_state(self, firm_id: UUID, state_id: UUID, actor_id: UUID) -> None:
        row = self.get_state(firm_id, state_id)
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="document_state.deleted",
            entity_type="document_state_definition",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
        )

    def list_numbering_rules(
        self,
        firm_id: UUID,
        page: int,
        page_size: int,
        search: str | None,
        document_type_id: UUID | None,
        sort_by: str,
        descending: bool,
    ) -> tuple[list[DocumentNumberingRule], int]:
        columns = {
            "code": DocumentNumberingRule.code,
            "name": DocumentNumberingRule.name,
            "next_sequence": DocumentNumberingRule.next_sequence,
            "created_at": DocumentNumberingRule.created_at,
        }
        statement = select(DocumentNumberingRule).where(
            DocumentNumberingRule.firm_id == firm_id,
            DocumentNumberingRule.is_deleted.is_(False),
        )
        count = (
            select(func.count())
            .select_from(DocumentNumberingRule)
            .where(
                DocumentNumberingRule.firm_id == firm_id,
                DocumentNumberingRule.is_deleted.is_(False),
            )
        )
        if document_type_id is not None:
            statement = statement.where(
                DocumentNumberingRule.document_type_id == document_type_id
            )
            count = count.where(
                DocumentNumberingRule.document_type_id == document_type_id
            )
        if search:
            token = search.strip()
            condition = or_(
                DocumentNumberingRule.code.ilike(f"%{token}%"),
                DocumentNumberingRule.name.ilike(f"%{token}%"),
                DocumentNumberingRule.prefix.ilike(f"%{token}%"),
                DocumentNumberingRule.suffix.ilike(f"%{token}%"),
            )
            statement = statement.where(condition)
            count = count.where(condition)
        ordering = columns[sort_by].desc() if descending else columns[sort_by].asc()
        rows = self._session.scalars(
            statement.order_by(ordering).offset((page - 1) * page_size).limit(page_size)
        ).all()
        return list(rows), int(self._session.scalar(count) or 0)

    def create_numbering_rule(
        self, firm_id: UUID, data: DocumentNumberingRuleCreate, actor_id: UUID
    ) -> DocumentNumberingRule:
        self._assert_unique_numbering_rule(firm_id, data.document_type_id, data.code)
        row = DocumentNumberingRule(
            firm_id=firm_id,
            **data.model_dump(),
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        record_audit(
            self._session,
            action="document_numbering_rule.created",
            entity_type="document_numbering_rule",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "code": row.code,
                "document_type_id": str(row.document_type_id),
            },
        )
        return row

    def get_numbering_rule(
        self, firm_id: UUID, rule_id: UUID, *, for_update: bool = False
    ) -> DocumentNumberingRule:
        """Load one numbering rule, optionally locking it for allocation.

        Args:
            firm_id: The owning firm.
            rule_id: The rule to load.
            for_update: Take a row lock, so two concurrent allocations of the
                next sequence cannot read the same value. SQLite ignores the
                clause, which is why the unit suite cannot catch a collision.

        Returns:
            The numbering rule.

        Raises:
            ResourceNotFoundError: If no such rule exists for the firm.

        """
        statement = select(DocumentNumberingRule).where(
            DocumentNumberingRule.id == rule_id,
            DocumentNumberingRule.firm_id == firm_id,
            DocumentNumberingRule.is_deleted.is_(False),
        )
        if for_update:
            statement = statement.with_for_update()
        row = self._session.scalar(statement)
        if row is None:
            raise ResourceNotFoundError("Document numbering rule not found.")
        return row

    def update_numbering_rule(
        self,
        firm_id: UUID,
        rule_id: UUID,
        data: DocumentNumberingRuleUpdate,
        actor_id: UUID,
    ) -> DocumentNumberingRule:
        row = self.get_numbering_rule(firm_id, rule_id)
        self._assert_unique_numbering_rule(
            firm_id, data.document_type_id, data.code, current_id=row.id
        )
        before = {
            "code": row.code,
            "name": row.name,
            "next_sequence": row.next_sequence,
        }
        for field, value in data.model_dump().items():
            setattr(row, field, value)
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="document_numbering_rule.updated",
            entity_type="document_numbering_rule",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
        )
        return row

    def delete_numbering_rule(
        self, firm_id: UUID, rule_id: UUID, actor_id: UUID
    ) -> None:
        row = self.get_numbering_rule(firm_id, rule_id)
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="document_numbering_rule.deleted",
            entity_type="document_numbering_rule",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
        )

    # Document dates default to utc_now().date(), not date.today(): the
    # server's local date decides which day -- and which financial year --
    # a document number belongs to, and everything else here is UTC.
    def preview_number(
        self,
        rule_id: UUID,
        *,
        firm_id: UUID,
        financial_year_label: str | None = None,
        branch_code: str | None = None,
        company_code: str | None = None,
        document_date: date | None = None,
        manual_number: str | None = None,
    ) -> str:
        rule = self.get_numbering_rule(firm_id, rule_id)
        return self._build_document_number(
            rule,
            financial_year_label=financial_year_label,
            branch_code=branch_code,
            company_code=company_code,
            document_date=document_date or utc_now().date(),
            manual_number=manual_number,
        )

    def reserve_number(
        self,
        rule_id: UUID,
        *,
        firm_id: UUID,
        financial_year_label: str | None = None,
        branch_code: str | None = None,
        company_code: str | None = None,
        document_date: date | None = None,
        manual_number: str | None = None,
        actor_id: UUID | None = None,
    ) -> str:
        rule = self.get_numbering_rule(firm_id, rule_id, for_update=True)
        scope_signature = self._scope_signature(
            financial_year_label=financial_year_label,
            branch_code=branch_code,
            company_code=company_code,
            document_date=document_date or utc_now().date(),
        )
        counter = self._sequence_for(rule, scope_signature, actor_id=actor_id)
        number = self._build_document_number(
            rule,
            financial_year_label=financial_year_label,
            branch_code=branch_code,
            company_code=company_code,
            document_date=document_date or utc_now().date(),
            manual_number=manual_number,
        )
        if manual_number is not None and rule.manual_allowed:
            return number
        counter.next_sequence += 1
        # Kept in step so anything reading the rule still sees a sensible
        # number, and so a rule that has never been used starts where it says.
        rule.next_sequence = counter.next_sequence
        rule.last_scope_signature = scope_signature
        if actor_id is not None:
            rule.updated_by = actor_id
            counter.updated_by = actor_id
        return number

    def _sequence_for(
        self,
        rule: DocumentNumberingRule,
        scope_signature: str,
        *,
        actor_id: UUID | None,
    ) -> DocumentNumberSequence:
        """Return this scope's counter, creating it the first time it is used.

        A scope not seen before starts at the rule's configured
        ``next_sequence`` when the rule has never issued anything, and at 1
        otherwise -- a new financial year begins at one, which is the point of
        ``auto_reset``.
        """
        counter = self._session.scalar(
            select(DocumentNumberSequence)
            .where(
                DocumentNumberSequence.numbering_rule_id == rule.id,
                DocumentNumberSequence.scope_signature == scope_signature,
                DocumentNumberSequence.is_deleted.is_(False),
            )
            .with_for_update()
        )
        if counter is not None:
            return counter
        start = 1 if rule.last_scope_signature else rule.next_sequence
        counter = DocumentNumberSequence(
            firm_id=rule.firm_id,
            numbering_rule_id=rule.id,
            scope_signature=scope_signature,
            next_sequence=max(start, 1),
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(counter)
        self._session.flush()
        return counter

    def record_event(
        self, firm_id: UUID, data: DocumentLifecycleEventCreate, actor_id: UUID
    ) -> DocumentLifecycleEvent:
        self.get_type(firm_id, data.document_type_id)
        payload = data.model_dump(exclude={"actor_id"})
        row = DocumentLifecycleEvent(
            firm_id=firm_id,
            **payload,
            actor_id=data.actor_id or actor_id,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def list_timeline(
        self,
        firm_id: UUID,
        document_id: UUID,
        page: int,
        page_size: int,
        sort_direction: bool,
    ) -> tuple[list[DocumentLifecycleEvent], int]:
        statement = select(DocumentLifecycleEvent).where(
            DocumentLifecycleEvent.firm_id == firm_id,
            DocumentLifecycleEvent.source_document_id == document_id,
            DocumentLifecycleEvent.is_deleted.is_(False),
        )
        count = (
            select(func.count())
            .select_from(DocumentLifecycleEvent)
            .where(
                DocumentLifecycleEvent.firm_id == firm_id,
                DocumentLifecycleEvent.source_document_id == document_id,
                DocumentLifecycleEvent.is_deleted.is_(False),
            )
        )
        ordering = (
            DocumentLifecycleEvent.occurred_at.desc()
            if sort_direction
            else DocumentLifecycleEvent.occurred_at.asc()
        )
        rows = self._session.scalars(
            statement.order_by(ordering).offset((page - 1) * page_size).limit(page_size)
        ).all()
        return list(rows), int(self._session.scalar(count) or 0)

    def _assert_unique_type(
        self, firm_id: UUID, code: str, *, current_id: UUID | None = None
    ) -> None:
        statement = select(DocumentTypeDefinition.id).where(
            DocumentTypeDefinition.firm_id == firm_id,
            DocumentTypeDefinition.code == code,
            DocumentTypeDefinition.is_deleted.is_(False),
        )
        if current_id is not None:
            statement = statement.where(DocumentTypeDefinition.id != current_id)
        existing = self._session.scalar(statement)
        if existing is not None:
            raise ConflictError("A document type with this code already exists.")

    def _assert_unique_state(
        self,
        firm_id: UUID,
        document_type_id: UUID,
        code: str,
        *,
        current_id: UUID | None = None,
    ) -> None:
        statement = select(DocumentStateDefinition.id).where(
            DocumentStateDefinition.firm_id == firm_id,
            DocumentStateDefinition.document_type_id == document_type_id,
            DocumentStateDefinition.code == code,
            DocumentStateDefinition.is_deleted.is_(False),
        )
        if current_id is not None:
            statement = statement.where(DocumentStateDefinition.id != current_id)
        existing = self._session.scalar(statement)
        if existing is not None:
            raise ConflictError("A document state with this code already exists.")

    def _assert_unique_numbering_rule(
        self,
        firm_id: UUID,
        document_type_id: UUID,
        code: str,
        *,
        current_id: UUID | None = None,
    ) -> None:
        statement = select(DocumentNumberingRule.id).where(
            DocumentNumberingRule.firm_id == firm_id,
            DocumentNumberingRule.document_type_id == document_type_id,
            DocumentNumberingRule.code == code,
            DocumentNumberingRule.is_deleted.is_(False),
        )
        if current_id is not None:
            statement = statement.where(DocumentNumberingRule.id != current_id)
        existing = self._session.scalar(statement)
        if existing is not None:
            raise ConflictError("A numbering rule with this code already exists.")

    def _build_document_number(
        self,
        rule: DocumentNumberingRule,
        *,
        financial_year_label: str | None,
        branch_code: str | None,
        company_code: str | None,
        document_date: date,
        manual_number: str | None = None,
    ) -> str:
        if manual_number is not None and rule.manual_allowed:
            return manual_number.strip()
        scope_signature = self._scope_signature(
            financial_year_label=financial_year_label,
            branch_code=branch_code,
            company_code=company_code,
            document_date=document_date,
        )
        counter = self._session.scalar(
            select(DocumentNumberSequence).where(
                DocumentNumberSequence.numbering_rule_id == rule.id,
                DocumentNumberSequence.scope_signature == scope_signature,
                DocumentNumberSequence.is_deleted.is_(False),
            )
        )
        if counter is not None:
            sequence = counter.next_sequence
        else:
            sequence = 1 if rule.last_scope_signature else rule.next_sequence
        if rule.format_pattern:
            return rule.format_pattern.format(
                prefix=rule.prefix or "",
                suffix=rule.suffix or "",
                separator=rule.separator,
                sequence=str(sequence).zfill(rule.sequence_padding),
                financial_year=financial_year_label or str(document_date.year),
                branch_code=branch_code or "",
                company_code=company_code or "",
                document_date=document_date.isoformat(),
            )
        parts: list[str] = []
        if rule.prefix:
            parts.append(rule.prefix)
        if rule.include_company_code and company_code:
            parts.append(company_code)
        if rule.include_branch_code and branch_code:
            parts.append(branch_code)
        if rule.include_financial_year:
            parts.append(financial_year_label or str(document_date.year))
        parts.append(str(sequence).zfill(rule.sequence_padding))
        if rule.suffix:
            parts.append(rule.suffix)
        return rule.separator.join(parts)

    def _scope_signature(
        self,
        *,
        financial_year_label: str | None,
        branch_code: str | None,
        company_code: str | None,
        document_date: date,
    ) -> str:
        return "|".join(
            [
                financial_year_label or str(document_date.year),
                branch_code or "",
                company_code or "",
            ]
        )

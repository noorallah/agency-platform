"""Approval in up to three levels by amount, and rejection (PLT-1, A131).

A firm says, per document type, which roles sign off at which level from
which amount: an order from 1 lakh needs the branch manager (level 1), from
5 lakh the finance head too (level 2). Levels are signed in order, a person
signs one level of a document, and the module's own *Approve* goes through
only once every level the total calls for is signed:

* someone who can sign the last level still open approves in one step, as
  before -- a firm with no rules sees no change at all;
* anyone else is refused, naming the level and roles still needed; they
  *Sign off* their level instead, and the document waits for the next;
* the sign-off that completes the chain approves the document.

A sign-off counts only while the total is no more than it was signed at, so
raising an order after its first sign-off asks for it again. *Reject* needs a
reason, clears the sign-offs and sends a submitted purchase order back to
draft; it can be done for many documents at once. A platform administrator is
not limited, as with the other approval limits.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.approvals.models import ApprovalDecision, ApprovalRule
from app.common.audit.services import record_audit
from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import (
    ApplicationError,
    ResourceNotFoundError,
    ValidationError,
)
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO, quantize_ledger

PLATFORM_ADMIN = "platform_admin"


@dataclass(frozen=True)
class DocumentKind:
    """How one approvable document type is read."""

    model_path: str
    number_field: str
    approve_code: str
    settings_code: str
    #: The statuses a document waits for approval in.
    waiting: tuple[str, ...]
    label: str


KINDS: dict[str, DocumentKind] = {
    "SALES_ORDER": DocumentKind(
        "app.sales_order.models:SalesOrder",
        "order_number",
        "SALES_APPROVE",
        "SALES_MANAGE_SETTINGS",
        ("DRAFT",),
        "Sales order",
    ),
    "SALES_INVOICE": DocumentKind(
        "app.sales_invoice.models:SalesInvoice",
        "invoice_number",
        "SALES_APPROVE",
        "SALES_MANAGE_SETTINGS",
        ("DRAFT",),
        "Sales invoice",
    ),
    "PURCHASE_ORDER": DocumentKind(
        "app.purchase.models:PurchaseOrder",
        "po_number",
        "PURCHASE_APPROVE",
        "PURCHASE_MANAGE_SETTINGS",
        ("SUBMITTED",),
        "Purchase order",
    ),
    "PURCHASE_INVOICE": DocumentKind(
        "app.purchase_invoice.models:PurchaseInvoice",
        "invoice_number",
        "PURCHASE_APPROVE",
        "PURCHASE_MANAGE_SETTINGS",
        ("DRAFT",),
        "Purchase invoice",
    ),
}


def _model(kind: DocumentKind) -> Any:  # noqa: ANN401 -- one of four models
    """Import a document model by its dotted path."""
    import importlib

    module, name = kind.model_path.split(":")
    return getattr(importlib.import_module(module), name)


def kind_of(document_type: str) -> DocumentKind:
    """Return an approvable document type, refusing any other."""
    found = KINDS.get(document_type)
    if found is None:
        raise ValidationError(
            f"{document_type} has no approval rules; one of "
            + ", ".join(sorted(KINDS))
            + "."
        )
    return found


class ApprovalRuleWrite(BaseModel):
    """One role's sign-off at one level, from an amount up."""

    model_config = ConfigDict(extra="forbid")

    level: int = Field(ge=1, le=3)
    min_amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    role_code: str = Field(min_length=1, max_length=100)


class ApprovalRulesWrite(BaseModel):
    """Every rule of one document type, replacing what is there."""

    model_config = ConfigDict(extra="forbid")

    rules: list[ApprovalRuleWrite] = Field(default_factory=list, max_length=60)


class ApprovalRuleResponse(BaseModel):
    """One rule."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    document_type: str
    level: int
    min_amount: Decimal
    role_code: str


class ApprovalStep(BaseModel):
    """One level a document needs, and whether it is signed."""

    model_config = ConfigDict(extra="forbid")

    level: int
    roles: list[str]
    signed_by: UUID | None
    signed_at: str | None


class ApprovalStatusResponse(BaseModel):
    """Where one document stands in its chain."""

    model_config = ConfigDict(extra="forbid")

    document_type: str
    document_id: UUID
    document_number: str
    amount: Decimal
    status: str
    steps: list[ApprovalStep]
    #: The lowest level still unsigned, or None when nothing is owed.
    next_level: int | None
    rejected_reason: str | None
    rejected_at: str | None


class ApprovalDecisionWrite(BaseModel):
    """Sign off or reject one document."""

    model_config = ConfigDict(extra="forbid")

    document_type: str = Field(min_length=1, max_length=30)
    document_id: UUID
    remarks: str | None = Field(default=None, max_length=1000)


class ApprovalRejectWrite(BaseModel):
    """Reject one document; a reason is required."""

    model_config = ConfigDict(extra="forbid")

    document_type: str = Field(min_length=1, max_length=30)
    document_id: UUID
    reason: str = Field(min_length=1, max_length=1000)


class ApprovalChainService:
    """Rules, sign-offs, rejections and the queue of what awaits a person."""

    def __init__(self, session: Session) -> None:
        """Bind to the caller's session."""
        self._session = session

    # ---- rules ---------------------------------------------------------

    def rules(
        self, firm_id: UUID, document_type: str | None = None
    ) -> list[ApprovalRule]:
        """Return the firm's live rules, by type, level and amount."""
        query = select(ApprovalRule).where(
            ApprovalRule.firm_id == firm_id,
            ApprovalRule.is_deleted.is_(False),
            ApprovalRule.is_active.is_(True),
        )
        if document_type is not None:
            query = query.where(ApprovalRule.document_type == document_type)
        return list(
            self._session.scalars(
                query.order_by(
                    ApprovalRule.document_type,
                    ApprovalRule.level,
                    ApprovalRule.min_amount,
                    ApprovalRule.role_code,
                )
            ).all()
        )

    def replace_rules(
        self,
        firm_id: UUID,
        document_type: str,
        data: ApprovalRulesWrite,
        *,
        actor_id: UUID,
    ) -> list[ApprovalRule]:
        """Replace one document type's rules; commit.

        Raises:
            ValidationError: If a level is used without the one below it, or a
                rule is stated twice.

        """
        kind_of(document_type)
        levels = {rule.level for rule in data.rules}
        missing = [level for level in levels if level > 1 and (level - 1) not in levels]
        if missing:
            raise ValidationError(
                f"Level {min(missing)} needs a level {min(missing) - 1} below it."
            )
        seen: set[tuple[int, Decimal, str]] = set()
        for rule in data.rules:
            key = (rule.level, rule.min_amount, rule.role_code.strip().upper())
            if key in seen:
                raise ValidationError("A rule is stated twice.")
            seen.add(key)
        now = utc_now()
        for old in self.rules(firm_id, document_type):
            old.is_deleted = True
            old.deleted_at = now
            old.deleted_by = actor_id
        rows = [
            ApprovalRule(
                firm_id=firm_id,
                document_type=document_type,
                level=rule.level,
                min_amount=rule.min_amount,
                role_code=rule.role_code.strip(),
                created_by=actor_id,
                updated_by=actor_id,
            )
            for rule in data.rules
        ]
        self._session.add_all(rows)
        record_audit(
            self._session,
            action="approval_rules.replaced",
            entity_type="approval_rules",
            entity_id=firm_id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "document_type": document_type,
                "rules": [
                    {
                        "level": r.level,
                        "min_amount": str(r.min_amount),
                        "role_code": r.role_code,
                    }
                    for r in data.rules
                ],
            },
        )
        self._session.commit()
        return self.rules(firm_id, document_type)

    # ---- the chain -----------------------------------------------------

    def required(
        self, firm_id: UUID, document_type: str, amount: Decimal
    ) -> dict[int, set[str]]:
        """Return the levels a total calls for, each with the roles that sign it."""
        needed: dict[int, set[str]] = {}
        for rule in self.rules(firm_id, document_type):
            if Decimal(str(rule.min_amount)) <= amount:
                needed.setdefault(rule.level, set()).add(rule.role_code.upper())
        return dict(sorted(needed.items()))

    def _signed(
        self, firm_id: UUID, document_type: str, document_id: UUID, amount: Decimal
    ) -> dict[int, ApprovalDecision]:
        """Return the sign-offs that still count, by level."""
        rows = self._session.scalars(
            select(ApprovalDecision).where(
                ApprovalDecision.firm_id == firm_id,
                ApprovalDecision.document_type == document_type,
                ApprovalDecision.document_id == document_id,
                ApprovalDecision.decision == "APPROVED",
                ApprovalDecision.is_deleted.is_(False),
            )
        ).all()
        return {
            row.level: row
            for row in rows
            if Decimal(str(row.amount)) >= quantize_ledger(amount)
        }

    def _roles(self, firm_id: UUID, actor_id: UUID) -> frozenset[str]:
        """Return the actor's role codes in the firm, upper-cased."""
        return frozenset(
            code.upper()
            for code in FirmMetadataReader(self._session).role_codes(firm_id, actor_id)
        )

    def assert_cleared(
        self,
        firm_id: UUID,
        document_type: str,
        document_id: UUID,
        amount: Decimal,
        actor_id: UUID,
    ) -> None:
        """Let an approval through only once its chain is signed; stages, never commits.

        The person approving may sign the one level still open, which is how
        a single-level rule, or the last level of a longer one, is approved
        in one step.

        Raises:
            ValidationError: Naming the level and roles still needed.

        """
        total = quantize_ledger(Decimal(str(amount)))
        needed = self.required(firm_id, document_type, total)
        if not needed:
            return
        roles = self._roles(firm_id, actor_id)
        signed = self._signed(firm_id, document_type, document_id, total)
        open_levels = [level for level in needed if level not in signed]
        if not open_levels:
            return
        if PLATFORM_ADMIN.upper() in roles:
            for level in open_levels:
                self._record(
                    firm_id, document_type, document_id, level, total, actor_id
                )
            return
        first = open_levels[0]
        already = any(row.decided_by == actor_id for row in signed.values())
        if len(open_levels) == 1 and not already and roles & needed[first]:
            self._record(firm_id, document_type, document_id, first, total, actor_id)
            return
        raise ValidationError(
            f"This needs a level {first} sign-off by "
            + " or ".join(sorted(needed[first]))
            + (
                f" ({len(open_levels)} levels still open)"
                if len(open_levels) > 1
                else ""
            )
            + " before it can be approved."
        )

    def sign_off(
        self,
        data: ApprovalDecisionWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
        approve: Callable[[], object],
    ) -> ApprovalStatusResponse:
        """Sign the next level; approve the document when that completes it.

        The sign-off is committed first, so an approval the module then
        refuses -- a price floor, a credit limit -- keeps the signature and
        says why the document is still waiting.

        Raises:
            ValidationError: If nothing is owed, the actor signed a level
                already or holds none of the next level's roles.

        """
        kind = kind_of(data.document_type)
        document = self.document(kind, data.document_id, firm_id)
        total = quantize_ledger(Decimal(str(document.grand_total)))
        if document.status not in kind.waiting:
            raise ValidationError(
                f"This {kind.label.lower()} is not awaiting approval."
            )
        needed = self.required(firm_id, data.document_type, total)
        signed = self._signed(firm_id, data.document_type, document.id, total)
        open_levels = [level for level in needed if level not in signed]
        if not open_levels:
            raise ValidationError("Every level is signed; approve it instead.")
        roles = self._roles(firm_id, actor_id)
        if any(row.decided_by == actor_id for row in signed.values()):
            raise ValidationError("You signed an earlier level of this document.")
        first = open_levels[0]
        if not roles & needed[first] and PLATFORM_ADMIN.upper() not in roles:
            raise ValidationError(
                f"Level {first} is signed by "
                + " or ".join(sorted(needed[first]))
                + "."
            )
        self._record(
            firm_id,
            data.document_type,
            document.id,
            first,
            total,
            actor_id,
            remarks=data.remarks,
        )
        self._session.commit()
        if len(open_levels) == 1:
            try:
                approve()
            except ApplicationError:
                # The signature stands; the approval it completed did not.
                self._session.rollback()
                raise
        return self.status(data.document_type, document.id, firm_id=firm_id)

    def reject(
        self, data: ApprovalRejectWrite, *, firm_id: UUID, actor_id: UUID
    ) -> ApprovalStatusResponse:
        """Refuse a document with a reason; clear its sign-offs; commit.

        A submitted purchase order goes back to draft; the others are drafts
        already and stay so, marked rejected until they are changed.

        Raises:
            ValidationError: If it is not awaiting approval, or the actor
                holds none of the roles of its next level.

        """
        kind = kind_of(data.document_type)
        document = self.document(kind, data.document_id, firm_id)
        if document.status not in kind.waiting:
            raise ValidationError(
                f"This {kind.label.lower()} is not awaiting approval."
            )
        reason = data.reason.strip()
        if not reason:
            raise ValidationError("Say why it is rejected.")
        total = quantize_ledger(Decimal(str(document.grand_total)))
        needed = self.required(firm_id, data.document_type, total)
        signed = self._signed(firm_id, data.document_type, document.id, total)
        open_levels = [level for level in needed if level not in signed]
        level = open_levels[0] if open_levels else 0
        if level:
            roles = self._roles(firm_id, actor_id)
            if not roles & needed[level] and PLATFORM_ADMIN.upper() not in roles:
                raise ValidationError(
                    f"Level {level} is decided by "
                    + " or ".join(sorted(needed[level]))
                    + "."
                )
        now = utc_now()
        for row in self._session.scalars(
            select(ApprovalDecision).where(
                ApprovalDecision.firm_id == firm_id,
                ApprovalDecision.document_type == data.document_type,
                ApprovalDecision.document_id == document.id,
                ApprovalDecision.is_deleted.is_(False),
            )
        ).all():
            row.is_deleted = True
            row.deleted_at = now
            row.deleted_by = actor_id
        self._session.flush()
        self._session.add(
            ApprovalDecision(
                firm_id=firm_id,
                document_type=data.document_type,
                document_id=document.id,
                level=level,
                decision="REJECTED",
                amount=total,
                decided_by=actor_id,
                decided_at=now,
                remarks=reason,
                created_by=actor_id,
                updated_by=actor_id,
            )
        )
        if data.document_type == "PURCHASE_ORDER":
            document.status = "DRAFT"
        document.updated_by = actor_id
        record_audit(
            self._session,
            action="approval.rejected",
            entity_type=data.document_type.lower(),
            entity_id=document.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"level": level, "reason": reason},
        )
        self._session.commit()
        return self.status(data.document_type, document.id, firm_id=firm_id)

    # ---- reads ---------------------------------------------------------

    def status(
        self, document_type: str, document_id: UUID, *, firm_id: UUID
    ) -> ApprovalStatusResponse:
        """Return where one document stands in its chain."""
        kind = kind_of(document_type)
        document = self.document(kind, document_id, firm_id)
        total = quantize_ledger(Decimal(str(document.grand_total)))
        needed = self.required(firm_id, document_type, total)
        signed = self._signed(firm_id, document_type, document.id, total)
        open_levels = [level for level in needed if level not in signed]
        rejected = self._last_rejection(firm_id, document_type, document.id)
        return ApprovalStatusResponse(
            document_type=document_type,
            document_id=document.id,
            document_number=str(getattr(document, kind.number_field)),
            amount=total,
            status=document.status,
            steps=[
                ApprovalStep(
                    level=level,
                    roles=sorted(roles),
                    signed_by=signed[level].decided_by if level in signed else None,
                    signed_at=(
                        signed[level].decided_at.isoformat()
                        if level in signed
                        else None
                    ),
                )
                for level, roles in needed.items()
            ],
            next_level=open_levels[0] if open_levels else None,
            rejected_reason=rejected.remarks if rejected is not None else None,
            rejected_at=(
                rejected.decided_at.isoformat() if rejected is not None else None
            ),
        )

    def pending_for(
        self, firm_id: UUID, actor_id: UUID, *, approve_codes: set[str]
    ) -> list[ApprovalStatusResponse]:
        """Return what awaits this person's sign-off, oldest first.

        A document is listed when its next open level is one the person's
        roles sign, they signed no earlier level, and it was not rejected
        since it was last changed. Only the types whose approve code they
        hold are read.
        """
        roles = self._roles(firm_id, actor_id)
        answer: list[ApprovalStatusResponse] = []
        for document_type, kind in KINDS.items():
            if kind.approve_code not in approve_codes:
                continue
            if not self.rules(firm_id, document_type):
                continue
            model = _model(kind)
            for document in self._session.scalars(
                select(model)
                .where(
                    model.firm_id == firm_id,
                    model.is_deleted.is_(False),
                    model.status.in_(kind.waiting),
                )
                .order_by(model.created_at)
                .limit(500)
            ).all():
                total = quantize_ledger(Decimal(str(document.grand_total)))
                needed = self.required(firm_id, document_type, total)
                if not needed:
                    continue
                signed = self._signed(firm_id, document_type, document.id, total)
                open_levels = [level for level in needed if level not in signed]
                if not open_levels:
                    continue
                if any(row.decided_by == actor_id for row in signed.values()):
                    continue
                if not roles & needed[open_levels[0]] and (
                    PLATFORM_ADMIN.upper() not in roles
                ):
                    continue
                rejected = self._last_rejection(firm_id, document_type, document.id)
                if rejected is not None and rejected.decided_at >= document.updated_at:
                    continue
                answer.append(self.status(document_type, document.id, firm_id=firm_id))
        return answer

    def awaiting_count(self, firm_id: UUID) -> int:
        """Count documents part-way through a chain, for the bell."""
        rows = self._session.execute(
            select(ApprovalDecision.document_type, ApprovalDecision.document_id)
            .where(
                ApprovalDecision.firm_id == firm_id,
                ApprovalDecision.decision == "APPROVED",
                ApprovalDecision.is_deleted.is_(False),
            )
            .distinct()
        ).all()
        count = 0
        for document_type, document_id in rows:
            kind = KINDS.get(document_type)
            if kind is None:
                continue
            document = self._session.get(_model(kind), document_id)
            if document is not None and document.status in kind.waiting:
                count += 1
        return count

    # ---- helpers -------------------------------------------------------

    def document(
        self, kind: DocumentKind, document_id: UUID, firm_id: UUID
    ) -> Any:  # noqa: ANN401 -- one of four document models
        """Return one of the firm's documents of a kind."""
        document = self._session.get(_model(kind), document_id)
        if document is None or document.is_deleted or document.firm_id != firm_id:
            raise ResourceNotFoundError(f"{kind.label} not found.")
        return document

    def _last_rejection(
        self, firm_id: UUID, document_type: str, document_id: UUID
    ) -> ApprovalDecision | None:
        """Return the latest live rejection of a document."""
        return self._session.scalar(
            select(ApprovalDecision)
            .where(
                ApprovalDecision.firm_id == firm_id,
                ApprovalDecision.document_type == document_type,
                ApprovalDecision.document_id == document_id,
                ApprovalDecision.decision == "REJECTED",
                ApprovalDecision.is_deleted.is_(False),
            )
            .order_by(ApprovalDecision.decided_at.desc())
            .limit(1)
        )

    def _record(
        self,
        firm_id: UUID,
        document_type: str,
        document_id: UUID,
        level: int,
        amount: Decimal,
        actor_id: UUID,
        *,
        remarks: str | None = None,
    ) -> None:
        """Stage one sign-off, replacing a stale one at the same level."""
        now = utc_now()
        for stale in self._session.scalars(
            select(ApprovalDecision).where(
                ApprovalDecision.firm_id == firm_id,
                ApprovalDecision.document_type == document_type,
                ApprovalDecision.document_id == document_id,
                ApprovalDecision.level == level,
                ApprovalDecision.decision == "APPROVED",
                ApprovalDecision.is_deleted.is_(False),
            )
        ).all():
            stale.is_deleted = True
            stale.deleted_at = now
            stale.deleted_by = actor_id
        self._session.flush()
        self._session.add(
            ApprovalDecision(
                firm_id=firm_id,
                document_type=document_type,
                document_id=document_id,
                level=level,
                decision="APPROVED",
                amount=amount if amount > ZERO else ZERO,
                decided_by=actor_id,
                decided_at=now,
                remarks=remarks,
                created_by=actor_id,
                updated_by=actor_id,
            )
        )
        self._session.flush()

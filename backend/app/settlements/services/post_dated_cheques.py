"""The post-dated cheque register (backlog 42.3, ACC-2, decision A80).

A cheque dated ahead is **held**, not posted: it clears no bill, moves no bank
book and counts as no collection until it can be banked. Depositing it records
the receipt (or, for the firm's own cheque, the payment) through the
settlement service a person would use, dated the day it was banked, so
everything downstream -- allocations, the customer's balance, TCS, the
collection reports -- treats it as the receipt it now is.

From there the bank answers. **Cleared** posts nothing more, as TallyPrime and
BUSY treat a PDC once it is converted. **Bounced** reverses the settlement
through its own reversal, dated the day the bank returned it, so the bills owe
again; the bank's fee for the return (Dr bank charges, Cr bank) and any charge
the firm makes the customer (Dr receivable, Cr cheque return charges -- outside
GST, CBIC circular 178/10/2022) post together in one journal of their own, and
the customer's charge is written to their account so the statement shows it.

A held cheque can be **cancelled** -- handed back, or replaced -- and nothing is
undone because nothing was posted. Re-presenting a bounced cheque is a new
cheque in the register, which is what the bank sees too.
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO, quantize_ledger
from app.customers.models import Customer
from app.customers.schemas.customer import (
    CustomerReceivableTransactionCreate,
    CustomerReceivableTransactionType,
)
from app.customers.services.customer_service import CustomerService
from app.finance.services.document_posting import DocumentPostingService
from app.settlements.models import Settlement, SettlementDirection
from app.settlements.models.post_dated_cheque import (
    LIVE_STATUSES,
    PostDatedCheque,
    PostDatedChequeStatus,
)
from app.settlements.schemas import (
    SettlementCreate,
    SettlementMethodEnum,
    SettlementModeEnum,
)
from app.settlements.schemas.post_dated_cheque import (
    PostDatedChequeBounce,
    PostDatedChequeCreate,
    PostDatedChequeDeposit,
    PostDatedChequeResponse,
    PostDatedChequeStatusEnum,
)
from app.settlements.services.settlement_service import (
    PaymentService,
    ReceiptService,
    SettlementService,
)
from app.vendors.models import Vendor

_HELD = PostDatedChequeStatus.HELD.value
_DEPOSITED = PostDatedChequeStatus.DEPOSITED.value


class PostDatedChequeService:
    """Hold a cheque dated ahead, bank it, and record the bank's answer."""

    def __init__(self, session: Session, *, direction: SettlementDirection) -> None:
        """Bind the service to a session and to one direction of cheque."""
        if direction not in (SettlementDirection.RECEIPT, SettlementDirection.PAYMENT):
            raise ValueError("A post-dated cheque is a receipt or a payment.")
        self._session = session
        self._direction = direction
        self._is_receipt = direction == SettlementDirection.RECEIPT

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def _scoped(self, firm_id: UUID) -> Select[tuple[PostDatedCheque]]:
        """Select this firm's live rows in this service's direction."""
        return select(PostDatedCheque).where(
            PostDatedCheque.firm_id == firm_id,
            PostDatedCheque.direction == self._direction.value,
            PostDatedCheque.is_deleted.is_(False),
        )

    def list_cheques(
        self,
        *,
        firm_id: UUID,
        page: int,
        page_size: int,
        status: str | None = None,
        party_id: UUID | None = None,
        due_on: date | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        search: str | None = None,
    ) -> tuple[Sequence[PostDatedCheque], int]:
        """Return one page of the register in cheque-date order, and the total.

        ``due_on`` narrows to what can be banked that day: cheques still held
        whose date has come, the "deposit today" list.
        """
        statement = self._scoped(firm_id)
        if status:
            statement = statement.where(PostDatedCheque.status == status)
        if due_on is not None:
            statement = statement.where(
                PostDatedCheque.status == _HELD,
                PostDatedCheque.cheque_date <= due_on,
            )
        if party_id is not None:
            column = (
                PostDatedCheque.customer_id
                if self._is_receipt
                else PostDatedCheque.vendor_id
            )
            statement = statement.where(column == party_id)
        if date_from is not None:
            statement = statement.where(PostDatedCheque.cheque_date >= date_from)
        if date_to is not None:
            statement = statement.where(PostDatedCheque.cheque_date <= date_to)
        if search:
            statement = statement.where(
                PostDatedCheque.cheque_number.ilike(f"%{search.strip()}%")
            )
        total = self._session.scalar(
            select(func.count()).select_from(statement.subquery())
        )
        rows = self._session.scalars(
            statement.order_by(
                PostDatedCheque.cheque_date.asc(),
                PostDatedCheque.cheque_number.asc(),
                PostDatedCheque.id.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return rows, int(total or 0)

    def get(self, cheque_id: UUID, *, firm_id: UUID) -> PostDatedCheque:
        """Return one cheque.

        Raises:
            ResourceNotFoundError: If the firm has no such cheque this way.

        """
        row = self._session.scalar(
            self._scoped(firm_id).where(PostDatedCheque.id == cheque_id)
        )
        if row is None:
            raise ResourceNotFoundError("Post-dated cheque not found.")
        return row

    def responses(
        self, rows: Sequence[PostDatedCheque]
    ) -> list[PostDatedChequeResponse]:
        """Build the responses for a page, one read per table."""
        if not rows:
            return []
        model: type[Customer] | type[Vendor] = Customer if self._is_receipt else Vendor
        party_ids = {self._party_id(row) for row in rows}
        parties = {
            party_id: (code, name)
            for party_id, code, name in self._session.execute(
                select(model.id, model.code, model.name).where(model.id.in_(party_ids))
            )
        }
        settlement_ids = {row.settlement_id for row in rows if row.settlement_id}
        numbers: dict[UUID, str] = (
            {
                settlement_id: number
                for settlement_id, number in self._session.execute(
                    select(Settlement.id, Settlement.settlement_number).where(
                        Settlement.id.in_(settlement_ids)
                    )
                )
            }
            if settlement_ids
            else {}
        )
        today = utc_now().date()
        answer: list[PostDatedChequeResponse] = []
        for row in rows:
            party_id = self._party_id(row)
            code, name = parties.get(party_id, ("", ""))
            answer.append(
                PostDatedChequeResponse(
                    id=row.id,
                    firm_id=row.firm_id,
                    direction=row.direction,
                    party_id=party_id,
                    party_code=code,
                    party_name=name,
                    cheque_number=row.cheque_number,
                    cheque_date=row.cheque_date,
                    drawn_on_bank=row.drawn_on_bank,
                    amount=row.amount,
                    received_on=row.received_on,
                    narration=row.narration,
                    status=PostDatedChequeStatusEnum(row.status),
                    is_due=row.status == _HELD and row.cheque_date <= today,
                    settlement_id=row.settlement_id,
                    settlement_number=(
                        None
                        if row.settlement_id is None
                        else numbers.get(row.settlement_id)
                    ),
                    deposited_on=row.deposited_on,
                    cleared_on=row.cleared_on,
                    bounced_on=row.bounced_on,
                    bounce_reason=row.bounce_reason,
                    bank_charges_amount=row.bank_charges_amount,
                    customer_charge_amount=row.customer_charge_amount,
                    charges_journal_entry_id=row.charges_journal_entry_id,
                    cancelled_at=row.cancelled_at,
                    cancel_reason=row.cancel_reason,
                    version=row.version,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
            )
        return answer

    # ------------------------------------------------------------------
    # Writes. Each flushes; the router commits.
    # ------------------------------------------------------------------

    def create(
        self, data: PostDatedChequeCreate, *, firm_id: UUID, actor_id: UUID
    ) -> PostDatedCheque:
        """Hold a cheque dated ahead. Nothing is posted.

        Raises:
            ValidationError: If the cheque is dated before it was received, or
                the same party's same cheque is already in the register.

        """
        settlements = self._settlements()
        party = settlements._require_party(firm_id=firm_id, party_id=data.party_id)
        if data.cheque_date < data.received_on:
            raise ValidationError(
                "The cheque is dated before it was received, so it is not "
                "post-dated: record it as a receipt or payment."
            )
        number = data.cheque_number.strip()
        if not number:
            raise ValidationError("Give the cheque number.")
        party_column = (
            PostDatedCheque.customer_id
            if self._is_receipt
            else PostDatedCheque.vendor_id
        )
        clash = self._session.scalar(
            self._scoped(firm_id).where(
                party_column == data.party_id,
                PostDatedCheque.cheque_number == number,
                PostDatedCheque.status.in_(LIVE_STATUSES),
            )
        )
        if clash is not None:
            raise ValidationError(
                f"Cheque {number} from {party.name} is already in the register."
            )
        row = PostDatedCheque(
            firm_id=firm_id,
            direction=self._direction.value,
            customer_id=data.party_id if self._is_receipt else None,
            vendor_id=None if self._is_receipt else data.party_id,
            cheque_number=number,
            cheque_date=data.cheque_date,
            drawn_on_bank=(data.drawn_on_bank or "").strip() or None,
            amount=quantize_ledger(data.amount),
            received_on=data.received_on,
            narration=data.narration,
            status=_HELD,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        self._audit(
            row,
            "recorded",
            actor_id=actor_id,
            after={
                "cheque_number": number,
                "cheque_date": data.cheque_date.isoformat(),
                "amount": str(row.amount),
                "party": party.code,
            },
        )
        return row

    def deposit(
        self,
        cheque_id: UUID,
        data: PostDatedChequeDeposit,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> PostDatedCheque:
        """Bank a held cheque: it becomes a posted receipt or payment.

        Raises:
            ValidationError: If it is not held, or is banked before its date.

        """
        row = self.get(cheque_id, firm_id=firm_id)
        self._require_status(row, _HELD, "banked")
        if data.deposited_on < row.cheque_date:
            raise ValidationError(
                f"Cheque {row.cheque_number} is dated "
                f"{row.cheque_date.isoformat()}; the bank will not take it "
                "before then."
            )
        settlement = self._settlements().create(
            SettlementCreate(
                party_id=self._party_id(row),
                settlement_date=data.deposited_on,
                amount=row.amount,
                method=SettlementMethodEnum.BANK,
                payment_mode=SettlementModeEnum.CHEQUE,
                instrument_reference=row.cheque_number,
                instrument_date=row.cheque_date,
                narration=row.narration or f"Post-dated cheque {row.cheque_number}",
                allocations=data.allocations,
            ),
            firm_id=firm_id,
            actor_id=actor_id,
        )
        row.status = _DEPOSITED
        row.deposited_on = data.deposited_on
        row.settlement_id = settlement.id
        row.updated_by = actor_id
        self._session.flush()
        self._audit(
            row,
            "deposited",
            actor_id=actor_id,
            before={"status": _HELD},
            after={
                "status": _DEPOSITED,
                "deposited_on": data.deposited_on.isoformat(),
                "settlement_number": settlement.settlement_number,
            },
        )
        return row

    def clear(
        self, cheque_id: UUID, *, cleared_on: date, firm_id: UUID, actor_id: UUID
    ) -> PostDatedCheque:
        """Record that the bank honoured it. Nothing more is posted.

        Raises:
            ValidationError: If it was not banked, or clears before it was.

        """
        row = self.get(cheque_id, firm_id=firm_id)
        self._require_status(row, _DEPOSITED, "cleared")
        if row.deposited_on is not None and cleared_on < row.deposited_on:
            raise ValidationError(
                "A cheque cannot clear before the day it was banked "
                f"({row.deposited_on.isoformat()})."
            )
        row.status = PostDatedChequeStatus.CLEARED.value
        row.cleared_on = cleared_on
        row.updated_by = actor_id
        self._session.flush()
        self._audit(
            row,
            "cleared",
            actor_id=actor_id,
            before={"status": _DEPOSITED},
            after={"status": row.status, "cleared_on": cleared_on.isoformat()},
        )
        return row

    def bounce(
        self,
        cheque_id: UUID,
        data: PostDatedChequeBounce,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> PostDatedCheque:
        """Record a returned cheque: reverse what it posted, and its charges.

        Raises:
            ValidationError: If it was not banked, is returned before it was,
                or charges a supplier for the firm's own cheque.

        """
        row = self.get(cheque_id, firm_id=firm_id)
        self._require_status(row, _DEPOSITED, "returned")
        if row.deposited_on is not None and data.bounced_on < row.deposited_on:
            raise ValidationError(
                "A cheque cannot come back before the day it was banked "
                f"({row.deposited_on.isoformat()})."
            )
        bank_charges = quantize_ledger(data.bank_charges_amount or ZERO)
        customer_charge = quantize_ledger(data.customer_charge_amount or ZERO)
        if customer_charge > ZERO and not self._is_receipt:
            raise ValidationError(
                "Only a customer's cheque carries a return charge to the party."
            )
        if row.settlement_id is None:  # pragma: no cover - set with DEPOSITED
            raise ValidationError("The cheque was banked without a receipt.")
        reason = data.reason.strip()
        settlements = self._settlements()
        settlement = settlements.reverse(
            row.settlement_id,
            firm_id=firm_id,
            actor_id=actor_id,
            reason=f"Cheque {row.cheque_number} returned: {reason}",
            on=data.bounced_on,
        )
        if bank_charges > ZERO or customer_charge > ZERO:
            self._post_charges(
                row,
                settlement,
                bounced_on=data.bounced_on,
                bank_charges=bank_charges,
                customer_charge=customer_charge,
                firm_id=firm_id,
                actor_id=actor_id,
            )
        row.status = PostDatedChequeStatus.BOUNCED.value
        row.bounced_on = data.bounced_on
        row.bounce_reason = reason
        row.bank_charges_amount = bank_charges
        row.customer_charge_amount = customer_charge
        row.updated_by = actor_id
        self._session.flush()
        self._audit(
            row,
            "bounced",
            actor_id=actor_id,
            before={"status": _DEPOSITED},
            after={
                "status": row.status,
                "bounced_on": data.bounced_on.isoformat(),
                "reason": reason,
                "bank_charges_amount": str(bank_charges),
                "customer_charge_amount": str(customer_charge),
            },
        )
        return row

    def cancel(
        self, cheque_id: UUID, *, reason: str, firm_id: UUID, actor_id: UUID
    ) -> PostDatedCheque:
        """Take a held cheque out of the register. Nothing was posted.

        Raises:
            ValidationError: If it has already been banked or cancelled.

        """
        row = self.get(cheque_id, firm_id=firm_id)
        self._require_status(row, _HELD, "cancelled")
        row.status = PostDatedChequeStatus.CANCELLED.value
        row.cancelled_at = utc_now()
        row.cancel_reason = reason.strip()
        row.updated_by = actor_id
        self._session.flush()
        self._audit(
            row,
            "cancelled",
            actor_id=actor_id,
            before={"status": _HELD},
            after={"status": row.status, "reason": row.cancel_reason},
        )
        return row

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _settlements(self) -> SettlementService:
        """Return the settlement service for this direction."""
        if self._is_receipt:
            return ReceiptService(self._session)
        return PaymentService(self._session)

    def _party_id(self, row: PostDatedCheque) -> UUID:
        """Return the customer or supplier the cheque is with."""
        party = row.customer_id if self._is_receipt else row.vendor_id
        if party is None:  # pragma: no cover - the check constraint forbids it
            raise ValidationError("The cheque has no party.")
        return party

    @staticmethod
    def _require_status(row: PostDatedCheque, wanted: str, action: str) -> None:
        """Refuse a transition from any state but the one it starts from."""
        if row.status != wanted:
            raise ValidationError(
                f"Cheque {row.cheque_number} is {row.status.lower()}, so it "
                f"cannot be {action}."
            )

    def _post_charges(
        self,
        row: PostDatedCheque,
        settlement: Settlement,
        *,
        bounced_on: date,
        bank_charges: Decimal,
        customer_charge: Decimal,
        firm_id: UUID,
        actor_id: UUID,
    ) -> None:
        """Post the return's charges, and put the customer's on their account."""
        reference = f"{settlement.settlement_number}-RTN"
        entry = DocumentPostingService(self._session).post_cheque_return_charges(
            firm_id=firm_id,
            cheque_id=row.id,
            reference=reference,
            bounced_on=bounced_on,
            bank_account_id=settlement.ledger_account_id,
            bank_charges_amount=bank_charges,
            customer_charge_amount=customer_charge,
            description=f"Cheque {row.cheque_number} returned",
            actor_id=actor_id,
        )
        row.charges_journal_entry_id = entry.id
        if customer_charge > ZERO and row.customer_id is not None:
            transaction = CustomerService(self._session).post_receivable_transaction(
                row.customer_id,
                CustomerReceivableTransactionCreate(
                    transaction_type=(
                        CustomerReceivableTransactionType.CHEQUE_RETURN_CHARGE
                    ),
                    amount=customer_charge,
                    transaction_date=bounced_on,
                    reference_type="post_dated_cheque",
                    reference_id=row.id,
                    reference_number=reference,
                    remarks=f"Charge for cheque {row.cheque_number} returned.",
                ),
                firm_scope=firm_id,
                actor_id=actor_id,
                commit=False,
            )
            row.charge_receivable_transaction_id = transaction.id

    def _audit(
        self,
        row: PostDatedCheque,
        event: str,
        *,
        actor_id: UUID,
        after: dict[str, object],
        before: dict[str, object] | None = None,
    ) -> None:
        """Write one audit row for a step in the cheque's life."""
        record_audit(
            self._session,
            action=f"post_dated_cheque.{event}",
            entity_type="post_dated_cheque",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=row.firm_id,
            before_data=before,
            after_data=after,
        )

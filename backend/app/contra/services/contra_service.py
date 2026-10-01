"""Recording and cancelling a contra voucher (backlog 74 row 3).

Cash paid into the bank, cash drawn out of it, a transfer between two bank
accounts or two cash accounts. It was possible before as a hand journal, with
no number of its own and no warning when the cash it moved did not exist.

**Which accounts hold money.** The firm's CASH and BANK control accounts, and
any other active ASSET account in the same account group as either -- a second
bank account, petty cash -- that no other control purpose claims. Receivables,
inventory and input tax share *Current Assets* with cash and bank in the
seeded chart; they are kept by their own documents and are never money, so
being mapped to another purpose rules an account out. Decided by convention
(2026-10-01) from the rule `ExpenseService.paid_from_accounts` already applies,
narrowed to the cash and bank groups.

**Cash or bank.** The CASH control account is cash and the BANK one is a bank.
Any other money account is cash when it sits in the cash account's group and
not the bank's, a bank in the reverse case, and -- where the two share a group,
as they do in the seeded chart -- cash when its name says "cash" (petty cash,
cash at branch) and a bank otherwise. The kind is derived from the two and
stored with the voucher; nobody types it.

**A warning, not a refusal, below zero.** When the account the money leaves
would stand below zero on the voucher's own date, the save goes through and
says so. The books may simply be behind -- a day's takings not yet keyed --
and refusing would make the clerk enter things out of order to get past it.
The same check runs on cancel for the account the money goes back out of.
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.contra.models import ContraKind, ContraStatus, ContraVoucher
from app.contra.schemas import (
    ContraKindEnum,
    ContraRegisterRecord,
    ContraStatusEnum,
    ContraVoucherCreate,
    ContraVoucherResponse,
    MoneyAccountKindEnum,
    MoneyAccountRecord,
)
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.pagination import WHOLE_HISTORY, ReportWindow, mapped_like
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO, quantize_ledger
from app.document_framework.services.transactional_document_service import (
    DocumentStateSpec,
    DocumentTypeSpec,
    TransactionalDocumentService,
)
from app.finance.models import (
    AccountType,
    FirmControlAccount,
    GLPosting,
    JournalEntry,
    LedgerAccount,
)
from app.finance.services.control_accounts import ControlAccountPurpose
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine

_MONEY_PURPOSES = frozenset(
    {ControlAccountPurpose.CASH.value, ControlAccountPurpose.BANK.value}
)

_KIND_NAMES = {
    ContraKind.DEPOSIT.value: "Cash deposited",
    ContraKind.WITHDRAWAL.value: "Cash withdrawn",
    ContraKind.BANK_TRANSFER.value: "Bank transfer",
    ContraKind.CASH_TRANSFER.value: "Cash transfer",
}


def kind_of(from_kind: str, to_kind: str) -> ContraKind:
    """Name the movement from the kinds of the two accounts."""
    cash = MoneyAccountKindEnum.CASH.value
    if from_kind == cash and to_kind == cash:
        return ContraKind.CASH_TRANSFER
    if from_kind == cash:
        return ContraKind.DEPOSIT
    if to_kind == cash:
        return ContraKind.WITHDRAWAL
    return ContraKind.BANK_TRANSFER


def _money(value: Decimal) -> str:
    """Write an amount with Indian digit grouping, as the screens do."""
    sign = "-" if value < ZERO else ""
    whole, _, paise = f"{abs(quantize_ledger(value)):.2f}".partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join([*groups, tail])
    return f"{sign}{whole}.{paise}"


class ContraVoucherService(TransactionalDocumentService):
    """Move money between the firm's own accounts, and take it back."""

    DOCUMENT = DocumentTypeSpec(
        code="CONTRA_VOUCHER",
        name="Contra Voucher",
        description="Cash deposited, withdrawn or moved between own accounts",
        category="FINANCE",
        module="contra",
        prefix="CV",
        states=(
            DocumentStateSpec("POSTED", "Posted", 1),
            DocumentStateSpec("CANCELLED", "Cancelled", 2, is_terminal=True),
        ),
    )

    def __init__(self, session: Session) -> None:
        """Bind the lifecycle base plus the ledger collaborators."""
        super().__init__(session)
        self._posting = DocumentPostingService(session)
        self._journals = JournalEntryEngine(session)

    # ---- money accounts ------------------------------------------------

    def money_accounts(self, firm_id: UUID) -> list[MoneyAccountRecord]:
        """Return every account money may move into or out of, cash first.

        See the module docstring for the rule. A firm that has nominated
        neither a cash nor a bank account has none.
        """
        mapped: dict[UUID, set[str]] = {}
        nominated: dict[str, UUID] = {}
        for account_id, purpose in self._session.execute(
            select(
                FirmControlAccount.ledger_account_id, FirmControlAccount.purpose
            ).where(
                FirmControlAccount.firm_id == firm_id,
                FirmControlAccount.is_deleted.is_(False),
            )
        ).all():
            mapped.setdefault(account_id, set()).add(purpose)
            if purpose in _MONEY_PURPOSES:
                nominated[purpose] = account_id
        if not nominated:
            return []
        groups: dict[UUID, UUID] = {
            account_id: group_id
            for account_id, group_id in self._session.execute(
                select(LedgerAccount.id, LedgerAccount.account_group_id).where(
                    LedgerAccount.id.in_(nominated.values())
                )
            ).all()
        }
        cash_id = nominated.get(ControlAccountPurpose.CASH.value)
        bank_id = nominated.get(ControlAccountPurpose.BANK.value)
        cash_group = groups.get(cash_id) if cash_id else None
        bank_group = groups.get(bank_id) if bank_id else None
        wanted = {group for group in (cash_group, bank_group) if group is not None}
        candidates = self._session.scalars(
            select(LedgerAccount)
            .where(
                LedgerAccount.firm_id == firm_id,
                LedgerAccount.is_deleted.is_(False),
                LedgerAccount.is_active.is_(True),
                LedgerAccount.account_type == AccountType.ASSET.value,
                or_(
                    LedgerAccount.account_group_id.in_(wanted),
                    LedgerAccount.id.in_(nominated.values()),
                ),
            )
            .order_by(LedgerAccount.code.asc())
        ).all()
        records: list[MoneyAccountRecord] = []
        for account in candidates:
            if not mapped.get(account.id, set()) <= _MONEY_PURPOSES:
                continue
            records.append(
                MoneyAccountRecord(
                    id=account.id,
                    code=account.code,
                    name=account.name,
                    kind=self._kind_of_account(
                        account,
                        cash_id=cash_id,
                        bank_id=bank_id,
                        cash_group=cash_group,
                        bank_group=bank_group,
                    ),
                )
            )
        records.sort(key=lambda row: (row.kind != MoneyAccountKindEnum.CASH, row.code))
        return records

    @staticmethod
    def _kind_of_account(
        account: LedgerAccount,
        *,
        cash_id: UUID | None,
        bank_id: UUID | None,
        cash_group: UUID | None,
        bank_group: UUID | None,
    ) -> MoneyAccountKindEnum:
        """Say whether one money account is cash or a bank account."""
        if account.id == cash_id:
            return MoneyAccountKindEnum.CASH
        if account.id == bank_id:
            return MoneyAccountKindEnum.BANK
        in_cash = account.account_group_id == cash_group
        in_bank = account.account_group_id == bank_group
        if in_cash and not in_bank:
            return MoneyAccountKindEnum.CASH
        if in_bank and not in_cash:
            return MoneyAccountKindEnum.BANK
        return (
            MoneyAccountKindEnum.CASH
            if "cash" in account.name.lower()
            else MoneyAccountKindEnum.BANK
        )

    def balance_on(self, account_id: UUID, *, firm_id: UUID, on: date) -> Decimal:
        """Return what a money account held at the end of a day.

        Summed from every posting dated on or before it -- by the journal's
        own date, not when it was keyed, so a back-dated receipt counts on the
        day it says. Reversed originals and their mirrors both count, which
        nets them to nothing as it should.
        """
        total = self._session.scalar(
            select(
                func.coalesce(
                    func.sum(GLPosting.debit_amount - GLPosting.credit_amount), 0
                )
            )
            .join(JournalEntry, JournalEntry.id == GLPosting.journal_entry_id)
            .where(
                GLPosting.firm_id == firm_id,
                GLPosting.ledger_account_id == account_id,
                JournalEntry.journal_date <= on,
            )
        )
        return quantize_ledger(Decimal(str(total or 0)))

    def _warning(
        self, account: MoneyAccountRecord, *, firm_id: UUID, on: date
    ) -> str | None:
        """Say so when an account stands below zero at the end of a day."""
        balance = self.balance_on(account.id, firm_id=firm_id, on=on)
        if balance >= ZERO:
            return None
        return (
            f"{account.code} {account.name} stands at {_money(balance)} on "
            f"{on.strftime('%d-%m-%Y')} after this -- below zero. Check that "
            "everything paid into it by then has been recorded."
        )

    # ---- reads ---------------------------------------------------------

    def _scoped(
        self, statement: Select[tuple[ContraVoucher]], firm_id: UUID
    ) -> Select[tuple[ContraVoucher]]:
        """Restrict a query to one firm's live vouchers."""
        return statement.where(
            ContraVoucher.firm_id == firm_id,
            ContraVoucher.is_deleted.is_(False),
        )

    def list_vouchers(
        self,
        *,
        firm_id: UUID,
        page: int,
        page_size: int,
        kind: ContraKindEnum | None = None,
        status: ContraStatusEnum | None = None,
        account_id: UUID | None = None,
        search: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> tuple[Sequence[ContraVoucher], int]:
        """Return one page of vouchers, newest first, and the total matching."""
        statement = self._scoped(select(ContraVoucher), firm_id)
        if kind is not None:
            statement = statement.where(ContraVoucher.kind == kind.value)
        if status is not None:
            statement = statement.where(ContraVoucher.status == status.value)
        if account_id is not None:
            statement = statement.where(
                or_(
                    ContraVoucher.from_account_id == account_id,
                    ContraVoucher.to_account_id == account_id,
                )
            )
        if search and search.strip():
            token = f"%{search.strip()}%"
            statement = statement.where(
                or_(
                    ContraVoucher.voucher_number.ilike(token),
                    ContraVoucher.reference.ilike(token),
                    ContraVoucher.remarks.ilike(token),
                )
            )
        if date_from is not None:
            statement = statement.where(ContraVoucher.voucher_date >= date_from)
        if date_to is not None:
            statement = statement.where(ContraVoucher.voucher_date <= date_to)
        total = self._session.scalar(
            select(func.count()).select_from(statement.subquery())
        )
        rows = self._session.scalars(
            statement.order_by(
                ContraVoucher.voucher_date.desc(),
                ContraVoucher.voucher_number.desc(),
                ContraVoucher.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return rows, int(total or 0)

    def get(self, voucher_id: UUID, *, firm_id: UUID) -> ContraVoucher:
        """Return one voucher.

        Raises:
            ResourceNotFoundError: If the firm has no such live voucher.

        """
        row = self._session.scalar(
            self._scoped(select(ContraVoucher), firm_id).where(
                ContraVoucher.id == voucher_id
            )
        )
        if row is None:
            raise ResourceNotFoundError("Contra voucher not found.")
        return row

    # ---- writes --------------------------------------------------------

    def create(
        self, data: ContraVoucherCreate, *, firm_id: UUID, actor_id: UUID
    ) -> tuple[ContraVoucher, str | None]:
        """Record the movement and post its journal. The caller commits.

        Returns:
            The voucher, and the below-zero warning for the account the money
            left, if it has one.

        Raises:
            ValidationError: If either account is not a money account, they
                are the same, or no open period covers the date.

        """
        offered = {row.id: row for row in self.money_accounts(firm_id)}
        source = self._require_money(data.from_account_id, offered, role="from")
        target = self._require_money(data.to_account_id, offered, role="to")
        if source.id == target.id:
            raise ValidationError(
                "The money has to move between two different accounts."
            )
        amount = quantize_ledger(data.amount)
        kind = kind_of(source.kind.value, target.kind.value)
        _, numbering_rule = self._ensure_document_setup(
            firm_id=firm_id, actor_id=actor_id
        )
        number = self._issue_number(
            numbering_rule,
            typed=None,
            number_column=ContraVoucher.voucher_number,
            firm_id=firm_id,
            document_date=data.voucher_date,
            actor_id=actor_id,
            company_code=self._company_code(firm_id),
        )
        reference = (
            data.reference.strip()
            if data.reference and data.reference.strip()
            else None
        )
        remarks = (
            data.remarks.strip() if data.remarks and data.remarks.strip() else None
        )
        description = (
            f"{_KIND_NAMES[kind.value]} {number}: {source.name} to {target.name}"
        )
        if reference:
            description = f"{description} ({reference})"
        # Both directions of the link are set before either row is written,
        # as an expense does: if posting is refused, nothing is left behind.
        voucher_id = uuid4()
        entry = self._posting.post_contra_voucher(
            firm_id=firm_id,
            voucher_id=voucher_id,
            voucher_number=number,
            voucher_date=data.voucher_date,
            from_account_id=source.id,
            to_account_id=target.id,
            amount=amount,
            description=description[:500],
            actor_id=actor_id,
        )
        row = ContraVoucher(
            id=voucher_id,
            firm_id=firm_id,
            voucher_number=number,
            voucher_date=data.voucher_date,
            kind=kind.value,
            from_account_id=source.id,
            to_account_id=target.id,
            amount=amount,
            reference=reference,
            remarks=remarks,
            status=ContraStatus.POSTED.value,
            journal_entry_id=entry.id,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._flush_or_conflict(f"Contra voucher number {number} is already in use.")
        self._record_event(row, action="POSTED", from_state=None, actor_id=actor_id)
        record_audit(
            self._session,
            action="contra_voucher.posted",
            entity_type="contra_voucher",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data=self._snapshot(row),
        )
        self._session.flush()
        return row, self._warning(source, firm_id=firm_id, on=data.voucher_date)

    def cancel(
        self,
        voucher_id: UUID,
        *,
        firm_id: UUID,
        actor_id: UUID,
        reason: str,
    ) -> tuple[ContraVoucher, str | None]:
        """Take a voucher back with a mirror journal. The caller commits.

        The original journal stays and a mirror under ``<number>-CAN`` cancels
        it, dated the day it happened in the period open that day, never
        before the original -- the journal engine's rule for every reversal.

        Returns:
            The voucher, and the below-zero warning for the account the money
            goes back out of, if it has one.

        Raises:
            ValidationError: If it is already cancelled, or no reason is given.

        """
        row = self.get(voucher_id, firm_id=firm_id)
        if row.status == ContraStatus.CANCELLED.value:
            raise ValidationError(f"{row.voucher_number} has already been cancelled.")
        why = reason.strip()
        if not why:
            raise ValidationError("Say why the voucher is being cancelled.")
        before = self._snapshot(row)
        mirror = self._journals.reverse_entry(
            row.journal_entry_id,
            firm_id=firm_id,
            reference_number=f"{row.voucher_number}-CAN",
            actor_id=actor_id,
        )
        row.status = ContraStatus.CANCELLED.value
        row.reversal_journal_entry_id = mirror.id
        row.cancel_reason = why
        row.cancelled_at = utc_now()
        row.cancelled_by = actor_id
        row.updated_by = actor_id
        self._session.flush()
        self._record_event(
            row,
            action="CANCELLED",
            from_state=ContraStatus.POSTED.value,
            actor_id=actor_id,
            remarks=why,
        )
        record_audit(
            self._session,
            action="contra_voucher.cancelled",
            entity_type="contra_voucher",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data=self._snapshot(row),
        )
        self._session.flush()
        account = self._session.get(LedgerAccount, row.to_account_id)
        warning = None
        if account is not None:
            warning = self._warning(
                MoneyAccountRecord(
                    id=account.id,
                    code=account.code,
                    name=account.name,
                    kind=MoneyAccountKindEnum.BANK,
                ),
                firm_id=firm_id,
                on=mirror.journal_date,
            )
        return row, warning

    def _require_money(
        self,
        account_id: UUID,
        offered: dict[UUID, MoneyAccountRecord],
        *,
        role: str,
    ) -> MoneyAccountRecord:
        """Return the chosen money account, or refuse it by name and say why."""
        found = offered.get(account_id)
        if found is not None:
            return found
        account = self._session.get(LedgerAccount, account_id)
        if account is None or account.is_deleted:
            raise ValidationError(f"The {role} account was not found in this firm.")
        raise ValidationError(
            f"{account.code} {account.name} is not a cash or bank account. A "
            "contra voucher moves money between the firm's cash and bank "
            "accounts and the accounts grouped with them."
        )

    def _record_event(
        self,
        row: ContraVoucher,
        *,
        action: str,
        from_state: str | None,
        actor_id: UUID,
        remarks: str | None = None,
    ) -> None:
        """Append one step to the voucher's timeline."""
        self._record_lifecycle_event(
            firm_id=row.firm_id,
            document_type=self._document_type(row.firm_id),
            document_id=row.id,
            document_number=row.voucher_number,
            action=action,
            from_state=from_state,
            to_state=row.status,
            actor_id=actor_id,
            remarks=remarks,
            details={
                "voucher_number": row.voucher_number,
                "kind": row.kind,
                "amount": str(row.amount),
            },
            snapshot={"status": row.status},
        )

    @staticmethod
    def _snapshot(row: ContraVoucher) -> dict[str, object]:
        """Describe a voucher for the audit trail."""
        return {
            "voucher_number": row.voucher_number,
            "voucher_date": row.voucher_date.isoformat(),
            "kind": row.kind,
            "status": row.status,
            "from_account_id": str(row.from_account_id),
            "to_account_id": str(row.to_account_id),
            "amount": str(row.amount),
            "reference": row.reference,
            "journal_entry_id": str(row.journal_entry_id),
            "reversal_journal_entry_id": (
                str(row.reversal_journal_entry_id)
                if row.reversal_journal_entry_id
                else None
            ),
            "cancel_reason": row.cancel_reason,
        }

    # ---- responses -----------------------------------------------------

    def _accounts(self, rows: Sequence[ContraVoucher]) -> dict[UUID, tuple[str, str]]:
        """Return the code and name of every account a page names, in one read."""
        ids = {row.from_account_id for row in rows} | {
            row.to_account_id for row in rows
        }
        if not ids:
            return {}
        return {
            account_id: (code, name)
            for account_id, code, name in self._session.execute(
                select(LedgerAccount.id, LedgerAccount.code, LedgerAccount.name).where(
                    LedgerAccount.id.in_(ids)
                )
            ).all()
        }

    def response(
        self, row: ContraVoucher, *, warning: str | None = None
    ) -> ContraVoucherResponse:
        """Build the response for one voucher."""
        answer = self.responses([row])[0]
        answer.balance_warning = warning
        return answer

    def responses(self, rows: Sequence[ContraVoucher]) -> list[ContraVoucherResponse]:
        """Build the responses for a page, reading the accounts once."""
        accounts = self._accounts(rows)
        missing = ("", "")
        return [
            ContraVoucherResponse(
                id=row.id,
                voucher_number=row.voucher_number,
                voucher_date=row.voucher_date,
                kind=ContraKindEnum(row.kind),
                status=ContraStatusEnum(row.status),
                from_account_id=row.from_account_id,
                from_account_code=accounts.get(row.from_account_id, missing)[0],
                from_account_name=accounts.get(row.from_account_id, missing)[1],
                to_account_id=row.to_account_id,
                to_account_code=accounts.get(row.to_account_id, missing)[0],
                to_account_name=accounts.get(row.to_account_id, missing)[1],
                amount=row.amount,
                reference=row.reference,
                remarks=row.remarks,
                journal_entry_id=row.journal_entry_id,
                reversal_journal_entry_id=row.reversal_journal_entry_id,
                created_by=row.created_by,
                created_at=row.created_at,
                cancelled_at=row.cancelled_at,
                cancel_reason=row.cancel_reason,
                version=row.version,
            )
            for row in rows
        ]

    # ---- print ---------------------------------------------------------

    def render_pdf(self, voucher_id: UUID, *, firm_id: UUID) -> tuple[bytes, str]:
        """Draw one voucher on the firm's letterhead, for the file and a signature.

        Returns:
            The PDF bytes and a file name built from the voucher number.

        """
        # Imported here: the print helpers reach the sales invoice renderer,
        # which nothing else in this module needs.
        from app.document_framework.services.letter_pdf import (
            LetterPage,
            LetterPdfRenderer,
        )
        from app.document_framework.services.print_support import (
            firm_party,
            load_template,
        )
        from app.sales_invoice.services.invoice_pdf import amount_in_words

        row = self.get(voucher_id, firm_id=firm_id)
        view = self.responses([row])[0]
        facts = [
            ("Voucher number", row.voucher_number),
            ("Date", row.voucher_date.strftime("%d-%m-%Y")),
            ("Kind", _KIND_NAMES[row.kind]),
            ("From (credit)", f"{view.from_account_code} {view.from_account_name}"),
            ("To (debit)", f"{view.to_account_code} {view.to_account_name}"),
            ("Amount", _money(Decimal(str(row.amount)))),
            ("In words", amount_in_words(Decimal(str(row.amount)))),
        ]
        if row.reference:
            facts.append(("Reference", row.reference))
        if row.remarks:
            facts.append(("Remarks", row.remarks))
        if row.status == ContraStatus.CANCELLED.value:
            facts.append(("Status", f"CANCELLED -- {row.cancel_reason or ''}"))
        template = load_template(
            self._session, firm_scope=firm_id, document_type="SALES_INVOICE"
        )
        pdf = LetterPdfRenderer(template.accent_color).render(
            [
                LetterPage(
                    firm=firm_party(firm_id),
                    title="CONTRA VOUCHER",
                    facts=facts,
                    counter_signatory="Prepared by",
                )
            ]
        )
        return pdf, f"{row.voucher_number}.pdf".replace("/", "-")

    # ---- reports -------------------------------------------------------

    def register_report(
        self, *, firm_id: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[ContraRegisterRecord]:
        """Every voucher in the window, newest first; paged in SQL."""
        rows = window.fetch(
            self._session,
            select(ContraVoucher)
            .where(
                ContraVoucher.firm_id == firm_id,
                ContraVoucher.is_deleted.is_(False),
                *window.dated(ContraVoucher.voucher_date),
            )
            .order_by(
                ContraVoucher.voucher_date.desc(),
                ContraVoucher.voucher_number.desc(),
                ContraVoucher.id.desc(),
            ),
        )
        accounts = self._accounts(rows)
        records = [
            ContraRegisterRecord(
                voucher_id=row.id,
                voucher_number=row.voucher_number,
                voucher_date=row.voucher_date,
                kind=ContraKindEnum(row.kind),
                status=ContraStatusEnum(row.status),
                from_account_name=accounts.get(row.from_account_id, ("", ""))[1],
                to_account_name=accounts.get(row.to_account_id, ("", ""))[1],
                amount=row.amount,
                reference=row.reference,
                remarks=row.remarks,
            )
            for row in rows
        ]
        return mapped_like(rows, records)


__all__ = ["ContraVoucherService", "kind_of"]

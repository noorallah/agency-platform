"""The firm's adjustment and write-off reasons, as a master (STK-7, A104).

A firm keeps its own list. The six reasons the code always knew are seeded
as system rows the first time the firm's list is read, so a firm with none
loses nothing; they can be renamed, deactivated or pointed at another
account, never deleted. Each reason may name the ledger account its cost
lands in; without one it lands where it always did.
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.concurrency import assert_version
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.finance.models import FirmControlAccount, LedgerAccount
from app.finance.services.control_accounts import (
    EXPECTED_TYPE,
    PURPOSE_LABELS,
    ControlAccountPurpose,
)
from app.inventory.models.adjustment_reason import StockAdjustmentReason

#: The reasons the code knew before they were a master, in their order. The
#: names are what the ledger narration always said ("Expiry: ...").
SYSTEM_REASONS: tuple[tuple[str, str], ...] = (
    ("DAMAGE", "Damage"),
    ("EXPIRY", "Expiry"),
    ("LOSS", "Loss"),
    ("INTERNAL_USE", "Internal use"),
    ("STAFF", "Staff"),
    ("DISPLAY", "Display"),
    ("FREE_TO_CUSTOMER", "Given free to customer"),
    ("SAMPLE", "Sample"),
)


def _a(account_type: str) -> str:
    """Return an account type as it reads in a sentence: "an asset"."""
    word = account_type.lower()
    return f"{'an' if word[:1] in 'aeiou' else 'a'} {word}"


def _purpose_label(purpose: str) -> str:
    """Return a control-account purpose as the firm's screens name it."""
    try:
        return PURPOSE_LABELS[ControlAccountPurpose(purpose)]
    except (KeyError, ValueError):
        return purpose.replace("_", " ").lower()


class AdjustmentReasonWrite(BaseModel):
    """Create or change one reason."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=120)
    #: Absent on an update leaves the account alone; null clears it.
    ledger_account_id: UUID | None = None
    is_active: bool = True

    @field_validator("code", mode="before")
    @classmethod
    def upper_code(cls, value: str) -> str:
        """Match codes regardless of case."""
        return value.strip().upper()


class AdjustmentReasonResponse(BaseModel):
    """One reason, with its account named."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    code: str
    name: str
    ledger_account_id: UUID | None
    ledger_account_name: str | None
    is_system: bool
    is_active: bool
    version: int


class AdjustmentReasonService:
    """List, add, change and remove one firm's reasons."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request's session."""
        self._session = session

    def ensure_seeded(self, firm_id: UUID) -> None:
        """Write any system reason the firm does not have yet, unflushed."""
        have = set(
            self._session.scalars(
                select(StockAdjustmentReason.code).where(
                    StockAdjustmentReason.firm_id == firm_id,
                    StockAdjustmentReason.is_deleted.is_(False),
                )
            ).all()
        )
        for code, name in SYSTEM_REASONS:
            if code not in have:
                self._session.add(
                    StockAdjustmentReason(
                        firm_id=firm_id, code=code, name=name, is_system=True
                    )
                )
        self._session.flush()

    def list_reasons(
        self, firm_id: UUID, *, include_inactive: bool = True
    ) -> list[AdjustmentReasonResponse]:
        """Return the firm's reasons, system ones first, seeding them once."""
        self.ensure_seeded(firm_id)
        self._session.commit()
        query = select(StockAdjustmentReason).where(
            StockAdjustmentReason.firm_id == firm_id,
            StockAdjustmentReason.is_deleted.is_(False),
        )
        if not include_inactive:
            query = query.where(StockAdjustmentReason.is_active.is_(True))
        rows = list(self._session.scalars(query).all())
        order = {code: index for index, (code, _) in enumerate(SYSTEM_REASONS)}
        rows.sort(key=lambda r: (order.get(r.code, len(order)), r.code))
        return self._responses(rows)

    def resolve(self, firm_id: UUID, code: str) -> StockAdjustmentReason:
        """Return the active reason a movement names.

        Raises:
            ValidationError: If the firm keeps no such active reason.

        """
        self.ensure_seeded(firm_id)
        row = self._session.scalar(
            select(StockAdjustmentReason).where(
                StockAdjustmentReason.firm_id == firm_id,
                StockAdjustmentReason.code == code.strip().upper(),
                StockAdjustmentReason.is_deleted.is_(False),
            )
        )
        if row is None or not row.is_active:
            raise ValidationError(
                f"'{code}' is not an active stock adjustment reason of this firm. "
                "Choose one from Settings > Stock > Adjustment reasons."
            )
        return row

    def create(
        self, data: AdjustmentReasonWrite, *, firm_id: UUID, actor_id: UUID
    ) -> AdjustmentReasonResponse:
        """Add one reason of the firm's own."""
        self.ensure_seeded(firm_id)
        self._assert_code_free(firm_id, data.code)
        self._assert_account(firm_id, data.ledger_account_id)
        row = StockAdjustmentReason(
            firm_id=firm_id,
            code=data.code,
            name=data.name,
            ledger_account_id=data.ledger_account_id,
            is_active=data.is_active,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        self._audit("stock_adjustment_reason.created", row, actor_id)
        self._session.commit()
        return self._responses([row])[0]

    def update(
        self,
        reason_id: UUID,
        data: AdjustmentReasonWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
        expected_version: int | None = None,
    ) -> AdjustmentReasonResponse:
        """Change one reason; a system reason keeps its code.

        ``expected_version`` is the version the caller read; a save aimed at
        an older one is refused rather than laid over the newer (F15).

        Raises:
            ValidationError: If a system reason's code would change.

        """
        row = self._get(reason_id, firm_id)
        assert_version(row.version, expected_version)
        if data.code != row.code:
            if row.is_system:
                raise ValidationError(
                    f"{row.code} is a system reason; rename it, but its code stays."
                )
            self._assert_code_free(firm_id, data.code)
            row.code = data.code
        row.name = data.name
        row.is_active = data.is_active
        if "ledger_account_id" in data.model_fields_set:
            self._assert_account(firm_id, data.ledger_account_id)
            row.ledger_account_id = data.ledger_account_id
        row.updated_by = actor_id
        self._session.flush()
        self._audit("stock_adjustment_reason.updated", row, actor_id)
        self._session.commit()
        return self._responses([row])[0]

    def delete(self, reason_id: UUID, *, firm_id: UUID, actor_id: UUID) -> None:
        """Remove a reason of the firm's own; a system one is deactivated instead.

        Raises:
            ValidationError: For a system reason.

        """
        row = self._get(reason_id, firm_id)
        if row.is_system:
            raise ValidationError(
                f"{row.code} is a system reason and cannot be deleted; mark it "
                "inactive to stop offering it."
            )
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.updated_by = actor_id
        self._audit("stock_adjustment_reason.deleted", row, actor_id)
        self._session.commit()

    def _get(self, reason_id: UUID, firm_id: UUID) -> StockAdjustmentReason:
        """Return one of the firm's reasons."""
        row = self._session.get(StockAdjustmentReason, reason_id)
        if row is None or row.is_deleted or row.firm_id != firm_id:
            raise ResourceNotFoundError("Adjustment reason not found.")
        return row

    def _assert_code_free(self, firm_id: UUID, code: str) -> None:
        """Refuse a code another live reason holds."""
        clash = self._session.scalar(
            select(StockAdjustmentReason.id).where(
                StockAdjustmentReason.firm_id == firm_id,
                StockAdjustmentReason.code == code,
                StockAdjustmentReason.is_deleted.is_(False),
            )
        )
        if clash is not None:
            raise ConflictError(f"There is already a reason {code}.")

    def _assert_account(self, firm_id: UUID, account_id: UUID | None) -> None:
        """Refuse an account a stock difference must not be booked to.

        A reason's account takes the other side of the Inventory entry, so it
        has to be a profit-and-loss account -- the same classes the firm's
        own Inventory adjustment account may be. Pointed at Inventory itself
        a write-off lowered the valuation and left the books where they were;
        pointed at Cash or Payables it moved a balance nobody paid (F9).

        One of the firm's control accounts is refused as well, unless it is
        one stock differences already post to (inventory adjustment, stock
        used in business, staff welfare, samples, promotion): Sales and Cost
        of goods sold are profit-and-loss accounts too, and a write-off does
        not belong in either.

        Raises:
            ValidationError: Naming the account and the kind that is needed.

        """
        if account_id is None:
            return
        from app.inventory.services.inventory_service import ISSUE_PURPOSES

        account = self._session.get(LedgerAccount, account_id)
        if (
            account is None
            or account.is_deleted
            or account.firm_id != firm_id
            or not account.is_active
        ):
            raise ValidationError("That ledger account is not one of this firm's.")
        named = f"{account.code} {account.name}"
        allowed_types = EXPECTED_TYPE[ControlAccountPurpose.INVENTORY_ADJUSTMENT]
        if account.account_type not in allowed_types:
            raise ValidationError(
                f"{named} is {_a(account.account_type)} account, so a stock "
                "adjustment reason cannot post to it. Choose an expense "
                "account (or an income account for stock gains)."
            )
        stock_purposes = {ControlAccountPurpose.INVENTORY_ADJUSTMENT.value} | {
            purpose.value for purpose in ISSUE_PURPOSES.values()
        }
        mapped = set(
            self._session.scalars(
                select(FirmControlAccount.purpose).where(
                    FirmControlAccount.firm_id == firm_id,
                    FirmControlAccount.ledger_account_id == account.id,
                    FirmControlAccount.is_deleted.is_(False),
                )
            ).all()
        )
        if mapped and not mapped & stock_purposes:
            raise ValidationError(
                f"{named} is the firm's {_purpose_label(sorted(mapped)[0])} "
                "account, so a stock adjustment reason cannot post to it. "
                "Choose an expense account kept for stock differences."
            )

    def _audit(self, action: str, row: StockAdjustmentReason, actor_id: UUID) -> None:
        """Write one audit row for a change to a reason."""
        record_audit(
            self._session,
            action=action,
            entity_type="stock_adjustment_reason",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=row.firm_id,
            after_data={
                "code": row.code,
                "name": row.name,
                "ledger_account_id": (
                    None
                    if row.ledger_account_id is None
                    else str(row.ledger_account_id)
                ),
                "is_active": row.is_active,
            },
        )

    def _responses(
        self, rows: list[StockAdjustmentReason]
    ) -> list[AdjustmentReasonResponse]:
        """Shape reasons, naming their accounts in one read."""
        ids = {row.ledger_account_id for row in rows if row.ledger_account_id}
        names: dict[UUID, str] = {}
        if ids:
            for account_id, name in self._session.execute(
                select(LedgerAccount.id, LedgerAccount.name).where(
                    LedgerAccount.id.in_(ids)
                )
            ).all():
                names[account_id] = name
        return [
            AdjustmentReasonResponse(
                id=row.id,
                code=row.code,
                name=row.name,
                ledger_account_id=row.ledger_account_id,
                ledger_account_name=(
                    names.get(row.ledger_account_id) if row.ledger_account_id else None
                ),
                is_system=row.is_system,
                is_active=row.is_active,
                version=row.version,
            )
            for row in rows
        ]

"""Reading and setting a person's usual branch and warehouse (backlog 44).

Validated on save -- a live branch and warehouse of the firm, the warehouse
belonging to the branch -- and on use: one retired since is reported as
ignored rather than handed to a form, so nothing is ever filled in from a
place that no longer exists.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.branches.models import Branch, Warehouse
from app.branches.models.user_work_default import UserWorkDefault
from app.common.audit.services import record_audit
from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import ResourceNotFoundError, ValidationError


@dataclass(frozen=True)
class WorkDefaults:
    """What a person's forms open with, and anything set that was dropped."""

    branch_id: UUID | None
    warehouse_id: UUID | None
    #: Set, but retired or moved since: named so the screen can say so.
    ignored: tuple[str, ...] = ()


class UserWorkDefaultService:
    """Read and set one person's usual branch and warehouse in a firm."""

    def __init__(self, session: Session) -> None:
        """Bind to the firm's store."""
        self._session = session

    def assert_member(self, firm_id: UUID, user_id: UUID) -> None:
        """Refuse an administrator's read or write for a non-member.

        The person an administrator sets defaults for must be an active
        member of the firm -- checked through `FirmMetadataReader`, because
        `users` and `user_firms` live only in the platform store. Answered as
        not found rather than forbidden, so the route says nothing about
        people outside the firm.
        """
        if (
            FirmMetadataReader(self._session).active_member_count(firm_id, [user_id])
            != 1
        ):
            raise ResourceNotFoundError("That person is not a member of this firm.")

    def current(self, firm_id: UUID, user_id: UUID) -> WorkDefaults:
        """Return the person's defaults that still stand, and what was dropped."""
        row = self._row(firm_id, user_id)
        if row is None:
            return WorkDefaults(branch_id=None, warehouse_id=None)
        ignored: list[str] = []
        branch = self._live_branch(firm_id, row.branch_id)
        if row.branch_id is not None and branch is None:
            ignored.append("The branch you usually work from has been retired.")
        warehouse = self._live_warehouse(firm_id, row.warehouse_id)
        if row.warehouse_id is not None and warehouse is None:
            ignored.append("The warehouse you usually work from has been retired.")
        elif (
            warehouse is not None
            and branch is not None
            and warehouse.branch_id != branch.id
        ):
            ignored.append(
                "Your usual warehouse now belongs to another branch, so it is "
                "not used."
            )
            warehouse = None
        return WorkDefaults(
            branch_id=None if branch is None else branch.id,
            warehouse_id=None if warehouse is None else warehouse.id,
            ignored=tuple(ignored),
        )

    def set(
        self,
        firm_id: UUID,
        user_id: UUID,
        *,
        branch_id: UUID | None,
        warehouse_id: UUID | None,
        actor_id: UUID,
    ) -> WorkDefaults:
        """Set (or, with both None, clear) the person's defaults; the caller commits.

        Raises:
            ValidationError: If the branch or warehouse is not a live one of
                the firm, or the warehouse is not the branch's.

        """
        branch = self._live_branch(firm_id, branch_id)
        if branch_id is not None and branch is None:
            raise ValidationError("Choose one of the firm's working branches.")
        warehouse = self._live_warehouse(firm_id, warehouse_id)
        if warehouse_id is not None and warehouse is None:
            raise ValidationError("Choose one of the firm's working warehouses.")
        if (
            warehouse is not None
            and branch is not None
            and warehouse.branch_id != branch.id
        ):
            raise ValidationError(
                f"{warehouse.code} belongs to another branch, not {branch.code}."
            )
        if warehouse is not None and branch is None:
            branch_id = warehouse.branch_id
        row = self._row(firm_id, user_id)
        if row is None:
            row = UserWorkDefault(firm_id=firm_id, user_id=user_id, created_by=actor_id)
            self._session.add(row)
        row.branch_id = branch_id
        row.warehouse_id = warehouse_id
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="user_work_defaults.set",
            entity_type="user_work_default",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "user_id": str(user_id),
                "branch_id": None if branch_id is None else str(branch_id),
                "warehouse_id": None if warehouse_id is None else str(warehouse_id),
            },
        )
        return self.current(firm_id, user_id)

    def _row(self, firm_id: UUID, user_id: UUID) -> UserWorkDefault | None:
        return self._session.scalar(
            select(UserWorkDefault).where(
                UserWorkDefault.firm_id == firm_id,
                UserWorkDefault.user_id == user_id,
                UserWorkDefault.is_deleted.is_(False),
            )
        )

    def _live_branch(self, firm_id: UUID, branch_id: UUID | None) -> Branch | None:
        if branch_id is None:
            return None
        branch = self._session.get(Branch, branch_id)
        if (
            branch is None
            or branch.firm_id != firm_id
            or branch.is_deleted
            or (branch.status or "ACTIVE") != "ACTIVE"
        ):
            return None
        return branch

    def _live_warehouse(
        self, firm_id: UUID, warehouse_id: UUID | None
    ) -> Warehouse | None:
        if warehouse_id is None:
            return None
        warehouse = self._session.get(Warehouse, warehouse_id)
        if (
            warehouse is None
            or warehouse.firm_id != firm_id
            or warehouse.is_deleted
            or (warehouse.status or "ACTIVE") != "ACTIVE"
        ):
            return None
        return warehouse

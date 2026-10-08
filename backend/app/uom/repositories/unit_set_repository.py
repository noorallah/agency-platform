"""SQLAlchemy persistence adapter for unit sets."""

from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.products.models.goods_type import GoodsType
from app.uom.models import UnitSet, UnitSetGoodsType


class UnitSetRepository:
    """Centralize unit set queries: the shared catalogue and a firm's own."""

    def __init__(self, session: Session) -> None:
        """Bind the adapter to the firm's store session."""
        self._session = session

    def add(self, row: UnitSet) -> None:
        """Stage a new unit set."""
        self._session.add(row)

    def get(self, unit_set_id: UUID, firm_id: UUID) -> UnitSet | None:
        """Return a live shared set or one of the firm's own."""
        return self._session.scalar(
            select(UnitSet).where(
                UnitSet.id == unit_set_id,
                UnitSet.is_deleted.is_(False),
                or_(UnitSet.firm_id.is_(None), UnitSet.firm_id == firm_id),
            )
        )

    def visible(self, firm_id: UUID, *, include_inactive: bool) -> list[UnitSet]:
        """Return the shared sets and the firm's own, by name."""
        statement = select(UnitSet).where(
            UnitSet.is_deleted.is_(False),
            or_(UnitSet.firm_id.is_(None), UnitSet.firm_id == firm_id),
        )
        if not include_inactive:
            statement = statement.where(UnitSet.is_active.is_(True))
        return list(
            self._session.scalars(
                statement.order_by(UnitSet.name.asc(), UnitSet.id.asc())
            )
        )

    def name_taken(
        self, name: str, firm_id: UUID, *, current: UUID | None = None
    ) -> bool:
        """Say whether the firm or the shared catalogue already uses a name.

        Asked without regard to case: the product import finds a set by name
        that way, so *strip, BOX of 10* beside *Strip, box of 10* left it to
        chance which of the two a file meant (D-MST-20).
        """
        statement = select(UnitSet.id).where(
            func.lower(UnitSet.name) == name.strip().lower(),
            UnitSet.is_deleted.is_(False),
            or_(UnitSet.firm_id.is_(None), UnitSet.firm_id == firm_id),
        )
        if current is not None:
            statement = statement.where(UnitSet.id != current)
        return self._session.scalar(statement.limit(1)) is not None

    def goods_types_by_set(self, firm_id: UUID) -> dict[UUID, list[UUID]]:
        """Return each set's live goods types, for every set the firm sees.

        One statement for the whole list. A type the firm cannot see -- another
        firm's own, tied to a shared set by nobody but guarded here all the
        same -- and a deleted one are left out.
        """
        rows = self._session.execute(
            select(UnitSetGoodsType.unit_set_id, UnitSetGoodsType.goods_type_id)
            .join(GoodsType, GoodsType.id == UnitSetGoodsType.goods_type_id)
            .where(
                GoodsType.is_deleted.is_(False),
                or_(GoodsType.firm_id.is_(None), GoodsType.firm_id == firm_id),
            )
            .order_by(GoodsType.name.asc(), GoodsType.id.asc())
        ).all()
        by_set: dict[UUID, list[UUID]] = {}
        for unit_set_id, goods_type_id in rows:
            by_set.setdefault(unit_set_id, []).append(goods_type_id)
        return by_set

    def visible_goods_types(self, firm_id: UUID, ids: set[UUID]) -> set[UUID]:
        """Return which of ``ids`` are live goods types this firm can see."""
        if not ids:
            return set()
        return set(
            self._session.scalars(
                select(GoodsType.id).where(
                    GoodsType.id.in_(ids),
                    GoodsType.is_deleted.is_(False),
                    or_(GoodsType.firm_id.is_(None), GoodsType.firm_id == firm_id),
                )
            )
        )

    def replace_goods_types(
        self, unit_set_id: UUID, goods_type_ids: list[UUID], *, actor_id: UUID
    ) -> None:
        """Make the set's goods types exactly ``goods_type_ids``; flush."""
        self._session.execute(
            delete(UnitSetGoodsType).where(UnitSetGoodsType.unit_set_id == unit_set_id)
        )
        for goods_type_id in dict.fromkeys(goods_type_ids):
            self._session.add(
                UnitSetGoodsType(
                    unit_set_id=unit_set_id,
                    goods_type_id=goods_type_id,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        self._session.flush()

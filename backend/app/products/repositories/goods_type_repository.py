"""SQLAlchemy persistence adapter for goods types."""

from uuid import UUID

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.orm import Session

from app.products.models import Product, ProductCategory
from app.products.models.goods_type import FirmGoodsType, GoodsType
from app.tax.models import TaxProfile

#: The kinds of tracking a firm's menus follow, and the switch behind each.
TRACKING_SWITCHES = {
    "BATCH": "track_batch",
    "EXPIRY": "track_expiry",
    "SERIAL": "track_serial",
}


class GoodsTypeRepository:
    """Centralize goods type queries: the shared catalogue and a firm's own."""

    def __init__(self, session: Session) -> None:
        """Bind the adapter to the firm's store session."""
        self._session = session

    def add(self, row: GoodsType | FirmGoodsType) -> None:
        """Stage a new goods type, or a firm's use of one."""
        self._session.add(row)

    def find(self, goods_type_id: UUID) -> GoodsType | None:
        """Return a goods type by id, whoever keeps it and deleted or not."""
        return self._session.get(GoodsType, goods_type_id)

    def visible(self, firm_id: UUID) -> list[GoodsType]:
        """Return the live shared types and the firm's own, by name."""
        return list(
            self._session.scalars(
                select(GoodsType)
                .where(GoodsType.is_deleted.is_(False), self._reach(firm_id))
                .order_by(GoodsType.name.asc(), GoodsType.code.asc())
            )
        )

    def uses(self, firm_id: UUID) -> dict[UUID, FirmGoodsType]:
        """Return the firm's live use rows by goods type."""
        return {
            use.goods_type_id: use
            for use in self._session.scalars(
                select(FirmGoodsType).where(
                    FirmGoodsType.firm_id == firm_id,
                    FirmGoodsType.is_deleted.is_(False),
                )
            )
        }

    def code_taken(
        self, code: str, firm_id: UUID, *, current: UUID | None = None
    ) -> bool:
        """Say whether the firm or the shared catalogue already uses a code."""
        statement = select(GoodsType.id).where(
            GoodsType.code == code,
            GoodsType.is_deleted.is_(False),
            self._reach(firm_id),
        )
        if current is not None:
            statement = statement.where(GoodsType.id != current)
        return self._session.scalar(statement.limit(1)) is not None

    def inherited_type(self, firm_id: UUID, paths: list[str]) -> UUID | None:
        """Return the type of the deepest of these categories that has one."""
        return self._session.scalar(
            select(ProductCategory.goods_type_id)
            .where(
                ProductCategory.firm_id == firm_id,
                ProductCategory.path.in_(paths),
                ProductCategory.is_deleted.is_(False),
                ProductCategory.goods_type_id.is_not(None),
            )
            .order_by(ProductCategory.level.desc())
            .limit(1)
        )

    def category_holding(self, goods_type_id: UUID, firm_id: UUID) -> str | None:
        """Return the name of one live category of the firm carrying the type."""
        return self._session.scalar(
            select(ProductCategory.name)
            .where(
                ProductCategory.firm_id == firm_id,
                ProductCategory.goods_type_id == goods_type_id,
                ProductCategory.is_deleted.is_(False),
            )
            .limit(1)
        )

    def product_holding(self, goods_type_id: UUID, firm_id: UUID) -> str | None:
        """Return the code of one live product of the firm carrying the type."""
        return self._session.scalar(
            select(Product.code)
            .where(
                Product.firm_id == firm_id,
                Product.goods_type_id == goods_type_id,
                Product.is_deleted.is_(False),
            )
            .limit(1)
        )

    def has_tax_group(self, firm_id: UUID, group_code: str) -> bool:
        """Say whether the firm has a live tax profile in this group."""
        found = self._session.scalar(
            select(TaxProfile.id)
            .where(
                TaxProfile.firm_id == firm_id,
                TaxProfile.group_code == group_code,
                TaxProfile.is_deleted.is_(False),
                TaxProfile.status == "ACTIVE",
            )
            .limit(1)
        )
        return found is not None

    def tracking_in_use(self, firm_id: UUID) -> list[str]:
        """Return the kinds of tracking the firm's goods need, in a fixed order.

        A kind is needed when a goods type the firm uses switches it on, or
        when a product of the firm does: a product keeps its own switches,
        and one filed before goods types existed has no type at all. One read
        of the types in use, then one short read of the products for each
        kind no type answered.
        """
        types = self._session.execute(
            select(
                GoodsType.track_batch, GoodsType.track_expiry, GoodsType.track_serial
            )
            .join(FirmGoodsType, FirmGoodsType.goods_type_id == GoodsType.id)
            .where(
                FirmGoodsType.firm_id == firm_id,
                FirmGoodsType.is_deleted.is_(False),
                GoodsType.is_deleted.is_(False),
            )
        ).all()
        needed: list[str] = []
        for position, (kind, switch) in enumerate(TRACKING_SWITCHES.items()):
            if any(row[position] for row in types) or self._a_product_tracks(
                firm_id, switch
            ):
                needed.append(kind)
        return needed

    def _a_product_tracks(self, firm_id: UUID, switch: str) -> bool:
        """Say whether one live product of the firm has this switch on."""
        found = self._session.scalar(
            select(Product.id)
            .where(
                Product.firm_id == firm_id,
                Product.is_deleted.is_(False),
                getattr(Product, switch).is_(True),
            )
            .limit(1)
        )
        return found is not None

    @staticmethod
    def _reach(firm_id: UUID) -> ColumnElement[bool]:
        """Match the shared catalogue and the firm's own rows."""
        return or_(GoodsType.firm_id.is_(None), GoodsType.firm_id == firm_id)

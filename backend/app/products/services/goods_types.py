"""Goods types: the shared catalogue, a firm's own, and the ones it uses.

A goods type says how a line of goods is tracked (backlog 89). The platform
keeps a shared catalogue every firm reads and none changes; a firm's
administrator adds the firm's own. Which types a firm trades in is a row of
``firm_goods_types``, and that row also carries the HSN code and tax group a
new product of the type starts with -- a tax group is the firm's own code.

The category carries the type and a product takes it from there:
``type_for_category`` answers that, nearest category first.
"""

from uuid import UUID

from sqlalchemy.orm import Session

from app.common.audit.services import record_audit, record_change, row_state
from app.core.concurrency import assert_version
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.products.models import ProductCategory
from app.products.models.goods_type import FirmGoodsType, GoodsType
from app.products.repositories import GoodsTypeRepository
from app.products.schemas.goods_type import (
    GoodsTypeCreate,
    GoodsTypeResponse,
    GoodsTypeUpdate,
    GoodsTypeUse,
    ProductGoodsTypeOption,
)

_DEFAULTS = ("default_hsn_sac", "default_tax_profile_group_code")
#: The switches a type holds, which a new product of it starts with.
_SWITCHES = (
    "track_batch",
    "track_expiry",
    "track_manufacturing_date",
    "track_serial",
    "track_warranty",
)
#: The product's "must be named" rules, and the switch each one follows: a
#: line tracked by batch is one whose goods may not arrive or leave without
#: one. The type holds no column for these; they are its switch said twice.
_FOLLOWERS = {
    "require_batch_on_receipt": "track_batch",
    "require_batch_on_issue": "track_batch",
    "require_serial_on_receipt": "track_serial",
    "require_serial_on_issue": "track_serial",
}


class GoodsTypeService:
    """Keep a firm's goods types and resolve the one a product takes."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the firm's store session."""
        self._session = session
        self._repository = GoodsTypeRepository(session)

    # -- reading --------------------------------------------------------
    def list_types(self, firm_id: UUID) -> list[GoodsTypeResponse]:
        """Return the shared types and the firm's own, by name; two reads."""
        uses = self._uses(firm_id)
        return [
            self._response(row, uses.get(row.id))
            for row in self._repository.visible(firm_id)
        ]

    def tracking_in_use(self, firm_id: UUID) -> list[str]:
        """Return which of BATCH, EXPIRY and SERIAL the firm's goods need.

        What the Batches, Serial Numbers and Expiry Monitor menus follow: a
        goods type the firm uses, or a product it already holds.
        """
        return self._repository.tracking_in_use(firm_id)

    def type_for_category(
        self, firm_id: UUID, category: ProductCategory | None
    ) -> UUID | None:
        """Return the goods type a product filed under ``category`` takes.

        The category's own, or its nearest parent's that has one; none is
        General. One statement: a category's ``path`` names every ancestor.
        """
        if category is None:
            return None
        if category.goods_type_id is not None or category.parent_id is None:
            return category.goods_type_id
        codes = category.path.split("/")
        ancestors = ["/".join(codes[:depth]) for depth in range(1, len(codes))]
        return self._repository.inherited_type(firm_id, ancestors)

    @staticmethod
    def product_switches(row: GoodsType) -> dict[str, bool]:
        """Return every switch a new product of this type starts with."""
        switches = {name: bool(getattr(row, name)) for name in _SWITCHES}
        switches.update({name: switches[lead] for name, lead in _FOLLOWERS.items()})
        return switches

    def product_options(
        self, firm_id: UUID, *, tax_groups: set[str]
    ) -> list[ProductGoodsTypeOption]:
        """Return each type as the product form needs it; two reads.

        ``tax_groups`` is the firm's live ones: a default naming a group the
        firm has since retired is not offered, as it is not filled on a save.
        """
        uses = self._uses(firm_id)
        options: list[ProductGoodsTypeOption] = []
        for row in self._repository.visible(firm_id):
            use = uses.get(row.id)
            tax_group = None if use is None else use.default_tax_profile_group_code
            options.append(
                ProductGoodsTypeOption(
                    id=row.id,
                    code=row.code,
                    name=row.name,
                    switches=self.product_switches(row),
                    default_hsn_sac=None if use is None else use.default_hsn_sac,
                    default_tax_profile_group_code=(
                        tax_group if tax_group in tax_groups else None
                    ),
                )
            )
        return options

    def starting_values(
        self,
        firm_id: UUID,
        goods_type_id: UUID | None,
        *,
        sent: set[str],
        values: dict[str, object],
    ) -> dict[str, object]:
        """Return what the type fills on a product being created.

        ``sent`` is the fields the caller named and ``values`` what they hold.
        A switch the caller named is theirs, on or off: that is how one
        product differs from its line. The rest take the type's, and a
        "must be named" rule follows its switch as it ends up, so a product
        sent with batch tracking off is not left demanding a batch. The HSN
        code and tax group are filled only where the product has none, and a
        tax group the firm no longer has is passed over rather than refused.
        General fills nothing.
        """
        row = None if goods_type_id is None else self._repository.find(goods_type_id)
        if row is None:
            return {}
        filled: dict[str, object] = {
            name: bool(getattr(row, name)) for name in _SWITCHES if name not in sent
        }
        for name, lead in _FOLLOWERS.items():
            if name not in sent:
                tracked = filled[lead] if lead in filled else values.get(lead)
                filled[name] = bool(getattr(row, lead)) and bool(tracked)
        use = self._uses(firm_id).get(row.id)
        if use is None:
            return filled
        if values.get("hsn_sac") is None and use.default_hsn_sac:
            filled["hsn_sac"] = use.default_hsn_sac
        tax_group = use.default_tax_profile_group_code
        if (
            values.get("tax_profile_group_code") is None
            and tax_group
            and self._has_tax_group(firm_id, tax_group)
        ):
            filled["tax_profile_group_code"] = tax_group
        return filled

    def assert_offered(self, firm_id: UUID, goods_type_id: UUID | None) -> None:
        """Refuse a type a category of this firm may not carry.

        Raises:
            ValidationError: If the type is another firm's, retired, or one
                this firm does not trade in.

        """
        if goods_type_id is None:
            return
        row = self._repository.find(goods_type_id)
        if (
            row is None
            or row.is_deleted
            or not row.is_active
            or row.firm_id not in (None, firm_id)
        ):
            raise ValidationError("Selected goods type is unavailable.")
        if goods_type_id not in self._uses(firm_id):
            raise ValidationError(
                f"{row.name} is not among the goods types this firm uses. "
                "Add it under Goods Types first."
            )

    # -- the firm's own types -------------------------------------------
    def create(
        self, data: GoodsTypeCreate, *, firm_id: UUID, actor_id: UUID
    ) -> GoodsTypeResponse:
        """Add a goods type of the firm's own, in use from the start; commit."""
        self._assert_code_free(data.code, firm_id=firm_id)
        self._assert_tax_group(firm_id, data.default_tax_profile_group_code)
        row = GoodsType(
            **data.model_dump(exclude=set(_DEFAULTS)),
            firm_id=firm_id,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._repository.add(row)
        self._session.flush()
        use = FirmGoodsType(
            firm_id=firm_id,
            goods_type_id=row.id,
            default_hsn_sac=data.default_hsn_sac,
            default_tax_profile_group_code=data.default_tax_profile_group_code,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._repository.add(use)
        self._session.flush()
        record_change(
            self._session,
            action="goods_type.created",
            entity_type="goods_type",
            row=row,
            actor_id=actor_id,
            firm_id=firm_id,
        )
        self._session.commit()
        return self._response(row, use)

    def update(
        self,
        goods_type_id: UUID,
        data: GoodsTypeUpdate,
        *,
        firm_id: UUID,
        actor_id: UUID,
        expected_version: int | None = None,
    ) -> GoodsTypeResponse:
        """Change a goods type of the firm's own; commit.

        Its switches reach products created afterwards only: a product keeps
        the switches it was saved with.

        Raises:
            ConflictError: If the new code is taken, or the row moved.

        """
        row = self._own(goods_type_id, firm_id)
        assert_version(row.version, expected_version)
        values = data.model_dump(exclude_unset=True)
        # A column that cannot be null is left alone by an explicit null too.
        for field in [name for name, value in values.items() if value is None]:
            if field not in (*_DEFAULTS, "description"):
                del values[field]
        if "code" in values and values["code"] != row.code:
            self._assert_code_free(str(values["code"]), firm_id=firm_id, current=row.id)
        before = row_state(row)
        for field, value in values.items():
            if field not in _DEFAULTS:
                setattr(row, field, value)
        row.updated_by = actor_id
        use = self._uses(firm_id).get(row.id)
        defaults = {name: values[name] for name in _DEFAULTS if name in values}
        if defaults:
            use = self._write_use(
                row, use, firm_id=firm_id, actor_id=actor_id, defaults=defaults
            )
        self._session.flush()
        record_change(
            self._session,
            action="goods_type.updated",
            entity_type="goods_type",
            row=row,
            actor_id=actor_id,
            before=before,
            firm_id=firm_id,
        )
        self._session.commit()
        return self._response(row, use)

    def delete(self, goods_type_id: UUID, *, firm_id: UUID, actor_id: UUID) -> None:
        """Remove a goods type of the firm's own that nothing carries; commit.

        Raises:
            ConflictError: If a category or a product still carries it.

        """
        row = self._own(goods_type_id, firm_id)
        self._assert_no_category(row, firm_id, verb="deleted")
        held = self._repository.product_holding(row.id, firm_id)
        if held is not None:
            raise ConflictError(
                f"{row.name} is still the goods type of product {held}, so it "
                "cannot be deleted. Deactivate it instead."
            )
        use = self._uses(firm_id).get(row.id)
        now = utc_now()
        for item in (row, use):
            if item is not None:
                item.is_deleted = True
                item.deleted_at = now
                item.deleted_by = actor_id
                item.updated_by = actor_id
        record_change(
            self._session,
            action="goods_type.deleted",
            entity_type="goods_type",
            row=row,
            actor_id=actor_id,
            firm_id=firm_id,
        )
        self._session.commit()

    # -- what the firm uses ---------------------------------------------
    def set_use(
        self,
        goods_type_id: UUID,
        data: GoodsTypeUse,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> GoodsTypeResponse:
        """Take a type into use or drop it, and set its defaults; commit.

        The one write a firm has over a shared type. Dropping one keeps the
        products that hold it as they are; it is refused while a category
        still hands the type to new products.

        Raises:
            ConflictError: If a live category carries a type being dropped.

        """
        row = self._visible(goods_type_id, firm_id)
        use = self._uses(firm_id).get(row.id)
        values = data.model_dump(exclude_unset=True)
        defaults = {name: values[name] for name in _DEFAULTS if name in values}
        if not data.in_use:
            self._assert_no_category(row, firm_id, verb="dropped")
            if use is not None:
                use.is_deleted = True
                use.deleted_at = utc_now()
                use.deleted_by = actor_id
                use.updated_by = actor_id
            use = None
        else:
            if not row.is_active:
                raise ValidationError(f"{row.name} is retired and cannot be used.")
            use = self._write_use(
                row, use, firm_id=firm_id, actor_id=actor_id, defaults=defaults
            )
        self._session.flush()
        record_audit(
            self._session,
            action="goods_type.use_changed",
            entity_type="goods_type",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"code": row.code, "in_use": data.in_use, **defaults},
        )
        self._session.commit()
        return self._response(row, use)

    # -- internals ------------------------------------------------------
    def _uses(self, firm_id: UUID) -> dict[UUID, FirmGoodsType]:
        """Return the firm's live use rows by goods type."""
        return self._repository.uses(firm_id)

    def _write_use(
        self,
        row: GoodsType,
        use: FirmGoodsType | None,
        *,
        firm_id: UUID,
        actor_id: UUID,
        defaults: dict[str, str | None],
    ) -> FirmGoodsType:
        """Create the firm's use row if it is missing and write the defaults."""
        if "default_tax_profile_group_code" in defaults:
            self._assert_tax_group(firm_id, defaults["default_tax_profile_group_code"])
        if use is None:
            use = FirmGoodsType(
                firm_id=firm_id, goods_type_id=row.id, created_by=actor_id
            )
            self._repository.add(use)
        for name, value in defaults.items():
            setattr(use, name, value)
        use.updated_by = actor_id
        return use

    def _visible(self, goods_type_id: UUID, firm_id: UUID) -> GoodsType:
        """Return a shared type or one of the firm's own."""
        row = self._repository.find(goods_type_id)
        if row is None or row.is_deleted or row.firm_id not in (None, firm_id):
            raise ResourceNotFoundError("Goods type not found.")
        return row

    def _own(self, goods_type_id: UUID, firm_id: UUID) -> GoodsType:
        """Return a type of the firm's own; a shared one is not theirs to change."""
        row = self._visible(goods_type_id, firm_id)
        if row.firm_id != firm_id:
            raise ValidationError(
                f"{row.name} is a shared goods type and cannot be changed here. "
                "Add one of the firm's own instead."
            )
        return row

    def _assert_no_category(self, row: GoodsType, firm_id: UUID, *, verb: str) -> None:
        """Refuse while a live category of the firm carries the type."""
        held = self._repository.category_holding(row.id, firm_id)
        if held is not None:
            raise ConflictError(
                f"{row.name} is still the goods type of category {held}, so it "
                f"cannot be {verb}. Give that category another type first."
            )

    def _assert_code_free(
        self, code: str, *, firm_id: UUID, current: UUID | None = None
    ) -> None:
        """Refuse a code the firm or the shared catalogue already uses."""
        if self._repository.code_taken(code, firm_id, current=current):
            raise ConflictError(f"A goods type with code {code} already exists.")

    def _assert_tax_group(self, firm_id: UUID, group_code: str | None) -> None:
        """Refuse a default tax group the firm does not have."""
        if group_code is not None and not self._has_tax_group(firm_id, group_code):
            raise ValidationError(
                "No active tax profile found for the given group code."
            )

    def _has_tax_group(self, firm_id: UUID, group_code: str) -> bool:
        """Say whether the firm has a live tax profile in this group."""
        return self._repository.has_tax_group(firm_id, group_code)

    @staticmethod
    def _response(row: GoodsType, use: FirmGoodsType | None) -> GoodsTypeResponse:
        """Build one type as the firm sees it."""
        return GoodsTypeResponse(
            id=row.id,
            firm_id=row.firm_id,
            code=row.code,
            name=row.name,
            description=row.description,
            track_batch=row.track_batch,
            track_expiry=row.track_expiry,
            track_manufacturing_date=row.track_manufacturing_date,
            track_serial=row.track_serial,
            track_warranty=row.track_warranty,
            is_active=row.is_active,
            in_use=use is not None,
            default_hsn_sac=None if use is None else use.default_hsn_sac,
            default_tax_profile_group_code=(
                None if use is None else use.default_tax_profile_group_code
            ),
            version=row.version,
        )

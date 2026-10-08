"""Unit sets: the shared catalogue, a firm's own, and what one fills.

A unit set is a template for a product's units (backlog 89). The platform
keeps a shared catalogue every firm reads and none changes; a firm's
administrator adds the firm's own. A set names the goods types it suits, and
that only orders the product form's picker: nothing is refused for pairing a
product with a set of another type.

A set is **copied** onto a new product, never linked: ``starting_units`` hands
``ProductService.stage_product`` the units and the factor, and from then on
the product's own columns and its own conversion rule are what every document
reads.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit, record_change, row_state
from app.core.concurrency import assert_version
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.uom.models import UNIT_SLOTS, UnitSet, Uom
from app.uom.repositories import UnitSetRepository
from app.uom.schemas.unit_set import (
    ProductUnitSetOption,
    UnitSetCreate,
    UnitSetResponse,
    UnitSetUpdate,
)

#: What a set writes onto a product besides its units.
_COPIED = (*UNIT_SLOTS, "allow_decimal")


class UnitSetService:
    """Keep a firm's unit sets and say what one fills on a new product."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the firm's store session."""
        self._session = session
        self._sets = UnitSetRepository(session)

    # -- reading --------------------------------------------------------
    def list_sets(
        self, firm_id: UUID, *, include_inactive: bool = False
    ) -> list[UnitSetResponse]:
        """Return the shared sets and the firm's own, by name; two reads."""
        rows = self._sets.visible(firm_id, include_inactive=include_inactive)
        types = self._sets.goods_types_by_set(firm_id)
        return [self._response(row, types.get(row.id, [])) for row in rows]

    def product_options(self, firm_id: UUID) -> list[ProductUnitSetOption]:
        """Return every set a new product may take; two reads."""
        rows = self._sets.visible(firm_id, include_inactive=False)
        types = self._sets.goods_types_by_set(firm_id)
        return [
            ProductUnitSetOption(
                id=row.id,
                name=row.name,
                **{slot: getattr(row, slot) for slot in UNIT_SLOTS},
                allow_decimal=row.allow_decimal,
                conversion_factor=row.conversion_factor,
                goods_type_ids=types.get(row.id, []),
            )
            for row in rows
        ]

    def starting_units(
        self,
        firm_id: UUID,
        unit_set_id: UUID | None,
        *,
        sent: set[str],
    ) -> tuple[dict[str, object], Decimal | None]:
        """Return what the set fills on a product being created, and its factor.

        ``sent`` is the fields the caller named. A unit the caller named is
        theirs, blank included: that is how the form overrides a set after
        showing it. The rest take the set's, and a slot the set leaves empty
        fills nothing. The goods type the product belongs to is not asked
        about: a set of another type is a choice, never an error.

        Raises:
            ValidationError: If the set is another firm's, retired or gone.

        """
        if unit_set_id is None:
            return {}, None
        row = self._sets.get(unit_set_id, firm_id)
        if row is None or not row.is_active:
            raise ValidationError("Selected unit set is unavailable.")
        filled = {
            name: getattr(row, name)
            for name in _COPIED
            if name not in sent and getattr(row, name) is not None
        }
        return filled, row.conversion_factor

    # -- the firm's own sets --------------------------------------------
    def create(
        self, data: UnitSetCreate, *, firm_id: UUID, actor_id: UUID
    ) -> UnitSetResponse:
        """Add a unit set of the firm's own; commit.

        Raises:
            ConflictError: If the firm or the shared catalogue has the name.

        """
        values = data.model_dump(exclude={"goods_type_ids"})
        self._assert_name_free(data.name, firm_id=firm_id)
        self._assert_consistent(values)
        self._assert_goods_types(firm_id, data.goods_type_ids)
        row = UnitSet(
            **values, firm_id=firm_id, created_by=actor_id, updated_by=actor_id
        )
        self._sets.add(row)
        self._session.flush()
        self._sets.replace_goods_types(row.id, data.goods_type_ids, actor_id=actor_id)
        record_change(
            self._session,
            action="unit_set.created",
            entity_type="unit_set",
            row=row,
            actor_id=actor_id,
            firm_id=firm_id,
        )
        self._session.commit()
        return self._response(row, self._types_of(row, firm_id))

    def update(
        self,
        unit_set_id: UUID,
        data: UnitSetUpdate,
        *,
        firm_id: UUID,
        actor_id: UUID,
        expected_version: int | None = None,
    ) -> UnitSetResponse:
        """Change a unit set of the firm's own; commit.

        Reaches products created afterwards only: a product holds its own
        copy of the units and its own conversion rule.

        Raises:
            ConflictError: If the new name is taken, or the row moved.

        """
        row = self._own(unit_set_id, firm_id)
        assert_version(row.version, expected_version)
        values = data.model_dump(exclude_unset=True, exclude={"goods_type_ids"})
        if "name" in values and values["name"] != row.name:
            self._assert_name_free(str(values["name"]), firm_id=firm_id, current=row.id)
        self._assert_consistent(
            {name: values.get(name, getattr(row, name)) for name in _STATE}
        )
        before = row_state(row)
        for field, value in values.items():
            setattr(row, field, value)
        if self._session.is_modified(row):
            row.updated_by = actor_id
        self._session.flush()
        record_change(
            self._session,
            action="unit_set.updated",
            entity_type="unit_set",
            row=row,
            actor_id=actor_id,
            before=before,
            firm_id=firm_id,
            exclude=("updated_by",),
        )
        if data.goods_type_ids is not None:
            self._retie(row, data.goods_type_ids, firm_id=firm_id, actor_id=actor_id)
        self._session.commit()
        return self._response(row, self._types_of(row, firm_id))

    def delete(self, unit_set_id: UUID, *, firm_id: UUID, actor_id: UUID) -> None:
        """Remove a unit set of the firm's own; commit.

        Never refused for the products made from it: each holds its own copy,
        and the set's name stays readable on them.
        """
        row = self._own(unit_set_id, firm_id)
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        row.updated_by = actor_id
        record_change(
            self._session,
            action="unit_set.deleted",
            entity_type="unit_set",
            row=row,
            actor_id=actor_id,
            firm_id=firm_id,
        )
        self._session.commit()

    # -- internals ------------------------------------------------------
    def _retie(
        self, row: UnitSet, wanted: list[UUID], *, firm_id: UUID, actor_id: UUID
    ) -> None:
        """Replace the set's goods types where they moved, with an audit row."""
        held = self._types_of(row, firm_id)
        if set(held) == set(wanted):
            return
        self._assert_goods_types(firm_id, wanted)
        self._sets.replace_goods_types(row.id, wanted, actor_id=actor_id)
        record_audit(
            self._session,
            action="unit_set.goods_types_changed",
            entity_type="unit_set",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={"goods_type_ids": sorted(str(item) for item in held)},
            after_data={"goods_type_ids": sorted(str(item) for item in wanted)},
        )

    def _types_of(self, row: UnitSet, firm_id: UUID) -> list[UUID]:
        """Return one set's live goods types."""
        return self._sets.goods_types_by_set(firm_id).get(row.id, [])

    def _own(self, unit_set_id: UUID, firm_id: UUID) -> UnitSet:
        """Return a set of the firm's own; a shared one is not theirs to change."""
        row = self._sets.get(unit_set_id, firm_id)
        if row is None:
            raise ResourceNotFoundError("Unit set not found.")
        if row.firm_id != firm_id:
            raise ValidationError(
                f"{row.name} is a shared unit set and cannot be changed here. "
                "Add one of the firm's own instead."
            )
        return row

    def _assert_name_free(
        self, name: str, *, firm_id: UUID, current: UUID | None = None
    ) -> None:
        """Refuse a name the firm or the shared catalogue already uses."""
        if self._sets.name_taken(name, firm_id, current=current):
            raise ConflictError(f"A unit set named {name} already exists.")

    def _assert_consistent(self, values: dict[str, object]) -> None:
        """Refuse a unit the catalogue lacks, or a factor between no two units.

        Raises:
            ValidationError: Naming what does not fit.

        """
        wanted = {value for name in UNIT_SLOTS if (value := values.get(name))}
        live = set(
            self._session.scalars(
                select(Uom.id).where(
                    Uom.id.in_(wanted),
                    Uom.is_deleted.is_(False),
                    Uom.status == "ACTIVE",
                )
            )
        )
        if wanted - live:
            raise ValidationError("One or more selected units are unavailable.")
        if values.get("conversion_factor") is None:
            return
        stock = values.get("inventory_uom_id") or values.get("base_uom_id")
        purchase = values.get("purchase_uom_id")
        if purchase is None or purchase == stock:
            raise ValidationError(
                "A conversion factor needs a purchase unit that differs from "
                "the stock unit. Choose the two units, or leave the factor blank."
            )

    def _assert_goods_types(self, firm_id: UUID, goods_type_ids: list[UUID]) -> None:
        """Refuse a goods type this firm cannot see."""
        wanted = set(goods_type_ids)
        if wanted - self._sets.visible_goods_types(firm_id, wanted):
            raise ValidationError("One or more selected goods types are unavailable.")

    @staticmethod
    def _response(row: UnitSet, goods_type_ids: list[UUID]) -> UnitSetResponse:
        """Build one set as the firm sees it."""
        return UnitSetResponse(
            id=row.id,
            firm_id=row.firm_id,
            name=row.name,
            description=row.description,
            **{slot: getattr(row, slot) for slot in UNIT_SLOTS},
            allow_decimal=row.allow_decimal,
            conversion_factor=row.conversion_factor,
            is_active=row.is_active,
            goods_type_ids=goods_type_ids,
            version=row.version,
        )


#: What ``_assert_consistent`` reads, on a row as an update will leave it.
_STATE = (*UNIT_SLOTS, "conversion_factor")

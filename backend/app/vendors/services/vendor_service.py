"""Transactional application service for vendor management."""

from collections.abc import Mapping
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.business.gating import assert_feature_fields
from app.common.audit.services import record_audit
from app.core.database.entity import BaseEntity
from app.core.exceptions import ConflictError, ResourceNotFoundError
from app.core.utils.dates import utc_now
from app.vendors.models import (
    Vendor,
    VendorAddress,
    VendorAttachment,
    VendorBankAccount,
    VendorCategory,
    VendorContact,
    VendorNote,
    VendorTaxDetail,
    VendorType,
)
from app.vendors.repositories import VendorRepository
from app.vendors.schemas import (
    VendorAddressInput,
    VendorAttachmentInput,
    VendorBankInput,
    VendorCategoryWrite,
    VendorContactInput,
    VendorCreate,
    VendorListFilters,
    VendorNoteInput,
    VendorSummary,
    VendorTaxInput,
    VendorTypeWrite,
    VendorUpdate,
)


class VendorService:
    """Coordinate validated vendor mutations, queries, and audits."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session
        self._repository = VendorRepository(session)

    def create(self, data: VendorCreate, *, firm_id: UUID, actor_id: UUID) -> Vendor:
        """Create a vendor with its nested detail rows."""
        try:
            vendor = self._stage_create(data, firm_id=firm_id, actor_id=actor_id)
        except IntegrityError as error:
            self._session.rollback()
            raise self._unique_conflict() from error
        self._commit_unique()
        return vendor

    def import_vendors(
        self,
        records: list[VendorCreate],
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> list[Vendor]:
        """Create several vendors from an uploaded batch."""
        try:
            vendors = [
                self._stage_create(record, firm_id=firm_id, actor_id=actor_id)
                for record in records
            ]
        except (ConflictError, IntegrityError) as error:
            self._session.rollback()
            if isinstance(error, ConflictError):
                raise
            raise self._unique_conflict() from error
        self._commit_unique()
        return vendors

    def get(
        self,
        vendor_id: UUID,
        *,
        firm_scope: UUID | None,
        include_deleted: bool = False,
    ) -> Vendor:
        """Return one vendor the firm owns."""
        vendor = self._repository.get(
            vendor_id, firm_scope, include_deleted=include_deleted
        )
        if vendor is None:
            raise ResourceNotFoundError("Vendor not found.")
        return vendor

    def update(
        self,
        vendor_id: UUID,
        data: VendorUpdate,
        *,
        firm_scope: UUID | None,
        actor_id: UUID,
    ) -> Vendor:
        """Replace a vendor and reconcile its nested rows."""
        vendor = self.get(vendor_id, firm_scope=firm_scope)
        self._assert_unique(vendor.firm_id, data, excluding_id=vendor.id)
        self._assert_drug_license_allowed(vendor.firm_id, data)
        before = self._audit_snapshot(vendor)
        for field, value in self._vendor_values(data).items():
            setattr(vendor, field, value)
        vendor.display_name = data.display_name or data.name
        vendor.updated_by = actor_id
        # Only the collections the caller actually sent. An absent one is left
        # exactly as it is, because this update replaces rather than merges and
        # a client that does not manage a collection must not be able to erase
        # it by omission.
        if data.contacts is not None:
            self._reconcile_contacts(vendor, data.contacts, actor_id)
        if data.addresses is not None:
            self._reconcile_addresses(vendor, data.addresses, actor_id)
        if data.banking is not None:
            self._reconcile_banks(vendor, data.banking, actor_id)
        if data.tax is not None:
            self._reconcile_tax(vendor, data.tax, actor_id)
        if data.attachments is not None:
            self._reconcile_attachments(vendor, data.attachments, actor_id)
        if data.notes is not None:
            self._reconcile_notes(vendor, data.notes, actor_id)
        record_audit(
            self._session,
            action="vendor.updated",
            entity_type="vendor",
            entity_id=vendor.id,
            actor_id=actor_id,
            firm_id=vendor.firm_id,
            before_data=before,
            after_data=self._audit_snapshot(vendor),
        )
        self._commit_unique()
        self._session.expire(
            vendor,
            [
                "contacts",
                "addresses",
                "bank_accounts",
                "tax_details",
                "attachments",
                "notes",
            ],
        )
        return vendor

    def delete(
        self, vendor_id: UUID, *, firm_scope: UUID | None, actor_id: UUID
    ) -> None:
        """Soft delete a vendor."""
        vendor = self.get(vendor_id, firm_scope=firm_scope)
        before = self._audit_snapshot(vendor)
        vendor.is_deleted = True
        vendor.deleted_at = utc_now()
        vendor.deleted_by = actor_id
        vendor.updated_by = actor_id
        record_audit(
            self._session,
            action="vendor.deleted",
            entity_type="vendor",
            entity_id=vendor.id,
            actor_id=actor_id,
            firm_id=vendor.firm_id,
            before_data=before,
        )
        self._session.commit()

    def restore(
        self, vendor_id: UUID, *, firm_scope: UUID | None, actor_id: UUID
    ) -> Vendor:
        """Restore a soft-deleted vendor."""
        vendor = self.get(vendor_id, firm_scope=firm_scope, include_deleted=True)
        if not vendor.is_deleted:
            return vendor
        vendor.is_deleted = False
        vendor.deleted_at = None
        vendor.deleted_by = None
        vendor.updated_by = actor_id
        record_audit(
            self._session,
            action="vendor.restored",
            entity_type="vendor",
            entity_id=vendor.id,
            actor_id=actor_id,
            firm_id=vendor.firm_id,
            after_data=self._audit_snapshot(vendor),
        )
        self._session.commit()
        return vendor

    def list_vendors(
        self,
        *,
        firm_scope: UUID | None,
        filters: VendorListFilters,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
    ) -> tuple[list[Vendor], int]:
        """Return a page of vendors for the firm in scope."""
        return self._repository.list_vendors(
            firm_scope=firm_scope,
            filters=filters,
            search=search,
            sort_by=sort_by,
            descending=descending,
            offset=(page - 1) * page_size,
            limit=page_size,
        )

    def summary(
        self, *, firm_scope: UUID | None, filters: VendorListFilters
    ) -> VendorSummary:
        """Return vendor counts by status."""
        total, active, inactive, draft, archived, deleted = self._repository.summary(
            firm_scope, filters
        )
        return VendorSummary(
            total=total,
            active=active,
            inactive=inactive,
            draft=draft,
            archived=archived,
            deleted=deleted,
        )

    def _audit_bulk(self, vendor: Vendor, *, action: str, actor_id: UUID) -> None:
        """Record a bulk mutation the way the single-row endpoint records it.

        All five bulk endpoints wrote nothing, so whether a change reached the
        audit trail depended on which button the user pressed.
        """
        record_audit(
            self._session,
            action=action,
            entity_type="vendor",
            entity_id=vendor.id,
            actor_id=actor_id,
            firm_id=vendor.firm_id,
            before_data={"code": vendor.code},
            after_data={"status": vendor.status, "is_deleted": vendor.is_deleted},
        )

    def bulk_delete(
        self, *, ids: list[UUID], firm_scope: UUID | None, actor_id: UUID
    ) -> int:
        """Soft delete several vendors, auditing each."""
        affected = 0
        for vendor_id in ids:
            vendor = self.get(vendor_id, firm_scope=firm_scope)
            if vendor.is_deleted:
                continue
            vendor.is_deleted = True
            vendor.deleted_at = utc_now()
            vendor.deleted_by = actor_id
            vendor.updated_by = actor_id
            self._audit_bulk(vendor, action="vendor.deleted", actor_id=actor_id)
            affected += 1
        if affected:
            self._session.commit()
        return affected

    def bulk_restore(
        self, *, ids: list[UUID], firm_scope: UUID | None, actor_id: UUID
    ) -> int:
        """Restore several vendors, auditing each."""
        affected = 0
        for vendor_id in ids:
            vendor = self.get(vendor_id, firm_scope=firm_scope, include_deleted=True)
            if not vendor.is_deleted:
                continue
            vendor.is_deleted = False
            vendor.deleted_at = None
            vendor.deleted_by = None
            vendor.updated_by = actor_id
            self._audit_bulk(vendor, action="vendor.restored", actor_id=actor_id)
            affected += 1
        if affected:
            self._session.commit()
        return affected

    def bulk_status(
        self, *, ids: list[UUID], status: str, firm_scope: UUID | None, actor_id: UUID
    ) -> int:
        """Set the status of several vendors, auditing each."""
        affected = 0
        normalized = status.strip().upper()
        for vendor_id in ids:
            vendor = self.get(vendor_id, firm_scope=firm_scope)
            if vendor.status == normalized:
                continue
            vendor.status = normalized
            vendor.updated_by = actor_id
            self._audit_bulk(vendor, action="vendor.updated", actor_id=actor_id)
            affected += 1
        if affected:
            self._session.commit()
        return affected

    def bulk_category(
        self,
        *,
        ids: list[UUID],
        category_id: UUID | None,
        firm_scope: UUID | None,
        actor_id: UUID,
    ) -> int:
        """Reassign the category of several vendors, auditing each."""
        affected = 0
        for vendor_id in ids:
            vendor = self.get(vendor_id, firm_scope=firm_scope)
            if vendor.category_id == category_id:
                continue
            vendor.category_id = category_id
            vendor.updated_by = actor_id
            self._audit_bulk(vendor, action="vendor.updated", actor_id=actor_id)
            affected += 1
        if affected:
            self._session.commit()
        return affected

    def bulk_profile(
        self,
        *,
        ids: list[UUID],
        business_profile_id: UUID | None,
        firm_scope: UUID | None,
        actor_id: UUID,
    ) -> int:
        """Reassign the business profile of several vendors, auditing each."""
        affected = 0
        for vendor_id in ids:
            vendor = self.get(vendor_id, firm_scope=firm_scope)
            if vendor.business_profile_id == business_profile_id:
                continue
            vendor.business_profile_id = business_profile_id
            vendor.updated_by = actor_id
            self._audit_bulk(vendor, action="vendor.updated", actor_id=actor_id)
            affected += 1
        if affected:
            self._session.commit()
        return affected

    def duplicate(
        self, vendor_id: UUID, *, firm_scope: UUID | None, actor_id: UUID
    ) -> Vendor:
        """Duplicate ."""
        source = self.get(vendor_id, firm_scope=firm_scope)
        payload = self._vendor_values_for_duplicate(source)
        duplicate = Vendor(
            firm_id=source.firm_id,
            **payload,
            code=f"{source.code}-COPY",
            created_by=actor_id,
            updated_by=actor_id,
        )
        duplicate.contacts = [
            VendorContact(
                name=item.name,
                department=item.department,
                designation=item.designation,
                phone=item.phone,
                mobile=item.mobile,
                email=item.email,
                is_primary=item.is_primary,
                status=item.status,
                created_by=actor_id,
                updated_by=actor_id,
            )
            for item in source.contacts
        ]
        self._repository.add(duplicate)
        self._commit_unique()
        return duplicate

    def list_categories(
        self, *, firm_id: UUID, include_deleted: bool = False
    ) -> list[VendorCategory]:
        """Return the firm's vendor categories."""
        return self._repository.list_categories(firm_id, include_deleted)

    def create_category(
        self, data: VendorCategoryWrite, *, firm_id: UUID, actor_id: UUID
    ) -> VendorCategory:
        """Add a vendor category."""
        category = VendorCategory(
            firm_id=firm_id,
            code=data.code,
            name=data.name,
            description=data.description,
            is_active=data.is_active,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._repository.add_category(category)
        self._commit_unique()
        return category

    def update_category(
        self,
        category_id: UUID,
        data: VendorCategoryWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> VendorCategory:
        """Change a vendor category."""
        category = self._repository.get_category(
            category_id, firm_id, include_deleted=True
        )
        if category is None:
            raise ResourceNotFoundError("Vendor category not found.")
        category.code = data.code
        category.name = data.name
        category.description = data.description
        category.is_active = data.is_active
        category.updated_by = actor_id
        category.is_deleted = False
        category.deleted_at = None
        category.deleted_by = None
        self._commit_unique()
        return category

    def delete_category(
        self, category_id: UUID, *, firm_id: UUID, actor_id: UUID
    ) -> None:
        """Soft delete a vendor category."""
        category = self._repository.get_category(
            category_id, firm_id, include_deleted=False
        )
        if category is None:
            raise ResourceNotFoundError("Vendor category not found.")
        category.is_deleted = True
        category.deleted_at = utc_now()
        category.deleted_by = actor_id
        category.updated_by = actor_id
        self._session.commit()

    def list_types(
        self, *, firm_id: UUID, include_deleted: bool = False
    ) -> list[VendorType]:
        """List types."""
        return self._repository.list_types(firm_id, include_deleted)

    def create_type(
        self, data: VendorTypeWrite, *, firm_id: UUID, actor_id: UUID
    ) -> VendorType:
        """Create type."""
        vendor_type = VendorType(
            firm_id=firm_id,
            code=data.code,
            name=data.name,
            description=data.description,
            is_active=data.is_active,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._repository.add_type(vendor_type)
        self._commit_unique()
        return vendor_type

    def update_type(
        self,
        type_id: UUID,
        data: VendorTypeWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> VendorType:
        """Change type."""
        vendor_type = self._repository.get_type(type_id, firm_id, include_deleted=True)
        if vendor_type is None:
            raise ResourceNotFoundError("Vendor type not found.")
        vendor_type.code = data.code
        vendor_type.name = data.name
        vendor_type.description = data.description
        vendor_type.is_active = data.is_active
        vendor_type.updated_by = actor_id
        vendor_type.is_deleted = False
        vendor_type.deleted_at = None
        vendor_type.deleted_by = None
        self._commit_unique()
        return vendor_type

    def delete_type(self, type_id: UUID, *, firm_id: UUID, actor_id: UUID) -> None:
        """Soft delete type."""
        vendor_type = self._repository.get_type(type_id, firm_id, include_deleted=False)
        if vendor_type is None:
            raise ResourceNotFoundError("Vendor type not found.")
        vendor_type.is_deleted = True
        vendor_type.deleted_at = utc_now()
        vendor_type.deleted_by = actor_id
        vendor_type.updated_by = actor_id
        self._session.commit()

    def _stage_create(
        self, data: VendorCreate, *, firm_id: UUID, actor_id: UUID
    ) -> Vendor:
        """Stage create."""
        self._assert_unique(firm_id, data)
        self._assert_drug_license_allowed(firm_id, data)
        vendor = Vendor(
            firm_id=firm_id,
            **self._vendor_values(data),
            created_by=actor_id,
            updated_by=actor_id,
        )
        # On create an omitted collection and an empty one mean the same
        # thing: a vendor that does not exist yet has nothing to preserve.
        vendor.contacts = [
            self._new_contact(item, actor_id) for item in data.contacts or []
        ]
        vendor.addresses = [
            self._new_address(item, actor_id) for item in data.addresses or []
        ]
        vendor.bank_accounts = [
            self._new_bank(item, actor_id) for item in data.banking or []
        ]
        vendor.tax_details = [self._new_tax(item, actor_id) for item in data.tax or []]
        vendor.attachments = [
            self._new_attachment(item, actor_id) for item in data.attachments or []
        ]
        vendor.notes = [self._new_note(item, actor_id) for item in data.notes or []]
        self._repository.add(vendor)
        self._repository.flush()
        record_audit(
            self._session,
            action="vendor.created",
            entity_type="vendor",
            entity_id=vendor.id,
            actor_id=actor_id,
            firm_id=vendor.firm_id,
            after_data=self._audit_snapshot(vendor),
        )
        return vendor

    def _assert_unique(
        self,
        firm_id: UUID,
        data: VendorCreate | VendorUpdate,
        excluding_id: UUID | None = None,
    ) -> None:
        """Assert unique."""
        if (
            self._repository.duplicate_id(
                firm_id,
                code=data.code,
                gstin=data.gstin,
                excluding_id=excluding_id,
            )
            is not None
        ):
            raise ConflictError("Vendor code or GSTIN already exists in this firm.")

    def _commit_unique(self) -> None:
        """Commit unique."""
        try:
            self._session.commit()
        except IntegrityError as error:
            self._session.rollback()
            raise self._unique_conflict() from error

    @staticmethod
    def _unique_conflict() -> ConflictError:
        """Return the conflict message for a duplicate natural key."""
        return ConflictError("Vendor uniqueness constraints were violated.")

    def _assert_drug_license_allowed(
        self, firm_id: UUID, data: VendorCreate | VendorUpdate
    ) -> None:
        """Only a firm whose profile handles pharmaceuticals records a licence.

        The field, not the vendor: a firm without DRUG_LICENSE still keeps
        vendors, it just has no business recording a drug licence number
        against one. The number lives on the vendor's tax rows rather than the
        vendor itself, so every submitted row is checked.
        """
        licences = {
            f"tax[{index}].drug_license": row.drug_license
            for index, row in enumerate(data.tax or [])
        }
        assert_feature_fields(
            self._session, firm_id, feature="DRUG_LICENSE", values=licences
        )

    @staticmethod
    def _vendor_values(data: VendorCreate | VendorUpdate) -> dict[str, object]:
        """Return values."""
        values = data.model_dump(
            exclude={
                "contacts",
                "addresses",
                "banking",
                "tax",
                "attachments",
                "notes",
            },
            mode="python",
        )
        values["status"] = data.status.value
        values["display_name"] = data.display_name or data.name
        return values

    @staticmethod
    def _new_contact(data: VendorContactInput, actor_id: UUID) -> VendorContact:
        """Build a vendor contact row from its payload."""
        return VendorContact(
            **data.model_dump(exclude={"id"}, mode="python"),
            created_by=actor_id,
            updated_by=actor_id,
        )

    @staticmethod
    def _new_address(data: VendorAddressInput, actor_id: UUID) -> VendorAddress:
        """Build a vendor address row from its payload."""
        values = data.model_dump(exclude={"id"}, mode="python")
        values["address_type"] = data.address_type.value
        return VendorAddress(**values, created_by=actor_id, updated_by=actor_id)

    @staticmethod
    def _new_bank(data: VendorBankInput, actor_id: UUID) -> VendorBankAccount:
        """Build a vendor bank account row from its payload."""
        return VendorBankAccount(
            **data.model_dump(exclude={"id"}, mode="python"),
            created_by=actor_id,
            updated_by=actor_id,
        )

    @staticmethod
    def _new_tax(data: VendorTaxInput, actor_id: UUID) -> VendorTaxDetail:
        """Build a vendor tax detail row from its payload."""
        return VendorTaxDetail(
            **data.model_dump(exclude={"id"}, mode="python"),
            created_by=actor_id,
            updated_by=actor_id,
        )

    @staticmethod
    def _new_attachment(
        data: VendorAttachmentInput, actor_id: UUID
    ) -> VendorAttachment:
        """Build a vendor attachment row from its payload."""
        return VendorAttachment(
            **data.model_dump(exclude={"id"}, mode="python"),
            created_by=actor_id,
            updated_by=actor_id,
        )

    @staticmethod
    def _new_note(data: VendorNoteInput, actor_id: UUID) -> VendorNote:
        """Build a vendor note row from its payload."""
        return VendorNote(
            **data.model_dump(exclude={"id"}, mode="python"),
            created_by=actor_id,
            updated_by=actor_id,
        )

    def _reconcile_contacts(
        self,
        vendor: Vendor,
        inputs: list[VendorContactInput],
        actor_id: UUID,
    ) -> None:
        """Reconcile contacts."""
        existing = {item.id: item for item in vendor.contacts}
        requested = {item.id for item in inputs if item.id is not None}
        for item in inputs:
            row = existing.get(item.id) if item.id else None
            if item.id and row is None:
                raise ResourceNotFoundError("A vendor contact no longer exists.")
            if row is None:
                vendor.contacts.append(self._new_contact(item, actor_id))
                continue
            for field, value in item.model_dump(exclude={"id"}, mode="python").items():
                setattr(row, field, value)
            row.updated_by = actor_id
        self._mark_removed(existing, requested, actor_id)

    def _reconcile_addresses(
        self,
        vendor: Vendor,
        inputs: list[VendorAddressInput],
        actor_id: UUID,
    ) -> None:
        """Reconcile addresses."""
        existing = {item.id: item for item in vendor.addresses}
        requested = {item.id for item in inputs if item.id is not None}
        for item in inputs:
            row = existing.get(item.id) if item.id else None
            if item.id and row is None:
                raise ResourceNotFoundError("A vendor address no longer exists.")
            if row is None:
                vendor.addresses.append(self._new_address(item, actor_id))
                continue
            values = item.model_dump(exclude={"id"}, mode="python")
            values["address_type"] = item.address_type.value
            for field, value in values.items():
                setattr(row, field, value)
            row.updated_by = actor_id
        self._mark_removed(existing, requested, actor_id)

    def _reconcile_banks(
        self,
        vendor: Vendor,
        inputs: list[VendorBankInput],
        actor_id: UUID,
    ) -> None:
        """Reconcile banks."""
        existing = {item.id: item for item in vendor.bank_accounts}
        requested = {item.id for item in inputs if item.id is not None}
        for item in inputs:
            row = existing.get(item.id) if item.id else None
            if item.id and row is None:
                raise ResourceNotFoundError("A vendor bank account no longer exists.")
            if row is None:
                vendor.bank_accounts.append(self._new_bank(item, actor_id))
                continue
            for field, value in item.model_dump(exclude={"id"}, mode="python").items():
                setattr(row, field, value)
            row.updated_by = actor_id
        self._mark_removed(existing, requested, actor_id)

    def _reconcile_tax(
        self,
        vendor: Vendor,
        inputs: list[VendorTaxInput],
        actor_id: UUID,
    ) -> None:
        """Reconcile tax."""
        existing = {item.id: item for item in vendor.tax_details}
        requested = {item.id for item in inputs if item.id is not None}
        for item in inputs:
            row = existing.get(item.id) if item.id else None
            if item.id and row is None:
                raise ResourceNotFoundError("A vendor tax row no longer exists.")
            if row is None:
                vendor.tax_details.append(self._new_tax(item, actor_id))
                continue
            for field, value in item.model_dump(exclude={"id"}, mode="python").items():
                setattr(row, field, value)
            row.updated_by = actor_id
        self._mark_removed(existing, requested, actor_id)

    def _reconcile_attachments(
        self,
        vendor: Vendor,
        inputs: list[VendorAttachmentInput],
        actor_id: UUID,
    ) -> None:
        """Reconcile attachments."""
        existing = {item.id: item for item in vendor.attachments}
        requested = {item.id for item in inputs if item.id is not None}
        for item in inputs:
            row = existing.get(item.id) if item.id else None
            if item.id and row is None:
                raise ResourceNotFoundError("A vendor attachment no longer exists.")
            if row is None:
                vendor.attachments.append(self._new_attachment(item, actor_id))
                continue
            for field, value in item.model_dump(exclude={"id"}, mode="python").items():
                setattr(row, field, value)
            row.updated_by = actor_id
        self._mark_removed(existing, requested, actor_id)

    def _reconcile_notes(
        self,
        vendor: Vendor,
        inputs: list[VendorNoteInput],
        actor_id: UUID,
    ) -> None:
        """Reconcile notes."""
        existing = {item.id: item for item in vendor.notes}
        requested = {item.id for item in inputs if item.id is not None}
        for item in inputs:
            row = existing.get(item.id) if item.id else None
            if item.id and row is None:
                raise ResourceNotFoundError("A vendor note no longer exists.")
            if row is None:
                vendor.notes.append(self._new_note(item, actor_id))
                continue
            for field, value in item.model_dump(exclude={"id"}, mode="python").items():
                setattr(row, field, value)
            row.updated_by = actor_id
        self._mark_removed(existing, requested, actor_id)

    @staticmethod
    def _mark_removed(
        existing: Mapping[UUID, BaseEntity],
        requested_ids: set[UUID],
        actor_id: UUID,
    ) -> None:
        """Soft delete the child rows the caller left out of the payload."""
        now = utc_now()
        for row_id, row in existing.items():
            if row_id in requested_ids:
                continue
            row.is_deleted = True
            row.deleted_at = now
            row.deleted_by = actor_id
            row.updated_by = actor_id

    @staticmethod
    def _vendor_values_for_duplicate(vendor: Vendor) -> dict[str, object]:
        """Return values for duplicate."""
        return {
            "name": vendor.name,
            "legal_name": vendor.legal_name,
            "display_name": f"{vendor.display_name} (Copy)",
            "category_id": vendor.category_id,
            "type_id": vendor.type_id,
            "business_profile_id": vendor.business_profile_id,
            "status": vendor.status,
            "gst_registration": vendor.gst_registration,
            "gstin": None,
            "pan": vendor.pan,
            "license_number": vendor.license_number,
            "registration_number": vendor.registration_number,
            "website": vendor.website,
            "email": vendor.email,
            "phone": vendor.phone,
            "mobile": vendor.mobile,
            "remarks": vendor.remarks,
            "business_attributes": dict(vendor.business_attributes),
        }

    @staticmethod
    def _audit_snapshot(vendor: Vendor) -> dict[str, object]:
        """Audit snapshot."""
        return {
            "firm_id": str(vendor.firm_id),
            "code": vendor.code,
            "name": vendor.name,
            "status": vendor.status,
            "contact_count": sum(not item.is_deleted for item in vendor.contacts),
            "address_count": sum(not item.is_deleted for item in vendor.addresses),
            "bank_count": sum(not item.is_deleted for item in vendor.bank_accounts),
            "tax_count": sum(not item.is_deleted for item in vendor.tax_details),
            "is_deleted": vendor.is_deleted,
        }

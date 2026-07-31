"""Transactional application service for customer management."""

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ConflictError, ResourceNotFoundError
from app.core.utils.dates import utc_now
from app.customers.models import Customer, CustomerAddress, CustomerContact
from app.customers.repositories import CustomerRepository
from app.customers.schemas import (
    CustomerAddressInput,
    CustomerContactInput,
    CustomerCreate,
    CustomerSummary,
    CustomerUpdate,
)
from app.customers.schemas.customer import CustomerListFilters


class CustomerService:
    """Coordinate validated customer mutations, queries, and audits."""

    def __init__(self, session: Session) -> None:
        """Bind the service to one request unit of work."""
        self._session = session
        self._repository = CustomerRepository(session)

    def create(
        self, data: CustomerCreate, *, firm_id: UUID, actor_id: UUID
    ) -> Customer:
        """Create a firm-owned customer and all nested records."""
        try:
            customer = self._stage_create(data, firm_id=firm_id, actor_id=actor_id)
        except IntegrityError as error:
            self._session.rollback()
            raise self._unique_conflict() from error
        self._commit_unique()
        return customer

    def import_customers(
        self,
        records: list[CustomerCreate],
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> list[Customer]:
        """Create a validated customer batch in one transaction."""
        try:
            customers = [
                self._stage_create(data, firm_id=firm_id, actor_id=actor_id)
                for data in records
            ]
        except (ConflictError, IntegrityError) as error:
            self._session.rollback()
            if isinstance(error, ConflictError):
                raise
            raise self._unique_conflict() from error
        self._commit_unique()
        return customers

    def _stage_create(
        self, data: CustomerCreate, *, firm_id: UUID, actor_id: UUID
    ) -> Customer:
        """Stage one customer and audit event without committing."""
        self._assert_unique(firm_id, data)
        values = self._customer_values(data)
        customer = Customer(
            firm_id=firm_id,
            **values,
            created_by=actor_id,
            updated_by=actor_id,
        )
        customer.addresses = [
            self._new_address(address, actor_id) for address in data.addresses
        ]
        customer.contacts = [
            self._new_contact(contact, actor_id) for contact in data.contacts
        ]
        self._repository.add(customer)
        self._repository.flush()
        record_audit(
            self._session,
            action="customer.created",
            entity_type="customer",
            entity_id=customer.id,
            actor_id=actor_id,
            firm_id=customer.firm_id,
            after_data=self._audit_snapshot(customer),
        )
        return customer

    def get(
        self,
        customer_id: UUID,
        *,
        firm_scope: UUID | None,
        include_deleted: bool = False,
    ) -> Customer:
        """Return one customer inside the authorized firm scope."""
        customer = self._repository.get(
            customer_id, firm_scope, include_deleted=include_deleted
        )
        if customer is None:
            raise ResourceNotFoundError("Customer not found.")
        return customer

    def update(
        self,
        customer_id: UUID,
        data: CustomerUpdate,
        *,
        firm_scope: UUID | None,
        actor_id: UUID,
    ) -> Customer:
        """Replace customer fields and reconcile addresses and contacts."""
        customer = self.get(customer_id, firm_scope=firm_scope)
        self._assert_unique(customer.firm_id, data, excluding_id=customer.id)
        before = self._audit_snapshot(customer)
        for field, value in self._customer_values(data).items():
            setattr(customer, field, value)
        customer.display_name = data.display_name or data.name
        customer.updated_by = actor_id
        self._reconcile_addresses(customer, data.addresses, actor_id)
        self._reconcile_contacts(customer, data.contacts, actor_id)
        record_audit(
            self._session,
            action="customer.updated",
            entity_type="customer",
            entity_id=customer.id,
            actor_id=actor_id,
            firm_id=customer.firm_id,
            before_data=before,
            after_data=self._audit_snapshot(customer),
        )
        self._commit_unique()
        self._session.expire(customer, ["addresses", "contacts"])
        return customer

    def delete(
        self, customer_id: UUID, *, firm_scope: UUID | None, actor_id: UUID
    ) -> None:
        """Soft delete one customer and audit the lifecycle action."""
        customer = self.get(customer_id, firm_scope=firm_scope)
        before = self._audit_snapshot(customer)
        customer.is_deleted = True
        customer.deleted_at = utc_now()
        customer.deleted_by = actor_id
        customer.updated_by = actor_id
        record_audit(
            self._session,
            action="customer.deleted",
            entity_type="customer",
            entity_id=customer.id,
            actor_id=actor_id,
            firm_id=customer.firm_id,
            before_data=before,
        )
        self._session.commit()

    def restore(
        self, customer_id: UUID, *, firm_scope: UUID | None, actor_id: UUID
    ) -> Customer:
        """Restore one soft-deleted customer."""
        customer = self.get(customer_id, firm_scope=firm_scope, include_deleted=True)
        if not customer.is_deleted:
            return customer
        customer.is_deleted = False
        customer.deleted_at = None
        customer.deleted_by = None
        customer.updated_by = actor_id
        record_audit(
            self._session,
            action="customer.restored",
            entity_type="customer",
            entity_id=customer.id,
            actor_id=actor_id,
            firm_id=customer.firm_id,
            after_data=self._audit_snapshot(customer),
        )
        self._session.commit()
        return customer

    def list_customers(
        self,
        *,
        firm_scope: UUID | None,
        filters: CustomerListFilters,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
    ) -> tuple[list[Customer], int]:
        """Return a firm-safe filtered customer page."""
        return self._repository.list_customers(
            firm_scope=firm_scope,
            filters=filters,
            search=search,
            sort_by=sort_by,
            descending=descending,
            offset=(page - 1) * page_size,
            limit=page_size,
        )

    def summary(
        self, *, firm_scope: UUID | None, filters: CustomerListFilters
    ) -> CustomerSummary:
        """Return aggregate customer lifecycle and financial values."""
        (
            total,
            active,
            inactive,
            on_hold,
            deleted,
            credit_limit,
            opening_balance,
        ) = self._repository.summary(firm_scope, filters)
        return CustomerSummary(
            total=total,
            active=active,
            inactive=inactive,
            on_hold=on_hold,
            deleted=deleted,
            total_credit_limit=credit_limit,
            total_opening_balance=opening_balance,
        )

    def addresses(
        self, customer_id: UUID, *, firm_scope: UUID | None
    ) -> list[CustomerAddress]:
        """Return active addresses after verifying customer visibility."""
        self.get(customer_id, firm_scope=firm_scope)
        return self._repository.active_addresses(customer_id)

    def contacts(
        self, customer_id: UUID, *, firm_scope: UUID | None
    ) -> list[CustomerContact]:
        """Return active contacts after verifying customer visibility."""
        self.get(customer_id, firm_scope=firm_scope)
        return self._repository.active_contacts(customer_id)

    def _assert_unique(
        self,
        firm_id: UUID,
        data: CustomerCreate | CustomerUpdate,
        excluding_id: UUID | None = None,
    ) -> None:
        if (
            self._repository.duplicate_id(
                firm_id,
                code=data.code,
                gst_number=data.gst_number,
                pan_number=data.pan_number,
                excluding_id=excluding_id,
            )
            is not None
        ):
            raise ConflictError(
                "Customer code, GST number, or PAN number already exists "
                "in this firm."
            )

    def _commit_unique(self) -> None:
        try:
            self._session.commit()
        except IntegrityError as error:
            self._session.rollback()
            raise self._unique_conflict() from error

    @staticmethod
    def _unique_conflict() -> ConflictError:
        return ConflictError(
            "Customer code, GST number, or PAN number already exists " "in this firm."
        )

    @staticmethod
    def _customer_values(
        data: CustomerCreate | CustomerUpdate,
    ) -> dict[str, object]:
        values = data.model_dump(exclude={"addresses", "contacts"}, mode="python")
        values["customer_type"] = data.customer_type.value
        values["status"] = data.status.value
        values["display_name"] = data.display_name or data.name
        return values

    @staticmethod
    def _new_address(data: CustomerAddressInput, actor_id: UUID) -> CustomerAddress:
        values = data.model_dump(exclude={"id"}, mode="python")
        values["address_type"] = data.address_type.value
        return CustomerAddress(**values, created_by=actor_id, updated_by=actor_id)

    @staticmethod
    def _new_contact(data: CustomerContactInput, actor_id: UUID) -> CustomerContact:
        return CustomerContact(
            **data.model_dump(exclude={"id"}, mode="python"),
            created_by=actor_id,
            updated_by=actor_id,
        )

    def _reconcile_addresses(
        self,
        customer: Customer,
        inputs: list[CustomerAddressInput],
        actor_id: UUID,
    ) -> None:
        existing = {address.id: address for address in customer.addresses}
        requested_ids = {item.id for item in inputs if item.id is not None}
        for item in inputs:
            address = existing.get(item.id) if item.id is not None else None
            if item.id is not None and address is None:
                raise ResourceNotFoundError("A customer address no longer exists.")
            if address is None:
                address = self._new_address(item, actor_id)
                customer.addresses.append(address)
            else:
                values = item.model_dump(exclude={"id"}, mode="python")
                values["address_type"] = item.address_type.value
                for field, value in values.items():
                    setattr(address, field, value)
                address.updated_by = actor_id
        now = utc_now()
        for address_id, address in existing.items():
            if address_id not in requested_ids:
                address.is_deleted = True
                address.deleted_at = now
                address.deleted_by = actor_id
                address.updated_by = actor_id

    def _reconcile_contacts(
        self,
        customer: Customer,
        inputs: list[CustomerContactInput],
        actor_id: UUID,
    ) -> None:
        existing = {contact.id: contact for contact in customer.contacts}
        requested_ids = {item.id for item in inputs if item.id is not None}
        for item in inputs:
            contact = existing.get(item.id) if item.id is not None else None
            if item.id is not None and contact is None:
                raise ResourceNotFoundError("A customer contact no longer exists.")
            if contact is None:
                contact = self._new_contact(item, actor_id)
                customer.contacts.append(contact)
            else:
                for field, value in item.model_dump(
                    exclude={"id"}, mode="python"
                ).items():
                    setattr(contact, field, value)
                contact.updated_by = actor_id
        now = utc_now()
        for contact_id, contact in existing.items():
            if contact_id not in requested_ids:
                contact.is_deleted = True
                contact.deleted_at = now
                contact.deleted_by = actor_id
                contact.updated_by = actor_id

    @staticmethod
    def _audit_snapshot(customer: Customer) -> dict[str, object]:
        return {
            "firm_id": str(customer.firm_id),
            "code": customer.code,
            "name": customer.name,
            "status": customer.status,
            "credit_limit": str(customer.credit_limit),
            "opening_balance": str(customer.opening_balance),
            "address_count": sum(not item.is_deleted for item in customer.addresses),
            "contact_count": sum(not item.is_deleted for item in customer.contacts),
            "is_deleted": customer.is_deleted,
        }

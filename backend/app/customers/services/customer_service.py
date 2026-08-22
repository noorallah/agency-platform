"""Transactional application service for customer management."""

from datetime import date
from decimal import Decimal
from typing import ClassVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.customers.models import (
    Customer,
    CustomerAddress,
    CustomerContact,
    CustomerReceivableTransaction,
)
from app.customers.repositories import CustomerRepository
from app.customers.schemas import (
    CustomerAddressInput,
    CustomerContactInput,
    CustomerCreate,
    CustomerReceivableSummary,
    CustomerReceivableTransactionCreate,
    CustomerReceivableTransactionType,
    CustomerSummary,
    CustomerUpdate,
)
from app.customers.schemas.customer import CustomerListFilters
from app.finance.models import JournalEntry
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine
from app.sales.models.territory import (
    GeoCity,
    GeoCountry,
    GeoDistrict,
    GeoLocality,
    GeoPostalCode,
    GeoState,
)

#: Any of the six geography masters. They share `BaseEntity` and a `name` (a
#: postal code calls its own column `postal_code`), which is all this module
#: reads off them.
GeoRow = GeoCountry | GeoState | GeoDistrict | GeoCity | GeoPostalCode | GeoLocality


class CustomerService:
    """Coordinate validated customer mutations, queries, and audits."""

    def __init__(self, session: Session) -> None:
        """Bind the service to one request unit of work."""
        self._session = session
        self._repository = CustomerRepository(session)
        self._posting = DocumentPostingService(session)

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
        (
            values["current_outstanding"],
            values["unapplied_advance_balance"],
        ) = self._normalize_customer_balances(data.opening_balance)
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
        self._record_opening_balance_transaction(
            customer=customer,
            amount=data.opening_balance,
            actor_id=actor_id,
        )
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
        # Partial on update: a field the caller never mentioned keeps what the
        # row holds. Every optional field on the write model has a default, so
        # dumping in full turns an omission into an instruction -- the shape
        # that cost a vendor its addresses and reset an approved order to
        # draft. An explicit null still clears, which is what keeps a complete
        # client able to empty a field.
        values = self._customer_values(data, partial=True)
        # The dump is untyped, so the figure is read back as a Decimal before
        # any of the balance arithmetic below touches it.
        opening_balance = Decimal(
            str(values.get("opening_balance", customer.opening_balance))
        )
        if (
            customer.opening_balance != opening_balance
            and self._repository.has_receivable_transactions(customer.id)
        ):
            raise ValidationError(
                "Opening balance cannot be changed after receivable activity exists."
            )
        before = self._audit_snapshot(customer)
        # Read before the field loop below overwrites it: whether the opening
        # balance moved is what decides if any of the balance work runs at all.
        balance_changed = customer.opening_balance != opening_balance
        if "name" in values or "display_name" in values:
            # Only recomputed when one of the two was actually sent. The
            # fallback is the stored name rather than the sent one, so clearing
            # the display name alone leaves the customer named after itself.
            values["display_name"] = (
                values.get("display_name") or values.get("name") or customer.name
            )
        for field, value in values.items():
            setattr(customer, field, value)
        if balance_changed:
            # Only reachable when the customer has no receivable activity --
            # the guard above refuses it otherwise -- so recomputing the
            # balances from the opening figure is the whole truth about them.
            #
            # It used to run on every update, which silently discarded
            # everything the customer had traded: an edit to a phone number
            # reset `current_outstanding` to the opening balance, and the
            # receivable control account was then out by the difference. On the
            # seeded WHOLE01 firm one such edit moved a customer from 84,901.23
            # to 25,000.00 and put the store 59,901.23 out.
            (
                customer.current_outstanding,
                customer.unapplied_advance_balance,
            ) = self._normalize_customer_balances(opening_balance)
            self._reset_opening_balance_transaction(
                customer=customer,
                amount=opening_balance,
                actor_id=actor_id,
            )
        customer.updated_by = actor_id
        # Both collections are replaced rather than merged, so reconciling one
        # the caller never sent would soft-delete every row in it -- the defect
        # that destroyed a vendor's addresses, contacts and bank accounts when
        # somebody corrected a phone number. Sending an empty list still
        # clears; saying nothing leaves them alone.
        if "addresses" in data.model_fields_set:
            self._reconcile_addresses(customer, data.addresses, actor_id)
        if "contacts" in data.model_fields_set:
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
        """Soft delete one customer and audit the lifecycle action.

        A customer with an opening balance takes its journal with it. The
        balance leaves the customer's account on delete, so leaving the entry
        behind would put the receivable control account above what anybody is
        recorded as owing -- which is the same drift in the other direction.
        """
        customer = self.get(customer_id, firm_scope=firm_scope)
        before = self._audit_snapshot(customer)
        self._reverse_opening_balance_postings(customer, actor_id=actor_id)
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
            current_outstanding,
            unapplied_advance,
        ) = self._repository.summary(firm_scope, filters)
        return CustomerSummary(
            total=total,
            active=active,
            inactive=inactive,
            on_hold=on_hold,
            deleted=deleted,
            total_credit_limit=credit_limit,
            total_opening_balance=opening_balance,
            total_current_outstanding=current_outstanding,
            total_unapplied_advance=unapplied_advance,
        )

    def receivable_summary(
        self,
        customer_id: UUID,
        *,
        firm_scope: UUID | None,
    ) -> CustomerReceivableSummary:
        """Return one customer's receivable and advance balances."""
        customer = self.get(customer_id, firm_scope=firm_scope)
        return CustomerReceivableSummary(
            customer_id=customer.id,
            customer_name=customer.display_name,
            outstanding=customer.current_outstanding,
            unapplied_advance=customer.unapplied_advance_balance,
            net_position=(
                customer.current_outstanding - customer.unapplied_advance_balance
            ),
        )

    def receivable_transactions(
        self,
        customer_id: UUID,
        *,
        firm_scope: UUID | None,
        page: int,
        page_size: int,
    ) -> tuple[list[CustomerReceivableTransaction], int]:
        """Return paged receivable transactions after firm-scope validation."""
        customer = self.get(customer_id, firm_scope=firm_scope)
        return self._repository.list_receivable_transactions(
            customer.id,
            offset=(page - 1) * page_size,
            limit=page_size,
        )

    def post_receivable_transaction(
        self,
        customer_id: UUID,
        payload: CustomerReceivableTransactionCreate,
        *,
        firm_scope: UUID | None,
        actor_id: UUID,
        commit: bool = True,
    ) -> CustomerReceivableTransaction:
        """Post one immutable receivable transaction and update customer balances."""
        customer = self.get(customer_id, firm_scope=firm_scope)
        amount = payload.amount
        current = customer.current_outstanding
        advance = customer.unapplied_advance_balance
        outstanding_delta = Decimal("0")
        advance_delta = Decimal("0")
        tx_type = payload.transaction_type

        if tx_type == CustomerReceivableTransactionType.OPENING_BALANCE:
            raise ValidationError("Opening balance transactions are system-managed.")
        if tx_type == CustomerReceivableTransactionType.REVERSAL:
            raise ValidationError(
                "A reversal is posted against the transaction it undoes, "
                "not on its own."
            )
        if tx_type == CustomerReceivableTransactionType.INVOICE:
            outstanding_delta = amount
        elif tx_type in {
            CustomerReceivableTransactionType.RECEIPT,
            CustomerReceivableTransactionType.CREDIT_NOTE,
        }:
            applied = amount if amount <= current else current
            excess = amount - applied
            outstanding_delta = -applied
            advance_delta = excess
        elif tx_type == CustomerReceivableTransactionType.ADVANCE_RECEIPT:
            advance_delta = amount
        elif tx_type == CustomerReceivableTransactionType.ADVANCE_APPLY:
            applicable = amount
            if applicable > advance:
                raise ValidationError("Advance apply amount exceeds unapplied advance.")
            if applicable > current:
                raise ValidationError(
                    "Advance apply amount exceeds outstanding balance."
                )
            outstanding_delta = -applicable
            advance_delta = -applicable
        elif tx_type == CustomerReceivableTransactionType.REFUND:
            if amount > advance:
                raise ValidationError("Refund amount exceeds unapplied advance.")
            advance_delta = -amount
        else:
            raise ValidationError("Unsupported receivable transaction type.")

        outstanding_after = current + outstanding_delta
        advance_after = advance + advance_delta
        if outstanding_after < 0 or advance_after < 0:
            raise ValidationError("Receivable balances cannot become negative.")

        customer.current_outstanding = outstanding_after
        customer.unapplied_advance_balance = advance_after
        customer.updated_by = actor_id
        row = self._record_receivable_transaction(
            customer=customer,
            tx_type=tx_type.value,
            amount=amount,
            outstanding_delta=outstanding_delta,
            advance_delta=advance_delta,
            transaction_date=payload.transaction_date,
            reference_type=payload.reference_type,
            reference_id=payload.reference_id,
            reference_number=payload.reference_number,
            remarks=payload.remarks,
            actor_id=actor_id,
        )
        record_audit(
            self._session,
            action="customer.receivable_transaction_posted",
            entity_type="customer",
            entity_id=customer.id,
            actor_id=actor_id,
            firm_id=customer.firm_id,
            after_data={
                "transaction_type": tx_type.value,
                "amount": str(amount),
                "outstanding_after": str(customer.current_outstanding),
                "unapplied_advance_after": str(customer.unapplied_advance_balance),
            },
        )
        if commit:
            self._session.commit()
        return row

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
        *,
        partial: bool = False,
    ) -> dict[str, object]:
        """Return the column values a write model carries.

        ``partial`` dumps only what the caller actually sent, which is right on
        update and wrong on create -- there a default really is the value to
        store, and a new customer needs every column filled.
        """
        values = data.model_dump(
            exclude={"addresses", "contacts"}, mode="python", exclude_unset=partial
        )
        if "customer_type" in values:
            values["customer_type"] = data.customer_type.value
        if "status" in values:
            values["status"] = data.status.value
        if not partial:
            values["display_name"] = data.display_name or data.name
        return values

    #: Which geography level fills which free-text column, and what to read
    #: off the master row. The text stays NOT NULL and every report reads it,
    #: so it is derived rather than left to disagree with the key beside it.
    _PLACE_TEXT: ClassVar[
        tuple[tuple[str, type[GeoRow], str, tuple[str, ...], str], ...]
    ] = (
        # A country's text column is two characters, so it takes `iso2` and
        # falls back to `code` for a row that never had one.
        ("country_id", GeoCountry, "country", ("iso2", "code"), ""),
        ("state_id", GeoState, "state", ("name",), "country_id"),
        ("district_id", GeoDistrict, "district", ("name",), "state_id"),
        ("city_id", GeoCity, "city", ("name",), "district_id"),
        ("postal_code_id", GeoPostalCode, "postal_code", ("postal_code",), "city_id"),
        ("locality_id", GeoLocality, "area", ("name",), "postal_code_id"),
    )

    def _apply_place(
        self, values: dict[str, object], data: CustomerAddressInput
    ) -> None:
        """Fill the free-text columns from whichever geography keys were sent.

        Blank keys change nothing, so a firm with no masters -- and every
        client written before these columns existed -- keeps working on the
        text alone. Where a key is given it wins: the alternative is a row
        whose ``city`` says one thing and whose ``city_id`` says another, and
        nothing to say which a report should believe.
        """
        chosen: dict[str, UUID] = {}
        for field, model, text_field, attributes, parent_field in self._PLACE_TEXT:
            place_id: UUID | None = getattr(data, field)
            if place_id is None:
                continue
            row = self._session.get(model, place_id)
            if row is None or row.is_deleted:
                raise ValidationError(
                    f"That {text_field.replace('_', ' ')} is unknown."
                )
            parent_id = chosen.get(parent_field) if parent_field else None
            if parent_id is not None and getattr(row, parent_field) != parent_id:
                raise ValidationError(
                    "That address names places that do not belong together."
                )
            text: str | None = None
            for attribute in attributes:
                text = getattr(row, attribute, None)
                if text:
                    break
            if not text:
                raise ValidationError(
                    f"That {text_field.replace('_', ' ')} has no name."
                )
            chosen[field] = place_id
            values[text_field] = text[:100]

    def _new_address(
        self, data: CustomerAddressInput, actor_id: UUID
    ) -> CustomerAddress:
        values = data.model_dump(exclude={"id"}, mode="python")
        values["address_type"] = data.address_type.value
        self._apply_place(values, data)
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
                self._apply_place(values, item)
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
            "current_outstanding": str(customer.current_outstanding),
            "unapplied_advance_balance": str(customer.unapplied_advance_balance),
            "address_count": sum(not item.is_deleted for item in customer.addresses),
            "contact_count": sum(not item.is_deleted for item in customer.contacts),
            "is_deleted": customer.is_deleted,
        }

    @staticmethod
    def _normalize_customer_balances(
        opening_balance: Decimal,
    ) -> tuple[Decimal, Decimal]:
        """Split a signed opening balance into outstanding and advance."""
        zero = Decimal("0")
        outstanding = opening_balance if opening_balance > 0 else zero
        advance = -opening_balance if opening_balance < 0 else zero
        return outstanding, advance

    def _reverse_opening_balance_postings(
        self, customer: Customer, *, actor_id: UUID
    ) -> None:
        """Mirror every journal this customer's opening balances have posted.

        Used by both paths that make an opening balance stop being true:
        revising it and deleting the customer. Each reversal takes the original
        entry's reference with `-REV`, so the pair reads as one correction.
        """
        engine = JournalEntryEngine(self._session)
        for row in self._session.scalars(
            select(CustomerReceivableTransaction).where(
                CustomerReceivableTransaction.customer_id == customer.id,
                CustomerReceivableTransaction.transaction_type
                == CustomerReceivableTransactionType.OPENING_BALANCE.value,
                CustomerReceivableTransaction.journal_entry_id.is_not(None),
            )
        ).all():
            if row.journal_entry_id is None:
                continue
            original = self._session.get(JournalEntry, row.journal_entry_id)
            engine.reverse_entry(
                row.journal_entry_id,
                firm_id=customer.firm_id,
                reference_number=(
                    f"{original.reference_number}-REV"
                    if original is not None
                    else f"{customer.code}-OB-REV"
                ),
                actor_id=actor_id,
            )
            row.journal_entry_id = None

    def _opening_balance_reference(self, customer: Customer) -> str:
        """Return a journal reference no earlier opening balance has taken.

        Journal references are unique per firm, and a customer code is not:
        soft-deleting a customer releases the code, and revising an opening
        balance posts a second entry for the same one. Both collided on the
        bare code.
        """
        base = f"{customer.code}-OB"
        taken = set(
            self._session.scalars(
                select(JournalEntry.reference_number).where(
                    JournalEntry.firm_id == customer.firm_id,
                    JournalEntry.reference_number.like(f"{base}%"),
                )
            ).all()
        )
        if base not in taken:
            return base
        suffix = 2
        while f"{base}{suffix}" in taken:
            suffix += 1
        return f"{base}{suffix}"

    def _record_opening_balance_transaction(
        self,
        *,
        customer: Customer,
        amount: Decimal,
        actor_id: UUID,
    ) -> None:
        """Record a day-one balance on the customer's account and in the ledger.

        Both, together. This wrote the receivable transaction and stopped, so a
        firm's customers could owe it 885,000 against a receivable control
        account of zero -- the same shape of gap that cancelling an invoice had
        until 2026-08-14, and the one `verify_sample_data.py` exists to catch.

        The posting runs first and is allowed to fail the write: a balance the
        firm cannot book is one it should not be told it has recorded. A firm
        with no chart of accounts therefore cannot open a customer with a
        balance -- it can still open the customer -- and the error says which
        setup is missing.
        """
        if amount == 0:
            return
        try:
            entry = self._posting.post_opening_balance(
                firm_id=customer.firm_id,
                customer_id=customer.id,
                reference_number=self._opening_balance_reference(customer),
                posting_date=utc_now().date(),
                amount=amount,
                actor_id=actor_id,
            )
        except ValidationError as error:
            # `_require_mapping` speaks about approving a document, which is
            # not what anybody is doing here. Say what this operation needs.
            raise ValidationError(
                f"{customer.code} cannot open with a balance: {error}. An "
                "opening balance is money owed and has to be booked, so the "
                "firm needs a chart of accounts and an open period covering "
                "today. Create the customer without a balance, or complete "
                "the firm's finance setup first."
            ) from error
        zero = Decimal("0")
        outstanding_delta = amount if amount > 0 else zero
        advance_delta = -amount if amount < 0 else zero
        self._record_receivable_transaction(
            customer=customer,
            tx_type=CustomerReceivableTransactionType.OPENING_BALANCE.value,
            amount=abs(amount),
            outstanding_delta=outstanding_delta,
            advance_delta=advance_delta,
            transaction_date=utc_now().date(),
            reference_type="CUSTOMER_MASTER",
            reference_id=customer.id,
            reference_number=customer.code,
            remarks="Opening balance seeded from customer financial profile.",
            actor_id=actor_id,
            journal_entry_id=None if entry is None else entry.id,
        )

    def reverse_receivable_transaction(
        self,
        transaction_id: UUID,
        *,
        firm_scope: UUID | None,
        actor_id: UUID,
        reference_number: str | None = None,
        remarks: str | None = None,
        commit: bool = True,
    ) -> CustomerReceivableTransaction:
        """Undo one receivable transaction by its own recorded deltas.

        The deltas are read from the row rather than recomputed from its type,
        which is the whole reason this can be correct. A receipt of 500 against
        an outstanding 300 became 300 off the balance and 200 of advance; a
        reversal that re-derived those numbers from the *current* balance would
        put back something else entirely.

        Args:
            transaction_id: The transaction to undo.
            firm_scope: The firm the caller is acting in.
            actor_id: The user reversing it.
            reference_number: What to call the reversal.
            remarks: Why it was reversed.
            commit: Whether to commit, so a caller inside a larger unit of
                work can keep the whole thing atomic.

        Returns:
            The reversal row.

        Raises:
            ResourceNotFoundError: If the transaction is not visible.
            ValidationError: If it is a reversal, is already reversed, or the
                undo would drive a balance negative.

        """
        original = self._session.scalar(
            select(CustomerReceivableTransaction).where(
                CustomerReceivableTransaction.id == transaction_id,
                CustomerReceivableTransaction.is_deleted.is_(False),
            )
        )
        if original is None:
            raise ResourceNotFoundError("Receivable transaction not found.")
        customer = self.get(original.customer_id, firm_scope=firm_scope)
        if original.transaction_type == CustomerReceivableTransactionType.REVERSAL:
            raise ValidationError("A reversal cannot itself be reversed.")
        already = self._session.scalar(
            select(CustomerReceivableTransaction.id).where(
                CustomerReceivableTransaction.reference_type == "reversal",
                CustomerReceivableTransaction.reference_id == original.id,
                CustomerReceivableTransaction.is_deleted.is_(False),
            )
        )
        if already is not None:
            raise ValidationError("This transaction has already been reversed.")

        outstanding_after = customer.current_outstanding - original.outstanding_delta
        advance_after = customer.unapplied_advance_balance - original.advance_delta
        if outstanding_after < 0 or advance_after < 0:
            # The customer has traded since, and undoing this now would leave
            # them owing less than nothing. Refusing is the honest answer:
            # the correction needed is a credit note, not a reversal.
            raise ValidationError(
                "Reversing this would drive the customer's balance negative. "
                "It has been overtaken by later transactions."
            )
        customer.current_outstanding = outstanding_after
        customer.unapplied_advance_balance = advance_after
        customer.updated_by = actor_id
        row = self._record_receivable_transaction(
            customer=customer,
            tx_type=CustomerReceivableTransactionType.REVERSAL.value,
            amount=original.amount,
            outstanding_delta=-original.outstanding_delta,
            advance_delta=-original.advance_delta,
            transaction_date=original.transaction_date,
            reference_type="reversal",
            reference_id=original.id,
            reference_number=reference_number or original.reference_number,
            remarks=remarks,
            actor_id=actor_id,
        )
        record_audit(
            self._session,
            action="customer.receivable_transaction_reversed",
            entity_type="customer",
            entity_id=customer.id,
            actor_id=actor_id,
            firm_id=customer.firm_id,
            before_data={"transaction_id": str(original.id)},
            after_data={
                "outstanding_delta": str(row.outstanding_delta),
                "advance_delta": str(row.advance_delta),
            },
        )
        self._session.flush()
        if commit:
            self._session.commit()
        return row

    def _record_receivable_transaction(
        self,
        *,
        customer: Customer,
        tx_type: str,
        amount: Decimal,
        outstanding_delta: Decimal,
        advance_delta: Decimal,
        transaction_date: date,
        reference_type: str | None,
        reference_id: UUID | None,
        reference_number: str | None,
        remarks: str | None,
        actor_id: UUID,
        journal_entry_id: UUID | None = None,
    ) -> CustomerReceivableTransaction:
        row = CustomerReceivableTransaction(
            journal_entry_id=journal_entry_id,
            firm_id=customer.firm_id,
            customer_id=customer.id,
            transaction_type=tx_type,
            transaction_date=transaction_date,
            amount=amount,
            outstanding_delta=outstanding_delta,
            advance_delta=advance_delta,
            outstanding_after=customer.current_outstanding,
            advance_after=customer.unapplied_advance_balance,
            reference_type=reference_type,
            reference_id=reference_id,
            reference_number=reference_number,
            remarks=remarks,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def _reset_opening_balance_transaction(
        self,
        *,
        customer: Customer,
        amount: Decimal,
        actor_id: UUID,
    ) -> None:
        # Mirror whatever the old balance posted before dropping the row that
        # points at it. Deleting the transaction alone would leave the journal
        # asserting a figure the customer no longer carries.
        self._reverse_opening_balance_postings(customer, actor_id=actor_id)
        # Deleted through the ORM, one row at a time, and not with a bulk
        # ``query().delete(synchronize_session=False)``. The reversal above
        # sets ``journal_entry_id = None`` on these very rows, so a bulk delete
        # removes them in the database while leaving the dirty objects in the
        # session: the pending UPDATE then fires against a row that is gone and
        # raises StaleDataError, which the handler reports as 409 "this record
        # changed since you loaded it". It only bites where the session does
        # not autoflush -- which is every request, and no unit test.
        for stale in self._session.scalars(
            select(CustomerReceivableTransaction).where(
                CustomerReceivableTransaction.customer_id == customer.id,
                CustomerReceivableTransaction.transaction_type
                == CustomerReceivableTransactionType.OPENING_BALANCE.value,
            )
        ).all():
            self._session.delete(stale)
        self._session.flush()
        self._record_opening_balance_transaction(
            customer=customer,
            amount=amount,
            actor_id=actor_id,
        )

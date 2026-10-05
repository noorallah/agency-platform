"""Transactional application service for customer management."""

from datetime import date
from decimal import Decimal
from typing import ClassVar
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.business.gating import assert_feature_fields
from app.business.schemas import AttributeValueInput, AttributeValueResponse
from app.business.services import AttributeInput, AttributeService
from app.common.audit.services import record_audit
from app.common.firm_metadata import FirmMetadataReader
from app.common.master_code_series import MasterCodeNumbering
from app.common.master_references import (
    MasterReferences,
    assert_master_references,
)
from app.common.open_documents import describe_documents, find_open_documents
from app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    ResourceNotFoundError,
    ValidationError,
)
from app.core.utils.dates import utc_now
from app.core.validation import settle_pan
from app.customers.gst_registration import assert_consistent
from app.customers.models import (
    Customer,
    CustomerAddress,
    CustomerAttributeValue,
    CustomerContact,
    CustomerGroup,
    CustomerOpeningBill,
    CustomerOpeningBillStatus,
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
from app.customers.schemas.customer import CustomerListFilters, CustomerStatus
from app.customers.services.cash_customer import (
    assert_cash_customer_stays,
    assert_not_cash_customer,
)
from app.finance.models import JournalEntry, JournalStatus
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine
from app.pricing.models import PriceLevel
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

#: The masters a customer names by id. Each must be a live row of the
#: customer's own firm (D-MST-3): in the shared store another firm's segment
#: was accepted, and its discount then priced this firm's orders.
_CUSTOMER_REFERENCES: MasterReferences = {
    "customer_group_id": (CustomerGroup, "Customer segment"),
    "price_level_id": (PriceLevel, "Price level"),
}


class CustomerService:
    """Coordinate validated customer mutations, queries, and audits."""

    def __init__(self, session: Session) -> None:
        """Bind the service to one request unit of work."""
        self._session = session
        self._repository = CustomerRepository(session)
        self._posting = DocumentPostingService(session)

    def create(
        self,
        data: CustomerCreate,
        *,
        firm_id: UUID,
        actor_id: UUID,
        may_set_standing_discount: bool = False,
        may_approve: bool = True,
    ) -> Customer:
        """Create a firm-owned customer and all nested records.

        ``may_set_standing_discount`` says the caller holds
        ``CUSTOMER_MANAGE_SETTINGS``; without it the customer starts at no
        standing discount, which is what a form that leaves the box alone
        sends (D-MST-2).
        """
        self._assert_may_set_standing_discount(
            [data], allowed=may_set_standing_discount
        )
        data = self._held_for_approval(data, firm_id=firm_id, may_approve=may_approve)
        try:
            customer = self.stage_create(data, firm_id=firm_id, actor_id=actor_id)
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
        may_set_standing_discount: bool = False,
        may_approve: bool = True,
    ) -> list[Customer]:
        """Create a validated customer batch in one transaction.

        A file is a second way to write the same fields, so it takes the same
        code for a standing discount as the form does, and every row is judged
        before any is staged.
        """
        self._assert_may_set_standing_discount(
            records, allowed=may_set_standing_discount
        )
        records = [
            self._held_for_approval(data, firm_id=firm_id, may_approve=may_approve)
            for data in records
        ]
        try:
            customers = [
                self.stage_create(data, firm_id=firm_id, actor_id=actor_id)
                for data in records
            ]
        except (ConflictError, IntegrityError) as error:
            self._session.rollback()
            if isinstance(error, ConflictError):
                raise
            raise self._unique_conflict() from error
        self._commit_unique()
        return customers

    def stage_create(
        self, data: CustomerCreate, *, firm_id: UUID, actor_id: UUID
    ) -> Customer:
        """Stage one customer and audit event without committing."""
        if data.code is None:
            # A blank code takes the next from the firm's series (MST-5).
            issued = MasterCodeNumbering(self._session, "CUSTOMER").code(
                None, code_column=Customer.code, firm_id=firm_id, actor_id=actor_id
            )
            data = data.model_copy(update={"code": issued})
        # A shelf-life requirement is about expiry dates (backlog 79 row 6).
        assert_feature_fields(
            self._session,
            firm_id,
            feature="EXPIRY_TRACKING",
            values={"minimum_shelf_life_days": data.minimum_shelf_life_days},
        )
        pan = self._settled_pan(
            firm_id,
            pan=data.pan_number,
            gstin=data.gst_number,
            current=None,
        )
        if pan != data.pan_number:
            data = data.model_copy(update={"pan_number": pan})
        self._assert_unique(firm_id, data)
        values = self._customer_values(data)
        values["whatsapp_opt_in_at"] = utc_now() if data.whatsapp_opt_in else None
        assert_master_references(
            self._session, values, _CUSTOMER_REFERENCES, firm_id=firm_id
        )
        self._assert_account_manager(firm_id, data.salesman_id, current=None)
        self._assert_account_manager(
            firm_id, data.collector_id, current=None, role="collector"
        )
        self._assert_linked_vendor(
            firm_id,
            data.linked_vendor_id,
            customer_id=None,
            pan=data.pan_number,
            gstin=data.gst_number,
            name=data.name,
        )
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
        assert_consistent(customer.gst_registration_type, customer.gst_number)
        customer.addresses = [
            self._new_address(address, actor_id) for address in data.addresses
        ]
        customer.contacts = [
            self._new_contact(contact, actor_id) for contact in data.contacts
        ]
        self._repository.add(customer)
        self._repository.flush()
        self._store_attributes(customer, data.attributes, actor_id=actor_id)
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
        may_change_credit_limit: bool = False,
        may_change_standing_discount: bool = False,
        may_approve: bool = True,
    ) -> Customer:
        """Replace customer fields and reconcile addresses and contacts.

        ``may_change_credit_limit`` and ``may_change_standing_discount`` each
        say the caller holds ``CUSTOMER_MANAGE_SETTINGS``. Without it a save
        that moves the limit or the standing discount is refused by name, and
        one that resends the stored figure goes through.
        """
        customer = self.get(customer_id, firm_scope=firm_scope)
        if (
            customer.status == CustomerStatus.PENDING.value
            and "status" in data.model_fields_set
            and data.status != CustomerStatus.PENDING
            and not may_approve
        ):
            raise AuthorizationError(
                f"{customer.code} is waiting for approval. Approving a new outlet "
                "needs the approve customers permission (CUSTOMER_APPROVE)."
            )
        self.stage_update(
            customer,
            data,
            actor_id=actor_id,
            may_change_credit_limit=may_change_credit_limit,
            may_change_standing_discount=may_change_standing_discount,
        )
        self._commit_unique()
        self._session.expire(customer, ["addresses", "contacts"])
        return customer

    def stage_update(
        self,
        customer: Customer,
        data: CustomerUpdate,
        *,
        actor_id: UUID,
        may_change_credit_limit: bool = False,
        may_change_standing_discount: bool = False,
    ) -> Customer:
        """Apply, guard and audit one update without committing it.

        Split out so a file import can update customers by code and commit the
        whole file once (backlog 46), as ``stage_create`` does for a create.
        Flushed at the end, so a later row of the same file that claims this
        customer's new GST or PAN number is refused by the uniqueness check
        rather than by the database at commit.
        """
        self._assert_unique(customer.firm_id, data, excluding_id=customer.id)
        if "minimum_shelf_life_days" in data.model_fields_set:
            assert_feature_fields(
                self._session,
                customer.firm_id,
                feature="EXPIRY_TRACKING",
                values={"minimum_shelf_life_days": data.minimum_shelf_life_days},
            )
        # Partial on update: a field the caller never mentioned keeps what the
        # row holds. Every optional field on the write model has a default, so
        # dumping in full turns an omission into an instruction -- the shape
        # that cost a vendor its addresses and reset an approved order to
        # draft. An explicit null still clears, which is what keeps a complete
        # client able to empty a field.
        values = self._customer_values(data, partial=True)
        assert_cash_customer_stays(customer, values)
        # Checked against what the row will hold, and only where the write
        # moves the PAN or the GSTIN: a PAN stored before the check existed
        # does not block an unrelated edit (backlog 53 item 2).
        sent_pan = values.get("pan_number", customer.pan_number)
        pan = self._settled_pan(
            customer.firm_id,
            pan=sent_pan if isinstance(sent_pan, str) else None,
            gstin=_text(values.get("gst_number", customer.gst_number)),
            current=customer,
        )
        if pan != customer.pan_number or "pan_number" in values:
            values["pan_number"] = pan
        assert_master_references(
            self._session,
            values,
            _CUSTOMER_REFERENCES,
            firm_id=customer.firm_id,
            current=customer,
        )
        if "salesman_id" in values:
            sent = values["salesman_id"]
            self._assert_account_manager(
                customer.firm_id,
                sent if isinstance(sent, UUID) else None,
                current=customer.salesman_id,
            )
        if "collector_id" in values:
            collector = values["collector_id"]
            self._assert_account_manager(
                customer.firm_id,
                collector if isinstance(collector, UUID) else None,
                current=customer.collector_id,
                role="collector",
            )
        if "linked_vendor_id" in values:
            linked = values["linked_vendor_id"]
            if linked != customer.linked_vendor_id:
                self._assert_linked_vendor(
                    customer.firm_id,
                    linked if isinstance(linked, UUID) else None,
                    customer_id=customer.id,
                    pan=_text(values.get("pan_number", customer.pan_number)),
                    gstin=_text(values.get("gst_number", customer.gst_number)),
                    name=str(values.get("name", customer.name)),
                )
        self._assert_may_change_credit_limit(
            customer, values, allowed=may_change_credit_limit
        )
        self._assert_may_change_standing_discount(
            customer, values, allowed=may_change_standing_discount
        )
        # The dump is untyped, so the figure is read back as a Decimal before
        # any of the balance arithmetic below touches it.
        opening_balance = Decimal(
            str(values.get("opening_balance", customer.opening_balance))
        )
        if opening_balance != 0 and customer.opening_balance != opening_balance:
            self._assert_no_opening_bills(customer)
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
        if (
            "whatsapp_opt_in" in values
            and bool(values["whatsapp_opt_in"]) != customer.whatsapp_opt_in
        ):
            # When the customer agreed is the record, so it is the server's
            # clock rather than anything a client sends.
            values["whatsapp_opt_in_at"] = (
                utc_now() if values["whatsapp_opt_in"] else None
            )
        for field, value in values.items():
            setattr(customer, field, value)
        if "gst_registration_type" in values or "gst_number" in values:
            assert_consistent(customer.gst_registration_type, customer.gst_number)
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
        # Same rule as the two collections: replaced whole when sent, left
        # alone when not. A form that does not show the custom fields must
        # not be able to clear them by saving.
        if "attributes" in data.model_fields_set:
            self._store_attributes(customer, data.attributes, actor_id=actor_id)
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
        try:
            self._session.flush()
        except IntegrityError as error:
            self._session.rollback()
            raise self._unique_conflict() from error
        return customer

    def delete(
        self, customer_id: UUID, *, firm_scope: UUID | None, actor_id: UUID
    ) -> None:
        """Soft delete one customer and audit the lifecycle action.

        Only a customer whose account is square can go (D-FIN-1). Deleting
        one who still owed money, or held an advance, left the balance in the
        receivable control account while no live customer carried it, so every
        report of the receivable ledger dropped it -- TEST01 held 1,960.00
        that way. A settled account has nothing in the ledger to take with it,
        which is why nothing is reversed here any more: reversing the opening
        balance of a customer who has since paid it would put the control
        account out by the balance in the other direction.
        """
        customer = self.get(customer_id, firm_scope=firm_scope)
        assert_not_cash_customer(customer)
        self._assert_account_is_square(customer)
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
        """Restore one soft-deleted customer.

        A customer deleted before D-FIN-1 was fixed may have had its opening
        balance journal reversed on the way out while the balance stayed on
        the account. Bringing the account back brings that balance back, so
        the journal is posted again, or the receivable control account would
        be short of what the restored customer is recorded as owing.
        """
        customer = self.get(customer_id, firm_scope=firm_scope, include_deleted=True)
        if not customer.is_deleted:
            return customer
        # A delete released the code, GST and PAN (D-MST-11); a live customer
        # may hold one now, and restoring into the clash is refused by name.
        if (
            self._repository.duplicate_id(
                customer.firm_id, code=customer.code, excluding_id=customer.id
            )
            is not None
        ):
            raise ConflictError(
                f"{customer.code} cannot be restored: a live customer now holds "
                "its code."
            )
        self._repost_reversed_opening_balance(customer, actor_id=actor_id)
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

        if tx_type in {
            CustomerReceivableTransactionType.OPENING_BALANCE,
            CustomerReceivableTransactionType.OPENING_BILL,
        }:
            raise ValidationError("Opening balance transactions are system-managed.")
        if tx_type == CustomerReceivableTransactionType.REVERSAL:
            raise ValidationError(
                "A reversal is posted against the transaction it undoes, "
                "not on its own."
            )
        if tx_type in {
            CustomerReceivableTransactionType.INVOICE,
            # A debit note is more of a bill already raised.
            CustomerReceivableTransactionType.DEBIT_NOTE,
            # Tax collected at source is owed on top of what was just paid,
            # so it increases the balance exactly as a bill does.
            CustomerReceivableTransactionType.TCS,
            # So is what the firm charged for the customer's bounced cheque.
            CustomerReceivableTransactionType.CHEQUE_RETURN_CHARGE,
        }:
            outstanding_delta = amount
        elif tx_type in {
            CustomerReceivableTransactionType.RECEIPT,
            CustomerReceivableTransactionType.CREDIT_NOTE,
            # Loyalty credit settles a bill exactly as a receipt does: the
            # firm has been paid, in credit it already owed rather than in
            # cash. Without this the journal reduced the receivable control
            # account while the customer's own balance stayed where it was,
            # and the two books drifted by every redemption -- which
            # `verify_sample_data.py` caught within minutes of the seed
            # running.
            CustomerReceivableTransactionType.LOYALTY,
        }:
            applied = amount if amount <= current else current
            excess = amount - applied
            outstanding_delta = -applied
            advance_delta = excess
        elif tx_type in {
            # A write-off or set-off clears a balance the customer owes and
            # never makes an advance: the party adjustment service refuses
            # one larger than the balance, and this refuses it again rather
            # than turning given-up debt into money held for the customer.
            CustomerReceivableTransactionType.WRITE_OFF,
            CustomerReceivableTransactionType.SET_OFF,
        }:
            if amount > current:
                raise ValidationError(
                    f"The customer owes {current}, so {amount} cannot be "
                    "written off or set off."
                )
            outstanding_delta = -amount
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

    def _store_attributes(
        self,
        customer: Customer,
        attributes: list[AttributeValueInput],
        *,
        actor_id: UUID,
    ) -> None:
        """Validate and persist the customer's custom fields."""
        AttributeService(self._session).replace_values(
            CustomerAttributeValue,
            customer.id,
            [
                AttributeInput(
                    attribute_definition_id=item.attribute_definition_id,
                    value=item.value,
                )
                for item in attributes
            ],
            firm_id=customer.firm_id,
            actor_id=actor_id,
        )

    def attribute_responses(self, customer: Customer) -> list[AttributeValueResponse]:
        """Return one customer's stored custom fields in response shape."""
        return [
            AttributeValueResponse.model_validate(row)
            for row in AttributeService(self._session).value_rows(
                CustomerAttributeValue, customer.id
            )
        ]

    def attribute_responses_for_many(
        self, customers: list[Customer]
    ) -> dict[UUID, list[AttributeValueResponse]]:
        """Return a page of customers' custom fields in one query (D-CFG-20)."""
        grouped = AttributeService(self._session).value_rows_for_many(
            CustomerAttributeValue, [row.id for row in customers]
        )
        return {
            owner: [AttributeValueResponse.model_validate(row) for row in rows]
            for owner, rows in grouped.items()
        }

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
                # A create's blank code is issued before this is asked.
                firm_id,
                code=data.code or "",
                excluding_id=excluding_id,
            )
            is not None
        ):
            raise ConflictError(
                f"Customer code {data.code} already exists in this firm."
            )

    def identity_holders(
        self,
        firm_id: UUID,
        *,
        gst_number: str | None,
        pan_number: str | None,
        excluding_id: UUID | None = None,
    ) -> list[Customer]:
        """Return the live customers already holding this GSTIN or PAN (A7)."""
        return self._repository.identity_holders(
            firm_id,
            gst_number=gst_number,
            pan_number=pan_number,
            excluding_id=excluding_id,
        )

    def identity_warning(
        self,
        firm_id: UUID,
        *,
        gst_number: str | None,
        pan_number: str | None,
        excluding_id: UUID | None = None,
    ) -> str | None:
        """Say which other customers hold this GSTIN or PAN, or None (A7).

        One company is often several accounts -- a branch per state shares
        its PAN, a head office and its outlets may share a GSTIN -- so a
        repeat is allowed, as Tally and Zoho allow it, and named so a
        duplicate typed by mistake is caught by whoever saves it.
        """
        holders = self._repository.identity_holders(
            firm_id,
            gst_number=gst_number,
            pan_number=pan_number,
            excluding_id=excluding_id,
        )
        if not holders:
            return None
        parts: list[str] = []
        for label, value, field in (
            ("GSTIN", gst_number, "gst_number"),
            ("PAN", pan_number, "pan_number"),
        ):
            named = [
                f"{row.code} {row.name}".strip()
                for row in holders
                if value and getattr(row, field) == value
            ]
            if named:
                parts.append(f"{label} {value} is also on {', '.join(named[:5])}")
        return "; ".join(parts) + "." if parts else None

    def _assert_account_manager(
        self,
        firm_id: UUID,
        salesman_id: UUID | None,
        *,
        current: UUID | None,
        role: str = "account manager",
    ) -> None:
        """Refuse an account manager who is not an active member of the firm.

        The customer's collector (SG-8) is checked the same way, under its
        own name in the message.

        Asked only when the write *moves* it: a manager who has since left
        stays on the record (and is skipped when documents are raised, see
        `resolve_sales_scope`), so a full-form save that resends them does
        not block an unrelated edit. Through `FirmMetadataReader`, because
        `users` and `user_firms` live only in the platform store.
        """
        if salesman_id is None or salesman_id == current:
            return
        if (
            FirmMetadataReader(self._session).active_member_count(
                firm_id, [salesman_id]
            )
            != 1
        ):
            raise ValidationError(f"The {role} must be an active member of this firm.")

    def _settled_pan(
        self,
        firm_id: UUID,
        *,
        pan: str | None,
        gstin: str | None,
        current: Customer | None,
    ) -> str | None:
        """Check the PAN against the GSTIN; return the PAN to store.

        A PAN filled from the GSTIN is always kept now that a PAN may repeat
        across one company's branches (decision A7); until then it was left
        blank when another customer held it.
        """
        return settle_pan(
            pan=pan,
            gstin=gstin,
            stored_pan=current.pan_number if current is not None else None,
            stored_gstin=current.gst_number if current is not None else None,
            creating=current is None,
            pan_field="pan_number",
            gstin_field="gst_number",
        )

    def _commit_unique(self) -> None:
        try:
            self._session.commit()
        except IntegrityError as error:
            self._session.rollback()
            raise self._unique_conflict() from error

    @staticmethod
    def _unique_conflict() -> ConflictError:
        return ConflictError("Customer code already exists in this firm.")

    @staticmethod
    def _assert_may_change_credit_limit(
        customer: Customer, values: dict[str, object], *, allowed: bool
    ) -> None:
        """Refuse a credit-limit change from somebody the limit constrains.

        The credit policy -- `CUSTOMER_MANAGE_SETTINGS` -- is withheld from
        `SALES_MANAGER` so the role the block limits cannot switch it off. The
        limit is the other half of that control: raising it, or setting it to
        zero ("no limit"), lifts a BLOCK for that customer just as surely, so
        it takes the same code. A form resending the stored figure is not a
        change and is not refused (D-CFG-17).
        """
        if allowed or "credit_limit" not in values:
            return
        sent = Decimal(str(values["credit_limit"]))
        if sent != customer.credit_limit:
            raise AuthorizationError(
                "Changing a customer's credit limit needs the manage customer "
                "settings permission (CUSTOMER_MANAGE_SETTINGS)."
            )

    @staticmethod
    def _assert_may_change_standing_discount(
        customer: Customer, values: dict[str, object], *, allowed: bool
    ) -> None:
        """Refuse a standing-discount change from somebody who sells on it.

        The rate is the customer tier of the shared discount rule -- above the
        price list and the segment -- and a segment's rate already takes
        `CUSTOMER_MANAGE_SETTINGS`. The customer's own rate rode on
        `CUSTOMER_UPDATE`, so the sales manager refused the credit limit
        (D-CFG-17) could set 100% instead and bill an order at nothing
        (D-MST-2). Whoever sells at a price must not be the one who sets it:
        moving the rate, down as well as up, takes the settings code. A form
        resending the stored figure is not a change and is not refused.
        """
        if allowed or "default_discount_percent" not in values:
            return
        sent = Decimal(str(values["default_discount_percent"]))
        if sent != customer.default_discount_percent:
            raise AuthorizationError(
                "Changing a customer's standing discount needs the manage "
                "customer settings permission (CUSTOMER_MANAGE_SETTINGS)."
            )

    @staticmethod
    def _assert_may_set_standing_discount(
        records: list[CustomerCreate], *, allowed: bool
    ) -> None:
        """Refuse a new customer that starts with a standing discount.

        Creating a customer at 100% off is the same act as editing one to it,
        so the form and the import both answer to the same code. Zero -- the
        default, and what a form that leaves the box alone sends -- is not a
        discount and is never refused.
        """
        if allowed:
            return
        for data in records:
            if data.default_discount_percent != 0:
                raise AuthorizationError(
                    f"{data.code}: giving a customer a standing discount needs "
                    "the manage customer settings permission "
                    "(CUSTOMER_MANAGE_SETTINGS). Leave it at zero, or ask "
                    "somebody who holds it."
                )

    def _assert_linked_vendor(
        self,
        firm_id: UUID,
        vendor_id: UUID | None,
        *,
        customer_id: UUID | None,
        pan: str | None,
        gstin: str | None,
        name: str,
    ) -> None:
        """Refuse a supplier link that is not one business with this customer.

        The supplier must be the firm's and live, not linked to another
        customer, and -- where both carry a PAN, recorded or read off the
        GSTIN -- carry the same one (ACC-11, the set-off's own test).
        """
        if vendor_id is None:
            return
        from app.party_adjustments.services.party_adjustment_service import _pan_of
        from app.vendors.models import Vendor

        vendor = self._session.get(Vendor, vendor_id)
        if vendor is None or vendor.firm_id != firm_id or vendor.is_deleted:
            raise ValidationError("The linked supplier is not one of the firm's.")
        taken = self._session.scalar(
            select(Customer.name).where(
                Customer.firm_id == firm_id,
                Customer.linked_vendor_id == vendor_id,
                Customer.is_deleted.is_(False),
                *(() if customer_id is None else (Customer.id != customer_id,)),
            )
        )
        if taken is not None:
            raise ValidationError(
                f"{vendor.name} is already linked to the customer {taken}."
            )
        ours = _pan_of(pan, gstin)
        theirs = _pan_of(vendor.pan, vendor.gstin)
        if ours and theirs and ours != theirs:
            raise ValidationError(
                f"{name} (PAN {ours}) and {vendor.name} (PAN {theirs}) are "
                "different businesses, so they cannot be linked."
            )

    def _held_for_approval(
        self, data: CustomerCreate, *, firm_id: UUID, may_approve: bool
    ) -> CustomerCreate:
        """Start a new outlet PENDING where the firm wants it approved (SEL-15).

        Only for a creator who cannot approve it themselves: the office adding
        a customer is the approval.
        """
        if may_approve or data.status == CustomerStatus.PENDING:
            return data
        from app.sales_order.services.workflow_settings_service import (
            SalesWorkflowService,
        )

        policy = SalesWorkflowService(self._session).settings_response(firm_id)
        if not policy.new_outlets_need_approval:
            return data
        return data.model_copy(update={"status": CustomerStatus.PENDING})

    def approve(self, customer_id: UUID, *, firm_id: UUID, actor_id: UUID) -> Customer:
        """Approve a new outlet so it can be billed (SEL-15); the caller commits.

        Raises:
            ValidationError: If the customer is not waiting for approval.

        """
        customer = self.get(customer_id, firm_scope=firm_id)
        if customer.status != CustomerStatus.PENDING.value:
            raise ValidationError(
                f"{customer.code} is not waiting for approval ({customer.status})."
            )
        customer.status = CustomerStatus.ACTIVE.value
        customer.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="customer.approved",
            entity_type="customer",
            entity_id=customer.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={"status": CustomerStatus.PENDING.value},
            after_data={"status": customer.status},
        )
        return customer

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
            exclude={"addresses", "contacts", "attributes"},
            mode="python",
            exclude_unset=partial,
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
            # Consent is a record somebody may be asked for (backlog 51).
            "no_reminders": customer.no_reminders,
            "preferred_channel": customer.preferred_channel,
            "whatsapp_opt_in": customer.whatsapp_opt_in,
            # Decides which batch trade rate the customer is sold at (PG-14).
            "trade_class": customer.trade_class,
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

    def _assert_no_opening_bills(self, customer: Customer) -> None:
        """Refuse a single-figure opening balance beside bill-wise ones.

        A customer's day-one position is entered one way or the other -- one
        figure on the master, or bill by bill (`CustomerOpeningBill`) -- the
        convention Tally calls a bill-wise breakup. Both at once would count
        the same debt twice, in the balance and in the ledger.
        """
        live = self._session.scalar(
            select(func.count(CustomerOpeningBill.id)).where(
                CustomerOpeningBill.customer_id == customer.id,
                CustomerOpeningBill.status == CustomerOpeningBillStatus.POSTED.value,
                CustomerOpeningBill.is_deleted.is_(False),
            )
        )
        if live:
            raise ValidationError(
                f"{customer.code} has {live} opening bill"
                f"{'' if live == 1 else 's'}. Enter the opening balance either "
                "as one figure on the customer or bill by bill, not both -- "
                "cancel the opening bills first, or leave the opening balance "
                "at 0."
            )

    def _assert_account_is_square(self, customer: Customer) -> None:
        """Refuse to delete a customer whose account is not settled (D-FIN-1).

        The rule every ledger package keeps -- Tally will not delete a ledger
        with a balance, Odoo and Zoho refuse a contact with open documents:
        what a customer owes, any advance they hold, and any invoice still
        open or still in draft all have to be dealt with first. A customer the
        firm has stopped trading with is marked inactive instead.
        """
        # Imported here: the settlement module imports this service.
        from app.sales_invoice.models import SalesInvoice
        from app.settlements.services import ReceiptService

        reasons: list[str] = []
        if customer.current_outstanding != 0:
            reasons.append(f"owes {customer.current_outstanding:,.2f}")
        if customer.unapplied_advance_balance != 0:
            reasons.append(
                f"holds an advance of {customer.unapplied_advance_balance:,.2f}"
            )
        open_numbers = [
            record.invoice_number
            for record in ReceiptService(self._session).outstanding_invoices(
                firm_id=customer.firm_id, party_id=customer.id
            )
        ]
        open_numbers += list(
            self._session.scalars(
                select(SalesInvoice.invoice_number)
                .where(
                    SalesInvoice.firm_id == customer.firm_id,
                    SalesInvoice.customer_id == customer.id,
                    SalesInvoice.is_deleted.is_(False),
                    SalesInvoice.status == "DRAFT",
                )
                .order_by(SalesInvoice.created_at.asc())
            ).all()
        )
        if open_numbers:
            shown = ", ".join(open_numbers[:5])
            more = len(open_numbers) - 5
            reasons.append(
                f"has {len(open_numbers)} open invoice"
                f"{'' if len(open_numbers) == 1 else 's'} ({shown}"
                f"{f' and {more} more' if more > 0 else ''})"
            )
        # The documents still in flight (D-MST-4). The guard stopped at
        # invoices, so a customer went under an approved order holding a
        # reservation, or with goods shipped and not billed -- and the note or
        # the bill that order needs was then refused, because every sales
        # service loads the customer with ``is_deleted`` false. A draft
        # invoice is already named above.
        in_flight = [
            group
            for group in find_open_documents(
                self._session, customer.firm_id, customer_id=customer.id
            )
            if group.label != "draft sales invoice"
        ]
        if in_flight:
            reasons.append(f"is on {describe_documents(in_flight)}")
        if reasons:
            raise ValidationError(
                f"{customer.code} cannot be deleted: it {', '.join(reasons)}. "
                "Settle, refund or cancel what is open first, or set the "
                "customer inactive to stop trading with them."
            )

    def _repost_reversed_opening_balance(
        self, customer: Customer, *, actor_id: UUID
    ) -> None:
        """Post again an opening balance a pre-D-FIN-1 delete reversed.

        Such a delete mirrored the opening-balance journal and cleared the
        link on the receivable row, but left the balance on the account. Only
        that shape is reposted: an opening-balance row with no journal while a
        REVERSED original from this customer's master still stands. A row that
        never posted (a nil balance) has no reversed original to find.
        """
        rows = [
            row
            for row in self._session.scalars(
                select(CustomerReceivableTransaction).where(
                    CustomerReceivableTransaction.customer_id == customer.id,
                    CustomerReceivableTransaction.transaction_type
                    == CustomerReceivableTransactionType.OPENING_BALANCE.value,
                    CustomerReceivableTransaction.journal_entry_id.is_(None),
                    CustomerReceivableTransaction.is_deleted.is_(False),
                )
            ).all()
            if row.outstanding_delta != 0 or row.advance_delta != 0
        ]
        if not rows:
            return
        reversed_original = self._session.scalar(
            select(JournalEntry.id)
            .where(
                JournalEntry.firm_id == customer.firm_id,
                JournalEntry.source_module == "customers",
                JournalEntry.source_id == customer.id,
                JournalEntry.reversal_of_id.is_(None),
                JournalEntry.status == JournalStatus.REVERSED.value,
            )
            .limit(1)
        )
        if reversed_original is None:
            return
        for row in rows:
            entry = self._posting.post_opening_balance(
                firm_id=customer.firm_id,
                customer_id=customer.id,
                reference_number=self._opening_balance_reference(customer),
                posting_date=utc_now().date(),
                amount=row.outstanding_delta - row.advance_delta,
                actor_id=actor_id,
            )
            row.journal_entry_id = None if entry is None else entry.id

    def _reverse_opening_balance_postings(
        self, customer: Customer, *, actor_id: UUID
    ) -> None:
        """Mirror every journal this customer's opening balances have posted.

        Used when an opening balance stops being true because it is revised.
        Deleting the customer no longer calls it: only a settled account can
        be deleted, and its journals already net to nothing. Each reversal
        takes the original entry's reference with `-REV`, so the pair reads as
        one correction.
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

    def record_opening_bill(
        self,
        customer: Customer,
        *,
        amount: Decimal,
        posting_date: date,
        bill_id: UUID,
        bill_number: str,
        label: str,
        journal_entry_id: UUID,
        actor_id: UUID,
    ) -> CustomerReceivableTransaction:
        """Raise the customer's balance by one opening bill, without committing.

        The same shape as an invoice: it adds to what the customer owes and
        leaves any advance alone, since applying an advance to a bill is a
        decision somebody takes on Record Receipt, not a side effect. Written
        as `OPENING_BILL` on the posting date and linked to the bill's journal,
        so the statement shows it the day the books start.
        """
        customer.current_outstanding = customer.current_outstanding + amount
        customer.updated_by = actor_id
        return self._record_receivable_transaction(
            customer=customer,
            tx_type=CustomerReceivableTransactionType.OPENING_BILL.value,
            amount=amount,
            outstanding_delta=amount,
            advance_delta=Decimal("0"),
            transaction_date=posting_date,
            reference_type="customer_opening_bill",
            reference_id=bill_id,
            reference_number=bill_number,
            remarks=f"Opening bill {label}.",
            actor_id=actor_id,
            journal_entry_id=journal_entry_id,
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
        on: date | None = None,
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
            on: The day the reversal carries -- the caller's mirror journal
                date, which is what the statement must agree with (D-FIN-17).

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
            transaction_date=on or self._reversal_date(original),
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

    def _reversal_date(self, original: CustomerReceivableTransaction) -> date:
        """Return the day a reversal row carries: the day of its journal.

        It carried the original's date (D-FIN-17), so a statement already sent
        for a month changed when something in it was cancelled later, and
        never agreed with 1100 at that month end. The mirror journal is dated
        the day it happened; the row takes that date when the original's
        journal has been reversed, and otherwise the same rule the journal
        engine applies -- today, never before the original.
        """
        if original.journal_entry_id is not None:
            mirrored = self._session.scalar(
                select(JournalEntry.journal_date)
                .where(
                    JournalEntry.reversal_of_id == original.journal_entry_id,
                    JournalEntry.is_deleted.is_(False),
                )
                .order_by(JournalEntry.created_at.desc(), JournalEntry.id.desc())
                .limit(1)
            )
            if mirrored is not None:
                return mirrored
        return max(utc_now().date(), original.transaction_date)

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


def _text(value: object) -> str | None:
    """Read an optional text value out of an untyped dump."""
    return value if isinstance(value, str) else None

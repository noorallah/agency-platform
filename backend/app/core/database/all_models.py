"""Import every model module, so ``Base.metadata`` describes the whole schema.

Three places need the complete schema and each kept its own copy of this list:
``alembic/env.py`` (or a migration autogenerates against half a schema),
``tests/conftest.py`` (or ``create_all`` builds half a database and a test file
passes alone but not in a suite), and ``scripts/generate_sample_data.py`` (or
``--reset`` misses tables and dies on a foreign key). ``CLAUDE.md`` carried a
standing instruction to keep two of them in step by hand, which is the shape of
a rule that gets forgotten -- and it was: the seed script's own delete list had
gone stale by 61 tables.

One list. Importing this module is what makes the metadata complete; nothing
here is meant to be referenced by name.

A new model module belongs here and nowhere else. ``test_schema_registry.py``
fails the build if a module under ``app/*/models/`` is missing.
"""

from app.approvals import models as _approvals  # noqa: F401
from app.bank_reconciliation.models import bank_statement  # noqa: F401
from app.batch_serial.models import batch_serial  # noqa: F401
from app.bill_of_entry.models import bill_of_entry  # noqa: F401
from app.branches.models import (
    branch_warehouse,  # noqa: F401
    user_work_default,  # noqa: F401
)
from app.branding.models import agency_branding  # noqa: F401
from app.business.models import (
    document_attributes,  # noqa: F401
    framework,  # noqa: F401
)
from app.commission.models import commission  # noqa: F401
from app.commission.models import payout as _commission_payout  # noqa: F401
from app.common.audit.models import audit_log  # noqa: F401
from app.contra.models import contra_voucher  # noqa: F401
from app.credit_note.models import credit_note as _credit_note  # noqa: F401
from app.customer_debit_note.models import (  # noqa: F401
    customer_debit_note as _customer_debit_note,
)
from app.customers.models import customer, customer_records  # noqa: F401
from app.customers.models import opening_bill as _customer_opening_bill  # noqa: F401
from app.debit_note.models import debit_note as _debit_note  # noqa: F401
from app.delivery_note.models import delivery_note  # noqa: F401
from app.diagnostics.models import error_report  # noqa: F401
from app.document_files.models import document_file  # noqa: F401
from app.document_framework.models import document_framework  # noqa: F401
from app.einvoice.models import einvoice as _einvoice  # noqa: F401
from app.enquiry import models as _enquiry  # noqa: F401
from app.expenses.models import expense  # noqa: F401
from app.finance.models import (  # noqa: F401
    bank_details,
    finance,
    ledger_attachment,
    tally,
    tds_194q,
    tds_challan,
    tds_sections,
)
from app.firms.models import firm  # noqa: F401
from app.fixed_assets.models import fixed_asset  # noqa: F401
from app.goods_receipt.models import goods_receipt  # noqa: F401
from app.gst_returns.models import (
    gst_cash_deposit,  # noqa: F401
    gst_payment,  # noqa: F401
    gst_return_filing,  # noqa: F401
    gstr2b,  # noqa: F401
    itc_common_reversal,  # noqa: F401
    itc_reversal,  # noqa: F401
)
from app.identity.models import identity  # noqa: F401
from app.imports.models import import_mapping  # noqa: F401
from app.inventory.models import (
    adjustment_approval,  # noqa: F401
    adjustment_reason,  # noqa: F401
    inventory,  # noqa: F401
    physical_count,  # noqa: F401
    repack,  # noqa: F401
    stock_attachment,  # noqa: F401
    stock_transfer,  # noqa: F401
)
from app.landed_costs import models as _landed_costs  # noqa: F401
from app.loyalty.models import loyalty  # noqa: F401
from app.messaging.models import messaging as _messaging  # noqa: F401
from app.notifications.models import notification_read  # noqa: F401
from app.party_adjustments.models import party_adjustment  # noqa: F401
from app.pricing.models import price_level, price_list  # noqa: F401
from app.principal_claims.models import claim as _principal_claim  # noqa: F401
from app.products.models import brand, kit, price_revision, product  # noqa: F401
from app.proforma.models import proforma  # noqa: F401
from app.promotions.models import promotion  # noqa: F401
from app.purchase.models import purchase, requisition  # noqa: F401
from app.purchase_invoice.models import purchase_invoice  # noqa: F401
from app.purchase_return.models import purchase_return  # noqa: F401
from app.quotation.models import quotation  # noqa: F401
from app.rate_contracts.models import rate_contract  # noqa: F401
from app.report_layouts.models import report_layout  # noqa: F401
from app.rfq.models import rfq  # noqa: F401
from app.sales.models import territory  # noqa: F401
from app.sales_invoice.models import sales_invoice  # noqa: F401
from app.sales_order.models import sales_order  # noqa: F401
from app.sales_return.models import sales_return  # noqa: F401
from app.sales_targets.models import sales_target  # noqa: F401
from app.settlements.models import (  # noqa: F401
    cheque_layout,
    payment_run,
    post_dated_cheque,
    settlement,
)
from app.supplier_rebates.models import rebate  # noqa: F401
from app.supplier_schemes.models import supplier_scheme  # noqa: F401
from app.tax.models import tax_framework  # noqa: F401
from app.tcs.models import tcs  # noqa: F401
from app.trade_licences.models import trade_licence  # noqa: F401
from app.uom.models import uom  # noqa: F401
from app.vendors.models import (  # noqa: F401
    opening_bill,
    supplier_gift,
    supplier_product,
    vendor,
    vendor_rating,
)

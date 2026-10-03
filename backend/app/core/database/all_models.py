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

from app.batch_serial.models import batch_serial  # noqa: F401
from app.branches.models import (
    branch_warehouse,  # noqa: F401
    user_work_default,  # noqa: F401
)
from app.business.models import framework  # noqa: F401
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
from app.document_framework.models import document_framework  # noqa: F401
from app.einvoice.models import einvoice as _einvoice  # noqa: F401
from app.expenses.models import expense  # noqa: F401
from app.finance.models import finance, tds_194q, tds_challan  # noqa: F401
from app.firms.models import firm  # noqa: F401
from app.goods_receipt.models import goods_receipt  # noqa: F401
from app.gst_returns.models import (
    gst_payment,  # noqa: F401
    gst_return_filing,  # noqa: F401
    gstr2b,  # noqa: F401
    itc_reversal,  # noqa: F401
)
from app.identity.models import identity  # noqa: F401
from app.imports.models import import_mapping  # noqa: F401
from app.inventory.models import (
    inventory,  # noqa: F401
    physical_count,  # noqa: F401
    stock_attachment,  # noqa: F401
)
from app.loyalty.models import loyalty  # noqa: F401
from app.messaging.models import messaging as _messaging  # noqa: F401
from app.party_adjustments.models import party_adjustment  # noqa: F401
from app.pricing.models import price_list  # noqa: F401
from app.products.models import product  # noqa: F401
from app.proforma.models import proforma  # noqa: F401
from app.promotions.models import promotion  # noqa: F401
from app.purchase.models import purchase  # noqa: F401
from app.purchase_invoice.models import purchase_invoice  # noqa: F401
from app.purchase_return.models import purchase_return  # noqa: F401
from app.quotation.models import quotation  # noqa: F401
from app.sales.models import territory  # noqa: F401
from app.sales_invoice.models import sales_invoice  # noqa: F401
from app.sales_order.models import sales_order  # noqa: F401
from app.sales_return.models import sales_return  # noqa: F401
from app.sales_targets.models import sales_target  # noqa: F401
from app.settlements.models import (  # noqa: F401
    cheque_layout,
    post_dated_cheque,
    settlement,
)
from app.tax.models import tax_framework  # noqa: F401
from app.tcs.models import tcs  # noqa: F401
from app.trade_licences.models import trade_licence  # noqa: F401
from app.uom.models import uom  # noqa: F401
from app.vendors.models import opening_bill, vendor, vendor_rating  # noqa: F401

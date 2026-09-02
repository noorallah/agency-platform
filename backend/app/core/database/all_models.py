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
from app.branches.models import branch_warehouse  # noqa: F401
from app.business.models import framework  # noqa: F401
from app.commission.models import commission  # noqa: F401
from app.commission.models import payout as _commission_payout  # noqa: F401
from app.common.audit.models import audit_log  # noqa: F401
from app.customers.models import customer  # noqa: F401
from app.delivery_note.models import delivery_note  # noqa: F401
from app.diagnostics.models import error_report  # noqa: F401
from app.document_framework.models import document_framework  # noqa: F401
from app.finance.models import finance  # noqa: F401
from app.firms.models import firm  # noqa: F401
from app.goods_receipt.models import goods_receipt  # noqa: F401
from app.identity.models import identity  # noqa: F401
from app.inventory.models import (
    inventory,  # noqa: F401
    physical_count,  # noqa: F401
)
from app.pricing.models import price_list  # noqa: F401
from app.products.models import product  # noqa: F401
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
from app.settlements.models import settlement  # noqa: F401
from app.tax.models import tax_framework  # noqa: F401
from app.uom.models import uom  # noqa: F401
from app.vendors.models import vendor  # noqa: F401

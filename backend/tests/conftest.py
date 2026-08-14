"""Shared pytest configuration for the backend test suite.

Unit tests build their own SQLite engines and call ``Base.metadata.create_all``.
That only emits the tables whose model modules have already been imported, so a
test file that touches one module used to fail when run on its own while
passing inside the full suite, purely because a sibling test had imported the
missing models first.

Importing every model module here removes that ordering dependency: by the time
any test runs, ``Base.metadata`` describes the whole schema. This list must stay
in step with the equivalent imports in ``alembic/env.py``.
"""

from app.batch_serial.models import batch_serial  # noqa: F401
from app.branches.models import branch_warehouse  # noqa: F401
from app.business.models import framework  # noqa: F401
from app.common.audit.models import audit_log  # noqa: F401
from app.customers.models import customer  # noqa: F401
from app.delivery_note.models import delivery_note  # noqa: F401
from app.diagnostics.models import error_report  # noqa: F401
from app.document_framework.models import document_framework  # noqa: F401
from app.finance.models import finance  # noqa: F401
from app.firms.models import firm  # noqa: F401
from app.goods_receipt.models import goods_receipt  # noqa: F401
from app.identity.models import identity  # noqa: F401
from app.inventory.models import inventory  # noqa: F401
from app.products.models import product  # noqa: F401
from app.purchase.models import purchase  # noqa: F401
from app.purchase_invoice.models import purchase_invoice  # noqa: F401
from app.purchase_return.models import purchase_return  # noqa: F401
from app.sales.models import territory  # noqa: F401
from app.sales_invoice.models import sales_invoice  # noqa: F401
from app.sales_order.models import sales_order  # noqa: F401
from app.settlements.models import settlement  # noqa: F401
from app.tax.models import tax_framework  # noqa: F401
from app.uom.models import uom  # noqa: F401
from app.vendors.models import vendor  # noqa: F401

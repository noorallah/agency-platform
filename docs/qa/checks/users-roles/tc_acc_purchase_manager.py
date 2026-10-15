"""Rule 3 (the server agrees) for the purchase-manager job template: writes the job holds are allowed, writes it lacks are 403."""
from _ur import job_check

job_check("tc_acc_purchase_manager", "purchase-manager", ["vendors", "purchases", "rfqs"], ["customers", "receipts", "journal-entries", "inventory-adjustments", "roles"])

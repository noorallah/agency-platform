"""Rule 3 (the server agrees) for the warehouse job template: writes the job holds are allowed, writes it lacks are 403."""
from _ur import job_check

job_check("tc_acc_warehouse", "warehouse", ["inventory-adjustments", "delivery-notes"], ["customers", "receipts", "vendors", "journal-entries", "sales-orders", "roles"])

"""Rule 3 (the server agrees) for the purchasing job template: writes the job holds are allowed, writes it lacks are 403."""
from _ur import job_check

job_check("tc_acc_purchasing", "purchasing", ["purchases", "rfqs"], ["vendors", "customers", "receipts", "journal-entries", "inventory-adjustments", "roles"])

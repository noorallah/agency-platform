"""Rule 3 (the server agrees) for the read-only job template: writes the job holds are allowed, writes it lacks are 403."""
from _ur import job_check

job_check("tc_acc_read_only", "read-only", [], ["customers", "vendors", "receipts", "payments", "quotations", "journal-entries", "inventory-adjustments", "roles"])

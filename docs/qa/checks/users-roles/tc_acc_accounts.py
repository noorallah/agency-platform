"""Rule 3 (the server agrees) for the accounts job template: writes the job holds are allowed, writes it lacks are 403."""
from _ur import job_check

job_check("tc_acc_accounts", "accounts", ["receipts", "payments", "expenses", "journal-entries"], ["customers", "vendors", "quotations", "inventory-adjustments", "roles"])

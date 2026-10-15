"""Rule 3 (the server agrees) for the counter-sales job template: writes the job holds are allowed, writes it lacks are 403."""
from _ur import job_check

job_check("tc_acc_counter_sales", "counter-sales", ["receipts", "payments", "sales-invoices"], ["customers", "vendors", "quotations", "journal-entries", "inventory-adjustments", "roles"])

"""Rule 3 (the server agrees) for the field-sales job template: writes the job holds are allowed, writes it lacks are 403."""
from _ur import job_check

job_check("tc_acc_field_sales", "field-sales", ["customers", "quotations", "sales-orders", "sales-invoices"], ["receipts", "payments", "vendors", "journal-entries", "inventory-adjustments", "roles"])

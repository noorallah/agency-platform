"""Rule 3 (the server agrees) for the customer-support job template: writes the job holds are allowed, writes it lacks are 403."""
from _ur import job_check

job_check("tc_acc_customer_support", "customer-support", ["customer-update"], ["customers", "receipts", "quotations", "journal-entries", "roles"])

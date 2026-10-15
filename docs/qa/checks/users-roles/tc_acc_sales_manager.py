"""Rule 3 (the server agrees) for the sales-manager job template: writes the job holds are allowed, writes it lacks are 403."""
from _ur import job_check

job_check("tc_acc_sales_manager", "sales-manager", ["customers", "credit-notes", "delivery-notes", "sales-orders", "customer-update"], ["vendors", "payments", "journal-entries", "inventory-adjustments", "purchases", "roles"])

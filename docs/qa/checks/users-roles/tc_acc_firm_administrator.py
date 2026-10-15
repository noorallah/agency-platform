"""Rule 3 (the server agrees) for the firm-administrator job template: writes the job holds are allowed, writes it lacks are 403."""
from _ur import job_check

job_check("tc_acc_firm_administrator", "firm-administrator", ["customers", "vendors", "receipts", "payments", "journal-entries", "inventory-adjustments", "roles"], [], platform_part=True)

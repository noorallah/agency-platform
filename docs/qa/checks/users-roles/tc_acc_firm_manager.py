"""Rule 3 (the server agrees) for the firm-manager job template: writes the job holds are allowed, writes it lacks are 403."""
from _ur import job_check

job_check("tc_acc_firm_manager", "firm-manager", ["customers", "vendors", "receipts", "journal-entries", "inventory-adjustments"], ["roles"])

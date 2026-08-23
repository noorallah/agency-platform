"""Salesman commission: what a sale earned the person who made it.

Commission is computed on **money actually collected**, not on invoiced value.
A firm that pays on invoices pays for sales it may never be paid for, and every
bad debt then has to be clawed back from a person who has already been paid --
so the trigger is the receipt clearing the invoice, and an invoice nobody pays
earns nobody anything.

Who earned it is the **invoice's own** `salesman_id`, the tag the document
carried when the sale happened, not the customer's territory assignment today.
Reading it off the assignment would move March's commission to whoever holds
the round in August, which is the same reason a sales invoice inherits its
price from the line it bills rather than re-reading the customer master.

v1 reports. Nothing here posts a payout to the ledger: that needs a per-firm
expense and payable mapping, and a decision about when the liability is
recognised, neither of which has been made.
"""

"""Debit notes to a customer: more charged on a sale already invoiced.

A price revised upward after billing, a line under-billed, a charge added
later -- each raises what the customer owes **and the output tax the firm owes
on that supply** (CGST Act s.34(3)). The mirror of `app/credit_note`: it names
the invoice it corrects, moves no stock, and is taxed at the rate that
invoice's line was charged. `app/debit_note` is the other direction, a debit
note the firm raises on a supplier.
"""

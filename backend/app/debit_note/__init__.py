"""Debit notes: a claim on a supplier without goods going back.

A price billed above what was agreed, or goods billed that never arrived --
both reduce what the firm owes the supplier **and the input tax it may claim
on that bill**. `app/purchase_return` covers the other case, where the goods
themselves go back and stock moves with them. The purchasing mirror of
`app/credit_note`.
"""

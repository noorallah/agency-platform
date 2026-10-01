"""Party adjustments: a balance moved without money and without tax (74 row 2).

A customer's debt written off, a supplier's balance written back, and a set-off
between a customer and a supplier who are the same business. Each posts its
journal at approval and, where it names bills, takes them off what those bills
still owe -- through `party_adjustment_allocations`, read beside
`settlement_allocations` by every derivation of what a bill owes.
"""

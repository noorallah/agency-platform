"""The labels a grouped report uses for a group that has no name.

A report grouped by salesperson, territory, route or warehouse has to say
something about the rows carrying none. Dropping them is the one answer that
cannot be right: the totals then fail to reconcile against the register, and
nothing on the screen says why. The delivery-note by-* reports have always
bucketed them under "Unassigned" and the sales-order ones dropped them, so
the same firm's orders totalled differently in two places (D-RPT-19).

The constant lives here, outside any one module, because the whole point is
that every report spells it the same way.
"""

#: The group a row with no salesperson, territory, route or warehouse falls in.
UNASSIGNED = "Unassigned"

__all__ = ["UNASSIGNED"]

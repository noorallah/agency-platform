"""Contra vouchers: money moved between the firm's own cash and bank (74 row 3).

A deposit, a withdrawal, or a transfer between two bank or two cash accounts.
Each posts its journal on save -- Dr the account the money went to, Cr the one
it left -- and is undone by cancelling, which mirrors it.
"""

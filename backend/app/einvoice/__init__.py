"""Registering a sales invoice with the tax authority, and its e-way bill.

Both live here because they share one portal, one set of credentials and one
failure story. Every registration records the **mode** it was made in, and a
sandbox one marks every reference it mints: a rehearsal that could be mistaken
for a filing is a document somebody eventually presents at a check post.
"""

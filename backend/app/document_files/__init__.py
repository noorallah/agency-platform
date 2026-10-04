"""Files uploaded onto purchase documents: the supplier's bill, its photo (PG-4).

The first file *content* this platform keeps. The older ``*_attachments``
tables beside each document record where a file is -- a path the client
typed -- and are rewritten wholesale on every edit of their document, so an
uploaded file cannot live there. ``document_files`` holds the metadata and
``document_file_contents`` the bytes, in the firm's own store, so a list never
loads a file and a firm's paper travels with its database.
"""

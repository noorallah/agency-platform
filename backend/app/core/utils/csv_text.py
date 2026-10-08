"""Text that is safe to put in a cell of an exported file.

An export is opened in a spreadsheet, and a spreadsheet runs a cell that
begins with ``=``, ``+``, ``-`` or ``@`` as a formula. A product named
``=1+1`` therefore arrived as 2, and a name somebody chose with care could
have fetched a web page (inventory round 1, F11). The convention every
exporting tool follows is to put an apostrophe in front, which a spreadsheet
shows as the text that was typed.
"""

#: What a spreadsheet reads as the start of a formula, and the two control
#: characters that let one begin after a harmless-looking prefix.
_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def sheet_text(value: object) -> str:
    """Return text a spreadsheet will show rather than run.

    Args:
        value: What the cell holds; ``None`` is an empty cell.

    """
    text = "" if value is None else str(value)
    if text.startswith(_FORMULA_STARTS):
        return "'" + text
    return text


def csv_text(value: object) -> str:
    """Return one CSV field: shown rather than run, and quoted where needed.

    A comma, a quote or a line break inside a name used to shift every column
    after it, so the field is quoted the way RFC 4180 says whenever it holds
    one.
    """
    text = sheet_text(value)
    if any(mark in text for mark in (",", '"', "\n", "\r")):
        return '"' + text.replace('"', '""') + '"'
    return text

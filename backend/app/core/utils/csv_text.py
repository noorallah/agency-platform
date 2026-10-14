"""Text that is safe to put in a cell of an exported file.

An export is opened in a spreadsheet, and a spreadsheet runs a cell that
begins with ``=``, ``+``, ``-`` or ``@`` as a formula. A product named
``=1+1`` therefore arrived as 2, and a name somebody chose with care could
have fetched a web page (inventory round 1, F11). The convention every
exporting tool follows is to put an apostrophe in front, which a spreadsheet
shows as the text that was typed.
"""

import csv
import io
import re
from collections.abc import Iterable, Iterator, Mapping
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from _typeshed import SupportsWrite

#: What a spreadsheet reads as the start of a formula, and the two control
#: characters that let one begin after a harmless-looking prefix.
_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")

#: A number written as text -- ``-150.00``, ``1,250.5``, ``+919876543210``.
#: A spreadsheet reads it as the number it is and runs nothing, and an
#: apostrophe in front would make it text that no longer adds up.
_PLAIN_NUMBER = re.compile(r"[+-]?\d[\d,]*(\.\d+)?")


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


def sheet_cell(value: object) -> object:
    """Return a cell for ``csv.writer``: text guarded, numbers as they are.

    A number stays a number whether it arrives as one or already written
    out as text, because a figure an export formatted itself (``-150.00``)
    is no formula; anything else that is text is guarded as
    :func:`sheet_text` guards it.
    """
    if not isinstance(value, str) or _PLAIN_NUMBER.fullmatch(value):
        return value
    return sheet_text(value)


class SheetWriter:
    """A ``csv.writer`` whose every text cell is shown rather than run.

    Every export a person opens in a spreadsheet writes through this
    (D-MST-23): they wrote with the bare ``csv.writer``, which quotes a
    comma but runs ``=1+1``. Two files keep the bare writer on purpose,
    because other software reads them as written: the bank's payment file
    and the TDS deductee sheet.
    """

    def __init__(
        self, stream: "SupportsWrite[str]", *, lineterminator: str = "\r\n"
    ) -> None:
        """Write to ``stream``, each record ended by ``lineterminator``."""
        self._writer = csv.writer(stream, lineterminator=lineterminator)

    def writerow(self, row: Iterable[object]) -> None:
        """Write one record, each text cell made safe."""
        self._writer.writerow([sheet_cell(cell) for cell in row])

    def writerows(self, rows: Iterable[Iterable[object]]) -> None:
        """Write every record, each text cell made safe."""
        for row in rows:
            self.writerow(row)


def unsheet(text: str) -> str:
    """Take off the apostrophe an export put in front of a formula's start.

    So a file exported here and read back by an import holds what was
    typed: ``'+91 98400 12345`` comes back as ``+91 98400 12345``. Only an
    apostrophe followed by one of the characters the guard protects is
    taken off; a name that begins with an apostrophe otherwise keeps it.
    """
    if len(text) > 1 and text[0] == "'" and text[1:].startswith(_FORMULA_STARTS):
        return text[1:]
    return text


def unsheet_record(record: Mapping[str, str | None]) -> dict[str, str | None]:
    """Return a ``csv.DictReader`` record with every guarded value restored."""
    return {
        key: unsheet(value) if isinstance(value, str) else value
        for key, value in record.items()
    }


def read_records(text: str) -> Iterator[dict[str, str | None]]:
    """Read CSV text as records, each guarded value restored (D-MST-23)."""
    for record in csv.DictReader(io.StringIO(text)):
        yield unsheet_record(record)


def csv_line(cells: Iterable[object]) -> str:
    """Return one CSV record from its cells, each one made safe.

    Every hand-built export joins its cells here rather than with
    ``",".join``, which neither quoted a comma nor guarded a formula
    (D-MST-22). A number is written as it is: ``-5`` is a quantity, not the
    start of a formula, and an apostrophe in front would turn it into text.
    ``None`` is an empty cell.
    """
    return ",".join(
        (
            str(cell)
            if isinstance(cell, int | float | Decimal) and not isinstance(cell, bool)
            else csv_text(cell)
        )
        for cell in cells
    )

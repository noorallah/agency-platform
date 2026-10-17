"""Turn a Swathi MySQL dump into our import-template CSV files.

Swathi trial conversion, part 1 (plan: ``docs/SWATHI_IMPORT_PLAN.md``). The
dump is plain ``CREATE TABLE`` / ``INSERT`` text, so no MySQL server is
needed. The output is real customer data: write it **outside the repository**
and never print a name, a GST number or a bank detail -- only counts.

Usage::

    python scripts/swathi_dump_to_templates.py DUMP.sql OUTPUT_DIR [STATE]

``STATE`` is the state name written on every **customer** row, because the dump
holds none; left out, the column is blank. A **supplier** may be from any state,
so its State comes from the first two digits of its GSTIN (the GST state code);
one with no usable GSTIN is left blank and its code is written to
``suppliers_state_questions.txt`` for the customer to answer -- never guessed.

Files written (one per import kind, headings as the templates give them):
``principals.csv``, ``brands.csv``, ``routes.csv``, ``salesmen.csv``,
``customers.csv``, ``suppliers.csv``, ``ledger_accounts.csv``.
"""

import csv
import re
import sys
from pathlib import Path
from typing import Any

#: Heads whose accounts are customers, and suppliers; every other head is a
#: ledger account (plan, section 2).
CUSTOMER_HEADS = frozenset({8, 28})
SUPPLIER_HEADS = frozenset({9, 27, 29})

#: Group written for an account whose head the dump does not name, so the
#: value mapping can send it somewhere on purpose.
UNASSIGNED_GROUP = "UNASSIGNED"

#: ``P & L ACCOUNTS`` mixes income and expense heads; an account whose name
#: carries one of these words is income and gets its own group to map.
PL_GROUP = "P & L ACCOUNTS"
PL_INCOME_GROUP = "P & L ACCOUNTS (INCOME)"
PL_INCOME_WORDS = ("RECEIVED", "RECD", "INCOME", "COMMISSION RECEIPT", "GAIN")

#: GST state codes (first two digits of a GSTIN) -> state name.
GST_STATES = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab",
    "04": "Chandigarh", "05": "Uttarakhand", "06": "Haryana", "07": "Delhi",
    "08": "Rajasthan", "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim",
    "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur",
    "15": "Mizoram", "16": "Tripura", "17": "Meghalaya", "18": "Assam",
    "19": "West Bengal", "20": "Jharkhand", "21": "Odisha",
    "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra",
    "29": "Karnataka", "30": "Goa", "31": "Lakshadweep", "32": "Kerala",
    "33": "Tamil Nadu", "34": "Puducherry",
    "35": "Andaman and Nicobar Islands", "36": "Telangana",
    "37": "Andhra Pradesh", "38": "Ladakh",
}  # fmt: skip


def state_from_gstin(gstin: str) -> str:
    """Return the state a GSTIN's first two digits name, or blank."""
    return GST_STATES.get(gstin[:2], "") if len(gstin) == 15 else ""


_CREATE = re.compile(r"CREATE TABLE `(\w+)` \((.*?)\n\)", re.S)
_COLUMN = re.compile(r"^\s*`(\w+)`", re.M)
_INSERT = re.compile(r"INSERT INTO `(\w+)` VALUES ")

Row = dict[str, Any]


def _parse_values(text: str, start: int) -> tuple[list[list[Any]], int]:
    """Read ``(..),(..);`` from ``start``; return the tuples and the end."""
    rows: list[list[Any]] = []
    i = start
    n = len(text)
    while i < n:
        if text[i] != "(":
            break
        i += 1
        row: list[Any] = []
        while True:
            ch = text[i]
            if ch == "'":
                i += 1
                buf: list[str] = []
                while True:
                    ch = text[i]
                    if ch == "\\":
                        nxt = text[i + 1]
                        buf.append(
                            {"n": "\n", "r": "\r", "t": "\t", "0": ""}.get(nxt, nxt)
                        )
                        i += 2
                    elif ch == "'":
                        if text[i + 1] == "'":
                            buf.append("'")
                            i += 2
                        else:
                            i += 1
                            break
                    else:
                        buf.append(ch)
                        i += 1
                row.append("".join(buf))
            else:
                j = i
                while text[j] not in ",)":
                    j += 1
                token = text[i:j]
                i = j
                row.append(None if token == "NULL" else token)
            if text[i] == ",":
                i += 1
                continue
            i += 1  # the closing bracket
            break
        rows.append(row)
        if i < n and text[i] == ",":
            i += 1
            continue
        break
    return rows, i


def read_dump(path: Path, wanted: set[str]) -> dict[str, list[Row]]:
    """Read the named tables of a dump into lists of column-keyed rows."""
    text = path.read_text(encoding="utf-8", errors="replace")
    columns: dict[str, list[str]] = {}
    for match in _CREATE.finditer(text):
        if match.group(1) in wanted:
            columns[match.group(1)] = _COLUMN.findall(match.group(2))
    tables: dict[str, list[Row]] = {name: [] for name in wanted}
    for match in _INSERT.finditer(text):
        name = match.group(1)
        if name not in wanted or name not in columns:
            continue
        values, _ = _parse_values(text, match.end())
        names = columns[name]
        tables[name].extend(dict(zip(names, row, strict=False)) for row in values)
    return tables


def _text(value: object) -> str:
    """Return a trimmed string; ``None`` is blank."""
    return "" if value is None else str(value).strip()


def _int(value: object) -> int | None:
    """Return an integer, or ``None`` when blank or not a number."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _code(prefix: str, number: object) -> str:
    """Our code for a Swathi number: the prefix and the number kept."""
    return f"{prefix}{_text(number)}"


def _email(value: object) -> str:
    """Return the address, or blank for the one-character filler Swathi keeps."""
    text = _text(value)
    return text if "@" in text else ""


def _phone(value: object) -> str:
    """Digits and a leading plus only."""
    return re.sub(r"[^0-9+]", "", _text(value))


def principals(tables: dict[str, list[Row]]) -> list[Row]:
    """``company`` -> principals."""
    return [
        {
            "Code": _code("CO", r["comp_id"]),
            "Name": _text(r["company"]),
            "Active": "Yes",
        }
        for r in tables["company"]
    ]


def brands(tables: dict[str, list[Row]]) -> list[Row]:
    """``codehead`` -> brands, each under the company it names."""
    return [
        {
            "Name": _text(r["headname"]),
            "Company": _code("CO", r["comp_id"]),
            "Active": "Yes",
        }
        for r in tables["codehead"]
    ]


def routes(tables: dict[str, list[Row]]) -> list[Row]:
    """``beatman`` rows of type B -> routes."""
    return [
        {
            "Code": _code("BEAT", r["bcode"]),
            "Name": _text(r["bname"]),
            "Parent": "",
            "Type": "",
            "Frequency": "",
            "Days": "",
            "Status": "Active",
        }
        for r in tables["beatman"]
        if _text(r["ctype"]) == "B"
    ]


def salesmen(tables: dict[str, list[Row]]) -> list[Row]:
    """``beatman`` rows of type S -> salesmen."""
    return [
        {
            "Code": _code("SM", r["bcode"]),
            "Name": _text(r["bname"]),
            "Phone": "",
            "Commission": "",
            "Active": "Yes",
            "Notes": "",
        }
        for r in tables["beatman"]
        if _text(r["ctype"]) == "S"
    ]


def _account_rows(tables: dict[str, list[Row]], heads: frozenset[int]) -> list[Row]:
    """Return the ``codes`` rows under the given heads."""
    return [r for r in tables["codes"] if _int(r["hcode"]) in heads]


def customers(tables: dict[str, list[Row]]) -> list[Row]:
    """``codes`` heads 8 and 28 -> customers, with beat and licence."""
    out: list[Row] = []
    for r in _account_rows(tables, CUSTOMER_HEADS):
        beat = _int(r.get("mcode"))
        licence = _text(r.get("dlone"))
        out.append(
            {
                "Code": _code("C", r["acode"]),
                "Name": _text(r["acname"]),
                "Type": "BUSINESS",
                "GSTIN": _text(r.get("tin")).upper(),
                "PAN": _text(r.get("pan")).upper(),
                "Email": _email(r.get("mail")),
                "Phone": _phone(r.get("ph")),
                "Status": "ACTIVE" if _text(r.get("act")) != "N" else "INACTIVE",
                "Address1": _text(r.get("adr1")),
                "Address2": _text(r.get("adr2")),
                "City": _text(r.get("city")),
                "State": "",
                "PIN": _text(r.get("pin")) if _int(r.get("pin")) else "",
                "Country": "IN",
                "Beat": _code("BEAT", beat) if beat else "",
                "LicenceType": "DRUG_WHOLESALE" if licence else "",
                "LicenceNumber": licence,
                "LicenceExpiry": "",
            }
        )
    return out


def suppliers(tables: dict[str, list[Row]]) -> list[Row]:
    """``codes`` heads 9, 27 and 29 -> suppliers."""
    out: list[Row] = []
    for r in _account_rows(tables, SUPPLIER_HEADS):
        out.append(
            {
                "Code": _code("S", r["acode"]),
                "Name": _text(r["acname"]),
                "GSTIN": _text(r.get("tin")).upper(),
                "PAN": _text(r.get("pan")).upper(),
                "Email": _email(r.get("mail")),
                "Phone": _phone(r.get("ph")),
                "Address1": _text(r.get("adr1")),
                "Address2": _text(r.get("adr2")),
                "City": _text(r.get("city")),
                "State": "",
                "PIN": _text(r.get("pin")) if _int(r.get("pin")) else "",
                "Country": "IN",
            }
        )
    return out


def ledger_accounts(tables: dict[str, list[Row]]) -> list[Row]:
    """``codes`` under every other head -> chart of accounts.

    The group is the Swathi head's name (``acchead``); it is mapped onto the
    firm's own account groups by a saved value mapping (gap G6, part 2).
    """
    heads = {_int(h["hcode"]): _text(h["hname"]) for h in tables["acchead"]}
    skip = CUSTOMER_HEADS | SUPPLIER_HEADS
    out: list[Row] = []
    for r in tables["codes"]:
        if _int(r["hcode"]) in skip:
            continue
        name = _text(r["acname"])
        group = heads.get(_int(r["hcode"]), _text(r["hcode"])) or UNASSIGNED_GROUP
        if group == PL_GROUP and any(w in name.upper() for w in PL_INCOME_WORDS):
            group = PL_INCOME_GROUP
        out.append(
            {
                "Code": _code("A", r["acode"]),
                "Name": name,
                "Group": group,
                "Description": "",
                "Active": "Yes",
            }
        )
    return out


#: Output file -> (builder, headings in template order).
OUTPUTS: dict[str, tuple[Any, tuple[str, ...]]] = {
    "principals.csv": (principals, ("Code", "Name", "Supplier", "Active")),
    "brands.csv": (brands, ("Name", "Company", "Active")),
    "routes.csv": (
        routes,
        ("Code", "Name", "Parent", "Type", "Frequency", "Days", "Status"),
    ),
    "salesmen.csv": (
        salesmen,
        ("Code", "Name", "Phone", "Commission", "Active", "Notes"),
    ),
    "customers.csv": (
        customers,
        (
            "Code",
            "Name",
            "Type",
            "GSTIN",
            "PAN",
            "Email",
            "Phone",
            "Status",
            "Address1",
            "Address2",
            "City",
            "State",
            "PIN",
            "Country",
            "Beat",
            "LicenceType",
            "LicenceNumber",
            "LicenceExpiry",
        ),
    ),
    "suppliers.csv": (
        suppliers,
        (
            "Code",
            "Name",
            "GSTIN",
            "PAN",
            "Email",
            "Phone",
            "Address1",
            "Address2",
            "City",
            "State",
            "PIN",
            "Country",
        ),
    ),
    "ledger_accounts.csv": (
        ledger_accounts,
        ("Code", "Name", "Group", "Description", "Active"),
    ),
}

TABLES = {"company", "codehead", "beatman", "codes", "acchead"}


def convert(dump: Path, out_dir: Path, state: str = "") -> dict[str, int]:
    """Write every file; return the number of rows written per file.

    ``state`` is written on every customer and supplier row (the dump has none).
    """
    tables = read_dump(dump, set(TABLES))
    out_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for filename, (builder, headings) in OUTPUTS.items():
        rows = builder(tables)
        for row in rows:
            if "State" in row and "Type" in row:
                row["State"] = state
            elif "State" in row:
                row["State"] = state_from_gstin(row["GSTIN"])
        with (out_dir / filename).open("w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=headings, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        counts[filename] = len(rows)
        if filename == "suppliers.csv":
            open_codes = [r["Code"] for r in rows if not r["State"]]
            (out_dir / "suppliers_state_questions.txt").write_text(
                "\n".join(open_codes), encoding="utf-8"
            )
    return counts


def main(argv: list[str]) -> int:
    """Command line: dump path, output directory; prints counts only."""
    if len(argv) not in (3, 4):
        print(__doc__)
        return 2
    state = argv[3] if len(argv) == 4 else ""
    for filename, count in convert(Path(argv[1]), Path(argv[2]), state).items():
        print(f"{filename}: {count} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

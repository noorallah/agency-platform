"""Build the places pack shipped with the server from India Post's directory.

The source is the *All India Pincode Directory* published by the Department of
Posts on data.gov.in under the Government Open Data Licence - India, which
permits redistribution with attribution (decision B6). Download the CSV from
https://www.data.gov.in/catalog/all-india-pincode-directory and run::

    uv run python scripts/build_places_pack.py path/to/the.csv

It writes ``app/sales/data/india_post_pincodes.csv.gz``: one row per post
office, holding only what the places loader reads -- the state's two-letter
code, district, PIN code, office name and office type -- so the pack is a
tenth of the source's size. Rows with no state ("NA") are dropped. Rebuild it
when India Post republishes; the loader skips what a store already holds, so
loading a newer pack adds only what is new.
"""

import csv
import gzip
import sys
from pathlib import Path

#: India Post's state names to the codes ``20260917_0137`` seeds.
STATE_CODES = {
    "ANDAMAN AND NICOBAR ISLANDS": "AN",
    "ANDHRA PRADESH": "AP",
    "ARUNACHAL PRADESH": "AR",
    "ASSAM": "AS",
    "BIHAR": "BR",
    "CHANDIGARH": "CH",
    "CHHATTISGARH": "CG",
    "DELHI": "DL",
    "GOA": "GA",
    "GUJARAT": "GJ",
    "HARYANA": "HR",
    "HIMACHAL PRADESH": "HP",
    "JAMMU AND KASHMIR": "JK",
    "JHARKHAND": "JH",
    "KARNATAKA": "KA",
    "KERALA": "KL",
    "LADAKH": "LA",
    "LAKSHADWEEP": "LD",
    "MADHYA PRADESH": "MP",
    "MAHARASHTRA": "MH",
    "MANIPUR": "MN",
    "MEGHALAYA": "ML",
    "MIZORAM": "MZ",
    "NAGALAND": "NL",
    "ODISHA": "OD",
    "PUDUCHERRY": "PY",
    "PUNJAB": "PB",
    "RAJASTHAN": "RJ",
    "SIKKIM": "SK",
    "TAMIL NADU": "TN",
    "TELANGANA": "TS",
    "THE DADRA AND NAGAR HAVELI AND DAMAN AND DIU": "DH",
    "TRIPURA": "TR",
    "UTTAR PRADESH": "UP",
    "UTTARAKHAND": "UK",
    "WEST BENGAL": "WB",
}

PACK = Path(__file__).resolve().parents[1] / "app/sales/data/india_post_pincodes.csv.gz"


def main(source: str) -> None:
    """Read the directory and write the pack, reporting what was dropped."""
    kept = 0
    unknown: dict[str, int] = {}
    with (
        open(source, encoding="utf-8-sig", newline="") as raw,
        gzip.open(PACK, "wt", encoding="utf-8", newline="") as packed,
    ):
        writer = csv.writer(packed)
        writer.writerow(["state", "district", "pincode", "office", "type"])
        rows = sorted(
            csv.DictReader(raw),
            key=lambda row: (row["statename"], row["district"], row["pincode"]),
        )
        for row in rows:
            code = STATE_CODES.get(row["statename"].strip().upper())
            if code is None:
                name = row["statename"].strip()
                unknown[name] = unknown.get(name, 0) + 1
                continue
            writer.writerow(
                [
                    code,
                    row["district"].strip(),
                    row["pincode"].strip(),
                    row["officename"].strip(),
                    row["officetype"].strip(),
                ]
            )
            kept += 1
    print(f"{kept} offices written to {PACK}")
    for name, count in sorted(unknown.items()):
        print(f"  dropped {count} rows with state {name!r}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: build_places_pack.py <india-post-directory.csv>")
    main(sys.argv[1])

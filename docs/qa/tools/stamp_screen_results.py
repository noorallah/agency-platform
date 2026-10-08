#!/usr/bin/env python3
"""File the results of the screen click tests under the case book's ids.

Reads the ``FLOW:`` lines the integration tests print (``integration_test/run.sh``
leaves a log per file in ``$TEMP/agency-it-<file>.log``), and

* keeps every result in ``docs/qa/tools/screen_results_round2.json`` (latest run
  of a case wins, so a feature can be re-run alone);
* writes ``docs/qa/SCREEN_FLOW_CHECK_ROUND_2_2026-10-07.md``: one row per case
  run, with the Findings and Established-behaviour sections you keep by hand
  between the ``<!-- HAND:... -->`` markers (kept across regenerations);
* stamps the "Automated in" and "Result" columns of
  ``docs/qa/SCREEN_TEST_CASES_BUY_SELL_PRICE.md`` for those ids.

Usage (from the repository root)::

    python docs/qa/tools/stamp_screen_results.py [log files...]

With no argument it reads every ``agency-it-sc_*.log`` and the three positive
flows' logs in ``$TEMP``. A line is filed under a case id when its label starts
with one (``SC-SO-014``); several lines for one id (a case with two attempts)
combine: any FAIL or DEFECT fails the case, otherwise any PASS passes it, and a
case with only SKIP lines is skipped.
"""
from __future__ import annotations

import datetime
import glob
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BOOK = ROOT / "docs" / "qa" / "SCREEN_TEST_CASES_BUY_SELL_PRICE.md"
REPORT = ROOT / "docs" / "qa" / "SCREEN_FLOW_CHECK_ROUND_2_2026-10-07.md"
STORE = ROOT / "docs" / "qa" / "tools" / "screen_results_round2.json"
DATE = "2026-10-07"
#: The day of the run being filed. A case run again on a later day (the
#: re-drive after a fix) carries that day, not the round's.
RUN_DATE = os.environ.get("SCREEN_RUN_DATE") or datetime.date.today().isoformat()

LINE = re.compile(
    r"FLOW: (PASS|FAIL|SKIP|DEFECT|INFO) \[([^\]]+)\] (SC-[A-Z]+-\d{3})\b(.*)$"
)
ID_ROW = re.compile(r"^\| (SC-[A-Z]+-\d{3}) \| (\w[\w-]*) \|")

# Cases the three positive flows cover, by their original step names.
POSITIVE_RENAME = {
    "selling": "selling_flow_test.dart",
    "buying": "buying_flow_test.dart",
    "pricing": "pricing_flow_test.dart",
}


def flow_file(name: str, log_path: str) -> str:
    """The test file a flow name came from."""
    base = os.path.basename(log_path)
    m = re.match(r"agency-it-(sc_[a-z]+)(?:_[a-z0-9]+)?\.log$", base)
    if m:
        return m.group(1) + "_test.dart"
    m = re.match(r"agency-it-([a-z_]+?)(?:\.[a-z0-9]+)?\.log$", base)
    if m:
        return m.group(1) + ".dart"
    return POSITIVE_RENAME.get(name.split("-")[0], name)


def parse(paths: list[str]) -> dict[str, dict]:
    """Case id -> combined result from the given logs (later logs win)."""
    found: dict[str, dict] = {}
    for path in paths:
        per_run: dict[str, dict] = {}
        with open(path, encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                m = LINE.search(raw.rstrip("\n"))
                if not m:
                    continue
                kind, name, cid, rest = m.groups()
                rest = rest.strip()
                # A step that covers several cases names them all up front.
                extra = re.match(r"((?:SC-[A-Z]+-\d{3}\s+)+)", rest + " ")
                ids = [cid] + (extra.group(1).split() if extra else [])
                if extra:
                    rest = rest[len(extra.group(1).rstrip()) :].strip()
                for cid in ids:
                    _record(per_run, kind, name, cid, rest, path)
        for cid, entry in per_run.items():
            if entry["fail"]:
                entry["result"] = "FAIL"
            elif entry["pass"]:
                entry["result"] = "PASS"
            else:
                entry["result"] = "SKIP"
            found[cid] = entry
    return found


def _record(per_run: dict, kind: str, name: str, cid: str, rest: str, path: str) -> None:
    """Add one FLOW line's outcome to its case's entry."""
    entry = per_run.setdefault(
        cid,
        {
            "pass": 0,
            "fail": 0,
            "skip": 0,
            "notes": [],
            "file": flow_file(name, path),
            "user": name.split("-", 1)[1] if "-" in name else "",
        },
    )
    if kind == "PASS":
        entry["pass"] += 1
        note = rest.split(" :: ", 1)[1] if " :: " in rest else ""
    elif kind in ("FAIL", "DEFECT"):
        entry["fail"] += 1
        note = rest.split(": ", 1)[1] if ": " in rest else rest
    elif kind == "SKIP":
        entry["skip"] += 1
        note = re.sub(r"^.*\(because (.*)\)\s*$", r"\1", rest)
    else:
        note = rest.split(" :: ", 1)[1] if " :: " in rest else rest
        note = "note: " + note
    if note:
        entry["notes"].append(note)


def book_kinds() -> dict[str, str]:
    """Case id -> kind, read from the book's tables."""
    kinds: dict[str, str] = {}
    for line in BOOK.read_text(encoding="utf-8").splitlines():
        m = ID_ROW.match(line)
        if m:
            kinds[m.group(1)] = m.group(2)
    return kinds


def clean(text: str, limit: int = 380) -> str:
    """One table cell: no pipes, no newlines, bounded."""
    text = text.replace("|", "/").replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 3] + "..."


def hand(text: str, tag: str, default: str) -> str:
    """The hand-kept block between the markers of the old report, or default."""
    m = re.search(
        rf"<!-- HAND:{tag} -->\n(.*?)<!-- /HAND:{tag} -->", text, flags=re.S
    )
    return m.group(1) if m else default


FINDINGS_DEFAULT = (
    "| Id | Severity | Case | Screen | What a person sees | Expected | File:line |\n"
    "| --- | --- | --- | --- | --- | --- | --- |\n"
)
ESTABLISHED_DEFAULT = "- (none yet)\n"


def write_report(results: dict[str, dict], kinds: dict[str, str]) -> None:
    """Regenerate the round 2 report, keeping the hand-kept sections."""
    old = REPORT.read_text(encoding="utf-8") if REPORT.exists() else ""
    findings = hand(old, "FINDINGS", FINDINGS_DEFAULT)
    established = hand(old, "ESTABLISHED", ESTABLISHED_DEFAULT)
    notes = hand(old, "NOTES", "")
    order = sorted(results)
    tally: dict[str, dict[str, int]] = {}
    for cid in order:
        feature = cid.split("-")[1]
        kind = kinds.get(cid, "?")
        slot = tally.setdefault(feature, {})
        key = f"{kind} {results[cid]['result']}"
        slot[key] = slot.get(key, 0) + 1
    out = [
        "# Screen cases, round 2: click tests against the real server, 2026-10-07",
        "",
        "Generated by `docs/qa/tools/stamp_screen_results.py` from the `FLOW:` lines of",
        "the run logs; the Findings, Established behaviour and Notes sections are kept by",
        "hand and survive regeneration. Book: `SCREEN_TEST_CASES_BUY_SELL_PRICE.md`.",
        "Firm T10069CWY-S; users are the fixture firm's `t10069cwy.<handle>` accounts",
        "(tradeadmin = FA, qsexe = FS, qsmgr = SM, qstore = WH, qpexe = PU,",
        "qpmgr = PM, qacct = AC, qro = RO, qfmgr = FM). A case that names FS or SM",
        "and is a refusal runs as the administrator unless its Role kind says otherwise.",
        "",
        "## Findings",
        "",
        "<!-- HAND:FINDINGS -->",
        findings.rstrip("\n"),
        "<!-- /HAND:FINDINGS -->",
        "",
        "## Established behaviour (the book should say this)",
        "",
        "<!-- HAND:ESTABLISHED -->",
        established.rstrip("\n"),
        "<!-- /HAND:ESTABLISHED -->",
        "",
        "## Notes",
        "",
        "<!-- HAND:NOTES -->",
        notes.rstrip("\n"),
        "<!-- /HAND:NOTES -->",
        "",
        "## Tally by feature",
        "",
        "| Feature | Counts (kind result: n) |",
        "| --- | --- |",
    ]
    for feature, slot in sorted(tally.items()):
        out.append(
            f"| {feature} | " + ", ".join(f"{k}: {v}" for k, v in sorted(slot.items())) + " |"
        )
    out += [
        "",
        "## Result per case",
        "",
        "| Id | Kind | Result | What the screen showed | Flow file |",
        "| --- | --- | --- | --- | --- |",
    ]
    for cid in order:
        r = results[cid]
        shown = clean("; ".join(r["notes"]) or "-", 600)
        user = f" ({r['user']})" if r.get("user") else ""
        again = r.get("date", DATE)
        word = r["result"] + (f" (run again {again})" if again != DATE else "")
        out.append(
            f"| {cid} | {kinds.get(cid, '?')} | {word} | {shown} | "
            f"`{r['file']}`{user} |"
        )
    REPORT.write_text("\n".join(out) + "\n", encoding="utf-8")


def stamp_book(results: dict[str, dict]) -> int:
    """Fill Automated in and Result in the book's rows; returns rows stamped."""
    lines = BOOK.read_text(encoding="utf-8").split("\n")
    stamped = 0
    for i, line in enumerate(lines):
        m = ID_ROW.match(line)
        if not m or m.group(1) not in results:
            continue
        cells = line.split(" | ")
        # The row ends "| <Automated in> | <Result> |"; split keeps the edges.
        if len(cells) < 9:
            continue
        r = results[m.group(1)]
        auto = f"`{r['file']}`" + (f" ({r['user']})" if r.get("user") else "")
        note = clean("; ".join(r["notes"]), 160)
        word = {"PASS": "Pass", "FAIL": "Fail", "SKIP": "Skipped"}[r["result"]]
        result = f"{word} {r.get('date', DATE)}" + (
            f": {note}" if note and note != "-" else ""
        )
        cells[-2] = auto
        cells[-1] = result + " |"
        lines[i] = " | ".join(cells)
        stamped += 1
    BOOK.write_text("\n".join(lines), encoding="utf-8")
    return stamped


def main(argv: list[str]) -> None:
    """Parse logs, merge into the store, write the report, stamp the book."""
    temp = os.environ.get("TEMP", "/tmp")
    paths = argv or sorted(
        glob.glob(os.path.join(temp, "agency-it-sc_*.log"))
        + glob.glob(os.path.join(temp, "agency-it-selling_flow_test.log"))
        + glob.glob(os.path.join(temp, "agency-it-buying_flow_test.log"))
        + glob.glob(os.path.join(temp, "agency-it-pricing_flow_test.log"))
    )
    store: dict[str, dict] = (
        json.loads(STORE.read_text(encoding="utf-8")) if STORE.exists() else {}
    )
    fresh = parse(paths)
    for entry in fresh.values():
        entry["date"] = RUN_DATE
    store.update(fresh)
    STORE.write_text(json.dumps(store, indent=1, sort_keys=True), encoding="utf-8")
    kinds = book_kinds()
    write_report(store, kinds)
    print(f"{len(store)} cases on file, {stamp_book(store)} book rows stamped")


if __name__ == "__main__":
    main(sys.argv[1:])

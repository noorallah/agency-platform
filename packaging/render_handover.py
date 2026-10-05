"""Render the QA hand-over documents to HTML and PDF beside each other.

A build-time tool, like `render_guide.py`, which it reuses: each document in
`docs/` is rendered to one self-contained HTML page and printed to a PDF with
Edge. Run from the repository root with an interpreter that has the
`markdown` package (the backend's):

    python packaging/render_handover.py "dist/windows/<folder>" [name-filter]
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_guide import render  # noqa: E402

EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
DOCS = Path("docs")

#: The hand-over's documents: the name a tester sees, and its source in docs/.
DOCUMENTS: list[tuple[str, str]] = [
    ("01 Release notes 1.3.0", "RELEASE_NOTES_1.3.0.md"),
    ("02 Sanity check", "qa/SANITY_CHECK.md"),
    ("03 QA module reference", "QA_MODULE_REFERENCE.md"),
    ("04 QA test book", "QA_TEST_BOOK.md"),
    ("05 QA functional walkthrough (end to end)", "QA_FUNCTIONAL_WALKTHROUGH.md"),
    ("07 Installation guide", "INSTALL_GUIDE.md"),
    ("08 Installer QA checklist", "INSTALLER_QA_CHECKLIST.md"),
    ("09 Sales flow and configuration", "SALES_TO_RECEIPT_FLOW.md"),
    ("10 Purchase flow and configuration", "PURCHASE_TO_PAYMENT_FLOW.md"),
    ("11 GST documents compliance", "GST_DOCUMENT_COMPLIANCE.md"),
    ("12 Application features guide", "APPLICATION_FEATURES_GUIDE.md"),
    ("13 Configuration settings guide", "CONFIGURATION_SETTINGS_GUIDE.md"),
    ("14 Functional guide", "FUNCTIONAL_GUIDE.md"),
    ("15 Go-live guide", "GO_LIVE_GUIDE.md"),
    ("16 Profit and loss guide", "PROFIT_AND_LOSS_GUIDE.md"),
    ("17 Promotions and discounts guide", "PROMOTIONS_AND_DISCOUNTS_GUIDE.md"),
    ("18 User administration guide", "USER_ADMINISTRATION_GUIDE.md"),
    ("19 Messaging setup guide", "MESSAGING_SETUP_GUIDE.md"),
    ("20 Release notes 1.2.0 (carried into 1.3.0)", "RELEASE_NOTES_1.2.0.md"),
    ("21 Selling reference", "SALES_FRAMEWORK.md"),
    ("22 Purchasing reference", "PURCHASE_FRAMEWORK.md"),
    ("23 Module status", "MODULE_STATUS.md"),
    ("24 Known defects", "DEFECTS.md"),
]


def suite() -> list[tuple[str, str]]:
    """Return the QA suite chapters, named as the earlier hand-overs named them."""
    chapters = []
    for path in sorted((DOCS / "qa").glob("[0-9][0-9]_*.md")):
        number, _, rest = path.stem.partition("_")
        title = rest.replace("_", " ").title()
        chapters.append((f"06 QA suite/QA suite {number} {title}", f"qa/{path.name}"))
    return chapters


def to_pdf(html: Path) -> bool:
    """Print one HTML page to a PDF beside it with Edge; say whether it worked."""
    pdf = html.with_suffix(".pdf")
    if pdf.exists():
        pdf.unlink()
    subprocess.run(  # noqa: S603
        [
            str(EDGE),
            "--headless",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={pdf.resolve()}",
            html.resolve().as_uri(),
        ],
        check=False,
        capture_output=True,
        timeout=300,
    )
    return pdf.exists() and pdf.stat().st_size > 1000


def main(argv: list[str]) -> int:
    """Render every document; report what failed."""
    if len(argv) < 2:
        print(__doc__)
        return 2
    target = Path(argv[1])
    only = argv[2].lower() if len(argv) > 2 else ""
    failed: list[str] = []
    done = 0
    for name, source in [*DOCUMENTS, *suite()]:
        if only and only not in name.lower():
            continue
        origin = DOCS / source
        if not origin.exists():
            failed.append(f"{name}: source {origin} is missing")
            continue
        html = target / f"{name}.html"
        html.parent.mkdir(parents=True, exist_ok=True)
        render(origin, html)
        if to_pdf(html):
            done += 1
        else:
            failed.append(f"{name}: no PDF produced")
    print(f"{done} document(s) rendered to HTML and PDF in {target}")
    for line in failed:
        print("FAILED", line)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

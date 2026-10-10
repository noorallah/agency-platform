"""Turn a plain Markdown document into an A4 PDF.

What builds the customer documents in `dist/customer` from their sources in
`docs/`: the question list, the meeting guide, the brochure, the demonstration
script and the promotions guide. It reads headings, tables, lists, bold,
italic and inline code, which is all those documents use, and sets them small
enough that a wide table fits a portrait page.

It is a build-time tool. It never ships, and it needs the `pymupdf` package,
which the backend's environment does not carry: run it with an interpreter
that has it (`pip install pymupdf`).

Usage::

    python packaging/md_to_pdf.py docs/NAME.md dist/customer/NAME.pdf
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

import pymupdf

_LIST_ITEM = re.compile(r"^(\d+\.|-)\s")
_TABLE_RULE = re.compile(r":?-+:?")
_BLOCK_START = re.compile(r"^(#|\||\d+\.\s|-\s)")

_CSS = """
body { font-family: sans-serif; font-size: 9.5pt; line-height: 1.35; color: #1b1f24; }
h1 { font-size: 17pt; margin: 0 0 8pt 0; }
h2 { font-size: 12.5pt; margin: 14pt 0 5pt 0; color: #0b3d91; }
p { margin: 0 0 6pt 0; }
table { border-collapse: collapse; width: 100%; margin: 4pt 0 8pt 0; }
th { background-color: #e8edf5; text-align: left; font-size: 8.5pt; padding: 3pt 4pt;
     border: 0.5pt solid #9aa5b5; }
td { font-size: 8.5pt; padding: 3pt 4pt; border: 0.5pt solid #c3cad6;
     vertical-align: top; }
code { font-family: monospace; font-size: 8.5pt; }
li { margin-bottom: 3pt; }
"""


def inline(text: str) -> str:
    """Return one line of Markdown as HTML: code, bold and italic."""
    text = html.escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    return re.sub(r"(?<![*\w])\*([^*]+)\*(?![*\w])", r"<i>\1</i>", text)


def to_html(lines: list[str]) -> str:
    """Return the document's lines as the HTML the page is set from."""
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
        elif line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            out.append(f"<h{level}>{inline(line[level:].strip())}</h{level}>")
            i += 1
        elif line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            body = [r for r in rows if not all(_TABLE_RULE.fullmatch(c) for c in r)]
            out.append("<table>")
            for n, row in enumerate(body):
                tag = "th" if n == 0 else "td"
                cells = "".join(f"<{tag}>{inline(c)}</{tag}>" for c in row)
                out.append(f"<tr>{cells}</tr>")
            out.append("</table>")
        elif _LIST_ITEM.match(line):
            ordered = line[0].isdigit()
            out.append("<ol>" if ordered else "<ul>")
            while i < len(lines) and (
                _LIST_ITEM.match(lines[i]) or lines[i].startswith("  ")
            ):
                if not _LIST_ITEM.match(lines[i]):
                    i += 1
                    continue
                item = _LIST_ITEM.sub("", lines[i], count=1).lstrip()
                i += 1
                # A wrapped item carries on, indented, on the lines below it.
                while i < len(lines) and lines[i].startswith("  ") and lines[i].strip():
                    item += " " + lines[i].strip()
                    i += 1
                out.append(f"<li>{inline(item)}</li>")
            out.append("</ol>" if ordered else "</ul>")
        else:
            para = line
            i += 1
            while (
                i < len(lines) and lines[i].strip() and not _BLOCK_START.match(lines[i])
            ):
                para += " " + lines[i].strip()
                i += 1
            out.append(f"<p>{inline(para)}</p>")
    return "".join(out)


def render(source: Path, target: Path) -> int:
    """Write `source` (Markdown) to `target` as an A4 PDF; return its pages."""
    story = pymupdf.Story(
        html=to_html(source.read_text(encoding="utf-8").splitlines()),
        user_css=_CSS,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    writer = pymupdf.DocumentWriter(str(target))
    page = pymupdf.paper_rect("a4")
    where = page + (42, 42, -42, -46)
    more, pages = 1, 0
    while more:
        device = writer.begin_page(page)
        more, _ = story.place(where)
        story.draw(device)
        writer.end_page()
        pages += 1
    writer.close()
    return pages


def main(argv: list[str]) -> int:
    """Command-line entry: source and target paths."""
    if len(argv) != 3:
        print("usage: md_to_pdf.py <source.md> <target.pdf>", file=sys.stderr)
        return 2
    target = Path(argv[2])
    print(f"{target} ({render(Path(argv[1]), target)} pages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

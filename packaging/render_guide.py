"""Render the customer installation guide to one self-contained HTML page.

`build_installer.ps1` runs this at staging time so that the guide reaches a
customer in the two places they look for it: beside `Setup.exe`, and in the
Start menu of an installed copy. The source of truth stays
`docs/INSTALL_GUIDE.md`, which is also what the repository's guard tests read;
this file only changes its shape.

It is a build-time tool. It never ships, and it needs the `markdown` package
from the `build` dependency group.

Usage::

    python packaging/render_guide.py docs/INSTALL_GUIDE.md "dist/guide.html"
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import markdown

#: Links between repository documents. Beside a customer's Setup.exe there is
#: no `RELEASE_BUILD.md` to link to, so the link text stays and the link goes.
_REPO_LINK = re.compile(r'<a href="[^"]*\.md(?:#[^"]*)?">(.*?)</a>')

_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  body {{ font-family: Segoe UI, system-ui, sans-serif; line-height: 1.5;
          max-width: 46rem; margin: 2rem auto; padding: 0 1rem; color: #1f2933; }}
  h1 {{ font-size: 1.9rem; }}
  h2 {{ font-size: 1.35rem; margin-top: 2.2rem; border-bottom: 1px solid #d9dee3;
        padding-bottom: .25rem; }}
  code {{ background: #f1f3f5; padding: .1rem .3rem; border-radius: 3px;
          font-size: .92em; }}
  pre {{ background: #f1f3f5; padding: .75rem; overflow-x: auto; }}
  pre code {{ background: none; padding: 0; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
  th, td {{ border: 1px solid #d9dee3; padding: .4rem .6rem; text-align: left;
            vertical-align: top; }}
  th {{ background: #f1f3f5; }}
  /* A checklist's last column is where a tester writes; give it room. */
  td:last-child {{ min-width: 9rem; }}
  hr {{ border: 0; border-top: 1px solid #d9dee3; margin: 2rem 0; }}
  @media print {{ body {{ max-width: none; margin: 0; }} }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def render(source: Path, target: Path) -> None:
    """Write `source` (Markdown) to `target` as a complete HTML page."""
    text = source.read_text(encoding="utf-8")
    body = markdown.markdown(text, extensions=["tables", "fenced_code"])
    body = _REPO_LINK.sub(r"\1", body)
    title_match = re.search(r"^# (.+)$", text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else source.stem
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_PAGE.format(title=title, body=body), encoding="utf-8")


def main(argv: list[str]) -> int:
    """Command-line entry: source and target paths."""
    if len(argv) != 3:
        print("usage: render_guide.py <source.md> <target.html>", file=sys.stderr)
        return 2
    render(Path(argv[1]), Path(argv[2]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

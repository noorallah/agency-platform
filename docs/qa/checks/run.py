"""Run every kept check of one module; print only failures and a tally.

    python docs/qa/checks/run.py goods_types            # every tc_*.py / d_*.py / p_*.py
    python docs/qa/checks/run.py goods_types tc_mast_02  # only names starting so

A ``setup*.py`` or ``_*.py`` file in the folder is not a check and is never run from here.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent


def main() -> int:
    """Run the module's checks one after another."""
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    folder = HERE / sys.argv[1]
    prefix = sys.argv[2] if len(sys.argv) > 2 else ""
    scripts = sorted(
        path
        for path in folder.glob("*.py")
        if not path.name.startswith("setup")
        and not path.name.startswith("_")
        and path.name.startswith(prefix)
    )
    if not scripts:
        print(f"no checks under {folder} matching {prefix!r}")
        return 2
    failed = 0
    for script in scripts:
        result = subprocess.run(  # noqa: S603 -- our own scripts
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=900,
            cwd=str(folder),
            env={**__import__("os").environ, "PYTHONPATH": str(HERE)},
            check=False,
        )
        if result.returncode != 0:
            failed += 1
            lines = (result.stdout + result.stderr).strip().splitlines()
            shown = [line for line in lines if line.startswith("FAIL")] or lines[-3:]
            for line in shown:
                print(line)
    print(f"{len(scripts) - failed} of {len(scripts)} checks clean, {failed} failing")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

"""Backlog 81: the firm form's state list is the geography masters' list.

The firm form is a platform screen, and the platform store holds no geography
tables, so the desktop carries the Indian states with their GST codes
(``desktop/lib/models/india_states.dart``). That is a second copy of what the
migration ``20260917_0137`` seeds into every firm store; this fails the build
when the two stop agreeing, which is the only way a second copy stays true.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_DART = _ROOT / "desktop" / "lib" / "models" / "india_states.dart"
_MIGRATION = (
    _ROOT
    / "backend"
    / "alembic"
    / "versions"
    / "20260917_0137_seed_the_india_state_master.py"
)


def _seeded() -> set[str]:
    """Return the state names the migration seeds into every store."""
    spec = importlib.util.spec_from_file_location("seed_states_0137", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {name for _, name in module._INDIAN_STATES}


def _offered() -> list[tuple[str, str]]:
    """Return ``(gst_code, name)`` pairs the desktop form offers."""
    text = _DART.read_text(encoding="utf-8")
    return re.findall(r"IndiaState\('(\d{2})', '([^']+)'\)", text)


def test_the_form_offers_exactly_the_seeded_states() -> None:
    """Every seeded state is offered, and nothing else."""
    offered = _offered()
    assert {name for _, name in offered} == _seeded()
    assert len(offered) == len(_seeded())


def test_each_state_has_one_distinct_gst_code() -> None:
    """The GST code is what proposes the state, so it must be unique."""
    codes = [code for code, _ in _offered()]
    assert len(codes) == len(set(codes))
    assert "25" not in codes, "25 is Daman and Diu, merged into 26"

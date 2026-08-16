"""Global search must point at a screen that exists.

Every ``SearchDefinition`` carries the module and tab the desktop should open
when somebody picks that result. Nothing checked that the tab was real, and one
was not: purchase orders named ``"purchases"``, which is the *module* id. No tab
has ever been called that, so opening a purchase order from Ctrl+K fell through
to whichever tab the shell defaults to -- the record the user searched for was
never shown, and the only symptom was landing on the wrong screen.

The tab ids live in the desktop's `ModuleCatalog`, which is Dart. Reading them
with a regex is coarse, but the alternative is a second copy of the list on this
side, which is the thing that let them drift apart to begin with. The test skips
rather than fails if the desktop tree is absent, so the backend suite still
stands on its own.
"""

# ruff: noqa: D103

import re
from pathlib import Path

import pytest

from app.search.services.search_service import _DEFINITIONS

_CATALOG = (
    Path(__file__).resolve().parents[3]
    / "desktop"
    / "lib"
    / "ui"
    / "workspace"
    / "module_catalog.dart"
)

#: `id: AppModule.purchases,` opens each module block.
_MODULE_ID = re.compile(r"id:\s*AppModule\.(\w+)\s*,")
#: `ModuleTabDefinition(id: 'purchase-orders', ...)`, however it is wrapped.
_TAB_ID = re.compile(r"ModuleTabDefinition\(\s*id:\s*'([^']+)'")
#: `purchaseTabAliases` keeps retired ids resolvable, so they count as real.
_ALIAS = re.compile(r"^\s*'([^']+)':\s*'[^']+',\s*$", re.MULTILINE)


def _tabs_by_module() -> dict[str, set[str]]:
    """Map each `AppModule` name to the tab ids declared under it.

    A module with no tabs maps to an empty set, which is different from being
    absent: the shell renders such a module directly and the search
    definition's tab is simply unused.
    """
    text = _CATALOG.read_text(encoding="utf-8")
    blocks = text.split("ModuleDefinition(")
    tabs: dict[str, set[str]] = {}
    for block in blocks[1:]:
        match = _MODULE_ID.search(block)
        if match is None:
            continue
        tabs[match.group(1)] = set(_TAB_ID.findall(block))
    aliases = text.split("purchaseTabAliases", 1)
    if len(aliases) == 2 and "purchases" in tabs:
        tabs["purchases"] |= set(_ALIAS.findall(aliases[1].split("};", 1)[0]))
    return tabs


@pytest.mark.skipif(not _CATALOG.exists(), reason="desktop tree not present")
def test_every_search_definition_names_a_real_tab() -> None:
    tabs = _tabs_by_module()
    assert tabs, "no modules parsed -- the catalog moved or its shape changed"

    unknown: dict[str, str] = {}
    for definition in _DEFINITIONS:
        declared = tabs.get(definition.module)
        # A module the catalog does not declare is a separate problem and is
        # covered below; a module with no tabs ignores the value entirely.
        if definition.tab is None or not declared:
            continue
        if definition.tab not in declared:
            unknown[definition.entity_type] = definition.tab
    assert not unknown, (
        "these search results open a tab their module does not have, so "
        f"picking one lands on the fallback screen: {unknown}"
    )


@pytest.mark.skipif(not _CATALOG.exists(), reason="desktop tree not present")
def test_every_search_definition_names_a_real_module() -> None:
    tabs = _tabs_by_module()
    unknown = {
        definition.entity_type: definition.module
        for definition in _DEFINITIONS
        if definition.module not in tabs
    }
    assert not unknown, f"search results pointing at no module at all: {unknown}"


@pytest.mark.skipif(not _CATALOG.exists(), reason="desktop tree not present")
def test_a_purchase_order_result_opens_the_purchase_order_list() -> None:
    """The defect this file was written for."""
    definition = next(
        item for item in _DEFINITIONS if item.entity_type == "purchase_orders"
    )
    assert definition.module == "purchases"
    assert definition.tab == "purchase-orders"

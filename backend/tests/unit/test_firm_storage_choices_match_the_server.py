"""The firm form offers exactly the storage options the server accepts.

Where a firm's data lives is decided once, by whoever sets the firm up, and
never again -- `FirmService.update` refuses any change to it because nothing
migrates a firm's rows between stores. So the moment to get it right is the
only moment there is, and until 2026-09-17 the screen asked for it as a **free
text box**: type SHARED, SCHEMA or DATABASE, exactly, or take a 422.

`FieldSpec.choices` renders a dropdown and says in its own docstring why a text
box backed by a server-side enum is wrong. This test is the half that keeps the
two lists the same afterwards -- a new deployment mode on the server that the
screen never offers is a feature nobody can reach, and a mode the screen offers
that the server dropped is a 422 with no clue in it.

It reads the Dart rather than trusting a copy, the same way
`test_desktop_preference_payloads_are_accepted.py` reads the keys the client
sends: a fixture that restates the list cannot see the two drifting apart.
"""

import re
from pathlib import Path

from app.core.database.config import DatabaseDialect
from app.core.tenancy.models import DeploymentMode

_SHELL = (
    Path(__file__).resolve().parents[3]
    / "desktop"
    / "lib"
    / "ui"
    / "desktop_shell.dart"
)


def _choices_for(field_key: str) -> list[str]:
    """Return the `choices:` list declared on one FieldSpec in the shell."""
    source = _SHELL.read_text(encoding="utf-8")
    # The key line, then the first `choices: [...]` after it. Anchoring on the
    # key rather than scanning the file keeps this honest when another field
    # gains choices of its own.
    start = source.index(f"key: '{field_key}'")
    block = source[start : start + 900]
    found = re.search(r"choices:\s*\[(.*?)\]", block, re.DOTALL)
    assert found is not None, (
        f"'{field_key}' declares no `choices:`, so it renders as a free text "
        "box. It is backed by a server-side enum: a typo there becomes a 422 "
        "rather than a validation message."
    )
    return re.findall(r"'([^']*)'", found.group(1))


def _labels_for(field_key: str) -> dict[str, str]:
    """Return the `choiceLabels:` map declared on one FieldSpec."""
    source = _SHELL.read_text(encoding="utf-8")
    start = source.index(f"key: '{field_key}'")
    block = source[start : start + 900]
    found = re.search(r"choiceLabels:\s*\{(.*?)\}", block, re.DOTALL)
    if found is None:
        return {}
    return dict(re.findall(r"'([^']*)':\s*'([^']*)'", found.group(1)))


def test_the_firm_form_offers_every_deployment_mode_and_no_others() -> None:
    """The dropdown and `DeploymentMode` name the same three things."""
    offered = _choices_for("deployment_mode")
    assert set(offered) == {mode.value for mode in DeploymentMode}, (
        f"The screen offers {sorted(offered)} and the server accepts "
        f"{sorted(mode.value for mode in DeploymentMode)}."
    )


def test_the_firm_form_offers_every_database_engine_and_no_others() -> None:
    """The same question for the engine, which is also a server-side enum."""
    offered = _choices_for("database_type")
    assert set(offered) == {dialect.value for dialect in DatabaseDialect}, (
        f"The screen offers {sorted(offered)} and the server accepts "
        f"{sorted(dialect.value for dialect in DatabaseDialect)}."
    )


def test_every_deployment_mode_is_named_in_words_rather_than_in_code() -> None:
    """A person choosing where their firm's data lives must not read jargon.

    SHARED, SCHEMA and DATABASE are three words about the server, offered to
    whoever is setting a firm up -- often the person installing this at the
    firm, who was told they would not need to understand any of it. Each mode
    needs a label, and a label that merely repeats the code is not one.
    """
    labels = _labels_for("deployment_mode")
    for mode in DeploymentMode:
        label = labels.get(mode.value, "")
        assert label, f"{mode.value} has no plain-language label."
        assert label.upper() != mode.value, (
            f"{mode.value}'s label is just the code again, which tells the "
            "reader nothing they did not already see."
        )

"""What backlog 89 removed stays removed.

Backlog 89 moved a product's behaviour from the firm's business profile to the
product's goods type, and deleted what the old design left behind: seventeen
feature codes, two columns that tied an extra field to a profile, two tables of
unit defaults and the functions, routes and screens that served them. A
clean-up nobody guards is undone by the first person who copies an old pattern
out of a migration or a dated doc, so the names are held here, each with one
line saying what answers in its place.

The files are read as text. Migrations are not read -- they must go on naming
what they dropped -- and neither are tests, some of which name an old code to
prove that nothing reads it any more.
"""

import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.business.models import AttributeDefinition, CategoryAttributeRule
from app.business.services import AttributeService
from app.core.database import all_models  # noqa: F401
from app.core.database.base import Base

_REPO_ROOT = Path(__file__).resolve().parents[3]

#: Where a removed name must not come back, and the files read there.
_TREES: tuple[tuple[str, str], ...] = (
    ("backend/app", "*.py"),
    ("backend/scripts", "*.py"),
    ("desktop/lib", "*.dart"),
)

#: A name removed outright -> what replaced it. Matched as a whole word.
_REMOVED: dict[str, str] = {
    # Feature codes withdrawn by `20261008_0353`.
    "BATCH_TRACKING": "the product's own `track_batch`, filled by its goods type",
    "EXPIRY_TRACKING": "the product's own `track_expiry`",
    "SERIAL_NUMBER": "the product's own `track_serial`",
    "SERIAL_TRACKING": "the product's own `track_serial`",
    "MANUFACTURING_DATE": "the product's own `track_manufacturing_date`",
    "SHELF_LIFE": "`shelf_life_days` on a product that tracks expiry",
    "QR_CODE": "a plain product field every firm has",
    "MULTIPLE_WAREHOUSES": "nothing: every firm may add a warehouse",
    "APPROVAL_WORKFLOW": "the firm's own stage and approval settings",
    "KITCHEN_MANAGEMENT": "nothing: no code was ever behind it",
    "PRESCRIPTION_REQUIRED": "nothing: no code was ever behind it",
    "PROJECT_MANAGEMENT": "nothing: no code was ever behind it",
    "RECIPE_MANAGEMENT": "nothing: no code was ever behind it",
    "SERVICE_CONTRACTS": "nothing: no code was ever behind it",
    # Extra fields no longer follow the profile (`20261008_0352`).
    "applicable_business_profile_id": "`firm_attribute_switches`, per firm",
    "applicableBusinessProfileId": "the firm's own switch on a shared field",
    # The profile's goods settings (`20261008_0353`).
    "inventory_tracking": "the goods types a firm uses",
    # Unit defaults by profile and industry (`20261008_0351`).
    "business_profile_uom_defaults": "`unit_sets`, copied onto a new product",
    "uom_industry_templates": "`unit_sets` and `unit_set_goods_types`",
    "BusinessProfileUomDefault": "`UnitSet`",
    "BusinessProfileUomDefaults": "the unit sets in the product metadata",
    "IndustryTemplate": "`UnitSet`",
    "IndustryTemplateRecord": "the unit set record",
    "ProfileUomDefaultsDialog": "the Unit Sets list under Set up",
    "businessProfileUomDefaults": "the unit sets in the product metadata",
    "firmUomDefaults": "the unit sets in the product metadata",
    "resolve_firm_profile_default": "`UnitSetService`, asked by the product save",
    "get_firm_profile_defaults": "the unit set routes",
    "upsert_profile_defaults": "the unit set routes",
    # Checks that asked the profile about a product.
    "_validate_feature_gated_fields": "`GoodsTypeService.starting_values`",
    "_assert_batch_features": "`product_tracking.assert_product_fields`",
    "with_barcode_feature": "nothing: a barcode needs no feature",
    # The menu answer now carries which tracking screens a firm needs.
    "activeBusinessModuleCodes": "`ApiClient.activeBusinessModules`",
}

#: Withdrawn codes that are also ordinary words (a serial prefix, a territory
#: level, an attribute key), so only their use as a feature is refused.
_WITHDRAWN_WORDS: tuple[str, ...] = ("BARCODE", "WARRANTY", "IMEI", "TERRITORY")

#: Route paths deleted with the tables behind them.
_ROUTES: dict[str, str] = {
    "/industry-templates": "`/api/v1/uom-framework/unit-sets`",
    "/profile-defaults": "the unit sets in the product metadata",
}

#: Tables `20261008_0351` dropped.
_DROPPED_TABLES: tuple[str, ...] = (
    "business_profile_uom_defaults",
    "uom_industry_templates",
)


def _files() -> Iterator[Path]:
    """Yield every source file a removed name must stay out of."""
    for tree, pattern in _TREES:
        root = _REPO_ROOT / tree
        assert root.is_dir(), f"{tree} is missing, so nothing would be read"
        yield from sorted(root.rglob(pattern))


def _hits(pattern: re.Pattern[str]) -> list[str]:
    """Return ``path:line`` for every line of the guarded trees that matches."""
    found: list[str] = []
    for path in _files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                found.append(f"{path.relative_to(_REPO_ROOT).as_posix()}:{number}")
    return found


def test_the_guard_reads_real_files() -> None:
    """Fail if a moved directory would leave every check passing on nothing."""
    counts = {
        tree: sum(1 for _ in (_REPO_ROOT / tree).rglob(pattern))
        for tree, pattern in _TREES
    }
    assert all(count > 20 for count in counts.values()), counts


@pytest.mark.parametrize("name", sorted(_REMOVED))
def test_a_removed_name_has_not_come_back(name: str) -> None:
    """Refuse a name backlog 89 deleted, and say what answers instead."""
    word = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])")
    found = _hits(word)
    assert not found, (
        f"{name} was removed by backlog 89; use {_REMOVED[name]}. "
        f"Found at {found[:5]}"
    )


@pytest.mark.parametrize("code", _WITHDRAWN_WORDS)
def test_a_withdrawn_word_is_not_used_as_a_feature(code: str) -> None:
    """Refuse a gate on a code the catalogue no longer holds."""
    gate = re.compile(
        rf"""(require_feature\(|feature\s*=|has_feature\(|hasFeature\()\s*"""
        rf"""["']{code}["']"""
    )
    found = _hits(gate)
    assert not found, (
        f"{code} is no longer a business feature (20261008_0353), so a gate "
        f"on it refuses every firm. Found at {found[:5]}"
    )


@pytest.mark.parametrize("path", sorted(_ROUTES))
def test_a_deleted_route_is_not_declared_or_called(path: str) -> None:
    """Refuse a route, or a desktop call to one, that went with its table."""
    found = _hits(re.compile(re.escape(path)))
    assert (
        not found
    ), f"{path} was deleted by backlog 89; use {_ROUTES[path]}. Found at {found[:5]}"


def test_the_dropped_tables_and_columns_are_not_mapped() -> None:
    """Refuse a model that maps what the migrations dropped."""
    for table in _DROPPED_TABLES:
        assert table not in Base.metadata.tables, table
    # An extra field is switched per firm; a rule names a goods type, a
    # customer group, a supplier type or a category, and never a profile.
    assert "applicable_business_profile_id" not in AttributeDefinition.__table__.c
    assert "business_profile_id" not in CategoryAttributeRule.__table__.c
    # The resolver was written again without the profile; this was its filter.
    assert not hasattr(AttributeService, "_profile_id")

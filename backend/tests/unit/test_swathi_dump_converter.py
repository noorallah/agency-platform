"""The Swathi dump converter reads a tiny synthetic dump into template files."""

import csv
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "swathi_dump_to_templates.py"

DUMP = """
CREATE TABLE `company` (
  `comp_id` int(11) DEFAULT NULL,
  `company` char(15) DEFAULT NULL
) ENGINE=InnoDB;
INSERT INTO `company` VALUES (1,' GENERAL'),(9,'DAN''ONE');
CREATE TABLE `codehead` (
  `nhead` int(11) DEFAULT NULL,
  `headname` varchar(20) DEFAULT NULL,
  `comp_id` int(11) DEFAULT NULL
) ENGINE=InnoDB;
INSERT INTO `codehead` VALUES (140,'DEXOLAC',9);
CREATE TABLE `beatman` (
  `bcode` int(11) DEFAULT NULL,
  `bname` char(30) DEFAULT NULL,
  `ctype` char(1) DEFAULT NULL
) ENGINE=InnoDB;
INSERT INTO `beatman` VALUES (1,'RETAIL','O'),(2,'MARKET, ROAD','B'),(3,'RAJU','S');
CREATE TABLE `acchead` (
  `hcode` int(11) DEFAULT NULL,
  `hname` varchar(30) DEFAULT NULL
) ENGINE=InnoDB;
INSERT INTO `acchead` VALUES (3,'EXPENSES   '),(8,'DEBTORS');
CREATE TABLE `codes` (
  `acode` int(11) DEFAULT NULL,
  `acname` varchar(50) DEFAULT NULL,
  `adr1` varchar(35) DEFAULT NULL,
  `hcode` int(11) DEFAULT NULL,
  `mcode` int(11) DEFAULT NULL,
  `ph` char(15) DEFAULT NULL,
  `tin` char(20) DEFAULT NULL,
  `dlone` char(25) DEFAULT NULL,
  `pin` int(11) DEFAULT NULL
) ENGINE=InnoDB;
INSERT INTO `codes` VALUES \
(100,'Shop \\'A\\'','1, Main',8,2,'98-76',NULL,'DL 55',560001),\
(101,'Shop B',NULL,28,0,NULL,'29ABCDE1234F1Z5','',0),\
(200,'Supplier',NULL,9,0,NULL,NULL,NULL,NULL),\
(300,'Rent',NULL,3,0,NULL,NULL,NULL,NULL);
""".replace(
    "\\\n", ""
)


@pytest.fixture(scope="module")
def module() -> ModuleType:
    """Load the script by path; ``scripts/`` is not a package."""
    spec = importlib.util.spec_from_file_location("swathi_converter", SCRIPT)
    assert spec and spec.loader
    loaded = importlib.util.module_from_spec(spec)
    sys.modules["swathi_converter"] = loaded
    spec.loader.exec_module(loaded)
    return loaded


def _read(path: Path) -> list[dict[str, str]]:
    """Read a written CSV back."""
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def test_every_kind_is_written_and_split_by_head(
    module: ModuleType, tmp_path: Path
) -> None:
    """Customers, suppliers and accounts come from their heads, and no other."""
    dump = tmp_path / "d.sql"
    dump.write_text(DUMP, encoding="utf-8")
    counts = module.convert(dump, tmp_path / "out")
    assert counts == {
        "principals.csv": 2,
        "brands.csv": 1,
        "routes.csv": 1,
        "salesmen.csv": 1,
        "customers.csv": 2,
        "suppliers.csv": 1,
        "ledger_accounts.csv": 1,
    }


def test_values_are_unescaped_and_linked(module: ModuleType, tmp_path: Path) -> None:
    """Escaped quotes read back, a beat links by code, a licence is carried."""
    dump = tmp_path / "d.sql"
    dump.write_text(DUMP, encoding="utf-8")
    module.convert(dump, tmp_path / "out")
    customers = _read(tmp_path / "out" / "customers.csv")
    assert customers[0]["Name"] == "Shop 'A'"
    assert customers[0]["Beat"] == "BEAT2"
    assert customers[0]["LicenceNumber"] == "DL 55"
    assert customers[0]["Phone"] == "9876"
    assert customers[1]["Beat"] == ""
    assert customers[1]["PIN"] == ""
    assert customers[1]["LicenceType"] == ""
    brand = _read(tmp_path / "out" / "brands.csv")[0]
    assert brand["Company"] == "CO9"
    account = _read(tmp_path / "out" / "ledger_accounts.csv")[0]
    assert account["Group"] == "EXPENSES"
    principals = _read(tmp_path / "out" / "principals.csv")
    assert principals[1]["Name"] == "DAN'ONE"


def test_state_is_written_and_blank_group_is_named(
    module: ModuleType, tmp_path: Path
) -> None:
    """A given state fills every party row; a blank head gets a mappable name."""
    dump = tmp_path / "d.sql"
    dump.write_text(DUMP, encoding="utf-8")
    module.convert(dump, tmp_path / "out", "Andhra Pradesh")
    for name in ("customers.csv", "suppliers.csv"):
        rows = _read(tmp_path / "out" / name)
        assert {r["State"] for r in rows} == {"Andhra Pradesh"}
    assert all(r["Group"] for r in _read(tmp_path / "out" / "ledger_accounts.csv"))


def test_pl_income_heads_get_their_own_group(module: ModuleType) -> None:
    """An income-looking head under P & L ACCOUNTS is split from the expenses."""
    tables = {
        "acchead": [{"hcode": 5, "hname": "P & L ACCOUNTS"}],
        "codes": [
            {"hcode": 5, "acode": 1, "acname": "INTEREST RECEIVED"},
            {"hcode": 5, "acode": 2, "acname": "BANK CHARGES"},
            {"hcode": 99, "acode": 3, "acname": "ODD"},
        ],
    }
    rows = module.ledger_accounts(tables)
    assert [r["Group"] for r in rows][:2] == [
        "P & L ACCOUNTS (INCOME)",
        "P & L ACCOUNTS",
    ]

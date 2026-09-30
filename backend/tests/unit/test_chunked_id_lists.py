"""Large id lists are asked about in chunks (backlog 56 C).

The PostgreSQL driver refuses a statement with more than 65,535 parameters,
and two years of a mid-size distributor's invoices is more than that. These
force a chunk of one, so the ordinary report tests run through the chunked
path and must give exactly the same answers.
"""

from uuid import uuid4

import pytest

from app.core.utils import chunks as chunk_module
from app.core.utils.chunks import chunks, over_chunks
from tests.unit import test_customer_statement, test_gst_returns


def test_chunks_splits_and_drops_repeats() -> None:
    """Every id once, in order, no chunk larger than asked."""
    ids = [uuid4() for _ in range(5)]
    assert list(chunks([*ids, ids[0]], size=2)) == [ids[0:2], ids[2:4], ids[4:5]]


def test_over_chunks_merges_dicts_and_sets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Positional or keyword, a dict answer is updated and a set one united."""
    monkeypatch.setattr(chunk_module, "CHUNK_SIZE", 2)
    calls: list[int] = []

    @over_chunks("ids")
    def as_dict(prefix: str, ids: list[int]) -> dict[int, str]:
        """Answer per id."""
        calls.append(len(ids))
        return {item: f"{prefix}{item}" for item in ids}

    @over_chunks("ids")
    def as_set(*, ids: list[int]) -> set[int]:
        """Answer which ids are even."""
        return {item for item in ids if item % 2 == 0}

    assert as_dict("n", [1, 2, 3, 4, 5]) == {i: f"n{i}" for i in range(1, 6)}
    assert calls == [2, 2, 1]
    assert as_set(ids=[1, 2, 3, 4, 5, 6]) == {2, 4, 6}


def test_gstr1_reads_the_same_in_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    """GSTR-1's HSN summary over two invoices, read one id at a time."""
    monkeypatch.setattr(chunk_module, "CHUNK_SIZE", 1)
    test_gst_returns.test_the_hsn_summary_adds_up_to_the_supplies()
    test_gst_returns.test_the_hsn_summary_is_net_of_credit_notes_and_returns()


def test_the_ageing_reads_the_same_in_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    """What is owed per bill, read one bill at a time, ages the same."""
    monkeypatch.setattr(chunk_module, "CHUNK_SIZE", 1)
    test_customer_statement.test_the_ageing_ages_what_record_receipt_says_is_owed()
    test_customer_statement.test_the_ageing_row_reconciles_with_the_account()

"""Large id lists are asked about in chunks (backlog 56 C).

The PostgreSQL driver refuses a statement with more than 65,535 parameters,
and two years of a mid-size distributor's invoices is more than that. These
force a chunk of one, so the ordinary report tests run through the chunked
path and must give exactly the same answers.
"""

from uuid import uuid4

import pytest

from app.core.utils import chunks as chunk_module
from app.core.utils.chunks import chunks, over_chunks, whole_past_a_chunk
from tests.unit import (
    test_commission,
    test_customer_statement,
    test_delivery_note_module,
    test_document_summaries_in_sql,
    test_gst_returns,
    test_settlements,
)


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


def test_whole_past_a_chunk_asks_once_and_keeps_what_was_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Up to a chunk the ids are passed on; past one, None, and the answer is cut."""
    monkeypatch.setattr(chunk_module, "CHUNK_SIZE", 2)
    asked: list[list[int] | None] = []

    @whole_past_a_chunk("ids")
    def doubled(ids: list[int] | None) -> dict[int, int]:
        """Answer per id; None means every id there is."""
        asked.append(ids)
        return {item: item * 2 for item in (range(10) if ids is None else ids)}

    assert doubled([1, 2]) == {1: 2, 2: 4}
    assert doubled(ids=[3, 5, 7]) == {3: 6, 5: 10, 7: 14}
    assert asked == [[1, 2], None]


def test_what_a_bill_owes_reads_the_same_past_a_chunk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Receipts, returns and credit notes come off a bill the same either way."""
    monkeypatch.setattr(chunk_module, "CHUNK_SIZE", 1)
    test_settlements.test_returns_and_credit_notes_against_a_bill_come_off_what_it_owes()
    test_settlements.test_what_an_invoice_still_owes_comes_down_as_it_is_settled()


def test_commission_reads_the_same_past_a_chunk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A credit note comes off the commission base the same either way."""
    monkeypatch.setattr(chunk_module, "CHUNK_SIZE", 1)
    test_commission.test_a_credit_note_takes_the_sale_off_what_was_collected()
    test_commission.test_a_credit_note_takes_the_sale_off_what_was_invoiced()


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


def test_the_delivery_reports_read_the_same_in_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The delivery-note page summary sent every order id in one statement.

    Found timing PERF01 (109,566 orders): the summary answered 503. Its order
    lines and what was delivered against them are now read in chunks.
    """
    monkeypatch.setattr(chunk_module, "CHUNK_SIZE", 1)
    test_delivery_note_module.test_the_delivery_reports_count_what_left_the_warehouse()
    test_document_summaries_in_sql.test_delivery_note_summary()

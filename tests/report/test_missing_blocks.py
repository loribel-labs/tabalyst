# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The blocks of columns missing together and the dataset card of report.html
(docs/dev/report/chart-pages.md 6.1 and 6.2), read from a MissingPatternsResult alone."""

from __future__ import annotations

import time
from types import SimpleNamespace

from tabalyst.report_insights import MAX_BLOCKS, dataset_insights, missing_blocks
from tabalyst.scanner.secondpass.models import (
    MissingColumn,
    MissingPattern,
    MissingPatternsResult,
)


def _result(
    records: int,
    patterns: dict[tuple[str, ...], int],
    *,
    complete: bool = True,
    other: tuple[int, int] = (0, 0),
    untracked: int = 0,
) -> MissingPatternsResult:
    """A result whose columns and counts follow from ``patterns``, as the second
    pass writes them: each column's missing is the sum of the combinations holding it."""
    names = sorted({name for pattern in patterns for name in pattern})
    missing = {name: sum(count for pattern, count in patterns.items() if name in pattern) for name in names}
    lacking = sum(patterns.values()) + other[1] + untracked
    listed = sorted(patterns.items(), key=lambda item: (-item[1], len(item[0])))
    return MissingPatternsResult(
        records=records,
        columns=[MissingColumn(field=name, display=name.upper(), missing=missing[name]) for name in names],
        complete_records=records - lacking,
        distinct=len(patterns) + other[0] + (1 if untracked else 0),
        complete=complete,
        untracked=untracked,
        listed=[MissingPattern(columns=list(pattern), count=count) for pattern, count in listed],
        other_patterns=other[0],
        other_records=other[1],
    )


def _blocks(result: MissingPatternsResult) -> list[tuple[str, ...]]:
    return [block.fields for block in missing_blocks(result)]


def test_columns_that_lack_values_in_the_same_records_form_a_block():
    result = _result(10_000, {("a", "b", "c"): 900, ("a",): 50, ("d",): 400})

    (block,) = missing_blocks(result)

    assert block.fields == ("a", "b", "c")
    assert block.displays == ("A", "B", "C")
    assert block.records == 900
    assert block.share == 900 / 950
    assert block.exact


def test_only_the_largest_block_is_named_not_its_subsets():
    result = _result(10_000, {("a", "b", "c"): 900, ("a", "b"): 100})

    assert _blocks(result) == [("a", "b", "c")]


def test_a_column_missing_alone_too_often_is_not_in_the_block():
    # c lacks a value in 900 records with a and b, and in 400 more on its own: 69%.
    result = _result(10_000, {("a", "b", "c"): 900, ("c",): 400})

    assert _blocks(result) == [("a", "b")]


def test_a_rare_coincidence_is_not_a_block():
    # 99 records of 10,000 is under 1%.
    result = _result(10_000, {("a", "b"): 99})

    assert _blocks(result) == []
    assert _blocks(_result(10_000, {("a", "b"): 100})) == [("a", "b")]


def test_blocks_come_by_decreasing_records_and_at_most_five():
    patterns = {(f"x{n}", f"y{n}"): 200 + n for n in range(MAX_BLOCKS + 2)}

    blocks = missing_blocks(_result(10_000, patterns))

    assert len(blocks) == MAX_BLOCKS
    assert [block.records for block in blocks] == sorted((200 + n for n in range(2, MAX_BLOCKS + 2)), reverse=True)


def test_combinations_that_share_a_column_join_in_one_block_or_none():
    result = _result(10_000, {("a", "b"): 500, ("b", "c"): 500, ("a", "b", "c"): 4_000})

    assert _blocks(result) == [("a", "b", "c")]
    result = _result(10_000, {("a", "b"): 3_000, ("b", "c"): 3_000})
    # b lacks a value in 6,000 records, each pair holds half of them: no block.
    assert _blocks(result) == []


def test_a_listing_that_misses_combinations_gives_a_lower_bound():
    result = _result(10_000, {("a", "b"): 800}, other=(3, 20))

    (block,) = missing_blocks(result)

    assert not block.exact
    card = _card(result)
    (line,) = card.lines
    assert line.kind == "at_least"
    assert "at least 800 records lack both" in "".join(part.text for part in line.parts)


def test_a_wide_block_is_found_without_going_through_its_subsets():
    columns = tuple(f"c{n:02d}" for n in range(60))
    result = _result(100_000, {columns: 30_000, columns[:30]: 500, (columns[0],): 200})

    start = time.perf_counter()
    blocks = missing_blocks(result)

    assert time.perf_counter() - start < 1.0
    assert [len(block.fields) for block in blocks] == [60]


def _card(result: MissingPatternsResult, exposure: dict[str, str | None] | None = None):
    # dataset_insights reads these members of an analysis of the second pass only.
    item = SimpleNamespace(
        analyzer="missing_patterns",
        dataset="d",
        field="$",
        partner=None,
        display="d",
        status="complete",
        result=result,
    )
    analyses = SimpleNamespace(deep=SimpleNamespace(analyses=[item]))
    cards = dataset_insights(analyses, "d", exposure or {})
    return next((card for card in cards if card.family == "missing"), None)


def test_the_dataset_card_names_the_blocks_and_lists_the_combinations():
    result = _result(10_000, {("a", "b", "c"): 900, ("a",): 50, ("d",): 400})

    card = _card(result)

    assert card is not None and card.scope == "dataset"
    assert card.summary == "1,350 of the 10,000 records lack a value in at least one of 4 columns."
    (line,) = card.lines
    assert [part.text for part in line.parts if part.code] == ["A", "B", "C"]
    text = "".join(part.text for part in line.parts)
    assert text == (
        "A, B and C go missing together: 900 records lack all three, at least 94.7% of "
        "the records that lack any one of them."
    )
    facts = {fact.label: fact.value for fact in card.facts}
    assert facts["Records with every value"] == "8,650 (86.5%)"
    assert facts["Combinations"] == "3"
    (table,) = card.tables
    assert table.rows[0] == ["A, B, C", "3", "900", "9.0%"]
    assert table.note is None


def test_the_card_says_what_the_listing_leaves_out():
    result = _result(10_000, {("a", "b"): 800}, complete=False, other=(3, 20), untracked=7)

    card = _card(result)

    facts = {fact.label: fact for fact in card.facts}
    assert facts["Combinations"].kind == "at_least"
    note = card.tables[0].note
    assert "3 rarer combinations (20 records) are counted but not listed." in note
    assert "7 records lack values in combinations found after the tracked ones" in note


def test_a_report_that_withholds_a_member_shows_no_combination():
    result = _result(10_000, {("a", "b"): 800})

    assert _card(result, {"a": "hide"}) is None

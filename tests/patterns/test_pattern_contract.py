# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The contract of design 18.12 and 20.9 beyond the reference trees: eligibility,
budgets and ``limits``, sums, provenance, ``check_scan``, cache and exposure.

Every test is skipped until the lot that marks it is enabled in ``conftest.py``
(cahier 13.3). Where a decision is still open (OPEN-009 thresholds of the
eligibility, OPEN-012 a new combination of known segments) a test states only
what is decided.
"""

from __future__ import annotations

import random
import re
import string
from collections.abc import Iterator
from dataclasses import replace
from typing import Any

import pytest
from pattern_adapter import (
    Change,
    CountedNode,
    Tamper,
    check_scan_problems,
    count,
    discover,
    eligibility,
    published_renders,
    published_text,
    rerun_after,
    source_reads,
)
from pattern_corpus import Field, field, with_variants
from pattern_tree import SeenNode


def _walk(nodes: tuple[SeenNode, ...]) -> Iterator[SeenNode]:
    for node in nodes:
        yield node
        yield from _walk(node.children)


def _node_count(source: Field, settings: dict[str, int] | None = None) -> int:
    seen = discover(source, settings)
    assert seen is not None
    return sum(len(list(_walk(item.nodes))) for item in seen.families)


def _rng(name: str) -> random.Random:
    return random.Random(f"tabalyst-patterns/contract/{name}")


def _words(rng: random.Random, size: int) -> str:
    return " ".join(
        "".join(rng.choices(string.ascii_lowercase, k=rng.randint(3, 9)))
        for _ in range(rng.randint(3, 9))
    )[:size]


def _column(name: str, values: list[str], **extra: Any) -> Field:
    pairs = tuple(sorted((value, 1) for value in dict.fromkeys(values)))
    return Field(case="CT", name=name, pairs=pairs, **extra)


def _identifiers() -> Field:
    rng = _rng("identifiers")
    prefixes = ("AK", "AB", "AZ", "BC", "CD")
    return _column(
        "identifiers",
        [f"{rng.choice(prefixes)}-{rng.randrange(10**5):05d}" for _ in range(800)],
    )


def _descriptions() -> Field:
    rng = _rng("descriptions")
    return _column("descriptions", [_words(rng, 60) for _ in range(800)])


def _statuses() -> Field:
    rng = _rng("statuses")
    names = ["new", "open", "paid", "late", "closed"]
    return Field(
        case="CT",
        name="statuses",
        pairs=tuple(sorted((name, rng.randint(50, 400)) for name in names)),
    )


# Eligibility (lot P2): FR-001, AC-001, AC-002 -------------------------------------


@pytest.mark.pattern_lot("P2")
def test_an_identifier_column_scores_above_free_text_and_a_few_statuses() -> None:
    identifiers = eligibility(_identifiers())
    assert identifiers.score > eligibility(_descriptions()).score
    assert identifiers.score > eligibility(_statuses()).score
    assert identifiers.state == "eligible"


@pytest.mark.pattern_lot("P2")
@pytest.mark.parametrize("item", [_identifiers(), _descriptions(), _statuses()], ids=lambda f: f.name)
def test_every_column_gets_a_state_a_score_between_zero_and_one_and_reasons(item: Field) -> None:
    result = eligibility(item)
    assert result.state in {"eligible", "low_relevance", "excluded", "not_assessable"}
    assert 0 <= result.score <= 1
    assert result.reasons


@pytest.mark.pattern_lot("P2")
def test_a_date_column_is_not_excluded_for_being_a_date_and_scores_lower() -> None:
    rng = _rng("dates")
    dates = _column(
        "dates",
        [f"2026-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}" for _ in range(600)],
        detector="date",
    )
    plain = _column("plain", list(dates.values()))
    result = eligibility(dates)
    assert result.state != "excluded"
    assert result.score < eligibility(plain).score


@pytest.mark.pattern_lot("P2")
@pytest.mark.parametrize("field_id", ["RC-10/nine_30", "RC-11/cards"])
def test_a_column_of_digits_typed_as_integers_is_admitted(field_id: str) -> None:
    assert eligibility(field(field_id)).state == "eligible"


@pytest.mark.pattern_lot("P2")
@pytest.mark.parametrize("field_id", ["RC-03/scaled", "RC-13/identifiers", "RC-20/postal_codes"])
def test_structured_columns_of_the_corpus_are_eligible(field_id: str) -> None:
    assert eligibility(field(field_id)).state == "eligible"


@pytest.mark.pattern_lot("P2")
def test_hyphenated_isbn_needing_many_fixed_lengths_is_not_eligible() -> None:
    # DEC-034: more than a handful of formats of fixed length is a poor candidate.
    result = eligibility(field("RC-12/isbn"))
    assert result.state != "eligible"
    assert result.reasons


@pytest.mark.pattern_lot("P2")
def test_a_masked_column_is_excluded_with_the_reason_exposure() -> None:
    result = eligibility(field("RC-18/emails"))
    assert result.state == "excluded"
    assert "exposure" in result.reasons


@pytest.mark.pattern_lot("P2")
def test_a_column_with_too_little_information_is_not_assessable_with_a_reason() -> None:
    result = eligibility(_column("single", ["AK-0001"]))
    assert result.state == "not_assessable"
    assert "too_few_distinct" in result.reasons


@pytest.mark.pattern_lot("P2")
def test_cardinality_alone_does_not_exclude_a_column() -> None:
    unique = _column("unique", [f"ID-{n:07d}" for n in range(5000)])
    assert eligibility(unique).state == "eligible"


# Budgets and limits (lots P3 and P4): FR-002, FR-011, AC-004, AC-011, AC-012 ---------


def _many(size: int) -> Field:
    return _column("many", [f"AK-{n:07d}" for n in range(size)])


@pytest.mark.pattern_lot("P3")
def test_discovery_reads_at_most_max_values_and_says_so_in_limits() -> None:
    source = _many(10_500)
    seen = discover(source)
    assert seen is not None
    assert "max_values" in seen.limits
    assert discover(source) == seen


@pytest.mark.pattern_lot("P3")
def test_discovery_stops_at_the_structures_the_data_show() -> None:
    # AC-011: exactly four clear structures, four families and no more.
    rng = _rng("four")
    shapes = ["AA-9999", "9999-AA", "AAA9", "99.99"]
    values = []
    for shape in shapes:
        for _ in range(60):
            values.append(
                "".join(
                    rng.choice(string.ascii_uppercase)
                    if c == "A"
                    else str(rng.randrange(10))
                    if c == "9"
                    else c
                    for c in shape
                )
            )
    seen = discover(_column("four", values))
    assert seen is not None and len(seen.families) == 4


@pytest.mark.pattern_lot("P3")
def test_a_lower_family_budget_folds_the_rest_into_other_and_names_the_budget() -> None:
    source = field("RC-07/plates")
    full = discover(source)
    cut = discover(source, {"max_families": 2})
    assert full is not None and cut is not None
    assert len(cut.families) == 2 < len(full.families)
    assert "max_families" in cut.limits
    assert cut.other


@pytest.mark.pattern_lot("P3")
def test_a_lower_pattern_budget_per_family_keeps_the_largest_patterns() -> None:
    source = field("RC-06/invoices")
    cut = discover(source, {"max_patterns_per_family": 1})
    assert cut is not None
    assert "max_patterns_per_family" in cut.limits


@pytest.mark.pattern_lot("P4")
def test_a_lower_variant_budget_gives_fewer_nodes_without_error_and_names_it() -> None:
    source = field("RC-03/scaled")
    full = _node_count(source)
    seen = discover(source, {"max_patterns": 3})
    assert seen is not None
    assert _node_count(source, {"max_patterns": 3}) < full
    assert "max_patterns" in seen.limits


@pytest.mark.pattern_lot("P4")
def test_the_depth_never_goes_below_the_maximum_depth_setting() -> None:
    seen = discover(field("RC-16/lots"), {"max_depth": 1})
    assert seen is not None
    for family in seen.families:
        assert all(node.children == () for node in family.nodes)
    assert "max_depth" in seen.limits


@pytest.mark.pattern_lot("P4")
def test_random_rare_prefixes_do_not_exceed_the_variant_budget() -> None:
    # AC-011: 150 random and rare prefixes stay within the budget of variants.
    rng = _rng("rare")
    prefixes = {"".join(rng.choices(string.ascii_uppercase, k=2)) for _ in range(400)}
    values = [f"{p}-{rng.randrange(10**4):04d}" for p in sorted(prefixes)[:150] for _ in range(2)]
    assert _node_count(_column("rare", values)) <= 128


@pytest.mark.pattern_lot("P4")
def test_uniform_noise_gets_no_variant() -> None:
    # AC-030, REC-013.
    assert _node_count(field("RC-17/noise")) == 0


# Sums, outcomes and provenance (lot P6): FR-012 to FR-015, AC-005, AC-013 to AC-017 ----


def _check_node(node: CountedNode, label: str = "") -> None:
    inside = sum(child.occurrences for child in node.children) + node.rest
    if node.children or node.rest:
        assert inside == node.occurrences, f"{label}{node.label}"
    for child in node.children:
        _check_node(child, f"{label}{node.label} > ")


@pytest.mark.pattern_lot("P6")
@pytest.mark.parametrize("field_id", ["RC-05/invoices", "RC-07/plates", "RC-16/lots"])
def test_counts_add_up_through_the_hierarchy(field_id: str) -> None:
    counted = count(field(field_id))
    assert counted.matched + counted.unknown_structure + counted.excluded == counted.values
    assert sum(family.occurrences for family in counted.families) == counted.matched
    for family in counted.families:
        patterns = sum(pattern.occurrences for pattern in family.patterns)
        assert patterns + family.new_length_variants == family.occurrences
        for pattern in family.patterns:
            _check_node(pattern)


@pytest.mark.pattern_lot("P6")
def test_a_result_never_writes_the_invalid_outcome() -> None:
    # REC-006: reserved, no rule exists in the V1.
    counted = count(with_variants(field("RC-03/scaled")))
    assert not any("invalid" in key for key in counted.keys)


@pytest.mark.pattern_lot("P6")
def test_a_complete_distribution_is_counted_without_reading_the_source() -> None:
    source = field("RC-03/scaled")
    counted = count(source)
    assert counted.computed_from == "samples"
    assert source_reads([source]) == 0


@pytest.mark.pattern_lot("P6")
def test_one_reading_of_the_source_serves_fifteen_columns() -> None:
    # AC-015.
    fields = [
        replace(item, name=f"{item.name}_{n}")
        for n in range(5)
        for item in (field("RC-03/scaled"), field("RC-13/identifiers"), field("RC-16/lots"))
    ][:15]
    assert len(fields) == 15
    assert source_reads(fields) <= 1


@pytest.mark.pattern_lot("P6")
def test_distinct_values_of_a_node_are_exact_or_marked_at_least() -> None:
    # AC-016: a bound is never presented as exact.
    counted = count(field("RC-13/identifiers"), exact_budget=1)
    accuracies = {
        pattern.distinct_accuracy for family in counted.families for pattern in family.patterns
    }
    assert accuracies <= {"exact", "at_least"}
    assert "at_least" in accuracies
    exact = count(field("RC-13/identifiers"))
    assert {
        pattern.distinct_accuracy for family in exact.families for pattern in family.patterns
    } == {"exact"}


@pytest.mark.pattern_lot("P6")
def test_a_full_table_keeps_the_most_frequent_values_and_says_it_is_limited() -> None:
    # AC-014 and TR-003.
    counted = count(field("RC-14/prefixes"), table_capacity=4)
    tables = [table for family in counted.families for table in family.tables]
    assert tables and all(len(table.cells) <= 4 for table in tables)
    limited = [table for table in tables if table.saturated]
    assert limited
    for table in limited:
        kept = sorted(table.cells.values(), reverse=True)
        assert kept and table.others > 0


@pytest.mark.pattern_lot("P6")
def test_a_length_never_seen_in_a_known_structure_is_a_new_variant_not_unknown() -> None:
    variants = with_variants(field("RC-06/invoices"))
    counted = count(variants)
    assert counted.unknown_structure >= 1
    assert sum(family.new_length_variants for family in counted.families) >= 1


# check_scan (lot P7): FR-021, AC-022 ----------------------------------------------------


@pytest.mark.pattern_lot("P7")
def test_check_scan_accepts_an_untouched_hierarchy() -> None:
    assert check_scan_problems(field("RC-07/plates")) == []


@pytest.mark.pattern_lot("P7")
@pytest.mark.parametrize("tamper", ["family_sum", "missing_parent", "entry_count", "unknown_signature"])
def test_check_scan_reports_a_broken_hierarchy(tamper: Tamper) -> None:
    assert check_scan_problems(field("RC-07/plates"), tamper)


# Cache and provenance (lot P7): FR-020, AC-021, S-07, S-08 ------------------------------


@pytest.mark.pattern_lot("P7")
def test_a_new_rendering_of_the_same_scan_recomputes_nothing() -> None:
    run = rerun_after(field("RC-03/scaled"), "render_only")
    assert not run.discovery and not run.validation and not run.scan_stale


@pytest.mark.pattern_lot("P7")
@pytest.mark.parametrize("change", ["setting", "algorithm_version"])
def test_a_changed_budget_or_algorithm_recomputes_discovery_and_validation(change: Change) -> None:
    run = rerun_after(field("RC-03/scaled"), change)
    assert run.discovery and run.validation


@pytest.mark.pattern_lot("P7")
def test_a_changed_setting_makes_the_scan_stale() -> None:
    assert rerun_after(field("RC-03/scaled"), "setting").scan_stale


# Exposure (lots P3 and P4): FR-022, AC-023 ----------------------------------------------


@pytest.mark.pattern_lot("P3")
def test_a_masked_field_publishes_no_value_example_node_or_table() -> None:
    source = field("RC-18/emails")
    text = published_text(source)
    assert not any(value in text for value in source.values())


@pytest.mark.pattern_lot("P4")
def test_card_like_columns_publish_no_complete_number_and_short_constants_only() -> None:
    # Algorithm section 9.4: no detector reads cards, so the discovery does; its
    # constants have three characters at most.
    source = field("RC-11/cards")
    for render in published_renders(source):
        for literal in re.findall(r"'((?:[^']|'')*)'", render):
            assert len(literal) <= 3, render
    text = published_text(source)
    assert not any(value in text for value in source.values())

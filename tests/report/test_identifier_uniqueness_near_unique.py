# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Near-uniqueness (UID-014, contract 14): a non-binding reading of the residual repetitions."""

import json
import re
from math import isqrt

import pytest
from identifier_uniqueness_helpers import (
    assess,
    facts,
    population,
    uniqueness_of,
    write_csv,
)

from tabalyst import generate_reports
from tabalyst.identifier_uniqueness import (
    assess_identifier_uniqueness,
    assess_near_unique,
)
from tabalyst.identifier_uniqueness.near_unique import tolerance
from tabalyst.report_uniqueness import uniqueness_view

pytestmark = pytest.mark.uid_lot("9")


def _near(n: int, residual: int, copies: int = 0):
    """The near-unique member for ``n`` records, ``residual`` shared IDs and ``copies`` copies."""
    return assess(n=n, d=n - copies - residual, e=copies)["near_unique"]


@pytest.mark.parametrize(
    ("distinct_rows", "expected", "bound"),
    [
        (100, 1, "relative"),
        (1_000, 10, "relative"),
        (10_000, 100, "relative"),
        (100_000, 316, "root"),
        (1_000_000, 1_000, "root"),
        (1_000_001, 1_000, "root"),
        (4_000_000, 1_000, "cap"),
    ],
)
def test_the_tolerance_is_the_smallest_of_the_three_terms(distinct_rows, expected, bound):
    assert tolerance(distinct_rows) == (expected, bound)


def test_the_tolerance_never_decreases_and_stays_within_its_three_terms():
    previous = 0
    for u in list(range(100, 3_000)) + [10**4, 10**5, 10**6, 10**7, 10**9]:
        value, _ = tolerance(u)
        assert value >= previous
        assert 1 <= value <= min(u // 100, isqrt(u), 1_000)
        previous = value


def test_a_few_repetitions_among_many_records_are_near_unique():
    near = _near(1_000, 10)

    assert near["signal"] == "near_unique"
    assert (near["residual_repetitions"], near["distinct_records"]) == (10, 1_000)
    assert (near["tolerance"], near["limiting_bound"]) == (10, "relative")
    assert near["model_version"] == 1


def test_one_repetition_more_than_the_tolerance_is_not_near_unique():
    assert _near(1_000, 11)["signal"] == "not_near_unique"
    assert _near(10_000, 100)["signal"] == "near_unique"
    assert _near(10_000, 101)["signal"] == "not_near_unique"


def test_a_share_alone_does_not_decide_the_same_share_of_a_million_is_far_from_near_unique():
    # 1% of 10,000 records is near-unique, 1% of a million is ten times the absolute cap.
    assert _near(10_000, 100)["signal"] == "near_unique"
    assert _near(1_000_000, 10_000)["signal"] == "not_near_unique"
    assert _near(1_000_000, 1_000)["signal"] == "near_unique"


def test_the_copies_of_rows_are_not_counted_against_the_tolerance():
    # U = N - E: 500 explained repetitions leave 1,000 records of 10 residual ones.
    near = _near(1_510, 10, copies=500)

    assert near["distinct_records"] == 1_010
    assert near["tolerance"] == 10
    assert near["signal"] == "near_unique"


def test_fewer_than_a_hundred_distinct_records_give_no_verdict():
    near = _near(99, 1)

    assert near["signal"] == "population_too_small"
    assert (near["tolerance"], near["limiting_bound"]) == (0, None)
    assert _near(100, 1)["signal"] == "near_unique"


@pytest.mark.parametrize(
    "options",
    [
        {"n": 1_000, "d": 1_000, "e": 0},  # raw unique ID
        {"n": 1_000, "d": 995, "e": 5},  # unique after row deduplication
        {"n": 1_000, "d": 990, "present": 995, "e": 0},  # missing IDs
        {"n": 1_000, "d": 980, "e": None},  # no duplicate count at all
        {"n": 1_000, "d": 980, "e": 1, "duplicate_accuracy": "lower_bound"},  # E is a bound
        {"n": 1_000, "d": 980, "e": 5, "scope_complete": False},  # partial scope
        {"n": 1_000, "d": 980, "distinct_accuracy": "estimated", "e": 5},  # D estimated
        {"n": 1_000, "d": 1_001, "e": 0},  # contradictory measures
        {"n": 1_000, "d": 1, "e": 999},  # one distinct row
    ],
)
def test_only_a_concluded_repetition_between_distinct_records_has_a_reading(options):
    result = assess(**options)

    assert result["interpretation"] != "repeated_between_distinct_records"
    assert result["near_unique"] is None


def test_the_reading_never_turns_the_repetitions_into_a_unique_id():
    result = assess(n=1_000, d=990, e=0)

    assert result["near_unique"]["signal"] == "near_unique"
    assert result["interpretation"] == "repeated_between_distinct_records"
    assert result["status"] == "complete"
    assert result["after_row_deduplication"]["unique"] is False
    assert result["raw"]["unique"] is False
    assert result["explanation"]["id_repetitions_residual"] == 10


def test_the_model_is_deterministic_and_only_integers():
    first = assess_near_unique(7, 12_345)

    assert first == assess_near_unique(7, 12_345)
    assert all(
        isinstance(getattr(first, name), int)
        for name in ("residual_repetitions", "distinct_records", "tolerance")
    )


# ------------------------------------------------------------------ the Report


def _report(tmp_path, rows):
    source = write_csv(tmp_path, "r.csv", rows)
    generate_reports([source], output_dir=tmp_path / "out", details=True)
    out = tmp_path / "out"
    document = json.loads((out / "r.json").read_text(encoding="utf-8"))
    page = next(p for p in out.rglob("*.html") if p.name != "r.html" and "customer-id" in p.name)
    return document, page.read_text(encoding="utf-8"), (out / "r.html").read_text(encoding="utf-8")


def test_the_json_carries_the_reading_and_the_classification_stays_an_id(tmp_path):
    document, _, _ = _report(tmp_path, population(distinct_ids=990, shared_id_rows=10, copies=5))

    item = uniqueness_of(document, "customer_id")
    field = next(f for f in document["datasets"][0]["fields"] if f["name"] == "customer_id")

    assert item["near_unique"]["signal"] == "near_unique"
    assert item["near_unique"]["distinct_records"] == 1_000
    assert item["explanation"]["id_repetitions_residual"] == 10
    assert (field["classification"]["family"], field["classification"]["type"]) == (
        "identifier",
        "id",
    )


def test_the_column_page_says_near_unique_and_that_it_is_no_guarantee(tmp_path):
    _, page, report = _report(tmp_path, population(distinct_ids=990, shared_id_rows=10))

    near = re.search(r'class="uq-near[^"]*">.*?</p>', page, re.DOTALL).group(0)
    assert "Near-unique." in near
    assert "10 repetitions among 1,000 distinct records, within the tolerance of 10 (set by one in 100" in near
    assert "not a guarantee" in near and "not a unique ID" in near
    assert "10 ID repetitions remain between distinct records" in report
    assert "uq-near uq-near-" not in report  # the Summary keeps the figures, not the reading


def test_above_the_tolerance_the_page_says_so(tmp_path):
    _, page, _ = _report(tmp_path, population(distinct_ids=900, shared_id_rows=100))

    near = re.search(r'class="uq-near[^"]*">.*?</p>', page, re.DOTALL).group(0)
    assert "Not near-unique." in near
    assert "above the tolerance of 10" in near


def test_a_small_population_says_it_cannot_tell(tmp_path):
    _, page, _ = _report(tmp_path, population(distinct_ids=40, shared_id_rows=1))

    near = re.search(r'class="uq-near[^"]*">.*?</p>', page, re.DOTALL).group(0)
    assert "Too few distinct records to tell." in near
    assert "not a guarantee" not in near


def test_the_raw_repetition_finding_stays_and_links_to_the_reading_card(tmp_path):
    document, page, _ = _report(tmp_path, population(distinct_ids=990, shared_id_rows=10))

    column = next(
        c for c in document["report"]["datasets"][0]["columns"] if c["name"] == "customer_id"
    )
    assert "identifier.repetition" in json.dumps(column["summary"]["findings"])
    assert 'href="#uniqueness"' in page


def test_the_view_has_no_reading_outside_the_case_c():
    unique = assess_identifier_uniqueness(facts(n=500, d=500, e=0))

    assert uniqueness_view(unique).near is None

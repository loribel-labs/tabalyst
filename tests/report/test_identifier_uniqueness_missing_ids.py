# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The decomposition of the ID repetitions despite missing IDs (Unique ID lot 10, cahier 5.4).

With a missing ID, ``E`` mixes copies of rows that have an ID and copies of rows that have none.
The second pass counts the second kind (``E_missing``), so ``E_present = E - E_missing`` and the
repetitions left between the distinct rows that have an ID are exact. A record without an ID stays
among the distinct rows, so the ID is never strictly unique.
"""

import json
import random

import pytest
from identifier_uniqueness_helpers import (
    assess,
    oracle,
    population,
    random_population,
    uniqueness_of,
    write_csv,
)

from tabalyst import generate_reports

pytestmark = pytest.mark.uid_lot("10")

DEEP = "deep.missing_id_copies"


def _case(**override):
    """1,000 records, 100 without an ID, 800 distinct IDs, 120 copies of which 30 have no ID."""
    options = {
        "n": 1_000,
        "present": 900,
        "d": 800,
        "e": 120,
        "missing_copies": (30, "exact"),
    }
    options.update(override)
    return assess(**options)


# ------------------------------------------------------------------ the rule


def test_the_copies_with_an_id_are_set_apart_from_those_without():
    result = _case()

    assert (result["status"], result["reason"]) == ("limited", "missing_ids")
    assert result["interpretation"] == "repeated_between_distinct_records"
    assert result["explanation"] == {
        "duplicate_row_extra_copies": 120,
        "id_repetitions_explained": 90,
        "id_repetitions_residual": 10,
        "duplicate_row_extra_copies_without_id": 30,
    }
    assert result["raw"] == {"unique": False, "id_distinct": 800, "id_redundant": 100}
    assert result["after_row_deduplication"] == {
        "unique": False,
        "id_distinct": 800,
        "id_redundant": 10,
    }
    assert result["scope"]["distinct_records"] == 880
    assert result["near_unique"] is None


def test_no_repetition_among_the_rows_with_an_id_is_not_a_strict_unique():
    result = _case(d=810)

    assert (result["status"], result["reason"]) == ("limited", "missing_ids")
    assert result["interpretation"] == "unique_among_present_ids"
    assert result["explanation"]["id_repetitions_residual"] == 0
    assert result["after_row_deduplication"]["unique"] is None
    assert result["raw"]["unique"] is False


def test_the_cahier_example_has_too_few_rows_with_an_id_to_conclude():
    # ,Alice / ,Alice / B-002,Bob
    result = assess(n=3, present=1, d=1, e=1, missing_copies=(1, "exact"))

    assert result["interpretation"] == "not_assessed"
    assert result["reason"] == "missing_ids"
    assert result["explanation"]["id_repetitions_explained"] == 0
    assert result["explanation"]["id_repetitions_residual"] == 0
    assert result["after_row_deduplication"]["unique"] is None


def test_without_the_count_of_the_copies_nothing_is_subtracted():
    result = assess(n=1_000, present=900, d=800, e=120)

    assert (result["status"], result["interpretation"], result["reason"]) == (
        "limited",
        "not_assessed",
        "missing_ids",
    )
    assert result["explanation"] == {
        "duplicate_row_extra_copies": None,
        "id_repetitions_explained": None,
        "id_repetitions_residual": None,
    }
    assert result["raw"] == {"unique": None, "id_distinct": None, "id_redundant": None}
    assert "missing_id_copies" not in result["evidence"]


def test_a_stopped_count_is_a_bound_and_subtracts_nothing():
    result = _case(missing_copies=(30, "lower_bound"))

    assert result["interpretation"] == "not_assessed"
    assert result["explanation"]["id_repetitions_residual"] is None
    assert result["evidence"]["missing_id_copies"]["accuracy"] == "lower_bound"


def test_the_copies_of_the_rows_need_an_exact_total():
    result = _case(e=None, duplicate_accuracy="disabled")

    assert result["interpretation"] == "not_assessed"
    assert result["explanation"]["id_repetitions_residual"] is None


def test_the_second_pass_names_its_source_in_the_evidence():
    result = _case()

    assert result["evidence"]["missing_id_copies"] == {
        "source": DEEP,
        "accuracy": "exact",
        "identity": "full_decoded_csv_row_v1",
    }


def test_a_column_without_a_missing_id_does_not_carry_the_new_members():
    result = assess(n=1_000, d=900, e=100)

    assert "duplicate_row_extra_copies_without_id" not in result["explanation"]
    assert "missing_id_copies" not in result["evidence"]


@pytest.mark.parametrize(
    "override",
    [
        {"missing_copies": (100, "exact")},  # a copy needs an original: at most M - 1 = 99
        {"missing_copies": (121, "exact"), "present": 850, "d": 700},  # more than E
        {"missing_copies": (5, "exact")},  # 115 copies with an ID exceed P - D = 100
    ],
)
def test_counts_that_break_an_invariant_are_failed_not_corrected(override):
    result = _case(**override)

    assert (result["status"], result["reason"]) == ("failed", "inconsistent_measures")
    assert result["explanation"]["id_repetitions_residual"] is None


def test_a_count_of_copies_without_an_id_is_inconsistent_when_no_id_is_missing():
    result = assess(n=1_000, d=900, e=100, missing_copies=(1, "exact"))

    assert (result["status"], result["reason"]) == ("failed", "inconsistent_measures")


def test_the_total_may_come_from_any_exact_source():
    result = _case(
        e=None,
        duplicate_accuracy="disabled",
        extra_duplicates=[("dedup.report", 120, "exact")],
    )

    assert result["explanation"]["id_repetitions_residual"] == 10
    assert result["evidence"]["duplicate_rows"]["source"] == "dedup.report"


@pytest.mark.parametrize("seed", range(200))
def test_the_residual_equals_the_one_of_an_explicit_deduplication(seed):
    rows = random_population(random.Random(seed))
    expected = oracle(rows)
    if expected.m == 0 or expected.n < 2:
        pytest.skip("this population has no missing ID")
    absent_rows = [row for row in rows if row[0] == ""]
    e_missing = len(absent_rows) - len(set(absent_rows))
    if expected.p == 0:
        pytest.skip("no ID at all: there is no distinct count to compose")

    result = assess(
        n=expected.n,
        present=expected.p,
        d=expected.d,
        e=expected.e,
        missing_copies=(e_missing, "exact"),
    )

    assert result["explanation"]["id_repetitions_residual"] == expected.r_residual
    assert result["explanation"]["id_repetitions_explained"] == expected.r_explained


# ------------------------------------------------------------- the whole Report


def _rows(distinct_ids, shared, copies, blank, blank_copies, seed=3):
    """Rows ``(id, status, region)``: ``blank`` records without an ID, ``blank_copies`` of them copies."""
    base = [(a, b, f"r{a[-1]}") for a, b in population(distinct_ids=distinct_ids, shared_id_rows=shared, copies=copies, seed=seed)]
    empty = [("", f"none-{n}", "rx") for n in range(blank)]
    rows = base + empty + [empty[n % blank] for n in range(blank_copies)]
    random.Random(seed).shuffle(rows)
    return rows


HEADER = ("customer_id", "status", "region")


def _report(tmp_path, rows, **options):
    source = write_csv(tmp_path, "r.csv", rows, HEADER)
    generate_reports([source], output_dir=tmp_path / "out", **options)
    return json.loads((tmp_path / "out" / "r.json").read_text(encoding="utf-8"))


def test_a_forced_report_counts_the_copies_of_the_rows_without_an_id(tmp_path):
    rows = _rows(distinct_ids=1_900, shared=40, copies=300, blank=25, blank_copies=15)
    expected = oracle(rows)

    document = _report(tmp_path, rows, deep=True, confirmed=True)

    item = uniqueness_of(document, "customer_id")
    assert (item["status"], item["reason"]) == ("limited", "missing_ids")
    assert item["interpretation"] == "repeated_between_distinct_records"
    assert item["explanation"]["id_repetitions_explained"] == expected.r_explained
    assert item["explanation"]["id_repetitions_residual"] == expected.r_residual == 40
    assert item["explanation"]["duplicate_row_extra_copies_without_id"] == 15
    assert item["evidence"]["missing_id_copies"]["source"] == DEEP
    assert item["near_unique"] is None


def test_a_plain_report_counts_them_by_itself_for_a_small_file(tmp_path):
    rows = _rows(distinct_ids=1_900, shared=0, copies=300, blank=25, blank_copies=15)

    document = _report(tmp_path, rows)

    item = uniqueness_of(document, "customer_id")
    assert item["interpretation"] == "unique_among_present_ids"
    assert item["explanation"]["id_repetitions_explained"] == 300
    assert item["after_row_deduplication"]["unique"] is None
    assert document["analyses"]["mode"] == "auto"


def test_a_report_with_the_second_pass_off_keeps_the_old_reading(tmp_path):
    rows = _rows(distinct_ids=1_900, shared=0, copies=300, blank=25, blank_copies=15)
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"deep": {"mode": "off"}}), encoding="utf-8")

    document = _report(tmp_path, rows, config_path=config)

    item = uniqueness_of(document, "customer_id")
    assert (item["status"], item["interpretation"]) == ("limited", "not_assessed")
    assert item["explanation"]["id_repetitions_residual"] is None


def test_the_page_of_the_column_prints_the_decomposition(tmp_path):
    rows = _rows(distinct_ids=1_900, shared=40, copies=300, blank=25, blank_copies=15)
    source = write_csv(tmp_path, "r.csv", rows, HEADER)
    generate_reports([source], output_dir=tmp_path / "out", deep=True, confirmed=True, details=True)
    html = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((tmp_path / "out").rglob("*.html"))
    )

    assert "25 records have no ID" in html or "40 ID repetitions remain" in html
    assert "Copies of rows without an ID" in html

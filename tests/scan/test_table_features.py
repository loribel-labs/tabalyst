# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The classes of a category and of the features of a column (design 20.13,
REL-01, REL-12)."""

import pytest
from planner_helpers import scan_csv, with_field
from table_helpers import branch_rows

from tabalyst.scanner import ScanConfig
from tabalyst.scanner.features import (
    FEW_LENGTHS,
    FEW_PREFIXES,
    MISSING,
    NO_FREQUENCIES,
    NO_PATTERN,
    SINGLE_VALUE,
    TOO_MANY_CATEGORIES,
    UNCLASSIFIED,
    UNKNOWN_FEATURE,
    PatternClassifier,
    category_coder,
    feature_coder,
)
from tabalyst.scanner.models import Disabled, FieldPatternsComplete
from tabalyst.scanner.secondpass.replay import CellReader


def _reader() -> CellReader:
    return CellReader(ScanConfig())


def _field(result, display):
    return next(f for f in result.datasets[0].fields if f.display == display)


def _entry(result, display):
    field = _field(result, display)
    return next(
        e
        for e in result.derived.patterns.fields
        if e.field == field.id and isinstance(e, FieldPatternsComplete)
    )


def _coders(tmp_path, rows=None, **settings):
    rows = rows or branch_rows(per_branch=40)[0]
    result = scan_csv(tmp_path, "branch,client", rows, **settings)
    return result, _reader()


def test_a_category_is_coded_against_the_exact_frequencies_of_the_scan(tmp_path):
    result, reader = _coders(tmp_path)

    coder, why = category_coder(reader, _field(result, "branch"), 30, 100)

    assert why is None and len(coder.classes) == 13 and coder.classes[-1].kind == "other"
    codes = coder.code_strings(["branch-01", " branch-02 ", "elsewhere", "", "  "])
    assert codes[0] == 0 and codes[1] == 1  # the analytical text is trimmed
    assert codes[2] == coder.other
    assert codes[3] == MISSING and codes[4] == MISSING


def test_the_most_frequent_categories_are_classes_and_the_rest_is_other(tmp_path):
    rows = [f"c{n % 8},{n}" for n in range(200)] + ["c0,1"] * 50
    result, reader = _coders(tmp_path, rows)

    coder, _ = category_coder(reader, _field(result, "branch"), 3, 100)

    assert [c.label for c in coder.classes] == ["c0", "c1", "c2", "other"]
    assert coder.code_strings(["c5"]) == [coder.other]


@pytest.mark.parametrize(
    ("rows", "reason"),
    [
        ([f"same,{n}" for n in range(60)], SINGLE_VALUE),
        ([f"v{n},{n}" for n in range(300)], TOO_MANY_CATEGORIES),
    ],
)
def test_a_column_that_cannot_be_a_category_says_why(tmp_path, rows, reason):
    result, reader = _coders(tmp_path, rows)

    coder, why = category_coder(reader, _field(result, "branch"), 30, 100)

    assert coder is None and why == reason


def test_a_column_without_exact_frequencies_is_not_a_category(tmp_path):
    result, reader = _coders(tmp_path)
    edited = with_field(result, "branch", values=_field(result, "branch").values.model_copy(
        update={"frequencies": Disabled()}
    ))

    coder, why = category_coder(reader, _field(edited, "branch"), 30, 100)

    assert coder is None and why == NO_FREQUENCIES


def test_a_pattern_is_the_most_specific_candidate_that_reads_the_value(tmp_path):
    result, reader = _coders(tmp_path)
    entry = _entry(result, "client")

    coder, why = feature_coder(
        reader, "pattern", _field(result, "client"), entry,
        max_classes=12, prefix_length=2, max_value_length=64,
    )

    assert why is None and coder.domain == "original"
    codes = coder.code_strings(["AB1234", "123456", "??##", "", "A" * 100, "x"])
    named = [c.label for c in coder.classes]
    assert named[codes[0]] == "XX9999" and named[codes[1]] == "999999"
    assert codes[2] == coder.other  # no candidate reads it
    assert codes[3] == MISSING
    assert codes[4] == UNCLASSIFIED  # longer than the inference reads
    assert codes[5] == coder.other
    # A JSON number is not a string: no pattern is tried on it.
    assert coder.code_native("integer", 12) == UNCLASSIFIED


def test_the_classifier_reports_the_overlaps_of_candidates(tmp_path):
    result, _ = _coders(tmp_path)
    entry = _entry(result, "client")

    first, overlaps = PatternClassifier(entry, 64).classify("AB1234")

    assert first >= 0 and overlaps is None or len(overlaps) >= 2


def test_a_length_is_the_length_of_the_analytical_text(tmp_path):
    rows = [f"{'a' * (1 + n % 4)},{n}" for n in range(80)]
    result, reader = _coders(tmp_path, rows)

    coder, why = feature_coder(
        reader, "length", _field(result, "branch"), None,
        max_classes=12, prefix_length=2, max_value_length=64,
    )

    assert why is None and [c.label for c in coder.classes] == ["1", "2", "3", "4", "other"]
    assert coder.code_strings([" aa ", "aaaa", "a" * 9, ""]) == [1, 3, coder.other, MISSING]


def test_the_lengths_beyond_the_class_budget_are_other(tmp_path):
    rows = [f"{'a' * (1 + n % 9)},{n}" for n in range(180)]
    result, reader = _coders(tmp_path, rows)

    coder, _ = feature_coder(
        reader, "length", _field(result, "branch"), None,
        max_classes=4, prefix_length=2, max_value_length=64,
    )

    assert len(coder.classes) == 4 and coder.classes[-1].kind == "other"


def test_a_prefix_is_read_on_the_original_value(tmp_path):
    rows = [f"{p}-{n},{n}" for n, p in enumerate(["QC", "ON", "QC", "BC"] * 20)]
    result, reader = _coders(tmp_path, rows)

    coder, why = feature_coder(
        reader, "prefix", _field(result, "branch"), None,
        max_classes=12, prefix_length=2, max_value_length=64,
    )

    assert why is None and coder.domain == "original"
    assert [c.label for c in coder.classes] == ["QC", "BC", "ON", "other"]
    assert coder.code_strings(["QC-9", "ZZ-1", " QC", ""]) == [0, 3, 3, MISSING]


@pytest.mark.parametrize(
    ("feature", "reason"),
    [("pattern", NO_PATTERN), ("length", FEW_LENGTHS), ("prefix", FEW_PREFIXES), ("shape", UNKNOWN_FEATURE)],
)
def test_a_feature_a_column_cannot_offer_says_why(tmp_path, feature, reason):
    rows = [f"v{n % 5},same" for n in range(100)]
    result, reader = _coders(tmp_path, rows)
    # A column of one length and one prefix, and without patterns.
    bare = result.model_copy(update={"derived": None})

    coder, why = feature_coder(
        reader, feature, _field(bare, "client"), None,
        max_classes=12, prefix_length=4, max_value_length=64,
    )

    assert coder is None and why == reason

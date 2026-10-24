# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Edge cases of the pure rule beyond the contract tests T01 to T34."""

import pytest
from identifier_uniqueness_helpers import assess, facts

from tabalyst.identifier_uniqueness import assess_identifier_uniqueness

pytestmark = [pytest.mark.uid_lot("1")]


def test_a_lower_bound_above_the_exact_count_fails():
    result = assess(
        n=100,
        d=90,
        e=2,
        extra_duplicates=[("dedup.report", 5, "lower_bound")],
    )

    assert result["status"] == "failed"
    assert result["reason"] == "inconsistent_measures"


def test_a_conflict_lists_the_values_that_disagree():
    result = assess(
        n=10, d=8, e=2, extra_duplicates=[("dedup.report", 3, "exact")]
    )

    values = result["evidence"]["conflict"]["values"]
    assert [(v["source"], v["value"]) for v in values] == [
        ("scan.records.duplicates", 2),
        ("dedup.report", 3),
    ]


def test_a_failed_object_keeps_the_counts_of_the_scope_only():
    result = assess(n=10, d=11, e=0)

    assert result["scope"]["source_records"] == 10
    assert result["scope"]["distinct_records"] is None
    assert result["raw"] == {"unique": None, "id_distinct": None, "id_redundant": None}


def test_missing_distinct_evidence_is_not_assessed():
    result = assess(n=10, d=None, e=0)

    assert result["status"] == "not_assessed"
    assert result["reason"] == "distinct_unavailable"
    assert result["evidence"]["id_cardinality"] is None


def test_inconsistent_counts_of_the_facts_fail():
    result = assess(n=10, present=12, d=5, e=0)

    assert result["reason"] == "inconsistent_measures"


def test_a_rule_that_breaks_reports_a_computation_error(monkeypatch):
    from tabalyst.identifier_uniqueness import rule

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(rule, "_assess", boom)
    result = assess_identifier_uniqueness(facts(n=10, d=10, e=0))

    assert (result.status, result.reason) == ("failed", "computation_error")


def test_the_object_is_frozen():
    result = assess_identifier_uniqueness(facts(n=10, d=10, e=0))

    with pytest.raises(ValueError):
        result.status = "failed"

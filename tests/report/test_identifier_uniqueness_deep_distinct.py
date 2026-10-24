# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The Deep analytical cardinality as a source of ``D`` (contract 6.1 and 6.4, Unique ID lot 7)."""

import json

import pytest
from identifier_uniqueness_helpers import assess, uniqueness_of, write_csv

from tabalyst import generate_reports
from tabalyst.scanner.config import ScanConfig

pytestmark = pytest.mark.uid_lot("7")

SCAN = "scan.values.cardinality"
ORIGINAL = "deep.exact_distinct"
ANALYTICAL = "deep.analytical_distinct"


def test_a_deep_analytical_count_is_d_when_the_scan_has_none():
    result = assess(n=1_000, d=900, e=100, distinct_source=ANALYTICAL)

    assert result["status"] == "complete"
    assert result["interpretation"] == "unique_after_row_deduplication"
    assert result["evidence"]["id_cardinality"] == {
        "source": ANALYTICAL,
        "accuracy": "exact",
        "domain": "analytical",
    }
    assert result["scope"]["id_value_domain"] == "analytical"


def test_the_analytical_count_serves_where_the_original_one_does_not():
    original = assess(
        n=1_000,
        d=950,
        e=0,
        distinct_source=ORIGINAL,
        domain="original",
        stages_changed_values=True,
    )
    both = assess(
        n=1_000,
        d=900,
        e=0,
        distinct_source=ANALYTICAL,
        alternatives=[(ORIGINAL, 950, "original", True)],
    )

    assert original["reason"] == "distinct_not_exact"
    assert both["status"] == "complete"
    assert both["interpretation"] == "repeated_between_distinct_records"
    assert both["explanation"]["id_repetitions_residual"] == 100


def test_two_exact_counts_that_agree_leave_the_first_as_the_source():
    result = assess(
        n=1_000,
        d=900,
        e=100,
        alternatives=[(ANALYTICAL, 900, "analytical", False)],
    )

    assert result["status"] == "complete"
    assert result["evidence"]["id_cardinality"]["source"] == SCAN


def test_two_exact_counts_that_differ_are_a_conflict_not_a_choice():
    result = assess(
        n=1_000,
        d=900,
        e=100,
        alternatives=[(ANALYTICAL, 899, "analytical", False)],
    )

    assert (result["status"], result["reason"]) == ("failed", "evidence_conflict")
    conflict = result["evidence"]["conflict"]
    assert conflict["measure"] == "id_cardinality"
    assert {item["source"]: item["value"] for item in conflict["values"]} == {
        SCAN: 900,
        ANALYTICAL: 899,
    }
    assert result["raw"]["unique"] is None


def test_the_original_count_must_agree_when_no_stage_changed_a_value():
    result = assess(
        n=1_000,
        d=900,
        e=100,
        distinct_source=ANALYTICAL,
        alternatives=[(ORIGINAL, 901, "original", False)],
    )

    assert (result["status"], result["reason"]) == ("failed", "evidence_conflict")


def test_an_analytical_count_above_the_original_one_is_inconsistent():
    result = assess(
        n=1_000,
        d=900,
        e=100,
        distinct_source=ANALYTICAL,
        alternatives=[(ORIGINAL, 880, "original", True)],
    )

    assert (result["status"], result["reason"]) == ("failed", "inconsistent_measures")


def test_an_original_count_above_the_analytical_one_is_what_normalization_does():
    result = assess(
        n=1_000,
        d=900,
        e=100,
        distinct_source=ANALYTICAL,
        alternatives=[(ORIGINAL, 960, "original", True)],
    )

    assert result["status"] == "complete"


# From the documents ------------------------------------------------------------


def padded_rows(distinct=1_200, padded=150):
    """Rows whose IDs repeat only under trim: ``padded`` rows write an ID of another row with
    a space, so they are no copy of a row yet repeat the ID of its analytical value."""
    rows = [(f"A-{i:07d}", "active") for i in range(distinct)]
    rows += [(f" A-{i:07d}", "active") for i in range(padded)]
    return rows


def _config(tmp_path, **deep):
    scan = ScanConfig.model_validate(
        {"limits": {"max_distinct_per_field": 300, "max_samples": 100}}
    )
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {"scan": scan.model_dump(by_alias=True, mode="json", exclude_defaults=True), "deep": deep}
        ),
        encoding="utf-8",
    )
    return path


def _report(tmp_path, rows, *, deep):
    source = write_csv(tmp_path, "r.csv", rows)
    generate_reports(
        [source],
        output_dir=tmp_path / "out",
        config_path=_config(tmp_path),
        deep=deep,
        confirmed=True,
    )
    return json.loads((tmp_path / "out" / "r.json").read_text(encoding="utf-8"))


def test_a_forced_report_counts_the_ids_after_trim_and_tells_the_residual_repetitions(tmp_path):
    document = _report(tmp_path, padded_rows(), deep=True)

    item = uniqueness_of(document, "customer_id")
    assert item["status"] == "complete"
    assert item["interpretation"] == "repeated_between_distinct_records"
    assert item["explanation"]["duplicate_row_extra_copies"] == 0
    assert item["explanation"]["id_repetitions_residual"] == 150
    assert item["raw"]["id_distinct"] == 1_200
    assert item["evidence"]["id_cardinality"]["source"] == ANALYTICAL
    assert item["evidence"]["id_cardinality"]["domain"] == "analytical"


def test_a_report_that_does_not_force_the_second_pass_never_counts_them(tmp_path):
    document = _report(tmp_path, padded_rows(), deep=False)

    item = uniqueness_of(document, "customer_id")
    # The automatic second pass counts the original values, which trim made differ from the
    # analytical ones: that count is not D, and nothing counts the analytical ones unasked.
    assert item["status"] == "limited" and item["reason"] == "distinct_not_exact"
    assert item["raw"]["unique"] is None
    assert item["evidence"]["id_cardinality"]["source"] == ORIGINAL


def test_the_second_pass_document_holds_the_analytical_count_beside_the_original_one(tmp_path):
    document = _report(tmp_path, padded_rows(), deep=True)

    ran = {
        item["analyzer"]: item["result"]
        for item in document["analyses"]["deep"]["analyses"]
        if item["analyzer"] in ("exact_distinct", "analytical_distinct")
        and item["display"] == "customer_id"
    }
    assert ran["exact_distinct"]["distinct"] == 1_350
    assert ran["analytical_distinct"]["distinct"] == 1_200
    assert ran["analytical_distinct"]["kind"] == "analytical_distinct"
    assert ran["analytical_distinct"]["changed"] == 150


def test_the_facts_prefer_the_scan_then_the_analytical_count_then_the_original_one(tmp_path):
    facts = _deep_facts(tmp_path, scan_limits={"max_distinct_per_field": 300, "max_samples": 100})

    assert facts.distinct.source == ANALYTICAL
    assert [(item.source, item.stages_changed_values) for item in facts.distinct_alternatives] == [
        (ORIGINAL, True)
    ]


def test_a_scan_that_kept_its_table_has_no_alternative(tmp_path):
    facts = _deep_facts(tmp_path, scan_limits={})

    assert facts.distinct.source == SCAN
    assert facts.distinct_alternatives == ()


def test_an_analytical_count_standing_on_another_scan_is_ignored(tmp_path):
    facts = _deep_facts(
        tmp_path,
        scan_limits={"max_distinct_per_field": 300, "max_samples": 100},
        other_scan=True,
    )

    assert facts.distinct.source == SCAN and facts.distinct.accuracy == "estimated"
    assert facts.distinct_alternatives == ()


def test_a_stopped_analytical_count_is_never_d(tmp_path):
    facts = _deep_facts(
        tmp_path,
        scan_limits={"max_distinct_per_field": 300, "max_samples": 100},
        stopped=True,
    )

    assert facts.distinct.source != ANALYTICAL


def _deep_facts(tmp_path, *, scan_limits, other_scan=False, stopped=False):
    """The facts of ``customer_id`` with the second pass of its Scan."""
    from tabalyst import scan
    from tabalyst.identifier_uniqueness.facts import facts_from_scan
    from tabalyst.models import AnalysesBlock
    from tabalyst.scanner.planner import (
        AnalysisRequest,
        default_registry,
        plan_analyses,
    )
    from tabalyst.scanner.planner.planner import plan_base
    from tabalyst.scanner.secondpass import run_second_pass

    source = write_csv(tmp_path, "r.csv", padded_rows())
    config = ScanConfig.model_validate({"limits": scan_limits})
    result = scan(source, config=config)
    plan = plan_analyses(
        result,
        requests=[AnalysisRequest("analytical_distinct"), AnalysisRequest("exact_distinct")],
        registry=default_registry().runnable(),
    )
    document = run_second_pass(result, source, plan).document
    if stopped:
        document = document.model_copy(
            update={
                "analyses": [
                    item.model_copy(update={"status": "limited"})
                    if item.analyzer == "analytical_distinct"
                    else item
                    for item in document.analyses
                ]
            }
        )
    block = AnalysesBlock(mode="forced", outcome="ran", deep=document)
    dataset = result.datasets[0]
    column = next(f.id for f in dataset.fields if f.display == "customer_id")
    base = plan_base(result)
    if other_scan:
        base = base.model_copy(update={"source_sha256": "f" * 64})
    return facts_from_scan(result, dataset.id, column, analyses=block, base=base)

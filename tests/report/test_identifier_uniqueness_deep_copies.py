# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The Deep count of the copies of rows as the third source of ``E`` (contract 6.2, Unique ID lot 6)."""

import json

import pytest
from identifier_uniqueness_helpers import (
    assess,
    population,
    uniqueness_of,
    write_csv,
)

from tabalyst import generate_reports
from tabalyst.scanner.config import ScanConfig

pytestmark = pytest.mark.uid_lot("6")

DEEP = "deep.duplicate_rows_count"
SCAN = "scan.records.duplicates"


def _limited(tmp_path, **deep):
    path = tmp_path / "config.json"
    scan = ScanConfig.model_validate({"limits": {"max_tracked_records": 500}})
    document = {
        "scan": scan.model_dump(by_alias=True, mode="json", exclude_defaults=True),
        "deep": deep,
    }
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _report(tmp_path, rows, *, deep=True, **config):
    source = write_csv(tmp_path, "r.csv", rows)
    generate_reports(
        [source],
        output_dir=tmp_path / "out",
        config_path=_limited(tmp_path, **config),
        deep=deep,
        confirmed=True,
    )
    return json.loads((tmp_path / "out" / "r.json").read_text(encoding="utf-8"))


def test_a_deep_exact_count_replaces_the_limited_one_of_the_scan():
    result = assess(
        n=1_000,
        d=900,
        e=80,
        duplicate_accuracy="lower_bound",
        extra_duplicates=[(DEEP, 100, "exact")],
    )

    assert result["status"] == "complete"
    assert result["interpretation"] == "unique_after_row_deduplication"
    assert result["explanation"]["duplicate_row_extra_copies"] == 100
    assert result["evidence"]["duplicate_rows"]["source"] == DEEP
    assert result["evidence"]["duplicate_rows"]["accuracy"] == "exact"


def test_a_deep_exact_count_serves_a_scan_that_did_not_count():
    result = assess(
        n=1_000,
        d=900,
        e=None,
        duplicate_accuracy="disabled",
        extra_duplicates=[(DEEP, 100, "exact")],
    )

    assert result["status"] == "complete"
    assert result["evidence"]["duplicate_rows"]["source"] == DEEP


def test_two_exact_counts_that_differ_are_a_conflict_not_a_choice():
    result = assess(n=1_000, d=900, e=100, extra_duplicates=[(DEEP, 99, "exact")])

    assert (result["status"], result["reason"]) == ("failed", "evidence_conflict")
    values = {item["source"]: item["value"] for item in result["evidence"]["conflict"]["values"]}
    assert values == {SCAN: 100, DEEP: 99}


def test_two_exact_counts_that_agree_leave_the_scan_as_the_source():
    result = assess(n=1_000, d=900, e=100, extra_duplicates=[(DEEP, 100, "exact")])

    assert result["status"] == "complete"
    assert result["evidence"]["duplicate_rows"]["source"] == SCAN


def test_a_stopped_deep_count_is_a_bound_and_the_highest_bound_is_shown():
    result = assess(
        n=1_000,
        d=900,
        e=40,
        duplicate_accuracy="lower_bound",
        extra_duplicates=[(DEEP, 70, "lower_bound")],
    )

    assert (result["status"], result["reason"]) == ("limited", "duplicates_limited")
    assert result["evidence"]["duplicate_rows"]["source"] == DEEP
    assert result["evidence"]["duplicate_rows"]["accuracy"] == "lower_bound"


def test_a_deep_bound_above_what_the_ids_allow_is_inconsistent():
    result = assess(
        n=1_000,
        d=950,
        e=None,
        duplicate_accuracy="disabled",
        extra_duplicates=[(DEEP, 200, "lower_bound")],
    )

    assert (result["status"], result["reason"]) == ("failed", "inconsistent_measures")


def test_a_forced_report_counts_the_copies_the_scan_could_only_bound(tmp_path):
    document = _report(tmp_path, population(distinct_ids=2_000, copies=600))

    item = uniqueness_of(document, "customer_id")
    assert item["status"] == "complete"
    assert item["interpretation"] == "unique_after_row_deduplication"
    assert item["explanation"]["duplicate_row_extra_copies"] == 600
    assert item["explanation"]["id_repetitions_residual"] == 0
    assert item["evidence"]["duplicate_rows"]["source"] == DEEP
    assert item["evidence"]["duplicate_rows"]["accuracy"] == "exact"
    assert item["evidence"]["duplicate_rows"]["identity"] == "full_decoded_csv_row_v1"


def test_a_forced_report_tells_residual_repetitions_after_the_deep_count(tmp_path):
    document = _report(tmp_path, population(distinct_ids=1_900, shared_id_rows=100, copies=600))

    item = uniqueness_of(document, "customer_id")
    assert item["interpretation"] == "repeated_between_distinct_records"
    assert item["explanation"]["id_repetitions_explained"] == 600
    assert item["explanation"]["id_repetitions_residual"] == 100


def test_a_report_that_does_not_force_the_second_pass_never_counts_the_copies(tmp_path):
    document = _report(tmp_path, population(distinct_ids=2_000, copies=600), deep=False)

    item = uniqueness_of(document, "customer_id")
    assert item["status"] == "limited" and item["reason"] == "duplicates_limited"
    assert item["evidence"]["duplicate_rows"]["source"] == SCAN


def test_a_ceiling_of_the_plan_leaves_a_bound_in_the_report(tmp_path):
    document = _report(
        tmp_path,
        population(distinct_ids=2_000, copies=600),
        copies={"max_rows": 1_500},
    )

    item = uniqueness_of(document, "customer_id")
    assert item["status"] == "limited" and item["reason"] == "duplicates_limited"
    assert item["evidence"]["duplicate_rows"]["accuracy"] == "lower_bound"


def _deep_facts(tmp_path, *, other_scan=False, tamper=None, copies=None):
    """The facts of ``customer_id`` with the second pass of its Scan, or of another one."""
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

    source = write_csv(tmp_path, "r.csv", population(distinct_ids=2_000, copies=600))
    config = ScanConfig.model_validate({"limits": {"max_tracked_records": 500}})
    result = scan(source, config=config)
    plan = plan_analyses(
        result,
        requests=[AnalysisRequest("duplicate_rows_count")],
        registry=default_registry().runnable(),
        deep=copies,
    )
    document = run_second_pass(result, source, plan, settings=copies).document
    if tamper is not None:
        document = document.model_copy(
            update={
                "analyses": [
                    item.model_copy(update={"result": item.result.model_copy(update=tamper)})
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


def test_the_facts_carry_the_deep_count_after_the_scan_and_the_dedup_proof(tmp_path):
    found = _deep_facts(tmp_path)

    assert [item.source for item in found.duplicates] == [SCAN, DEEP]
    assert found.duplicates[1].accuracy == "exact" and found.duplicates[1].value == 600


def test_a_deep_count_standing_on_another_scan_is_ignored(tmp_path):
    found = _deep_facts(tmp_path, other_scan=True)

    assert [item.source for item in found.duplicates] == [SCAN]


def test_an_exact_deep_count_of_another_file_is_ignored(tmp_path):
    found = _deep_facts(tmp_path, tamper={"source_sha256": "e" * 64})

    assert [item.source for item in found.duplicates] == [SCAN]


def test_a_stopped_count_that_read_more_records_than_the_scan_is_ignored(tmp_path):
    from tabalyst.config import CopySettings, DeepSettings

    deep = DeepSettings(copies=CopySettings(max_rows=1_500))

    kept = _deep_facts(tmp_path, copies=deep)
    foreign = _deep_facts(tmp_path, copies=deep, tamper={"records": 10**9})

    assert [item.accuracy for item in kept.duplicates] == ["lower_bound", "lower_bound"]
    assert [item.source for item in foreign.duplicates] == [SCAN]

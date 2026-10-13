# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Eligibility of the fields for the pattern discovery (design 18.12, PAT-12):
states, scores and reasons from the facts and the samples of a Scan."""

from pathlib import Path

import pytest
from planner_helpers import by_analyzer
from scan_helpers import write_json, write_text
from second_pass_helpers import entry, forced_plan

from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner.models import PatternEligibility, ScanResult
from tabalyst.scanner.pattern_eligibility import deciding_reason
from tabalyst.scanner.secondpass import run_second_pass
from tabalyst.scanner.validation import check_scan


def _scan_csv(tmp_path: Path, rows: list[str]) -> ScanResult:
    source = write_text(tmp_path, "data.csv", "value\n" + "\n".join(rows) + "\n")
    return scan(source, config=ScanConfig())


def _eligibility(result: ScanResult) -> PatternEligibility:
    """The eligibility of the first field."""
    assert result.derived is not None and result.derived.patterns is not None
    return result.derived.patterns.fields[0].eligibility


def test_booleans_are_excluded(tmp_path):
    result = _scan_csv(tmp_path, ["true", "false"] * 20)
    assert _eligibility(result).state == "excluded"
    assert _eligibility(result).reasons == ["booleans_only"]
    assert _eligibility(result).score == 0


def test_decimal_numbers_are_assessed_and_of_low_relevance(tmp_path):
    result = _scan_csv(tmp_path, [f"{i * 1.37:.2f}" for i in range(1, 80)])
    eligibility = _eligibility(result)
    assert eligibility.state == "low_relevance"
    assert "decimal_numbers" in eligibility.reasons
    assert 0 < eligibility.score < 0.35


def test_free_text_takes_too_many_formats_of_fixed_length(tmp_path):
    words = ["red", "fox", "jumps", "over", "a", "lazy", "brown", "dog", "today"]
    rows = [" ".join(words[(i + j) % 9] for j in range(2 + i % 5)) for i in range(60)]
    eligibility = _eligibility(_scan_csv(tmp_path, rows))
    assert eligibility.state == "low_relevance"
    assert eligibility.reasons[0] == "many_fixed_lengths"


def test_an_empty_column_has_no_values(tmp_path):
    source = write_text(tmp_path, "data.csv", "value,other\n" + ",x\n" * 20)
    eligibility = _eligibility(scan(source, config=ScanConfig()))
    assert eligibility.state == "excluded"
    assert eligibility.reasons == ["no_values"]


def test_an_empty_column_gets_no_pattern_validation_in_the_plan(tmp_path):
    source = write_text(tmp_path, "data.csv", "code,empty\n" + "".join(
        f"AB-{n:04d},\n" for n in range(40)
    ))
    plan = forced_plan(scan(source, config=ScanConfig()))
    validations = by_analyzer(plan, "pattern_validation")
    assert len(validations) == 1


def test_json_integers_are_read_as_their_decimal_text(tmp_path):
    rows = [{"number": 400_000_000 + i * 104_729} for i in range(60)]
    result = scan(write_json(tmp_path, "data.json", rows), config=ScanConfig())
    assert result.derived is not None and result.derived.patterns is not None
    [entry] = result.derived.patterns.fields
    assert entry.eligibility.state == "eligible"
    assert entry.status == "complete"
    assert [pattern.render for pattern in entry.all_patterns()] == ["'40'9{7}"]


@pytest.mark.parametrize(("max_samples", "computed_from"), [(10_000, "samples"), (20, "source")])
def test_json_integers_are_validated_as_the_text_they_were_discovered_from(
    tmp_path, max_samples, computed_from
):
    rows = [{"number": 400_000_000 + i * 104_729} for i in range(60)]
    source = write_json(tmp_path, "data.json", rows)
    result = scan(source, config=ScanConfig.model_validate({"limits": {"max_samples": max_samples}}))
    outcome = run_second_pass(result, source, forced_plan(result))
    counts = entry(outcome, "pattern_validation", "number").result

    assert counts.computed_from == computed_from
    assert counts.excluded.non_string == 0
    assert counts.matched == counts.values == 60


def test_a_semantic_detector_lowers_the_score_without_excluding(tmp_path):
    rows = [f"2026-{1 + i % 12:02d}-{1 + i % 28:02d}" for i in range(80)]
    with_detector = _eligibility(_scan_csv(tmp_path, rows))
    source = write_text(tmp_path, "plain.csv", "value\n" + "\n".join(rows) + "\n")
    plain = _eligibility(
        scan(source, config=ScanConfig.model_validate({"detectors": {"date": {"enabled": False}}}))
    )
    assert with_detector.state == "eligible"
    assert "semantic_detector" in with_detector.reasons
    assert with_detector.score < plain.score


def test_the_reason_of_an_entry_without_patterns_is_the_deciding_one():
    eligibility = PatternEligibility(
        state="low_relevance",
        score=0.2,
        reasons=["regular_structure", "no_structural_marks", "few_distinct"],
    )
    assert deciding_reason(eligibility) == "no_structural_marks"


def test_check_scan_reports_an_eligibility_that_contradicts_the_entry(tmp_path):
    result = _scan_csv(tmp_path, ["true", "false"] * 20)
    assert not [problem for problem in check_scan(result) if "eligibility" in problem]
    document = result.model_dump(mode="json", by_alias=True)
    entry = document["derived"]["patterns"]["fields"][0]
    assert entry["status"] == "not_applicable"
    entry["eligibility"] = {"state": "eligible", "score": 0.9, "reasons": ["regular_structure"]}
    tampered = ScanResult.model_validate(document)
    assert [problem for problem in check_scan(tampered) if "eligibility" in problem]

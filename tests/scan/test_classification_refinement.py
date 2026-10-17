# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Refinement of the classification by the second pass (Report overview lot R4).

``report_classification.refine`` starts from the classification of the Scan and
turns an ID whose cardinality the first pass could not complete into a Unique ID
when ``exact_distinct`` proves it. Everything else, and every second pass that is
absent, stale, incomplete or failed, leaves the Scan's classification as it is.
"""

import pytest
from planner_helpers import scan_csv
from scan_helpers import write_json, write_text
from second_pass_helpers import deep_csv, forced_plan

from tabalyst.models import AnalysesBlock
from tabalyst.report_classification import refine
from tabalyst.report_config import ReportConfig
from tabalyst.report_profile import build_profile
from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner.planner.planner import plan_base
from tabalyst.scanner.secondpass import run_second_pass
from tabalyst.scanner.secondpass.models import DistinctLimited

ID = ("identifier", "id")
UNIQUE_ID = ("identifier", "unique_id")
IDENTIFIERS = [f"C{n:05d}" for n in range(300)]
# The scan stops counting distinct values at 50: 300 identifiers are limited.
LIMITED = {"limits": {"max_distinct_per_field": 50}}


def _pair(classification):
    return classification.family, classification.type


def _analyses(outcome):
    return AnalysesBlock(mode="forced", outcome="ran", deep=outcome.document)


def _second_pass(tmp_path, name, cells, *, label=True, **settings):
    """The Scan of a CSV whose first column is ``name`` and its forced second pass."""
    header = f"{name},label" if label else name
    rows = [f"{value},x" if label else str(value) for value in cells]
    result, _, outcome = deep_csv(tmp_path, header, rows, **{**LIMITED, **settings})
    return result, _analyses(outcome)


def _first(result):
    return result.datasets[0].fields[0]


def _refined(result, analyses, **keywords):
    return refine(
        _first(result),
        analyses,
        dataset=result.datasets[0].id,
        base=plan_base(result),
        **keywords,
    )


def _evidence(classification):
    return {
        (item.id, item.role): item.scope.model_dump()
        for item in classification.evidence
        if item.source == "measure"
    }


# --- The refinement ----------------------------------------------------------------


def test_the_second_pass_turns_a_limited_id_into_a_unique_id(tmp_path):
    result, analyses = _second_pass(tmp_path, "customer_id", IDENTIFIERS)
    first = _first(result).classification

    refined = _refined(result, analyses)

    assert _pair(first) == ID and "observed_unique" not in first.traits
    assert _pair(refined) == UNIQUE_ID
    assert (refined.state, refined.basis) == ("candidate", "inferred")
    assert "observed_unique" in refined.traits
    assert refined.rule_version == first.rule_version


def test_a_refinement_lists_the_second_pass_fact_that_did_it(tmp_path):
    result, analyses = _second_pass(tmp_path, "customer_id", IDENTIFIERS)

    refined = _refined(result, analyses)

    measures = _evidence(refined)
    assert measures[("exact_distinct.distinct", "supports")] == {
        "population": "present_values",
        "of": 300,
        "partial": False,
        "accuracy": "exact",
    }
    assert measures[("missing.count", "supports")]["population"] == "positions"
    # Nothing the first pass established is dropped.
    first = _first(result).classification
    assert all(item in refined.evidence for item in first.evidence)
    assert refined.alternatives == first.alternatives


def test_the_records_the_scan_excluded_make_the_refined_scope_partial(tmp_path):
    result, analyses = _second_pass(tmp_path, "customer_id", IDENTIFIERS)

    refined = _refined(result, analyses, excluded_records=2)

    measures = _evidence(refined)
    assert measures[("exact_distinct.distinct", "supports")]["partial"] is True
    assert measures[("missing.count", "supports")]["partial"] is True


def test_the_report_carries_the_refined_classification_and_the_counts(tmp_path):
    result, analyses = _second_pass(tmp_path, "customer_id", IDENTIFIERS)
    config = ReportConfig(scan=result.config)

    refined = build_profile(result, config, analyses=analyses)
    plain = build_profile(result, config)

    column = refined.report.datasets[0].columns[0]
    assert _pair(column.classification) == UNIQUE_ID
    assert _pair(plain.report.datasets[0].columns[0].classification) == ID
    summary = refined.report.datasets[0].summary
    assert summary.type_counts == {"identifier/unique_id": 1, "categorical/constant": 1}
    assert summary.type_family_counts == {"identifier": 1, "categorical": 1}
    assert summary.type_percents["identifier/unique_id"] == 50.0
    assert summary.type_family_percents == {"identifier": 50.0, "categorical": 50.0}


# --- When the first pass already knows ---------------------------------------------


def test_a_unique_id_of_the_first_pass_is_the_same_with_and_without_the_second_pass(
    tmp_path,
):
    result, _, outcome = deep_csv(
        tmp_path,
        "customer_id,label",
        [f"{value},x" for value in IDENTIFIERS[:40]],
    )
    first = _first(result).classification

    assert _pair(first) == UNIQUE_ID
    assert _refined(result, _analyses(outcome)) == first
    assert _refined(result, None) == first


def test_an_id_with_repetitions_stays_an_id_with_or_without_the_second_pass(tmp_path):
    result, analyses = _second_pass(tmp_path, "customer_id", IDENTIFIERS[:100] * 2)
    first = _first(result).classification

    assert _pair(first) == ID
    assert _refined(result, analyses) == first


def test_only_an_id_is_refined(tmp_path):
    result, analyses = _second_pass(tmp_path, "note", [f"text {n}" for n in range(300)])
    first = _first(result).classification

    assert first.family == "text"
    assert _refined(result, analyses) == first


# --- Nothing is invented -----------------------------------------------------------


def _unchanged(result, analyses):
    assert _refined(result, analyses) == _first(result).classification


def test_without_a_second_pass_the_scan_classification_is_unchanged(tmp_path):
    result, analyses = _second_pass(tmp_path, "customer_id", IDENTIFIERS)

    _unchanged(result, None)
    _unchanged(result, AnalysesBlock(mode="off", outcome="disabled", reason="off"))
    _unchanged(
        result, AnalysesBlock(mode="auto", outcome="failed", reason="source changed")
    )
    assert analyses.deep is not None


def test_a_second_pass_of_another_scan_is_stale_and_changes_nothing(tmp_path):
    result, analyses = _second_pass(tmp_path, "customer_id", IDENTIFIERS)
    elsewhere = tmp_path / "other"
    elsewhere.mkdir()
    other = scan_csv(
        elsewhere,
        "customer_id,label",
        [f"{value},x" for value in IDENTIFIERS[::-1]],
        **LIMITED,
    )
    stale = analyses.deep.model_copy(update={"base": plan_base(other)})

    _unchanged(result, analyses.model_copy(update={"deep": stale}))
    # The caller that vouches for the document skips the check.
    assert _pair(
        refine(_first(result), analyses.model_copy(update={"deep": stale}))
    ) == UNIQUE_ID


@pytest.mark.parametrize("status", ["failed", "skipped", "limited"])
def test_an_analysis_that_did_not_complete_proves_nothing(tmp_path, status):
    result, analyses = _second_pass(tmp_path, "customer_id", IDENTIFIERS)
    items = [
        item.model_copy(update={"status": status})
        if item.analyzer == "exact_distinct"
        else item
        for item in analyses.deep.analyses
    ]

    _unchanged(
        result,
        analyses.model_copy(
            update={"deep": analyses.deep.model_copy(update={"analyses": items})}
        ),
    )


def test_a_stopped_count_is_a_lower_bound_and_proves_nothing(tmp_path):
    result, analyses = _second_pass(tmp_path, "customer_id", IDENTIFIERS)
    stopped = DistinctLimited(values_read=120, lower_bound=120)
    items = [
        item.model_copy(update={"result": stopped})
        if item.analyzer == "exact_distinct"
        else item
        for item in analyses.deep.analyses
    ]

    _unchanged(
        result,
        analyses.model_copy(
            update={"deep": analyses.deep.model_copy(update={"analyses": items})}
        ),
    )


def test_a_count_of_other_values_than_the_field_has_is_incompatible(tmp_path):
    result, analyses = _second_pass(tmp_path, "customer_id", IDENTIFIERS)
    items = []
    for item in analyses.deep.analyses:
        if item.analyzer == "exact_distinct":
            counted = item.result.model_copy(update={"values": item.result.values - 1})
            item = item.model_copy(update={"result": counted})
        items.append(item)

    _unchanged(
        result,
        analyses.model_copy(
            update={"deep": analyses.deep.model_copy(update={"analyses": items})}
        ),
    )


def test_the_analysis_of_another_field_is_not_read(tmp_path):
    result, analyses = _second_pass(tmp_path, "customer_id", IDENTIFIERS)
    items = [
        item.model_copy(update={"field": "f99"})
        if item.analyzer == "exact_distinct"
        else item
        for item in analyses.deep.analyses
    ]

    _unchanged(
        result,
        analyses.model_copy(
            update={"deep": analyses.deep.model_copy(update={"analyses": items})}
        ),
    )


# --- The conditions of Unique ID, as in the first pass -----------------------------


def test_a_missing_position_keeps_the_id_even_if_the_present_values_are_distinct(
    tmp_path,
):
    cells = [*IDENTIFIERS[:100], " ", *IDENTIFIERS[100:]]
    result, analyses = _second_pass(tmp_path, "customer_id", cells)

    assert _first(result).missing.count == 1
    _unchanged(result, analyses)


def test_a_value_the_trim_changes_keeps_the_id_and_the_count_is_context(tmp_path):
    # Distinct as written, so ``exact_distinct`` says unique; after the trim two
    # of them are one value ("A" and " A "), which the original count cannot see.
    cells = [f" {value}" for value in IDENTIFIERS[:150]] + IDENTIFIERS[:150]
    result, analyses = _second_pass(tmp_path, "customer_id", cells)

    refined = _refined(result, analyses)

    assert _pair(refined) == ID
    assert "observed_unique" not in refined.traits
    context = [item for item in refined.evidence if item.id == "exact_distinct.distinct"]
    assert [item.role for item in context] == ["context"]


def test_values_the_trim_changes_stay_unique_when_the_trim_is_off(tmp_path):
    cells = [f" {value}" for value in IDENTIFIERS[:150]] + IDENTIFIERS[:150]
    result, analyses = _second_pass(
        tmp_path, "customer_id", cells, normalization={"trim": False}
    )

    assert _pair(_refined(result, analyses)) == UNIQUE_ID


def test_a_field_under_a_json_array_stays_an_id(tmp_path):
    rows = [{"orders": [{"id": f"a{n}"}, {"id": f"b{n}"}]} for n in range(60)]
    source = write_json(tmp_path, "data.json", rows)
    result = scan(source, config=ScanConfig.model_validate(LIMITED))
    plan = forced_plan(result)
    analyses = _analyses(run_second_pass(result, source, plan))
    identifier = next(
        item for item in result.datasets[0].fields if item.name == "id"
    )

    assert _pair(identifier.classification) == ID
    assert any(
        item.analyzer == "exact_distinct" and item.field == identifier.id
        for item in analyses.deep.analyses
    )
    assert refine(identifier, analyses, dataset=result.datasets[0].id) == (
        identifier.classification
    )


def test_a_json_key_with_a_limited_cardinality_becomes_a_unique_id(tmp_path):
    rows = [{"customer": {"id": f"u{n}"}} for n in range(120)]
    source = write_json(tmp_path, "data.json", rows)
    result = scan(source, config=ScanConfig.model_validate(LIMITED))
    analyses = _analyses(run_second_pass(result, source, forced_plan(result)))
    identifier = next(item for item in result.datasets[0].fields if item.name == "id")

    refined = refine(
        identifier, analyses, dataset=result.datasets[0].id, base=plan_base(result)
    )

    assert _pair(identifier.classification) == ID
    assert _pair(refined) == UNIQUE_ID


# --- Without the source, with any number of workers --------------------------------


def test_the_refinement_needs_no_source_and_is_the_same_with_one_or_more_workers(
    tmp_path,
):
    rows = [f"C{n:05d},{n * 1.37:.2f},K{n % 700:03d}" for n in range(4_000)]
    header = "customer_id,amount,code\n"
    source = write_text(tmp_path, "data.csv", header + "\n".join(rows) + "\n")
    config = ScanConfig.model_validate(LIMITED)
    # The workers of the Scan and of the second pass: the exact sets stay in the
    # process, the routes of the other columns are shared.
    runs = []
    for scan_workers, deep_workers in ((1, 1), (2, 3)):
        result = scan(source, config=config, workers=scan_workers)
        outcome = run_second_pass(
            result, source, forced_plan(result), workers=deep_workers
        )
        runs.append(
            build_profile(
                result, ReportConfig(scan=result.config), analyses=_analyses(outcome)
            )
        )
    # The Report is built from its documents alone.
    source.unlink()

    columns = [profile.report.datasets[0].columns for profile in runs]
    classifications = [
        [column.classification.model_dump(mode="json") for column in dataset]
        for dataset in columns
    ]
    assert classifications[0] == classifications[1]
    assert _pair(columns[0][0].classification) == UNIQUE_ID


def test_a_complete_count_is_used_even_when_another_result_of_the_field_stopped(
    tmp_path,
):
    result, analyses = _second_pass(tmp_path, "customer_id", IDENTIFIERS)
    complete = next(
        item for item in analyses.deep.analyses if item.analyzer == "exact_distinct"
    )
    stopped = complete.model_copy(update={"status": "limited", "key": "other"})
    items = [stopped, *analyses.deep.analyses]

    refined = _refined(
        result,
        analyses.model_copy(
            update={"deep": analyses.deep.model_copy(update={"analyses": items})}
        ),
    )

    assert _pair(refined) == UNIQUE_ID


def test_every_type_of_the_catalogue_has_a_label():
    from tabalyst.report_labels import FAMILY_LABELS, TYPE_LABELS
    from tabalyst.scanner.classify.catalog import FAMILIES

    pairs = {f"{f.code}/{t}" for f in FAMILIES for t in f.types}

    assert set(TYPE_LABELS) == pairs
    assert {f.code for f in FAMILIES} == set(FAMILY_LABELS)

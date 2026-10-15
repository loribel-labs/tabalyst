# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The targets that stand on the exact tables of the second pass (design 20.15, lot S4):
the values a detector leaves out, the values of a column the first pass could not list
and the values no pattern reads."""

from planner_helpers import scan_csv
from second_pass_helpers import deep_csv
from smart_helpers import report

from tabalyst.config import SmartSettings
from tabalyst.scanner.smart import plan_sampling

# The first pass lists 100 values at most, as in the configuration of the examples.
FEW = {
    "limits": {"max_samples": 100, "max_listed_frequencies": 100},
    "exposure": {"sensitive_values": "show"},
}


def _assert_faithful(document):
    assert [e.id for e in document.targets if e.status == "unresolved"] == []
    assert document.coverage.verification.disagreed == []
    assert [e.id for e in document.targets if e.reason == "not_observed"] == []


def scan_and_plan(directory, header, rows):
    """The plan of a file with its second pass."""
    result, _, outcome = deep_csv(directory, header, rows, **FEW)
    return plan_sampling(result, deep=outcome.document)


def _kinds(plan, kind):
    return [t for t in plan.targets if t.predicate.kind == kind]


def _sample_cells(selection, column):
    return {row[column] for row in selection.rows}


def test_each_value_a_detector_leaves_out_is_a_target_found_in_a_small_sample(tmp_path):
    rows = [f"user{i}@mail.example,{i % 7}" for i in range(600)]
    rows[10] = "us er10@mail.example,3"
    rows[200] = "user200@mail.exa mple,4"
    _, plan, selection, document = report(tmp_path, "email,k", rows, 40, **FEW)

    _assert_faithful(document)
    targets = _kinds(plan, "residual_value")
    assert sorted(t.frequency.count for t in targets) == [1, 1]
    assert all(t.evidence == "second_pass" and t.needs == ["scan", "second_pass"] for t in targets)
    assert {rows[i].split(",")[0] for i in (10, 200)} <= _sample_cells(selection, 0)


def test_no_residual_target_without_the_second_pass(tmp_path):
    rows = [f"user{i}@mail.example" for i in range(600)]
    rows[10] = "us er10@mail.example"
    result = scan_csv(tmp_path, "email", rows)

    assert _kinds(plan_sampling(result), "residual_value") == []


def test_a_column_the_first_pass_could_not_list_gets_a_target_per_value_from_the_exact_table(
    tmp_path,
):
    rows = [f"C{i},town{i % 150}" for i in range(900)]
    rows[7] = "C7,Zzyzx"
    rows[8] = "C8,Zz yzx"
    _, plan, selection, document = report(tmp_path, "code,town", rows, 400, **FEW)

    _assert_faithful(document)
    values = [t for t in _kinds(plan, "value_equals") if t.displays == ["town"]]
    assert len(values) == 152
    assert all(t.predicate.source == "second_pass" and t.obligation == "optional" for t in values)
    assert all(t.weight.base == 2.0 for t in values)
    catalog = next(c for c in plan.catalogs if c.display == "town" and c.family == "low_cardinality")
    assert catalog.guarantee == "catalog_complete" and catalog.targets == 152
    assert {"Zzyzx", "Zz yzx"} <= _sample_cells(selection, 1)


def test_the_exact_table_is_ignored_above_max_exact_values(tmp_path):
    rows = [f"C{i},town{i % 150}" for i in range(900)]
    result, _, outcome = deep_csv(tmp_path, "code,town", rows, **FEW)

    plan = plan_sampling(result, deep=outcome.document, settings=SmartSettings(max_exact_values=100))

    assert [t for t in _kinds(plan, "value_equals") if t.displays == ["town"]] == []


def test_values_no_pattern_reads_are_a_target_when_only_the_second_pass_sees_them(tmp_path):
    rows = [f"AB-{1000 + i}" for i in range(3000)]
    rows[300] = "AB/1300"
    rows[600] = "AB/1600"
    _, plan, selection, document = report(tmp_path, "code", rows, 60, **FEW)

    _assert_faithful(document)
    [other] = _kinds(plan, "pattern_other")
    assert other.frequency.count == 2 and other.frequency.method == "pattern_validation"
    assert _sample_cells(selection, 0) & {"AB/1300", "AB/1600"}


def test_a_numeric_column_with_an_exact_table_keeps_its_extremes_and_signs(tmp_path):
    rows = [f"C{i},{(i % 300) - 5}" for i in range(900)]
    result, _, outcome = deep_csv(tmp_path, "code,qty", rows, **FEW)

    plan = plan_sampling(result, deep=outcome.document)

    qty = [t for t in plan.targets if t.displays == ["qty"]]
    kinds = {t.predicate.kind for t in qty}
    assert "value_equals" in kinds
    assert {"numeric_min", "numeric_max", "numeric_sign"} <= kinds


def _emails(invalid: int, rows: int = 600) -> list[str]:
    values = [f"user{i}@mail.example" for i in range(rows)]
    for i in range(invalid):
        values[5 + 7 * i] = f"us er{i}@mail.example"
    return values


def test_a_table_of_invalid_values_that_fits_is_listed_whole_and_a_truncated_one_is_not(tmp_path):
    (tmp_path / "few").mkdir()
    (tmp_path / "many").mkdir()
    few = scan_and_plan(tmp_path / "few", "email", _emails(15))
    many = scan_and_plan(tmp_path / "many", "email", _emails(30))

    assert len(_kinds(few, "residual_value")) == 15
    assert _kinds(many, "residual_value") == []


def test_values_that_are_most_of_a_column_are_its_format_and_not_residual_targets(tmp_path):
    rows = _emails(0, 10)
    rows[1], rows[2], rows[3] = "a b@mail.example", "c d@mail.example", "e f@mail.example"

    assert _kinds(scan_and_plan(tmp_path, "email", rows), "residual_value") == []


def test_the_invalid_values_of_a_whole_file_have_a_budget(tmp_path):
    header = ",".join(f"mail{c}" for c in range(8))
    columns = [_emails(15) for _ in range(8)]
    rows = [",".join(column[i] for column in columns) for i in range(600)]

    plan = scan_and_plan(tmp_path, header, rows)

    assert len(_kinds(plan, "residual_value")) == 100


def test_the_empty_cells_of_a_column_with_an_exact_table_are_a_target_of_the_catalog(tmp_path):
    rows = [f"C{i},town{i % 150}" for i in range(900)]
    rows[40] = "C40,"
    rows[41] = "C41,"

    plan = scan_and_plan(tmp_path, "code,town", rows)

    [empty] = [t for t in _kinds(plan, "value_missing") if t.displays == ["town"]]
    assert empty.frequency.count == 2
    catalog = next(c for c in plan.catalogs if c.display == "town" and c.family == "low_cardinality")
    assert catalog.targets == 150 + 1 and catalog.guarantee == "catalog_complete"

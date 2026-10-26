# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The criteria of the planner for the uniqueness of an identifier (Unique ID lot 8, UID-011,
design 20.42): when the two Deep analyses of the plan are chosen without being asked for."""

import csv

from tabalyst import scan
from tabalyst.config import CopySettings, DeepSettings
from tabalyst.scanner import ScanConfig
from tabalyst.scanner.planner import default_budgets, default_registry, plan_analyses
from tabalyst.scanner.secondpass import run_second_pass
from tabalyst.scanner.secondpass.document import analysis_key

COPIES = "duplicate_rows_count"
ANALYTICAL = "analytical_distinct"


def write_csv(directory, name, rows, header):
    path = directory / name
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\r\n")
        writer.writerow(header)
        writer.writerows(rows)
    return path


def with_copies(total, copies, *, id_of=lambda i: f"K{i:06d}"):
    """``total`` rows of which the last ``copies`` repeat an earlier row."""
    distinct = total - copies
    rows = [(id_of(i), f"a{i}", f"b{i}") for i in range(distinct)]
    return rows + [rows[(7 * k) % distinct] for k in range(copies)]


def scanned(source, **limits):
    config = ScanConfig.model_validate({"limits": limits}) if limits else None
    return scan(source, config=config)


def planned(result, **options):
    return plan_analyses(result, registry=default_registry().runnable(), **options)


def candidate(plan, analyzer, field=None):
    found = [
        c for c in plan.candidates if c.analyzer == analyzer and (field is None or c.field == field)
    ]
    assert len(found) == 1
    return found[0]


def limited_copies(tmp_path, header=("id", "a", "b"), rows=None):
    source = write_csv(tmp_path, "t.csv", rows or with_copies(5_000, 1_500), list(header))
    result = scanned(source, max_tracked_records=1_000)
    assert result.datasets[0].records.duplicates.count.status == "limited"
    return source, result


def messy_ids(total=3_000, copies=100):
    """Identifiers some of which carry spaces, and ``copies`` that repeat one only under trim."""
    rows = []
    for i in range(total):
        value = f"ID{i}"
        if i % 7 == 0:
            value = f"  {value}  "
        rows.append((value, f"a{i}", f"b{i}"))
    rows += [(f" ID{i} ", "again", "again") for i in range(1, copies + 1) if i % 7]
    return rows


# ------------------------------------------------------------------ the count of the copies


def test_the_copies_of_rows_are_counted_by_itself_for_an_identifier_the_scan_could_only_bound(
    tmp_path,
):
    _, result = limited_copies(tmp_path)

    chosen = candidate(planned(result), COPIES)

    assert chosen.selection.state == "selected"
    assert chosen.selection.reason == "automatic"
    assert chosen.utility.reasons == ["identifier_copies"]


def test_the_copies_are_not_counted_when_the_scan_already_has_them(tmp_path):
    source = write_csv(tmp_path, "t.csv", with_copies(2_000, 300), ["id", "a", "b"])

    chosen = candidate(planned(scanned(source)), COPIES)

    assert chosen.selection.state == "already_satisfied"


def test_the_copies_are_not_counted_for_a_table_without_an_identifier(tmp_path):
    _, result = limited_copies(tmp_path, header=("x", "y", "z"))

    chosen = candidate(planned(result), COPIES)

    assert (chosen.selection.state, chosen.selection.reason) == ("rejected", "low_utility")


def test_a_unique_id_needs_no_count_of_the_copies(tmp_path):
    rows = [(f"K{i:06d}", f"a{i}", f"b{i}") for i in range(5_000)]
    source = write_csv(tmp_path, "t.csv", rows, ["id", "a", "b"])
    result = scanned(source, max_tracked_records=1_000)
    assert result.datasets[0].fields[0].classification.type == "unique_id"

    chosen = candidate(planned(result), COPIES)

    assert (chosen.selection.state, chosen.selection.reason) == ("rejected", "low_utility")


def test_an_identifier_with_a_missing_value_is_a_candidate_too(tmp_path):
    # The copies of the rows that have an ID are counted apart (lot 10), so the column can conclude.
    rows = with_copies(5_000, 1_500)
    rows[10] = ("", rows[10][1], rows[10][2])
    _, result = limited_copies(tmp_path, rows=rows)

    chosen = candidate(planned(result), COPIES)

    assert (chosen.selection.state, chosen.selection.reason) == ("selected", "automatic")
    assert chosen.utility.reasons == ["identifier_copies"]


def test_the_copies_wait_for_a_distinct_count_that_is_known_or_planned(tmp_path):
    # Values too long for an exact set: no distinct count can come, so the copies settle nothing.
    rows = [(f"{'x' * 70}{i:06d}", f"a{i}", f"b{i}") for i in range(1_000)]
    rows += rows[:300]
    source = write_csv(tmp_path, "t.csv", rows, ["id", "a", "b"])
    result = scanned(source, max_tracked_records=500, max_distinct_per_field=200, max_samples=100)
    assert result.datasets[0].records.duplicates.count.status == "limited"

    chosen = candidate(planned(result), COPIES)

    assert (chosen.selection.state, chosen.selection.reason) == ("rejected", "distinct_unknown")


def test_the_copies_follow_the_exact_count_chosen_for_the_same_identifier(tmp_path):
    # The Scan lost its table of values: the exact count is planned, and the copies with it.
    source = write_csv(tmp_path, "t.csv", with_copies(5_000, 1_500), ["id", "a", "b"])
    result = scanned(source, max_tracked_records=1_000, max_distinct_per_field=200, max_samples=100)
    assert result.datasets[0].fields[0].values.cardinality.status == "limited"

    plan = planned(result)

    assert candidate(plan, "exact_distinct", "column_1").selection.state == "selected"
    assert candidate(plan, COPIES).selection.state == "selected"


def test_a_valid_dedup_proof_makes_the_count_useless(tmp_path):
    _, result = limited_copies(tmp_path)

    chosen = candidate(planned(result, proved_copies=frozenset({"rows"})), COPIES)

    assert chosen.selection.state == "already_satisfied"
    assert chosen.selection.reason == "copies_proved"


def test_an_exact_scan_count_is_named_before_a_proof(tmp_path):
    source = write_csv(tmp_path, "t.csv", with_copies(2_000, 300), ["id", "a", "b"])

    chosen = candidate(planned(scanned(source), proved_copies=frozenset({"rows"})), COPIES)

    assert chosen.selection.reason == "copies_exact"


def test_a_proof_answers_even_a_count_that_was_asked_for(tmp_path):
    from tabalyst.scanner.planner import AnalysisRequest

    _, result = limited_copies(tmp_path)

    plan = planned(
        result, requests=[AnalysisRequest(COPIES)], proved_copies=frozenset({"rows"})
    )

    # Satisfied beats requested everywhere in the planner: a proof is an answer.
    assert candidate(plan, COPIES).selection.state == "already_satisfied"


def test_a_table_that_would_not_fit_the_automatic_memory_is_left_to_a_forced_pass(tmp_path):
    _, result = limited_copies(tmp_path)
    budgets = default_budgets().model_copy(update={"automatic_memory_bytes": 1 << 20})

    automatic = candidate(planned(result, budgets=budgets), COPIES)
    forced = candidate(planned(result, budgets=budgets, forced=True), COPIES)

    assert (automatic.selection.state, automatic.selection.reason) == ("rejected", "budget")
    assert forced.selection.state == "selected"


def test_the_cpu_class_of_the_count_is_that_of_a_cell_of_the_record(tmp_path):
    _, wide = limited_copies(tmp_path)
    narrow_rows = [(i, f"K{i}") for i in range(4_000)] + [(i, f"K{i}") for i in range(1_200)]
    narrow_source = write_csv(tmp_path, "narrow.csv", narrow_rows, ["id", "a"])
    narrow = scanned(narrow_source, max_tracked_records=1_000)
    assert narrow.datasets[0].records.duplicates.count.status == "limited"

    wide_candidate = candidate(planned(wide), COPIES)
    narrow_candidate = candidate(planned(narrow), COPIES)

    # Three columns: 2,000 ns a cell. Two columns: 3,000, above the automatic limit.
    assert wide_candidate.costs.cpu == "moderate"
    assert narrow_candidate.costs.cpu == "high"
    assert narrow_candidate.selection.reason == "cpu_class"
    # The time estimate still counts the record.
    assert wide_candidate.costs.cell_ns == narrow_candidate.costs.cell_ns


def test_a_forced_pass_on_a_small_wide_table_does_not_ask_for_the_count(tmp_path):
    _, result = limited_copies(tmp_path)

    plan = planned(result, forced=True)

    assert "cpu_over_automatic" not in plan.summary.beyond_automatic


# ----------------------------------------------------------- the exact count of the analytical values


def test_the_analytical_count_is_chosen_by_itself_for_an_identifier_a_stage_changed(tmp_path):
    source = write_csv(tmp_path, "m.csv", messy_ids(), ["id", "a", "b"])
    result = scanned(source, max_distinct_per_field=200, max_samples=100)

    chosen = candidate(planned(result), ANALYTICAL, "column_1")

    assert chosen.selection.state == "selected"
    assert chosen.selection.reason == "automatic"
    assert chosen.utility.reasons == ["identifier_uniqueness"]


def test_the_analytical_count_is_not_chosen_by_itself_for_another_column(tmp_path):
    source = write_csv(tmp_path, "m.csv", messy_ids(), ["code_x", "a", "b"])
    result = scanned(source, max_distinct_per_field=200, max_samples=100)
    assert result.datasets[0].fields[0].classification.family != "identifier"

    chosen = candidate(planned(result), ANALYTICAL, "column_1")

    assert (chosen.selection.state, chosen.selection.reason) == ("rejected", "low_utility")


def test_the_analytical_and_the_copies_come_in_one_automatic_plan(tmp_path):
    rows = messy_ids() + messy_ids()[:1_200]
    source = write_csv(tmp_path, "m.csv", rows, ["id", "a", "b"])
    result = scanned(
        source, max_tracked_records=1_000, max_distinct_per_field=200, max_samples=100
    )

    plan = planned(result)

    assert candidate(plan, ANALYTICAL, "column_1").selection.state == "selected"
    assert candidate(plan, COPIES).selection.state == "selected"


# -------------------------------------------------------------------------- cache and versions


def run(source, result, previous=None, deep=None, **options):
    plan = planned(result, deep=deep, **options)
    return run_second_pass(result, source, plan, settings=deep, previous=previous), plan


def test_a_second_run_reads_nothing_when_the_results_are_stored(tmp_path):
    source, result = limited_copies(tmp_path)

    first, _ = run(source, result)
    second, _ = run(source, result, previous=first.document)

    assert first.read_source is True
    assert second.read_source is False
    assert COPIES in {a.analyzer for a in second.document.analyses}
    assert second.reused


def test_a_stopped_count_of_the_copies_is_reused_at_the_same_ceilings(tmp_path):
    source, result = limited_copies(tmp_path)
    deep = DeepSettings(copies=CopySettings(max_rows=4_500))

    first, _ = run(source, result, deep=deep)
    second, _ = run(source, result, previous=first.document, deep=deep)

    stopped = next(a for a in first.document.analyses if a.analyzer == COPIES)
    assert stopped.status == "limited"
    assert second.read_source is False
    assert next(a for a in second.document.analyses if a.analyzer == COPIES) == stopped


def test_a_stopped_count_is_computed_again_when_a_ceiling_changes(tmp_path):
    source, result = limited_copies(tmp_path)

    first, _ = run(source, result, deep=DeepSettings(copies=CopySettings(max_rows=4_500)))
    second, _ = run(source, result, previous=first.document, deep=DeepSettings())

    entry = next(a for a in second.document.analyses if a.analyzer == COPIES)
    assert second.read_source is True
    assert entry.status == "complete"


def test_the_version_of_the_calculation_is_part_of_the_key(tmp_path):
    from tabalyst.dedup.calculation import CALCULATION_VERSION

    _, result = limited_copies(tmp_path)
    chosen = candidate(planned(result), COPIES)
    older = chosen.model_copy(update={"analyzer_version": CALCULATION_VERSION + 1})

    assert chosen.analyzer_version == CALCULATION_VERSION
    assert analysis_key(planned(result).base, chosen) != analysis_key(planned(result).base, older)


def test_the_normalization_of_the_scan_is_part_of_the_key_of_the_analytical_count(tmp_path):
    source = write_csv(tmp_path, "m.csv", messy_ids(), ["id", "a", "b"])
    kept = scanned(source, max_distinct_per_field=200, max_samples=100)
    config = ScanConfig.model_validate(
        {
            "limits": {"max_distinct_per_field": 200, "max_samples": 100},
            "normalization": {"trim": False},
        }
    )
    changed = scan(source, config=config)

    first = candidate(planned(kept), ANALYTICAL, "column_1")
    second = candidate(planned(changed), ANALYTICAL, "column_1")

    assert analysis_key(planned(kept).base, first) != analysis_key(planned(changed).base, second)


def test_a_stored_document_of_another_scan_is_not_reused(tmp_path):
    source, result = limited_copies(tmp_path)
    first, _ = run(source, result)
    with source.open("a", encoding="utf-8", newline="") as stream:
        stream.write("K999999,a,b\r\n")
    other = scanned(source, max_tracked_records=1_000)

    second, _ = run(source, other, previous=first.document)

    assert second.read_source is True
    assert not second.reused


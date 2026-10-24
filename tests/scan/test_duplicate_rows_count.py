# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The analyzer ``duplicate_rows_count``: the extra copies of whole rows, counted by the engine of
Dedup in the second pass (Unique ID lot 6, design 20.40)."""

import csv

import pytest

from tabalyst import scan
from tabalyst.config import CopySettings, DeepSettings
from tabalyst.scanner import ScanConfig
from tabalyst.scanner.planner import (
    AnalysisRequest,
    default_registry,
    plan_analyses,
)
from tabalyst.scanner.secondpass import run_second_pass
from tabalyst.scanner.secondpass.models import DuplicateRowsResult
from tabalyst.source_guard import StaleSource

ANALYZER = "duplicate_rows_count"
WIDE = ["id", "c1", "c2"]


def generated_rows(total, copies, *, width=3):
    """``total`` rows of which the last ``copies`` repeat, in turn, one of the first rows."""
    distinct = total - copies
    rows = [(str(i), *(f"value {i} {c}" for c in range(1, width))) for i in range(distinct)]
    return rows + [rows[(7 * k) % distinct] for k in range(copies)]


def write_csv(directory, name, rows, *, header):
    path = directory / name
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\r\n")
        writer.writerow(header)
        writer.writerows(rows)
    return path


def copies_of(source):
    """The extra copies, counted by a plain set (the oracle)."""
    with source.open(encoding="utf-8", newline="") as stream:
        rows = [tuple(row) for row in csv.reader(stream)][1:]
    return len(rows) - len(set(rows))
REQUEST = [AnalysisRequest(ANALYZER)]


def _scan(source, **limits):
    config = ScanConfig.model_validate({"limits": limits}) if limits else None
    return scan(source, config=config)


def _plan(result, deep=None, **options):
    return plan_analyses(
        result,
        requests=REQUEST,
        registry=default_registry().runnable(),
        deep=deep,
        **options,
    )


def _candidate(plan):
    found = [c for c in plan.candidates if c.analyzer == ANALYZER]
    assert len(found) == 1
    return found[0]


def _limited_csv(tmp_path, rows=5_000, copies=1_500):
    source = write_csv(tmp_path, "limited.csv", generated_rows(rows, copies, width=3), header=WIDE)
    result = _scan(source, max_tracked_records=1_000)
    assert result.datasets[0].records.duplicates.count.status == "limited"
    return source, result


def _run(source, result, deep=None, **options):
    plan = _plan(result, deep)
    return run_second_pass(result, source, plan, settings=deep, **options), plan


def test_a_scan_that_counted_the_copies_exactly_needs_no_second_reading(tmp_path):
    source = write_csv(tmp_path, "exact.csv", generated_rows(2_000, 300, width=3), header=WIDE)

    candidate = _candidate(_plan(_scan(source)))

    assert candidate.selection.state == "already_satisfied"
    assert candidate.selection.reason == "copies_exact"
    assert candidate.selection.satisfied_by == "datasets/rows/records/duplicates"


def test_a_scan_that_switched_the_count_off_is_not_overridden(tmp_path):
    source = write_csv(tmp_path, "off.csv", generated_rows(500, 50, width=3), header=WIDE)
    result = scan(source, config=ScanConfig.model_validate({"records": {"duplicates": False}}))

    candidate = _candidate(_plan(result))

    assert candidate.selection.state == "rejected"
    assert candidate.applicability.reasons == ["duplicates_disabled"]
    # Even a forced second pass does not turn the count back on.
    forced = plan_analyses(result, forced=True, registry=default_registry().runnable())
    assert next(c for c in forced.candidates if c.analyzer == ANALYZER).selection.state == "rejected"


def test_a_source_that_is_not_a_csv_has_no_candidate(tmp_path):
    source = tmp_path / "records.jsonl"
    source.write_text('{"id": 1}\n{"id": 1}\n', encoding="utf-8")

    plan = _plan(scan(source))

    assert not [c for c in plan.candidates if c.analyzer == ANALYZER]


def test_the_analyzer_is_never_chosen_by_itself(tmp_path):
    _, result = _limited_csv(tmp_path)

    automatic = plan_analyses(result, registry=default_registry().runnable())
    asked = _plan(result)
    forced = plan_analyses(result, forced=True, registry=default_registry().runnable())

    chosen = lambda plan: next(c for c in plan.candidates if c.analyzer == ANALYZER)
    assert chosen(automatic).selection.state == "rejected"
    assert chosen(automatic).selection.reason == "low_utility"
    assert chosen(asked).selection.state == "selected"
    assert chosen(asked).selection.reason == "requested"
    assert chosen(forced).selection.reason == "forced"


def test_the_plan_carries_the_ceilings_and_a_memory_that_respects_them(tmp_path):
    _, result = _limited_csv(tmp_path)
    deep = DeepSettings(copies=CopySettings(memory_mb=8, disk_mb=16, max_rows=1_000_000))

    candidate = _candidate(_plan(result, deep))

    assert candidate.method == "extra_copies"
    assert candidate.parameters == {"memory_mb": 8, "disk_mb": 16, "max_rows": 1_000_000}
    assert candidate.execution.requires_source is True
    assert candidate.costs is not None
    assert candidate.costs.memory.max <= 8 * (1 << 20) + 1_000_000


def test_the_second_pass_counts_what_dedup_counts(tmp_path):
    source, result = _limited_csv(tmp_path)
    exact = copies_of(source)

    outcome, _ = _run(source, result)

    entry = next(a for a in outcome.document.analyses if a.analyzer == ANALYZER)
    assert entry.status == "complete"
    assert isinstance(entry.result, DuplicateRowsResult)
    assert entry.result.accuracy == "exact"
    assert entry.result.extra_copies == exact == 1_500
    assert entry.result.distinct_rows == 5_000 - exact
    assert entry.result.records == result.datasets[0].record_count
    assert entry.result.identity == "full_decoded_csv_row_v1"
    assert entry.result.source_sha256 == result.source.sha256
    assert outcome.read_source is True
    assert outcome.document.run.source_verified is True


def test_the_result_does_not_depend_on_the_number_of_workers(tmp_path):
    source, result = _limited_csv(tmp_path)

    one, _ = _run(source, result, workers=1)
    several, _ = _run(source, result, workers=4)

    results = [
        next(a for a in outcome.document.analyses if a.analyzer == ANALYZER).result
        for outcome in (one, several)
    ]
    assert results[0] == results[1]


def test_a_ceiling_makes_the_result_limited_with_its_reason(tmp_path):
    source, result = _limited_csv(tmp_path)
    exact = copies_of(source)
    deep = DeepSettings(copies=CopySettings(max_rows=4_500))

    outcome, _ = _run(source, result, deep)

    entry = next(a for a in outcome.document.analyses if a.analyzer == ANALYZER)
    assert entry.status == "limited" and entry.reason == "row_limit"
    assert entry.result.accuracy == "lower_bound"
    assert entry.result.records == 4_500
    assert entry.result.source_sha256 is None
    assert 0 < entry.result.extra_copies < exact
    assert outcome.document.status == "partial"


def test_the_ceilings_are_part_of_the_key_of_a_result(tmp_path):
    source, result = _limited_csv(tmp_path)

    first, _ = _run(source, result)
    second, _ = _run(source, result, DeepSettings(copies=CopySettings(max_rows=4_500)))

    keys = [
        next(a for a in o.document.analyses if a.analyzer == ANALYZER).key for o in (first, second)
    ]
    assert keys[0] != keys[1]


def test_a_stored_result_is_reused_without_reading_the_source_again(tmp_path):
    source, result = _limited_csv(tmp_path)
    first, plan = _run(source, result)

    again = run_second_pass(result, source, plan, previous=first.document)

    assert again.read_source is False
    assert again.reused == first.executed


def test_a_source_changed_since_the_scan_stops_the_pass(tmp_path):
    source, result = _limited_csv(tmp_path)
    plan = _plan(result)
    content = source.read_bytes()
    # The same size, another content: only the digest tells.
    source.write_bytes(content.replace(b"value 1 1", b"value 9 1", 1))

    with pytest.raises(StaleSource):
        run_second_pass(result, source, plan)


def test_a_stopped_count_does_not_claim_the_source_was_verified(tmp_path):
    source, result = _limited_csv(tmp_path)

    deep = DeepSettings(copies=CopySettings(max_rows=4_500))
    alone = _plan(result, deep, automatic=False)

    outcome = run_second_pass(result, source, alone, settings=deep)

    assert outcome.executed == ("duplicate_rows_count:rows:$",)
    assert outcome.document.run.source_read is True
    assert outcome.document.run.source_verified is False


def test_an_exact_count_alone_verifies_the_source(tmp_path):
    source, result = _limited_csv(tmp_path)

    outcome = run_second_pass(result, source, _plan(result, automatic=False))

    assert outcome.document.run.source_verified is True

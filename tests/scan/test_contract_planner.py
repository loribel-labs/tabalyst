# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contract of the planner (Scan and JSON plan, tests D01 to D03, requirements
PLAN-01 to PLAN-06).

The behavior is specified in ``docs/dev/scan/design.md`` section 20.5. The
expectations are on the plan a Scan gives.
"""

import pytest
from planner_helpers import by_analyzer, scan_csv, unique_state_bytes, with_field

from tabalyst.scanner.models import Limited
from tabalyst.scanner.planner import default_budgets, plan_analyses
from tabalyst.scanner.planner.planner import PARSER_RESERVE_BYTES


@pytest.mark.scan_json_lot("6a")
def test_D01_an_enum_already_counted_needs_no_second_pass(tmp_path):
    values = [f"state_{index:02d}" for index in range(17)]
    result = scan_csv(tmp_path, "state", [values[i % 17] for i in range(500)])

    plan = plan_analyses(result)

    frequencies = by_analyzer(plan, "exact_frequencies")["state"]
    assert frequencies.selection.state == "already_satisfied"
    assert frequencies.selection.reason == "counts_complete"
    assert frequencies.selection.satisfied_by == "datasets/rows/fields/column_1/values/frequencies"
    distinct = by_analyzer(plan, "exact_distinct")["state"]
    assert distinct.selection.state == "already_satisfied"
    # Nothing selected reads the source: no second pass, no parser reserve.
    assert plan.summary.second_pass_required is False
    assert plan.common.requires_source is False
    assert plan.common.memory_bytes == 0
    assert all(not c.execution.requires_source for c in plan.candidates if c.selection.state == "selected")


@pytest.mark.scan_json_lot("6a")
def test_D02_three_costly_ids_never_exceed_the_shared_budget(tmp_path):
    rows = [f"A{n:07d},B{n:07d},C{n:07d}" for n in range(5_000)]
    result = scan_csv(
        tmp_path, "id_a,id_b,id_c", rows, limits={"max_distinct_per_field": 50}
    )
    ids = by_analyzer(plan_analyses(result), "exact_distinct")
    one = ids["id_a"].costs.memory.max
    assert ids["id_a"].selection.state == "selected"  # the default budget holds all three
    # A budget with room for the reading and one and a half sets.
    budget = default_budgets().model_copy(
        update={"memory_bytes": PARSER_RESERVE_BYTES + one + one // 2}
    )

    plan = plan_analyses(result, budgets=budget)

    selected = [c for c in by_analyzer(plan, "exact_distinct").values() if c.selection.state == "selected"]
    rejected = [c for c in by_analyzer(plan, "exact_distinct").values() if c.selection.state == "rejected"]
    assert len(selected) == 1
    assert {c.selection.reason for c in rejected} == {"budget"}
    assert plan.summary.memory.max <= budget.memory_bytes
    assert plan.summary.memory.max == PARSER_RESERVE_BYTES + unique_state_bytes(plan)


@pytest.mark.scan_json_lot("6a")
def test_D03_histogram_lengths_and_patterns_share_one_reading(tmp_path):
    rows = [f"{index * 7.31:.2f},AB-{index:04d}" for index in range(300)]
    result = scan_csv(
        tmp_path, "amount,code", rows, limits={"max_samples": 20, "max_distinct_per_field": 50}
    )
    # The length histogram of the code was not kept: as a Scan written with the
    # measure limited would be.
    result = with_field(
        result, "code", string_lengths=Limited(reason="distinct_limit", limit=50)
    )

    plan = plan_analyses(result)

    selected = {(c.analyzer, c.display) for c in plan.candidates if c.selection.state == "selected"}
    assert ("numeric_histogram", "amount") in selected
    assert ("length_distribution", "code") in selected
    assert ("pattern_validation", "code") in selected
    # One common reading, counted once whatever the number of analyses.
    assert plan.common.requires_source is True
    assert plan.common.memory_bytes == PARSER_RESERVE_BYTES
    assert plan.summary.memory.max == PARSER_RESERVE_BYTES + unique_state_bytes(plan)
    assert plan.summary.second_pass_required is True

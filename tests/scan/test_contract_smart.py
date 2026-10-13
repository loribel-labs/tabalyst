# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contract tests of the targets and the plan of a smart sample (plan tests E09,
E12 and E14; design 20.15, SMART-01 to SMART-04, SMART-10, SMART-13) and of the
selection of the rows (E10, E11, E13 and E15; design 20.16, SMART-05 to SMART-12)."""

import csv

import pytest
from planner_helpers import scan_csv
from second_pass_helpers import deep_csv, forced_plan
from smart_helpers import region_rows, report

from tabalyst.scanner.planner import plan_analyses
from tabalyst.scanner.smart import plan_sampling


def _sub(directory, name):
    path = directory / name
    path.mkdir()
    return path


NORMAL = [f"Region-{chr(65 + i)}" for i in range(13)]
SINGLETONS = [f"Regoin-typo-{i}" for i in range(10)]


def _regions(per_normal: int = 100) -> list[str]:
    rows = [f"{name},{i}" for name in NORMAL for i in range(per_normal)]
    rows += [f"{name},{i}" for i, name in enumerate(SINGLETONS)]
    return rows


def _region_targets(plan):
    field = next(c.field for c in plan.catalogs if c.display == "region")
    return [
        t
        for t in plan.targets
        if t.family == "low_cardinality" and t.fields == [field]
    ]


@pytest.mark.scan_json_lot("10a")
def test_E09_thirteen_normal_values_and_ten_singletons_are_twenty_three_mandatory_targets(
    tmp_path,
):
    result = scan_csv(tmp_path, "region,n", _regions())

    plan = plan_sampling(result, size=60)

    targets = _region_targets(plan)
    assert len(targets) == 23
    assert {t.predicate.kind for t in targets} == {"value_equals"}
    assert all(t.obligation == "mandatory" and t.feasibility == "ready" for t in targets)
    # The catalog is exhaustive, so a sample large enough can promise all 23.
    [catalog] = [
        c for c in plan.catalogs if c.display == "region" and c.family == "low_cardinality"
    ]
    assert (catalog.complete, catalog.guarantee, catalog.targets) == (
        True,
        "catalog_complete",
        23,
    )
    assert plan.size.mandatory_bound >= 23 and plan.size.requested == 60
    # A rare value weighs more than a frequent one (SMART-02), and the plan names
    # no value of the data (it points into the Scan).
    singles = [t for t in targets if t.frequency.count == 1]
    normals = [t for t in targets if t.frequency.count == 100]
    assert len(singles) == 10 and len(normals) == 13
    assert min(t.weight.value for t in singles) > max(t.weight.value for t in normals)
    text = plan.model_dump_json()
    assert not any(name in text for name in NORMAL + SINGLETONS)


@pytest.mark.scan_json_lot("10a")
def test_E12_an_incompletely_known_enum_promises_no_coverage_of_its_real_values(tmp_path):
    result = scan_csv(
        tmp_path,
        "region,n",
        _regions(),
        limits={"max_distinct_per_field": 20, "max_samples": 20},
    )

    plan = plan_sampling(result, size=60)

    targets = _region_targets(plan)
    assert 0 < len(targets) <= 20
    # Targets exist for the values the Scan saw, none of them is mandatory.
    assert all(t.obligation == "optional" for t in targets)
    [catalog] = [
        c for c in plan.catalogs if c.display == "region" and c.family == "low_cardinality"
    ]
    assert catalog.complete is False
    assert catalog.guarantee == "known_values_only"
    assert "domain_not_exhaustive" in catalog.reasons


@pytest.mark.scan_json_lot("10a")
def test_E14_targets_that_only_a_finished_enrichment_gives_announce_an_extra_pass(tmp_path):
    rows = [f"{i},{i * 3}" for i in range(1000)]
    result = scan_csv(tmp_path, "n,m", rows)
    enrichment = forced_plan(result)

    plain = plan_sampling(result)
    asked = plan_sampling(result, enrichment=enrichment)
    from_source = plan_sampling(result, enrichment=enrichment, scan_stored=False)

    def needed(plan):
        return [step.name for step in plan.passes.steps if step.needed]

    # Targets from the Scan alone: the sample reads the source once.
    assert plain.passes.total == 1 and needed(plain) == ["selection"]
    # A second pass asked for before the sample is announced, and what it adds.
    assert asked.passes.total == 2 and needed(asked) == ["second_pass", "selection"]
    assert asked.enrichment.awaiting and asked.enrichment.deep == "absent"
    assert {a.family for a in asked.enrichment.awaiting} == {"numeric"}
    # From a source with no Scan the three readings of the specification are named.
    assert from_source.passes.total == 3
    assert needed(from_source) == ["scan", "second_pass", "selection"]

    # The enrichment finished: it is used, and no extra pass is announced.
    folder = tmp_path / "done"
    folder.mkdir()
    done_scan, _, outcome = deep_csv(folder, "n,m", rows)
    done = plan_sampling(done_scan, deep=outcome.document, enrichment=plan_analyses(done_scan))
    assert done.enrichment.deep == "current" and done.enrichment.used > 0
    assert done.passes.total == 1
    bins = [t for t in done.targets if t.predicate.kind == "numeric_bin" and t.displays == ["n"]]
    assert bins and all(t.evidence == "second_pass" for t in bins)
    assert sum(t.frequency.count for t in bins) == 1000


@pytest.mark.scan_json_lot("10b")
def test_E10_a_sample_too_small_keeps_its_size_and_says_which_targets_it_misses(tmp_path):
    _, plan, selection, document = report(tmp_path, "region,n", region_rows(), 10)

    # Ten rows for 23 mandatory values: the size is respected, and the rarest
    # values, which weigh most (SMART-02), are the ones kept.
    assert len(selection.rows) == 10
    assert {row[0] for row in selection.rows} == set(SINGLETONS)
    coverage = document.coverage
    assert coverage.mandatory.defined == 23 and coverage.mandatory.covered == 10
    assert len(coverage.mandatory.missing) == 13
    assert {m.reason for m in coverage.missing} == {"size"}
    must = [m.weight for m in coverage.missing if m.obligation == "mandatory"]
    assert must == sorted(must, reverse=True) and len(must) == 13
    assert coverage.missing[0].obligation == "mandatory"
    assert document.selection.reserve.planned == 0
    assert plan.size.mandatory_bound >= 23


@pytest.mark.scan_json_lot("10b")
def test_E11_a_row_that_covers_several_targets_is_held_once_and_counts_for_each(tmp_path):
    # Two columns of three values each, almost always together: three rows can cover
    # the six values, and a row with a single new value is not worth one more.
    pairs = [("x", "p"), ("y", "q"), ("z", "r")]
    rows = [f"{a},{b},{i}" for i in range(300) for a, b in [pairs[i % 3]]]
    rows += ["x,q,901", "y,r,902", "z,p,903"]
    _, plan, selection, document = report(tmp_path, "a,b,n", rows, 3)

    assert len(selection.rows) == 3
    assert {row[0] for row in selection.rows} == {"x", "y", "z"}
    assert {row[1] for row in selection.rows} == {"p", "q", "r"}
    assert document.coverage.mandatory.covered == document.coverage.mandatory.defined == 6
    # A row is stored once however many targets hold it (SMART-05, SMART-08).
    assert document.selection.pool.candidate_rows <= len(plan.targets) * 2
    assert len({id(row) for row in selection.rows}) == 3


@pytest.mark.scan_json_lot("10b")
def test_E13_the_reserve_of_ordinary_rows_gives_way_to_targets_and_is_declared(tmp_path):
    _, plan, selection, document = report(tmp_path, "region,n", region_rows(), 100)

    # Room for everything: the reserve is the share the plan granted, plus the
    # slots that no target could use, and the report says so.
    reserve = document.selection.reserve
    assert reserve.planned == plan.reserve.rows_granted == 20
    assert reserve.taken == document.selection.by_reserve >= 20
    assert reserve.adjusted == (reserve.taken != reserve.planned)
    assert len(selection.rows) == 100
    assert "proportions_not_population" in document.statements
    assert "catalog_not_population" in document.statements
    assert document.coverage.scope == "target_catalog"

    # Short of room, the targets come first and the reserve is reduced (SMART-10).
    _, small, _, short = report(_sub(tmp_path, "short"), "region,n", region_rows(), 26)
    assert small.reserve.reduced_by_mandatory
    assert short.coverage.mandatory.covered == 23


@pytest.mark.scan_json_lot("10b")
def test_E15_long_rows_come_out_whole_and_never_as_a_preview(tmp_path):
    from tabalyst.config import SmartSettings
    from tabalyst.scanner.smart.execute import select_rows

    long_text = "é" * 40_000
    rows = [f"{name},{long_text}-{i}" for i, name in enumerate(["a", "b", "c"] * 4)]
    rows += [f"{name}{i},{long_text}" for i, name in enumerate(["u"] * 150)]
    result = scan_csv(tmp_path, "tag,text", rows)
    source = tmp_path / "data.csv"
    with source.open(encoding="utf-8", newline="") as stream:
        original = list(csv.reader(stream))[1:]

    plan = plan_sampling(result, size=20)
    selection = select_rows(result, source, plan)
    assert len(selection.rows) == 20
    assert all(row in original for row in selection.rows)
    assert any(len(row[1]) >= 40_000 for row in selection.rows)

    # A budget too small for a row never turns it into a shorter one: the rows the
    # pool cannot hold are refused and counted.
    tight = plan_sampling(result, size=20, settings=SmartSettings(max_candidate_bytes=1_000))
    refused = select_rows(result, source, tight)
    assert refused.outcome.refused_rows > 0
    assert refused.outcome.peak_bytes <= 1_000
    assert all(row in original for row in refused.rows)

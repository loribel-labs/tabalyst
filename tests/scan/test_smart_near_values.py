# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Rare values one edit away from a frequent one of the same column (design 20.39, lot S5)."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from planner_helpers import scan_csv
from second_pass_helpers import deep_csv

from tabalyst.config import SmartSettings
from tabalyst.scanner.smart import plan_sampling
from tabalyst.scanner.smart.evaluate import Evaluator
from tabalyst.scanner.smart.execute import select_rows
from tabalyst.scanner.smart.models import SamplingPlan, Target
from tabalyst.scanner.smart.near import NearGroup, fold, near_groups, one_edit
from tabalyst.scanner.smart.result import build_document

CITIES = [("Longueuil", 120), ("Laval", 100), ("Montreal", 300)]


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Longueuil", "Longueuuil"),  # a letter doubled (an insertion)
        ("Longueuil", "Longueil"),  # a letter dropped
        ("Laval", "Lavad"),  # a letter replaced
        ("Montreal", "Mnotreal"),  # two neighbouring letters exchanged
        ("ab", "b"),
        ("ab", "a"),
    ],
)
def test_one_edit_is_an_insertion_a_deletion_a_substitution_or_an_exchange(a: str, b: str) -> None:
    assert one_edit(a, b) and one_edit(b, a)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Laval", "Laval"),  # the same text
        ("Laval", "Lavxx"),  # two substitutions
        ("Laval", "Lavalxx"),  # two insertions
        ("abcd", "cbad"),  # an exchange of characters that are not neighbours
        ("abcd", "badc"),  # two exchanges
    ],
)
def test_two_edits_or_none_are_not_one_edit(a: str, b: str) -> None:
    assert not one_edit(a, b)


def test_fold_removes_case_accents_and_repeated_spaces() -> None:
    assert fold("  MONTRÉAL  ") == "montreal"
    assert fold("Saint  Jean") == fold("saint jean") == "saint jean"


def test_a_rare_value_one_edit_from_a_frequent_one_joins_its_group() -> None:
    table = [*CITIES, ("Longueuuil", 1)]

    [group] = near_groups(table)

    assert group == NearGroup(frequent=0, neighbours=(3,), count=1)


def test_a_rare_value_joins_the_most_frequent_value_one_edit_away() -> None:
    table = [("Lavall", 40), ("Laval", 100), ("Lavalx", 1)]

    [group] = near_groups(table)

    assert (group.frequent, group.neighbours) == (1, (2,))


def test_case_and_accent_variants_are_not_typos() -> None:
    table = [("Montréal", 300), ("MONTRÉAL", 1), ("Montreal", 2)]

    assert near_groups(table) == []


@pytest.mark.parametrize(
    "table",
    [
        [("Longueuil", 9), ("Longueuuil", 1)],  # the frequent value is not frequent enough
        [("Longueuil", 100), ("Longueuuil", 3)],  # the neighbour is not rare
        [("Longueuil", 15), ("Longueuuil", 2)],  # not ten times as frequent
        [("Roy", 100), ("Roi", 1)],  # too short
        [("Longueuil", 100), ("", 1)],  # an empty value
        [("Longueuil", 100), ("Montreal", 1)],  # not one edit
    ],
)
def test_the_thresholds_keep_a_pair_out(table: list[tuple[str, int]]) -> None:
    assert near_groups(table) == []


def test_groups_are_sorted_by_the_rows_of_their_neighbours_then_by_text() -> None:
    table = [
        ("Longueuil", 120),
        ("Laval", 100),
        ("Montreal", 300),
        ("Longueuuil", 1),
        ("Lavval", 1),
        ("Lavval2", 0),
        ("Montrreal", 2),
        ("Montreall", 1),
    ]

    groups = near_groups(table)

    assert [(g.frequent, g.neighbours, g.count) for g in groups] == [
        (2, (6, 7), 3),
        (1, (4,), 1),
        (0, (3,), 1),
    ]


def test_a_group_lists_at_most_max_neighbours_and_counts_those_it_lists() -> None:
    table = [("Longueuil", 500), *((f"Longueuil{c}", 2 - (i % 2)) for i, c in enumerate("abcdef"))]

    [group] = near_groups(table, max_neighbours=3)

    assert len(group.neighbours) == 3
    assert group.count == sum(table[i][1] for i in group.neighbours)
    assert [table[i][1] for i in group.neighbours] == [2, 2, 2]


def test_the_groups_do_not_depend_on_the_order_of_the_table() -> None:
    table = [*CITIES, ("Longueuuil", 1), ("Montrreal", 1), ("Lavval", 2)]
    reordered = list(reversed(table))

    def named(groups: list[NearGroup], source: list[tuple[str, int]]) -> list[tuple[str, tuple[str, ...]]]:
        return [(source[g.frequent][0], tuple(sorted(source[i][0] for i in g.neighbours))) for g in groups]

    assert named(near_groups(table), table) == named(near_groups(reordered), reordered)


# --- the targets of a plan -------------------------------------------------------------------

CITY_NAMES = [
    "Longueuil", "Laval", "Montreal", "Quebec", "Gatineau", "Sherbrooke", "Brossard",
    "Toronto", "Ottawa", "Calgary", "Vancouver", "Victoria", "Granby", "Joliette",
    "Rimouski", "Terrebonne", "Drummondville", "Blainville", "Repentigny", "Shawinigan",
]  # fmt: skip
TYPOS = ["Longueuuil", "Lavval", "Montrreal"]
# The first pass lists 100 values at most, as in the configuration of the examples.
FEW = {
    "limits": {"max_samples": 100, "max_listed_frequencies": 100},
    "exposure": {"sensitive_values": "show"},
}


def _city_rows(typos: list[str], junk: int = 100) -> list[str]:
    """Twenty cities of 30 rows, ``junk`` values seen once and the typos (more than the
    100 distinct values a column may list by value)."""
    rows = [f"{CITY_NAMES[i % 20]},{i}" for i in range(600)]
    rows += [f"Xq{n:03d}z,{600 + n}" for n in range(junk)]
    rows += [f"{typo},{700 + n}" for n, typo in enumerate(typos)]
    return rows


def _near(plan: SamplingPlan) -> list[Target]:
    return [t for t in plan.targets if t.predicate.kind == "near_value"]


def test_a_complete_list_of_the_scan_gives_a_target_per_frequent_value_with_typos(
    tmp_path: Path,
) -> None:
    result = scan_csv(tmp_path, "city,n", _city_rows(TYPOS))

    plan = plan_sampling(result)

    targets = _near(plan)
    assert len(targets) == 3
    assert all(t.family == "quality" and t.obligation == "optional" for t in targets)
    assert all(t.predicate.source == "scan" and t.evidence == "exact" for t in targets)
    assert all(t.needs == ["scan"] and t.origin is None for t in targets)
    assert all(t.frequency.count == 1 and t.weight.base == 4.0 for t in targets)
    field = next(f for f in result.datasets[0].fields if f.display == "city")
    names = {e.id: e.value for e in field.values.samples.listed}
    found = {
        names[int(t.predicate.params["of"])]: [names[int(i)] for i in str(t.predicate.params["entries"]).split(",")]
        for t in targets
    }
    assert found == {"Longueuil": ["Longueuuil"], "Laval": ["Lavval"], "Montreal": ["Montrreal"]}


def test_the_exact_table_of_the_second_pass_gives_the_targets_of_a_truncated_list(
    tmp_path: Path,
) -> None:
    result, _, outcome = deep_csv(tmp_path, "city,n", _city_rows(TYPOS), **FEW)

    plan = plan_sampling(result, deep=outcome.document)

    targets = _near(plan)
    assert len(targets) == 3
    assert all(t.predicate.source == "second_pass" and t.evidence == "second_pass" for t in targets)
    assert all(t.needs == ["scan", "second_pass"] and t.origin for t in targets)
    analysis = next(a for a in outcome.document.analyses if a.id == targets[0].origin)
    assert analysis.analyzer == "exact_frequencies"
    values = [e.value for e in analysis.result.values]
    named = {
        values[int(t.predicate.params["of"])]: [values[int(i)] for i in str(t.predicate.params["entries"]).split(",")]
        for t in targets
    }
    assert named == {"Longueuil": ["Longueuuil"], "Laval": ["Lavval"], "Montreal": ["Montrreal"]}


def test_a_truncated_list_without_the_second_pass_gives_no_near_target(tmp_path: Path) -> None:
    result = scan_csv(tmp_path, "city,n", _city_rows(TYPOS), **FEW)

    assert _near(plan_sampling(result)) == []


def test_a_column_listed_by_value_has_no_near_target(tmp_path: Path) -> None:
    rows = [f"{name},{i}" for i in range(10) for name in CITY_NAMES[:5]] + ["Longueuuil,1"]
    result = scan_csv(tmp_path, "city,n", rows)

    plan = plan_sampling(result)

    assert _near(plan) == []
    assert any(t.predicate.kind == "value_equals" for t in plan.targets)


def test_the_groups_are_capped_per_column_and_per_dataset_and_the_rest_is_counted(
    tmp_path: Path,
) -> None:
    result = scan_csv(tmp_path, "city,n", _city_rows(TYPOS))

    per_column = plan_sampling(result, settings=SmartSettings(near_groups_per_column=2))
    per_dataset = plan_sampling(result, settings=SmartSettings(near_groups=1))
    off = plan_sampling(result, settings=SmartSettings(near_groups=0))

    assert len(_near(per_column)) == 2 and per_column.summary.dropped == 1
    assert len(_near(per_dataset)) == 1 and per_dataset.summary.dropped == 2
    quality = next(f for f in per_column.summary.families if f.family == "quality")
    assert quality.dropped == 1
    assert _near(off) == [] and off.summary.dropped == 0


def test_the_cap_of_a_dataset_goes_to_the_first_columns(tmp_path: Path) -> None:
    rows = [f"{CITY_NAMES[i % 20]},{CITY_NAMES[(i + 1) % 20]}" for i in range(600)]
    rows += [f"Xq{n:03d}z,Yq{n:03d}z" for n in range(100)]
    rows += ["Longueuuil,Lavval", "Montrreal,Granbyy"]
    result = scan_csv(tmp_path, "first,second", rows)

    plan = plan_sampling(result, settings=SmartSettings(near_groups=3))

    assert sorted(t.displays[0] for t in _near(plan)) == ["first", "first", "second"]
    assert plan.summary.dropped == 1


# --- the selection of the rows ---------------------------------------------------------------


def _sample(tmp_path: Path, rows: list[str], size: int, settings: SmartSettings, **config: object):
    """Scan, second pass, plan and selection; returns the plan, the cells of the first column
    the sample holds and the report document."""
    result, _, outcome = deep_csv(tmp_path, "city,n", rows, **config)
    plan = plan_sampling(result, deep=outcome.document, size=size, settings=settings)
    selection = select_rows(result, tmp_path / "data.csv", plan, deep=outcome.document)
    document = build_document(
        result,
        plan,
        selection,
        percent=None,
        output_name="data.sample.csv",
        encoding="utf-8",
        delimiter=",",
        started_at=datetime.now(UTC),
        duration_seconds=1.0,
        scan_ran=False,
    )
    return plan, {row[0] for row in selection.rows}, document


def _faithful(document) -> None:
    assert [e.id for e in document.targets if e.status == "unresolved"] == []
    assert document.coverage.verification.disagreed == []


@pytest.mark.parametrize("config", [{}, FEW], ids=["list of the scan", "exact table"])
def test_a_small_sample_keeps_a_typo_of_each_frequent_value_it_would_otherwise_miss(
    tmp_path: Path, config: dict[str, object]
) -> None:
    (tmp_path / "with").mkdir()
    (tmp_path / "without").mkdir()
    rows = _city_rows(TYPOS)

    plan, kept, document = _sample(tmp_path / "with", rows, 30, SmartSettings(near_share=0.2), **config)
    _, missed, _ = _sample(tmp_path / "without", rows, 30, SmartSettings(near_groups=0), **config)

    _faithful(document)
    assert set(TYPOS) <= kept
    assert not set(TYPOS) <= missed
    covered = {e.id for e in document.targets if e.status == "covered"}
    assert {t.id for t in _near(plan)} <= covered


def test_one_row_of_any_neighbour_covers_the_group(tmp_path: Path) -> None:
    rows = _city_rows(["Longueuuil", "Longeuil", "Lonqueuil"])

    plan, kept, document = _sample(tmp_path, rows, 30, SmartSettings(near_share=0.2))

    _faithful(document)
    [target] = _near(plan)
    assert target.frequency.count == 3
    assert kept & {"Longueuuil", "Longeuil", "Lonqueuil"}
    assert [e.status for e in document.targets if e.id == target.id] == ["covered"]


def test_a_group_whose_entries_changed_is_unresolved_and_covers_nothing(tmp_path: Path) -> None:
    result, _, outcome = deep_csv(tmp_path, "city,n", _city_rows(TYPOS), **FEW)
    plan = plan_sampling(result, deep=outcome.document)
    broken = [
        t.model_copy(
            update={"predicate": t.predicate.model_copy(update={"params": {**t.predicate.params, "entries": "9999"}})}
        )
        if t.predicate.kind == "near_value"
        else t
        for t in plan.targets
    ]

    evaluator = Evaluator(result, result.datasets[0], outcome.document, broken)

    codes = {broken[position].predicate.kind: code for position, code in evaluator.unresolved.items()}
    assert codes == {"near_value": "reference_missing"}


# --- the budget follows the rows asked for ------------------------------------------------------


def test_the_groups_are_bounded_by_a_share_of_the_rows_asked_for(tmp_path: Path) -> None:
    result = scan_csv(tmp_path, "city,n", _city_rows(TYPOS))
    settings = SmartSettings(near_share=0.1)

    small = plan_sampling(result, size=20, settings=settings)
    large = plan_sampling(result, size=200, settings=settings)
    unsized = plan_sampling(result, settings=settings)
    off = plan_sampling(result, size=200, settings=SmartSettings(near_share=0))

    assert [len(_near(p)) for p in (small, large, unsized, off)] == [2, 3, 3, 0]
    assert small.summary.dropped == 1 and large.summary.dropped == 0 and off.summary.dropped == 0


def test_the_columns_share_the_budget_in_turn(tmp_path: Path) -> None:
    rows = [f"{CITY_NAMES[i % 20]},{CITY_NAMES[(i + 7) % 20]}" for i in range(600)]
    rows += [f"Xq{n:03d}z,Yq{n:03d}z" for n in range(100)]
    rows += ["Longueuuil,Granbyy", "Lavval,Joliete", "Montrreal,Rimouskii"]
    result = scan_csv(tmp_path, "first,second", rows)

    plan = plan_sampling(result, size=40, settings=SmartSettings(near_share=0.1))

    assert sorted(t.displays[0] for t in _near(plan)) == ["first", "first", "second", "second"]
    assert plan.summary.dropped == 2


def test_a_sample_too_small_for_its_mandatory_targets_gets_no_group(tmp_path: Path) -> None:
    levels = [f"level{i:02d}" for i in range(40)]
    rows = [f"{CITY_NAMES[i % 20]},{levels[i % 40]}" for i in range(600)]
    rows += [f"Xq{n:03d}z,{levels[n % 40]}" for n in range(100)]
    rows += [f"{typo},{levels[0]}" for typo in TYPOS]
    result = scan_csv(tmp_path, "city,level", rows)
    settings = SmartSettings(near_share=0.5)

    small = plan_sampling(result, size=20, settings=settings)
    enough = plan_sampling(result, size=40, settings=settings)

    assert _near(small) == [] and small.summary.dropped == 3
    assert len(_near(enough)) == 3


def test_a_long_text_takes_no_part_in_a_group() -> None:
    sentence = "x" * 100
    table = [(sentence, 50), (sentence[:-1], 1), ("Longueuil", 120), ("Longueuuil", 1)]

    [group] = near_groups(table)

    assert (group.frequent, group.neighbours) == (2, (3,))

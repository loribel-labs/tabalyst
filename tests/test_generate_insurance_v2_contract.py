# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contract tests of Insurance V2, enabled lot by lot.

The contract is ``docs/dev/generate/insurance-v2.md`` (the section of each test is in its
docstring). Lot 0 enables the non-regression guards and the checks of the numbers written in
the contract. Lots 1 to 3 are skeletons: each test carries
``@contract("<lot>")`` and is skipped until the lot is listed in ``ENABLED_LOTS``. A lot adds
its number when it starts and replaces the ``_to_write`` call of its tests with the real
assertions, so the suite stays green between lots and a test left unwritten fails loudly.
"""

from __future__ import annotations

import csv
import json
import shutil
from collections.abc import Callable
from fractions import Fraction
from importlib.resources import files
from pathlib import Path
from typing import NoReturn, TypeVar, cast

import pytest
import yaml

from tabalyst.errors import ConfigurationError, ReportError
from tabalyst.generate_anomalies import CHANGE_FIELDS, AnomalyEvent, inject_anomalies
from tabalyst.generate_insurance import FIELDS, insurance_canonical
from tabalyst.generate_package import load_generate_package
from tabalyst.generate_service import (
    build_generate_plan,
    generate_datasets,
    validate_generate_package,
)

ENABLED_LOTS: set[str] = {"0", "1"}

PACKAGE = Path(str(files("tabalyst").joinpath("generate_examples", "insurance")))
ROOT = Path(__file__).resolve().parents[1]
LEGACY_PROFILES = {"dirty_realistic", "dirty_stress", "rule_breaks"}

# Section 3.3 of the contract: the unit is the case; the band is what a scenario total may be.
NOMINAL_CASES = {"frequent": 5000, "uncommon": 500, "rare": 100, "very_rare": 50,
                 "extremely_rare": 5, "single": 1}
RARITY_BANDS = {"single": (1, 1), "extremely_rare": (2, 9), "very_rare": (10, 74),
                "rare": (75, 199), "uncommon": (200, 999), "frequent": (1000, None)}
# Section 3.3: the counts of the report (section 3) and the level their text implies.
REPORT_COUNTS = {"R02": (5, "extremely_rare"), "R04": (10, "very_rare"),
                 "R05": (20, "very_rare"), "R06": (25, "very_rare"),
                 "R07": (50, "very_rare"), "R08": (50, "very_rare"),
                 "R09": (100, "rare"), "R10": (100, "rare"),
                 "R11": (250, "uncommon"), "R12": (500, "uncommon")}
# Section 6.3: probability that 5,000 rows drawn at random hold none of ``cases`` cases.
ABSENCE_5000 = {
    500_000: {500: 0.0065539338818227785, 100: 0.3659957349884044, 50: 0.6049910939572138,
              5: 0.9509898577796588, 1: 0.99},
    275_000: {500: 0.00010277378077750461, 100: 0.1595740372097392, 50: 0.3995008304780598,
              5: 0.9123365190796224, 1: 0.9818181818181818},
}

F = TypeVar("F", bound=Callable[..., object])


def contract(lot: str) -> Callable[[F], F]:
    """Mark a test as the contract of a lot and skip it until the lot is enabled."""
    def decorate(test: F) -> F:
        marked = pytest.mark.insurance_v2_lot(lot)(test)
        return cast(F, pytest.mark.skipif(
            lot not in ENABLED_LOTS,
            reason=f"Insurance V2 lot {lot} is not implemented yet")(marked))
    return decorate


def _to_write(section: str) -> NoReturn:
    """Fail a skeleton: the lot that enables it writes the assertions of the contract."""
    raise NotImplementedError(f"Insurance V2 contract {section}: write this test with the lot")


def _absence(rows: int, cases: int, sample: int) -> float:
    """Exact ``C(N - c, n) / C(N, n)`` as a product of ``c`` fractions (contract 6.3)."""
    probability = Fraction(1)
    for i in range(cases):
        probability *= Fraction(rows - sample - i, rows - i)
    return float(probability)


# --- Lot 0: guards and numbers of the contract (enabled) -------------------------------------


@contract("0")
def test_default_insurance_output_keeps_its_34_columns(tmp_path: Path) -> None:
    """Contract 2 and 7: the default output profile is the 33 named fields plus ``filiale``."""
    assert len(FIELDS) == 33
    plan = build_generate_plan(example="insurance", rows=20, seed=42, output_dir=tmp_path)
    assert plan.rows["insurance-combined"] == 20
    generate_datasets(plan)
    header = (tmp_path / "insurance-combined.csv").read_text(encoding="utf-8").splitlines()[0]
    assert header.split(",") == [*FIELDS, "filiale"]
    assert len(header.split(",")) == 34


@contract("0")
def test_legacy_profiles_are_the_three_documented_ones() -> None:
    """Contract 2 and 4.1: a V2 profile is a new profile, never a change of these three."""
    package = load_generate_package(PACKAGE)
    assert set(cast(dict[str, object], package.manifest["anomaly_profiles"])) == LEGACY_PROFILES


@contract("0")
@pytest.mark.parametrize("profile", sorted(LEGACY_PROFILES))
def test_legacy_profile_plans_no_truth_rules_metrics_or_manifest_file(
        tmp_path: Path, profile: str) -> None:
    """Contract 5.1: a profile without ``scenario_id`` writes the set of artifacts of today."""
    plan = build_generate_plan(example="insurance", output_dir=tmp_path, anomaly_profile=profile)
    assert {artifact.kind for artifact in plan.artifacts} == {
        "clean", "altered", "changes", "summary"}
    assert len(plan.artifacts) == 7


@contract("0")
def test_non_regression_references_of_the_contract_exist() -> None:
    """Contract 2: the pinned demo manifest and the contract itself are in place."""
    manifest = json.loads(
        (ROOT / "examples/datasets/insurance-customers-100k.json").read_text(encoding="utf-8"))
    assert manifest["generate"]["anomaly_profile"] == "dirty_stress"
    assert manifest["generate"]["rows"] == 100000
    assert all(len(entry["sha256"]) == 64 for entry in manifest["files"].values())
    assert (ROOT / "examples/datasets/insurance-customers.csv").is_file()
    assert (ROOT / "docs/dev/generate/insurance-v2.md").is_file()


@contract("0")
def test_rarity_bands_partition_the_counts_and_hold_the_nominal_and_report_counts() -> None:
    """Contract 3.3: bands are contiguous, hold their nominal count and every report count."""
    ordered = ["single", "extremely_rare", "very_rare", "rare", "uncommon", "frequent"]
    previous_high = 0
    for level in ordered:
        low, high = RARITY_BANDS[level]
        assert low == previous_high + 1
        assert low <= NOMINAL_CASES[level] and (high is None or NOMINAL_CASES[level] <= high)
        previous_high = high if high is not None else previous_high
    for scenario, (count, level) in REPORT_COUNTS.items():
        low, high = RARITY_BANDS[level]
        assert low <= count and (high is None or count <= high), scenario


@contract("0")
@pytest.mark.parametrize("rows", sorted(ABSENCE_5000))
def test_documented_absence_probabilities_are_exact(rows: int) -> None:
    """Contract 6.3: the table of the contract is the exact product, not a copied figure."""
    for cases, expected in ABSENCE_5000[rows].items():
        assert _absence(rows, cases, 5000) == pytest.approx(expected, rel=1e-12)
    # The report's rounded table, valid for 500,000 rows only.
    if rows == 500_000:
        assert [round(100 * _absence(rows, c, 5000), 2) for c in (500, 100, 50, 5, 1)] == [
            0.66, 36.6, 60.5, 95.1, 99.0]


# --- Lot 1: scenario engine (contract 4) ---------------------------------------------------


def _scenario(scenario_id: str, kind: str, column: str, count: int, **extra: object,
              ) -> dict[str, object]:
    """One V2 operation: ``kind`` on ``column`` for ``count`` cases of ``scenario_id``."""
    operation: dict[str, object] = {
        "kind": kind, "column": column, "count": count, "scenario_id": scenario_id,
        "category": "semantic_invalid", "severity": "major"}
    if kind == "replace":
        operation["value"] = "Z"
    elif kind == "format":
        operation["value"] = "suffix_x"
    operation.update(extra)
    return operation


def _write_clean(tmp_path: Path, rows: list[dict[str, str]]) -> Path:
    clean = tmp_path / "clean.csv"
    with clean.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return clean


def _inject(tmp_path: Path, rows: list[dict[str, str]], operations: list[dict[str, object]],
            name: str = "p") -> tuple[list[dict[str, str]], list[dict[str, str]],
                                      dict[str, object]]:
    """Inject ``operations`` in a small clean file; return altered rows, journal and summary."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    summary = inject_anomalies(
        _write_clean(tmp_path, rows), tmp_path / "altered.csv", tmp_path / "changes.csv",
        dataset="demo", profile={"id": name, "operations": operations}, seed=7,
        count=len(rows), delimiter=",")
    with (tmp_path / "altered.csv").open(encoding="utf-8", newline="") as stream:
        altered = list(csv.DictReader(stream))
    with (tmp_path / "changes.csv").open(encoding="utf-8", newline="") as stream:
        changes = list(csv.DictReader(stream))
    return altered, changes, summary


def _pairs(count: int) -> list[dict[str, str]]:
    return [{"id": f"R{i:03d}", "a": f"a{i}", "b": f"b{i}", "c": f"c{i}"} for i in range(count)]


def _scenarios_by_row(changes: list[dict[str, str]],
                      operations: list[dict[str, object]]) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for change in changes:
        scenario = str(operations[int(change["operation_index"]) - 1]["scenario_id"])
        found.setdefault(change["row_number"], set()).add(scenario)
    return found


def _insurance_package(tmp_path: Path, operations: list[dict[str, object]],
                       source: Path = PACKAGE, profile: str = "v2_test") -> Path:
    """Copy a shipped package and add one profile that targets its first dataset."""
    package = tmp_path / "package"
    shutil.copytree(source, package)
    manifest = package / "dataset.yaml"
    document = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    targets = [("insurance-combined" if source == PACKAGE else
                next(d["id"] for d in document["datasets"] if d["mode"] == "generated"))]
    document["anomaly_profiles"][profile] = {"targets": targets, "operations": operations}
    manifest.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True),
                        encoding="utf-8")
    return package


def _refused(tmp_path: Path, operations: list[dict[str, object]], message: str) -> None:
    package = _insurance_package(tmp_path, operations)
    with pytest.raises(ConfigurationError, match=message):
        validate_generate_package(package)


@contract("1")
def test_legacy_profile_summary_gains_no_v2_member(tmp_path: Path) -> None:
    """4.2: the summary of a legacy profile keeps the scenario digest of test_generate_insurance."""
    operations: list[dict[str, object]] = [
        {"kind": "format", "column": "a", "value": "suffix_x", "count": 4},
        {"kind": "format", "column": "b", "value": "suffix_x", "rate": 0.5}]
    _, _, summary = _inject(tmp_path, _pairs(20), operations)
    assert set(summary) == {"dataset", "profile", "seed", "total_rows", "affected_rows",
                            "affected_row_rate", "events", "changed_cells", "operations"}
    entries = cast(list[dict[str, object]], summary["operations"])
    assert all(not set(entry) & {"scenario_id", "mode", "eligible_population"}
               for entry in entries)


@contract("1")
@pytest.mark.parametrize(("operations", "message"), [
    ([{"kind": "set_missing", "column": "nom", "count": 2, "scenario_id": "S1",
       "severity": "major"}],
     r"operations\[1\]: operation.category is required"),
    ([{"kind": "set_missing", "column": "nom", "count": 2, "scenario_id": "S1",
       "category": "format_invalid"}],
     r"operations\[1\]: operation.severity is required"),
    ([_scenario("S1", "set_missing", "nom", 2),
      {"kind": "set_missing", "column": "prenom", "count": 2}],
     r"operations\[2\]: a scenario profile declares scenario_id on every"),
    ([_scenario("S1", "set_missing", "nom", 2),
      {"kind": "set_missing", "column": "prenom", "count": 2, "category": "format_invalid"}],
     r"operations\[2\]: operation.category needs operation.scenario_id"),
])
def test_v2_profile_needs_scenario_category_and_severity_on_every_operation(
        tmp_path: Path, operations: list[dict[str, object]], message: str) -> None:
    """4.1: one operation without them in a V2 profile is refused, naming profile and index."""
    _refused(tmp_path, operations, rf"profile v2_test: {message}")
    with pytest.raises(ValueError, match=rf"v2_test\.{message}"):
        _inject(tmp_path / "direct", _pairs(5), operations, "v2_test")


@contract("1")
def test_v2_profile_refuses_rate_operations_and_a_mix_with_legacy_operations(
        tmp_path: Path) -> None:
    """4.1 and ADR overlap: V2 profiles use ``count`` only."""
    _refused(tmp_path, [{**_scenario("S1", "set_missing", "nom", 2), "rate": 0.1}],
             r"operations\[1\]: operation.rate is not allowed with scenario_id")
    legacy: dict[str, object] = {"kind": "set_missing", "column": "prenom", "count": 2}
    _refused(tmp_path / "mix", [_scenario("S1", "set_missing", "nom", 2), legacy],
             r"operations\[2\]: a scenario profile declares scenario_id on every operation")


@contract("1")
@pytest.mark.parametrize("package_id", ["insurance", "crm", "computer"])
def test_legacy_operation_refuses_v2_keys_in_every_package(
        tmp_path: Path, package_id: str) -> None:
    """4.1: a V2 key on an operation without ``scenario_id`` (Insurance, CRM, Computer) fails."""
    source = Path(str(files("tabalyst").joinpath("generate_examples", package_id)))
    document = yaml.safe_load((source / "dataset.yaml").read_text(encoding="utf-8"))
    profile = next(iter(document["anomaly_profiles"].values()))
    column = next(op["column"] for op in profile["operations"] if "column" in op)
    key: dict[str, object] = {"kind": "set_missing", "column": column, "count": 1,
                              "severity": "major"}
    with pytest.raises(ConfigurationError, match="severity"):
        validate_generate_package(_insurance_package(tmp_path, [key], source))
    # A complete scenario operation is accepted by Insurance alone.
    complete = {**key, "scenario_id": "S1", "category": "format_invalid"}
    package = _insurance_package(tmp_path / "complete", [complete], source)
    if package_id == "insurance":
        assert validate_generate_package(package).package_id == "insurance"
    else:
        with pytest.raises(ConfigurationError, match="scenario"):
            validate_generate_package(package)


@contract("1")
def test_rarity_level_must_match_the_band_of_the_scenario_total(tmp_path: Path) -> None:
    """3.3 and 4.1: counts 40 + 40 under ``very_rare`` fail (80 is above 74), 25 + 25 pass."""
    def pair(count: int) -> list[dict[str, object]]:
        return [_scenario("S1", "set_missing", "nom", count, rarity_level="very_rare"),
                _scenario("S1", "set_missing", "prenom", count, rarity_level="very_rare")]

    _refused(tmp_path / "over", pair(40),
             r"scenario S1 declares rarity_level very_rare \(10 to 74 cases\) but its "
             r"operations total 80")
    assert validate_generate_package(_insurance_package(tmp_path / "ok", pair(25)))
    _refused(tmp_path / "single", [_scenario("S2", "set_missing", "nom", 2,
                                             rarity_level="single")],
             r"scenario S2 declares rarity_level single \(1 to 1 cases\) but its operations "
             r"total 2")


@contract("1")
def test_requires_names_a_column_missing_from_the_output_profile_and_is_refused(
        tmp_path: Path) -> None:
    """4.1: the message names the column and the output profile that provides it."""
    _refused(tmp_path, [_scenario("S1", "set_missing", "nom", 2, requires=["date_sinistre"])],
             r"operations\[1\]: scenario S1 requires column 'date_sinistre', which the "
             r"default output profile does not have \(the extended output profile provides it\)")
    _refused(tmp_path / "unknown", [_scenario("S1", "set_missing", "nom", 2,
                                              requires=["no_such_column"])],
             r"requires column 'no_such_column', which the default output profile does not have"
             r"$")
    assert validate_generate_package(_insurance_package(
        tmp_path / "ok", [_scenario("S1", "set_missing", "nom", 2, requires=["filiale"])]))


@contract("1")
def test_conflicts_with_unknown_scenario_is_refused_and_is_symmetric(tmp_path: Path) -> None:
    """4.1: ``A`` lists ``B`` and ``B`` does not: the pair still never overlaps."""
    _refused(tmp_path, [_scenario("S1", "set_missing", "nom", 2, conflicts_with=["S9"])],
             r"operations\[1\]: conflicts_with names the unknown scenario S9")
    _refused(tmp_path / "self", [_scenario("S1", "set_missing", "nom", 2,
                                           conflicts_with=["S1"])],
             r"scenario S1 cannot conflict with itself")
    operations = [
        _scenario("A", "format", "a", 8, can_overlap=True, conflicts_with=["B"]),
        _scenario("B", "format", "b", 8, can_overlap=True)]
    _, changes, _ = _inject(tmp_path / "run", _pairs(20), operations)
    assert all(len(found) == 1 for found in _scenarios_by_row(changes, operations).values())
    assert len(changes) == 16


@contract("1")
def test_operations_of_a_v2_profile_never_share_a_row_by_default(tmp_path: Path) -> None:
    """4.3: every row of the journal carries one scenario when nothing allows overlap."""
    operations = [_scenario("A", "format", "a", 10), _scenario("B", "format", "b", 10),
                  _scenario("C", "format", "c", 10)]
    _, changes, summary = _inject(tmp_path, _pairs(30), operations)
    by_row = _scenarios_by_row(changes, operations)
    assert len(by_row) == 30 and all(len(found) == 1 for found in by_row.values())
    assert summary["events"] == summary["affected_rows"] == 30
    # More cases than rows left: refused, never squeezed onto a shared row.
    too_many = [_scenario("A", "format", "a", 12), _scenario("B", "format", "b", 12)]
    with pytest.raises(ValueError, match=r"operation 2 \(scenario B\) asks for count 12 but "
                                         r"only 8 rows can take it"):
        _inject(tmp_path / "many", _pairs(20), too_many)


@contract("1")
def test_two_scenarios_share_a_row_when_both_allow_it(tmp_path: Path) -> None:
    """4.3 (C01): ``can_overlap`` on both gives rows with two scenarios, counts exact."""
    operations = [_scenario("A", "format", "a", 15, can_overlap=True),
                  _scenario("B", "format", "b", 15, can_overlap=True)]
    _, changes, summary = _inject(tmp_path, _pairs(20), operations)
    by_row = _scenarios_by_row(changes, operations)
    assert sum(len(found) == 2 for found in by_row.values()) >= 10  # 15 + 15 on 20 rows
    entries = cast(list[dict[str, object]], summary["operations"])
    assert [(e["requested_rows"], e["applied_rows"]) for e in entries] == [(15, 15), (15, 15)]
    # Only one of the two opting in is not enough.
    one_sided = [_scenario("A", "format", "a", 15, can_overlap=True),
                 _scenario("B", "format", "b", 15)]
    with pytest.raises(ValueError, match="asks for count 15 but only 5 rows can take it"):
        _inject(tmp_path / "one", _pairs(20), one_sided)


@contract("1")
def test_operations_of_one_scenario_never_share_a_row_even_when_they_may_overlap(
        tmp_path: Path) -> None:
    """4.3 and 4.6: one scenario is one case per row, so its operations stay apart."""
    one_scenario = [_scenario("A", "format", "a", 8, can_overlap=True),
                    _scenario("A", "format", "b", 8, can_overlap=True)]
    _, changes, _ = _inject(tmp_path, _pairs(20), one_scenario)
    assert len({c["row_number"] for c in changes}) == 16
    greedy = [{**one_scenario[0], "count": 14}, {**one_scenario[1], "count": 14}]
    with pytest.raises(ValueError, match="asks for count 14 but only 6 rows can take it"):
        _inject(tmp_path / "greedy", _pairs(20), greedy)


@contract("1")
def test_overlapping_operation_that_cannot_apply_to_the_shared_row_fails_the_run(
        tmp_path: Path) -> None:
    """4.2 and 4.6: exact or refused: a second set_missing finds the cell already empty."""
    operations = [_scenario("A", "set_missing", "a", 10, can_overlap=True),
                  _scenario("B", "set_missing", "a", 10, can_overlap=True)]
    with pytest.raises(ValueError, match=r"operation 2 \(scenario B\) applied 0 of its count 10"):
        _inject(tmp_path, _pairs(10), operations)


@contract("1")
def test_conflicts_with_forbids_overlap_even_when_both_allow_it(tmp_path: Path) -> None:
    """4.3: no row carries both scenarios."""
    free = [_scenario("A", "format", "a", 14, can_overlap=True),
            _scenario("B", "format", "b", 14, can_overlap=True)]
    _, changes, _ = _inject(tmp_path, _pairs(20), free)
    assert any(len(found) == 2 for found in _scenarios_by_row(changes, free).values())
    apart = [_scenario("A", "format", "a", 8, can_overlap=True, conflicts_with=["B"]),
             _scenario("B", "format", "b", 8, can_overlap=True, conflicts_with=["A"])]
    _, changes, _ = _inject(tmp_path / "apart", _pairs(20), apart)
    assert all(len(found) == 1 for found in _scenarios_by_row(changes, apart).values())
    unbalanced = [{**apart[0], "count": 14}, {**apart[1], "count": 14}]
    with pytest.raises(ValueError, match="asks for count 14 but only 6 rows can take it"):
        _inject(tmp_path / "unbalanced", _pairs(20), unbalanced)


@contract("1")
def test_two_successive_modifications_of_one_cell_are_journaled_in_order(
        tmp_path: Path) -> None:
    """4.3 (C04): ``before`` of the second event is ``after`` of the first."""
    operations = [_scenario("A", "format", "a", 10, can_overlap=True),
                  _scenario("B", "format", "a", 10, value="upper", can_overlap=True)]
    altered, changes, _ = _inject(tmp_path, _pairs(10), operations)
    for row in range(10):
        events = sorted((c for c in changes if c["row_number"] == str(row + 2)),
                        key=lambda c: int(c["event_id"]))
        assert [e["operation_index"] for e in events] == ["1", "2"]
        assert (events[0]["before"], events[0]["after"]) == (f"a{row}", f"a{row}_X")
        assert (events[1]["before"], events[1]["after"]) == (f"a{row}_X", f"A{row}_X")
        assert altered[row]["a"] == f"A{row}_X"


@contract("1")
def test_summary_reports_events_distinct_cells_and_net_differences(tmp_path: Path) -> None:
    """4.2: three numbers that differ on a profile where one change undoes another (C03)."""
    operations = [_scenario("A", "swap", "a", 10, value="b", can_overlap=True),
                  _scenario("B", "swap", "a", 10, value="b", can_overlap=True),
                  _scenario("C", "replace", "a", 10, can_overlap=True)]
    altered, changes, summary = _inject(tmp_path, _pairs(10), operations)
    assert summary["events"] == 30  # three operations on ten rows
    assert summary["changed_cells"] == len(changes) == 50  # a swap writes two cells
    assert summary["distinct_changed_cells"] == 20  # a and b of every row
    assert summary["net_differences"] == 10  # b was swapped back; a ends at "Z"
    assert all(row["b"] == f"b{i}" and row["a"] == "Z" for i, row in enumerate(altered))


@contract("1")
def test_summary_marks_exact_mode_and_the_eligible_population_per_operation(
        tmp_path: Path) -> None:
    """4.2: ``mode`` is ``exact`` and ``eligible_population`` is at least the count."""
    rows = [{"id": f"R{i:03d}", "branch": "x" if i % 10 == 0 else "y", "v": "a-b"}
            for i in range(200)]
    operations = [_scenario("A", "format", "v", 5, value="double_hyphen", when={"branch": "x"}),
                  _scenario("B", "set_missing", "v", 7)]
    _, _, summary = _inject(tmp_path, rows, operations)
    entries = cast(list[dict[str, object]], summary["operations"])
    assert [(e["scenario_id"], e["mode"]) for e in entries] == [("A", "exact"), ("B", "exact")]
    assert [e["eligible_population"] for e in entries] == [20, 200]
    assert all(cast(int, e["eligible_population"]) >= cast(int, e["count"]) for e in entries)
    assert all("rate" not in e for e in entries)


@contract("1")
def test_exact_count_fails_when_the_eligible_population_is_too_small(tmp_path: Path) -> None:
    """4.2: the error names the operation and the eligible size; no file is left behind."""
    package = _insurance_package(tmp_path, [
        _scenario("ONT", "set_missing", "nom", 100, when={"filiale": "ontario"})])
    out = tmp_path / "out"
    plan = build_generate_plan(package, rows=300, seed=42, output_dir=out,
                               anomaly_profile="v2_test")
    with pytest.raises(ReportError, match=r"operation 1 \(scenario ONT\) asks for count 100 but "
                                          r"only 2\d rows can take it \(eligible population 2\d"):
        generate_datasets(plan)
    assert list(out.iterdir()) == []


@contract("1")
def test_appending_a_scenario_does_not_change_the_rows_of_the_earlier_ones(
        tmp_path: Path) -> None:
    """4.3 and 4.4: streams are keyed by scenario; inserting one is allowed to move the rest."""
    first = [_scenario("A", "format", "a", 10, value="replace_char"),
             _scenario("B", "format", "b", 10, value="drop_char")]
    both = [*first, _scenario("C", "format", "c", 10, value="replace_char")]
    short = _inject(tmp_path / "short", _pairs(60), first)[1]
    long = _inject(tmp_path / "long", _pairs(60), both)[1]

    def cells(journal: list[dict[str, str]]) -> list[tuple[str, ...]]:
        # event_id is a running number over the file, so it moves when a scenario is added.
        return [(c["row_number"], c["operation_index"], c["column"], c["before"], c["after"])
                for c in journal if c["operation_index"] != "3"]

    assert cells(long) == cells(short)
    assert any(c["operation_index"] == "3" for c in long)


@contract("1")
def test_changes_csv_keeps_its_columns_with_v2_metadata(tmp_path: Path) -> None:
    """ADR truth: ten fixed columns (plus ``class`` when declared), nothing else."""
    rich = _scenario("A", "format", "a", 3, rule_id="M01", rarity_level="extremely_rare",
                     root_cause_id="import_error", expected_detection="syntactic|domain",
                     requires=["a"], can_overlap=True)
    _inject(tmp_path, _pairs(10), [rich])
    header = (tmp_path / "changes.csv").read_text(encoding="utf-8").splitlines()[0]
    assert header.split(",") == CHANGE_FIELDS
    (tmp_path / "classed").mkdir()
    _inject(tmp_path / "classed", _pairs(10), [{**rich, "class": "tagged"}])
    header = (tmp_path / "classed" / "changes.csv").read_text(encoding="utf-8").splitlines()[0]
    assert header.split(",") == [*CHANGE_FIELDS, "class"]


@contract("1")
def test_canonical_value_is_captured_in_iso_for_a_branch_convention_date(
        tmp_path: Path) -> None:
    """4.5: the Quebec clean cell ``05-10-2026`` has the canonical value ``2026-10-05``."""
    generate_datasets(build_generate_plan(
        example="insurance", rows=300, seed=42, output_dir=tmp_path / "clean"))
    operations = [_scenario("MISREAD", "format", "date_debut", 3, value="date_mdy_iso",
                            category="contextual_invalid", when={"filiale": "quebec"})]
    events: list[AnomalyEvent] = []
    inject_anomalies(
        tmp_path / "clean" / "insurance-combined.csv", tmp_path / "altered.csv",
        tmp_path / "changes.csv", dataset="insurance-combined",
        profile={"id": "p", "operations": operations}, seed=42, count=300, delimiter=",",
        on_event=events.append, canonical=insurance_canonical)
    assert len(events) == 3
    for event in events:
        day, month, year = event.before.split("-")  # the Quebec clean cell is DD-MM-YYYY
        assert event.canonical_value == f"{year}-{month}-{day}"
        assert event.after == f"{year}-{day}-{month}"  # valid, read as another day
    assert any(event.after != event.canonical_value for event in events)
    # Without a reader the canonical value is the clean cell itself.
    plain: list[AnomalyEvent] = []
    inject_anomalies(
        tmp_path / "clean" / "insurance-combined.csv", tmp_path / "altered2.csv",
        tmp_path / "changes2.csv", dataset="insurance-combined",
        profile={"id": "p", "operations": operations}, seed=42, count=300, delimiter=",",
        on_event=plain.append)
    assert [e.canonical_value for e in plain] == [e.before for e in plain]


# --- Lot 2: truth files (contract 5) -------------------------------------------------------


@contract("2")
def test_v2_profile_writes_truth_rules_metrics_and_manifest_beside_changes() -> None:
    """5.1: names ``<dataset>.<profile>.<role>`` and the artifact kinds of the plan."""
    _to_write("5.1")


@contract("2")
def test_truth_columns_are_the_documented_ones_in_the_documented_order() -> None:
    """5.2: ``truth_id`` to ``expected_detection``."""
    _to_write("5.2")


@contract("2")
def test_every_changes_line_has_exactly_one_injected_truth_line() -> None:
    """5.2: same ``event_id`` and ``column``."""
    _to_write("5.2")


@contract("2")
def test_every_cell_that_differs_from_the_clean_file_has_one_net_difference_line() -> None:
    """5.2: and a cell restored by a later event has none."""
    _to_write("5.2")


@contract("2")
def test_truth_ids_are_unique_and_rule_ids_exist_in_rules_json() -> None:
    """5.2 and 5.3."""
    _to_write("5.2")


@contract("2")
def test_truth_row_numbers_count_the_header_as_line_one_like_changes_csv() -> None:
    """5.2: ``row_number`` indexes the altered file the same way as the journal."""
    _to_write("5.2")


@contract("2")
def test_outputs_are_identical_byte_for_byte_for_the_same_inputs() -> None:
    """1 and 5.5: seed, profile, rows, as-of date and generation version fix every byte."""
    _to_write("5.5")


@contract("2")
def test_manifest_lists_the_sha256_of_every_other_artifact() -> None:
    """5.5: bytes and digest per role; never its own digest."""
    _to_write("5.5")


@contract("2")
def test_existing_artifacts_collide_without_force_and_nothing_is_published() -> None:
    """5.1: the protection of ``_publish_artifacts`` covers the new kinds."""
    _to_write("5.1")


@contract("2")
def test_json_files_carry_format_0_2_0_revision_1_and_match_their_schema() -> None:
    """5.7: ``format``, ``format_version``, ``format_revision`` and the committed schema."""
    _to_write("5.7")


@contract("2")
def test_committed_schemas_are_not_stale() -> None:
    """5.7: regenerated from the models they equal the committed files."""
    _to_write("5.7")


@contract("2")
def test_clean_file_satisfies_every_rule_of_the_profile_before_injection() -> None:
    """5.3 and ADR 2026-11-11: the generator checks its clean file with ``generate_rules``."""
    _to_write("5.3")


# --- Lot 3: rarity levels and rare_events (contract 6) ---------------------------------------


@contract("3")
def test_rarity_levels_in_the_code_are_the_documented_nominal_counts_and_bands() -> None:
    """3.3: ``generate_rarity`` equals ``NOMINAL_CASES`` and ``RARITY_BANDS`` of this module."""
    _to_write("3.3")


@contract("3")
def test_rare_events_refuses_fewer_rows_than_its_floor() -> None:
    """6.1: 99,999 rows fail naming the profile, the floor 100,000 and the request."""
    _to_write("6.1")


@contract("3")
def test_rare_events_applies_the_exact_count_of_every_scenario() -> None:
    """6.2: R01 1 case on 2 rows, R02 5, R05 20, R06 25, R07 50, R08 50, R10 100, R11 250, R12 500."""
    _to_write("6.2")


@contract("3")
def test_rare_events_refuses_a_count_above_the_eligible_population() -> None:
    """4.2 and 6.1: no partial application."""
    _to_write("4.2")


@contract("3")
def test_one_truth_line_per_rare_case_with_its_scenario_and_level() -> None:
    """5.2 and 6.2."""
    _to_write("6.2")


@contract("3")
def test_valid_boundary_cases_are_valid_atypical_with_info_severity() -> None:
    """3.1 and 6.2: valid, expected detection ``none``, never counted as violations."""
    _to_write("3.1")


@contract("3")
@pytest.mark.parametrize("rows", sorted(ABSENCE_5000))
def test_absence_probability_matches_the_documented_values(rows: int) -> None:
    """6.3: ``generate_rarity`` agrees with ``ABSENCE_5000`` for the actual file size."""
    _to_write("6.3")


@contract("3")
def test_metrics_hold_the_absence_probability_for_every_documented_sample_size() -> None:
    """6.3: 500, 1,000, 5,000, 10,000 and 50,000 per scenario."""
    _to_write("6.3")


@contract("3")
def test_a_multi_row_scenario_has_a_null_probability_with_its_reason() -> None:
    """6.3: ``null`` and ``"reason": "multi_row_case"`` for R01."""
    _to_write("6.3")


@contract("3")
def test_rare_events_keeps_the_default_34_columns() -> None:
    """6.2 and 7: the profile needs no extended column."""
    _to_write("7")

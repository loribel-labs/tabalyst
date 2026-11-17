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
from collections import Counter
from collections.abc import Callable
from fractions import Fraction
from importlib.resources import files
from pathlib import Path
from typing import NoReturn, TypeVar, cast

import pytest
import yaml

from tabalyst.errors import ConfigurationError, ReportError
from tabalyst.generate_anomalies import CHANGE_FIELDS, AnomalyEvent, inject_anomalies
from tabalyst.generate_insurance import EXTENDED_FIELDS, FIELDS, insurance_canonical
from tabalyst.generate_package import load_generate_package
from tabalyst.generate_service import (
    GenerateResult,
    build_generate_plan,
    generate_datasets,
    validate_generate_package,
)

ENABLED_LOTS: set[str] = {"0", "1", "2", "3", "4", "5"}

PACKAGE = Path(str(files("tabalyst").joinpath("generate_examples", "insurance")))
ROOT = Path(__file__).resolve().parents[1]
LEGACY_PROFILES = {"dirty_realistic", "dirty_stress", "rule_breaks"}
# The scenario profiles the package ships: each lot that delivers one adds it here (lot 3).
V2_PROFILES = {"rare_events"}

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
    profiles = cast(dict[str, dict[str, list[dict[str, object]]]],
                    package.manifest["anomaly_profiles"])
    assert set(profiles) == LEGACY_PROFILES | V2_PROFILES
    for name in LEGACY_PROFILES:
        assert not any("scenario_id" in operation for operation in profiles[name]["operations"])
    for name in V2_PROFILES:
        assert all("scenario_id" in operation for operation in profiles[name]["operations"])


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

TRUTH_PROFILE = "v2_truth"
TRUTH_ROWS = 1000
DOCUMENTED_TRUTH_COLUMNS = [
    "truth_id", "kind", "scenario_id", "rule_id", "category", "severity", "rarity_level",
    "root_cause_id", "group_id", "event_id", "row_number", "column", "canonical_value",
    "expected_detection"]
ROLES = ("truth", "rules", "metrics", "manifest")


def _truth_operations() -> list[dict[str, object]]:
    """A profile with a business violation, a domain violation and a misread date."""
    return [
        _scenario("R08", "swap", "date_debut", 10, value="date_fin", rule_id="M01",
                  category="business_rule_violation", rarity_level="very_rare",
                  expected_detection="cross_column",
                  description="Contract ending before it starts"),
        _scenario("R11", "replace", "statut_contrat", 5, value="inconnu", rule_id="M23",
                  rarity_level="extremely_rare", expected_detection="domain"),
        _scenario("F19", "format", "date_debut", 3, value="date_mdy_iso",
                  category="contextual_invalid", when={"filiale": "quebec"},
                  expected_detection="contextual"),
    ]


def _run_truth(base: Path, operations: list[dict[str, object]] | None = None,
               rows: int = TRUTH_ROWS, force: bool = False) -> tuple[Path, GenerateResult]:
    """Generate the truth profile into ``base / "out"``; return the directory and result."""
    package = _insurance_package(base, operations or _truth_operations(), profile=TRUTH_PROFILE)
    out = base / "out"
    plan = build_generate_plan(package, rows=rows, seed=42, output_dir=out,
                               anomaly_profile=TRUTH_PROFILE, force=force)
    return out, generate_datasets(plan)


@pytest.fixture(scope="module")
def truth_result(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, GenerateResult]:
    """One run of the truth profile, shared by the tests that only read its files."""
    if "2" not in ENABLED_LOTS:
        pytest.skip("Insurance V2 lot 2 is not implemented yet")
    return _run_truth(tmp_path_factory.mktemp("truth"))


@pytest.fixture
def truth_run(truth_result: tuple[Path, GenerateResult]) -> Path:
    return truth_result[0]


def _file(out: Path, role: str) -> Path:
    suffix = "csv" if role in {"truth", "altered"} else "json"
    if role == "altered":
        return out / f"insurance-combined.{TRUTH_PROFILE}.csv"
    if role == "changes":
        return out / f"insurance-combined.{TRUTH_PROFILE}.changes.csv"
    return out / f"insurance-combined.{TRUTH_PROFILE}.{role}.{suffix}"


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _truth(out: Path) -> list[dict[str, str]]:
    return _csv_rows(_file(out, "truth"))


def _json(out: Path, role: str) -> dict[str, object]:
    return cast(dict[str, object], json.loads(_file(out, role).read_text(encoding="utf-8")))


@contract("2")
def test_v2_profile_writes_truth_rules_metrics_and_manifest_beside_changes(
        tmp_path: Path, truth_result: tuple[Path, GenerateResult]) -> None:
    """5.1: names ``<dataset>.<profile>.<role>`` and the artifact kinds of the plan."""
    package = _insurance_package(tmp_path, _truth_operations(), profile=TRUTH_PROFILE)
    plan = build_generate_plan(package, rows=TRUTH_ROWS, seed=42, output_dir=tmp_path / "out",
                               anomaly_profile=TRUTH_PROFILE)
    combined = [(a.kind, a.path.name) for a in plan.artifacts
                if a.dataset_id == "insurance-combined"]
    prefix = f"insurance-combined.{TRUTH_PROFILE}"
    assert combined == [
        ("clean", "insurance-combined.csv"), ("altered", f"{prefix}.csv"),
        ("changes", f"{prefix}.changes.csv"), ("summary", f"{prefix}.summary.json"),
        ("truth", f"{prefix}.truth.csv"), ("rules", f"{prefix}.rules.json"),
        ("metrics", f"{prefix}.metrics.json"), ("manifest", f"{prefix}.manifest.json")]
    out, result = truth_result
    assert all(_file(out, role).is_file() for role in ROLES)
    assert [artifact.kind for artifact in result.artifacts][-4:] == list(ROLES)
    assert [artifact.path for artifact in result.artifacts] == list(result.paths)


@contract("2")
def test_truth_columns_are_the_documented_ones_in_the_documented_order(truth_run: Path) -> None:
    """5.2: ``truth_id`` to ``expected_detection``."""
    header = _file(truth_run, "truth").read_text(encoding="utf-8").splitlines()[0]
    assert header.split(",") == DOCUMENTED_TRUTH_COLUMNS
    assert _json(truth_run, "manifest")["truth_columns"] == DOCUMENTED_TRUTH_COLUMNS
    raw = _file(truth_run, "truth").read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")


@contract("2")
def test_every_changes_line_has_exactly_one_injected_truth_line(truth_run: Path) -> None:
    """5.2: same ``event_id`` and ``column``."""
    changes = _csv_rows(_file(truth_run, "changes"))
    injected = [line for line in _truth(truth_run) if line["kind"] == "injected"]
    assert len(changes) == len(injected) == 10 * 2 + 5 + 3  # a swap writes two cells
    pairs = Counter((line["event_id"], line["column"]) for line in injected)
    assert all(count == 1 for count in pairs.values())
    assert set(pairs) == {(change["event_id"], change["column"]) for change in changes}
    by_event = {(line["event_id"], line["column"]): line for line in injected}
    operations = _truth_operations()
    for change in changes:
        line = by_event[(change["event_id"], change["column"])]
        operation = operations[int(change["operation_index"]) - 1]
        assert line["row_number"] == change["row_number"]
        assert (line["scenario_id"], line["category"], line["severity"]) == (
            operation["scenario_id"], operation["category"], operation["severity"])


@contract("2")
def test_every_cell_that_differs_from_the_clean_file_has_one_net_difference_line(
        tmp_path: Path, truth_run: Path) -> None:
    """5.2: and a cell restored by a later event has none."""
    clean = _csv_rows(truth_run / "insurance-combined.csv")
    altered = _csv_rows(_file(truth_run, "altered"))
    differs = {(str(number), column) for number, (before, after) in enumerate(
        zip(clean, altered, strict=True), 2) for column in before if before[column] != after[column]}
    net = Counter((line["row_number"], line["column"]) for line in _truth(truth_run)
                  if line["kind"] == "net_difference")
    assert set(net) == differs and all(count == 1 for count in net.values())
    # C03: B swaps back 20 of the rows A swapped; those cells have events and no difference.
    restored = [
        _scenario("A", "swap", "nom", 300, value="telephone", can_overlap=True),
        _scenario("B", "swap", "nom", 20, value="telephone", can_overlap=True)]
    out, _ = _run_truth(tmp_path, restored, rows=300)
    lines = _truth(out)
    kinds = Counter(line["kind"] for line in lines)
    assert kinds["injected"] == 2 * (300 + 20)
    assert kinds["net_difference"] == 2 * (300 - 20)
    back = {line["row_number"] for line in lines if line["scenario_id"] == "B"}
    assert not any(line["kind"] == "net_difference" and line["row_number"] in back
                   for line in lines)
    assert _json(out, "metrics")["counts"] == {
        "events": 320, "changed_cells": 640, "distinct_changed_cells": 600,
        "net_differences": 560}


@contract("2")
def test_truth_ids_are_unique_and_rule_ids_exist_in_rules_json(truth_run: Path) -> None:
    """5.2 and 5.3."""
    lines = _truth(truth_run)
    assert [int(line["truth_id"]) for line in lines] == list(range(1, len(lines) + 1))
    rules = {cast(dict[str, str], rule)["id"]
             for rule in cast(list[object], _json(truth_run, "rules")["rules"])}
    assert rules == {"M01", "M23"}  # the rules the profile names, nothing else
    used = {line["rule_id"] for line in lines if line["rule_id"]}
    assert used <= rules
    violations = Counter(line["rule_id"] for line in lines if line["kind"] == "rule_violation")
    # The misread Quebec dates are unreadable, so M01 is unknown there, never a violation.
    assert violations == {"M01": 10, "M23": 5}
    assert _json(truth_run, "metrics")["rules"] == {"M01": 10, "M23": 5}


@contract("2")
def test_truth_row_numbers_count_the_header_as_line_one_like_changes_csv(
        truth_run: Path) -> None:
    """5.2: ``row_number`` indexes the altered file the same way as the journal."""
    def lines_of(path: Path) -> list[list[str]]:
        with path.open(encoding="utf-8", newline="") as stream:
            return list(csv.reader(stream))

    altered = lines_of(_file(truth_run, "altered"))
    clean = lines_of(truth_run / "insurance-combined.csv")
    header = altered[0]
    nets = [line for line in _truth(truth_run) if line["kind"] == "net_difference"]
    assert nets
    for line in nets:
        number, column = int(line["row_number"]), header.index(line["column"])
        # Line ``number`` of the file, the header being line 1, is where the cell differs.
        assert altered[number - 1][column] != clean[number - 1][column]
    # The canonical value of a misread date keeps the intended day (contract 4.5).
    misread = [line for line in _truth(truth_run)
               if line["scenario_id"] == "F19" and line["kind"] == "injected"]
    assert len(misread) == 3
    clean_rows = _csv_rows(truth_run / "insurance-combined.csv")
    for line in misread:
        day, month, year = clean_rows[int(line["row_number"]) - 2]["date_debut"].split("-")
        assert line["canonical_value"] == f"{year}-{month}-{day}"


@contract("2")
def test_outputs_are_identical_byte_for_byte_for_the_same_inputs(
        tmp_path: Path, truth_run: Path) -> None:
    """1 and 5.5: seed, profile, rows, as-of date and generation version fix every byte."""
    out, result = _run_truth(tmp_path)
    names = sorted(path.name for path in result.paths)
    assert names == sorted(path.name for path in truth_run.iterdir())
    for name in names:
        assert (out / name).read_bytes() == (truth_run / name).read_bytes(), name


@contract("2")
def test_manifest_lists_the_sha256_of_every_other_artifact(truth_run: Path) -> None:
    """5.5: bytes and digest per role; never its own digest."""
    import hashlib

    manifest = _json(truth_run, "manifest")
    files_listed = cast(list[dict[str, object]], manifest["files"])
    own = _file(truth_run, "manifest").name
    assert {entry["name"] for entry in files_listed} == {
        path.name for path in truth_run.iterdir()} - {own}
    for entry in files_listed:
        data = (truth_run / cast(str, entry["name"])).read_bytes()
        assert entry["bytes"] == len(data)
        assert entry["sha256"] == hashlib.sha256(data).hexdigest()
    assert [entry["role"] for entry in files_listed][-3:] == ["truth", "rules", "metrics"]
    assert {key: manifest[key] for key in ("seed", "rows", "as_of_date", "profile",
                                           "output_profile", "generation_version")} == {
        "seed": 42, "rows": TRUTH_ROWS, "as_of_date": "2026-09-16", "profile": TRUTH_PROFILE,
        "output_profile": "default", "generation_version": 2}
    scenarios = cast(list[dict[str, object]], manifest["scenarios"])
    assert [(s["id"], s["description"], s["operations"], s["expected_cases"])
            for s in scenarios] == [
        ("R08", "Contract ending before it starts", [1], 10), ("R11", None, [2], 5),
        ("F19", None, [3], 3)]


@contract("2")
def test_existing_artifacts_collide_without_force_and_nothing_is_published(
        tmp_path: Path) -> None:
    """5.1: the protection of ``_publish_artifacts`` covers the new kinds."""
    package = _insurance_package(tmp_path, _truth_operations(), profile=TRUTH_PROFILE)
    out = tmp_path / "out"
    out.mkdir()
    existing = _file(out, "metrics")
    existing.write_text("mine", encoding="utf-8")
    with pytest.raises(ReportError, match=r"(?s)output already exists.*metrics\.json"):
        build_generate_plan(package, rows=300, seed=42, output_dir=out,
                            anomaly_profile=TRUTH_PROFILE)
    # A file that appears between the plan and the publication is never replaced either.
    existing.unlink()
    plan = build_generate_plan(package, rows=300, seed=42, output_dir=out,
                               anomaly_profile=TRUTH_PROFILE)
    late = _file(out, "manifest")
    late.write_text("late", encoding="utf-8")
    with pytest.raises(ReportError, match=r"(?s)output already exists.*manifest\.json"):
        generate_datasets(plan)
    assert [path.name for path in out.iterdir()] == [late.name]
    assert late.read_text(encoding="utf-8") == "late"
    forced = build_generate_plan(package, rows=300, seed=42, output_dir=out,
                                 anomaly_profile=TRUTH_PROFILE, force=True)
    generate_datasets(forced)
    assert _json(out, "manifest")["format"] == "tabalyst.generate.manifest"


@contract("2")
def test_json_files_carry_format_0_2_0_revision_1_and_match_their_schema(
        truth_run: Path) -> None:
    """5.7: ``format``, ``format_version``, ``format_revision`` and the committed schema."""
    import jsonschema

    schemas = ROOT / "src/tabalyst/schemas"
    for role in ("rules", "metrics", "manifest"):
        document = _json(truth_run, role)
        assert (document["format"], document["format_version"], document["format_revision"]) == (
            f"tabalyst.generate.{role}", "0.2.0", 1)
        schema = json.loads((schemas / f"tabalyst.generate.{role}.schema.json").read_text(
            encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate(document, schema, cls=jsonschema.Draft202012Validator)
        assert {"format", "format_version", "format_revision"} <= set(schema["required"])
    # The summary of the package keeps its own, unrelated format.
    summary = _json(truth_run, "summary")
    assert (summary["format"], summary["format_version"]) == ("tabalyst.generate.package",
                                                              "0.1.0")


@contract("2")
def test_committed_schemas_are_not_stale() -> None:
    """5.7: regenerated from the models they equal the committed files."""
    from tabalyst.generate_truth import SCHEMA_FILES, generate_schemas

    for role, text in generate_schemas().items():
        committed = ROOT / "src/tabalyst/schemas" / SCHEMA_FILES[role]
        assert committed.read_text(encoding="utf-8") == text, role


@contract("2")
def test_clean_file_satisfies_every_rule_of_the_profile_before_injection(tmp_path: Path) -> None:
    """5.3 and ADR 2026-11-11: the generator checks its clean file with ``generate_rules``."""
    from tabalyst.generate_columns_package import load_columns_definition
    from tabalyst.generate_rules import RuleContext, RuleEvaluator

    generate_datasets(build_generate_plan(example="insurance", rows=3000, seed=42,
                                          output_dir=tmp_path / "clean"))
    catalogue = load_columns_definition(load_generate_package(PACKAGE)).rules
    assert catalogue is not None
    evaluator = RuleEvaluator(catalogue.rules, RuleContext(catalogue.conventions, "2026-09-16"))
    rows = _csv_rows(tmp_path / "clean" / "insurance-combined.csv")
    assert [v for number, row in enumerate(rows, 2) for v in evaluator.check(number, row)] == []
    # A catalogue whose rule the clean file breaks stops the run before anything is published.
    package = _insurance_package(tmp_path / "broken", [
        _scenario("S1", "set_missing", "courriel", 2, rule_id="M14")])
    rules = package / "rules.yaml"
    rules.write_text(rules.read_text(encoding="utf-8").replace(
        'right: {value: "0"}', 'right: {value: "100000"}'), encoding="utf-8")
    out = tmp_path / "broken" / "out"
    plan = build_generate_plan(package, rows=300, seed=42, output_dir=out,
                               anomaly_profile="v2_test")
    with pytest.raises(ReportError, match=r"the clean file breaks rule M14 \(Annual premium "
                                          r"above zero\) at row 2"):
        generate_datasets(plan)
    assert not out.exists() or list(out.iterdir()) == []


# --- Lot 3: rarity levels and rare_events (contract 6) ---------------------------------------

RARE_ROWS = 100_000
# Contract 6.2: cases per scenario of ``rare_events`` and the level they carry.
RARE_CASES = {"R01": (1, "single"), "R02": (5, "extremely_rare"), "R05": (20, "very_rare"),
              "R06": (25, "very_rare"), "R07": (50, "very_rare"), "R08": (50, "very_rare"),
              "R10": (100, "rare"), "R11": (250, "uncommon"), "R12": (500, "uncommon"),
              "B01": (100, "rare"), "B02": (100, "rare")}
SAMPLE_SIZES = (500, 1000, 5000, 10000, 50000)


@pytest.fixture(scope="module")
def rare_run(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One ``rare_events`` run at the floor of 100,000 rows, shared by the tests that read it."""
    if "3" not in ENABLED_LOTS:
        pytest.skip("Insurance V2 lot 3 is not implemented yet")
    out = tmp_path_factory.mktemp("rare") / "out"
    generate_datasets(build_generate_plan(
        example="insurance", rows=RARE_ROWS, seed=42, output_dir=out,
        anomaly_profile="rare_events"))
    return out


def _rare(out: Path, suffix: str) -> Path:
    return out / f"insurance-combined.rare_events.{suffix}"


def _rare_package(base: Path, floor: int, counts: dict[str, int]) -> Path:
    """A copy of the package whose ``rare_events`` has a lower floor and other counts.

    ``counts`` maps a scenario to the count of its first operation; the scenario is then
    labeled ``frequent`` so that its new total still falls in its band.
    """
    package = base / "package"
    shutil.copytree(PACKAGE, package)
    manifest = package / "dataset.yaml"
    document = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    profile = document["anomaly_profiles"]["rare_events"]
    profile["min_rows"] = floor
    seen: set[str] = set()
    for operation in profile["operations"]:
        scenario = operation["scenario_id"]
        if scenario in counts:
            operation["rarity_level"] = "frequent"
            if scenario not in seen:
                operation["count"] = counts[scenario]
        seen.add(scenario)
    manifest.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True),
                        encoding="utf-8")
    return package


@contract("3")
def test_rarity_levels_in_the_code_are_the_documented_nominal_counts_and_bands() -> None:
    """3.3: ``generate_rarity`` equals ``NOMINAL_CASES`` and ``RARITY_BANDS`` of this module."""
    from tabalyst import generate_rarity

    assert generate_rarity.NOMINAL_CASES == NOMINAL_CASES
    assert generate_rarity.RARITY_BANDS == RARITY_BANDS
    for level, cases in NOMINAL_CASES.items():
        assert generate_rarity.level_of(cases) == level
    for count, level in REPORT_COUNTS.values():
        assert generate_rarity.level_of(count) == level


@contract("3")
def test_rare_events_refuses_fewer_rows_than_its_floor(tmp_path: Path) -> None:
    """6.1: 99,999 rows fail naming the profile, the floor 100,000 and the request."""
    with pytest.raises(ConfigurationError, match=(
            r"Profile rare_events needs at least 100,000 rows on insurance-combined.*"
            r"99,999 requested")):
        build_generate_plan(example="insurance", rows=99_999, output_dir=tmp_path,
                            anomaly_profile="rare_events")
    plan = build_generate_plan(example="insurance", rows=RARE_ROWS, output_dir=tmp_path,
                               anomaly_profile="rare_events")
    assert plan.rows["insurance-combined"] == RARE_ROWS
    # A legacy profile has no floor, and a floor needs a scenario profile and the largest count.
    legacy = _insurance_package(tmp_path / "legacy", [
        {"kind": "format", "column": "nom", "value": "upper", "count": 5}])
    manifest = legacy / "dataset.yaml"
    document = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    document["anomaly_profiles"]["v2_test"]["min_rows"] = 100
    manifest.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True),
                        encoding="utf-8")
    with pytest.raises(ConfigurationError, match="min_rows is for a scenario profile"):
        validate_generate_package(legacy)
    low = _insurance_package(tmp_path / "low", [_scenario("A", "set_missing", "nom", 50)])
    manifest = low / "dataset.yaml"
    document = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    document["anomaly_profiles"]["v2_test"]["min_rows"] = 49
    manifest.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True),
                        encoding="utf-8")
    with pytest.raises(ConfigurationError, match=r"min_rows must be .* at least the largest total of its "
                                                 r"scenarios \(50\)"):
        validate_generate_package(low)


@contract("3")
def test_rare_events_applies_the_exact_count_of_every_scenario(rare_run: Path) -> None:
    """6.2: R01 1 case on 2 rows, R02 5, R05 20, R06 25, R07 50, R08 50, R10 100, R11 250, R12 500."""
    metrics = _csv_free_json(_rare(rare_run, "metrics.json"))
    scenarios = cast(dict[str, dict[str, object]], metrics["scenarios"])
    assert list(scenarios) == list(RARE_CASES)
    for scenario, (cases, level) in RARE_CASES.items():
        entry = scenarios[scenario]
        assert (entry["requested_cases"], entry["applied_cases"], entry["rarity_level"]) == (
            cases, cases, level), scenario
        assert entry["rows_touched"] == (2 if scenario == "R01" else cases), scenario
    # The rules that name a scenario find exactly its cases in the final file.
    assert metrics["rules"] == {"M01": 50, "M02": 0, "M04": 5, "M21": 2, "M23": 250}
    summary = _csv_free_json(_rare(rare_run, "summary.json"))
    assert summary["events"] == sum(cases for cases, _ in RARE_CASES.values())
    for entry in cast(list[dict[str, object]], summary["operations"]):
        assert entry["mode"] == "exact" and entry["applied_rows"] == entry["count"]


def _csv_free_json(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


@contract("3")
def test_rare_events_refuses_a_count_above_the_eligible_population(tmp_path: Path) -> None:
    """4.2 and 6.1: no partial application."""
    # 3,000 rows keep the run short: the floor of the copy follows the rows. The principal branch
    # holds about 2,180 of them, so 2,800 agency changes there cannot all apply.
    package = _rare_package(tmp_path, floor=3000, counts={"R12": 2800})
    out = tmp_path / "out"
    plan = build_generate_plan(package, rows=3000, seed=42, output_dir=out,
                               anomaly_profile="rare_events")
    with pytest.raises((ValueError, ReportError), match=r"operation 15 \(scenario R12\) asks "
                                                       r"for count 2800 but only \d+ rows"):
        generate_datasets(plan)
    assert not out.exists() or list(out.iterdir()) == []
    # With its own counts the same profile runs on the shorter file: only the floor is lowered.
    good = _rare_package(tmp_path / "good", floor=3000, counts={})
    result = generate_datasets(build_generate_plan(
        good, rows=3000, seed=42, output_dir=tmp_path / "good-out",
        anomaly_profile="rare_events"))
    assert len(result.artifacts) == 11


@contract("3")
def test_one_truth_line_per_rare_case_with_its_scenario_and_level(rare_run: Path) -> None:
    """5.2 and 6.2."""
    lines = _csv_rows(_rare(rare_run, "truth.csv"))
    for scenario, (cases, level) in RARE_CASES.items():
        injected = [line for line in lines if line["kind"] == "injected"
                    and line["scenario_id"] == scenario]
        assert {line["rarity_level"] for line in injected} == {level}
        assert len({line["row_number"] for line in injected}) == cases, scenario
        # A swap writes two cells, every other operation one.
        assert len(injected) == cases * (2 if scenario == "R08" else 1), scenario
    # R01: one case on two rows, told by two relational lines with one group.
    relational = [line for line in lines if line["kind"] == "relational"]
    assert len(relational) == 2 and {line["scenario_id"] for line in relational} == {"R01"}
    assert len({line["group_id"] for line in relational}) == 1
    first, second = sorted(relational, key=lambda line: int(line["row_number"]))
    assert first["group_id"] == f"R01-{first['row_number']}" and first["event_id"] == ""
    assert second["event_id"] != "" and {line["column"] for line in relational} == {"id_contrat"}
    altered = {number: row for number, row in enumerate(
        _csv_rows(rare_run / "insurance-combined.rare_events.csv"), 2)
        if str(number) in {first["row_number"], second["row_number"]}}
    keys = {row["id_contrat"] for row in altered.values()}
    assert len(keys) == 1  # the same key on both rows
    assert first["canonical_value"] != second["canonical_value"]  # each keeps its own key
    # R02 moves the birth date a century on (after the reference date) and the truth keeps the
    # real one as canonical value.
    rows = _csv_rows(rare_run / "insurance-combined.rare_events.csv")
    for line in lines:
        if line["scenario_id"] == "R02" and line["kind"] == "injected":
            assert line["canonical_value"] < "2026-09-16"
            altered_date = rows[int(line["row_number"]) - 2]["date_naissance"]
            assert max(altered_date[:4], altered_date[-4:]) > "2026"


@contract("3")
def test_valid_boundary_cases_are_valid_atypical_with_info_severity(
        tmp_path: Path, rare_run: Path) -> None:
    """3.1 and 6.2: valid, expected detection ``none``, never counted as violations."""
    lines = _csv_rows(_rare(rare_run, "truth.csv"))
    valid = [line for line in lines if line["kind"] == "valid_atypical"]
    assert len(valid) == 200 and {line["scenario_id"] for line in valid} == {"B01", "B02"}
    assert {(line["category"], line["severity"], line["expected_detection"]) for line in valid} == {
        ("valid_atypical", "info", "none")}
    rows = _csv_rows(rare_run / "insurance-combined.rare_events.csv")
    for line in valid:
        row = rows[int(line["row_number"]) - 2]
        if line["scenario_id"] == "B01":
            assert row["date_fin"] == row["date_debut"] and line["column"] == "date_fin"
        else:
            assert row["date_modification"] == row["date_creation"]
    # No rule is broken on those rows: they sit on the boundary the rule allows.
    boundary_rows = {line["row_number"] for line in valid}
    assert not any(line["kind"] == "rule_violation" and line["row_number"] in boundary_rows
                   for line in lines)
    assert not any(line["kind"] == "rule_violation" and line["scenario_id"] in {"B01", "B02"}
                   for line in lines)
    # A non-defect cannot claim a severity or a detection: it is refused at load.
    _refused(tmp_path / "severity", [_scenario(
        "B", "set_missing", "nom", 5, category="valid_atypical", severity="major",
        expected_detection="none")], r"severity must be info for a valid_atypical scenario")
    _refused(tmp_path / "detection", [_scenario(
        "B", "set_missing", "nom", 5, category="valid_atypical", severity="info",
        expected_detection="domain")], r"expected_detection must be none for a valid_atypical")


@contract("3")
@pytest.mark.parametrize("rows", sorted(ABSENCE_5000))
def test_absence_probability_matches_the_documented_values(rows: int) -> None:
    """6.3: ``generate_rarity`` agrees with ``ABSENCE_5000`` for the actual file size."""
    from math import comb

    from tabalyst.generate_rarity import absence_probability

    for cases, expected in ABSENCE_5000[rows].items():
        assert absence_probability(rows, cases, 5000) == expected
        assert absence_probability(rows, cases, 5000) == _absence(rows, cases, 5000)
    # The product is the hypergeometric ratio, checked against binomial coefficients.
    assert absence_probability(60, 4, 10) == pytest.approx(comb(56, 10) / comb(60, 10))
    assert absence_probability(60, 0, 10) == 1.0
    assert absence_probability(60, 51, 10) == 0.0  # fewer rows left out than cases
    assert absence_probability(60, 1, 61) is None  # a sample larger than the file


@contract("3")
def test_metrics_hold_the_absence_probability_for_every_documented_sample_size(
        tmp_path: Path, rare_run: Path) -> None:
    """6.3: 500, 1,000, 5,000, 10,000 and 50,000 per scenario."""
    metrics = _csv_free_json(_rare(rare_run, "metrics.json"))
    table = cast(dict[str, dict[str, object]], metrics["absence_probability"])
    assert list(table) == list(RARE_CASES)
    for scenario, (cases, _) in RARE_CASES.items():
        if scenario == "R01":
            continue
        entry = table[scenario]
        probability = cast(dict[str, float], entry["probability"])
        assert entry["cases"] == cases and entry["reason"] is None
        assert list(probability) == [str(size) for size in SAMPLE_SIZES]
        for size in SAMPLE_SIZES:
            assert probability[str(size)] == _absence(RARE_ROWS, cases, size), (scenario, size)
    # On a small file a sample larger than the file has no probability, never a made-up one.
    out, _ = _run_truth(tmp_path, [_scenario("A", "set_missing", "nom", 5)], rows=3000)
    small = cast(dict[str, dict[str, object]],
                 _json(out, "metrics")["absence_probability"])["A"]
    probability = cast(dict[str, float | None], small["probability"])
    assert probability["500"] == _absence(3000, 5, 500)
    assert probability["5000"] is None and probability["50000"] is None


@contract("3")
def test_a_multi_row_scenario_has_a_null_probability_with_its_reason(rare_run: Path) -> None:
    """6.3: ``null`` and ``"reason": "multi_row_case"`` for R01."""
    metrics = _csv_free_json(_rare(rare_run, "metrics.json"))
    table = cast(dict[str, dict[str, object]], metrics["absence_probability"])
    assert table["R01"] == {"cases": 1, "probability": None, "reason": "multi_row_case"}
    assert all(entry["reason"] is None for scenario, entry in table.items() if scenario != "R01")


@contract("3")
def test_rare_events_keeps_the_default_34_columns(rare_run: Path) -> None:
    """6.2 and 7: the profile needs no extended column."""
    for name in ("insurance-combined.csv", "insurance-combined.rare_events.csv"):
        header = (rare_run / name).read_text(encoding="utf-8").splitlines()[0]
        assert header.split(",") == [*FIELDS, "filiale"]
    manifest = _csv_free_json(_rare(rare_run, "manifest.json"))
    assert manifest["output_profile"] == "default" and manifest["generation_version"] == 2


# --- Lot 4: extended column profile (contract 7) ---------------------------------------


@contract("4")
def test_default_profile_keeps_34_columns_and_combined_35(tmp_path: Path) -> None:
    """7 and D1: without --output-profile, branches have 34 columns and combined has 35."""
    out = tmp_path / "default_out"
    plan = build_generate_plan(example="insurance", rows=100, seed=42, output_dir=out)
    assert plan.output_profile == "default"
    generate_datasets(plan)
    for branch in ("insurance-principal", "insurance-ontario", "insurance-quebec"):
        header = (out / f"{branch}.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
        assert header == list(FIELDS)
    combined_header = (out / "insurance-combined.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
    assert combined_header == [*FIELDS, "filiale"]


@contract("4")
def test_extended_output_profile_appends_10_columns_in_contract_order(tmp_path: Path) -> None:
    """7: extended appends the 10 priority columns; combined places filiale before them."""
    out_def = tmp_path / "default_out"
    out_ext = tmp_path / "extended_out"
    plan_def = build_generate_plan(example="insurance", rows=300, seed=42, output_dir=out_def)
    plan_ext = build_generate_plan(example="insurance", rows=300, seed=42, output_dir=out_ext,
                                   output_profile="extended")
    assert plan_ext.output_profile == "extended"
    generate_datasets(plan_def)
    generate_datasets(plan_ext)

    # Branches: 43 columns (*FIELDS, *EXTENDED_FIELDS)
    for branch in ("insurance-principal", "insurance-ontario", "insurance-quebec"):
        def_rows = _csv_rows(out_def / f"{branch}.csv")
        ext_rows = _csv_rows(out_ext / f"{branch}.csv")
        ext_header = (out_ext / f"{branch}.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
        assert ext_header == [*FIELDS, *EXTENDED_FIELDS]
        assert len(ext_header) == 43
        # First 33 columns are byte-identical
        for d_row, e_row in zip(def_rows, ext_rows, strict=True):
            for col in FIELDS:
                assert d_row[col] == e_row[col]

    # Combined: 44 columns (*FIELDS, "filiale", *EXTENDED_FIELDS)
    comb_def_rows = _csv_rows(out_def / "insurance-combined.csv")
    comb_ext_rows = _csv_rows(out_ext / "insurance-combined.csv")
    comb_ext_header = (out_ext / "insurance-combined.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
    assert comb_ext_header == [*FIELDS, "filiale", *EXTENDED_FIELDS]
    assert len(comb_ext_header) == 44
    # First 34 columns are byte-identical
    for d_row, e_row in zip(comb_def_rows, comb_ext_rows, strict=True):
        for col in (*FIELDS, "filiale"):
            assert d_row[col] == e_row[col]


@contract("4")
def test_clean_extended_file_satisfies_every_rule_on_20000_rows(tmp_path: Path) -> None:
    """7 and Lot 4 goal: the clean extended file satisfies every rule with zero exception on 20,000 rows."""
    from tabalyst.generate_columns_package import load_columns_definition
    from tabalyst.generate_rules import RuleContext, RuleEvaluator

    out = tmp_path / "extended_20k"
    plan = build_generate_plan(example="insurance", rows=20000, seed=42, output_dir=out,
                               output_profile="extended")
    generate_datasets(plan)

    catalogue = load_columns_definition(load_generate_package(PACKAGE)).rules
    assert catalogue is not None
    # All rules: M01, M02, M03, M04, M07, M08, M09, M10, M11, M12, M13, M14, M21, M23, M24, M25
    rule_ids = {r.id for r in catalogue.rules}
    assert {"M01", "M02", "M03", "M04", "M07", "M08", "M09", "M10", "M11", "M12", "M13", "M14", "M21", "M23", "M24", "M25"} <= rule_ids

    evaluator = RuleEvaluator(catalogue.rules, RuleContext(catalogue.conventions, "2026-09-16"))
    rows = _csv_rows(out / "insurance-combined.csv")
    assert len(rows) == 20000
    violations = [v for number, row in enumerate(rows, 2) for v in evaluator.check(number, row)]
    assert violations == []


@contract("4")
def test_unknown_output_profile_is_refused_for_insurance(tmp_path: Path) -> None:
    """7: an unknown output profile for Insurance fails."""
    for bad in ("compact", "standard", "unknown", "autre"):
        with pytest.raises(ConfigurationError, match=f"unsupported Insurance output profile {bad!r}"):
            build_generate_plan(example="insurance", rows=100, output_dir=tmp_path / "out",
                                output_profile=bad)


@contract("4")
def test_output_profile_is_refused_for_packages_without_profiles(tmp_path: Path) -> None:
    """Option applies to Computer and Insurance only."""
    with pytest.raises(ConfigurationError, match=r"--output-profile applies to the Computer and Insurance packages only\."):
        build_generate_plan(example="crm", rows=100, output_dir=tmp_path / "out",
                            output_profile="extended")


@contract("4")
def test_extended_columns_invariants_and_structural_absence(tmp_path: Path) -> None:
    """7: structural absence and cross-column coherence on clean rows."""
    out = tmp_path / "ext_inv"
    plan = build_generate_plan(example="insurance", rows=1000, seed=123, output_dir=out,
                               output_profile="extended")
    generate_datasets(plan)
    rows = _csv_rows(out / "insurance-combined.csv")

    for row in rows:
        # Absence structurelle
        if not row["date_reclamation"]:
            assert row["date_sinistre"] == ""
            assert row["montant_indemnise"] == ""
            assert row["nombre_reclamations"] == "0"
        else:
            assert row["date_sinistre"] != ""
            assert row["nombre_reclamations"] in {"1", "2", "3"}

        # Date de résiliation
        if row["statut_contrat"] == "résilié":
            assert row["date_resiliation"] != ""
        else:
            assert row["date_resiliation"] == ""

        # Courtier
        if row["canal_acquisition"] == "courtier":
            assert row["courtier_id"].startswith("CRT-")
        else:
            assert row["courtier_id"] == ""

        # Montants
        assert float(row["montant_couverture"]) > 0
        assert float(row["franchise"]) >= 0
        if row["montant_indemnise"]:
            assert float(row["montant_indemnise"]) >= 0
            assert float(row["montant_indemnise"]) <= float(row["montant_couverture"])


@contract("4")
def test_extended_manifest_records_output_profile(tmp_path: Path) -> None:
    """5.5 and 7: manifest.json carries output_profile: 'extended'."""
    pkg = _insurance_package(tmp_path / "pkg", [
        _scenario("S1", "set_missing", "courriel", 2, rule_id="M14")],
        profile=TRUTH_PROFILE)
    out = tmp_path / "manifest_out"
    plan = build_generate_plan(pkg, rows=300, seed=42, output_dir=out,
                               anomaly_profile=TRUTH_PROFILE, output_profile="extended")
    generate_datasets(plan)
    manifest = _json(out, "manifest")
    assert manifest["output_profile"] == "extended"


@contract("4")
def test_profile_scenario_error_reports_missing_columns_in_default_profile() -> None:
    """generate_scenarios.py: PROVIDING_PROFILES points to extended when column is missing."""
    from tabalyst.generate_scenarios import profile_scenario_error

    operations = [
        {"scenario_id": "S1", "kind": "set_missing", "column": "courriel", "count": 10,
         "requires": ["date_sinistre"], "category": "semantic_invalid", "severity": "minor",
         "rarity_level": "very_rare", "description": "test", "expected_detection": "domain"},
    ]
    # In default profile (35 columns without date_sinistre)
    default_cols = [*FIELDS, "filiale"]
    err_def = profile_scenario_error(operations, columns=default_cols, output_profile="default")
    assert err_def is not None
    assert "requires column 'date_sinistre'" in err_def
    assert "the extended output profile provides it" in err_def

    # In extended profile (44 columns with filiale)
    extended_cols = [*FIELDS, "filiale", *EXTENDED_FIELDS]
    err_ext = profile_scenario_error(operations, columns=extended_cols, output_profile="extended")
    assert err_ext is None


@contract("4")
def test_extended_streams_independence(tmp_path: Path) -> None:
    """4.4 and Lot 4 goal: extended columns draw from their own streams without shifting base rows."""
    from tabalyst.generate_insurance import extend_insurance_row
    from tabalyst.generate_values import _stream

    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"
    plan1 = build_generate_plan(example="insurance", rows=500, seed=777, output_dir=out1,
                                output_profile="extended")
    plan2 = build_generate_plan(example="insurance", rows=500, seed=777, output_dir=out2,
                                output_profile="extended")
    generate_datasets(plan1)
    generate_datasets(plan2)

    rows1 = _csv_rows(out1 / "insurance-principal.csv")
    rows2 = _csv_rows(out2 / "insurance-principal.csv")
    assert rows1 == rows2

    # Verifying that extend_insurance_row uses the column streams deterministically
    streams_a = {col: _stream(777, "insurance-principal", col, "extended") for col in EXTENDED_FIELDS}
    streams_b = {col: _stream(777, "insurance-principal", col, "extended") for col in EXTENDED_FIELDS}
    base_row = {col: rows1[0][col] for col in FIELDS}
    ext_a = extend_insurance_row(base_row, "principal", streams_a, "2026-09-16")
    ext_b = extend_insurance_row(base_row, "principal", streams_b, "2026-09-16")
    assert ext_a == ext_b
    assert {col: ext_a[col] for col in EXTENDED_FIELDS} == {col: rows1[0][col] for col in EXTENDED_FIELDS}


# --- Lot 5: format catalogue F01 to F22 (contract 4.2, 4.3, 4.5) ----------------------------


@contract("5")
def test_format_catalogue_package_validation_rejects_unknown_format(tmp_path: Path) -> None:
    """SRS 4 and 4.2: unknown format value fails validation with ConfigurationError."""
    pkg = _insurance_package(tmp_path / "pkg", [
        _scenario("F_BAD", "format", "ville", 5, value="unknown_format_xyz")],
        profile="bad_format")
    with pytest.raises(ConfigurationError, match=r"unknown format mutation"):
        validate_generate_package(pkg)


@contract("5")
def test_format_catalogue_v2_profile_generation(tmp_path: Path) -> None:
    """SRS 4 and 4.2: new format catalogue values execute correctly in a V2 profile."""
    operations = [
        _scenario("F01", "format", "ville", 5, value="surrounding_space"),
        _scenario("F03", "format", "code_postal", 5, value="insert_non_breaking_space"),
        _scenario("F04", "format", "nom", 5, value="unicode_nfd"),
        _scenario("F05", "format", "courriel", 5, value="title_case"),
        _scenario("F08", "format", "telephone", 5, value="phone_drop_digit"),
        _scenario("F10", "format", "courriel", 5, value="email_forbidden_domain"),
        _scenario("F11", "format", "code_postal", 5, value="postal_no_space"),
        _scenario("F12", "format", "code_postal", 5, value="postal_invalid_syntax"),
        _scenario("F13", "format", "prime_annuelle", 5, value="decimal_comma"),
        _scenario("F14", "format", "prime_annuelle", 5, value="thousands_space"),
        _scenario("F18", "format", "date_debut", 5, value="date_impossible"),
        _scenario("F20", "format", "date_debut", 5, value="date_swap_month_day",
                  when={"filiale": "quebec"}),
        _scenario("F21", "format", "id_client", 5, value="drop_leading_zeros"),
        _scenario("F22", "format", "nom", 5, value="similar_char"),
    ]
    pkg = _insurance_package(tmp_path / "pkg", operations, profile="v2_formats")
    out = tmp_path / "out"
    plan = build_generate_plan(pkg, rows=300, seed=42, output_dir=out, anomaly_profile="v2_formats")
    res = generate_datasets(plan)
    assert len(res.artifacts) > 0

    truth_file = out / "insurance-combined.v2_formats.truth.csv"
    assert truth_file.is_file()
    truth_rows = _csv_rows(truth_file)
    scenario_ids = {r["scenario_id"] for r in truth_rows}
    for op in operations:
        assert str(op["scenario_id"]) in scenario_ids


@contract("5")
def test_format_catalogue_f20_ambiguous_date_preserves_canonical_iso_value(tmp_path: Path) -> None:
    """SRS 4 and 4.5: F20 (date_swap_month_day) preserves clean ISO date as canonical_value."""
    operations = [
        _scenario("F20", "format", "date_debut", 5, value="date_swap_month_day",
                  when={"filiale": "quebec"}),
    ]
    pkg = _insurance_package(tmp_path / "pkg", operations, profile="v2_f20")
    out = tmp_path / "out"
    plan = build_generate_plan(pkg, rows=300, seed=42, output_dir=out, anomaly_profile="v2_f20")
    generate_datasets(plan)

    truth_rows = _csv_rows(out / "insurance-combined.v2_f20.truth.csv")
    f20_events = [r for r in truth_rows if r["scenario_id"] == "F20" and r["kind"] == "injected"]
    assert len(f20_events) == 5

    changes_rows = _csv_rows(out / "insurance-combined.v2_f20.changes.csv")
    f20_changes = {c["event_id"]: c for c in changes_rows}

    for ev in f20_events:
        change = f20_changes[ev["event_id"]]
        before = change["before"]  # DD-MM-YYYY in Quebec, e.g. 05-10-2026
        after = change["after"]    # MM-DD-YYYY, e.g. 10-05-2026
        d, m, y = before.split("-")
        expected_iso = f"{y}-{m}-{d}"
        assert ev["canonical_value"] == expected_iso
        assert after == f"{m}-{d}-{y}"
        assert after != ev["canonical_value"]


@contract("5")
def test_format_catalogue_canonical_decimal_and_nfc(tmp_path: Path) -> None:
    """SRS 4 and 4.5: F04 (NFD) has NFC canonical value; F13/F14 has plain decimal canonical value."""
    import unicodedata

    operations = [
        _scenario("F04", "format", "nom", 5, value="unicode_nfd"),
        _scenario("F13", "format", "prime_annuelle", 5, value="decimal_comma"),
        _scenario("F14", "format", "prime_annuelle", 5, value="thousands_space"),
    ]
    pkg = _insurance_package(tmp_path / "pkg", operations, profile="v2_canon")
    out = tmp_path / "out"
    plan = build_generate_plan(pkg, rows=300, seed=42, output_dir=out, anomaly_profile="v2_canon")
    generate_datasets(plan)

    truth_rows = _csv_rows(out / "insurance-combined.v2_canon.truth.csv")
    f04_events = [r for r in truth_rows if r["scenario_id"] == "F04" and r["kind"] == "injected"]
    assert len(f04_events) == 5
    for ev in f04_events:
        assert unicodedata.is_normalized("NFC", ev["canonical_value"])

    f13_events = [r for r in truth_rows if r["scenario_id"] == "F13" and r["kind"] == "injected"]
    assert len(f13_events) == 5
    for ev in f13_events:
        assert "," not in ev["canonical_value"]
        assert " " not in ev["canonical_value"]
        float(ev["canonical_value"])


@contract("5")
def test_format_defects_do_not_cause_spurious_business_rule_violations(tmp_path: Path) -> None:
    """SRS 4 and 5.8: Kleene 3-valued logic ensures format defects never trigger business rules."""
    operations = [
        _scenario("F18", "format", "date_debut", 10, value="date_impossible",
                  category="format_invalid"),
        _scenario("F20", "format", "date_debut", 10, value="date_swap_month_day",
                  when={"filiale": "quebec"}, category="contextual_invalid"),
        _scenario("F13", "format", "prime_annuelle", 10, value="decimal_comma",
                  category="format_variant"),
        _scenario("F14", "format", "prime_annuelle", 10, value="thousands_space",
                  category="format_variant"),
        _scenario("F08", "format", "telephone", 10, value="phone_drop_digit",
                  category="format_invalid"),
        _scenario("F09", "format", "courriel", 10, value="email_invalid",
                  category="format_invalid"),
    ]
    pkg = _insurance_package(tmp_path / "pkg", operations, profile="v2_kleene")
    out = tmp_path / "out"
    plan = build_generate_plan(pkg, rows=500, seed=42, output_dir=out, anomaly_profile="v2_kleene")
    generate_datasets(plan)

    truth_rows = _csv_rows(out / "insurance-combined.v2_kleene.truth.csv")
    rule_violations = [r for r in truth_rows if r["kind"] == "rule_violation"]
    assert len(rule_violations) == 0


@contract("5")
def test_format_catalogue_completeness_and_non_regression() -> None:
    """SRS 4: FORMAT_VALUES contains all 22 format catalog operations and preserves legacy ones."""
    from tabalyst.generate_anomalies import FORMAT_VALUES

    assert len(FORMAT_VALUES) == 52

    expected_f_ops = {
        "surrounding_space", "insert_non_breaking_space", "unicode_nfd", "unicode_nfc",
        "title_case", "phone_drop_digit", "email_invalid", "email_forbidden_domain",
        "postal_no_space", "postal_invalid_syntax", "decimal_comma", "decimal_dot",
        "thousands_space", "thousands_comma", "date_impossible", "date_swap_month_day",
        "drop_leading_zeros", "similar_char",
    }
    for op_name in expected_f_ops:
        assert op_name in FORMAT_VALUES, f"Missing format value: {op_name}"




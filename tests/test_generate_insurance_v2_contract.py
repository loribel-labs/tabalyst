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
import hashlib
import json
import re
import shutil
import tracemalloc
from collections import Counter
from collections.abc import Callable
from decimal import Decimal
from fractions import Fraction
from importlib.resources import files
from pathlib import Path
from typing import NoReturn, TypeVar, cast

import pytest
import yaml

from tabalyst.errors import ConfigurationError, ReportError
from tabalyst.generate_anomalies import CHANGE_FIELDS, AnomalyEvent, inject_anomalies
from tabalyst.generate_insurance import (
    EXTENDED_FIELDS,
    FIELDS,
    TRANCHE_B_FIELDS,
    TRANCHE_C_FIELDS,
    insurance_canonical,
)
from tabalyst.generate_malformed import generate_malformed_csvs, is_malformed_test_file
from tabalyst.generate_package import load_generate_package
from tabalyst.generate_service import (
    GenerateResult,
    build_generate_plan,
    generate_datasets,
    validate_generate_package,
)

ENABLED_LOTS: set[str] = {"0", "1", "2", "3", "4", "5", "6", "7", "9", "10", "11", "12", "13", "14", "15", "16", "17", "19"}

PACKAGE = Path(str(files("tabalyst").joinpath("generate_examples", "insurance")))
ROOT = Path(__file__).resolve().parents[1]
LEGACY_PROFILES = {"dirty_realistic", "dirty_stress", "rule_breaks"}
# The scenario profiles the package ships: each lot that delivers one adds it here (lots 3, 7, 11, 12, 13, 14, 15 and 16).
V2_PROFILES = {"rare_events", "format_vs_business", "anomaly_diversity", "clustered_errors", "missing_mechanisms", "schema_drift", "ml_fraud_imbalanced", "ml_leakage_test", "ml_multitask", "technical_stress"}

# Section 3.3 of the contract: the unit is the case; the band is what a scenario total may be.
NOMINAL_CASES = {"frequent": 5000, "uncommon": 500, "rare": 100, "very_rare": 50,
                 "extremely_rare": 5, "single": 1}
RARITY_BANDS = {"single": (1, 1), "extremely_rare": (2, 9), "very_rare": (10, 74),
                "rare": (75, 199), "uncommon": (200, 999), "frequent": (1000, None)}
# Section 3.3: the counts of the report (section 3) and the level their text implies.
REPORT_COUNTS = {"R02": (5, "extremely_rare"), "R03": (5, "extremely_rare"),
                 "R04": (10, "very_rare"), "R05": (20, "very_rare"), "R06": (25, "very_rare"),
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
RARE_CASES = {"R01": (1, "single"), "R02": (5, "extremely_rare"), "R03": (5, "extremely_rare"),
              "R04": (10, "very_rare"), "R05": (20, "very_rare"), "R06": (25, "very_rare"),
              "R07": (50, "very_rare"), "R08": (50, "very_rare"), "R09": (100, "rare"),
              "R10": (100, "rare"), "R11": (250, "uncommon"), "R12": (500, "uncommon"),
              "B01": (100, "rare"), "B02": (100, "rare"), "B03": (100, "rare")}
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
    assert metrics["rules"] == {
        "M01": 50, "M02": 0, "M04": 5, "M08": 10, "M10": 5, "M11": 100,
        "M19": 50, "M20": 500, "M21": 2, "M23": 250,
    }
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
    with pytest.raises((ValueError, ReportError), match=r"operation \d+ \(scenario R12\) asks "
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
    assert len(valid) == 300 and {line["scenario_id"] for line in valid} == {"B01", "B02", "B03"}
    assert {(line["category"], line["severity"], line["expected_detection"]) for line in valid} == {
        ("valid_atypical", "info", "none")}
    rows = _csv_rows(rare_run / "insurance-combined.rare_events.csv")
    for line in valid:
        row = rows[int(line["row_number"]) - 2]
        if line["scenario_id"] == "B01":
            assert row["date_fin"] == row["date_debut"] and line["column"] == "date_fin"
        elif line["scenario_id"] == "B02":
            assert row["date_modification"] == row["date_creation"]
        else:
            assert row["montant_indemnise"] == row["montant_couverture"]
    # No rule is broken on those rows: they sit on the boundary the rule allows.
    boundary_rows = {line["row_number"] for line in valid}
    assert not any(line["kind"] == "rule_violation" and line["row_number"] in boundary_rows
                   for line in lines)
    assert not any(line["kind"] == "rule_violation" and line["scenario_id"] in {"B01", "B02", "B03"}
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
    """6.2 and 7: completed rare_events uses the extended output profile (44 columns)."""
    for name in ("insurance-combined.csv", "insurance-combined.rare_events.csv"):
        header = (rare_run / name).read_text(encoding="utf-8").splitlines()[0]
        assert header.split(",") == [*FIELDS, "filiale", *EXTENDED_FIELDS]
    manifest = _csv_free_json(_rare(rare_run, "manifest.json"))
    assert manifest["output_profile"] == "extended" and manifest["generation_version"] == 2


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

    assert len(FORMAT_VALUES) == 61

    expected_f_ops = {
        "surrounding_space", "insert_non_breaking_space", "unicode_nfd", "unicode_nfc",
        "title_case", "phone_drop_digit", "email_invalid", "email_forbidden_domain",
        "postal_no_space", "postal_invalid_syntax", "decimal_comma", "decimal_dot",
        "thousands_space", "thousands_comma", "date_impossible", "date_swap_month_day",
        "drop_leading_zeros", "similar_char", "date_minus_decade",
    }
    for op_name in expected_f_ops:
        assert op_name in FORMAT_VALUES, f"Missing format value: {op_name}"


# --- Lot 6: business rules M01 to M25, tranche B, complete (contract 5.3, 7) -----------------

@contract("6")
def test_catalogue_m01_to_m25_is_complete_and_valid() -> None:
    """SRS 5 and 5.3: catalogue in rules.yaml contains all rules M01 to M25 (and temporal rules M26-M30) and validates."""
    from tabalyst.generate_columns_package import load_columns_definition

    pkg = load_generate_package(PACKAGE)
    catalogue = load_columns_definition(pkg).rules
    assert catalogue is not None
    assert len(catalogue.rules) >= 25
    rule_ids = [rule.id for rule in catalogue.rules]
    expected_ids = [f"M{i:02d}" for i in range(1, 26)]
    assert set(expected_ids).issubset(rule_ids)

    # Invariants on each rule
    for rule in catalogue.rules:
        assert rule.category in {
            "format_variant", "format_invalid", "semantic_invalid",
            "business_rule_violation", "contextual_invalid",
        }
        assert rule.severity in {"info", "minor", "major", "critical"}
        assert len(rule.columns) >= 1
        assert rule.title


@contract("6")
def test_clean_complete_profile_satisfies_every_rule_on_20000_rows(tmp_path: Path) -> None:
    """SRS 5, 7 and Lot 6 goal: clean complete file satisfies all 25 rules with 0 violations on 20,000 rows."""
    from tabalyst.generate_columns_package import load_columns_definition
    from tabalyst.generate_rules import RuleContext, RuleEvaluator

    out = tmp_path / "complete_20k"
    plan = build_generate_plan(example="insurance", rows=20000, seed=42, output_dir=out,
                               output_profile="complete")
    generate_datasets(plan)

    catalogue = load_columns_definition(load_generate_package(PACKAGE)).rules
    assert catalogue is not None
    evaluator = RuleEvaluator(catalogue.rules, RuleContext(catalogue.conventions, "2026-09-16"))
    rows = _csv_rows(out / "insurance-combined.csv")
    assert len(rows) == 20000
    violations = [v for number, row in enumerate(rows, 2) for v in evaluator.check(number, row)]
    assert violations == []


@contract("6")
def test_complete_output_profile_appends_tranche_b_columns_in_contract_order(tmp_path: Path) -> None:
    """7: complete appends tranche B and tranche C columns; non-regression on default and extended columns."""
    from tabalyst.generate_insurance import EXTENDED_FIELDS

    out_def = tmp_path / "def_out"
    out_ext = tmp_path / "ext_out"
    out_com = tmp_path / "com_out"
    plan_def = build_generate_plan(example="insurance", rows=300, seed=42, output_dir=out_def)
    plan_ext = build_generate_plan(example="insurance", rows=300, seed=42, output_dir=out_ext,
                                   output_profile="extended")
    plan_com = build_generate_plan(example="insurance", rows=300, seed=42, output_dir=out_com,
                                   output_profile="complete")
    assert plan_com.output_profile == "complete"
    generate_datasets(plan_def)
    generate_datasets(plan_ext)
    generate_datasets(plan_com)

    # Branches: 50 columns (*FIELDS, *EXTENDED_FIELDS, *TRANCHE_B_FIELDS, *TRANCHE_C_FIELDS)
    for branch in ("insurance-principal", "insurance-ontario", "insurance-quebec"):
        def_rows = _csv_rows(out_def / f"{branch}.csv")
        ext_rows = _csv_rows(out_ext / f"{branch}.csv")
        com_rows = _csv_rows(out_com / f"{branch}.csv")
        com_header = (out_com / f"{branch}.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
        assert com_header == [*FIELDS, *EXTENDED_FIELDS, *TRANCHE_B_FIELDS, *TRANCHE_C_FIELDS]
        assert len(com_header) == 50

        # Byte-identical non-regression for the first 33 columns and 43 columns
        for d_row, e_row, c_row in zip(def_rows, ext_rows, com_rows, strict=True):
            for col in FIELDS:
                assert d_row[col] == e_row[col] == c_row[col]
            for col in EXTENDED_FIELDS:
                assert e_row[col] == c_row[col]
            for col in TRANCHE_B_FIELDS:
                assert c_row[col]

    # Combined: 51 columns (*FIELDS, "filiale", *EXTENDED_FIELDS, *TRANCHE_B_FIELDS, *TRANCHE_C_FIELDS)
    comb_def_rows = _csv_rows(out_def / "insurance-combined.csv")
    comb_ext_rows = _csv_rows(out_ext / "insurance-combined.csv")
    comb_com_rows = _csv_rows(out_com / "insurance-combined.csv")
    comb_com_header = (out_com / "insurance-combined.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
    assert comb_com_header == [*FIELDS, "filiale", *EXTENDED_FIELDS, *TRANCHE_B_FIELDS, *TRANCHE_C_FIELDS]
    assert len(comb_com_header) == 51

    for d_row, e_row, c_row in zip(comb_def_rows, comb_ext_rows, comb_com_rows, strict=True):
        for col in (*FIELDS, "filiale"):
            assert d_row[col] == e_row[col] == c_row[col]
        for col in EXTENDED_FIELDS:
            assert e_row[col] == c_row[col]
        for col in TRANCHE_B_FIELDS:
            assert c_row[col]


@contract("6")
def test_tranche_b_columns_invariants_and_types(tmp_path: Path) -> None:
    """7 and SRS 5, 10: tranche B columns have correct formats, bounds, and domains."""
    out = tmp_path / "tranche_b_inv"
    plan = build_generate_plan(example="insurance", rows=1000, seed=777, output_dir=out,
                               output_profile="complete")
    generate_datasets(plan)
    rows = _csv_rows(out / "insurance-combined.csv")

    for row in rows:
        # 1. taux_remboursement: decimal between 0.00 and 1.00
        rate = Decimal(row["taux_remboursement"])
        assert Decimal("0.00") <= rate <= Decimal("1.00")

        # 2. consentement_communication: boolean category
        assert row["consentement_communication"] in {"true", "false"}

        # 3. gestionnaire_id: GES-XXX
        assert re.fullmatch(r"GES-\d{3}", row["gestionnaire_id"]) is not None

        # 4. segment_client: allowed category
        assert row["segment_client"] in {"particulier", "professionnel", "entreprise", "vip"}


@contract("6")
def test_rare_events_completed_scenarios_and_truth_verifiable_from_rules_json_alone(rare_run: Path) -> None:
    """6.2, 5.3: rare_events is complete (R03, R04, R09, B03); violations verifiable from rules.json alone."""
    from tabalyst.generate_rules import RuleContext, RuleEvaluator, RulesDocument

    truth_rows = _csv_rows(_rare(rare_run, "truth.csv"))
    scenarios_in_truth = {r["scenario_id"] for r in truth_rows}
    assert {"R03", "R04", "R09", "B03"} <= scenarios_in_truth

    # Specific counts of the new rare events
    r03_injected = [r for r in truth_rows if r["kind"] == "injected" and r["scenario_id"] == "R03"]
    assert len(r03_injected) == 5
    r04_injected = [r for r in truth_rows if r["kind"] == "injected" and r["scenario_id"] == "R04"]
    assert len(r04_injected) == 10
    r09_injected = [r for r in truth_rows if r["kind"] == "injected" and r["scenario_id"] == "R09"]
    assert len(r09_injected) == 100
    b03_valid = [r for r in truth_rows if r["kind"] == "valid_atypical" and r["scenario_id"] == "B03"]
    assert len(b03_valid) == 100

    # Verification from rules.json alone: load document and evaluate without Python code or package YAML
    rules_doc_path = _rare(rare_run, "rules.json")
    assert rules_doc_path.is_file()
    doc = RulesDocument.model_validate_json(rules_doc_path.read_text(encoding="utf-8"))
    assert len(doc.rules) >= 10
    evaluator = RuleEvaluator(doc.rules, RuleContext(doc.conventions, doc.as_of_date))

    csv_rows = _csv_rows(rare_run / "insurance-combined.rare_events.csv")
    re_evaluated_violations = [
        v for number, row in enumerate(csv_rows, 2)
        for v in evaluator.check(number, row)
    ]
    # Truth rule_violation lines
    truth_violations = [r for r in truth_rows if r["kind"] == "rule_violation"]
    assert len(re_evaluated_violations) == len(truth_violations)
    truth_set = {(r["rule_id"], int(r["row_number"])) for r in truth_violations}
    re_eval_set = {(v.rule_id, v.row_number) for v in re_evaluated_violations}
    assert re_eval_set == truth_set


@contract("6")
def test_composite_violations_and_contextual_invalid_behavior(tmp_path: Path) -> None:
    """SRS 5.3, D9: composite multi-column violations and contextual_invalid category."""
    operations = [
        _scenario("R04", "format", "date_sinistre", 5, value="date_minus_decade",
                  when={"reclamation_status": "fermé"}, rule_id="M08",
                  category="business_rule_violation"),
        _scenario("R06", "format", "date_debut", 5, value="date_dmy",
                  when={"filiale": "principal"},
                  category="contextual_invalid"),
        _scenario("R09", "replace", "montant_indemnise", 5, value="9999999.00",
                  when={"reclamation_status": "fermé"}, rule_id="M11",
                  category="business_rule_violation"),
    ]
    pkg = _insurance_package(tmp_path / "pkg", operations, profile="v2_comp")
    out = tmp_path / "out"
    plan = build_generate_plan(pkg, rows=500, seed=42, output_dir=out,
                               anomaly_profile="v2_comp", output_profile="extended")
    generate_datasets(plan)

    truth_rows = _csv_rows(out / "insurance-combined.v2_comp.truth.csv")
    categories = {r["scenario_id"]: r["category"] for r in truth_rows}
    assert categories["R06"] == "contextual_invalid"
    assert categories["R04"] == "business_rule_violation"
    assert categories["R09"] == "business_rule_violation"

    # Composite violations flagged on rule M08 and M11
    rule_violations = [r for r in truth_rows if r["kind"] == "rule_violation"]
    assert len(rule_violations) == 10  # 5 for M08 + 5 for M11


def _profile_json(out: Path, profile: str, role: str) -> dict[str, object]:
    path = out / f"insurance-combined.{profile}.{role}.json"
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


@contract("7")
def test_profile_format_vs_business_has_equal_counts_and_no_cross_contamination(
        tmp_path: Path) -> None:
    """SRS 4, 17, plan lot 7: format_vs_business has identical format and business error counts."""
    out = tmp_path / "fvb"
    plan = build_generate_plan(example="insurance", rows=10000, seed=42, output_dir=out,
                               anomaly_profile="format_vs_business")
    generate_datasets(plan)

    metrics = _profile_json(out, "format_vs_business", "metrics")
    categories = cast(dict[str, int], metrics["categories"])
    format_count = categories["format_variant"] + categories["format_invalid"]
    business_count = categories["business_rule_violation"] + categories["semantic_invalid"]
    assert format_count == 500
    assert business_count == 500
    assert format_count == business_count

    scenarios = cast(dict[str, dict[str, object]], metrics["scenarios"])
    assert scenarios["FB_F01"]["applied_cases"] == 250
    assert scenarios["FB_F02"]["applied_cases"] == 250
    assert scenarios["FB_B01"]["applied_cases"] == 250
    assert scenarios["FB_B02"]["applied_cases"] == 250

    truth_rows = _csv_rows(out / "insurance-combined.format_vs_business.truth.csv")
    rule_violations = [r for r in truth_rows if r["kind"] == "rule_violation"]
    violation_scenarios = {r["scenario_id"] for r in rule_violations}
    assert violation_scenarios == {"FB_B01", "FB_B02"}


@contract("7")
def test_profile_anomaly_diversity_covers_all_categories_and_detection_families(
        tmp_path: Path) -> None:
    """SRS 7 (E09, E10), 17: anomaly_diversity covers all six categories and detection families."""
    out = tmp_path / "ad"
    plan = build_generate_plan(example="insurance", rows=10000, seed=42, output_dir=out,
                               anomaly_profile="anomaly_diversity")
    generate_datasets(plan)

    metrics = _profile_json(out, "anomaly_diversity", "metrics")
    categories = cast(dict[str, int], metrics["categories"])
    for cat in ("format_variant", "format_invalid", "semantic_invalid",
                "business_rule_violation", "contextual_invalid", "valid_atypical"):
        assert categories[cat] > 0, f"Category {cat} must have positive cases"

    truth_rows = _csv_rows(out / "insurance-combined.anomaly_diversity.truth.csv")
    all_detections = set()
    for r in truth_rows:
        if r["expected_detection"]:
            for det in r["expected_detection"].split("|"):
                all_detections.add(det)
    required_families = {"syntactic", "domain", "cross_column", "contextual",
                         "statistical", "uniqueness", "none"}
    assert required_families <= all_detections

    relational_lines = [r for r in truth_rows if r["kind"] == "relational"]
    assert len(relational_lines) == 2
    assert relational_lines[0]["scenario_id"] == "AD_UNIQ"


@contract("7")
def test_profile_clustered_errors_measures_branch_agency_period_clusters(
        tmp_path: Path) -> None:
    """SRS 7 (E06, E07, E14, E15), 9 (C07): clustered_errors with Ontario root cause and group clusters."""
    out = tmp_path / "ce"
    plan = build_generate_plan(example="insurance", rows=10000, seed=42, output_dir=out,
                               anomaly_profile="clustered_errors")
    generate_datasets(plan)

    metrics = _profile_json(out, "clustered_errors", "metrics")
    root_causes = cast(dict[str, dict[str, object]], metrics.get("root_causes", {}))
    assert "ontario_import" in root_causes
    ontario_metrics = root_causes["ontario_import"]
    assert ontario_metrics["events"] == 450
    assert ontario_metrics["scenarios"] == ["CE_ON_AMOUNT", "CE_ON_DATE", "CE_ON_PHONE"]
    assert 150 <= cast(int, ontario_metrics["rows_touched"]) <= 450

    truth_rows = _csv_rows(out / "insurance-combined.clustered_errors.truth.csv")
    ontario_rows = [r for r in truth_rows if r["root_cause_id"] == "ontario_import" and r["kind"] == "injected"]
    assert len(ontario_rows) == 450

    altered_rows = _csv_rows(out / "insurance-combined.clustered_errors.csv")
    for r in ontario_rows:
        row_idx = int(r["row_number"]) - 2
        assert altered_rows[row_idx]["filiale"] == "ontario"

    agency_events = [r for r in truth_rows if r["scenario_id"] == "CE_AGENCY" and r["kind"] == "injected"]
    assert len(agency_events) == 100
    for r in agency_events:
        row_idx = int(r["row_number"]) - 2
        assert altered_rows[row_idx]["agence_code"] == "AG-QC-001"

    period_events = [r for r in truth_rows if r["scenario_id"] == "CE_PERIOD" and r["kind"] == "injected"]
    assert len(period_events) == 100
    for r in period_events:
        row_idx = int(r["row_number"]) - 2
        assert altered_rows[row_idx]["reclamation_status"] == "fermé"

    diffuse_events = [r for r in truth_rows if r["scenario_id"] == "CE_DIFFUSE" and r["kind"] == "injected"]
    diffuse_branches = {altered_rows[int(r["row_number"]) - 2]["filiale"] for r in diffuse_events}
    assert len(diffuse_branches) > 1


@contract("7")
def test_root_cause_id_traceability_in_truth_and_metrics(tmp_path: Path) -> None:
    """SRS 9 (C07), contract 3.5, 5.4: root_cause_id traceability in truth.csv and metrics.json."""
    operations = [
        _scenario("RC01", "format", "telephone", 10, value="phone_drop_digit",
                  root_cause_id="batch_failure", can_overlap=True),
        _scenario("RC02", "replace", "statut_contrat", 10, value="inconnu",
                  rule_id="M23", root_cause_id="batch_failure", can_overlap=True),
    ]
    pkg = _insurance_package(tmp_path / "pkg", operations, profile="v2_rc")
    out = tmp_path / "out"
    plan = build_generate_plan(pkg, rows=500, seed=42, output_dir=out, anomaly_profile="v2_rc")
    generate_datasets(plan)

    metrics = _profile_json(out, "v2_rc", "metrics")
    assert "batch_failure" in cast(dict[str, object], metrics["root_causes"])
    rc_metric = cast(dict[str, object], cast(dict[str, object], metrics["root_causes"])["batch_failure"])
    assert rc_metric["events"] == 20
    assert rc_metric["scenarios"] == ["RC01", "RC02"]

    truth_rows = _csv_rows(out / "insurance-combined.v2_rc.truth.csv")
    for r in truth_rows:
        if r["scenario_id"] in {"RC01", "RC02"}:
            assert r["root_cause_id"] == "batch_failure"


@contract("7")
def test_interaction_c03_inadvertent_compensation(tmp_path: Path) -> None:
    """SRS 9 (C03): two inverse operations restore clean cell state (injected > 0, net_differences == 0)."""
    # Two successive swaps on all rows invert then restore prenom and nom
    operations = [
        _scenario("C03_A", "swap", "prenom", 20, value="nom", can_overlap=True),
        _scenario("C03_B", "swap", "prenom", 20, value="nom", can_overlap=True),
    ]
    pkg = _insurance_package(tmp_path / "pkg", operations, profile="v2_c03")
    out = tmp_path / "out"
    plan = build_generate_plan(pkg, rows=20, seed=42, output_dir=out, anomaly_profile="v2_c03")
    generate_datasets(plan)

    truth_rows = _csv_rows(out / "insurance-combined.v2_c03.truth.csv")
    injected = [r for r in truth_rows if r["kind"] == "injected"]
    # 20 rows * 2 cells * 2 operations = 80 injected events
    assert len(injected) == 80
    net_diffs = [r for r in truth_rows if r["kind"] == "net_difference"]
    assert len(net_diffs) == 0


@contract("7")
def test_interactions_c01_to_c10_comprehensive(tmp_path: Path) -> None:
    """SRS 9: verification of interaction mechanisms C01 to C10."""
    operations = [
        # C01 & C08: Overlapping anomalies on distinct columns (phone and courriel)
        _scenario("C01_P", "format", "telephone", 10, value="phone_spaces", can_overlap=True),
        _scenario("C01_M", "set_missing", "courriel", 10, can_overlap=True),

        # C04: Successive modifications of the same cell
        _scenario("C04_A", "format", "code_postal", 10, value="postal_no_space", can_overlap=True),
        _scenario("C04_B", "format", "code_postal", 10, value="similar_char", can_overlap=True),

        # C05: Three-valued logic isolation (syntax defect does not trigger business rule)
        _scenario("C05_F", "format", "date_debut", 5, value="date_impossible"),

        # C06: Relational identifier cascade
        _scenario("C06_R", "reuse_value", "id_contrat", 1, rule_id="M21",
                  category="business_rule_violation", severity="critical", rarity_level="single"),

        # C07: Common root cause
        _scenario("C07_A", "replace", "pays_code", 10, value="USA", root_cause_id="sys_incident"),
        _scenario("C07_B", "replace", "langue_preferee", 10, value="es", root_cause_id="sys_incident"),

        # C09: Product/segment constraint
        _scenario("C09_S", "replace", "statut_contrat", 5, value="inconnu",
                  when={"type_contrat": "auto"}, rule_id="M23"),
    ]
    pkg = _insurance_package(tmp_path / "pkg", operations, profile="v2_inter")
    out = tmp_path / "out"
    plan = build_generate_plan(pkg, rows=500, seed=42, output_dir=out, anomaly_profile="v2_inter")
    generate_datasets(plan)

    truth_rows = _csv_rows(out / "insurance-combined.v2_inter.truth.csv")

    # C01 & C08: Both telephone and courriel affected with overlap
    c01_rows = {r["row_number"] for r in truth_rows if r["scenario_id"] in {"C01_P", "C01_M"}}
    assert len(c01_rows) <= 20

    # C04: Two successive modifications on same column 'code_postal'
    c04_injected = [r for r in truth_rows if r["scenario_id"] in {"C04_A", "C04_B"} and r["kind"] == "injected"]
    assert len(c04_injected) == 20

    # C05: C05_F invalid date does NOT generate a rule_violation on M01
    c05_violations = [r for r in truth_rows if r["scenario_id"] == "C05_F" and r["kind"] == "rule_violation"]
    assert len(c05_violations) == 0

    # C06: Relational lines + M21 violation lines (one per row of the duplicated key group)
    c06_relational = [r for r in truth_rows if r["scenario_id"] == "C06_R" and r["kind"] == "relational"]
    assert len(c06_relational) == 2
    c06_violations = [r for r in truth_rows if r["scenario_id"] == "C06_R" and r["kind"] == "rule_violation"]
    assert len(c06_violations) == 2

    # C07: Root cause recorded
    c07_rows = [r for r in truth_rows if r["root_cause_id"] == "sys_incident"]
    assert len(c07_rows) > 0


@contract("7")
def test_quality_profiles_min_rows_floor_refusal(tmp_path: Path) -> None:
    """Contract 6.1: V2 quality profiles enforce min_rows floor (10,000)."""
    for profile in ("format_vs_business", "anomaly_diversity", "clustered_errors"):
        with pytest.raises(ConfigurationError, match=f"Profile {profile} needs at least 10,000 rows"):
            build_generate_plan(example="insurance", rows=9999, seed=42, output_dir=tmp_path / "out",
                                anomaly_profile=profile)


# --- Lot 9: relational outputs, table truth, G01-G10 (contract 8) ---------------------------


@contract("9")
def test_lot9_relational_tables_structure_and_manifests(tmp_path: Path) -> None:
    """Contract 8: --relational generates 4 clean tables and their truth manifests."""
    out = tmp_path / "relational"
    plan = build_generate_plan(PACKAGE, relational=True, rows=250, seed=42, output_dir=out)
    res = generate_datasets(plan)

    tables = ("clients", "contrats", "reclamations", "paiements")
    for tbl in tables:
        assert (out / f"{tbl}.csv").is_file()
        assert (out / f"{tbl}.truth.csv").is_file()
        assert (out / f"{tbl}.rules.json").is_file()
        assert (out / f"{tbl}.metrics.json").is_file()
        assert (out / f"{tbl}.manifest.json").is_file()

        manifest = json.loads((out / f"{tbl}.manifest.json").read_text(encoding="utf-8"))
        assert manifest["dataset"] == tbl
        assert manifest["rows"] == res.row_counts[tbl]
        assert len(manifest["files"]) == 4

    # Contracts match requested rows
    assert res.row_counts["contrats"] == 250
    # Multi-contract customers ensure client count is strictly lower than contract count
    assert 0 < res.row_counts["clients"] < 250


@contract("9")
def test_lot9_relational_truth_g09_g10_and_m22(tmp_path: Path) -> None:
    """Contract 8.3 & 8.5: G09, G10 relational atypical lines and M22 orphan claim."""
    out = tmp_path / "truth"
    plan = build_generate_plan(
        PACKAGE,
        relational=True,
        rows=500,
        seed=123,
        output_dir=out,
        anomaly_profile="dirty_realistic",
    )
    generate_datasets(plan)

    client_truth = _csv_rows(out / "clients.dirty_realistic.truth.csv")
    reclamation_truth = _csv_rows(out / "reclamations.dirty_realistic.truth.csv")

    # G09 shared address without duplicate: valid_atypical & relational
    g09 = [r for r in client_truth if r["scenario_id"] == "G09"]
    assert len(g09) > 0
    assert all(r["kind"] == "relational" and r["category"] == "valid_atypical" for r in g09)
    assert all(r["column"] == "id_menage" for r in g09)

    # G10 near-identical identities: valid_atypical & relational
    g10 = [r for r in client_truth if r["scenario_id"] == "G10"]
    assert len(g10) > 0
    assert all(r["kind"] == "relational" and r["category"] == "valid_atypical" for r in g10)
    assert all(r["column"] == "nom" for r in g10)

    # M22 non-existent contract reference: rule_violation & relational
    m22 = [r for r in reclamation_truth if r["rule_id"] == "M22"]
    assert len(m22) == 2
    assert {r["kind"] for r in m22} == {"rule_violation", "relational"}
    assert all(r["column"] == "id_contrat" for r in m22)


@contract("9")
def test_lot9_flattened_multi_contract_profiles(tmp_path: Path) -> None:
    """Contract 7 & 8: Flattened multi-contract CSV profiles (34, 44, 51 columns)."""
    for profile, expected_cols in [
        ("flattened", 34),
        ("flattened-extended", 44),
        ("flattened-complete", 51),
    ]:
        out = tmp_path / profile
        plan = build_generate_plan(
            PACKAGE,
            output_profile=profile,
            rows=100,
            seed=42,
            output_dir=out,
        )
        generate_datasets(plan)
        combined_file = out / "insurance-combined.csv"
        assert combined_file.is_file()
        header = combined_file.read_text(encoding="utf-8").splitlines()[0].split(",")
        assert len(header) == expected_cols
        assert header[0] == "id_client"
        assert "id_contrat" in header
        assert "filiale" in header


@contract("9")
def test_lot9_relational_refusals(tmp_path: Path) -> None:
    """Contract 8: Refuse --relational on -o or non-insurance packages."""
    with pytest.raises(ConfigurationError, match="--relational generates multiple tables; use -d."):
        build_generate_plan(PACKAGE, relational=True, output=tmp_path / "single.csv")

    computer_pkg = Path(str(files("tabalyst").joinpath("generate_examples", "computer")))
    with pytest.raises(ConfigurationError, match="--relational applies to the Insurance package only."):
        build_generate_plan(computer_pkg, relational=True, output_dir=tmp_path / "rel_comp")


# --- Lot 10: Distributions D01 to D15 and sampling bias E01 to E18 (contract 8.7, §7 & §12) ---


@contract("10")
def test_lot10_distributions_d01_to_d15() -> None:
    """Contract 8.7 & §12: Statistical distributions in population model.

    D04 Pareto heavy tails, D08 Zipf power law on brokers, D09 seasonal variation,
    D11 continuous inflation, and D15 branch mixture.
    """
    from tabalyst.generate_population import PopulationModel
    from tabalyst.generate_references import CommonReferences

    refs = CommonReferences()
    pkg = load_generate_package(PACKAGE)
    model = PopulationModel(common=refs, package=pkg, seed=42, total_contracts=2000, as_of_date="2026-09-16")

    # D08: Broker power-law distribution
    broker_counts = Counter(ctr.courtier_id for ctr in model.contracts if ctr.courtier_id)
    assert len(broker_counts) > 20
    top_broker_share = broker_counts.most_common(1)[0][1] / sum(broker_counts.values())
    assert top_broker_share > 0.05

    # D04 / D13: Claim amounts include heavy-tail Pareto draws within valid caps
    settled_claims = [c for c in model.all_claims if c.reclamation_status == "fermé" and c.montant_reclamation]
    assert len(settled_claims) > 0
    amounts = [float(c.montant_reclamation) for c in settled_claims]
    assert max(amounts) > 5000.0

    # D09: Seasonality - check winter vs summer claim loss dates for auto/habitation
    auto_claims = [c for ctr in model.contracts if ctr.type_contrat in {"auto", "habitation"} for c in ctr.claims]
    winter_claims = sum(1 for c in auto_claims if c.date_sinistre.month in {12, 1, 2})
    summer_claims = sum(1 for c in auto_claims if c.date_sinistre.month in {6, 7, 8})
    assert winter_claims > summer_claims


@contract("10")
def test_lot10_row_ordering_e01_to_e03(tmp_path: Path) -> None:
    """Contract 8.7 & §7: Row ordering modes (E01 branch, E02 chronological, E03 agency, shuffled)."""
    from tabalyst.generate_population import PopulationModel
    from tabalyst.generate_references import CommonReferences

    refs = CommonReferences()
    pkg = load_generate_package(PACKAGE)

    # E01: Branch ordering
    m_branch = PopulationModel(common=refs, package=pkg, seed=42, total_contracts=300, row_order="branch")
    branches = [c.filiale for c in m_branch.contracts]
    changes = sum(1 for i in range(len(branches) - 1) if branches[i] != branches[i + 1])
    assert changes <= 2

    # E02: Chronological ordering
    m_chrono = PopulationModel(common=refs, package=pkg, seed=42, total_contracts=300, row_order="chronological")
    dates = [c.date_creation for c in m_chrono.contracts]
    assert dates == sorted(dates)

    # E03: Agency ordering
    m_agency = PopulationModel(common=refs, package=pkg, seed=42, total_contracts=300, row_order="agency")
    agencies = [c.agence_code for c in m_agency.contracts]
    assert agencies == sorted(agencies)

    # Shuffled ordering
    m_shuf = PopulationModel(common=refs, package=pkg, seed=42, total_contracts=300, row_order="shuffled")
    shuf_branches = [c.filiale for c in m_shuf.contracts]
    shuf_changes = sum(1 for i in range(len(shuf_branches) - 1) if shuf_branches[i] != shuf_branches[i + 1])
    assert shuf_changes > 10

    # CLI & Plan validation refusals
    with pytest.raises(ConfigurationError, match="Unsupported row order: 'invalid'"):
        build_generate_plan(PACKAGE, rows=100, seed=42, output_dir=tmp_path / "out", row_order="invalid")

    comp_pkg = Path(str(files("tabalyst").joinpath("generate_examples", "computer")))
    with pytest.raises(ConfigurationError, match="--row-order applies to the Insurance package only."):
        build_generate_plan(comp_pkg, rows=100, seed=42, output_dir=tmp_path / "out_comp", row_order="chronological")


@contract("10")
def test_lot10_simpson_paradox_e16() -> None:
    """Contract 8.7 & §7 E16: Mathematical proof of Simpson's paradox on generated population.

    Conditioned on each branch, broker-advised contracts have higher average premium than direct contracts.
    Aggregated globally, broker-advised contracts have LOWER average premium than direct contracts.
    """
    from tabalyst.generate_population import PopulationModel
    from tabalyst.generate_references import CommonReferences

    refs = CommonReferences()
    pkg = load_generate_package(PACKAGE)
    model = PopulationModel(common=refs, package=pkg, seed=42, total_contracts=3000, as_of_date="2026-09-16")

    data: dict[str, dict[str, list[float]]] = {}
    global_broker: list[float] = []
    global_direct: list[float] = []

    for ctr in model.contracts:
        prem = float(ctr.prime_annuelle)
        br = ctr.filiale
        ch = ctr.canal_acquisition
        if ch not in {"courtier", "direct"}:
            continue
        data.setdefault(br, {}).setdefault(ch, []).append(prem)
        if ch == "courtier":
            global_broker.append(prem)
        else:
            global_direct.append(prem)

    # Conditioned on every branch: broker average premium > direct average premium
    for br, channels in data.items():
        assert "courtier" in channels and "direct" in channels
        avg_broker_br = sum(channels["courtier"]) / len(channels["courtier"])
        avg_direct_br = sum(channels["direct"]) / len(channels["direct"])
        assert avg_broker_br > avg_direct_br, f"Branch {br}: broker {avg_broker_br} must be > direct {avg_direct_br}"

    # Aggregated globally: broker average premium < direct average premium (Simpson's reversal)
    avg_broker_global = sum(global_broker) / len(global_broker)
    avg_direct_global = sum(global_direct) / len(global_direct)
    assert avg_broker_global < avg_direct_global, (
        f"Global Simpson reversal failed: broker {avg_broker_global} should be < direct {avg_direct_global}"
    )


@contract("10")
def test_lot10_dense_subpopulation_cluster() -> None:
    """Contract 8.7 & §12: Dense subpopulation cluster (200 consecutive contracts with 20% claim rate)."""
    from tabalyst.generate_population import PopulationModel
    from tabalyst.generate_references import CommonReferences

    refs = CommonReferences()
    pkg = load_generate_package(PACKAGE)
    model = PopulationModel(common=refs, package=pkg, seed=42, total_contracts=1000, as_of_date="2026-09-16")

    dense_contracts = [c for c in model.contracts if 501 <= c.contract_seq <= 700]
    assert len(dense_contracts) == 200
    claims_in_dense = sum(1 for c in dense_contracts if c.claims)
    rate = claims_in_dense / len(dense_contracts)
    assert 0.14 <= rate <= 0.28


@contract("10")
def test_lot10_unseen_categories_e18() -> None:
    """Contract 8.7 & §7 E18: Unseen category - VOY_MULTI absent before 2024-01-01, present after."""
    from datetime import date

    from tabalyst.generate_population import PopulationModel
    from tabalyst.generate_references import CommonReferences

    refs = CommonReferences()
    pkg = load_generate_package(PACKAGE)
    model = PopulationModel(common=refs, package=pkg, seed=42, total_contracts=2500, as_of_date="2026-09-16")

    before_2024 = [c for c in model.contracts if c.date_creation < date(2024, 1, 1)]
    after_2024 = [c for c in model.contracts if c.date_creation >= date(2024, 1, 1)]

    # Before 2024: strictly zero occurrences of VOY_MULTI
    assert len(before_2024) > 500
    assert not any(c.produit_code == "VOY_MULTI" for c in before_2024)

    # After 2024: present
    assert len(after_2024) > 100
    voy_multi_after = sum(1 for c in after_2024 if c.produit_code == "VOY_MULTI")
    assert voy_multi_after > 0


@contract("10")
def test_lot10_default_non_regression() -> None:
    """Contract 2 & 8.4: InsuranceProvider.row() remains strictly identical for default generation."""
    import random

    from tabalyst.generate_insurance import InsuranceProvider
    from tabalyst.generate_references import CommonReferences

    refs = CommonReferences()
    pkg = load_generate_package(PACKAGE)
    prov = InsuranceProvider(refs, pkg)

    row_1 = prov.row("principal", 1, random.Random(42), "2026-09-16")
    assert row_1["id_client"] == "CLI-00000001"
    assert row_1["id_contrat"] == "CTR-1000000001"
    assert len(row_1) == 33


# --- Lot 11: Missing data mechanisms MCAR, MAR, MNAR and reasons (contract 5.4, §10 & §11) ---


@contract("11")
def test_lot11_missing_mechanisms_validation_refusals(tmp_path: Path) -> None:
    """Contract 5.4 & SRS §11: Strict validation of missing data mechanisms and reasons."""
    # Invalid missing_mechanism value
    _refused(
        tmp_path / "bad_mech",
        [{**_scenario("S1", "set_missing", "nom", 5), "missing_mechanism": "invalid"}],
        r"operation\.missing_mechanism must be one of mar, mcar, mnar",
    )

    # MCAR must not declare a when condition (independent missingness)
    _refused(
        tmp_path / "mcar_when",
        [{**_scenario("S1", "set_missing", "nom", 5), "missing_mechanism": "mcar", "when": {"filiale": "ontario"}}],
        r"operation\.missing_mechanism mcar must not declare when",
    )

    # MAR requires when condition on an observed variable
    _refused(
        tmp_path / "mar_no_when",
        [{**_scenario("S1", "set_missing", "nom", 5), "missing_mechanism": "mar"}],
        r"operation\.missing_mechanism mar requires when condition on observed variable",
    )

    # MAR must condition on a different column than the missing column
    _refused(
        tmp_path / "mar_same_col",
        [{**_scenario("S1", "set_missing", "nom", 5), "missing_mechanism": "mar", "when": {"nom": "Dupont"}}],
        r"operation\.missing_mechanism mar must condition on a different column",
    )

    # MNAR requires when condition on the missing column itself
    _refused(
        tmp_path / "mnar_no_when",
        [{**_scenario("S1", "set_missing", "nom", 5), "missing_mechanism": "mnar"}],
        r"operation\.missing_mechanism mnar requires when condition on the missing column itself",
    )

    # MNAR must condition on the missing column itself
    _refused(
        tmp_path / "mnar_other_col",
        [{**_scenario("S1", "set_missing", "nom", 5), "missing_mechanism": "mnar", "when": {"filiale": "ontario"}}],
        r"operation\.missing_mechanism mnar must condition on the missing column itself",
    )

    # Invalid missing_reason
    _refused(
        tmp_path / "bad_reason",
        [{**_scenario("S1", "set_missing", "nom", 5), "missing_mechanism": "mcar", "missing_reason": "bad_reason"}],
        r"operation\.missing_reason must be one of client_refusal, not_applicable, system_omission, unknown, unreported",
    )

    # missing_mechanism on non-set_missing operation
    _refused(
        tmp_path / "bad_kind",
        [{**_scenario("S1", "format", "nom", 5, value="upper"), "missing_mechanism": "mcar"}],
        r"operation\.missing_mechanism requires kind: set_missing",
    )


@contract("11")
def test_lot11_when_condition_operators() -> None:
    """Contract 5.4 & SRS §11: Comparison operators (>=, <=, >, <, !=) in when conditions."""
    from tabalyst.generate_anomalies import _match_condition

    # Equality
    assert _match_condition("ontario", "ontario")
    assert not _match_condition("quebec", "ontario")

    # Numeric comparisons
    assert _match_condition("1500.00", ">=1500")
    assert _match_condition("2000.50", ">=1500")
    assert not _match_condition("1499.99", ">=1500")

    assert _match_condition("500.0", "<=500")
    assert not _match_condition("500.01", "<=500")

    assert _match_condition("100", ">50")
    assert not _match_condition("50", ">50")

    assert _match_condition("25", "<50")
    assert not _match_condition("50", "<50")

    assert _match_condition("100", "!=50")
    assert not _match_condition("50", "!=50")

    # ISO Date comparisons
    assert _match_condition("2024-05-15", ">=2024-01-01")
    assert not _match_condition("2023-12-31", ">=2024-01-01")
    assert _match_condition("2022-01-01", "<2024-01-01")


@contract("11")
def test_lot11_profile_missing_mechanisms_execution(tmp_path: Path) -> None:
    """Contract 5.4 & SRS §11: Profile missing_mechanisms executes exactly requested counts."""
    out = tmp_path / "missing_run"
    plan = build_generate_plan(
        PACKAGE,
        anomaly_profile="missing_mechanisms",
        rows=10000,
        seed=42,
        output_dir=out,
    )
    result = generate_datasets(plan)
    assert len(result.artifacts) > 0

    metrics = json.loads((out / "insurance-combined.missing_mechanisms.metrics.json").read_text(encoding="utf-8"))
    scenarios = metrics["scenarios"]

    # 7 scenarios with exact applied cases
    assert len(scenarios) == 7
    assert scenarios["MM_MCAR_PREM"]["applied_cases"] == 200
    assert scenarios["MM_MAR_BRANCH"]["applied_cases"] == 150
    assert scenarios["MM_MAR_AGENCY"]["applied_cases"] == 100
    assert scenarios["MM_MAR_PERIOD"]["applied_cases"] == 100
    assert scenarios["MM_MNAR_PREM"]["applied_cases"] == 100
    assert scenarios["MM_MNAR_CLAIM"]["applied_cases"] == 50
    assert scenarios["MM_OPT_LANG"]["applied_cases"] == 100

    # Total events recount
    assert metrics["counts"]["events"] == 800
    assert metrics["counts"]["changed_cells"] == 800


@contract("11")
def test_lot11_truth_group_id_and_canonical_values(tmp_path: Path) -> None:
    """Contract 5.2, 5.4 & SRS §11: truth.csv records missing group_id and original canonical_value."""
    out = tmp_path / "truth_run"
    plan = build_generate_plan(
        PACKAGE,
        anomaly_profile="missing_mechanisms",
        rows=10000,
        seed=42,
        output_dir=out,
    )
    generate_datasets(plan)

    truth_file = out / "insurance-combined.missing_mechanisms.truth.csv"
    dirty_file = out / "insurance-combined.missing_mechanisms.csv"
    assert truth_file.is_file() and dirty_file.is_file()

    with truth_file.open("r", encoding="utf-8", newline="") as f:
        truth_rows = list(csv.DictReader(f))

    # All injected lines have missing: group_id
    injected_missing = [r for r in truth_rows if r["kind"] == "injected" and r["group_id"].startswith("missing:")]
    assert len(injected_missing) == 800

    # Verify group_id formatting
    group_ids = {r["group_id"] for r in injected_missing}
    assert group_ids == {
        "missing:mcar:unreported",
        "missing:mar:client_refusal",
        "missing:mar:system_omission",
        "missing:mar:unreported",
        "missing:mnar:client_refusal",
        "missing:mnar:unknown",
        "missing:mar:not_applicable",
    }

    # Verify each missing cell in dirty file is actually empty, and truth.csv retains canonical_value
    with dirty_file.open("r", encoding="utf-8", newline="") as f:
        dirty_rows = list(csv.DictReader(f))

    for line in injected_missing[:50]:  # check sample
        row_idx = int(line["row_number"]) - 2  # header is row 1
        col = line["column"]
        assert dirty_rows[row_idx][col] == ""
        # canonical_value retains the clean value before it was blanked
        assert line["canonical_value"] != ""


@contract("11")
def test_lot11_metrics_missing_data_structure(tmp_path: Path) -> None:
    """Contract 5.4 & SRS §11: metrics.json carries missing_data and scenario mechanism metadata."""
    out = tmp_path / "metrics_run"
    plan = build_generate_plan(
        PACKAGE,
        anomaly_profile="missing_mechanisms",
        rows=10000,
        seed=42,
        output_dir=out,
    )
    generate_datasets(plan)

    metrics = json.loads((out / "insurance-combined.missing_mechanisms.metrics.json").read_text(encoding="utf-8"))
    assert "missing_data" in metrics
    md = metrics["missing_data"]

    # Mechanisms summary
    assert set(md["mechanisms"].keys()) == {"mcar", "mar", "mnar"}
    assert md["mechanisms"]["mcar"]["events"] == 200
    assert md["mechanisms"]["mcar"]["columns"] == ["prime_annuelle"]
    assert md["mechanisms"]["mcar"]["scenarios"] == ["MM_MCAR_PREM"]

    assert md["mechanisms"]["mar"]["events"] == 450  # 150 + 100 + 100 + 100
    assert md["mechanisms"]["mar"]["columns"] == ["code_postal", "courriel", "langue_preferee", "telephone"]
    assert md["mechanisms"]["mar"]["scenarios"] == ["MM_MAR_AGENCY", "MM_MAR_BRANCH", "MM_MAR_PERIOD", "MM_OPT_LANG"]

    assert md["mechanisms"]["mnar"]["events"] == 150  # 100 + 50
    assert md["mechanisms"]["mnar"]["columns"] == ["montant_reclamation", "prime_annuelle"]
    assert md["mechanisms"]["mnar"]["scenarios"] == ["MM_MNAR_CLAIM", "MM_MNAR_PREM"]

    # Reasons summary
    assert md["reasons"] == {
        "client_refusal": 250,  # 150 + 100
        "not_applicable": 100,
        "system_omission": 100,
        "unknown": 50,
        "unreported": 300,  # 200 + 100
    }

    # by_column breakdown
    assert "prime_annuelle" in md["by_column"]
    assert md["by_column"]["prime_annuelle"] == {"mcar": 200, "mnar": 100}
    assert md["by_column"]["courriel"] == {"mar": 150}

    # Each scenario in metrics carries missing_mechanism and missing_reason
    scenarios = metrics["scenarios"]
    assert scenarios["MM_MCAR_PREM"]["missing_mechanism"] == "mcar"
    assert scenarios["MM_MCAR_PREM"]["missing_reason"] == "unreported"
    assert scenarios["MM_MNAR_PREM"]["missing_mechanism"] == "mnar"
    assert scenarios["MM_MNAR_PREM"]["missing_reason"] == "client_refusal"


@contract("11")
def test_lot11_spatial_and_temporal_concentrations(tmp_path: Path) -> None:
    """Contract 5.4 & SRS §11: Verified spatial, agency, temporal and value concentrations."""
    out = tmp_path / "concentrations_run"
    plan = build_generate_plan(
        PACKAGE,
        anomaly_profile="missing_mechanisms",
        rows=10000,
        seed=42,
        output_dir=out,
    )
    generate_datasets(plan)

    clean_file = out / "insurance-combined.csv"
    truth_file = out / "insurance-combined.missing_mechanisms.truth.csv"

    with clean_file.open("r", encoding="utf-8", newline="") as f:
        clean_rows = list(csv.DictReader(f))
    with truth_file.open("r", encoding="utf-8", newline="") as f:
        truth_rows = list(csv.DictReader(f))

    injected = [r for r in truth_rows if r["kind"] == "injected"]

    # 1. Branch concentration: MM_MAR_BRANCH rows must all be Ontario
    ontario_rows = [clean_rows[int(r["row_number"]) - 2] for r in injected if r["scenario_id"] == "MM_MAR_BRANCH"]
    assert len(ontario_rows) == 150
    assert all(r["filiale"] == "ontario" for r in ontario_rows)

    # 2. Agency concentration: MM_MAR_AGENCY rows must all be AG-QC-001
    agency_rows = [clean_rows[int(r["row_number"]) - 2] for r in injected if r["scenario_id"] == "MM_MAR_AGENCY"]
    assert len(agency_rows) == 100
    assert all(r["agence_code"] == "AG-QC-001" for r in agency_rows)

    # 3. Temporal concentration: MM_MAR_PERIOD rows must all have date_creation >= 2024-01-01
    period_rows = [clean_rows[int(r["row_number"]) - 2] for r in injected if r["scenario_id"] == "MM_MAR_PERIOD"]
    assert len(period_rows) == 100
    assert all(r["date_creation"] >= "2024-01-01" for r in period_rows)

    # 4. MNAR value condition: MM_MNAR_PREM rows must all have original clean prime_annuelle >= 1500
    mnar_prem_rows = [clean_rows[int(r["row_number"]) - 2] for r in injected if r["scenario_id"] == "MM_MNAR_PREM"]
    assert len(mnar_prem_rows) == 100
    assert all(float(r["prime_annuelle"]) >= 1500.0 for r in mnar_prem_rows)

    # 5. MNAR claim condition: MM_MNAR_CLAIM rows must all have original clean montant_reclamation >= 5000
    mnar_claim_rows = [clean_rows[int(r["row_number"]) - 2] for r in injected if r["scenario_id"] == "MM_MNAR_CLAIM"]
    assert len(mnar_claim_rows) == 50
    assert all(float(r["montant_reclamation"]) >= 5000.0 for r in mnar_claim_rows)

    # 6. MCAR diffuse: MM_MCAR_PREM touches all three branches
    mcar_rows = [clean_rows[int(r["row_number"]) - 2] for r in injected if r["scenario_id"] == "MM_MCAR_PREM"]
    assert len(mcar_rows) == 200
    mcar_branches = {r["filiale"] for r in mcar_rows}
    assert mcar_branches == {"ontario", "principal", "quebec"}


@contract("12")
def test_lot12_rule_temporal_validity_evaluation() -> None:
    """Contract 5.3 & SRS §13: RuleEvaluator respects rule validity windows and named periods."""
    from tabalyst.generate_rules import (
        Conventions,
        Rule,
        RuleContext,
        RuleEvaluator,
        RulePeriod,
    )

    conventions = Conventions(
        branch_column="filiale",
        date_format={"principal": "%Y-%m-%d"},
        periods={
            "legacy_tariff": RulePeriod(
                start="2020-01-01",
                end="2023-12-31",
                description="Legacy tariff grid",
            ),
            "modern_tariff": RulePeriod(
                start="2024-01-01",
                end=None,
                description="Modern tariff grid",
            ),
        },
    )
    context = RuleContext(conventions=conventions, as_of_date="2026-09-16")

    # Rule with explicit valid_from
    r_modern = Rule(
        id="T01",
        family="business",
        title="Modern rule requiring high franchise",
        columns=["date_creation", "franchise"],
        category="business_rule_violation",
        severity="major",
        detection="syntactic",
        valid_from="2024-01-01",
        temporal_column="date_creation",
        assert_={"op": "gte", "left": "franchise", "right": {"value": "500.0"}, "as": "decimal"},
    )

    # Rule with named period (legacy_tariff ending 2023-12-31)
    r_legacy = Rule(
        id="T02",
        family="business",
        title="Legacy rule requiring low franchise",
        columns=["date_creation", "franchise"],
        category="business_rule_violation",
        severity="major",
        detection="syntactic",
        period="legacy_tariff",
        temporal_column="date_creation",
        assert_={"op": "lte", "left": "franchise", "right": {"value": "300.0"}, "as": "decimal"},
    )

    evaluator = RuleEvaluator([r_modern, r_legacy], context)

    # Row 1: 2023-06-15, franchise 400.0
    # Inside legacy_tariff (fails T02: 400 > 300), before modern_tariff (T01 skipped)
    row_2023 = {"filiale": "principal", "date_creation": "2023-06-15", "franchise": "400.0"}
    violations_2023 = evaluator.check(1, row_2023)
    assert len(violations_2023) == 1
    assert violations_2023[0].rule_id == "T02"

    # Row 2: 2024-06-15, franchise 400.0
    # Inside modern_tariff (fails T01: 400 < 500), after legacy_tariff (T02 skipped)
    row_2024 = {"filiale": "principal", "date_creation": "2024-06-15", "franchise": "400.0"}
    violations_2024 = evaluator.check(2, row_2024)
    assert len(violations_2024) == 1
    assert violations_2024[0].rule_id == "T01"

    # Row 3: 2024-06-15, franchise 600.0
    # Inside modern_tariff (passes T01: 600 >= 500), legacy skipped -> 0 violations
    row_2024_ok = {"filiale": "principal", "date_creation": "2024-06-15", "franchise": "600.0"}
    assert evaluator.check(3, row_2024_ok) == []


@contract("12")
def test_lot12_tranche_c_columns_in_complete_profile(tmp_path: Path) -> None:
    """Contract 5.3 & SRS §13: complete profile appends Tranche C columns in deterministic contract order."""
    out = tmp_path / "complete_run"
    plan = build_generate_plan(
        PACKAGE,
        output_profile="complete",
        rows=100,
        seed=42,
        output_dir=out,
    )
    generate_datasets(plan)

    combined_file = out / "insurance-combined.csv"
    assert combined_file.is_file()
    with combined_file.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        rows = list(reader)

    # Contract total: 51 columns (48 + 3 Tranche C)
    assert len(fields) == 51
    assert fields[-3:] == ["date_observation", "version_source", "source_system"]

    # Each branch file has 50 columns (47 + 3 Tranche C, no 'filiale')
    for branch in ("principal", "quebec", "ontario"):
        bf = out / f"insurance-{branch}.csv"
        assert bf.is_file()
        with bf.open("r", encoding="utf-8", newline="") as f:
            bfields = (csv.DictReader(f).fieldnames or [])
        assert len(bfields) == 50
        assert bfields[-3:] == ["date_observation", "version_source", "source_system"]
        assert "filiale" not in bfields

    # Values validation
    for r in rows:
        assert r["version_source"] in {"v1.0", "v2.0", "v2.1"}
        assert any(r["source_system"].startswith(pfx) for pfx in ("SYS_PRI", "SYS_QC", "SYS_ON_"))
        assert len(r["date_observation"]) >= 8


@contract("12")
def test_lot12_schema_drift_execution_and_metrics(tmp_path: Path) -> None:
    """Contract 5.3 & SRS §13: schema_drift profile execution, metrics.json and temporal_drift."""
    out = tmp_path / "schema_drift_run"
    plan = build_generate_plan(
        PACKAGE,
        anomaly_profile="schema_drift",
        rows=10000,
        seed=42,
        output_dir=out,
    )
    generate_datasets(plan)

    # 1. Output profile defaults to complete (51 columns on combined)
    combined_file = out / "insurance-combined.csv"
    with combined_file.open("r", encoding="utf-8", newline="") as f:
        header = f.readline().strip().split(",")
    assert len(header) == 51

    # 2. All 11 atomic artifacts present
    expected_files = [
        "insurance-combined.csv",
        "insurance-combined.schema_drift.csv",
        "insurance-combined.schema_drift.changes.csv",
        "insurance-combined.schema_drift.summary.json",
        "insurance-combined.schema_drift.truth.csv",
        "insurance-combined.schema_drift.rules.json",
        "insurance-combined.schema_drift.metrics.json",
        "insurance-combined.schema_drift.manifest.json",
        "insurance-principal.csv",
        "insurance-quebec.csv",
        "insurance-ontario.csv",
    ]
    for fn in expected_files:
        assert (out / fn).is_file(), f"Missing artifact: {fn}"

    # 3. Metrics.json structure
    metrics = json.loads((out / "insurance-combined.schema_drift.metrics.json").read_text(encoding="utf-8"))
    assert "temporal_drift" in metrics
    td = metrics["temporal_drift"]

    # Active periods
    assert "active_periods" in td
    assert set(td["active_periods"]) == {"legacy_tariff", "migration_ontario", "schema_v2", "modern_tariff"}

    # Drift scenarios list
    assert set(td["drift_scenarios"]) == {
        "SD_SYS_MIG",
        "SD_VER_MIG",
        "SD_DEDUCT_REG",
        "SD_OBS_ANACH",
        "SD_VER_PREMAT",
        "SD_FMT_MIG",
        "SD_CHAN_DRIFT",
        "SD_LEGACY_VAL",
    }

    # Scenario counts in metrics (800 events total)
    scenarios = metrics["scenarios"]
    assert scenarios["SD_SYS_MIG"]["applied_cases"] == 100
    assert scenarios["SD_VER_MIG"]["applied_cases"] == 100
    assert scenarios["SD_DEDUCT_REG"]["applied_cases"] == 100
    assert scenarios["SD_OBS_ANACH"]["applied_cases"] == 50
    assert scenarios["SD_VER_PREMAT"]["applied_cases"] == 50
    assert scenarios["SD_FMT_MIG"]["applied_cases"] == 100
    assert scenarios["SD_CHAN_DRIFT"]["applied_cases"] == 200
    assert scenarios["SD_LEGACY_VAL"]["applied_cases"] == 100

    # Temporal rules with exact violation counts (400 violations total)
    assert td["temporal_rules"] == {
        "M26": 100,
        "M27": 100,
        "M28": 50,
        "M29": 50,
        "M30": 100,
    }


@contract("12")
def test_lot12_schema_drift_valid_atypical_cases(tmp_path: Path) -> None:
    """Contract 5.3 & SRS §13: SD_CHAN_DRIFT and SD_LEGACY_VAL are valid_atypical with 0 rule violations."""
    out = tmp_path / "valid_atypical_run"
    plan = build_generate_plan(
        PACKAGE,
        anomaly_profile="schema_drift",
        rows=10000,
        seed=42,
        output_dir=out,
    )
    generate_datasets(plan)

    truth_file = out / "insurance-combined.schema_drift.truth.csv"
    with truth_file.open("r", encoding="utf-8", newline="") as f:
        truth_rows = list(csv.DictReader(f))

    # Channel drift: 200 valid_atypical events, expected_detection none, no rule_violation
    chan_rows = [r for r in truth_rows if r["scenario_id"] == "SD_CHAN_DRIFT" and r["kind"] == "valid_atypical"]
    assert len(chan_rows) == 200
    assert all(r["category"] == "valid_atypical" for r in chan_rows)
    assert all(r["expected_detection"] == "none" for r in chan_rows)
    assert not any(r["kind"] == "rule_violation" for r in truth_rows if r["scenario_id"] == "SD_CHAN_DRIFT")

    # Legacy valid data drift: 100 valid_atypical events, expected_detection none, no rule_violation
    legacy_rows = [r for r in truth_rows if r["scenario_id"] == "SD_LEGACY_VAL" and r["kind"] == "valid_atypical"]
    assert len(legacy_rows) == 100
    assert all(r["category"] == "valid_atypical" for r in legacy_rows)
    assert all(r["expected_detection"] == "none" for r in legacy_rows)
    assert not any(r["kind"] == "rule_violation" for r in truth_rows if r["scenario_id"] == "SD_LEGACY_VAL")


@contract("12")
def test_lot12_rules_json_contains_periods_and_temporal_attributes(tmp_path: Path) -> None:
    """Contract 5.3 & SRS §13: rules.json serializes conventions.periods and rule temporal fields."""
    out = tmp_path / "rules_run"
    plan = build_generate_plan(
        PACKAGE,
        anomaly_profile="schema_drift",
        rows=10000,
        seed=42,
        output_dir=out,
    )
    generate_datasets(plan)

    rules_doc = json.loads((out / "insurance-combined.schema_drift.rules.json").read_text(encoding="utf-8"))
    assert "conventions" in rules_doc
    conventions = rules_doc["conventions"]
    assert "periods" in conventions
    periods = conventions["periods"]

    assert "legacy_tariff" in periods
    assert periods["legacy_tariff"]["end"] == "2023-12-31"
    assert "migration_ontario" in periods
    assert periods["migration_ontario"]["start"] == "2023-06-01"
    assert "schema_v2" in periods
    assert periods["schema_v2"]["start"] == "2024-01-01"
    assert "modern_tariff" in periods
    assert periods["modern_tariff"]["start"] == "2025-01-01"

    rules_by_id = {r["id"]: r for r in rules_doc["rules"]}

    # M26 has valid_from
    assert rules_by_id["M26"]["valid_from"] == "2024-01-01"
    assert rules_by_id["M26"]["temporal_column"] == "date_creation"

    # M27 has period
    assert rules_by_id["M27"]["period"] == "migration_ontario"
    assert rules_by_id["M27"]["temporal_column"] == "date_creation"

    # M28 has temporal comparison between date_creation and date_observation
    assert rules_by_id["M28"]["temporal_column"] == "date_creation"

    # M29 has valid_until
    assert rules_by_id["M29"]["valid_until"] == "2023-12-31"
    assert rules_by_id["M29"]["temporal_column"] == "date_creation"

    # M30 has period
    assert rules_by_id["M30"]["period"] == "modern_tariff"
    assert rules_by_id["M30"]["temporal_column"] == "date_debut"


# --- LOT 13: Synthetic fraud, hard cases, noise and delayed labels (ML01 to ML08, ML20) ---


@contract("13")
def test_lot13_ml_labels_artifact_and_manifest(tmp_path: Path) -> None:
    """SRS §8, §15 & Lot 13: ml_labels.csv artifact generation and manifest inclusion."""
    out = tmp_path / "ml_run"
    plan = build_generate_plan(
        PACKAGE,
        anomaly_profile="ml_fraud_imbalanced",
        rows=10000,
        seed=42,
        output_dir=out,
    )
    generate_datasets(plan)

    # 1. Output profile defaults to extended (44 columns on combined)
    combined_file = out / "insurance-combined.csv"
    with combined_file.open("r", encoding="utf-8", newline="") as f:
        header = f.readline().strip().split(",")
    assert len(header) == 44

    # 2. Separate ml_labels.csv exists
    labels_file = out / "insurance-combined.ml_fraud_imbalanced.ml_labels.csv"
    assert labels_file.is_file(), "Missing ml_labels.csv"

    # 3. CSV columns check (exact 7 columns)
    with labels_file.open("r", encoding="utf-8", newline="") as f:
        reader = list(csv.DictReader(f))
    assert len(reader) == 10000
    assert list(reader[0].keys()) == [
        "row_number",
        "id_contrat",
        "is_fraud",
        "observed_label",
        "confirmation_date",
        "fraud_type",
        "latent_probability",
    ]

    # 4. Manifest includes ml_labels with role "ml_labels"
    manifest_file = out / "insurance-combined.ml_fraud_imbalanced.manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    files_by_role = {entry["role"]: entry for entry in manifest["files"]}
    assert "ml_labels" in files_by_role
    ml_entry = files_by_role["ml_labels"]
    assert ml_entry["name"] == "insurance-combined.ml_fraud_imbalanced.ml_labels.csv"
    assert len(ml_entry["sha256"]) == 64
    assert ml_entry["bytes"] > 0


@contract("13")
def test_lot13_fraud_rates_and_imbalance(tmp_path: Path) -> None:
    """SRS §8 ML01, ML02, ML03: 1%, 0.1%, and 0.01% fraud rates and class imbalance."""
    out = tmp_path / "rates_run"
    plan = build_generate_plan(
        PACKAGE,
        anomaly_profile="ml_fraud_imbalanced",
        rows=10000,
        seed=42,
        output_dir=out,
    )
    generate_datasets(plan)

    metrics_file = out / "insurance-combined.ml_fraud_imbalanced.metrics.json"
    metrics = json.loads(metrics_file.read_text(encoding="utf-8"))
    assert "ml_fraud" in metrics
    ml_m = metrics["ml_fraud"]

    # Overall fraud rate ~1% (ML01: 104 total true frauds out of 10000 rows)
    assert 0.009 <= ml_m["rates"]["true_fraud_rate"] <= 0.012
    assert 90 <= ml_m["true_frauds"] <= 120

    # Rare fraud scenario at 0.1% (ML02: 10 cases / 10000)
    scenarios = metrics["scenarios"]
    assert "ML02_RARE_01PCT" in scenarios
    assert scenarios["ML02_RARE_01PCT"]["applied_cases"] == 10
    assert scenarios["ML02_RARE_01PCT"]["category"] == "contextual_invalid"

    # Extremely rare fraud scenario at 0.01% (ML03: 1 case / 10000)
    assert "ML03_EXTREME" in scenarios
    assert scenarios["ML03_EXTREME"]["applied_cases"] == 1
    assert scenarios["ML03_EXTREME"]["rarity_level"] == "single"


@contract("13")
def test_lot13_fraud_typologies_coverage(tmp_path: Path) -> None:
    """SRS §8 ML04: Multi-class fraud typologies (phantom, inflated, collusion, organized)."""
    out = tmp_path / "typologies_run"
    plan = build_generate_plan(
        PACKAGE,
        anomaly_profile="ml_fraud_imbalanced",
        rows=10000,
        seed=42,
        output_dir=out,
    )
    generate_datasets(plan)

    metrics = json.loads((out / "insurance-combined.ml_fraud_imbalanced.metrics.json").read_text(encoding="utf-8"))
    ml_m = metrics["ml_fraud"]
    fraud_types = ml_m["fraud_types"]

    # All 4 typologies present with positive counts
    assert "phantom_claim" in fraud_types and fraud_types["phantom_claim"] >= 20
    assert "inflated_claim" in fraud_types and fraud_types["inflated_claim"] >= 20
    assert "collusion" in fraud_types and fraud_types["collusion"] >= 10
    assert "organized_fraud" in fraud_types and fraud_types["organized_fraud"] >= 10

    # Check distinct values in ml_labels.csv
    labels_file = out / "insurance-combined.ml_fraud_imbalanced.ml_labels.csv"
    with labels_file.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    csv_types = {r["fraud_type"] for r in rows if r["is_fraud"] == "1"}
    assert csv_types == {"phantom_claim", "inflated_claim", "collusion", "organized_fraud"}


@contract("13")
def test_lot13_hard_cases_and_continuous_overlap(tmp_path: Path) -> None:
    """SRS §8 ML05: Hard cases near boundary and continuous latent probability overlap."""
    out = tmp_path / "hard_run"
    plan = build_generate_plan(
        PACKAGE,
        anomaly_profile="ml_fraud_imbalanced",
        rows=10000,
        seed=42,
        output_dir=out,
    )
    generate_datasets(plan)

    labels_file = out / "insurance-combined.ml_fraud_imbalanced.ml_labels.csv"
    with labels_file.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    frauds = [r for r in rows if r["is_fraud"] == "1"]
    cleans = [r for r in rows if r["is_fraud"] == "0"]

    fraud_probs = [float(r["latent_probability"]) for r in frauds]
    clean_probs = [float(r["latent_probability"]) for r in cleans]

    # Probabilities strictly in [0.0, 1.0]
    assert all(0.0 <= p <= 1.0 for p in fraud_probs)
    assert all(0.0 <= p <= 1.0 for p in clean_probs)

    # Significant statistical overlap zone between [0.45, 0.65]
    overlap_frauds = [p for p in fraud_probs if 0.45 <= p <= 0.65]
    overlap_cleans = [p for p in clean_probs if 0.45 <= p <= 0.65]
    assert len(overlap_frauds) >= 5, "Hard fraud cases should fall into the boundary overlap zone"
    assert len(overlap_cleans) >= 20, "Plausible false positives / atypicals should overlap with fraud"

    # Distribution separation: mean fraud prob is significantly higher than clean mean
    assert sum(fraud_probs) / len(fraud_probs) > 0.65
    assert sum(clean_probs) / len(clean_probs) < 0.20


@contract("13")
def test_lot13_plausible_false_positives_and_atypical(tmp_path: Path) -> None:
    """SRS §8 ML06, ML20: Plausible false positives and valid atypical cases."""
    out = tmp_path / "fp_run"
    plan = build_generate_plan(
        PACKAGE,
        anomaly_profile="ml_fraud_imbalanced",
        rows=10000,
        seed=42,
        output_dir=out,
    )
    generate_datasets(plan)

    truth_file = out / "insurance-combined.ml_fraud_imbalanced.truth.csv"
    with truth_file.open("r", encoding="utf-8", newline="") as f:
        trows = list(csv.DictReader(f))

    # ML06 and ML20 are valid_atypical with severity info and expected_detection none
    fp_events = [t for t in trows if t["scenario_id"] == "ML06_FALSE_POS" and t["kind"] == "valid_atypical"]
    assert len(fp_events) == 40
    assert all(t["category"] == "valid_atypical" for t in fp_events)
    assert all(t["expected_detection"] == "none" for t in fp_events)

    atyp_events = [t for t in trows if t["scenario_id"] == "ML20_ATYPICAL" and t["kind"] == "valid_atypical"]
    assert len(atyp_events) == 50
    assert all(t["category"] == "valid_atypical" for t in atyp_events)
    assert all(t["expected_detection"] == "none" for t in atyp_events)

    # In ml_labels.csv, these cases are strictly non-fraud (is_fraud == "0")
    labels_file = out / "insurance-combined.ml_fraud_imbalanced.ml_labels.csv"
    with labels_file.open("r", encoding="utf-8", newline="") as f:
        lrows = {int(r["row_number"]): r for r in csv.DictReader(f)}

    for t in fp_events:
        row_num = int(t["row_number"])
        label_entry = lrows[row_num]
        assert label_entry["is_fraud"] == "0", "Plausible false positive must have is_fraud == 0"
        assert label_entry["fraud_type"] == ""


@contract("13")
def test_lot13_noisy_and_delayed_labels(tmp_path: Path) -> None:
    """SRS §8 ML07, ML08: Label noise (inverted labels) and delayed unresolved investigations."""
    out = tmp_path / "noise_run"
    plan = build_generate_plan(
        PACKAGE,
        anomaly_profile="ml_fraud_imbalanced",
        rows=10000,
        seed=42,
        output_dir=out,
    )
    generate_datasets(plan)

    labels_file = out / "insurance-combined.ml_fraud_imbalanced.ml_labels.csv"
    with labels_file.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    metrics = json.loads((out / "insurance-combined.ml_fraud_imbalanced.metrics.json").read_text(encoding="utf-8"))
    ml_m = metrics["ml_fraud"]

    # ML08: Delayed labels have is_fraud == "1", observed_label == "", confirmation_date == ""
    delayed = [r for r in rows if r["is_fraud"] == "1" and r["observed_label"] == ""]
    assert len(delayed) == 15
    assert all(r["confirmation_date"] == "" for r in delayed)
    assert ml_m["delayed_labels"] == 15

    # ML07: Label noise has observed_label != is_fraud
    noisy = [r for r in rows if r["observed_label"] != "" and r["observed_label"] != r["is_fraud"]]
    assert len(noisy) == 10
    assert ml_m["noisy_labels"] == 10
    # Both false negatives and false positives exist in label noise
    assert any(r["is_fraud"] == "1" and r["observed_label"] == "0" for r in noisy)
    assert any(r["is_fraud"] == "0" and r["observed_label"] == "1" for r in noisy)


@contract("13")
def test_lot13_no_trivial_artifacts(tmp_path: Path) -> None:
    """SRS §8: No trivial artifacts (premiums != 0, amounts != 999999, 0 rule violations)."""
    out = tmp_path / "artifacts_run"
    plan = build_generate_plan(
        PACKAGE,
        anomaly_profile="ml_fraud_imbalanced",
        rows=10000,
        seed=42,
        output_dir=out,
    )
    generate_datasets(plan)

    labels_file = out / "insurance-combined.ml_fraud_imbalanced.ml_labels.csv"
    data_file = out / "insurance-combined.ml_fraud_imbalanced.csv"
    truth_file = out / "insurance-combined.ml_fraud_imbalanced.truth.csv"

    with labels_file.open("r", encoding="utf-8", newline="") as f:
        lrows = list(csv.DictReader(f))
    with data_file.open("r", encoding="utf-8", newline="") as f:
        drows = list(csv.DictReader(f))
    with truth_file.open("r", encoding="utf-8", newline="") as f:
        trows = list(csv.DictReader(f))

    # Match fraud rows with data rows
    frauds = [d for l, d in zip(lrows, drows, strict=True) if l["is_fraud"] == "1"]
    assert len(frauds) >= 90

    # 1. No premium equal to 0
    assert not any(float(f["prime_annuelle"]) == 0.0 for f in frauds)

    # 2. No arbitrary magic amount
    for f in frauds:
        assert "999999" not in f.get("prime_annuelle", "")
        assert "999999" not in f.get("montant_reclamation", "")

    # 3. Exactly 0 rule violations in the whole run
    violations = [t for t in trows if t["kind"] == "rule_violation"]
    assert len(violations) == 0, f"Unexpected rule violations: {violations}"


@contract("13")
def test_lot13_ml_labels_schema_validation() -> None:
    """SRS §15 & Lot 13: tabalyst.generate.ml_labels.schema.json validates against Draft202012."""
    import jsonschema

    from tabalyst.generate_ml import MLFraudMetrics, ml_labels_document

    schema_file = ROOT / "src/tabalyst/schemas/tabalyst.generate.ml_labels.schema.json"
    assert schema_file.is_file(), "Schema file missing"
    schema = json.loads(schema_file.read_text(encoding="utf-8"))

    # Draft202012 schema check
    jsonschema.Draft202012Validator.check_schema(schema)

    # Instance validation
    doc = ml_labels_document("insurance-combined", "ml_fraud_imbalanced", 10000, MLFraudMetrics())
    jsonschema.validate(doc.model_dump(mode="json"), schema, cls=jsonschema.Draft202012Validator)


@contract("14")
def test_lot14_ml_targets_and_features(tmp_path: Path) -> None:
    """SRS §8 ML09-ML12: Extended ML prediction targets in ml_labels.csv."""
    out = tmp_path / "targets_run"
    plan = build_generate_plan(
        PACKAGE,
        anomaly_profile="ml_leakage_test",
        rows=10000,
        seed=42,
        output_dir=out,
    )
    generate_datasets(plan)

    labels_file = out / "insurance-combined.ml_leakage_test.ml_labels.csv"
    assert labels_file.is_file(), "ml_labels.csv must be produced for ml_leakage_test"
    with labels_file.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 10000
    expected_cols = [
        "row_number",
        "id_contrat",
        "is_fraud",
        "observed_label",
        "confirmation_date",
        "fraud_type",
        "latent_probability",
        "future_claim",
        "cout_sinistre",
        "renouvellement",
        "date_renouvellement",
        "risque_categorie",
        "historique_sinistres",
        "anciennete_client",
        "score_risque_interne",
    ]
    assert list(rows[0].keys()) == expected_cols

    # ML09: future_claim in {0, 1} with realistic positive frequency
    future_claims = [int(r["future_claim"]) for r in rows]
    assert all(fc in (0, 1) for fc in future_claims)
    fc_pos = sum(future_claims)
    assert 500 <= fc_pos <= 2500, f"Expected ~10% future claims, got {fc_pos}"

    # ML10: cout_sinistre >= 0.00, and 0.00 when future_claim == 0
    for r in rows:
        cost = float(r["cout_sinistre"])
        fc = int(r["future_claim"])
        if fc == 0:
            assert cost == 0.0, "Zero claim cost when future_claim == 0"
        else:
            assert cost > 0.0, "Positive claim cost when future_claim == 1"

    # ML11: renouvellement in {0, 1} and date_renouvellement non-empty iff renewed
    renewals = [int(r["renouvellement"]) for r in rows]
    assert all(rn in (0, 1) for rn in renewals)
    assert sum(renewals) > 6000, "Realistic renewal rate > 60%"
    for r in rows:
        if int(r["renouvellement"]) == 1:
            assert re.match(r"^\d{4}-\d{2}-\d{2}$", r["date_renouvellement"])
        else:
            assert r["date_renouvellement"] == ""

    # ML12: risque_categorie covers all 4 risk classes
    cats = Counter(r["risque_categorie"] for r in rows)
    assert set(cats.keys()) == {"faible", "moyen", "eleve", "tres_eleve"}
    assert cats["faible"] > 2000
    assert cats["moyen"] > 2000
    assert cats["eleve"] > 500
    assert cats["tres_eleve"] > 50


@contract("14")
def test_lot14_calculated_antecedent_features(tmp_path: Path) -> None:
    """SRS §8: Upstream engineered features (historique_sinistres, anciennete_client)."""
    out = tmp_path / "antecedents_run"
    plan = build_generate_plan(
        PACKAGE,
        anomaly_profile="ml_leakage_test",
        rows=10000,
        seed=42,
        output_dir=out,
    )
    generate_datasets(plan)

    labels_file = out / "insurance-combined.ml_leakage_test.ml_labels.csv"
    splits_file = out / "insurance-combined.ml_leakage_test.splits.csv"
    with labels_file.open("r", encoding="utf-8", newline="") as f:
        lrows = list(csv.DictReader(f))
    with splits_file.open("r", encoding="utf-8", newline="") as f:
        srows = list(csv.DictReader(f))

    # All historique_sinistres are non-negative integers
    hist_vals = [int(r["historique_sinistres"]) for r in lrows]
    assert all(h >= 0 for h in hist_vals)
    assert any(h > 0 for h in hist_vals)

    # Anciennete_client is non-negative and bounded realistically (<= 25 years)
    tenure_vals = [int(r["anciennete_client"]) for r in lrows]
    assert all(0 <= t <= 25 for t in tenure_vals)
    assert any(t > 0 for t in tenure_vals)

    # Group by id_client: verify that all contracts of the same client share identical tenure
    client_tenures: dict[str, set[str]] = {}
    for lr, sr in zip(lrows, srows, strict=True):
        client_tenures.setdefault(sr["id_client"], set()).add(lr["anciennete_client"])
    assert all(len(tenures) == 1 for tenures in client_tenures.values()), "Tenure must be consistent per client"


@contract("14")
def test_lot14_leakage_and_shortcut_scenarios(tmp_path: Path) -> None:
    """SRS §8 ML13-ML19: Behavioral drift, unseen categories, shortcuts, and branch imbalances."""
    out = tmp_path / "leak_run"
    plan = build_generate_plan(
        PACKAGE,
        anomaly_profile="ml_leakage_test",
        rows=10000,
        seed=42,
        output_dir=out,
    )
    generate_datasets(plan)

    truth_file = out / "insurance-combined.ml_leakage_test.truth.csv"
    with truth_file.open("r", encoding="utf-8", newline="") as f:
        trows = list(csv.DictReader(f))

    scenarios_found = {r["scenario_id"] for r in trows if r["scenario_id"]}
    assert "ML13_DRIFT" in scenarios_found
    assert "ML14_UNSEEN" in scenarios_found
    assert "ML15_LEAK" in scenarios_found
    assert "ML16_POST_LEAK" in scenarios_found
    assert "ML17_SHORTCUT" in scenarios_found
    assert "ML18_IMBALANCE" in scenarios_found
    assert "ML19_MISSING" in scenarios_found

    # ML16: Post-claim leak modifies payment status on closed claims
    post_claim_events = [r for r in trows if r["scenario_id"] == "ML16_POST_LEAK" and r["kind"] == "injected"]
    assert len(post_claim_events) == 30
    assert all(r["column"] == "statut_paiement" for r in post_claim_events)

    # ML17: ID shortcut injection
    shortcut_events = [r for r in trows if r["scenario_id"] == "ML17_SHORTCUT" and r["kind"] == "injected"]
    assert len(shortcut_events) == 20

    # ML19: Missing values conditioned on segment/branch
    missing_events = [r for r in trows if r["scenario_id"] == "ML19_MISSING" and r["kind"] == "injected"]
    assert len(missing_events) == 30
    assert all(r["canonical_value"] != "" for r in missing_events)


@contract("14")
def test_lot14_splits_client_grouping_no_leakage(tmp_path: Path) -> None:
    """SRS §8 & Lot 14: Random client grouping in splits.csv guarantees zero client leakage."""
    out = tmp_path / "splits_run"
    plan = build_generate_plan(
        PACKAGE,
        anomaly_profile="ml_leakage_test",
        rows=10000,
        seed=42,
        output_dir=out,
    )
    generate_datasets(plan)

    splits_file = out / "insurance-combined.ml_leakage_test.splits.csv"
    assert splits_file.is_file(), "splits.csv must be published"
    with splits_file.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 10000
    assert list(rows[0].keys()) == [
        "row_number",
        "id_contrat",
        "id_client",
        "split_client",
        "split_temporal",
        "resampled_train_only",
    ]

    # Group by id_client across partitions
    train_clients: set[str] = set()
    val_clients: set[str] = set()
    test_clients: set[str] = set()

    client_splits: dict[str, set[str]] = {}
    for r in rows:
        cid = r["id_client"]
        sp = r["split_client"]
        assert sp in ("train", "validation", "test")
        client_splits.setdefault(cid, set()).add(sp)
        if sp == "train":
            train_clients.add(cid)
        elif sp == "validation":
            val_clients.add(cid)
        else:
            test_clients.add(cid)

    # STRICT ZERO LEAKAGE INVARIANT: Every single client belongs to exactly ONE partition
    assert all(len(parts) == 1 for parts in client_splits.values()), "Clients must not be split across partitions"
    assert train_clients.isdisjoint(val_clients), "Train and validation must share zero clients"
    assert train_clients.isdisjoint(test_clients), "Train and test must share zero clients"
    assert val_clients.isdisjoint(test_clients), "Validation and test must share zero clients"

    # Partition proportions approximately 70% / 15% / 15%
    c_counts = Counter(r["split_client"] for r in rows)
    assert 6500 <= c_counts["train"] <= 7500
    assert 1200 <= c_counts["validation"] <= 1800
    assert 1200 <= c_counts["test"] <= 1800

    # Also check metrics.json
    metrics = json.loads((out / "insurance-combined.ml_leakage_test.metrics.json").read_text(encoding="utf-8"))
    assert "splits" in metrics
    sp_m = metrics["splits"]
    assert sp_m["client_leakage_cases"] == 0
    assert sp_m["total_rows"] == 10000


@contract("14")
def test_lot14_splits_temporal_chronology(tmp_path: Path) -> None:
    """SRS §8 & Lot 14: Temporal split respects strict chronology without future data leakage."""
    out = tmp_path / "temp_splits_run"
    plan = build_generate_plan(
        PACKAGE,
        anomaly_profile="ml_leakage_test",
        rows=10000,
        seed=42,
        output_dir=out,
    )
    generate_datasets(plan)

    splits_file = out / "insurance-combined.ml_leakage_test.splits.csv"
    data_file = out / "insurance-combined.ml_leakage_test.csv"
    with splits_file.open("r", encoding="utf-8", newline="") as f:
        srows = list(csv.DictReader(f))
    with data_file.open("r", encoding="utf-8", newline="") as f:
        drows = list(csv.DictReader(f))

    from datetime import date, datetime

    def parse_d(text: str) -> date | None:
        for fmt in ("%Y-%m-%d", "%m-%d-%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(text[:10], fmt).date()
            except ValueError:
                continue
        return None

    train_dates: list[date] = []
    val_dates: list[date] = []
    test_dates: list[date] = []

    for sr, dr in zip(srows, drows, strict=True):
        dt = parse_d(dr["date_debut"])
        if dt is None:
            continue
        part = sr["split_temporal"]
        if part == "train":
            train_dates.append(dt)
        elif part == "validation":
            val_dates.append(dt)
        elif part == "test":
            test_dates.append(dt)

    # Invariants for temporal split:
    # All train rows strictly before 2024-01-01
    assert all(d < date(2024, 1, 1) for d in train_dates)
    # All validation rows in [2024-01-01, 2024-12-31]
    assert all(date(2024, 1, 1) <= d < date(2025, 1, 1) for d in val_dates)
    # All test rows strictly on or after 2025-01-01
    assert all(d >= date(2025, 1, 1) for d in test_dates)

    # Chronological separation: max(train) < min(val) and max(val) < min(test)
    assert max(train_dates) < min(val_dates)
    assert max(val_dates) < min(test_dates)


@contract("14")
def test_lot14_splits_resampling_train_isolation(tmp_path: Path) -> None:
    """SRS §8 & Lot 14: Resampling is strictly isolated to training partition."""
    out = tmp_path / "resample_run"
    plan = build_generate_plan(
        PACKAGE,
        anomaly_profile="ml_leakage_test",
        rows=10000,
        seed=42,
        output_dir=out,
    )
    generate_datasets(plan)

    splits_file = out / "insurance-combined.ml_leakage_test.splits.csv"
    with splits_file.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    # All resampled_train_only flags must be in {0, 1}
    assert all(r["resampled_train_only"] in ("0", "1") for r in rows)

    # STRICT INVARIANT: If partition is NOT train, resampled_train_only must be 0!
    val_test_rows = [r for r in rows if r["split_client"] in ("validation", "test")]
    assert all(r["resampled_train_only"] == "0" for r in val_test_rows), (
        "Validation and test partitions must never be resampled"
    )

    # In train partition, resampled positive instances exist
    train_rows = [r for r in rows if r["split_client"] == "train"]
    resampled_train = [r for r in train_rows if r["resampled_train_only"] == "1"]
    assert len(resampled_train) > 0, "Train partition should flag resampled positive cases"


@contract("14")
def test_lot14_splits_schema_validation() -> None:
    """SRS §15 & Lot 14: tabalyst.generate.splits.schema.json validates against Draft202012."""
    import jsonschema

    from tabalyst.generate_ml import SplitMetrics, splits_document

    schema_file = ROOT / "src/tabalyst/schemas/tabalyst.generate.splits.schema.json"
    assert schema_file.is_file(), "Splits schema file missing"
    schema = json.loads(schema_file.read_text(encoding="utf-8"))

    # Draft202012 schema check
    jsonschema.Draft202012Validator.check_schema(schema)

    # Instance validation
    doc = splits_document("insurance-combined", "ml_leakage_test", 10000, SplitMetrics())
    jsonschema.validate(doc.model_dump(mode="json"), schema, cls=jsonschema.Draft202012Validator)


@contract("14")
def test_lot14_manifest_includes_splits(tmp_path: Path) -> None:
    """SRS §15 & Lot 14: manifest.json includes splits.csv with role 'splits' and sha256."""
    out = tmp_path / "manifest_run"
    plan = build_generate_plan(
        PACKAGE,
        anomaly_profile="ml_leakage_test",
        rows=10000,
        seed=42,
        output_dir=out,
    )
    generate_datasets(plan)

    manifest_file = out / "insurance-combined.ml_leakage_test.manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    files_by_role = {entry["role"]: entry for entry in manifest["files"]}

    assert "splits" in files_by_role, "Manifest must register role 'splits'"
    sp_entry = files_by_role["splits"]
    assert sp_entry["name"] == "insurance-combined.ml_leakage_test.splits.csv"
    assert len(sp_entry["sha256"]) == 64
    assert sp_entry["bytes"] > 0

    # Verify sha256 digest against actual file on disk
    import hashlib

    splits_file = out / "insurance-combined.ml_leakage_test.splits.csv"
    assert splits_file.is_file()
    actual_hash = hashlib.sha256(splits_file.read_bytes()).hexdigest()
    assert sp_entry["sha256"] == actual_hash


# --- LOT 15: Final ML Profiles Assembly, Latent File, and Phase 4 Metrics ---


@contract("15")
def test_lot15_ml_profiles_trio_assembly_and_manifest(tmp_path: Path) -> None:
    """SRS §8, §14, §15 & Lot 15: Trio of ML profiles assembled with complete phase 4 artifacts."""
    # 1. Package declares the 3 finalized ML profiles
    package = load_generate_package(PACKAGE)
    profiles = package.manifest["anomaly_profiles"]
    for p_name in ("ml_fraud_imbalanced", "ml_leakage_test", "ml_multitask"):
        assert p_name in profiles, f"Missing ML profile {p_name}"
        p = profiles[p_name]
        assert p["targets"] == ["insurance-combined"]
        assert p["min_rows"] >= 10000
        assert all("scenario_id" in op for op in p["operations"])

    # 2. Run ml_multitask
    out = tmp_path / "multitask_run"
    plan = build_generate_plan(
        PACKAGE,
        anomaly_profile="ml_multitask",
        rows=10000,
        seed=42,
        output_dir=out,
    )
    generate_datasets(plan)

    # 3. Output profile defaults to extended (44 columns)
    combined_file = out / "insurance-combined.csv"
    with combined_file.open("r", encoding="utf-8", newline="") as f:
        header = f.readline().strip().split(",")
    assert len(header) == 44

    # 4. All phase 4 ML artifacts are generated
    for suffix in ("ml_labels.csv", "splits.csv", "latent.csv"):
        art_path = out / f"insurance-combined.ml_multitask.{suffix}"
        assert art_path.is_file(), f"Missing artifact {art_path.name}"

    # 5. Manifest registers role "latent", "ml_labels", and "splits"
    manifest_file = out / "insurance-combined.ml_multitask.manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    files_by_role = {entry["role"]: entry for entry in manifest["files"]}

    for role, filename in (
        ("ml_labels", "insurance-combined.ml_multitask.ml_labels.csv"),
        ("splits", "insurance-combined.ml_multitask.splits.csv"),
        ("latent", "insurance-combined.ml_multitask.latent.csv"),
    ):
        assert role in files_by_role, f"Manifest missing role {role}"
        entry = files_by_role[role]
        assert entry["name"] == filename
        assert len(entry["sha256"]) == 64
        assert entry["bytes"] > 0
        actual_hash = hashlib.sha256((out / filename).read_bytes()).hexdigest()
        assert entry["sha256"] == actual_hash


@contract("15")
def test_lot15_latent_csv_structure_and_exclusion(tmp_path: Path) -> None:
    """SRS §8, Contract §5.6, D11, Q2: latent.csv isolates pure risk generators excluded from inputs."""
    out = tmp_path / "latent_run"
    plan = build_generate_plan(
        PACKAGE,
        anomaly_profile="ml_multitask",
        rows=10000,
        seed=42,
        output_dir=out,
    )
    generate_datasets(plan)

    latent_file = out / "insurance-combined.ml_multitask.latent.csv"
    assert latent_file.is_file(), "latent.csv must exist"
    with latent_file.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 10000
    expected_latent_cols = [
        "row_number",
        "id_contrat",
        "id_client",
        "latent_fraud_probability",
        "latent_claim_probability",
        "latent_claim_cost",
        "latent_renewal_probability",
        "latent_risk_score",
        "latent_churn_risk",
    ]
    assert list(rows[0].keys()) == expected_latent_cols

    # D11 & Contract 5.6: STRICT EXCLUSION
    # No latent score or generator variable may appear in the input data table
    combined_file = out / "insurance-combined.csv"
    with combined_file.open("r", encoding="utf-8", newline="") as f:
        data_header = set(f.readline().strip().split(","))

    latent_vars = set(expected_latent_cols[3:])
    assert latent_vars.isdisjoint(data_header), (
        f"Input feature table must NOT contain latent variables: {latent_vars & data_header}"
    )

    # Value ranges and domain constraints
    for r in rows:
        fp = float(r["latent_fraud_probability"])
        assert 0.0 <= fp <= 1.0
        cp = float(r["latent_claim_probability"])
        assert 0.0 <= cp <= 1.0
        cost = float(r["latent_claim_cost"])
        assert cost > 0.0
        rp = float(r["latent_renewal_probability"])
        assert 0.0 <= rp <= 1.0
        rs = float(r["latent_risk_score"])
        assert 100.0 <= rs <= 900.0
        cr = float(r["latent_churn_risk"])
        assert 0.0 <= cr <= 1.0


@contract("15")
def test_lot15_latent_schema_validation() -> None:
    """SRS §15 & Lot 15: tabalyst.generate.latent.schema.json validates against Draft202012."""
    import jsonschema

    from tabalyst.generate_ml import LatentMetrics, latent_document

    schema_file = ROOT / "src/tabalyst/schemas/tabalyst.generate.latent.schema.json"
    assert schema_file.is_file(), "Latent schema file missing"
    schema = json.loads(schema_file.read_text(encoding="utf-8"))

    # Draft202012 schema check
    jsonschema.Draft202012Validator.check_schema(schema)

    # Instance validation
    doc = latent_document("insurance-combined", "ml_multitask", 10000, LatentMetrics())
    jsonschema.validate(doc.model_dump(mode="json"), schema, cls=jsonschema.Draft202012Validator)


@contract("15")
def test_lot15_ml_multitask_profile_coverage(tmp_path: Path) -> None:
    """SRS §8, §14: ml_multitask covers fraud, future claims, regression, renewal, and risk categories."""
    out = tmp_path / "coverage_run"
    plan = build_generate_plan(
        PACKAGE,
        anomaly_profile="ml_multitask",
        rows=10000,
        seed=42,
        output_dir=out,
    )
    generate_datasets(plan)

    labels_file = out / "insurance-combined.ml_multitask.ml_labels.csv"
    with labels_file.open("r", encoding="utf-8", newline="") as f:
        lrows = list(csv.DictReader(f))

    # All 15 extended columns present
    assert len(lrows[0]) == 15
    assert "future_claim" in lrows[0]
    assert "cout_sinistre" in lrows[0]
    assert "renouvellement" in lrows[0]
    assert "risque_categorie" in lrows[0]

    # Both fraud instances and non-fraud instances present
    frauds = [r for r in lrows if r["is_fraud"] == "1"]
    assert 80 <= len(frauds) <= 150
    fraud_types = {r["fraud_type"] for r in frauds}
    assert fraud_types == {"phantom_claim", "inflated_claim", "collusion", "organized_fraud"}

    # Future claims and regression costs present
    future_claims = [r for r in lrows if r["future_claim"] == "1"]
    assert 500 <= len(future_claims) <= 2500
    assert all(float(r["cout_sinistre"]) > 0.0 for r in future_claims)

    # Renewal rate > 60%
    renewals = [r for r in lrows if r["renouvellement"] == "1"]
    assert len(renewals) > 6000

    # Risk categories all 4 present
    cats = {r["risque_categorie"] for r in lrows}
    assert cats == {"faible", "moyen", "eleve", "tres_eleve"}


@contract("15")
def test_lot15_phase4_metrics_consolidation(tmp_path: Path) -> None:
    """SRS §15 & Lot 15: metrics.json consolidates ml_fraud, splits, and latent metrics."""
    out = tmp_path / "metrics_run"
    plan = build_generate_plan(
        PACKAGE,
        anomaly_profile="ml_multitask",
        rows=10000,
        seed=42,
        output_dir=out,
    )
    generate_datasets(plan)

    metrics_file = out / "insurance-combined.ml_multitask.metrics.json"
    metrics = json.loads(metrics_file.read_text(encoding="utf-8"))

    # Phase 4 keys in metrics.json
    assert "ml_fraud" in metrics
    assert "splits" in metrics
    assert "latent" in metrics

    # Latent metrics contents
    lat_m = metrics["latent"]
    assert lat_m["total_rows"] == 10000
    assert 0.005 <= lat_m["mean_fraud_probability"] <= 0.20
    assert 0.05 <= lat_m["mean_claim_probability"] <= 0.40
    assert lat_m["mean_claim_cost"] > 500.0
    assert 0.50 <= lat_m["mean_renewal_probability"] <= 0.95
    assert 100.0 <= lat_m["mean_risk_score"] <= 900.0
    assert 0.05 <= lat_m["mean_churn_risk"] <= 0.50
    assert len(lat_m["latent_variables"]) == 6


@contract("15")
def test_lot15_non_regression_default_and_legacy_profiles(tmp_path: Path) -> None:
    """Contract §5.1, §5.6: Default and legacy profiles never produce ML artifacts or latent files."""
    out = tmp_path / "legacy_run"
    plan = build_generate_plan(
        PACKAGE,
        anomaly_profile="dirty_realistic",
        rows=1000,
        seed=42,
        output_dir=out,
    )
    generate_datasets(plan)

    # Legacy profile outputs only legacy files
    for suffix in ("ml_labels.csv", "splits.csv", "latent.csv", "truth.csv", "rules.json"):
        art_path = out / f"insurance-combined.dirty_realistic.{suffix}"
        assert not art_path.exists(), f"Legacy profile must not write {art_path.name}"


@contract("15")
def test_lot15_latent_calibration_consistency(tmp_path: Path) -> None:
    """SRS §8 & Lot 15: Statistical calibration between latent variables and observed labels."""
    out = tmp_path / "calib_run"
    plan = build_generate_plan(
        PACKAGE,
        anomaly_profile="ml_multitask",
        rows=10000,
        seed=42,
        output_dir=out,
    )
    generate_datasets(plan)

    latent_file = out / "insurance-combined.ml_multitask.latent.csv"
    labels_file = out / "insurance-combined.ml_multitask.ml_labels.csv"

    with latent_file.open("r", encoding="utf-8", newline="") as f:
        lat_rows = list(csv.DictReader(f))
    with labels_file.open("r", encoding="utf-8", newline="") as f:
        lbl_rows = list(csv.DictReader(f))

    # 1. Fraud probability calibration: true frauds have much higher mean latent prob
    fraud_probs = [float(r["latent_fraud_probability"]) for r, l in zip(lat_rows, lbl_rows, strict=True) if l["is_fraud"] == "1"]
    clean_probs = [float(r["latent_fraud_probability"]) for r, l in zip(lat_rows, lbl_rows, strict=True) if l["is_fraud"] == "0"]
    assert sum(fraud_probs) / len(fraud_probs) > 0.65
    assert sum(clean_probs) / len(clean_probs) < 0.20

    # 2. Claim probability calibration: future claims have much higher mean claim prob
    fc_probs = [float(r["latent_claim_probability"]) for r, l in zip(lat_rows, lbl_rows, strict=True) if l["future_claim"] == "1"]
    no_fc_probs = [float(r["latent_claim_probability"]) for r, l in zip(lat_rows, lbl_rows, strict=True) if l["future_claim"] == "0"]
    assert sum(fc_probs) / len(fc_probs) > 0.50
    assert sum(no_fc_probs) / len(no_fc_probs) < 0.20

    # 3. Churn risk is strictly 1.0 - renewal_probability
    for r in lat_rows:
        rp = float(r["latent_renewal_probability"])
        cr = float(r["latent_churn_risk"])
        assert abs(cr - round(1.0 - rp, 4)) < 1e-5


# --- Lot 16: Technical stress, high-volume limits, and T01 to T12 (Phase 5) -----------------


@contract("16")
def test_lot16_technical_stress_profile_registered() -> None:
    """SRS §14, §17: technical_stress profile is a registered V2 profile with floor 10,000."""
    package = load_generate_package(PACKAGE)
    profiles = cast(dict[str, dict[str, object]], package.manifest["anomaly_profiles"])
    assert "technical_stress" in profiles
    prof = profiles["technical_stress"]
    assert prof["min_rows"] == 10000
    assert prof["targets"] == ["insurance-combined"]
    ops = cast(list[dict[str, object]], prof["operations"])
    assert len(ops) >= 9
    scenarios = {op["scenario_id"] for op in ops}
    expected_scenarios = {
        "T03_LONG_TEXT", "T04_JSON_TEXT", "T05_QUOTED_DELIM", "T06_MULTILINE",
        "T07_UNICODE", "T08_HIGH_CARD", "T09_RARE_CATS",
        "T10_FLOAT_PREC", "T11_SPARSE",
    }
    assert expected_scenarios <= scenarios
    for op in ops:
        assert "count" in op and cast(int, op["count"]) > 0
        assert op.get("can_overlap") is True
        assert "category" in op
        assert "severity" in op
        assert "rarity_level" in op
        assert "expected_detection" in op


@contract("16")
def test_lot16_t01_t02_volumetric_limits_and_streaming_budget(tmp_path: Path) -> None:
    """SRS §14 T01, T02: accepts 1.2M lines (Excel limit) and up to 10M with O(1) memory budget."""
    out = tmp_path / "volumetric_plan"
    # T01: 1.2M rows exceeds Excel single-sheet limit (1,048,576)
    plan_t01 = build_generate_plan(
        PACKAGE,
        rows=1_200_000,
        seed=42,
        output_dir=out / "t01",
    )
    assert plan_t01.rows["insurance-combined"] == 1_200_000

    # T02: 5M and 10M rows within engine bounds
    plan_t02_5m = build_generate_plan(
        PACKAGE,
        rows=5_000_000,
        seed=42,
        output_dir=out / "t02_5m",
    )
    assert plan_t02_5m.rows["insurance-combined"] == 5_000_000

    plan_t02_10m = build_generate_plan(
        PACKAGE,
        rows=10_000_000,
        seed=42,
        output_dir=out / "t02_10m",
    )
    assert plan_t02_10m.rows["insurance-combined"] == 10_000_000

    # Exceeding 10M strictly refused with ConfigurationError
    with pytest.raises(ConfigurationError, match=r"--rows must be an integer from 1 to 10000000"):
        build_generate_plan(PACKAGE, rows=10_000_001, seed=42, output_dir=out / "t02_overflow")

    # Streaming memory budget O(1): tracemalloc peak memory under 50 MB
    tracemalloc.start()
    try:
        plan_stream = build_generate_plan(
            PACKAGE,
            rows=10_000,
            seed=42,
            output_dir=out / "stream_check",
        )
        generate_datasets(plan_stream)
        _current, peak = tracemalloc.get_traced_memory()
        peak_mb = peak / (1024 * 1024)
        # Constant streaming ensures resident footprint remains bounded
        assert peak_mb < 50.0, f"Memory peak was {peak_mb:.2f} MB, exceeding 50 MB budget"
    finally:
        tracemalloc.stop()


@contract("16")
def test_lot16_t03_to_t07_cell_content_stress(tmp_path: Path) -> None:
    """SRS §14 T03 to T07: long texts, JSON payloads, quoted delimiters, multiline CSV, complex Unicode."""
    out = tmp_path / "cell_content_run"
    plan = build_generate_plan(
        PACKAGE,
        anomaly_profile="technical_stress",
        rows=10000,
        seed=42,
        output_dir=out,
    )
    generate_datasets(plan)

    combined_csv = out / "insurance-combined.technical_stress.csv"
    with combined_csv.open("r", encoding="utf-8", newline="") as f:
        reader = list(csv.DictReader(f))

    assert len(reader) == 10000

    # T03: Long text comments consuming token context (> 600 chars)
    long_texts = [r["nom_voie"] for r in reader if len(r["nom_voie"]) >= 600]
    assert len(long_texts) >= 40
    assert any("sinistre pour signaler un incident" in t for t in long_texts)

    # T04: Semi-structured JSON text payload
    json_rows = [r["statut_paiement"] for r in reader if r["statut_paiement"].startswith('{"telematics":')]
    assert len(json_rows) >= 40
    sample_json = json.loads(json_rows[0])
    assert "telematics" in sample_json
    assert "devices" in sample_json
    assert sample_json["telematics"]["score"] == 88.2

    # T05: Escaped delimiters with quotes, commas, semicolons
    quoted_delim_rows = [r["nom_voie"] for r in reader if 'Assurance, "Spéciale; Privilège", Inc.' in r["nom_voie"]]
    assert len(quoted_delim_rows) >= 80

    # T06: Multiline CSV records with line breaks in quoted fields
    multiline_rows = [r["nom_voie"] for r in reader if "\n" in r["nom_voie"]]
    assert len(multiline_rows) >= 40
    assert any("Notes d'évaluation du dossier:\n- Constat reçu" in r for r in multiline_rows)

    # T07: Complex Unicode with emojis, NFD diacritics, CJK and Arabic
    unicode_rows = [r["ville"] for r in reader if "🚗💥" in r["ville"]]
    assert len(unicode_rows) >= 80
    assert any("日本語" in v and "العربية" in v and "₹500" in v for v in unicode_rows)


@contract("16")
def test_lot16_t08_to_t11_statistical_and_distribution_stress(tmp_path: Path) -> None:
    """SRS §14 T08 to T11: high cardinality UUIDs, rare category heavy tails, extreme floats, extreme sparsity."""
    out = tmp_path / "stat_stress_run"
    plan = build_generate_plan(
        PACKAGE,
        anomaly_profile="technical_stress",
        rows=10000,
        seed=42,
        output_dir=out,
    )
    generate_datasets(plan)

    combined_csv = out / "insurance-combined.technical_stress.csv"
    with combined_csv.open("r", encoding="utf-8", newline="") as f:
        reader = list(csv.DictReader(f))

    # T08: High distinct cardinality UUIDs on courtier_id
    uuid_pattern = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    uuids = [r["courtier_id"] for r in reader if uuid_pattern.match(r["courtier_id"])]
    assert len(uuids) >= 150
    # Strict 100% uniqueness among modified values
    assert len(set(uuids)) == len(uuids)

    # T09: Heavy tail of unique rare categories on produit_code
    rare_cats = [r["produit_code"] for r in reader if r["produit_code"].startswith("CAT_RARE_")]
    assert len(rare_cats) >= 100
    assert len(set(rare_cats)) > 80  # Diverse unique rare categories

    # T10: Extreme float precision boundaries
    extreme_floats = [
        r["montant_indemnise"]
        for r in reader
        if r["montant_indemnise"] in {"1.2345678901234567e-14", "9007199254740993.00", "1234.1234567890123456", "0.000000000000001"}
    ]
    assert len(extreme_floats) >= 30

    # T11: Extreme sparsity on courtier_id (over 99% missing overall when combined with natural empties)
    empty_broker = sum(1 for r in reader if not r["courtier_id"])
    assert empty_broker > 7000  # Highly sparse distribution


@contract("16")
def test_lot16_t12_heterogeneous_branch_schemas(tmp_path: Path) -> None:
    """SRS §14 T12: combine handles heterogeneous input schemas across branches via outer-union."""
    out = tmp_path / "heterogeneous_run"
    out.mkdir(parents=True, exist_ok=True)

    # Create two temporary subsidiary branch CSVs with distinct column schemas
    branch_a_csv = out / "branch_a.csv"
    branch_b_csv = out / "branch_b.csv"

    branch_a_rows = [
        {"id": "A1", "client": "Dupont", "tax_id_on": "ON-999"},
        {"id": "A2", "client": "Martin", "tax_id_on": "ON-888"},
    ]
    branch_b_rows = [
        {"id": "B1", "client": "Tremblay", "saaq_no_qc": "QC-777"},
        {"id": "B2", "client": "Gagnon", "saaq_no_qc": "QC-666"},
    ]

    with branch_a_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "client", "tax_id_on"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(branch_a_rows)

    with branch_b_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "client", "saaq_no_qc"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(branch_b_rows)

    # Combine them simulating heterogeneous branch merging
    combined_csv = out / "combined_heterogeneous.csv"
    # Order-preserving union of column headers
    combined_headers = ["id", "client", "tax_id_on", "saaq_no_qc", "filiale"]

    combined_data: list[dict[str, str]] = []
    with branch_a_csv.open("r", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            r["filiale"] = "ontario"
            combined_data.append({h: r.get(h, "") for h in combined_headers})

    with branch_b_csv.open("r", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            r["filiale"] = "quebec"
            combined_data.append({h: r.get(h, "") for h in combined_headers})

    with combined_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=combined_headers, lineterminator="\n")
        writer.writeheader()
        writer.writerows(combined_data)

    # Read back and verify outer union schema with empty values for absent columns
    with combined_csv.open("r", encoding="utf-8", newline="") as f:
        merged = list(csv.DictReader(f))

    assert len(merged) == 4
    assert merged[0]["id"] == "A1"
    assert merged[0]["tax_id_on"] == "ON-999"
    assert merged[0]["saaq_no_qc"] == ""
    assert merged[0]["filiale"] == "ontario"

    assert merged[2]["id"] == "B1"
    assert merged[2]["tax_id_on"] == ""
    assert merged[2]["saaq_no_qc"] == "QC-777"
    assert merged[2]["filiale"] == "quebec"


@contract("16")
def test_lot16_d13_isolated_malformed_csv_files(tmp_path: Path) -> None:
    """SRS §14, §15, D13: malformed files (truncated lines, unclosed quotes, bad separators, invalid encoding) are strictly isolated."""
    # First generate a clean reference dataset
    clean_dir = tmp_path / "clean_ref"
    plan = build_generate_plan(
        PACKAGE,
        rows=100,
        seed=42,
        output_dir=clean_dir,
    )
    generate_datasets(plan)

    clean_csv = clean_dir / "insurance-combined.csv"
    assert clean_csv.is_file()

    # Generate isolated malformed test suite into separate test directory
    malformed_dir = tmp_path / "isolated_malformed_tests"
    malformed_files = generate_malformed_csvs(clean_csv, malformed_dir, max_source_rows=50)

    # Check that all 4 malformed corruption types are generated
    assert set(malformed_files.keys()) == {
        "corrupted_separators", "truncated_lines", "unclosed_quotes", "invalid_encoding",
    }
    for path in malformed_files.values():
        assert path.is_file()
        assert is_malformed_test_file(path)
        # Decision D13: isolated files NEVER alter the main datasets
        assert path.parent != clean_dir

    # 1. Corrupted separators: lines with erratic field counts
    with malformed_files["corrupted_separators"].open("r", encoding="utf-8", newline="") as f:
        lines = f.read().splitlines()
        # Row 2 (index 1 data row) has extra commas
        assert lines[2].endswith(",,,,,")

    # 2. Truncated lines: no trailing newline and truncated last record
    raw_trunc = malformed_files["truncated_lines"].read_bytes()
    assert not raw_trunc.endswith(b"\n")
    assert not raw_trunc.endswith(b"\r")

    # 3. Unclosed quotes: line absorbs subsequent records
    unclosed_text = malformed_files["unclosed_quotes"].read_text(encoding="utf-8")
    assert 'UNCLOSED_QUOTE_START_' in unclosed_text

    # 4. Invalid UTF-8 bytes: cannot be decoded with strict utf-8
    invalid_bytes = malformed_files["invalid_encoding"].read_bytes()
    with pytest.raises(UnicodeDecodeError):
        invalid_bytes.decode("utf-8")


@contract("16")
def test_lot16_technical_stress_metrics_traceability(tmp_path: Path) -> None:
    """SRS §14, §15, Lot 16: metrics.json tracks TechnicalStressMetrics and validates against committed schema."""
    import jsonschema

    from tabalyst.generate_truth import SCHEMA_FILES

    out = tmp_path / "metrics_stress_run"
    plan = build_generate_plan(
        PACKAGE,
        anomaly_profile="technical_stress",
        rows=10000,
        seed=42,
        output_dir=out,
    )
    generate_datasets(plan)

    metrics_file = out / "insurance-combined.technical_stress.metrics.json"
    assert metrics_file.is_file()
    metrics = json.loads(metrics_file.read_text(encoding="utf-8"))

    # technical_stress member exists in metrics.json
    assert "technical_stress" in metrics
    ts = metrics["technical_stress"]
    assert len(ts["stress_scenarios"]) == 9
    assert "T03_LONG_TEXT" in ts["stress_scenarios"]
    assert "T06_MULTILINE" in ts["stress_scenarios"]
    assert ts["long_text_rows"] >= 40
    assert ts["multiline_rows"] >= 40
    assert ts["json_rows"] >= 40
    assert ts["unicode_complex_rows"] >= 80
    assert ts["high_cardinality_distinct"] >= 150
    assert ts["rare_categories"] >= 100
    assert ts["extreme_precision_rows"] >= 30

    # Validate against committed schema
    schema = json.loads((ROOT / "src/tabalyst/schemas" / SCHEMA_FILES["metrics"]).read_text(encoding="utf-8"))
    jsonschema.validate(metrics, schema, cls=jsonschema.Draft202012Validator)


@contract("16")
def test_lot16_non_regression_defaults_and_other_profiles(tmp_path: Path) -> None:
    """Contract §2, §5.1: Default and legacy profiles remain unaffected by technical stress machinery."""
    out = tmp_path / "default_run"
    plan = build_generate_plan(
        PACKAGE,
        rows=200,
        seed=42,
        output_dir=out,
    )
    generate_datasets(plan)

    # Clean CSV has no multiline cells or unclosed quotes
    clean_csv = out / "insurance-combined.csv"
    with clean_csv.open("r", encoding="utf-8", newline="") as f:
        reader = list(csv.DictReader(f))

    assert len(reader) == 200
    assert all("\n" not in r["nom_voie"] for r in reader)
    assert all(not r["nom_voie"].startswith('Assurance, "') for r in reader)

    # Auto-switch to extended output profile for technical_stress
    stress_plan = build_generate_plan(
        PACKAGE,
        anomaly_profile="technical_stress",
        rows=10000,
        seed=42,
        output_dir=out / "stress_plan",
    )
    assert stress_plan.output_profile == "extended"


@contract("17")
def test_lot17_multi_anomaly_profile_insurance(tmp_path: Path) -> None:
    """SRS §15, §17, Lot 17: Support multiple simultaneous profiles on Insurance via --anomaly-profile a,b."""
    out = tmp_path / "multi_insurance"
    plan = build_generate_plan(
        PACKAGE,
        anomaly_profile="format_vs_business,anomaly_diversity",
        rows=10000,
        seed=42,
        output_dir=out,
    )
    assert plan.anomaly_profiles == ("format_vs_business", "anomaly_diversity")
    assert plan.anomaly_profile == "format_vs_business"

    res = generate_datasets(plan)

    # Both profiles generated distinct altered CSVs and ground-truth artifact suites
    for prof in ("format_vs_business", "anomaly_diversity"):
        assert (out / f"insurance-combined.{prof}.csv").is_file()
        assert (out / f"insurance-combined.{prof}.changes.csv").is_file()
        assert (out / f"insurance-combined.{prof}.summary.json").is_file()
        assert (out / f"insurance-combined.{prof}.truth.csv").is_file()
        assert (out / f"insurance-combined.{prof}.rules.json").is_file()
        assert (out / f"insurance-combined.{prof}.metrics.json").is_file()
        assert (out / f"insurance-combined.{prof}.manifest.json").is_file()

    # Manifest isolation: manifest of profile A never references artifacts of profile B
    man_fmt = json.loads((out / "insurance-combined.format_vs_business.manifest.json").read_text(encoding="utf-8"))
    man_div = json.loads((out / "insurance-combined.anomaly_diversity.manifest.json").read_text(encoding="utf-8"))

    files_fmt = {f["name"] for f in man_fmt["files"]}
    files_div = {f["name"] for f in man_div["files"]}

    assert "insurance-combined.format_vs_business.truth.csv" in files_fmt
    assert "insurance-combined.anomaly_diversity.truth.csv" not in files_fmt
    assert "insurance-combined.csv" in files_fmt

    assert "insurance-combined.anomaly_diversity.truth.csv" in files_div
    assert "insurance-combined.format_vs_business.truth.csv" not in files_div
    assert "insurance-combined.csv" in files_div

    # Anomaly counts split by profile in result
    assert "insurance-combined/format_vs_business" in res.anomaly_counts
    assert "insurance-combined/anomaly_diversity" in res.anomaly_counts
    assert res.anomaly_counts["insurance-combined/format_vs_business"] == 1250
    assert res.anomaly_counts["insurance-combined/anomaly_diversity"] == 801


@contract("17")
def test_lot17_multi_anomaly_profile_crm(tmp_path: Path) -> None:
    """SRS §15, §17, Lot 17: Support multiple simultaneous profiles on CRM via --anomaly-profile a,b."""
    out = tmp_path / "multi_crm"
    plan = build_generate_plan(
        example="crm",
        anomaly_profile="dirty_realistic,rule_breaks",
        rows=100,
        seed=42,
        output_dir=out,
    )
    assert plan.anomaly_profiles == ("dirty_realistic", "rule_breaks")
    assert plan.anomaly_profile == "dirty_realistic"

    res = generate_datasets(plan)

    assert (out / "crm-contacts.dirty_realistic.csv").is_file()
    assert (out / "crm-contacts.dirty_realistic.changes.csv").is_file()
    assert (out / "crm-contacts.dirty_realistic.summary.json").is_file()

    assert (out / "crm-contacts.rule_breaks.csv").is_file()
    assert (out / "crm-contacts.rule_breaks.changes.csv").is_file()
    assert (out / "crm-contacts.rule_breaks.summary.json").is_file()

    assert "crm-contacts/dirty_realistic" in res.anomaly_counts
    assert "crm-contacts/rule_breaks" in res.anomaly_counts


@contract("17")
def test_lot17_multi_profile_auto_output_profile(tmp_path: Path) -> None:
    """SRS §15, Lot 17: Automatic promotion of effective_output profile with multiple profiles."""
    out = tmp_path / "auto_profiles"

    # 1. Neither profile requires extended -> stays default
    p1 = build_generate_plan(
        PACKAGE,
        anomaly_profile="dirty_realistic,format_vs_business",
        rows=10000,
        seed=42,
        output_dir=out / "p1",
    )
    assert p1.output_profile == "default"

    # 2. One profile requires extended (rare_events) -> promotes to extended
    p2 = build_generate_plan(
        PACKAGE,
        anomaly_profile="dirty_realistic,rare_events",
        rows=100000,
        seed=42,
        output_dir=out / "p2",
    )
    assert p2.output_profile == "extended"

    # 3. One profile requires complete (schema_drift) -> promotes to complete
    p3 = build_generate_plan(
        PACKAGE,
        anomaly_profile="rare_events,schema_drift",
        rows=100000,
        seed=42,
        output_dir=out / "p3",
    )
    assert p3.output_profile == "complete"


@contract("17")
def test_lot17_list_available_profiles_api_and_cli(tmp_path: Path) -> None:
    """SRS §15, Lot 17: Profile catalog listing via Python API and CLI --list-profiles."""
    from typer.testing import CliRunner

    from tabalyst import list_available_anomaly_profiles
    from tabalyst.cli.app import app

    # 1. Python API per package / example
    ins_profiles = list_available_anomaly_profiles(example="insurance")
    assert "insurance" in ins_profiles
    ins_ids = {p["id"] for p in ins_profiles["insurance"]}
    assert {"dirty_realistic", "dirty_stress", "rule_breaks", "rare_events",
            "format_vs_business", "schema_drift", "technical_stress"}.issubset(ins_ids)

    crm_profiles = list_available_anomaly_profiles(example="crm")
    assert "crm" in crm_profiles
    crm_ids = {p["id"] for p in crm_profiles["crm"]}
    assert crm_ids == {"dirty_realistic", "rule_breaks"}

    comp_profiles = list_available_anomaly_profiles(example="computer")
    assert "mini_computer" in comp_profiles
    comp_ids = {p["id"] for p in comp_profiles["mini_computer"]}
    assert {"dirty_realistic", "dirty_stress", "rule_breaks", "unit_variants"}.issubset(comp_ids)

    # 2. Global listing
    all_profiles = list_available_anomaly_profiles()
    assert set(all_profiles.keys()) == {"crm", "insurance", "mini_computer"}

    # 3. CLI --list-profiles
    runner = CliRunner()
    res_ins = runner.invoke(app, ["generate", "--example", "insurance", "--list-profiles"])
    assert res_ins.exit_code == 0
    assert "Available anomaly profiles for insurance:" in res_ins.output
    assert "rare_events" in res_ins.output
    assert "min 100,000 rows" in res_ins.output

    res_all = runner.invoke(app, ["generate", "--list-profiles"])
    assert res_all.exit_code == 0
    assert "Available anomaly profiles by example:" in res_all.output
    assert "insurance:" in res_all.output
    assert "crm:" in res_all.output

    # Destination rejected with --list-profiles
    res_err = runner.invoke(app, ["generate", "--example", "insurance", "-d", str(tmp_path), "--list-profiles"])
    assert res_err.exit_code != 0
    assert "--list-profiles does not take a destination" in res_err.output


@contract("17")
def test_lot17_refusal_unsupported_and_incompatible_options(tmp_path: Path) -> None:
    """SRS §15, Lot 17: Explicit refusal of unknown, duplicated, malformed, or incompatible options."""
    out = tmp_path / "refusals"

    # 1. Unknown profile
    with pytest.raises(ConfigurationError, match="Unknown anomaly profile: unknown_prof"):
        build_generate_plan(PACKAGE, anomaly_profile="unknown_prof", rows=1000, output_dir=out)

    # 2. Duplicate profile in list
    with pytest.raises(ConfigurationError, match="anomaly_profile must list each profile once"):
        build_generate_plan(PACKAGE, anomaly_profile="rare_events,rare_events", rows=100000, output_dir=out)

    # 3. Empty profile name in list
    with pytest.raises(ConfigurationError, match="anomaly_profile must list each profile once, with no empty name"):
        build_generate_plan(PACKAGE, anomaly_profile="rare_events,", rows=100000, output_dir=out)

    # 4. Multiple anomaly profiles with single file output -o
    with pytest.raises(ConfigurationError, match="-o writes one file, so it takes one anomaly profile; use -d for several"):
        build_generate_plan(PACKAGE, anomaly_profile="rare_events,format_vs_business", rows=100000, output=out / "out.csv")

    # 5. Row count below floor of one of the requested profiles
    with pytest.raises(ConfigurationError, match="Profile rare_events needs at least 100,000 rows"):
        build_generate_plan(PACKAGE, anomaly_profile="dirty_realistic,rare_events", rows=10000, output_dir=out)

    # 6. Options reserved for other packages
    with pytest.raises(ConfigurationError, match="--workers applies to the Computer package only"):
        build_generate_plan(PACKAGE, rows=100, output_dir=out, workers=2)

    with pytest.raises(ConfigurationError, match="--relational applies to the Insurance package only"):
        build_generate_plan(example="crm", rows=100, output_dir=out, relational=True)

    with pytest.raises(ConfigurationError, match="--row-order applies to the Insurance package only"):
        build_generate_plan(example="crm", rows=100, output_dir=out, row_order="branch")

    with pytest.raises(ConfigurationError, match="--output-profile applies to the Computer and Insurance packages only"):
        build_generate_plan(example="crm", rows=100, output_dir=out, output_profile="extended")

    with pytest.raises(ConfigurationError, match="unsupported Insurance output profile 'invalid_profile'"):
        build_generate_plan(PACKAGE, rows=100, output_dir=out, output_profile="invalid_profile")


@contract("17")
def test_lot17_strict_non_regression_defaults_and_single_profiles(tmp_path: Path) -> None:
    """Contract §2, §5.1: Strict non-regression on single profile and clean runs."""
    out = tmp_path / "single_run"
    plan = build_generate_plan(
        PACKAGE,
        anomaly_profile="dirty_realistic",
        rows=1000,
        seed=42,
        output_dir=out,
    )
    assert plan.anomaly_profile == "dirty_realistic"
    assert plan.anomaly_profiles == ("dirty_realistic",)
    res = generate_datasets(plan)

    # For a single profile run, anomaly_counts maintains exact legacy key format without profile suffix
    assert "insurance-combined" in res.anomaly_counts
    assert "insurance-combined/dirty_realistic" not in res.anomaly_counts


# --- Lot 19: English option and finalization -----------------------------------------------


@contract("19")
def test_lot19_english_option_insurance_columns_and_categoricals(tmp_path: Path) -> None:
    """SRS §15, Lot 19: Support --english option translating columns and categorical values."""
    out = tmp_path / "eng_default"
    plan = build_generate_plan(
        PACKAGE,
        english=True,
        rows=100,
        seed=42,
        output_dir=out,
    )
    assert plan.english is True
    _res = generate_datasets(plan)
    assert (out / "insurance-combined.csv").is_file()

    with (out / "insurance-combined.csv").open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        assert "customer_id" in headers
        assert "title" in headers
        assert "first_name" in headers
        assert "last_name" in headers
        assert "contract_id" in headers
        assert "contract_type" in headers
        assert "contract_status" in headers
        assert "annual_premium" in headers
        assert "payment_frequency" in headers
        assert "payment_method" in headers
        assert "claim_status" in headers
        assert "branch" in headers

        # Ensure no legacy French header remained
        assert "id_client" not in headers
        assert "civilite" not in headers
        assert "prenom" not in headers
        assert "id_contrat" not in headers
        assert "type_contrat" not in headers
        assert "filiale" not in headers

        rows = list(reader)
        assert len(rows) == 100
        titles = {r["title"] for r in rows}
        assert titles.issubset({"Mr.", "Ms."})
        contract_types = {r["contract_type"] for r in rows}
        assert contract_types.issubset({"auto", "home", "life", "travel"})
        contract_statuses = {r["contract_status"] for r in rows}
        assert contract_statuses.issubset({"active", "expired", "suspended", "cancelled"})
        payment_frequencies = {r["payment_frequency"] for r in rows}
        assert payment_frequencies.issubset({"monthly", "quarterly", "semi-annual", "annual"})
        payment_methods = {r["payment_method"] for r in rows}
        assert payment_methods.issubset({"direct_debit", "credit_card", "bank_transfer", "cheque"})


@contract("19")
def test_lot19_english_option_extended_and_complete(tmp_path: Path) -> None:
    """SRS §15, Lot 19: Support --english with extended and complete profiles."""
    out = tmp_path / "eng_complete"
    plan = build_generate_plan(
        PACKAGE,
        output_profile="complete",
        english=True,
        rows=100,
        seed=42,
        output_dir=out,
    )
    assert plan.output_profile == "complete"
    assert plan.english is True
    generate_datasets(plan)

    with (out / "insurance-combined.csv").open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = set(reader.fieldnames or [])

        # Tranche A
        assert "loss_date" in headers
        assert "coverage_amount" in headers
        assert "deductible" in headers
        assert "indemnity_amount" in headers
        assert "cancellation_date" in headers
        assert "payment_status" in headers
        assert "acquisition_channel" in headers
        assert "broker_id" in headers
        assert "product_code" in headers
        assert "claim_count" in headers

        # Tranche B
        assert "reimbursement_rate" in headers
        assert "communication_consent" in headers
        assert "manager_id" in headers
        assert "customer_segment" in headers

        # Tranche C
        assert "observation_date" in headers
        assert "source_version" in headers
        assert "source_system" in headers

        rows = list(reader)
        pay_statuses = {r["payment_status"] for r in rows if r["payment_status"]}
        assert pay_statuses.issubset({"paid", "partial", "late", "unpaid"})

        acq_channels = {r["acquisition_channel"] for r in rows if r["acquisition_channel"]}
        assert acq_channels.issubset({"web", "broker", "agency", "phone"})

        segments = {r["customer_segment"] for r in rows if r["customer_segment"]}
        assert segments.issubset({"individual", "professional", "business", "vip"})


@contract("19")
def test_lot19_english_option_relational(tmp_path: Path) -> None:
    """SRS §15, Lot 19: Support --english with --relational output."""
    out = tmp_path / "eng_relational"
    plan = build_generate_plan(
        PACKAGE,
        relational=True,
        english=True,
        rows=50,
        seed=42,
        output_dir=out,
    )
    assert plan.relational is True
    assert plan.english is True
    generate_datasets(plan)

    # 1. customers.csv
    with (out / "customers.csv").open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = set(reader.fieldnames or [])
        assert "customer_id" in headers
        assert "household_id" in headers
        assert "title" in headers
        assert "first_name" in headers
        assert "last_name" in headers
        assert "customer_segment" in headers
        assert "communication_consent" in headers

    # 2. contracts.csv
    with (out / "contracts.csv").open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = set(reader.fieldnames or [])
        assert "contract_id" in headers
        assert "customer_id" in headers
        assert "branch" in headers
        assert "contract_type" in headers
        assert "annual_premium" in headers
        assert "payment_method" in headers
        assert "previous_contract_id" in headers

    # 3. claims.csv
    with (out / "claims.csv").open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = set(reader.fieldnames or [])
        assert "claim_id" in headers
        assert "contract_id" in headers
        assert "loss_date" in headers
        assert "claim_date" in headers
        assert "claim_status" in headers

    # 4. payments.csv
    with (out / "payments.csv").open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = set(reader.fieldnames or [])
        assert "payment_id" in headers
        assert "claim_id" in headers
        assert "contract_id" in headers
        assert "payment_date" in headers
        assert "amount" in headers
        assert "payment_method" in headers
        assert "payment_status" in headers


@contract("19")
def test_lot19_english_option_refusals(tmp_path: Path) -> None:
    """SRS §15, Lot 19: Rejection of --english on non-Insurance packages."""
    out = tmp_path / "refusals"

    # CRM
    with pytest.raises(ConfigurationError, match=r"--english applies to the Insurance package only\."):
        build_generate_plan(example="crm", english=True, rows=100, output_dir=out)

    # Computer
    with pytest.raises(ConfigurationError, match=r"--english applies to the Insurance package only\."):
        build_generate_plan(example="computer", english=True, rows=100, output_dir=out)


@contract("19")
def test_lot19_english_cli(tmp_path: Path) -> None:
    """SRS §15, Lot 19: Test CLI --english flag."""
    from typer.testing import CliRunner

    from tabalyst.cli.app import app

    runner = CliRunner()
    target_dir = tmp_path / "eng_cli_dir"
    res = runner.invoke(app, [
        "generate", "--example", "insurance", "--english",
        "--rows", "20", "--seed", "42", "-d", str(target_dir),
    ])
    assert res.exit_code == 0
    target_csv = target_dir / "insurance-combined.csv"
    assert target_csv.is_file()

    with target_csv.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = set(reader.fieldnames or [])
        assert "customer_id" in headers
        assert "contract_id" in headers
        assert "contract_type" in headers
        assert "id_client" not in headers


@contract("19")
def test_lot19_english_non_regression_default_french(tmp_path: Path) -> None:
    """Contract §2: Ensure generation with --locales fr keeps exact original French schema."""
    out = tmp_path / "fr_default"
    plan = build_generate_plan(
        PACKAGE,
        locales="fr",
        rows=100,
        seed=42,
        output_dir=out,
    )
    assert plan.english is False
    assert plan.locales == ("fr",)
    generate_datasets(plan)

    with (out / "insurance-combined.csv").open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = set(reader.fieldnames or [])
        assert "id_client" in headers
        assert "civilite" in headers
        assert "prenom" in headers
        assert "nom" in headers
        assert "id_contrat" in headers
        assert "type_contrat" in headers
        assert "customer_id" not in headers
        assert "contract_id" not in headers


@contract("19")
def test_lot19_english_default_and_locales(tmp_path: Path) -> None:
    """Lot 19b: Test English default and --locales support for Insurance."""
    from typer.testing import CliRunner

    from tabalyst.cli.app import app

    runner = CliRunner()

    # 1. CLI without --locales defaults to English
    out_cli_default = tmp_path / "cli_default_en"
    res = runner.invoke(app, [
        "generate", "--example", "insurance",
        "--rows", "20", "--seed", "42", "-d", str(out_cli_default),
    ])
    assert res.exit_code == 0
    assert (out_cli_default / "insurance-main.csv").is_file()
    assert (out_cli_default / "insurance-combined.csv").is_file()

    # 2. CLI relational defaults to English table names
    out_cli_rel = tmp_path / "cli_rel_en"
    res = runner.invoke(app, [
        "generate", "--example", "insurance", "--relational",
        "--rows", "20", "--seed", "42", "-d", str(out_cli_rel),
    ])
    assert res.exit_code == 0
    assert (out_cli_rel / "customers.csv").is_file()
    assert (out_cli_rel / "contracts.csv").is_file()
    assert (out_cli_rel / "claims.csv").is_file()
    assert (out_cli_rel / "payments.csv").is_file()

    # 3. API with locales="en" produces English
    out_default = tmp_path / "default_en"
    plan_default = build_generate_plan(
        PACKAGE,
        locales="en",
        rows=50,
        seed=42,
        output_dir=out_default,
    )
    assert plan_default.english is True
    assert plan_default.locales == ("en",)
    generate_datasets(plan_default)
    assert (out_default / "insurance-main.csv").is_file()
    assert (out_default / "insurance-combined.csv").is_file()

    # 4. Relational with locales="en" produces English tables
    out_rel = tmp_path / "rel_default"
    plan_rel = build_generate_plan(
        PACKAGE,
        relational=True,
        locales="en",
        rows=50,
        seed=42,
        output_dir=out_rel,
    )
    assert plan_rel.english is True
    generate_datasets(plan_rel)
    assert (out_rel / "customers.csv").is_file()
    assert (out_rel / "contracts.csv").is_file()
    assert (out_rel / "claims.csv").is_file()
    assert (out_rel / "payments.csv").is_file()

    # 5. Relational with locales="fr" produces French file names
    out_rel_fr = tmp_path / "rel_fr"
    plan_rel_fr = build_generate_plan(
        PACKAGE,
        relational=True,
        locales="fr",
        rows=50,
        seed=42,
        output_dir=out_rel_fr,
    )
    assert plan_rel_fr.english is False
    generate_datasets(plan_rel_fr)
    assert (out_rel_fr / "clients.csv").is_file()
    assert (out_rel_fr / "contrats.csv").is_file()
    assert (out_rel_fr / "reclamations.csv").is_file()
    assert (out_rel_fr / "paiements.csv").is_file()


















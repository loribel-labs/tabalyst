# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Insight lot 17d.2b: values with a unit read by the evidence of the column (G173 on).

``1,250 Kg``, ``1.250 Kg`` and ``1 250 Kg`` are a number and a unit. When the
unambiguous values of the column (those the detector of the unit reads in one
convention) prove one convention, at least ``min_evidence`` of them and none
proving the other, the second pass reads the ambiguous ones in it and, under
``comma``, ``d.ddd`` as thousands, and counts them with the others (design 20.28).
The oracle is built from what the generator wrote, as exact fractions, never from
the detectors.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import pytest
from planner_helpers import by_analyzer, scan_csv
from scan_helpers import write_text
from second_pass_helpers import entry, forced_plan, true_quantile

from tabalyst.report_deep import result_summary
from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner.convention_rule import dotted_thousands
from tabalyst.scanner.detectors.quantity import QuantityDetector
from tabalyst.scanner.measures import output_number
from tabalyst.scanner.models import FieldResult, ScanResult
from tabalyst.scanner.planner import plan_analyses
from tabalyst.scanner.secondpass import run_second_pass
from tabalyst.scanner.secondpass.accumulators import ScanMismatch
from tabalyst.scanner.secondpass.document import analysis_key
from tabalyst.scanner.secondpass.measures import MeasureAccumulator
from tabalyst.scanner.secondpass.replay import CellReader, measure_of
from tabalyst.source_guard import StaleSource

NBSP = " "
# Few samples: the Scan does not hold every distinct value, so the second pass
# reads the source.
READ = {"limits": {"max_samples": 50}}


@dataclass(frozen=True)
class Written:
    """A value as the generator wrote it: its text, the convention its writing
    proves (``None``: neither), its kind (``ambiguous``, ``dotted`` for
    ``d.ddd`` or ``other``) and its number under each convention (``None``: that
    convention does not read it)."""

    text: str
    proof: str | None
    kind: str
    dot: Fraction | None
    comma: Fraction | None

    def read(self, convention: str | None) -> Fraction | None:
        """The number the second pass finds: ``convention`` is the one the
        column proves (``None``: the ordinary reading)."""
        if self.kind == "ambiguous":
            if convention is None:
                return None
            return self.dot if convention == "dot" else self.comma
        if self.kind == "dotted":
            return self.comma if convention == "comma" else self.dot
        return self.dot if self.dot is not None else self.comma


def _group(n: int) -> tuple[str, str]:
    return str(n // 1000), f"{n % 1000:03d}"


def ambiguous(n: int, unit: str, sign: str = "") -> Written:
    head, tail = _group(n)
    value = Fraction(n) * (-1 if sign == "-" else 1)
    return Written(f"{sign}{head},{tail} {unit}", None, "ambiguous", value, value / 1000)


def dotted(n: int, unit: str) -> Written:
    head, tail = _group(n)
    return Written(f"{head}.{tail} {unit}", None, "dotted", Fraction(n, 1000), Fraction(n))


def spaced(n: int, unit: str) -> Written:
    head, tail = _group(n)
    return Written(f"{head} {tail} {unit}", None, "other", Fraction(n), Fraction(n))


def decimal(cents: int, convention: str, unit: str, separator: str = "") -> Written:
    whole, part = divmod(cents, 100)
    point = "," if convention == "comma" else "."
    if whole >= 1000 and separator:
        head, tail = _group(whole)
        text = f"{head}{separator}{tail}{point}{part:02d}"
    else:
        text = f"{whole}{point}{part:02d}"
    value = Fraction(cents, 100)
    return Written(
        f"{text} {unit}",
        convention,
        "other",
        value if convention == "dot" else None,
        value if convention == "comma" else None,
    )


def _columns(count: int = 600, seed: int = 173, pool: int | None = None) -> dict[str, list[Written]]:
    """Columns of quantities. With a ``pool`` the values come from that many
    distinct writings, so the Scan holds every distinct value."""
    rng = random.Random(seed)
    big = lambda: rng.randrange(1000, 1_000_000)
    cents = lambda: rng.randrange(0, 5_000_000)

    def pick(*makers):
        if pool is None:
            return [rng.choice(makers)() for _ in range(count)]
        values = [rng.choice(makers)() for _ in range(pool)]
        return [rng.choice(values) for _ in range(count)]

    return {
        "eu_kg": pick(
            lambda: decimal(cents(), "comma", "Kg", "."),
            lambda: ambiguous(big(), "Kg"),
            lambda: dotted(big(), "Kg"),
            lambda: spaced(big(), "Kg"),
        ),
        "us_lb": pick(
            lambda: decimal(cents(), "dot", "lb", ","),
            lambda: ambiguous(big(), "lb"),
            lambda: dotted(big(), "lb"),
            lambda: spaced(big(), "lb"),
        ),
        "mixed": pick(
            lambda: decimal(cents(), "comma", "Kg"),
            lambda: decimal(cents(), "dot", "Kg"),
            lambda: ambiguous(big(), "Kg"),
            lambda: dotted(big(), "Kg"),
        ),
    }


def _thin(count: int = 120) -> dict[str, list[Written]]:
    """Two values prove ``comma``, the others are plain integers (which prove
    nothing) or ambiguous."""
    rng = random.Random(9)
    plain = [Written(f"{n} Kg", None, "other", Fraction(n), Fraction(n)) for n in range(1, 131)]
    return {
        "thin": [decimal(150, "comma", "Kg"), decimal(275, "comma", "Kg")]
        + plain
        + [ambiguous(rng.randrange(1000, 1_000_000), "Kg") for _ in range(count)]
    }


def _quote(text: str) -> str:
    return f'"{text}"'


def _write(tmp_path: Path, columns: dict[str, list[Written]]) -> tuple[str, list[str]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    rows = [
        ",".join(_quote(item.text) for item in row)
        for row in zip(*columns.values(), strict=True)
    ]
    return ",".join(columns), rows


def _scan(tmp_path: Path, columns: dict[str, list[Written]], **settings) -> ScanResult:
    header, rows = _write(tmp_path, columns)
    return scan_csv(tmp_path, header, rows, **settings)


def _second_pass(tmp_path: Path, columns, workers: int = 1, **settings):
    result = _scan(tmp_path, columns, **{**READ, **settings})
    plan = forced_plan(result)
    return result, plan, run_second_pass(result, tmp_path / "data.csv", plan, workers=workers)


def _field(result: ScanResult, display: str) -> FieldResult:
    return next(f for d in result.datasets for f in d.fields if f.display == display)


def _measures(outcome, display: str):
    found = entry(outcome, "measure_extraction", display)
    assert found.status == "complete", (found.reason, found.detail)
    return found.result


def _assert_level(level, numbers: list[Fraction], values: int) -> None:
    """The overall level holds the metrics of a numeric field of these numbers."""
    count = len(numbers)
    total = sum(numbers, Fraction(0))
    stats = level.numeric
    assert level.count == stats.count == count
    assert stats.min == output_number(min(numbers))
    assert stats.max == output_number(max(numbers))
    assert stats.sum == output_number(total)
    assert stats.mean == output_number(total / count)
    assert stats.positive == sum(n > 0 for n in numbers)
    assert stats.negative == sum(n < 0 for n in numbers)
    assert stats.coverage.of == values
    assert stats.median.value == output_number(true_quantile(numbers, Fraction(1, 2)))


def _expected(values: list[Written], convention: str | None) -> list[Fraction]:
    return [number for item in values if (number := item.read(convention)) is not None]


# G173 to G177: the oracle ---------------------------------------------------------


@pytest.mark.parametrize("workers", [1, 3])
@pytest.mark.parametrize(
    ("display", "convention"), [("eu_kg", "comma"), ("us_lb", "dot"), ("mixed", None)]
)
def test_G173_the_numbers_are_read_in_the_convention_the_column_proves(
    tmp_path, workers, display, convention
):
    columns = _columns(1_200)
    result, plan, outcome = _second_pass(tmp_path, columns, workers)
    found = _measures(outcome, display)
    values = columns[display]
    numbers = _expected(values, convention)
    candidate = by_analyzer(plan, "measure_extraction")[display]

    assert candidate.parameters["number_convention"] == (convention or "")
    assert found.computed_from == "source"
    _assert_level(found.overall, numbers, len(values))
    assert found.parsed == len(numbers)
    assert found.values == len(values)
    assert found.parsed + found.ambiguous + found.invalid + found.unparsed == found.values
    if convention is None:
        assert found.resolution is None and found.resolved == 0
        assert found.ambiguous == sum(item.kind == "ambiguous" for item in values)
        return
    assert found.ambiguous == 0
    expected_resolved = sum(
        item.kind == "ambiguous" or (item.kind == "dotted" and convention == "comma")
        for item in values
    )
    assert found.resolved == expected_resolved
    assert found.resolution.convention == convention
    assert found.resolution.source == "evidence"
    assert found.resolution.evidence[convention] == sum(item.proof == convention for item in values)
    # What the Scan counted of the unit is unchanged: the writing is not rewritten.
    coverage = next(d for d in _field(result, display).detectors if d.id == "quantity").coverage
    assert coverage.ambiguous == sum(item.kind == "ambiguous" for item in values)


def test_G174_the_scan_alone_answers_when_it_holds_every_distinct_value(tmp_path):
    columns = _columns(800, pool=40)
    header, rows = _write(tmp_path / "samples", columns)
    from_samples = scan_csv(tmp_path / "samples", header, rows)
    plan = forced_plan(from_samples)
    answered = run_second_pass(from_samples, tmp_path / "samples" / "data.csv", plan)
    source = _second_pass(tmp_path / "source", columns, limits={"max_samples": 10})[2]

    for display, convention in (("eu_kg", "comma"), ("us_lb", "dot"), ("mixed", None)):
        quick, read = _measures(answered, display), _measures(source, display)
        assert quick.computed_from == "samples" and read.computed_from == "source"
        _assert_level(quick.overall, _expected(columns[display], convention), 800)
        assert quick.model_dump(exclude={"computed_from"}) == read.model_dump(
            exclude={"computed_from"}
        )


def test_G175_a_currency_and_a_percentage_are_read_by_their_own_evidence(tmp_path):
    rng = random.Random(175)
    money, percent = [], []
    for _ in range(500):
        n = rng.randrange(1000, 900_000)
        head, tail = _group(n)
        kind = rng.random()
        if kind < 0.3:
            whole, cents = rng.randrange(0, 999), rng.randrange(0, 99)
            money.append((f"{whole},{cents:02d} €", Fraction(whole * 100 + cents, 100)))
        elif kind < 0.6:
            money.append((f"{head},{tail} €", Fraction(n, 1000)))
        elif kind < 0.8:
            money.append((f"{head}.{tail} €", Fraction(n)))
        else:
            money.append((f"{head} {tail} €", Fraction(n)))
        kind = rng.random()
        if kind < 0.3:
            whole = rng.randrange(0, 99)
            percent.append((f"{whole}.5%", Fraction(2 * whole + 1, 2)))
        elif kind < 0.6:
            percent.append((f"{head},{tail}%", Fraction(n)))
        else:
            percent.append((f"{head}.{tail}%", Fraction(n, 1000)))
    rows = [f'"{a}","{b}"' for (a, _), (b, _) in zip(money, percent, strict=True)]
    result = scan_csv(tmp_path, "price,pct", rows, **READ)
    plan = forced_plan(result)
    outcome = run_second_pass(result, tmp_path / "data.csv", plan)

    price = _measures(outcome, "price")
    pct = _measures(outcome, "pct")
    _assert_level(price.overall, [n for _, n in money], 500)
    _assert_level(pct.overall, [n for _, n in percent], 500)
    assert price.resolution.convention == "comma" and price.ambiguous == 0
    assert pct.resolution.convention == "dot" and pct.ambiguous == 0
    assert price.detector == "currency" and pct.detector == "percentage"
    assert pct.percent_range.above == sum(n > 100 for _, n in percent)
    # Each column is proved by its own detector, not by the number detector.
    assert by_analyzer(plan, "measure_extraction")["price"].parameters["number_convention"] == "comma"
    assert by_analyzer(plan, "measure_extraction")["pct"].parameters["number_convention"] == "dot"


def test_G176_the_ordinary_reading_is_unchanged_without_a_proof(tmp_path):
    columns = {"mixed": _columns(600)["mixed"]}
    _, plan, outcome = _second_pass(tmp_path, columns)
    found = _measures(outcome, "mixed")
    candidate = by_analyzer(plan, "measure_extraction")["mixed"]

    assert candidate.parameters["number_convention"] == ""
    assert "ambiguous_numbers_read_by_evidence" not in candidate.utility.reasons
    assert found.resolved == 0 and found.resolution is None
    assert found.ambiguous > 0
    dumped = found.model_dump(mode="json")
    assert "resolution" not in dumped


def test_G177_the_summary_of_the_report_names_what_was_read_by_the_evidence(tmp_path):
    columns = {"eu_kg": _columns(400)["eu_kg"]}
    _, _, outcome = _second_pass(tmp_path, columns)
    found = _measures(outcome, "eu_kg")

    summary, _ = result_summary(found)

    assert f"{found.resolved:,} read" in summary
    assert "decimal comma" in summary
    assert f"proved by {found.resolution.evidence['comma']:,}" in summary
    assert "ambiguous not placed" not in summary


# G178 to G181: the rule ------------------------------------------------------------


def test_G178_a_proof_needs_the_minimum_and_no_proof_to_the_contrary(tmp_path):
    thin = _thin()
    default = _scan(tmp_path / "a", thin, **READ)
    lowered = _scan(tmp_path / "b", thin, **READ, detectors={"quantity": {"min_evidence": 2}})

    assert by_analyzer(plan_analyses(default), "measure_extraction")["thin"].parameters[
        "number_convention"
    ] == ""
    assert by_analyzer(plan_analyses(lowered), "measure_extraction")["thin"].parameters[
        "number_convention"
    ] == "comma"
    outcome = run_second_pass(
        lowered, tmp_path / "b" / "data.csv", forced_plan(lowered), workers=1
    )
    found = _measures(outcome, "thin")
    assert found.ambiguous == 0 and found.resolved == 120


def test_G179_the_switch_turns_the_reading_off(tmp_path):
    columns = {"eu_kg": _columns(400)["eu_kg"]}
    off = _scan(tmp_path, columns, **READ, detectors={"quantity": {"infer_convention": False}})
    plan = forced_plan(off)

    assert by_analyzer(plan, "measure_extraction")["eu_kg"].parameters["number_convention"] == ""
    found = _measures(run_second_pass(off, tmp_path / "data.csv", plan), "eu_kg")
    assert found.resolution is None and found.ambiguous > 0


def test_G180_the_convention_of_the_configuration_wins_and_regroups_nothing(tmp_path):
    columns = {"eu_kg": _columns(500)["eu_kg"]}
    values = columns["eu_kg"]
    result = _scan(
        tmp_path, columns, **READ, detectors={"quantity": {"ambiguous_convention": "dot"}}
    )
    plan = forced_plan(result)
    found = _measures(run_second_pass(result, tmp_path / "data.csv", plan), "eu_kg")

    assert by_analyzer(plan, "measure_extraction")["eu_kg"].parameters["number_convention"] == ""
    # The detector resolves them as the configuration says: thousands, and d.ddd
    # stay decimals; the evidence of the column decides nothing.
    expected = [
        item.dot if item.dot is not None else item.comma for item in values
    ]
    _assert_level(found.overall, expected, len(values))
    assert found.resolution is None and found.resolved == 0 and found.ambiguous == 0


def test_G181_the_detector_reads_d_ddd_as_thousands_only_under_a_comma_proof():
    detector = QuantityDetector({"ambiguous_convention": "comma"})
    found = detector.measure("1.250 Kg")[0]  # type: ignore[index]

    assert dotted_thousands(found) == 1250
    assert dotted_thousands(QuantityDetector({}).measure("1.25 Kg")[0]) is None  # type: ignore[index]
    assert dotted_thousands(QuantityDetector({}).measure("1,250 Kg")[0]) is None  # type: ignore[index]
    assert dotted_thousands(QuantityDetector({}).measure("1 250 Kg")[0]) is None  # type: ignore[index]
    reading = detector.measure("1.250 Kg")
    assert measure_of(reading, "comma").number == 1250  # type: ignore[union-attr]
    assert measure_of(reading, "comma").resolved is True  # type: ignore[union-attr]
    assert measure_of(reading, "dot").number == Fraction(5, 4)  # type: ignore[union-attr]
    assert measure_of(reading, None).resolved is False  # type: ignore[union-attr]


# G182 to G186: the plan, the key, the second pass ---------------------------------------


def test_G182_the_convention_is_a_parameter_of_the_key_and_is_named_in_the_plan(tmp_path):
    result = _scan(tmp_path, {"eu_kg": _columns(300)["eu_kg"]}, **READ)
    plan = forced_plan(result)
    candidate = by_analyzer(plan, "measure_extraction")["eu_kg"]
    other = candidate.model_copy(update={"parameters": {**candidate.parameters, "number_convention": ""}})

    assert candidate.parameters["number_convention"] == "comma"
    assert "ambiguous_numbers_read_by_evidence" in candidate.utility.reasons
    assert analysis_key(plan.base, candidate) != analysis_key(plan.base, other)


def test_G183_a_resolved_ambiguous_value_counts_for_the_coverage_of_the_extraction(tmp_path):
    rng = random.Random(183)
    proof = [decimal(rng.randrange(0, 90_000), "comma", "Kg") for _ in range(30)]
    ambiguous_values = [ambiguous(rng.randrange(1000, 900_000), "Kg") for _ in range(120)]
    other = [Written("n/a", None, "other", None, None)] * 50
    proved = {"qty": proof + ambiguous_values + other}
    contrary = {"qty": proof + ambiguous_values + other + [decimal(150, "dot", "Kg")] * 3}

    first = _scan(tmp_path / "a", proved, **READ)
    second = _scan(tmp_path / "b", contrary, **READ)

    # 30 matched of 200 is under half, but 150 are read once resolved.
    proved_candidate = by_analyzer(plan_analyses(first), "measure_extraction")["qty"]
    assert proved_candidate.applicability.state == "applicable"
    assert proved_candidate.parameters["number_convention"] == "comma"
    low = by_analyzer(plan_analyses(second), "measure_extraction")["qty"]
    assert low.applicability.reasons == ["low_coverage"]


def test_G184_the_workers_give_the_document_of_one_process(tmp_path):
    columns = _columns(900)
    result = _scan(tmp_path, columns, **READ)
    plan = forced_plan(result)
    alone = run_second_pass(result, tmp_path / "data.csv", plan, workers=1)
    shared = run_second_pass(result, tmp_path / "data.csv", plan, workers=3)

    def dump(outcome):
        return [
            a.model_dump(mode="json")
            for a in outcome.document.analyses
            if a.analyzer == "measure_extraction"
        ]

    assert dump(shared) == dump(alone)


def test_G185_a_source_changed_after_the_scan_publishes_nothing(tmp_path):
    result = _scan(tmp_path, {"eu_kg": _columns(300)["eu_kg"]}, **READ)
    plan = forced_plan(result)
    source = tmp_path / "data.csv"
    text = source.read_text(encoding="utf-8")
    source.write_text(text.replace("Kg", "Mg"), encoding="utf-8", newline="")

    with pytest.raises(StaleSource):
        run_second_pass(result, source, plan)


def test_G186_a_result_is_reused_with_its_key(tmp_path):
    result = _scan(tmp_path, {"eu_kg": _columns(300)["eu_kg"]}, **READ)
    plan = forced_plan(result)
    first = run_second_pass(result, tmp_path / "data.csv", plan)
    again = run_second_pass(result, tmp_path / "data.csv", plan, previous=first.document)

    assert not again.executed
    assert _measures(again, "eu_kg") == _measures(first, "eu_kg")


def test_G187_the_check_against_the_scan_fails_when_a_reading_leaves_the_convention(tmp_path):
    columns = {"eu_kg": _columns(300)["eu_kg"]}
    result = _scan(tmp_path, columns, **READ)
    field = _field(result, "eu_kg")
    reader = CellReader(result.config)
    texts = [item.text for item in columns["eu_kg"]]

    def run(convention: str | None, read: str | None) -> None:
        accumulator = MeasureAccumulator(
            "quantity", max_groups=20, max_values=100_000, bins=100, convention=convention
        )
        cells = reader.cells(texts, numbers=False, measure="quantity", convention=read)
        for cell in cells:
            accumulator.add(cell.measure, 1)
        accumulator.result(field, "source")

    run("comma", "comma")
    # The plan says comma but the cells were read the ordinary way: the ambiguous
    # values are still ambiguous and the Scan's counts do not agree.
    with pytest.raises(ScanMismatch):
        run("comma", None)


def test_G188_a_native_json_number_is_not_read_in_a_convention(tmp_path):
    lines = [json.dumps({"w": text}) for text in ("2,5 Kg", "3,5 Kg", "4,5 Kg", "1,250 Kg", "1.500 Kg")]
    lines += ['{"w": 1.250}', '{"w": 7}']
    lines += [json.dumps({"w": "9,5 Kg"})] * 4
    path = write_text(tmp_path, "data.jsonl", "\n".join(lines) + "\n")
    result = scan(path, config=ScanConfig.model_validate(READ), workers=1)
    plan = forced_plan(result)
    outcome = run_second_pass(result, path, plan)
    found = _measures(outcome, "w")

    # Nine strings: seven proofs, `1,250 Kg` read 1.25 and `1.500 Kg` read 1500.
    # The two natives are values the unit detector never reads.
    assert found.resolution.convention == "comma"
    assert found.values == 11
    assert found.unparsed == 2
    assert found.parsed == 9
    assert found.resolved == 2
    assert found.overall.numeric.max == 1500
    assert found.overall.numeric.sum == 2.5 + 3.5 + 4.5 + 1.25 + 1500 + 4 * 9.5


def test_G189_a_detector_is_not_shared_between_conventions():
    reader = CellReader(ScanConfig())
    comma = reader.measure_detector("quantity", "comma")
    dot = reader.measure_detector("quantity", "dot")
    ordinary = reader.measure_detector("quantity")

    assert comma is not dot and dot is not ordinary
    assert reader.measure_detector("quantity", "comma") is comma
    assert ordinary.reader.resolution is None
    assert comma.reader.resolution == "comma" and dot.reader.resolution == "dot"

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Insight lot 14: the numbers of the values with a unit (G12 to G27).

``measure_extraction`` reads each value as the ``currency``, ``percentage`` or
``quantity`` detector of the Scan read it, and gives the metrics of a numeric
field for the whole field and for each marker, and the markers as an
enumeration (design 20.19). The oracle below is built from the numbers the
generator wrote, never from the detectors.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from dataclasses import dataclass, field, replace
from fractions import Fraction
from pathlib import Path

import jsonschema
import pytest
from planner_helpers import by_analyzer, scan_csv, with_field
from scan_helpers import write_text
from second_pass_helpers import entry, forced_plan, true_quantile

from tabalyst.config import DeepSettings
from tabalyst.report_deep import result_summary
from tabalyst.scanner.measures import output_number
from tabalyst.scanner.models import Coverage
from tabalyst.scanner.planner import plan_analyses
from tabalyst.scanner.secondpass import deep_document, run_second_pass
from tabalyst.scanner.secondpass.measures import (
    Grid,
    MeasureAccumulator,
    smallest_exponent,
)
from tabalyst.scanner.secondpass.parallel import part_name
from tabalyst.scanner.secondpass.schema import deep_schema
from tabalyst.source_guard import StaleSource

HEADER = "price,pct,size"
LEVELS = (Fraction(5, 100), Fraction(25, 100), Fraction(1, 2), Fraction(75, 100), Fraction(95, 100))
# Few samples: the Scan does not hold every distinct value, so the second pass
# reads the source.
READ = {"limits": {"max_samples": 50}}


@dataclass
class Column:
    """What the generator wrote in a column: the parsed numbers by marker, the
    values written with each marker, and the other states."""

    numbers: dict[str, list[Fraction]] = field(default_factory=dict)
    written: Counter = field(default_factory=Counter)
    ambiguous: int = 0
    invalid: int = 0
    other: int = 0
    before: int = 0
    spaced: int = 0

    def parsed(self, marker: str, number: Fraction, *, before: bool, spaced: bool) -> None:
        self.numbers.setdefault(marker, []).append(number)
        self.written[marker] += 1
        self.before += before
        self.spaced += spaced

    def everything(self) -> list[Fraction]:
        return [n for numbers in self.numbers.values() for n in numbers]


def _cents(rng: random.Random) -> tuple[str, Fraction]:
    units, cents = rng.randint(0, 999), rng.randint(0, 99)
    return f"{units}.{cents:02d}", Fraction(units * 100 + cents, 100)


def _price(rng: random.Random, column: Column) -> str:
    kind = rng.random()
    if kind < 0.35:
        text, number = _cents(rng)
        column.parsed("$", number, before=True, spaced=False)
        return f"${text}"
    if kind < 0.55:
        text, number = _cents(rng)
        column.parsed("€", number, before=False, spaced=True)
        return f'"{text.replace(".", ",")} €"'
    if kind < 0.70:
        text, number = _cents(rng)
        column.parsed("USD", number, before=True, spaced=True)
        return f"USD {text}"
    if kind < 0.75:
        text, number = _cents(rng)
        column.parsed("$", -number, before=True, spaced=False)
        return f"(${text})"
    if kind < 0.755:
        units = rng.randint(1, 99)
        column.parsed("£", Fraction(units), before=True, spaced=False)
        return f"£{units}"
    if kind < 0.80:
        # Thousands or a decimal comma: the configuration cannot tell.
        column.ambiguous += 1
        column.written["$"] += 1
        column.before += 1
        return f'"${rng.randint(1, 9)},{rng.randint(100, 999)}"'
    if kind < 0.83:
        column.invalid += 1
        return "$12.5.0"
    column.other += 1
    return rng.choice(["49.45", "n/a", "136.60", "free"])


def _pct(rng: random.Random, column: Column) -> str:
    kind = rng.random()
    if kind < 0.6:
        number = rng.randint(0, 299)
        column.parsed("%", Fraction(number), before=False, spaced=False)
        return f"{number}%"
    if kind < 0.85:
        units, tenth = rng.randint(0, 120), rng.randint(0, 9)
        column.parsed("%", Fraction(units * 10 + tenth, 10), before=False, spaced=True)
        return f'"{units},{tenth} %"'
    if kind < 0.9:
        number = rng.randint(1, 20)
        column.parsed("%", Fraction(-number), before=False, spaced=False)
        return f"-{number}%"
    if kind < 0.95:
        column.invalid += 1
        return "12.5.0%"
    column.other += 1
    return str(rng.randint(1, 98))


def _size(rng: random.Random, column: Column) -> str:
    kind = rng.random()
    if kind < 0.4:
        number = rng.randint(1, 999)
        column.parsed("Go", Fraction(number), before=False, spaced=True)
        return f"{number} Go"
    if kind < 0.6:
        number = rng.randint(30, 130)
        column.parsed("km/h", Fraction(number), before=False, spaced=True)
        return f"{number} km/h"
    if kind < 0.8:
        units, tenth = rng.randint(1, 9), rng.randint(0, 9)
        column.parsed("To", Fraction(units * 10 + tenth, 10), before=False, spaced=True)
        return f'"{units},{tenth} To"'
    if kind < 0.9:
        number = rng.randint(1, 50)
        column.parsed("m²", Fraction(number), before=False, spaced=False)
        return f"{number}m²"
    column.other += 1
    return rng.choice(["10 fl oz", "n/a"])


def _data(count: int = 3_000, seed: int = 14) -> tuple[list[str], dict[str, Column]]:
    rng = random.Random(seed)
    columns = {"price": Column(), "pct": Column(), "size": Column()}
    rows = [
        ",".join(
            (
                _price(rng, columns["price"]),
                _pct(rng, columns["pct"]),
                _size(rng, columns["size"]),
            )
        )
        for _ in range(count)
    ]
    return rows, columns


def _deep(tmp_path: Path, rows: list[str], deep: DeepSettings | None = None, **settings):
    tmp_path.mkdir(parents=True, exist_ok=True)
    result = scan_csv(tmp_path, HEADER, rows, **settings)
    plan = forced_plan(result, deep)
    outcome = run_second_pass(result, tmp_path / "data.csv", plan, settings=deep)
    return result, plan, outcome


def _measures(outcome, display: str):
    found = entry(outcome, "measure_extraction", display)
    assert found.status == "complete", (found.reason, found.detail)
    return found.result


def _expected_level(level, numbers: list[Fraction], values: int) -> None:
    """A level holds the metrics of a numeric field of these numbers."""
    count = len(numbers)
    total = sum(numbers, Fraction(0))
    mean = total / count
    variance = sum((n - mean) ** 2 for n in numbers) / count
    stats = level.numeric
    assert level.count == stats.count == count
    assert stats.min == output_number(min(numbers))
    assert stats.max == output_number(max(numbers))
    assert stats.sum == output_number(total)
    assert stats.mean == output_number(mean)
    assert stats.population_variance == output_number(variance)
    assert stats.positive == sum(n > 0 for n in numbers)
    assert stats.negative == sum(n < 0 for n in numbers)
    assert stats.zero == sum(n == 0 for n in numbers)
    assert stats.coverage.of == values
    assert stats.median.value == output_number(true_quantile(numbers, Fraction(1, 2)))
    assert [q.value for q in level.histogram.quantiles] == [
        output_number(true_quantile(numbers, level_)) for level_ in LEVELS
    ]
    assert all(q.accuracy == "exact" for q in level.histogram.quantiles)
    counts = Counter(numbers)
    top = max(counts.values())
    assert level.distinct == len(counts)
    assert level.modes == [output_number(n) for n in sorted(n for n, c in counts.items() if c == top)][:10]


# G12 to G14: the oracle -------------------------------------------------------


def test_G12_amounts_give_the_metrics_of_a_numeric_field_overall_and_per_marker(tmp_path):
    rows, columns = _data()
    _, _, outcome = _deep(tmp_path, rows, **READ)
    result = _measures(outcome, "price")
    price = columns["price"]
    parsed = len(price.everything())

    assert result.detector == "currency" and result.computed_from == "source"
    assert (result.storage, result.accuracy) == ("table", "exact")
    assert result.values == len(rows)
    assert (result.parsed, result.ambiguous, result.invalid) == (parsed, price.ambiguous, price.invalid)
    assert result.parsed + result.ambiguous + result.invalid + result.unparsed == result.values
    assert result.homogeneous is False
    _expected_level(result.overall, price.everything(), len(rows))
    ranked = sorted(price.numbers, key=lambda marker: (-len(price.numbers[marker]), marker))
    assert [group.marker for group in result.groups] == ranked
    for group in result.groups:
        _expected_level(group, price.numbers[group.marker], len(rows))


def test_G13_markers_are_an_enumeration_with_their_layout(tmp_path):
    rows, columns = _data()
    _, _, outcome = _deep(tmp_path, rows, **READ)
    markers = _measures(outcome, "price").markers
    price = columns["price"]
    total = sum(price.written.values())

    assert markers.kind == "currency"
    assert markers.count == total and markers.distinct == len(price.written)
    assert [(m.value, m.count) for m in markers.listed] == sorted(
        price.written.items(), key=lambda item: (-item[1], item[0])
    )
    assert markers.modes == ["$"]
    assert markers.dominant_share == round(price.written["$"] / total, 4)
    # The pound sign is written in fewer than one value in a hundred.
    assert markers.rare.markers == 1 and markers.rare.count == price.written["£"]
    assert markers.layout.before == price.before
    assert markers.layout.after == total - price.before
    assert markers.layout.spaced == price.spaced
    by_value = {m.value: m for m in markers.listed}
    assert by_value["$"].parsed == by_value["$"].count - price.ambiguous


def test_G14_percentages_outside_0_to_100_are_counted(tmp_path):
    rows, columns = _data()
    _, _, outcome = _deep(tmp_path, rows, **READ)
    result = _measures(outcome, "pct")
    numbers = columns["pct"].everything()

    assert result.detector == "percentage" and result.homogeneous is True
    assert result.percent_range.below == sum(n < 0 for n in numbers)
    assert result.percent_range.above == sum(n > 100 for n in numbers)
    assert result.percent_range.within == sum(0 <= n <= 100 for n in numbers)
    assert result.percent_range.above > 0
    _expected_level(result.overall, numbers, len(rows))
    assert result.markers.kind == "percent" and result.markers.distinct == 1


def test_G15_units_are_groups_and_an_enumeration_without_conversion(tmp_path):
    rows, columns = _data()
    _, _, outcome = _deep(tmp_path, rows, **READ)
    result = _measures(outcome, "size")
    size = columns["size"]

    assert result.detector == "quantity" and result.homogeneous is False
    assert result.markers.kind == "unit"
    assert {m.value: m.count for m in result.markers.listed} == dict(size.written)
    assert result.markers.layout.unspaced == size.written["m²"]
    for group in result.groups:
        _expected_level(group, size.numbers[group.marker], len(rows))
    # Integers of a small range are counted one by one, as by numeric_histogram.
    kinds = {group.marker: group.histogram.kind for group in result.groups}
    assert kinds == {"Go": "dense_counts", "km/h": "dense_counts", "To": "bins", "m²": "dense_counts"}
    assert result.percent_range is None


# G16: the same metrics as a numeric column ----------------------------------------


def test_G16_amounts_have_the_metrics_of_a_numeric_column_of_the_same_numbers(tmp_path):
    rng = random.Random(16)
    numbers = [rng.randint(-50, 400) for _ in range(800)]
    decimals = [f"{rng.randint(0, 999)}.{rng.randint(0, 99):02d}" for _ in range(800)]
    rows = [f"${n},{n},${d},{d}" if n >= 0 else f"(${-n}),{n},${d},{d}" for n, d in zip(numbers, decimals)]
    result = scan_csv(tmp_path, "amount,plain,price,number", rows, **READ)
    outcome = run_second_pass(result, tmp_path / "data.csv", forced_plan(result))
    fields = {f.display: f for f in result.datasets[0].fields}

    amount = _measures(outcome, "amount").overall
    assert amount.numeric == fields["plain"].numeric.value
    assert amount.histogram == entry(outcome, "numeric_histogram", "plain").result
    price = _measures(outcome, "price").overall
    assert price.numeric == fields["number"].numeric.value


# G17 to G19: where the numbers come from, and the grid ------------------------------


def test_G17_the_samples_of_the_scan_give_the_result_of_the_source(tmp_path):
    rows, _ = _data(800)
    _, plan, from_samples = _deep(tmp_path / "samples", rows)
    _, _, from_source = _deep(tmp_path / "source", rows, limits={"max_samples": 50})
    candidate = by_analyzer(plan, "measure_extraction")["price"]

    assert candidate.execution.requires_source is False
    assert "derivable_from_samples" in candidate.utility.reasons
    for display in ("price", "pct", "size"):
        samples = _measures(from_samples, display).model_dump(exclude={"computed_from"})
        source = _measures(from_source, display).model_dump(exclude={"computed_from"})
        assert samples == source
    assert from_samples.read_source is False


def test_G18_beyond_max_values_the_groups_go_on_in_bins_with_exact_counts(tmp_path):
    rows, columns = _data()
    deep = DeepSettings.model_validate({"measures": {"max_values": 200}})
    _, _, exact = _deep(tmp_path / "exact", rows, **READ)
    _, _, gridded = _deep(tmp_path / "grid", rows, deep, **READ)
    table, grid = _measures(exact, "price"), _measures(gridded, "price")

    assert (grid.storage, grid.accuracy) == ("grid", "exact_counts")
    assert grid.overall.distinct is None and grid.overall.modes is None
    assert grid.overall.numeric.median.status == "limited"
    assert grid.overall.numeric.model_dump(exclude={"median"}) == table.overall.numeric.model_dump(
        exclude={"median"}
    )
    assert grid.markers == table.markers
    numbers = columns["price"].everything()
    for quantile, level in zip(grid.overall.histogram.quantiles, LEVELS, strict=True):
        assert quantile.accuracy == "estimated"
        assert quantile.lower <= true_quantile(numbers, level) <= quantile.upper
    histogram = grid.overall.histogram
    assert histogram.bounds_source == "grid" and sum(histogram.counts) == len(numbers)
    assert len(histogram.counts) <= 100


def test_G19_the_grid_does_not_depend_on_the_order_of_the_values(tmp_path):
    rows, _ = _data(1_500)
    deep = DeepSettings.model_validate({"measures": {"max_values": 100}})
    _, _, forward = _deep(tmp_path / "forward", rows, deep, **READ)
    _, _, backward = _deep(tmp_path / "backward", rows[::-1], deep, **READ)

    for display in ("price", "pct", "size"):
        assert _measures(forward, display) == _measures(backward, display)


def test_G19_a_grid_widens_to_the_smallest_width_that_holds_its_range():
    grid = Grid(10)
    for number in (Fraction(3), Fraction(-7, 2), Fraction(1000), Fraction(2)):
        grid.add(number, 1)

    assert grid.exponent == smallest_exponent(Fraction(-7, 2), Fraction(1000), 10)
    assert grid.high - grid.low + 1 <= 10 and sum(grid.counts.values()) == 4


def test_G20_markers_beyond_max_groups_are_summed_up_in_other(tmp_path):
    rows, columns = _data()
    deep = DeepSettings.model_validate({"measures": {"max_groups": 2}})
    _, _, outcome = _deep(tmp_path, rows, deep, **READ)
    result = _measures(outcome, "size")
    size = columns["size"]

    ranked = sorted(size.numbers, key=lambda marker: (-len(size.numbers[marker]), marker))
    assert [group.marker for group in result.groups] == ranked[:2]
    assert result.other.markers == 2
    _expected_level(
        result.other, [n for marker in ranked[2:] for n in size.numbers[marker]], len(rows)
    )


# G21 to G24: one reading, workers, a changed source, reuse ----------------------------


def test_G21_the_extraction_shares_the_one_reading_of_the_other_analyses(tmp_path, monkeypatch):
    rows, _ = _data(600)
    result = scan_csv(tmp_path, HEADER, rows, **READ)
    plan = forced_plan(result)
    opened = []
    from tabalyst.scanner.readers import factory
    from tabalyst.scanner.secondpass import executor

    def counting(path, config, on_bytes):
        opened.append(path)
        return factory.open_reader(path, config, on_bytes)

    monkeypatch.setattr(executor, "open_reader", counting)
    outcome = run_second_pass(result, tmp_path / "data.csv", plan, workers=1)

    analyzers = {a.analyzer for a in outcome.document.analyses}
    assert {"measure_extraction", "pattern_validation"} <= analyzers
    assert len(opened) == 1 and outcome.document.run.records_read == 600


def test_G22_the_workers_give_the_result_of_one_process(tmp_path):
    rows, _ = _data(4_000)
    result = scan_csv(tmp_path, HEADER, rows, **READ)
    plan = forced_plan(result)
    # A route with a set of the shared pool (the values left out of the patterns) stays
    # in the process: this is about the routes of the extractions.
    plan = plan.model_copy(
        update={
            "candidates": [c for c in plan.candidates if c.analyzer != "residual_values"]
        }
    )
    alone = run_second_pass(result, tmp_path / "data.csv", plan, workers=1)
    shared = run_second_pass(result, tmp_path / "data.csv", plan, workers=3)

    assert shared.document.run.workers == 3
    assert [a.model_dump(mode="json") for a in shared.document.analyses] == [
        a.model_dump(mode="json") for a in alone.document.analyses
    ]
    assert part_name(MeasureAccumulator("quantity", max_groups=2, max_values=5, bins=4)) == "measures"


def test_G23_a_source_changed_after_the_scan_publishes_nothing(tmp_path):
    rows, _ = _data(500)
    result = scan_csv(tmp_path, HEADER, rows, **READ)
    plan = forced_plan(result)
    source = tmp_path / "data.csv"
    text = source.read_text(encoding="utf-8")
    # Same size, other content: only the digest of the reading can tell.
    source.write_text(text.replace("Go", "Mo"), encoding="utf-8", newline="")

    with pytest.raises(StaleSource):
        run_second_pass(result, source, plan)


def test_G24_a_change_of_the_measure_settings_computes_only_the_extraction_again(tmp_path):
    rows, _ = _data(600)
    result = scan_csv(tmp_path, HEADER, rows, **READ)
    first = run_second_pass(result, tmp_path / "data.csv", forced_plan(result))
    deep = DeepSettings.model_validate({"measures": {"max_groups": 1}})
    again = run_second_pass(
        result,
        tmp_path / "data.csv",
        forced_plan(result, deep),
        settings=deep,
        previous=first.document,
    )

    assert {i.split(":")[0] for i in again.executed} == {"measure_extraction"}
    assert again.reused and all(not i.startswith("measure") for i in again.reused)
    assert _measures(again, "size").other is not None


# G25 to G27: the planner and the Scan -------------------------------------------------


def test_G25_the_planner_proposes_the_extraction_for_the_fields_it_concerns(tmp_path):
    rows = [f"${n}.50,{n % 7} Go,{'$1' if n < 10 else 'none'},{n}" for n in range(300)]
    result = scan_csv(tmp_path, "money,size,rare,plain", rows)
    plan = plan_analyses(result)
    candidates = by_analyzer(plan, "measure_extraction")

    assert set(candidates) == {"money", "size", "rare"}
    assert candidates["rare"].applicability.reasons == ["low_coverage"]
    money = candidates["money"]
    assert money.parameters == {"detector": "currency", "max_groups": 20, "max_values": 100_000, "bins": 100}
    assert money.selection.state == "selected" and money.selection.reason == "automatic"
    assert plan.cost_model_version >= 7

    hidden = plan_analyses(with_field(result, "money", exposure="mask"))
    assert by_analyzer(hidden, "measure_extraction")["money"].applicability.reasons == [
        "sensitive_exposure"
    ]


def test_G26_counts_that_disagree_with_the_detector_of_the_scan_fail_the_extraction(tmp_path):
    rows, _ = _data(500)
    result = scan_csv(tmp_path, HEADER, rows, **READ)
    column = next(f for f in result.datasets[0].fields if f.display == "price")
    currency = next(d for d in column.detectors if d.id == "currency")
    coverage = currency.coverage

    def edited(**changes) -> object:
        changed = currency.model_copy(update={"coverage": Coverage(**{**coverage.model_dump(), **changes})})
        detectors = [changed if d.id == "currency" else d for d in column.detectors]
        return with_field(result, "price", detectors=detectors)

    wrong_scan = edited(matched=coverage.matched - 1)
    wrong = run_second_pass(wrong_scan, tmp_path / "data.csv", forced_plan(wrong_scan))
    failed = entry(wrong, "measure_extraction", "price")
    assert (failed.status, failed.reason) == ("failed", "scan_mismatch")

    # Values the Scan did not test may add what it did not count, and no more.
    untested = edited(
        matched=coverage.matched - 3, not_matched=coverage.not_matched - 2, not_tested=5
    )
    bounded = run_second_pass(untested, tmp_path / "data.csv", forced_plan(untested))
    assert entry(bounded, "measure_extraction", "price").status == "complete"
    assert _measures(bounded, "price").scan_not_tested == 5


def test_G27_the_document_follows_its_schema_and_the_report_summarises_it(tmp_path):
    rows, _ = _data(400)
    _, _, outcome = _deep(tmp_path, rows, **READ)

    jsonschema.validate(json.loads(deep_document(outcome.document)), deep_schema())
    summary, _ = result_summary(_measures(outcome, "size"))
    assert "4 units" in summary and "Go" in summary
    pct, _ = result_summary(_measures(outcome, "pct"))
    assert "above 100" in pct


def test_G28_the_reading_of_the_second_pass_is_the_classification_of_the_detector():
    from tabalyst.scanner.detectors.currency import CurrencyDetector
    from tabalyst.scanner.detectors.percentage import PercentageDetector
    from tabalyst.scanner.detectors.quantity import QuantityDetector

    rows, _ = _data(2_000)
    values = [cell.strip('"') for row in rows for cell in row.split(",")]
    values += ["(USD 12.50)", "-$3", "+4 %", "12.5.0 km", "1 024 Mo", "€", "%", "10er", "5 EUR"]
    for detector in (CurrencyDetector({}), PercentageDetector({}), QuantityDetector({})):
        for value in values:
            reading = detector.measure(value)
            assert (None if reading is None else reading[0]) == detector.classify(value), value


def test_G29_the_cost_of_an_extraction_follows_the_distinct_values_of_the_field(tmp_path):
    from tabalyst.scanner.planner.analyzers.measures import measure_tier
    from tabalyst.scanner.planner.facts import scan_facts

    rows = [f"${n % 50}.99,${n}.{n % 100:02d}" for n in range(3_000)]
    facts = {f.display: f for f in scan_facts(scan_csv(tmp_path, "few,many", rows))}

    assert measure_tier(facts["few"]) == "measure_few"
    assert measure_tier(facts["many"]) == "measure"
    assert measure_tier(replace(facts["many"], distinct=200_000)) == "measure_wide"


def test_G28_random_strings_get_the_same_reading_as_the_classification():
    from tabalyst.scanner.detectors.currency import CurrencyDetector
    from tabalyst.scanner.detectors.percentage import PercentageDetector
    from tabalyst.scanner.detectors.quantity import QuantityDetector

    rng = random.Random(28)
    alphabet = "0123456789.,  $€£%-+()GokmUSDECA/²°h"
    values = ["".join(rng.choice(alphabet) for _ in range(rng.randint(1, 10))) for _ in range(20_000)]
    for detector in (CurrencyDetector({}), PercentageDetector({}), QuantityDetector({})):
        for value in values:
            reading = detector.measure(value)
            assert (None if reading is None else reading[0]) == detector.classify(value), value


# G30 to G32: JSON values, the grid from the samples, the command -------------------


def test_G30_json_numbers_and_booleans_are_values_without_a_marker(tmp_path):
    lines = []
    for n in range(400):
        price = f"${n}.25" if n % 10 else (n * 1.5 if n % 20 else True)
        lines.append(json.dumps({"id": n, "price": price}))
    source = write_text(tmp_path, "data.jsonl", "\n".join(lines) + "\n")
    from tabalyst.scanner import ScanConfig, scan

    result = scan(source, config=ScanConfig.model_validate(READ))
    outcome = run_second_pass(result, source, forced_plan(result))
    measures = _measures(outcome, "price")

    assert (measures.values, measures.parsed) == (400, 360)
    assert measures.unparsed == 40 and measures.computed_from == "source"
    _expected_level(measures.overall, [Fraction(4 * n + 1, 4) for n in range(400) if n % 10], 400)


def test_G31_the_grid_from_the_samples_is_the_grid_from_the_source(tmp_path):
    rows, _ = _data(800)
    deep = DeepSettings.model_validate({"measures": {"max_values": 60}})
    _, _, from_samples = _deep(tmp_path / "samples", rows, deep)
    _, _, from_source = _deep(tmp_path / "source", rows, deep, **READ)

    for display in ("price", "pct", "size"):
        samples = _measures(from_samples, display)
        assert samples.storage == "grid" and samples.computed_from == "samples"
        assert samples.model_dump(exclude={"computed_from"}) == _measures(
            from_source, display
        ).model_dump(exclude={"computed_from"})


def test_G32_the_command_says_when_the_scan_alone_answers(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from tabalyst.cli import app

    monkeypatch.setenv("TABALYST_HOME", str(tmp_path / "home"))
    rows, _ = _data(300)
    source = write_text(tmp_path, "prices.csv", HEADER + "\n" + "\n".join(rows) + "\n")
    runner = CliRunner()

    first = runner.invoke(app, ["scan", str(source), "--deep", "--yes"])
    again = runner.invoke(app, ["scan", str(source), "--deep", "--yes"])

    assert first.exit_code == 0, first.output
    assert "computed from the scan, the source is not read again" in first.output
    assert "already stored" not in first.output
    assert "every result is already stored" in again.output

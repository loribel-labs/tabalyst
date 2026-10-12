# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Insight lot 17: the shape of the numbers and the parts of the dates (G115 on).

``numeric_shape`` gives the asymmetry, the kurtosis, the outliers of Tukey, the
decimals a number is written with and a logarithmic and an equal-count view of
its spread (design 20.24). The oracles below are built from the numbers the
generator wrote, as exact fractions, never from the accumulators.
"""

from __future__ import annotations

import json
import random
from bisect import bisect_left, bisect_right
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from fractions import Fraction

import jsonschema
import pytest
from planner_helpers import by_analyzer, scan_csv, with_field
from scan_helpers import write_text
from second_pass_helpers import entry, forced_plan, true_quantile

from tabalyst.config import DeepSettings
from tabalyst.report_deep import result_summary
from tabalyst.scanner.measures import output_number
from tabalyst.scanner.planner import plan_analyses
from tabalyst.scanner.secondpass import deep_document, run_second_pass
from tabalyst.scanner.secondpass.parallel import part_name
from tabalyst.scanner.secondpass.parts import PartsAccumulator
from tabalyst.scanner.secondpass.schema import deep_schema
from tabalyst.scanner.secondpass.shape import ShapeAccumulator, centered, merge_moments
from tabalyst.source_guard import StaleSource

# Few samples: the Scan does not hold every distinct value, so nothing is
# answered from them and the source is read.
READ = {"limits": {"max_samples": 50}}
Q1, MEDIAN, Q3 = Fraction(1, 4), Fraction(1, 2), Fraction(3, 4)


def _numbers(count: int = 3_000, seed: int = 17) -> dict[str, list[str]]:
    """Columns as written: skewed integers, decimals with a varying precision,
    and a signed column."""
    rng = random.Random(seed)
    skewed = [str(int(rng.lognormvariate(3, 1.1)) + 1) for _ in range(count)]
    decimals = []
    for _ in range(count):
        value = rng.lognormvariate(4, 1)
        decimals.append(f"{value:.{rng.choice((1, 2, 2, 2, 3))}f}")
    signed = [f"{rng.gauss(0, 50):.2f}" for _ in range(count)]
    return {"count": skewed, "price": decimals, "delta": signed}


def _rows(columns: dict[str, list[str]]) -> list[str]:
    return [",".join(values) for values in zip(*columns.values(), strict=True)]


def _deep(tmp_path, columns, deep: DeepSettings | None = None, **settings):
    tmp_path.mkdir(parents=True, exist_ok=True)
    result = scan_csv(tmp_path, ",".join(columns), _rows(columns), **{**READ, **settings})
    plan = forced_plan(result, deep)
    outcome = run_second_pass(result, tmp_path / "data.csv", plan, settings=deep)
    return result, plan, outcome


def _shape(outcome, display: str):
    found = entry(outcome, "numeric_shape", display)
    assert found.status == "complete", (found.reason, found.detail)
    return found.result


def _moments(numbers: list[Fraction]) -> tuple[float, float]:
    """The skewness and the excess kurtosis of exact numbers."""
    n = len(numbers)
    mean = sum(numbers, Fraction(0)) / n
    m2 = sum((x - mean) ** 2 for x in numbers) / n
    m3 = sum((x - mean) ** 3 for x in numbers) / n
    m4 = sum((x - mean) ** 4 for x in numbers) / n
    return float(m3) / float(m2) ** 1.5, float(m4) / float(m2) ** 2 - 3


def _outside(numbers: list[Fraction], factor: Fraction) -> tuple[int, int]:
    ordered = sorted(numbers)
    q1, q3 = true_quantile(numbers, Q1), true_quantile(numbers, Q3)
    low, high = q1 - factor * (q3 - q1), q3 + factor * (q3 - q1)
    return bisect_left(ordered, low), len(ordered) - bisect_right(ordered, high)


def _counted(numbers: list[Fraction], histogram, *, decimal: bool = False) -> list[int]:
    """The numbers per bin of a histogram, by its written edges. The outer edges
    are the minimum and maximum as the Scan wrote them (a float64), so a number
    that rounds past one is kept in the first or the last bin."""
    # The edges of quantiles of decimals are those decimals, written as floats.
    edges = [Fraction(str(edge) if decimal else edge) for edge in histogram.edges]
    counts = [0] * (len(edges) - 1)
    for number in numbers:
        index = max(0, min(bisect_right(edges, number) - 1, len(counts) - 1))
        counts[index] += 1
    return counts


# G115 to G120: the oracle -------------------------------------------------------


@pytest.mark.parametrize("display", ["count", "price", "delta"])
def test_G115_the_moments_and_the_outliers_match_an_oracle_of_exact_fractions(tmp_path, display):
    columns = _numbers()
    _, _, outcome = _deep(tmp_path, columns)
    result = _shape(outcome, display)
    numbers = [Fraction(text) for text in columns[display]]
    skewness, kurtosis = _moments(numbers)

    assert (result.storage, result.accuracy) == ("table", "exact")
    assert result.count == len(numbers) and result.distinct == len(set(numbers))
    assert result.moments.precision == "float64"
    assert result.moments.skewness == pytest.approx(skewness, abs=2e-6)
    assert result.moments.excess_kurtosis == pytest.approx(kurtosis, abs=2e-6)
    tukey = result.tukey
    assert tukey.accuracy == "exact"
    assert tukey.q1.value == output_number(true_quantile(numbers, Q1))
    assert tukey.q3.value == output_number(true_quantile(numbers, Q3))
    assert tukey.iqr == output_number(true_quantile(numbers, Q3) - true_quantile(numbers, Q1))
    for fence in tukey.fences:
        below, above = _outside(numbers, Fraction(fence.factor))
        assert (fence.below.certain, fence.below.possible) == (below, below)
        assert (fence.above.certain, fence.above.possible) == (above, above)
    assert [f.factor for f in tukey.fences] == [1.5, 3.0]


def test_G116_the_skewed_column_has_outliers_above_and_a_positive_skewness(tmp_path):
    _, _, outcome = _deep(tmp_path, _numbers())
    price = _shape(outcome, "price")

    assert price.moments.skewness > 1 and price.moments.excess_kurtosis > 1
    mild, far = price.tukey.fences
    assert mild.above.certain > far.above.certain > 0
    assert mild.below.certain == 0


def test_G117_the_decimals_are_the_places_the_numbers_are_written_with(tmp_path):
    columns = _numbers()
    _, _, outcome = _deep(tmp_path, columns)
    scale = _shape(outcome, "price").scale
    written = columns["price"]
    places = Counter(len(text.split(".")[1]) for text in written)
    trailing = sum(text.endswith("0") for text in written)

    assert {p.places: p.count for p in scale.places} == dict(places)
    assert [p.places for p in scale.places] == sorted(places)
    assert scale.max_places == max(places) and scale.trailing_zero == trailing
    assert scale.mixed is True and trailing > 0
    integers = _shape(outcome, "count").scale
    assert [(p.places, p.count) for p in integers.places] == [(0, len(written))]
    assert integers.mixed is False and integers.trailing_zero == 0


def test_G118_the_log_view_counts_the_numbers_by_ratio_and_equal_count_by_quantile(tmp_path):
    columns = _numbers()
    _, _, outcome = _deep(tmp_path, columns)
    result = _shape(outcome, "price")
    numbers = [Fraction(text) for text in columns["price"]]

    log, equal = result.log, result.equal_count
    assert log.strategy == "log" and log.requested_strategy == "log" and log.bounds_source == "range"
    assert log.counts == _counted(numbers, log) and sum(log.counts) == len(numbers)
    ratios = [b / a for a, b in zip(log.edges[1:-2], log.edges[2:-1], strict=True)]
    assert max(ratios) == pytest.approx(min(ratios), rel=1e-9)
    assert equal.strategy == "sample_quantile" and equal.requested_strategy == "sample_quantile"
    assert equal.counts == _counted(numbers, equal, decimal=True) and sum(equal.counts) == len(numbers)
    # Bins of the quantiles of the samples are more even than bins of equal width.
    assert max(equal.counts) < 0.2 * len(numbers)
    assert result.log_reason is None


def test_G119_a_column_with_zero_or_negative_numbers_has_no_log_view(tmp_path):
    _, _, outcome = _deep(tmp_path, _numbers())
    delta = _shape(outcome, "delta")

    assert delta.log is None and delta.log_reason == "non_positive"
    assert delta.equal_count.counts and delta.moments.skewness is not None
    assert delta.tukey.fences[0].below.certain > 0 and delta.tukey.fences[0].above.certain > 0


def test_G120_integers_and_decimals_written_as_integers_are_a_scale_of_zero_places(tmp_path):
    columns = {"v": ["1", "2", "3", "4", "50", "6", "7", "8", "9", "10"] * 30}
    _, _, outcome = _deep(tmp_path, columns)
    result = _shape(outcome, "v")

    assert result.tukey.q1.value == 3 and result.tukey.q3.value == 9
    assert result.tukey.fences[0].above.certain == 30
    assert result.scale.max_places == 0 and result.distinct == 10


# G121 to G124: the grid ----------------------------------------------------------


def test_G121_beyond_max_values_the_numbers_go_on_in_bins_with_bracketed_outliers(tmp_path):
    columns = _numbers()
    deep = DeepSettings.model_validate({"shape": {"max_values": 100}})
    _, _, exact = _deep(tmp_path / "exact", columns)
    _, _, gridded = _deep(tmp_path / "grid", columns, deep)

    for display in ("count", "price", "delta"):
        table, grid = _shape(exact, display), _shape(gridded, display)
        numbers = [Fraction(text) for text in columns[display]]
        if len(set(numbers)) <= 100:
            assert grid.storage == "table"
            continue
        assert (grid.storage, grid.accuracy, grid.tukey.accuracy) == ("grid", "exact_counts", "bounds")
        assert grid.distinct is None
        # What the extremes, the views and the decimals count does not depend on the storage.
        assert grid.scale == table.scale and grid.log == table.log
        assert grid.equal_count == table.equal_count
        assert grid.moments.skewness == pytest.approx(table.moments.skewness, abs=1e-6)
        assert grid.moments.excess_kurtosis == pytest.approx(table.moments.excess_kurtosis, abs=1e-6)
        for quantile, truth in ((grid.tukey.q1, Q1), (grid.tukey.q3, Q3)):
            assert quantile.accuracy == "estimated"
            assert quantile.lower <= true_quantile(numbers, truth) <= quantile.upper
        for fence in grid.tukey.fences:
            below, above = _outside(numbers, Fraction(fence.factor))
            assert fence.below.certain <= below <= fence.below.possible
            assert fence.above.certain <= above <= fence.above.possible


def test_G122_the_grid_does_not_depend_on_the_order_of_the_values(tmp_path):
    columns = _numbers(1_500)
    deep = DeepSettings.model_validate({"shape": {"max_values": 50}})
    reversed_columns = {name: values[::-1] for name, values in columns.items()}
    _, _, forward = _deep(tmp_path / "forward", columns, deep)
    _, _, backward = _deep(tmp_path / "backward", reversed_columns, deep)

    for display in columns:
        one, other = _shape(forward, display), _shape(backward, display)
        # The edges of the equal-count view come from the samples of the Scan,
        # which depend on the order of the rows; the rest does not.
        skipped = {"moments", "equal_count"}
        assert one.model_dump(exclude=skipped) == other.model_dump(exclude=skipped)
        assert one.moments.skewness == pytest.approx(other.moments.skewness, abs=1e-6)


def test_G123_the_float_moments_merge_like_the_moments_of_the_whole():
    rng = random.Random(123)
    values = [(rng.lognormvariate(2, 1), rng.randint(1, 5)) for _ in range(500)]
    whole = centered(values)
    merged = merge_moments(centered(values[:137]), centered(values[137:]))
    for a, b in zip(whole, merged, strict=True):
        assert a == pytest.approx(b, rel=1e-9)
    assert merge_moments((0.0,) * 5, whole) == whole and merge_moments(whole, (0.0,) * 5) == whole


# G124 to G129: one reading, workers, a changed source, reuse ---------------------


def test_G124_the_shape_shares_the_one_reading_of_the_other_analyses(tmp_path, monkeypatch):
    columns = _numbers(600)
    result = scan_csv(tmp_path, ",".join(columns), _rows(columns), **READ)
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
    assert {"numeric_shape", "numeric_histogram"} <= analyzers
    assert len(opened) == 1 and outcome.document.run.records_read == 600
    # Each cell is read once whatever the number of analyses of its column.
    assert outcome.document.run.cells_read == 600 * 3


def test_G125_the_workers_give_the_result_of_one_process(tmp_path):
    columns = _numbers(4_000)
    result = scan_csv(tmp_path, ",".join(columns), _rows(columns), **READ)
    plan = forced_plan(result)
    plan = plan.model_copy(
        update={"candidates": [c for c in plan.candidates if c.analyzer != "residual_values"]}
    )
    alone = run_second_pass(result, tmp_path / "data.csv", plan, workers=1)
    shared = run_second_pass(result, tmp_path / "data.csv", plan, workers=3)

    assert shared.document.run.workers == 3
    assert [a.model_dump(mode="json") for a in shared.document.analyses] == [
        a.model_dump(mode="json") for a in alone.document.analyses
    ]
    assert part_name(ShapeAccumulator(None, None, None, max_values=5, bins=4)) == "shape"  # type: ignore[arg-type]


def test_G126_a_source_changed_after_the_scan_publishes_nothing(tmp_path):
    columns = _numbers(500)
    result = scan_csv(tmp_path, ",".join(columns), _rows(columns), **READ)
    plan = forced_plan(result)
    source = tmp_path / "data.csv"
    text = source.read_text(encoding="utf-8")
    first = text.splitlines()[1]
    changed = first.replace(first[0], "9" if first[0] != "9" else "8", 1)
    source.write_text(text.replace(first, changed, 1), encoding="utf-8", newline="")

    with pytest.raises(StaleSource):
        run_second_pass(result, source, plan)


def test_G127_a_change_of_the_shape_settings_computes_only_the_shape_again(tmp_path):
    columns = _numbers(600)
    result = scan_csv(tmp_path, ",".join(columns), _rows(columns), **READ)
    first = run_second_pass(result, tmp_path / "data.csv", forced_plan(result))
    deep = DeepSettings.model_validate({"shape": {"max_values": 60}})
    again = run_second_pass(
        result,
        tmp_path / "data.csv",
        forced_plan(result, deep),
        settings=deep,
        previous=first.document,
    )

    assert {i.split(":")[0] for i in again.executed} == {"numeric_shape"}
    assert again.reused and all(not i.startswith("numeric_shape") for i in again.reused)
    assert _shape(again, "price").storage == "grid"


# G128 to G131: the planner, the Scan, the document -----------------------------------


def test_G128_the_planner_proposes_the_shape_but_leaves_it_to_a_request(tmp_path):
    columns = _numbers(300)
    columns["name"] = [f"n{i}" for i in range(300)]
    columns["flat"] = ["5"] * 300
    result = scan_csv(tmp_path, ",".join(columns), _rows(columns))
    plan = plan_analyses(result)
    candidates = by_analyzer(plan, "numeric_shape")

    assert set(candidates) == {"count", "price", "delta", "flat"}
    price = candidates["price"]
    assert price.parameters == {"max_values": 100_000, "bins": 100}
    assert price.utility.score == 40 and price.utility.reasons == ["numeric_shape"]
    assert price.selection.state == "rejected" and price.selection.reason == "low_utility"
    assert candidates["flat"].selection.state == "already_satisfied"
    assert plan.cost_model_version >= 11
    forced = by_analyzer(forced_plan(result), "numeric_shape")
    assert forced["price"].selection.state == "selected"

    hidden = plan_analyses(with_field(result, "price", exposure="mask"))
    assert by_analyzer(hidden, "numeric_shape")["price"].applicability.reasons == [
        "sensitive_exposure"
    ]


def test_G129_the_cost_of_a_shape_follows_the_distinct_values_of_the_field(tmp_path):
    from dataclasses import replace

    from tabalyst.scanner.planner.analyzers.shape import shape_tier
    from tabalyst.scanner.planner.facts import scan_facts

    rows = [f"{n % 50},{n}.{n % 100:02d}" for n in range(3_000)]
    facts = {f.display: f for f in scan_facts(scan_csv(tmp_path, "few,many", rows))}

    assert shape_tier(facts["few"]) == "shape_few"
    assert shape_tier(facts["many"]) == "shape"
    assert shape_tier(replace(facts["many"], distinct=200_000)) == "shape_wide"


def test_G130_a_count_that_disagrees_with_the_scan_fails_the_shape(tmp_path):
    columns = _numbers(500)
    result = scan_csv(tmp_path, ",".join(columns), _rows(columns), **READ)
    column = next(f for f in result.datasets[0].fields if f.display == "price")
    numeric = column.numeric.model_copy(
        update={"value": column.numeric.value.model_copy(update={"count": column.numeric.value.count - 1})}
    )
    wrong = with_field(result, "price", numeric=numeric)
    outcome = run_second_pass(wrong, tmp_path / "data.csv", forced_plan(wrong))
    failed = entry(outcome, "numeric_shape", "price")

    assert (failed.status, failed.reason) == ("failed", "scan_mismatch")
    assert entry(outcome, "numeric_shape", "count").status == "complete"


def test_G131_the_document_follows_its_schema_and_the_report_summarises_it(tmp_path):
    _, _, outcome = _deep(tmp_path, _numbers(400))

    jsonschema.validate(json.loads(deep_document(outcome.document)), deep_schema())
    summary, _ = result_summary(_shape(outcome, "price"))
    assert "skewness" in summary and "outliers" in summary


def test_G132_json_numbers_are_read_like_the_text_numbers(tmp_path):
    lines = [json.dumps({"id": n, "x": n * 1.5 if n % 3 else n}) for n in range(1, 301)]
    source = write_text(tmp_path, "data.jsonl", "\n".join(lines) + "\n")
    from tabalyst.scanner import ScanConfig, scan

    result = scan(source, config=ScanConfig.model_validate(READ))
    outcome = run_second_pass(result, source, forced_plan(result))
    shape = _shape(outcome, "x")
    numbers = [Fraction(n * 3, 2) if n % 3 else Fraction(n) for n in range(1, 301)]

    assert shape.count == 300 and shape.distinct == len(set(numbers))
    assert shape.tukey.q1.value == output_number(true_quantile(numbers, Q1))
    assert {p.places: p.count for p in shape.scale.places} == {0: 100, 1: 200}


# Lot 17b: the parts of the dates (G133 on) ----------------------------------------------


@dataclass
class Dates:
    """What the generator wrote in the date columns."""

    day: list[date] = field(default_factory=list)
    invalid: Counter = field(default_factory=Counter)
    unplaced: int = 0
    stamps: list[datetime] = field(default_factory=list)
    european: list[tuple[int, int, int]] = field(default_factory=list)
    # Dates written month-day with a day above 12: they prove the other order.
    american: list[tuple[int, int, int]] = field(default_factory=list)
    clocks: list[time] = field(default_factory=list)


def _dates(count: int = 1_500, seed: int = 133) -> tuple[dict[str, list[str]], Dates]:
    rng = random.Random(seed)
    written = Dates()
    columns: dict[str, list[str]] = {"day": [], "stamp": [], "eu": [], "clock": []}
    start = date(2022, 3, 1).toordinal()
    for _ in range(count):
        kind = rng.random()
        if kind < 0.025:
            columns["day"].append(f"{rng.choice((2023, 2024))}-02-30")
            written.invalid["invalid_calendar_date"] += 1
        elif kind < 0.035:
            columns["day"].append("2024-05/06")
            written.invalid["mixed_separators"] += 1
        elif kind < 0.045:
            columns["day"].append("n/a")
            written.unplaced += 1
        else:
            day = date.fromordinal(start + rng.randint(0, 851))
            columns["day"].append(day.isoformat())
            written.day.append(day)
        offset = rng.choice((0, 2, -5))
        moment = datetime(
            2024,
            rng.randint(1, 12),
            rng.randint(1, 28),
            rng.randint(0, 23),
            rng.randint(0, 59),
            tzinfo=timezone(timedelta(hours=offset)),
        )
        columns["stamp"].append(moment.isoformat())
        written.stamps.append(moment)
        d, m, y = rng.randint(1, 28), rng.randint(1, 12), rng.choice((2023, 2024))
        if rng.random() < 0.03:
            d = rng.randint(13, 28)
            columns["eu"].append(f"{m:02d}/{d:02d}/{y}")
            written.american.append((d, m, y))
        else:
            columns["eu"].append(f"{d:02d}/{m:02d}/{y}")
            written.european.append((d, m, y))
        clock = time(rng.randint(0, 23), rng.randint(0, 59), 0)
        columns["clock"].append(clock.isoformat())
        written.clocks.append(clock)
    return columns, written


def _parts(outcome, display: str):
    found = entry(outcome, "datetime_parts", display)
    assert found.status == "complete", (found.reason, found.detail)
    return found.result


def _as_counts(parts) -> dict[int, int]:
    return {part.value: part.count for part in parts}


def _by_month(days) -> dict[str, int]:
    return dict(Counter(f"{d.year:04d}-{d.month:02d}" for d in days))


def _as_months(parts) -> dict[str, int]:
    return {part.period: part.count for part in parts}


def test_G133_the_parts_of_the_dates_match_an_oracle(tmp_path):
    columns, written = _dates()
    deep = DeepSettings.model_validate({"datetime": {"as_of": "2023-06-30"}})
    _, _, outcome = _deep(tmp_path, columns, deep)
    result = _parts(outcome, "day")
    days = written.day

    assert result.temporal_kind == "date" and result.zone == "as_written"
    assert result.count == len(days) and result.ambiguous == 0
    assert result.count + result.invalid + result.unplaced == result.values == 1_500
    assert result.invalid == sum(written.invalid.values()) and result.unplaced == written.unplaced
    assert _as_months(result.year_months) == _by_month(days)
    periods = [part.period for part in result.year_months]
    assert periods == sorted(periods) and len(periods) == len(set(periods))
    assert _as_counts(result.weekdays) == {w: sum(d.weekday() == w for d in days) for w in range(7)}
    assert len(result.weekdays) == 7 and result.hours is None
    assert (result.as_of, result.after_as_of) == ("2023-06-30", sum(d > date(2023, 6, 30) for d in days))
    assert result.simulation is None
    # The years and the months of the year are sums of the year-months.
    by_year = Counter()
    for part in result.year_months:
        by_year[int(part.period[:4])] += part.count
    assert dict(by_year) == dict(Counter(d.year for d in days))


def test_G134_the_hours_and_days_are_those_written_without_converting_the_offset(tmp_path):
    columns, written = _dates()
    _, _, outcome = _deep(tmp_path, columns)
    result = _parts(outcome, "stamp")
    stamps = written.stamps

    assert result.temporal_kind == "datetime_aware"
    assert _as_counts(result.hours) == dict(Counter(s.hour for s in stamps))
    assert _as_counts(result.weekdays) == {w: sum(s.weekday() == w for s in stamps) for w in range(7)}
    assert _as_months(result.year_months) == _by_month(stamps)
    assert result.as_of is None and result.after_as_of is None


def test_G135_the_year_months_are_the_months_that_occur_whatever_the_span(tmp_path):
    columns = {
        "day": ["1999-12-31", "2000-01-01", "2000-01-31", "2024-02-29", "2024-02-01"] * 20
    }
    _, _, outcome = _deep(tmp_path, columns)
    result = _parts(outcome, "day")

    assert _as_months(result.year_months) == {"1999-12": 20, "2000-01": 40, "2024-02": 40}
    assert [p.period for p in result.year_months] == ["1999-12", "2000-01", "2024-02"]


def test_G136_a_short_span_is_a_single_year_month(tmp_path):
    columns = {"day": [(date(2024, 1, 1) + timedelta(days=n % 30)).isoformat() for n in range(400)]}
    _, _, outcome = _deep(tmp_path, columns)

    assert _as_months(_parts(outcome, "day").year_months) == {"2024-01": 400}


def test_G137_the_ambiguous_dates_are_read_under_each_order_and_never_placed(tmp_path):
    columns, written = _dates()
    deep = DeepSettings.model_validate({"datetime": {"as_of": "2023-12-31"}})
    _, _, outcome = _deep(tmp_path, columns, deep)
    result = _parts(outcome, "eu")
    # 05/05 is ambiguous too: the detector sees two formats, not two different dates.
    ambiguous = [(d, m, y) for d, m, y in written.european if d <= 12]
    sure = [(d, m, y) for d, m, y in written.european if d > 12] + written.american

    assert result.ambiguous == len(ambiguous) and result.count == len(sure)
    assert _as_months(result.year_months) == dict(Counter(f"{y:04d}-{m:02d}" for _, m, y in sure))
    readings = {r.order: r for r in result.simulation.readings}
    assert result.simulation.ambiguous == len(ambiguous) and set(readings) == {"DMY", "MDY"}
    # In day-month order the month is the second number, in month-day order the first.
    assert _as_months(readings["DMY"].year_months) == dict(
        Counter(f"{y:04d}-{m:02d}" for _, m, y in ambiguous)
    )
    assert _as_months(readings["MDY"].year_months) == dict(
        Counter(f"{y:04d}-{d:02d}" for d, _, y in ambiguous)
    )
    assert readings["DMY"].placed == readings["MDY"].placed == len(ambiguous)
    assert _as_counts(readings["MDY"].weekdays) == {
        w: sum(1 for d, m, y in ambiguous if date(y, d, m).weekday() == w) for w in range(7)
    }
    assert readings["DMY"].after_as_of == sum(1 for _, _, y in ambiguous if y > 2023)


def test_G138_an_order_given_by_the_configuration_leaves_nothing_to_simulate(tmp_path):
    columns, written = _dates()
    _, _, outcome = _deep(tmp_path, columns, detectors={"date": {"ambiguous_order": "DMY"}})
    result = _parts(outcome, "eu")

    assert result.ambiguous == 0 and result.simulation is None
    assert result.count == len(written.european) + len(written.american)


def test_G139_the_invalid_dates_are_counted_by_reason(tmp_path):
    columns, written = _dates()
    _, _, outcome = _deep(tmp_path, columns)
    result = _parts(outcome, "day")

    assert {r.reason: r.count for r in result.invalid_reasons} == dict(written.invalid)
    assert [r.reason for r in result.invalid_reasons] == sorted(
        written.invalid, key=lambda r: (-written.invalid[r], r)
    )


def test_G140_a_column_of_times_has_hours_only(tmp_path):
    columns, written = _dates()
    _, _, outcome = _deep(tmp_path, columns)
    result = _parts(outcome, "clock")

    assert result.temporal_kind == "time"
    assert _as_counts(result.hours) == dict(Counter(c.hour for c in written.clocks))
    assert result.year_months is None and result.weekdays is None


def test_G141_the_parts_share_the_one_reading_of_the_distribution_over_time(tmp_path, monkeypatch):
    columns, _ = _dates(600)
    result = scan_csv(tmp_path, ",".join(columns), _rows(columns), **READ)
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
    assert {"datetime_parts", "temporal_distribution"} <= analyzers
    assert len(opened) == 1 and outcome.document.run.records_read == 600
    assert outcome.document.run.cells_read == 600 * 4


def test_G142_the_workers_give_the_result_of_one_process(tmp_path):
    columns, _ = _dates(3_000)
    result = scan_csv(tmp_path, ",".join(columns), _rows(columns), **READ)
    plan = forced_plan(result)
    plan = plan.model_copy(
        update={"candidates": [c for c in plan.candidates if c.analyzer != "residual_values"]}
    )
    alone = run_second_pass(result, tmp_path / "data.csv", plan, workers=1)
    shared = run_second_pass(result, tmp_path / "data.csv", plan, workers=3)

    assert [a.model_dump(mode="json") for a in shared.document.analyses] == [
        a.model_dump(mode="json") for a in alone.document.analyses
    ]
    sample = PartsAccumulator("date", {}, as_of=None)
    assert part_name(sample) == "parts"


def test_G143_a_change_of_the_bound_computes_only_the_parts_again(tmp_path):
    columns, _ = _dates(600)
    result = scan_csv(tmp_path, ",".join(columns), _rows(columns), **READ)
    first = run_second_pass(result, tmp_path / "data.csv", forced_plan(result))
    deep = DeepSettings.model_validate({"datetime": {"as_of": "2024-01-01"}})
    again = run_second_pass(
        result,
        tmp_path / "data.csv",
        forced_plan(result, deep),
        settings=deep,
        previous=first.document,
    )

    assert {i.split(":")[0] for i in again.executed} == {"datetime_parts"}
    assert again.reused and all(not i.startswith("datetime_parts") for i in again.reused)
    assert _parts(again, "day").as_of == "2024-01-01"


def test_G144_the_planner_proposes_the_parts_but_leaves_them_to_a_request(tmp_path):
    columns, _ = _dates(300)
    columns["name"] = [f"n{i}" for i in range(300)]
    result = scan_csv(tmp_path, ",".join(columns), _rows(columns))
    plan = plan_analyses(result)
    candidates = by_analyzer(plan, "datetime_parts")

    assert set(candidates) == {"day", "stamp", "eu", "clock"}
    day = candidates["day"]
    assert day.parameters == {"as_of": "", "date_order": ""}
    assert day.utility.score == 40 and day.selection.reason == "low_utility"
    assert by_analyzer(forced_plan(result), "datetime_parts")["day"].selection.state == "selected"
    hidden = plan_analyses(with_field(result, "day", exposure="mask"))
    assert by_analyzer(hidden, "datetime_parts")["day"].applicability.reasons == [
        "sensitive_exposure"
    ]


def test_G145_a_count_that_disagrees_with_the_scan_fails_the_parts(tmp_path):
    columns, _ = _dates(500)
    result = scan_csv(tmp_path, ",".join(columns), _rows(columns), **READ)
    column = next(f for f in result.datasets[0].fields if f.display == "stamp")
    stats = column.temporal.value
    kinds = [stats.kinds[0].model_copy(update={"count": stats.kinds[0].count - 1})]
    temporal = column.temporal.model_copy(
        update={"value": stats.model_copy(update={"kinds": kinds})}
    )
    wrong = with_field(result, "stamp", temporal=temporal)
    outcome = run_second_pass(wrong, tmp_path / "data.csv", forced_plan(wrong))

    failed = entry(outcome, "datetime_parts", "stamp")
    assert (failed.status, failed.reason) == ("failed", "scan_mismatch")
    assert entry(outcome, "datetime_parts", "day").status == "complete"


def test_G146_the_document_follows_its_schema_and_the_report_summarises_it(tmp_path):
    columns, _ = _dates(400)
    deep = DeepSettings.model_validate({"datetime": {"as_of": "2023-01-01"}})
    _, _, outcome = _deep(tmp_path, columns, deep)

    jsonschema.validate(json.loads(deep_document(outcome.document)), deep_schema())
    summary, _ = result_summary(_parts(outcome, "eu"))
    assert "busiest weekday" in summary and "ambiguous read under 2 orders" in summary
    after, _ = result_summary(_parts(outcome, "day"))
    assert "after 2023-01-01" in after and "invalid" in after
    clocks, _ = result_summary(_parts(outcome, "clock"))
    assert "busiest hour" in clocks


def test_G147_the_bound_must_be_a_calendar_date():
    deep = DeepSettings.model_validate({"datetime": {"as_of": "2024-02-29"}})
    assert deep.datetime.as_of == "2024-02-29"
    for wrong in ("2023-02-29", "yesterday", "2024-1-5x"):
        with pytest.raises(ValueError, match="calendar date"):
            DeepSettings.model_validate({"datetime": {"as_of": wrong}})


# Corrections found by the review of the lot ------------------------------------------------


def test_G149_aware_datetimes_with_any_offset_are_placed_by_the_day_they_are_written(tmp_path):
    # The Scan orders aware datetimes as instants; the parts count the written days.
    values = [
        "2024-03-11T23:30:00-05:00",
        "2024-03-12T01:00:00+14:00",
        "2024-03-11T12:00:00+00:00",
        "2024-03-10T00:30:00+10:00",
        "2024-04-01T10:00:00-10:00",
    ] * 20
    _, _, outcome = _deep(tmp_path, {"at": values})
    result = _parts(outcome, "at")

    assert result.temporal_kind == "datetime_aware" and result.count == 100
    assert _as_months(result.year_months) == {"2024-03": 80, "2024-04": 20}
    assert _as_counts(result.hours) == {23: 20, 1: 20, 12: 20, 0: 20, 10: 20}


def test_G150_numbers_beyond_float64_have_no_moments_and_say_so():
    from decimal import Decimal

    from tabalyst.scanner.secondpass.accumulators import BinAccumulator
    from tabalyst.scanner.secondpass.bins import BinEdges

    equal = BinAccumulator(
        BinEdges([Fraction(0), Fraction(1)]),
        strategy="linear",
        requested="linear",
        source="range",
        reason=None,
        tight=False,
    )
    accumulator = ShapeAccumulator(None, None, equal, max_values=100, bins=4)
    for number in (Decimal("1E+400"), Decimal("2E+400"), Decimal("3E+400"), Decimal(5)):
        accumulator.add(number, 10)

    moments = accumulator._moments(centered(accumulator._table_floats()))
    assert moments.reason == "not_representable" and moments.skewness is None


def test_G151_the_empty_periods_follow_from_the_distribution_over_time():
    from tabalyst.report_measures import empty_periods

    days = empty_periods("day", ["2024-01-01", "2024-01-02", "2024-01-06", "2024-01-08"])
    assert (days.periods, days.empty, days.longest) == (8, 4, 3)
    assert (days.longest_from, days.longest_to) == ("2024-01-03", "2024-01-05")
    months = empty_periods("month", ["2023-11", "2024-02", "2024-03"])
    assert (months.periods, months.empty, months.longest) == (5, 2, 2)
    assert (months.longest_from, months.longest_to) == ("2023-12", "2024-01")
    years = empty_periods("year", ["1990", "1991", "1992"])
    assert (years.empty, years.longest, years.longest_from) == (0, 0, None)
    assert empty_periods("year", ["2000"]) is None


# The order the unambiguous dates of a column give the ambiguous ones ---------------------


def test_G152_a_column_of_only_ambiguous_dates_stays_ambiguous(tmp_path):
    from tabalyst.scanner.planner.facts import inferred_order

    values = [f"{d:02d}-{m:02d}-2020" for d in (1, 3, 5) for m in (2, 4, 6)] * 10
    result = scan_csv(tmp_path, "d", values)
    field = result.datasets[0].fields[0]

    # Nothing proves an order: the Scan counts them as ambiguous and there is no date to analyze.
    assert field.temporal.value.ambiguous == 90 and field.temporal.value.kinds == []
    assert inferred_order(field) is None
    candidate = by_analyzer(plan_analyses(result), "datetime_parts")["d"]
    assert candidate.applicability.reasons == ["measure_unavailable"]


def test_G153_dates_read_day_first_by_the_evidence_are_counted_with_the_others(tmp_path):
    # Day-month dates above 12 prove the order, in any separator, and year-first dates
    # next to them change nothing.
    rng = random.Random(153)
    values = ["25-03-2020", "14/07/2021", "31.12.2020", "2021-02-13", "2020-05-06"] * 4
    values += ["03-04-2020", "05/06/2021", "01.02.2020", "11-12-2021"] * 25
    rng.shuffle(values)
    _, _, outcome = _deep(tmp_path, {"d": values})
    parts = _parts(outcome, "d")
    days = {
        "25-03-2020": date(2020, 3, 25), "14/07/2021": date(2021, 7, 14),
        "31.12.2020": date(2020, 12, 31), "2021-02-13": date(2021, 2, 13),
        "2020-05-06": date(2020, 5, 6), "03-04-2020": date(2020, 4, 3),
        "05/06/2021": date(2021, 6, 5), "01.02.2020": date(2020, 2, 1),
        "11-12-2021": date(2021, 12, 11),
    }
    placed = [days[v] for v in values]

    assert parts.ambiguous == 0 and parts.simulation is None
    assert parts.count == len(values) and parts.invalid == 0
    # Of the count, the ambiguous dates that are valid now.
    assert parts.resolved == 100 and parts.count - parts.resolved == 20
    assert (parts.resolution.order, parts.resolution.source, parts.resolved) == ("DMY", "evidence", 100)
    assert parts.resolution.evidence == {"DMY": 12, "MDY": 0}
    assert _as_months(parts.year_months) == _by_month(placed)
    assert _as_counts(parts.weekdays) == {w: sum(d.weekday() == w for d in placed) for w in range(7)}
    # The distribution over time counts them too, and the Scan alone could not answer.
    periods = entry(outcome, "temporal_distribution", "d").result
    assert periods.ambiguous == 0 and periods.count == len(values)
    assert (periods.resolution.order, periods.resolved) == ("DMY", 100)
    assert sum(p.count for p in periods.periods) == len(values)


def test_G154_dates_read_month_first_by_the_evidence_whatever_the_separators(tmp_path):
    values = ["03-25-2020", "07/14/2021", "12.31.2020"] * 5 + ["03-04-2020", "05/06/2021", "01.02.2020"] * 20
    _, _, outcome = _deep(tmp_path, {"d": values})
    parts = _parts(outcome, "d")

    assert parts.resolution.order == "MDY" and parts.resolution.evidence == {"DMY": 0, "MDY": 15}
    assert parts.ambiguous == 0 and parts.count == len(values)
    months = _as_months(parts.year_months)
    assert months == {"2020-03": 25, "2021-07": 5, "2020-12": 5, "2021-05": 20, "2020-01": 20}


def test_G155_both_orders_in_the_column_keep_the_dates_ambiguous(tmp_path):
    values = ["25-03-2020", "03-25-2021"] * 5 + ["03-04-2020", "05/06/2021"] * 30
    _, _, outcome = _deep(tmp_path, {"d": values})
    parts = _parts(outcome, "d")

    assert parts.ambiguous == 60 and parts.resolution is None and parts.resolved == 0
    assert parts.count == 10 and parts.simulation is not None


def test_G156_an_order_of_the_configuration_wins_and_the_switch_turns_the_inference_off(tmp_path):
    values = ["25-03-2020", "14/07/2021"] * 5 + ["03-04-2020", "05/06/2021"] * 30
    columns = {"d": values}
    _, _, given = _deep(tmp_path / "given", columns, detectors={"date": {"ambiguous_order": "MDY"}})
    off = DeepSettings.model_validate({"datetime": {"infer_order": False}})
    _, _, switched = _deep(tmp_path / "off", columns, off)

    # The configuration read them month-day: nothing is left to infer.
    assert _parts(given, "d").resolution is None and _parts(given, "d").ambiguous == 0
    assert _parts(switched, "d").resolution is None and _parts(switched, "d").ambiguous == 60
    assert entry(switched, "temporal_distribution", "d").result.ambiguous == 60


def test_G157_the_plan_names_the_evidence_and_the_years_of_the_scan_no_longer_answer(tmp_path):
    values = [f"{d:02d}-{m:02d}-{y}" for y in range(1900, 1990) for d in (25, 4) for m in (3, 7)] * 3
    result = scan_csv(tmp_path, "d", values)
    plan = plan_analyses(result, requests=[], automatic=True)
    candidates = by_analyzer(plan, "temporal_distribution")["d"]
    parts = by_analyzer(plan, "datetime_parts")["d"]

    assert candidates.parameters["date_order"] == "DMY" and parts.parameters["date_order"] == "DMY"
    # Ninety years: the Scan counts the years, but without the ambiguous dates.
    assert candidates.selection.state != "already_satisfied"
    assert "ambiguous_dates_read_by_evidence" in candidates.utility.reasons
    off = DeepSettings.model_validate({"datetime": {"infer_order": False}})
    quiet = plan_analyses(result, requests=[], automatic=True, deep=off)
    # Off, the ambiguous dates stay out and the years the Scan counts answer as before.
    assert by_analyzer(quiet, "temporal_distribution")["d"].selection.state == "already_satisfied"


def test_G158_the_workers_and_the_summary_carry_the_reading_of_the_ambiguous_dates(tmp_path):
    values = ["25-03-2020", "14/07/2021"] * 20 + ["03-04-2020", "05/06/2021"] * 60
    columns = {"d": values, "e": values}
    result = scan_csv(tmp_path, "d,e", _rows(columns), **READ)
    plan = forced_plan(result)
    plan = plan.model_copy(
        update={"candidates": [c for c in plan.candidates if c.analyzer != "residual_values"]}
    )
    alone = run_second_pass(result, tmp_path / "data.csv", plan, workers=1)
    shared = run_second_pass(result, tmp_path / "data.csv", plan, workers=2)

    assert [a.model_dump(mode="json") for a in shared.document.analyses] == [
        a.model_dump(mode="json") for a in alone.document.analyses
    ]
    jsonschema.validate(json.loads(deep_document(alone.document)), deep_schema())
    summary, _ = result_summary(_parts(alone, "d"))
    assert "120 ambiguous now valid, read as DMY (proved by 40 unambiguous dates)" in summary
    periods, _ = result_summary(entry(alone, "temporal_distribution", "d").result)
    assert "read as DMY" in periods


def test_G159_too_few_proofs_leave_the_dates_ambiguous_until_the_threshold_is_lowered(tmp_path):
    values = ["25-03-2020", "14/07/2021"] + ["03-04-2020", "05/06/2021"] * 30
    _, _, thin = _deep(tmp_path / "thin", {"d": values})
    lowered = DeepSettings.model_validate({"datetime": {"min_evidence": 2}})
    _, _, enough = _deep(tmp_path / "enough", {"d": values}, lowered)

    # Two day-month dates against the default threshold of 3: nothing is decided.
    assert _parts(thin, "d").resolution is None and _parts(thin, "d").ambiguous == 60
    assert _parts(thin, "d").resolved == 0
    assert _parts(enough, "d").resolution.evidence == {"DMY": 2, "MDY": 0}
    assert _parts(enough, "d").resolved == 60 and _parts(enough, "d").ambiguous == 0
    assert DeepSettings().datetime.min_evidence == 3
    with pytest.raises(ValueError):
        DeepSettings.model_validate({"datetime": {"min_evidence": 0}})


def test_G160_the_threshold_counts_the_proofs_of_one_order_and_both_orders_still_mix():
    from tabalyst.scanner.planner.facts import order_of

    assert order_of({"DMY": 3, "MDY": 0}, 3) == "DMY" and order_of({"DMY": 2, "MDY": 0}, 3) is None
    assert order_of({"DMY": 0, "MDY": 5}, 3) == "MDY"
    assert order_of({"DMY": 100, "MDY": 1}, 1) is None and order_of({"DMY": 0, "MDY": 0}) is None

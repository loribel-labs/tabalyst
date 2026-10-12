# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Insight lot 17d.2a: ambiguous numbers read by the evidence of the column (G152 on).

When the unambiguous numbers of a column prove one convention, at least
``min_evidence`` of them and none proving the other, the Scan reads the
ambiguous ``1,234`` in it and, under ``comma``, the strict decimal ``1.234`` as
thousands; every later reading of the field reads the same numbers (design
20.27). The oracle is built from what the generator wrote, as exact fractions,
never from the detector or the accumulators.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

import pytest
from planner_helpers import scan_csv
from second_pass_helpers import forced_plan
from smart_helpers import report

from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner.convention_rule import NumberRule, scan_convention, single_reading
from tabalyst.scanner.measures import output_number
from tabalyst.scanner.models import Complete, FieldResult, ScanResult
from tabalyst.scanner.planner.facts import order_of
from tabalyst.scanner.secondpass import run_second_pass
from tabalyst.scanner.secondpass.document import analysis_key
from tabalyst.scanner.secondpass.replay import CellReader

NBSP = " "


@dataclass(frozen=True)
class Written:
    """A number as the generator wrote it: its text, the convention it proves
    (``None``: neither) and its value under each convention (``None``: that
    convention does not read it)."""

    text: str
    proof: str | None
    dot: Fraction | None
    comma: Fraction | None


def _group(n: int) -> tuple[str, str]:
    return str(n // 1000), f"{n % 1000:03d}"


def ambiguous(n: int, sign: str = "") -> Written:
    head, tail = _group(n)
    value = Fraction(n) * (-1 if sign == "-" else 1)
    return Written(f"{sign}{head},{tail}", None, value, value / 1000)


def dotted(n: int, sign: str = "") -> Written:
    head, tail = _group(n)
    value = Fraction(n) * (-1 if sign == "-" else 1)
    return Written(f"{sign}{head}.{tail}", None, value / 1000, value)


def integer(n: int) -> Written:
    return Written(str(n), None, Fraction(n), Fraction(n))


def spaced(n: int) -> Written:
    head, tail = _group(n)
    return Written(f"{head}{NBSP}{tail}", None, Fraction(n), Fraction(n))


def decimal(cents: int, convention: str, separator: str = "") -> Written:
    """A number with two decimals, grouped by thousands with ``separator``."""
    whole, part = divmod(cents, 100)
    point = "," if convention == "comma" else "."
    if whole >= 1000 and separator:
        head, tail = _group(whole)
        text = f"{head}{separator}{tail}{point}{part:02d}"
    else:
        text = f"{whole}{point}{part:02d}"
    value = Fraction(cents, 100)
    return Written(text, convention, value if convention == "dot" else None,
                   value if convention == "comma" else None)


def _columns(count: int = 600, seed: int = 172) -> dict[str, list[Written]]:
    rng = random.Random(seed)

    def pick(*makers):
        return [rng.choice(makers)() for _ in range(count)]

    big = lambda: rng.randrange(1000, 1_000_000)
    cents = lambda: rng.randrange(0, 5_000_000)
    return {
        "eu": pick(
            lambda: decimal(cents(), "comma", "."),
            lambda: ambiguous(big()),
            lambda: dotted(big()),
            lambda: integer(rng.randrange(0, 999)),
        ),
        "us": pick(
            lambda: decimal(cents(), "dot", ","),
            lambda: ambiguous(big()),
            lambda: dotted(big()),
            lambda: integer(rng.randrange(0, 999)),
        ),
        "mixed": pick(
            lambda: decimal(cents(), "comma"),
            lambda: decimal(cents(), "dot"),
            lambda: ambiguous(big()),
        ),
        "spaces": pick(
            lambda: decimal(cents(), "comma", NBSP),
            lambda: spaced(big()),
            lambda: ambiguous(big()),
        ),
        "spaces_only": pick(lambda: spaced(big()), lambda: ambiguous(big())),
        "signed": pick(
            lambda: decimal(cents(), "comma", "."),
            lambda: ambiguous(big(), rng.choice(("", "-"))),
            lambda: dotted(big(), rng.choice(("", "-", "+"))),
        ),
    }


def _thin(count: int = 200) -> list[Written]:
    """Two values prove ``comma``, the rest is ambiguous."""
    rng = random.Random(9)
    return [decimal(150, "comma"), decimal(275, "comma")] + [
        ambiguous(rng.randrange(1000, 1_000_000)) for _ in range(count)
    ]


def _quote(text: str) -> str:
    return f'"{text}"'


def _scan(tmp_path, columns: dict[str, list[Written]], workers: int | None = 1, **settings):
    tmp_path.mkdir(parents=True, exist_ok=True)
    rows = [
        ",".join(_quote(item.text) for item in row)
        for row in zip(*columns.values(), strict=True)
    ]
    if workers is None:
        return scan_csv(tmp_path, ",".join(columns), rows, **settings)
    path = tmp_path / "data.csv"
    path.write_text(",".join(columns) + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return scan(path, config=ScanConfig.model_validate(settings), workers=workers)


def _field(result: ScanResult, display: str) -> FieldResult:
    return next(f for d in result.datasets for f in d.fields if f.display == display)


def _ambiguity(field: FieldResult) -> dict:
    detector = next(d for d in field.detectors if d.id == "number")
    return detector.details["ambiguity"]


@dataclass(frozen=True)
class Expected:
    convention: str | None
    numbers: list[Fraction]
    evidence: dict[str, int]
    resolved: int


def oracle(values: list[Written], minimum: int = 3) -> Expected:
    """The numbers of a column as the rule reads them, from the writings alone."""
    evidence = {
        "comma": sum(item.proof == "comma" for item in values),
        "dot": sum(item.proof == "dot" for item in values),
    }
    if evidence["comma"] >= minimum and not evidence["dot"]:
        convention = "comma"
    elif evidence["dot"] >= minimum and not evidence["comma"]:
        convention = "dot"
    else:
        convention = None
    numbers: list[Fraction] = []
    resolved = 0
    for item in values:
        both = item.dot is not None and item.comma is not None
        if both and item.dot != item.comma and item.proof is None and "," in item.text:
            if convention is None:
                continue  # ambiguous and unproved: not a number
            numbers.append(item.dot if convention == "dot" else item.comma)  # type: ignore[arg-type]
            resolved += 1
        elif both and item.dot != item.comma:
            # The strict decimal d.ddd: thousands only under a comma proof.
            if convention == "comma":
                numbers.append(item.comma)  # type: ignore[arg-type]
                resolved += 1
            else:
                numbers.append(item.dot)  # type: ignore[arg-type]
        else:
            numbers.append(item.dot if item.dot is not None else item.comma)  # type: ignore[arg-type]
    return Expected(convention, numbers, evidence, resolved if convention else 0)


def _median(numbers: list[Fraction]) -> Fraction:
    ordered = sorted(numbers)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _assert_numeric(field: FieldResult, numbers: list[Fraction], *, median: bool = True) -> None:
    assert isinstance(field.numeric, Complete), field.numeric
    stats = field.numeric.value
    total = sum(numbers, Fraction(0))
    assert stats.count == len(numbers)
    assert stats.min == output_number(min(numbers))
    assert stats.max == output_number(max(numbers))
    assert stats.sum == output_number(total)
    assert stats.mean == output_number(total / len(numbers))
    assert stats.positive == sum(n > 0 for n in numbers)
    assert stats.negative == sum(n < 0 for n in numbers)
    assert stats.zero == sum(n == 0 for n in numbers)
    if median:
        assert isinstance(stats.median, Complete)
        assert stats.median.value == output_number(_median(numbers))
    else:
        assert stats.median.status == "limited"


def _assert_resolution(field: FieldResult, expected: Expected) -> None:
    resolution = _ambiguity(field)["resolution"]
    if expected.convention is None or not expected.resolved:
        assert resolution is None
        return
    assert resolution == {
        "convention": expected.convention,
        "source": "evidence",
        "evidence": expected.evidence,
        "resolved": expected.resolved,
    }


@pytest.mark.parametrize("display", ["eu", "us", "mixed", "spaces", "spaces_only", "signed"])
def test_G152_the_numbers_of_a_column_match_an_oracle_of_exact_fractions(tmp_path, display):
    columns = _columns()
    result = _scan(tmp_path, columns)
    expected = oracle(columns[display])
    field = _field(result, display)

    _assert_numeric(field, expected.numbers)
    _assert_resolution(field, expected)
    assert _ambiguity(field)["evidence"] == expected.evidence


def test_G153_a_released_table_gives_the_same_numbers_but_the_median(tmp_path):
    columns = _columns()
    result = _scan(tmp_path, columns, limits={"max_distinct_per_field": 10})

    for display, values in columns.items():
        expected = oracle(values)
        field = _field(result, display)
        _assert_numeric(field, expected.numbers, median=False)
        _assert_resolution(field, expected)


def test_G154_a_column_proving_both_conventions_leaves_the_ambiguous_numbers_out(tmp_path):
    columns = _columns()
    field = _field(_scan(tmp_path, columns), "mixed")
    ambiguous_count = sum("," in v.text and v.proof is None for v in columns["mixed"])

    assert _ambiguity(field)["resolution"] is None
    assert field.numeric.value.count == len(columns["mixed"]) - ambiguous_count  # type: ignore[union-attr]
    assert scan_convention(field) is None


def test_G155_fewer_proofs_than_min_evidence_resolve_nothing(tmp_path):
    values = _thin()
    unproved = _field(_scan(tmp_path / "three", {"thin": values}), "thin")
    proved = _field(
        _scan(tmp_path / "two", {"thin": values}, detectors={"number": {"min_evidence": 2}}),
        "thin",
    )

    assert _ambiguity(unproved)["resolution"] is None
    assert unproved.numeric.value.count == 2  # type: ignore[union-attr]
    _assert_numeric(proved, oracle(values, minimum=2).numbers)
    assert _ambiguity(proved)["resolution"]["resolved"] == len(values) - 2


def test_G156_infer_convention_false_keeps_the_reading_of_the_strict_rule(tmp_path):
    columns = _columns()
    off = _scan(tmp_path, columns, detectors={"number": {"infer_convention": False}})

    for display, values in columns.items():
        field = _field(off, display)
        # The oracle with an unreachable proof: ambiguous out, d.ddd decimal.
        _assert_numeric(field, oracle(values, minimum=10**9).numbers)
        assert _ambiguity(field)["resolution"] is None


def test_G157_a_convention_given_by_the_configuration_wins_and_regroups_nothing(tmp_path):
    columns = {"eu": _columns()["eu"]}
    result = _scan(tmp_path, columns, detectors={"number": {"ambiguous_convention": "comma"}})
    field = _field(result, "eu")
    numbers = [
        item.comma if "," in item.text and item.proof is None else (
            item.dot if item.dot is not None else item.comma
        )
        for item in columns["eu"]
    ]

    assert _ambiguity(field)["resolution"] == {"convention": "comma", "source": "config"}
    _assert_numeric(field, numbers)  # type: ignore[arg-type]
    assert scan_convention(field) is None


def test_G158_spaces_prove_nothing_and_their_decimal_separator_decides(tmp_path):
    columns = _columns()
    result = _scan(tmp_path, columns)

    spaces = _ambiguity(_field(result, "spaces"))
    assert spaces["resolution"]["convention"] == "comma"
    assert spaces["evidence"]["comma"] == sum(v.proof == "comma" for v in columns["spaces"])
    only = _ambiguity(_field(result, "spaces_only"))
    assert only["evidence"] == {"comma": 0, "dot": 0}
    assert only["resolution"] is None


def test_G159_a_column_without_a_number_to_resolve_is_unchanged_by_the_rule(tmp_path):
    rng = random.Random(3)
    values = [decimal(rng.randrange(0, 10**6), "comma", ".") for _ in range(300)]
    values += [integer(rng.randrange(0, 999)) for _ in range(100)]
    on = _field(_scan(tmp_path / "on", {"n": values}), "n")
    off = _field(
        _scan(tmp_path / "off", {"n": values}, detectors={"number": {"infer_convention": False}}),
        "n",
    )

    assert _ambiguity(on)["resolution"] is None
    assert on.model_dump(mode="json") == off.model_dump(mode="json")


def test_G160_the_workers_give_the_document_of_one_process(tmp_path):
    columns = _columns(2_000)
    settings = {"limits": {"max_distinct_per_field": 500}}
    alone = _scan(tmp_path / "one", columns, workers=1, **settings)
    shared = _scan(tmp_path / "two", columns, workers=3, **settings)

    assert [d.model_dump(mode="json")["fields"] for d in shared.datasets] == [
        d.model_dump(mode="json")["fields"] for d in alone.datasets
    ]
    assert _ambiguity(_field(shared, "eu"))["resolution"]["convention"] == "comma"


def test_G161_the_coverage_and_the_formats_still_describe_the_writing(tmp_path):
    columns = _columns()
    field = _field(_scan(tmp_path, columns), "eu")
    number = next(d for d in field.detectors if d.id == "number")
    ambiguous_count = sum("," in v.text and v.proof is None for v in columns["eu"])

    assert number.coverage.ambiguous == ambiguous_count
    assert number.coverage.matched == len(columns["eu"]) - ambiguous_count
    # d.ddd keeps its written format, and the ambiguous ones have none.
    assert "0.0" in {item.format for item in number.formats}
    assert sum(item.count for item in number.formats) == number.coverage.matched
    assert field.numeric.value.count == len(columns["eu"])  # type: ignore[union-attr]


# Few samples: the Scan does not hold every distinct value, so the second pass
# reads the source.
READ = {"limits": {"max_samples": 50}}


def _second_pass(tmp_path, columns, workers: int = 1, **settings):
    result = _scan(tmp_path, columns, workers=None, **{**READ, **settings})
    plan = forced_plan(result)
    return result, plan, run_second_pass(result, tmp_path / "data.csv", plan, workers=workers)


def _by_field(result: ScanResult, outcome) -> dict[str, dict[str, object]]:
    names = {f.id: f.display for d in result.datasets for f in d.fields}
    found: dict[str, dict[str, object]] = {}
    for item in outcome.document.analyses:
        found.setdefault(names[item.field], {})[item.analyzer] = item
    return found


@pytest.mark.parametrize("workers", [1, 3])
def test_G162_the_second_pass_reads_the_numbers_the_scan_counted(tmp_path, workers):
    columns = _columns(1_500)
    result, _, outcome = _second_pass(tmp_path, columns, workers)
    analyses = _by_field(result, outcome)

    for display in ("eu", "us", "spaces", "signed"):
        field = _field(result, display)
        assert scan_convention(field) is not None
        for analyzer in ("numeric_histogram", "numeric_shape"):
            item = analyses[display][analyzer]
            assert item.status == "complete", (display, analyzer, item.reason, item.detail)  # type: ignore[attr-defined]
            assert item.result.count == field.numeric.value.count  # type: ignore[attr-defined, union-attr]


def test_G163_the_workers_of_the_second_pass_give_the_result_of_one_process(tmp_path):
    columns = _columns(1_500)
    result = _scan(tmp_path, columns, workers=None, **READ)
    plan = forced_plan(result)
    alone = run_second_pass(result, tmp_path / "data.csv", plan, workers=1)
    shared = run_second_pass(result, tmp_path / "data.csv", plan, workers=3)

    assert [a.model_dump(mode="json") for a in shared.document.analyses] == [
        a.model_dump(mode="json") for a in alone.document.analyses
    ]


def _pairs(count: int = 400, seed: int = 5) -> tuple[list[str], list[str], list[str]]:
    """A European amount, a European price that follows it and a category of
    the amount."""
    rng = random.Random(seed)
    amounts, prices, groups = [], [], []
    for i in range(count):
        n = rng.randrange(1000, 1_000_000)
        # n / 1000 either way: ``1,234`` read as a comma, or ``1,2340``, which
        # only the comma reads.
        amounts.append(ambiguous(n).text + ("" if i % 3 else "0"))
        prices.append(dotted(n).text if i % 4 else decimal(n * 100, "comma").text)
        # A category that explains the amount, so its numbers by category count.
        groups.append(("low", "mid", "high")[n * 3 // 1_000_000])
    return amounts, prices, groups


@pytest.mark.parametrize("settings", [{}, READ], ids=["from_the_scan", "from_the_source"])
def test_G164_pairs_and_numbers_by_category_read_the_numbers_of_the_scan(tmp_path, settings):
    amounts, prices, groups = _pairs()
    rows = [",".join(_quote(v) for v in row) for row in zip(amounts, prices, groups, strict=True)]
    result = scan_csv(tmp_path, "amount,price,group", rows, **settings)
    plan = forced_plan(result)
    outcome = run_second_pass(result, tmp_path / "data.csv", plan, workers=1)

    assert scan_convention(_field(result, "amount")) == "comma"
    assert scan_convention(_field(result, "price")) == "comma"
    for item in outcome.document.analyses:
        if item.analyzer in ("pearson_correlation", "category_stats", "numeric_histogram"):
            assert item.status == "complete", (item.analyzer, item.reason, item.detail)
    pair = next(a for a in outcome.document.analyses if a.analyzer == "pearson_correlation")
    # The price is the amount read in the same convention: a perfect line.
    assert pair.result.pairs == len(amounts)
    assert pair.result.coefficient == pytest.approx(1.0)


def test_G165_a_smart_sample_tests_the_numbers_as_the_scan_counted_them(tmp_path):
    amounts, prices, groups = _pairs(600)
    # The same numbers, written so that nothing is ambiguous: ``1,2340`` and an
    # integer for ``1.234``.
    plain_amounts = [text if text.count(",") and len(text.split(",")[1]) == 4
                     else text + "0" for text in amounts]
    plain_prices = [text.replace(".", "") for text in prices]
    outcomes = []
    for name, columns in (
        ("ambiguous", (amounts, prices, groups)),
        ("plain", (plain_amounts, plain_prices, groups)),
    ):
        rows = [",".join(_quote(v) for v in row) for row in zip(*columns, strict=True)]
        (tmp_path / name).mkdir()
        result, plan, _, document = report(tmp_path / name, "amount,price,group", rows, 60)
        assert [(e.id, e.reason) for e in document.targets if e.status == "unresolved"] == []
        assert any(t.predicate.kind == "numeric_bin" for t in plan.targets)
        outcomes.append((result, plan, document))

    (result, plan, document), (_, plain_plan, plain_document) = outcomes
    assert scan_convention(_field(result, "amount")) == "comma"
    assert [t.model_dump(mode="json") for t in plan.targets] == [
        t.model_dump(mode="json") for t in plain_plan.targets
    ]
    assert [e.model_dump(mode="json") for e in document.targets] == [
        e.model_dump(mode="json") for e in plain_document.targets
    ]


def test_G166_the_reader_of_a_field_reads_in_the_convention_of_the_scan(tmp_path):
    result = _scan(tmp_path, _columns())
    reader = CellReader(result.config)
    texts = ["1,234", "1.250", "12", "2,5"]

    ordinary = [cell.number for cell in reader.cells(texts)]
    comma = [cell.number for cell in reader.for_field(_field(result, "eu")).cells(texts)]
    dot = [cell.number for cell in reader.for_field(_field(result, "us")).cells(texts)]
    none = [cell.number for cell in reader.for_field(_field(result, "mixed")).cells(texts)]

    assert ordinary == none == [None, Decimal("1.250"), 12, Decimal("2.5")]
    assert comma == [Decimal("1.234"), 1250, 12, Decimal("2.5")]
    assert dot == [1234, Decimal("1.250"), 12, Decimal("2.5")]
    assert reader.reading("comma") is reader.for_field(_field(result, "eu"))


def test_G167_the_rule_is_the_one_of_the_dates():
    for day_first in range(5):
        for month_first in range(5):
            for minimum in (1, 3):
                evidence = {"DMY": day_first, "MDY": month_first}
                assert order_of(evidence, minimum) == single_reading(evidence, minimum)
    rule = NumberRule.of({"conventions": ["dot", "comma"], "min_evidence": 3})
    assert rule.convention({"comma": 3, "dot": 0}) == "comma"
    assert rule.convention({"comma": 2, "dot": 0}) is None
    assert rule.convention({"comma": 30, "dot": 1}) is None
    assert not NumberRule.of({"conventions": ["comma"]}).active
    assert not NumberRule.of({"ambiguous_convention": "dot"}).active
    assert not NumberRule.of({"infer_convention": False}).active


def test_G168_another_threshold_makes_other_keys_for_the_second_pass(tmp_path):
    values = _thin()
    first = _scan(tmp_path / "a", {"thin": values}, workers=None, **READ)
    second = _scan(
        tmp_path / "b",
        {"thin": values},
        workers=None,
        **READ,
        detectors={"number": {"min_evidence": 2}},
    )
    keys = []
    for result in (first, second):
        plan = forced_plan(result)
        candidate = next(c for c in plan.candidates if c.analyzer == "numeric_histogram")
        keys.append(analysis_key(plan.base, candidate))

    assert keys[0] != keys[1]


def test_G169_the_settings_are_validated_and_inherited_by_the_amounts():
    config = ScanConfig.model_validate(
        {"detectors": {"currency": {"infer_convention": False, "min_evidence": 5}}}
    )
    assert config.detectors.number.infer_convention is True
    assert config.detectors.number.min_evidence == 3
    assert config.detectors.currency.min_evidence == 5
    with pytest.raises(ValueError):
        ScanConfig.model_validate({"detectors": {"number": {"min_evidence": 0}}})


def test_G170_the_explorations_of_the_planner_read_the_numbers_of_the_scan(tmp_path):
    amounts, prices, groups = _pairs()
    rows = [",".join(_quote(v) for v in row) for row in zip(amounts, prices, groups, strict=True)]
    result = scan_csv(tmp_path, "amount,price,group", rows)
    plan = forced_plan(result)

    pair = next(c for c in plan.candidates if c.analyzer == "pearson_correlation")
    assert pair.exploration.pairs == len(amounts)  # type: ignore[union-attr]
    assert pair.exploration.coefficient == pytest.approx(1.0)  # type: ignore[union-attr]
    stats = [c for c in plan.candidates if c.analyzer == "category_stats"]
    assert stats and all(c.exploration.rows == len(amounts) for c in stats)  # type: ignore[union-attr]


def test_G171_a_native_json_number_is_kept_as_it_is_never_read_in_a_convention(tmp_path):
    from tabalyst.scanner.secondpass.boundaries import distinct_numbers, row_numbers

    lines = (
        ['{"n": 1.250}', '{"n": 2}', '{"n": "1.500"}', '{"n": "1,234"}']
        + ['{"n": "2,5"}', '{"n": "3,5"}', '{"n": "4,5"}']
    )
    path = tmp_path / "data.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = scan(path, workers=1)
    dataset = result.datasets[0]
    field = _field(result, "n")
    reader = CellReader(result.config)

    assert scan_convention(field) == "comma"
    # The Scan: the natives as they are, the strings in the proven convention.
    _assert_numeric(
        field,
        [Fraction(5, 4), Fraction(2), Fraction(1500), Fraction(1234, 1000)]
        + [Fraction(25, 10), Fraction(35, 10), Fraction(45, 10)],
    )
    # The bottom-k sample knows the native type: 1.250 stays 1.25.
    distinct = distinct_numbers(field, reader)
    assert Fraction(5, 4) in distinct and Fraction(1250) not in distinct
    assert Fraction(1500) in distinct
    # The row sample writes natives as text: in a field that holds natives, d.ddd
    # keeps the value written, so the native 1.250 is never read as 1250.
    rows = row_numbers(dataset, field, reader)
    assert Fraction(5, 4) in rows and Fraction(1250) not in rows


def test_G172_a_stored_scan_whose_fingerprint_no_longer_matches_is_scanned_again(
    tmp_path, monkeypatch
):
    import json

    from tabalyst.projects.location import StorageLocation
    from tabalyst.scanner.config import config_sha256
    from tabalyst.shared_scan_service import current_scan

    # The shared storage of the test, never the user's.
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path / "home"))
    source = tmp_path / "data.csv"
    source.write_text("n\n1\n2\n", encoding="utf-8")
    location = StorageLocation.local()
    first = current_scan(source, ScanConfig(), location=location, workers=1)
    data = json.loads(first.path.read_text(encoding="utf-8"))
    # As written before the setting existed: the fingerprint of the old configuration.
    number = data["config"]["detectors"]["number"]
    del number["infer_convention"], number["min_evidence"]
    data["config_sha256"] = "0" * 64
    first.path.write_text(json.dumps(data), encoding="utf-8")

    second = current_scan(source, ScanConfig(), location=location, workers=1)

    assert second.reused is False
    stored = json.loads(second.path.read_text(encoding="utf-8"))
    assert stored["config"]["detectors"]["number"]["min_evidence"] == 3
    assert stored["config_sha256"] == config_sha256(second.result.config)
    assert current_scan(source, ScanConfig(), location=location, workers=1).reused is True

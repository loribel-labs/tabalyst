# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The hierarchical validation of the patterns (design 20.9, lot P6): the reader
agrees with the signatures, the counts add up whatever the path or the number of
workers, the result is serializable and the budgets are bounded."""

import pickle
import random
import string

import pytest
from planner_helpers import scan_csv
from second_pass_helpers import entry, forced_plan, pattern_accumulator

from tabalyst.config import DeepSettings
from tabalyst.scanner import ScanConfig, pattern_eligibility, scan
from tabalyst.scanner.models import FieldPatternsComplete, PatternEligibility
from tabalyst.scanner.patterninfer import compile_signature, matches
from tabalyst.scanner.planner import plan_analyses
from tabalyst.scanner.planner.analyzers.patterns import PatternValidation
from tabalyst.scanner.planner.registry import AnalyzerRegistry
from tabalyst.scanner.secondpass import run_second_pass
from tabalyst.scanner.secondpass.models import PatternCounts
from tabalyst.scanner.secondpass.patternreader import (
    KNOWN,
    NEW_LENGTH,
    UNKNOWN_STRUCTURE,
)
from tabalyst.scanner.secondpass.patterns import derive_from_samples


def _codes(rng: random.Random, count: int) -> list[str]:
    """Identifiers of several structures and lengths: three prefixes with a number of 4
    to 6 digits, a year-month column and a dozen of lowercase words."""
    prefixes = ["LOT"] * 5 + ["SER"] * 3 + ["AGR"]
    rows = [f"{rng.choice(prefixes)}-{rng.randrange(10 ** rng.choice((4, 5, 6)))}" for _ in range(count)]
    rows += [f"{rng.choice(prefixes)}{rng.randrange(1000, 9999)}" for _ in range(count // 4)]
    return rows


def _scanned(tmp_path, rows, **settings):
    result = scan_csv(tmp_path, "code", rows, **settings)
    patterns = result.derived.patterns.fields[0]
    assert isinstance(patterns, FieldPatternsComplete)
    return result, patterns


def test_a_value_that_a_pattern_signature_reads_is_counted_in_that_pattern(tmp_path, monkeypatch):
    # The reader finds the pattern by the lengths of the value, never by trying the
    # signatures: a test makes sure that the two agree on random values (design 20.9).
    eligible = PatternEligibility(state="eligible", score=1.0, reasons=["regular_structure"])
    monkeypatch.setattr(pattern_eligibility, "assess", lambda *args: eligible)
    rng = random.Random(4)
    alphabet = string.ascii_letters + string.digits + "-_ '"
    rows = [
        "".join(rng.choice(alphabet) for _ in range(rng.randrange(1, 9))) for _ in range(800)
    ]
    rows += [f"AB{n:04d}" for n in range(200)] + [f"x{n}-{n * 3}" for n in range(200)]
    result, patterns = _scanned(tmp_path, rows)
    accumulator = pattern_accumulator(result, patterns)
    owner = {}
    for family in accumulator.reader.families:
        for pattern in family.patterns:
            stack = [pattern]
            while stack:
                node = stack.pop()
                owner[node.slot] = pattern.id
                stack.extend(node.children)
    probes = rows + ["", "AB", "AB12345", "x1-", "9" * 30] + [
        "".join(rng.choice(alphabet) for _ in range(rng.randrange(0, 14))) for _ in range(2_000)
    ]

    checked = 0
    for family in patterns.families:
        for pattern in family.patterns:
            matcher = compile_signature(pattern.signature)
            for probe in probes:
                if not matches(matcher, probe):
                    continue
                _, family, slot, _, _ = accumulator.reader.read(probe)
                assert family is not None, probe
                assert owner.get(slot) == pattern.id, (pattern.render, probe)
                checked += 1
    assert checked > 500


def test_the_counts_from_the_samples_are_those_of_a_reading_of_the_source(tmp_path):
    rows = _codes(random.Random(7), 800)
    result, patterns = _scanned(tmp_path, rows)
    field = result.datasets[0].fields[0]
    assert patterns.population.complete

    from_samples = pattern_accumulator(result, patterns, unique=True)
    derive_from_samples(from_samples, field)
    read = pattern_accumulator(result, patterns)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row] = counts.get(row, 0) + 1
    read.add_strings(list(counts), list(counts.values()))

    left = from_samples.result(len(rows), "samples").model_dump(mode="json")
    right = read.result(len(rows), "source").model_dump(mode="json")
    assert left.pop("computed_from") == "samples" and right.pop("computed_from") == "source"
    assert left == right


def test_the_result_adds_up_through_the_hierarchy_and_the_families_and_the_excluded(tmp_path):
    rows = _codes(random.Random(11), 600)
    result, patterns = _scanned(tmp_path, rows, limits={"max_samples": 200})
    accumulator = pattern_accumulator(result, patterns)
    file = rows + ["LOT-12#", "ZZZ", "LOT-" + "9" * 70, "AGR-999999999", "XYZ-1"]
    accumulator.add_strings(file, [1] * len(file))
    accumulator.add_native(3)

    counts = accumulator.result(len(file) + 3, "source")

    assert counts.matched + counts.unknown_structure + sum(counts.excluded.model_dump().values()) == counts.values
    assert counts.excluded.too_long == 1 and counts.excluded.non_string == 3
    assert counts.unknown_structure == 2
    assert sum(family.occurrences for family in counts.families) == counts.matched

    def check(node) -> int:
        below = sum(check(child) for child in node.nodes)
        assert below + node.rest == node.occurrences, node.id
        assert node.distinct.count >= 1 or node.occurrences == 0
        return node.occurrences

    for family in counts.families:
        inside = sum(check(pattern) for pattern in family.patterns)
        lengths = [table for table in family.tables if table.facet == "lengths"]
        held = sum(cell.occurrences for table in lengths for cell in table.cells) + sum(
            table.others for table in lengths
        )
        assert inside + held + family.new_variants.length == family.occurrences


def test_a_set_of_lengths_the_discovery_never_saw_is_a_new_variant_of_its_family(tmp_path):
    result, patterns = _scanned(tmp_path, [f"AB-{n:04d}" for n in range(300)])
    accumulator = pattern_accumulator(result, patterns)

    assert accumulator.outcome("AB-0001") == "known"
    assert accumulator.outcome("AB-00012") == "new_variant"
    assert accumulator.outcome("AB-00012") != "unknown_structure"
    assert accumulator.outcome("AB_0001") == "unknown_structure"
    assert accumulator.reader.read("AB-00012")[0] == NEW_LENGTH
    assert accumulator.reader.read("AB-0001")[0] == KNOWN
    assert accumulator.reader.read("12")[0] == UNKNOWN_STRUCTURE


def test_the_accumulator_is_serializable_and_gives_the_same_result_after_the_trip(tmp_path):
    # A route moves to a worker process and comes back (TR-005).
    rows = _codes(random.Random(5), 500)
    result, patterns = _scanned(tmp_path, rows, limits={"max_samples": 150})
    accumulator = pattern_accumulator(result, patterns)
    accumulator.add_strings(rows[:300], [1] * 300)

    other = pickle.loads(pickle.dumps(accumulator))
    for target in (accumulator, other):
        target.add_strings(rows[300:], [1] * (len(rows) - 300))

    assert accumulator.result(len(rows), "source") == other.result(len(rows), "source")


def test_a_table_is_bounded_by_its_capacity_and_a_set_of_distinct_values_by_its_bytes(tmp_path):
    rows = [f"{a}{b}-{n:03d}" for a in "AB" for b in "CDEFGHJK" for n in range(5, 40)]
    result, patterns = _scanned(tmp_path, rows, limits={"max_samples": 40})
    tight = pattern_accumulator(result, patterns, table_cells=3)
    tight.budget = 400
    tight.add_strings(rows, [1] * len(rows))

    counts = tight.result(len(rows), "source")

    for family in counts.families:
        for table in family.tables:
            assert len(table.cells) <= 3
            if table.others:
                assert table.saturated
        assert family.distinct.accuracy == "at_least"
        assert family.distinct.count < len(set(rows))


def _write_columns(directory, columns: dict[str, list[str]]):
    rows = max(len(column) for column in columns.values())
    lines = [",".join(columns)]
    for row in range(rows):
        lines.append(",".join(column[row] if row < len(column) else "" for column in columns.values()))
    (directory / "data.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_the_counts_of_many_columns_come_from_one_reading_and_do_not_depend_on_the_workers(
    tmp_path,
):
    rng = random.Random(3)
    columns = {f"c{n}": _codes(rng, 400)[:480] for n in range(6)}
    _write_columns(tmp_path, columns)
    result = scan(tmp_path / "data.csv", config=ScanConfig.model_validate({"limits": {"max_samples": 100}}))
    plan = plan_analyses(result, forced=True, registry=AnalyzerRegistry([PatternValidation]))
    displays = [item.display for item in plan.candidates if item.analyzer == "pattern_validation"]
    assert len(displays) == 6

    documents = {}
    for workers in (1, 3):
        outcome = run_second_pass(result, tmp_path / "data.csv", plan, workers=workers)
        assert outcome.document.run.source_read
        assert outcome.document.run.workers == workers
        documents[workers] = {}
        for name in displays:
            counts = entry(outcome, "pattern_validation", name).result
            assert isinstance(counts, PatternCounts)
            assert counts.computed_from == "source" and counts.values == 480
            documents[workers][name] = counts.model_dump(mode="json")

    assert documents[1] == documents[3]


def test_the_plan_carries_the_budgets_of_the_validation(tmp_path):
    result, _ = _scanned(tmp_path, [f"AB-{n:04d}" for n in range(300)], limits={"max_samples": 40})
    deep = DeepSettings.model_validate({"patterns": {"table_bytes": 4_096, "distinct_bytes": 8_192}})

    plan = forced_plan(result, deep)

    [candidate] = [c for c in plan.candidates if c.analyzer == "pattern_validation"]
    assert candidate.parameters["table_bytes"] == 4_096
    assert candidate.parameters["distinct_bytes"] == 8_192
    assert candidate.parameters["facets"] >= 0 and candidate.parameters["nodes"] >= 1


def _column(rng: random.Random, kind: int, count: int) -> list[str]:
    """A column of one of several shapes that make the discovery build families,
    merged blocks, chains of prefixes, folded constants and nodes that merged."""
    upper, lower, digits = string.ascii_uppercase, string.ascii_lowercase, string.digits

    def pick(alphabet: str, size: int) -> str:
        return "".join(rng.choice(alphabet) for _ in range(size))

    if kind == 0:
        years = [2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]
        return [
            f"{rng.choice(years)}-{rng.randrange(1, 13):02d}-{rng.randrange(1, 29):02d}"
            for _ in range(count)
        ]
    if kind == 1:
        prefixes = [pick(upper, 2) for _ in range(rng.randrange(2, 30))]
        return [f"{rng.choice(prefixes)}-{pick(digits, rng.choice((4, 4, 5)))}" for _ in range(count)]
    if kind == 2:
        return [pick(digits, 5) + (pick(upper, 1) if rng.random() < 0.3 else "") for _ in range(count)]
    if kind == 3:
        heads = ["AB", "AB", "AB", "AC", "XY", "QZ"]
        tails = ["00", "00", "01", "99"]
        return [f"{rng.choice(heads)}{pick(digits, 3)}-{rng.choice(tails)}" for _ in range(count)]
    if kind == 4:
        return [
            f"{pick(upper, 1)}{pick(digits, 1)}{pick(upper, 1)} {pick(digits, 1)}{pick(upper, 1)}{pick(digits, 1)}"
            for _ in range(count)
        ]
    if kind == 5:
        words = ["inv", "ord", "ref"]
        return [
            f"{rng.choice(words)}_{pick(digits, rng.choice((3, 6)))}{pick(lower, rng.choice((0, 0, 1, 2)))}"
            for _ in range(count)
        ]
    if kind == 6:
        return [
            f"{rng.choice(['LOT', 'SER'])}-{rng.choice(['07', '12', '31'])}-{pick(digits, 6)}-"
            f"{rng.choice(['EU', 'NA', 'AS'])}"
            for _ in range(count)
        ]
    return [f"é{pick(digits, 3)}" if rng.random() < 0.3 else f"E{pick(digits, 3)}" for _ in range(count)]


@pytest.mark.parametrize("seed", range(32))
def test_the_reader_agrees_with_the_discovery_on_varied_columns(tmp_path, seed):
    # The reader recognizes again the population the discovery read and refuses a
    # Scan whose entry does not match it (ScanMismatch): none must, whatever the shape
    # of the column, the size of the sample or the budgets of the discovery.
    rng = random.Random(seed)
    rows = _column(rng, seed % 8, rng.choice((200, 600)))
    settings: dict[str, object] = {"limits": {"max_samples": rng.choice((50, 300, 5_000))}}
    if seed % 3 == 0:
        settings["pattern_inference"] = {
            "max_depth": rng.choice((2, 3, 4)),
            "max_patterns": rng.choice((8, 128)),
        }
    result = scan_csv(tmp_path, "code", rows, **settings)
    patterns = result.derived.patterns.fields[0]
    if not isinstance(patterns, FieldPatternsComplete):
        pytest.skip("the field is not eligible")

    accumulator = pattern_accumulator(result, patterns)

    assert accumulator.reader.families
    # Every value of the file is read the same way by the check on one string and by the
    # count of the batch.
    file = rows + [row + "#" for row in rows[:5]] + [row + "7" for row in rows[5:15]]
    expected = {"known": 0, "new_variant": 0, "unknown_structure": 0}
    for value in file:
        expected[accumulator.outcome(value)] += 1
    accumulator.add_strings(file, [1] * len(file))
    counts = accumulator.result(len(file), "source")
    new = sum(f.new_variants.length + f.new_variants.segment for f in counts.families)
    assert counts.unknown_structure == expected["unknown_structure"]
    assert new == expected["new_variant"]
    assert counts.matched == len(file) - expected["unknown_structure"]


def test_a_value_that_is_no_cell_of_an_open_facet_is_not_a_new_variant(tmp_path):
    # The sample shows the digits of a date vary: another month is not a new variant.
    rng = random.Random(2)
    rows = _column(rng, 0, 900)
    result, patterns = _scanned(tmp_path, rows, limits={"max_samples": 60})
    accumulator = pattern_accumulator(result, patterns)
    accumulator.add_strings(rows, [1] * len(rows))

    counts = accumulator.result(len(rows), "source")

    assert counts.matched == len(rows)
    assert all(family.new_variants.segment == 0 for family in counts.families)


def test_a_value_that_is_no_cell_of_a_closed_facet_is_a_new_variant(tmp_path):
    rows = [f"{prefix}-{n:04d}" for prefix in ("AK", "BC", "CD", "DE") for n in range(60)]
    result, patterns = _scanned(tmp_path, rows)
    accumulator = pattern_accumulator(result, patterns)

    assert accumulator.outcome("AK-0001") == "known"
    assert accumulator.outcome("QZ-0001") == "new_variant"
    accumulator.add_strings(["AK-0001", "QZ-0001", "QZ-0002"], [3, 5, 1])
    counts = accumulator.result(9, "source")

    assert counts.families[0].new_variants.segment == 6
    [table] = [table for table in counts.families[0].tables if table.facet == "head:1"]
    assert {cell.value: cell.occurrences for cell in table.cells}["QZ"] == 6


def test_the_second_pass_opens_the_source_once_for_fifteen_columns(tmp_path, monkeypatch):
    # AC-015: one reading serves every column, as many as there are.
    from tabalyst.scanner.secondpass import executor

    rng = random.Random(8)
    columns = {f"c{n}": _codes(rng, 300)[:300] for n in range(15)}
    _write_columns(tmp_path, columns)
    result = scan(
        tmp_path / "data.csv", config=ScanConfig.model_validate({"limits": {"max_samples": 80}})
    )
    plan = plan_analyses(result, forced=True, registry=AnalyzerRegistry([PatternValidation]))
    assert sum(c.execution.requires_source for c in plan.candidates if c.selection.state == "selected") >= 15
    opened = []
    real = executor.open_reader
    monkeypatch.setattr(executor, "open_reader", lambda *a, **k: opened.append(a[0]) or real(*a, **k))

    run_second_pass(result, tmp_path / "data.csv", plan, workers=1)

    assert len(opened) == 1


def test_the_flat_view_counts_as_other_every_value_that_no_pattern_reads(tmp_path):
    # The readers of the flat list (the report, the smart sample) add up: the patterns
    # they list, the values none reads and the values left out are the values.
    result, patterns = _scanned(tmp_path, [f"AB-{n:04d}" for n in range(300)])
    accumulator = pattern_accumulator(result, patterns)
    accumulator.add_strings(["AB-0001", "AB-00012", "AB_1", "x" * 80], [4, 2, 1, 1])

    counts = accumulator.result(8, "source")

    assert counts.unknown_structure == 1 and counts.families[0].new_variants.length == 2
    assert counts.other == 3
    assert (
        sum(tally.occurrences for tally in counts.candidates)
        + counts.other
        + sum(counts.excluded.model_dump().values())
        == counts.values
    )

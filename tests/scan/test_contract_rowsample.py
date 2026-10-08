# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contract of the row sample (Scan and JSON plan, tests C01 to C06).

The behavior is specified in ``docs/dev/scan/design.md`` section 18.11 and in
the specification, section 9 (ROW-01 to ROW-11). The oracle is the definition
itself, computed by the test: the first and last ``edge`` records, and the
records of the interior with the smallest position priorities.
"""

import json

import pytest
from scan_helpers import dataset, run_scan, write_text

from tabalyst.scanner.config import RowSampleSettings
from tabalyst.scanner.paths import Column
from tabalyst.scanner.rowsample import RowBudget, RowPriority, RowSampler

PATH = (Column(1),)
IDS = {PATH: "column_1"}
SEED = 42


def _sampler(rows: int, edge: int, *, seed: int = SEED) -> RowSampler:
    settings = RowSampleSettings(rows=rows, edge=edge)
    return RowSampler(settings, seed, RowBudget(1 << 30), (PATH,))


def _feed(sampler: RowSampler, count: int, sizes: tuple[int, ...] = ()) -> None:
    """Rows ``r1`` to ``r<count>``, in batches of the given sizes (then one)."""
    rows = [[f"r{index}"] for index in range(1, count + 1)]
    position = 0
    for size in sizes:
        sampler.add_batch(position + 1, rows[position : position + size])
        position += size
    sampler.add_batch(position + 1, rows[position:])


def _finish(sampler: RowSampler):
    return sampler.finalize(IDS, {}, ["column_1"], False, lambda text: True)


def _expected(count: int, edge: int, middle: int, seed: int = SEED):
    """Positions of the start, the middle and the end, by definition."""
    priority = RowPriority(seed)
    interior = range(edge + 1, count - edge + 1)
    best = sorted(interior, key=lambda position: (priority.at(position), position))
    return (
        list(range(1, min(count, edge) + 1)),
        sorted(best[:middle]),
        list(range(max(1, count - edge + 1), count + 1)),
    )


def _positions(sample):
    def of(origin: str) -> list[int]:
        return [row.record for row in sample.rows if origin in row.origins]

    return of("start"), of("middle"), of("end")


@pytest.mark.scan_json_lot("3b")
@pytest.mark.parametrize("count", [0, 2, 6, 15, 20, 21, 500])
@pytest.mark.parametrize("sizes", [(), (1, 3, 7)])
def test_C01_every_size_gives_unique_positions_and_the_defined_edges(count, sizes):
    # S = 20, E = 4, M = 12: N below E, below 2E, below S, at S and above.
    sampler = _sampler(20, 4)
    _feed(sampler, count, sizes)

    sample = _finish(sampler)

    start, middle, end = _expected(count, 4, 12)
    assert _positions(sample) == (start, middle, end)
    positions = [row.record for row in sample.rows]
    assert len(positions) == len(set(positions))
    assert sample.population.records == count
    assert sample.population.interior == max(0, count - 8)
    assert sample.complete is (count <= 20)
    assert sample.kept == sample.of == len(sample.rows)
    if count <= 20:
        # A census: every record is a row, under its edge labels.
        assert sorted(positions) == list(range(1, count + 1))
    # A record of both edges is stored once with both labels.
    for row in sample.rows:
        if len(row.origins) > 1:
            assert row.origins == ["start", "end"]


@pytest.mark.scan_json_lot("3b")
def test_C02_identical_rows_are_distinct_observations():
    sampler = _sampler(30, 3)
    sampler.add_batch(1, [["same"]] * 200)

    sample = _finish(sampler)

    middle = [row for row in sample.rows if row.origins == ["middle"]]
    assert len(middle) == 24
    assert len({row.record for row in middle}) == 24
    assert {tuple(row.values["column_1"]) for row in sample.rows} == {("same",)}
    # The same positions as for rows of different content: the priority never
    # looks at the content.
    other = _sampler(30, 3)
    _feed(other, 200)
    assert _positions(_finish(other)) == _positions(sample)


@pytest.mark.scan_json_lot("3b")
def test_C03_only_the_rows_that_left_the_buffer_are_candidates_of_the_middle():
    # M is larger than the interior, so every candidate is kept: the middle is
    # exactly the records that left the buffer of the last E rows.
    by_batches = _sampler(100, 4)
    _feed(by_batches, 30, (5, 1, 9))
    by_records = _sampler(100, 4)
    from tabalyst.scanner.observations import Observation, Record
    from tabalyst.scanner.paths import ROOT

    for index in range(1, 31):
        by_records.add_record(
            Record(
                "rows",
                index,
                None,
                [Observation(ROOT, "object", None), Observation(PATH, "string", f"r{index}")],
            )
        )

    for sampler in (by_batches, by_records):
        start, middle, end = _positions(_finish(sampler))
        assert start == [1, 2, 3, 4]
        assert middle == list(range(5, 27))
        assert end == [27, 28, 29, 30]


@pytest.mark.scan_json_lot("3b")
def test_C04_an_exploration_reads_the_interior_and_its_scope():
    sampler = _sampler(20, 4)
    _feed(sampler, 500)

    sample = _finish(sampler)

    assert sample.population.scope == "interior_rows"
    interior = sample.interior()
    assert len(interior) == 12
    assert {row.record for row in interior} == set(_expected(500, 4, 12)[1])
    # No edge row is ever part of what an exploration treats as a sample.
    assert all(row.origins == ["middle"] for row in interior)
    # A dataset without interior has nothing to explore (ROW-07).
    small = _sampler(20, 4)
    _feed(small, 8)
    finished = _finish(small)
    assert finished.interior() == []
    assert finished.population.interior == 0


@pytest.mark.scan_json_lot("3b")
def test_C05_nulls_and_invalid_values_keep_the_cells_of_the_same_rows(tmp_path):
    lines = ["a,b,c"]
    for index in range(1, 31):
        lines.append(f"{index},{'' if index % 3 == 0 else 'x' + str(index)},{'N/A' if index % 5 == 0 else index * 2}")
    source = write_text(tmp_path, "rows.csv", "\n".join(lines) + "\n")

    result = run_scan(
        source, records={"sample": {"rows": 12, "edge": 2}}, values={"null_markers": ["N/A"]}
    )

    sample = dataset(result, "rows")["records"]["sample"]
    table = [line.split(",") for line in lines[1:]]
    assert sample["rows"]
    for row in sample["rows"]:
        expected = table[row["record"] - 1]
        # All the columns of one record, in one row: null markers and empty
        # cells stay where they were read.
        assert row["values"] == {
            "column_1": [expected[0]],
            "column_2": [expected[1]],
            "column_3": [expected[2]],
        }
    jsonl = write_text(
        tmp_path,
        "rows.jsonl",
        "".join(
            json.dumps({"a": index, "b": None if index % 2 else "t", "c": [index, None]}) + "\n"
            for index in range(1, 21)
        ),
    )
    result = run_scan(jsonl, records={"sample": {"rows": 8, "edge": 2}})
    for row in dataset(result, "$[]")["records"]["sample"]["rows"]:
        index = row["record"]
        assert sorted(row["values"].values(), key=str) == sorted(
            [[str(index)], [None] if index % 2 else ["t"], [str(index), None]], key=str
        )


@pytest.mark.scan_json_lot("3b")
def test_C06_a_projection_without_a_field_cannot_serve_a_relation_on_it(tmp_path):
    text = "x" * 500
    rows = "".join(f"{index},{index * 2},{text},ann{index}@example.com,{index}\n" for index in range(1, 41))
    source = write_text(tmp_path, "rows.csv", "a,b,c,mail,d\n" + rows)

    result = run_scan(
        source,
        limits={"max_fields": 4},
        records={"sample": {"rows": 10, "edge": 2, "cell_chars": 100}},
        exposure={"sensitive_values": "hide"},
    )

    from tabalyst.scanner.models import RowSample

    sample = RowSample.model_validate(dataset(result, "rows")["records"]["sample"])
    # The fifth column is untracked: not projected, and the sample says so.
    assert sample.fields_limited is True
    assert "column_5" not in sample.fields
    assert sample.covers(["column_1", "column_2"])
    assert not sample.covers(["column_1", "column_5"])
    # A cell cut at cell_chars or hidden cannot serve a relation either.
    assert not sample.covers(["column_1", "column_3"])
    assert not sample.covers(["column_4"])
    assert sample.truncated_cells == len(sample.rows)

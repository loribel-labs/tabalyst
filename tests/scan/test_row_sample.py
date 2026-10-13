# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Row sample (lot 3b, design 18.11): priorities, batches, cells, budget,
exposure, validation and the Report base."""

import gc
import json
import random
import tracemalloc

import pytest
from scan_helpers import dataset, run_scan, write_text

from tabalyst import ScanConfig, scan
from tabalyst.json_text import dump_json
from tabalyst.scan_document import complete_samples, facts_sha256
from tabalyst.scanner.config import RowSampleSettings
from tabalyst.scanner.observations import Observation, Record
from tabalyst.scanner.paths import ROOT, Column, Key
from tabalyst.scanner.rowsample import RowBudget, RowPriority, RowSampler
from tabalyst.scanner.validation import check_scan

PATH = (Column(1),)
IDS = {PATH: "column_1"}


def _settings(**values) -> RowSampleSettings:
    return RowSampleSettings.model_validate(values)


def _sample(result: dict, dataset_id: str = "rows") -> dict:
    return dataset(result, dataset_id)["records"]["sample"]


def _csv(tmp_path, rows: int, columns: int = 3, name: str = "rows.csv"):
    header = ",".join(f"c{index}" for index in range(columns))
    body = "".join(
        ",".join(f"v{row}x{column}" for column in range(columns)) + "\n"
        for row in range(1, rows + 1)
    )
    return write_text(tmp_path, name, header + "\n" + body)


# Priorities ---------------------------------------------------------------


def test_priorities_are_stable_values_of_the_seed_and_the_position():
    priority = RowPriority(42)

    # Pinned: any change of these values is a change of ROW_HASH_VERSION.
    assert [priority.at(index) for index in (1, 2, 8, 9, 1000)] == [
        8900790365749050740,
        12911773691602474662,
        11670494171022022760,
        10227013887443399393,
        5432572835340126736,
    ]
    assert RowPriority(0).at(1) == 1780154860073318069


def test_a_range_of_priorities_is_the_priorities_of_its_positions():
    priority = RowPriority(7)
    for first, stop in [(1, 1), (1, 2), (5, 30), (8, 16), (13, 14), (1, 100)]:
        assert priority.range(first, stop) == [priority.at(i) for i in range(first, stop)]


def test_a_seed_outside_the_range_is_refused():
    with pytest.raises(ValueError, match="seed"):
        RowPriority(-1)
    with pytest.raises(ValueError, match="seed"):
        RowPriority(1 << 64)


# Settings -----------------------------------------------------------------


def test_the_edges_must_fit_in_the_sample():
    assert _settings().rows == 1_000 and _settings().edge == 50
    assert _settings(rows=0).rows == 0
    assert _settings(rows=10, edge=5).edge == 5
    with pytest.raises(ValueError, match="edge"):
        _settings(rows=10, edge=6)


def test_the_settings_are_read_from_the_scan_configuration():
    config = ScanConfig.model_validate(
        {"records": {"sample": {"rows": 40, "edge": 3, "cell_chars": 9}}}
    )

    assert (config.records.sample.rows, config.records.sample.edge) == (40, 3)
    with pytest.raises(ValueError, match="edge"):
        ScanConfig.model_validate({"records": {"sample": {"rows": 4, "edge": 3}}})


# Batches and records --------------------------------------------------------


def _table_record(index: int, text: str) -> Record:
    return Record(
        "rows",
        index,
        None,
        [Observation(ROOT, "object", None), Observation(PATH, "string", text)],
    )


def _finish(sampler: RowSampler):
    return sampler.finalize(IDS, {}, ["column_1"], False, lambda text: True)


def test_the_sample_does_not_depend_on_how_the_rows_arrive():
    rng = random.Random(5)
    rows = [[f"r{index}"] for index in range(1, 401)]
    whole = RowSampler(_settings(rows=40, edge=5), 3, RowBudget(1 << 30), (PATH,))
    whole.add_batch(1, rows)
    results = [_finish(whole)]
    for _ in range(4):
        sampler = RowSampler(_settings(rows=40, edge=5), 3, RowBudget(1 << 30), (PATH,))
        position = 0
        while position < len(rows):
            size = rng.randint(1, 60)
            sampler.add_batch(position + 1, rows[position : position + size])
            position += size
        results.append(_finish(sampler))
    byrecord = RowSampler(_settings(rows=40, edge=5), 3, RowBudget(1 << 30), (PATH,))
    for index in range(1, 401):
        byrecord.add_record(_table_record(index, f"r{index}"))
    results.append(_finish(byrecord))

    # A record costs more than a row of strings in the model, so ``bytes`` is the
    # one fact that depends on the path; the rows themselves never do.
    batched, byrecord = results[:-1], results[-1]
    assert all(result == batched[0] for result in batched)
    assert byrecord.model_copy(update={"bytes": batched[0].bytes}) == batched[0]
    assert byrecord.bytes > batched[0].bytes
    assert batched[0].threshold is not None


def test_a_gap_in_the_indices_keeps_the_priority_of_each_index():
    # Excluded records leave gaps: the first batch ends at 20, the next starts
    # at 31. Positions are the record indices.
    sampler = RowSampler(_settings(rows=20, edge=2), 3, RowBudget(1 << 30), (PATH,))
    sampler.add_batch(1, [[f"r{i}"] for i in range(1, 21)])
    sampler.add_batch(31, [[f"r{i}"] for i in range(31, 61)])

    sample = _finish(sampler)

    assert sample.population.records == 50
    assert [row.record for row in sample.rows if "start" in row.origins] == [1, 2]
    assert [row.record for row in sample.rows if "end" in row.origins] == [59, 60]
    priority = RowPriority(3)
    candidates = [*range(3, 21), *range(31, 59)]
    best = sorted(candidates, key=lambda index: (priority.at(index), index))[:16]
    assert [row.record for row in sample.rows if row.origins == ["middle"]] == sorted(best)


def test_a_sample_without_rows_is_absent(tmp_path):
    config = ScanConfig.model_validate({"records": {"sample": {"rows": 0}}})

    result = scan(_csv(tmp_path, 20), config=config)

    assert result.datasets[0].records.sample is None
    assert "sample" not in dataset(result.model_dump(mode="json"), "rows")["records"]
    assert check_scan(result) == []


def test_two_scans_and_two_worker_counts_give_the_same_rows(tmp_path):
    source = _csv(tmp_path, 3000, columns=4)
    config = ScanConfig.model_validate({"records": {"sample": {"rows": 100, "edge": 10}}})

    documents = [
        scan(source, config=config, workers=workers).model_dump(mode="json")
        for workers in (1, 1, 2)
    ]

    samples = [_sample(document) for document in documents]
    assert samples[0]["rows"] and samples[0] == samples[1] == samples[2]


def test_the_seed_of_the_scan_chooses_the_middle(tmp_path):
    source = _csv(tmp_path, 500)

    settings = {"sample": {"rows": 100, "edge": 10}}
    first = _sample(run_scan(source, random_seed=1, records=settings))
    second = _sample(run_scan(source, random_seed=2, records=settings))

    assert first["hash"]["seed"] == 1 and second["hash"]["seed"] == 2
    assert [r["record"] for r in first["rows"]] != [r["record"] for r in second["rows"]]
    assert first["rows"][:10] == second["rows"][:10]  # the start is the start


# Cells ------------------------------------------------------------------------


def test_a_long_cell_is_cut_and_named(tmp_path):
    source = write_text(
        tmp_path, "rows.csv", "a,b\n" + "".join(f"{'é' * 30},{i}\n" for i in range(1, 6))
    )

    sample = _sample(run_scan(source, records={"sample": {"rows": 10, "edge": 1, "cell_chars": 12}}))

    assert sample["cell_chars"] == 12
    assert sample["truncated_cells"] == 5
    for row in sample["rows"]:
        assert row["values"]["column_1"] == ["é" * 12]
        assert row["truncated"] == ["column_1"]
        assert "column_2" not in row["truncated"]


def test_the_values_of_a_repeated_path_share_the_cell_budget(tmp_path):
    source = write_text(
        tmp_path, "rows.json", json.dumps([{"tags": ["a" * 10, "b" * 10, "c" * 10, "d"]}])
    )

    sample = _sample(
        run_scan(source, records={"sample": {"rows": 4, "edge": 1, "cell_chars": 25}}), "$[]"
    )

    (row,) = sample["rows"]
    assert list(row["values"].values()) == [["a" * 10, "b" * 10, "c" * 5]]
    assert len(row["truncated"]) == 1
    assert sample["truncated_cells"] == 1


@pytest.mark.parametrize(
    ("mode", "expected"),
    [("mask", ["aaa9@aaaaaaa.aaa"]), ("hide", None), ("show", ["ann1@example.com"])],
)
def test_the_cells_go_through_the_exposure(tmp_path, mode, expected):
    rows = "".join(f"ann{index}@example.com,{index}\n" for index in range(1, 4))
    source = write_text(tmp_path, "mails.csv", "email,n\n" + rows + ",4\n")

    sample = _sample(run_scan(source, exposure={"sensitive_values": mode}))

    assert sample["rows"][0]["values"]["column_1"] == expected
    assert sample["rows"][0]["values"]["column_2"] == ["1"]
    assert sample["rows"][3]["values"]["column_1"] == [""]


# Budget ----------------------------------------------------------------------


def _wide(count: int, width: int = 20):
    return [[f"cell-{row}-{column}-" + "x" * 20 for column in range(width)] for row in range(count)]


def test_the_byte_budget_cuts_the_middle_and_says_so():
    paths = tuple((Column(position),) for position in range(1, 21))
    ids = {path: f"column_{position}" for position, path in enumerate(paths, start=1)}
    rows = _wide(2000)
    row_bytes = 150 + 60 * 20 + 20 * 40

    sampler = RowSampler(_settings(rows=1000, edge=50), 42, RowBudget(300 * row_bytes), paths)
    sampler.add_batch(1, rows)
    sample = sampler.finalize(ids, {}, list(ids.values()), False, lambda text: True)

    assert sample.reason == "memory_budget"
    assert sample.requested.middle == 900 and 0 < sample.middle_k < 900
    assert sample.bytes <= sample.max_bytes
    assert not sample.complete
    # The edges came first and are intact; the middle kept its best rows.
    start = [row.record for row in sample.rows if "start" in row.origins]
    end = [row.record for row in sample.rows if "end" in row.origins]
    assert start == list(range(1, 51)) and end == list(range(1951, 2001))
    priority = RowPriority(42)
    middle = [row.record for row in sample.rows if row.origins == ["middle"]]
    assert len(middle) == sample.middle_k
    assert int(sample.threshold, 16) == max(priority.at(index) for index in middle)
    ranked = sorted(range(51, 1951), key=lambda index: (priority.at(index), index))
    assert middle == sorted(ranked[: sample.middle_k])


def test_a_budget_smaller_than_the_edges_keeps_the_first_and_the_last_that_fit():
    paths = tuple((Column(position),) for position in range(1, 21))
    ids = {path: f"column_{position}" for position, path in enumerate(paths, start=1)}
    row_bytes = 150 + 60 * 20 + 20 * 40

    sampler = RowSampler(_settings(rows=100, edge=10), 42, RowBudget(12 * row_bytes), paths)
    sampler.add_batch(1, _wide(500))
    sample = sampler.finalize(ids, {}, list(ids.values()), False, lambda text: True)

    assert sample.reason == "memory_budget"
    assert sample.bytes <= sample.max_bytes
    start = [row.record for row in sample.rows if "start" in row.origins]
    end = [row.record for row in sample.rows if "end" in row.origins]
    assert start == list(range(1, len(start) + 1)) and start
    assert end[-1] == 500 and end == list(range(500 - len(end) + 1, 501))
    assert sample.middle_k == 0 and sample.threshold is None


def test_the_budget_is_shared_by_the_datasets_first_come_first_served():
    paths = tuple((Column(position),) for position in range(1, 21))
    ids = {path: f"column_{position}" for position, path in enumerate(paths, start=1)}
    row_bytes = 200 + 60 * 20 + 20 * 40
    budget = RowBudget(150 * row_bytes)  # one dataset of 100 rows and half of another

    samples = []
    for _ in range(2):
        sampler = RowSampler(_settings(rows=100, edge=5), 42, budget, paths)
        sampler.add_batch(1, _wide(300))
        samples.append(sampler)
    first, second = (
        sampler.finalize(ids, {}, list(ids.values()), False, lambda text: True)
        for sampler in samples
    )

    # The second dataset found the budget half spent while it was read; the
    # ends of both are charged when they are finalized, in the order of the
    # datasets, so the first one may give up middle rows for its own end.
    assert second.reason == "memory_budget" and 0 < second.middle_k < 90
    assert first.middle_k > second.middle_k
    assert first.bytes + second.bytes <= budget.limit
    assert [row.record for row in first.rows[:5]] == [1, 2, 3, 4, 5]
    with pytest.raises(RuntimeError, match="already finalized"):
        samples[0].finalize(ids, {}, list(ids.values()), False, lambda text: True)


def test_a_sample_that_lists_no_row_covers_no_field(tmp_path):
    from tabalyst.report_profile import report_base

    result = scan(_csv(tmp_path, 40))
    whole = result.datasets[0].records.sample
    dropped = report_base(result, 100).datasets[0].records.sample

    assert whole.covers(["column_1", "column_2"])
    assert not dropped.covers(["column_1", "column_2"])
    assert dropped.interior() == []


def test_a_null_after_a_full_cell_is_kept_and_does_not_cut_it(tmp_path):
    source = write_text(tmp_path, "rows.json", json.dumps([{"a": ["x" * 10, None]}]))

    sample = _sample(
        run_scan(source, records={"sample": {"rows": 4, "edge": 1, "cell_chars": 10}}), "$[]"
    )

    (row,) = sample["rows"]
    assert list(row["values"].values()) == [["x" * 10, None]]
    assert "truncated" not in row


def test_the_validator_refuses_another_priority_function(tmp_path):
    result = scan(_csv(tmp_path, 300), config=ScanConfig.model_validate({"records": {"sample": {"rows": 40, "edge": 5}}}))
    document = result.model_dump(mode="json")
    document["datasets"][0]["records"]["sample"]["hash"]["version"] = 2

    problems = check_scan(type(result).model_validate(document))

    assert any("priority function" in problem for problem in problems)


def test_the_cost_model_is_close_to_the_memory_of_the_rows():
    path = tuple((Column(position),) for position in range(1, 31))
    budget = RowBudget(1 << 30)
    sampler = RowSampler(_settings(rows=300, edge=0), 1, budget, path)

    gc.collect()
    tracemalloc.start()
    try:
        before = tracemalloc.get_traced_memory()[0]
        batch = [
            [f"{row:06d}-{column:03d}-" + "z" * 14 for column in range(30)]
            for row in range(300)
        ]
        sampler.add_batch(1, batch)
        del batch
        gc.collect()
        measured = tracemalloc.get_traced_memory()[0] - before
    finally:
        tracemalloc.stop()

    # The model errs on the safe side and stays close to the measure.
    assert 0.9 * measured <= budget.used <= 1.5 * measured


def test_the_cost_model_of_a_record_is_close_to_the_memory_of_its_cells():
    paths = [(Key(f"k{index}"),) for index in range(10)]
    budget = RowBudget(1 << 30)
    sampler = RowSampler(_settings(rows=300, edge=0), 1, budget)

    gc.collect()
    tracemalloc.start()
    try:
        before = tracemalloc.get_traced_memory()[0]
        for row in range(300):
            observations = [Observation(ROOT, "object", None)] + [
                Observation(path, "string", f"{row:06d}-" + "z" * 14) for path in paths
            ]
            sampler.add_record(Record("d", row + 1, None, observations))
        del observations
        gc.collect()
        measured = tracemalloc.get_traced_memory()[0] - before
    finally:
        tracemalloc.stop()

    assert 0.9 * measured <= budget.used <= 1.6 * measured


def test_the_memory_of_the_sample_does_not_grow_with_the_rows_read():
    path = tuple((Column(position),) for position in range(1, 11))

    def peak(count: int) -> int:
        sampler = RowSampler(_settings(rows=200, edge=20), 1, RowBudget(1 << 30), path)
        gc.collect()
        tracemalloc.start()
        try:
            for start in range(1, count, 1000):
                sampler.add_batch(
                    start,
                    [[f"{row}-{column}" for column in range(10)] for row in range(start, start + 1000)],
                )
            gc.collect()
            return tracemalloc.get_traced_memory()[0]
        finally:
            tracemalloc.stop()

    small, large = peak(5_000), peak(40_000)

    assert large <= 1.1 * small


# Document and validation --------------------------------------------------------


def test_the_sample_of_a_scan_is_valid_and_complete_for_a_small_source(tmp_path):
    result = scan(_csv(tmp_path, 40))

    sample = result.datasets[0].records.sample
    assert check_scan(result) == []
    assert sample.complete and sample.kept == sample.of == 40
    assert sample.fields == ["column_1", "column_2", "column_3"]
    assert sample.population.interior == 0 or sample.population.records == 40
    assert sample.threshold is None and sample.reason is None


def test_the_validator_names_a_tampered_sample(tmp_path):
    source = _csv(tmp_path, 300)
    config = ScanConfig.model_validate({"records": {"sample": {"rows": 40, "edge": 5}}})
    result = scan(source, config=config)
    assert check_scan(result) == []
    document = result.model_dump(mode="json")

    def problems(change) -> list[str]:
        edited = json.loads(json.dumps(document))
        change(edited["datasets"][0]["records"]["sample"])
        return check_scan(type(result).model_validate(edited))

    assert any("threshold" in p for p in problems(lambda s: s.update(threshold="0" * 16)))
    assert any("group" in p or "ascend" in p for p in problems(lambda s: s["rows"].reverse()))
    assert any("not projected" in p for p in problems(lambda s: s["rows"][0]["values"].update(zz=["1"])))
    assert any("interior" in p for p in problems(lambda s: s["population"].update(interior=3)))
    assert any("requested" in p for p in problems(lambda s: s["requested"].update(edge=4)))
    assert any("complete" in p for p in problems(lambda s: s.update(complete=True)))
    assert any("memory_budget" in p for p in problems(lambda s: s.update(reason="other")))


def test_the_report_base_keeps_the_header_of_the_sample_and_the_rows_it_asks_for(
    tmp_path,
):
    from tabalyst.config import RowSampleSettings
    from tabalyst.report_profile import report_base

    result = scan(_csv(tmp_path, 300))

    base = report_base(result, 100)
    none = report_base(result, 100, RowSampleSettings(start=0, middle=0, end=0))

    sample = base.datasets[0].records.sample
    original = result.datasets[0].records.sample
    # Ten rows of each part by default, a subset of the Scan's rows.
    assert sample.kept == len(sample.rows) == 30 and sample.of == original.of > 0
    assert all(row in original.rows for row in sample.rows)
    assert sample.population == original.population
    assert check_scan(base) == []
    empty = none.datasets[0].records.sample
    assert empty.kept == 0 and empty.rows == [] and empty.of == original.of
    assert check_scan(none) == []
    assert original.kept == original.of  # the scan itself is untouched
    assert facts_sha256(base) == facts_sha256(result)
    assert complete_samples(result) and not complete_samples(base)


def test_the_indented_document_writes_one_row_per_line(tmp_path):
    result = scan(_csv(tmp_path, 12, columns=2))
    document = result.model_dump(mode="json")

    text = dump_json(document, indent=True)

    lines = [line for line in text.splitlines() if line.lstrip().startswith('{"record"')]
    assert len(lines) == 12
    assert json.loads(text) == json.loads(dump_json(document))
    assert dump_json(document, indent=True) == text  # the document was restored

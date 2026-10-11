# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The routes of the second pass in worker processes (lot 12, design 20.18)."""

from planner_helpers import scan_csv
from second_pass_helpers import forced_plan

from tabalyst.scanner import workers as scan_workers
from tabalyst.scanner.secondpass import run_second_pass
from tabalyst.scanner.secondpass.parallel import PARTS, part_name, route_weight
from tabalyst.scanner.secondpass.routing import FieldRoute

HEADER = "id,amount,when,code,label"


def _rows(count: int) -> list[str]:
    return [
        f"{100000 + n},{n * 0.37:.2f},2024-{n % 12 + 1:02d}-{n % 27 + 1:02d},"
        f"AB-{n % 90:04d},{'north' if n % 3 else 'south'} {n % 17}"
        for n in range(count)
    ]


def _analyses(outcome) -> list[dict]:
    return [item.model_dump(mode="json") for item in outcome.document.analyses]


def _runs(tmp_path, *workers: int | None):
    """One scan, one plan, and the second pass for each number of workers: the
    keys of the analyses follow the scan, so it is made once."""
    result = scan_csv(tmp_path, HEADER, _rows(4000))
    plan = forced_plan(result)
    return [
        run_second_pass(result, tmp_path / "data.csv", plan, workers=count)
        for count in workers
    ]


def test_the_workers_give_the_analyses_of_one_process(tmp_path):
    alone, shared = _runs(tmp_path, 1, 3)

    assert shared.document.run.workers == 3
    assert alone.document.run.workers == 1
    assert _analyses(shared) == _analyses(alone)
    assert shared.document.run.cells_read == alone.document.run.cells_read
    assert shared.document.status == "complete"


def test_the_result_does_not_depend_on_the_number_of_workers(tmp_path):
    two, four = _runs(tmp_path, 2, 4)

    assert _analyses(two) == _analyses(four)


def test_workers_that_cannot_start_leave_the_second_pass_in_one_process(
    tmp_path, monkeypatch
):
    def fail(*args, **kwargs):
        raise OSError("no processes here")

    monkeypatch.setattr(scan_workers.subprocess, "Popen", fail)
    alone, outcome = _runs(tmp_path, 1, 3)
    expected = _analyses(alone)

    assert outcome.document.run.workers == 1
    assert _analyses(outcome) == expected


def test_workers_that_stop_at_start_leave_the_second_pass_in_one_process(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(scan_workers, "_BOOTSTRAP", "import sys; sys.exit(3)")
    alone, outcome = _runs(tmp_path, 1, 3)
    expected = _analyses(alone)

    assert outcome.document.run.workers == 1
    assert _analyses(outcome) == expected


def test_a_single_field_is_not_shared_out(tmp_path):
    result = scan_csv(tmp_path, "n", [str(n % 40) for n in range(500)])

    outcome = run_second_pass(
        result, tmp_path / "data.csv", forced_plan(result), workers=4
    )

    assert outcome.document.run.workers == 1


def test_a_source_that_is_not_csv_stays_in_one_process(tmp_path):
    from scan_helpers import write_json

    source = write_json(
        tmp_path,
        "data.json",
        [{"id": n, "label": f"x{n % 9}", "amount": n * 1.5} for n in range(400)],
    )
    from tabalyst.scanner import scan

    result = scan(source)

    outcome = run_second_pass(result, source, forced_plan(result), workers=3)

    assert outcome.document.run.workers == 1


def test_a_route_weighs_what_its_accumulators_cost():
    class Bare(FieldRoute):
        def __init__(self) -> None:
            for name in PARTS:
                setattr(self, name, None)

    light = Bare()
    heavy = Bare()
    heavy.lengths = object()  # type: ignore[assignment]
    heavy.periods = object()  # type: ignore[assignment]

    assert route_weight(heavy) > route_weight(light) > 0


def test_every_accumulator_has_the_part_of_a_route_that_holds_it():
    from tabalyst.scanner.secondpass.accumulators import (
        DenseAccumulator,
        LengthAccumulator,
    )
    from tabalyst.scanner.secondpass.frequencies import FrequencyAccumulator
    from tabalyst.scanner.secondpass.periods import PeriodAccumulator

    assert part_name(LengthAccumulator()) == "lengths"
    assert part_name(FrequencyAccumulator(10)) == "frequencies"
    assert part_name(PeriodAccumulator("month", "date")) == "periods"
    assert part_name(DenseAccumulator(0, 10)) == "numeric"


def test_the_workers_asked_for_the_command_apply_to_the_second_pass_too(tmp_path):
    from scan_helpers import write_text

    from tabalyst import generate_deep

    source = write_text(tmp_path, "rows.csv", HEADER + "\n" + "\n".join(_rows(3000)) + "\n")

    one = generate_deep([source], output_dir=tmp_path / "one", workers=1, force=True)
    two = generate_deep([source], output_dir=tmp_path / "two", workers=2, force=True)

    assert one.successes[0].outcome.document.run.workers == 1
    assert two.successes[0].outcome.document.run.workers == 2


def test_a_route_left_out_of_a_batch_holds_back_nothing_for_the_others(tmp_path):
    from tabalyst.scanner import ScanConfig
    from tabalyst.scanner.secondpass.accumulators import LengthAccumulator
    from tabalyst.scanner.secondpass.parallel import SecondPassWorkers
    from tabalyst.scanner.secondpass.replay import CellReader

    config = ScanConfig()
    cells = CellReader(config)
    routes = [FieldRoute(cells, None, LengthAccumulator()) for _ in range(2)]
    pool = SecondPassWorkers(config.model_dump_json(by_alias=True), 2)
    assert pool.start()
    try:
        first, second = pool.place(routes)
        for batch in range(3):
            first.strings(["ab", "abc"])
            if batch == 0:  # the second route has no column in the later batches
                second.strings(["abcd"])
            pool.flush()
        results = pool.finish([first, second])
    finally:
        pool.close()

    assert results[first.rid][2] == 6
    assert results[second.rid][2] == 1
    assert results[first.rid][1] is None

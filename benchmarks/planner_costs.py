# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Measures that calibrate the cost model of the planner (lot 6b, design 20.2).

    python benchmarks/planner_costs.py structures [--entries N]
    python benchmarks/planner_costs.py reader SOURCE
    python benchmarks/planner_costs.py cpu [--cells N]

``structures`` measures, with ``tracemalloc``, the bytes an entry costs in the
structures an analysis keeps (a set of texts of several lengths, a set of
integers, a table of counts) and the peak of their growth. ``reader`` measures
the peak memory of reading a source once, which sizes the parser reserve.
``cpu`` times the proxies of the work per cell (a dense counter, a length, a
bin, a period, a set, a table, a compiled matcher) that the CPU classes of the
analyzers stand on, on values already parsed: the parsing is the common
reading.
Prints one JSON object. Numbers are only comparable on the same machine.
"""

import argparse
import gc
import json
import re
import sys
import tracemalloc
from collections.abc import Callable
from datetime import date
from pathlib import Path
from time import perf_counter

from tabalyst.scanner import ScanConfig
from tabalyst.scanner.api import _open_reader

LENGTHS = (8, 12, 24, 48, 64)


def _text(index: int, length: int) -> str:
    """A text of ``length`` characters (8 or more), distinct for each index."""
    return f"{index:08d}".ljust(length, "x")


def _traced(build: Callable[[], object]) -> tuple[object, int, int]:
    """Run ``build`` and return its result, the bytes it holds and its peak."""
    gc.collect()
    tracemalloc.start()
    tracemalloc.reset_peak()
    base = tracemalloc.get_traced_memory()[0]
    held = build()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return held, current - base, peak - base


def structures(entries: int) -> dict[str, object]:
    result: dict[str, object] = {"entries": entries}
    texts: dict[str, dict[str, float]] = {}
    for length in LENGTHS:
        # The texts are built inside the trace: they belong to the set.
        def build(length: int = length) -> set[str]:
            held: set[str] = set()
            add = held.add
            for index in range(entries):
                add(_text(index, length))
            return held

        _, held, peak = _traced(build)
        texts[str(length)] = {"per_entry": held / entries, "peak_per_entry": peak / entries}
    result["set_of_texts"] = texts

    def build_ints() -> set[int]:
        return {index * 7919 for index in range(entries)}

    _, held, peak = _traced(build_ints)
    result["set_of_integers"] = {"per_entry": held / entries, "peak_per_entry": peak / entries}

    small = min(entries, 1_000)

    def build_table() -> dict[str, int]:
        table: dict[str, int] = {}
        for index in range(small):
            table[f"state_{index:04d}"] = index
        return table

    _, held, peak = _traced(build_table)
    result["table_of_counts"] = {"per_entry": held / small, "peak_per_entry": peak / small}

    def build_dense() -> list[int]:
        return [0] * 65_536

    _, held, _ = _traced(build_dense)
    result["dense_counters_per_slot"] = held / 65_536
    return result


def reader(source: Path) -> dict[str, object]:
    """Peak traced memory while one pass reads and drops every item."""
    config = ScanConfig()
    gc.collect()
    tracemalloc.start()
    tracemalloc.reset_peak()
    base = tracemalloc.get_traced_memory()[0]
    start = perf_counter()
    items = 0
    for _ in _open_reader(source, config, None):
        items += 1
    seconds = perf_counter() - start
    peak = tracemalloc.get_traced_memory()[1] - base
    tracemalloc.stop()
    return {
        "source": source.name,
        "size_bytes": source.stat().st_size,
        "items": items,
        "peak_bytes": peak,
        "traced_seconds": seconds,
    }


def cpu(cells: int) -> dict[str, float]:
    """Nanoseconds per cell of the proxies, on texts of 12 characters."""
    values = [f"AB-{index % 10000:04d}-X" for index in range(cells)]
    ids = [f"A{index:011d}" for index in range(cells)]
    numbers = [index % 1000 for index in range(cells)]
    matcher = re.compile(r"[A-Z]{2}-\d{4}-[A-Z]")

    def run(work: Callable[[], object]) -> float:
        gc.collect()
        start = perf_counter()
        work()
        return (perf_counter() - start) * 1e9 / cells

    def dense() -> None:
        counters = [0] * 1000
        for number in numbers:
            counters[number] += 1

    def table() -> None:
        counts: dict[str, int] = {}
        get = counts.get
        for value in values:
            counts[value] = get(value, 0) + 1

    def distinct() -> None:
        seen: set[str] = set()
        add = seen.add
        for value in ids:
            add(value)

    def match() -> None:
        search = matcher.fullmatch
        for value in values:
            search(value)

    lows = [float(number) for number in numbers]
    days = [date.fromordinal(738000 + number) for number in numbers]

    def length() -> None:
        counters = [0] * 100
        for value in values:
            counters[len(value)] += 1

    def binned() -> None:
        counters = [0] * 100
        low, width = 0.0, 10.0
        for number in lows:
            counters[int((number - low) / width)] += 1

    def period() -> None:
        counters = [0] * 600
        base = 738000
        for day in days:
            counters[(day.toordinal() - base) // 30] += 1

    def loop() -> None:
        for _ in values:
            pass

    return {
        "loop": run(loop),
        "dense_counter": run(dense),
        "length_counter": run(length),
        "bin": run(binned),
        "period": run(period),
        "table_of_counts": run(table),
        "set_of_unique_texts": run(distinct),
        "compiled_matcher": run(match),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="task", required=True)
    one = sub.add_parser("structures")
    one.add_argument("--entries", type=int, default=200_000)
    two = sub.add_parser("reader")
    two.add_argument("source", type=Path)
    three = sub.add_parser("cpu")
    three.add_argument("--cells", type=int, default=1_000_000)
    args = parser.parse_args()
    if args.task == "structures":
        out = structures(args.entries)
    elif args.task == "reader":
        out = reader(args.source)
    else:
        out = cpu(args.cells)
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

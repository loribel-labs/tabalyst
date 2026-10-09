# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Measures that calibrate the cost model of the planner (lot 6b, design 20.2).

    python benchmarks/planner_costs.py structures [--entries N]
    python benchmarks/planner_costs.py reader SOURCE
    python benchmarks/planner_costs.py cpu [--cells N]
    python benchmarks/planner_costs.py executor SOURCE [--repeat N] [--max-samples N]
    python benchmarks/planner_costs.py exact [--entries N]

``structures`` measures, with ``tracemalloc``, the bytes an entry costs in the
structures an analysis keeps (a set of texts of several lengths, a set of
integers, a table of counts) and the peak of their growth. ``reader`` measures
the peak memory of reading a source once, which sizes the parser reserve.
``cpu`` times the proxies of the work per cell (a dense counter, a length, a
bin, a period, a set, a table, a compiled matcher) that the CPU classes of the
analyzers stand on, on values already parsed: the parsing is the common
reading.
``executor`` (lot 7a) scans a source, then runs its second pass once per kind of
analysis (counters of an integer domain, bins, lengths) and gives the
nanoseconds the executor adds to each cell it hands to the analysis, the
firm bound of the plan beside the memory the run held at its peak, and the
cost of the reading it shares. These replace the proxies of ``cpu``.
``exact`` (lot 7b) fills the exact set of the second pass with identifiers of
8, 10 and 12 characters (digits with leading zeros, letters and digits) and
gives the bytes an entry holds, the nanoseconds a distinct value costs and the
peak of the growth, beside the model of the planner.
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

from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner.models import Disabled
from tabalyst.scanner.planner import default_registry, plan_analyses
from tabalyst.scanner.readers.factory import open_reader
from tabalyst.scanner.secondpass import run_second_pass
from tabalyst.scanner.secondpass.exactset import ExactPool, ExactSet

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
    for _ in open_reader(source, config, None):
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


def executor(source: Path, repeat: int, max_samples: int | None) -> dict[str, object]:
    """Time and memory of the second pass, by kind of analysis, on ``source``.

    ``max_samples`` lowers the sample of the Scan so that a field of a few
    hundred values still needs its frequencies counted (the table analysis)."""
    started = perf_counter()
    limits: dict[str, int] = {}
    if max_samples is not None:
        limits = {"max_samples": max_samples, "max_listed_frequencies": 10}
    scanned = scan(source, config=ScanConfig.model_validate({"limits": limits}))
    first_pass = perf_counter() - started
    registry = default_registry().runnable()
    plan = plan_analyses(scanned, forced=True, registry=registry)
    # The Scan always holds the length histogram: switch it off to plan the
    # length analysis, as a Scan whose measure is limited or off would.
    lengthless = scanned.model_copy(
        update={
            "datasets": [
                dataset.model_copy(
                    update={
                        "fields": [
                            field.model_copy(update={"string_lengths": Disabled()})
                            for field in dataset.fields
                        ]
                    }
                )
                for dataset in scanned.datasets
            ]
        }
    )
    length_plan = plan_analyses(lengthless, forced=True, registry=registry)
    kinds = {
        "dense_counter": lambda c: c.analyzer == "numeric_histogram"
        and c.method == "dense_counts",
        "bin": lambda c: c.analyzer == "numeric_histogram" and c.method == "bins",
        "length_counter": lambda c: c.analyzer == "length_distribution",
        "distinct_set": lambda c: c.analyzer == "exact_distinct",
        "table": lambda c: c.analyzer == "exact_frequencies",
    }
    out: dict[str, object] = {
        "source": source.name,
        "first_pass_seconds": round(first_pass, 3),
        "cells": scanned.source.shape.cells,
        "reading_seconds_of_the_scan": scanned.run.timings.reading,
    }
    for label, keep in kinds.items():
        base_scan, base_plan = (
            (lengthless, length_plan) if label == "length_counter" else (scanned, plan)
        )
        chosen = [
            c for c in base_plan.candidates if c.selection.state == "selected" and keep(c)
        ]
        if not chosen:
            out[label] = None
            continue
        part = base_plan.model_copy(update={"candidates": chosen})
        runs = [
            run_second_pass(base_scan, source, part).document.run for _ in range(repeat)
        ]
        best = min(runs, key=lambda run: run.timings.analysis)
        gc.collect()
        tracemalloc.start()
        tracemalloc.reset_peak()
        base = tracemalloc.get_traced_memory()[0]
        run_second_pass(base_scan, source, part)
        peak = tracemalloc.get_traced_memory()[1] - base
        tracemalloc.stop()
        states: dict[str, int] = {}
        for candidate in chosen:
            for state in candidate.costs.states:
                states[state.key] = max(states.get(state.key, 0), state.memory.max)
        out[label] = {
            "analyses": len(chosen),
            "cells_handled": best.cells_read,
            "reading_seconds": best.timings.reading,
            "analysis_seconds": best.timings.analysis,
            "ns_per_cell": round(best.timings.analysis / best.cells_read * 1e9, 1),
            "model_firm_bytes": sum(states.values()),
            "peak_traced_bytes": peak,
        }
    return out


def _identifiers(shape: str, start: int, size: int) -> list[str]:
    """``size`` distinct identifiers from number ``start``: digits with leading
    zeros, or a letter and hexadecimal digits, of 8, 10 or 12 characters."""
    width = int(shape.split("-")[1])
    if shape.startswith("digits"):
        return [f"{index:0{width}d}" for index in range(start, start + size)]
    return [f"K{index:0{width - 1}X}" for index in range(start, start + size)]


def exact(entries: int) -> dict[str, object]:
    """Bytes and nanoseconds of the exact set of the second pass, by shape of
    identifier. The raw strings come from the reader in batches of at most
    4,096 distinct values: they are built inside the trace, so the keys the set
    keeps are counted with it."""
    out: dict[str, object] = {"entries": entries}
    for shape in ("digits-8", "digits-10", "digits-12", "alnum-8", "alnum-10", "alnum-12"):

        def build(shape: str = shape) -> ExactSet:
            held = ExactSet(ExactPool(1 << 40))
            for start in range(0, entries, 4_096):
                batch = _identifiers(shape, start, min(4_096, entries - start))
                held.add_strings(batch, [1] * len(batch))
            return held

        gc.collect()
        started = perf_counter()
        built, held, peak = _traced(build)
        traced_seconds = perf_counter() - started
        assert isinstance(built, ExactSet)
        started = perf_counter()
        build()
        seconds = perf_counter() - started
        out[shape] = {
            "distinct": built.distinct(),
            "per_entry": round(held / entries, 1),
            "peak_per_entry": round(peak / entries, 1),
            "charged_per_entry": round(built.used / entries, 1),
            "ns_per_distinct": round(seconds / entries * 1e9, 1),
            "traced_seconds": round(traced_seconds, 2),
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="task", required=True)
    one = sub.add_parser("structures")
    one.add_argument("--entries", type=int, default=200_000)
    two = sub.add_parser("reader")
    two.add_argument("source", type=Path)
    three = sub.add_parser("cpu")
    three.add_argument("--cells", type=int, default=1_000_000)
    four = sub.add_parser("executor")
    four.add_argument("source", type=Path)
    four.add_argument("--repeat", type=int, default=3)
    four.add_argument("--max-samples", type=int, default=None)
    five = sub.add_parser("exact")
    five.add_argument("--entries", type=int, default=1_000_000)
    args = parser.parse_args()
    if args.task == "structures":
        out = structures(args.entries)
    elif args.task == "reader":
        out = reader(args.source)
    elif args.task == "executor":
        out = executor(args.source, args.repeat, args.max_samples)
    elif args.task == "exact":
        out = exact(args.entries)
    else:
        out = cpu(args.cells)
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

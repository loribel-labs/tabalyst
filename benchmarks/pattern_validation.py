# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Cost per cell of the hierarchical validation of the patterns (lot P6, AC-027).

A column of ``XX-9999`` codes of 10, 64 and 256 prefixes (variants) is written as a
CSV of one million rows with the same number of distinct values whatever the
number of variants, scanned with a sample too small to hold every value (so that
the second pass must read the source), and validated by the second pass with the
analyzer of the patterns alone. The cost per cell is the analysis time of the pass
(its consumption minus the reading) over the cells read. The recognition is flat in
the number of variants when columns that read the same number of facets cost the
same (TR-002): compare the rows with the same ``facets`` of the table, the
discovery choosing them and the cost growing with each one::

    python benchmarks/pattern_validation.py --root D:/GIT.test/tabalyst/artifacts/patterns-p6/bench

Writes ``results.json`` and ``results.md`` under ``--root``. Times are medians of
``--repeat`` runs; compare runs of one session only.
"""

from __future__ import annotations

import argparse
import json
import platform
import random
import statistics
import string
import sys
from pathlib import Path

from tabalyst.config import DeepSettings
from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner.models import FieldPatternsComplete
from tabalyst.scanner.planner import plan_analyses
from tabalyst.scanner.planner.analyzers.patterns import PatternValidation
from tabalyst.scanner.planner.registry import AnalyzerRegistry
from tabalyst.scanner.secondpass import run_second_pass

VARIANTS = (10, 64, 256)
DISTINCT = 100_000


def prefixes(count: int) -> list[str]:
    """``count`` two-letter prefixes spread over the alphabet."""
    letters = string.ascii_uppercase
    every = [a + b for a in letters for b in letters]
    return random.Random(5).sample(every, count)


def write_column(path: Path, variants: int, rows: int) -> None:
    """A CSV of ``rows`` codes ``XX-9999`` drawn from ``DISTINCT`` values spread
    over ``variants`` prefixes, in a fixed order."""
    names = prefixes(variants)
    per = DISTINCT // variants
    pool = [f"{name}-{number:04d}" for name in names for number in range(per)]
    rng = random.Random(11)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("code\n")
        for _ in range(rows):
            handle.write(rng.choice(pool) + "\n")


def measure(path: Path, repeat: int) -> dict[str, object]:
    config = ScanConfig.model_validate(
        {
            "limits": {"max_samples": 20_000},
            "pattern_inference": {"max_patterns": 1_024, "max_depth": 3},
        }
    )
    result = scan(path, config=config)
    derived = result.derived
    assert derived is not None and derived.patterns is not None
    entry = derived.patterns.fields[0]
    assert isinstance(entry, FieldPatternsComplete)
    registry = AnalyzerRegistry([PatternValidation])
    plan = plan_analyses(result, forced=True, registry=registry, deep=DeepSettings())
    times = []
    peak = 0
    cells = 0
    for _ in range(repeat):
        outcome = run_second_pass(result, path, plan, workers=1)
        run = outcome.document.run
        assert run.source_read
        times.append(run.timings.analysis)
        peak = max(peak, run.peak_memory_bytes or 0)
        cells = run.cells_read
    candidate = next(c for c in plan.candidates if c.analyzer == "pattern_validation")
    return {
        "patterns": candidate.parameters["patterns"],
        "nodes": candidate.parameters["nodes"],
        "facets": candidate.parameters["facets"],
        "cells": cells,
        "analysis_seconds": statistics.median(times),
        "ns_per_cell": round(statistics.median(times) / cells * 1e9),
        "peak_memory_bytes": peak,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--rows", type=int, default=1_000_000)
    parser.add_argument("--repeat", type=int, default=3)
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    results = {}
    for variants in VARIANTS:
        path = args.root / f"variants-{variants}.csv"
        write_column(path, variants, args.rows)
        results[variants] = measure(path, args.repeat)
        print(variants, results[variants], flush=True)
    (args.root / "results.json").write_text(
        json.dumps(
            {"python": sys.version.split()[0], "machine": platform.platform(), "results": results},
            indent=2,
        ),
        encoding="utf-8",
    )
    lines = ["| Variants | Nodes | Facets | ns per cell | Peak memory (MB) |", "| --- | --- | --- | --- | --- |"]
    for variants, row in results.items():
        lines.append(
            f"| {variants} | {row['nodes']} | {row['facets']} | {row['ns_per_cell']} | "
            f"{int(row['peak_memory_bytes']) / 1e6:.0f} |"
        )
    (args.root / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

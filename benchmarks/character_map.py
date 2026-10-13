# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Cost of the character map (lot C2): what the Scan's post-pass takes and what the
second-pass analyzer costs a cell, for columns of short codes, names and texts.

Each column is written as a CSV of ``--rows`` rows, scanned with a sample too small to
hold every value (so that the second pass reads the source), and counted by the
analyzer ``character_profile`` alone. The cost per cell is the analysis time of the
pass (its consumption minus the reading) over the cells read::

    python benchmarks/character_map.py --root D:/GIT.test/tabalyst/artifacts/c2/bench

Writes ``results.json`` under ``--root``. Times are medians of ``--repeat`` runs;
compare runs of one session only.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import string
import sys
from collections.abc import Callable
from pathlib import Path

from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner.planner import plan_analyses
from tabalyst.scanner.planner.analyzers.characters import CharacterProfile
from tabalyst.scanner.planner.registry import AnalyzerRegistry
from tabalyst.scanner.secondpass import run_second_pass

WORDS = ["caf\u00e9", "Montr\u00e9al", "Qu\u00e9bec", "Z\u00fcrich", "Paris", "Lyon", "Nice", "Lille"]


def _code(rng: random.Random, number: int) -> str:
    return f"{rng.choice(string.ascii_uppercase)}{rng.choice(string.ascii_uppercase)}-{number % 100_000:05d}"


def _name(rng: random.Random, number: int) -> str:
    return f"{rng.choice(WORDS)} {rng.choice(WORDS)}-{number % 20_000}"


def _text(rng: random.Random, number: int) -> str:
    return " ".join(rng.choice(WORDS).lower() for _ in range(14)) + f" {number}"


SHAPES: dict[str, Callable[[random.Random, int], str]] = {
    "codes": _code,
    "names": _name,
    "texts": _text,
}


def measure(root: Path, shape: str, rows: int, repeat: int) -> dict[str, float]:
    """The median cost of the post-pass and of the second-pass analyzer on one column."""
    rng = random.Random(7)
    path = root / f"{shape}.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("value\n")
        for number in range(rows):
            handle.write(SHAPES[shape](rng, number) + "\n")
    config = ScanConfig.model_validate({"limits": {"max_samples": 1_000}})
    derived: list[float] = []
    nanoseconds: list[float] = []
    for _ in range(repeat):
        result = scan(path, config=config)
        derived.append(result.run.timings.derived)
        plan = plan_analyses(result, forced=True, registry=AnalyzerRegistry([CharacterProfile]))
        outcome = run_second_pass(result, path, plan, workers=1)
        nanoseconds.append(outcome.document.run.timings.analysis / rows * 1e9)
    return {
        "rows": rows,
        "derived_seconds": statistics.median(derived),
        "ns_per_cell": statistics.median(nanoseconds),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--rows", type=int, default=500_000)
    parser.add_argument("--repeat", type=int, default=3)
    options = parser.parse_args()
    options.root.mkdir(parents=True, exist_ok=True)
    results = {shape: measure(options.root, shape, options.rows, options.repeat) for shape in SHAPES}
    (options.root / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    sys.stdout.write(json.dumps(results, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

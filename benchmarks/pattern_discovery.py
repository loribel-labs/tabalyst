# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Starting cost of the pattern discovery on the reference corpus (block B1).

Before the hierarchical discovery exists, two costs bound it from below and from
the side: the current inference (``patterninfer.infer_patterns``, the flat
candidates and the generalization ladder) and a counting floor, the one pass any
implementation of E1 to E3 makes (tokenize, group by structure, count the
shapes, the heads and tails of 1 to 3 characters and the whole tokens, on
distinct values and occurrences). Each field of RC-01 to RC-20 is written as a
CSV, scanned once, then timed; a sweep of RC-13-like identifiers shows how the
cost grows with the distinct values::

    python benchmarks/pattern_discovery.py --root D:/GIT.test/tabalyst/artifacts/patterns-b1/bench

Writes ``results.json`` and ``results.md`` under ``--root``. Times are medians
of ``--repeat`` runs in this interpreter; compare runs of one session only (the
machine drifts by 20 % between sessions, benchmarks.md, lot 0).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import random
import statistics
import subprocess
import sys
import tracemalloc
from collections import defaultdict
from collections.abc import Callable, Sequence
from pathlib import Path
from time import perf_counter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tests" / "patterns"))

from pattern_corpus import Field, corpus

from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner.diagnostics import DiagnosticCollector
from tabalyst.scanner.models import DerivedPatterns
from tabalyst.scanner.patterninfer import infer_patterns, tokenize

SWEEP = (1_000, 2_500, 5_000, 10_000, 20_000)
MAX_CHAIN = 3


def count_floor(pairs: Sequence[tuple[str, int]]) -> int:
    """The counting pass of E1 to E3 on ``pairs``; returns the number of
    counters, so that the work cannot be optimized away."""
    counters: dict[tuple, list[int]] = defaultdict(lambda: [0, 0])
    for value, occurrences in pairs:
        tokens = tokenize(value)
        key = tuple((code, literal) for code, literal, _, _ in tokens)
        shape = tuple(count for code, _, count, _ in tokens if code != "P")
        for entry in ((key, "shape", shape),) + tuple(
            item
            for index, (code, _, _, text) in enumerate(tokens)
            if code != "P"
            for item in (
                *((key, index, "head", text[:size]) for size in range(1, min(MAX_CHAIN, len(text)) + 1)),
                *((key, index, "tail", text[-size:]) for size in range(1, min(MAX_CHAIN, len(text)) + 1)),
                (key, index, "token", text),
            )
        ):  # fmt: skip
            counter = counters[entry]
            counter[0] += 1
            counter[1] += occurrences
    return len(counters)


def _rows(field: Field) -> list[str]:
    """The rows of a field, each value repeated by its occurrences, in an order
    fixed by a seed (a scan sees the rows, not the pairs)."""
    rows = [value for value, count in field.pairs for _ in range(count)]
    random.Random(field.id).shuffle(rows)
    return rows


def _write(path: Path, rows: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["value"])
        writer.writerows([row] for row in rows)


def _median(task: Callable[[], object], repeat: int) -> float:
    times = []
    for _ in range(repeat):
        started = perf_counter()
        task()
        times.append(perf_counter() - started)
    return statistics.median(times)


def _peak(task: Callable[[], object]) -> int:
    tracemalloc.start()
    try:
        task()
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def measure(name: str, field: Field, data: Path, repeat: int) -> dict:
    path = data / (name.replace("/", "-") + ".csv")
    _write(path, _rows(field))
    config = ScanConfig.model_validate({"limits": {"max_samples": 20_000}})
    started = perf_counter()
    result = scan(path, config=config)
    scan_seconds = perf_counter() - started
    settings = config.pattern_inference

    def infer() -> DerivedPatterns | None:
        return infer_patterns(result.datasets, settings, DiagnosticCollector(config.errors.max_locations))

    patterns = infer()
    entry = patterns.fields[0] if patterns is not None else None
    infer_seconds = _median(infer, repeat)
    floor_seconds = _median(lambda: count_floor(field.pairs), repeat)
    samples = result.datasets[0].fields[0].values.samples
    return {
        "field": name,
        "distinct": field.distinct,
        "occurrences": field.occurrences,
        "sample_selection": samples.selection,
        "sample_kept": samples.kept,
        "inference_status": getattr(entry, "status", None),
        "inference_reason": getattr(entry, "reason", None),
        "candidates": len(getattr(entry, "candidates", []) or []),
        "scan_seconds": round(scan_seconds, 4),
        "inference_seconds": round(infer_seconds, 5),
        "inference_ns_per_value": round(infer_seconds / field.distinct * 1e9),
        "floor_seconds": round(floor_seconds, 5),
        "floor_ns_per_value": round(floor_seconds / field.distinct * 1e9),
        "floor_counters": count_floor(field.pairs),
        "inference_peak_bytes": _peak(infer),
        "floor_peak_bytes": _peak(lambda: count_floor(field.pairs)),
    }


def sweep_field(size: int) -> Field:
    """RC-13-like identifiers at ``size`` distinct values: 95 % AK, 4 % AB,
    0.9 % AZ, the rest isolated prefixes."""
    rng = random.Random(f"tabalyst-patterns/sweep/{size}")
    shares = (("AK", 0.95), ("AB", 0.04), ("AZ", 0.009))
    values: set[str] = set()
    for prefix, share in shares:
        target = len(values) + round(size * share)
        while len(values) < target:
            values.add(f"{prefix}-{rng.randrange(10**6):06d}")
    while len(values) < size:
        prefix = chr(66 + rng.randrange(24)) + chr(65 + rng.randrange(26))
        values.add(f"{prefix}-{rng.randrange(10**6):06d}")
    return Field("sweep", str(size), tuple(sorted((value, 1) for value in values)))


def _commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=HERE.parent,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _markdown(report: dict) -> str:
    lines = [
        "# Pattern discovery: starting cost (block B1)",
        "",
        (
            f"Commit `{report['commit']}`, Python {report['python']}, "
            f"{report['platform']}, {report['cpus']} CPUs, median of "
            f"{report['repeat']} runs. Each scan reads one column: the share of "
            "the inference is not the share in a realistic scan (AC-026)."
        ),
        "",
        "| Field | Distinct | Occurrences | Inference | ns/value | Floor | ns/value | Scan | Inference / scan |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in report["corpus"] + report["sweep"]:
        share = row["inference_seconds"] / row["scan_seconds"] if row["scan_seconds"] else 0
        status = row["inference_status"]
        inference = (
            f"{row['inference_seconds'] * 1000:.2f} ms"
            if status == "complete"
            else f"{row['inference_seconds'] * 1000:.2f} ms ({status}: {row['inference_reason']})"
        )
        lines.append(
            f"| {row['field']} | {row['distinct']:,} | {row['occurrences']:,} | {inference} "
            f"| {row['inference_ns_per_value']:,} | {row['floor_seconds'] * 1000:.2f} ms "
            f"| {row['floor_ns_per_value']:,} | {row['scan_seconds']:.2f} s | {share:.1%} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--repeat", type=int, default=5)
    arguments = parser.parse_args()
    root: Path = arguments.root
    if HERE.parent in (root.resolve(), *root.resolve().parents):
        parser.error("--root must be outside the checkout (docs/dev/architecture.md)")
    data = root / "data"
    rows = [
        measure(item.id, item, data, arguments.repeat)
        for item in corpus()
        if not item.toy
    ]
    sweep = [
        measure(f"sweep/{size}", sweep_field(size), data, arguments.repeat)
        for size in SWEEP
    ]
    report = {
        "commit": _commit(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cpus": os.cpu_count(),
        "repeat": arguments.repeat,
        "corpus": rows,
        "sweep": sweep,
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (root / "results.md").write_text(_markdown(report), encoding="utf-8")
    print(_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

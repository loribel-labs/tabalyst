# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The benchmark matrix of the specification (17.2), one isolated process per run.

    python benchmarks/final_matrix.py --root D:/GIT.test/tabalyst/bench/matrix \
        --out D:/GIT.test/tabalyst/artifacts/lot11-matrix --repeat 3

It writes the deterministic files of the matrix under ``--root`` when they are
missing (never in the checkout), then measures each case with the tasks of
``scan_json_baseline.py``: ``scan``, ``report`` (with the second pass the planner
chooses), ``report-off`` (without it) and ``smart-sample``. ``--limit`` keeps the
cases that fit in 1,000,000 rows and 100 columns, the profile used until the
complete matrix is run (2,000,000 rows, 500 and 1,000 columns, and every task of
every case). Existing files named on the command line (the realistic insurance
file, ``worst-width``, ``long-text``, ``many-lengths``) are added as they are.
"""

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import matrix_layouts
import run_baseline
import scan_json_baseline as baseline

# (case, layout, rows, options). The options of the layouts are ``columns`` and
# ``distinct``. ``K`` is the size of the bottom-k sample (10,000).
LIMITED: tuple[tuple[str, str, int, dict], ...] = (
    ("low-cardinality", "low-cardinality", 1_000_000, {}),
    ("transition-K-1", "transition", 200_000, {"distinct": 9_999}),
    ("transition-K", "transition", 200_000, {"distinct": 10_000}),
    ("transition-K+1", "transition", 200_000, {"distinct": 10_001}),
    ("transition-T", "transition", 200_000, {"distinct": 100_000}),
    ("high-cardinality", "high-cardinality", 1_000_000, {}),
    ("short-ids", "short-ids", 1_000_000, {}),
    ("repeated-550k", "repeated", 550_000, {}),
    ("wide-100", "wide", 200_000, {"columns": 100}),
    ("growth-250k", "high-cardinality", 250_000, {}),
    ("growth-500k", "high-cardinality", 500_000, {}),
    ("normalization-clean", "normalization-clean", 500_000, {}),
    ("normalization-effect", "normalization-effect", 500_000, {}),
)
TASKS = ("scan", "report-off", "report", "smart-sample")


def _ensure(root: Path, case: str, layout: str, rows: int, options: dict) -> Path:
    path = root / f"{case}.csv"
    if not path.exists():
        matrix_layouts.write_layout(layout, rows, path, **options)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--case", action="append", help="Only these cases.")
    parser.add_argument("--task", action="append", choices=baseline.TASKS)
    parser.add_argument("--existing", nargs="*", type=Path, default=[])
    args = parser.parse_args()
    checkout = Path(__file__).resolve().parents[1]
    for folder in (args.root.resolve(), args.out.resolve()):
        if checkout in folder.parents:
            parser.error("--root and --out must be outside the checkout (see AGENTS.md)")
    args.out.mkdir(parents=True, exist_ok=True)
    work = args.out / "work"
    work.mkdir(exist_ok=True)

    files: list[tuple[str, Path]] = [(path.stem, path) for path in args.existing]
    for case, layout, rows, options in LIMITED:
        if args.case and case not in args.case:
            continue
        files.append((case, _ensure(args.root, case, layout, rows, options)))

    results: list[dict] = []
    lines = [
        "| Case | Rows | Size (MB) | Task | Median (s) | Range (s) | Peak (MB) | Phases (s) |",
        "| --- | ---: | ---: | --- | ---: | --- | ---: | --- |",
    ]
    print("\n".join(lines), flush=True)
    for case, path in files:
        known_rows = 0
        for task in args.task or TASKS:
            runs = [baseline._measure(task, path, work) for _ in range(args.repeat)]
            median, low, high = baseline._summary(runs, "seconds")
            peak = statistics.median(run["peak_bytes"] for run in runs) / 1024**2
            rows = runs[0]["rows"] or runs[0].get("records_read") or known_rows
            known_rows = rows
            phases = ""
            timings = runs[0].get("timings") or runs[0].get("scan_timings")
            if task == "smart-sample":
                timings = runs[0].get("selection_timings")
            if timings:
                phases = ", ".join(
                    f"{name} {statistics.median(run.get('timings', run.get('scan_timings', run.get('selection_timings')))[name] for run in runs):.2f}"
                    for name in timings
                )
            if task in ("report", "report-off"):
                second = statistics.median(run["second_pass_seconds"] or 0 for run in runs)
                phases = f"scan {statistics.median(run['scan_seconds'] for run in runs):.2f}, second pass {second:.2f}"
            line = (
                f"| {case} | {rows:,} | {path.stat().st_size / 1024**2:,.1f} | {task} | "
                f"{median:.2f} | {low:.2f}-{high:.2f} | {peak:,.0f} | {phases} |"
            )
            lines.append(line)
            print(line, flush=True)
            results.append({"case": case, "size_bytes": path.stat().st_size, "task": task, "runs": runs})
            (args.out / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    environment = run_baseline._environment() + [f"- Repeats per measurement: {args.repeat}"]
    (args.out / "results.md").write_text("\n".join(lines + [""] + environment) + "\n", encoding="utf-8")
    print("\n".join(environment))


if __name__ == "__main__":
    main()

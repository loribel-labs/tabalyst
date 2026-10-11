# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Variants of the same task, alternated in one session (PERF-06, lot 12).

Each run is a fresh interpreter of ``scan_json_baseline.py --child``; see ``USAGE``.
"""

import argparse
import json
import os
import statistics
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# A variant is ``label=tree`` (a checkout, its ``src`` first on ``PYTHONPATH``),
# optionally followed by ``;NAME=value`` environment settings. The machine drifts
# by 20% between sessions (benchmarks.md, lot 0): only runs alternated here are
# compared, and this checkout's script measures every variant, so a base commit
# needs no copy of it. ``results.md`` gives the median and the paired ratios
# against the first variant.
USAGE = """
    python benchmarks/interleave.py --out D:/GIT.test/tabalyst/artifacts/lot12/il
        --variant base=D:/GIT.test/tabalyst/worktrees/baseline-0acf126
        --variant head=. --variant head4=.;TABALYST_BENCH_WORKERS=4
        --task scan --repeat 3 D:/GIT.test/tabalyst/csv/insurance-combined.csv
"""


def _parse(spec: str) -> tuple[str, Path, dict[str, str]]:
    label, _, rest = spec.partition("=")
    tree, *settings = rest.split(";")
    environment = dict(item.split("=", 1) for item in settings if item)
    return label, Path(tree).resolve(), environment


def _run(task: str, path: Path, work: Path, tree: Path, extra: dict[str, str]) -> dict:
    # The benchmarks folder first: scan workers import run_baseline from it.
    paths = os.pathsep.join([str(tree / "src"), str(HERE)])
    environment = {
        **os.environ,
        "PYTHONPATH": paths,
        "TABALYST_BASELINE_WORK": str(work),
        **extra,
    }
    completed = subprocess.run(
        [sys.executable, str(HERE / "scan_json_baseline.py"), "--child", task, str(path)],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    return json.loads(completed.stdout.strip().splitlines()[-1])


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog=USAGE,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--variant", action="append", required=True)
    parser.add_argument("--task", action="append", default=None)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    if HERE.parent in out.parents:
        parser.error("--out must be outside the checkout (see AGENTS.md)")
    out.mkdir(parents=True, exist_ok=True)
    work = out / "work"
    work.mkdir(exist_ok=True)
    variants = [_parse(spec) for spec in args.variant]

    results: list[dict] = []
    lines = [
        "| File | Task | Variant | Seconds (runs) | Median (s) | Paired ratio | Peak median (MB) |",
        "| --- | --- | --- | --- | ---: | ---: | ---: |",
    ]
    for path in args.files:
        for task in args.task or ["scan"]:
            runs: dict[str, list[dict]] = {label: [] for label, _, _ in variants}
            for _ in range(args.repeat):
                for label, tree, extra in variants:
                    run = _run(task, path, work, tree, extra)
                    runs[label].append(run)
                    print(label, path.name, task, round(run["seconds"], 2), flush=True)
            first = variants[0][0]
            for label, _, _ in variants:
                seconds = [run["seconds"] for run in runs[label]]
                ratios = [
                    run["seconds"] / base["seconds"] - 1
                    for run, base in zip(runs[label], runs[first], strict=True)
                ]
                peak = statistics.median(run["peak_bytes"] for run in runs[label]) / 1024**2
                paired = "" if label == first else f"{statistics.median(ratios):+.1%}"
                lines.append(
                    f"| {path.name} | {task} | {label} | "
                    f"{', '.join(f'{s:.2f}' for s in seconds)} | "
                    f"{statistics.median(seconds):.2f} | {paired} | {peak:,.0f} |"
                )
            results.append({"file": path.name, "task": task, "runs": runs})
            (out / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
            (out / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Baseline of the Scan and JSON work (lot 0), one isolated process per run.

    python benchmarks/scan_json_baseline.py D:/GIT.test/tabalyst/csv/insurance-combined.csv

Each measurement runs in a fresh interpreter. Results are written under the
external artifacts root, never in the checkout, as ``results.json`` (every run)
and ``results.md`` (medians and spread). Tasks:

- ``csv-read``: the floor, one ``csv.reader`` pass (PERF-04).
- ``scan``: ``tabalyst.scan()`` with defaults, phases from ``run.timings``.
- ``scan-single``: the same in one process.
- ``scan-t10000``: ``limits.max_distinct_per_field = 10000`` (decision P1),
  to measure what the lower tracking limit costs and saves.
- ``report``: ``generate_reports()`` from the source, scan included.
- ``report-off``: the same with ``deep.mode`` off, so without the second pass: the
  report of the overhead measurements (lot 11, F07).
- ``smart-sample`` (lot 11): ``tabalyst sample --sample-method smart`` of 0.5% of the
  rows, with the Scan made first (not timed): only the selection is timed.
- ``report-from-scan``: ``generate_reports(from_scan=True)`` on a scan document
  written beforehand: only the time to build and render the report.

Memory is the peak working set of the process plus the peak of each worker,
an upper bound of the memory used at once (see ``run_baseline.py``).
"""

import argparse
import json
import os
import statistics
import sys
import tempfile
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_baseline

DEFAULT_OUT = Path("D:/GIT.test/tabalyst/artifacts/scan-json-lot0")
TASKS = (
    "csv-read",
    "scan",
    "scan-single",
    "scan-t10000",
    "report",
    "report-off",
    "report-from-scan",
    "smart-sample",
)
THRESHOLD_FIELD_RANGE = (10_000, 100_000)


def _limited_envelopes(node, path="", found=None) -> dict[str, int]:
    """Count the ``limited`` envelopes of a scan document by key path."""
    found = {} if found is None else found
    if isinstance(node, dict):
        if node.get("status") == "limited":
            found[path] = found.get(path, 0) + 1
        for key, value in node.items():
            _limited_envelopes(value, f"{path}.{key}" if path else key, found)
    elif isinstance(node, list):
        for item in node:
            _limited_envelopes(item, path, found)
    return found


def _scan_extras(result) -> dict:
    document = result.model_dump(mode="json", by_alias=True)
    text = json.dumps(document, ensure_ascii=False, indent=2)
    low, high = THRESHOLD_FIELD_RANGE
    between = []
    for dataset in document["datasets"]:
        for item in dataset["fields"]:
            cardinality = item["values"]["cardinality"]
            if (
                cardinality["status"] == "complete"
                and low < cardinality["value"] <= high
            ):
                between.append(
                    {"field": item["display"], "distinct": cardinality["value"]}
                )
    return {
        "scan_json_bytes": len(text.encode("utf-8")),
        "timings": document["run"]["timings"],
        "run_seconds": document["run"]["duration_seconds"],
        "workers": document["run"]["workers"],
        "main_peak_bytes": document["run"]["peak_memory_bytes"],
        "limited_envelopes": _limited_envelopes(document["datasets"]),
        "fields_between_10k_and_100k_distinct": between,
    }


def _profile_size(folder: Path) -> int:
    """Size of the report profile: the JSON next to the HTML, not the history."""
    profiles = [
        item for item in folder.glob("*.json") if item.name != "executions.json"
    ]
    return profiles[0].stat().st_size


def _second_pass(folder: Path) -> dict:
    """What the second pass of a report recorded: its time, reading and work."""
    profile = next(item for item in folder.glob("*.json") if item.name != "executions.json")
    document = json.loads(profile.read_text(encoding="utf-8"))
    analyses = document.get("analyses") or {}
    run = (analyses.get("deep") or {}).get("run") or {}
    return {
        "scan_seconds": document["run"]["duration_seconds"],
        "scan_timings": document["run"]["timings"],
        "second_pass_outcome": analyses.get("outcome"),
        "second_pass_seconds": run.get("duration_seconds"),
        "second_pass_reading": (run.get("timings") or {}).get("reading"),
        "analyses": run.get("executed", 0) + run.get("reused", 0),
        "cells_read": run.get("cells_read"),
        "second_pass_peak_bytes": run.get("peak_memory_bytes"),
        "report_processing_seconds": document["report"]["processing_seconds"],
    }


def _smart_extras(report: Path) -> dict:
    document = json.loads(report.read_text(encoding="utf-8"))
    coverage = document["coverage"]
    return {
        "targets": coverage["defined"],
        "evaluable": coverage["evaluable"],
        "covered": coverage["covered"],
        "weighted_share": coverage["weighted"]["share"],
        "verification_disagreed": len(coverage["verification"]["disagreed"]),
        "selection_timings": document["run"]["timings"],
        "records_read": document["run"]["records_read"],
        "cells_read": document["run"]["cells_read"],
        "pool_bytes": document["selection"]["pool"]["peak_bytes"],
        "candidate_rows": document["selection"]["pool"]["candidate_rows"],
        "sample_rows": document["selection"]["rows"],
    }


def _run_task(task: str, path: Path, work: Path) -> tuple[int, object, float | None]:
    """Return rows, extra data (or a function that computes it after the
    measurement) and, when only a part is timed, its seconds."""
    if task == "csv-read":
        import csv

        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            return sum(1 for _ in csv.reader(stream, strict=True)) - 1, {}, None
    from tabalyst import ScanConfig, generate_reports, generate_scans, scan

    if task in ("scan", "scan-single", "scan-t10000"):
        config = None
        if task == "scan-t10000":
            config = ScanConfig.model_validate(
                {"limits": {"max_distinct_per_field": 10000}}
            )
        workers = 1 if task == "scan-single" else None
        if workers is None and os.environ.get("TABALYST_BENCH_WORKERS"):
            # Interleaved studies of the worker count (benchmarks/interleave.py).
            workers = int(os.environ["TABALYST_BENCH_WORKERS"])
        result = scan(path, config=config, workers=workers)
        return result.scope.records_analyzed, lambda: _scan_extras(result), None
    run_baseline._isolated_storage()
    if task in ("report", "report-off"):
        config = None
        if task == "report-off":
            (work / "config").mkdir(exist_ok=True)
            config = work / "config" / "off.json"
            config.write_text(json.dumps({"deep": {"mode": "off"}}), encoding="utf-8")
        started = perf_counter()
        generate_reports([path], output_dir=work, config_path=config, force=True)
        seconds = perf_counter() - started
        return 0, {"report_json_bytes": _profile_size(work), **_second_pass(work)}, seconds
    if task == "smart-sample":
        from tabalyst import execute_smart_samples, prepare_smart_samples

        preparation = prepare_smart_samples([path], percent=0.5, output_dir=work, force=True)
        started = perf_counter()
        execute_smart_samples(preparation, confirmed=True)
        seconds = perf_counter() - started
        [job] = preparation.jobs
        return 0, _smart_extras(job.report), seconds
    if task == "report-from-scan":
        scans = work / "scans"
        generate_scans([path], output_dir=scans, force=True)
        document = next(scans.glob("*.scan.json"))
        reports = work / "reports"
        started = perf_counter()
        generate_reports([document], output_dir=reports, from_scan=True, force=True)
        seconds = perf_counter() - started
        return (
            0,
            {
                "scan_json_bytes": document.stat().st_size,
                "report_json_bytes": _profile_size(reports),
            },
            seconds,
        )
    raise ValueError(f"Unknown task: {task}")


def _child(task: str, path: Path) -> None:
    if task != "csv-read":
        import tabalyst.service  # noqa: F401  Import cost is excluded from the timing.

        run_baseline._count_worker_peaks()
    peaks = tempfile.mkdtemp()
    os.environ[run_baseline._PEAKS] = peaks
    work = Path(tempfile.mkdtemp(dir=os.environ.get("TABALYST_BASELINE_WORK")))
    start_memory, _ = run_baseline._memory_bytes()
    started = perf_counter()
    rows, outcome, timed = _run_task(task, path, work)
    seconds = timed if timed is not None else perf_counter() - started
    # Read before the extras, which serialize the whole document.
    _, peak = run_baseline._memory_bytes()
    extras = outcome() if callable(outcome) else outcome
    peak += sum(int(item.read_text()) for item in Path(peaks).glob("*.peak"))
    print(
        json.dumps(
            {
                "rows": rows,
                "seconds": seconds,
                "start_bytes": start_memory,
                "peak_bytes": peak,
                **extras,
            }
        )
    )


def _measure(task: str, path: Path, work: Path) -> dict:
    import subprocess

    completed = subprocess.run(
        [sys.executable, __file__, "--child", task, str(path)],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "TABALYST_BASELINE_WORK": str(work)},
    )
    return json.loads(completed.stdout.strip().splitlines()[-1])


def _summary(runs: list[dict], key: str) -> tuple[float, float, float]:
    values = [run[key] for run in runs]
    return statistics.median(values), min(values), max(values)


def main() -> None:
    if len(sys.argv) == 4 and sys.argv[1] == "--child":
        _child(sys.argv[2], Path(sys.argv[3]))
        return

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--task", action="append", choices=TASKS)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    out = args.out.resolve()
    if Path(__file__).resolve().parents[1] in out.parents:
        parser.error("--out must be outside the checkout (see AGENTS.md)")
    out.mkdir(parents=True, exist_ok=True)
    work = out / "work"
    work.mkdir(exist_ok=True)

    everything: list[dict] = []
    lines = [
        "| File | Task | Median (s) | Min (s) | Max (s) | Peak median (MB) | Phases (s) |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    print("\n".join(lines))
    for path in args.files:
        for task in args.task or TASKS:
            runs = [_measure(task, path, work) for _ in range(args.repeat)]
            everything.append(
                {
                    "file": path.name,
                    "size_bytes": path.stat().st_size,
                    "task": task,
                    "runs": runs,
                }
            )
            median, low, high = _summary(runs, "seconds")
            peak = statistics.median(run["peak_bytes"] for run in runs) / 1024**2
            phases = ""
            if "timings" in runs[0]:
                keys = runs[0]["timings"]
                phases = ", ".join(
                    f"{name} {statistics.median(run['timings'][name] for run in runs):.2f}"
                    for name in keys
                )
            line = (
                f"| {path.name} | {task} | {median:.2f} | {low:.2f} | {high:.2f} | "
                f"{peak:,.0f} | {phases} |"
            )
            lines.append(line)
            print(line, flush=True)
            (out / "results.json").write_text(
                json.dumps(everything, indent=2), encoding="utf-8"
            )
    environment = run_baseline._environment()
    environment.append(f"- Repeats per measurement: {args.repeat}")
    (out / "results.md").write_text(
        "\n".join(lines + [""] + environment) + "\n", encoding="utf-8"
    )
    print("\n".join(environment))


if __name__ == "__main__":
    main()

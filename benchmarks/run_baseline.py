"""Measure Tabalyst engines on benchmark files, one isolated process per run.

    python benchmarks/run_baseline.py benchmarks/data/synthetic-100k.csv --repeat 3

Each measurement runs in a fresh interpreter so peak memory is not inherited
from a previous run. Results are printed as a Markdown table followed by the
environment needed to reproduce them.
"""

import argparse
import csv
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from time import perf_counter

TASKS = {
    "csv-read": "Stream every record with csv.reader (lower bound for a Python reader)",
    "report-engine": "Current report engine: tabalyst.analyze_csv() with defaults",
}


def _memory_bytes() -> tuple[int, int]:
    """Return (current, peak) resident memory of this process in bytes."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        # Explicit types keep the 64-bit process handle from being truncated.
        get_process = ctypes.windll.kernel32.GetCurrentProcess
        get_process.restype = wintypes.HANDLE
        get_info = ctypes.windll.psapi.GetProcessMemoryInfo
        get_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        get_info.restype = wintypes.BOOL
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        if not get_info(get_process(), ctypes.byref(counters), counters.cb):
            raise OSError(ctypes.get_last_error(), "GetProcessMemoryInfo failed")
        return counters.WorkingSetSize, counters.PeakWorkingSetSize

    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak = peak if sys.platform == "darwin" else peak * 1024
    return peak, peak


def _run_task(task: str, path: Path) -> int:
    if task == "csv-read":
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            return sum(1 for _ in csv.reader(stream, strict=True)) - 1
    if task == "report-engine":
        from tabalyst import AnalysisConfig, analyze_csv

        return analyze_csv(path, AnalysisConfig()).summary.row_count
    raise ValueError(f"Unknown task: {task}")


def _child(task: str, path: Path) -> None:
    if task == "report-engine":
        import tabalyst  # noqa: F401  Import cost is excluded from the timing.
    start_memory, _ = _memory_bytes()
    started = perf_counter()
    rows = _run_task(task, path)
    seconds = perf_counter() - started
    _, peak_memory = _memory_bytes()
    print(
        json.dumps(
            {
                "rows": rows,
                "seconds": seconds,
                "start_bytes": start_memory,
                "peak_bytes": peak_memory,
            }
        )
    )


def _measure(task: str, path: Path) -> dict:
    completed = subprocess.run(
        [sys.executable, __file__, "--child", task, str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout.strip().splitlines()[-1])


def _environment() -> list[str]:
    try:
        from tabalyst import __version__ as version
    except ImportError:
        version = "not installed"
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
    return [
        f"- Tabalyst {version}, commit {commit}",
        f"- Python {platform.python_version()} ({platform.python_implementation()})",
        f"- {platform.platform()}",
        f"- Processor: {platform.processor() or 'unknown'}, {os.cpu_count()} logical CPUs",
    ]


def main() -> None:
    if len(sys.argv) == 4 and sys.argv[1] == "--child":
        _child(sys.argv[2], Path(sys.argv[3]))
        return

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument(
        "--task",
        action="append",
        choices=sorted(TASKS),
        help="Task to measure; repeat the option for several tasks (default: all).",
    )
    parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args()

    print("| File | Rows | Size (MB) | Task | Best time (s) | Rows/s | Peak memory (MB) | Growth (MB) |")
    print("| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: |")
    for path in args.files:
        size_mb = path.stat().st_size / 1024**2
        for task in args.task or sorted(TASKS):
            runs = [_measure(task, path) for _ in range(args.repeat)]
            best = min(run["seconds"] for run in runs)
            peak = max(run["peak_bytes"] for run in runs) / 1024**2
            growth = max(run["peak_bytes"] - run["start_bytes"] for run in runs) / 1024**2
            rows = runs[0]["rows"]
            print(
                f"| {path.name} | {rows:,} | {size_mb:,.1f} | {task} | {best:,.2f} | "
                f"{rows / best:,.0f} | {peak:,.0f} | {growth:,.0f} |",
                flush=True,
            )
    print()
    print("\n".join(_environment()))
    print(f"- Repeats per measurement: {args.repeat}")


if __name__ == "__main__":
    main()

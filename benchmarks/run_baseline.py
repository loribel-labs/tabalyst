# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Measure Tabalyst engines on benchmark files, one isolated process per run.

    python benchmarks/run_baseline.py benchmarks/data/synthetic-100k.csv --repeat 3

Each measurement runs in a fresh interpreter so peak memory is not inherited
from a previous run. Results are printed as a Markdown table followed by the
environment needed to reproduce them. Scans may use worker processes: their
peak memory is added to the peak of the measuring process, an upper bound of
the memory used at once.
"""

import argparse
import csv
import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path
from time import perf_counter

TASKS = {
    "csv-read": "Stream every record with csv.reader (lower bound for a Python reader)",
    "report-engine": "Report engine: tabalyst.analyze_csv() with defaults (Scan since lot 5a)",
    "scan": "Tabalyst Scan: tabalyst.scan() with defaults, workers for large files",
    "scan-single": "Tabalyst Scan in one process: tabalyst.scan(workers=1)",
}
# Tasks added with JSON Inspect (lot JI-8); run them with ``--task`` on JSON or
# JSONL sources. The default keeps the four historical tasks.
INSPECT_TASKS = {
    "sha256": "Full SHA-256 of the source (scan_reuse.file_sha256)",
    "events": "JSON only: ijson event pass of the Scan reader, nothing else",
    "inspect": "Tabalyst Inspect: inspect_source() (event pass, hash, detection)",
    "resolve-cold": "resolve_interpretation() with an empty storage (inspects, writes the cache)",
    "resolve-warm": "resolve_interpretation() with the cache written by a first call",
    "report-cold": "generate_reports() with an empty storage (resolution, scan, report)",
    "report-reuse": "generate_reports() again: stored scan reused, report rebuilt",
    "jsonl-parse-hook": "JSONL only: json.loads per line with the duplicate-key hook",
    "jsonl-parse-plain": "JSONL only: json.loads per line without the hook (same Decimal)",
}
TASKS.update(INSPECT_TASKS)
DEFAULT_TASKS = ("csv-read", "report-engine", "scan", "scan-single")
# Directory where scan workers record their peak memory, set by ``_child``.
_PEAKS = "TABALYST_BENCHMARK_PEAKS"


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


def _record_peak() -> None:
    """At the exit of a scan worker, record its peak memory."""
    directory = os.environ.get(_PEAKS)
    if directory:
        peak = _memory_bytes()[1]
        Path(directory, f"{os.getpid()}.peak").write_text(str(peak), encoding="ascii")


def _count_worker_peaks() -> None:
    """Make scan workers record their peak memory when they exit."""
    from tabalyst.scanner import workers

    workers._BOOTSTRAP = workers._BOOTSTRAP.replace(
        "main()",
        "import atexit, run_baseline; atexit.register(run_baseline._record_peak); main()",
    )


def _isolated_storage() -> None:
    """Point the shared storage at an empty folder, so no cache is inherited."""
    os.environ["TABALYST_HOME"] = tempfile.mkdtemp()


def _run_inspect_task(task: str, path: Path) -> tuple[int, float | None]:
    """Run a JI-8 task; return the count and, when only a part is timed, its seconds."""
    if task == "sha256":
        from tabalyst.scan_reuse import file_sha256

        file_sha256(path)
        return 1, None
    if task == "events":
        from tabalyst.scanner.readers.json_reader import JsonEvents

        count = 0
        for _ in JsonEvents(path):
            count += 1
        return count, None
    if task == "inspect":
        from tabalyst.inspector.json_inspect import inspect_source

        document = inspect_source(path)
        return sum(item.elements for item in document.detection.candidates), None
    if task in ("resolve-cold", "resolve-warm"):
        from tabalyst.inspector.resolution import resolve_interpretation
        from tabalyst.projects.location import StorageLocation

        _isolated_storage()
        location = StorageLocation.local()
        if task == "resolve-warm":
            resolve_interpretation(path, location=location)
        started = perf_counter()
        resolve_interpretation(path, location=location)
        return 1, perf_counter() - started
    if task in ("report-cold", "report-reuse"):
        from tabalyst import generate_reports

        _isolated_storage()
        out = Path(tempfile.mkdtemp())
        if task == "report-reuse":
            generate_reports([path], output_dir=out, force=True)
        started = perf_counter()
        generate_reports([path], output_dir=out, force=True)
        return 1, perf_counter() - started
    if task in ("jsonl-parse-hook", "jsonl-parse-plain"):
        import json as json_module
        from decimal import Decimal

        from tabalyst.scanner.readers.jsonl_reader import _object, _reject_constant

        hook = _object if task == "jsonl-parse-hook" else None
        count = 0
        with path.open("rb") as stream:
            for line in stream:
                if line.strip():
                    json_module.loads(
                        line,
                        parse_float=Decimal,
                        parse_constant=_reject_constant,
                        object_pairs_hook=hook,
                    )
                    count += 1
        return count, None
    raise ValueError(f"Unknown task: {task}")


def _run_task(task: str, path: Path) -> int | tuple[int, float | None]:
    if task in INSPECT_TASKS:
        return _run_inspect_task(task, path)
    if task == "csv-read":
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            return sum(1 for _ in csv.reader(stream, strict=True)) - 1
    if task in ("scan", "scan-single"):
        from tabalyst import scan

        result = scan(path, workers=1 if task == "scan-single" else None)
        return result.scope.records_analyzed
    if task == "report-engine":
        from tabalyst import analyze_csv

        return sum(
            dataset.summary.row_count for dataset in analyze_csv(path).datasets
        )
    raise ValueError(f"Unknown task: {task}")


def _child(task: str, path: Path) -> None:
    if task != "csv-read":
        import tabalyst.service  # noqa: F401  Import cost is excluded from the timing.

        _count_worker_peaks()
    peaks = tempfile.mkdtemp()
    os.environ[_PEAKS] = peaks
    start_memory, _ = _memory_bytes()
    started = perf_counter()
    outcome = _run_task(task, path)
    seconds = perf_counter() - started
    rows = outcome
    if isinstance(outcome, tuple):
        rows, timed = outcome
        seconds = timed if timed is not None else seconds
    _, peak_memory = _memory_bytes()
    peak_memory += sum(int(item.read_text()) for item in Path(peaks).glob("*.peak"))
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
        for task in args.task or DEFAULT_TASKS:
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

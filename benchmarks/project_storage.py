# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Private d1 measurements, one source/stage in a fresh interpreter per run.

python benchmarks/project_storage.py SOURCE --stage artifacts/storage-measure-1
The stage must not exist. Nothing is published as a project. Full d3 query,
million-record and old/new-generation disk benchmarks remain separate work.
"""

import argparse
import json
import platform
import threading
from pathlib import Path
from time import perf_counter

from run_baseline import _memory_bytes

from tabalyst.projects import _staging
from tabalyst.projects._schema import DUCKDB_VERSION, STORAGE_COMPATIBILITY
from tabalyst.projects._staging import _file_hash, build_staging
from tabalyst.projects._validation import validate_staging
from tabalyst.projects.identity import new_project_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--memory-limit", default="256MB")
    parser.add_argument("--batch-rows", type=int, default=_staging.BATCH_ROWS)
    args = parser.parse_args()
    if args.batch_rows < 1:
        parser.error("--batch-rows must be positive")
    _staging.BATCH_ROWS = args.batch_rows
    binding = {
        "project_id": new_project_id(),
        "workspace_id": "local",
        "generation_id": new_project_id(),
    }
    peaks = {"staging_bytes": 0, "spill_bytes": 0}
    stop = threading.Event()

    def sample_disk():
        while not stop.is_set():
            total = spill = 0
            for path in args.stage.rglob("*"):
                try:
                    if path.is_file():
                        size = path.stat().st_size
                        total += size
                        if "spill" in path.relative_to(args.stage).parts:
                            spill += size
                except FileNotFoundError:
                    pass  # DuckDB can remove a spill file between samples.
            peaks["staging_bytes"] = max(total, peaks["staging_bytes"])
            peaks["spill_bytes"] = max(spill, peaks["spill_bytes"])
            stop.wait(0.01)

    monitor = threading.Thread(target=sample_disk, daemon=True)
    monitor.start()
    started = perf_counter()
    try:
        staged = build_staging(
            args.source,
            args.stage,
            **binding,
            workers=1,
            memory_limit=args.memory_limit,
        )
    finally:
        stop.set()
        monitor.join()
    elapsed = perf_counter() - started
    started = perf_counter()
    validate_staging(staged.database_path, staged.scan_path, staged.result, **binding)
    reopen = perf_counter() - started
    started = perf_counter()
    assert _file_hash(staged.database_path) == staged.database_sha256
    hash_seconds = perf_counter() - started
    print(
        json.dumps(
            {
                "source": str(args.source),
                "records": staged.result.scope.records_analyzed,
                "build_seconds": round(elapsed, 3),
                "scan_with_hook_seconds": staged.result.duration_seconds,
                "reopen_validation_seconds": round(reopen, 3),
                "database_hash_seconds": round(hash_seconds, 3),
                "peak_process_bytes": _memory_bytes()[1],
                "database_bytes": staged.database_path.stat().st_size,
                "scan_bytes": staged.scan_path.stat().st_size,
                "sampled_peak_disk": peaks,
                "memory_limit": args.memory_limit,
            "batch_rows": args.batch_rows,
            "batch_bytes": _staging.BATCH_BYTES,
                "duckdb": DUCKDB_VERSION,
                "storage_target": STORAGE_COMPATIBILITY,
                "platform": platform.platform(),
                "python": platform.python_version(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

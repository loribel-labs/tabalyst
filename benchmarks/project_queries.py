# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Private d3 measurements in fresh processes, synthetic data only.

python benchmarks/project_queries.py --case csv --rows 1000000 --root artifacts/d3-csv --repeat 2
python benchmarks/project_queries.py --case json --rows 100000 --root artifacts/d3-json
An existing --root is rejected. No public demo or source is modified. On
failure, retained staging and JSON evidence remain for inspection; no retry
with a larger budget or automatic cleanup is performed.
"""

import argparse
import csv
import json
import platform
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from time import perf_counter

from run_baseline import _memory_bytes

from tabalyst.projects import StorageLocation, _staging
from tabalyst.projects._generation import open_generation
from tabalyst.projects._publication import publish_scan
from tabalyst.projects._queries import materialize_values, records_page
from tabalyst.projects._query_budget import QueryBudget
from tabalyst.projects._schema import DUCKDB_VERSION, STORAGE_COMPATIBILITY
from tabalyst.projects._staging import _file_hash
from tabalyst.scanner import ScanConfig

MIB = 1024 * 1024


def generate(path, case, rows):
    """Include missing, duplicate, variant and high-cardinality populations."""
    forms = (" É  CAT ", "É  CAT", "é cat", "e cat")
    if case in ("csv", "wide", "long"):
        width = 100 if case == "wide" else 3
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(
                ["id", "variant", "missing", *[f"c{i}" for i in range(width - 3)]]
            )
            for i in range(rows):
                # Adjacent pairs compare equal as records; each group has
                # one retained first occurrence, unlike normalized variants.
                key = i // 2
                text = forms[key % 4]
                if case == "long":
                    text += str(key) * 2000
                writer.writerow(
                    [
                        key,
                        text,
                        "" if key % 3 == 0 else "ok",
                        *[str((key + c) % 17) for c in range(width - 3)],
                    ]
                )
    else:
        with path.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write("[")
            for i in range(rows):
                key = i // 2
                obj = {
                    "id": key,
                    "variant": forms[key % 4],
                    "missing": None if key % 3 == 0 else "ok",
                }
                if case == "deep":
                    nested = {"value": forms[key % 4]}
                    for _ in range(30):
                        nested = {"child": nested}
                    obj["nested"] = nested
                else:
                    obj["items"] = [{"v": key}, {}, {"v": None}]
                if i:
                    stream.write(",")
                stream.write(json.dumps(obj, ensure_ascii=False))
            stream.write("]")


class Monitor:
    """10ms samples are lower bounds on transient disk/RSS peaks."""

    def __init__(self, storage):
        self.storage = storage
        self.phase = "startup"
        self.samples = {}
        self.at_disk_peak = {}
        self.old_generation_id = None
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def sample(self):
        sizes = {
            "total": 0,
            "generations": 0,
            "old": 0,
            "new": 0,
            "staging": 0,
            "cache": 0,
            "spill": 0,
        }
        for path in self.storage.rglob("*"):
            try:
                if not path.is_file():
                    continue
                size = path.stat().st_size
            except FileNotFoundError:
                continue
            parts = path.relative_to(self.storage).parts
            sizes["total"] += size
            if "generations" in parts:
                generation_id = parts[parts.index("generations") + 1]
                sizes["old" if generation_id == self.old_generation_id else "new"] += (
                    size
                )
            for label, component in (
                ("generations", "generations"),
                ("staging", ".staging"),
                ("cache", "cache"),
                ("spill", "spill"),
            ):
                if component in parts:
                    sizes[label] += size
        sizes["rss"] = _memory_bytes()[0]
        phase = self.samples.setdefault(self.phase, {k: 0 for k in sizes})
        for key, value in sizes.items():
            phase[key] = max(phase[key], value)
        if sizes["total"] >= self.at_disk_peak.get(self.phase, {}).get("total", -1):
            self.at_disk_peak[self.phase] = sizes.copy()

    def run(self):
        while not self.stop.is_set():
            self.sample()
            self.stop.wait(0.01)

    def close(self):
        self.stop.set()
        self.thread.join()
        self.sample()


def paginate(method):
    cursor, count, pages = None, 0, 0
    started = perf_counter()
    first_seconds = None
    while True:
        page = method(size=1000, cursor=cursor)
        if first_seconds is None:
            first_seconds = perf_counter() - started
        count += len(page.items)
        pages += 1
        cursor = page.next_cursor
        if cursor is None:
            if page.reason != "sensitive_values_hidden":
                assert count == page.total
            return {
                "status": page.status,
                "reason": page.reason,
                "retained_occurrences": page.scope.retained_occurrences,
                "omitted_occurrences": page.scope.omitted_occurrences,
                "count": count,
                "pages": pages,
                "first_seconds": round(first_seconds, 4),
                "all_seconds": round(perf_counter() - started, 4),
            }


def measure(args):
    args.root.mkdir(parents=True, exist_ok=False)
    source = args.root / (
        "source.csv" if args.case in ("csv", "wide", "long") else "source.json"
    )
    if args.source is None:
        generate(source, args.case, args.rows)
    else:
        shutil.copyfile(args.source, source)
    location = StorageLocation(args.root / "storage")
    # Intentionally exhausted Scan budgets: complete memberships and a
    # separately capped value catalog must keep their own explicit scope.
    config = ScanConfig.model_validate(
        {
            "limits": {
                "max_distinct_per_field": 2000,
                "max_tracked_values": 20000,
                "max_tracked_records": 1000,
                "max_listed_records": 0,
                "max_listed_frequencies": 0,
                "max_variant_groups": 0,
            }
        }
    )
    reader_budget = QueryBudget(
        memory_bytes=args.reader_memory_mib * MIB, spill_bytes=args.spill_mib * MIB
    )
    query_budget = QueryBudget(
        memory_bytes=args.query_memory_mib * MIB, spill_bytes=args.spill_mib * MIB
    )
    monitor = Monitor(location.root)
    monitor.thread.start()
    report = {
        "case": args.case,
        "rows": args.rows,
        "source_bytes": source.stat().st_size,
        "memory_mib": args.memory_mib,
        "reader_memory_mib": args.reader_memory_mib,
        "query_memory_mib": args.query_memory_mib,
        "spill_mib": args.spill_mib,
        "duckdb": DUCKDB_VERSION,
        "storage_target": STORAGE_COMPATIBILITY,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "phases": {},
    }

    def timed(name, action):
        monitor.phase = name
        started = perf_counter()
        try:
            return action()
        finally:
            report["phases"][name] = round(perf_counter() - started, 4)

    def instrument(owner, name):
        original = getattr(owner, name)

        def measured(*positional, **keywords):
            outer = monitor.phase
            phase = f"{outer}:{name}"
            monitor.phase = phase
            started = perf_counter()
            try:
                return original(*positional, **keywords)
            except Exception:
                report.setdefault("failed_phase", phase)
                raise
            finally:
                report["phases"][phase] = round(perf_counter() - started, 4)
                monitor.phase = outer

        setattr(owner, name, measured)

    for name in ("scan", "validate_database", "validate_staging"):
        instrument(_staging, name)
    instrument(_staging._Sink, "finalize")

    try:
        first = timed(
            "first_build",
            lambda: publish_scan(
                source,
                location,
                config,
                workers=1,
                memory_limit=f"{args.memory_mib * MIB}B",
                spill_limit=f"{args.spill_mib * MIB}B",
            ),
        )
        report["analyzed_records"] = first.result.scope.records_analyzed
        report["datasets"] = {d.id: d.record_count for d in first.result.datasets}
        report["first_generation_bytes"] = (
            first.database_path.stat().st_size + first.scan_path.stat().st_size
        )
        report["first_warnings"] = first.warnings
        monitor.old_generation_id = first.project.generation.id
        timed("database_hash", lambda: _file_hash(first.database_path))
        second = timed(
            "second_build",
            lambda: publish_scan(
                source,
                location,
                config,
                workers=1,
                memory_limit=f"{args.memory_mib * MIB}B",
                spill_limit=f"{args.spill_mib * MIB}B",
            ),
        )
        report["new_generation_bytes"] = (
            second.database_path.stat().st_size + second.scan_path.stat().st_size
        )
        report["second_warnings"] = second.warnings
        report["database_bytes"] = second.database_path.stat().st_size
        report["scan_bytes"] = second.scan_path.stat().st_size
        context = open_generation(
            location, second.project.project_id, budget=reader_budget
        )
        pinned = timed("verified_open", context.__enter__)
        try:
            dataset = pinned.result.datasets[0]
            report["records"] = {}
            for listing in (
                "records.with_missing",
                "records.empty",
                "records.duplicates",
            ):
                monitor.phase = listing
                report["records"][listing] = paginate(
                    lambda listing=listing, **kw: records_page(
                        pinned, dataset.id, listing, **kw
                    )
                )
            report["values"] = {}
            for name in ("id", args.value_field):
                field = next(f for f in dataset.fields if f.name == name)
                ctx = materialize_values(
                    pinned, dataset.id, field.id, budget=query_budget
                )
                query = timed(f"materialize_{name}", ctx.__enter__)
                try:
                    monitor.phase = f"page_{name}"
                    frequencies = paginate(query.frequencies_page)
                    groups = paginate(query.groups_page)
                    first_groups = query.groups_page(size=1).items
                    variants = (
                        paginate(
                            lambda query=query, key=first_groups[0].key, **kw: (
                                query.variants_page(key, **kw)
                            )
                        )
                        if first_groups
                        else None
                    )
                    report["values"][name] = {
                        "frequencies": frequencies,
                        "groups": groups,
                        "variants": variants,
                    }
                finally:
                    ctx.__exit__(None, None, None)
        finally:
            context.__exit__(None, None, None)
        report["status"] = "complete"
    except Exception as exc:  # noqa: BLE001 - benchmark failures are evidence
        report["status"] = "failed"
        report.setdefault("failed_phase", monitor.phase)
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        monitor.close()
        report["sampled_peaks"] = monitor.samples
        report["at_sampled_disk_peak"] = monitor.at_disk_peak
        report["peak_process_bytes"] = _memory_bytes()[1]
        (args.root / "measurement.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        print(json.dumps(report, indent=2), flush=True)
    return 0 if report["status"] == "complete" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case", choices=("csv", "json", "wide", "deep", "long"), required=True
    )
    parser.add_argument("--rows", type=int, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--source", type=Path, help="An existing synthetic source to copy into the run"
    )
    parser.add_argument("--value-field", default="variant")
    parser.add_argument("--memory-mib", type=int, default=256)
    parser.add_argument("--reader-memory-mib", type=int, default=256)
    parser.add_argument("--query-memory-mib", type=int, default=256)
    parser.add_argument("--spill-mib", type=int, default=1024)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--child", action="store_true")
    args = parser.parse_args()
    if args.root.exists() or args.rows < 1 or args.repeat < 1:
        parser.error("A new root, positive row count and positive repeat are required")
    if args.child:
        raise SystemExit(measure(args))
    args.root.mkdir(parents=True)
    status = 0
    for i in range(args.repeat):
        command = [
            sys.executable,
            __file__,
            "--child",
            "--case",
            args.case,
            "--rows",
            str(args.rows),
            "--root",
            str(args.root / f"run-{i + 1}"),
        ]
        for option in (
            "memory_mib",
            "reader_memory_mib",
            "query_memory_mib",
            "spill_mib",
        ):
            command.extend(
                ["--" + option.replace("_", "-"), str(getattr(args, option))]
            )
        command.extend(["--value-field", args.value_field])
        if args.source is not None:
            command.extend(["--source", str(args.source.resolve())])
        result = subprocess.run(command, check=False)
        status = max(status, result.returncode)
    raise SystemExit(status)


if __name__ == "__main__":
    main()

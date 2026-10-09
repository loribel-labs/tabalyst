# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""What the second pass adds to ``tabalyst report`` (lot 7c, PERF-07).

Runs the command on one source in four ways, each with its own home so that the
storage is cold, and prints the wall time, the phases the documents record, the
memory and the size of what is written::

    python benchmarks/report_overhead.py SOURCE --root D:/GIT.test/tabalyst/artifacts/overhead

``off`` is the report without a second pass (``deep.mode`` off), ``auto`` the
default, ``warm`` the default again on the storage ``auto`` filled (a second
pass that reads nothing), ``forced`` is ``--deep --yes``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from time import perf_counter


def _run(source: Path, home: Path, output: Path, *options: str) -> tuple[float, dict]:
    environment = {"TABALYST_HOME": str(home)}
    started = perf_counter()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "tabalyst",
            "report",
            str(source),
            "-o",
            str(output),
            "--force",
            "--no-progress",
            "--quiet",
            *options,
        ],
        check=True,
        env={**os.environ, **environment},
    )
    wall = perf_counter() - started
    document = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
    return wall, document


def _summary(label: str, wall: float, document: dict, output: Path) -> dict:
    analyses = document.get("analyses") or {}
    deep = analyses.get("deep") or {}
    run = deep.get("run") or {}
    return {
        "case": label,
        "wall_seconds": round(wall, 2),
        "processing_seconds": document["report"]["processing_seconds"],
        "scan_seconds": document["run"]["duration_seconds"],
        "second_pass_outcome": analyses.get("outcome"),
        "second_pass_seconds": run.get("duration_seconds"),
        "second_pass_reading": (run.get("timings") or {}).get("reading"),
        "analyses": run.get("executed", 0) + run.get("reused", 0),
        "executed": run.get("executed"),
        "reused": run.get("reused"),
        "cells_read": run.get("cells_read"),
        "second_pass_peak_bytes": run.get("peak_memory_bytes"),
        "scan_peak_bytes": document["run"].get("peak_memory_bytes"),
        "json_bytes": output.with_suffix(".json").stat().st_size,
        "html_bytes": output.stat().st_size,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--root", type=Path, required=True)
    arguments = parser.parse_args()
    root: Path = arguments.root
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    off_config = root / "off.json"
    off_config.write_text(json.dumps({"deep": {"mode": "off"}}), encoding="utf-8")

    rows = []
    for label, home, options in (
        ("off", "home-off", ("-c", str(off_config))),
        ("auto", "home-auto", ()),
        ("warm", "home-auto", ()),
        ("forced", "home-forced", ("--deep", "--yes")),
    ):
        output = root / label / f"{arguments.source.stem}.html"
        wall, document = _run(arguments.source, root / home, output, *options)
        rows.append(_summary(label, wall, document, output))
    print(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

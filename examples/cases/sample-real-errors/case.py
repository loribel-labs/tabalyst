# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Case "sample-real-errors": which defects a sample keeps from a 100,000-row file.

The source is the generated base ``examples/datasets/insurance-customers-100k.json``
(profile ``dirty_stress``), built outside the checkout by ``examples/tools/make_datasets.py``.
Its truth, the rows of each of the 45 classes, is the change log of the generation, so it needs
no injector: ``input/truth.json`` is derived from it and committed.
"""

import collections
import csv
import importlib.util
import json
import subprocess
import sys
from functools import cache
from pathlib import Path
from types import ModuleType

CASE_DIR = Path(__file__).resolve().parent
EXAMPLES = CASE_DIR.parents[1]
REQUEST = EXAMPLES / "datasets" / "insurance-customers-100k.json"
CONFIG = EXAMPLES / "config.json"
TRUTH = CASE_DIR / "input" / "truth.json"
MANIFEST = json.loads((CASE_DIR / "case.json").read_text(encoding="utf-8"))
ARGS: dict[str, list[str]] = {m: r["args"] for m, r in MANIFEST["runs"].items()}
SEEDS: dict[str, tuple[int, ...]] = {m: tuple(r["seeds"]) for m, r in MANIFEST["runs"].items()}
SIZES: tuple[int, ...] = tuple(MANIFEST["measure"]["sizes"])
Row = tuple[str, ...]


def _tool() -> ModuleType:
    script = EXAMPLES / "tools" / "make_datasets.py"
    spec = importlib.util.spec_from_file_location("case_make_datasets", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@cache
def dataset() -> tuple[Path, Path]:
    """The generated source and its change log (built or reused, SHA-256 checked)."""
    paths: dict[str, Path] = _tool().ensure(REQUEST)
    return paths["insurance-customers-100k.csv"], paths["insurance-customers-100k.changes.csv"]


def _read(path: Path) -> tuple[Row, list[Row]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = tuple(next(reader))
        return header, [tuple(row) for row in reader]


def truth_from_changes(changes: Path) -> dict[str, list[int]]:
    """Per class, the sorted 0-based data rows the generation changed."""
    rows: dict[str, set[int]] = collections.defaultdict(set)
    with changes.open(newline="", encoding="utf-8") as handle:
        for change in csv.DictReader(handle):
            rows[change["class"]].add(int(change["row_number"]) - 2)
    return {name: sorted(indexes) for name, indexes in rows.items()}


def build_matches_input() -> bool:
    """Whether the committed truth is the change log of the generated base."""
    return json.loads(TRUTH.read_text(encoding="utf-8")) == truth_from_changes(dataset()[1])


def write_case() -> None:
    """Write ``input/truth.json`` from the generated base."""
    TRUTH.parent.mkdir(parents=True, exist_ok=True)
    TRUTH.write_text(json.dumps(truth_from_changes(dataset()[1])) + "\n", encoding="utf-8")


@cache
def _prepare() -> Path:
    """Scan the source once with the second pass, as the showcase does, and return it."""
    source = dataset()[0]
    command = [
        sys.executable, "-m", "tabalyst", "scan", str(source), "--config", str(CONFIG),
        "--deep", "--yes", "--force", "--no-html",
    ]
    done = subprocess.run(command, capture_output=True, text=True, check=False)
    if done.returncode:
        raise RuntimeError(done.stderr)
    return source


def run(method: str, rows: int, seed: int, output: Path) -> None:
    """Run ``tabalyst sample`` with the arguments of ``runs[method]`` in the manifest.

    Raises ``RuntimeError`` with the error output when the command fails.
    """
    command = [
        sys.executable, "-m", "tabalyst", "sample", str(_prepare()),
        "-o", str(output), "--force", "--rows", str(rows), "--seed", str(seed),
        "--config", str(CONFIG), *ARGS[method],
    ]
    done = subprocess.run(command, capture_output=True, text=True, check=False)
    if done.returncode:
        raise RuntimeError(done.stderr)


@cache
def _source_rows() -> list[Row]:
    return _read(dataset()[0])[1]


def score(sample_csv: Path, truth: Path = TRUTH) -> dict[str, int]:
    """Per class, how many of its rows the sample holds.

    A row is matched by its whole content. An exact copy cannot be told from its original,
    so for ``duplicate_rows`` the count is the number of distinct contents in the sample that
    occur more than once in the source.
    """
    source = _source_rows()
    kept = collections.Counter(_read(sample_csv)[1])
    occurrences = collections.Counter(source)
    classes: dict[str, list[int]] = json.loads(truth.read_text(encoding="utf-8"))
    result: dict[str, int] = {}
    for name, indexes in classes.items():
        if name == "duplicate_rows":
            result[name] = sum(1 for row in kept if occurrences[row] > 1)
        else:
            result[name] = sum(1 for index in indexes if source[index] in kept)
    return result


def measure(work: Path, sizes: tuple[int, ...] = SIZES) -> str:
    """Two markdown tables: the share of runs that keep at least one row of each
    class, then the mean number of rows of the class a run keeps."""
    classes: dict[str, list[int]] = json.loads(TRUTH.read_text(encoding="utf-8"))
    work.mkdir(parents=True, exist_ok=True)
    head = "| Class | Rows | " + " | ".join(
        f"{method} {size}" for size in sizes for method in SEEDS
    ) + " |\n| --- | ---: |" + " ---: |" * (len(sizes) * len(SEEDS)) + "\n"
    results: dict[tuple[str, int], list[dict[str, int]]] = {}
    for size in sizes:
        for method, method_seeds in SEEDS.items():
            runs = []
            for seed in method_seeds:
                output = work / "sample.csv"
                run(method, size, seed, output)
                runs.append(score(output))
            results[(method, size)] = runs
    shares, means = [], []
    for name, indexes in classes.items():
        share, mean = [], []
        for size in sizes:
            for method in SEEDS:
                runs = results[(method, size)]
                share.append(f"{sum(1 for r in runs if r[name]) / len(runs):.0%}")
                mean.append(f"{sum(r[name] for r in runs) / len(runs):.1f}")
        shares.append(f"| `{name}` | {len(indexes)} | " + " | ".join(share) + " |")
        means.append(f"| `{name}` | {len(indexes)} | " + " | ".join(mean) + " |")
    lost = {
        (method, size): sum(
            1 for name in classes if not any(r[name] for r in results[(method, size)]))
        for size in sizes for method in SEEDS
    }
    footer = "\nClasses never kept in any seed: " + ", ".join(
        f"{method} {size}: {count}" for (method, size), count in lost.items()) + "\n"
    return head + "\n".join(shares) + "\n\n" + head + "\n".join(means) + "\n" + footer


def main() -> None:
    """``build`` writes the truth; ``measure WORK_DIR`` prints the tables."""
    if len(sys.argv) >= 2 and sys.argv[1] == "build":
        write_case()
    elif len(sys.argv) == 3 and sys.argv[1] == "measure":
        sys.stdout.write(measure(Path(sys.argv[2])))
    else:
        sys.exit("usage: case.py build | case.py measure WORK_DIR")


if __name__ == "__main__":
    main()

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Case "sample-injected-errors": how many injected errors a sample keeps.

Builds a dirty copy of the insurance example with known errors, runs
``tabalyst sample`` on it and counts the injected rows a sample holds. The errors
are injected by the Generate engine from ``injections.json`` (design
``docs/dev/generate/test-cases.md``), which also writes the change log the truth
comes from. Two classes stay here because Generate never puts two classes on a row:
``common_anomalies`` and ``worst_row``, applied afterwards on rows the log does not
name. The build is deterministic, so the committed ``input/dirty.csv``,
``input/changes.csv`` and ``input/truth.json`` can always be rebuilt and compared.
"""

import collections
import csv
import importlib.util
import json
import random
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

from tabalyst.generate_anomalies import inject_anomalies

CASE_DIR = Path(__file__).resolve().parent
EXAMPLES = CASE_DIR.parents[1]
SOURCE = EXAMPLES / "datasets" / "insurance-customers.csv"
INJECTIONS = CASE_DIR / "injections.json"
DIRTY = CASE_DIR / "input" / "dirty.csv"
CHANGES = CASE_DIR / "input" / "changes.csv"
TRUTH = CASE_DIR / "input" / "truth.json"
MANIFEST = json.loads((CASE_DIR / "case.json").read_text(encoding="utf-8"))
BUILD_SEED: int = MANIFEST["build"]["seed"]
ARGS: dict[str, list[str]] = {m: r["args"] for m, r in MANIFEST["runs"].items()}
SEEDS: dict[str, tuple[int, ...]] = {m: tuple(r["seeds"]) for m, r in MANIFEST["runs"].items()}
SIZES: tuple[int, ...] = tuple(MANIFEST["measure"]["sizes"])

Row = list[str]
# Classes the source already holds some of (malformed emails, whitespace around a
# name, a shouting city, an agency code of another length): scored by the property of the cell.
# Classes scored by the rows whose value occurs once in the source (a value seen
# once is what a typo or a rare name is; the source holds some by itself).
SINGLETONS: dict[str, str] = {"rare_surname": "nom"}
# Classes scored by the typos of the column: a value of at most two rows one edit away from a
# value of ten rows or more. The source holds about fifty of its own in ``ville``, so an injected
# row cannot be told from them.
TYPOS: dict[str, str] = {"city_typo": "ville"}
BY_CONTENT: dict[str, tuple[str, Callable[[str], bool]]] = {
    "email_malformed": ("courriel", lambda v: re.fullmatch(r"[^@\s]+@[^@\s]+[.][^@\s]+", v) is None),
    "name_zero_width": ("prenom", lambda v: chr(0x200B) in v),
    "name_replacement_char": ("nom", lambda v: chr(0xFFFD) in v),
    "name_leading_space": ("prenom", lambda v: v != v.lstrip()),
    "name_double_space": ("nom", lambda v: "  " in v),
    "city_case_variant": ("ville", lambda v: len(v) > 1 and v.isupper()),
    "agency_code_length": ("agence_code", lambda v: len(v) != 9),
}

# Six anomalies that are common in the file, one per column: each is a target of
# the sample with many candidate rows, so a row that has all six is not among
# the candidates of any of them unless the sample looks for such rows.
COMMON: tuple[tuple[str, Callable[[str], str]], ...] = (
    ("nom_voie", lambda v: " " + v),
    ("province_nom", lambda v: " " + v),
    ("date_creation", lambda v: " " + v),
    ("appartement", lambda v: v + "  x"),
    ("montant_reclamation", lambda v: v[:1] + "  " + v[1:]),
    ("date_modification", lambda v: v[:4] + "  " + v[4:]),
)
COMMON_ROWS = 60
WORST_ROWS = 3


def _read(path: Path) -> tuple[list[str], list[Row]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        return header, list(reader)


def _tool(name: str) -> ModuleType:
    """A script of ``examples/tools/`` loaded as a module."""
    spec = importlib.util.spec_from_file_location(f"case_{name}", EXAMPLES / "tools" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def operations(request: dict[str, object]) -> list[dict[str, object]]:
    """The operations of the engine: a ``replace`` with ``values`` becomes one operation
    of ``count`` 1 per value, with the same class."""
    expanded: list[dict[str, object]] = []
    for operation in request["operations"]:  # type: ignore[attr-defined]
        values = operation.get("values")
        if values is None:
            expanded.append(operation)
            continue
        assert operation["kind"] == "replace" and "count" not in operation
        base = {key: item for key, item in operation.items() if key != "values"}
        expanded.extend({**base, "value": value, "count": 1} for value in values)
    return expanded


def _one_edit(a: str, b: str) -> bool:
    """Whether the texts differ by one insertion, deletion, substitution or exchange of neighbours."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        spots = [i for i, (x, y) in enumerate(zip(a, b, strict=True)) if x != y]
        return len(spots) == 1 or (
            len(spots) == 2 and spots[1] == spots[0] + 1 and a[spots[0]] == b[spots[1]] and a[spots[1]] == b[spots[0]]
        )
    shorter, longer = sorted((a, b), key=len)
    spot = next((i for i, c in enumerate(shorter) if c != longer[i]), len(shorter))
    return shorter[spot:] == longer[spot + 1 :]


def typo_values(rows: list[Row], column: int) -> set[str]:
    """The values of a column that are typos of a frequent value."""
    counts = collections.Counter(row[column] for row in rows if row[column])
    frequent = [value for value, count in counts.items() if count >= 10]
    return {
        value
        for value, count in counts.items()
        if count <= 2 and len(value) >= 4 and any(_one_edit(value, other) for other in frequent)
    }


def build(source: Path = SOURCE) -> tuple[list[str], list[Row], dict[str, list[int]], str]:
    """The dirty rows, the 0-based data rows of each error class and the change log.

    Generate injects the classes of ``injections.json`` into the source and its change log
    is the truth of those classes; ``common_anomalies`` and ``worst_row`` are then applied to
    rows no class has taken. The classes are listed in the order of the request.
    """
    request = json.loads(INJECTIONS.read_text(encoding="utf-8"))
    _, original = _read(source)
    with tempfile.TemporaryDirectory() as work:
        altered, changes = Path(work) / "altered.csv", Path(work) / "changes.csv"
        inject_anomalies(
            source, altered, changes, dataset=request["dataset"],
            profile={"id": request["id"], "operations": operations(request)},
            seed=BUILD_SEED, count=len(original), delimiter=",",
        )
        header, rows = _read(altered)
        log = changes.read_text(encoding="utf-8")
        found = _tool("case_truth").truth_from_changes(changes)
    order = list(dict.fromkeys(str(operation["class"]) for operation in request["operations"]))
    classes = {name: found[name] for name in order}
    column = {name: index for index, name in enumerate(header)}
    taken = {index for indexes in classes.values() for index in indexes}
    free = [index for index in range(len(rows)) if index not in taken]
    chosen = random.Random(BUILD_SEED).sample(free, COMMON_ROWS + WORST_ROWS)
    common, worst = sorted(chosen[:COMMON_ROWS]), sorted(chosen[COMMON_ROWS:])
    for position, index in enumerate(common):
        field, change = COMMON[position % len(COMMON)]
        rows[index][column[field]] = change(rows[index][column[field]])
    for index in worst:
        for field, change in COMMON:
            rows[index][column[field]] = change(rows[index][column[field]])
    classes["common_anomalies"] = common
    classes["worst_row"] = worst
    return header, rows, classes, log


def write_case() -> None:
    """Write ``input/dirty.csv``, ``input/changes.csv`` and ``input/truth.json``."""
    header, rows, classes, log = build()
    DIRTY.parent.mkdir(parents=True, exist_ok=True)
    with DIRTY.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
    CHANGES.write_text(log, encoding="utf-8", newline="")
    TRUTH.write_text(json.dumps(classes, indent=1) + "\n", encoding="utf-8")


def score(sample_csv: Path, dirty: Path = DIRTY, truth: Path = TRUTH) -> dict[str, int]:
    """Per error class, how many injected rows the sample holds.

    A row is matched by its whole content. A duplicated row cannot be told
    from its original, so for ``duplicate_rows`` the count is the number of
    distinct contents in the sample that occur more than once in the source.
    In the same way the source already holds empty contract identifiers, which
    cannot be told from the injected ones, so for ``missing_required`` the count
    is the number of sample rows whose contract identifier is empty. The classes
    of ``BY_CONTENT`` are scored the same way, by the property of the row, and
    the classes of ``SINGLETONS`` count the sample rows whose value occurs once in the source,
    and ``TYPOS`` those whose value is a typo of a frequent value of the source.
    """
    header, source = _read(dirty)
    _, sample = _read(sample_csv)
    contract = header.index("id_contrat")
    occurrences = collections.Counter(map(tuple, source))
    kept = collections.Counter(map(tuple, sample))
    classes: dict[str, list[int]] = json.loads(truth.read_text(encoding="utf-8"))
    result: dict[str, int] = {}
    for name, indexes in classes.items():
        if name == "duplicate_rows":
            result[name] = sum(1 for row in kept if occurrences[row] > 1)
        elif name == "missing_required":
            result[name] = sum(1 for row in sample if not row[contract].strip())
        elif name in SINGLETONS:
            at = header.index(SINGLETONS[name])
            seen = collections.Counter(row[at] for row in source)
            result[name] = sum(1 for row in sample if seen[row[at]] == 1)
        elif name in TYPOS:
            at = header.index(TYPOS[name])
            typos = typo_values(source, at)
            result[name] = sum(1 for row in sample if row[at] in typos)
        elif name in BY_CONTENT:
            field, has = BY_CONTENT[name]
            result[name] = sum(1 for row in sample if has(row[header.index(field)]))
        else:
            result[name] = sum(1 for index in indexes if tuple(source[index]) in kept)
    return result


def build_matches_input() -> bool:
    """Whether the committed input is exactly what the deterministic build gives."""
    header, rows, classes, log = build()
    if json.loads(TRUTH.read_text(encoding="utf-8")) != classes:
        return False
    if CHANGES.read_text(encoding="utf-8") != log:
        return False
    committed_header, committed = _read(DIRTY)
    return committed_header == header and committed == rows


def run(method: str, rows: int, seed: int, output: Path, dirty: Path = DIRTY) -> None:
    """Run ``tabalyst sample`` with the arguments of ``runs[method]`` in the manifest.

    Raises ``RuntimeError`` with the error output when the command fails.
    """
    command = [
        sys.executable, "-m", "tabalyst", "sample", str(dirty),
        "-o", str(output), "--force", "--rows", str(rows), "--seed", str(seed),
    ]
    command += ARGS[method]
    done = subprocess.run(command, capture_output=True, text=True, check=False)
    if done.returncode:
        raise RuntimeError(done.stderr)


def measure(work: Path, sizes: tuple[int, ...] = SIZES) -> str:
    """Two markdown tables: the share of runs that keep at least one row of each
    error class, then the mean number of rows of the class a run keeps (the
    first hides the classes of several different errors, the second shows them)."""
    classes: dict[str, list[int]] = json.loads(TRUTH.read_text(encoding="utf-8"))
    seeds = SEEDS
    work.mkdir(parents=True, exist_ok=True)
    head = "| Error class | Rows | " + " | ".join(
        f"{method} {size}" for size in sizes for method in seeds
    ) + " |\n| --- | --- |" + " --- |" * (len(sizes) * len(seeds)) + "\n"
    results: dict[tuple[str, int], list[dict[str, int]]] = {}
    for size in sizes:
        for method, method_seeds in seeds.items():
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
            for method in seeds:
                runs = results[(method, size)]
                share.append(f"{sum(1 for run in runs if run[name]) / len(runs):.0%}")
                mean.append(f"{sum(run[name] for run in runs) / len(runs):.1f}")
        shares.append(f"| `{name}` | {len(indexes)} | " + " | ".join(share) + " |")
        means.append(f"| `{name}` | {len(indexes)} | " + " | ".join(mean) + " |")
    return head + "\n".join(shares) + "\n\n" + head + "\n".join(means) + "\n"


def main() -> None:
    """``build`` rewrites the input; ``measure WORK_DIR`` prints the table."""
    if len(sys.argv) >= 2 and sys.argv[1] == "build":
        write_case()
    elif len(sys.argv) == 3 and sys.argv[1] == "measure":
        sys.stdout.write(measure(Path(sys.argv[2])))
    else:
        sys.exit("usage: case.py build | case.py measure WORK_DIR")


if __name__ == "__main__":
    main()

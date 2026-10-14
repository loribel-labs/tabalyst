# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Case "sample-injected-errors": how many injected errors a sample keeps.

Builds a dirty copy of the insurance example with known errors, runs
``tabalyst sample`` on it and counts the injected rows a sample holds. The
build is deterministic, so the committed ``input/dirty.csv`` and ``truth.json``
can always be rebuilt and compared.
"""

import collections
import csv
import json
import random
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parent
SOURCE = CASE_DIR.parents[1] / "input" / "insurance-customers.csv"
DIRTY = CASE_DIR / "input" / "dirty.csv"
TRUTH = CASE_DIR / "input" / "truth.json"
BUILD_SEED = 123

Row = list[str]
Injector = Callable[[Row, int], None]


def _read(path: Path) -> tuple[list[str], list[Row]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        return header, list(reader)


def build(source: Path = SOURCE) -> tuple[list[str], list[Row], dict[str, list[int]]]:
    """The dirty rows and, per error class, the 0-based data rows that hold it."""
    header, rows = _read(source)
    column = {name: index for index, name in enumerate(header)}
    rng = random.Random(BUILD_SEED)
    original = len(rows)
    used: set[int] = set()
    classes: dict[str, list[int]] = {}

    def pick(count: int) -> list[int]:
        chosen: list[int] = []
        while len(chosen) < count:
            index = rng.randrange(original)
            if index not in used:
                used.add(index)
                chosen.append(index)
        return chosen

    def inject(name: str, count: int, change: Injector) -> None:
        indexes = pick(count)
        for position, index in enumerate(indexes):
            change(rows[index], position)
        classes[name] = indexes

    def replace(field: str, values: list[str]) -> Injector:
        def change(row: Row, position: int) -> None:
            row[column[field]] = values[position]

        return change

    def trailing_space(row: Row, position: int) -> None:
        row[column["id_client"]] += " "

    def end_before_start(row: Row, position: int) -> None:
        row[column["date_debut"]] = "2030-01-01"
        row[column["date_fin"]] = "2001-01-01"

    def blank_contract(row: Row, position: int) -> None:
        row[column["id_contrat"]] = ""

    inject("email_malformed", 6, replace("courriel", [
        "nobody.example", "a@@b.example", "x@", "@y.example", "bad email@z.example", "u@v",
    ]))
    inject("phone_malformed", 6, replace("telephone", [
        "5551234", "+1-4685550110", "abc", "(514) 555-0110", "+1-468-555-01", "0",
    ]))
    inject("postal_malformed", 6, replace("code_postal", [
        "H4A9M3", "12345", "H4A 9M", "h4a 9m3", "H4A  9M3", "ZZZ",
    ]))
    inject("birthdate_invalid", 6, replace("date_naissance", [
        "1961-13-45", "N/A", "1961/03/31", "31-03-1961", "0000-00-00", "2099-01-01",
    ]))
    inject("premium_outlier", 6, replace("prime_annuelle", [
        "-100", "abc", "99999999", "0", "1e9", "12,5,6",
    ]))
    inject("id_trailing_space", 6, trailing_space)
    bell, bidi = chr(0x07), chr(0x202E)
    inject("name_long_weird", 4, replace("nom", ["X" * 300, f"Ré{bell}x", "<script>", bidi * 2]))
    inject("end_before_start", 8, end_before_start)
    inject("novel_category_typo", 4, replace("type_contrat", ["autoo", "VIE", "santé ", "hab"]))
    inject("missing_required", 6, blank_contract)

    copies = pick(6)
    rows.extend(list(rows[index]) for index in copies)
    classes["duplicate_rows"] = list(range(original, original + 6))
    return header, rows, classes


def write_case() -> None:
    """Write ``input/dirty.csv`` and ``input/truth.json``."""
    header, rows, classes = build()
    DIRTY.parent.mkdir(parents=True, exist_ok=True)
    with DIRTY.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    TRUTH.write_text(json.dumps(classes, indent=1) + "\n", encoding="utf-8")


def score(sample_csv: Path, dirty: Path = DIRTY, truth: Path = TRUTH) -> dict[str, int]:
    """Per error class, how many injected rows the sample holds.

    A row is matched by its whole content. A duplicated row cannot be told
    from its original, so for ``duplicate_rows`` the count is the number of
    distinct contents in the sample that occur more than once in the source.
    """
    _, source = _read(dirty)
    _, sample = _read(sample_csv)
    occurrences = collections.Counter(map(tuple, source))
    kept = collections.Counter(map(tuple, sample))
    classes: dict[str, list[int]] = json.loads(truth.read_text(encoding="utf-8"))
    result: dict[str, int] = {}
    for name, indexes in classes.items():
        if name == "duplicate_rows":
            result[name] = sum(1 for row in kept if occurrences[row] > 1)
        else:
            result[name] = sum(1 for index in indexes if tuple(source[index]) in kept)
    return result


def run_sample(method: str, rows: int, seed: int, output: Path, dirty: Path = DIRTY) -> None:
    """Run ``tabalyst sample`` (``smart`` or ``random``) and raise if it fails."""
    command = [
        sys.executable, "-m", "tabalyst", "sample", str(dirty),
        "-o", str(output), "--force", "--rows", str(rows), "--seed", str(seed),
    ]
    command += ["--smart", "--yes"] if method == "smart" else ["--sample-method", method]
    done = subprocess.run(command, capture_output=True, text=True, check=False)
    if done.returncode:
        raise RuntimeError(done.stderr)


def measure(work: Path, sizes: tuple[int, ...] = (100, 200, 400)) -> str:
    """The markdown table of the share of runs that keep each error class."""
    classes: dict[str, list[int]] = json.loads(TRUTH.read_text(encoding="utf-8"))
    seeds = {"smart": (1, 2, 3), "random": tuple(range(1, 9))}
    work.mkdir(parents=True, exist_ok=True)
    lines = ["| Error class | Rows | " + " | ".join(
        f"{method} {size}" for size in sizes for method in seeds
    ) + " |", "| --- | --- |" + " --- |" * (len(sizes) * len(seeds))]
    results: dict[tuple[str, int], list[dict[str, int]]] = {}
    for size in sizes:
        for method, method_seeds in seeds.items():
            runs = []
            for seed in method_seeds:
                output = work / "sample.csv"
                run_sample(method, size, seed, output)
                runs.append(score(output))
            results[(method, size)] = runs
    for name, indexes in classes.items():
        cells = []
        for size in sizes:
            for method in seeds:
                runs = results[(method, size)]
                cells.append(f"{sum(1 for run in runs if run[name]) / len(runs):.0%}")
        lines.append(f"| `{name}` | {len(indexes)} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


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

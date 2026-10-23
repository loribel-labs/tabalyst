# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Helpers of the Dedup contract tests.

Production modules of Dedup are imported lazily inside the helpers, so the tests
can be collected before they exist. The reference implementation below is the
specification (S4, S6) written the simplest possible way; it never calls Tabalyst.
The entry points ``analyze`` and ``run`` follow ``docs/dev/dedup/design.md`` 4.3:
lot 8 may rewire ``run`` to the public API without changing the tests.
"""

import csv
import json
import os
import tempfile
from collections import Counter
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path

Row = tuple[str, ...]

HEADER = ["id", "name"]


# ---------------------------------------------------------------- files


def write_csv(
    directory: Path,
    name: str,
    rows: Iterable[Sequence[str]],
    *,
    header: Sequence[str] = HEADER,
    delimiter: str = ",",
    encoding: str = "utf-8",
) -> Path:
    """Write a CSV with ``\\r\\n`` line ends, as the Dedup outputs are."""
    path = directory / name
    with path.open("w", encoding=encoding, newline="") as stream:
        writer = csv.writer(stream, delimiter=delimiter, lineterminator="\r\n")
        writer.writerow(header)
        writer.writerows(rows)
    return path


def read_csv(
    path: Path, *, delimiter: str = ",", encoding: str = "utf-8-sig"
) -> tuple[list[str], list[Row]]:
    """Read a CSV strictly, with the dialect Dedup writes."""
    with path.open("r", encoding=encoding, newline="") as stream:
        reader = csv.reader(stream, delimiter=delimiter, strict=True)
        header = next(reader)
        return header, [tuple(row) for row in reader]


def artifact_root() -> Path:
    """Where heavy tests put their data: never inside the checkout."""
    configured = os.environ.get("TABALYST_ARTIFACTS_DIR")
    default = Path(tempfile.gettempdir()) / "tabalyst" / "artifacts"
    root = Path(configured) if configured else default
    root.mkdir(parents=True, exist_ok=True)
    return root


def generated_rows(
    total: int, extra_copies: int, *, width: int = 4, seed: int = 7
) -> Iterator[Row]:
    """``total`` records of which exactly ``extra_copies`` repeat an earlier row.

    Distinct rows are ``total - extra_copies``; each extra copy repeats an earlier
    distinct row chosen by a deterministic generator, so the groups have mixed sizes.
    """
    import random

    rng = random.Random(seed)
    if extra_copies >= total and total:
        raise ValueError("at least one distinct row is needed")
    next_id = 0
    copies_left = extra_copies
    for emitted in range(total):
        remaining = total - emitted
        can_copy = next_id > 0 and copies_left > 0
        if can_copy and (
            copies_left == remaining or rng.random() < copies_left / remaining
        ):
            yield _row(rng.randrange(next_id), width)
            copies_left -= 1
        else:
            yield _row(next_id, width)
            next_id += 1


def _row(number: int, width: int) -> Row:
    return (str(number),) + tuple(f"value {number} {column}" for column in range(1, width))


def write_generated_csv(
    path: Path, total: int, extra_copies: int, *, width: int = 4, seed: int = 7
) -> Path:
    """Stream a large CSV to ``path`` (heavy tests)."""
    header = ["id"] + [f"column_{column}" for column in range(1, width)]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\r\n")
        writer.writerow(header)
        writer.writerows(generated_rows(total, extra_copies, width=width, seed=seed))
    return path


# ------------------------------------------------------------ reference


def reference_stats(rows: Iterable[Sequence[str]]) -> dict[str, int]:
    """N, D, G, E, O, S, M, G2 and G3+ of S4, from ``Counter(tuple(row))``."""
    counts = Counter(tuple(row) for row in rows)
    total = sum(counts.values())
    distinct = len(counts)
    groups = sum(1 for count in counts.values() if count >= 2)
    return {
        "N": total,
        "D": distinct,
        "G": groups,
        "E": total - distinct,
        "O": groups + (total - distinct),
        "S": distinct - groups,
        "M": max(counts.values(), default=0),
        "G2": sum(1 for count in counts.values() if count == 2),
        "G3+": sum(1 for count in counts.values() if count >= 3),
    }


def check_invariants(stats: dict[str, int]) -> None:
    """The invariants of S4 and DD-12, on reference-style counts."""
    assert stats["N"] == stats["D"] + stats["E"]
    assert stats["D"] == stats["S"] + stats["G"]
    assert stats["O"] == stats["G"] + stats["E"]
    assert stats["G"] == stats["G2"] + stats["G3+"]
    assert 0 <= stats["S"] <= stats["D"] <= stats["N"]
    assert (stats["M"] == 0) == (stats["N"] == 0)
    assert (stats["G"] == 0) == (stats["M"] <= 1)
    assert (stats["G3+"] > 0) == (stats["M"] >= 3)


def reference_outputs(
    rows: Sequence[Sequence[str]],
) -> dict[str, list[Row]]:
    """The rows of ``unique``, ``duplicates`` and ``duplicates_all`` (S6.1, S6.2).

    A key is absent when the matrix of S6.2 does not produce that file.
    """
    ordered = [tuple(row) for row in rows]
    counts = Counter(ordered)
    seen: set[Row] = set()
    unique: list[Row] = []
    duplicates: list[Row] = []
    everything: list[Row] = []
    for row in ordered:
        first = row not in seen
        seen.add(row)
        repeated = counts[row] >= 2
        if first:
            unique.append(row)
            if repeated:
                duplicates.append(row)
        if repeated:
            everything.append(row)
    stats = reference_stats(ordered)
    outputs: dict[str, list[Row]] = {}
    if stats["G"] > 0:
        outputs["unique"] = unique
        outputs["duplicates"] = duplicates
        if stats["M"] >= 3:
            outputs["duplicates_all"] = everything
    return outputs


def output_names(stem: str) -> dict[str, str]:
    """The managed CSV names of a source stem (design 6.1)."""
    return {
        "unique": f"{stem}.unique.csv",
        "duplicates": f"{stem}.duplicates.csv",
        "duplicates_all": f"{stem}.duplicates_all.csv",
    }


def assert_published(
    directory: Path,
    stem: str,
    rows: Sequence[Sequence[str]],
    *,
    header: Sequence[str] = HEADER,
) -> None:
    """The CSV in ``directory`` are exactly those of S6.2, with the exact ordered rows."""
    expected = reference_outputs(rows)
    for kind, name in output_names(stem).items():
        path = directory / name
        if kind not in expected:
            assert not path.exists(), f"{name} must not be written"
            continue
        written_header, written = read_csv(path)
        assert written_header == list(header), f"header of {name}"
        assert written == expected[kind], f"content or order of {name}"


def no_temporary_files(directory: Path) -> bool:
    """Whether no provisional data file remains in ``directory`` (S16.2)."""
    return not [p for p in directory.iterdir() if p.name.endswith(".tmp")]


def varint(value: int) -> bytes:
    """Unsigned LEB128 (design 5.2)."""
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def reference_key(row: Sequence[str]) -> bytes:
    """The canonical key of design 5.2, written independently of the product."""
    key = bytearray(varint(len(row)))
    for cell in row:
        encoded = cell.encode("utf-8")
        key += varint(len(encoded)) + encoded
    return bytes(key)


# ------------------------------------------------------- the product


def settings(**options):
    """``DedupSettings`` (lot 1) with the defaults of the project and these options."""
    from tabalyst.dedup.settings import DedupSettings

    return DedupSettings(**options)


def analyze(path: Path, **options):
    """``analyze_dedup`` (lot 4): the counts and the marks, no output."""
    from tabalyst.config import CsvConfig
    from tabalyst.dedup.analysis import analyze_dedup

    return analyze_dedup(
        path,
        csv=options.pop("csv", CsvConfig()),
        max_rows=options.pop("max_rows", 10_000_000),
        memory_budget_mb=options.pop("memory_budget_mb", 512),
        temp_dir=options.pop("temp_dir", None),
        **options,
    )


def run(path: Path, destination: Path | None = None, **options):
    """``process_source`` (lots 5 to 7): one source from decision to published set."""
    effective = settings(**options)  # invalid options fail before the pipeline exists
    from tabalyst.dedup.pipeline import process_source

    return process_source(path, effective, destination=destination or path.parent)


def load_report(directory: Path, stem: str) -> dict:
    return json.loads((directory / f"{stem}.dedup.json").read_text(encoding="utf-8"))


def validate_report(document: dict) -> None:
    """The committed JSON Schema (lot 6) and the invariants of design 12.3."""
    import jsonschema

    import tabalyst

    schema_path = Path(tabalyst.__file__).parent / "schemas" / "tabalyst.dedup.schema.json"
    jsonschema.validate(document, json.loads(schema_path.read_text(encoding="utf-8")))
    if document["status"] != "complete":
        return
    records = document["records"]
    assert records["total"] == records["distinct"] + records["extra_copies"]
    assert records["distinct"] == records["singletons"] + records["duplicate_groups"]
    assert records["duplicate_group_occurrences"] == (
        records["duplicate_groups"] + records["extra_copies"]
    )
    assert records["duplicate_groups"] == (
        records["groups_occurring_twice"] + records["groups_occurring_three_plus"]
    )
    outputs = document["outputs"]
    created = [name for name in ("unique", "duplicates", "duplicates_all") if outputs[name]]
    assert outputs["csv_files_created"] == len(created)
    if outputs["unique"]:
        assert outputs["unique"]["rows"] == records["distinct"]
    if outputs["duplicates"]:
        assert outputs["duplicates"]["rows"] == records["duplicate_groups"]
    if outputs["duplicates_all"]:
        assert outputs["duplicates_all"]["rows"] == records["duplicate_group_occurrences"]


def count_stats(analysis) -> dict[str, int]:
    """The counts of a ``DedupAnalysis`` under the letters of S4."""
    stats = analysis.stats
    return {
        "N": stats.total,
        "D": stats.distinct,
        "G": stats.duplicate_groups,
        "E": stats.extra_copies,
        "O": stats.duplicate_group_occurrences,
        "S": stats.singletons,
        "M": stats.max_occurrences,
        "G2": stats.groups_occurring_twice,
        "G3+": stats.groups_occurring_three_plus,
    }

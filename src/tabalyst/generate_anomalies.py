# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Measured, streaming mutation pass over a staged clean Generate CSV."""

from __future__ import annotations

import csv
import math
import random
import re
import unicodedata
from collections import Counter, deque
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import cast

CHANGE_FIELDS = ["event_id", "dataset", "profile", "row_number", "operation_index",
                 "kind", "column", "before", "after", "cause"]

# Shared by the definition and the Computer package validators: one rule, one place.
OPERATION_KINDS = frozenset({"set_missing", "replace", "duplicate", "format", "swap",
                             "duplicate_row"})
ROW_KINDS = frozenset({"duplicate_row"})
OPERATION_KEYS = frozenset({"kind", "column", "rate", "count", "value", "when", "class"})
FORMAT_VALUES = frozenset({
    "upper", "lower", "strip", "date_slash", "phone_spaces", "insert_space", "double_space",
    "drop_char", "double_hyphen", "suffix_x", "strip_accents", "negate", "leading_apostrophe",
})
CLASS_NAME = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
# Enough to pick a copy that is not the previous line, small enough to stream in constant memory.
COPY_WINDOW = 1000


def _insert_space(value: str, rng: random.Random) -> str:
    spots = [i for i in range(1, len(value)) if value[i - 1] != " " and value[i] != " "]
    if not spots:
        return value
    spot = rng.choice(spots)
    return f"{value[:spot]} {value[spot:]}"


def _drop_char(value: str, rng: random.Random) -> str:
    if len(value) < 2:
        return value
    spot = rng.randrange(len(value))
    return value[:spot] + value[spot + 1:]


def _negate(value: str, rng: random.Random) -> str:
    # A negative zero would read as a typo of the generator, not as a sign error.
    if re.fullmatch(r"\d+(?:\.\d+)?", value) and re.search(r"[1-9]", value):
        return f"-{value}"
    return value


def _strip_accents(value: str, rng: random.Random) -> str:
    decomposed = unicodedata.normalize("NFD", value)
    return unicodedata.normalize(
        "NFC", "".join(char for char in decomposed if unicodedata.category(char) != "Mn"))


# The random stream is passed to every transform so that adding one never shifts another.
TEXT_TRANSFORMS: dict[str, Callable[[str, random.Random], str]] = {
    "upper": lambda value, rng: value.upper(),
    "lower": lambda value, rng: value.lower(),
    "strip": lambda value, rng: value.strip(),
    "date_slash": lambda value, rng: value.replace("-", "/"),
    "phone_spaces": lambda value, rng: value.replace("-", " "),
    "insert_space": _insert_space,
    "double_space": lambda value, rng: value.replace(" ", "  ", 1),
    "drop_char": _drop_char,
    "double_hyphen": lambda value, rng: value.replace("-", "--", 1),
    "suffix_x": lambda value, rng: f"{value}_X",
    "strip_accents": _strip_accents,
    "negate": _negate,
    "leading_apostrophe": lambda value, rng: f"'{value}",
}


def operation_option_error(operation: Mapping[str, object]) -> str | None:
    """Return why the quantity, class or row options of an operation are invalid.

    Exactly one of ``rate`` and ``count`` must be given. A row operation names
    no column and no value. The kind itself and the column names are checked by
    the callers, who know their schema.
    """
    rate = operation.get("rate")
    count = operation.get("count")
    if ("rate" in operation) == ("count" in operation):
        return "operation needs exactly one of rate and count"
    if "rate" in operation and (
            type(rate) not in (int, float) or not math.isfinite(cast(float, rate))
            or not 0 <= cast(float, rate) <= 1):
        return "operation.rate must be from 0 to 1"
    if "count" in operation and (type(count) is not int or cast(int, count) < 1):
        return "operation.count must be a positive integer"
    name = operation.get("class")
    if "class" in operation and (not isinstance(name, str) or not CLASS_NAME.match(name)):
        return "operation.class must be a lower-case identifier of at most 64 characters"
    if operation.get("kind") in ROW_KINDS:
        if "column" in operation:
            return "operation.column is unused for this kind"
        if "value" in operation:
            return "operation.value is unused for this kind"
    return None


def check_operation_counts(operations: Sequence[Mapping[str, object]], rows: int,
                           where: str) -> None:
    """Raise ValueError when an absolute count asks for more rows than the file has."""
    for index, operation in enumerate(operations, 1):
        count = operation.get("count")
        if isinstance(count, int) and count > rows:
            raise ValueError(
                f"{where}: operation {index} asks for count {count} but the dataset "
                f"has {rows} rows")


def _mutate(row: dict[str, str], operation: Mapping[str, object],
            history: dict[str, list[str]],
            rng: random.Random, locale: str,
            unit_suffixes: Mapping[str, tuple[str, str]] | None) -> dict[str, str]:
    column = cast(str, operation["column"])
    before = row[column]
    kind = operation["kind"]
    if kind == "set_missing":
        return {column: ""} if before else {}
    if kind == "replace":
        value = cast(str, operation["value"])
        return {column: value} if value != before else {}
    if kind == "duplicate":
        choices = [value for value in history[column] if value and value != before]
        return {column: rng.choice(choices)} if choices else {}
    if kind == "swap":
        other = cast(str, operation["value"])
        return {column: row[other], other: before} if before != row[other] else {}
    if operation["value"] in {"unit_gb", "unit_suffix"}:
        if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", before):
            return {}
        suffixes = ("GB", "Go") if operation["value"] == "unit_gb" else (
            unit_suffixes[column] if unit_suffixes is not None else None
        )
        if suffixes is None:
            raise ValueError(f"unit suffix is unavailable for {column}")
        return {column: f"{before} {suffixes[0 if locale == 'en' else 1]}"}
    after = TEXT_TRANSFORMS[cast(str, operation["value"])](before, rng)
    return {column: after} if before and after != before else {}


def inject_anomalies(clean: Path, altered: Path, changes: Path, *,
                     dataset: str, profile: Mapping[str, object], seed: int, count: int,
                     delimiter: str, locale: str = "en",
                     unit_suffixes: Mapping[str, tuple[str, str]] | None = None) -> dict[str, object]:
    """Write altered CSV and cell log; return requested and actual counts.

    Computer unit suffixes are supplied by its output register. An operation
    selects ``round(count * rate)`` rows, or exactly its own absolute ``count``,
    so a fixed ``count`` touches the same number of rows in any file size.
    The journal gains a ``class`` column only when an operation declares one,
    which keeps the files of profiles without classes byte for byte unchanged.
    A ``duplicate_row`` operation overwrites the row with an exact copy of an
    earlier output row; put it last in a profile, since the other operations of
    the same row are lost in the copy.
    """
    # Imported here because generate_values reaches generate_definition, which
    # imports this module for the operation rules.
    from tabalyst.generate_values import _stream

    if locale not in {"en", "fr"}:
        raise ValueError(f"unsupported anomaly locale {locale!r}")
    operations = cast(list[dict[str, object]], profile["operations"])
    profile_id = cast(str, profile["id"])
    for index, operation in enumerate(operations, 1):
        problem = operation_option_error(operation)
        if problem is not None:
            raise ValueError(f"{profile_id}.operations[{index}]: {problem}")
    check_operation_counts(operations, count, f"{profile_id} on {dataset}")
    requested = [cast(int, operation["count"]) if "count" in operation
                 else round(count * cast(float, operation["rate"])) for operation in operations]
    remaining = requested.copy()
    selection_rngs = [_stream(seed, dataset, f"{profile_id}:{index}",
                              "anomaly_selection") for index in range(len(operations))]
    mutation_rngs = [_stream(seed, dataset, f"{profile_id}:{index}", "anomaly_value")
                     for index in range(len(operations))]
    applied: Counter[int] = Counter()
    skipped: Counter[int] = Counter()
    history: dict[str, list[str]] = {}
    keeps_classes = any("class" in operation for operation in operations)
    copies_rows = any(operation["kind"] in ROW_KINDS for operation in operations)
    written: deque[tuple[int, tuple[str, ...]]] = deque(maxlen=COPY_WINDOW)
    affected_rows = 0
    changed_cells = 0
    events = 0
    with (clean.open("r", encoding="utf-8", newline="") as source,
          altered.open("w", encoding="utf-8", newline="") as dirty,
          changes.open("w", encoding="utf-8", newline="") as journal):
        reader = csv.DictReader(source, delimiter=delimiter)
        fields = reader.fieldnames or []
        history = {field: [] for field in fields}
        writer = csv.DictWriter(dirty, fieldnames=fields, delimiter=delimiter,
                                lineterminator="\n", extrasaction="raise")
        log = csv.DictWriter(journal, fieldnames=[*CHANGE_FIELDS, *(["class"] if keeps_classes else [])],
                             lineterminator="\n")
        writer.writeheader()
        log.writeheader()
        observed = 0
        for row_index, clean_row in enumerate(reader):
            observed += 1
            row = clean_row.copy()
            changed = False
            for index, operation in enumerate(operations):
                rows_left = count - row_index
                selected = (remaining[index] == rows_left or
                            (remaining[index] > 0 and
                             selection_rngs[index].random() < remaining[index] / rows_left))
                if not selected:
                    continue
                remaining[index] -= 1
                when = cast(dict[str, str], operation.get("when", {}))
                if any(row.get(field) != value for field, value in when.items()):
                    skipped[index] += 1
                    continue
                cause = f"{profile_id}.operations[{index}]"
                if operation["kind"] == "duplicate_row":
                    if not written:
                        skipped[index] += 1
                        continue
                    number, values = written[mutation_rngs[index].randrange(len(written))]
                    updates = {field: value for field, value in zip(fields, values)
                               if row[field] != value}
                    cause += f" copy_of_row={number}"
                else:
                    updates = _mutate(row, operation, history, mutation_rngs[index], locale,
                                      unit_suffixes)
                if not updates:
                    skipped[index] += 1
                    continue
                events += 1
                for column, after in updates.items():
                    before = row[column]
                    row[column] = after
                    changed_cells += 1
                    entry = {"event_id": events, "dataset": dataset,
                             "profile": profile_id, "row_number": row_index + 2,
                             "operation_index": index + 1, "kind": operation["kind"],
                             "column": column, "before": before, "after": after,
                             "cause": cause}
                    if keeps_classes:
                        entry["class"] = operation.get("class", "")
                    log.writerow(entry)
                applied[index] += 1
                changed = True
            writer.writerow(row)
            affected_rows += int(changed)
            if copies_rows:
                written.append((row_index + 2, tuple(row[field] for field in fields)))
            for field, value in clean_row.items():
                if value and len(history[field]) < 1000:
                    history[field].append(value)
        if observed != count:
            raise ValueError(f"Clean row count changed for {dataset}: {observed} != {count}")
    return {
        "dataset": dataset, "profile": profile_id, "seed": seed,
        "total_rows": count, "affected_rows": affected_rows,
        "affected_row_rate": affected_rows / count if count else 0.0,
        "events": events, "changed_cells": changed_cells,
        "operations": [_operation_summary(index, operation, requested[index],
                                          applied[index], skipped[index], count)
                       for index, operation in enumerate(operations)],
    }


def _operation_summary(index: int, operation: Mapping[str, object], requested: int,
                       applied: int, skipped: int, rows: int) -> dict[str, object]:
    """Build one summary entry; the keys of rate-based operations are unchanged."""
    entry: dict[str, object] = {"index": index + 1, "kind": operation["kind"]}
    if "column" in operation:
        entry["column"] = operation["column"]
    if "count" in operation:
        entry["count"] = operation["count"]
    else:
        entry["rate"] = operation["rate"]
    if "class" in operation:
        entry["class"] = operation["class"]
    entry.update({"requested_rows": requested, "applied_rows": applied,
                  "skipped_rows": skipped, "applied_rate": applied / rows if rows else 0.0})
    return entry

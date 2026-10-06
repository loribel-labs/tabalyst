# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Measured, streaming mutation pass over a staged clean Generate CSV."""

from __future__ import annotations

import csv
import random
from collections import Counter
from pathlib import Path

from tabalyst.generate_values import _stream

CHANGE_FIELDS = ["event_id", "dataset", "profile", "row_number", "operation_index",
                 "kind", "column", "before", "after", "cause"]


def _mutate(row: dict[str, str], operation: dict, history: dict[str, list[str]],
            rng: random.Random) -> dict[str, str]:
    column = operation["column"]
    before = row[column]
    kind = operation["kind"]
    if kind == "set_missing":
        return {column: ""} if before else {}
    if kind == "replace":
        return {column: operation["value"]} if operation["value"] != before else {}
    if kind == "duplicate":
        choices = [value for value in history[column] if value and value != before]
        return {column: rng.choice(choices)} if choices else {}
    if kind == "swap":
        other = operation["value"]
        return {column: row[other], other: before} if before != row[other] else {}
    transforms = {
        "upper": str.upper,
        "lower": str.lower,
        "strip": str.strip,
        "date_slash": lambda value: value.replace("-", "/"),
        "phone_spaces": lambda value: value.replace("-", " "),
    }
    after = transforms[operation["value"]](before)
    return {column: after} if before and after != before else {}


def inject_anomalies(clean: Path, altered: Path, changes: Path, *,
                     dataset: str, profile: dict, seed: int, count: int,
                     delimiter: str) -> dict:
    """Write altered CSV and cell log; return requested and actual counts."""
    operations = profile["operations"]
    requested = [round(count * operation["rate"]) for operation in operations]
    remaining = requested.copy()
    selection_rngs = [_stream(seed, dataset, f"{profile['id']}:{index}",
                              "anomaly_selection") for index in range(len(operations))]
    mutation_rngs = [_stream(seed, dataset, f"{profile['id']}:{index}", "anomaly_value")
                     for index in range(len(operations))]
    applied: Counter[int] = Counter()
    skipped: Counter[int] = Counter()
    history: dict[str, list[str]] = {}
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
        log = csv.DictWriter(journal, fieldnames=CHANGE_FIELDS, lineterminator="\n")
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
                when = operation.get("when", {})
                if any(row.get(field) != value for field, value in when.items()):
                    skipped[index] += 1
                    continue
                updates = _mutate(row, operation, history, mutation_rngs[index])
                if not updates:
                    skipped[index] += 1
                    continue
                events += 1
                for column, after in updates.items():
                    before = row[column]
                    row[column] = after
                    changed_cells += 1
                    log.writerow({"event_id": events, "dataset": dataset,
                                  "profile": profile["id"], "row_number": row_index + 2,
                                  "operation_index": index + 1, "kind": operation["kind"],
                                  "column": column, "before": before, "after": after,
                                  "cause": f"{profile['id']}.operations[{index}]"})
                applied[index] += 1
                changed = True
            writer.writerow(row)
            affected_rows += int(changed)
            for field, value in clean_row.items():
                if value and len(history[field]) < 1000:
                    history[field].append(value)
        if observed != count:
            raise ValueError(f"Clean row count changed for {dataset}: {observed} != {count}")
    return {
        "dataset": dataset, "profile": profile["id"], "seed": seed,
        "total_rows": count, "affected_rows": affected_rows,
        "affected_row_rate": affected_rows / count if count else 0.0,
        "events": events, "changed_cells": changed_cells,
        "operations": [
            {"index": index + 1, "kind": operation["kind"], "column": operation["column"],
             "rate": operation["rate"], "requested_rows": requested[index],
             "applied_rows": applied[index], "skipped_rows": skipped[index],
             "applied_rate": applied[index] / count if count else 0.0}
            for index, operation in enumerate(operations)
        ],
    }

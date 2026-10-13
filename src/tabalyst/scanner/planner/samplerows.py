# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The rows of the row sample that an exploration may use (design 20.12, 20.13)."""

from __future__ import annotations

from dataclasses import dataclass

from tabalyst.scanner.models import DatasetResult, RowSample, SampleRow


@dataclass(slots=True)
class UsableSample:
    """The rows of a dataset an exploration may use, and what they stand for."""

    scope: str
    rows: list[SampleRow]
    complete: bool
    sample: RowSample


def usable_rows(dataset: DatasetResult, minimum: int) -> tuple[UsableSample | None, str | None]:
    """The sample rows of a dataset, or why there are none to use: a complete
    sample is the whole population, otherwise only the interior rows are a
    sample (ROW-07); the first and last rows say nothing of the rest. Fewer
    than ``minimum`` rows are too few."""
    sample = dataset.records.sample
    if sample is None or not sample.rows:
        return None, "no_sample"
    if sample.kept != sample.of:
        return None, "sample_reduced"
    complete = sample.complete
    rows = list(sample.rows) if complete else sample.interior()
    if len(rows) < minimum:
        return None, "too_few_rows"
    return UsableSample("all_rows" if complete else "interior_rows", rows, complete, sample), None


def cell_text(row: SampleRow, field_id: str) -> str | None:
    """The text of a single-valued cell, or ``None`` for a row without a value
    (null, absent, or several occurrences, which no pair may use)."""
    cell = row.values.get(field_id)
    if cell is None or len(cell) != 1:
        return None
    return cell[0]

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The copies of the rows that have no ID, counted for the identifier columns of a CSV file with
the engine of Dedup (design 20.43, Unique ID lot 10)."""

from __future__ import annotations

import json
from typing import ClassVar

from tabalyst.dedup.calculation import MISSING_CALCULATION_VERSION
from tabalyst.dedup.store import ENTRY_OVERHEAD
from tabalyst.scanner.planner.analyzer import Analyzer, Assessment, costs, memory
from tabalyst.scanner.planner.analyzers.common import (
    AUTOMATIC_IDENTIFIER_SCORE,
    result_state,
)
from tabalyst.scanner.planner.costmodel import (
    NS_PER_CELL,
    ROWS_COPIES_BYTES,
    cpu_class_for,
)
from tabalyst.scanner.planner.facts import FieldFacts
from tabalyst.scanner.planner.models import Costs, State, Utility

MIB = 1 << 20


def columns_parameter(facts: FieldFacts) -> str:
    """The columns of the count as the plan writes them (part of the key of the result): a list of
    ``[field id, 1-based position]`` in JSON, in the order of the Scan."""
    return json.dumps([[name, position] for name, position, _ in facts.rows_missing_columns])


class MissingIdCopies(Analyzer):
    """Counts, for each identifier column that lacks a value, the extra copies of the rows without it.

    With a missing ID, the extra copies of rows (``E``) mix copies of rows that have an ID and copies
    of rows that have none, so the repetitions of the ID that copies explain are not ``E``. A copy
    repeats the whole row, so the rows that lack a value are the only ones to count: ``E_missing``,
    which gives ``E_present = E - E_missing``. The reading keeps a table of those rows only; the count
    of ``E`` comes from the Scan, a Dedup report or ``duplicate_rows_count``. The planner takes it by
    itself under the criteria of ``duplicate_rows_count`` (design 20.42): the copies and the distinct
    count of a column are known or planned, and the table fits the automatic memory.
    """

    id: ClassVar[str] = "missing_id_copies"
    available: ClassVar[bool] = True
    outputs: ClassVar[tuple[str, ...]] = ("missing_id_copies",)
    rows: ClassVar[bool] = True
    version: ClassVar[int] = MISSING_CALCULATION_VERSION

    def relevant(self, facts: FieldFacts) -> bool:
        return facts.rows_duplicates != "not_applicable"

    def needs_copies(self, facts: FieldFacts) -> bool:
        return True

    def distinct_fields(self, facts: FieldFacts) -> tuple[str, ...] | None:
        return tuple(name for name, _, _ in facts.rows_missing_columns)

    def distinct_known(self, facts: FieldFacts) -> bool:
        return any(known for _, _, known in facts.rows_missing_columns)

    def assess(self, facts: FieldFacts) -> Assessment:
        if not facts.rows_missing_columns:
            return Assessment("not_applicable", ("no_missing_id_candidate",))
        if facts.records_excluded:
            return Assessment("not_applicable", ("records_left_out",))
        if facts.rows_duplicates == "disabled" and not facts.rows_proved:
            # The copies of the rows cannot be counted by Tabalyst, so ``E_present`` has no ``E``.
            return Assessment("not_applicable", ("duplicates_disabled",))
        settings = self.settings.copies
        return Assessment(
            "applicable",
            method="extra_copies_without_id",
            parameters={
                "memory_mb": settings.memory_mb,
                "disk_mb": settings.disk_mb,
                "max_rows": settings.max_rows,
                "columns": columns_parameter(facts),
            },
        )

    def estimate(self, facts: FieldFacts, assessment: Assessment) -> Costs:
        parameters = assessment.parameters
        ceiling = int(parameters["memory_mb"]) * MIB
        # The table holds the rows that lack a value in one of the columns, not the file.
        held = min(facts.rows_missing_records, int(parameters["max_rows"]))
        table = held * (facts.row_bytes + ENTRY_OVERHEAD)
        state = State(
            key=f"rows_without_id:{facts.dataset}",
            memory=memory(
                ROWS_COPIES_BYTES,
                ROWS_COPIES_BYTES + min(table // 2, ceiling),
                ROWS_COPIES_BYTES + min(table, ceiling),
            ),
        )
        work = costs(NS_PER_CELL["rows_without_id"], [state, result_state(self.id, facts)])
        # The class of a share of a cell, as ``DuplicateRows`` states it; ``cell_ns`` stays per record.
        return work.model_copy(
            update={
                "cpu": cpu_class_for(
                    NS_PER_CELL["rows_without_id"] // max(1, facts.dataset_fields)
                )
            }
        )

    def utility(self, facts: FieldFacts, assessment: Assessment) -> Utility:
        # Above the automatic threshold: the count settles the uniqueness of the identifiers that
        # lack a value. The planner still checks that the copies and a distinct count are known.
        return Utility(score=AUTOMATIC_IDENTIFIER_SCORE, reasons=["identifier_missing_copies"])

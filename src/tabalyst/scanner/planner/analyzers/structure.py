# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""What JSON adds to a table: the lengths of the arrays of a field and the sets of
keys of its objects (design 20.33, lot 18)."""

from __future__ import annotations

from typing import ClassVar

from tabalyst.scanner.planner.analyzer import Analyzer, Assessment, costs, memory
from tabalyst.scanner.planner.analyzers.common import result_state
from tabalyst.scanner.planner.costmodel import (
    ARRAY_BYTES,
    ARRAY_ENTRY_BYTES,
    CLASS_NS,
    NS_PER_CELL,
    STRUCTURE_BYTES,
    STRUCTURE_KEY_BYTES,
    STRUCTURE_VARIANT_BYTES,
)
from tabalyst.scanner.planner.facts import FieldFacts
from tabalyst.scanner.planner.models import Costs, State, Utility


class ArrayProfile(Analyzer):
    """Counts every length of the arrays of a field. The Scan has the shortest,
    the longest and the total of the items; this is the whole distribution."""

    id: ClassVar[str] = "array_profile"
    available: ClassVar[bool] = True
    outputs: ClassVar[tuple[str, ...]] = ("array_lengths",)

    def relevant(self, facts: FieldFacts) -> bool:
        return facts.arrays is not None

    def assess(self, facts: FieldFacts) -> Assessment:
        arrays = facts.arrays
        assert arrays is not None
        if arrays.min_length == arrays.max_length:
            # Every array has the same length: the Scan's figures are the whole answer.
            return Assessment(
                "satisfied",
                ("lengths_constant",),
                satisfied_by=f"{facts.where}/arrays",
            )
        settings = self.settings.arrays
        if arrays.max_length - arrays.min_length + 1 > settings.max_lengths:
            return Assessment("not_applicable", ("array_lengths_too_wide",))
        return Assessment(
            "applicable",
            method="length_counts",
            parameters={"max_lengths": settings.max_lengths},
        )

    def estimate(self, facts: FieldFacts, assessment: Assessment) -> Costs:
        arrays = facts.arrays
        assert arrays is not None
        distinct = min(
            arrays.max_length - arrays.min_length + 1,
            arrays.count,
            int(assessment.parameters["max_lengths"]),
        )
        state = State(
            key=f"arrays:{facts.where}",
            memory=memory(
                ARRAY_BYTES + 2 * ARRAY_ENTRY_BYTES,
                ARRAY_BYTES + max(2, distinct // 4) * ARRAY_ENTRY_BYTES,
                ARRAY_BYTES + distinct * ARRAY_ENTRY_BYTES,
            ),
        )
        return costs(NS_PER_CELL["array_profile"], [state, result_state(self.id, facts)])

    def utility(self, facts: FieldFacts, assessment: Assessment) -> Utility:
        # Below the automatic threshold: asked for, or run by a forced pass.
        return Utility(score=40, reasons=["array_lengths"])


class StructureVariants(Analyzer):
    """Counts the sets of keys of the objects of a field, and of the records of a
    JSON source (the field ``$``). Several objects with the same keys are one set."""

    id: ClassVar[str] = "structure_variants"
    available: ClassVar[bool] = True
    roots: ClassVar[bool] = True
    outputs: ClassVar[tuple[str, ...]] = ("key_sets",)

    def relevant(self, facts: FieldFacts) -> bool:
        return facts.objects > 0

    def assess(self, facts: FieldFacts) -> Assessment:
        if facts.untracked_paths:
            # The Scan stopped naming the paths: a key it never named could be in a set.
            return Assessment("not_applicable", ("untracked_paths",))
        if facts.objects < 2:
            return Assessment("not_applicable", ("single_object",))
        if facts.object_keys == 0:
            return Assessment("not_applicable", ("no_keys",))
        if not facts.object_varies:
            # Every key is in every object: one set, which the Scan already says.
            return Assessment("not_applicable", ("uniform_keys",))
        settings = self.settings.structure
        return Assessment(
            "applicable",
            method="key_sets",
            parameters={
                "max_variants": settings.max_variants,
                "max_listed": settings.max_listed,
                "max_keys": settings.max_keys,
            },
        )

    def estimate(self, facts: FieldFacts, assessment: Assessment) -> Costs:
        possible = min(
            facts.objects,
            int(assessment.parameters["max_variants"]),
            2 ** min(facts.object_keys, 30),
        )
        entry = STRUCTURE_VARIANT_BYTES + facts.object_keys // 8
        names = facts.object_keys * STRUCTURE_KEY_BYTES
        state = State(
            key=f"structure:{facts.where}",
            memory=memory(
                STRUCTURE_BYTES + names + entry,
                STRUCTURE_BYTES + names + min(possible, 20) * entry,
                STRUCTURE_BYTES + names + possible * entry,
            ),
        )
        # Every observation of the record meets the table of paths once, whatever
        # the object: the cost follows the fields of the dataset. Declared at the top
        # of the class ``moderate`` at most, as the analyses that read a whole column.
        nanoseconds = min(
            NS_PER_CELL["structure"] + NS_PER_CELL["structure_field"] * facts.dataset_fields,
            CLASS_NS["moderate"],
        )
        return costs(nanoseconds, [state, result_state(self.id, facts)])

    def utility(self, facts: FieldFacts, assessment: Assessment) -> Utility:
        # Below the automatic threshold: asked for, or run by a forced pass.
        return Utility(score=40, reasons=["key_sets"])

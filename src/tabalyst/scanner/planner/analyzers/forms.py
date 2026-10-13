# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""What can be counted of a sensitive field without a value: its masks and, for an
address or a phone number, its classes (design 20.35, decision O61, lot 18)."""

from __future__ import annotations

from typing import ClassVar

from tabalyst.scanner.planner.analyzer import (
    Analyzer,
    Assessment,
    costs,
    memory,
    table_entry,
    text_length,
)
from tabalyst.scanner.planner.analyzers.common import result_state
from tabalyst.scanner.planner.costmodel import (
    CLASS_NS,
    FORMS_BYTES,
    FORMS_ENTRY_BYTES,
    NS_PER_CELL,
)
from tabalyst.scanner.planner.facts import FieldFacts
from tabalyst.scanner.planner.models import Costs, State, Utility


class SensitiveForms(Analyzer):
    """Counts the masks the values of a masked field take, and their class when a
    detector of addresses or phone numbers reads them. A field whose exposure is
    ``hide`` has none: its masks are kept out too (decision O61)."""

    id: ClassVar[str] = "sensitive_forms"
    available: ClassVar[bool] = True
    outputs: ClassVar[tuple[str, ...]] = ("mask_counts", "value_classes")

    def relevant(self, facts: FieldFacts) -> bool:
        # Off, the analyzer concerns no field, so a plan is what it was without it.
        return facts.withheld and self.settings.sensitive.enabled

    def assess(self, facts: FieldFacts) -> Assessment:
        if facts.values == 0:
            return Assessment("not_applicable", ("no_values",))
        if facts.exposure == "hide":
            return Assessment("not_applicable", ("hidden_exposure",))
        settings = self.settings.sensitive
        return Assessment(
            "applicable",
            method="masks",
            parameters={
                "min_count": settings.min_count,
                "max_listed": settings.max_listed,
                "max_tracked": settings.max_tracked,
                "classes": facts.classified[0] if facts.classified else "",
            },
        )

    def estimate(self, facts: FieldFacts, assessment: Assessment) -> Costs:
        limit = int(assessment.parameters["max_tracked"])
        known = facts.frequencies_distinct
        shortest, mean, longest = text_length(facts)
        expected = limit if known is None else min(limit, known)
        state = State(
            key=f"forms:{facts.where}",
            memory=memory(
                FORMS_BYTES + table_entry(shortest) + FORMS_ENTRY_BYTES,
                FORMS_BYTES + expected * (table_entry(mean) + FORMS_ENTRY_BYTES),
                FORMS_BYTES + limit * (table_entry(longest) + FORMS_ENTRY_BYTES),
            ),
        )
        nanoseconds = min(
            NS_PER_CELL["forms"]
            + (NS_PER_CELL["forms_class"] if assessment.parameters["classes"] else 0),
            CLASS_NS["moderate"],
        )
        return costs(nanoseconds, [state, result_state(self.id, facts)])

    def utility(self, facts: FieldFacts, assessment: Assessment) -> Utility:
        # Below the automatic threshold: asked for, or run by a forced pass.
        return Utility(score=40, reasons=["forms_without_values"])

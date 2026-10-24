# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The exact set of the analytical values of a field (design 20.41, Unique ID lot 7).

Same sets, budget and stop as the original values (``exactset``); what goes in is the
analytical text of a string, the output of the enabled ``nfc``, ``trim`` and
``collapse_whitespace`` stages, so ``" A "`` and ``"A"`` are one value as they are in the
Scan's ``analytical_distinct``. A JSON integer, number or boolean has no text to normalize
and enters as it is.
"""

from __future__ import annotations

from collections.abc import Sequence

from tabalyst.scanner.models import FieldResult
from tabalyst.scanner.quality import ANALYTICAL_STAGES
from tabalyst.scanner.secondpass.accumulators import ScanMismatch
from tabalyst.scanner.secondpass.exactset import ExactPool, ExactSet
from tabalyst.scanner.secondpass.models import AnalyticalDistinctCount, DistinctLimited


def analytical_stages(field: FieldResult) -> list[str]:
    """The enabled stages that make the analytical value, in order."""
    return [
        stage.stage
        for stage in field.normalization.stages
        if stage.stage in ANALYTICAL_STAGES and stage.enabled
    ]


class AnalyticalSet(ExactSet):
    """Every distinct analytical value of a field, exactly, within a pool.

    ``changed`` counts the occurrences whose analytical text is not the original string:
    the Scan counts the occurrences each stage modified, so it must lie between the largest
    and the sum of those counters, which proves that both readings normalize alike.
    """

    __slots__ = ("changed",)

    def __init__(self, pool: ExactPool) -> None:
        super().__init__(pool)
        self.changed = 0

    def add_texts(self, raws: Sequence[str], texts: Sequence[str], counts: Sequence[int]) -> None:
        """Account for distinct raw strings, their analytical texts and their counts."""
        if self.limited:
            return
        merged: dict[str, int] = {}
        for raw, text, count in zip(raws, texts, counts, strict=True):
            if text != raw:
                self.changed += count
            merged[text] = merged.get(text, 0) + count
        self.add_strings(list(merged), list(merged.values()))

    def analytical_result(
        self, field: FieldResult
    ) -> AnalyticalDistinctCount | DistinctLimited:
        """The exact count, checked against the Scan, or what is proven when the field
        was stopped."""
        if self.pending and not self.limited:
            self.measure()
        if self.limited:
            return DistinctLimited(values_read=self.values, lower_bound=self.lower_bound)
        if self.values != field.values.count:
            raise ScanMismatch(
                f"values: the second pass found {self.values}, the scan {field.values.count}"
            )
        counters = [
            stage.changed or 0
            for stage in field.normalization.stages
            if stage.stage in ANALYTICAL_STAGES and stage.enabled
        ]
        if counters and not max(counters) <= self.changed <= sum(counters):
            raise ScanMismatch(
                f"changed values: the second pass found {self.changed}, "
                f"the scan between {max(counters)} and {sum(counters)}"
            )
        distinct = self.distinct()
        return AnalyticalDistinctCount(
            stages=analytical_stages(field),
            values=self.values,
            distinct=distinct,
            redundant=self.values - distinct,
            unique=distinct == self.values,
            changed=self.changed,
        )

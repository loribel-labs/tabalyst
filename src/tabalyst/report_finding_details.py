# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Details of a finding of the Findings table: the evidence behind a count.

Today the spelling variants (``variant_groups``): the groups to correct, each
with its spellings. Values go through the exposure of their column, whatever
the document holds (contract summary-table.md 7.6).
"""

from __future__ import annotations

from typing import Literal

from tabalyst.models import ResultModel
from tabalyst.report_views import ColumnView
from tabalyst.scanner.exposure import ExposureGate, ExposureMode

# Groups and spellings written in the hover; the rest is counted.
GROUPS_SHOWN = 20
SPELLINGS_SHOWN = 6

VariantState = Literal["shown", "masked", "hidden"]


class Spelling(ResultModel):
    value: str
    count: int
    # The most frequent spelling of its group: the likely target of a correction.
    most_frequent: bool


class VariantGroupDetail(ResultModel):
    """The spellings of one comparison key, the most frequent first."""

    spellings: list[Spelling]
    # Spellings the group has beyond those listed (never negative).
    more_spellings: int


class VariantDetails(ResultModel):
    """The groups of spelling variants of a column that a reader would correct."""

    state: VariantState
    groups: list[VariantGroupDetail]
    # Groups the scan found beyond those written here; ``None`` when unknown.
    more_groups: int | None

    @property
    def total_groups(self) -> int | None:
        """The groups of the column, listed or not; ``None`` when unknown."""
        return None if self.more_groups is None else len(self.groups) + self.more_groups


def variant_details(column: ColumnView) -> VariantDetails | None:
    """The variants of a column, or ``None`` when it has no group to show.

    A hidden column gives no value; a masked one gives merged masks, which are not
    spellings of the source (``state`` says so). The groups are the largest
    the scan listed, at most ``GROUPS_SHOWN``; ``more_groups`` counts the others when the total is known.
    """
    stats = column.normalization
    if not stats.variant_groups and not stats.variant_group_count:
        return None
    mode: ExposureMode = column.exposure or "show"
    states: dict[ExposureMode, VariantState] = {
        "show": "shown",
        "mask": "masked",
        "hide": "hidden",
    }
    state = states[mode]
    gate = ExposureGate(mode)
    groups: list[VariantGroupDetail] = []
    for group in stats.variant_groups[:GROUPS_SHOWN]:
        counts = gate.counts((item.value, item.count) for item in group.variants)
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        # A mask can merge every spelling of a group into one: nothing to correct.
        if len(ordered) < (1 if mode == "show" else 2):
            continue
        listed = ordered[:SPELLINGS_SHOWN]
        groups.append(
            VariantGroupDetail(
                spellings=[
                    Spelling(value=value, count=count, most_frequent=index == 0)
                    for index, (value, count) in enumerate(listed)
                ],
                more_spellings=max(0, group.distinct_count - len(listed)),
            )
        )
    total = stats.variant_group_count
    return VariantDetails(
        state=state,
        groups=groups,
        more_groups=None if total is None else max(0, total - len(groups)),
    )


class ExposedVariantGroup(ResultModel):
    """A stored group of spelling variants as the column page lists it, through the
    exposure: the key and the spellings are masks for a masked column."""

    key: str
    count: int
    truncated: bool
    variants: list[tuple[str, int]]


def exposed_variant_groups(column: ColumnView) -> list[ExposedVariantGroup]:
    """Every stored variant group of a column through its exposure (CA-19): nothing
    for a hidden column, merged masks for a masked one."""
    mode: ExposureMode = column.exposure or "show"
    if mode == "hide":
        return []
    gate = ExposureGate(mode)
    return [
        ExposedVariantGroup(
            key=gate.value(group.key) or "",
            count=group.count,
            truncated=group.truncated,
            variants=list(gate.counts((v.value, v.count) for v in group.variants).items()),
        )
        for group in column.normalization.variant_groups
    ]

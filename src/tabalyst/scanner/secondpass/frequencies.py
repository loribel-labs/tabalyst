# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The exact frequencies of the analytical values of a field (design 20.8).

The table of the Scan is keyed by native type and analytical text, so the string
``007``, the string ``7`` and the integer 7 are three entries; counters of
integers would merge them. A field of this analysis has at most 1,000 distinct
values, so a table is the smaller state as well as the exact one.
"""

from __future__ import annotations

from decimal import Decimal

from tabalyst.scanner.measures import canonical_text
from tabalyst.scanner.models import Frequencies, ValueCount
from tabalyst.scanner.secondpass.accumulators import ScanMismatch
from tabalyst.scanner.secondpass.models import MAX_MODES, FrequencyTable

# The order of ``type`` in a tie, as the Scan lists them.
TYPE_ORDER = {"string": 0, "integer": 1, "number": 2, "boolean": 3}


class FrequencyAccumulator:
    """A count per ``(native type, analytical text)``. A source that has more
    distinct values than the Scan found cannot be the one it read: new values
    are no longer kept past ``limit`` and the result fails."""

    __slots__ = ("counts", "limit", "overflow")

    def __init__(self, limit: int) -> None:
        self.counts: dict[tuple[str, str], int] = {}
        self.limit = limit
        self.overflow = False

    def add_text(self, text: str, count: int) -> None:
        """A content string of the field, with its analytical text."""
        self._add(("string", text), count)

    def add_native(self, native_type: str, value: object) -> None:
        """A JSON integer, number or boolean."""
        if native_type == "number":
            text = str(Decimal(str(value)))
        else:
            text = canonical_text(native_type, value)
        self._add((native_type, text), 1)

    def _add(self, key: tuple[str, str], count: int) -> None:
        counts = self.counts
        held = counts.get(key)
        if held is not None:
            counts[key] = held + count
        elif len(counts) < self.limit:
            counts[key] = count
        else:
            self.overflow = True

    def result(self, scan: Frequencies, values: int) -> FrequencyTable:
        """The table, checked against the Scan: the same number of values and
        of distinct values, and the entries it lists."""
        if self.overflow:
            raise ScanMismatch(
                f"distinct values: the second pass found more than the {scan.distinct} of the scan"
            )
        ordered = sorted(
            self.counts.items(),
            key=lambda item: (-item[1], item[0][1], TYPE_ORDER[item[0][0]]),
        )
        total = sum(self.counts.values())
        if total != values:
            raise ScanMismatch(f"values: the second pass found {total}, the scan {values}")
        if len(ordered) != scan.distinct:
            raise ScanMismatch(
                f"distinct values: the second pass found {len(ordered)}, the scan {scan.distinct}"
            )
        listed = [
            ValueCount(value=text, type=kind, count=n)  # type: ignore[arg-type]
            for (kind, text), n in ordered
        ]
        if listed[: len(scan.listed)] != scan.listed:
            raise ScanMismatch("the most frequent values are not those the scan listed")
        top = listed[0].count
        tied = [entry for entry in listed if entry.count == top]
        return FrequencyTable(
            count=total,
            distinct=len(listed),
            values=listed,
            modes=tied[:MAX_MODES],
            modes_truncated=len(tied) > MAX_MODES,
        )

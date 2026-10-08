# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Memory budget of the samples of a scan, in bytes of a cost model (design 18.10).

The scan process reserves the size of each sample before the sample is built,
in the order the source is read, so the size granted to a field never depends on
the number of workers or on which one finishes first.
"""

from __future__ import annotations

# Bytes of a bottom-k entry without its text: tuple, dictionary slots, priority
# and counters, plus the slack held between two compactions (measured at 540
# bytes at K = 10,000, benchmarks.md).
SAMPLE_ENTRY_BYTES = 600
# Bytes of an entry of the long texts without its preview: digest, payload and
# bookkeeping.
LONG_ENTRY_BYTES = 700
# The long texts take this share of ``limits.max_sample_memory``.
LONG_SHARE = 8
# The samples by length (design 18.7) take the same share again.
LENGTH_SHARE = 8


def sample_entry_bytes(mean_chars: float) -> int:
    """Modelled bytes of a sample entry whose text has ``mean_chars`` characters
    on average (a Python string takes one to four bytes per character; two
    covers text with accents)."""
    return SAMPLE_ENTRY_BYTES + int(2 * mean_chars)


def long_entry_bytes(preview_chars: int) -> int:
    """Modelled bytes of a long text entry: its preview is the only text."""
    return LONG_ENTRY_BYTES + 4 * preview_chars


class SamplingTotals:
    """Work of the samplers of the whole scan, summed over the fields (design
    18.4); the scan process merges what each field reports."""

    __slots__ = ("k_max", "k_min", "totals")

    def __init__(self) -> None:
        self.totals: dict[str, int] = dict.fromkeys(_COUNTERS, 0)
        self.k_min: int | None = None
        self.k_max: int | None = None

    def merge(self, field: dict[str, int]) -> None:
        """Add the counters of one field."""
        totals = self.totals
        for name in _COUNTERS:
            totals[name] += field.get(name, 0)
        if field.get("bottom_k_fields"):
            k = field["k"]
            self.k_min = k if self.k_min is None else min(self.k_min, k)
            self.k_max = k if self.k_max is None else max(self.k_max, k)


_COUNTERS = (
    "hashed_keys",
    "hit_keys",
    "admitted_keys",
    "rejected_keys",
    "evicted_keys",
    "long_texts_hashed",
    "long_bytes_hashed",
    "bottom_k_fields",
    "reduced_fields",
    "strata_fields",
    "strata_limited_fields",
)


class SampleBudget:
    """``limits.max_sample_memory``: the bytes the samples of the whole scan may
    reserve, with a sub-budget for the long texts and one for the samples by
    length.

    ``grant_sample``, ``grant_long`` and ``grant_strata`` return the size a
    field may have; they are called in the scan process only, in reading order
    (design 18.10).
    A field never takes more than its share of the sample budget, the whole
    budget divided by the fields discovered so far, so one wide source degrades
    every column evenly instead of the late ones first.
    """

    __slots__ = (
        "length_limit",
        "length_reserved",
        "limit",
        "long_limit",
        "long_reserved",
        "reserved",
    )

    def __init__(self, limit: int) -> None:
        self.long_limit = limit // LONG_SHARE
        self.length_limit = limit // LENGTH_SHARE
        self.limit = limit - self.long_limit - self.length_limit
        self.reserved = 0
        self.long_reserved = 0
        self.length_reserved = 0

    def grant_sample(
        self, requested: int, entries: int | None, mean_chars: float, fields: int
    ) -> int:
        """The size K of the sample of a field.

        ``requested`` is the K of the configuration; ``entries`` the number of
        distinct values the sample will hold at most (a complete table), or
        ``None`` when it can grow to K (a released table). ``fields`` is the
        number of fields discovered so far.
        """
        cost = sample_entry_bytes(mean_chars)
        wanted = requested if entries is None else min(requested, entries)
        room = min(self.limit // max(fields, 1), self.limit - self.reserved)
        granted = min(requested, max(room, 0) // cost)
        self.reserved += min(wanted, granted) * cost
        return granted

    def grant_strata(
        self,
        requested: int,
        per_length_k: int,
        entries: int | None,
        mean_chars: float,
        fields: int,
    ) -> int:
        """The number of lengths a field may track: ``requested`` strata of
        ``per_length_k`` entries each, at the cost of a full stratum. A complete
        table holds ``entries`` values at most, which is all it reserves."""
        cost = per_length_k * sample_entry_bytes(mean_chars)
        room = min(
            self.length_limit // max(fields, 1),
            self.length_limit - self.length_reserved,
        )
        granted = min(requested, max(room, 0) // cost)
        wanted = granted * per_length_k
        if entries is not None:
            wanted = min(wanted, entries)
        self.length_reserved += wanted * sample_entry_bytes(mean_chars)
        return granted

    def grant_long(self, requested: int, preview_chars: int) -> int:
        """The size K of the long text sample of a field, first come first
        served: only fields that have a long text ask."""
        cost = long_entry_bytes(preview_chars)
        granted = min(requested, max(self.long_limit - self.long_reserved, 0) // cost)
        self.long_reserved += granted * cost
        return granted

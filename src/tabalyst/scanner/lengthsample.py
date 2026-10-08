# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Bottom-k samples by length of the original text, a stratum per length (design 18.7).

The global sample favors the lengths that most values have; a stratum keeps
a few values of every tracked length, so a rare length stays visible. The
module knows nothing about the product: it receives keys and their priorities.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from itertools import accumulate
from typing import NamedTuple

from tabalyst.scanner import bottomk
from tabalyst.scanner.bottomk import BottomKSampler, Entry, Key

EXACT = "exact"
PARTIAL = "partial"


class OtherLengths:
    """What the strata do not hold (LEN-04): the lengths that are not tracked
    and the occurrences counted while they were not.

    ``occurrences`` also keeps the occurrences a stratum counted before it was
    dropped, so the strata and ``other`` always add up to every occurrence
    the sampler received.
    """

    __slots__ = ("_lengths", "occurrences")

    def __init__(self) -> None:
        self._lengths: set[int] = set()
        self.occurrences = 0

    @property
    def lengths(self) -> int:
        """Distinct lengths that are untracked now."""
        return len(self._lengths)


class Stratum:
    """The values of one length: a bottom-k sample and how it was counted.

    ``count_accuracy`` is ``exact`` when the length was tracked from its first
    occurrence, so a retained value has the exact count of the whole stream
    (the argument of design 18.3), and ``partial`` when it was admitted late
    or readmitted after a drop: only the occurrences from
    ``tracking_started_at_occurrence`` on are counted.
    """

    __slots__ = ("count_accuracy", "length", "sampler", "tracking_started_at_occurrence")

    def __init__(
        self, length: int, sampler: BottomKSampler, accuracy: str, started: int
    ) -> None:
        self.length = length
        self.sampler = sampler
        self.count_accuracy = accuracy
        self.tracking_started_at_occurrence = started

    def entries(self) -> list[Entry]:
        """The retained keys, ordered by ``(priority, key)`` ascending."""
        return self.sampler.entries()

    @property
    def occurrences(self) -> int:
        """Occurrences of this length since its tracking started."""
        return self.sampler.occurrences

    @property
    def retained(self) -> int:
        """Distinct values in the stratum (at most ``per_length_k``)."""
        return self.sampler.retained

    @property
    def distinct_exact(self) -> bool:
        """True while the stratum dropped no value."""
        return self.sampler.distinct_exact

    @property
    def threshold(self) -> int | None:
        """Largest priority kept once a value was dropped, else ``None``."""
        return self.sampler.threshold


class _Group(NamedTuple):
    """The positions of one length in a table that seeds the strata."""

    first: int
    positions: list[int]


class LengthStrataSampler:
    """A bottom-k of ``per_length_k`` values for each of at most ``max_lengths``
    tracked lengths (LEN-01, LEN-04).

    A length is tracked from its first occurrence while a place is free; the
    others are summed in ``other`` and ``limited`` is true. ``drop`` frees a
    place (the memory budget's hook): the length, if it returns, is admitted
    late and its stratum is ``partial`` (LEN-05). The length of a key is the
    number of characters of its text. Occurrences are numbered from 1 in the
    order the sampler receives them.
    """

    __slots__ = (
        "_limits",
        "_occurrences",
        "_strata",
        "max_lengths",
        "other",
        "per_length_k",
        "seed",
    )

    def __init__(self, per_length_k: int, max_lengths: int, *, seed: int = 0) -> None:
        if per_length_k < 1:
            raise ValueError(f"per_length_k must be at least 1, got {per_length_k}")
        if max_lengths < 1:
            raise ValueError(f"max_lengths must be at least 1, got {max_lengths}")
        self.per_length_k = per_length_k
        self.max_lengths = max_lengths
        self.seed = seed
        self.other = OtherLengths()
        self._strata: dict[int, Stratum] = {}
        # Admission limit of each tracked length (``BottomKSampler.admission_limit``),
        # refreshed after every batch: a key above it cannot enter its stratum.
        self._limits: dict[int, float] = {}
        self._occurrences = 0

    @classmethod
    def from_exact_strings(
        cls,
        per_length_k: int,
        max_lengths: int,
        texts: Sequence[str],
        counts: Sequence[int],
        priorities: Sequence[int],
        *,
        seed: int = 0,
    ) -> LengthStrataSampler:
        """The strata of an exact table of strings, in first-seen order.

        The result is the one of streaming the same keys: the lengths are
        tracked in order of first appearance, each from its first occurrence.
        Used when the global sample switches from ``all`` to ``bottom_k``, the
        moment the table holds every value with its exact count.
        """
        sampler = cls(per_length_k, max_lengths, seed=seed)
        sampler._seed(list(map(len, texts)), counts, priorities, texts, None)
        return sampler

    @classmethod
    def from_exact(
        cls,
        per_length_k: int,
        max_lengths: int,
        keys: Sequence[Key],
        counts: Sequence[int],
        priorities: Sequence[int],
        *,
        seed: int = 0,
    ) -> LengthStrataSampler:
        """``from_exact_strings`` for keys ``(native type, text)`` of any type."""
        sampler = cls(per_length_k, max_lengths, seed=seed)
        sampler._seed([len(key[1]) for key in keys], counts, priorities, None, keys)
        return sampler

    def _seed(
        self,
        lengths: list[int],
        counts: Sequence[int],
        priorities: Sequence[int],
        texts: Sequence[str] | None,
        keys: Sequence[Key] | None,
    ) -> None:
        groups: dict[int, _Group] = {}
        for position, length in enumerate(lengths):
            group = groups.get(length)
            if group is None:
                groups[length] = _Group(position, [position])
            else:
                group.positions.append(position)
        before = list(accumulate(counts, initial=0))
        for length, (first, positions) in groups.items():
            members = [counts[position] for position in positions]
            if len(self._strata) >= self.max_lengths:
                self.other._lengths.add(length)
                self.other.occurrences += sum(members)
                continue
            values = [priorities[position] for position in positions]
            if texts is not None:
                sampler = BottomKSampler.from_exact_strings(
                    self.per_length_k,
                    [texts[position] for position in positions],
                    members,
                    seed=self.seed,
                    priorities=values,
                )
            else:
                assert keys is not None
                sampler = BottomKSampler.from_exact(
                    self.per_length_k,
                    dict(zip([keys[position] for position in positions], members)),
                    seed=self.seed,
                    priorities=values,
                )
            self._strata[length] = Stratum(length, sampler, EXACT, before[first] + 1)
            self._limits[length] = sampler.admission_limit
        self._occurrences = before[-1]

    def strata(self) -> dict[int, Stratum]:
        """The tracked strata by length, in ascending length."""
        return dict(sorted(self._strata.items()))

    @property
    def limited(self) -> bool:
        """True when some occurrences are in ``other``: a length is untracked
        or a stratum was dropped (LEN-04)."""
        return self.other.occurrences > 0

    @property
    def occurrences(self) -> int:
        """Occurrences received, whatever stratum holds them."""
        return self._occurrences

    def add(self, key: Key, count: int = 1) -> None:
        """Add ``count`` occurrences of a key (at least 1)."""
        if count < 1:
            raise ValueError(f"count must be at least 1, got {count}")
        self.update((key,), (count,), [bottomk.priority(key, seed=self.seed)])

    def drop(self, length: int) -> None:
        """Give a stratum up, for the memory budget: its occurrences move to
        ``other`` and the place is free. A later occurrence of the length is
        admitted late and its stratum is ``partial``. Does nothing for a
        length that is not tracked."""
        stratum = self._strata.pop(length, None)
        if stratum is None:
            return
        del self._limits[length]
        self.other._lengths.add(length)
        self.other.occurrences += stratum.occurrences

    def update_strings(
        self, texts: Sequence[str], counts: Sequence[int], priorities: Sequence[int]
    ) -> None:
        """A batch of distinct keys of the type ``"string"``, given as their
        texts, with their counts and priorities (computed once by the caller,
        who shares them with the global sample)."""
        self._update(list(map(len, texts)), counts, priorities, texts, None)

    def update(
        self, keys: Sequence[Key], counts: Sequence[int], priorities: Sequence[int]
    ) -> None:
        """A batch of distinct keys with their counts and priorities."""
        self._update([len(key[1]) for key in keys], counts, priorities, None, keys)

    def _update(
        self,
        lengths: list[int],
        counts: Sequence[int],
        priorities: Sequence[int],
        texts: Sequence[str] | None,
        keys: Sequence[Key] | None,
    ) -> None:
        """The hot loop: every key is counted for its length, and only those
        that can enter a stratum are handed to it."""
        limits = self._limits
        other = self.other
        before = self._occurrences
        occurrences: dict[int, int] = {}
        kept: list[int] = []
        for position, (length, count, value) in enumerate(
            zip(lengths, counts, priorities, strict=True)
        ):
            limit = limits.get(length)
            if limit is None:
                if len(self._strata) >= self.max_lengths:
                    other._lengths.add(length)
                    other.occurrences += count
                    continue
                limit = self._admit(length, before + sum(counts[:position]) + 1)
            occurrences[length] = occurrences.get(length, 0) + count
            if value <= limit:
                kept.append(position)
        groups: dict[int, list[int]] = {}
        for position in kept:
            groups.setdefault(lengths[position], []).append(position)
        for length, total in occurrences.items():
            sampler = self._strata[length].sampler
            positions = groups.get(length)
            if positions:
                members = [counts[position] for position in positions]
                if texts is not None:
                    chosen = [("string", texts[position]) for position in positions]
                else:
                    assert keys is not None
                    chosen = [keys[position] for position in positions]
                sampler.update_ranked(
                    chosen, members, [priorities[position] for position in positions]
                )
                total -= sum(members)
            sampler.count_occurrences(total)
            limits[length] = sampler.admission_limit
        self._occurrences = before + sum(counts)

    def _admit(self, length: int, occurrence: int) -> float:
        """Start tracking a length at ``occurrence``; exact when it was never
        met, partial when it was in ``other`` or dropped. Returns its limit."""
        other = self.other
        late = length in other._lengths
        other._lengths.discard(length)
        self._strata[length] = Stratum(
            length,
            BottomKSampler(self.per_length_k, seed=self.seed),
            PARTIAL if late else EXACT,
            occurrence,
        )
        self._limits[length] = math.inf
        return math.inf

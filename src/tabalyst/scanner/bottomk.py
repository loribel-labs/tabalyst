# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Bottom-k sampler of distinct keys by stable hash priority (design 18).

The module knows nothing about the product: a key is
``(native type, canonical original text)`` and the sampler keeps the K keys of
smallest priority, each with its exact count, and estimates the number of
distinct keys (KMV) once it has dropped one.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from itertools import repeat
from typing import NamedTuple

HASH_ALGORITHM = "blake2b"
# Version of the priority function. Any change of the function, of the seed
# encoding or of the key encoding raises it: samples of two versions are not
# comparable.
HASH_VERSION = 1
HASH_BITS = 128

_SPACE = 1 << HASH_BITS
# The start of every encoded key of the type ``string`` (see ``_hasher``).
_STRING_PREFIX = b"string\0"
_SEED_LIMIT = 1 << 64

Key = tuple[str, str]
PriorityFunction = Callable[[Key], int]


class Entry(NamedTuple):
    """A retained key with its priority and its exact count."""

    key: Key
    priority: int
    count: int


@dataclass(frozen=True, slots=True)
class KmvEstimate:
    """Estimate of a number of distinct keys (design 18.5)."""

    estimate: float
    relative_standard_error: float
    k: int
    # The threshold as 32 hexadecimal digits: a 128-bit integer is not a safe
    # JSON number.
    theta_hex: str


@lru_cache(maxsize=32)
def _prototype(seed: int) -> hashlib._Hash:
    """The hash state that has absorbed the seed; every priority copies it."""
    if not 0 <= seed < _SEED_LIMIT:
        raise ValueError(f"seed must be in [0, 2**64), got {seed}")
    return hashlib.blake2b(seed.to_bytes(8, "little"), digest_size=HASH_BITS // 8)


def _hasher(seed: int) -> PriorityFunction:
    """``priority`` with the seed resolved once, for loops."""
    copy = _prototype(seed).copy

    def hashed(key: Key) -> int:
        state = copy()
        # The type is a short ASCII name without NUL, so the NUL separator
        # makes the encoding injective. Lone surrogates survive decoding of
        # some sources and must not raise. One f-string and one encode is the
        # fastest form measured (benchmarks/bottomk_hash.py).
        state.update(f"{key[0]}\0{key[1]}".encode("utf-8", "surrogatepass"))
        return int.from_bytes(state.digest(), "big")

    return hashed


def priority(key: Key, *, seed: int = 0) -> int:
    """Stable priority of a key in ``[0, 2**128)``, smaller is better.

    It depends only on the complete key and the seed (BLAKE2b with a 128-bit
    digest, ``HASH_VERSION``), never on the process: the builtin ``hash()`` is
    randomized per process and never used. The type of the key must not
    contain a NUL character. Raises ``ValueError`` for a seed outside
    ``[0, 2**64)``.
    """
    return _hasher(seed)(key)


def kmv_estimate(*, threshold: int, k: int) -> KmvEstimate:
    """KMV estimate of the distinct keys from the K-th smallest priority.

    ``estimate = (k - 1) / theta`` with ``theta = threshold / 2**128``, and a
    relative standard error of ``1 / sqrt(k - 2)``. Raises ``ValueError`` for
    ``k < 3`` and for a threshold outside ``(0, 2**128)``.
    """
    if k < 3:
        raise ValueError(f"a KMV estimate needs k >= 3, got {k}")
    if not 0 < threshold < _SPACE:
        raise ValueError("the threshold must be in (0, 2**128)")
    return KmvEstimate(
        estimate=((k - 1) << HASH_BITS) / threshold,
        relative_standard_error=1 / math.sqrt(k - 2),
        k=k,
        theta_hex=f"{threshold:032x}",
    )


def _trigger_after_drop(k: int) -> int:
    """Retained keys that trigger the next compaction once keys were dropped:
    a slack of half of K, so a compaction is paid by K / 2 admissions."""
    return k + max(k // 2, 1)


class BottomKSampler:
    """The K distinct keys of smallest priority of a stream, with exact counts.

    Every key is kept with its count until K is exceeded. From then on an
    unretained key enters only if it ranks before the worst retained one, and
    a key that left never comes back because the threshold never increases.
    A key of the final sample therefore entered at its first occurrence and
    never left: its count is the exact count of the whole stream. The sample
    is a function of the set of distinct keys, of the seed and of K, not of
    their order.

    Ranks are ``(priority, key)`` pairs, so equal priorities are ordered by
    the complete key. Between compactions the sampler holds up to half of K
    more keys than K (the admission limit is then the one of the last
    compaction, never tighter than the exact one); every public member
    settles to exactly K first.

    ``priority`` replaces the hash function, for tests (injected collisions).
    """

    __slots__ = (
        "_admitted",
        "_counts",
        "_custom",
        "_hashed",
        "_hits",
        "_limit",
        "_occurrences",
        "_overflow_at",
        "_priorities",
        "_rank",
        "_rejected",
        "_trigger",
        "k",
        "seed",
    )

    def __init__(
        self, k: int, *, seed: int = 0, priority: PriorityFunction | None = None
    ) -> None:
        if k < 1:
            raise ValueError(f"k must be at least 1, got {k}")
        self.k = k
        self.seed = seed
        self._rank: PriorityFunction = (
            priority if priority is not None else _hasher(seed)
        )
        self._custom = priority is not None
        self._counts: dict[Key, int] = {}
        self._priorities: dict[Key, int] = {}
        self._occurrences = 0
        # Counters of the work (design 18.4): priorities computed, keys that
        # entered the sample, and occurrences of keys it already held. They
        # only move in branches that already do work, never per rejected key.
        self._hashed = 0
        self._admitted = 0
        self._hits = 0
        self._rejected = 0
        self._overflow_at: int | None = None
        # Rank of the K-th key at the last compaction, None while nothing was
        # dropped: the domain is exact exactly while it is None.
        self._limit: tuple[int, Key] | None = None
        # Retained keys that trigger a compaction: the first overflow (K + 1)
        # is settled at once, later ones in slack of half of K.
        self._trigger = k + 1

    @classmethod
    def from_exact(
        cls,
        k: int,
        counts: Mapping[Key, int],
        *,
        seed: int = 0,
        priority: PriorityFunction | None = None,
        overflow_at_occurrence: int | None = None,
    ) -> BottomKSampler:
        """The sample of an exact table of keys with their counts.

        Holding more than K keys, the result is the one of streaming the same
        keys: the K best with their counts. The engine calls it when its table
        of T keys is released (design 18.2). ``overflow_at_occurrence`` is the
        occurrence the caller knows proved the overflow, if any. Counts must
        be at least 1.
        """
        sampler = cls(k, seed=seed, priority=priority)
        if counts and min(counts.values()) < 1:
            raise ValueError("counts must be at least 1")
        rank = sampler._rank
        sampler._occurrences = sum(counts.values())
        sampler._hashed = len(counts)
        sampler._admitted = min(len(counts), k)
        sampler._rejected = max(len(counts) - k, 0)
        if len(counts) <= k:
            sampler._counts.update(counts)
            sampler._priorities.update(zip(counts, map(rank, counts)))
            return sampler
        # Sorting every key would cost far more than the hash: the K-th
        # smallest priority bounds the keys worth ranking (ties on it are
        # settled by the complete key, as everywhere).
        keys = list(counts)
        values = list(map(rank, keys))
        cut = sorted(values)[k - 1]
        ranked = sorted((v, key) for v, key in zip(values, keys) if v <= cut)[:k]
        sampler._counts.update((key, counts[key]) for _, key in ranked)
        sampler._priorities.update((key, value) for value, key in ranked)
        sampler._limit = ranked[-1]
        sampler._trigger = _trigger_after_drop(k)
        sampler._overflow_at = overflow_at_occurrence
        return sampler

    @classmethod
    def from_exact_strings(
        cls,
        k: int,
        texts: Sequence[str],
        counts: Sequence[int],
        *,
        seed: int = 0,
        overflow_at_occurrence: int | None = None,
    ) -> BottomKSampler:
        """``from_exact`` for a table of keys of the type ``"string"`` given as
        texts with their counts: the same sample, without building a key or a
        table for the keys that are dropped (the engine's release of a table
        of T strings)."""
        if len(texts) <= k:
            sampler = cls(k, seed=seed)
            sampler.update_strings(texts, counts)
            if counts and min(counts) < 1:
                raise ValueError("counts must be at least 1")
            return sampler
        if min(counts) < 1:
            raise ValueError("counts must be at least 1")
        sampler = cls(k, seed=seed)
        sampler._occurrences = sum(counts)
        sampler._hashed = len(texts)
        sampler._admitted = k
        sampler._rejected = len(texts) - k
        copy = _prototype(seed).copy
        from_bytes = int.from_bytes
        prefix = _STRING_PREFIX
        values = []
        append = values.append
        for text in texts:
            state = copy()
            state.update(prefix + text.encode("utf-8", "surrogatepass"))
            append(from_bytes(state.digest(), "big"))
        cut = sorted(values)[k - 1]
        ranked = sorted(
            (value, texts[position], counts[position])
            for position, value in enumerate(values)
            if value <= cut
        )[:k]
        for value, text, count in ranked:
            key = ("string", text)
            sampler._counts[key] = count
            sampler._priorities[key] = value
        sampler._limit = (ranked[-1][0], ("string", ranked[-1][1]))
        sampler._trigger = _trigger_after_drop(k)
        sampler._overflow_at = overflow_at_occurrence
        return sampler

    def add(self, key: Key, count: int = 1) -> None:
        """Add ``count`` occurrences of a key (at least 1)."""
        if count < 1:
            raise ValueError(f"count must be at least 1, got {count}")
        self.update((key,), (count,))

    def update(self, keys: Iterable[Key], counts: Iterable[int]) -> None:
        """Add distinct keys with their counts, as one batch of occurrences.

        Equivalent to adding the occurrences one by one in any order. Counts
        must be at least 1; this loop is the hot path and does not check.
        """
        retained = self._counts
        priorities = self._priorities
        rank = self._rank
        trigger = self._trigger
        occurrences = self._occurrences
        hashed = admitted = hits = 0
        limit = self._limit
        limit_priority: float
        if limit is None:
            limit_priority, limit_key = math.inf, ("", "")
        else:
            limit_priority, limit_key = limit
        try:
            for key, count in zip(keys, counts, strict=True):
                known = retained.get(key)
                if known is not None:
                    retained[key] = known + count
                    hits += 1
                else:
                    value = rank(key)
                    hashed += 1
                    if value < limit_priority or (
                        value == limit_priority and key < limit_key
                    ):
                        retained[key] = count
                        priorities[key] = value
                        admitted += 1
                        if len(retained) >= trigger:
                            limit_priority, limit_key = self._compact(occurrences + 1)
                            trigger = self._trigger
                occurrences += count
        finally:
            # Also when a key raises, so the count matches the keys admitted.
            self._occurrences = occurrences
            self._hashed += hashed
            self._admitted += admitted
            self._hits += hits
            self._rejected += hashed - admitted

    def update_strings(self, texts: Iterable[str], counts: Iterable[int]) -> None:
        """``update`` for distinct keys of the type ``"string"``, given as their
        texts: the engine's hot path for fields of strings.

        The same result as ``update`` with the keys ``("string", text)``. Once
        the sample is full, a text whose priority is above the limit is
        rejected before any key is built or looked up: a retained key never
        has a priority above the limit.
        """
        if self._custom:
            self.update(zip(repeat("string"), texts), counts)
            return
        retained = self._counts
        priorities = self._priorities
        copy = _prototype(self.seed).copy
        from_bytes = int.from_bytes
        prefix = _STRING_PREFIX
        trigger = self._trigger
        occurrences = self._occurrences
        hashed = admitted = hits = 0
        limit = self._limit
        limit_priority: float
        if limit is None:
            limit_priority, limit_key = math.inf, ("", "")
        else:
            limit_priority, limit_key = limit
        try:
            for text, count in zip(texts, counts, strict=True):
                state = copy()
                state.update(prefix + text.encode("utf-8", "surrogatepass"))
                value = from_bytes(state.digest(), "big")
                hashed += 1
                if value <= limit_priority:
                    key = ("string", text)
                    known = retained.get(key)
                    if known is not None:
                        retained[key] = known + count
                        hits += 1
                    elif value < limit_priority or key < limit_key:
                        retained[key] = count
                        priorities[key] = value
                        admitted += 1
                        if len(retained) >= trigger:
                            limit_priority, limit_key = self._compact(occurrences + 1)
                            trigger = self._trigger
                occurrences += count
        finally:
            self._occurrences = occurrences
            self._hashed += hashed
            self._admitted += admitted
            self._hits += hits
            self._rejected += hashed - admitted - hits

    def _compact(self, overflow_at: int | None = None) -> tuple[int, Key]:
        """Keep the K best keys (more than K are held) and tighten the
        admission limit, which is returned.

        ``overflow_at`` is the occurrence that proves the first overflow, given
        by the caller that adds the (K + 1)th key.
        """
        ranked = sorted(zip(self._priorities.values(), self._priorities))
        k = self.k
        if self._limit is None and overflow_at is not None:
            self._overflow_at = overflow_at
        counts, priorities = self._counts, self._priorities
        if len(ranked) > 2 * k:
            # Dropping most of a large table (``from_exact``): rebuilding the
            # K survivors is cheaper than deleting the rest key by key. In
            # place, since ``update`` holds these dictionaries.
            survivors = ranked[:k]
            kept = {key: counts[key] for _, key in survivors}
            counts.clear()
            counts.update(kept)
            priorities.clear()
            priorities.update((key, value) for value, key in survivors)
        else:
            for _, key in ranked[k:]:
                del counts[key]
                del priorities[key]
        self._limit = ranked[k - 1]
        self._trigger = _trigger_after_drop(k)
        return self._limit

    def _settle(self) -> None:
        if len(self._counts) > self.k:
            self._compact()

    def entries(self) -> list[Entry]:
        """The retained keys ordered by ``(priority, key)`` ascending."""
        self._settle()
        priorities, counts = self._priorities, self._counts
        return [
            Entry(key, value, counts[key])
            for value, key in sorted(zip(priorities.values(), priorities))
        ]

    @property
    def occurrences(self) -> int:
        """Occurrences added."""
        return self._occurrences

    @property
    def distinct_exact(self) -> bool:
        """True while no overflow happened and no entry was dropped."""
        return self._limit is None

    @property
    def overflow_at_occurrence(self) -> int | None:
        """1-based occurrence number of the first occurrence of the (K + 1)th
        distinct key, else ``None`` (also when the caller of ``from_exact`` or
        ``reduce`` did not know it)."""
        return self._overflow_at

    @property
    def threshold(self) -> int | None:
        """Largest priority of the sample once a key was dropped, else ``None``."""
        self._settle()
        return None if self._limit is None else self._limit[0]

    def reduce(self, k: int) -> None:
        """Keep the keys of smaller priority only.

        K can shrink and never grow: keys rejected earlier are lost. Dropping
        entries makes ``distinct_exact`` false. Raises ``ValueError`` for a
        larger ``k``.
        """
        if k < 1:
            raise ValueError(f"k must be at least 1, got {k}")
        if k > self.k:
            raise ValueError(f"k cannot grow from {self.k} to {k}")
        self._settle()
        self.k = k
        self._trigger = k + 1 if self._limit is None else _trigger_after_drop(k)
        if len(self._counts) > k:
            self._compact()

    def kmv(self) -> KmvEstimate | None:
        """The KMV estimate of the distinct keys, or ``None``.

        There is none while the domain is exact (the count is known), for K
        below 3, or for a threshold outside ``(0, 2**128)``, which only
        injected priorities can produce.
        """
        threshold = self.threshold
        if threshold is None or self.k < 3:
            return None
        if not 0 < threshold < _SPACE:
            return None
        return kmv_estimate(threshold=threshold, k=self.k)

    @property
    def counters(self) -> dict[str, int]:
        """Work counters (design 18.4): priorities computed, keys admitted, hits
        on retained keys, keys rejected (computed, neither admitted nor already
        held) and keys evicted (admitted, no longer retained). Hits on keys
        retained before the hash is computed (``update``) are not hashed."""
        self._settle()
        retained = len(self._counts)
        return {
            "hashed": self._hashed,
            "admitted": self._admitted,
            "hits": self._hits,
            "rejected": self._rejected,
            "evicted": self._admitted - retained,
        }

    def holds(self, key: Key) -> bool:
        """Whether the sampler holds the key now. Between compactions it also
        holds keys that a later compaction drops; ``retained`` and ``entries``
        settle first."""
        return key in self._counts

    @property
    def retained(self) -> int:
        """Keys in the sample: at most K, all the distinct keys while exact."""
        self._settle()
        return len(self._counts)

    def __repr__(self) -> str:
        return (
            f"BottomKSampler(k={self.k}, "
            f"retained={min(len(self._counts), self.k)}, "
            f"occurrences={self._occurrences}, exact={self.distinct_exact})"
        )

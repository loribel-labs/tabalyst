# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Bounded samples of the cases of the rules a field is observed to break (design 18.15).

A case is a class of cells (a kind of whitespace, an analytical length) with the exact
number of its cells and a bottom-k of its original texts, chosen by the hash of design 18.3.
"""

from __future__ import annotations

import math
from collections.abc import Hashable, Sequence
from typing import Generic, Literal, TypedDict, TypeVar

from tabalyst.scanner.bottomk import BottomKSampler, string_priorities
from tabalyst.scanner.exposure import ExposureGate
from tabalyst.scanner.models import (
    CaseEntry,
    CaseLengths,
    Cases,
    LengthCase,
    LengthOther,
    WhitespaceCase,
)
from tabalyst.scanner.quality import minority_length_split

# The kinds of whitespace, in the order the document lists them. Bit 2 of the
# changes of ``Normalizer.run`` is the ``trim`` stage, bit 4 ``collapse_whitespace``.
KINDS = ("leading", "trailing", "repeated")
TRIM, COLLAPSE = 2, 4
MEMORY_BUDGET = "memory_budget"

# The class of a cell: the index of a kind of whitespace or an analytical length.
ClassId = TypeVar("ClassId", bound=Hashable)


class _Tracked:
    """One class: its cells, and a sampler of its texts (``None`` when the budget
    granted none or the class is muted). ``limit`` is the admission limit of the
    sampler as of the last batch: a priority above it cannot enter."""

    __slots__ = ("limit", "occurrences", "sampler")

    def __init__(self, sampler: BottomKSampler | None) -> None:
        self.occurrences = 0
        self.sampler = sampler
        self.limit: float = math.inf


class ClassSampler(Generic[ClassId]):
    """A bottom-k of ``k`` texts for each of at most ``max_classes`` classes.

    A class is tracked from its first cell while a place is free (first met, first
    tracked), so a text admitted to its sampler is counted from its first
    occurrence and its count is exact (the argument of design 18.3). The cells of
    the other classes are summed in ``other_occurrences``. A muted class counts its
    cells and keeps no text: the dominant length, which only deferred feeding knows.
    """

    __slots__ = (
        "k",
        "max_classes",
        "muted",
        "other_classes",
        "other_occurrences",
        "seed",
        "tracked",
    )

    def __init__(self, k: int, max_classes: int, seed: int) -> None:
        self.k = k
        self.max_classes = max_classes
        self.seed = seed
        self.muted: ClassId | None = None
        self.tracked: dict[ClassId, _Tracked] = {}
        self.other_classes: set[ClassId] = set()
        self.other_occurrences = 0

    def update(
        self,
        classes: Sequence[ClassId],
        texts: Sequence[str],
        counts: Sequence[int],
        priorities: Sequence[int] | None = None,
    ) -> None:
        """A batch of distinct texts with the class of each and its count.
        ``priorities`` are those of the texts when the caller computed them;
        without them only the texts of a class that keeps some are hashed."""
        tracked = self.tracked
        live: list[int] = []
        owners: list[_Tracked] = []
        for position, (name, count) in enumerate(zip(classes, counts, strict=True)):
            entry = tracked.get(name)
            if entry is None:
                if len(tracked) >= self.max_classes:
                    self.other_classes.add(name)
                    self.other_occurrences += count
                    continue
                keep = self.k > 0 and name != self.muted
                entry = tracked[name] = _Tracked(
                    BottomKSampler(self.k, seed=self.seed) if keep else None
                )
            entry.occurrences += count
            if entry.sampler is not None:
                live.append(position)
                owners.append(entry)
        if not live:
            return
        if priorities is None:
            values = string_priorities([texts[position] for position in live], seed=self.seed)
        else:
            values = [priorities[position] for position in live]
        chosen: dict[int, tuple[_Tracked, list[tuple[str, str]], list[int], list[int]]] = {}
        for position, owner, value in zip(live, owners, values, strict=True):
            if value > owner.limit:
                continue
            group = chosen.get(id(owner))
            if group is None:
                group = chosen[id(owner)] = (owner, [], [], [])
            group[1].append(("string", texts[position]))
            group[2].append(counts[position])
            group[3].append(value)
        for owner, keys, members, ranks in chosen.values():
            sampler = owner.sampler
            assert sampler is not None
            sampler.update_ranked(keys, members, ranks)
            owner.limit = sampler.admission_limit


class CaseCollector:
    """The cases of one field (design 18.15): the kinds of whitespace and, when
    the field has a minority length, the analytical lengths other than the
    dominant one.

    ``k`` is the number of texts per class granted by the memory budget,
    ``requested`` the one the configuration asked for. Whitespace is fed as it is
    met (only the cells a stage changed are hashed). The lengths of a streamed
    field are fed as they are met, since the rule that needs them is only known
    at the end (``observe``); those of a complete table are kept as references
    (``defer``) and fed at the end if the rule holds, hashing nothing otherwise
    (``finish``). Both feedings give the same classes: the lengths are tracked in
    the same order, the dominant one included.
    """

    __slots__ = (
        "dominant",
        "k",
        "lengths",
        "long_whitespace",
        "max_stored",
        "pending",
        "requested",
        "whitespace",
    )

    def __init__(
        self, k: int, requested: int, max_lengths: int, seed: int, max_stored: int
    ) -> None:
        self.k = k
        self.requested = requested
        self.max_stored = max_stored
        self.whitespace: ClassSampler[int] = ClassSampler(k, len(KINDS), seed)
        # Cells of the long texts by kind: counted, never listed (design 18.6).
        self.long_whitespace = [0] * len(KINDS)
        self.lengths: ClassSampler[int] | None = (
            ClassSampler(k, max_lengths, seed) if max_lengths else None
        )
        self.dominant: int | None = None
        self.pending: list[tuple[Sequence[str], Sequence[int], Sequence[int]]] = []

    def observe(
        self,
        raws: Sequence[str],
        counts: Sequence[int],
        lengths: Sequence[int],
        flagged: Sequence[tuple[int, int]],
        priorities: Sequence[int] | None = None,
    ) -> None:
        """Distinct raw strings with their counts and analytical lengths, as
        met; ``flagged`` lists the positions a whitespace stage changed with the
        changes of ``Normalizer.run``. ``priorities`` are those of the strings
        when the caller hashed them for the sample."""
        self._whitespace(raws, counts, flagged, priorities)
        if self.lengths is not None:
            self._lengths(raws, counts, lengths, priorities)

    def defer(
        self,
        raws: Sequence[str],
        counts: Sequence[int],
        lengths: Sequence[int],
        flagged: Sequence[tuple[int, int]],
        priorities: Sequence[int] | None = None,
    ) -> None:
        """``observe`` for a complete table: the lengths wait for ``finish``."""
        self._whitespace(raws, counts, flagged, priorities)
        if self.lengths is not None:
            self.pending.append((raws, counts, lengths))

    def finish(self, histogram: dict[int, int]) -> None:
        """Settle the lengths with the histogram of the analytical lengths of
        the field: the dominant length of the rule of ``minority_length``, or no
        lengths when the rule does not hold."""
        pending, self.pending = self.pending, []
        if self.lengths is None:
            return
        split = minority_length_split(histogram)
        if split is None:
            self.lengths = None
            return
        self.dominant = split[0]
        if pending:
            self.lengths.muted = self.dominant
            for batch in pending:
                self._lengths(*batch)

    def _whitespace(
        self,
        raws: Sequence[str],
        counts: Sequence[int],
        flagged: Sequence[tuple[int, int]],
        priorities: Sequence[int] | None,
    ) -> None:
        classes: list[int] = []
        texts: list[str] = []
        members: list[int] = []
        ranks: list[int] = []
        longest = self.max_stored
        for position, changes in flagged:
            raw = raws[position]
            kinds = []
            if changes & TRIM:
                if raw != raw.lstrip():
                    kinds.append(0)
                if raw != raw.rstrip():
                    kinds.append(1)
            if changes & COLLAPSE:
                kinds.append(2)
            count = counts[position]
            if len(raw) > longest:
                for kind in kinds:
                    self.long_whitespace[kind] += count
                continue
            for kind in kinds:
                classes.append(kind)
                texts.append(raw)
                members.append(count)
                if priorities is not None:
                    ranks.append(priorities[position])
        if classes:
            self.whitespace.update(classes, texts, members, ranks or None)

    def _lengths(
        self,
        raws: Sequence[str],
        counts: Sequence[int],
        lengths: Sequence[int],
        priorities: Sequence[int] | None = None,
    ) -> None:
        sampler = self.lengths
        assert sampler is not None
        longest = self.max_stored
        if not raws:
            return
        if max(map(len, raws)) > longest:
            stored = [position for position, raw in enumerate(raws) if len(raw) <= longest]
            raws = [raws[position] for position in stored]
            counts = [counts[position] for position in stored]
            lengths = [lengths[position] for position in stored]
            if priorities is not None:
                priorities = [priorities[position] for position in stored]
        if raws:
            sampler.update(lengths, raws, counts, priorities)

    def block(self, gate: ExposureGate) -> Cases | None:
        """The ``cases`` member through the exposure gate, or ``None`` when the
        field has no case."""
        whitespace = []
        for kind, name in enumerate(KINDS):
            tracked = self.whitespace.tracked.get(kind)
            occurrences = self.long_whitespace[kind]
            if tracked is not None:
                occurrences += tracked.occurrences
            if occurrences:
                whitespace.append(
                    WhitespaceCase(
                        kind=name,  # type: ignore[arg-type]
                        occurrences=occurrences,
                        **_listing(None if tracked is None else tracked.sampler, gate),
                    )
                )
        lengths = None
        if self.lengths is not None and self.dominant is not None:
            sampler = self.lengths
            classes = [
                LengthCase(
                    length=length,
                    occurrences=tracked.occurrences,
                    **_listing(tracked.sampler, gate),
                )
                for length, tracked in sorted(sampler.tracked.items())
                if length != self.dominant
            ]
            other = (
                LengthOther(
                    lengths=len(sampler.other_classes),
                    occurrences=sampler.other_occurrences,
                )
                if sampler.other_occurrences
                else None
            )
            lengths = CaseLengths(
                max_lengths=sampler.max_classes, other=other, classes=classes
            )
        if not whitespace and lengths is None:
            return None
        reduced = self.k < self.requested
        return Cases(
            per_class_k=self.k,
            requested_per_class_k=self.requested if reduced else None,
            reason=MEMORY_BUDGET if reduced else None,
            whitespace=whitespace or None,
            lengths=lengths,
        )


class _Listing(TypedDict):
    selection: Literal["all", "bottom_k"]
    kept: int
    of: int
    threshold: str | None
    listed: list[CaseEntry]


def _listing(sampler: BottomKSampler | None, gate: ExposureGate) -> _Listing:
    """The members of a class that come from its sampler, through the gate:
    ``mask`` merges equal masks (counts added), ``hide`` lists none, and the
    threshold of a sensitive field is withheld (it is the priority of a value)."""
    if sampler is None:
        return {"selection": "bottom_k", "kept": 0, "of": 0, "threshold": None, "listed": []}
    items = [(entry.key[1], entry.count) for entry in sampler.entries()]
    exact = sampler.distinct_exact
    threshold = sampler.threshold
    exposed = gate.counts(items)
    return {
        "selection": "all" if exact else "bottom_k",
        "kept": len(exposed),
        "of": len(items),
        "threshold": (
            f"{threshold:032x}"
            if threshold is not None and not exact and gate.mode == "show"
            else None
        ),
        "listed": [CaseEntry(value=value, count=count) for value, count in exposed.items()],
    }

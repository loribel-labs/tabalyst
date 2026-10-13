# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The values that patterns and detectors leave out (design 20.20, lot 15).

The Scan counts how many distinct values no pattern reads and how many values a
detector finds invalid or does not match, and keeps ten examples. This keeps the
values themselves with exact counts: each is tracked from its first appearance,
so what it counts is exact, up to ``max_tracked`` distinct values per source and
state; the occurrences of values met after that are only counted. A pattern is
read as the validation of the hierarchy reads it (design 20.9): a value is in the
pattern of its family that has its lengths, and a value that no pattern holds is
left out; a detector is replayed as the first pass decides it.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from tabalyst.scanner.config import PatternInferenceSettings
from tabalyst.scanner.models import DetectorComplete, FieldPatternsComplete, FieldResult
from tabalyst.scanner.planner.costmodel import MEASURE_MEMO_ENTRIES
from tabalyst.scanner.secondpass.accumulators import ScanMismatch
from tabalyst.scanner.secondpass.exactset import ExactPool, ExactSet
from tabalyst.scanner.secondpass.models import (
    PatternExclusions,
    PatternProfile,
    ReasonCount,
    ResidualDetector,
    ResidualResult,
    ResidualTable,
    ResidualValue,
)
from tabalyst.scanner.secondpass.patternreader import (
    TOO_COMPLEX,
    TOO_LONG,
    HierarchyReader,
)
from tabalyst.scanner.secondpass.replay import CellReader, Reading

# Distinct texts per detector whose reading is remembered from one batch to the
# next: the same as for the dates and the values with a unit.
MEMO_ENTRIES = MEASURE_MEMO_ENTRIES
# The name the plan gives the pattern source in its ``sources`` parameter.
PATTERN_SOURCE = "pattern"

# The first record of a value: the router hands the function of a batch, the
# samples hand none.
FirstRecord = Callable[[str], int]


class _Table:
    """The tracked values of one source and state, with their counts and first
    records. A value enters at its first appearance while there is room, so its
    count is exact; once the table is full the occurrences of new values are
    counted in ``untracked``."""

    __slots__ = ("entries", "occurrences", "reasons", "too_long", "untracked")

    def __init__(self) -> None:
        self.entries: dict[str, list[int | None]] = {}
        self.occurrences = 0
        self.untracked = 0
        self.too_long = 0
        self.reasons: dict[str, int] = {}

    def add(
        self,
        value: str,
        count: int,
        record: int | None,
        limit: int,
        max_length: int,
        reason: str | None = None,
    ) -> None:
        self.occurrences += count
        if reason is not None:
            self.reasons[reason] = self.reasons.get(reason, 0) + count
        if len(value) > max_length:
            self.too_long += count
            return
        slot = self.entries.get(value)
        if slot is None:
            if len(self.entries) >= limit:
                self.untracked += count
                return
            self.entries[value] = [count, record]
            return
        slot[0] += count  # type: ignore[operator]
        known = slot[1]
        if record is not None and (known is None or record < known):
            slot[1] = record

    def result(
        self,
        source: str,
        detector: str | None,
        state: str,
        max_listed: int,
    ) -> ResidualTable:
        ranked = sorted(self.entries.items(), key=lambda item: (-item[1][0], item[0]))  # type: ignore[operator]
        return ResidualTable(
            source=source,  # type: ignore[arg-type]
            detector=detector,
            state=state,  # type: ignore[arg-type]
            occurrences=self.occurrences,
            distinct=len(self.entries),
            complete=not (self.untracked or self.too_long),
            untracked=self.untracked,
            too_long=self.too_long,
            truncated=len(ranked) > max_listed,
            listed=[
                ResidualValue(value=value, count=slot[0], first_record=slot[1])  # type: ignore[arg-type]
                for value, slot in ranked[:max_listed]
            ],
            reasons=(
                [
                    ReasonCount(reason=reason, count=count)
                    for reason, count in sorted(self.reasons.items(), key=lambda i: (-i[1], i[0]))
                ]
                if state == "invalid"
                else None
            ),
        )


class _Replay:
    """One detector replayed on the field: its tally, its two tables and the
    readings of the texts it met."""

    __slots__ = ("ambiguous", "eligible", "invalid", "matched", "memo", "not_matched", "not_tested", "tables")

    def __init__(self) -> None:
        self.eligible = 0
        self.matched = 0
        self.ambiguous = 0
        self.invalid = 0
        self.not_matched = 0
        self.not_tested = 0
        self.tables = {"invalid": _Table(), "not_matched": _Table()}
        self.memo: dict[str, Reading] = {}


class ResidualAccumulator:
    """The values a pattern leaves out and the values a detector finds invalid or
    does not match, for one field."""

    __slots__ = (
        "cell_ns",
        "entry",
        "examples",
        "excluded",
        "max_listed",
        "max_tracked",
        "max_value_length",
        "occurrences",
        "other",
        "profile",
        "reader",
        "replays",
        "values",
    )

    def __init__(
        self,
        *,
        entry: FieldPatternsComplete | None,
        field: FieldResult | None,
        inference: PatternInferenceSettings,
        detectors: Sequence[str],
        pool: ExactPool,
        max_listed: int,
        max_tracked: int,
        max_value_length: int,
        cell_ns: int = 0,
    ) -> None:
        self.entry = entry
        # The Scan must give the samples the entry was made from: a reader that
        # cannot recognize them again raises ``ScanMismatch``.
        self.reader: HierarchyReader | None = None
        if entry is not None:
            assert field is not None
            self.reader = HierarchyReader.build(entry, field, inference)
        self.max_listed = max_listed
        self.max_tracked = max_tracked
        self.max_value_length = max_value_length
        # What the plan expects a cell to cost: it weighs the route among the
        # workers and is no input of the result.
        self.cell_ns = cell_ns
        self.values = 0
        count = 0 if entry is None else len(entry.all_patterns())
        self.occurrences = [0] * count
        self.other = _Table()
        self.excluded = {"non_string": 0, "too_long": 0, "too_complex": 0}
        # One set of the distinct values each candidate reads, in the pool of the
        # run, and the first value each read with its record.
        self.profile = [ExactSet(pool) for _ in range(count)]
        self.examples: list[tuple[str, int | None] | None] = [None] * count
        self.replays = {detector: _Replay() for detector in detectors}

    @property
    def needs_text(self) -> bool:
        """Whether the analytical text of each string is needed."""
        return bool(self.replays)

    @property
    def uses_pool(self) -> bool:
        """Whether the accumulator holds exact sets of the run's pool."""
        return bool(self.profile)

    def add(
        self,
        reader: CellReader,
        raws: Sequence[str],
        counts: Sequence[int],
        texts: Sequence[str] | None,
        first: FirstRecord | None,
    ) -> None:
        """Account for the distinct content strings of a batch with their counts
        and, for the detectors, their analytical texts. ``first`` gives the record
        of the first occurrence of a string in the batch."""
        self.values += sum(counts)
        hierarchy = self.reader
        if hierarchy is not None:
            self._pattern(hierarchy, raws, counts, first)
        if self.replays:
            assert texts is not None
            for detector, replay in self.replays.items():
                self._detector(reader, detector, replay, raws, counts, texts, first)

    def add_native(self, count: int = 1) -> None:
        """JSON integers, numbers or booleans: not strings, so not tested."""
        self.values += count
        self.excluded["non_string"] += count

    def _pattern(
        self,
        hierarchy: HierarchyReader,
        raws: Sequence[str],
        counts: Sequence[int],
        first: FirstRecord | None,
    ) -> None:
        read = hierarchy.read
        pattern_of = hierarchy.pattern_of
        groups: dict[int, tuple[list[str], list[int]]] = {}
        for raw, count in zip(raws, counts, strict=True):
            outcome, family, slot, _, _ = read(raw, False)
            if outcome == TOO_LONG:
                self.excluded["too_long"] += count
                continue
            if outcome == TOO_COMPLEX:
                self.excluded["too_complex"] += count
                continue
            # A value of a family whose lengths no pattern holds is left out too.
            found = -1 if family is None else pattern_of[slot]
            if found < 0:
                self.other.add(
                    raw,
                    count,
                    None if first is None else first(raw),
                    self.max_tracked,
                    self.max_value_length,
                )
                continue
            self.occurrences[found] += count
            group = groups.get(found)
            if group is None:
                group = groups[found] = ([], [])
                if self.examples[found] is None:
                    self.examples[found] = (raw, None if first is None else first(raw))
            group[0].append(raw)
            group[1].append(count)
        for number, (members, weights) in groups.items():
            self.profile[number].add_strings(members, weights)

    def _detector(
        self,
        reader: CellReader,
        detector: str,
        replay: _Replay,
        raws: Sequence[str],
        counts: Sequence[int],
        texts: Sequence[str],
        first: FirstRecord | None,
    ) -> None:
        memo = replay.memo
        missing = [text for text in dict.fromkeys(texts) if text not in memo]
        if missing:
            read = reader.readings(detector, missing)
            if read is None:
                raise ScanMismatch(f"the {detector} detector cannot be replayed")
            room = MEMO_ENTRIES - len(memo)
            fresh = dict(zip(missing, read, strict=True))
            for text in missing[:room] if room > 0 else ():
                memo[text] = fresh[text]
        else:
            fresh = {}
        limit, size = self.max_tracked, self.max_value_length
        for raw, count, text in zip(raws, counts, texts, strict=True):
            state, reason = memo[text] if text in memo else fresh[text]
            replay.eligible += count
            if state == "matched":
                replay.matched += count
            elif state == "ambiguous":
                replay.ambiguous += count
            elif state == "not_tested":
                replay.not_tested += count
            else:
                if state == "invalid":
                    replay.invalid += count
                else:
                    replay.not_matched += count
                replay.tables[state].add(
                    text, count, None if first is None else first(raw), limit, size, reason
                )

    # The result -------------------------------------------------------------

    def result(self, field: FieldResult, computed_from: str, records: bool) -> ResidualResult:
        """The tables and the profile of the patterns, checked against the Scan:
        the values of the field and, for each detector, what its coverage
        counted. Raises ``ScanMismatch`` when they disagree."""
        if self.values != field.values.count:
            raise ScanMismatch(
                f"values: the second pass found {self.values}, the scan {field.values.count}"
            )
        tables: list[ResidualTable] = []
        patterns: list[PatternProfile] | None = None
        excluded: PatternExclusions | None = None
        exact = True
        entry = self.entry
        if entry is not None:
            tallied = sum(self.occurrences) + self.other.occurrences + sum(self.excluded.values())
            if tallied != self.values:
                raise ScanMismatch("the counts of the patterns do not add up to the values read")
            patterns = []
            for number, candidate in enumerate(entry.all_patterns()):
                held = self.profile[number]
                if held.pending and not held.limited:
                    held.measure()
                example = self.examples[number]
                accurate = not held.limited
                exact = exact and accurate
                patterns.append(
                    PatternProfile(
                        id=candidate.id,
                        render=candidate.render,
                        occurrences=self.occurrences[number],
                        distinct=held.distinct(),
                        distinct_accuracy="exact" if accurate else "at_least",
                        example=None if example is None else example[0],
                        first_record=None if example is None else example[1],
                    )
                )
            excluded = PatternExclusions(**self.excluded)
            if self.other.occurrences:
                tables.append(
                    self.other.result(PATTERN_SOURCE, None, "other", self.max_listed)
                )
        tallies: list[ResidualDetector] = []
        for detector, replay in self.replays.items():
            found = _detector(field, detector)
            self._check(detector, replay, found)
            tallies.append(
                ResidualDetector(
                    detector=detector,
                    eligible=replay.eligible,
                    matched=replay.matched,
                    ambiguous=replay.ambiguous,
                    invalid=replay.invalid,
                    not_matched=replay.not_matched,
                    scan_not_tested=found.coverage.not_tested,
                )
            )
            for state in ("invalid", "not_matched"):
                table = replay.tables[state]
                if table.occurrences:
                    tables.append(table.result("detector", detector, state, self.max_listed))
        exact = exact and all(table.complete for table in tables)
        return ResidualResult(
            accuracy="exact" if exact else "exact_counts",
            computed_from=computed_from,  # type: ignore[arg-type]
            records=records,
            values=self.values,
            tables=tables,
            patterns=patterns,
            pattern_excluded=excluded,
            detectors=tallies,
        )

    @staticmethod
    def _check(detector: str, replay: _Replay, found: DetectorComplete) -> None:
        coverage = found.coverage
        if replay.eligible != coverage.eligible:
            raise ScanMismatch(
                f"{detector} strings: the second pass found {replay.eligible}, "
                f"the scan {coverage.eligible}"
            )
        read = (replay.matched, replay.ambiguous, replay.invalid, replay.not_matched)
        counted = (coverage.matched, coverage.ambiguous, coverage.invalid, coverage.not_matched)
        if coverage.not_tested == 0:
            if read != counted or replay.not_tested:
                raise ScanMismatch(
                    f"{detector} states: the second pass found {read}, the scan {counted}"
                )
        # The Scan left values untested: this pass reads them all, so it finds at
        # least what the Scan found and no more than those values can add.
        elif any(a < b for a, b in zip(read, counted, strict=True)) or (
            sum(read) - sum(counted) > coverage.not_tested
        ):
            raise ScanMismatch(
                f"{detector} states: the second pass found {read}, the scan {counted} "
                f"and {coverage.not_tested} values not tested"
            )


def _detector(field: FieldResult, detector: str) -> DetectorComplete:
    for result in field.detectors:
        if result.id == detector:
            if not isinstance(result, DetectorComplete):
                raise ScanMismatch(f"the {detector} detector of the scan is {result.status}")
            return result
    raise ScanMismatch(f"the scan has no {detector} detector for the field")


def derive_from_samples(
    accumulator: ResidualAccumulator, field: FieldResult, reader: CellReader
) -> None:
    """Fill ``accumulator`` from the exact counts of a Scan that holds every
    distinct original value of the field, without reading the source (and so
    without a record). Raises ``ScanMismatch`` when the Scan does not hold them."""
    samples = field.values.samples
    if (
        samples.selection != "all"
        or samples.kept != samples.of
        or samples.long_texts is not None
        or any(entry.count_accuracy != "exact" for entry in samples.listed)
    ):
        raise ScanMismatch("the scan does not hold every distinct value with its exact count")
    strings = [entry for entry in samples.listed if entry.type == "string"]
    cells = reader.cells([str(entry.value) for entry in strings], numbers=False)
    raws: list[str] = []
    counts: list[int] = []
    texts: list[str] = []
    for entry, cell in zip(strings, cells, strict=True):
        if cell.length >= 0:
            raws.append(str(entry.value))
            counts.append(entry.count)
            texts.append(cell.text)
    accumulator.add(reader, raws, counts, texts if accumulator.needs_text else None, None)
    for entry in samples.listed:
        if entry.type != "string":
            accumulator.add_native(entry.count)

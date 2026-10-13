# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Validation of the inferred patterns of a field over every occurrence (design
20.9, PAT-07 to PAT-11).

The patterns of the Scan were found in a sample of the distinct values; this
counts the occurrences of the whole field. Each value is read by the candidates
of the Scan with the same matcher the inference uses, one pass and no
backtracking, and counts for the most specific candidate that reads it (PAT-08).
The population is the one of the inference: a value longer than
``max_value_length``, of more than ``MAX_TOKENS`` tokens, or that is not a
string is excluded and counted as such.
"""

from __future__ import annotations

from collections.abc import Sequence

from tabalyst.scanner.features import PatternClassifier, ascii_regex
from tabalyst.scanner.models import (
    FieldPatterns,
    FieldPatternsComplete,
    FieldResult,
)
from tabalyst.scanner.patterninfer import GRAMMAR_VERSION, MAX_TOKENS, matches, tokenize
from tabalyst.scanner.secondpass.accumulators import ScanMismatch
from tabalyst.scanner.secondpass.models import (
    PatternCounts,
    PatternExclusions,
    PatternOverlapCount,
    PatternTally,
)

__all__ = ["PatternAccumulator", "ascii_regex", "derive_from_samples", "pattern_entry"]


def pattern_entry(
    patterns: Sequence[FieldPatterns], dataset: str, field: str
) -> FieldPatternsComplete | None:
    """The complete pattern entry of a field of the Scan, if it has one."""
    for entry in patterns:
        if entry.dataset == dataset and entry.field == field:
            return entry if isinstance(entry, FieldPatternsComplete) else None
    return None


class PatternAccumulator:
    """A count per candidate pattern of a field, plus what no candidate reads
    and what the population leaves out."""

    __slots__ = (
        "classifier",
        "entry",
        "excluded",
        "occurrences",
        "other",
        "overlaps",
        "values",
    )

    def __init__(self, entry: FieldPatternsComplete, max_value_length: int) -> None:
        self.entry = entry
        # Candidates tried from the most specific: the first that reads a value
        # is the one it counts for, the others only tell of an overlap.
        self.classifier = PatternClassifier(entry, max_value_length)
        self.occurrences = [0] * len(entry.candidates)
        self.other = 0
        self.values = 0
        self.overlaps: dict[tuple[int, ...], int] = {}
        self.excluded = {"non_string": 0, "too_long": 0, "too_complex": 0}

    def add_strings(self, raws: Sequence[str], counts: Sequence[int]) -> None:
        """Account for the distinct content strings of a batch with their
        counts."""
        # The loop of ``PatternClassifier.classify`` is repeated here, not called:
        # a call and a tuple for each distinct value cost a third more than the
        # regular expressions themselves on a column of identifiers (measured at
        # lot 8b), and the cost model of the validation stands on this loop.
        classifier = self.classifier
        limit = classifier.max_length
        matchers = classifier.matchers
        regexes = classifier.regexes
        order = classifier.order
        excluded = self.excluded
        occurrences = self.occurrences
        overlaps = self.overlaps
        for raw, count in zip(raws, counts, strict=True):
            self.values += count
            size = len(raw)
            if size > limit:
                excluded["too_long"] += count
                continue
            # A token has at least one character: a short value cannot have too
            # many, and the others are tokenized only when they are long enough.
            if size > MAX_TOKENS and len(tokenize(raw)) > MAX_TOKENS:
                excluded["too_complex"] += count
                continue
            first = -1
            found: list[int] | None = None
            ascii_value = raw.isascii()
            for number in order:
                if (
                    regexes[number].fullmatch(raw) is not None
                    if ascii_value
                    else matches(matchers[number], raw)
                ):
                    if first < 0:
                        first = number
                    else:
                        if found is None:
                            found = [first]
                        found.append(number)
            if first < 0:
                self.other += count
                continue
            occurrences[first] += count
            if found is not None:
                key = tuple(sorted(found))
                overlaps[key] = overlaps.get(key, 0) + count

    def add_native(self, count: int = 1) -> None:
        """JSON integers, numbers or booleans: not strings, so not tested."""
        self.values += count
        self.excluded["non_string"] += count

    def result(self, expected_values: int, computed_from: str) -> PatternCounts:
        """The counts, checked against the Scan: the values read are the values
        the Scan counted, and they add up."""
        if self.values != expected_values:
            raise ScanMismatch(
                f"values: the second pass found {self.values}, the scan {expected_values}"
            )
        candidates = self.entry.candidates
        matched = sum(self.occurrences)
        excluded = sum(self.excluded.values())
        if matched + self.other + excluded != self.values:
            raise ScanMismatch("the counts of the patterns do not add up to the values read")
        return PatternCounts(
            computed_from=computed_from,  # type: ignore[arg-type]
            grammar_version=GRAMMAR_VERSION,
            values=self.values,
            matched=matched,
            candidates=[
                PatternTally(id=candidate.id, render=candidate.render, occurrences=count)
                for candidate, count in zip(candidates, self.occurrences, strict=True)
            ],
            other=self.other,
            excluded=PatternExclusions(**self.excluded),
            overlaps=[
                PatternOverlapCount(
                    patterns=[candidates[number].id for number in key], occurrences=count
                )
                for key, count in sorted(self.overlaps.items())
            ],
        )


def derive_from_samples(accumulator: PatternAccumulator, field: FieldResult) -> None:
    """Fill ``accumulator`` from the exact counts of a Scan that holds every
    distinct original value of the field, without reading the source.

    Raises ``ScanMismatch`` when the Scan does not hold them: the planner only
    leaves the source unread for a population of the inference that is complete
    (``basis`` ``all_distinct``), which this checks again.
    """
    samples = field.values.samples
    if (
        samples.selection != "all"
        or samples.kept != samples.of
        or samples.long_texts is not None
        or any(entry.count_accuracy != "exact" for entry in samples.listed)
    ):
        raise ScanMismatch("the scan does not hold every distinct value with its exact count")
    strings = [entry for entry in samples.listed if entry.type == "string"]
    accumulator.add_strings(
        [entry.value for entry in strings], [entry.count for entry in strings]
    )
    for entry in samples.listed:
        if entry.type != "string":
            accumulator.add_native(entry.count)

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Derived features of a column and the classes of a category (design 20.13).

A feature turns each value of a column into a class of a small, fixed set known
before the source is read again (REL-01, REL-12): the pattern that reads it, its
length, its first characters, or the value itself (design 20.22). A category
column is coded the same way against
the exact table of frequencies of the Scan. A value is coded ``MISSING`` when
the row has none and ``UNCLASSIFIED`` when the feature cannot classify it; any
other value goes to a named class or to the explicit class ``other``, so nothing
creates an axis while the source streams. The exploration of the row sample and
the second pass code values with the same objects.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from tabalyst.scanner.config import PatternInferenceSettings
from tabalyst.scanner.measures import canonical_text
from tabalyst.scanner.models import (
    FieldPatternsComplete,
    FieldResult,
    Frequencies,
    PatternToken,
)

if TYPE_CHECKING:
    # The second pass imports the planner, which imports this module: the reader
    # is only a type here.
    from tabalyst.scanner.secondpass.replay import CellReader

# Codes below zero are not classes.
MISSING = -1
UNCLASSIFIED = -2

# The features a column offers, in the order of their precedence in a tie.
FEATURES = ("pattern", "length", "prefix", "value")
FEATURE_VERSION = 1
OTHER_ID = "other"

# The order of ``type`` in a tie, as the frequencies of the Scan list them.
TYPE_ORDER = {"string": 0, "integer": 1, "number": 2, "boolean": 3}

# The ASCII reading of each class of the grammar. For an ASCII value the
# letters of `letter_unicode` are the ASCII ones.
_ASCII_CLASS = {
    "digit_ascii": "[0-9]",
    "upper_ascii": "[A-Z]",
    "lower_ascii": "[a-z]",
    "letter_unicode": "[A-Za-z]",
    "upper_digit": "[0-9A-Z]",
    "lower_digit": "[0-9a-z]",
    "alphanumeric": "[0-9A-Za-z]",
}


def ascii_regex(signature: Sequence[PatternToken]) -> re.Pattern[str]:
    """A regular expression that reads an ASCII value like ``matches`` does.

    Every repeat is possessive (``{low,high}+``): it takes as many characters as
    allowed and never gives one back, which is what the matcher of the grammar
    does, so nothing backtracks whatever the value (PAT-07). The compiled form
    runs in C, an order of magnitude faster than the token loop.
    """
    parts = []
    for token in signature:
        unit = (
            f"(?:{re.escape(token.text or '')})"
            if token.kind == "literal"
            else _ASCII_CLASS[token.kind]
        )
        parts.append(f"{unit}{{{token.min},{token.max}}}+")
    return re.compile("".join(parts))


@dataclass(frozen=True, slots=True)
class FeatureClass:
    """One class of a feature or one category: a stable ``id``, the ``label`` a
    reader sees (a pattern rendering, a length, a prefix, a category value) and,
    for a category of a JSON file, the native ``type`` of its value."""

    id: str
    label: str
    kind: Literal["value", "other"] = "value"
    type: str | None = None


def native_key(native_type: str, value: object) -> tuple[str, str]:
    """The key of the table of frequencies for a JSON integer, number or
    boolean: its native type and canonical text."""
    if native_type == "number":
        return native_type, str(Decimal(str(value)))
    return native_type, canonical_text(native_type, value)


class Coder:
    """Codes the values of a column into the classes of a feature.

    ``classes`` lists the named classes then ``other``; the code of a value is
    the index of its class. ``domain`` is the domain of the values the feature
    reads (design 21). The three ``code_*`` methods serve a batch of strings of
    a CSV file or a string of a record, a native JSON value, and the cells of a
    row sample, whose native type is not known.
    """

    kind: str = ""
    domain: Literal["analytical", "original"] = "analytical"

    def __init__(self, reader: CellReader, classes: list[FeatureClass]) -> None:
        self.reader = reader
        self.classes = (*classes, FeatureClass(OTHER_ID, OTHER_ID, "other"))
        self.other = len(classes)

    def code_strings(self, raws: Sequence[str]) -> list[int]:
        raise NotImplementedError

    def code_native(self, native_type: str, value: object) -> int:
        return UNCLASSIFIED

    def code_texts(self, texts: Sequence[str]) -> list[int]:
        return self.code_strings(texts)


class CategoryCoder(Coder):
    """A category column against the exact frequencies of the Scan: the
    ``max_categories`` most frequent analytical values are classes, the rest is
    ``other``."""

    kind = "category"
    domain = "analytical"

    def __init__(
        self, reader: CellReader, frequencies: Frequencies, max_categories: int
    ) -> None:
        ranked = sorted(
            frequencies.listed,
            key=lambda entry: (-entry.count, entry.value, TYPE_ORDER.get(entry.type, 9)),
        )[:max_categories]
        super().__init__(
            reader,
            [
                FeatureClass(
                    f"c{number}",
                    entry.value,
                    type=None if entry.type == "string" else entry.type,
                )
                for number, entry in enumerate(ranked, 1)
            ],
        )
        self.keys: dict[tuple[str, str], int] = {
            (entry.type, entry.value): number for number, entry in enumerate(ranked)
        }
        self.by_text: dict[str, int] = {}
        for number, entry in enumerate(ranked):
            self.by_text.setdefault(entry.value, number)

    def code_strings(self, raws: Sequence[str]) -> list[int]:
        keys, other = self.keys, self.other
        return [
            MISSING if cell.length < 0 else keys.get(("string", cell.text), other)
            for cell in self.reader.cells(raws, numbers=False)
        ]

    def code_native(self, native_type: str, value: object) -> int:
        return self.keys.get(native_key(native_type, value), self.other)

    def code_texts(self, texts: Sequence[str]) -> list[int]:
        by_text, other = self.by_text, self.other
        return [
            MISSING if cell.length < 0 else by_text.get(cell.text, other)
            for cell in self.reader.cells(texts, numbers=False)
        ]


class ValueCoder(CategoryCoder):
    """The value itself, against the exact frequencies of the Scan: the most
    frequent analytical values are classes and the rest is ``other``. It is the
    category coder on the column side of a table, so a category can be set
    against another category (design 20.22)."""

    kind = "value"


class PatternCoder(Coder):
    """The pattern of the hierarchy that reads a value, over the original values:
    the families recognize a value by its structure and its pattern by its lengths,
    as the validation does (design 20.9). A value of no family, or of a family whose
    lengths no pattern holds, is ``other``; a value the population of the inference
    leaves out is unclassified. The classes are the patterns in the order of the
    document."""

    kind = "pattern"
    domain = "original"

    def __init__(
        self,
        reader: CellReader,
        entry: FieldPatternsComplete,
        field: FieldResult,
        settings: PatternInferenceSettings,
    ) -> None:
        # The reader of the second pass imports the planner, which imports this
        # module: it is loaded when a coder is made.
        from tabalyst.scanner.secondpass.patternreader import HierarchyReader

        super().__init__(
            reader, [FeatureClass(pattern.id, pattern.render) for pattern in entry.all_patterns()]
        )
        self.hierarchy = HierarchyReader.build(entry, field, settings)

    def code_strings(self, raws: Sequence[str]) -> list[int]:
        classify = self.hierarchy.pattern_class
        other = self.other
        codes: list[int] = []
        for raw, content in zip(raws, self.reader.content(raws), strict=True):
            if not content:
                codes.append(MISSING)
                continue
            found = classify(raw)
            codes.append(UNCLASSIFIED if found is None else other if found < 0 else found)
        return codes


class LengthCoder(Coder):
    """The length of the analytical text, in characters: the lengths of the exact
    histogram of the Scan are the classes, in increasing order."""

    kind = "length"
    domain = "analytical"

    def __init__(self, reader: CellReader, lengths: list[int]) -> None:
        super().__init__(reader, [FeatureClass(f"l{n}", str(n)) for n in lengths])
        self.index = {n: number for number, n in enumerate(lengths)}

    def code_strings(self, raws: Sequence[str]) -> list[int]:
        index, other = self.index, self.other
        return [
            MISSING if cell.length < 0 else index.get(cell.length, other)
            for cell in self.reader.cells(raws, numbers=False)
        ]


class PrefixCoder(Coder):
    """The first ``size`` characters of the original value: the most frequent
    prefixes of the values the Scan lists are the classes."""

    kind = "prefix"
    domain = "original"

    def __init__(self, reader: CellReader, size: int, prefixes: list[str]) -> None:
        super().__init__(
            reader, [FeatureClass(f"x{number}", text) for number, text in enumerate(prefixes, 1)]
        )
        self.size = size
        self.index = {text: number for number, text in enumerate(prefixes)}

    def code_strings(self, raws: Sequence[str]) -> list[int]:
        index, other, size = self.index, self.other, self.size
        return [
            index.get(raw[:size], other) if content else MISSING
            for raw, content in zip(raws, self.reader.content(raws), strict=True)
        ]


# Why a column cannot be a category or offer a feature.
SINGLE_VALUE = "single_value"
TOO_MANY_CATEGORIES = "too_many_categories"
NO_FREQUENCIES = "no_frequencies"
NO_PATTERN = "no_pattern"
UNREADABLE_PATTERN = "unreadable_pattern"
NO_LENGTHS = "no_lengths"
FEW_LENGTHS = "few_lengths"
NO_VALUES = "no_values_listed"
FEW_PREFIXES = "few_prefixes"
UNKNOWN_FEATURE = "unknown_feature"


def category_coder(
    reader: CellReader, field: FieldResult, max_categories: int, max_distinct: int
) -> tuple[CategoryCoder | None, str | None]:
    """The coder of a category column, or the reason it is not one: the Scan
    must hold its exact frequencies, with at least two and at most
    ``max_distinct`` distinct values, and list at least the ``max_categories``
    most frequent of them."""
    measure = field.values.frequencies
    if measure.status != "complete":
        return None, NO_FREQUENCIES
    frequencies = measure.value
    # The Scan may list only its most frequent values: the categories are the
    # first of them, so the listing must reach as far.
    if len(frequencies.listed) < min(frequencies.distinct, max_categories):
        return None, NO_FREQUENCIES
    if frequencies.distinct < 2:
        return None, SINGLE_VALUE
    if frequencies.distinct > max_distinct:
        return None, TOO_MANY_CATEGORIES
    return CategoryCoder(reader, frequencies, max_categories), None


def feature_coder(
    reader: CellReader,
    feature: str,
    field: FieldResult,
    patterns: FieldPatternsComplete | None,
    *,
    max_classes: int,
    prefix_length: int,
    inference: PatternInferenceSettings,
    max_distinct: int | None = None,
) -> tuple[Coder | None, str | None]:
    """The coder of a feature of a column, or why the column does not offer it.
    The classes come from the Scan only: the patterns of the inference, the
    lengths of the exact histogram, the prefixes and the values it lists.
    ``max_distinct`` caps the distinct values of a column that offers its
    ``value``; the second pass, which stands on a plan that already checked it,
    leaves it out."""
    if feature == "pattern":
        if patterns is None or not patterns.all_patterns():
            return None, NO_PATTERN
        from tabalyst.scanner.secondpass.accumulators import ScanMismatch

        try:
            return PatternCoder(reader, patterns, field, inference), None
        except ScanMismatch:
            return None, UNREADABLE_PATTERN
    if feature == "length":
        measure = field.string_lengths
        if measure.status != "complete":
            return None, NO_LENGTHS
        counts = {entry.length: entry.count for entry in measure.value.length_histogram}
        if len(counts) < 2:
            return None, FEW_LENGTHS
        kept = sorted(counts, key=lambda length: (-counts[length], length))[: max_classes - 1]
        return LengthCoder(reader, sorted(kept)), None
    if feature == "prefix":
        samples = field.values.samples
        tally: dict[str, int] = {}
        for entry in samples.listed:
            if entry.type == "string" and entry.value.strip():
                prefix = entry.value[:prefix_length]
                tally[prefix] = tally.get(prefix, 0) + entry.count
        if not samples.listed:
            return None, NO_VALUES
        if len(tally) < 2:
            return None, FEW_PREFIXES
        ranked = sorted(tally, key=lambda text: (-tally[text], text))[: max_classes - 1]
        return PrefixCoder(reader, prefix_length, ranked), None
    if feature == "value":
        measure = field.values.frequencies
        if measure.status != "complete":
            return None, NO_FREQUENCIES
        frequencies = measure.value
        if len(frequencies.listed) < min(frequencies.distinct, max_classes - 1):
            return None, NO_FREQUENCIES
        if frequencies.distinct < 2:
            return None, SINGLE_VALUE
        if max_distinct is not None and frequencies.distinct > max_distinct:
            return None, TOO_MANY_CATEGORIES
        return ValueCoder(reader, frequencies, max_classes - 1), None
    return None, UNKNOWN_FEATURE

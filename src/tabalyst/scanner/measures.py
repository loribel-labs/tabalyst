# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Per-value facts and the accumulators of string, length and numeric measures
(design sections 9.2 to 9.4).

Facts are a pure function of one raw value. The value tracker adds them in
batches of distinct values, each weighted by its count: once per distinct
value while the frequency table is complete, once per batch of a streamed
field after it is released. Both give the same results (design section 13).
"""

from __future__ import annotations

import math
import re
from array import array
from decimal import (
    Clamped,
    Context,
    Decimal,
    DecimalException,
    DivisionByZero,
    Inexact,
    InvalidOperation,
    Overflow,
    Subnormal,
    Underflow,
)
from fractions import Fraction
from unicodedata import is_normalized

from tabalyst.scanner.characters import CharacterProfile
from tabalyst.scanner.models import (
    Complete,
    LengthCount,
    Limited,
    NotApplicable,
    NumericCoverage,
    NumericStats,
    StringCharacteristics,
    StringLengths,
)
from tabalyst.scanner.normalization import (
    ANALYTICAL_STAGE,
    STAGES,
    Normalizer,
    collapse,
    strip_accents,
)

# Exact decimal arithmetic: any rounding or exponent outside the range makes
# the numeric envelope ``limited`` with reason ``precision``.
PRECISION = 200
EXPONENT_LIMIT = 1_000
_EXACT = Context(
    prec=PRECISION,
    Emax=EXPONENT_LIMIT,
    Emin=-EXPONENT_LIMIT,
    traps=[
        Clamped,
        DivisionByZero,
        Inexact,
        InvalidOperation,
        Overflow,
        Subnormal,
        Underflow,
    ],
)
# Integral results below this magnitude are output as JSON integers.
_MAX_INTEGRAL_OUTPUT = 10**PRECISION

# Bounds of the tables of characters (``scan.limits``, design 9.2).
DEFAULT_MAX_SPECIAL_CHARACTERS = 256
DEFAULT_MAX_DISTINCT_CHARACTERS = 1_024

CHARACTERISTICS = (
    "non_ascii",
    "with_line_breaks",
    "with_control_characters",
    "with_surrounding_whitespace",
    "with_repeated_whitespace",
    "uppercase",
    "lowercase",
    "mixed_case",
    "no_letters",
)
# Line boundaries of ``str.splitlines``.
_LINE_BREAK = re.compile("[\n\r\v\f\x1c-\x1e\x85  ]")
# Category Cc, except the tabulation and line breaks.
_CONTROL = re.compile("[\x00-\x08\x0e-\x1b\x1f\x7f-\x84\x86-\x9f]")
_REPEATED_WHITESPACE = re.compile(r"\s\s")
# Any character that the two patterns above can match: most values have none.
_RARE = re.compile("[\x00-\x1f\x7f-\x9f  ]")

def characteristic_flags(raw: str) -> int:
    """Bit ``i`` is set when the raw string has ``CHARACTERISTICS[i]``."""
    is_ascii = raw.isascii()
    flags = 0 if is_ascii else 1
    if _RARE.search(raw):
        if _LINE_BREAK.search(raw):
            flags |= 2
        if _CONTROL.search(raw):
            flags |= 4
    stripped = raw.strip()
    if stripped != raw:
        flags |= 8
    if _REPEATED_WHITESPACE.search(stripped):
        flags |= 16
    if raw.upper() != raw.lower():  # has cased characters
        if raw.isupper():
            flags |= 32
        elif raw.islower():
            flags |= 64
        else:
            flags |= 128
        # Cased ASCII characters are letters.
        if not is_ascii and not any(map(str.isalpha, raw)):
            flags |= 256
    elif is_ascii or not any(map(str.isalpha, raw)):
        flags |= 256
    return flags


class _Unconvertible:
    """A number accepted by the strict rule that ``Decimal`` cannot hold, such
    as ``1e9999999999999999999999``: it makes the statistics ``limited``."""

    __slots__ = ()


UNCONVERTIBLE = _Unconvertible()


def decimal_or_unconvertible(text: str) -> Decimal | _Unconvertible:
    try:
        return Decimal(text)
    except InvalidOperation:  # exponent beyond the range of ``decimal``
        return UNCONVERTIBLE


def canonical_text(native_type: str, value: object) -> str:
    """Canonical text of a non-string value: ``str()`` of the parsed value."""
    if native_type == "boolean":
        return "true" if value else "false"
    return str(value)


class Unrepresentable(Exception):
    """A result that cannot be output exactly or as a finite float64."""


def output_number(value: Fraction) -> int | float:
    """Integral results are JSON integers, others float64 (design 9.4)."""
    if value.denominator == 1 and abs(value.numerator) < _MAX_INTEGRAL_OUTPUT:
        return value.numerator
    try:
        result = float(value)
    except OverflowError as exc:
        raise Unrepresentable from exc
    if math.isinf(result):
        raise Unrepresentable
    return result


def weighted_median(pairs: list[tuple[object, int]], total: int) -> Fraction:
    """Median of values given with their counts; the mean of the two middle
    values for an even total."""
    pairs.sort(key=lambda pair: pair[0])
    lower_rank, upper_rank = (total - 1) // 2, total // 2
    lower = upper = None
    seen = 0
    for value, count in pairs:
        seen += count
        if lower is None and seen > lower_rank:
            lower = value
        if seen > upper_rank:
            upper = value
            break
    return (Fraction(lower) + Fraction(upper)) / 2


class ThousandsReadings:
    """Numbers whose two readings are the integer N and N / 1000 (design 20.27):
    the ambiguous ``1,234`` and the strict decimal ``1.234``. They are kept as N,
    exactly and compactly, until the finalization of the field knows which
    reading its column proves (``NumericAccumulator.absorb``).

    ``values`` and ``weights`` hold the ``(N, count)`` pairs of the median while
    the frequency table is complete, 16 bytes a pair; N has at most six digits.
    """

    __slots__ = (
        "count",
        "maximum",
        "minimum",
        "negative",
        "squares",
        "thousands",
        "total",
        "values",
        "weights",
    )

    def __init__(self, keep_pairs: bool) -> None:
        self.count = 0
        self.total = 0
        self.squares = 0
        self.minimum = 0
        self.maximum = 0
        self.negative = 0
        # Occurrences of a multiple of 1,000: integral when read as N / 1000.
        self.thousands = 0
        self.values: array[int] | None = array("q") if keep_pairs else None
        self.weights: array[int] | None = array("q") if keep_pairs else None

    def add(self, n: int, count: int) -> None:
        if not self.count:
            self.minimum = self.maximum = n
        elif n < self.minimum:
            self.minimum = n
        elif n > self.maximum:
            self.maximum = n
        self.count += count
        self.total += n * count
        self.squares += n * n * count
        if n < 0:
            self.negative += count
        if not n % 1000:
            self.thousands += count
        if self.values is not None:
            self.values.append(n)
            self.weights.append(count)  # type: ignore[union-attr]

    def release(self) -> None:
        """Forget the pairs of the median: the table of the field is released."""
        self.values = self.weights = None


class NumericAccumulator:
    """Exact numeric statistics (design section 9.4).

    Integers accumulate as Python ``int``, decimals as ``Decimal`` in an exact
    context. ``median_values`` holds ``(number, count)`` pairs while the
    frequency table is complete.
    """

    __slots__ = (
        "count",
        "dec_sum",
        "dec_sumsq",
        "imprecise",
        "int_sum",
        "int_sumsq",
        "integral_decimals",
        "maximum",
        "median_values",
        "minimum",
        "native_count",
        "negative",
        "positive",
        "zero",
    )

    def __init__(self) -> None:
        self.count = 0
        self.native_count = 0
        self.int_sum = 0
        self.int_sumsq = 0
        self.dec_sum = Decimal(0)
        self.dec_sumsq = Decimal(0)
        self.minimum: int | Decimal | None = None
        self.maximum: int | Decimal | None = None
        self.positive = 0
        self.negative = 0
        self.zero = 0
        self.integral_decimals = 0
        self.imprecise = False
        self.median_values: list[tuple[int | Decimal, int]] | None = []

    def add(
        self, number: int | Decimal, decimal_form: bool, native: bool, count: int
    ) -> None:
        self.count += count
        if native:
            self.native_count += count
        if self.imprecise:
            return
        if number is UNCONVERTIBLE:
            self.imprecise = True
            self.median_values = None
            return
        if type(number) is not int and not number:
            # An exact zero, whatever its exponent (``0e-5000``).
            number = Decimal(0)
        if type(number) is int:
            self.int_sum += number * count
            self.int_sumsq += number * number * count
        else:
            context = _EXACT
            try:
                self.dec_sum = context.add(
                    self.dec_sum, context.multiply(number, count)
                )
                square = context.multiply(number, number)
                self.dec_sumsq = context.add(
                    self.dec_sumsq, context.multiply(square, count)
                )
                integral = number == number.to_integral_value(context=context)
            except DecimalException:
                self.imprecise = True
                self.median_values = None
                return
            if decimal_form and integral:
                self.integral_decimals += count
        if self.minimum is None or number < self.minimum:
            self.minimum = number
        if self.maximum is None or number > self.maximum:
            self.maximum = number
        if number > 0:
            self.positive += count
        elif number < 0:
            self.negative += count
        else:
            self.zero += count
        if self.median_values is not None:
            self.median_values.append((number, count))

    def merge(self, other: NumericAccumulator) -> None:
        """Add what ``other`` counted, as if its values had been added here.
        The median values are not merged: the caller computes the median."""
        self.count += other.count
        self.native_count += other.native_count
        self.median_values = None
        if other.imprecise:
            self.imprecise = True
        if self.imprecise or not other.count:
            return
        self.int_sum += other.int_sum
        self.int_sumsq += other.int_sumsq
        context = _EXACT
        self.dec_sum = context.add(self.dec_sum, other.dec_sum)
        self.dec_sumsq = context.add(self.dec_sumsq, other.dec_sumsq)
        self.integral_decimals += other.integral_decimals
        self.positive += other.positive
        self.negative += other.negative
        self.zero += other.zero
        if self.minimum is None or other.minimum < self.minimum:  # type: ignore[operator]
            self.minimum = other.minimum
        if self.maximum is None or other.maximum > self.maximum:  # type: ignore[operator]
            self.maximum = other.maximum

    def absorb(self, readings: ThousandsReadings, integer: bool) -> None:
        """Add the numbers of ``readings`` as if each had been added here, read as
        N when ``integer``, else as N / 1000 written as a decimal. Text values,
        never zero (a thousands group starts with 1 to 9)."""
        if not readings.count:
            return
        self.count += readings.count
        if self.imprecise:
            return
        context = _EXACT
        low: int | Decimal
        high: int | Decimal
        if integer:
            self.int_sum += readings.total
            self.int_sumsq += readings.squares
            low, high = readings.minimum, readings.maximum
        else:
            try:
                self.dec_sum = context.add(
                    self.dec_sum, context.scaleb(Decimal(readings.total), -3)
                )
                self.dec_sumsq = context.add(
                    self.dec_sumsq, context.scaleb(Decimal(readings.squares), -6)
                )
            except DecimalException:
                self.imprecise = True
                self.median_values = None
                return
            self.integral_decimals += readings.thousands
            low = context.scaleb(Decimal(readings.minimum), -3)
            high = context.scaleb(Decimal(readings.maximum), -3)
        self.negative += readings.negative
        self.positive += readings.count - readings.negative
        if self.minimum is None or low < self.minimum:
            self.minimum = low
        if self.maximum is None or high > self.maximum:
            self.maximum = high
        medians = self.median_values
        if medians is None:
            return
        if readings.values is None:
            self.median_values = None
        elif integer:
            medians.extend(zip(readings.values, readings.weights))  # type: ignore[arg-type]
        else:
            medians.extend(
                (context.scaleb(Decimal(n), -3), count)
                for n, count in zip(readings.values, readings.weights)  # type: ignore[arg-type]
            )

    def finalize(self, table_limit: Limited | None, values: int | None = None):
        """``values`` is the analyzable values of the field, for ``coverage``."""
        if not self.count:
            return NotApplicable(reason="no_values")
        imprecise = Limited(reason="precision", limit=PRECISION)
        if self.imprecise:
            return imprecise
        n = self.count
        of = max(values or n, n)
        total = self.int_sum + Fraction(self.dec_sum)
        squares = self.int_sumsq + Fraction(self.dec_sumsq)
        variance = (n * squares - total * total) / (n * n)
        try:
            if table_limit is not None:
                median = Limited(reason=table_limit.reason, limit=table_limit.limit)
            else:
                median = Complete[int | float](
                    value=output_number(weighted_median(self.median_values, n))
                )
            return Complete[NumericStats](
                value=NumericStats(
                    count=n,
                    native_count=self.native_count,
                    text_count=n - self.native_count,
                    min=output_number(Fraction(self.minimum)),
                    max=output_number(Fraction(self.maximum)),
                    sum=output_number(total),
                    mean=output_number(total / n),
                    population_variance=output_number(variance),
                    population_std=_square_root(variance),
                    positive=self.positive,
                    negative=self.negative,
                    zero=self.zero,
                    integral_decimals=self.integral_decimals,
                    median=median,
                    coverage=NumericCoverage(
                        of=of, share=n / of
                    ),
                )
            )
        except Unrepresentable:
            return imprecise


def _square_root(value: Fraction) -> int | float:
    if value.denominator == 1:
        root = math.isqrt(value.numerator)
        if root * root == value.numerator:
            return output_number(Fraction(root))
    try:
        return math.sqrt(value)
    except OverflowError as exc:
        raise Unrepresentable from exc


def _add_bits(counters: list[int], flags: int, count: int) -> None:
    """Add ``count`` to ``counters[i]`` for each bit ``i`` set in ``flags``."""
    while flags:
        bit = flags & -flags
        counters[bit.bit_length() - 1] += count
        flags ^= bit


def _expand(counts: dict[int, int], size: int) -> list[int]:
    """Counters per bit from occurrences per combination of bits."""
    counters = [0] * size
    for flags, count in counts.items():
        _add_bits(counters, flags, count)
    return counters


class ValueMeasures:
    """String characteristics, lengths, normalization changes, numeric
    statistics, technical type families and detector tallies of one field.

    Characteristics and normalization changes are counted per combination of
    flags, which few values share, and expanded per flag at the end.
    """

    __slots__ = (
        "ambiguous_numbers",
        "changes",
        "characters",
        "dotted_numbers",
        "families",
        "flags",
        "lengths",
        "numeric",
        "tallies",
    )

    def __init__(
        self,
        tallies: list | tuple = (),
        max_special_characters: int = DEFAULT_MAX_SPECIAL_CHARACTERS,
        max_distinct_characters: int = DEFAULT_MAX_DISTINCT_CHARACTERS,
    ) -> None:
        # Occurrences per combination of characteristic flags (design 9.2).
        self.flags: dict[int, int] = {}
        self.lengths: dict[int, int] = {}
        self.characters = CharacterProfile(
            max_special_characters, max_distinct_characters
        )
        # Occurrences per combination of normalization stages that changed
        # them (design section 10).
        self.changes: dict[int, int] = {}
        self.numeric = NumericAccumulator()
        # Ambiguous numbers (``1,234``) and strict decimals ``d.ddd``, kept as
        # integers until the field knows the convention its values prove
        # (design 20.27); ``None`` until one is met.
        self.ambiguous_numbers: ThousandsReadings | None = None
        self.dotted_numbers: ThousandsReadings | None = None
        # Values per technical type family (design 9.7).
        self.families: dict[str, int] = {}
        # One tally per active detector, aligned with the active detectors.
        self.tallies = tallies

    def read_thousands(self, convention: str | None) -> None:
        """Add the kept numbers to ``numeric`` in the convention the column
        proves (design 20.27): the ambiguous ones are read in it, and the strict
        decimals ``d.ddd`` are thousands under ``comma``; without a convention
        the ambiguous ones stay out and ``d.ddd`` is the decimal of the strict
        rule. The kept numbers are then forgotten, so a second call adds
        nothing."""
        ambiguous, dotted = self.ambiguous_numbers, self.dotted_numbers
        self.ambiguous_numbers = self.dotted_numbers = None
        if ambiguous is not None and convention is not None:
            self.numeric.absorb(ambiguous, integer=convention == "dot")
        if dotted is not None:
            self.numeric.absorb(dotted, integer=convention == "comma")

    @property
    def changed(self) -> list[int]:
        """Occurrences modified by each normalization stage."""
        return _expand(self.changes, len(STAGES))

    def add_strings(
        self,
        raws: list[str],
        counts: list[int],
        normalizer: Normalizer,
        forms: dict[str, tuple[str, ...]] | None = None,
        flagged: list[tuple[int, int]] | None = None,
    ) -> tuple[list[str], list[int]]:
        """Normalize distinct content strings (design 10) and count their
        characteristics, analytical lengths and normalization changes, each
        weighted by its count. Returns the analytical texts and their lengths.
        ``forms`` receives the output of every stage for the strings that a
        stage changed; ``flagged`` receives the position and the changes of
        those that a whitespace stage changed (the cases of design 18.15).

        Printable strings in NFC take a fast path with the same results as
        ``Normalizer.run`` and ``characteristic_flags``: their only whitespace
        is the space, and they have no line break or control character.
        """
        texts: list[str] = []
        lengths: list[int] = []
        histogram = self.lengths
        flag_counts = self.flags
        change_counts = self.changes
        self.characters.add(raws, counts)
        run = normalizer.run
        fast = normalizer.fast
        nfc = normalizer.nfc
        casefold = normalizer.casefold
        accents = normalizer.accents
        for raw, count in zip(raws, counts, strict=True):
            ascii_ = raw.isascii()
            if (
                fast
                and raw.isprintable()
                and (ascii_ or not nfc or is_normalized("NFC", raw))
            ):
                stripped = raw.strip()
                if len(stripped) != len(raw):
                    flags, changes = 8, 2
                else:
                    flags = changes = 0
                if "  " in stripped:
                    flags |= 16
                    changes |= 4
                    text = collapse(stripped)
                else:
                    text = stripped
                if ascii_:
                    # ASCII letters are cased, and case folding is lowering.
                    folded = text.lower()
                    if text.isupper():
                        flags |= 32
                    elif text.islower():
                        flags |= 64
                    elif folded != text:
                        flags |= 128
                    else:
                        flags |= 256
                    if not casefold:
                        folded = text
                    elif folded != text:
                        changes |= 8
                    final = folded
                else:
                    flags |= 1
                    if raw.upper() != raw.lower():  # has cased characters
                        if raw.isupper():
                            flags |= 32
                        elif raw.islower():
                            flags |= 64
                        else:
                            flags |= 128
                        if not any(map(str.isalpha, raw)):
                            flags |= 256
                    elif not any(map(str.isalpha, raw)):
                        flags |= 256
                    folded = text.casefold() if casefold else text
                    if folded != text:
                        changes |= 8
                    final = folded
                    if accents and not folded.isascii():
                        final = strip_accents(folded)
                        if final != folded:
                            changes |= 16
                if changes and forms is not None:
                    forms[raw] = (raw, stripped, text, folded, final)
            else:
                stages, changes = run(raw)
                text = stages[ANALYTICAL_STAGE]
                flags = characteristic_flags(raw)
                if changes and forms is not None:
                    forms[raw] = stages
            length = len(text)
            if flagged is not None and changes & 6:
                flagged.append((len(texts), changes))
            texts.append(text)
            lengths.append(length)
            histogram[length] = histogram.get(length, 0) + count
            flag_counts[flags] = flag_counts.get(flags, 0) + count
            if changes:
                change_counts[changes] = change_counts.get(changes, 0) + count
        return texts, lengths

    def string_characteristics(self, withheld: bool = False) -> StringCharacteristics:
        """``withheld`` (a masked or hidden field) keeps the counters and drops
        the distributions of characters (design 12.8)."""
        profile = self.characters
        return StringCharacteristics(
            **dict(zip(CHARACTERISTICS, _expand(self.flags, len(CHARACTERISTICS)))),
            **profile.counters(),
            characters=profile.characters,
            distinct_characters=profile.distinct_characters(withheld),
            special_characters=profile.special_characters(withheld),
        )

    def string_lengths(self):
        lengths = self.lengths
        count = sum(lengths.values())
        if not count:
            return NotApplicable(reason="no_values")
        total = sum(length * n for length, n in lengths.items())
        return Complete[StringLengths](
            value=StringLengths(
                count=count,
                min_length=min(lengths),
                max_length=max(lengths),
                mean_length=output_number(Fraction(total, count)),
                median_length=output_number(
                    weighted_median(list(lengths.items()), count)
                ),
                length_histogram=[
                    LengthCount(length=length, count=lengths[length])
                    for length in sorted(lengths)
                ],
            )
        )

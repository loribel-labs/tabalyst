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

from tabalyst.scanner.models import (
    Complete,
    LengthCount,
    Limited,
    NotApplicable,
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

    def finalize(self, table_limit: Limited | None):
        if not self.count:
            return NotApplicable(reason="no_values")
        imprecise = Limited(reason="precision", limit=PRECISION)
        if self.imprecise:
            return imprecise
        n = self.count
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
        "changes",
        "families",
        "flags",
        "lengths",
        "numeric",
        "tallies",
    )

    def __init__(self, tallies: list | tuple = ()) -> None:
        # Occurrences per combination of characteristic flags (design 9.2).
        self.flags: dict[int, int] = {}
        self.lengths: dict[int, int] = {}
        # Occurrences per combination of normalization stages that changed
        # them (design section 10).
        self.changes: dict[int, int] = {}
        self.numeric = NumericAccumulator()
        # Values per technical type family (design 9.7).
        self.families: dict[str, int] = {}
        # One tally per active detector, aligned with the active detectors.
        self.tallies = tallies

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
    ) -> tuple[list[str], list[int]]:
        """Normalize distinct content strings (design 10) and count their
        characteristics, analytical lengths and normalization changes, each
        weighted by its count. Returns the analytical texts and their lengths.
        ``forms`` receives the output of every stage for the strings that a
        stage changed.

        Printable strings in NFC take a fast path with the same results as
        ``Normalizer.run`` and ``characteristic_flags``: their only whitespace
        is the space, and they have no line break or control character.
        """
        texts: list[str] = []
        lengths: list[int] = []
        histogram = self.lengths
        flag_counts = self.flags
        change_counts = self.changes
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
            texts.append(text)
            lengths.append(length)
            histogram[length] = histogram.get(length, 0) + count
            flag_counts[flags] = flag_counts.get(flags, 0) + count
            if changes:
                change_counts[changes] = change_counts.get(changes, 0) + count
        return texts, lengths

    def string_characteristics(self) -> StringCharacteristics:
        return StringCharacteristics(
            **dict(zip(CHARACTERISTICS, _expand(self.flags, len(CHARACTERISTICS))))
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

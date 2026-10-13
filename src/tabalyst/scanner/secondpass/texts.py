# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The long texts of a field: their words, lines and digits, and the texts told
apart by a fingerprint (design 20.34, lot 18).

A text is never kept. The profile adds a few counters to each text it reads, and
the fingerprint holds 16 bytes and a count for each distinct text, within the
memory pool of the run like the exact sets.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from fractions import Fraction
from sys import getsizeof

from tabalyst.scanner.longtext import DIGEST_ALGORITHM, DIGEST_BITS
from tabalyst.scanner.measures import output_number
from tabalyst.scanner.secondpass.accumulators import ScanMismatch
from tabalyst.scanner.secondpass.exactset import MEASURE_STEP, ExactPool
from tabalyst.scanner.secondpass.frequencies import native_key
from tabalyst.scanner.secondpass.models import (
    DistinctLimited,
    FingerprintResult,
    RepeatedText,
    TextBucket,
    TextProfileResult,
)

# Decimal digits of Unicode (category ``Nd``), which ``str.isdecimal`` tests.
_DIGITS = re.compile(r"\d+")
_ASCII_WITHOUT_DIGITS = str.maketrans("", "", "0123456789")
# The digest of the Scan's long texts starts with the native type and a NUL.
_PREFIX = b"string\0"
# The bytes of an entry of the fingerprints: a 16-byte key, its count and the
# slot of the dictionary beside it.
KEY_BYTES = 49
COUNT_BYTES = 28


def digits_in(text: str) -> int:
    """The decimal digits of ``text``."""
    if text.isascii():
        return len(text) - len(text.translate(_ASCII_WITHOUT_DIGITS))
    return len(text) - len(_DIGITS.sub("", text))


def bucket(count: int) -> int:
    """The power-of-two bucket of a count: 0, 1, 2 to 3, 4 to 7, and so on."""
    return count.bit_length()


def buckets(counts: list[int]) -> list[TextBucket]:
    """The buckets from the first that holds a text to the last, bounds included."""
    filled = [index for index, count in enumerate(counts) if count]
    if not filled:
        return []
    return [
        TextBucket(
            low=0 if index == 0 else 1 << (index - 1),
            high=0 if index == 0 else (1 << index) - 1,
            count=counts[index],
        )
        for index in range(filled[0], filled[-1] + 1)
    ]


class TextAccumulator:
    """Counters of the words, the lines and the digits of the original texts of one
    field, constant in size whatever the texts."""

    __slots__ = (
        "cell_ns",
        "characters",
        "digit_buckets",
        "digits",
        "line_buckets",
        "lines",
        "max_lines",
        "max_words",
        "min_words",
        "multi_line",
        "texts",
        "word_buckets",
        "words",
    )

    def __init__(self, cell_ns: int = 0) -> None:
        # What the plan expects a text to cost: it weighs the route among the
        # workers and is no input of the result.
        self.cell_ns = cell_ns
        self.texts = 0
        self.characters = 0
        self.words = 0
        self.min_words = -1
        self.max_words = 0
        self.lines = 0
        self.max_lines = 0
        self.multi_line = 0
        self.digits = 0
        self.word_buckets: list[int] = [0] * 8
        self.line_buckets: list[int] = [0] * 8
        self.digit_buckets: list[int] = [0] * 11

    def add_strings(self, raws: Sequence[str], counts: Sequence[int]) -> None:
        """Account for the distinct content strings of a batch with their counts."""
        for raw, count in zip(raws, counts, strict=True):
            length = len(raw)
            words = len(raw.split())
            lines = len(raw.splitlines()) or 1
            digits = digits_in(raw)
            self.texts += count
            self.characters += length * count
            self.words += words * count
            if self.min_words < 0 or words < self.min_words:
                self.min_words = words
            self.max_words = max(self.max_words, words)
            self.lines += lines * count
            self.max_lines = max(self.max_lines, lines)
            if lines > 1:
                self.multi_line += count
            self.digits += digits * count
            self._bucket(self.word_buckets, bucket(words), count)
            self._bucket(self.line_buckets, bucket(lines), count)
            self.digit_buckets[-(-digits * 10 // length) if digits else 0] += count

    @staticmethod
    def _bucket(counts: list[int], index: int, count: int) -> None:
        while index >= len(counts):
            counts.append(0)
        counts[index] += count

    def result(self, content: int) -> TextProfileResult:
        """The profile, checked against the Scan: the texts are its content strings."""
        if self.texts != content:
            raise ScanMismatch(
                f"content strings: the second pass found {self.texts}, the scan {content}"
            )
        if not self.texts:
            raise ScanMismatch("content strings: the scan counted none for the field")
        return TextProfileResult(
            texts=self.texts,
            characters=self.characters,
            words=self.words,
            min_words=self.min_words,
            max_words=self.max_words,
            mean_words=output_number(Fraction(self.words, self.texts)),
            lines=self.lines,
            max_lines=self.max_lines,
            multi_line=self.multi_line,
            digits=self.digits,
            digit_share=output_number(Fraction(self.digits, self.characters)),
            word_buckets=buckets(self.word_buckets),
            line_buckets=buckets(self.line_buckets),
            digit_buckets=list(self.digit_buckets),
        )


def fingerprint(native_type: str, text: str) -> bytes:
    """The 128-bit digest the Scan gives a value: the native type, a NUL and the text
    in UTF-8, lone surrogates kept."""
    state = hashlib.blake2b(digest_size=DIGEST_BITS // 8)
    state.update(native_type.encode("ascii") + b"\0")
    state.update(text.encode("utf-8", "surrogatepass"))
    return state.digest()


class FingerprintAccumulator:
    """The distinct values of a field by fingerprint, each with its count, within a
    pool. When the pool cannot hold what the table weighs the field stops being
    tracked and the distinct values met at that moment are a lower bound."""

    __slots__ = (
        "_base",
        "counts",
        "limited",
        "lower_bound",
        "max_listed",
        "pending",
        "pool",
        "used",
        "values",
    )

    def __init__(self, pool: ExactPool, max_listed: int) -> None:
        self.pool = pool
        self.max_listed = max_listed
        self.counts: dict[bytes, int] = {}
        self.values = 0
        self.used = 0
        self.pending = 0
        self.limited = False
        self.lower_bound = 0
        base = hashlib.blake2b(digest_size=DIGEST_BITS // 8)
        base.update(_PREFIX)
        self._base = base

    def add_strings(self, raws: Sequence[str], counts: Sequence[int]) -> None:
        """Account for the distinct content strings of a batch with their counts."""
        if self.limited:
            return
        table = self.counts
        base = self._base
        for raw, count in zip(raws, counts, strict=True):
            state = base.copy()
            state.update(raw.encode("utf-8", "surrogatepass"))
            key = state.digest()
            table[key] = table.get(key, 0) + count
        self.values += sum(counts)
        self.pending += len(raws)
        if self.pending >= MEASURE_STEP:
            self.measure()

    def add_native(self, native_type: str, value: object) -> None:
        """Account for one JSON integer, number or boolean."""
        if self.limited:
            return
        kind, text = native_key(native_type, value)
        key = fingerprint(kind, text)
        self.counts[key] = self.counts.get(key, 0) + 1
        self.values += 1
        self.pending += 1
        if self.pending >= MEASURE_STEP:
            self.measure()

    def measure(self) -> None:
        """Charge the pool with what the table holds now, and stop the field if
        the pool cannot hold it."""
        self.pending = 0
        used = getsizeof(self.counts) + len(self.counts) * (KEY_BYTES + COUNT_BYTES)
        pool = self.pool
        pool.used += used - self.used
        self.used = used
        if pool.used > pool.total:
            self.stop()

    def stop(self) -> None:
        """Release the table: the count of a prefix is not the number of distinct
        values."""
        self.lower_bound = len(self.counts)
        self.limited = True
        self.pool.used -= self.used
        self.used = 0
        self.counts = {}

    def result(
        self, expected_values: int, exact: int | None, lower_bound: int | None
    ) -> FingerprintResult | DistinctLimited:
        """The count, checked against the Scan, or what is proven when the pool
        stopped the field. ``exact`` is the Scan's cardinality when it counted
        it, ``lower_bound`` the distinct values it proved otherwise."""
        if self.pending and not self.limited:
            self.measure()
        if self.limited:
            return DistinctLimited(values_read=self.values, lower_bound=self.lower_bound)
        if self.values != expected_values:
            raise ScanMismatch(
                f"values: the second pass found {self.values}, the scan {expected_values}"
            )
        counts = self.counts
        distinct = len(counts)
        if exact is not None and distinct != exact:
            raise ScanMismatch(
                f"distinct values: the second pass found {distinct}, the scan {exact}"
            )
        if lower_bound is not None and distinct < lower_bound:
            raise ScanMismatch(
                f"distinct values: the second pass found {distinct}, "
                f"the scan proved at least {lower_bound}"
            )
        repeated = [(key, count) for key, count in counts.items() if count > 1]
        repeated.sort(key=lambda item: (-item[1], item[0]))
        return FingerprintResult(
            algorithm=DIGEST_ALGORITHM,
            bits=DIGEST_BITS,
            values=self.values,
            distinct=distinct,
            redundant=self.values - distinct,
            unique=distinct == self.values,
            repeated=len(repeated),
            repeated_occurrences=sum(count for _, count in repeated),
            listed=[
                RepeatedText(digest=key.hex(), count=count)
                for key, count in repeated[: self.max_listed]
            ],
            truncated=len(repeated) > self.max_listed,
        )

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Character profile of the strings of a field: classes, composition, invisible
characters, the inventory of special characters and the count of distinct
characters (design 9.2).

Everything is a pure function of one raw value, counted once per distinct value
and weighted by its occurrences, so a complete table and a streamed field give
the same results (design 13).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from itertools import compress, repeat
from operator import mul
from unicodedata import category, name

from tabalyst.scanner.models import (
    Complete,
    Disabled,
    Limited,
    NotApplicable,
    SpecialCharacter,
    SpecialCharacters,
)

# Counters by combination of bits, in the order of the model's members. The nine
# counters of lot 2a keep their own flags (``measures.CHARACTERISTICS``).
PRESENCE = (
    "with_ascii_lowercase",
    "with_ascii_uppercase",
    "with_other_latin_letters",
    "with_non_latin_letters",
    "with_ascii_digits",
    "with_other_digits",
    "starts_uppercase",
    "starts_lowercase",
    "with_tabs",
    "with_non_breaking_spaces",
    "ascii_only",
    "letters_only",
    "digits_only",
    "alphanumeric_only",
    "letters_and_digits",
    "with_invisible_characters",
    "with_replacement_character",
)
_BIT = {name_: 1 << index for index, name_ in enumerate(PRESENCE)}
PRESENCE_BIT = _BIT

REASON = "character_limit"

# Class symbols of a character: l, u ASCII lower and upper case letters; L letters
# of the Latin script outside ASCII; N other letters; d ASCII digits; D other
# digits; o other alphanumeric characters (such as a vulgar fraction); t
# tabulation; b non-breaking space; w other whitespace; c control and format
# characters; i invisible characters; r replacement character; s special
# characters. The mask of a value has the bit of each symbol it contains; the
# ASCII symbols fit in a byte, which ``bytes.translate`` produces.
SYMBOL_BITS = {
    "l": 1,
    "u": 2,
    "d": 4,
    "s": 8,
    "w": 16,
    "t": 32,
    "c": 64,
    "L": 128,
    "N": 256,
    "D": 512,
    "o": 1024,
    "b": 2048,
    "i": 4096,
    "r": 8192,
}
_LETTERS = SYMBOL_BITS["l"] | SYMBOL_BITS["u"] | SYMBOL_BITS["L"] | SYMBOL_BITS["N"]
_DIGITS = SYMBOL_BITS["d"] | SYMBOL_BITS["D"]
_ALPHANUMERIC = _LETTERS | _DIGITS | SYMBOL_BITS["o"]
_SPECIAL = SYMBOL_BITS["s"] | SYMBOL_BITS["r"]
# U+200B to U+200D, U+FEFF, U+2060.
_INVISIBLE = frozenset(map(chr, (0x200B, 0x200C, 0x200D, 0xFEFF, 0x2060)))
_NON_BREAKING = frozenset(map(chr, (0xA0, 0x2007, 0x202F)))
_REPLACEMENT = chr(0xFFFD)
# First character of an ASCII value, as the bit of its symbol: the start counters.
_START = {
    SYMBOL_BITS["u"]: _BIT["starts_uppercase"],
    SYMBOL_BITS["l"]: _BIT["starts_lowercase"],
}


def _symbol(char: str) -> str:
    """The class symbol of one character."""
    if char in _INVISIBLE:
        return "i"
    if char == _REPLACEMENT:
        return "r"
    if char in _NON_BREAKING:
        return "b"
    if char == chr(9):
        return "t"
    if char.isalpha():
        if char.isascii():
            return "u" if char.isupper() else "l"
        # The Unicode name of a letter starts with its script.
        script = name(char, "")
        return "L" if script.startswith(("LATIN", "FULLWIDTH LATIN")) else "N"
    if char.isdigit():
        return "d" if char.isascii() else "D"
    if char.isalnum():
        return "o"
    if char.isspace():
        return "w"
    # A lone surrogate (valid in JSON text) cannot be written as UTF-8.
    if category(char) in ("Cc", "Cf", "Cs"):
        return "c"
    return "s"


# ``bytes.translate`` tables of the ASCII values, the common case: each byte
# becomes the bit of its symbol, or is deleted unless it is a special character.
_BIT_TABLE = bytes(SYMBOL_BITS[_symbol(chr(code))] for code in range(128)) + bytes(128)
_NOT_SPECIAL = bytes(
    code
    for code in range(256)
    if code >= 128 or SYMBOL_BITS[_symbol(chr(code))] != SYMBOL_BITS["s"]
)

# Characters of the tables below; a larger table is cleared, so it stays small.
_MAX_TABLE = 65_536


class _Symbols(dict[int, str]):
    """``str.translate`` table of ``_symbol``, filled as characters are met."""

    def __missing__(self, ordinal: int) -> str:
        if len(self) >= _MAX_TABLE:
            self.clear()
        symbol = self[ordinal] = _symbol(chr(ordinal))
        return symbol


class _Specials(dict[int, str | None]):
    """``str.translate`` table that keeps the special characters only."""

    def __missing__(self, ordinal: int) -> str | None:
        if len(self) >= _MAX_TABLE:
            self.clear()
        char = chr(ordinal)
        kept = self[ordinal] = char if SYMBOL_BITS[_symbol(char)] & _SPECIAL else None
        return kept


_SPECIAL_BYTE = bytes([SYMBOL_BITS["s"]])
_UNICODE_SYMBOLS = _Symbols()
_UNICODE_SPECIALS = _Specials()


class _Presence(dict[int, int]):
    """Presence and composition bits that the mask of a value decides."""

    def __missing__(self, mask: int) -> int:
        bits = 0
        for symbol, flag in (
            ("l", "with_ascii_lowercase"),
            ("u", "with_ascii_uppercase"),
            ("L", "with_other_latin_letters"),
            ("N", "with_non_latin_letters"),
            ("d", "with_ascii_digits"),
            ("D", "with_other_digits"),
            ("t", "with_tabs"),
            ("b", "with_non_breaking_spaces"),
            ("i", "with_invisible_characters"),
            ("r", "with_replacement_character"),
        ):
            if mask & SYMBOL_BITS[symbol]:
                bits |= _BIT[flag]
        if mask and not mask & ~_LETTERS:
            bits |= _BIT["letters_only"]
        if mask and not mask & ~_DIGITS:
            bits |= _BIT["digits_only"]
        if mask and not mask & ~_ALPHANUMERIC:
            bits |= _BIT["alphanumeric_only"]
            if mask & _LETTERS and mask & _DIGITS:
                bits |= _BIT["letters_and_digits"]
        self[mask] = bits
        return bits


_PRESENCE = _Presence()


def presence_flags(raw: str) -> int:
    """The presence bits (``PRESENCE`` names, bit ``i`` for ``PRESENCE[i]``) of
    one raw string, as the profile counts them."""
    mask = 0
    for char in set(raw):
        mask |= SYMBOL_BITS[_symbol(char)]
    return _PRESENCE[mask]


class CharacterProfile:
    """Counters of the character classes of one field and the two bounded
    tables of its characters.

    ``max_special`` bounds the inventory of special characters (0 turns it off)
    and ``max_distinct`` the set of distinct characters. A table that would pass
    its bound is dropped and the measure is ``limited``: the rule depends on the
    set of characters of the field, never on the order of the values.

    The ASCII values of a batch, nearly all of them, go through C-level
    iterators (``map``) rather than a Python loop: the profile runs once per
    distinct value of every text field, in the first pass.
    """

    __slots__ = (
        "_distinct",
        "_distinct_over",
        "_seen_ascii",
        "_shapes",
        "_special",
        "_special_over",
        "characters",
        "counts",
        "max_distinct",
        "max_special",
        "streamed",
        "strings",
    )

    def __init__(self, max_special: int, max_distinct: int) -> None:
        self.max_special = max_special
        self.max_distinct = max_distinct
        # Occurrences per combination of presence bits.
        self.counts: dict[int, int] = {}
        # Characters of the raw values, with their occurrences.
        self.characters = 0
        self.strings = 0
        # Per special character: [distinct values, occurrences] containing it.
        self._special: dict[str, list[int]] = {}
        self._special_over = max_special == 0
        self._distinct: set[str] = set()
        # The ASCII characters of ``_distinct`` as bytes, to delete from a batch.
        self._seen_ascii = b""
        self._distinct_over = False
        # Presence bits of the shapes met (bounded).
        self._shapes: dict[bytes, int] = {}
        # Set once the field is streamed: a value that returns in a later batch
        # is then counted again, so ``value_count`` is an upper bound.
        self.streamed = False

    def add(self, raws: Sequence[str], counts: Sequence[int]) -> None:
        """Count distinct raw strings, each weighted by its occurrences."""
        total = sum(counts)
        self.strings += total
        if not all(raws):
            kept = [(raw, count) for raw, count in zip(raws, counts, strict=True) if raw]
            raws = [raw for raw, _ in kept]
            counts = [count for _, count in kept]
        if not raws:
            return
        joined = "".join(raws)
        if total == len(counts):
            self.characters += len(joined)
        else:
            self.characters += sum(map(mul, map(len, raws), counts))
        if joined.isascii():
            self._add_ascii(raws, counts, joined)
        else:
            ascii_flags = list(map(str.isascii, raws))
            other_flags = [not flag for flag in ascii_flags]
            if any(ascii_flags):
                ascii_raws = list(compress(raws, ascii_flags))
                self._add_ascii(
                    ascii_raws, list(compress(counts, ascii_flags)), "".join(ascii_raws)
                )
            self._add_unicode(
                list(compress(raws, other_flags)), list(compress(counts, other_flags))
            )
        if not self._distinct_over and len(self._distinct) > self.max_distinct:
            self._distinct_over = True
            self._distinct.clear()

    def _add_ascii(
        self, raws: Sequence[str], counts: Sequence[int], joined: str
    ) -> None:
        encoded = list(map(str.encode, raws))
        # A shape is the string of the symbol bits of a value: values of one
        # shape have the same classes, so a batch pays for its distinct shapes.
        shapes = map(bytes.translate, encoded, repeat(_BIT_TABLE))
        if sum(counts) == len(counts):
            tally: dict[bytes, int] = Counter(shapes)
        else:
            tally = {}
            for shape, count in zip(shapes, counts, strict=True):
                tally[shape] = tally.get(shape, 0) + count
        presence = self.counts
        known = self._shapes
        if len(known) > _MAX_TABLE:
            known.clear()
        for shape, count in tally.items():
            flags = known.get(shape)
            if flags is None:
                flags = known[shape] = (
                    _PRESENCE[sum(set(shape))]
                    | _START.get(shape[0], 0)
                    | _BIT["ascii_only"]
                )
            presence[flags] = presence.get(flags, 0) + count
        if not self._distinct_over:
            # Only the characters not yet seen survive the deletion.
            fresh = joined.encode().translate(None, self._seen_ascii)
            if fresh:
                self._distinct.update(fresh.decode())
                self._seen_ascii += bytes(set(fresh))
        if not self._special_over and _SPECIAL_BYTE in b"".join(tally):
            found = map(
                bytes.translate, encoded, repeat(None), repeat(_NOT_SPECIAL)
            )
            self._tally_specials(found, counts)

    def _add_unicode(self, raws: Sequence[str], counts: Sequence[int]) -> None:
        if not raws:
            return
        presence = self.counts
        specials: list[str] = []
        special_counts: list[int] = []
        for raw, count in zip(raws, counts, strict=True):
            symbols = raw.translate(_UNICODE_SYMBOLS)
            mask = sum(map(SYMBOL_BITS.__getitem__, set(symbols)))
            flags = _PRESENCE[mask]
            if raw[0].isupper():
                flags |= _BIT["starts_uppercase"]
            elif raw[0].islower():
                flags |= _BIT["starts_lowercase"]
            presence[flags] = presence.get(flags, 0) + count
            if mask & _SPECIAL and not self._special_over:
                specials.append(raw.translate(_UNICODE_SPECIALS))
                special_counts.append(count)
        if specials:
            self._tally_specials(specials, special_counts)
        if not self._distinct_over:
            self._distinct.update("".join(raws))

    def _tally_specials(
        self, found: Iterable[str | bytes], counts: Sequence[int]
    ) -> None:
        """Count the special characters of the values: ``found`` holds, for each
        value, its special characters (as text or bytes), empty for most."""
        grouped: dict[str | bytes, list[int]] = {}
        for chars, count in zip(found, counts, strict=True):
            if not chars:
                continue
            entry = grouped.get(chars)
            if entry is None:
                grouped[chars] = [1, count]
            else:
                entry[0] += 1
                entry[1] += count
        table = self._special
        for chars, (values, occurrences) in grouped.items():
            text = chars.decode() if isinstance(chars, bytes) else chars
            for char in set(text):
                entry = table.get(char)
                if entry is None:
                    if len(table) >= self.max_special:
                        self._special_over = True
                        table.clear()
                        return
                    table[char] = [values, occurrences]
                else:
                    entry[0] += values
                    entry[1] += occurrences

    def counters(self) -> dict[str, int]:
        """Occurrences with each presence or composition counter."""
        totals = dict.fromkeys(PRESENCE, 0)
        for bits, count in self.counts.items():
            for flag in PRESENCE:
                if bits & _BIT[flag]:
                    totals[flag] += count
        return totals

    def special_characters(
        self, withheld: bool
    ) -> Disabled | NotApplicable | Limited | Complete[SpecialCharacters]:
        """The inventory of special characters, as a measure envelope."""
        if withheld or not self.max_special:
            return Disabled()
        if not self.strings:
            return NotApplicable(reason="no_values")
        if self._special_over:
            return Limited(
                reason=REASON, limit=self.max_special, lower_bound=self.max_special + 1
            )
        listed = [
            SpecialCharacter(
                char=char,
                codepoint=ord(char),
                value_count=entry[0],
                occurrence_count=entry[1],
            )
            for char, entry in sorted(
                self._special.items(), key=lambda item: (-item[1][1], item[0])
            )
        ]
        return Complete[SpecialCharacters](
            value=SpecialCharacters(
                distinct=len(listed),
                value_count_accuracy="upper_bound" if self.streamed else "exact",
                listed=listed,
            )
        )

    def distinct_characters(
        self, withheld: bool
    ) -> Disabled | NotApplicable | Limited | Complete[int]:
        """The number of distinct characters, as a measure envelope."""
        if withheld:
            return Disabled()
        if not self.strings:
            return NotApplicable(reason="no_values")
        if self._distinct_over:
            return Limited(
                reason=REASON,
                limit=self.max_distinct,
                lower_bound=self.max_distinct + 1,
            )
        return Complete[int](value=len(self._distinct))

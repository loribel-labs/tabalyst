# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Character map of the strings of a field: the most frequent characters, their
Unicode families, the case of the ends of the values and the emoji (design 9.2b).

The census is a pure function of the distinct strings it is given and their
counts, so the Scan (on its samples) and the second pass (on every string) share
it and a streamed field gives the same result as a complete table.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from functools import lru_cache
from itertools import compress
from typing import Literal
from unicodedata import category, name

from tabalyst.scanner.diagnostics import DiagnosticCollector
from tabalyst.scanner.models import (
    CharacterCount,
    CharacterFamily,
    CharacterMap,
    Complete,
    DatasetResult,
    DerivedCharacters,
    Disabled,
    EmojiCount,
    Failed,
    FieldCharacterMap,
    FieldCharacters,
    FieldResult,
    Limited,
    NotApplicable,
)

REASON = "character_limit"
# Distinct characters and emoji sequences a census keeps. A larger table gives up
# the field (``limited``) rather than a list that depends on the order of the values.
MAX_CHARACTERS = 65_536
MAX_EMOJI = 10_000

# Emoji, without a table of the standard: a character that is an emoji by default
# (the pictographs from U+1F300 and a few symbols below), or a symbol that needs the
# variation selector U+FE0F to be one. A sequence is a flag (two regional
# indicators), a keycap, a tag sequence (the flags of England...) or an emoji with
# its modifier and joiner chain. The symbols below U+1F300 that are text by
# default (arrows, card suits...) count only with U+FE0F.
_DEFAULT = (
    r"[\u231a\u231b\u23e9-\u23f3\u25fd\u25fe\u2614\u2615\u2648-\u2653\u267f\u2693"
    r"\u26a1\u26aa\u26ab\u26bd\u26be\u26c4\u26c5\u26ce\u26d4\u26ea\u26f2\u26f3\u26f5"
    r"\u26fa\u26fd\u2705\u270a\u270b\u2728\u274c\u274e\u2753-\u2755\u2757\u2795-\u2797"
    r"\u27b0\u27bf\u2b1b\u2b1c\u2b50\u2b55\U0001f004\U0001f0cf\U0001f18e"
    r"\U0001f191-\U0001f19a\U0001f201\U0001f21a\U0001f22f\U0001f232-\U0001f23a"
    r"\U0001f250\U0001f251\U0001f300-\U0001faff]"
)
_NEEDS_SELECTOR = (
    r"[\u00a9\u00ae\u203c\u2049\u2122\u2139\u2194-\u21aa\u2328\u23cf\u23ed-\u23fa"
    r"\u24c2\u25aa-\u25fe\u2600-\u27bf\u2934\u2935\u2b05-\u2b07\u3030\u303d\u3297\u3299]"
)
_UNIT = rf"(?:{_DEFAULT}|{_NEEDS_SELECTOR}\ufe0f)\ufe0f?[\U0001f3fb-\U0001f3ff]?"
_EMOJI = re.compile(
    r"\U0001f3f4[\U000e0020-\U000e007e]+\U000e007f"
    r"|[\U0001f1e6-\U0001f1ff]{2}"
    r"|[0-9#*]\ufe0f?\u20e3"
    rf"|{_UNIT}(?:\u200d{_UNIT})*"
)

# Everything an emoji sequence can start with or contain besides ASCII keycap bases: a
# cheap test that spares the regular expression of the emoji to most strings.
_MAYBE_EMOJI = re.compile(r"[\u00a9\u00ae\u203c-\U0010ffff]")

# Words of a Unicode name that qualify the script instead of naming it.
_WIDTH = ("FULLWIDTH", "HALFWIDTH")


@lru_cache(maxsize=MAX_CHARACTERS)
def family_of(char: str) -> tuple[str, str | None]:
    """The general category of a character and, for a letter, its script: the
    first word of its Unicode name (``LATIN``, ``CYRILLIC``, ``CJK``...), after
    ``FULLWIDTH`` or ``HALFWIDTH``; ``UNKNOWN`` when it has no name."""
    kind = category(char)
    if kind[0] != "L":
        return kind, None
    words = name(char, "").split()
    if len(words) > 1 and words[0] in _WIDTH:
        words = words[1:]
    return kind, words[0] if words else "UNKNOWN"


class CharacterCensus:
    """Counts the characters, the case of the ends and the emoji of distinct
    strings, each weighted by its occurrences."""

    __slots__ = (
        "_emoji",
        "_table",
        "emoji_sequences",
        "ends_lowercase",
        "ends_uppercase",
        "limit",
        "over",
        "title_case",
        "values",
        "with_emoji",
    )

    def __init__(self) -> None:
        self._table: Counter[str] = Counter()
        self._emoji: Counter[str] = Counter()
        self.values = 0
        self.ends_uppercase = 0
        self.ends_lowercase = 0
        self.title_case = 0
        self.with_emoji = 0
        self.emoji_sequences = 0
        # Set when a table passed its bound: the field is then ``limited``.
        self.over = False
        # The bound that was passed, for the ``limited`` envelope.
        self.limit = MAX_CHARACTERS

    def add(self, raws: Sequence[str], counts: Sequence[int]) -> None:
        """Count distinct strings, each weighted by its occurrences. Empty
        strings are values with no character."""
        self.values += sum(counts)
        if self.over:
            return
        if not all(raws):
            kept = [
                (raw, count) for raw, count in zip(raws, counts, strict=True) if raw
            ]
            raws = [raw for raw, _ in kept]
            counts = [count for _, count in kept]
        if not raws:
            return
        joined = "".join(raws)
        self._count_characters(raws, counts, joined)
        last = [raw[-1] for raw in raws]
        self.ends_uppercase += sum(compress(counts, map(str.isupper, last)))
        self.ends_lowercase += sum(compress(counts, map(str.islower, last)))
        self.title_case += sum(compress(counts, map(str.istitle, raws)))
        self._count_emoji(raws, counts, joined)
        if len(self._table) > MAX_CHARACTERS or len(self._emoji) > MAX_EMOJI:
            self.over = True
            self.limit = MAX_CHARACTERS if len(self._table) > MAX_CHARACTERS else MAX_EMOJI
            self._table.clear()
            self._emoji.clear()

    def _count_characters(
        self, raws: Sequence[str], counts: Sequence[int], joined: str
    ) -> None:
        table = self._table
        if len(raws) == sum(counts):
            table.update(joined)
            return
        groups: dict[int, list[str]] = {}
        for raw, count in zip(raws, counts, strict=True):
            groups.setdefault(count, []).append(raw)
        for count, group in groups.items():
            part = Counter("".join(group))
            if count == 1:
                table.update(part)
            else:
                for char, number in part.items():
                    table[char] += number * count

    def _count_emoji(
        self, raws: Sequence[str], counts: Sequence[int], joined: str
    ) -> None:
        if _MAYBE_EMOJI.search(joined) is None:
            return
        table = self._emoji
        for raw, count in zip(raws, counts, strict=True):
            if _MAYBE_EMOJI.search(raw) is None:
                continue
            found = _EMOJI.findall(raw)
            if found:
                self.with_emoji += count
                self.emoji_sequences += count * len(found)
                for sequence in found:
                    table[sequence] += count

    def result(
        self, basis: Literal["exact", "sample"], top: int
    ) -> Complete[CharacterMap] | Limited:
        """The map, listing ``top`` characters and emoji, or ``limited`` when a
        table passed its bound."""
        if self.over:
            return Limited(reason=REASON, limit=self.limit)
        scripts: Counter[str] = Counter()
        categories: Counter[str] = Counter()
        for char, number in self._table.items():
            kind, script = family_of(char)
            categories[kind] += number
            if script is not None:
                scripts[script] += number
        listed = sorted(self._table.items(), key=lambda item: (-item[1], item[0]))
        emoji = sorted(self._emoji.items(), key=lambda item: (-item[1], item[0]))
        return Complete[CharacterMap](
            value=CharacterMap(
                basis=basis,
                values=self.values,
                characters=sum(self._table.values()),
                distinct=len(self._table),
                top=[
                    CharacterCount(
                        char=char, codepoint=ord(char), occurrence_count=number
                    )
                    for char, number in listed[:top]
                ],
                scripts=_families(scripts),
                categories=_families(categories),
                ends_uppercase=self.ends_uppercase,
                ends_lowercase=self.ends_lowercase,
                title_case=self.title_case,
                with_emoji=self.with_emoji,
                emoji_sequences=self.emoji_sequences,
                emoji=[
                    EmojiCount(sequence=sequence, occurrence_count=number)
                    for sequence, number in emoji[:top]
                ],
            )
        )


def _families(counter: Counter[str]) -> list[CharacterFamily]:
    return [
        CharacterFamily(name=family, occurrence_count=number)
        for family, number in sorted(
            counter.items(), key=lambda item: (-item[1], item[0])
        )
    ]


def _field_map(field: FieldResult, top: int) -> FieldCharacterMap:
    """The character map of one field from its stored samples."""
    if field.exposure in ("mask", "hide"):
        return Disabled()
    samples = field.values.samples
    if samples.kept < samples.of:
        return NotApplicable(reason="samples_withheld")
    entries = list(samples.listed)
    if samples.by_length is not None:
        known = {entry.id for entry in entries}
        entries.extend(
            entry for entry in samples.by_length.listed if entry.id not in known
        )
    strings = [entry for entry in entries if entry.type == "string"]
    if not strings:
        return NotApplicable(reason="no_values")
    census = CharacterCensus()
    census.add([entry.value for entry in strings], [entry.count for entry in strings])
    # Long texts are stored as previews only, so they never make the map exact.
    exact = samples.selection == "all" and samples.long_texts is None
    return census.result("exact" if exact else "sample", top)


def derive_characters(
    datasets: Sequence[DatasetResult], top: int, diagnostics: DiagnosticCollector
) -> DerivedCharacters | None:
    """The character map of every field of ``datasets``, or ``None`` when it is
    turned off (``top`` is 0).

    Like the discovery of patterns it reads the samples of the finished scan and
    is isolated: a field on which it raises gets a ``failed`` entry and an error in
    ``diagnostics``, the others are unaffected."""
    if top == 0:
        return None
    fields = []
    for dataset in datasets:
        for field in dataset.fields:
            try:
                found = _field_map(field, top)
            except Exception as exc:  # noqa: BLE001 - the post-pass is isolated per field
                # Only the exception type: its message could quote a value.
                index = diagnostics.add(
                    "character_map_failed",
                    "error",
                    f"The character map of field {field.display} failed "
                    f"({type(exc).__name__}): it is omitted; other analyses continue.",
                    dataset=dataset.id,
                    field=field.id,
                )
                found = Failed(reason="character_map_failed", diagnostic=index)
            fields.append(
                FieldCharacters(dataset=dataset.id, field=field.id, characters=found)
            )
    return DerivedCharacters(fields=fields)

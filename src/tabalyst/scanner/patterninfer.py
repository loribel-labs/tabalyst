# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Structural pattern inference from the samples of a scan (design 18.12): the
grammar, the linear matcher and the candidates of a field. It never reads the
source.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from itertools import groupby

from tabalyst.scanner.config import PatternInferenceSettings
from tabalyst.scanner.models import (
    DatasetResult,
    DerivedPatterns,
    FieldPatterns,
    FieldPatternsComplete,
    FieldPatternsNotApplicable,
    FieldResult,
    PatternCandidate,
    PatternConfidence,
    PatternCoverage,
    PatternExcluded,
    PatternGrammar,
    PatternLengths,
    PatternOther,
    PatternOverlap,
    PatternPopulation,
    PatternToken,
    SampleEntry,
)

GRAMMAR_NAME = "tabalyst.pattern"
# Raised when a token class, a generalization rule or the rendering changes.
GRAMMAR_VERSION = 1
# A run of letters or digits that is the same in at least this many distinct
# values of a structure is a literal (so that `A` is not any capital): with
# fewer values a constant may be chance.
LITERAL_MIN_SUPPORT = 5
# A value with more tokens is excluded: the signature stays readable and the
# work per value bounded.
MAX_TOKENS = 32
# The most values one field's inference reads (design 18.12). The default
# sample sizes stay under it; a field with a larger sample is read in id order.
MAX_VALUES = 20_000
EXAMPLES = 3

# A token read from a value: (class code, literal character, count, text). The
# codes are D digits, U ASCII capitals, L ASCII lowercase letters, X letters of
# a run that has a non-ASCII letter (any letter once generalized), N letters or
# digits (generalized) and P a literal character repeated ``count`` times.
Token = tuple[str, str | None, int, str]
_KIND = {
    "D": "digit_ascii",
    "U": "upper_ascii",
    "L": "lower_ascii",
    "X": "letter_unicode",
    "N": "alphanumeric",
    "P": "literal",
}
_CODE = {kind: code for code, kind in _KIND.items()}
_SYMBOL = {
    "digit_ascii": "9",
    "upper_ascii": "X",
    "lower_ascii": "x",
    "letter_unicode": "@",
    "alphanumeric": "#",
}
_ASCII_RUNS = re.compile(r"([0-9]+)|([A-Z]+)|([a-z]+)|((.)\5*)", re.DOTALL)
_CASE_RUNS = re.compile(r"[A-Z]+|[a-z]+")
_GROUP_CODE = {1: "D", 2: "U", 3: "L"}
_LETTER_CODES = frozenset("ULX")
_ALNUM_CODES = frozenset("DULXN")
# Characters that need quotes in the human rendering, on top of letters, digits
# and white space.
_RESERVED = frozenset("'{}@#")


def tokenize(value: str) -> list[Token]:
    """The tokens of ``value`` under the grammar (design 18.12).

    A run of ASCII digits is one token, a run of letters one token or, for
    ASCII letters, one per case; any other character is a literal, a run of the
    same character being one token.
    """
    if value.isascii():
        tokens: list[Token] = []
        for match in _ASCII_RUNS.finditer(value):
            index = match.lastindex
            text = match.group(index)
            if index == 4:
                tokens.append(("P", match.group(5), len(text), text))
            else:
                tokens.append((_GROUP_CODE[index], None, len(text), text))
        return tokens
    return _tokenize_unicode(value)


def _category(char: str) -> str:
    if "0" <= char <= "9":
        return "D"
    if char.isalpha():
        return "A"
    return "P" + char


def _tokenize_unicode(value: str) -> list[Token]:
    tokens: list[Token] = []
    for category, chars in groupby(value, _category):
        text = "".join(chars)
        if category == "D":
            tokens.append(("D", None, len(text), text))
        elif category == "A":
            if text.isascii():
                for run in _CASE_RUNS.findall(text):
                    tokens.append(("U" if run[0] < "a" else "L", None, len(run), run))
            else:
                tokens.append(("X", None, len(text), text))
        else:
            tokens.append(("P", category[1:], len(text), text))
    return tokens


def generalize(tokens: Sequence[Token], level: int) -> list[Token]:
    """The tokens at a generalization level: 1 turns adjacent letter tokens into
    one letter token of any case or script, 2 turns adjacent letters and digits
    into one alphanumeric token. Level 0 is the tokens as read."""
    if level == 0:
        return list(tokens)
    codes = _LETTER_CODES if level == 1 else _ALNUM_CODES
    target = "X" if level == 1 else "N"
    merged: list[Token] = []
    for code, literal, count, text in tokens:
        if code not in codes:
            merged.append((code, literal, count, text))
        elif merged and merged[-1][0] == target:
            _, _, before, joined = merged[-1]
            merged[-1] = (target, None, before + count, joined + text)
        else:
            merged.append((target, None, count, text))
    return merged


# Signatures --------------------------------------------------------------------


def _is_class_char(kind: str, char: str) -> bool:
    if kind == "digit_ascii":
        return "0" <= char <= "9"
    if kind == "upper_ascii":
        return "A" <= char <= "Z"
    if kind == "lower_ascii":
        return "a" <= char <= "z"
    if kind == "letter_unicode":
        return char.isalpha()
    return "0" <= char <= "9" or char.isalpha()


Matcher = tuple[tuple[str, str | None, int, int], ...]


def compile_signature(signature: Sequence[PatternToken]) -> Matcher:
    """The matcher of a signature."""
    return tuple((token.kind, token.text, token.min, token.max) for token in signature)


def matches(matcher: Matcher, value: str) -> bool:
    """Whether the whole of ``value`` matches the signature.

    Adjacent class tokens never share a character (the grammar merges letters
    and digits into one token before they could), and a class token is followed
    by a literal outside it or by a class of another kind, so taking as many
    characters as allowed is always right: one pass, no backtracking, whatever
    the value.
    """
    position = 0
    size = len(value)
    for kind, text, low, high in matcher:
        if text is not None:
            step = len(text)
            count = 0
            while count < high and value.startswith(text, position):
                position += step
                count += 1
            if count < low:
                return False
        else:
            start = position
            limit = min(size, position + high)
            while position < limit and _is_class_char(kind, value[position]):
                position += 1
            if position - start < low:
                return False
    return position == size


def _needs_quotes(text: str) -> bool:
    return any(char.isalnum() or char.isspace() or char in _RESERVED for char in text)


def _quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def _repeat(low: int, high: int) -> str:
    return f"{{{low}}}" if low == high else f"{{{low},{high}}}"


def render_signature(signature: Sequence[PatternToken]) -> str:
    """The compact human rendering of a signature: `9` digit, `X` capital, `x`
    lowercase letter, `@` any letter, `#` letter or digit, repeated by a count
    (`X{2,3}`); literal letters, digits and spaces are quoted (`XX9999'A'`), so
    a literal `A` is never read as a capital."""
    parts = []
    for token in signature:
        low, high = token.min, token.max
        if token.kind == "literal":
            text = token.text or ""
            quoted = _needs_quotes(text)
            unit = _quote(text) if quoted else text
            if low == high and (low == 1 or (not quoted and low <= 4)):
                parts.append(unit * low)
            else:
                parts.append(_quote(text) + _repeat(low, high))
        else:
            symbol = _SYMBOL[token.kind]
            if low == high and low <= 6:
                parts.append(symbol * low)
            else:
                parts.append(symbol + _repeat(low, high))
    return "".join(parts)


# Groups of values that share a structure ------------------------------------------


class _Group:
    """The values of one structure, with the range of each token's length and the
    text of the tokens that never vary."""

    __slots__ = ("highs", "key", "level", "lows", "members", "merged", "texts")

    def __init__(self, key: tuple[tuple[str, str | None], ...], level: int) -> None:
        self.key = key
        self.members: list[int] = []
        self.lows: list[int] = []
        self.highs: list[int] = []
        self.texts: list[str | None] = []
        self.level = level
        self.merged = 0

    def add(self, index: int, tokens: Sequence[Token]) -> None:
        if not self.members:
            self.lows = [token[2] for token in tokens]
            self.highs = list(self.lows)
            self.texts = [token[3] for token in tokens]
        else:
            lows, highs, texts = self.lows, self.highs, self.texts
            for position, (_, _, count, text) in enumerate(tokens):
                if count < lows[position]:
                    lows[position] = count
                elif count > highs[position]:
                    highs[position] = count
                if texts[position] != text:
                    texts[position] = None
        self.members.append(index)

    def absorb(self, other: _Group) -> None:
        """Take the values of a group of the same key."""
        if not self.members:
            self.lows, self.highs, self.texts = other.lows, other.highs, other.texts
        else:
            for position, count in enumerate(other.lows):
                self.lows[position] = min(self.lows[position], count)
                self.highs[position] = max(self.highs[position], other.highs[position])
                if self.texts[position] != other.texts[position]:
                    self.texts[position] = None
        self.members.extend(other.members)
        self.merged += other.merged
        self.level = max(self.level, other.level)


def _key(tokens: Sequence[Token]) -> tuple[tuple[str, str | None], ...]:
    return tuple((token[0], token[1]) for token in tokens)


def _key_text(key: tuple[tuple[str, str | None], ...]) -> str:
    return "".join(code if literal is None else code + literal for code, literal in key)


def _group_values(all_tokens: Sequence[Sequence[Token]]) -> list[_Group]:
    groups: dict[tuple[tuple[str, str | None], ...], _Group] = {}
    for index, tokens in enumerate(all_tokens):
        key = _key(tokens)
        group = groups.get(key)
        if group is None:
            group = groups[key] = _Group(key, 0)
            group.merged = 1
        group.add(index, tokens)
    return list(groups.values())


def _ranked(groups: Sequence[_Group]) -> list[_Group]:
    return sorted(groups, key=lambda group: (-len(group.members), _key_text(group.key)))


def _regroup(
    tail: Sequence[_Group], all_tokens: Sequence[Sequence[Token]], level: int
) -> list[_Group]:
    """The groups of ``tail`` merged under the structure of ``level``."""
    regrouped: dict[tuple[tuple[str, str | None], ...], _Group] = {}
    for source in tail:
        key = _key(generalize(all_tokens[source.members[0]], level))
        group = regrouped.get(key)
        if group is None:
            group = regrouped[key] = _Group(key, level)
        group.merged += source.merged
        for index in source.members:
            group.add(index, generalize(all_tokens[index], level))
    return list(regrouped.values())


def _final_groups(
    groups: list[_Group],
    all_tokens: Sequence[Sequence[Token]],
    settings: PatternInferenceSettings,
) -> tuple[list[_Group], bool]:
    """The groups after the generalization ladder, and whether it ran.

    With more structures than ``max_patterns`` the smallest ones are generalized
    step by step (adjacent letters, then letters and digits) until the groups
    that can be candidates fit; a generalized group whose structure equals a kept
    one joins it.
    """
    ranked = _ranked(groups)
    limit = settings.max_patterns
    if len(ranked) <= limit:
        return ranked, False
    head, tail = ranked[: limit - 1], ranked[limit - 1 :]
    by_key = {group.key: group for group in head}
    for level in (1, 2):
        regrouped = []
        for group in _regroup(tail, all_tokens, level):
            kept = by_key.get(group.key)
            if kept is None:
                regrouped.append(group)
            else:
                kept.absorb(group)
        tail = regrouped
        eligible = sum(
            len(group.members) >= settings.min_distinct for group in head + tail
        )
        if eligible <= limit:
            break
    return _ranked(head + tail), True


def _signature(group: _Group) -> list[PatternToken]:
    """The signature of a group: promoted literals only for a structure read as
    it is, with enough values to rule out chance."""
    promote = group.level == 0 and len(group.members) >= LITERAL_MIN_SUPPORT
    signature = []
    for position, (code, literal) in enumerate(group.key):
        low, high = group.lows[position], group.highs[position]
        if code == "P":
            signature.append(
                PatternToken(kind="literal", text=literal, min=low, max=high)
            )
            continue
        text = group.texts[position]
        if promote and text is not None:
            signature.append(PatternToken(kind="literal", text=text, min=1, max=1))
        else:
            signature.append(PatternToken(kind=_KIND[code], min=low, max=high))
    return signature


def _specificity(
    signature: Sequence[PatternToken], level: int, order: int
) -> tuple[int, int, int, int]:
    """Order of exclusive classification: more literal letters or digits, then
    less generalization, then narrower repeats, then the rank (PAT-08)."""
    literal_chars = sum(
        len(token.text or "")
        for token in signature
        if token.kind == "literal" and (token.text or "").isalnum()
    )
    width = sum(token.max - token.min for token in signature)
    return (-literal_chars, level, width, order)


# Population -----------------------------------------------------------------------


def _population(
    field: FieldResult, settings: PatternInferenceSettings
) -> tuple[list[SampleEntry], PatternExcluded, bool, int]:
    """The usable entries of the samples of a field, the exclusions, whether the
    population was cut at ``MAX_VALUES`` and the usable count before the cut."""
    samples = field.values.samples
    entries = list(samples.listed)
    if samples.by_length is not None:
        known = {entry.id for entry in entries}
        entries.extend(
            entry for entry in samples.by_length.listed if entry.id not in known
        )
    entries.sort(key=lambda entry: entry.id)
    non_string = empty = too_long = 0
    usable = []
    for entry in entries:
        if entry.type != "string":
            non_string += 1
        elif not entry.value:
            empty += 1
        elif len(entry.value) > settings.max_value_length:
            too_long += 1
        else:
            usable.append(entry)
    long_texts = samples.long_texts.occurrences if samples.long_texts else 0
    excluded = PatternExcluded(
        long_text_occurrences=long_texts,
        non_string_values=non_string,
        empty_values=empty,
        too_long_values=too_long,
        too_complex_values=0,
    )
    return usable[:MAX_VALUES], excluded, len(usable) > MAX_VALUES, len(usable)


def _not_applicable(dataset: str, field: str, reason: str) -> FieldPatterns:
    return FieldPatternsNotApplicable(dataset=dataset, field=field, reason=reason)


def infer_field(
    dataset: str, field: FieldResult, settings: PatternInferenceSettings
) -> FieldPatterns:
    """The inferred patterns of one field, or why there are none."""
    if field.technical_type.type not in ("text", "mixed"):
        return _not_applicable(dataset, field.id, "technical_type")
    samples = field.values.samples
    if field.exposure in ("mask", "hide"):
        return _not_applicable(dataset, field.id, "exposure")
    if samples.kept < samples.of:
        return _not_applicable(dataset, field.id, "samples_withheld")
    entries, excluded, cut, available = _population(field, settings)
    if not entries:
        only_long = excluded.long_text_occurrences > 0 and samples.of == 0
        return _not_applicable(
            dataset, field.id, "long_texts_only" if only_long else "no_values"
        )
    tokens = [tokenize(entry.value) for entry in entries]
    complex_ = [index for index, row in enumerate(tokens) if len(row) > MAX_TOKENS]
    if complex_:
        drop = set(complex_)
        entries = [entry for index, entry in enumerate(entries) if index not in drop]
        tokens = [row for index, row in enumerate(tokens) if index not in drop]
        excluded = excluded.model_copy(update={"too_complex_values": len(complex_)})
    if len(entries) < settings.min_distinct:
        return _not_applicable(dataset, field.id, "too_few_distinct")
    return _infer(dataset, field, settings, entries, tokens, excluded, cut, available)


def _infer(
    dataset: str,
    field: FieldResult,
    settings: PatternInferenceSettings,
    entries: list[SampleEntry],
    tokens: list[list[Token]],
    excluded: PatternExcluded,
    cut: bool,
    available: int,
) -> FieldPatterns:
    samples = field.values.samples
    # `complete` claims every distinct value of the field: a sample that was
    # cut or a population from which values were excluded is only a part.
    complete = samples.selection == "all" and not cut and not (
        excluded.long_text_occurrences
        or excluded.non_string_values
        or excluded.empty_values
        or excluded.too_long_values
        or excluded.too_complex_values
    )
    basis = "all_distinct" if complete else "sample"
    total = len(entries)
    groups, laddered = _final_groups(_group_values(tokens), tokens, settings)
    eligible = [g for g in groups if len(g.members) >= settings.min_distinct]
    chosen = eligible[: settings.max_patterns]
    signatures = [_signature(group) for group in chosen]
    owner: dict[int, int] = {}
    for number, group in enumerate(chosen):
        for index in group.members:
            owner[index] = number
    specificity = [
        _specificity(signatures[number], chosen[number].level, number)
        for number in range(len(chosen))
    ]
    broad = [
        number
        for number, signature in enumerate(signatures)
        if any(token.kind in ("letter_unicode", "alphanumeric") for token in signature)
    ]
    matchers = {number: compile_signature(signatures[number]) for number in broad}
    attributed: list[list[int]] = [[] for _ in chosen]
    overlaps: dict[tuple[int, ...], int] = {}
    for index, entry in enumerate(entries):
        if not broad:
            if index in owner:
                attributed[owner[index]].append(index)
            continue
        found = {owner[index]} if index in owner else set()
        for number in broad:
            if number not in found and matches(matchers[number], entry.value):
                found.add(number)
        if not found:
            continue
        if len(found) > 1:
            key = tuple(sorted(found))
            overlaps[key] = overlaps.get(key, 0) + 1
        attributed[min(found, key=lambda number: specificity[number])].append(index)
    candidates = []
    for number, members in enumerate(attributed):
        signature = signatures[number]
        lengths = [len(entries[index].value) for index in members] or [0]
        count = len(members)
        share = count / total
        candidates.append(
            PatternCandidate(
                id=f"p{number + 1}",
                role="principal" if number == 0 else "secondary",
                signature=signature,
                render=render_signature(signature),
                lengths=PatternLengths(min=min(lengths), max=max(lengths)),
                generalization=chosen[number].level,
                merged_structures=chosen[number].merged,
                coverage=PatternCoverage(
                    distinct=count, share=round(share, 4), basis=basis
                ),
                confidence=PatternConfidence(
                    method="laplace_share", value=round(share * count / (count + 1), 4)
                ),
                examples=sorted(entries[index].id for index in members)[:EXAMPLES],
            )
        )
    left = len(groups) - len(chosen)
    other_count = total - sum(len(members) for members in attributed)
    limited = laddered or len(eligible) > settings.max_patterns
    return FieldPatternsComplete(
        dataset=dataset,
        field=field.id,
        population=PatternPopulation(
            source="samples",
            selection=samples.selection,
            complete=complete,
            available=available,
            distinct=total,
            excluded=excluded,
        ),
        candidates=candidates,
        other=PatternOther(
            distinct=other_count,
            share=round(other_count / total, 4),
            structures=left,
        ),
        overlaps=[
            PatternOverlap(
                patterns=[f"p{number + 1}" for number in key], values=values
            )
            for key, values in sorted(overlaps.items())
        ],
        limits=[
            *(["max_patterns"] if limited else []),
            *(["max_values"] if cut else []),
        ],
    )


def infer_patterns(
    datasets: Sequence[DatasetResult], settings: PatternInferenceSettings
) -> DerivedPatterns | None:
    """The patterns inferred in every field of ``datasets``, or ``None`` when the
    inference is turned off.

    One entry per field, in the order of the datasets and fields. The result
    depends on the samples only, not on how the scan ran (principle 6).
    """
    if not settings.enabled:
        return None
    return DerivedPatterns(
        grammar=PatternGrammar(name=GRAMMAR_NAME, version=GRAMMAR_VERSION),
        domain="original",
        fields=[
            infer_field(dataset.id, field, settings)
            for dataset in datasets
            for field in dataset.fields
        ],
    )

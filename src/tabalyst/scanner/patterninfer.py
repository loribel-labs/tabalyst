# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Hierarchical pattern discovery from the samples of a scan (design 18.12): the
grammar, the linear matcher, and the families and patterns of fixed length of an
eligible field. It never reads the source.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import groupby
from os.path import commonprefix

from tabalyst.scanner import pattern_eligibility
from tabalyst.scanner.config import PatternInferenceSettings
from tabalyst.scanner.diagnostics import DiagnosticCollector
from tabalyst.scanner.models import (
    DatasetResult,
    DerivedPatterns,
    FamilyPattern,
    FieldPatterns,
    FieldPatternsComplete,
    FieldPatternsFailed,
    FieldPatternsNotApplicable,
    FieldResult,
    PatternAlgorithm,
    PatternEligibility,
    PatternExcluded,
    PatternFamily,
    PatternGrammar,
    PatternLimit,
    PatternNode,
    PatternOtherStructures,
    PatternPopulation,
    PatternTable,
    PatternTableCell,
    PatternTableOthers,
    PatternToken,
    PatternTokenKind,
    SampleEntry,
)

GRAMMAR_NAME = "tabalyst.pattern"
# Raised when a token class, a rule of the signatures or the rendering changes.
GRAMMAR_VERSION = 2
# Raised when the discovery, a constant of it or the order of its steps changes
# (FR-020). It is part of the cache key of the discovery.
ALGORITHM_VERSION = 1
# A value with more tokens is excluded: the signature stays readable and the
# work per value bounded.
MAX_TOKENS = 32
EXAMPLES = 3
# Structures merge into one family only at the edge of a block, over at most
# this many positions (E2); each must be material: two distinct values or this
# share of the distinct values or of the occurrences.
MERGE_MAX_WIDTH = 2
MATERIAL_SHARE = 0.05

# A token read from a value: (class code, literal character, count, text). The
# codes are D digits, U ASCII capitals, L ASCII lowercase letters, X letters of
# a run that has a non-ASCII letter and P a literal character repeated ``count``
# times. The Z codes only appear in the rows of a pattern that merges
# structures: the position is of several classes.
Token = tuple[str, str | None, int, str]
_KIND: dict[str, PatternTokenKind] = {
    "D": "digit_ascii",
    "U": "upper_ascii",
    "L": "lower_ascii",
    "X": "letter_unicode",
    "ZDU": "upper_digit",
    "ZDL": "lower_digit",
    "ZDUL": "alphanumeric",
    "P": "literal",
}
_SYMBOL = {
    "digit_ascii": "9",
    "upper_ascii": "A",
    "lower_ascii": "a",
    "letter_unicode": "@",
    "upper_digit": "X",
    "lower_digit": "x",
    "alphanumeric": "#",
}
_ASCII_RUNS = re.compile(r"([0-9]+)|([A-Z]+)|([a-z]+)|((.)\5*)", re.DOTALL)
_CASE_RUNS = re.compile(r"[A-Z]+|[a-z]+")
_GROUP_CODE = {1: "D", 2: "U", 3: "L"}
# The classes a position of a merged block can take, and the codes of the union.
_MERGEABLE = "DUL"
# Characters that need quotes in the human rendering, on top of letters, digits
# and white space. `?` is never produced but belongs to the notation.
_RESERVED = frozenset("'{}@#?")
# A literal repeated up to this many times is written out in a run of literals.
_MAX_PLAIN_REPEAT = 4


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
    if "0" <= char <= "9":
        return True
    if kind == "upper_digit":
        return "A" <= char <= "Z"
    if kind == "lower_digit":
        return "a" <= char <= "z"
    return "A" <= char <= "Z" or "a" <= char <= "z"


Matcher = tuple[tuple[str, str | None, int, int], ...]


def compile_signature(signature: Sequence[PatternToken]) -> Matcher:
    """The matcher of a signature."""
    return tuple((token.kind, token.text, token.min, token.max) for token in signature)


def matches(matcher: Matcher, value: str) -> bool:
    """Whether the whole of ``value`` matches the signature.

    A class token takes as many characters as it is allowed. That is right for
    the signatures the discovery writes, whose tokens all have a fixed length,
    and for a written pattern whose adjacent tokens never share a character: one
    pass, no backtracking, whatever the value.
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
    """The compact human rendering of a signature (DEC-032): `9` digit, `A`
    capital, `a` lowercase letter, `@` letter of either case, `X` capital or
    digit, `x` lowercase letter or digit, `#` ASCII letter or digit, repeated by
    a count (`A{2,3}`); literal letters and digits are quoted (`AA9999'A'`), so a
    literal `A` is never read as a capital. A fixed value and the separators that
    touch it are written as one text (`'CLI-00'999999`), since `''` between two
    quoted texts is an apostrophe. A single space between two elements is written
    as it is and ends the text before it (`'AK' 9999`, `A9A 9A9`); at the start or
    the end, or repeated, a space is quoted with the text it touches."""
    parts: list[str] = []
    run = ""
    last = len(signature) - 1
    for index, token in enumerate(signature):
        low, high = token.min, token.max
        if token.kind == "literal":
            text = token.text or ""
            if text == " " and low == high == 1 and 0 < index < last and (
                signature[index - 1].text != " " and signature[index + 1].text != " "
            ):
                _flush_literals(parts, run)
                run = ""
                parts.append(" ")
            elif low == high and low <= _MAX_PLAIN_REPEAT:
                run += text * low
            else:
                _flush_literals(parts, run)
                run = ""
                parts.append(_quote(text) + _repeat(low, high))
            continue
        _flush_literals(parts, run)
        run = ""
        symbol = _SYMBOL[token.kind]
        if low == high and low <= 6:
            parts.append(symbol * low)
        else:
            parts.append(symbol + _repeat(low, high))
    _flush_literals(parts, run)
    return "".join(parts)


def _flush_literals(parts: list[str], run: str) -> None:
    """Write a run of literals: quoted when it holds a letter, a digit, a space or
    a character of the notation, as it is otherwise."""
    if run:
        parts.append(_quote(run) if _needs_quotes(run) else run)


def candidate_order(
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


def _build_signature(rows: Sequence[Sequence[Token]], fold: bool) -> list[PatternToken]:
    """The signature of rows of tokens that share their classes and lengths.

    With ``fold`` the characters that every row has at the start of a class
    token become a literal, and a token that every row repeats entirely a
    literal alone (DEC-026): `'AK'-9999`. A position of several classes is never
    folded.
    """
    signature: list[PatternToken] = []
    for position, (code, literal, count, _) in enumerate(rows[0]):
        if code == "P":
            signature.append(PatternToken(kind="literal", text=literal, min=count, max=count))
            continue
        size = 0
        if fold and len(code) == 1:
            texts = [row[position][3] for row in rows]
            size = len(commonprefix(texts))
            if size:
                signature.append(
                    PatternToken(kind="literal", text=texts[0][:size], min=1, max=1)
                )
        if count > size:
            signature.append(
                PatternToken(kind=_KIND[code], min=count - size, max=count - size)
            )
    return signature


# Population -----------------------------------------------------------------------


def _population(
    field: FieldResult, settings: PatternInferenceSettings
) -> tuple[list[SampleEntry], PatternExcluded, bool, int]:
    """The usable entries of the samples of a field, the exclusions, whether the
    population was cut at ``max_values`` and the usable count before the cut.

    An integer is read as its decimal text, so a column of digits typed as
    integers takes part (design 18.12); other non-string values are excluded."""
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
        if entry.type not in ("string", "integer"):
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
    return (
        usable[: settings.max_values],
        excluded,
        len(usable) > settings.max_values,
        len(usable),
    )


def _not_applicable(
    dataset: str, field: str, eligibility: PatternEligibility
) -> FieldPatterns:
    return FieldPatternsNotApplicable(
        dataset=dataset,
        field=field,
        eligibility=eligibility,
        reason=pattern_eligibility.deciding_reason(eligibility),
    )


# Families -------------------------------------------------------------------------

Key = tuple[tuple[str, str | None], ...]


def _key(tokens: Sequence[Token]) -> Key:
    return tuple((token[0], token[1]) for token in tokens)


def _key_text(key: Key) -> str:
    return "".join(code if literal is None else code + literal for code, literal in key)


@dataclass(frozen=True, slots=True)
class _Merge:
    """Structures merged at the edge of a block (E2). The base structure has the
    class ``base_code`` at its token ``token``; each merged one has a token of
    another class, ``parts[key]``, of ``width`` positions, after it (``suffix``)
    or before it (``prefix``). The position is of the union of the classes."""

    token: int
    edge: str
    width: int
    base_code: str
    parts: dict[Key, str]

    def union(self, keys: Sequence[Key], base: Key) -> str:
        """The code of the class of the merged positions of a pattern that holds
        the structures ``keys``: the classes of those structures only."""
        classes = {self.parts.get(key, self.base_code) if key != base else self.base_code for key in keys}
        return "Z" + "".join(code for code in _MERGEABLE if code in classes)


@dataclass(slots=True)
class _Family:
    """The distinct values of one structure or of merged structures."""

    keys: list[Key]
    members: list[int]
    merge: _Merge | None = None


def _material(members: Sequence[int], entries: Sequence[SampleEntry], total_d: int, total_o: int) -> bool:
    """Whether a structure is more than chance: two distinct values, or a share
    of the distinct values or of the occurrences."""
    if len(members) >= 2:
        return True
    occurrences = sum(entries[index].count for index in members)
    return len(members) >= MATERIAL_SHARE * total_d or occurrences >= MATERIAL_SHARE * total_o


def _merge_options(base: Key) -> list[tuple[int, str, str, Key]]:
    """The structures that could merge into ``base``: for each of its tokens
    that is a block by itself, a token of another class after or before it."""
    options = []
    for index, (code, _) in enumerate(base):
        if code not in _MERGEABLE:
            continue
        if index and base[index - 1][0] != "P":
            continue
        if index + 1 < len(base) and base[index + 1][0] != "P":
            continue
        for other in _MERGEABLE:
            if other == code or "D" not in (code, other):
                continue
            extra = ((other, None),)
            options.append((index, "suffix", other, base[: index + 1] + extra + base[index + 1 :]))
            options.append((index, "prefix", other, base[:index] + extra + base[index:]))
    return options


def _edge_positions(index: int, edge: str) -> tuple[int, int]:
    """The positions of the stable token and of the added token in a merged block
    whose base token is ``index``: the added one follows it (suffix) or precedes
    it (prefix)."""
    return (index, index + 1) if edge == "suffix" else (index + 1, index)


def _merged_width(
    key: Key,
    members: Sequence[int],
    tokens: Sequence[Sequence[Token]],
    index: int,
    edge: str,
    allowed: set[int],
) -> int | None:
    """The positions a structure adds to the block of its base, when its values
    all add the same number of them (``MERGE_MAX_WIDTH`` at most), keep a stable
    part at least as long as the added one and give a block length the base also
    has (E2); ``None`` otherwise."""
    stable, mixed = _edge_positions(index, edge)
    widths = set()
    for member in members:
        row = tokens[member]
        width = row[mixed][2]
        if width > MERGE_MAX_WIDTH or row[stable][2] < width:
            return None
        if row[stable][2] + width not in allowed:
            return None
        widths.add(width)
    return widths.pop() if len(widths) == 1 else None


def _best_merge(
    base: Key,
    groups: dict[Key, list[int]],
    tokens: Sequence[Sequence[Token]],
    usable: set[Key],
) -> _Merge | None:
    """The structures that merge into ``base`` at one edge of one block: of the
    edges that have some, the one that gathers most values (E2). Structures of
    another width than the largest one's stay apart."""
    found: dict[tuple[int, str], list[tuple[Key, str, int]]] = defaultdict(list)
    allowed: dict[int, set[int]] = {}
    for index, edge, other, key in _merge_options(base):
        if key not in usable:
            continue
        lengths = allowed.get(index)
        if lengths is None:
            lengths = allowed[index] = {tokens[member][index][2] for member in groups[base]}
        width = _merged_width(key, groups[key], tokens, index, edge, lengths)
        if width is not None:
            found[(index, edge)].append((key, other, width))
    best: tuple[int, tuple[int, str], _Merge] | None = None
    for (index, edge), options in sorted(found.items()):
        options.sort(key=lambda item: (-len(groups[item[0]]), _key_text(item[0])))
        width = options[0][2]
        parts = {key: other for key, other, size in options if size == width}
        size = sum(len(groups[key]) for key in parts)
        if best is None or size > best[0]:
            best = (size, (index, edge), _Merge(index, edge, width, base[index][0], parts))
    return None if best is None else best[2]


def _families(
    groups: dict[Key, list[int]],
    entries: Sequence[SampleEntry],
    tokens: Sequence[Sequence[Token]],
) -> list[_Family]:
    """The families of the structures, unranked (PAT-14, E2): one per structure,
    except the structures that merge at the edge of a block."""
    total_d = len(entries)
    total_o = sum(entry.count for entry in entries)
    material = {
        key for key, members in groups.items() if _material(members, entries, total_d, total_o)
    }
    ordered = sorted(groups, key=lambda key: (-len(groups[key]), _key_text(key)))
    claimed: set[Key] = set()
    merges: dict[Key, _Merge] = {}
    # The structures that can still be merged into a base: a structure that is
    # the base of a merge, or was merged, is never merged into another.
    usable = set(material)
    for base in ordered:
        if base in claimed or base not in material:
            continue
        merge = _best_merge(base, groups, tokens, usable)
        if merge is not None:
            merges[base] = merge
            claimed.update(merge.parts)
            usable.difference_update(merge.parts)
            usable.discard(base)
    families = []
    for key in ordered:
        if key in claimed:
            continue
        merge = merges.get(key)
        keys = [key, *sorted(merge.parts, key=_key_text)] if merge else [key]
        members = sorted(index for item in keys for index in groups[item])
        families.append(_Family(keys, members, merge))
    return families


def _vector(row: Sequence[Token], merge: _Merge | None, key: Key, base: Key) -> tuple[int, ...]:
    """The lengths of a value in the skeleton of its family: a merged block
    counts as one token, as long as the whole block."""
    if merge is None or key == base:
        return tuple(token[2] for token in row)
    stable, mixed = _edge_positions(merge.token, merge.edge)
    counts = [token[2] for token in row]
    counts[stable] += counts[mixed]
    del counts[mixed]
    return tuple(counts)


def _union_row(row: Sequence[Token], merge: _Merge, union: str, base: bool) -> list[Token]:
    """The row of a value of a merging pattern: its block split into the stable
    part and the positions of the class ``union``, whichever structure it has."""
    index = merge.token
    if base:
        code, _, count, text = row[index]
        width = merge.width
        if merge.edge == "suffix":
            split: list[Token] = [
                (code, None, count - width, text[:-width]),
                (union, None, width, text[-width:]),
            ]
        else:
            split = [
                (union, None, width, text[:width]),
                (code, None, count - width, text[width:]),
            ]
        return [*row[:index], *split, *row[index + 1 :]]
    first, second = row[index], row[index + 1]
    if merge.edge == "suffix":
        tail: list[Token] = [first, (union, None, second[2], second[3])]
    else:
        tail = [(union, None, first[2], first[3]), second]
    return [*row[:index], *tail, *row[index + 2 :]]


def _score(count_d: int, count_o: int, total_d: int, total_o: int) -> float:
    return round(max(count_d / total_d, count_o / total_o), 9)


@dataclass(slots=True)
class _BuiltNode:
    """A structure of a merging pattern, before its identifier."""

    key: Key
    signature: list[PatternToken]
    d: int
    o: int


@dataclass(slots=True)
class _Built:
    """A pattern before its identifier: its members, signature and nodes."""

    vector: tuple[int, ...]
    members: list[int]
    d: int
    o: int
    signature: list[PatternToken]
    nodes: list[_BuiltNode]


def _patterns(
    family: _Family,
    entries: Sequence[SampleEntry],
    tokens: Sequence[Sequence[Token]],
    row_keys: Sequence[Key],
    total_d: int,
    total_o: int,
) -> list[_Built]:
    """The patterns of a family, one per combination of lengths, the largest
    first (PAT-15). A pattern that holds several of the merged structures has a
    position of the union class and a node per structure (composition)."""
    base = family.keys[0]
    merge = family.merge
    by_vector: dict[tuple[int, ...], list[int]] = defaultdict(list)
    for member in family.members:
        by_vector[_vector(tokens[member], merge, row_keys[member], base)].append(member)
    built = []
    for vector, members in by_vector.items():
        keys = sorted({row_keys[member] for member in members}, key=_key_text)
        fold = len(members) >= 2
        nodes = []
        if merge is not None and len(keys) > 1:
            union = merge.union(keys, base)
            rows = [
                _union_row(tokens[member], merge, union, row_keys[member] == base)
                for member in members
            ]
            signature = _build_signature(rows, fold)
            for key in keys:
                part = [member for member in members if row_keys[member] == key]
                nodes.append(
                    _BuiltNode(
                        key,
                        _build_signature([tokens[member] for member in part], len(part) >= 2),
                        len(part),
                        sum(entries[member].count for member in part),
                    )
                )
            nodes.sort(key=lambda node: (-node.d, -node.o, _key_text(node.key)))
        else:
            signature = _build_signature([tokens[member] for member in members], fold)
        built.append(
            _Built(
                vector,
                members,
                len(members),
                sum(entries[member].count for member in members),
                signature,
                nodes,
            )
        )
    built.sort(key=lambda item: (-_score(item.d, item.o, total_d, total_o), item.vector))
    return built


def _lengths(vector: tuple[int, ...], base: Key) -> list[int]:
    return [count for count, (code, _) in zip(vector, base, strict=False) if code != "P"]


def _format(
    members: Sequence[int], entries: Sequence[SampleEntry], tokens: Sequence[Sequence[Token]]
) -> str:
    """The exact form of the commonest value of a pattern, one symbol per
    character: `AA-9999`."""
    commonest = min(members, key=lambda member: (-entries[member].count, entries[member].value))
    return render_signature(_build_signature([tokens[commonest]], False))


def _examples(members: Sequence[int], entries: Sequence[SampleEntry]) -> list[int]:
    return sorted(entries[member].id for member in members)[:EXAMPLES]


# Entry of a field -----------------------------------------------------------------

# What ``_infer`` reads: the entries, their tokens, the exclusions, whether the
# population was cut and the available count.
_Prepared = tuple[list[SampleEntry], list[list[Token]], PatternExcluded, bool, int]
# A failure before the eligibility was known.
_UNKNOWN = PatternEligibility(state="not_assessable", score=0.0, reasons=["inference_error"])


def _prepare(
    field: FieldResult, settings: PatternInferenceSettings
) -> tuple[PatternEligibility, _Prepared | None]:
    """The eligibility of a field and, for an eligible one, what ``_infer``
    reads. The population is tokenized once, for both."""
    early = pattern_eligibility.preselect(field)
    if early is not None:
        return early, None
    entries, excluded, cut, available = _population(field, settings)
    if not entries:
        return pattern_eligibility.without_values(field, excluded), None
    tokens = [tokenize(entry.value) for entry in entries]
    complex_ = [index for index, row in enumerate(tokens) if len(row) > MAX_TOKENS]
    if complex_:
        drop = set(complex_)
        entries = [entry for index, entry in enumerate(entries) if index not in drop]
        tokens = [row for index, row in enumerate(tokens) if index not in drop]
        excluded = excluded.model_copy(update={"too_complex_values": len(complex_)})
    eligibility = pattern_eligibility.assess(field, entries, tokens, settings)
    if eligibility.state != "eligible":
        return eligibility, None
    return eligibility, (entries, tokens, excluded, cut, available)


def infer_field(
    dataset: str, field: FieldResult, settings: PatternInferenceSettings
) -> FieldPatterns:
    """The discovered patterns of one field, or its eligibility when it is not
    eligible (design 18.12)."""
    return _entry(dataset, field, settings, *_prepare(field, settings))


def _entry(
    dataset: str,
    field: FieldResult,
    settings: PatternInferenceSettings,
    eligibility: PatternEligibility,
    prepared: _Prepared | None,
) -> FieldPatterns:
    """The entry of a field once its eligibility is known: discovered when it is
    eligible, ``not_applicable`` otherwise."""
    if prepared is None:
        return _not_applicable(dataset, field.id, eligibility)
    return _infer(dataset, field, settings, eligibility, *prepared)


def _lengths_table(cells: Sequence[tuple[str, int, int]], limit: int) -> PatternTable:
    """The table of the combinations of lengths kept out of the patterns: the
    largest ``limit`` cells, the rest in ``others``."""
    merged: dict[str, list[int]] = {}
    for text, d, o in cells:
        total = merged.setdefault(text, [0, 0])
        total[0] += d
        total[1] += o
    ranked = sorted(merged.items(), key=lambda item: (-item[1][1], -item[1][0], item[0]))
    kept, rest = ranked[:limit], ranked[limit:]
    return PatternTable(
        facet="lengths",
        cells=[PatternTableCell(value=text, d=total[0], o=total[1]) for text, total in kept],
        others=PatternTableOthers(
            distinct=len(rest),
            d=sum(total[0] for _, total in rest),
            o=sum(total[1] for _, total in rest),
        ),
    )


def _infer(
    dataset: str,
    field: FieldResult,
    settings: PatternInferenceSettings,
    eligibility: PatternEligibility,
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
    total_d = len(entries)
    total_o = sum(entry.count for entry in entries)
    row_keys = [_key(row) for row in tokens]
    groups: dict[Key, list[int]] = defaultdict(list)
    for index, key in enumerate(row_keys):
        groups[key].append(index)
    ranked = sorted(
        _families(groups, entries, tokens),
        key=lambda family: (
            -_score(
                len(family.members),
                sum(entries[member].count for member in family.members),
                total_d,
                total_o,
            ),
            _key_text(family.keys[0]),
        ),
    )
    limits: set[PatternLimit] = {"max_values"} if cut else set()
    kept, dropped = ranked[: settings.max_families], ranked[settings.max_families :]
    if dropped:
        limits.add("max_families")
    built = [_patterns(family, entries, tokens, row_keys, total_d, total_o) for family in kept]
    cut_patterns: list[list[_Built]] = [[] for _ in kept]
    for number, patterns in enumerate(built):
        if len(patterns) > settings.max_patterns_per_family:
            cut_patterns[number] = patterns[settings.max_patterns_per_family :]
            built[number] = patterns[: settings.max_patterns_per_family]
            limits.add("max_patterns_per_family")
    _fit_budget(kept, dropped, built, cut_patterns, settings.max_patterns, limits)
    families = [
        _publish_family(
            f"f{number}", family, built[number - 1], cut_patterns[number - 1], entries, tokens, settings
        )
        for number, family in enumerate(kept, 1)
    ]
    other_members = [member for family in dropped for member in family.members]
    other = PatternOtherStructures(
        structures=sum(len(family.keys) for family in dropped),
        d=len(other_members),
        o=sum(entries[member].count for member in other_members),
    )
    order: tuple[PatternLimit, ...] = (
        "max_values",
        "max_families",
        "max_patterns_per_family",
        "max_patterns",
    )
    return FieldPatternsComplete(
        dataset=dataset,
        field=field.id,
        eligibility=eligibility,
        population=PatternPopulation(
            source="samples",
            selection=samples.selection,
            complete=complete,
            available=available,
            distinct=total_d,
            occurrences=total_o,
            occurrences_basis="exact" if complete else "sample",
            excluded=excluded,
        ),
        families=families,
        other=other,
        limits=[name for name in order if name in limits],
    )


def _fit_budget(
    kept: list[_Family],
    dropped: list[_Family],
    built: list[list[_Built]],
    cut_patterns: list[list[_Built]],
    budget: int,
    limits: set[PatternLimit],
) -> None:
    """Keep the patterns and nodes of the field within ``max_patterns``: first
    the nodes of the smallest patterns go (a pattern keeps all its nodes or
    none), then the smallest patterns, each family keeping its largest one, which
    go to the table of lengths of their family, then the smallest families, which
    go to ``dropped`` (counted in ``other``) so that a budget below the number of
    families is met too."""

    def size() -> int:
        return sum(1 + len(pattern.nodes) for patterns in built for pattern in patterns)

    if size() <= budget:
        return
    limits.add("max_patterns")
    everything = sorted(
        ((number, pattern) for number, patterns in enumerate(built) for pattern in patterns),
        key=lambda item: (item[1].d, item[1].o),
    )
    for _, pattern in everything:
        if size() <= budget:
            return
        pattern.nodes = []
    for number, pattern in everything:
        if size() <= budget:
            return
        patterns = built[number]
        if patterns[0] is not pattern:
            patterns[:] = [item for item in patterns if item is not pattern]
            cut_patterns[number].append(pattern)
    while size() > budget and len(kept) > 1:
        dropped.append(kept.pop())
        built.pop()
        cut_patterns.pop()


def _publish_family(
    identifier: str,
    family: _Family,
    patterns: list[_Built],
    left_out: list[_Built],
    entries: Sequence[SampleEntry],
    tokens: Sequence[Sequence[Token]],
    settings: PatternInferenceSettings,
) -> PatternFamily:
    base = family.keys[0]
    published = []
    for number, pattern in enumerate(patterns, 1):
        pattern_id = f"{identifier}.p{number}"
        nodes = [
            PatternNode(
                id=f"{pattern_id}.n{position}",
                parent=pattern_id,
                level=2,
                facet="composition",
                signature=built.signature,
                render=render_signature(built.signature),
                d=built.d,
                o=built.o,
                role="principal" if position == 1 else "secondary",
            )
            for position, built in enumerate(pattern.nodes, 1)
        ]
        published.append(
            FamilyPattern(
                id=pattern_id,
                signature=pattern.signature,
                render=render_signature(pattern.signature),
                format=_format(pattern.members, entries, tokens),
                lengths=_lengths(pattern.vector, base),
                d=pattern.d,
                o=pattern.o,
                examples=_examples(pattern.members, entries),
                nodes=nodes,
            )
        )
    tables = []
    if left_out:
        tables.append(
            _lengths_table(
                [
                    (",".join(map(str, _lengths(item.vector, base))), item.d, item.o)
                    for item in left_out
                ],
                settings.max_patterns_per_family,
            )
        )
    return PatternFamily(
        id=identifier,
        key=_key_text(base),
        composition=[_key_text(key) for key in family.keys] if family.merge else [],
        d=len(family.members),
        o=sum(entries[member].count for member in family.members),
        patterns=published,
        tables=tables,
        examples=_examples(family.members, entries),
    )


def _infer_isolated(
    dataset: str,
    field: FieldResult,
    settings: PatternInferenceSettings,
    diagnostics: DiagnosticCollector,
) -> FieldPatterns:
    """``infer_field``, with an exception turned into a ``failed`` entry and a
    ``pattern_inference_failed`` error: a bug in this post-pass must not lose a
    scan that already read the whole source (as for a detector, CA19)."""
    eligibility = _UNKNOWN
    try:
        eligibility, prepared = _prepare(field, settings)
        return _entry(dataset, field, settings, eligibility, prepared)
    except Exception as exc:  # noqa: BLE001 - the inference is isolated per field
        # Only the exception type: its message could quote a value.
        index = diagnostics.add(
            "pattern_inference_failed",
            "error",
            f"Pattern inference failed on field {field.display} "
            f"({type(exc).__name__}): its patterns are omitted; other analyses "
            "continue.",
            dataset=dataset,
            field=field.id,
        )
        return FieldPatternsFailed(
            dataset=dataset, field=field.id, eligibility=eligibility, diagnostic=index
        )


def infer_patterns(
    datasets: Sequence[DatasetResult],
    settings: PatternInferenceSettings,
    diagnostics: DiagnosticCollector,
) -> DerivedPatterns | None:
    """The patterns discovered in every field of ``datasets``, or ``None`` when
    the discovery is turned off.

    One entry per field, in the order of the datasets and fields. The result
    depends on the samples only, not on how the scan ran (principle 6). A field
    on which the discovery raises gets a ``failed`` entry and an error in
    ``diagnostics``; the others are unaffected.
    """
    if not settings.enabled:
        return None
    return DerivedPatterns(
        grammar=PatternGrammar(name=GRAMMAR_NAME, version=GRAMMAR_VERSION),
        algorithm=PatternAlgorithm(version=ALGORITHM_VERSION),
        domain="original",
        fields=[
            _infer_isolated(dataset.id, field, settings, diagnostics)
            for dataset in datasets
            for field in dataset.fields
        ],
    )

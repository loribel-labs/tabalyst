# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The reader of the hierarchy of patterns of a field: it recognizes a value once, in
its family, and finds the deepest pattern or node that reads it (design 20.9).

It is compiled from the entry of the discovery and from the population the discovery
read, which it recognizes again to learn what the sample showed (the segments, the
combinations of lengths) and to check the entry against the samples. It holds no count.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from tabalyst.scanner.config import PatternInferenceSettings
from tabalyst.scanner.models import (
    FamilyPattern,
    FieldPatternsComplete,
    FieldResult,
    PatternFamily,
    PatternNode,
)
from tabalyst.scanner.patterninfer import (
    MAX_TOKENS,
    Matcher,
    Token,
    compile_signature,
    key_text,
    matches,
    tokenize,
    tokenized_population,
)
from tabalyst.scanner.secondpass.accumulators import ScanMismatch

# The outcomes of a value (design 20.9, PAT-24), and the two ways to be left out.
KNOWN = 0
NEW_LENGTH = 1
NEW_SEGMENT = 2
UNKNOWN_STRUCTURE = 3
TOO_LONG = 4
TOO_COMPLEX = 5

# The code of a literal token in a structure key (``UP-D``: capitals, the literal
# ``-``, digits); the codes of the classes are one other letter.
_LITERAL = "P"


@dataclass(slots=True)
class Group:
    """The children of a node that read one position of the skeleton, by the text
    they fix. ``sizes`` are the lengths of those texts, the longest first (a head
    and a tail are read at each); a token and a composition are read whole."""

    edge: str
    position: int
    cells: dict[str, list[Node]]
    sizes: tuple[int, ...] = ()


@dataclass(slots=True)
class Node:
    """A pattern or a node: its identifier and rendering in the Scan, the slot of
    its counters, the distinct values the Scan published for it and its children.
    ``also`` is what the node fixes besides the text its parent finds it by, as
    (edge, position, text)."""

    id: str
    render: str
    slot: int
    published_d: int
    also: tuple[tuple[str, int, str], ...] = ()
    groups: list[Group] = field(default_factory=list)
    children: list[Node] = field(default_factory=list)
    # The reading of the children when they all read one position at one length:
    # (position, mode, width, cells). The common case, read without a loop.
    quick: tuple[int, int, int, dict[str, list[Node]]] | None = None


_MODES = {"token": 0, "head": 1, "tail": 2}


@dataclass(slots=True)
class Facet:
    """A position of the skeleton of a family that a node or a table reads, at the
    lengths its cells have. ``cells`` maps the text of a cell to its slot in the
    table. ``seen`` holds the texts the sample showed that were no cell: when it is
    empty the sample showed the facet *closed* (every value was a cell) and a
    value that is no cell is new; a facet with other values is open, and a value
    that is no cell is nothing remarkable."""

    label: str
    edge: str
    position: int
    cells: dict[str, int] = field(default_factory=dict)
    texts: list[str] = field(default_factory=list)
    seen: set[str] = field(default_factory=set)
    sizes: tuple[int, ...] = (1,)
    index: int = 0
    mode: int = 0
    width: int = 1

    def settle(self, index: int) -> None:
        """Fix the lengths of the cells once they are all known."""
        self.index = index
        self.mode = _MODES[self.edge]
        self.sizes = tuple(sorted({len(text) for text in self.cells}, reverse=True)) or (1,)
        self.width = self.sizes[0]

    def find(self, texts: Sequence[str]) -> tuple[int | None, str]:
        """The slot of the cell that reads a value, if any, and the text of the
        value at this facet (at the finest length for a head or a tail)."""
        text = texts[self.position]
        mode = self.mode
        if mode == 0:
            return self.cells.get(text), text
        width = self.width
        if mode == 1:
            segment = text[:width]
            slot = self.cells.get(segment)
            if slot is None and len(self.sizes) > 1:
                for size in self.sizes[1:]:
                    slot = self.cells.get(text[:size])
                    if slot is not None:
                        break
            return slot, segment
        segment = text[-width:]
        slot = self.cells.get(segment) if len(text) >= width else None
        if slot is None and len(self.sizes) > 1:
            for size in self.sizes[1:]:
                if len(text) >= size:
                    slot = self.cells.get(text[-size:])
                    if slot is not None:
                        break
        return slot, segment


@dataclass(slots=True)
class Family:
    """A family compiled for the recognition of its values."""

    id: str
    index: int
    published_d: int
    base: tuple[str, ...]
    # The structure keys it reads, each with the index of the token where a merged
    # structure holds its block (None for the base structure).
    blocks: dict[str, int | None]
    patterns: list[Node] = field(default_factory=list)
    matchers: list[Matcher] = field(default_factory=list)
    by_vector: dict[tuple[int, ...], Node] = field(default_factory=dict)
    # The combinations of lengths the sample showed that no pattern holds (the table
    # of lengths of the family) and the cells that table lists.
    off_vectors: set[tuple[int, ...]] = field(default_factory=set)
    lengths_cells: list[str] = field(default_factory=list)
    facets: list[Facet] = field(default_factory=list)
    off_slot: int = 0
    new_slot: int = 0
    # How each facet is read, unpacked in the hot loop: (position, mode, width, cells,
    # seen, simple, facet); ``simple`` when the cells all have one length.
    plan: list[tuple[int, int, int, dict[str, int], set[str], bool, Facet]] = field(
        default_factory=list
    )

    def lengths_text(self, vector: tuple[int, ...]) -> str:
        """The combination of lengths of the class tokens, as the table of
        lengths of the Scan spells it."""
        return ",".join(
            str(count) for count, code in zip(vector, self.base, strict=False) if code != _LITERAL
        )


# What the hot path returns for a string: the outcome, its family, the slot that
# counts it, what each facet of the family reads in it (the slot of the cell, if any,
# and the text) and its lengths. A tuple is built faster than an object.
Reading = tuple[int, "Family | None", int, "list[tuple[int | None, str]]", tuple[int, ...]]
_TOO_LONG: Reading = (TOO_LONG, None, -1, [], ())
_TOO_COMPLEX: Reading = (TOO_COMPLEX, None, -1, [], ())
_UNKNOWN: Reading = (UNKNOWN_STRUCTURE, None, -1, [], ())
_CLASS_PATTERN = {"D": "[0-9]+", "U": "[A-Z]+", "L": "[a-z]+"}


def _ascii_regex(key: str) -> re.Pattern[str] | None:
    """The regular expression that reads the ASCII strings of a structure key, one
    group a token: classes that are disjoint and literal runs of one character
    leave nothing to backtrack, and it matches exactly the strings that tokenize to
    the key. ``None`` for a key that no ASCII string has (a letter that is not
    ASCII, a literal that is not)."""
    parts = []
    position = 0
    while position < len(key):
        code = key[position]
        if code == _LITERAL:
            char = key[position + 1]
            if not char.isascii():
                return None
            parts.append(f"({re.escape(char)}+)")
            position += 2
        elif code in _CLASS_PATTERN:
            parts.append(f"({_CLASS_PATTERN[code]})")
            position += 1
        else:
            return None
    return re.compile("".join(parts))


def _skeleton(
    family: Family, key: str, row: Sequence[Token]
) -> tuple[list[str], tuple[int, ...]]:
    """The texts and the lengths of a value in the skeleton of its family: the two
    tokens of a merged structure that make up the block count as one."""
    texts = [token[3] for token in row]
    counts = [token[2] for token in row]
    block = family.blocks[key]
    if block is not None:
        texts[block : block + 2] = ["".join(texts[block : block + 2])]
        counts[block : block + 2] = [counts[block] + counts[block + 1]]
    return texts, tuple(counts)


class HierarchyReader:
    """The compiled hierarchy of a field and what its sample showed."""

    __slots__ = ("ascii", "by_key", "families", "max_length", "slots")

    def __init__(self, max_length: int) -> None:
        self.max_length = max_length
        self.families: list[Family] = []
        self.by_key: dict[str, Family] = {}
        # The regular expressions of the structures that an ASCII string can have,
        # in the order of the families (the largest first).
        self.ascii: list[tuple[re.Pattern[str], Family, str, int | None]] = []
        self.slots = 0

    # Compilation --------------------------------------------------------------

    @classmethod
    def build(
        cls,
        entry: FieldPatternsComplete,
        field_result: FieldResult,
        settings: PatternInferenceSettings,
    ) -> HierarchyReader:
        """Compile ``entry`` and recognize again the population its discovery read.

        Raises ``ScanMismatch`` when the samples of the Scan no longer give what the
        entry says: it was not made from them."""
        reader = cls(settings.max_value_length)
        _, rows = tokenized_population(field_result, settings)
        keys = [key_text(row) for row in rows]
        shapes: dict[str, tuple[str, ...]] = {}
        for key, row in zip(keys, rows, strict=True):
            shapes.setdefault(key, tuple(token[0] for token in row))
        for index, published in enumerate(entry.families):
            reader._add_family(index, published, shapes)
        slots: Counter[int] = Counter()
        families: Counter[int] = Counter()
        left_out = 0
        for key, row in zip(keys, rows, strict=True):
            _, family, slot, _, _ = reader._locate(row, key, learn=True)
            if family is None:
                left_out += 1
            else:
                slots[slot] += 1
                families[family.index] += 1
        if left_out != entry.other.d:
            raise ScanMismatch("the samples of the scan no longer give the families of its patterns")
        for family in reader.families:
            if families[family.index] != family.published_d:
                raise ScanMismatch(f"the samples of the scan no longer give family {family.id}")
            for pattern in family.patterns:
                _check(pattern, slots)
        return reader

    def _slot(self) -> int:
        self.slots += 1
        return self.slots - 1

    def _add_family(
        self, index: int, published: PatternFamily, shapes: dict[str, tuple[str, ...]]
    ) -> None:
        base = shapes.get(published.key)
        if base is None:
            raise ScanMismatch(f"the samples of the scan hold no value of family {published.id}")
        keys = published.composition or [published.key]
        family = Family(
            id=published.id,
            index=index,
            published_d=published.d,
            base=base,
            blocks={
                key: None if key == published.key else _block(base, shapes.get(key))
                for key in keys
            },
        )
        family.off_slot = self._slot()
        family.new_slot = self._slot()
        facets: dict[tuple[str, int], Facet] = {}
        for pattern in published.patterns:
            family.patterns.append(self._node(pattern, facets))
            family.matchers.append(compile_signature(pattern.signature))
        for table in published.tables:
            if table.facet == "lengths":
                family.lengths_cells = [cell.value for cell in table.cells]
                continue
            edge, _, position = table.facet.partition(":")
            facet = _facet(facets, edge, int(position) - 1)
            for cell in table.cells:
                _seed(facet, cell.value)
        family.facets = sorted(facets.values(), key=lambda item: (item.position, item.edge))
        for number, facet in enumerate(family.facets):
            facet.settle(number)
            family.plan.append(
                (
                    facet.position,
                    facet.mode,
                    facet.width,
                    facet.cells,
                    facet.seen,
                    len(facet.sizes) == 1,
                    facet,
                )
            )
        self.families.append(family)
        for key in keys:
            self.by_key[key] = family
            regex = _ascii_regex(key)
            if regex is not None:
                self.ascii.append((regex, family, key, family.blocks[key]))

    def _node(
        self, published: FamilyPattern | PatternNode, facets: dict[tuple[str, int], Facet]
    ) -> Node:
        conditions = getattr(published, "also", ())
        also = tuple(
            (edge, int(number) - 1, condition.value)
            for condition in conditions
            for edge, _, number in [condition.facet.partition(":")]
        )
        node = Node(published.id, published.render, self._slot(), published.d, also)
        groups: dict[tuple[str, int], Group] = {}
        for child in published.nodes:
            built = self._node(child, facets)
            node.children.append(built)
            if child.facet == "composition":
                edge, position = "composition", -1
            else:
                edge, _, number = child.facet.partition(":")
                position = int(number) - 1
                _seed(_facet(facets, edge, position), child.value)
            group = groups.get((edge, position))
            if group is None:
                group = groups[(edge, position)] = Group(edge, position, {})
            group.cells.setdefault(child.value, []).append(built)
        for group in groups.values():
            group.sizes = tuple(sorted({len(text) for text in group.cells}, reverse=True))
        node.groups = list(groups.values())
        if len(node.groups) == 1 and node.groups[0].edge != "composition":
            [only] = node.groups
            if len(only.sizes) == 1:
                node.quick = (only.position, _MODES[only.edge], only.sizes[0], only.cells)
        return node

    # Recognition --------------------------------------------------------------

    def read(self, raw: str) -> Reading:
        """Where a string falls, once: excluded (too long or too complex), read by no
        family, or in a family (see ``Reading``). An ASCII string is read by the
        regular expression of its structure and never tokenized."""
        if len(raw) > self.max_length:
            return _TOO_LONG
        if raw.isascii():
            for regex, family, key, block in self.ascii:
                found = regex.fullmatch(raw)
                if found is not None:
                    texts: Sequence[str] = found.groups()
                    vector = tuple(map(len, texts))
                    if block is not None:
                        merged = list(texts)
                        merged[block : block + 2] = ["".join(texts[block : block + 2])]
                        counts = list(vector)
                        counts[block : block + 2] = [counts[block] + counts[block + 1]]
                        texts, vector = merged, tuple(counts)
                    return self._place(family, texts, vector, key, False)
            if len(raw) > MAX_TOKENS and len(tokenize(raw)) > MAX_TOKENS:
                return _TOO_COMPLEX
            return _UNKNOWN
        row = tokenize(raw)
        if len(row) > MAX_TOKENS:
            return _TOO_COMPLEX
        return self._locate(row, key_text(row), learn=False)

    def _locate(self, row: Sequence[Token], key: str, learn: bool) -> Reading:
        family = self.by_key.get(key)
        if family is None:
            return _UNKNOWN
        texts, vector = _skeleton(family, key, row)
        return self._place(family, texts, vector, key, learn)

    def _place(
        self, family: Family, texts: Sequence[str], vector: tuple[int, ...], key: str, learn: bool
    ) -> Reading:
        """Where a value of ``family`` falls: its pattern by its lengths, the deepest
        node that reads it, and what each facet of the family reads in it. When
        ``learn`` is set the value is one of the sample: it is recorded."""
        pattern = family.by_vector.get(vector)
        outcome = KNOWN
        if pattern is None:
            if learn:
                pattern = self._learn_vector(family, vector, "".join(texts))
            elif vector not in family.off_vectors:
                outcome = NEW_LENGTH
        if outcome == NEW_LENGTH:
            slot = family.new_slot
        elif pattern is None:
            slot = family.off_slot
        else:
            node = pattern
            while node.groups:
                quick = node.quick
                if quick is not None:
                    where, how, size, children = quick
                    text = texts[where]
                    segment = text if how == 0 else text[:size] if how == 1 else text[-size:]
                    candidates = children.get(segment)
                    if candidates is None:
                        break
                    if len(candidates) == 1 and not candidates[0].also:
                        node = candidates[0]
                        continue
                child = _child(node, texts, key)
                if child is None:
                    break
                node = child
            slot = node.slot
        reads: list[tuple[int | None, str]] = []
        unseen = False
        for position, mode, width, cells, seen, simple, facet in family.plan:
            cell: int | None
            if simple:
                text = texts[position]
                segment = text if mode == 0 else text[:width] if mode == 1 else text[-width:]
                cell = cells.get(segment)
            else:
                cell, segment = facet.find(texts)
            reads.append((cell, segment))
            if cell is None:
                if learn:
                    seen.add(segment)
                elif not seen:
                    unseen = True
        if unseen and outcome == KNOWN:
            outcome = NEW_SEGMENT
        return (outcome, family, slot, reads, vector)

    @staticmethod
    def _learn_vector(family: Family, vector: tuple[int, ...], value: str) -> Node | None:
        """The pattern that holds a combination of lengths the sample showed (the one
        whose signature reads that value), or ``None``: the combination is in the
        table of lengths of the family."""
        if vector in family.off_vectors:
            return None
        for node, matcher in zip(family.patterns, family.matchers, strict=True):
            if matches(matcher, value):
                family.by_vector[vector] = node
                return node
        family.off_vectors.add(vector)
        return None


def _check(node: Node, slots: Counter[int]) -> int:
    """The distinct values the sample puts in the subtree of ``node``; they must be
    those the Scan published."""
    below = slots[node.slot] + sum(_check(child, slots) for child in node.children)
    if below != node.published_d:
        raise ScanMismatch(f"the samples of the scan no longer give node {node.id}")
    return below


def _child(node: Node, texts: Sequence[str], key: str) -> Node | None:
    """The child of ``node`` that reads a value, if any."""
    for group in node.groups:
        edge = group.edge
        found: list[Node] | None
        if edge == "composition":
            found = group.cells.get(key)
        else:
            text = texts[group.position]
            found = None
            if edge == "token":
                found = group.cells.get(text)
            elif edge == "head":
                for size in group.sizes:
                    found = group.cells.get(text[:size])
                    if found is not None:
                        break
            else:
                for size in group.sizes:
                    if len(text) >= size:
                        found = group.cells.get(text[-size:])
                        if found is not None:
                            break
        if found is not None:
            for candidate in found:
                if not candidate.also or _holds(candidate.also, texts):
                    return candidate
    return None


def _holds(conditions: tuple[tuple[str, int, str], ...], texts: Sequence[str]) -> bool:
    """Whether a value fixes everything a merged node fixes besides its own facet."""
    for edge, position, text in conditions:
        value = texts[position]
        if edge == "head":
            if not value.startswith(text):
                return False
        elif edge == "tail":
            if not value.endswith(text):
                return False
        elif value != text:
            return False
    return True


def _facet(facets: dict[tuple[str, int], Facet], edge: str, position: int) -> Facet:
    facet = facets.get((edge, position))
    if facet is None:
        facet = facets[(edge, position)] = Facet(f"{edge}:{position + 1}", edge, position)
    return facet


def _seed(facet: Facet, text: str) -> None:
    if text not in facet.cells:
        facet.cells[text] = len(facet.texts)
        facet.texts.append(text)


def _block(base: tuple[str, ...], other: tuple[str, ...] | None) -> int:
    """The index, in the tokens of a merged structure, of the pair of tokens that
    make up the block it shares with the base structure (design 18.12, E2): the
    merged structure has one more token than the base, of another class, after
    the base's token (suffix) or before it (prefix)."""
    if other is None:
        raise ScanMismatch("the samples of the scan hold no value of a merged structure")
    position = 0
    while position < len(base) and base[position] == other[position]:
        position += 1
    if position < len(base) and base[position] != _LITERAL:
        return position
    return position - 1

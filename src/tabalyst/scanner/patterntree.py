# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The tree of content nodes under a pattern (design 18.12, E5): the primary
facet, the facets that depend on it nested below, the compressions, the depth cut
and the facets left to the tables. It works on the texts of the members of a
pattern at each position of its skeleton and knows nothing of signatures.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from tabalyst.scanner.patternfacets import (
    FLATTEN,
    MIN_DEVELOP,
    NU_MIN,
    Alphabet,
    Edge,
    Facet,
    Member,
    Prefix,
    best_facet,
    dependence,
    reread,
)


@dataclass(frozen=True, slots=True)
class Position:
    """A token of the skeleton of a family that a facet can read: its place, its
    alphabet and the text it has in each member (one per member, in order)."""

    index: int
    alphabet: Alphabet
    texts: Sequence[str]


# What a node fixes at a position of the skeleton, by position: the head, the tail
# or the whole token, as text (a tail is spelled from the left).
Constraints = dict[int, tuple[Edge, str]]


@dataclass(slots=True)
class TreeNode:
    """A content node: the members that share what ``constraints`` fix (all those
    of its ancestors and its own), its occurrences, the gains of its prefix on both
    measures and the sigma of its facet, and its children."""

    position: int
    edge: Edge
    constraints: Constraints
    members: list[int]
    occurrences: int
    gain_d: float
    gain_o: float
    sigma: float
    children: list[TreeNode] = field(default_factory=list)

    @property
    def distinct(self) -> int:
        return len(self.members)

    def sort_key(self) -> tuple[int, int, str]:
        return (-self.distinct, -self.occurrences, self.constraints[self.position][1])


@dataclass(slots=True)
class Developed:
    """What the facets of a pattern gave: the published facet of each position,
    the primary nodes (``roots``, or for each given group the nodes nested under it),
    the positions the tree reads and whether ``max_depth`` cut a node."""

    facets: dict[int, Facet] = field(default_factory=dict)
    roots: list[TreeNode] = field(default_factory=list)
    under: list[list[TreeNode]] = field(default_factory=list)
    used: set[int] = field(default_factory=set)
    cut: bool = False


def published_facets(
    positions: Sequence[Position], occurrences: Sequence[int]
) -> dict[int, Facet]:
    """The facet of each position that is published (E3 and E4): the best of its
    head, its tail and its whole value. A constant token reads nothing."""
    found: dict[int, Facet] = {}
    for position in positions:
        if len(set(position.texts)) < 2:
            continue
        members = [Member(text, count) for text, count in zip(position.texts, occurrences, strict=True)]
        facet = best_facet(members, position.alphabet)
        if facet is not None:
            found[position.index] = facet
    return found


class _Builder:
    """The construction of the tree of one pattern (or of the nodes of one
    group of it)."""

    def __init__(
        self,
        positions: Sequence[Position],
        occurrences: Sequence[int],
        facets: dict[int, Facet],
        max_level: int,
    ) -> None:
        self.positions = {position.index: position for position in positions}
        self.occurrences = occurrences
        self.facets = facets
        self.max_level = max_level
        self.used: set[int] = set()
        self._cells: dict[int, list[int]] = {}
        self._whole: dict[int, tuple[Counter[int], Counter[int]]] = {}

    def _cell_of(self, position: int) -> list[int]:
        """For each member, the leaf of the facet of ``position`` that holds it
        (its index), or -1 for the rest of the facet."""
        cells = self._cells.get(position)
        if cells is None:
            cells = [-1] * len(self.occurrences)
            for number, leaf in enumerate(self.facets[position].leaves()):
                for index in leaf.group:
                    cells[index] = number
            self._cells[position] = cells
            whole_d: Counter[int] = Counter(cells)
            whole_o: Counter[int] = Counter()
            for index, cell in enumerate(cells):
                whole_o[cell] += self.occurrences[index]
            self._whole[position] = (whole_d, whole_o)
        return cells

    def dependence_on(self, members: Sequence[int], position: int) -> float:
        """How much the facet of ``position`` depends on being among ``members``,
        on distinct values and on occurrences, the larger kept."""
        cells = self._cell_of(position)
        node_d: Counter[int] = Counter()
        node_o: Counter[int] = Counter()
        for index in members:
            node_d[cells[index]] += 1
            node_o[cells[index]] += self.occurrences[index]
        whole_d, whole_o = self._whole[position]
        return max(dependence(node_d, whole_d), dependence(node_o, whole_o))

    def nodes_of(
        self,
        facet: Facet,
        position: int,
        members: Sequence[int],
        constraints: Constraints,
    ) -> list[TreeNode]:
        """The nodes of a facet read over ``members`` (its prefixes index them), its
        longer prefixes as children, then, below each leaf, the facets that depend
        on it."""
        sigma = facet.sigma()
        built = [
            self._node(prefix, facet.edge, position, members, constraints, sigma)
            for prefix in facet.nodes
        ]
        return sorted(built, key=TreeNode.sort_key)

    def _node(
        self,
        prefix: Prefix,
        edge: Edge,
        position: int,
        members: Sequence[int],
        constraints: Constraints,
        sigma: float,
    ) -> TreeNode:
        fixed = {**constraints, position: (edge, prefix.text)}
        node = TreeNode(
            position,
            edge,
            fixed,
            [members[index] for index in prefix.group],
            prefix.occurrences,
            prefix.gain_d,
            prefix.gain_o,
            sigma,
        )
        if prefix.children:
            node.children = sorted(
                (self._node(child, edge, position, members, constraints, sigma) for child in prefix.children),
                key=TreeNode.sort_key,
            )
        return node

    def nest(self, node: TreeNode, level: int) -> None:
        """Below every leaf of ``node``: the facet that depends on it and keeps
        most bits there, if any (E5). Nodes are built one level beyond
        ``max_level`` so that a cut can be told from a tree that simply ends."""
        if node.children:
            for child in node.children:
                self.nest(child, level + 1)
            return
        if node.distinct < MIN_DEVELOP or level >= self.max_level + 1:
            return
        best: tuple[float, int, int, Facet] | None = None
        for position, facet in self.facets.items():
            if position in node.constraints:
                continue
            if self.dependence_on(node.members, position) < NU_MIN:
                continue
            texts = self.positions[position].texts
            members = [Member(texts[i], self.occurrences[i]) for i in node.members]
            inside = reread(members, self.positions[position].alphabet, facet.edge)
            if inside is None:
                continue
            candidate = (inside.absolute_gain(), -position, position, inside)
            if best is None or candidate[:2] > best[:2]:
                best = candidate
        if best is None:
            return
        _, _, position, inside = best
        node.children = self.nodes_of(inside, position, node.members, node.constraints)
        for child in node.children:
            self.nest(child, level + 1)


def _merge_single_children(nodes: list[TreeNode]) -> list[TreeNode]:
    """E5: a node whose only child covers 95% of it, in distinct values and in
    occurrences, merges with that child."""
    merged: list[TreeNode] = []
    for node in nodes:
        node.children = _merge_single_children(node.children)
        if len(node.children) == 1:
            [child] = node.children
            if (
                child.distinct >= FLATTEN * node.distinct
                and child.occurrences >= FLATTEN * node.occurrences
            ):
                merged.append(child)
                continue
        merged.append(node)
    return merged


def _cut(nodes: list[TreeNode], level: int, max_level: int) -> bool:
    """Drop the nodes deeper than ``max_level`` (``nodes`` being at ``level``);
    whether any went."""
    if level > max_level:
        cut = bool(nodes)
        nodes.clear()
        return cut
    cut = False
    for node in nodes:
        cut = _cut(node.children, level + 1, max_level) or cut
    return cut


def _positions_read(nodes: Sequence[TreeNode], found: set[int]) -> None:
    for node in nodes:
        found.add(node.position)
        _positions_read(node.children, found)


def develop(
    positions: Sequence[Position],
    occurrences: Sequence[int],
    *,
    groups: Sequence[Sequence[int]] | None = None,
    max_level: int,
    first_level: int = 2,
) -> Developed:
    """The content nodes of a pattern whose members have ``occurrences`` and the
    texts of ``positions`` (E5).

    Without ``groups`` the primary facet is the published one that saves most bits
    and its prefixes are the nodes at ``first_level``. With ``groups`` (the
    structures a composition gathers, each a list of member indexes) they are the
    primary nodes and only the facets that depend on a group are nested under it,
    in ``under``. A pattern of fewer than ``MIN_DEVELOP`` members is not developed.
    A node deeper than ``max_level`` (the pattern being level 1) is dropped and
    ``cut`` says so. The facets no node reads are in ``facets`` without a position
    in ``used``: the caller makes tables of them.
    """
    result = Developed(under=[[] for _ in groups or ()])
    if len(occurrences) < MIN_DEVELOP:
        return result
    result.facets = published_facets(positions, occurrences)
    if not result.facets:
        return result
    builder = _Builder(positions, occurrences, result.facets, max_level)
    everyone = list(range(len(occurrences)))
    if groups is None:
        position = max(result.facets, key=lambda index: (result.facets[index].absolute_gain(), -index))
        result.roots = builder.nodes_of(result.facets[position], position, everyone, {})
        for node in result.roots:
            builder.nest(node, first_level)
        result.roots = _merge_single_children(result.roots)
        # Read before the cut: a facet the depth left out is not a table either.
        _positions_read(result.roots, result.used)
        result.cut = _cut(result.roots, first_level, max_level)
        return result
    result.under = []
    for group in groups:
        pseudo = TreeNode(-1, "head", {}, list(group), sum(occurrences[i] for i in group), 0.0, 0.0, 0.0)
        builder.nest(pseudo, first_level)
        below = _merge_single_children(pseudo.children)
        _positions_read(below, result.used)
        result.cut = _cut(below, first_level + 1, max_level) or result.cut
        result.under.append(below)
    return result

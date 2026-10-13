# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""An independent calculator of the discovery score (algorithm E4 as decided on
12 October 2026: whole prefixes, b_f of the positions read, a threshold that
depends on the size; section 4 for the declared mode), used to check the
figures of the reference cases.

It is not the algorithm: it scores one content facet at a time, from counted
values, so that a figure of the design can be recomputed without the engine.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from tabalyst.scanner.patterninfer import tokenize

LETTER_BITS = math.log2(26)
DIGIT_BITS = math.log2(10)
ALNUM_BITS = math.log2(36)
# Starting values of the algorithm (section 3); kappa is now only the cost of a
# branch, the departure test filters chance.
KAPPA = 2.0
NU_MIN = 0.10
GUARD = 0.90
FLATTEN = 0.95
MIN_DEVELOP = 4
MAX_CHAIN = 3
# Below this p-value the next characters of a prefix are not chance (DEC-031).
# On the corpus, chance splits give 0.00097 and more, real ones 1.3e-14 and less:
# 1e-6 leaves three orders of margin on the side of chance.
ALPHA = 1e-6


def gain(x: float, total: float, bits: float, kappa: float = KAPPA) -> float:
    """Bits a branch of weight ``x`` saves in a node of weight ``total`` (E4)."""
    return x * (bits + math.log2(x / total)) - (bits + kappa)


@dataclass(frozen=True)
class Member:
    """A distinct value as a facet reads it: the text of one token and the
    occurrences of the value."""

    text: str
    occurrences: int


@dataclass
class Prefix:
    """A head (or tail) of a token: the characters it fixes, its weights, its
    gains on both channels against the weight of the facet, and whether it is
    kept. ``children`` are its kept longer heads."""

    text: str
    distinct: int
    occurrences: int
    gain_d: float
    gain_o: float
    retained: bool
    children: list[Prefix] = field(default_factory=list)


@dataclass
class Heads:
    """The heads (or tails) of a token scored as whole prefixes (DEC-029).

    ``constant`` is what every member shares (folded, DEC-026); ``nodes`` are
    the kept prefixes once the intermediates their children cover are
    flattened (E5).
    """

    constant: str
    distinct: int
    occurrences: int
    bits: float
    nodes: list[Prefix]

    def walk(self) -> list[Prefix]:
        """Every node, at any depth, sorted by text."""
        found: list[Prefix] = []
        stack = list(self.nodes)
        while stack:
            node = stack.pop()
            found.append(node)
            stack.extend(node.children)
        return sorted(found, key=lambda node: node.text)

    def leaves(self) -> list[Prefix]:
        return [node for node in self.walk() if not node.children]

    def free_bits(self) -> float:
        """``b_f`` of sigma: the bits of the positions the kept prefixes read,
        the longest of them (DEC-030)."""
        return max((len(node.text) for node in self.leaves()), default=0) * self.bits

    def gain_d(self) -> float:
        """The gains of the leaves on distinct values (an intermediate is
        described by its children)."""
        return sum(node.gain_d for node in self.leaves() if node.gain_d > 0)

    def gain_o(self) -> float:
        return sum(node.gain_o for node in self.leaves() if node.gain_o > 0)

    def sigma_d(self, bits: float | None = None) -> float:
        """sigma on distinct values: the gains over ``X * b_f``; ``bits``
        replaces ``b_f`` to read sigma another way."""
        bits = self.free_bits() if bits is None else bits
        return self.gain_d() / (self.distinct * bits) if bits else 0.0

    def sigma_o(self, bits: float | None = None) -> float:
        """sigma on occurrences."""
        bits = self.free_bits() if bits is None else bits
        return self.gain_o() / (self.occurrences * bits) if bits else 0.0

    def sigma(self, bits: float | None = None) -> float:
        return max(self.sigma_d(bits), self.sigma_o(bits))

    def published(self, nu_min: float = NU_MIN, bits: float | None = None) -> bool:
        return bool(self.nodes) and self.sigma(bits) >= nu_min


def departure(counts: Sequence[int], symbols: int) -> float:
    """The p-value of the counts of the next character under a prefix against a
    uniform choice among ``symbols`` characters (G-test, ``symbols - 1``
    degrees of freedom, Wilson-Hilferty approximation of the chi-squared tail).

    Small: the next character is not chance. The test grows with the counts,
    so it is the threshold that depends on the size (DEC-031).
    """
    total = sum(counts)
    if total == 0:
        return 1.0
    expected = total / symbols
    statistic = 2 * sum(count * math.log(count / expected) for count in counts if count)
    freedom = symbols - 1
    if statistic <= 0:
        return 1.0
    scale = 2 / (9 * freedom)
    z = ((statistic / freedom) ** (1 / 3) - (1 - scale)) / math.sqrt(scale)
    return 0.5 * math.erfc(z / math.sqrt(2))


def _char(text: str, position: int, from_right: bool) -> str | None:
    if position >= len(text):
        return None
    return text[-1 - position] if from_right else text[position]


def heads(
    members: Sequence[Member],
    bits: float,
    symbols: int,
    *,
    from_right: bool = False,
    depth: int = MAX_CHAIN,
    kappa: float = KAPPA,
    guard: float = GUARD,
    alpha: float = ALPHA,
) -> Heads:
    """Score the heads (or tails) of a token as whole prefixes of 1 to ``depth``
    characters (E4 as decided by DEC-029).

    The gain of a prefix of ``k`` characters is taken against the weight of the
    facet with ``k * bits`` of free part. A prefix is a candidate when the
    characters that follow its parent depart from chance (``departure`` below
    ``alpha``, on the channel being scored) and the parent has at least
    ``MIN_DEVELOP`` distinct values. It is kept when its gain on distinct values
    is positive, or its gain on occurrences is and no single value carries more
    than ``guard`` of them. A character every member of a prefix shares is
    folded into it. A prefix that is not kept still lets its longer prefixes
    compete (``31`` can be kept without ``3``).
    """
    total_d = len(members)
    total_o = sum(member.occurrences for member in members)
    constant = ""
    position = 0
    while position < depth:
        chars = {_char(member.text, position, from_right) for member in members}
        if len(chars) != 1 or None in chars:
            break
        constant += chars.pop() or ""
        position += 1

    def score(text: str, group: Sequence[Member]) -> tuple[float, float, int]:
        size = len(text) * bits
        x_d = len(group)
        x_o = sum(member.occurrences for member in group)
        heaviest = max(member.occurrences for member in group)
        return gain(x_d, total_d, size, kappa), gain(x_o, total_o, size, kappa), heaviest

    def grow(group: Sequence[Member], text: str, position: int) -> list[Prefix]:
        """The kept prefixes below ``text`` (the members ``group`` share it)."""
        if position >= depth or len(group) < MIN_DEVELOP:
            return []
        split: dict[str, list[Member]] = defaultdict(list)
        for member in group:
            char = _char(member.text, position, from_right)
            if char is not None:
                split[char].append(member)
        if len(split) == 1 and len(next(iter(split.values()))) == len(group):
            char = next(iter(split))
            return grow(group, text + char, position + 1)
        departs_d = departure([len(g) for g in split.values()], symbols) < alpha
        departs_o = (
            departure([sum(m.occurrences for m in g) for g in split.values()], symbols)
            < alpha
        )
        kept: list[Prefix] = []
        for char in sorted(split):
            subgroup = split[char]
            longer, after = _extend(subgroup, text + char, position + 1, depth, from_right)
            gain_d, gain_o, heaviest = score(longer, subgroup)
            x_o = sum(member.occurrences for member in subgroup)
            retained = (departs_d and gain_d > 0) or (
                departs_o and gain_o > 0 and heaviest <= guard * x_o
            )
            below = grow(subgroup, longer, after)
            if retained:
                kept.append(
                    Prefix(
                        _spell(longer, from_right),
                        len(subgroup),
                        x_o,
                        gain_d,
                        gain_o,
                        True,
                        below,
                    )
                )
            else:
                kept.extend(below)
        return kept

    nodes = _flatten(grow(members, constant, position))
    return Heads(_spell(constant, from_right), total_d, total_o, bits, nodes)


def _spell(text: str, from_right: bool) -> str:
    return text[::-1] if from_right else text


def _extend(
    group: Sequence[Member], text: str, position: int, depth: int, from_right: bool
) -> tuple[str, int]:
    """``text`` followed by the characters every member of ``group`` shares
    (``B`` always followed by ``C`` gives ``BC``: the constant is folded into the
    prefix and scored with it), and the position after them."""
    while position < depth:
        chars = {_char(member.text, position, from_right) for member in group}
        if len(chars) != 1 or None in chars:
            break
        text += chars.pop() or ""
        position += 1
    return text, position


def _flatten(nodes: list[Prefix]) -> list[Prefix]:
    """E5: an intermediate whose kept children cover ``FLATTEN`` of its
    distinct values and occurrences gives way to them."""
    flat: list[Prefix] = []
    for node in nodes:
        node.children = _flatten(node.children)
        if node.children and _covers(node.children, node):
            flat.extend(node.children)
        else:
            flat.append(node)
    return flat


def _covers(children: Sequence[Prefix], parent: Prefix) -> bool:
    distinct = sum(child.distinct for child in children)
    occurrences = sum(child.occurrences for child in children)
    return (
        distinct >= FLATTEN * parent.distinct
        and occurrences >= FLATTEN * parent.occurrences
    )


@dataclass(frozen=True)
class TokenBranch:
    """A whole token value scored as one block (the reading of the hand
    calculations of section 7)."""

    text: str
    distinct: int
    occurrences: int
    gain_d: float
    gain_o: float
    retained: bool


def token_reading(
    members: Sequence[Member],
    bits_per_char: float,
    *,
    kappa: float = KAPPA,
    guard: float = GUARD,
) -> tuple[list[TokenBranch], float, float]:
    """Score every whole value of a fixed-length token at once, with ``b_f`` the
    bits of the whole token; returns the branches and sigma on both channels."""
    groups: dict[str, list[Member]] = defaultdict(list)
    for member in members:
        groups[member.text].append(member)
    length = len(members[0].text)
    bits = bits_per_char * length
    total_d = len(members)
    total_o = sum(member.occurrences for member in members)
    branches = []
    for text in sorted(groups):
        group = groups[text]
        x_d = len(group)
        x_o = sum(member.occurrences for member in group)
        gain_d = gain(x_d, total_d, bits, kappa)
        gain_o = gain(x_o, total_o, bits, kappa)
        heaviest = max(member.occurrences for member in group)
        retained = gain_d > 0 or (gain_o > 0 and heaviest <= guard * x_o)
        branches.append(TokenBranch(text, x_d, x_o, gain_d, gain_o, retained))
    kept = [branch for branch in branches if branch.retained]
    sigma_d = sum(b.gain_d for b in kept if b.gain_d > 0) / (total_d * bits)
    sigma_o = sum(b.gain_o for b in kept if b.gain_o > 0) / (total_o * bits)
    return branches, sigma_d, sigma_o


def dependence(node: Mapping[str, int], family: Mapping[str, int]) -> float:
    """How much a facet depends on a node (E5): the divergence of its table in
    the node from the table of the family, over the entropy of the family table.
    0 for an independent facet."""
    node_total = sum(node.values())
    family_total = sum(family.values())
    entropy = -sum(
        count / family_total * math.log2(count / family_total)
        for count in family.values()
        if count
    )
    if not entropy:
        return 0.0
    divergence = sum(
        count
        / node_total
        * math.log2((count / node_total) / (family[value] / family_total))
        for value, count in node.items()
        if count
    )
    return divergence / entropy


@dataclass(frozen=True)
class DeclaredKey:
    """A key of the declared mode kept at one level."""

    key: str
    occurrences: int
    share: float


@dataclass(frozen=True)
class DeclaredLevel:
    """The keys kept at one level of the declared mode and the rest."""

    kept: tuple[DeclaredKey, ...]
    other_keys: int
    other_occurrences: int
    other_share: float
    # The rule that stopped the listing: ``floor``, ``occurrences``, ``budget``,
    # ``coverage`` or ``None`` when every key was kept.
    stopped_by: str | None


def declared_level(
    counts: Mapping[str, int],
    *,
    floor: float,
    budget: int,
    min_occurrences: int = 5,
    coverage: float = 0.95,
) -> DeclaredLevel:
    """The keys of one level of the declared mode (algorithm, section 4).

    Keys are sorted by decreasing share, then by text; a key is kept while its
    share reaches ``floor``, it has ``min_occurrences``, its rank is within
    ``budget`` and the cumulative coverage before it is under ``coverage``.
    """
    total = sum(counts.values())
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    kept: list[DeclaredKey] = []
    covered = 0
    stopped: str | None = None
    for key, count in ordered:
        share = count / total
        if covered / total >= coverage:
            stopped = "coverage"
        elif share < floor:
            stopped = "floor"
        elif count < min_occurrences:
            stopped = "occurrences"
        elif len(kept) >= budget:
            stopped = "budget"
        if stopped is not None:
            break
        kept.append(DeclaredKey(key, count, share))
        covered += count
    rest = ordered[len(kept) :]
    other = sum(count for _, count in rest)
    return DeclaredLevel(
        kept=tuple(kept),
        other_keys=len(rest),
        other_occurrences=other,
        other_share=other / total if total else 0.0,
        stopped_by=stopped,
    )


def token_members(pairs: Iterable[tuple[str, int]], index: int) -> list[Member]:
    """The members a facet reads: token ``index`` of each value, under the
    tokenization of the Scan (E1); a negative index counts from the end."""
    return [
        Member(tokenize(value)[index][3], occurrences) for value, occurrences in pairs
    ]

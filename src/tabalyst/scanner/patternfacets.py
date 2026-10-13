# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Scoring of the content facets of a pattern (design 18.12, E3 and E4): heads,
tails and whole tokens read as prefixes, their gain in bits on distinct values and
on occurrences, and the dependence of a facet on a node. It works on counted
texts and knows nothing of signatures or of the model.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass, field
from os.path import commonprefix
from typing import Literal, TypeVar

# Starting values of the algorithm (algorithm section 3). They belong to the
# version of the algorithm (``patterninfer.ALGORITHM_VERSION``): a change of one
# raises it.
KAPPA = 2.0
NU_MIN = 0.10
GUARD = 0.90
FLATTEN = 0.95
MIN_DEVELOP = 4
MAX_CHAIN = 3
# Below this p-value the characters that follow a prefix are not chance (DEC-031).
# On the corpus a chance split gives 0.00097 and more, a real one 1.3e-14 and less.
ALPHA = 1e-6
# A token longer than this is an identifier, not a category: its whole value is
# never a facet (no complete number is published, exposure of RC-11).
MAX_WHOLE_TOKEN = 4
# A token whose distinct contents reach this share of the distinct values is almost
# unique: its whole value is ignored (E3).
QUASI_UNIQUE = 0.5

Edge = Literal["head", "tail", "token"]
K = TypeVar("K", bound=Hashable)


@dataclass(frozen=True, slots=True)
class Alphabet:
    """The bits of one position of a class of characters and the number of
    characters it can take (the uniform law of the departure test)."""

    bits: float
    symbols: int


DIGITS = Alphabet(math.log2(10), 10)
LETTERS = Alphabet(math.log2(26), 26)


def gain(x: float, total: float, bits: float, kappa: float = KAPPA) -> float:
    """Bits a branch of weight ``x`` saves in a node of weight ``total`` when it
    fixes ``bits`` of free part (E4)."""
    return x * (bits + math.log2(x / total)) - (bits + kappa)


def departure(counts: Sequence[int], symbols: int) -> float:
    """The p-value of the counts of the next character under a prefix against a
    uniform choice among ``symbols`` characters (G-test, ``symbols - 1`` degrees
    of freedom, Wilson-Hilferty approximation of the chi-squared tail).

    Small when the next character is not chance. It grows with the counts, so it
    is the threshold that depends on the size (DEC-031).
    """
    total = sum(counts)
    if total == 0:
        return 1.0
    expected = total / symbols
    statistic = 2 * sum(count * math.log(count / expected) for count in counts if count)
    freedom = symbols - 1
    if statistic <= 0 or freedom <= 0:
        return 1.0
    scale = 2 / (9 * freedom)
    z = ((statistic / freedom) ** (1 / 3) - (1 - scale)) / math.sqrt(scale)
    return 0.5 * math.erfc(z / math.sqrt(2))


@dataclass(frozen=True, slots=True)
class Member:
    """A distinct value as a facet reads it: the text of one token and the
    occurrences of the value."""

    text: str
    occurrences: int


@dataclass(slots=True)
class Prefix:
    """A head, tail or whole token that a facet keeps: the characters it fixes,
    the members it holds (indexes into the members that were scored), its gains on
    both measures against the weight of the facet, and its kept longer prefixes."""

    text: str
    group: list[int]
    distinct: int
    occurrences: int
    gain_d: float
    gain_o: float
    children: list[Prefix] = field(default_factory=list)


@dataclass(slots=True)
class Facet:
    """One facet scored as whole prefixes (DEC-029): ``constant`` is what every
    member shares (folded, DEC-026) and ``nodes`` the kept prefixes once the
    intermediates their children cover are flattened (E5)."""

    edge: Edge
    constant: str
    distinct: int
    occurrences: int
    bits: float
    nodes: list[Prefix]
    _leaves: list[Prefix] | None = field(default=None, repr=False)

    def leaves(self) -> list[Prefix]:
        """The prefixes without a kept longer prefix, in reading order (found once:
        a facet is not changed after it is scored)."""
        if self._leaves is None:
            found: list[Prefix] = []
            stack = list(reversed(self.nodes))
            while stack:
                node = stack.pop()
                if node.children:
                    stack.extend(reversed(node.children))
                else:
                    found.append(node)
            self._leaves = found
        return self._leaves

    def free_bits(self) -> float:
        """``b_f`` of sigma: the bits of the positions the kept prefixes read, the
        longest of them (DEC-030)."""
        return max((len(node.text) for node in self.leaves()), default=0) * self.bits

    def gain_d(self) -> float:
        """The gains of the leaves on distinct values (an intermediate is
        described by its children)."""
        return sum(node.gain_d for node in self.leaves() if node.gain_d > 0)

    def gain_o(self) -> float:
        return sum(node.gain_o for node in self.leaves() if node.gain_o > 0)

    def sigma_d(self) -> float:
        bits = self.free_bits()
        return self.gain_d() / (self.distinct * bits) if bits else 0.0

    def sigma_o(self) -> float:
        bits = self.free_bits()
        return self.gain_o() / (self.occurrences * bits) if bits else 0.0

    def sigma(self) -> float:
        return max(self.sigma_d(), self.sigma_o())

    def published(self) -> bool:
        """Whether the facet is worth a node or a table (E4): it keeps something
        and saves at least ``NU_MIN`` of the bits it reads."""
        return bool(self.nodes) and self.sigma() >= NU_MIN

    def absolute_gain(self) -> float:
        """The size of the facet, to compare facets (the primary one has the
        largest), rounded for a stable comparison (AC-019)."""
        return round(max(self.gain_d(), self.gain_o()), 9)


def _splits(counts_d: list[int], counts_o: list[int], symbols: int, weighted: bool) -> tuple[bool, bool]:
    departs_d = departure(counts_d, symbols) < ALPHA
    if not weighted:
        return departs_d, departs_d
    return departs_d, departure(counts_o, symbols) < ALPHA


def heads(
    members: Sequence[Member],
    alphabet: Alphabet,
    *,
    from_right: bool = False,
    depth: int = MAX_CHAIN,
) -> Facet:
    """Score the heads (or the tails) of a token as whole prefixes of 1 to
    ``depth`` characters (E4 as decided by DEC-029 to DEC-031).

    The gain of a prefix of ``k`` characters is taken against the weight of the
    facet with ``k * bits`` of free part. A prefix is a candidate when the
    characters that follow its parent depart from chance on the measure being
    scored and the parent has at least ``MIN_DEVELOP`` distinct values. It is kept
    when its gain on distinct values is positive, or its gain on occurrences is
    and no single value carries more than ``GUARD`` of them. A character that every
    member of a prefix shares is folded into it. A prefix that is not kept still
    lets its longer prefixes compete (``31`` can be kept without ``3``).
    """
    view = [member.text[::-1] if from_right else member.text for member in members]
    occurrences = [member.occurrences for member in members]
    weighted = any(count != 1 for count in occurrences)
    total_d = len(members)
    total_o = sum(occurrences)
    bits = alphabet.bits
    constant = commonprefix(view)[:depth]

    def extend(group: list[int], text: str, position: int) -> tuple[str, int]:
        """``text`` followed by the characters every member of ``group`` shares
        (``B`` always followed by ``C`` gives ``BC``), and the position after."""
        if position >= depth:
            return text, position
        shared = commonprefix([view[index][position:depth] for index in group])
        return text + shared, position + len(shared)

    def grow(group: list[int], text: str, position: int) -> list[Prefix]:
        if position >= depth or len(group) < MIN_DEVELOP:
            return []
        split: dict[str, list[int]] = defaultdict(list)
        for index in group:
            word = view[index]
            if position < len(word):
                split[word[position]].append(index)
        if len(split) == 1 and len(next(iter(split.values()))) == len(group):
            char = next(iter(split))
            return grow(group, text + char, position + 1)
        weights = {char: sum(occurrences[index] for index in part) for char, part in split.items()}
        departs_d, departs_o = _splits(
            [len(part) for part in split.values()],
            list(weights.values()),
            alphabet.symbols,
            weighted,
        )
        kept: list[Prefix] = []
        for char in sorted(split):
            subgroup = split[char]
            longer, after = extend(subgroup, text + char, position + 1)
            size = len(longer) * bits
            x_o = weights[char]
            gain_d = gain(len(subgroup), total_d, size)
            gain_o = gain(x_o, total_o, size) if weighted else gain_d
            heaviest = max(occurrences[index] for index in subgroup)
            retained = (departs_d and gain_d > 0) or (
                departs_o and gain_o > 0 and heaviest <= GUARD * x_o
            )
            below = grow(subgroup, longer, after)
            if retained:
                kept.append(
                    Prefix(
                        longer[::-1] if from_right else longer,
                        subgroup,
                        len(subgroup),
                        x_o,
                        gain_d,
                        gain_o,
                        below,
                    )
                )
            else:
                kept.extend(below)
        return kept

    nodes = _flatten(grow(list(range(total_d)), constant, len(constant)))
    return Facet(
        "tail" if from_right else "head",
        constant[::-1] if from_right else constant,
        total_d,
        total_o,
        bits,
        nodes,
    )


def _flatten(nodes: list[Prefix]) -> list[Prefix]:
    """E5: an intermediate whose kept children cover ``FLATTEN`` of its distinct
    values and of its occurrences gives way to them."""
    flat: list[Prefix] = []
    for node in nodes:
        node.children = _flatten(node.children)
        if node.children and _covers(node.children, node):
            flat.extend(node.children)
        else:
            flat.append(node)
    return flat


def _covers(children: Sequence[Prefix], parent: Prefix) -> bool:
    return (
        sum(child.distinct for child in children) >= FLATTEN * parent.distinct
        and sum(child.occurrences for child in children) >= FLATTEN * parent.occurrences
    )


def beyond_chance(x: float, total: float, symbols: int) -> bool:
    """Whether a value held by ``x`` of ``total`` draws is beyond what a uniform
    choice among ``symbols`` values gives (DEC-031 for a value of many characters).

    A G-test over all the possible values has too few expected counts to be valid
    when ``symbols`` is large (four digits make 10,000): the value is tested on its
    own with the Chernoff bound of the binomial tail, corrected by ``symbols`` for
    the values that could have stood out instead.
    """
    share = x / total
    chance = 1 / symbols
    if share <= chance:
        return False
    divergence = share * math.log(share / chance)
    if share < 1:
        divergence += (1 - share) * math.log((1 - share) / (1 - chance))
    return total * divergence > math.log(symbols) - math.log(ALPHA)


def whole_token(members: Sequence[Member], alphabet: Alphabet) -> Facet | None:
    """Score every whole value of a short token at once, ``b_f`` being the bits of
    the token (the reading of the year of RC-05); ``None`` when the token is too
    long to be a category (``MAX_WHOLE_TOKEN``), is constant or is almost unique
    (``QUASI_UNIQUE``). A value is kept like a prefix, when it is beyond chance among
    all the tokens of that length (``beyond_chance``)."""
    groups: dict[str, list[int]] = defaultdict(list)
    for index, member in enumerate(members):
        groups[member.text].append(index)
    longest = max(len(text) for text in groups)
    total_d = len(members)
    if longest > MAX_WHOLE_TOKEN or len(groups) < 2 or len(groups) >= QUASI_UNIQUE * total_d:
        return None
    occurrences = [member.occurrences for member in members]
    total_o = sum(occurrences)
    symbols = alphabet.symbols**longest
    kept: list[Prefix] = []
    for text in sorted(groups):
        part = groups[text]
        size = len(text) * alphabet.bits
        x_o = sum(occurrences[index] for index in part)
        gain_d = gain(len(part), total_d, size)
        gain_o = gain(x_o, total_o, size)
        heaviest = max(occurrences[index] for index in part)
        if (gain_d > 0 and beyond_chance(len(part), total_d, symbols)) or (
            gain_o > 0
            and heaviest <= GUARD * x_o
            and beyond_chance(x_o, total_o, symbols)
        ):
            kept.append(Prefix(text, part, len(part), x_o, gain_d, gain_o))
    return Facet("token", "", total_d, total_o, alphabet.bits, kept)


def best_facet(members: Sequence[Member], alphabet: Alphabet) -> Facet | None:
    """The published facet of a token that saves most bits among its head, its tail
    and its whole value; the head wins a tie. ``None`` when none is published.

    A tail is read only on a token longer than the chain (``MAX_CHAIN``): a shorter
    one is read in full by its head, and reading it from the other end would only
    find chance in the last letter of a code (RC-12).
    """
    found: list[Facet] = []
    head = heads(members, alphabet)
    if head.published():
        found.append(head)
    if any(len(member.text) > MAX_CHAIN for member in members):
        tail = heads(members, alphabet, from_right=True)
        if tail.published():
            found.append(tail)
    whole = whole_token(members, alphabet)
    if whole is not None and whole.published():
        found.append(whole)
    if not found:
        return None
    return max(found, key=lambda facet: facet.absolute_gain())


def reread(
    members: Sequence[Member], alphabet: Alphabet, edge: Edge
) -> Facet | None:
    """The facet of the same kind (head, tail or whole value) over other members,
    when it is published there: how a facet is read inside a node."""
    if edge == "token":
        facet = whole_token(members, alphabet)
    else:
        facet = heads(members, alphabet, from_right=edge == "tail")
    return facet if facet is not None and facet.published() else None


def dependence(node: Mapping[K, int], family: Mapping[K, int]) -> float:
    """How much a facet depends on a node (E5): the divergence of its table in the
    node from the table of the whole, over the entropy of the whole. 0 for an
    independent facet."""
    node_total = sum(node.values())
    family_total = sum(family.values())
    entropy = -sum(
        count / family_total * math.log2(count / family_total)
        for count in family.values()
        if count
    )
    if not entropy or not node_total:
        return 0.0
    divergence = sum(
        count
        / node_total
        * math.log2((count / node_total) / (family[value] / family_total))
        for value, count in node.items()
        if count
    )
    return divergence / entropy

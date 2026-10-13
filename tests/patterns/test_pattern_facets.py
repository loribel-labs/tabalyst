# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The engine's scoring of the content facets (``patternfacets``) and its tree
(``patterntree``) against the independent calculator ``pattern_bits.py``, and the
rules of the tree that the reference corpus does not reach."""

from __future__ import annotations

import pytest
from pattern_bits import DIGIT_BITS, LETTER_BITS, token_members
from pattern_bits import departure as oracle_departure
from pattern_bits import dependence as oracle_dependence
from pattern_bits import heads as oracle_heads
from pattern_corpus import field
from pattern_tree import lengths

from tabalyst.scanner import patternfacets
from tabalyst.scanner.patternfacets import (
    DIGITS,
    LETTERS,
    MAX_WHOLE_TOKEN,
    Member,
    best_facet,
    whole_token,
)
from tabalyst.scanner.patterntree import Position, develop

pytestmark = pytest.mark.pattern_lot("P4")


def _members(field_id: str, index: int, keep=lambda value: True) -> list[Member]:
    pairs = [(v, n) for v, n in field(field_id).pairs if keep(v)]
    return [Member(m.text, m.occurrences) for m in token_members(pairs, index - 1)]


def _oracle_members(members: list[Member]):
    from pattern_bits import Member as OracleMember

    return [OracleMember(m.text, m.occurrences) for m in members]


CASES = [
    ("RC-03/scaled", 1, lambda v: True, LETTERS, (LETTER_BITS, 26)),
    ("RC-07/plates", 1, lambda v: lengths(v) == (2, 4), LETTERS, (LETTER_BITS, 26)),
    ("RC-08/plates", 1, lambda v: "-" in v, LETTERS, (LETTER_BITS, 26)),
    ("RC-10/nine_30", 1, lambda v: True, DIGITS, (DIGIT_BITS, 10)),
    ("RC-11/cards", 1, lambda v: len(v) == 16, DIGITS, (DIGIT_BITS, 10)),
    ("RC-12/codes", 1, lambda v: len(v) == 3, LETTERS, (LETTER_BITS, 26)),
    ("RC-13/identifiers", 1, lambda v: True, LETTERS, (LETTER_BITS, 26)),
    ("RC-16/lots", 3, lambda v: True, DIGITS, (DIGIT_BITS, 10)),
    ("RC-16/lots", 5, lambda v: True, DIGITS, (DIGIT_BITS, 10)),
]


@pytest.mark.parametrize("from_right", [False, True])
@pytest.mark.parametrize("case", CASES, ids=lambda case: f"{case[0]}-{case[1]}")
def test_heads_and_tails_give_the_figures_of_the_independent_calculator(case, from_right):
    field_id, index, keep, alphabet, oracle_alphabet = case
    members = _members(field_id, index, keep)
    mine = patternfacets.heads(members, alphabet, from_right=from_right)
    theirs = oracle_heads(_oracle_members(members), *oracle_alphabet, from_right=from_right)
    assert mine.constant == theirs.constant
    assert [(p.text, p.distinct, p.occurrences) for p in _walk(mine.nodes)] == [
        (p.text, p.distinct, p.occurrences) for p in _walk(theirs.nodes)
    ]
    assert [round(p.gain_d, 6) for p in _walk(mine.nodes)] == [
        round(p.gain_d, 6) for p in _walk(theirs.nodes)
    ]
    assert round(mine.sigma(), 9) == round(theirs.sigma(), 9)
    assert mine.published() == theirs.published()


def _walk(nodes):
    """The nodes of a facet in reading order, each followed by its children."""
    found = []
    for node in sorted(nodes, key=lambda node: node.text):
        found.append(node)
        found.extend(_walk(node.children))
    return found


def test_the_departure_test_and_the_dependence_are_those_of_the_calculator():
    for counts, symbols in (([4, 1], 26), ([400, 100, 100], 10), ([100] * 10, 10)):
        assert patternfacets.departure(counts, symbols) == oracle_departure(counts, symbols)
    node, whole = {"a": 150, "b": 50}, {"a": 200, "b": 200}
    assert patternfacets.dependence(node, whole) == oracle_dependence(node, whole)


def test_a_whole_token_is_scored_with_b_f_of_the_token():
    year = whole_token(_members("RC-05/invoices", 3), DIGITS)
    assert year is not None and year.published()
    assert [(leaf.text, leaf.distinct) for leaf in year.leaves()] == [("2025", 200), ("2026", 200)]
    assert year.free_bits() == pytest.approx(4 * DIGIT_BITS)
    assert round(year.sigma(), 2) == 0.92


def test_a_whole_token_is_ignored_when_long_constant_or_almost_unique():
    assert whole_token(_members("RC-13/identifiers", 3), DIGITS) is None  # unique numbers
    assert whole_token(_members("RC-12/codes", 1, lambda v: len(v) == 3), LETTERS) is None
    assert MAX_WHOLE_TOKEN == 4
    cards = _members("RC-11/cards", 1, lambda v: len(v) == 16)
    assert whole_token(cards, DIGITS) is None  # 16 digits: never a category
    constant = [Member("AB", 1)] * 8
    assert whole_token(constant, LETTERS) is None


def test_a_whole_token_drawn_evenly_over_every_possible_value_is_not_kept():
    # 1,000 values over the 100 two-digit tokens: the counts do not depart from the
    # uniform law, whatever the few that are above average say.
    members = [Member(f"{n % 100:02d}", 1) for n in range(1_000)]
    members[0:22] = [Member("07", 1)] * 22  # twice the others: chance does that
    facet = whole_token(members, DIGITS)
    assert facet is not None and not facet.published()


def test_a_tail_is_read_only_on_a_token_longer_than_the_chain():
    # The last letter of a code is chance dressed as a facet (RC-12): the head
    # chain already reads a token of up to three characters in full.
    codes = _members("RC-12/codes", 1, lambda v: len(v) == 2)
    assert patternfacets.heads(codes, LETTERS, from_right=True).published()
    facet = best_facet(codes, LETTERS)
    assert facet is None or facet.edge != "tail"
    numbers = _members("RC-16/lots", 5)
    facet = best_facet(numbers, DIGITS)
    assert facet is not None and facet.edge == "tail"


def test_the_primary_facet_is_the_one_with_the_largest_gain():
    values = field("RC-16/lots").values()
    columns = {
        position: [v.split("-")[position] for v in values] for position in (0, 1, 2, 3)
    }
    occurrences = [1] * len(values)
    alphabets = {0: LETTERS, 1: DIGITS, 2: DIGITS, 3: LETTERS}
    positions = [Position(p, alphabets[p], columns[p]) for p in (0, 1, 2, 3)]
    developed = develop(positions, occurrences, max_level=3)
    assert {node.constraints[0][1] for node in developed.roots} == {"LOT", "SER"}
    assert developed.used == {0}
    assert {1, 3} <= set(developed.facets) and 2 in developed.facets


def test_a_node_with_one_child_that_covers_it_merges_with_the_child():
    # Prefix A is followed by K in 97 % of its values (and B, Z a few times); the
    # year is fixed given the prefix K, so the single child covers its parent.
    texts = ["AK"] * 97 + ["AB", "AZ", "AY"]
    positions = [Position(0, LETTERS, texts)]
    developed = develop(positions, [1] * 100, max_level=3)
    assert [node.constraints[0][1] for node in developed.roots] == ["AK"]
    assert developed.roots[0].children == []


def test_a_node_deeper_than_the_depth_is_dropped_and_says_so():
    values = field("RC-05/invoices_dependent").values()
    parts = [v.split("-") for v in values]
    positions = [
        Position(0, LETTERS, [p[0] for p in parts]),
        Position(1, DIGITS, [p[1] for p in parts]),
    ]
    deep = develop(positions, [1] * len(values), max_level=3)
    assert [len(node.children) for node in deep.roots] == [2, 2] and not deep.cut
    shallow = develop(positions, [1] * len(values), max_level=2)
    assert all(node.children == [] for node in shallow.roots) and shallow.cut
    none = develop(positions, [1] * len(values), max_level=1)
    assert none.roots == [] and none.cut

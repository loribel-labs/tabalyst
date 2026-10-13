# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The expectations of the reference corpus agree with its values, and the
comparison the engine tests use finds what it must."""

from collections import Counter
from dataclasses import replace

import pytest
from pattern_bits import declared_level
from pattern_corpus import corpus, field
from pattern_expected import (
    DECLARED,
    EXPECTED,
    email_keys,
    expected,
    phone_keys,
    postal_keys,
)
from pattern_tree import Declared, Key, SeenField, SeenNode, compare, ideal

KEYS = {"email": email_keys, "phone": phone_keys, "postal_code": postal_keys}


def test_every_field_has_an_expectation():
    informative = {item.id for item in corpus() if item.mode == "informative"}
    declared = {item.id for item in corpus() if item.mode == "declared"}
    # The hyphenated ISBN needs too many formats of fixed length to be discovered
    # (DEC-034): its eligibility sets it aside and no tree is expected.
    assert {item.field for item in EXPECTED} >= informative - {"RC-12/isbn"}
    assert {item.field for item in DECLARED} == declared


@pytest.mark.parametrize("expectation", EXPECTED, ids=lambda item: item.field)
def test_a_perfect_discovery_meets_the_expectation(expectation):
    # The counts written in the expectation are those of the generated values.
    source = field(expectation.field)
    assert compare(expectation, ideal(expectation, source.pairs), source.pairs) == []


def _perfect(field_id: str) -> tuple[SeenField, tuple]:
    source = field(field_id)
    return ideal(expected(field_id), source.pairs), source.pairs


def test_comparison_reports_a_missing_node():
    seen, pairs = _perfect("RC-03/scaled")
    family = seen.families[0]
    damaged = replace(seen, families=(replace(family, nodes=family.nodes[1:]),))
    problems = compare(expected("RC-03/scaled"), damaged, pairs)
    assert problems == ["AA-9999: node head:1:AB not found"]


def test_comparison_reports_a_node_the_case_does_not_allow():
    seen, pairs = _perfect("RC-17/noise")
    family = seen.families[0]
    chance = SeenNode("head:1:A", frozenset(v for v in family.members if v[0] == "A"))
    damaged = replace(seen, families=(replace(family, nodes=(chance,)),))
    problems = compare(expected("RC-17/noise"), damaged, pairs)
    assert problems == ["family AA-9999: unexpected node head:1:A"]


def test_comparison_accepts_an_optional_node_and_a_node_its_rules_allow():
    seen, pairs = _perfect("RC-13/identifiers")
    strict = expected("RC-13/identifiers")
    family = strict.families[0]
    loose = replace(
        strict,
        families=(replace(family, nodes=family.nodes[:2], optional=family.nodes[2:]),),
    )
    assert compare(loose, seen, pairs) == []
    observed = seen.families[0]
    without = replace(seen, families=(replace(observed, nodes=observed.nodes[:2]),))
    assert compare(loose, without, pairs) == []
    seen, pairs = _perfect("RC-12/codes")
    family = seen.families[0]
    two_letters = family.nodes[0]
    head = SeenNode(
        "head:1:Z", frozenset(v for v in two_letters.members if v[0] == "Z")
    )
    nested = replace(two_letters, children=(head,))
    allowed = replace(seen, families=(replace(family, nodes=(nested, family.nodes[1])),))
    assert compare(expected("RC-12/codes"), allowed, pairs) == []


def test_comparison_reports_a_node_that_fixes_a_whole_code():
    seen, pairs = _perfect("RC-12/codes")
    family = seen.families[0]
    two_letters = family.nodes[0]
    code = SeenNode("token:1:RZ", frozenset({"RZ"}))
    nested = replace(two_letters, children=(code,))
    damaged = replace(seen, families=(replace(family, nodes=(nested, family.nodes[1])),))
    problems = compare(expected("RC-12/codes"), damaged, pairs)
    assert problems == ["family AA / AAA: forbidden node token:1:RZ"]


def test_comparison_reports_overlapping_siblings_and_a_node_equal_to_its_parent():
    seen, pairs = _perfect("RC-14/prefixes")
    family = seen.families[0]
    both = SeenNode("head:1:A", family.nodes[0].members | family.nodes[1].members)
    whole = SeenNode("everything", family.members)
    damaged = replace(seen, families=(replace(family, nodes=family.nodes + (both, whole)),))
    problems = compare(expected("RC-14/prefixes"), damaged, pairs)
    assert "AA-9999 > head:1:A: overlaps a sibling" in problems
    assert "AA-9999 > everything: not a strict part of its parent" in problems


def test_comparison_reports_a_missing_table_cell_and_a_merged_family():
    seen, pairs = _perfect("RC-16/lots")
    family = seen.families[0]
    table = family.tables[0]
    tables = (replace(table, cells=table.cells[:1]),) + family.tables[1:]
    damaged = replace(seen, families=(replace(family, tables=tables),))
    problems = compare(expected("RC-16/lots"), damaged, pairs)
    assert problems == ["family AAA-99-999999-AA: table token:3 not found"]
    seen, pairs = _perfect("RC-06/invoices")
    merged = replace(
        seen.families[0], members=seen.families[0].members | seen.families[1].members
    )
    problems = compare(expected("RC-06/invoices"), replace(seen, families=(merged,)), pairs)
    assert "family 'INV'-999 / 'INV'-9999 / 'INV'-99999: not found" in problems


def test_toys_only_check_their_families():
    seen, pairs = _perfect("RC-03/toy")
    family = seen.families[0]
    chance = SeenNode("head:1:A", frozenset(v for v in family.members if v[0] == "A"))
    noisy = replace(seen, families=(replace(family, nodes=(chance,)),))
    assert compare(expected("RC-03/toy"), noisy, pairs) == []


@pytest.mark.parametrize("expectation", DECLARED, ids=lambda item: item.field)
def test_declared_keys_follow_the_rules_of_section_4(expectation):
    # An independent count of the generated values, run through the rules of
    # the declared mode (floors 0.5 % and 2 %, 5 occurrences, budgets 32 and 16,
    # 95 % coverage), gives the pinned expectation.
    source = field(expectation.field)
    first: Counter[str] = Counter()
    second: dict[str, Counter[str]] = {}
    for value, count in source.pairs:
        key, child = KEYS[expectation.detector](value)
        first[key] += count
        second.setdefault(key, Counter())[child] += count
    level = declared_level(first, floor=0.005, budget=32)
    keys = []
    for kept in level.kept:
        below = declared_level(second[kept.key], floor=0.02, budget=16)
        keys.append(
            Key(
                kept.key,
                kept.occurrences,
                tuple(Key(child.key, child.occurrences) for child in below.kept),
                other=(below.other_keys, below.other_occurrences),
            )
        )
    computed = Declared(
        expectation.field,
        expectation.detector,
        tuple(keys),
        other=(level.other_keys, level.other_occurrences),
        masked=source.masked,
    )
    assert computed == expectation

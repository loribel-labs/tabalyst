# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The figures of the algorithm (sections 7 and 8), recomputed by an independent
calculator under the reading decided on 12 October 2026: whole prefixes
(DEC-029), ``b_f`` of the positions the kept prefixes read (DEC-030), and a
departure test from chance whose threshold grows with the size (DEC-031).

Each figure of the hand calculations is confirmed or corrected here. The
rejected reading, position by position, halved the gains and lost AZ (RC-13)
and 31 (RC-16).
"""

import pytest
from pattern_bits import (
    ALPHA,
    DIGIT_BITS,
    LETTER_BITS,
    Member,
    departure,
    dependence,
    gain,
    heads,
    token_members,
    token_reading,
)
from pattern_corpus import field
from pattern_tree import shape, structure, token

LETTERS = (LETTER_BITS, 26)
DIGITS = (DIGIT_BITS, 10)


def _members(*groups: tuple[str, int, int]) -> list[Member]:
    """``count`` distinct values of ``text``, each with ``occurrences``."""
    return [
        Member(text, occurrences)
        for text, count, occurrences in groups
        for _ in range(count)
    ]


def _token(field_id: str, index: int, keep=lambda value: True) -> list[Member]:
    pairs = ((v, n) for v, n in field(field_id).pairs if keep(v))
    return token_members(pairs, index - 1)


def _nodes(scored) -> list[tuple[str, int]]:
    return [(node.text, node.distinct) for node in scored.walk()]


# The formula ------------------------------------------------------------------------


def test_gain_is_the_bits_saved_minus_the_cost_of_the_branch():
    # x (b + log2(x / X)) - (b + kappa): 50 values of 500 on two letters.
    assert gain(50, 500, 2 * LETTER_BITS) == pytest.approx(292.5, abs=0.1)
    # A branch at the level of chance saves nothing and pays its cost.
    assert gain(100, 1_000, DIGIT_BITS) == pytest.approx(-(DIGIT_BITS + 2))


def test_departure_grows_with_the_size_of_the_counts():
    # The same proportions (40 % against 10 %) say more on more values.
    assert departure([4] + [1] * 6, 10) > ALPHA
    assert departure([400] + [100] * 6, 10) < ALPHA
    assert departure([100] * 10, 10) == 1.0


# Section 7, case by case -------------------------------------------------------------


def test_rc03_ten_prefixes_with_sigma_062():
    prefixes = ("AK", "AB", "AZ", "BC", "CD", "DE", "KM", "PQ", "RT", "ZX")
    scored = heads(_members(*((p, 50, 1) for p in prefixes)), *LETTERS)
    assert round(scored.sigma(), 2) == 0.62  # confirmed
    assert {round(node.gain_d, 1) for node in scored.walk()} == {292.5}
    # The intermediate A is flattened; B always followed by C gives BC.
    assert _nodes(scored) == [(p, 50) for p in sorted(prefixes)]


def test_rc03_toy_is_too_small_to_find_anything():
    members = _members(("AK", 2, 1), ("AB", 1, 1), ("AZ", 1, 1), ("BC", 1, 1))
    # Corrected: the hand calculation gave AX-9999 alone with sigma 0.36; four
    # A of five depart from chance with p = 0.33 only. Algorithm 9.1: a toy
    # does not conclude.
    assert round(departure([4, 1], 26), 2) == 0.33
    assert heads(members, *LETTERS).nodes == []


def test_rc04_gain_of_187_000_bits_and_the_guard():
    members = _members(
        ("AK", 1, 12_000), ("AK", 1, 8_000), ("AB", 1, 500), ("AZ", 1, 100)
    )
    scored = heads(members, *LETTERS)
    assert scored.constant == "A"
    [ak] = scored.walk()
    assert ak.text == "AK" and round(ak.gain_o) == 187_153  # confirmed
    assert round(scored.sigma_o(), 2) == 0.97  # confirmed
    # Two values of four do not depart from chance on distinct values: only
    # the occurrences keep AK. AB and AZ carry all their occurrences on one
    # value: the 90 % guard refuses them although their gain is positive.
    assert departure([2, 1, 1], 26) > ALPHA
    assert gain(500, 20_600, 2 * LETTER_BITS) > 0
    assert round(20_000 / 20_600, 3) == 0.971


def test_ac007_gain_9367_bits_and_sigma_0996():
    scored = heads(_members(("AK", 998, 1), ("BC", 1, 1), ("ZQ", 1, 1)), *LETTERS)
    assert _nodes(scored) == [("AK", 998)]
    assert round(scored.gain_d()) == 9_368  # 9 367 in the hand calculation
    assert round(scored.sigma(), 3) == 0.996  # confirmed


def test_rc10_sigma_014_with_b_f_of_one_digit():
    members = _members(("9", 300, 1), *((str(d), 100, 1) for d in range(1, 8)))
    scored = heads(members, *DIGITS)
    assert _nodes(scored) == [("9", 300)]
    assert scored.free_bits() == DIGIT_BITS
    assert round(scored.sigma(), 4) == 0.1415  # confirmed
    # A 9 in 10 % is chance: confirmed, nothing departs.
    uniform = _members(*((str(d), 100, 1) for d in range(10)))
    assert heads(uniform, *DIGITS).nodes == []


def test_rc10_generated_values_keep_the_nine_and_nothing_below_it():
    scored = heads(_token("RC-10/nine_30", 1), *DIGITS)
    assert _nodes(scored) == [("9", 300)]
    assert scored.published()


def test_rc13_keeps_ak_ab_and_az_with_sigma_096():
    others = ("BC", "CD", "DE", "EF", "FG", "GH", "HJ", "JK", "KL", "LM")
    members = _members(
        ("AK", 9_500, 1), ("AB", 400, 1), ("AZ", 90, 1), *((p, 1, 1) for p in others)
    )
    scored = heads(members, *LETTERS)
    assert round(scored.sigma(), 2) == 0.96  # confirmed
    assert _nodes(scored) == [("AB", 400), ("AK", 9_500), ("AZ", 90)]  # confirmed
    assert round(next(n for n in scored.walk() if n.text == "AZ").gain_d, 1) == 223.1


def test_rc14_gain_309_bits_per_prefix():
    prefixes = ("AK", "BC", "CD", "DE", "EF", "FG", "GH", "HJ")
    scored = heads(_members(*((p, 50, 1) for p in prefixes)), *LETTERS)
    assert {round(node.gain_d, 1) for node in scored.walk()} == {308.6}  # confirmed
    assert len(scored.nodes) == 8


def test_rc05_prefix_is_primary_and_the_year_a_table_unless_it_depends():
    prefix = heads(_token("RC-05/invoices", 1), *LETTERS)
    branches, _, _ = token_reading(_token("RC-05/invoices", 3), DIGIT_BITS)
    year = sum(branch.gain_d for branch in branches if branch.retained)
    assert prefix.gain_d() > year  # 5 208 > 4 885 bits: confirmed
    assert dependence({"2025": 100, "2026": 100}, {"2025": 200, "2026": 200}) == 0
    # INV with 2025 at 75 %: dependence 0.19 >= nu_min, the year is nested.
    nested = dependence({"2025": 150, "2026": 50}, {"2025": 200, "2026": 200})
    assert round(nested, 2) == 0.19


def test_rc05_references_make_two_families_not_three():
    # Corrected: CUS-000123 and SUP-000123 share the structure UP-D.
    structures = {structure(v) for v in field("RC-05/references").values()}
    assert structures == {"UP-D", "UP-UP-D"}


def test_rc07_constant_c_is_folded_and_cc_cd_are_nodes():
    scored = heads(_token("RC-07/plates", 1, lambda v: shape(v) == (2, 4)), *LETTERS)
    assert scored.constant == "C"
    assert _nodes(scored) == [("CC", 60), ("CD", 40)]
    scored = heads(
        _token("RC-07/plates", 1, lambda v: shape(v) == (2, 1, 3)), *LETTERS
    )
    assert _nodes(scored) == [("VA", 90), ("VE", 60)]


def test_rc08_rc09_and_rc17_uniform_facets_stay_unpublished():
    for members, kind in (
        (_token("RC-08/plates", 1, lambda v: "-" in v), LETTERS),
        (_token("RC-08/plates", 5, lambda v: "-" in v), LETTERS),
        (_token("RC-09/permits", 1), LETTERS),
        (_token("RC-09/permits", 2), DIGITS),
        (_token("RC-17/noise", 1), LETTERS),
        (_token("RC-17/noise", 3), DIGITS),
    ):
        for from_right in (False, True):
            scored = heads(members, *kind, from_right=from_right)
            assert scored.sigma() < 0.04  # confirmed: far below nu_min
            assert not scored.published()
    # French plates skip I, O and U: the letters depart from chance, but each
    # saves little and the facet stays unpublished.
    french = heads(_token("RC-08/plates", 1, lambda v: "-" in v), *LETTERS)
    assert french.nodes and round(french.sigma(), 3) == 0.027


def test_rc11_heads_are_4_and_51_to_55_and_never_6():
    sixteen = heads(_token("RC-11/cards", 1, lambda v: len(v) == 16), *DIGITS)
    assert _nodes(sixteen) == [("4", 400)] + [(f"5{d}", 64) for d in range(1, 6)]
    fifteen = heads(_token("RC-11/cards", 1, lambda v: len(v) == 15), *DIGITS)
    assert fifteen.constant == "3"
    assert _nodes(fifteen) == [("34", 75), ("37", 75)]
    fourteen = heads(_token("RC-11/cards", 1, lambda v: len(v) == 14), *DIGITS)
    assert fourteen.constant == "36" and fourteen.nodes == []


def test_rc12_isbn_prefix_folds_97_and_groups_depend_on_it():
    prefix = heads(_token("RC-12/isbn", 1), *DIGITS)
    assert prefix.constant == "97"
    assert _nodes(prefix) == [("978", 700), ("979", 300)]
    groups = heads(_token("RC-12/isbn", 3, lambda v: v.startswith("979")), *DIGITS)
    assert _nodes(groups) == [("10", 200), ("8", 100)]


def test_rc12_codes_publish_at_most_first_letters_by_occurrences():
    two = [Member(v, n) for v, n in field("RC-12/codes").pairs if len(v) == 2]
    three = [Member(v, n) for v, n in field("RC-12/codes").pairs if len(v) == 3]
    assert not heads(two, *LETTERS).published()  # sigma 0.09
    scored = heads(three, *LETTERS)
    # Zipf weights: F carries 80 occurrences on three codes (sigma 0.14).
    assert scored.published() and {len(node.text) for node in scored.walk()} == {1}


# Section 8 -------------------------------------------------------------------------------


def test_rc16_prefix_is_the_primary_facet():
    gains = {
        "prefix": heads(_token("RC-16/lots", 1), *LETTERS).gain_d(),
        "middle": heads(_token("RC-16/lots", 3), *DIGITS).gain_d(),
        "suffix": heads(_token("RC-16/lots", 7), *LETTERS).gain_d(),
        "tail": heads(_token("RC-16/lots", 5), *DIGITS, from_right=True).gain_d(),
    }
    assert max(gains, key=gains.get) == "prefix"
    assert round(gains["prefix"], 1) == 13_187.8


def test_rc16_middle_keeps_31_and_the_tail_00_weighs_31_percent():
    middle = heads(_token("RC-16/lots", 3), *DIGITS)
    # 31 is kept although 3 alone is at the level of chance (confirmed).
    assert _nodes(middle) == [("07", 600), ("12", 300), ("31", 100)]
    tail = heads(_token("RC-16/lots", 5), *DIGITS, from_right=True)
    found = dict(_nodes(tail))
    # Confirmed: 30 % forced plus chance among the other 70 %, 30.6 % here,
    # under an intermediate 0 (37 %). The tail is a table of the family.
    assert found["00"] == 306 and found["0"] == 370
    assert tail.published()


def test_departure_threshold_separates_chance_from_real_splits():
    # DEC-031: on uniform facets the smallest p-value is 0.00097 (third digit
    # of RC-09; the first two characters are checked here), on real prefixes
    # the largest is 1.3e-14.
    chance = min(
        _smallest_departure(members, kind, from_right)
        for members, kind in (
            (_token("RC-09/permits", 1), LETTERS),
            (_token("RC-09/permits", 2), DIGITS),
            (_token("RC-17/noise", 1), LETTERS),
            (_token("RC-17/noise", 3), DIGITS),
            (_token("RC-13/identifiers", 3), DIGITS),
        )
        for from_right in (False, True)
    )
    real = max(
        _smallest_departure(members, kind, False)
        for members, kind in (
            (_token("RC-03/scaled", 1), LETTERS),
            (_token("RC-08/plates", 1, lambda v: "-" not in v), LETTERS),
            (_token("RC-10/nine_30", 1), DIGITS),
            (_token("RC-12/isbn", 3, lambda v: v.startswith("979")), DIGITS),
            (_token("RC-14/prefixes", 1), LETTERS),
        )
    )
    assert chance > 100 * ALPHA
    assert real < ALPHA / 1e6


def _smallest_departure(members, kind, from_right) -> float:
    _, symbols = kind
    position_counts: dict[str, int] = {}
    for member in members:
        char = member.text[-1] if from_right else member.text[0]
        position_counts[char] = position_counts.get(char, 0) + 1
    smallest = departure(list(position_counts.values()), symbols)
    # The second character under each first one.
    below: dict[str, dict[str, int]] = {}
    for member in members:
        if len(member.text) < 2:
            continue
        first = member.text[-1] if from_right else member.text[0]
        second = member.text[-2] if from_right else member.text[1]
        below.setdefault(first, {}).setdefault(second, 0)
        below[first][second] += 1
    for counts in below.values():
        if len(counts) > 1:
            smallest = min(smallest, departure(list(counts.values()), symbols))
    return smallest


def test_tokens_of_the_corpus_are_read_with_the_scan_tokenizer():
    assert token("LOT-07-482915-EU", 5) == "482915"
    assert _token("RC-16/lots", 7)[0].text in ("EU", "NA", "AS")

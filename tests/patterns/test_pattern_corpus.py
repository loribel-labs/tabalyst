# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The reference corpus RC-01 to RC-20: fixed seeds, the scale of the algorithm,
the composition each case describes and no real data (FR-023, AC-024)."""

import hashlib
import re
from collections import Counter

import pytest
from pattern_corpus import (
    CA_LETTERS,
    FR_PLATE_LETTERS,
    GENERATORS,
    RC11_CARDS,
    RC12_GROUPS,
    RC14_NEW,
    RC14_SAMPLED,
    RC18_DOMAINS,
    RC19_FR,
    corpus,
    field,
    luhn_valid,
    with_variants,
)
from pattern_tree import lengths, structure, token

from tabalyst.scanner.detectors.email import EmailDetector
from tabalyst.scanner.detectors.phone import PhoneDetector
from tabalyst.scanner.detectors.postal import PostalCodeDetector

# (distinct values, occurrences, first 16 hex digits of the SHA-256 of the
# listing): a change of a generator or of its seed shows here.
PINNED = {
    "RC-01/toy": (6, 6, "a4b480856f691c2a"),
    "RC-02/scaled": (200, 200, "99b7049d3e113b75"),
    "RC-02/toy": (4, 4, "4ff6451627ad03ed"),
    "RC-03/scaled": (500, 500, "b0a3763e21d36646"),
    "RC-03/toy": (5, 5, "35788b0b6e07ff21"),
    "RC-04/weighted": (4, 20600, "405ceff5d3012291"),
    "RC-05/invoices": (400, 400, "611576e7e133c59b"),
    "RC-05/invoices_dependent": (400, 400, "13aeb2c2fc95158b"),
    "RC-05/references": (400, 400, "e5747b9a5cde5e79"),
    "RC-06/invoices": (400, 400, "b350a03cecaa0459"),
    "RC-07/plates": (850, 850, "0dae4b8ac855c552"),
    "RC-08/plates": (1000, 1000, "92e2634d5f5f0020"),
    "RC-09/permits": (10000, 10000, "73c9a236544751d8"),
    "RC-10/nine_30": (1000, 1000, "2e8df20413b92f2e"),
    "RC-10/nine_10": (1000, 1000, "d66d797845f9f328"),
    "RC-11/cards": (1000, 1000, "571ab048196fac24"),
    "RC-12/isbn": (1000, 1000, "70e658288f7f4ac8"),
    "RC-12/codes": (55, 1000, "9ab6eee30558e1e7"),
    "RC-13/identifiers": (10000, 10000, "c4d96ab73e3fdb29"),
    "RC-14/prefixes": (400, 400, "8c5778a8aaf74e1e"),
    "RC-15/raw_variants": (5, 5, "3639d7e1afee3afd"),
    "RC-16/lots": (1000, 1000, "77584d7ec0cecf6b"),
    "RC-17/noise": (1000, 1000, "bebeb65b749d0118"),
    "RC-18/emails": (10000, 10000, "63ddcd75578a3e2b"),
    "RC-19/phones": (4687, 10000, "cf69fefe4d0bbbaf"),
    "RC-20/postal_codes": (9933, 10000, "85f63e54b51ae8bf"),
}


def _digest(item) -> str:
    body = "\n".join(f"{value}\t{count}" for value, count in item.pairs)
    if item.file:
        body += "\n--\n" + "\n".join(f"{value}\t{count}" for value, count in item.file)
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def test_every_case_from_rc01_to_rc20_has_at_least_one_field():
    cases = {item.case for item in corpus()}
    assert cases == {f"RC-{number:02d}" for number in range(1, 21)}
    assert len(GENERATORS) == 20


@pytest.mark.parametrize("item", corpus(), ids=lambda item: item.id)
def test_each_field_is_generated_at_its_fixed_scale_with_a_fixed_seed(item):
    assert (item.distinct, item.occurrences, _digest(item)) == PINNED[item.id]


def test_the_generators_give_the_same_values_on_every_call():
    first = [generate() for generate in GENERATORS]
    assert [generate() for generate in GENERATORS] == first


@pytest.mark.parametrize("item", corpus(), ids=lambda item: item.id)
def test_values_are_distinct_sorted_and_counted_at_least_once(item):
    values = item.values()
    assert values == sorted(set(values))
    assert all(count >= 1 for _, count in item.pairs)


# The composition of each case ---------------------------------------------------------


def test_rc02_second_letter_is_independent_of_the_last_character():
    values = field("RC-02/scaled").values()
    cells = Counter((value[1], value[-1].isdigit()) for value in values)
    for letter, count in (("K", 80), ("B", 72), ("Z", 48)):
        assert cells[letter, True] == count * 3 // 4
        assert cells[letter, False] == count // 4
    assert {structure(value) for value in values} == {"UP-D", "UP-DU"}


def test_rc03_has_ten_prefixes_of_fifty_values():
    counts = Counter(value[:2] for value in field("RC-03/scaled").values())
    assert sorted(counts.values()) == [50] * 10


def test_rc05_year_is_independent_in_one_field_and_dependent_in_the_other():
    for name, cells in (
        ("invoices", {("INV", "2025"): 100, ("INV", "2026"): 100, ("ORD", "2025"): 100, ("ORD", "2026"): 100}),
        ("invoices_dependent", {("INV", "2025"): 150, ("INV", "2026"): 50, ("ORD", "2025"): 50, ("ORD", "2026"): 150}),
    ):  # fmt: skip
        values = field(f"RC-05/{name}").values()
        assert Counter((value[:3], value[4:8]) for value in values) == cells


def test_rc07_plates_cover_four_structures():
    values = field("RC-07/plates").values()
    assert Counter(structure(value) for value in values) == {
        "DP U": 200,
        "UP D": 300,
        "UDP U": 300,
        "DUD": 50,
    }


def test_rc08_french_plates_never_use_i_o_or_u():
    for value in field("RC-08/plates").values():
        if "-" in value:
            assert set(value[:2] + value[-2:]) <= set(FR_PLATE_LETTERS)


def test_rc10_sets_the_rate_of_the_leading_nine():
    for name, nines in (("nine_30", 300), ("nine_10", 100)):
        values = field(f"RC-10/{name}").values()
        assert sum(value[0] == "9" for value in values) == nines
        assert {len(value) for value in values} == {9}


def test_rc11_cards_have_the_lengths_and_heads_of_the_case():
    values = field("RC-11/cards").values()
    for head, size, count in RC11_CARDS:
        found = [value for value in values if value.startswith(head) and len(value) == size]
        assert len(found) == count, head


def test_rc12_isbn_group_depends_on_the_prefix_and_lengths_vary_a_lot():
    values = field("RC-12/isbn").values()
    groups = Counter((token(value, 1), token(value, 3)) for value in values)
    assert groups == {(prefix, group): count for prefix, group, count in RC12_GROUPS}
    sizes = Counter(lengths(value) for value in values)
    # More than six sets of lengths, one pattern each (DEC-034): a poor
    # candidate the eligibility (B2) should set aside.
    assert len(sizes) > 6


def test_rc13_has_one_dominant_prefix_and_ten_isolated_ones():
    counts = Counter(value[:2] for value in field("RC-13/identifiers").values())
    assert counts["AK"] == 9_500 and counts["AB"] == 400 and counts["AZ"] == 90
    assert sorted(count for prefix, count in counts.items() if prefix[0] != "A") == [1] * 10


def test_rc14_sample_is_part_of_the_file_and_misses_four_prefixes():
    item = field("RC-14/prefixes")
    assert item.file is not None
    file = dict(item.file)
    assert all(value in file for value in item.values())
    sampled = {value[:2] for value in item.values()}
    in_file = {value[:2] for value in file}
    assert sampled == set(RC14_SAMPLED)
    assert in_file - sampled == set(RC14_NEW)


def test_rc15_keeps_five_raw_structures():
    values = field("RC-15/raw_variants").values()
    assert len({structure(value) for value in values}) == 5


def test_rc16_segments_are_exactly_independent():
    values = field("RC-16/lots").values()
    cells = Counter((token(v, 1), token(v, 3), token(v, 7)) for v in values)
    prefixes = Counter(token(v, 1) for v in values)
    middles = Counter(token(v, 3) for v in values)
    suffixes = Counter(token(v, 7) for v in values)
    for (prefix, middle, suffix), count in cells.items():
        expected = prefixes[prefix] * middles[middle] * suffixes[suffix] / 1000**2
        assert count == expected
    forced = sum(token(v, 5).endswith("00") for v in values)
    # 300 forced and a few by chance among the other 700.
    assert 300 <= forced <= 315


def test_rc17_noise_is_one_structure_without_a_repeated_value():
    values = field("RC-17/noise").values()
    assert {structure(value) for value in values} == {"UP-D"}


def test_rc18_domains_have_the_shares_of_the_case_and_a_long_tail_under_five():
    item = field("RC-18/emails")
    detector = EmailDetector({})
    domains = Counter()
    for value, count in item.pairs:
        assert detector.classify(value).state == "matched"
        domains[value.split("@")[1]] += count
    for domain, count in RC18_DOMAINS:
        assert domains.pop(domain) == count
    assert len(domains) == 2_000
    assert max(domains.values()) < 5


def test_rc19_numbers_are_read_by_the_detector_in_every_format():
    detector = PhoneDetector({})
    regions = Counter()
    for value, count in field("RC-19/phones").pairs:
        found = detector.classify(value)
        assert found is not None and found.state == "matched", value
        regions[found.value] += count
    assert regions == {"nanp": 8_000, "fr": 2_000}


def test_rc20_codes_are_read_by_the_detector():
    detector = PostalCodeDetector({})
    for value, _ in field("RC-20/postal_codes").pairs:
        found = detector.classify(value)
        assert found is not None and found.state == "matched", value


# No real data ----------------------------------------------------------------------


def test_no_card_or_social_insurance_number_passes_the_luhn_check():
    for field_id in ("RC-10/nine_30", "RC-10/nine_10", "RC-11/cards"):
        assert not any(luhn_valid(value) for value in field(field_id).values())


def test_telephone_numbers_stay_in_the_ranges_reserved_for_fiction():
    blocks = {block.replace(" ", "") for _, block, _ in RC19_FR}
    for value in field("RC-19/phones").values():
        digits = "".join(char for char in value if char.isdigit())
        if len(digits) in (10, 11) and digits[-7:-4] == "555":
            assert digits[-4:-2] == "01", value
        else:
            national = "0" + digits[2:] if value.startswith("+33") else digits
            assert national[:6] in blocks, value


def test_email_local_parts_are_random_and_tail_domains_synthetic():
    known = {domain for domain, _ in RC18_DOMAINS}
    for value in field("RC-18/emails").values():
        local, domain = value.split("@")
        assert re.fullmatch(r"u[a-z0-9]{7}", local)
        assert domain in known or re.fullmatch(r"[a-z]{6,10}\.(com|ca|fr|net)", domain)


def test_postal_codes_use_only_the_letters_canada_post_allows():
    for value in field("RC-20/postal_codes").values():
        assert value[2] in CA_LETTERS and value[5] in CA_LETTERS


# Mandatory variants (annex A) -----------------------------------------------------------


@pytest.mark.parametrize(
    "item",
    [item for item in corpus() if item.mode == "informative" and not item.toy],
    ids=lambda item: item.id,
)
def test_variants_add_an_unknown_structure_a_wrong_length_and_a_new_combination(item):
    variants = with_variants(item)
    assert with_variants(item) == variants
    sample = set(item.values())
    added = {value for value, _ in variants.file} - sample
    assert variants.unexpected in added and variants.wrong_length in added
    assert structure(variants.unexpected) not in {structure(v) for v in sample}
    assert structure(variants.wrong_length) == structure(variants.wrong_length[:-1])
    if variants.new_combination is not None:
        assert variants.new_combination in added
        assert structure(variants.new_combination) in {structure(v) for v in sample}

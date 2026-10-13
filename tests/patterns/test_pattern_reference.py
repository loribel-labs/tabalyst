# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The reference cases RC-01 to RC-20 against the engine (AC-024): skipped until
the hierarchical discovery (B4) and its validation (B5) exist."""

import pytest
from pattern_adapter import declared_keys, discover, validate, validate_file
from pattern_corpus import RC14_NEW, corpus, field, with_variants
from pattern_expected import DECLARED, EXPECTED, declared
from pattern_tree import compare, lengths, structure, tree_to_lines

INFORMATIVE = [item for item in corpus() if item.mode == "informative" and not item.toy]


@pytest.mark.pattern_lot("B4")
@pytest.mark.parametrize("expectation", EXPECTED, ids=lambda item: item.field)
def test_discovery_finds_the_expected_families_nodes_and_tables(expectation):
    source = field(expectation.field)
    seen = discover(source)
    assert seen is not None
    problems = compare(expectation, seen, source.pairs)
    assert not problems, "\n".join(problems + tree_to_lines(seen, dict(source.pairs)))


@pytest.mark.pattern_lot("B4")
@pytest.mark.parametrize("field_id", ["RC-07/plates", "RC-13/identifiers", "RC-16/lots"])
def test_discovery_gives_the_same_tree_twice(field_id):
    # AC-019: same values and settings, same result (the workers are covered by
    # tests/scan/test_pattern_inference.py once the hierarchy replaces the list).
    source = field(field_id)
    assert discover(source) == discover(source)


@pytest.mark.pattern_lot("B4")
@pytest.mark.parametrize("field_id", ["RC-18/emails", "RC-19/phones"])
def test_the_generic_discovery_stays_off_on_a_masked_field(field_id):
    assert discover(field(field_id)) is None


@pytest.mark.pattern_lot("B4")
@pytest.mark.parametrize("expectation", DECLARED, ids=lambda item: item.field)
def test_detectors_publish_their_declared_keys_with_exact_counts(expectation):
    # AC-028, AC-029: exposed on a masked field too (DEC-027).
    assert declared_keys(field(expectation.field)) == expectation


@pytest.mark.pattern_lot("B4")
def test_telephone_formats_give_the_same_area_code_counts():
    # AC-029: (514) 555-0123 and +1 514-555-0123 count for the same area code.
    keys = {key.key: key for key in declared_keys(field("RC-19/phones")).keys}
    assert keys["nanp"].children == declared("RC-19/phones").keys[0].children


@pytest.mark.pattern_lot("B5")
def test_new_prefixes_of_the_file_are_new_variants_of_their_family():
    # RC-14, AC-014: 8 prefixes discovered, 12 in the file.
    source = field("RC-14/prefixes")
    assert source.file is not None
    outcomes = validate_file(source).outcomes
    for value, _ in source.file:
        expected = "new_variant" if value[:2] in RC14_NEW else "known"
        assert outcomes[value] == expected, value
    assert sum(value[:2] in RC14_NEW for value in outcomes) == 20


@pytest.mark.pattern_lot("B5")
@pytest.mark.parametrize("source", INFORMATIVE, ids=lambda item: item.id)
def test_variants_of_the_file_get_an_outcome_and_none_is_invalid(source):
    # Annex A: unexpected characters, wrong lengths, new combinations; AC-017.
    variants = with_variants(source)
    outcomes = validate(variants).outcomes
    assert set(outcomes) == {value for value, _ in variants.file}
    assert "invalid" not in outcomes.values()
    for value, _ in source.pairs:
        assert outcomes[value] == "known", value
    assert outcomes[variants.unexpected] == "unknown_structure"
    # A set of lengths the discovery never saw, in a known structure, is a new
    # variant of length, not an unknown structure (DEC-034); whether a new
    # combination of known segments is a new variant waits for OPEN-012.
    seen = {(structure(v), lengths(v)) for v, _ in source.pairs}
    wrong = variants.wrong_length
    if (structure(wrong), lengths(wrong)) in seen:
        assert outcomes[wrong] == "known"
    else:
        assert outcomes[wrong] == "new_variant"
    if variants.new_combination is not None:
        assert outcomes[variants.new_combination] in ("known", "new_variant")

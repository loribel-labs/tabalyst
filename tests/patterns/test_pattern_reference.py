# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The reference cases RC-01 to RC-20 against the engine (AC-024): skipped until the
lot that provides each behavior is enabled (P3 and P4 discovery, P5 declared keys,
P6 validation)."""

from dataclasses import replace

import pytest
from pattern_adapter import declared_keys, discover, validate, validate_file
from pattern_corpus import RC14_NEW, corpus, field, with_variants
from pattern_expected import DECLARED, EXPECTED, declared
from pattern_tree import compare, lengths, structure, tree_to_lines

INFORMATIVE = [item for item in corpus() if item.mode == "informative" and not item.toy]
# The fields the discovery reads, hence the ones that have a hierarchy to validate:
# the ISBN with hyphens is low_relevance (DEC-034) and has no entry to count.
DISCOVERED = [item for item in INFORMATIVE if item.id in {found.field for found in EXPECTED}]

# The families alone are the work of the lot P3 (plan: RC-01, RC-02, RC-04 for the
# counts, RC-06, RC-07, RC-15); their nodes and tables need the content facets and
# the score of the lot P4, which checks every expectation in full.
FAMILIES_AT_P3 = {
    "RC-01/toy",
    "RC-02/scaled",
    "RC-04/weighted",
    "RC-06/invoices",
    "RC-07/plates",
    "RC-15/raw_variants",
}


@pytest.mark.pattern_lot("P3")
@pytest.mark.parametrize(
    "expectation",
    [item for item in EXPECTED if item.field in FAMILIES_AT_P3],
    ids=lambda item: item.field,
)
def test_discovery_finds_the_expected_families(expectation):
    # Same expectation, nodes and tables left out: only the families, their members
    # and their counts are compared.
    source = field(expectation.field)
    seen = discover(source)
    assert seen is not None
    problems = compare(replace(expectation, conclusive=False), seen, source.pairs)
    assert not problems, "\n".join(problems + tree_to_lines(seen, dict(source.pairs)))


@pytest.mark.pattern_lot("P4")
@pytest.mark.parametrize("expectation", EXPECTED, ids=lambda item: item.field)
def test_discovery_finds_the_expected_families_nodes_and_tables(expectation):
    source = field(expectation.field)
    seen = discover(source)
    assert seen is not None
    problems = compare(expectation, seen, source.pairs)
    assert not problems, "\n".join(problems + tree_to_lines(seen, dict(source.pairs)))


@pytest.mark.pattern_lot("P3")
@pytest.mark.parametrize("field_id", ["RC-07/plates", "RC-13/identifiers", "RC-16/lots"])
def test_discovery_gives_the_same_tree_twice(field_id):
    # AC-019: same values and settings, same result.
    source = field(field_id)
    assert discover(source) == discover(source)


@pytest.mark.pattern_lot("P3")
@pytest.mark.parametrize("field_id", ["RC-07/plates", "RC-13/identifiers"])
def test_discovery_gives_the_same_tree_with_one_or_more_workers(field_id):
    # AC-019: the number of first-pass workers never changes the result.
    source = field(field_id)
    assert discover(source, workers=1) == discover(source, workers=3)


@pytest.mark.pattern_lot("P3")
@pytest.mark.parametrize("field_id", ["RC-18/emails", "RC-19/phones"])
def test_the_generic_discovery_stays_off_on_a_masked_field(field_id):
    assert discover(field(field_id)) is None


@pytest.mark.pattern_lot("P5")
@pytest.mark.parametrize("expectation", DECLARED, ids=lambda item: item.field)
def test_detectors_publish_their_declared_keys_with_exact_counts(expectation):
    # AC-028, AC-029: exposed on a masked field too (DEC-027).
    assert declared_keys(field(expectation.field)) == expectation


@pytest.mark.pattern_lot("P5")
def test_telephone_formats_give_the_same_area_code_counts():
    # AC-029: (514) 555-0123 and +1 514-555-0123 count for the same area code.
    keys = {key.key: key for key in declared_keys(field("RC-19/phones")).keys}
    assert keys["nanp"].children == declared("RC-19/phones").keys[0].children


@pytest.mark.pattern_lot("P6")
def test_new_prefixes_of_the_file_are_new_variants_of_their_family():
    # RC-14, AC-014: 8 prefixes discovered, 12 in the file.
    source = field("RC-14/prefixes")
    assert source.file is not None
    outcomes = validate_file(source).outcomes
    for value, _ in source.file:
        expected = "new_variant" if value[:2] in RC14_NEW else "known"
        assert outcomes[value] == expected, value
    assert sum(value[:2] in RC14_NEW for value in outcomes) == 20


@pytest.mark.pattern_lot("P6")
@pytest.mark.parametrize("source", DISCOVERED, ids=lambda item: item.id)
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

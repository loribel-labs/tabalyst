# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Pattern inference from the samples (design 18.12): grammar, matcher, bounds,
exposure, document and Report."""

import json
import time
from pathlib import Path

import pytest
from scan_helpers import write_text

from tabalyst.report_config import ReportConfig
from tabalyst.report_profile import build_profile
from tabalyst.scan_document import base_of, facts_sha256
from tabalyst.scan_reuse import scan_from_document
from tabalyst.scanner import ScanConfig, patterninfer, scan
from tabalyst.scanner.config import PatternInferenceSettings
from tabalyst.scanner.models import PatternToken, ScanResult
from tabalyst.scanner.patterninfer import (
    compile_signature,
    matches,
    render_signature,
    tokenize,
)
from tabalyst.scanner.validation import check_scan

EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "input"
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _scan(tmp_path: Path, header: str, rows, **settings) -> ScanResult:
    source = write_text(tmp_path, "data.csv", header + "\n" + "\n".join(rows) + "\n")
    return scan(source, config=ScanConfig.model_validate(settings))


def _entries(result: ScanResult) -> dict[str, object]:
    assert result.derived is not None and result.derived.patterns is not None
    return {entry.field: entry for entry in result.derived.patterns.fields}


def _token(kind: str, low: int, high: int | None = None, text: str | None = None):
    return PatternToken(kind=kind, text=text, min=low, max=low if high is None else high)


# Grammar ---------------------------------------------------------------------


def test_tokens_split_digits_and_letters_by_case_and_keep_other_characters():
    assert tokenize("FQ4821B") == [
        ("U", None, 2, "FQ"),
        ("D", None, 4, "4821"),
        ("U", None, 1, "B"),
    ]
    assert tokenize("ab--12 x") == [
        ("L", None, 2, "ab"),
        ("P", "-", 2, "--"),
        ("D", None, 2, "12"),
        ("P", " ", 1, " "),
        ("L", None, 1, "x"),
    ]


def test_a_run_of_letters_with_a_non_ascii_letter_is_one_unicode_token():
    assert tokenize("Québec 2") == [
        ("X", None, 6, "Québec"),
        ("P", " ", 1, " "),
        ("D", None, 1, "2"),
    ]
    # A non-ASCII digit is not a digit of the grammar: it is a literal.
    assert tokenize("a٣")[1] == ("P", "٣", 1, "٣")


def test_a_fixed_value_and_its_separator_or_space_are_one_block_of_text():
    def text(*literals: str) -> str:
        return render_signature(
            [*(_token("literal", 1, text=item) for item in literals), _token("digit_ascii", 4)]
        )

    assert text("CLI", "-", "00") == "'CLI-00'9999"
    # A single space between two elements is written as it is, after the block.
    assert text("AK", " ") == "'AK' 9999"
    assert text("AK", "-", " ") == "'AK-' 9999"
    # A separator alone is not a fixed value: it is written as it is.
    assert text("-") == "-9999"


def test_a_single_space_between_two_elements_is_written_as_it_is():
    letters, digits = _token("upper_ascii", 3), _token("digit_ascii", 3)
    space = _token("literal", 1, text=" ")

    assert render_signature([digits, space, letters]) == "999 AAA"
    # At the start, at the end or repeated, a space is quoted to be seen.
    assert render_signature([space, digits]) == "' '999"
    assert render_signature([digits, space]) == "999' '"
    assert render_signature([digits, _token("literal", 2, text=" "), letters]) == "999'  'AAA"
    assert render_signature([_token("literal", 1, text="AK"), _token("literal", 2, text=" "), digits]) == "'AK  '999"


def test_the_classes_that_mix_letters_and_digits_have_their_own_symbols():
    signature = [_token("upper_digit", 1), _token("lower_digit", 2), _token("alphanumeric", 1)]

    assert render_signature(signature) == "Xxx#"
    matcher = compile_signature(signature)
    assert matches(matcher, "7ab9")
    assert matches(matcher, "Zx1c")
    assert not matches(matcher, "zab9")
    assert not matches(matcher, "7aB9")


def test_rendering_quotes_literal_letters_so_they_are_not_classes():
    signature = [
        _token("upper_ascii", 2),
        _token("digit_ascii", 4),
        _token("literal", 1, text="A"),
    ]
    assert render_signature(signature) == "AA9999'A'"
    spaced = [
        _token("lower_ascii", 2, 5),
        _token("literal", 1, 2, text=" "),
        _token("alphanumeric", 1, 12),
        _token("literal", 1, text="-"),
        _token("literal", 1, text="'"),
        _token("letter_unicode", 7),
    ]
    assert render_signature(spaced) == "a{2,5}' '{1,2}#{1,12}'-'''@{7}"


def test_the_matcher_follows_the_signature_and_never_backtracks():
    signature = [
        _token("upper_ascii", 2),
        _token("literal", 1, text="-"),
        _token("digit_ascii", 1, 4),
    ]
    matcher = compile_signature(signature)
    assert matches(matcher, "AB-123")
    assert not matches(matcher, "AB-12345")
    assert not matches(matcher, "ab-123")
    assert not matches(matcher, "AB-123 ")
    hostile = compile_signature(
        [_token("alphanumeric", 1, 10_000), _token("literal", 1, text="-")] * 8
    )
    started = time.perf_counter()
    assert not matches(hostile, "a" * 100_000)
    assert time.perf_counter() - started < 0.5


# Inference ------------------------------------------------------------------


def test_a_constant_carried_by_every_value_of_a_pattern_is_folded_into_it(tmp_path):
    rows = [f"{LETTERS[i]}{LETTERS[i + 3]}{1000 + i * 1111}A" for i in range(4)]
    rows += ["xx-xx-xx"]
    entry = _entries(_scan(tmp_path, "id", rows))["column_1"]

    first, stray = entry.families
    # The last letter is the same in all four values; a lone value proves nothing.
    assert [pattern.render for pattern in first.patterns] == ["AA9999'A'"]
    assert [pattern.render for pattern in stray.patterns] == ["aa-aa-aa"]


def test_a_common_start_of_a_token_is_folded_and_the_rest_stays_a_class(tmp_path):
    rows = [f"A{LETTERS[i]}-{i:04d}" for i in range(10)]
    [pattern] = _entries(_scan(tmp_path, "id", rows))["column_1"].families[0].patterns

    # The digits all start with 000 here: that is a constant of the pattern too.
    assert pattern.render == "'A'A'-000'9"
    assert [token.kind for token in pattern.signature] == [
        "literal",
        "upper_ascii",
        "literal",
        "literal",
        "digit_ascii",
    ]


def test_a_complete_population_is_reported_as_all_distinct_values(tmp_path):
    rows = [f"ID-{i:03d}" for i in range(50)]
    entry = _entries(_scan(tmp_path, "id", rows))["column_1"]

    assert entry.population.complete
    assert entry.population.selection == "all"
    [pattern] = entry.all_patterns()
    assert pattern.render == "'ID-0'99"
    assert entry.population.occurrences_basis == "exact"
    assert pattern.d == 50 == entry.population.distinct
    assert pattern.examples == [0, 1, 2]
    assert entry.other.d == 0
    assert entry.limits == []
    [family] = entry.families
    assert (family.id, family.key, family.d, family.o) == ("f1", "UP-D", 50, 50)
    assert [pattern.id for pattern in family.patterns] == ["f1.p1"]
    assert entry.population.occurrences == 50
    assert entry.population.occurrences_basis == "exact"


def test_small_integers_are_assessed_and_not_inferred(tmp_path):
    entry = _entries(_scan(tmp_path, "n", [str(i) for i in range(30)]))["column_1"]

    assert entry.status == "not_applicable"
    assert entry.eligibility.state == "low_relevance"
    assert entry.reason == "small_integers"


def test_a_column_of_long_integers_is_inferred_from_its_decimal_text(tmp_path):
    rows = [str(100_000_000 + i * 7_919) for i in range(60)]
    entry = _entries(_scan(tmp_path, "number", rows))["column_1"]

    assert entry.status == "complete"
    assert entry.eligibility.state == "eligible"
    assert "integer_digits" in entry.eligibility.reasons
    assert [pattern.render for pattern in entry.all_patterns()] == ["'100'999999"]


def test_a_sensitive_field_is_never_inferred(tmp_path):
    rows = [f"person{i}@example.com" for i in range(30)]
    entry = _entries(_scan(tmp_path, "email", rows))["column_1"]

    assert entry.status == "not_applicable"
    assert entry.eligibility.state == "excluded"
    assert entry.reason == "exposure"


def test_fewer_distinct_values_than_the_minimum_give_no_patterns(tmp_path):
    entry = _entries(_scan(tmp_path, "word", ["abc"] * 10))["column_1"]

    assert entry.status == "not_applicable"
    assert entry.eligibility.state == "not_assessable"
    assert entry.reason == "too_few_distinct"


def test_a_structure_with_one_value_is_a_family_of_its_own(tmp_path):
    rows = [f"{LETTERS[i]}{LETTERS[i + 1]}{i:03d}" for i in range(20)] + ["zz-zz-zz"]
    entry = _entries(_scan(tmp_path, "code", rows))["column_1"]

    assert [pattern.render for pattern in entry.all_patterns()] == ["AA'0'99", "aa-aa-aa"]
    assert [family.d for family in entry.families] == [20, 1]
    assert entry.other.d == 0
    assert entry.other.structures == 0


def test_values_that_cannot_take_part_are_counted_as_excluded(tmp_path):
    long_value = "x" * 70
    rows = [f"AB{i:03d}" for i in range(20)] + [long_value]
    entry = _entries(
        _scan(tmp_path, "code", rows, pattern_inference={"max_value_length": 64})
    )["column_1"]

    assert entry.population.excluded.too_long_values == 1
    assert entry.population.excluded.too_complex_values == 0
    assert entry.population.distinct == 20
    assert entry.population.available == 20
    # Values were left out: the population is not every distinct value.
    assert not entry.population.complete
    assert entry.population.occurrences_basis == "sample"


def test_a_value_with_too_many_tokens_is_excluded(tmp_path):
    complicated = "a1" * 20
    rows = [f"AB{i:03d}" for i in range(20)] + [complicated]
    entry = _entries(_scan(tmp_path, "code", rows))["column_1"]

    assert entry.population.excluded.too_complex_values == 1
    assert entry.population.distinct == 20


def _five_structures(tmp_path: Path, **settings) -> object:
    # Five structures of one fixed length each, so the field is eligible.
    rows = [f"ab{i:04d}" for i in range(200)]
    rows += [f"AB-{i:03d}" for i in range(200)]
    rows += [f"{i:03d}x" for i in range(100)]
    rows += [f"q_{i:03d}" for i in range(100)]
    rows += [f"Zz{i:02d}" for i in range(100)]
    return _entries(_scan(tmp_path, "code", rows, pattern_inference=settings))["column_1"]


def test_the_families_are_bounded_and_the_rest_is_other(tmp_path):
    entry = _five_structures(tmp_path, max_families=2)

    assert [family.d for family in entry.families] == [200, 200]
    assert entry.limits == ["max_families"]
    assert (entry.other.structures, entry.other.d, entry.other.o) == (3, 300, 300)
    taken = sum(family.d for family in entry.families)
    assert taken + entry.other.d == entry.population.distinct


def _lengths_column(tmp_path: Path, **settings) -> tuple[ScanResult, object]:
    # Five lengths of one structure: five patterns of fixed length, ten values each.
    rows = [f"ID-{'7' * length}{i}" for length in range(1, 6) for i in range(10)]
    result = _scan(tmp_path, "id", rows, pattern_inference=settings)
    return result, _entries(result)["column_1"]


def test_the_patterns_of_a_family_are_bounded_and_the_rest_is_a_table(tmp_path):
    result, entry = _lengths_column(tmp_path, max_patterns_per_family=3)

    [family] = entry.families
    assert len(family.patterns) == 3
    assert entry.limits == ["max_patterns_per_family"]
    # The sevens at the start of the numbers are a facet of content, kept apart.
    [table] = [table for table in family.tables if table.facet == "lengths"]
    assert sum(cell.d for cell in table.cells) + table.others.d == family.d - 30
    assert check_scan(result) == []


def test_the_patterns_and_nodes_of_a_field_are_bounded_by_max_patterns(tmp_path):
    result, entry = _lengths_column(tmp_path, max_patterns=2)

    [family] = entry.families
    assert len(family.patterns) == 2
    assert entry.limits == ["max_patterns"]
    assert family.tables
    assert check_scan(result) == []


def test_a_budget_below_the_number_of_families_leaves_the_smallest_in_other(tmp_path):
    entry = _five_structures(tmp_path, max_patterns=3)

    assert [family.d for family in entry.families] == [200, 200, 100]
    assert entry.limits == ["max_patterns"]
    assert (entry.other.structures, entry.other.d, entry.other.o) == (2, 200, 200)


def test_the_values_a_budget_keeps_out_of_the_patterns_are_unmatched(tmp_path):
    _, entry = _lengths_column(tmp_path, max_patterns_per_family=3)

    # Two of the five lengths, ten values each, belong to no pattern.
    assert entry.other.d == 0
    assert entry.outside_patterns()[0] == 20


def _lengths_of(family: dict) -> dict:
    return next(table for table in family["tables"] if table["facet"] == "lengths")


def test_the_validator_catches_a_table_or_a_composition_that_does_not_fit(tmp_path):
    (tmp_path / "cut").mkdir()
    (tmp_path / "merged").mkdir()
    cut = _scan(
        tmp_path / "cut", "id",
        [f"ID-{'7' * length}{i}" for length in range(1, 6) for i in range(10)],
        pattern_inference={"max_patterns_per_family": 3},
    )
    merged = _scan(tmp_path / "merged", "code", _code_rows("U"))

    def damaged(result, mutate):
        document = result.model_dump(mode="json")
        mutate(document["derived"]["patterns"]["fields"][0]["families"][0])
        return check_scan(ScanResult.model_validate(document))

    cells = [{"value": str(n), "d": 0, "o": 0} for n in range(4)]
    assert any("table has more cells" in p for p in damaged(cut, lambda f: _lengths_of(f).update(cells=cells)))
    assert any(
        "composition must start" in p
        for p in damaged(merged, lambda f: f.update(composition=["UP-DU", "UP-D"]))
    )


def test_a_population_above_the_cap_is_cut_and_says_so(tmp_path):
    rows = [f"ID-{i:03d}" for i in range(50)]
    entry = _entries(
        _scan(tmp_path, "id", rows, pattern_inference={"max_values": 30})
    )["column_1"]

    assert entry.population.available == 50
    assert entry.population.distinct == 30
    assert not entry.population.complete
    assert "max_values" in entry.limits
    assert entry.population.occurrences_basis == "sample"


def test_samples_that_exposure_withheld_give_no_patterns(tmp_path):
    result = _scan(tmp_path, "id", [f"ID-{i:03d}" for i in range(50)])
    field = result.datasets[0].fields[0]
    reduced = field.values.samples.model_copy(update={"kept": 10})
    field = field.model_copy(
        update={"values": field.values.model_copy(update={"samples": reduced})}
    )
    inferred = patterninfer.infer_field("rows", field, PatternInferenceSettings())

    assert inferred.status == "not_applicable"
    assert inferred.reason == "samples_withheld"


def test_the_inference_can_be_turned_off(tmp_path):
    result = _scan(
        tmp_path,
        "id",
        [f"ID-{i:03d}" for i in range(50)],
        pattern_inference={"enabled": False},
    )

    assert result.derived.patterns is None
    assert "patterns" not in result.model_dump(mode="json")["derived"]
    assert result.run.timings.derived < 0.5


def test_the_result_does_not_depend_on_the_number_of_workers():
    config = ScanConfig()
    source = EXAMPLES / "insurance-customers.csv"
    single = scan(source, config=config, workers=1)
    several = scan(source, config=config, workers=2)

    assert single.derived == several.derived


def test_the_inference_is_deterministic_and_independent_of_the_run(tmp_path):
    rows = [f"{LETTERS[i % 26]}{LETTERS[(i * 3) % 26]}{i:04d}" for i in range(300)]
    first = _scan(tmp_path, "id", rows, limits={"max_samples": 100})
    second = _scan(tmp_path, "id", rows, limits={"max_samples": 100})

    assert first.derived == second.derived
    assert first.derived is not None


# Families: the structures that merge (E2) ---------------------------------------


def _code_rows(trail: str, count: int = 30, extra: int = 10) -> list[str]:
    """`AK-` + 4 digits + a digit for ``count`` values, then the same with a
    character of ``trail`` ("U" capital, "L" lowercase letter) for ``extra``."""
    rows = [f"AK-{1000 + i * 37:04d}{i % 10}" for i in range(count)]
    for i in range(extra):
        last = LETTERS[i % 26] if trail == "U" else LETTERS[i % 26].lower()
        rows.append(f"AK-{2000 + i * 41:04d}{last}")
    return rows


def test_structures_that_differ_by_their_last_position_are_one_family(tmp_path):
    result = _scan(tmp_path, "code", _code_rows("U"))
    [family] = _entries(result)["column_1"].families
    [pattern] = family.patterns

    assert (family.key, family.composition, family.d) == ("UP-D", ["UP-D", "UP-DU"], 40)
    # The last position is a capital or a digit; each structure is a node.
    assert pattern.render == "'AK-'9999X"
    assert pattern.signature[-1].kind == "upper_digit"
    assert [(node.render, node.d, node.role) for node in pattern.nodes] == [
        ("'AK-'99999", 30, "principal"),
        ("'AK-2'999A", 10, "secondary"),
    ]
    assert sum(node.d for node in pattern.nodes) == pattern.d
    assert check_scan(result) == []


def test_the_merged_position_takes_the_classes_of_every_merged_structure(tmp_path):
    lower = _entries(_scan(tmp_path, "code", _code_rows("L")))["column_1"]
    assert lower.families[0].patterns[0].signature[-1].kind == "lower_digit"
    rows = _code_rows("U") + [f"AK-{3000 + i * 43:04d}{LETTERS[i % 26].lower()}" for i in range(10)]
    [family] = _entries(_scan(tmp_path, "code", rows))["column_1"].families

    assert family.composition == ["UP-D", "UP-DL", "UP-DU"]
    assert family.patterns[0].signature[-1].kind == "alphanumeric"
    assert family.patterns[0].render == "'AK-'9999#"


def test_a_pattern_takes_the_classes_of_the_structures_it_holds_only(tmp_path):
    rows = [f"AK-{1000 + i * 37:04d}{i % 10}" for i in range(30)]
    rows += [f"AK-{10000 + i * 371:05d}{i % 10}" for i in range(30)]
    rows += [f"AK-{2000 + i * 41:04d}{LETTERS[i % 26]}" for i in range(10)]
    rows += [f"AK-{20000 + i * 413:05d}{LETTERS[i % 26].lower()}" for i in range(10)]
    [family] = _entries(_scan(tmp_path, "code", rows))["column_1"].families

    assert family.composition == ["UP-D", "UP-DL", "UP-DU"]
    kinds = {pattern.lengths[1]: pattern.signature[-1].kind for pattern in family.patterns}
    assert kinds == {5: "upper_digit", 6: "lower_digit"}


def test_structures_that_differ_at_the_start_of_a_block_are_one_family(tmp_path):
    rows = [f"{i % 10}{1000 + i * 37:04d}-X" for i in range(30)]
    rows += [f"{LETTERS[i % 26]}{2000 + i * 41:04d}-X" for i in range(10)]
    [family] = _entries(_scan(tmp_path, "code", rows))["column_1"].families

    assert family.composition == ["DP-U", "UDP-U"]
    assert family.patterns[0].render == "X9999'-X'"


@pytest.mark.parametrize(
    ("name", "extra"),
    [
        ("three positions", [f"AK-{1000 + i * 37:04d}{LETTERS[i]}{LETTERS[i + 3]}{LETTERS[i + 5]}" for i in range(10)]),
        ("a stable part shorter than the mixed one", [f"AK-{LETTERS[i]}{LETTERS[i + 3]}{i}" for i in range(10)]),
        ("a block length the base never has", [f"AK-{20000 + i * 41:05d}{LETTERS[i]}" for i in range(10)]),
        ("a structure with one value", ["AK-1234Z"]),
    ],
)
def test_structures_that_do_not_fit_the_merge_rule_stay_apart(tmp_path, name, extra):
    rows = [f"AK-{100 + i * 7:03d}" for i in range(30)] if name.startswith("a stable") else [
        f"AK-{1000 + i * 37:04d}" for i in range(30)
    ]
    entry = _entries(_scan(tmp_path, "code", rows + extra))["column_1"]

    assert len(entry.families) == 2, name
    assert all(not family.composition for family in entry.families), name
    assert [family.d for family in entry.families] == [30, len(extra)]


def test_families_are_ranked_by_the_larger_of_their_shares_then_by_key(tmp_path):
    # `UD` has 20 distinct values; `UP-D` 10 values with 50 occurrences each, so it
    # is the larger family in occurrences although the smaller in distinct values.
    rows = [f"{LETTERS[i]}{i:02d}" for i in range(20)] + [f"Q-{1000 + i * 91}" for i in range(10)] * 50
    entry = _entries(_scan(tmp_path, "code", rows))["column_1"]

    assert [family.key for family in entry.families] == ["UP-D", "UD"]
    assert [family.id for family in entry.families] == ["f1", "f2"]
    assert entry.families[0].o == 500


def test_a_length_the_budget_keeps_out_is_counted_in_the_table_of_lengths(tmp_path):
    result, entry = _lengths_column(tmp_path, max_patterns_per_family=3)
    [table] = [table for table in entry.families[0].tables if table.facet == "lengths"]

    # The five combinations tie in size: the kept ones are the first by lengths,
    # the others are cells of the table.
    assert [pattern.lengths for pattern in entry.families[0].patterns] == [[2, 2], [2, 3], [2, 4]]
    assert [cell.value for cell in table.cells] == ["2,5", "2,6"]
    assert table.others.distinct == 0
    assert check_scan(result) == []


def test_the_discovery_gives_the_same_entry_whatever_the_order_of_the_rows(tmp_path):
    rows = _code_rows("U") + [f"{1000 + i * 91}" for i in range(12)]
    first = _entries(_scan(tmp_path, "code", rows))["column_1"]
    second = _entries(_scan(tmp_path, "code", list(reversed(rows))))["column_1"]

    def shape(entry):
        return [
            (family.key, family.d, family.o, [(p.render, p.d, p.o) for p in family.patterns])
            for family in entry.families
        ]

    # The ids of the examples follow the order of the rows; nothing else does.
    assert shape(first) == shape(second)
    assert first.other == second.other
    assert first.limits == second.limits


# Document and Report --------------------------------------------------------


def test_a_scan_with_patterns_is_valid_and_reads_back_identical():
    result = scan(EXAMPLES / "insurance-customers.csv")

    assert check_scan(result) == []
    document = json.loads(json.dumps(result.model_dump(mode="json", by_alias=True)))
    again = scan_from_document(document, "memory")
    assert again.derived == result.derived
    assert check_scan(again) == []


def test_the_schema_accepts_the_derived_block_and_rejects_a_damaged_one():
    jsonschema = pytest.importorskip("jsonschema")
    from tabalyst.scanner.schema import scan_schema

    validator = jsonschema.Draft202012Validator(scan_schema())
    document = scan(EXAMPLES / "insurance-customers.csv").model_dump(mode="json")

    validator.validate(document)
    entry = next(
        item
        for item in document["derived"]["patterns"]["fields"]
        if item["status"] == "complete"
    )
    entry["families"][0]["patterns"][0]["signature"][0]["kind"] = "boss"
    assert not validator.is_valid(document)


def _damaged(mutate) -> list[str]:
    document = scan(EXAMPLES / "insurance-customers.csv").model_dump(mode="json")
    entry = next(
        item
        for item in document["derived"]["patterns"]["fields"]
        if item["status"] == "complete" and item["families"]
    )
    mutate(entry)
    return check_scan(ScanResult.model_validate(document))


def _first_pattern(entry):
    return entry["families"][0]["patterns"][0]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda e: e["families"][0].update(d=e["families"][0]["d"] + 1),
        lambda e: _first_pattern(e).update(render="9"),
        lambda e: _first_pattern(e).update(examples=[10**6]),
        lambda e: _first_pattern(e).update(id="f1.p9"),
        lambda e: e["other"].update(d=e["other"]["d"] + 1),
        lambda e: e["population"].update(complete=not e["population"]["complete"]),
        lambda e: _first_pattern(e)["signature"][0].update(max=99),
    ],
    ids=["family", "render", "example", "id", "other", "population", "fixed_length"],
)
def test_the_validator_catches_a_pattern_block_that_does_not_reconcile(mutate):
    assert any("derived.patterns" in problem for problem in _damaged(mutate))


def test_the_facts_hash_ignores_the_derived_block():
    result = scan(EXAMPLES / "insurance-customers.csv")
    bare = result.model_copy(update={"derived": None})

    assert facts_sha256(result) == facts_sha256(bare)


def test_a_report_carries_the_patterns_of_its_scan():
    result = scan(EXAMPLES / "insurance-customers.csv")
    profile = build_profile(result, ReportConfig(scan=result.config))

    assert profile.derived == result.derived
    assert base_of(profile).derived == result.derived
    document = json.loads(profile.model_dump_json(by_alias=True))
    assert document["derived"]["patterns"]["grammar"]["version"] == 2
    assert check_scan(base_of(profile)) == []


# Failure ---------------------------------------------------------------------


def test_a_field_on_which_the_inference_raises_fails_alone(tmp_path, monkeypatch):
    real = patterninfer._infer

    def failing(dataset, field, *args):
        if field.display == "ids":
            raise ValueError("secret-value-123")
        return real(dataset, field, *args)

    monkeypatch.setattr(patterninfer, "_infer", failing)
    result = _scan(
        tmp_path,
        "ids,codes",
        [f"ID-{i:03d},{LETTERS[i % 26]}{i:02d}" for i in range(40)],
    )

    entries = _entries(result)
    failed = entries["column_1"]
    assert failed.status == "failed"
    assert failed.reason == "inference_error"
    # The eligibility was known before the inference raised.
    assert failed.eligibility.state == "eligible"
    diagnostic = result.diagnostics[failed.diagnostic]
    assert diagnostic.code == "pattern_inference_failed"
    assert diagnostic.level == "error"
    assert (diagnostic.dataset, diagnostic.field) == ("rows", "column_1")
    assert "ValueError" in diagnostic.message
    assert "secret-value-123" not in diagnostic.message
    # The scan and the other field are unaffected.
    assert result.status == "complete"
    assert entries["column_2"].status == "complete"
    assert check_scan(result) == []


def test_the_validator_checks_the_diagnostic_of_a_failed_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(
        patterninfer, "_infer", lambda *args: (_ for _ in ()).throw(KeyError("x"))
    )
    result = _scan(tmp_path, "id", [f"ID-{i:03d}" for i in range(40)])
    document = result.model_dump(mode="json")

    assert check_scan(result) == []
    document["derived"]["patterns"]["fields"][0]["diagnostic"] = 9
    assert any("diagnostic" in p for p in check_scan(ScanResult.model_validate(document)))

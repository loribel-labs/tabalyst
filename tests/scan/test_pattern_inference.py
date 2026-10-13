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
    generalize,
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


def test_generalization_merges_adjacent_letters_then_letters_and_digits():
    tokens = tokenize("Ab12-cd")
    assert [token[0] for token in generalize(tokens, 0)] == ["U", "L", "D", "P", "L"]
    assert [token[0] for token in generalize(tokens, 1)] == ["X", "D", "P", "X"]
    level2 = generalize(tokens, 2)
    assert [token[0] for token in level2] == ["N", "P", "N"]
    assert [token[2] for token in level2] == [4, 1, 2]


def test_rendering_quotes_literal_letters_so_they_are_not_classes():
    signature = [
        _token("upper_ascii", 2),
        _token("digit_ascii", 4),
        _token("literal", 1, text="A"),
    ]
    assert render_signature(signature) == "XX9999'A'"
    spaced = [
        _token("lower_ascii", 2, 5),
        _token("literal", 1, 2, text=" "),
        _token("alphanumeric", 1, 12),
        _token("literal", 1, text="-"),
        _token("literal", 1, text="'"),
        _token("letter_unicode", 7),
    ]
    assert render_signature(spaced) == "x{2,5}' '{1,2}#{1,12}-''''@{7}"


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


def test_a_constant_letter_needs_enough_values_to_become_a_literal(tmp_path):
    def render(count: int) -> str:
        rows = [f"{LETTERS[i]}{LETTERS[i + 3]}{1000 + i:04d}A" for i in range(count)]
        entry = _entries(_scan(tmp_path, "id", rows))["column_1"]
        return entry.candidates[0].render

    assert render(4) == "XX9999X"
    assert render(5) == "XX9999'A'"


def test_a_complete_population_is_reported_as_all_distinct_values(tmp_path):
    rows = [f"ID-{i:03d}" for i in range(50)]
    entry = _entries(_scan(tmp_path, "id", rows))["column_1"]

    assert entry.population.complete
    assert entry.population.selection == "all"
    [candidate] = entry.candidates
    assert candidate.render == "'ID'-999"
    assert candidate.coverage.basis == "all_distinct"
    assert candidate.coverage.distinct == 50
    assert candidate.coverage.share == 1.0
    assert candidate.role == "principal"
    assert candidate.examples == [0, 1, 2]
    assert candidate.confidence.method == "laplace_share"
    assert entry.other.distinct == 0
    assert entry.limits == []


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
    assert [candidate.render for candidate in entry.candidates] == ["9{9}"]


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


def test_a_structure_with_one_value_is_other_not_a_pattern(tmp_path):
    rows = [f"{LETTERS[i]}{LETTERS[i + 1]}{i:03d}" for i in range(20)] + ["zz-zz-zz"]
    entry = _entries(_scan(tmp_path, "code", rows))["column_1"]

    assert [candidate.render for candidate in entry.candidates] == ["XX999"]
    assert entry.other.distinct == 1
    assert entry.other.structures == 1
    assert entry.other.share == round(1 / 21, 4)


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
    assert entry.candidates[0].coverage.basis == "sample"


def test_a_value_with_too_many_tokens_is_excluded(tmp_path):
    complicated = "a1" * 20
    rows = [f"AB{i:03d}" for i in range(20)] + [complicated]
    entry = _entries(_scan(tmp_path, "code", rows))["column_1"]

    assert entry.population.excluded.too_complex_values == 1
    assert entry.population.distinct == 20


def test_the_candidates_are_bounded_and_the_rest_is_generalized(tmp_path):
    # Five structures of one fixed length each, so the field is eligible.
    rows = [f"ab{i:04d}" for i in range(200)]
    rows += [f"AB-{i:03d}" for i in range(200)]
    rows += [f"{i:03d}x" for i in range(100)]
    rows += [f"q_{i:03d}" for i in range(100)]
    rows += [f"Zz{i:02d}" for i in range(100)]
    entry = _entries(
        _scan(tmp_path, "code", rows, pattern_inference={"max_patterns": 2})
    )["column_1"]

    assert len(entry.candidates) <= 2
    assert "max_patterns" in entry.limits
    taken = sum(candidate.coverage.distinct for candidate in entry.candidates)
    assert taken + entry.other.distinct == entry.population.distinct


def test_a_population_above_the_cap_is_cut_and_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(patterninfer, "MAX_VALUES", 30)
    rows = [f"ID-{i:03d}" for i in range(50)]
    entry = _entries(_scan(tmp_path, "id", rows))["column_1"]

    assert entry.population.available == 50
    assert entry.population.distinct == 30
    assert not entry.population.complete
    assert "max_values" in entry.limits
    assert entry.candidates[0].coverage.basis == "sample"


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

    assert result.derived is None
    assert "derived" not in result.model_dump(mode="json")
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
    entry["candidates"][0]["role"] = "boss"
    assert not validator.is_valid(document)


def _damaged(mutate) -> list[str]:
    document = scan(EXAMPLES / "insurance-customers.csv").model_dump(mode="json")
    entry = next(
        item
        for item in document["derived"]["patterns"]["fields"]
        if item["status"] == "complete" and item["candidates"]
    )
    mutate(entry)
    return check_scan(ScanResult.model_validate(document))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda e: e["candidates"][0]["coverage"].update(distinct=1),
        lambda e: e["candidates"][0].update(render="9"),
        lambda e: e["candidates"][0].update(examples=[10**6]),
        lambda e: e["other"].update(distinct=e["other"]["distinct"] + 1),
        lambda e: e["population"].update(complete=not e["population"]["complete"]),
        lambda e: e["overlaps"].append({"patterns": ["p1", "p9"], "values": 1}),
    ],
    ids=["coverage", "render", "example", "other", "population", "overlap"],
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
    assert document["derived"]["patterns"]["grammar"]["version"] == 1
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

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Character map of the strings of a field (Patterns lot C2, design 9.2b): the
most frequent characters, their Unicode families, the case of the ends and the
emoji, on the samples of the Scan and exactly in the second pass."""

import pytest
from planner_helpers import scan_csv
from scan_helpers import write_text
from second_pass_helpers import deep_csv, entry, forced_plan

from tabalyst.report_sections import character_view
from tabalyst.reporting import (
    dataset_views,
    load_profile,
    render_column_report,
    render_report,
)
from tabalyst.scanner import ScanConfig, charactermap, scan
from tabalyst.scanner.charactermap import CharacterCensus
from tabalyst.scanner.models import (
    Complete,
    Disabled,
    Limited,
    NotApplicable,
    ScanResult,
)
from tabalyst.scanner.secondpass import run_second_pass
from tabalyst.scanner.secondpass.models import CharacterProfileResult
from tabalyst.scanner.validation import check_scan


def _map(values, counts=None, top=20):
    census = CharacterCensus()
    census.add(values, counts or [1] * len(values))
    found = census.result("exact", top)
    assert isinstance(found, Complete)
    return found.value


def _characters(result: ScanResult, display: str):
    index = [field.display for field in result.datasets[0].fields].index(display)
    return result.derived.characters.fields[index].characters


# The census ------------------------------------------------------------------------


def test_the_most_frequent_characters_are_ranked_by_occurrences_then_code_point():
    found = _map(["aab", "ba", "c"], [2, 1, 1])

    assert [(item.char, item.occurrence_count) for item in found.top] == [
        ("a", 5),
        ("b", 3),
        ("c", 1),
    ]
    assert found.characters == 9 and found.distinct == 3 and found.values == 4


def test_the_list_is_cut_at_the_asked_size_but_the_totals_count_every_character():
    found = _map(["abcdef"], top=2)

    assert len(found.top) == 2
    assert found.distinct == 6 and found.characters == 6


def test_letters_and_digits_and_punctuation_are_all_ranked():
    found = _map(["a1-"], top=10)

    assert {item.char for item in found.top} == {"a", "1", "-"}


def test_a_weighted_value_counts_each_of_its_characters_once_per_occurrence():
    assert _map(["ab"], [3]).top[0].occurrence_count == 3
    assert _map(["ab", "ab", "cd"], [1, 1, 1]) == _map(["ab", "cd"], [2, 1])


def test_unicode_families_name_the_script_of_the_letters_and_the_category_of_all():
    found = _map(["Paris", "\u041c\u043e\u0441\u043a\u0432\u0430", "\u6771\u4eac", "\u03b1\u03b2", "12 !"])

    scripts = {item.name: item.occurrence_count for item in found.scripts}
    categories = {item.name: item.occurrence_count for item in found.categories}
    assert scripts == {"LATIN": 5, "CYRILLIC": 6, "CJK": 2, "GREEK": 2}
    assert categories["Nd"] == 2 and categories["Zs"] == 1 and categories["Po"] == 1
    assert sum(categories.values()) == found.characters


def test_a_fullwidth_letter_belongs_to_its_script():
    found = _map(["\uff21\uff22"])

    assert [item.name for item in found.scripts] == ["LATIN"]


def test_the_case_of_the_ends_and_the_title_case_count_occurrences_of_values():
    found = _map(
        ["Paris", "paris", "PARIS", "McDonald", "Jean-Pierre", "x1", "12"],
        [2, 1, 1, 1, 1, 1, 1],
    )

    assert found.ends_uppercase == 1
    assert found.ends_lowercase == 2 + 1 + 1 + 1
    # str.istitle: a capital after each uncased character, lowercase elsewhere.
    assert found.title_case == 2 + 1


def test_a_value_with_no_cased_letter_is_never_title_case_nor_ends_in_a_case():
    found = _map(["123", "\u6771\u4eac", "---"])

    assert (found.ends_uppercase, found.ends_lowercase, found.title_case) == (0, 0, 0)


@pytest.mark.parametrize(
    ("text", "sequences"),
    [
        ("\U0001f600", ["\U0001f600"]),
        ("\U0001f468\u200d\U0001f469\u200d\U0001f467", ["\U0001f468\u200d\U0001f469\u200d\U0001f467"]),
        ("\U0001f44d\U0001f3fd", ["\U0001f44d\U0001f3fd"]),
        ("\U0001f1eb\U0001f1f7", ["\U0001f1eb\U0001f1f7"]),
        ("1\ufe0f\u20e3", ["1\ufe0f\u20e3"]),
        ("\u2764\ufe0f", ["\u2764\ufe0f"]),
        ("a\U0001f600b\U0001f389", ["\U0001f600", "\U0001f389"]),
    ],
)
def test_an_emoji_sequence_is_counted_once_whatever_its_code_points(text, sequences):
    found = _map([text])

    assert found.emoji_sequences == len(sequences)
    assert found.with_emoji == 1
    assert {item.sequence for item in found.emoji} == set(sequences)


@pytest.mark.parametrize("text", ["abc", "\u2764", "\u00e9\u00e8", "1 2", "\U0001f1eb", "\u2605"])
def test_text_symbols_and_lone_indicators_are_not_emoji(text):
    found = _map([text])

    assert found.with_emoji == 0 and found.emoji == []


def test_emoji_are_counted_with_the_occurrences_of_their_values():
    found = _map(["\U0001f600 \U0001f600", "\U0001f600", "x"], [2, 3, 1])

    assert found.with_emoji == 5
    assert found.emoji_sequences == 2 * 2 + 3
    assert [(item.sequence, item.occurrence_count) for item in found.emoji] == [
        ("\U0001f600", 7)
    ]


def test_a_table_past_its_bound_gives_the_field_up_instead_of_a_partial_list(
    monkeypatch,
):
    monkeypatch.setattr(charactermap, "MAX_CHARACTERS", 3)
    census = CharacterCensus()
    census.add(["ab"], [1])
    census.add(["cdef"], [1])
    census.add(["a"], [1])

    found = census.result("exact", 20)

    assert isinstance(found, Limited) and found.reason == "character_limit"


def test_empty_strings_are_values_with_no_character():
    found = _map(["", "ab"], [4, 1])

    assert found.values == 5 and found.characters == 2


# The Scan ----------------------------------------------------------------------------


def test_the_scan_maps_the_characters_of_a_complete_sample_exactly(tmp_path):
    result = scan_csv(tmp_path, "name", ["Paris", "lyon", "Nice", "Paris"])

    found = _characters(result, "name")

    assert isinstance(found, Complete) and found.value.basis == "exact"
    assert found.value.values == 4 and found.value.title_case == 3
    assert check_scan(result) == []


def test_a_sampled_field_maps_its_sample_and_says_so(tmp_path):
    rows = [f"v{n:04d}" for n in range(400)]

    result = scan_csv(tmp_path, "code", rows, limits={"max_samples": 50})

    found = _characters(result, "code")
    assert isinstance(found, Complete) and found.value.basis == "sample"
    assert found.value.values < 400
    assert check_scan(result) == []


@pytest.mark.parametrize("mode", ["mask", "hide"])
def test_a_sensitive_field_has_no_character_map(tmp_path, mode):
    source = write_text(
        tmp_path, "mails.csv", "email\nann@example.com\nbob@example.com\n"
    )

    result = scan(
        source,
        config=ScanConfig.model_validate({"exposure": {"sensitive_values": mode}}),
    )

    assert isinstance(_characters(result, "email"), Disabled)
    assert check_scan(result) == []


def test_a_column_with_no_text_has_no_character_map(tmp_path):
    source = write_text(tmp_path, "numbers.json", '[{"n": 1}, {"n": 2}, {"n": 3}]')

    result = scan(source)

    # Native integers are not strings: they have no characters to map.
    assert isinstance(_characters(result, "n"), NotApplicable)


def test_a_zero_size_turns_the_map_off(tmp_path):
    result = scan_csv(tmp_path, "name", ["a", "b"], limits={"max_top_characters": 0})

    assert result.derived is None or result.derived.characters is None


def test_check_scan_rejects_a_forged_character_map(tmp_path):
    result = scan_csv(tmp_path, "name", ["Paris", "lyon"])
    document = result.model_dump(mode="json")
    document["derived"]["characters"]["fields"][0]["characters"]["value"][
        "characters"
    ] += 1

    problems = check_scan(ScanResult.model_validate(document))

    assert any("derived.characters" in problem for problem in problems)


# The second pass ----------------------------------------------------------------------


def test_the_second_pass_counts_every_value_where_the_scan_counted_its_sample(tmp_path):
    rows = [f"Ville-{n:04d}" for n in range(300)] + ["caf\u00e9 \U0001f600"] * 3
    result, _, outcome = deep_csv(tmp_path, "name", rows, limits={"max_samples": 40})

    scan_map = _characters(result, "name").value
    exact = entry(outcome, "character_profile", "name").result

    assert scan_map.basis == "sample"
    assert isinstance(exact, CharacterProfileResult) and exact.basis == "exact"
    assert exact.values == 303 and exact.with_emoji == 3
    assert exact.characters == 300 * len("Ville-0000") + 3 * len("caf\u00e9 \U0001f600")
    assert exact.model_dump(exclude={"kind"}) != scan_map.model_dump()


def test_the_scan_answers_alone_when_it_kept_every_value(tmp_path):
    result = scan_csv(tmp_path, "name", ["Paris", "lyon", "Nice", "Paris", "caf\u00e9"])

    plan = forced_plan(result)
    candidate = next(item for item in plan.candidates if item.analyzer == "character_profile")

    assert candidate.selection.satisfied_by == "derived/characters/rows/column_1"
    assert not candidate.execution.requires_source
    assert _characters(result, "name").value.basis == "exact"


def test_the_exact_map_does_not_depend_on_the_number_of_workers(tmp_path):
    rows = [f"V\u00e9{n % 97:02d}-{'x' * (n % 5)}" for n in range(500)]
    result = scan_csv(tmp_path, "name", rows, limits={"max_samples": 30})
    plan = forced_plan(result)

    documents = [
        entry(
            run_second_pass(result, tmp_path / "data.csv", plan, workers=workers),
            "character_profile",
            "name",
        ).result.model_dump()
        for workers in (1, 3)
    ]

    assert documents[0] == documents[1]


def test_the_planner_proposes_the_map_without_choosing_it_by_itself(tmp_path):
    from tabalyst.scanner.planner import plan_analyses

    result = scan_csv(tmp_path, "name", [f"v{n}" for n in range(60)], limits={"max_samples": 10})

    plan = plan_analyses(result)
    candidate = next(
        item for item in plan.candidates if item.analyzer == "character_profile"
    )

    assert candidate.parameters == {"top": 20}
    assert candidate.selection.state != "selected"


def test_a_sensitive_field_is_not_read_for_its_characters(tmp_path):
    source = write_text(
        tmp_path, "mails.csv", "email\nann@example.com\nbob@example.com\n"
    )
    result = scan(
        source,
        config=ScanConfig.model_validate({"exposure": {"sensitive_values": "mask"}}),
    )

    plan = forced_plan(result)

    assert [
        item
        for item in plan.candidates
        if item.analyzer == "character_profile"
        and item.applicability.state == "applicable"
    ] == []


# The Report -----------------------------------------------------------------------------


def _report(tmp_path, rows, *options):
    from typer.testing import CliRunner

    from tabalyst.cli import app

    source = write_text(tmp_path, "names.csv", "name\n" + "\n".join(rows) + "\n")
    outcome = CliRunner().invoke(app, ["report", str(source), *options])
    assert outcome.exit_code == 0, outcome.output
    return load_profile(tmp_path / "names.json")


def _small_samples(tmp_path):
    path = tmp_path / "small.json"
    path.write_text('{"scan": {"limits": {"max_samples": 10}}}', encoding="utf-8")
    return str(path)


def _column_page(profile):
    dataset = dataset_views(profile)[0]
    return render_column_report(profile, dataset, dataset.columns[0], "report.html")


def test_the_column_page_draws_the_character_map_of_the_scan(tmp_path, monkeypatch):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path.parent / f"{tmp_path.name}-home"))
    profile = _report(tmp_path, ["Paris", "lyon", "Z\u00fcrich \U0001f600"])

    page = _column_page(profile)

    assert 'id="character-map"' in page
    assert "Most frequent characters" in page and "Scripts of the letters" in page
    assert "Latin" in page and "1 value with an emoji" in page
    assert "<script" not in page.split('id="character-map"')[1].split("</section>")[0]


def test_the_exact_map_of_the_second_pass_replaces_the_scans(tmp_path, monkeypatch):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path.parent / f"{tmp_path.name}-home"))
    profile = _report(tmp_path, [f"Ville-{n}" for n in range(50)], "--deep", "--yes", "--config", _small_samples(tmp_path))

    column = dataset_views(profile)[0].columns[0]
    page = _column_page(profile)

    assert (
        column.characters.source == "second_pass" and column.characters.basis == "exact"
    )
    assert "Counted on every value of the column by the second pass" in page


def test_a_map_the_document_lacks_is_said_so_not_rebuilt():
    assert character_view(None, None).status == "missing"


def test_the_report_page_names_the_character_analysis(tmp_path, monkeypatch):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path.parent / f"{tmp_path.name}-home"))
    profile = _report(tmp_path, [f"Ville-{n}" for n in range(50)], "--deep", "--yes", "--config", _small_samples(tmp_path))

    assert "Characters of the values" in render_report(profile)


# Bounds, failures and drawing ---------------------------------------------------------


def test_the_limit_names_the_table_that_was_passed(monkeypatch):
    monkeypatch.setattr(charactermap, "MAX_EMOJI", 1)
    census = CharacterCensus()
    census.add(["\U0001f600", "\U0001f601"], [1, 1])

    found = census.result("exact", 20)

    assert isinstance(found, Limited) and found.limit == 1


def test_a_second_pass_that_passes_the_bound_is_limited_without_a_result(tmp_path, monkeypatch):
    rows = [f"Ville-{n:04d}" for n in range(300)]
    result = scan_csv(tmp_path, "name", rows, limits={"max_samples": 20})
    plan = forced_plan(result)
    monkeypatch.setattr(charactermap, "MAX_CHARACTERS", 3)

    outcome = run_second_pass(result, tmp_path / "data.csv", plan, workers=1)
    item = entry(outcome, "character_profile", "name")

    assert item.status == "limited" and item.reason == "character_limit"
    assert item.result is None


def test_the_scan_map_that_is_limited_does_not_make_the_analysis_answered(tmp_path, monkeypatch):
    monkeypatch.setattr(charactermap, "MAX_CHARACTERS", 3)
    result = scan_csv(tmp_path, "name", ["Paris", "lyon", "Nice"])

    plan = forced_plan(result)
    candidate = next(item for item in plan.candidates if item.analyzer == "character_profile")

    assert isinstance(_characters(result, "name"), Limited)
    assert candidate.selection.satisfied_by is None
    assert candidate.execution.requires_source


def test_a_field_whose_map_raises_gets_a_failed_entry_and_the_others_survive(tmp_path, monkeypatch):
    original = charactermap._field_map

    def broken(field, top):
        if field.display == "city":
            raise RuntimeError("boom")
        return original(field, top)

    monkeypatch.setattr(charactermap, "_field_map", broken)
    source = write_text(tmp_path, "t.csv", "name,city\nParis,Nice\nlyon,Lille\n")

    result = scan(source)

    assert _characters(result, "city").status == "failed"
    assert _characters(result, "name").status == "complete"
    assert any(item.code == "character_map_failed" for item in result.diagnostics)


def test_check_scan_rejects_a_map_on_a_masked_field(tmp_path):
    source = write_text(tmp_path, "mails.csv", "email\nann@example.com\nbob@example.com\n")
    result = scan(source, config=ScanConfig.model_validate({"exposure": {"sensitive_values": "mask"}}))
    document = result.model_dump(mode="json")
    other = scan_csv(tmp_path, "email", ["ann", "bob"]).model_dump(mode="json")
    document["derived"]["characters"]["fields"][0]["characters"] = other["derived"]["characters"][
        "fields"
    ][0]["characters"]

    problems = check_scan(ScanResult.model_validate(document))

    assert any("masked or hidden" in problem for problem in problems)


@pytest.mark.parametrize(
    ("char", "shown"),
    [("a", "a"), (" ", "\u2420"), ("\t", "\u21e5"), ("\n", "\u21b5"), ("\u0301", "U+0301"), ("\u200b", "U+200B")],
)
def test_a_character_that_cannot_be_seen_is_drawn_as_a_mark_or_its_code_point(char, shown):
    from tabalyst.report_sections import _symbol

    assert _symbol(char) == shown

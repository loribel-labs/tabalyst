# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Character profile of the strings of a field (Patterns lot C1, design 9.2)."""

import json

import pytest
from scan_helpers import dataset, field, run_scan, without_value_counts, write_text

from tabalyst.scanner.characters import PRESENCE

EXISTING = (
    "non_ascii",
    "with_line_breaks",
    "with_control_characters",
    "with_surrounding_whitespace",
    "with_repeated_whitespace",
    "uppercase",
    "lowercase",
    "mixed_case",
    "no_letters",
)


def _profile(tmp_path, values, **settings):
    """The ``string_characteristics`` of a JSON field holding ``values``."""
    rows = ",".join('{"v": ' + json.dumps(value) + "}" for value in values)
    source = write_text(tmp_path, "values.json", "[" + rows + "]")
    return field(dataset(run_scan(source, **settings), "$[]"), "v")["string_characteristics"]


def _counters(profile):
    return {name: profile[name] for name in PRESENCE}


def test_the_profile_keeps_the_nine_existing_counters_and_adds_the_new_ones(tmp_path):
    profile = _profile(tmp_path, ["a"])

    assert set(profile) == {
        *EXISTING,
        *PRESENCE,
        "characters",
        "distinct_characters",
        "special_characters",
    }


def test_ascii_values_are_counted_by_class_and_composition(tmp_path):
    profile = _profile(tmp_path, ["abc", "ABC", "Abc1", "123", "a-1", "x y", "A_B"])

    assert _counters(profile) == {
        "with_ascii_lowercase": 4,
        "with_ascii_uppercase": 3,
        "with_other_latin_letters": 0,
        "with_non_latin_letters": 0,
        "with_ascii_digits": 3,
        "with_other_digits": 0,
        "starts_uppercase": 3,
        "starts_lowercase": 3,
        "with_tabs": 0,
        "with_non_breaking_spaces": 0,
        "ascii_only": 7,
        "letters_only": 2,
        "digits_only": 1,
        "alphanumeric_only": 4,
        "letters_and_digits": 1,
        "with_invisible_characters": 0,
        "with_replacement_character": 0,
    }
    assert profile["characters"] == 3 + 3 + 4 + 3 + 3 + 3 + 3


def test_non_ascii_letters_and_digits_are_classified_by_script(tmp_path):
    values = ["é", "Ünï", "日本語", "Привет", "٣٤", "abc٣", "x²"]

    profile = _profile(tmp_path, values)

    assert profile["with_other_latin_letters"] == 2
    assert profile["with_non_latin_letters"] == 2
    assert profile["with_other_digits"] == 3
    assert profile["with_ascii_lowercase"] == 3
    assert profile["non_ascii"] == 7
    assert profile["ascii_only"] == 0
    assert profile["letters_only"] == 4
    assert profile["digits_only"] == 1
    assert profile["letters_and_digits"] == 2


def test_the_replacement_character_is_counted_and_is_a_special_character(tmp_path):
    profile = _profile(tmp_path, ["caf\ufffd", "ok"])

    assert profile["with_replacement_character"] == 1
    assert profile["letters_only"] == 1
    listed = profile["special_characters"]["value"]["listed"]
    assert listed == [
        {"char": "\ufffd", "codepoint": 0xFFFD, "value_count": 1, "occurrence_count": 1}
    ]


@pytest.mark.parametrize(
    ("value", "counter"),
    [
        ("a\u200bb", "with_invisible_characters"),
        ("\ufeffa", "with_invisible_characters"),
        ("a\u2060", "with_invisible_characters"),
        ("a\u00a0b", "with_non_breaking_spaces"),
        ("a\tb", "with_tabs"),
    ],
)
def test_invisible_characters_tabs_and_non_breaking_spaces_have_their_counter(
    tmp_path, value, counter
):
    profile = _profile(tmp_path, [value, "plain"])

    assert profile[counter] == 1
    # None of them is a special character: they have their own counter.
    assert profile["special_characters"]["value"]["listed"] == []


def test_the_start_of_the_raw_value_decides_the_start_counters(tmp_path):
    profile = _profile(tmp_path, ["Abc", " Abc", "abc", "1bc", "Éa", "éA"])

    assert profile["starts_uppercase"] == 2
    assert profile["starts_lowercase"] == 2


def test_occurrences_weigh_every_counter(tmp_path):
    source = write_text(
        tmp_path, "rep.csv", "v\n" + "a-b\n" * 5 + "ABC\n" * 2 + "12\n" * 3 + "é\n"
    )

    profile = field(dataset(run_scan(source), "rows"), "v")["string_characteristics"]

    assert profile["with_ascii_lowercase"] == 5
    assert profile["with_ascii_uppercase"] == 2
    assert profile["digits_only"] == 3
    assert profile["with_other_latin_letters"] == 1
    assert profile["characters"] == 5 * 3 + 2 * 3 + 3 * 2 + 1
    assert profile["special_characters"]["value"]["listed"] == [
        {"char": "-", "codepoint": 45, "value_count": 1, "occurrence_count": 5}
    ]


def test_special_characters_are_listed_by_values_and_occurrences(tmp_path):
    source = write_text(
        tmp_path,
        "special.csv",
        'v\n"a-b"\n"a-b"\n"a-b-c"\n"x/y.z"\n"(1)"\n"(1)"\n"ok"\n',
    )

    profile = field(dataset(run_scan(source), "rows"), "v")["string_characteristics"]

    assert profile["special_characters"] == {
        "status": "complete",
        "value": {
            "distinct": 5,
            "value_count_accuracy": "exact",
            "listed": [
                {"char": "-", "codepoint": 45, "value_count": 2, "occurrence_count": 3},
                {"char": "(", "codepoint": 40, "value_count": 1, "occurrence_count": 2},
                {"char": ")", "codepoint": 41, "value_count": 1, "occurrence_count": 2},
                {"char": ".", "codepoint": 46, "value_count": 1, "occurrence_count": 1},
                {"char": "/", "codepoint": 47, "value_count": 1, "occurrence_count": 1},
            ],
        },
    }


def test_the_special_characters_of_non_ascii_values_are_listed(tmp_path):
    profile = _profile(tmp_path, ["a€b", "«x»", "café"])

    chars = [item["char"] for item in profile["special_characters"]["value"]["listed"]]
    assert sorted(chars) == sorted(["€", "«", "»", "́"])


def test_the_inventory_of_special_characters_is_limited_above_its_bound(tmp_path):
    profile = _profile(tmp_path, ["a-b", "c.d", "e,f", "g;h", "i-j"], limits={"max_special_characters": 3})

    assert profile["special_characters"] == {
        "status": "limited",
        "reason": "character_limit",
        "limit": 3,
        "lower_bound": 4,
    }
    # The bound is on the distinct characters, so three still fit.
    fits = _profile(tmp_path, ["a-b", "c.d", "e,f", "g-h"], limits={"max_special_characters": 3})
    assert fits["special_characters"]["status"] == "complete"
    assert fits["special_characters"]["value"]["distinct"] == 3


def test_a_zero_bound_turns_the_inventory_off(tmp_path):
    profile = _profile(tmp_path, ["a-b"], limits={"max_special_characters": 0})

    assert profile["special_characters"] == {"status": "disabled"}
    assert profile["distinct_characters"]["status"] == "complete"


def test_distinct_characters_are_counted_exactly_and_limited_above_the_bound(tmp_path):
    exact = _profile(tmp_path, ["abc", "cab", "a é-"])
    limited = _profile(tmp_path, ["abc", "def"], limits={"max_distinct_characters": 5})
    at_bound = _profile(tmp_path, ["abc", "de"], limits={"max_distinct_characters": 5})

    assert exact["distinct_characters"] == {"status": "complete", "value": 6}
    assert limited["distinct_characters"] == {
        "status": "limited",
        "reason": "character_limit",
        "limit": 5,
        "lower_bound": 6,
    }
    assert at_bound["distinct_characters"] == {"status": "complete", "value": 5}


def test_a_field_without_strings_has_no_inventory(tmp_path):
    source = write_text(tmp_path, "numbers.json", '[{"v": 1}, {"v": 2.5}, {"v": true}]')

    profile = field(dataset(run_scan(source), "$[]"), "v")["string_characteristics"]

    assert profile["characters"] == 0
    assert profile["distinct_characters"] == {"status": "not_applicable", "reason": "no_values"}
    assert profile["special_characters"] == {"status": "not_applicable", "reason": "no_values"}
    assert all(profile[name] == 0 for name in PRESENCE)


def test_the_table_and_the_stream_give_the_same_profile(tmp_path):
    values = [f"id-{index % 40}é {index}" for index in range(300)] + ["a\ufffd", "x\tb"]

    complete = _profile(tmp_path, values)
    streamed = _profile(tmp_path, values, limits={"max_distinct_per_field": 1})

    assert without_value_counts(streamed) == without_value_counts(complete)
    assert complete["special_characters"]["value"]["value_count_accuracy"] == "exact"
    assert streamed["special_characters"]["value"]["value_count_accuracy"] == "upper_bound"


@pytest.mark.parametrize("mode", ["mask", "hide"])
def test_a_sensitive_field_publishes_counters_but_no_distribution_of_characters(tmp_path, mode):
    rows = "".join(f"ann{index}@example.com\n" for index in range(1, 4))
    source = write_text(tmp_path, "mails.csv", "email\n" + rows)

    profile = field(
        dataset(run_scan(source, exposure={"sensitive_values": mode}), "rows"), "email"
    )["string_characteristics"]

    assert profile["with_ascii_lowercase"] == 3
    assert profile["with_ascii_digits"] == 3
    assert profile["characters"] == 3 * len("ann1@example.com")
    assert profile["distinct_characters"] == {"status": "disabled"}
    assert profile["special_characters"] == {"status": "disabled"}


def test_the_profile_of_a_shown_sensitive_field_keeps_its_distributions(tmp_path):
    rows = "".join(f"ann{index}@example.com\n" for index in range(1, 4))
    source = write_text(tmp_path, "mails.csv", "email\n" + rows)

    profile = field(
        dataset(run_scan(source, exposure={"sensitive_values": "show"}), "rows"), "email"
    )["string_characteristics"]

    assert profile["special_characters"]["status"] == "complete"
    assert profile["distinct_characters"]["status"] == "complete"


def test_check_scan_accepts_a_profile_and_rejects_a_forged_one(tmp_path):
    from tabalyst.scanner.models import ScanResult
    from tabalyst.scanner.validation import check_scan

    rows = ",".join('{"v": ' + json.dumps(value) + "}" for value in ["a-b", "c.d", "é"])
    source = write_text(tmp_path, "values.json", "[" + rows + "]")
    result = run_scan(source)
    assert check_scan(ScanResult.model_validate(result)) == []

    profile = field(dataset(result, "$[]"), "v")["string_characteristics"]
    profile["letters_only"] = 99
    profile["special_characters"]["value"]["listed"][0]["codepoint"] = 0
    problems = check_scan(ScanResult.model_validate(result))

    assert any("a counter exceeds" in problem for problem in problems)
    assert any("codepoint does not match" in problem for problem in problems)


def _reference(values):
    """The definitions of design 9.2, applied character by character."""
    from unicodedata import category, name

    invisible = {0x200B, 0x200C, 0x200D, 0xFEFF, 0x2060}
    counters = dict.fromkeys(PRESENCE, 0)
    specials: dict[str, list[int]] = {}
    for value, count in values:
        # A blank string is a missing value, not a content string.
        if not value.strip():
            continue
        kinds = set()
        for char in value:
            code = ord(char)
            if code in invisible:
                kinds.add("invisible")
            elif code == 0xFFFD:
                kinds.add("replacement")
            elif code in (0xA0, 0x2007, 0x202F):
                kinds.add("nbsp")
            elif char == "\t":
                kinds.add("tab")
            elif char.isalpha() and char.isascii():
                kinds.add("upper" if char.isupper() else "lower")
            elif char.isalpha():
                latin = name(char, "").startswith(("LATIN", "FULLWIDTH LATIN"))
                kinds.add("latin" if latin else "letter")
            elif char.isdigit():
                kinds.add("digit" if char.isascii() else "other_digit")
            elif char.isalnum():
                kinds.add("alnum")
            elif char.isspace() or category(char) in ("Cc", "Cf"):
                pass
            else:
                kinds.add("special")
        letters = kinds & {"upper", "lower", "latin", "letter"}
        digits = kinds & {"digit", "other_digit"}
        for flag, condition in {
            "with_ascii_lowercase": "lower" in kinds,
            "with_ascii_uppercase": "upper" in kinds,
            "with_other_latin_letters": "latin" in kinds,
            "with_non_latin_letters": "letter" in kinds,
            "with_ascii_digits": "digit" in kinds,
            "with_other_digits": "other_digit" in kinds,
            "starts_uppercase": value[0].isupper(),
            "starts_lowercase": value[0].islower(),
            "with_tabs": "tab" in kinds,
            "with_non_breaking_spaces": "nbsp" in kinds,
            "ascii_only": value.isascii(),
            "letters_only": value.isalpha(),
            "digits_only": value.isdigit(),
            "alphanumeric_only": value.isalnum(),
            "letters_and_digits": value.isalnum() and bool(letters) and bool(digits),
            "with_invisible_characters": "invisible" in kinds,
            "with_replacement_character": "replacement" in kinds,
        }.items():
            counters[flag] += count * bool(condition)
        for char in set(value):
            code = ord(char)
            if code == 0xFFFD or (
                not char.isalnum()
                and not char.isspace()
                and category(char) not in ("Cc", "Cf")
            ):
                entry = specials.setdefault(char, [0, 0])
                entry[0] += 1
                entry[1] += count
    return counters, specials


def test_the_profile_matches_the_definitions_on_random_strings(tmp_path):
    import random

    rng = random.Random(7)
    alphabet = "abcxyzABCXYZ0123456789 -_.,;:@#/()[]" + "".join(
        map(
            chr,
            (9, 1, 0xE9, 0xC9, 0xFC, 0xDF, 0x153, 0x141, 0x4E2D, 0x6587, 0x416, 0x3A9),
        )
    )
    # Arabic digit, superscript two, one half, non-breaking space, zero-width space,
    # byte order mark, replacement character, combining acute, euro, guillemet, emoji.
    alphabet += "".join(
        map(
            chr,
            (0x663, 0xB2, 0xBD, 0xA0, 0x200B, 0xFEFF, 0xFFFD, 0x301, 0x20AC, 0xAB, 0x1F600),
        )
    )
    values = [
        "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 8)))
        for _ in range(400)
    ]
    # Repeats give weights above one.
    values += rng.choices(values, k=300)
    source = write_text(
        tmp_path,
        "random.json",
        json.dumps([{"v": value} for value in values]),
    )

    profile = field(dataset(run_scan(source), "$[]"), "v")["string_characteristics"]

    weights = {}
    for value in values:
        weights[value] = weights.get(value, 0) + 1
    counters, specials = _reference(weights.items())
    assert _counters(profile) == counters
    listed = {
        item["char"]: [item["value_count"], item["occurrence_count"]]
        for item in profile["special_characters"]["value"]["listed"]
    }
    assert listed == specials
    content = [value for value in values if value.strip()]
    assert profile["distinct_characters"]["value"] == len({c for v in content for c in v})
    assert profile["characters"] == sum(len(v) for v in content)


def test_a_streamed_field_counts_a_returning_value_once_per_batch(tmp_path):
    # 4,096 distinct values fill a batch; the same values return in the next one.
    values = [f"a-{index}" for index in range(4_096)] * 2
    source = write_text(tmp_path, "batches.csv", "v\n" + "\n".join(values) + "\n")

    profile = field(
        dataset(run_scan(source, limits={"max_distinct_per_field": 1}), "rows"), "v"
    )["string_characteristics"]

    (dash,) = profile["special_characters"]["value"]["listed"]
    assert dash["occurrence_count"] == 2 * 4_096
    assert 4_096 <= dash["value_count"] <= 2 * 4_096
    assert profile["special_characters"]["value"]["value_count_accuracy"] == "upper_bound"


def test_a_batch_that_mixes_ascii_and_other_values_keeps_every_weight(tmp_path):
    rows = ["a-b"] * 3 + [chr(0xE9) + "-x"] * 2 + ["Q1"] * 4 + [chr(0x4E2D)]
    source = write_text(tmp_path, "mixed.csv", "v\n" + "\n".join(rows) + "\n")

    profile = field(dataset(run_scan(source), "rows"), "v")["string_characteristics"]

    assert profile["ascii_only"] == 7
    assert profile["with_other_latin_letters"] == 2
    assert profile["with_non_latin_letters"] == 1
    assert profile["letters_and_digits"] == 4
    assert profile["starts_uppercase"] == 4
    assert profile["characters"] == 3 * 3 + 2 * 3 + 4 * 2 + 1
    (dash,) = profile["special_characters"]["value"]["listed"]
    assert (dash["value_count"], dash["occurrence_count"]) == (2, 5)


def test_a_lone_surrogate_is_not_a_special_character():
    from tabalyst.scanner.characters import _symbol

    # It cannot be written as UTF-8, so it must never reach the inventory.
    assert _symbol(chr(0xD800)) == "c"

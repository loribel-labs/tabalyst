# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""JSON Inspect contract: field display syntax with a separator (lot JI-3).

Design section 6. The canonical segments are the identity; the relative
display is a reversible label built with ``flatten.separator``; the absolute
syntax of dataset paths never uses it.
"""

import itertools

import pytest

from tabalyst.scanner.paths import (
    ITEMS,
    Key,
    format_absolute,
    format_relative,
    parse_path,
)

pytestmark = pytest.mark.inspect_lot("JI-3")

SEPARATORS = [".", "/", "-", ":", "|"]

KEYS = [
    "a",
    "b",
    "a.b",
    "a/b",
    "a-b",
    "a:b",
    "a|b",
    "c[]",
    "[",
    "]",
    '"',
    "\\",
    "$",
    "",
    " ",
    "é",
    "1st",
    "_ok",
    "a b",
    " ",
]


def _paths(keys):
    for length in (1, 2, 3):
        for names in itertools.product(keys, repeat=length):
            yield tuple(Key(name) for name in names)


@pytest.mark.parametrize("separator", SEPARATORS)
def test_every_key_path_round_trips(separator):
    short_keys = KEYS[:6] + ["c[]", '"', "", "é"]
    for path in _paths(short_keys):
        text = format_relative(path, separator)
        assert parse_path(text, separator=separator) == path, text


@pytest.mark.parametrize("separator", SEPARATORS)
def test_paths_with_items_round_trip(separator):
    paths = [
        (Key("orders"), ITEMS, Key("amount")),
        (Key("a.b"), ITEMS, ITEMS, Key("c")),
        (ITEMS, Key("x")),
        (Key(f"a{separator}b"), ITEMS),
    ]
    for path in paths:
        text = format_relative(path, separator)
        assert parse_path(text, separator=separator) == path, text


@pytest.mark.parametrize("separator", SEPARATORS)
def test_distinct_paths_never_share_a_display(separator):
    seen: dict[str, tuple] = {}
    for path in _paths(KEYS[:8]):
        text = format_relative(path, separator)
        assert seen.setdefault(text, path) == path, text


def test_default_separator_is_todays_syntax():
    assert format_relative((Key("orders"), ITEMS, Key("amount"))) == "orders[].amount"
    assert format_relative((Key("a"), Key("b"))) == "a.b"
    assert format_relative((Key("a.b"),)) == '["a.b"]'
    assert format_relative((Key("é"), Key("x y"))) == '["é"]["x y"]'


def test_custom_separator_joins_bare_keys_and_items():
    assert format_relative((Key("a"), Key("b")), "/") == "a/b"
    assert format_relative((Key("orders"), ITEMS, Key("amount")), "/") == "orders[]/amount"
    assert format_relative((Key("a"), Key("b"), Key("c")), "|") == "a|b|c"


def test_a_key_holding_the_separator_is_quoted():
    assert format_relative((Key("a/b"),), "/") == '["a/b"]'
    assert format_relative((Key("a"), Key("b/c")), "/") == 'a["b/c"]'
    # A dot is only special when it is the separator.
    assert format_relative((Key("a.b"),), "/") == '["a.b"]'


def test_literal_key_and_nested_keys_stay_distinct():
    literal = (Key("a/b"),)
    nested = (Key("a"), Key("b"))

    assert format_relative(literal, "/") != format_relative(nested, "/")
    assert parse_path(format_relative(literal, "/"), separator="/") == literal
    assert parse_path(format_relative(nested, "/"), separator="/") == nested


def test_a_separator_is_not_a_separator_of_another_syntax():
    with pytest.raises(ValueError):
        parse_path("a.b", separator="/")


def test_absolute_paths_ignore_the_separator():
    assert format_absolute((Key("customers"), ITEMS)) == "$.customers[]"
    assert parse_path("$.customers[]", separator="/") == (Key("customers"), ITEMS)
    assert parse_path('$["a/b"][]', separator="/") == (Key("a/b"), ITEMS)

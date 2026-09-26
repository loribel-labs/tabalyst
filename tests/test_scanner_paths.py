import pytest

from tabalyst.scanner.paths import (
    ITEMS,
    Column,
    Key,
    column_labels,
    format_absolute,
    format_relative,
    parse_path,
    path_to_json,
)


@pytest.mark.parametrize(
    ("path", "display"),
    [
        ((), "$"),
        ((Key("amount"),), "amount"),
        ((Key("orders"), ITEMS, Key("amount")), "orders[].amount"),
        ((ITEMS,), "[]"),
        ((ITEMS, ITEMS), "[][]"),
        ((Key("a.b"),), '["a.b"]'),
        ((Key("a"), Key("b")), "a.b"),
        ((Key("c[]"),), '["c[]"]'),
        ((Key(""),), '[""]'),
        ((Key("é"), Key("x y")), '["é"]["x y"]'),
        ((Key('quote"'), Key("_ok1")), '["quote\\""]._ok1'),
        ((Key("1st"),), '["1st"]'),
    ],
)
def test_relative_display_is_reversible(path, display):
    assert format_relative(path) == display
    assert parse_path(display) == path


@pytest.mark.parametrize(
    ("path", "display"),
    [
        ((), "$"),
        ((ITEMS,), "$[]"),
        ((Key("customers"), ITEMS), "$.customers[]"),
        ((Key("a.b"), ITEMS), '$["a.b"][]'),
    ],
)
def test_absolute_display_is_reversible(path, display):
    assert format_absolute(path) == display
    assert parse_path(display) == path


@pytest.mark.parametrize(
    "text", ["", ".a", "a.", "a..b", "a[", '["a"', '["a"x', "$a", "a[0]", "a b"]
)
def test_invalid_display_is_rejected(text):
    with pytest.raises(ValueError):
        parse_path(text)


def test_column_segments_have_labels_not_a_display_syntax():
    assert path_to_json((Column(3),)) == [{"column": 3}]
    with pytest.raises(TypeError):
        format_relative((Column(3),))


def test_column_labels_disambiguate_duplicate_and_blank_headers():
    assert column_labels(["id", "name", "name", "", " "]) == [
        "id",
        "name#2",
        "name#3",
        "#4",
        " #5",
    ]

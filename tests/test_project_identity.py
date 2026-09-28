import pytest

from tabalyst.projects import is_project_id, new_project_id


def test_project_id_is_a_26_character_ulid():
    project_id = new_project_id()

    assert len(project_id) == 26
    assert is_project_id(project_id)
    assert project_id == project_id.upper()


def test_project_ids_are_unique():
    assert len({new_project_id() for _ in range(2000)}) == 2000


def test_project_ids_sort_by_creation_time():
    earlier = new_project_id(unix_ms=1_700_000_000_000)
    later = new_project_id(unix_ms=1_700_000_000_001)
    much_later = new_project_id(unix_ms=1_900_000_000_000)

    assert earlier < later < much_later


def test_time_part_matches_the_ulid_specification():
    # 2**48 - 1 milliseconds is the largest time a ULID holds: 7ZZZZZZZZZ.
    assert new_project_id(unix_ms=(1 << 48) - 1).startswith("7ZZZZZZZZZ")
    assert new_project_id(unix_ms=0).startswith("0000000000")


@pytest.mark.parametrize("unix_ms", [-1, 1 << 48])
def test_time_outside_48_bits_is_rejected(unix_ms):
    with pytest.raises(ValueError):
        new_project_id(unix_ms=unix_ms)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "index.json",
        "01J8Z3K9QYVJ8VXW3N6R2E9F4",  # 25 characters
        "01J8Z3K9QYVJ8VXW3N6R2E9F4DD",  # 27 characters
        "01j8z3k9qyvj8vxw3n6r2e9f4d",  # lowercase
        "01J8Z3K9QYVJ8VXW3N6R2E9F4I",  # I is not in the alphabet
        "01J8Z3K9QYUJ8VXW3N6R2E9F4D",  # U is not in the alphabet
        "81J8Z3K9QYVJ8VXW3N6R2E9F4D",  # time above 2**48
        "../01J8Z3K9QYVJ8VXW3N6R2E9F4",
        None,
        12,
    ],
)
def test_invalid_project_ids(value):
    assert not is_project_id(value)

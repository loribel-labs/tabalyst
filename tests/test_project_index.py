# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import json

import pytest

from tabalyst.projects import (
    StorageLocation,
    create_project,
    find_project,
    open_or_create_project,
    read_index,
    rebuild_index,
)
from tabalyst.projects.index import ProjectIndex, source_key, write_index


@pytest.fixture
def location(tmp_path):
    return StorageLocation(tmp_path / "storage")


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "customers.csv"
    path.write_text("id\n1\n", encoding="utf-8")
    return path


def test_create_registers_the_project_in_the_index(location, source):
    document = create_project(location, source)

    index = read_index(location)

    assert index is not None
    assert index.projects == {source_key(source): document.project_id}
    written = json.loads(location.index_path.read_text("utf-8"))
    assert written["format"] == "tabalyst.project-index"
    assert written["format_revision"] == 1


def test_find_returns_the_project_of_a_path(location, source):
    document = create_project(location, source)

    assert find_project(location, source) == document


def test_find_resolves_the_spelling_of_the_path(location, source, tmp_path):
    document = create_project(location, source)
    indirect = tmp_path / "sub" / ".." / "customers.csv"
    (tmp_path / "sub").mkdir()

    assert find_project(location, indirect) == document


def test_find_without_any_project_creates_nothing(location, source):
    assert find_project(location, source) is None
    assert not location.root.exists()


def test_find_of_an_unknown_path_leaves_the_index_alone(location, source, tmp_path):
    create_project(location, source)
    before = location.index_path.read_text(encoding="utf-8")

    assert find_project(location, tmp_path / "other.csv") is None
    assert location.index_path.read_text(encoding="utf-8") == before


def test_open_or_create_reuses_then_creates(location, source, tmp_path):
    first = open_or_create_project(location, source)
    again = open_or_create_project(location, source)
    other = open_or_create_project(location, tmp_path / "other.csv")

    assert again == first
    assert other.project_id != first.project_id


def test_missing_index_is_rebuilt_from_the_project_files(location, source):
    document = create_project(location, source)
    location.index_path.unlink()

    assert find_project(location, source) == document
    assert read_index(location).projects == {source_key(source): document.project_id}


@pytest.mark.parametrize(
    "text",
    ["{", "[]", '{"format": "tabalyst.project-index"}', '{"projects": {"a": "b"}}'],
)
def test_corrupt_index_is_rebuilt(location, source, text):
    document = create_project(location, source)
    location.index_path.write_text(text, encoding="utf-8")

    assert find_project(location, source) == document
    assert read_index(location).projects == {source_key(source): document.project_id}


def test_entry_of_a_deleted_project_is_repaired(location, source):
    document = create_project(location, source)
    (location.project_path(document.project_id)).unlink()

    assert find_project(location, source) is None
    assert read_index(location).projects == {}


def test_entry_pointing_at_another_path_is_not_trusted(location, source, tmp_path):
    first = create_project(location, source)
    other = tmp_path / "other.csv"
    other.write_text("id\n", encoding="utf-8")
    second = create_project(location, other)
    # A stale index that sends the first path to the second project.
    write_index(
        location, ProjectIndex(projects={source_key(source): second.project_id})
    )

    assert find_project(location, source) == first
    assert find_project(location, other) == second


def test_project_missing_from_the_index_is_found_after_an_interrupted_creation(
    location, source
):
    document = create_project(location, source)
    write_index(location, ProjectIndex(projects={}))

    assert find_project(location, source) == document
    assert read_index(location).projects == {source_key(source): document.project_id}


def test_moved_source_has_no_project(location, source, tmp_path):
    create_project(location, source)
    moved = tmp_path / "moved.csv"
    source.rename(moved)

    assert find_project(location, moved) is None


def test_rebuild_keeps_the_most_recent_project_of_a_path(location, source):
    older = create_project(location, source)
    newer = create_project(location, source)
    assert older.project_id < newer.project_id
    location.index_path.unlink()

    assert rebuild_index(location).projects == {
        source_key(source): newer.project_id
    }


def test_rebuild_of_an_empty_workspace_writes_nothing(location):
    assert rebuild_index(location).projects == {}
    assert not location.root.exists()


def test_index_is_only_a_lookup_of_the_project_files(location, source):
    document = create_project(location, source)

    rebuilt = rebuild_index(location)
    location.index_path.unlink()

    assert rebuild_index(location) == rebuilt
    assert rebuilt.projects == {source_key(source): document.project_id}


def test_rebuild_prefers_the_latest_creation_time_over_the_id(location, source):
    from datetime import UTC, datetime

    newer = create_project(location, source, now=datetime(2026, 9, 28, tzinfo=UTC))
    # Created later in real time (greater id) but stamped earlier, as after a
    # clock correction: the stamp decides.
    older = create_project(location, source, now=datetime(2026, 1, 1, tzinfo=UTC))
    assert older.project_id > newer.project_id
    location.index_path.unlink()

    assert rebuild_index(location).projects == {source_key(source): newer.project_id}

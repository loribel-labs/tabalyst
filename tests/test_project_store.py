# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import json
from datetime import UTC, datetime, timedelta, timezone

import pytest

from tabalyst import batch
from tabalyst.errors import InputError
from tabalyst.projects import (
    ProjectDocument,
    StorageLocation,
    create_project,
    list_projects,
    read_project,
    record_scan,
    write_project,
)

MOMENT = datetime(2026, 9, 28, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def location(tmp_path):
    return StorageLocation(tmp_path / "storage")


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "data" / "customers.csv"
    path.parent.mkdir()
    path.write_text("id\n1\n", encoding="utf-8")
    return path


def test_project_json_follows_the_documented_schema(location, source):
    document = create_project(location, source, now=MOMENT)

    written = json.loads(location.project_path(document.project_id).read_text("utf-8"))

    assert written == {
        "format": "tabalyst.project",
        "format_version": "0.1.0a",
        "format_revision": 1,
        "project_id": document.project_id,
        "workspace_id": "local",
        "created_at": "2026-09-28T12:00:00Z",
        "last_scan_at": "2026-09-28T12:00:00Z",
        "source": {"path": source.resolve().as_posix(), "name": "customers.csv"},
    }


def test_project_json_has_no_source_facts_that_scan_json_holds(location, source):
    document = create_project(location, source)

    written = json.loads(location.project_path(document.project_id).read_text("utf-8"))

    assert set(written["source"]) == {"path", "name"}


def test_project_id_does_not_derive_from_the_source_path(location, source, tmp_path):
    other = tmp_path / "other.csv"
    other.write_text("id\n1\n", encoding="utf-8")

    first = create_project(location, source)
    second = create_project(location, source)
    third = create_project(location, other)

    assert len({first.project_id, second.project_id, third.project_id}) == 3


def test_read_returns_what_was_written(location, source):
    document = create_project(location, source, now=MOMENT)

    assert read_project(location, document.project_id) == document


def test_record_scan_moves_last_scan_at_only(location, source):
    document = create_project(location, source, now=MOMENT)

    updated = record_scan(location, document.project_id, now=MOMENT + timedelta(hours=1))

    assert updated.created_at == MOMENT
    assert updated.last_scan_at == MOMENT + timedelta(hours=1)
    assert read_project(location, document.project_id) == updated
    assert updated.model_copy(update={"last_scan_at": MOMENT}) == document


def test_times_are_utc_whole_seconds(location, source):
    local = datetime(2026, 9, 28, 8, 0, 0, 999_999, tzinfo=timezone(timedelta(hours=-4)))
    document = create_project(location, source, now=local)

    assert document.created_at == MOMENT
    assert document.created_at.utcoffset() == timedelta(0)
    assert document.created_at.microsecond == 0


def test_naive_time_is_rejected(location, source):
    document = create_project(location, source, now=MOMENT)
    data = document.model_dump()
    data["created_at"] = MOMENT.replace(tzinfo=None)

    with pytest.raises(ValueError):
        ProjectDocument.model_validate(data)


def test_missing_project_is_an_input_error(location):
    with pytest.raises(InputError, match="not found"):
        read_project(location, "01J8Z3K9QYVJ8VXW3N6R2E9F4D")


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("{not json", "not valid UTF-8 JSON"),
        ("[]", "Not a project document"),
        ('{"format": "tabalyst.scan"}', "Not a project document"),
        (
            (
                '{"format": "tabalyst.project", "format_version": "0.1.0a",'
                ' "format_revision": 99}'
            ),
            "Unsupported project document",
        ),
        (
            (
                '{"format": "tabalyst.project", "format_version": "0.1.0a",'
                ' "format_revision": 1}'
            ),
            "Invalid project document",
        ),
    ],
)
def test_invalid_project_documents_are_input_errors(location, source, text, message):
    document = create_project(location, source)
    location.project_path(document.project_id).write_text(text, encoding="utf-8")

    with pytest.raises(InputError, match=message):
        read_project(location, document.project_id)


def test_a_copied_project_file_is_not_another_project(location, source):
    document = create_project(location, source)
    other_id = "01J8Z3K9QYVJ8VXW3N6R2E9F4D"
    other_path = location.project_path(other_id)
    other_path.parent.mkdir(parents=True)
    other_path.write_text(
        location.project_path(document.project_id).read_text("utf-8"),
        encoding="utf-8",
    )

    with pytest.raises(InputError, match="describes project"):
        read_project(location, other_id)


def test_project_of_another_workspace_is_refused(location, source):
    document = create_project(location, source)
    foreign = StorageLocation(location.root, "team_a")

    with pytest.raises(ValueError, match="belongs to workspace"):
        write_project(foreign, document)


def test_failed_write_leaves_no_partial_file(location, source, monkeypatch):
    document = create_project(location, source, now=MOMENT)
    path = location.project_path(document.project_id)
    before = path.read_text(encoding="utf-8")

    def fail(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(batch.os, "replace", fail)

    with pytest.raises(OSError, match="disk full"):
        record_scan(location, document.project_id, now=MOMENT + timedelta(days=1))

    assert path.read_text(encoding="utf-8") == before
    assert [entry.name for entry in path.parent.iterdir()] == ["project.json"]


def test_failed_creation_leaves_no_project_directory(location, source, monkeypatch):
    def fail(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(batch.os, "replace", fail)

    with pytest.raises(OSError, match="disk full"):
        create_project(location, source)

    assert list(location.projects_dir.iterdir()) == []


def test_list_skips_what_is_not_a_valid_project(location, source):
    first = create_project(location, source, now=MOMENT)
    second = create_project(location, source, now=MOMENT)
    (location.projects_dir / "leftover").mkdir()
    (location.projects_dir / "01J8Z3K9QYVJ8VXW3N6R2E9F4D").mkdir()
    broken = create_project(location, source)
    location.project_path(broken.project_id).write_text("{", encoding="utf-8")

    listed = list_projects(location)

    assert [document.project_id for document in listed] == sorted(
        [first.project_id, second.project_id]
    )


def test_list_of_a_missing_workspace_is_empty(location):
    assert list_projects(location) == []


def test_relative_source_path_is_rejected(location, source):
    document = create_project(location, source)
    data = document.model_dump()
    data["source"] = {"path": "data/customers.csv", "name": "customers.csv"}

    with pytest.raises(ValueError, match="absolute"):
        ProjectDocument.model_validate(data)


def test_other_format_revision_is_rejected_by_the_model(location, source):
    data = create_project(location, source).model_dump()
    data["format_revision"] = 99

    with pytest.raises(ValueError):
        ProjectDocument.model_validate(data)


def test_non_ascii_source_path_is_written_readably(location, tmp_path):
    accented = tmp_path / "Données" / "clients-Montréal.csv"

    document = create_project(location, accented)

    text = location.project_path(document.project_id).read_text(encoding="utf-8")
    assert "clients-Montréal.csv" in text
    assert r"\u00e9" not in text
    index_text = location.index_path.read_text(encoding="utf-8")
    assert "montréal.csv" in index_text.lower()
    assert "\\" + "u00e9" not in index_text
    assert read_project(location, document.project_id) == document

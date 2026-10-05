# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os

import pytest

from tabalyst import scan
from tabalyst.errors import InputError
from tabalyst.scan_reuse import SourceState, compare_source

ROWS = "id,city\n1,Paris\n2,Nice\n"


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text(ROWS, encoding="utf-8")
    return path


@pytest.fixture
def recorded(source):
    return scan(source).source


def test_a_source_as_scanned_is_fresh(source, recorded):
    check = compare_source(source, recorded)

    assert check.state is SourceState.FRESH
    assert check.reason is None


def test_a_touched_source_with_the_same_content_is_fresh(source, recorded):
    stat = source.stat()
    os.utime(source, (stat.st_atime, stat.st_mtime + 10))

    assert compare_source(source, recorded).state is SourceState.FRESH


def test_a_source_of_another_size_is_stale(source, recorded):
    source.write_text(ROWS + "3,Lyon\n", encoding="utf-8")

    check = compare_source(source, recorded)

    assert check.state is SourceState.STALE
    assert check.reason == (
        f"data.csv has {source.stat().st_size} bytes, "
        f"the scan read {recorded.size_bytes}."
    )


def test_a_changed_source_of_the_same_size_is_stale(source, recorded):
    source.write_text(ROWS.replace("Paris", "Lille"), encoding="utf-8")
    stat = source.stat()
    os.utime(source, (stat.st_atime, stat.st_mtime + 10))

    check = compare_source(source, recorded)

    assert check.state is SourceState.STALE
    assert "SHA-256 differs" in check.reason


def test_a_missing_source_is_not_checked(tmp_path, recorded):
    assert compare_source(tmp_path / "gone.csv", recorded).state is SourceState.MISSING


def test_a_directory_is_not_a_source(tmp_path, recorded):
    assert compare_source(tmp_path, recorded).state is SourceState.MISSING


def test_an_unreadable_source_is_an_input_error(source, recorded, monkeypatch):
    stat = source.stat()
    os.utime(source, (stat.st_atime, stat.st_mtime + 10))

    def refuse(self, *args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(type(source), "open", refuse)

    with pytest.raises(InputError, match="Cannot read source"):
        compare_source(source, recorded)

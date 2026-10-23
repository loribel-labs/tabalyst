# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The second pass, the staging and the publication of the CSV outputs (design 6.4, 8.4, 11.5)."""

import hashlib
import os
import random

import pytest
from dedup_helpers import (
    analyze,
    assert_published,
    no_temporary_files,
    output_names,
    read_csv,
    reference_outputs,
    run,
    write_csv,
)

from tabalyst.config import CsvConfig
from tabalyst.dedup import writer
from tabalyst.dedup.failures import DedupInputError, DedupReportError

pytestmark = pytest.mark.dedup_lot("5")

ROWS = [("101", "Alice"), ("102", "Bob"), ("101", "Alice"), ("103", "Charlie"),
        ("101", "Alice"), ("102", "Bob")]


def _stage(source, **options):
    analysis = analyze(source)
    return analysis, writer.write_outputs(
        source,
        analysis,
        csv=options.pop("csv", CsvConfig()),
        destination=options.pop("destination", source.parent),
        **options,
    )


def test_the_worked_example_gives_the_rows_of_the_specification(tmp_path):
    source = write_csv(tmp_path, "example.csv", ROWS)

    run(source)

    assert_published(tmp_path, "example", ROWS)
    assert read_csv(tmp_path / "example.unique.csv")[1] == [
        ("101", "Alice"), ("102", "Bob"), ("103", "Charlie"),
    ]
    assert read_csv(tmp_path / "example.duplicates.csv")[1] == [
        ("101", "Alice"), ("102", "Bob"),
    ]
    assert read_csv(tmp_path / "example.duplicates_all.csv")[1] == [
        ("101", "Alice"), ("102", "Bob"), ("101", "Alice"), ("101", "Alice"), ("102", "Bob"),
    ]


@pytest.mark.parametrize("seed", range(8))
def test_random_sources_match_the_reference_implementation(tmp_path, seed):
    rng = random.Random(seed)
    pool = [(str(n), f"v{n % 3}") for n in range(rng.randrange(1, 12))]
    rows = [rng.choice(pool) for _ in range(rng.randrange(0, 60))]
    source = write_csv(tmp_path, "random.csv", rows)

    run(source)

    assert_published(tmp_path, "random", rows)
    assert no_temporary_files(tmp_path)


def test_a_source_without_duplicate_is_read_once_and_stages_nothing(tmp_path, monkeypatch):
    source = write_csv(tmp_path, "clean.csv", [("1", "a"), ("2", "b")])
    analysis = analyze(source)
    opened = []
    real = writer.open_records
    monkeypatch.setattr(writer, "open_records", lambda *a, **k: opened.append(a) or real(*a, **k))

    staged = writer.write_outputs(source, analysis, csv=CsvConfig(), destination=tmp_path)

    assert staged.files == ()
    assert opened == []


def test_staged_files_are_hidden_temporaries_with_rows_size_and_digest(tmp_path):
    source = write_csv(tmp_path, "example.csv", ROWS)

    _, staged = _stage(source)

    try:
        assert [f.kind for f in staged.files] == ["unique", "duplicates", "duplicates_all"]
        for output in staged.files:
            assert output.temporary.name.startswith(f".{output.final.name}.")
            assert output.temporary.name.endswith(".tmp")
            assert not output.final.exists()
            data = output.temporary.read_bytes()
            assert output.size_bytes == len(data)
            assert output.sha256 == hashlib.sha256(data).hexdigest()
        assert [f.rows for f in staged.files] == [3, 2, 5]
    finally:
        staged.discard()
    assert no_temporary_files(tmp_path)


def test_outputs_use_the_delimiter_crlf_and_minimal_quoting_of_the_configuration(tmp_path):
    rows = [("1", 'a;b "c"'), ("1", 'a;b "c"')]
    source = write_csv(tmp_path, "semi.csv", rows, delimiter=";")

    run(source, csv=CsvConfig(delimiter=";"))

    data = (tmp_path / "semi.unique.csv").read_bytes()
    assert data == b'id;name\r\n1;"a;b ""c"""\r\n'


def test_a_row_with_one_empty_cell_is_written_quoted_and_reads_back(tmp_path):
    source = write_csv(tmp_path, "single.csv", [("",), ("",), ("x",)], header=["only"])

    run(source)

    assert (tmp_path / "single.unique.csv").read_bytes() == b'only\r\n""\r\nx\r\n'
    assert read_csv(tmp_path / "single.unique.csv") == (["only"], [("",), ("x",)])


@pytest.mark.parametrize(
    ("source_bytes", "expected_prefix"),
    [(b"\xef\xbb\xbf", b"\xef\xbb\xbf"), (b"", b"")],
)
def test_the_byte_order_mark_is_written_only_if_the_source_had_one(
    tmp_path, source_bytes, expected_prefix
):
    source = tmp_path / "bom.csv"
    source.write_bytes(source_bytes + b"id,name\r\n1,a\r\n1,a\r\n")

    run(source, csv=CsvConfig(encoding="utf-8-sig"))

    for kind in ("unique", "duplicates"):
        data = (tmp_path / f"bom.{kind}.csv").read_bytes()
        assert data.startswith(expected_prefix)
        assert data[len(expected_prefix):].startswith(b"id,name")


def test_outputs_keep_the_encoding_of_the_configuration(tmp_path):
    rows = [("1", "é"), ("1", "é")]
    source = write_csv(tmp_path, "latin.csv", rows, encoding="latin-1")

    run(source, csv=CsvConfig(encoding="latin-1"))

    assert (tmp_path / "latin.unique.csv").read_bytes() == b"id,name\r\n1,\xe9\r\n"


def test_the_destination_is_created_and_receives_the_outputs(tmp_path):
    source = write_csv(tmp_path, "data.csv", ROWS)
    destination = tmp_path / "out" / "deeper"

    outcome = run(source, destination)

    assert outcome.status == "DONE"
    assert {p.name for p in outcome.files} == set(output_names("data").values())
    assert all(p.parent == destination for p in outcome.files)
    assert not list(tmp_path.glob("data.*.csv"))


def test_a_source_rewritten_with_the_same_size_and_time_is_caught_by_the_digest(tmp_path):
    source = write_csv(tmp_path, "same.csv", [("1", "a"), ("2", "b"), ("1", "a")])
    analysis = analyze(source)
    status = source.stat()
    write_csv(tmp_path, "same.csv", [("1", "a"), ("2", "b"), ("2", "b")])
    os.utime(source, ns=(status.st_atime_ns, status.st_mtime_ns))
    assert source.stat().st_size == status.st_size

    with pytest.raises(DedupInputError) as caught:
        writer.write_outputs(source, analysis, csv=CsvConfig(), destination=tmp_path)

    assert caught.value.reason == "source_changed"
    assert no_temporary_files(tmp_path)
    assert not list(tmp_path.glob("same.*.csv"))


def test_a_source_that_became_malformed_between_the_passes_is_a_changed_source(tmp_path):
    source = write_csv(tmp_path, "broken.csv", [("1", "a"), ("1", "a")])
    analysis = analyze(source)
    status = source.stat()
    source.write_bytes(b"id,name\r\n1,a\r\n1\r\n")
    os.utime(source, ns=(status.st_atime_ns, status.st_mtime_ns))

    with pytest.raises(DedupInputError) as caught:
        writer.write_outputs(source, analysis, csv=CsvConfig(), destination=tmp_path)

    assert caught.value.reason == "source_changed"
    assert no_temporary_files(tmp_path)


def test_a_source_deleted_between_the_passes_is_unreadable(tmp_path):
    source = write_csv(tmp_path, "gone.csv", [("1", "a"), ("1", "a")])
    analysis = analyze(source)
    source.unlink()

    with pytest.raises(DedupInputError) as caught:
        writer.write_outputs(source, analysis, csv=CsvConfig(), destination=tmp_path)

    assert caught.value.reason == "source_unreadable"
    assert "gone" not in str(caught.value)


def test_a_count_that_disagrees_with_an_unchanged_source_is_an_internal_error(tmp_path):
    source = write_csv(tmp_path, "lying.csv", ROWS)
    analysis = analyze(source)
    analysis.marks.mark_group_first(2)  # a second "first record" the counts do not announce

    with pytest.raises(DedupReportError) as caught:
        writer.write_outputs(source, analysis, csv=CsvConfig(), destination=tmp_path)

    assert caught.value.reason == "unexpected_error"
    assert no_temporary_files(tmp_path)


def test_a_write_error_names_the_reason_and_leaves_no_temporary_file(tmp_path):
    source = write_csv(tmp_path, "data.csv", ROWS)
    not_a_folder = tmp_path / "occupied"
    not_a_folder.write_text("file", encoding="utf-8")

    outcome = run(source, not_a_folder / "inside")

    assert outcome.status == "FAILED"
    assert outcome.reason == "output_unwritable"
    assert "occupied" not in str(outcome.error)
    assert no_temporary_files(tmp_path)


def test_a_full_disk_while_writing_is_reported_as_such(tmp_path, monkeypatch):
    import errno

    source = write_csv(tmp_path, "data.csv", ROWS)

    def full(*args, **kwargs):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(writer, "open_writer", full)

    outcome = run(source)

    assert outcome.status == "FAILED"
    assert outcome.reason == "insufficient_disk_space"
    assert no_temporary_files(tmp_path)


def test_progress_of_the_second_reading_is_named_dedup_and_writing(tmp_path):
    # The reader reports every megabyte at most, so the file must be larger than that.
    source = write_csv(tmp_path, "data.csv", [(str(n), "x" * 200) for n in range(6000)] * 2)
    events = []

    analysis = analyze(source)
    writer.write_outputs(
        source, analysis, csv=CsvConfig(), destination=tmp_path, on_progress=events.append
    ).discard()

    assert events
    assert {e.stage for e in events} == {"Dedup"}
    assert {e.phase.value for e in events} == {"writing"}
    assert all(e.bytes_total for e in events)


# ------------------------------------------------------------- stale files


def test_stale_temporaries_of_the_source_are_removed_and_no_other_file(tmp_path):
    source = write_csv(tmp_path, "data.csv", ROWS)
    stale = [
        tmp_path / ".data.unique.csv.1a2b3c4d.tmp",
        tmp_path / ".data.duplicates.csv.ffff.tmp",
        tmp_path / ".data.dedup.json.0000.tmp",
    ]
    kept = [
        tmp_path / ".other.unique.csv.1a2b3c4d.tmp",
        tmp_path / "data.unique.csv.1a2b3c4d.tmp",
        tmp_path / ".data.unique.csv.keep",
    ]
    for path in (*stale, *kept):
        path.write_text("x", encoding="utf-8")

    run(source)

    assert not any(path.exists() for path in stale)
    assert all(path.exists() for path in kept)


def test_a_source_whose_name_has_glob_characters_only_removes_its_own_temporaries(tmp_path):
    source = write_csv(tmp_path, "d[1].csv", ROWS)
    own = tmp_path / ".d[1].unique.csv.aa.tmp"
    neighbour = tmp_path / ".d1.unique.csv.aa.tmp"
    own.write_text("x", encoding="utf-8")
    neighbour.write_text("x", encoding="utf-8")

    writer.remove_stale_temporaries(source, tmp_path)

    assert not own.exists()
    assert neighbour.exists()


# -------------------------------------------------------------- publication


def test_a_replacement_failure_removes_what_the_run_published_and_the_rest(
    tmp_path, monkeypatch
):
    from tabalyst.dedup import publish

    source = write_csv(tmp_path, "data.csv", ROWS)
    real = os.replace
    calls = []

    def replace(src, dst):
        calls.append(dst)
        if len(calls) == 2:
            raise PermissionError("denied")
        real(src, dst)

    monkeypatch.setattr(publish.os, "replace", replace)

    outcome = run(source)

    assert outcome.status == "FAILED"
    assert outcome.reason == "output_unwritable"
    assert not list(tmp_path.glob("data.*.csv"))
    assert no_temporary_files(tmp_path)


def test_a_failed_run_publishes_nothing_even_when_the_first_pass_succeeded(tmp_path):
    source = write_csv(tmp_path, "limit.csv", ROWS)

    outcome = run(source, max_rows=3)

    assert outcome.status == "FAILED"
    assert outcome.reason == "row_limit_exceeded"
    assert outcome.files == ()
    assert not list(tmp_path.glob("limit.*.csv"))


def test_an_unexpected_exception_is_a_failed_outcome_without_its_text(tmp_path, monkeypatch):
    source = write_csv(tmp_path, "boom.csv", ROWS)

    def boom(*args, **kwargs):
        raise RuntimeError("secret cell value")

    monkeypatch.setattr(writer, "write_outputs", boom)

    outcome = run(source)

    assert outcome.status == "FAILED"
    assert outcome.reason == "unexpected_error"
    assert "secret" not in str(outcome.error)
    assert isinstance(outcome.error.__cause__, RuntimeError)
    assert no_temporary_files(tmp_path)


def test_a_source_without_duplicate_is_done_with_no_file(tmp_path):
    source = write_csv(tmp_path, "clean.csv", [("1", "a"), ("2", "b")])

    outcome = run(source)

    assert outcome.status == "DONE"
    assert outcome.files == ()
    assert outcome.analysis is not None and outcome.analysis.passes == 1
    assert reference_outputs([("1", "a"), ("2", "b")]) == {}


def test_a_rerun_replaces_the_previous_outputs(tmp_path):
    source = write_csv(tmp_path, "data.csv", ROWS)
    run(source)
    changed = [("7", "z"), ("7", "z"), ("8", "y"), ("7", "z"), ("8", "y")]
    write_csv(tmp_path, "data.csv", changed)

    run(source)

    assert_published(tmp_path, "data", changed)

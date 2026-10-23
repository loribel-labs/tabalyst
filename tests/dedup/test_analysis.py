# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The first pass of Dedup, ``analyze_dedup`` (lot 4, design dedup 6.2, 8.4, 9)."""

import hashlib
import tracemalloc

import pytest
from dedup_helpers import (
    analyze,
    count_stats,
    generated_rows,
    reference_stats,
    write_csv,
)

from tabalyst.config import CsvConfig
from tabalyst.dedup.analysis import expected_rows, planned_outputs
from tabalyst.dedup.failures import DedupInputError, DedupReportError
from tabalyst.errors import ConfigurationError
from tabalyst.progress import ProgressPhase

WIDE = ["id", "c1", "c2"]


def _rows(total, extra):
    return list(generated_rows(total, extra, width=3))


def _error_of(path, **options):
    with pytest.raises(DedupInputError) as caught:
        analyze(path, **options)
    return caught.value


# --------------------------------------------------------------- the result


@pytest.mark.dedup_lot("4")
def test_the_analysis_describes_the_source_it_read(tmp_path):
    source = write_csv(tmp_path, "id.csv", [("1", "a"), ("1", "a")], encoding="utf-8-sig")

    identity = analyze(source).source

    assert identity.size_bytes == source.stat().st_size
    assert identity.mtime_ns == source.stat().st_mtime_ns
    assert identity.content_sha256 == hashlib.sha256(source.read_bytes()).hexdigest()


@pytest.mark.dedup_lot("4")
@pytest.mark.parametrize(
    ("rows", "outputs", "passes"),
    [
        ([], (), 1),
        ([("1", "a"), ("2", "b")], (), 1),
        ([("1", "a"), ("1", "a")], ("unique", "duplicates"), 2),
        ([("1", "a")] * 3, ("unique", "duplicates", "duplicates_all"), 2),
        (
            [("1", "a"), ("1", "a"), ("2", "b"), ("2", "b"), ("2", "b")],
            ("unique", "duplicates", "duplicates_all"),
            2,
        ),
    ],
)
def test_the_outputs_follow_the_maximum_frequency_of_a_row(tmp_path, rows, outputs, passes):
    analysis = analyze(write_csv(tmp_path, "m.csv", rows))

    assert analysis.outputs == outputs
    assert analysis.passes == passes


@pytest.mark.dedup_lot("4")
def test_the_rows_expected_in_each_output_are_d_g_and_o(tmp_path):
    rows = [("1", "a")] * 3 + [("2", "b")] * 2 + [("3", "c")]
    stats = analyze(write_csv(tmp_path, "rows.csv", rows)).stats

    assert planned_outputs(stats) == ("unique", "duplicates", "duplicates_all")
    assert expected_rows(stats, "unique") == 3
    assert expected_rows(stats, "duplicates") == 2
    assert expected_rows(stats, "duplicates_all") == 5


@pytest.mark.dedup_lot("4")
def test_a_small_file_stays_in_memory_and_measures_nothing_unasked(tmp_path):
    analysis = analyze(write_csv(tmp_path, "small.csv", _rows(50, 10), header=WIDE))

    assert analysis.storage_mode == "memory"
    assert analysis.spilled_at_record is None
    assert analysis.memory_peak_bytes is None
    assert analysis.first_pass_seconds > 0


@pytest.mark.dedup_lot("4")
def test_the_python_allocations_are_measured_only_on_request(tmp_path):
    source = write_csv(tmp_path, "peak.csv", _rows(2_000, 300), header=WIDE)

    analysis = analyze(source, measure_memory=True)

    assert analysis.memory_peak_bytes is not None and analysis.memory_peak_bytes > 0
    assert not tracemalloc.is_tracing()


# ------------------------------------------------------- reading the source


@pytest.mark.dedup_lot("4")
def test_cells_with_separators_quotes_and_line_breaks_are_compared_whole(tmp_path):
    rows = [
        ("1", 'say "hi", then\r\nleave'),
        ("1", "say"),
        ("1", 'say "hi", then\r\nleave'),
        ("1", "say"),
    ]
    source = write_csv(tmp_path, "cells.csv", rows)

    analysis = analyze(source)

    assert count_stats(analysis) == reference_stats(rows)
    assert analysis.stats.total == 4  # a multiline cell is one record


@pytest.mark.dedup_lot("4")
def test_a_byte_order_mark_and_a_configured_delimiter_are_honored(tmp_path):
    rows = [("1", "a"), ("1", "a"), ("2", "b")]
    source = write_csv(
        tmp_path, "semi.csv", rows, delimiter=";", encoding="utf-8-sig", header=["id", "name"]
    )

    analysis = analyze(source, csv=CsvConfig(delimiter=";"))

    assert count_stats(analysis) == reference_stats(rows)


@pytest.mark.dedup_lot("4")
def test_a_file_with_only_a_header_has_no_record(tmp_path):
    analysis = analyze(write_csv(tmp_path, "header.csv", []))

    assert analysis.stats.total == 0
    assert analysis.stats.max_occurrences == 0
    assert analysis.outputs == ()


@pytest.mark.dedup_lot("4")
def test_an_irregular_record_reports_how_many_records_were_accepted(tmp_path):
    path = tmp_path / "ragged.csv"
    path.write_text("id,name\r\n1,a\r\n2,b\r\n3\r\n", encoding="utf-8", newline="")

    error = _error_of(path)

    assert (error.reason, error.records_read) == ("invalid_csv", 2)


@pytest.mark.dedup_lot("4")
def test_a_directory_is_not_a_source(tmp_path):
    assert _error_of(tmp_path).reason == "source_unreadable"


# ----------------------------------------------------------------- the limit


@pytest.mark.dedup_lot("4")
def test_a_single_record_is_allowed_by_a_limit_of_one(tmp_path):
    source = write_csv(tmp_path, "one.csv", [("1", "a")])

    assert analyze(source, max_rows=1).stats.total == 1
    two = write_csv(tmp_path, "two.csv", [("1", "a"), ("2", "b")])
    error = _error_of(two, max_rows=1)
    assert (error.reason, error.records_read, error.limit) == ("row_limit_exceeded", 2, 1)


@pytest.mark.dedup_lot("4")
def test_the_message_of_the_limit_names_the_count_and_no_cell(tmp_path):
    source = write_csv(tmp_path, "limit.csv", [("secret-4711", "x")] * 5)

    message = str(_error_of(source, max_rows=3))

    assert "3" in message
    assert "secret" not in message


@pytest.mark.dedup_lot("4")
@pytest.mark.parametrize("option", ["max_rows", "memory_budget_mb"])
@pytest.mark.parametrize("value", [0, -1])
def test_an_option_below_its_minimum_is_a_configuration_error(tmp_path, option, value):
    source = write_csv(tmp_path, "opt.csv", [("1", "a")])

    with pytest.raises(ConfigurationError, match=option):
        analyze(source, **{option: value})


# ----------------------------------------------------------------- the disk


@pytest.mark.dedup_lot("4")
def test_the_limit_after_a_spill_leaves_no_temporary_database(tmp_path):
    source = write_csv(tmp_path, "late.csv", _rows(40_000, 2_000), header=WIDE)
    scratch = tmp_path / "tmp"
    scratch.mkdir()

    error = _error_of(source, max_rows=30_000, memory_budget_mb=1, temp_dir=scratch)

    assert error.reason == "row_limit_exceeded"
    assert not list(scratch.iterdir())


@pytest.mark.dedup_lot("4")
def test_a_malformed_record_after_a_spill_leaves_no_temporary_database(tmp_path):
    text = "id,c1,c2\r\n" + "".join(f"{n},value {n},more {n}\r\n" for n in range(30_000))
    source = tmp_path / "late-ragged.csv"
    source.write_text(text + "1,2\r\n", encoding="utf-8", newline="")
    scratch = tmp_path / "tmp"
    scratch.mkdir()

    error = _error_of(source, memory_budget_mb=1, temp_dir=scratch)

    assert error.reason == "invalid_csv"
    assert error.records_read == 30_000
    assert not list(scratch.iterdir())


@pytest.mark.dedup_lot("4")
def test_the_spill_is_named_in_the_progress_and_in_the_result(tmp_path):
    source = write_csv(tmp_path, "spill.csv", _rows(30_000, 3_000), header=WIDE)
    scratch = tmp_path / "tmp"
    scratch.mkdir()
    events = []

    analysis = analyze(
        source, memory_budget_mb=1, temp_dir=scratch, on_progress=events.append
    )

    assert analysis.storage_mode == "disk"
    assert 0 < analysis.spilled_at_record <= 30_000
    spills = [event for event in events if event.detail]
    assert len(spills) == 1
    assert spills[0].detail == (
        f"memory budget reached at record {analysis.spilled_at_record:,}, "
        "continuing on disk"
    )
    assert spills[0].phase is ProgressPhase.READING
    assert {event.stage for event in events} == {"Dedup"}


@pytest.mark.dedup_lot("4")
def test_the_progress_reports_the_bytes_read_and_never_a_cell(tmp_path):
    rows = [(str(n), f"secret-cell-{n}") for n in range(80_000)]
    source = write_csv(tmp_path, "big.csv", rows)
    assert source.stat().st_size > 1 << 20
    events = []

    analyze(source, on_progress=events.append)

    reads = [event for event in events if event.bytes_read is not None]
    assert reads
    assert reads[-1].bytes_total == source.stat().st_size
    assert all(event.bytes_read <= event.bytes_total for event in reads)
    assert "secret" not in repr(events)


@pytest.mark.dedup_lot("4")
def test_a_storage_failure_is_a_report_error_with_its_reason(tmp_path):
    source = write_csv(tmp_path, "nodisk.csv", _rows(30_000, 1_000), header=WIDE)
    occupied = tmp_path / "occupied"
    occupied.write_text("x", encoding="utf-8")

    with pytest.raises(DedupReportError) as caught:
        analyze(source, memory_budget_mb=1, temp_dir=occupied)

    assert caught.value.reason == "storage_unavailable"


# ------------------------------------------------------ stability (design 9.3)


@pytest.mark.dedup_lot("4")
def test_a_source_that_grows_during_the_pass_is_refused(tmp_path, monkeypatch):
    from tabalyst.dedup import analysis as module

    source = write_csv(tmp_path, "grows.csv", _rows(200, 20), header=WIDE)
    real = module.TieredRowStore

    class Growing(real):
        done = False

        def observe(self, key, position):
            if not Growing.done:
                Growing.done = True
                with source.open("ab") as stream:
                    stream.write(b"999,x,y\r\n")
            return super().observe(key, position)

    monkeypatch.setattr(module, "TieredRowStore", Growing)

    error = _error_of(source)

    assert error.reason == "source_changed"


@pytest.mark.dedup_lot("4")
def test_a_source_rewritten_into_a_malformed_file_is_reported_as_changed(
    tmp_path, monkeypatch
):
    from tabalyst.dedup import analysis as module

    source = write_csv(tmp_path, "garbled.csv", _rows(200, 20), header=WIDE)
    real = module.TieredRowStore

    class Garbling(real):
        done = False

        def observe(self, key, position):
            if not Garbling.done:
                Garbling.done = True
                with source.open("ab") as stream:
                    stream.write(b"only-one-cell\r\n")
            return super().observe(key, position)

    monkeypatch.setattr(module, "TieredRowStore", Garbling)

    assert _error_of(source).reason == "source_changed"


@pytest.mark.dedup_lot("4")
def test_the_messages_of_a_source_failure_carry_no_path(tmp_path):
    for target in (tmp_path / "missing-folder-name.csv", tmp_path):
        message = str(_error_of(target))
        assert str(tmp_path) not in message
        assert "missing-folder-name" not in message

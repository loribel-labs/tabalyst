# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Validation of the source and stability between the passes (design 4.4, 9.3):
T23 and T25."""

import pytest
from dedup_helpers import analyze, load_report, no_temporary_files, run, write_csv

ROWS = [("1", "a"), ("2", "b"), ("1", "a"), ("3", "c")]


def _error_of(path, **options):
    from tabalyst.dedup.failures import DedupInputError

    with pytest.raises(DedupInputError) as caught:
        analyze(path, **options)
    return caught.value


@pytest.mark.dedup_lot("4")
@pytest.mark.dedup_t("T25")
def test_an_empty_file_has_no_header_and_is_refused(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_bytes(b"")
    assert _error_of(path).reason == "invalid_csv"


@pytest.mark.dedup_lot("4")
@pytest.mark.dedup_t("T25")
def test_an_irregular_record_is_refused_with_its_number_and_without_its_cells(tmp_path):
    path = tmp_path / "ragged.csv"
    path.write_text(
        "id,name\r\n1,secret-4711\r\n2,secret-4712,extra\r\n", encoding="utf-8", newline=""
    )
    error = _error_of(path)
    assert error.reason == "invalid_csv"
    message = str(error)
    assert "2" in message  # the number of the data record
    assert "secret" not in message


@pytest.mark.dedup_lot("4")
@pytest.mark.dedup_t("T25")
def test_a_blank_line_is_a_record_of_the_wrong_width(tmp_path):
    path = tmp_path / "blank.csv"
    path.write_text("id,name\r\n1,a\r\n\r\n2,b\r\n", encoding="utf-8", newline="")
    assert _error_of(path).reason == "invalid_csv"


@pytest.mark.dedup_lot("4")
@pytest.mark.dedup_t("T25")
def test_an_unterminated_quote_is_refused(tmp_path):
    path = tmp_path / "quote.csv"
    path.write_text('id,name\r\n1,"never closed\r\n', encoding="utf-8", newline="")
    assert _error_of(path).reason == "invalid_csv"


@pytest.mark.dedup_lot("4")
@pytest.mark.dedup_t("T25")
def test_a_file_that_cannot_be_decoded_names_the_encoding_problem(tmp_path):
    path = tmp_path / "latin.csv"
    path.write_bytes(b"id,name\r\n1,caf\xe9\r\n")
    assert _error_of(path).reason == "encoding_error"


@pytest.mark.dedup_lot("4")
@pytest.mark.dedup_t("T25")
def test_a_missing_source_is_a_source_error(tmp_path):
    assert _error_of(tmp_path / "missing.csv").reason == "source_unreadable"


@pytest.mark.dedup_lot("6")
@pytest.mark.dedup_t("T25")
def test_a_malformed_source_publishes_no_csv_and_leaves_a_failed_report(tmp_path):
    path = tmp_path / "ragged.csv"
    path.write_text("id,name\r\n1,a\r\n1,a\r\n2\r\n", encoding="utf-8", newline="")
    outcome = run(path)
    assert outcome.status == "FAILED"
    assert outcome.reason == "invalid_csv"
    assert load_report(tmp_path, "ragged")["status"] == "failed"
    assert not list(tmp_path.glob("ragged.*.csv"))
    assert no_temporary_files(tmp_path)


@pytest.mark.dedup_lot("5")
@pytest.mark.dedup_t("T23")
@pytest.mark.parametrize("change", ["same_size", "longer"])
def test_a_source_changed_between_the_passes_publishes_nothing(
    tmp_path, monkeypatch, change
):
    from tabalyst.dedup import writer

    source = write_csv(tmp_path, "moving.csv", ROWS)
    real = writer.write_outputs

    def change_then_write(path, analysis, **options):
        if change == "same_size":
            write_csv(tmp_path, "moving.csv", [("1", "a"), ("2", "b"), ("2", "b"), ("3", "c")])
        else:
            write_csv(tmp_path, "moving.csv", [*ROWS, ("4", "d")])
        return real(path, analysis, **options)

    monkeypatch.setattr(writer, "write_outputs", change_then_write)
    outcome = run(source)
    assert outcome.status == "FAILED"
    assert outcome.reason == "source_changed"
    assert not list(tmp_path.glob("moving.*.csv"))
    assert no_temporary_files(tmp_path)

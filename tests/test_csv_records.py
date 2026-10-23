# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The strict CSV reading shared by ``sample`` and Dedup (design dedup 4.4)."""

import hashlib

import pytest

from tabalyst.config import CsvConfig
from tabalyst.csv_records import CsvRecordError, open_records, output_encoding
from tabalyst.errors import InputError


def _write(tmp_path, text, *, encoding="utf-8", name="data.csv"):
    path = tmp_path / name
    path.write_bytes(text.encode(encoding))
    return path


def _error(path, config=None):
    with pytest.raises(CsvRecordError) as caught, open_records(
        path, config or CsvConfig()
    ) as records:
        list(records)
    return caught.value


def test_the_header_and_the_records_are_read_in_order(tmp_path):
    path = _write(tmp_path, "id,name\r\n1,a\r\n2,b\r\n")

    with open_records(path, CsvConfig()) as records:
        assert records.header == ["id", "name"]
        assert list(records) == [["1", "a"], ["2", "b"]]
        assert records.records_read == 2


def test_a_multiline_cell_is_one_record_and_the_delimiter_is_configurable(tmp_path):
    path = _write(tmp_path, 'id;note\r\n1;"two\r\nlines"\r\n2;x\r\n')

    with open_records(path, CsvConfig(delimiter=";")) as records:
        assert list(records) == [["1", "two\r\nlines"], ["2", "x"]]
        assert records.line_num == 4


def test_a_byte_order_mark_is_not_part_of_the_first_header_cell(tmp_path):
    path = _write(tmp_path, "id,name\r\n1,a\r\n", encoding="utf-8-sig")

    with open_records(path, CsvConfig()) as records:
        assert records.header == ["id", "name"]


def test_a_header_only_file_has_no_records(tmp_path):
    path = _write(tmp_path, "id,name\r\n")

    with open_records(path, CsvConfig()) as records:
        assert list(records) == []
        assert records.records_read == 0


def test_an_empty_file_has_no_header(tmp_path):
    error = _error(_write(tmp_path, ""))

    assert error.kind == "invalid_csv"
    assert "empty or has no header" in str(error)


def test_a_record_of_the_wrong_width_is_refused_without_its_cells(tmp_path):
    path = _write(tmp_path, "id,name\r\n1,a\r\n2,secret,more\r\n3,c\r\n")

    error = _error(path)

    assert error.kind == "invalid_csv"
    assert error.records_read == 1
    assert "Data record 2 (ending at physical line 3)" in str(error)
    assert "secret" not in str(error)


def test_a_blank_line_is_a_record_of_width_zero(tmp_path):
    error = _error(_write(tmp_path, "id,name\r\n1,a\r\n\r\n2,b\r\n"))

    assert error.kind == "invalid_csv"
    assert "found 0" in str(error)


def test_an_unterminated_quote_is_invalid(tmp_path):
    error = _error(_write(tmp_path, 'id,name\r\n1,"open\r\n'))

    assert error.kind == "invalid_csv"
    assert "physical line 2" in str(error)


def test_a_file_that_cannot_be_decoded_is_an_encoding_error(tmp_path):
    error = _error(_write(tmp_path, "id,name\r\n1,café\r\n", encoding="latin-1"))

    assert error.kind == "encoding_error"
    assert "Specify --encoding" in str(error)


def test_a_missing_file_is_a_source_error_and_an_input_error(tmp_path):
    error = _error(tmp_path / "missing.csv")

    assert error.kind == "source_unreadable"
    assert isinstance(error, InputError)


def test_the_digest_and_the_byte_count_come_from_the_one_reading(tmp_path):
    text = 'id,name\r\n1,"two\r\nlines"\r\n2,b\r\n'
    path = _write(tmp_path, text, encoding="utf-8-sig")
    seen: list[int] = []

    with open_records(path, CsvConfig(), hash_content=True, on_bytes=seen.append) as records:
        list(records)
        digest = records.content_digest()
        assert records.bytes_read == path.stat().st_size

    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
    assert seen and seen[-1] == path.stat().st_size


def test_the_digest_covers_the_whole_file_even_when_the_records_stop_early(tmp_path):
    path = _write(tmp_path, "id,name\r\n" + "1,a\r\n" * 5000)

    with open_records(path, CsvConfig(), hash_content=True) as records:
        next(iter(records))
        digest = records.content_digest()

    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()


def test_a_digest_is_refused_when_the_records_were_not_opened_for_it(tmp_path):
    path = _write(tmp_path, "id,name\r\n1,a\r\n")

    with open_records(path, CsvConfig()) as records, pytest.raises(
        RuntimeError, match="hash_content"
    ):
        records.content_digest()


def test_the_output_encoding_keeps_the_presence_of_a_byte_order_mark(tmp_path):
    plain = _write(tmp_path, "a\r\n", name="plain.csv")
    marked = _write(tmp_path, "a\r\n", encoding="utf-8-sig", name="marked.csv")

    assert output_encoding(plain, "utf-8-sig") == "utf-8"
    assert output_encoding(marked, "utf-8-sig") == "utf-8-sig"
    assert output_encoding(plain, "cp1252") == "cp1252"

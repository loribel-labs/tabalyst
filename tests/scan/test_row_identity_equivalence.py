# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""A1 of the Unique ID plan: the row identity of the Scan equals that of Dedup for a CSV.

The Scan compares records through a 128-bit digest of their values
(``records.duplicates``, design scan 9.10); Dedup compares the decoded cells exactly
(``full_decoded_csv_row_v1``). The identifier uniqueness contract
(``docs/dev/report/identifier-uniqueness.md`` 6) takes either count as ``E``, so on
adversarial files the two counts must equal an independent oracle, the Python ``csv``
module read the way both readers read, and each other.
"""

import csv
import io
from pathlib import Path

import pytest

from tabalyst import scan
from tabalyst.dedup.failures import DedupInputError
from tabalyst.dedup_service import dedup_csv
from tabalyst.errors import InputError
from tabalyst.scanner import ScanConfig

CRLF = b"\r\n"
BOM = b"\xef\xbb\xbf"


def _oracle_extra_copies(content: bytes, encoding: str = "utf-8-sig") -> tuple[int, int]:
    """(rows, extra copies) of the data records, by ``Counter`` of tuples."""
    text = content.decode(encoding)
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    next(reader)
    rows = [tuple(row) for row in reader]
    return len(rows), len(rows) - len(set(rows))


CASES: dict[str, bytes] = {
    "plain": b"id,name\r\n1,a\r\n1,a\r\n2,b\r\n",
    "triple": b"id,name\r\n1,a\r\n1,a\r\n1,a\r\n1,a\r\n",
    "empty_cells": b"id,name,note\r\n,,\r\n,,\r\n1,,\r\n1,,\r\n,x,\r\n",
    "single_column_empty": b"id\r\n\"\"\r\n\"\"\r\nA\r\n",
    "bom": BOM + b"id,name\r\nA,b\r\nA,b\r\n",
    "quotes_equal": b'id,name\r\nA,"x"\r\nA,x\r\n"A",x\r\n',
    "quoted_comma": b'id,name\r\nA,"x,y"\r\nA,"x,y"\r\nA,x\r\n',
    "multiline_cell": b'id,name\r\nA,"line1\r\nline2"\r\nA,"line1\r\nline2"\r\nA,"line1\nline2"\r\n',
    "doubled_quote": b'id,name\r\nA,"say ""hi"""\r\nA,"say ""hi"""\r\n',
    "separator_ambiguity": b'a,b\r\n"x|y",z\r\nx,"y|z"\r\n"x|y",z\r\n',
    "trim_difference": b"id,name\r\nA-1,Alice\r\n A-1 ,Alice\r\n",
    "case_difference": b"id,name\r\nA,x\r\na,x\r\nA,x\r\n",
    "nfc_vs_nfd": "id,name\r\né,x\r\né,x\r\né,x\r\n".encode(),
    "only_header": b"id,name\r\n",
    "mixed_line_endings": b"id,name\r\nA,b\nA,b\rA,b\r\n",
    "no_final_newline": b"id,name\r\nA,b\r\nA,b",
    "long_cell": b"id,name\r\nA," + b"x" * 300 + b"\r\nA," + b"x" * 300 + b"\r\nA," + b"x" * 299 + b"\r\n",
    "wide": (
        b"c1,c2,c3,c4,c5,c6,c7,c8\r\n"
        b"1,,3,,5,,7,\r\n1,,3,,5,,7,\r\n1,,3,,5,,7,8\r\n"
    ),
}


def _scan(source: Path, **settings):
    config = ScanConfig.model_validate(settings) if settings else None
    return scan(source, config=config)


@pytest.mark.parametrize("name", sorted(CASES))
def test_scan_dedup_and_oracle_agree_on_adversarial_csv(tmp_path, name):
    content = CASES[name]
    source = tmp_path / f"{name}.csv"
    source.write_bytes(content)
    rows, extra = _oracle_extra_copies(content)

    result = _scan(source, limits={"max_listed_records": 100})
    dataset = result.datasets[0]
    outcome = dedup_csv(source, output_dir=tmp_path / "out")

    assert outcome.status == "DONE", (outcome.status, outcome.reason)
    assert outcome.report.status == "complete"
    records = outcome.report.records
    assert dataset.record_count == records.total == rows
    assert dataset.records.duplicates.count.status == "complete"
    assert dataset.records.duplicates.count.value == records.extra_copies == extra
    assert result.source.sha256 == outcome.report.source.content_sha256
    assert result.scope.records_excluded == 0


def test_a_ragged_csv_is_refused_by_default_by_both(tmp_path):
    source = tmp_path / "ragged.csv"
    source.write_bytes(b"id,name\r\nA,b\r\nA\r\nA,b,c\r\nA,b\r\n")

    with pytest.raises(InputError):
        _scan(source)
    with pytest.raises(DedupInputError) as refused:
        dedup_csv(source, output_dir=tmp_path / "out")
    assert refused.value.reason == "invalid_csv"


def test_tolerant_scan_excludes_ragged_rows_so_its_scope_is_partial(tmp_path):
    """The Scan counts duplicates among the rows of the header width only; Dedup cannot
    report such a file, so a Dedup report never describes a file with excluded rows."""
    source = tmp_path / "ragged.csv"
    source.write_bytes(b"id,name\r\nA,b\r\nA\r\nA,b,c\r\nA,b\r\nC,d\r\n")

    result = _scan(source, errors={"policy": "tolerant"})

    dataset = result.datasets[0]
    assert result.scope.records_excluded == 2
    assert result.scope.records_read == 5
    assert dataset.record_count == 3
    assert dataset.records.duplicates.count.value == 1
    with pytest.raises(DedupInputError):
        dedup_csv(source, output_dir=tmp_path / "out")


def test_a_blank_line_is_a_width_error_for_both(tmp_path):
    source = tmp_path / "blank.csv"
    source.write_bytes(b"id,name\r\nA,b\r\n\r\nA,b\r\n")

    with pytest.raises(InputError):
        _scan(source)
    with pytest.raises(DedupInputError):
        dedup_csv(source, output_dir=tmp_path / "out")


def test_a_cell_with_a_nul_is_refused_by_the_scan_reader(tmp_path):
    """The NUL form of the Scan digest is therefore unreachable for a CSV file."""
    source = tmp_path / "nul.csv"
    source.write_bytes(b"id,name\r\nA,b\x00\r\nA,b\x00\r\n")

    with pytest.raises(InputError):
        _scan(source)


def test_the_counts_agree_with_a_semicolon_and_latin_1(tmp_path):
    content = "id;nom\r\n1;café\r\n1;café\r\n2;thé\r\n".encode("latin-1", "replace")
    source = tmp_path / "latin.csv"
    source.write_bytes(content)

    result = _scan(source, csv={"delimiter": ";", "encoding": "latin-1"})
    outcome = dedup_csv(
        source, output_dir=tmp_path / "out", delimiter=";", encoding="latin-1"
    )

    assert outcome.status == "DONE"
    assert result.datasets[0].records.duplicates.count.value == 1
    assert outcome.report.records.extra_copies == 1
    assert outcome.report.settings.delimiter == ";"
    assert outcome.report.settings.encoding == "latin-1"


def test_random_files_agree_with_the_oracle(tmp_path):
    import random

    rng = random.Random(20261023)
    alphabet = ["", "a", "A", " a", "a ", "é", "é", "x,y", 'q"q', "l1\nl2", "l1\r\nl2"]
    for index in range(25):
        width = rng.randint(1, 5)
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\r\n")
        writer.writerow([f"c{n}" for n in range(width)])
        pool = [
            tuple(rng.choice(alphabet) for _ in range(width))
            for _ in range(rng.randint(1, 6))
        ]
        for _ in range(rng.randint(1, 60)):
            writer.writerow(rng.choice(pool))
        content = buffer.getvalue().encode("utf-8")
        source = tmp_path / f"random{index}.csv"
        source.write_bytes(content)
        rows, extra = _oracle_extra_copies(content)

        result = _scan(source)
        outcome = dedup_csv(source, output_dir=tmp_path / f"out{index}")

        assert outcome.status == "DONE", (index, outcome.reason)
        assert result.datasets[0].records.duplicates.count.value == extra, index
        assert outcome.report.records.extra_copies == extra, index
        assert outcome.report.records.total == result.datasets[0].record_count == rows

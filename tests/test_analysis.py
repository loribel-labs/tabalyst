from pathlib import Path

import pandas as pd
import pytest

from tabalyst import AnalysisConfig, analyze_column, analyze_csv
from tabalyst.config import CsvConfig
from tabalyst.ingestion import CsvInputError
from tabalyst.models import DatasetProfile


def test_basic_csv_statistics_and_json_roundtrip():
    profile = analyze_csv(Path(__file__).parents[1] / "examples/basic.csv")
    assert profile.summary.row_count == 5
    assert profile.summary.column_count == 6
    assert profile.summary.cell_count == 30
    assert profile.summary.missing_count == 2
    assert profile.summary.missing_percent == 6.67
    assert profile.summary.duplicate_row_count == 1
    assert profile.columns[0].inferred_type == "text"
    assert profile.columns[0].distinct_count == 4
    assert profile.preview[0].values[0] == "001"
    assert profile.columns[2].inferred_type == "mixed"
    assert profile.columns[3].inferred_type == "date"
    assert profile.columns[4].inferred_type == "boolean"
    assert next(
        i for i in profile.issues if i.code == "duplicate_rows"
    ).row_numbers == [4]
    assert DatasetProfile.model_validate_json(profile.model_dump_json()) == profile


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("", "empty"),
        ("\n", "no header"),
        ('"unterminated', "Invalid CSV"),
        ('a,b\n1,"unterminated', "Invalid CSV"),
        ("a,b\n1\n", "expected 2 fields, found 1"),
        ("a,b\n1,2,3\n", "expected 2 fields, found 3"),
        ("a,b\n\n1,2\n", "expected 2 fields, found 0"),
        ("a,b\n1,\0\n", "NUL"),
    ],
)
def test_invalid_csv_is_rejected_without_skipping(tmp_path, content, message):
    source = tmp_path / "input.csv"
    source.write_text(content, encoding="utf-8")
    with pytest.raises(CsvInputError, match=message):
        analyze_csv(source)


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_bom_accents_quotes_and_multiline_records(tmp_path, newline):
    source = tmp_path / "input.csv"
    source.write_text(
        'name,note\nAndr\u00e9,"first\nsecond, part"\nZo\u00e9,"a ""quote"""\n',
        encoding="utf-8-sig",
        newline=newline,
    )
    profile = analyze_csv(source)
    assert profile.summary.row_count == 2
    assert profile.columns[0].name == "name"
    assert profile.preview[0].values == ["Andr\u00e9", f"first{newline}second, part"]
    assert profile.preview[1].row_number == 2
    assert profile.preview[1].values[1] == 'a "quote"'


def test_latin_encoding_and_separator_are_configurable(tmp_path):
    source = tmp_path / "input.csv"
    source.write_bytes("name;amount\nAndr\u00e9;12,50\n".encode("cp1252"))
    with pytest.raises(CsvInputError, match="Cannot decode"):
        analyze_csv(source)
    profile = analyze_csv(
        source, AnalysisConfig(csv=CsvConfig(encoding="cp1252", delimiter=";"))
    )
    assert profile.preview[0].values == ["Andr\u00e9", "12,50"]
    assert profile.columns[1].inferred_type == "text"


def test_missing_markers_are_explicit_and_raw_values_are_preserved(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("a,b\nNA, \nNULL,NaN\n,ok\n", encoding="utf-8")
    profile = analyze_csv(source)
    assert profile.summary.missing_count == 2
    assert profile.preview[0].values == ["NA", " "]
    configured = analyze_csv(source, AnalysisConfig(missing_values=["", "NA", "NULL"]))
    assert configured.summary.missing_count == 4
    assert configured.preview == profile.preview


def test_duplicate_and_blank_headers_keep_their_original_values(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("a,a,\n1,2,3\n", encoding="utf-8")
    profile = analyze_csv(source)
    assert [c.name for c in profile.columns] == ["a", "a", ""]
    assert [c.id for c in profile.columns] == ["column_1", "column_2", "column_3"]
    assert profile.preview[0].values == ["1", "2", "3"]
    assert next(i for i in profile.issues if i.code == "ambiguous_headers").count == 3


def test_header_only_csv_has_zero_counts(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("a,b\n", encoding="utf-8")
    profile = analyze_csv(source)
    assert profile.summary.row_count == 0
    assert profile.summary.missing_percent == 0
    assert profile.summary.duplicate_row_count == 0
    assert profile.preview == []
    assert all(c.inferred_type == "empty" for c in profile.columns)


def test_explicit_empty_rows_are_counted(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("a,b\n,\n , \n", encoding="utf-8")
    profile = analyze_csv(source)
    assert profile.summary.empty_row_count == 2
    assert profile.summary.missing_count == 4
    assert profile.summary.empty_column_count == 2
    assert profile.summary.duplicate_row_count == 0


@pytest.mark.parametrize(
    ("values", "kind"),
    [
        (["001", "002"], "text"),
        (["true", "FALSE"], "boolean"),
        (["1", "-3", "+2"], "integer"),
        (["1", "2.5", "1e3"], "number"),
        (["2024-02-29", "2026-09-17"], "date"),
        (["2025-02-29", "2026-09-17"], "mixed"),
        (["1", "not a number"], "mixed"),
        (["", " "], "empty"),
    ],
)
def test_column_inference(values, kind):
    profile = analyze_column(pd.Series(values))
    assert profile.inferred_type == kind


def test_numeric_statistics_exclude_missing_values():
    profile = analyze_column(pd.Series(["1", "2", "3", "", "4"]))
    assert profile.numeric.model_dump() == {
        "minimum": 1.0,
        "maximum": 4.0,
        "mean": 2.5,
        "median": 2.5,
    }


def test_nonfinite_statistics_are_not_serialized():
    profile = analyze_column(pd.Series(["1e999", "2"]))
    assert profile.numeric is None
    assert "NaN" not in profile.model_dump_json()


def test_single_column_api_requires_raw_strings():
    with pytest.raises(ValueError, match="raw strings"):
        analyze_column(pd.Series([1, None]))


def test_preview_size_does_not_change_analysis(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("a\n1\n2\n2\n", encoding="utf-8")
    profile = analyze_csv(source, AnalysisConfig(preview_rows=1))
    assert len(profile.preview) == 1
    assert profile.summary.row_count == 3
    assert profile.summary.duplicate_row_count == 1
    assert analyze_csv(source, AnalysisConfig(preview_rows=0)).preview == []

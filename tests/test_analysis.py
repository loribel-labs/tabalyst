from pathlib import Path

import pandas as pd
import pytest

from tabalyst import AnalysisConfig, analyze_column, analyze_csv
from tabalyst.config import (
    CsvConfig,
    DateDetectionConfig,
    EnumDetectionConfig,
    NormalizationConfig,
    ValueExamplesConfig,
)
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


def test_whitespace_normalization_preserves_raw_preview_and_counts_operations(
    tmp_path,
):
    source = tmp_path / "input.csv"
    source.write_text(
        'name,note\n"  Alpha  ","Jean\t  Pierre"\nAlpha,"Jean\u00a0Pierre"\n'
        '   ,"line  one\nline   two"\n',
        encoding="utf-8",
    )

    profile = analyze_csv(source)

    name, note = profile.columns
    assert name.normalization.trim_count == 2
    assert name.normalization.collapse_internal_whitespace_count == 0
    assert name.missing_count == 1
    assert name.distinct_count == 1
    assert name.value_profile.values[0].model_dump() == {
        "value": "Alpha",
        "count": 2,
        "truncated": False,
    }
    assert note.normalization.trim_count == 0
    assert note.normalization.collapse_internal_whitespace_count == 3
    assert note.distinct_count == 2
    assert profile.summary.trim_count == 2
    assert profile.summary.collapse_internal_whitespace_count == 3
    assert profile.preview[0].values == ["  Alpha  ", "Jean\t  Pierre"]
    assert profile.preview[2].values[1].splitlines() == ["line  one", "line   two"]


def test_whitespace_normalization_can_be_disabled():
    profile = analyze_column(
        pd.Series([" 1 ", "1", "a  b", "a b"]),
        config=AnalysisConfig(
            normalization=NormalizationConfig(
                trim=False,
                collapse_internal_whitespace=False,
            )
        ),
    )

    assert profile.normalization.trim_count == 0
    assert profile.normalization.collapse_internal_whitespace_count == 0
    assert profile.distinct_count == 4
    assert profile.inferred_type == "mixed"


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


def test_multiple_strict_date_formats_and_separators_are_counted():
    profile = analyze_column(
        pd.Series(["2024-02-29", "02/29/2024", "29.02.2024", "2025/1/2"])
    )

    assert profile.inferred_type == "date"
    assert profile.date_profile is not None
    assert profile.date_profile.status == "multiple_formats"
    assert profile.date_profile.valid_count == 4
    assert profile.date_profile.ambiguous_count == 0
    assert [item.model_dump() for item in profile.date_profile.formats] == [
        {"order": "DMY", "separator": ".", "count": 1, "iso": False},
        {"order": "MDY", "separator": "/", "count": 1, "iso": False},
        {"order": "YMD", "separator": "-", "count": 1, "iso": True},
        {"order": "YMD", "separator": "/", "count": 1, "iso": False},
    ]


def test_ambiguous_dates_remain_unresolved_without_column_evidence():
    profile = analyze_column(pd.Series(["02/03/2025", "11/12/2025"]))

    assert profile.inferred_type == "text"
    assert profile.date_profile is not None
    assert profile.date_profile.status == "ambiguous"
    assert profile.date_profile.valid_count == 0
    assert profile.date_profile.ambiguous_count == 2
    assert profile.date_profile.resolved_ambiguous_order is None


def test_unambiguous_column_evidence_resolves_dates_consistently():
    profile = analyze_column(pd.Series(["13/02/2025", "02/03/2025"]))

    assert profile.inferred_type == "date"
    assert profile.date_profile is not None
    assert profile.date_profile.status == "valid"
    assert profile.date_profile.valid_count == 2
    assert profile.date_profile.resolved_ambiguous_order == "DMY"
    assert profile.date_profile.ambiguous_order_source == "column"
    assert profile.date_profile.formats[0].model_dump() == {
        "order": "DMY",
        "separator": "/",
        "count": 2,
        "iso": False,
    }


def test_configured_date_order_resolves_otherwise_ambiguous_values():
    profile = analyze_column(
        pd.Series(["02-03-2025", "11-12-2025"]),
        config=AnalysisConfig(
            date_detection=DateDetectionConfig(ambiguous_order="MDY")
        ),
    )

    assert profile.inferred_type == "date"
    assert profile.date_profile is not None
    assert profile.date_profile.valid_count == 2
    assert profile.date_profile.resolved_ambiguous_order == "MDY"
    assert profile.date_profile.ambiguous_order_source == "config"


def test_mixed_date_column_reports_calendar_structure_and_text_errors():
    profile = analyze_column(
        pd.Series(["2025-01-01", "2025-02-30", "2025/01-02", "hello"])
    )

    assert profile.inferred_type == "mixed"
    assert profile.date_profile is not None
    assert profile.date_profile.status == "mixed"
    assert profile.date_profile.valid_count == 1
    assert profile.date_profile.invalid_date_count == 2
    assert profile.date_profile.not_date_count == 1
    assert profile.date_profile.errors == {
        "invalid_calendar_date": 1,
        "mixed_separators": 1,
    }


def test_conflicting_date_orders_do_not_resolve_ambiguous_values():
    profile = analyze_column(
        pd.Series(["13/02/2025", "02/13/2025", "02/03/2025"])
    )

    assert profile.inferred_type == "mixed"
    assert profile.date_profile is not None
    assert profile.date_profile.valid_count == 2
    assert profile.date_profile.ambiguous_count == 1
    assert profile.date_profile.resolved_ambiguous_order is None


def test_date_detection_can_be_disabled():
    profile = analyze_column(
        pd.Series(["2025-01-01"]),
        config=AnalysisConfig(date_detection=DateDetectionConfig(enabled=False)),
    )

    assert profile.inferred_type == "text"
    assert profile.date_profile is None


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


def test_low_cardinality_values_include_complete_occurrence_counts():
    profile = analyze_column(pd.Series(["beta", "alpha", "beta", "", "alpha", "beta"]))

    assert profile.value_profile.selection == "complete"
    assert [item.model_dump() for item in profile.value_profile.values] == [
        {"value": "beta", "count": 3, "truncated": False},
        {"value": "alpha", "count": 2, "truncated": False},
    ]
    assert profile.examples == ["beta", "alpha"]


def test_high_cardinality_short_text_uses_reproducible_diverse_sample():
    values = [f"item-{index:03}" for index in range(120)]
    config = AnalysisConfig(
        value_examples=ValueExamplesConfig(
            candidate_sample_size=80,
            short_text_result_size=12,
            random_seed=7,
        )
    )

    first = analyze_column(pd.Series(values), config=config)
    second = analyze_column(pd.Series(values), config=config)

    assert first.value_profile == second.value_profile
    assert first.value_profile.selection == "diverse_sample"
    assert first.value_profile.sampled_distinct_count == 80
    assert len(first.value_profile.values) == 12
    assert len({item.value for item in first.value_profile.values}) == 12


def test_visible_examples_are_the_most_frequent_values():
    values = [f"item-{index:03}" for index in range(60)]
    values += ["popular"] * 8 + ["common"] * 5 + ["regular"] * 3

    profile = analyze_column(pd.Series(values))

    assert profile.examples == ["popular", "common", "regular"]
    assert [(item.value, item.count) for item in profile.value_profile.values[:3]] == [
        ("popular", 8),
        ("common", 5),
        ("regular", 3),
    ]
    assert [item.count for item in profile.value_profile.values] == sorted(
        (item.count for item in profile.value_profile.values), reverse=True
    )


def test_high_cardinality_long_text_uses_bounded_truncated_sample():
    values = [f"value-{index:03}-" + "x" * 40 for index in range(120)]
    config = AnalysisConfig(
        value_examples=ValueExamplesConfig(
            long_text_result_size=7,
            long_text_truncate_at=15,
            truncation_suffix="[...]",
        )
    )

    profile = analyze_column(pd.Series(values), config=config)

    assert profile.value_profile.selection == "random_sample"
    assert len(profile.value_profile.values) == 7
    assert all(item.truncated for item in profile.value_profile.values)
    assert all(len(item.value) == 20 for item in profile.value_profile.values)


def test_enum_is_a_semantic_candidate_with_coverage_and_confidence():
    values = ["open", "closed"] * 225 + [""] * 50
    profile = analyze_column(pd.Series(values))

    assert profile.inferred_type == "text"
    assert profile.semantic_type == "enum"
    assert profile.enum is not None
    assert profile.enum.status == "candidate"
    assert profile.enum.observed_distinct_count == 2
    assert profile.enum.non_missing_count == 450
    assert profile.enum.coverage_percent == 90.0
    assert profile.enum.confidence == 0.9


def test_enum_threshold_type_and_case_sensitivity_are_configurable():
    below_minimum = analyze_column(pd.Series(["a"] * 499))
    numeric = analyze_column(pd.Series(["1", "2"] * 250))
    exact = analyze_column(pd.Series([f"Value-{index}" for index in range(50)] * 10))
    insensitive = analyze_column(
        pd.Series(["OPEN", "open"] * 250),
        config=AnalysisConfig(
            enum_detection=EnumDetectionConfig(
                maximum_distinct_values=1,
                case_sensitive=False,
            )
        ),
    )

    assert below_minimum.semantic_type is None
    assert numeric.semantic_type is None
    assert exact.semantic_type is None
    assert insensitive.semantic_type == "enum"

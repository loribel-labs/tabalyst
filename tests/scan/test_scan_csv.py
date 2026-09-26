"""Scan contract: CSV reading, scope, presence and configuration (lot 1a)."""

import hashlib
import json
from pathlib import Path

import pytest
from scan_helpers import dataset, field, run_scan, write_text

from tabalyst import InputError

pytestmark = pytest.mark.lot("1a")


def test_csv_source_is_one_table_dataset_with_positional_fields(tmp_path):
    source = write_text(tmp_path, "people.csv", "id,name\n1,Ana\n2,Bob\n")

    result = run_scan(source)

    assert result["format"] == "tabalyst.scan"
    assert result["format_version"] == "0.1.0a"
    assert result["format_revision"] == 1
    assert result["status"] == "complete"
    assert result["source"]["format"] == "csv"
    assert result["source"]["name"] == "people.csv"
    assert result["source"]["size_bytes"] == source.stat().st_size
    assert result["source"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert [item["id"] for item in result["datasets"]] == ["rows"]
    rows = dataset(result, "rows")
    assert rows["kind"] == "table"
    assert rows["collection_path"] is None
    assert rows["record_count"] == 2
    assert rows["record_types"] == {"object": 2}
    name = field(rows, "name")
    assert name["id"] == "column_2"
    assert name["path"] == [{"column": 2}]
    assert name["name"] == "name"
    assert name["first_record"] == 1
    assert name["occurrences"] == 2
    assert name["presence"] == {
        "parent_type": "object",
        "parent_count": 2,
        "present": 2,
        "absent": 0,
    }
    assert name["native_types"] == {"string": 2}


def test_late_anomaly_belongs_to_the_analyzed_scope(tmp_path):
    """CA01: the last record is analyzed like the first ones."""
    numbers = "\n".join(str(number) for number in range(1, 20))
    source = write_text(tmp_path, "amounts.csv", f"amount\n{numbers}\nabc\n")

    result = run_scan(source)

    assert result["scope"]["records_read"] == 20
    assert result["scope"]["records_analyzed"] == 20
    assert result["scope"]["records_excluded"] == 0
    amount = field(dataset(result, "rows"), "amount")
    assert amount["strings"]["content"] == 20
    assert amount["values"]["count"] == 20


def test_string_categories_are_disjoint_and_missing_is_derived(tmp_path):
    """EF08 and O04: empty, blank, marker and content never overlap."""
    source = write_text(tmp_path, "values.csv", 'value\n""\n"  "\n NULL \nx\n')

    default = field(dataset(run_scan(source), "rows"), "value")
    with_marker = field(
        dataset(run_scan(source, values={"null_markers": ["NULL"]}), "rows"),
        "value",
    )

    assert default["strings"] == {
        "count": 4,
        "empty": 1,
        "blank": 1,
        "marker": 0,
        "content": 2,
    }
    assert with_marker["strings"] == {
        "count": 4,
        "empty": 1,
        "blank": 1,
        "marker": 1,
        "content": 1,
    }
    assert with_marker["values"]["count"] == 1
    assert with_marker["missing"] == {
        "count": 3,
        "definition": ["absent", "null", "empty", "blank", "marker"],
        "components": {"absent": 0, "null": 0, "empty": 1, "blank": 1, "marker": 1},
    }


def test_duplicate_and_blank_headers_keep_distinct_identities(tmp_path):
    """O02: CSV identities are positional; displays stay unambiguous labels."""
    source = write_text(tmp_path, "headers.csv", "id,name,name,\n1,a,b,c\n")

    fields = dataset(run_scan(source), "rows")["fields"]

    assert [item["id"] for item in fields] == [
        "column_1",
        "column_2",
        "column_3",
        "column_4",
    ]
    assert [item["path"] for item in fields] == [
        [{"column": 1}],
        [{"column": 2}],
        [{"column": 3}],
        [{"column": 4}],
    ]
    assert [item["name"] for item in fields] == ["id", "name", "name", ""]
    assert [item["display"] for item in fields] == ["id", "name#2", "name#3", "#4"]


def test_strict_policy_stops_on_a_record_of_unexpected_width(tmp_path):
    source = write_text(tmp_path, "ragged.csv", "a,b\n1,2\n3\n4,5,6\n7,8\n")

    with pytest.raises(InputError, match="record 2"):
        run_scan(source)


def test_tolerant_policy_excludes_malformed_records_visibly(tmp_path):
    """CA18 and EF05: exclusions are counted, located and change the status."""
    source = write_text(tmp_path, "ragged.csv", "a,b\n1,2\n3\n4,5,6\n7,8\n")

    result = run_scan(source, errors={"policy": "tolerant"})

    assert result["status"] == "partial"
    assert result["scope"]["records_read"] == 4
    assert result["scope"]["records_analyzed"] == 2
    assert result["scope"]["records_excluded"] == 2
    assert result["scope"]["exclusions"] == {"width_mismatch": 2}
    rows = dataset(result, "rows")
    assert rows["record_count"] == 2
    assert field(rows, "a")["presence"]["present"] == 2
    [diagnostic] = [
        item for item in result["diagnostics"] if item["code"] == "csv_width_mismatch"
    ]
    assert diagnostic["level"] == "error"
    assert diagnostic["count"] == 2
    assert diagnostic["locations"] == [
        {"record": 2, "line": 3},
        {"record": 3, "line": 4},
    ]


def test_header_only_csv_has_fields_without_records(tmp_path):
    """O15: an empty dataset is a result, not an error."""
    source = write_text(tmp_path, "empty.csv", "a,b\n")

    rows = dataset(run_scan(source), "rows")

    assert rows["record_count"] == 0
    assert [item["display"] for item in rows["fields"]] == ["a", "b"]
    assert field(rows, "a")["presence"] == {
        "parent_type": "object",
        "parent_count": 0,
        "present": 0,
        "absent": 0,
    }
    assert field(rows, "a")["first_record"] is None


def test_empty_file_is_an_input_error(tmp_path):
    source = write_text(tmp_path, "nothing.csv", "")

    with pytest.raises(InputError):
        run_scan(source)


def test_scan_runs_without_cli_or_html_and_round_trips(tmp_path):
    """CA06: a typed, serializable result produced without writing files."""
    from tabalyst.scanner import ScanResult, scan

    source = write_text(tmp_path, "people.csv", "id,name\n1,Ana\n")

    result = scan(source)

    assert isinstance(result, ScanResult)
    assert ScanResult.model_validate_json(result.model_dump_json()) == result
    assert sorted(path.name for path in tmp_path.iterdir()) == ["people.csv"]


def test_result_embeds_effective_configuration_and_its_fingerprint(tmp_path):
    """EF42: the configuration identity is the SHA-256 of its canonical JSON."""
    source = write_text(tmp_path, "people.csv", "id\n1\n")

    result = run_scan(source, limits={"max_samples": 7})

    assert result["config"]["limits"]["max_samples"] == 7
    canonical = json.dumps(
        result["config"], sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert result["config_sha256"] == expected


def test_configuration_enforces_hard_caps_and_rejects_unknown_keys():
    """CA13: user values change behavior only within protected limits."""
    from tabalyst.scanner import ScanConfig

    config = ScanConfig.model_validate({"limits": {"max_distinct_per_field": 5}})
    assert config.limits.max_distinct_per_field == 5
    assert config.limits.max_fields == 10_000

    with pytest.raises(ValueError):
        ScanConfig.model_validate({"limits": {"max_distinct_per_field": 10**9}})
    with pytest.raises(ValueError):
        ScanConfig.model_validate({"limits": {"max_distinct_per_field": 3_000_000}})
    with pytest.raises(ValueError):
        ScanConfig.model_validate({"limitz": {}})


def test_scanner_package_does_not_import_pandas():
    """ET04: the engine contract is not centered on a DataFrame."""
    package = Path(__file__).parents[2] / "src" / "tabalyst" / "scanner"
    sources = list(package.rglob("*.py"))

    assert sources
    for path in sources:
        content = path.read_text(encoding="utf-8")
        assert "import pandas" not in content, path
        assert "from pandas" not in content, path

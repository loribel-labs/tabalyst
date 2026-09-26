import csv
import json
from collections import Counter

import pytest
from typer.testing import CliRunner

import tabalyst
from tabalyst.cli import app
from tabalyst.errors import InputError, ReportError

runner = CliRunner()


def _write_csv(path, rows, headers=("id", "region", "note")):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        writer.writerows(rows)


def _read_csv(path):
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.reader(stream))


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "data.csv"
    rows = [
        (str(index), "Quebec" if index < 60 else "Ontario", f"value {index}")
        for index in range(100)
    ]
    _write_csv(path, rows)
    return path


def test_first_and_last_with_rows_preserve_header_and_columns(source, tmp_path):
    first = tmp_path / "first.csv"
    last = tmp_path / "last.csv"

    tabalyst.sample_csv(source, method="first", rows=3, output=first)
    tabalyst.sample_csv(source, method="last", rows=3, output=last)

    assert _read_csv(first) == [
        ["id", "region", "note"],
        ["0", "Quebec", "value 0"],
        ["1", "Quebec", "value 1"],
        ["2", "Quebec", "value 2"],
    ]
    assert [row[0] for row in _read_csv(last)[1:]] == ["97", "98", "99"]


def test_random_supports_rows_percent_and_reproducible_seed(source, tmp_path):
    by_rows = tmp_path / "rows.csv"
    by_percent = tmp_path / "percent.csv"
    repeated = tmp_path / "repeated.csv"

    tabalyst.sample_csv(source, method="random", rows=10, seed=42, output=by_rows)
    result = tabalyst.sample_csv(
        source, method="random", percent=10, seed=42, output=by_percent
    )
    tabalyst.sample_csv(source, method="random", rows=10, seed=42, output=repeated)

    assert result.sample_rows == 10
    assert _read_csv(by_rows) == _read_csv(by_percent) == _read_csv(repeated)


def test_stratified_rows_percent_proportions_and_seed(source, tmp_path):
    by_rows = tmp_path / "rows.csv"
    by_percent = tmp_path / "percent.csv"
    repeated = tmp_path / "repeated.csv"

    tabalyst.sample_csv(
        source,
        method="stratified",
        field="region",
        rows=20,
        seed=7,
        output=by_rows,
    )
    tabalyst.sample_csv(
        source,
        method="stratified",
        field="region",
        percent=20,
        seed=7,
        output=by_percent,
    )
    tabalyst.sample_csv(
        source,
        method="stratified",
        field="region",
        rows=20,
        seed=7,
        output=repeated,
    )

    sampled = _read_csv(by_rows)
    assert _read_csv(by_percent) == sampled == _read_csv(repeated)
    assert Counter(row[1] for row in sampled[1:]) == {"Quebec": 12, "Ontario": 8}


def test_stratified_handles_small_strata_and_empty_values(tmp_path):
    source = tmp_path / "strata.csv"
    rows = [(str(i), "common", "") for i in range(8)]
    rows.extend([("8", "rare", ""), ("9", "", "")])
    _write_csv(source, rows)
    output = tmp_path / "sample.csv"

    tabalyst.sample_csv(
        source,
        method="stratified",
        field="region",
        percent=80,
        seed=9,
        output=output,
    )

    sampled = _read_csv(output)
    assert sampled[0] == ["id", "region", "note"]
    assert Counter(row[1] for row in sampled[1:]) == {
        "common": 6,
        "rare": 1,
        "": 1,
    }


def test_percent_rounds_up_and_hundred_percent_keeps_all_rows(source, tmp_path):
    tiny = tmp_path / "tiny.csv"
    full = tmp_path / "full.csv"

    tiny_result = tabalyst.sample_csv(
        source, method="first", percent=0.1, output=tiny
    )
    full_result = tabalyst.sample_csv(
        source, method="random", percent=100, seed=2, output=full
    )

    assert tiny_result.sample_rows == 1
    assert full_result.sample_rows == 100
    assert _read_csv(full)[1:] == _read_csv(source)[1:]


def test_output_preserves_utf8_bom_presence_and_configured_encoding(tmp_path):
    plain = tmp_path / "plain.csv"
    plain.write_text("name\nQuébec\n", encoding="utf-8")
    with_bom = tmp_path / "bom.csv"
    with_bom.write_text("name\nQuébec\n", encoding="utf-8-sig")
    legacy = tmp_path / "legacy.csv"
    legacy.write_text("name\nQuébec\n", encoding="cp1252")

    plain_result = tabalyst.sample_csv(plain, method="first", rows=1)
    bom_result = tabalyst.sample_csv(with_bom, method="first", rows=1)
    legacy_result = tabalyst.sample_csv(
        legacy, method="first", rows=1, encoding="cp1252"
    )

    assert not plain_result.output.read_bytes().startswith(b"\xef\xbb\xbf")
    assert bom_result.output.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "Québec" in legacy_result.output.read_text(encoding="cp1252")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"method": "first"}, "exactly one"),
        ({"method": "first", "rows": 1, "percent": 2}, "exactly one"),
        ({"method": "first", "rows": 0}, "greater than 0"),
        ({"method": "first", "percent": 0}, "greater than 0"),
        ({"method": "first", "percent": 101}, "at most 100"),
        ({"method": "stratified", "rows": 1}, "--field is required"),
        ({"method": "first", "rows": 101}, "exceeds available"),
        (
            {"method": "stratified", "field": "missing", "rows": 1},
            "does not exist",
        ),
        ({"method": "first", "rows": 1, "output": "sample.txt"}, "ending in .csv"),
    ],
)
def test_invalid_requests_are_rejected(source, kwargs, message):
    with pytest.raises(InputError, match=message):
        tabalyst.sample_csv(source, **kwargs)


def test_empty_and_header_only_files(tmp_path):
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    header_only = tmp_path / "header.csv"
    header_only.write_text("id,name\n", encoding="utf-8")

    with pytest.raises(InputError, match="empty or has no header"):
        tabalyst.sample_csv(empty, method="first", rows=1)
    with pytest.raises(InputError, match="exceeds available"):
        tabalyst.sample_csv(header_only, method="first", rows=1)

    output = tmp_path / "header_sample.csv"
    result = tabalyst.sample_csv(
        header_only, method="random", percent=100, seed=1, output=output
    )
    assert result.sample_rows == 0
    assert _read_csv(output) == [["id", "name"]]


def test_output_defaults_and_never_overwrites_source_or_existing_file(source):
    result = tabalyst.sample_csv(source, method="first", rows=2)
    assert result.output == source.with_name("data.sample.csv")

    with pytest.raises(InputError, match="cannot overwrite"):
        tabalyst.sample_csv(
            source, method="first", rows=2, output=source, force=True
        )
    with pytest.raises(ReportError, match="already exists"):
        tabalyst.sample_csv(source, method="first", rows=2)


def test_cli_creates_sample_and_prints_summary(source, tmp_path):
    output = tmp_path / "chosen.csv"
    result = runner.invoke(
        app,
        [
            "sample",
            str(source),
            "--sample-method",
            "stratified",
            "--field",
            "region",
            "--rows",
            "10",
            "--seed",
            "42",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert "Sample created successfully." in result.stderr
    assert "Method:        stratified" in result.stderr
    assert "Field:         region" in result.stderr
    assert "Sample rows:   10" in result.stderr
    assert "Seed:          42" in result.stderr
    assert output.is_file()


def test_cli_rejects_unknown_method(source):
    result = runner.invoke(
        app,
        ["sample", str(source), "--sample-method", "unknown", "--rows", "2"],
    )
    assert result.exit_code == 2
    assert "Invalid value" in result.output


def test_cli_glob_uses_default_names_in_output_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_csv(tmp_path / "b.csv", [("2", "west", "b")])
    _write_csv(tmp_path / "a.csv", [("1", "east", "a")])

    result = runner.invoke(
        app,
        ["sample", "*.csv", "--sample-method", "first", "--rows", "1", "-d", "out"],
    )

    assert result.exit_code == 0, result.output
    assert (tmp_path / "out/a.sample.csv").is_file()
    assert (tmp_path / "out/b.sample.csv").is_file()
    assert "2 succeeded, 0 failed" in result.stderr


def test_cli_output_accepts_only_one_input(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_csv(tmp_path / "a.csv", [("1", "east", "a")])
    _write_csv(tmp_path / "b.csv", [("2", "west", "b")])

    result = runner.invoke(
        app,
        [
            "sample",
            "*.csv",
            "--sample-method",
            "first",
            "--rows",
            "1",
            "-o",
            "one.csv",
        ],
    )
    assert result.exit_code == 2
    assert "only be used with one input" in result.output
    assert not (tmp_path / "one.csv").exists()


def test_cli_output_and_output_dir_are_mutually_exclusive(source, tmp_path):
    result = runner.invoke(
        app,
        [
            "sample",
            str(source),
            "--sample-method",
            "first",
            "--rows",
            "1",
            "-o",
            str(tmp_path / "one.csv"),
            "-d",
            str(tmp_path / "out"),
        ],
    )
    assert result.exit_code == 2
    assert "cannot be used together" in result.output


def test_cli_uses_config_with_explicit_csv_overrides(tmp_path):
    source = tmp_path / "data.csv"
    source.write_text("id;name\n1;Québec\n", encoding="cp1252")
    config = tmp_path / "tabalyst.json"
    config.write_text(
        json.dumps({"csv": {"delimiter": ";", "encoding": "cp1252"}}),
        encoding="utf-8",
    )
    output = tmp_path / "sample.csv"

    result = runner.invoke(
        app,
        [
            "sample",
            str(source),
            "--sample-method",
            "first",
            "--rows",
            "1",
            "--config",
            str(config),
            "-o",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    with output.open("r", encoding="cp1252", newline="") as stream:
        assert list(csv.reader(stream, delimiter=";")) == [
            ["id", "name"],
            ["1", "Québec"],
        ]

import json

import pytest
from typer.testing import CliRunner

from tabalyst.cli import app
from tabalyst.config import load_config
from tabalyst.execution_log import tabalyst_version

runner = CliRunner()


def test_source_checkout_reports_pyproject_version():
    assert tabalyst_version() == "0.2.0"


def test_root_help_and_version_describe_the_toolkit():
    help_result = runner.invoke(app, ["--help"])
    assert help_result.exit_code == 0
    assert "Tools for unfamiliar data" in help_result.output
    assert "report" in help_result.output

    version_result = runner.invoke(app, ["--version"])
    assert version_result.exit_code == 0
    assert version_result.output.strip() == "0.2.0"


def test_report_generates_html_json_and_history(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("id,amount\n001,3\n002,4\n", encoding="utf-8")
    html = tmp_path / "output/report.html"

    result = runner.invoke(app, ["report", str(source), "-o", str(html)])

    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert "2 rows and 2 columns" in result.stderr
    profile_json = html.with_suffix(".json")
    data = json.loads(profile_json.read_text(encoding="utf-8"))
    assert data["preview"][0]["values"][0] == "001"
    generated_html = html.read_text(encoding="utf-8")
    assert "Tabalyst Design Model · Signature v1.0" in generated_html
    assert "cdn." not in generated_html
    assert (html.parent / "executions.json").is_file()


def test_report_uses_source_stem_when_output_is_omitted(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("a\n1\n", encoding="utf-8")

    result = runner.invoke(app, ["report", str(source)])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "input.html").is_file()
    assert (tmp_path / "input.json").is_file()
    assert (tmp_path / "executions.json").is_file()


def test_multiple_inputs_use_source_stems_in_output_directory(tmp_path):
    first = tmp_path / "customers.csv"
    second = tmp_path / "orders.csv"
    first.write_text("id\n1\n", encoding="utf-8")
    second.write_text("id\n2\n", encoding="utf-8")
    reports = tmp_path / "reports"

    result = runner.invoke(
        app,
        ["report", str(first), str(second), "-d", str(reports)],
    )

    assert result.exit_code == 0, result.output
    assert (reports / "customers.html").is_file()
    assert (reports / "customers.json").is_file()
    assert (reports / "orders.html").is_file()
    assert (reports / "orders.json").is_file()
    assert "2 succeeded, 0 failed" in result.stderr


@pytest.mark.parametrize("directory", ["reports", "reports/"])
def test_output_dir_accepts_optional_trailing_separator(
    tmp_path, monkeypatch, directory
):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "data.csv"
    source.write_text("id\n1\n", encoding="utf-8")

    result = runner.invoke(app, ["report", "data.csv", "-d", directory])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "reports/data.html").is_file()


def test_native_glob_is_sorted_and_deduplicated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "b.csv").write_text("id\n2\n", encoding="utf-8")
    (tmp_path / "a.csv").write_text("id\n1\n", encoding="utf-8")

    result = runner.invoke(
        app,
        ["report", "*.csv", "a.csv", "-d", "reports"],
    )

    assert result.exit_code == 0, result.output
    assert (tmp_path / "reports/a.html").is_file()
    assert (tmp_path / "reports/b.html").is_file()
    history = json.loads(
        (tmp_path / "reports/executions.json").read_text(encoding="utf-8")
    )
    assert [entry["source_file"] for entry in history["executions"]] == [
        "a.csv",
        "b.csv",
    ]


def test_unmatched_glob_is_an_input_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["report", "*.csv", "-d", "reports"])

    assert result.exit_code == 4
    assert "matched no files" in result.output


def test_output_file_is_rejected_for_multiple_inputs(tmp_path):
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    first.write_text("id\n1\n", encoding="utf-8")
    second.write_text("id\n2\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "report",
            str(first),
            str(second),
            "-o",
            str(tmp_path / "report.html"),
        ],
    )

    assert result.exit_code == 2
    assert "only be used with one input" in result.output
    assert not (tmp_path / "report.html").exists()


def test_output_and_output_dir_are_mutually_exclusive(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("id\n1\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "report",
            str(source),
            "-o",
            str(tmp_path / "report.html"),
            "-d",
            str(tmp_path / "reports"),
        ],
    )

    assert result.exit_code == 2
    assert "cannot be used together" in result.output


def test_output_dir_collision_stops_batch_before_processing(tmp_path):
    france = tmp_path / "france"
    canada = tmp_path / "canada"
    france.mkdir()
    canada.mkdir()
    first = france / "data.csv"
    second = canada / "data.csv"
    first.write_text("id\n1\n", encoding="utf-8")
    second.write_text("id\n2\n", encoding="utf-8")
    reports = tmp_path / "reports"

    result = runner.invoke(
        app,
        ["report", str(first), str(second), "-d", str(reports)],
    )

    assert result.exit_code == 1
    assert "Output name collision" in result.output
    assert not reports.exists()


def test_existing_output_stops_entire_batch_without_force(tmp_path):
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    first.write_text("id\n1\n", encoding="utf-8")
    second.write_text("id\n2\n", encoding="utf-8")
    reports = tmp_path / "reports"
    reports.mkdir()
    existing = reports / "second.html"
    existing.write_text("keep", encoding="utf-8")

    result = runner.invoke(
        app,
        ["report", str(first), str(second), "-d", str(reports)],
    )

    assert result.exit_code == 1
    assert "already exists" in result.output
    assert not (reports / "first.html").exists()
    assert existing.read_text(encoding="utf-8") == "keep"


def test_batch_continues_after_invalid_input_and_returns_nonzero(tmp_path):
    good = tmp_path / "good.csv"
    bad = tmp_path / "bad.csv"
    good.write_text("a,b\n1,2\n", encoding="utf-8")
    bad.write_text("a,b\n1,2,3\n", encoding="utf-8")
    reports = tmp_path / "reports"

    result = runner.invoke(
        app,
        ["report", str(bad), str(good), "-d", str(reports)],
    )

    assert result.exit_code == 4
    assert (reports / "good.html").is_file()
    assert not (reports / "bad.html").exists()
    assert "Error" in result.stderr
    assert "1 succeeded, 1 failed" in result.stderr


def test_legacy_direct_and_analyze_syntax_are_not_available(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("a\n1\n", encoding="utf-8")

    direct = runner.invoke(app, [str(source), str(tmp_path / "report.html")])
    analyze = runner.invoke(
        app, ["analyze", str(source), "-o", str(tmp_path / "report.html")]
    )

    assert direct.exit_code == 2
    assert analyze.exit_code == 2


def test_source_file_cannot_be_overwritten(tmp_path):
    source = tmp_path / "input.html"
    content = "a,b\n1,2\n"
    source.write_text(content, encoding="utf-8")

    result = runner.invoke(app, ["report", str(source), "-o", str(source)])

    assert result.exit_code == 4
    assert "overwrite an input" in result.output
    assert source.read_text(encoding="utf-8") == content


def test_existing_report_requires_force(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("a,b\n1,2\n", encoding="utf-8")
    output = tmp_path / "report.html"

    first = runner.invoke(app, ["report", str(source), "-o", str(output)])
    blocked = runner.invoke(app, ["report", str(source), "-o", str(output)])
    replaced = runner.invoke(
        app, ["report", str(source), "-o", str(output), "--force"]
    )

    assert first.exit_code == 0, first.output
    assert blocked.exit_code == 1
    assert "already exists" in blocked.output
    assert replaced.exit_code == 0, replaced.output


def test_bad_csv_returns_input_exit_code_without_artifacts(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("a,b\n1,2,3\n", encoding="utf-8")
    output = tmp_path / "report.html"

    result = runner.invoke(app, ["report", str(source), "-o", str(output)])

    assert result.exit_code == 4
    assert "Data record 1" in result.output
    assert not output.exists()
    assert not output.with_suffix(".json").exists()
    assert not output.with_name("executions.json").exists()


def test_config_and_cli_input_overrides_are_applied(tmp_path):
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "csv": {"delimiter": ";", "encoding": "cp1252"},
                "missing_values": ["", "NULL"],
                "preview_rows": 0,
            }
        )
    )
    source = tmp_path / "input.csv"
    source.write_text("a,b\n1,NULL\n2,ok\n", encoding="utf-8")
    output = tmp_path / "report.html"

    result = runner.invoke(
        app,
        [
            "report",
            str(source),
            "--config",
            str(config),
            "--delimiter",
            ",",
            "--encoding",
            "utf-8",
            "-o",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    data = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
    assert data["summary"]["missing_count"] == 1
    assert data["preview"] == []
    assert data["source"]["delimiter"] == ","
    assert data["source"]["encoding"] == "utf-8"


def test_quiet_and_verbose_control_diagnostics(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("a\n1\n", encoding="utf-8")
    quiet_output = tmp_path / "quiet.html"
    verbose_output = tmp_path / "verbose.html"

    quiet = runner.invoke(
        app, ["report", str(source), "-o", str(quiet_output), "--quiet"]
    )
    verbose = runner.invoke(
        app, ["report", str(source), "-o", str(verbose_output), "--verbose"]
    )

    assert quiet.exit_code == 0, quiet.output
    assert quiet.stdout == ""
    assert quiet.stderr == ""
    assert verbose.exit_code == 0, verbose.output
    assert verbose.stdout == ""
    assert "Encoding: utf-8-sig" in verbose.stderr
    assert "Delimiter: ','" in verbose.stderr
    assert "Execution history:" in verbose.stderr


def test_quiet_and_verbose_are_mutually_exclusive(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("a\n1\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "report",
            str(source),
            "-o",
            str(tmp_path / "report.html"),
            "--quiet",
            "--verbose",
        ],
    )

    assert result.exit_code == 2
    assert "cannot be used together" in result.output


def test_execution_history_accumulates_named_reports(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    first_source = tmp_path / "data.csv"
    second_source = tmp_path / "data2.csv"
    first_source.write_text("name\nalpha\nbeta\n", encoding="utf-8")
    second_source.write_text("name\ngamma\n", encoding="utf-8")
    output_folder = tmp_path / "reports"

    first = runner.invoke(
        app,
        ["report", str(first_source), "-o", str(output_folder / "report1.html")],
    )
    second = runner.invoke(
        app,
        ["report", str(second_source), "-o", str(output_folder / "report2.html")],
    )

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    history = json.loads(
        (output_folder / "executions.json").read_text(encoding="utf-8")
    )
    assert history["schema_version"] == "1.0"
    assert [item["source_file"] for item in history["executions"]] == [
        "data.csv",
        "data2.csv",
    ]


def test_nested_configuration_sections_merge_recursively(tmp_path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text(
        json.dumps(
            {
                "value_examples": {
                    "candidate_sample_size": 25,
                    "short_text_result_size": 8,
                }
            }
        )
    )
    second.write_text(json.dumps({"value_examples": {"candidate_sample_size": 40}}))

    config = load_config([first, second])

    assert config.value_examples.candidate_sample_size == 40
    assert config.value_examples.short_text_result_size == 8
    assert config.value_examples.long_text_result_size == 20


@pytest.mark.parametrize(
    "content",
    [
        '{"unexpected": true}',
        "[1, 2]",
        '{"csv": {"delimiter": "||"}}',
        '{"date_detection": {"separators": ["--"]}}',
        '{"date_detection": {"orders": ["YMD"], "ambiguous_order": "DMY"}}',
    ],
)
def test_invalid_config_is_rejected(tmp_path, content):
    config = tmp_path / "config.json"
    config.write_text(content)
    with pytest.raises(ValueError):
        load_config([config])

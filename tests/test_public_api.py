import json

import pytest
from typer.testing import CliRunner

import tabalyst
from tabalyst.cli import official_app

runner = CliRunner()


def test_public_api_writes_canonical_reports_and_execution_history(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("id,name\n001,Alice\n002,Bob\n", encoding="utf-8")
    report = tmp_path / "nested" / "client-a.html"

    result = tabalyst.analyze(source, report)

    json_report = report.with_suffix(".json")
    execution_report = report.parent / "executions.json"
    assert report.is_file()
    assert json_report.is_file()
    assert execution_report.is_file()
    assert result == json.loads(json_report.read_text(encoding="utf-8"))
    assert f"v{tabalyst.__version__}" in report.read_text(encoding="utf-8")
    history = json.loads(execution_report.read_text(encoding="utf-8"))
    assert history["executions"][0]["html_file"] == "client-a.html"
    assert history["executions"][0]["json_file"] == "client-a.json"


def test_config_encoding_and_explicit_separator_precedence(tmp_path):
    configured_source = tmp_path / "configured.csv"
    configured_source.write_bytes("city;value\nMontréal;1\n".encode("cp1252"))
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps({"csv": {"delimiter": ";", "encoding": "cp1252"}}),
        encoding="utf-8",
    )

    configured = tabalyst.analyze(
        configured_source,
        tmp_path / "configured.html",
        config_path=config,
    )
    assert configured["source"]["delimiter"] == ";"
    assert configured["source"]["encoding"] == "cp1252"
    assert configured["preview"][0]["values"][0] == "Montréal"

    explicit_source = tmp_path / "explicit.csv"
    explicit_source.write_text("city|value\nQuébec|2\n", encoding="utf-8")
    explicit = tabalyst.analyze(
        explicit_source,
        tmp_path / "explicit.html",
        separator="|",
        encoding="utf-8",
        config_path=config,
    )
    assert explicit["source"]["delimiter"] == "|"
    assert explicit["source"]["encoding"] == "utf-8"


@pytest.mark.parametrize("report_name", ["report", "report.json", "report.htm"])
def test_public_api_requires_html_report_path(tmp_path, report_name):
    source = tmp_path / "input.csv"
    source.write_text("a\n1\n", encoding="utf-8")

    with pytest.raises(tabalyst.InputError, match=r"ending in \.html"):
        tabalyst.analyze(source, tmp_path / report_name)


@pytest.mark.parametrize("content", ['{"seperator": ";"}', "{not-json"])
def test_public_api_reports_missing_input_and_invalid_config(tmp_path, content):
    with pytest.raises(tabalyst.InputError, match="does not exist"):
        tabalyst.analyze(tmp_path / "missing.csv", tmp_path / "report.html")

    source = tmp_path / "input.csv"
    source.write_text("a\n1\n", encoding="utf-8")
    config = tmp_path / "config.json"
    config.write_text(content, encoding="utf-8")
    with pytest.raises(tabalyst.ConfigurationError, match="Invalid configuration"):
        tabalyst.analyze(source, tmp_path / "report.html", config_path=config)


def test_multiple_named_reports_share_execution_history(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("a\n1\n", encoding="utf-8")
    reports = tmp_path / "reports"

    tabalyst.analyze(source, reports / "first.html")
    tabalyst.analyze(source, reports / "second.html")

    assert (reports / "first.json").is_file()
    assert (reports / "second.json").is_file()
    history = json.loads((reports / "executions.json").read_text(encoding="utf-8"))
    assert [item["html_file"] for item in history["executions"]] == [
        "first.html",
        "second.html",
    ]


def test_official_cli_help_version_and_analysis(tmp_path):
    help_result = runner.invoke(official_app, ["--help"])
    assert help_result.exit_code == 0
    assert "CSV_PATH" in help_result.output
    assert "REPORT_PATH" in help_result.output

    version_result = runner.invoke(official_app, ["--version"])
    assert version_result.exit_code == 0
    assert version_result.output.strip() == tabalyst.__version__

    source = tmp_path / "input.csv"
    source.write_text("a;b\n1;2\n", encoding="utf-8")
    report = tmp_path / "cli" / "report.html"
    result = runner.invoke(
        official_app,
        [str(source), str(report), "--separator", ";", "--encoding", "utf-8"],
    )
    assert result.exit_code == 0, result.output
    assert report.is_file()
    assert report.with_suffix(".json").is_file()
    assert (report.parent / "executions.json").is_file()


def test_official_cli_has_concise_user_errors(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("a\n1\n", encoding="utf-8")

    result = runner.invoke(official_app, [str(source), str(tmp_path / "report.txt")])

    assert result.exit_code == 1
    assert "ending in .html" in result.output
    assert "Traceback" not in result.output

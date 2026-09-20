import json

import pytest
from typer.testing import CliRunner

from tabalyst.cli import app
from tabalyst.config import load_config
from tabalyst.execution_log import tabalyst_version

runner = CliRunner()


def test_source_checkout_reports_pyproject_version():
    assert tabalyst_version() == "0.1.0a2"


def test_end_to_end_and_independent_json_render(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("id,amount\n001,3\n002,4\n", encoding="utf-8")
    html = tmp_path / "output/report.html"
    result = runner.invoke(app, ["analyze", str(source), "--output", str(html)])
    assert result.exit_code == 0, result.output
    assert "2 rows and 2 columns" in result.output
    profile_json = html.with_suffix(".json")
    data = json.loads(profile_json.read_text(encoding="utf-8"))
    assert data["preview"][0]["values"][0] == "001"
    expected_html = html.read_text(encoding="utf-8")
    assert "bootstrap@5.3.8" in expected_html
    source.unlink()
    second = tmp_path / "regenerated.html"
    result = runner.invoke(
        app, ["render", str(profile_json), "-o", str(second)]
    )
    assert result.exit_code == 0, result.output
    assert second.read_text(encoding="utf-8") == expected_html


def test_source_file_cannot_be_overwritten(tmp_path):
    source = tmp_path / "input.csv"
    content = "a,b\n1,2\n"
    source.write_text(content, encoding="utf-8")
    result = runner.invoke(app, ["analyze", str(source), "--output", str(source)])
    assert result.exit_code == 1
    assert "overwrite an input" in result.output
    assert source.read_text(encoding="utf-8") == content


def test_execution_filename_cannot_be_used_as_report_output(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("a,b\n1,2\n", encoding="utf-8")
    output = tmp_path / "execution.json"
    result = runner.invoke(app, ["analyze", str(source), "-o", str(output)])
    assert result.exit_code == 1
    assert "different" in result.output
    assert not output.exists()


def test_bad_csv_returns_actionable_error_without_artifacts(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("a,b\n1,2,3\n", encoding="utf-8")
    output = tmp_path / "report.html"
    result = runner.invoke(app, ["analyze", str(source), "-o", str(output)])
    assert result.exit_code == 1
    assert "Data record 1" in result.output
    assert not output.exists()
    assert not output.with_suffix(".json").exists()
    assert not output.with_name("execution.json").exists()


def test_configuration_files_merge_and_cli_options_override(tmp_path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text(
        json.dumps(
            {
                "csv": {"delimiter": ";", "encoding": "cp1252"},
                "missing_values": ["", "NULL"],
            }
        )
    )
    second.write_text(json.dumps({"csv": {"encoding": "utf-8"}, "preview_rows": 1}))
    config = load_config([first, second])
    assert config.csv.delimiter == ";"
    assert config.csv.encoding == "utf-8"
    assert config.missing_values == ["", "NULL"]
    source = tmp_path / "input.csv"
    source.write_text("a,b\n1,NULL\n2,ok\n", encoding="utf-8")
    output = tmp_path / "report.html"
    result = runner.invoke(
        app,
        [
            "analyze",
            str(source),
            "--config",
            str(first),
            "--config",
            str(second),
            "--delimiter",
            ",",
            "--preview-rows",
            "0",
            "-o",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
    assert data["summary"]["missing_count"] == 1
    assert data["preview"] == []


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
    second.write_text(
        json.dumps({"value_examples": {"candidate_sample_size": 40}})
    )

    config = load_config([first, second])

    assert config.value_examples.candidate_sample_size == 40
    assert config.value_examples.short_text_result_size == 8
    assert config.value_examples.long_text_result_size == 20


def test_project_config_is_automatic_and_explicit_config_overrides_it(
    tmp_path, monkeypatch
):
    project_config = tmp_path / "tabalyst.json"
    project_config.write_text(
        json.dumps(
            {
                "preview_rows": 0,
                "normalization": {"trim": False},
                "value_examples": {"short_text_result_size": 17},
            }
        )
    )
    override = tmp_path / "override.json"
    override.write_text(json.dumps({"preview_rows": 1}))
    source = tmp_path / "input.csv"
    source.write_text("name\nalpha\nbeta\n", encoding="utf-8")
    output = tmp_path / "report.html"
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        ["analyze", str(source), "--config", str(override), "-o", str(output)],
    )

    assert result.exit_code == 0, result.output
    data = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
    assert data["config"]["preview_rows"] == 1
    assert data["config"]["normalization"] == {
        "trim": False,
        "collapse_internal_whitespace": True,
    }
    assert data["config"]["value_examples"]["short_text_result_size"] == 17
    assert str(project_config.resolve()) in result.output
    assert str(override.resolve()) in result.output


def test_internal_defaults_apply_outside_a_project_without_config(
    tmp_path, monkeypatch
):
    source = tmp_path / "input.csv"
    source.write_text(
        "name\n" + "\n".join(f"value-{index:03}" for index in range(60)) + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "report.html"
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["analyze", str(source), "-o", str(output)])

    assert result.exit_code == 0, result.output
    assert "Configuration:" not in result.output
    data = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
    settings = data["config"]["value_examples"]
    assert settings["short_text_result_size"] == 20
    assert settings["long_text_result_size"] == 20
    assert len(data["columns"][0]["value_profile"]["values"]) == 20


def test_execution_history_accumulates_named_reports(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    first_source = tmp_path / "data.csv"
    second_source = tmp_path / "data2.csv"
    first_source.write_text("name\nalpha\nbeta\n", encoding="utf-8")
    second_source.write_text("name\ngamma\n", encoding="utf-8")
    output_folder = tmp_path / "reports"

    first = runner.invoke(
        app,
        ["analyze", str(first_source), "-o", str(output_folder / "report1.html")],
    )
    second = runner.invoke(
        app,
        ["analyze", str(second_source), "-o", str(output_folder / "report2.html")],
    )

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    assert (output_folder / "report1.json").is_file()
    assert (output_folder / "report2.json").is_file()
    history = json.loads(
        (output_folder / "execution.json").read_text(encoding="utf-8")
    )
    assert history["schema_version"] == "1.0"
    assert [item["source_file"] for item in history["executions"]] == [
        "data.csv",
        "data2.csv",
    ]
    assert [item["html_file"] for item in history["executions"]] == [
        "report1.html",
        "report2.html",
    ]
    assert [item["json_file"] for item in history["executions"]] == [
        "report1.json",
        "report2.json",
    ]
    for item in history["executions"]:
        assert item["tabalyst_version"]
        assert item["analysis_seconds"] >= 0
        assert item["total_seconds"] >= item["analysis_seconds"]
        assert item["git"] == {
            "available": False,
            "commit": None,
            "dirty": None,
            "state": None,
        }


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

import json

import pytest
from typer.testing import CliRunner

from tabalyst.cli import app
from tabalyst.config import load_config

runner = CliRunner()


def test_end_to_end_and_independent_json_render(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("id,amount\n001,3\n002,4\n", encoding="utf-8")
    html = tmp_path / "output/report.html"
    result = runner.invoke(app, ["analyze", str(source), "--output", str(html)])
    assert result.exit_code == 0, result.output
    assert "2 rows and 2 columns" in result.output
    data = json.loads(html.with_name("dataset.json").read_text(encoding="utf-8"))
    assert data["preview"][0]["values"][0] == "001"
    expected_html = html.read_text(encoding="utf-8")
    assert "bootstrap@5.3.8" in expected_html
    source.unlink()
    second = tmp_path / "regenerated.html"
    result = runner.invoke(
        app, ["render", str(html.with_name("dataset.json")), "-o", str(second)]
    )
    assert result.exit_code == 0, result.output
    assert second.read_text(encoding="utf-8") == expected_html


@pytest.mark.parametrize("option", ["--output", "--json-output"])
def test_source_file_cannot_be_overwritten(tmp_path, option):
    source = tmp_path / "input.csv"
    content = "a,b\n1,2\n"
    source.write_text(content, encoding="utf-8")
    result = runner.invoke(app, ["analyze", str(source), option, str(source)])
    assert result.exit_code == 1
    assert "overwrite an input" in result.output
    assert source.read_text(encoding="utf-8") == content


def test_same_output_paths_are_rejected(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("a,b\n1,2\n", encoding="utf-8")
    output = tmp_path / "same.html"
    result = runner.invoke(
        app, ["analyze", str(source), "-o", str(output), "--json-output", str(output)]
    )
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
    assert not output.with_name("dataset.json").exists()


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
    data = json.loads(output.with_name("dataset.json").read_text(encoding="utf-8"))
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
    data = json.loads(output.with_name("dataset.json").read_text(encoding="utf-8"))
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
    data = json.loads(output.with_name("dataset.json").read_text(encoding="utf-8"))
    settings = data["config"]["value_examples"]
    assert settings["short_text_result_size"] == 20
    assert settings["long_text_result_size"] == 20
    assert len(data["columns"][0]["value_profile"]["values"]) == 20


@pytest.mark.parametrize(
    "content", ['{"unexpected": true}', "[1, 2]", '{"csv": {"delimiter": "||"}}']
)
def test_invalid_config_is_rejected(tmp_path, content):
    config = tmp_path / "config.json"
    config.write_text(content)
    with pytest.raises(ValueError):
        load_config([config])

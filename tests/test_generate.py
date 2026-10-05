# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Lot 1 contract tests for Generate loading, planning and publication."""

import os
from importlib.resources import files
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tabalyst.cli.app import app
from tabalyst.errors import ConfigurationError, InputError, ReportError
from tabalyst.generate_csv import write_csv
from tabalyst.generate_definition import load_generate_definition
from tabalyst.generate_service import _publish_artifacts, build_generate_plan

SIMPLE = """\
definition_version: 1
id: demo
datasets:
  - id: contacts
    rows: 3
    columns:
      - name: id
        type: string
        generate: {kind: sequence, prefix: C, width: 3}
"""


def definition(tmp_path: Path, text: str = SIMPLE) -> Path:
    path = tmp_path / "definition.yaml"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "change, message",
    [
        ("definition_version: 1\ndefinition_version: 1\n", "Duplicate key"),
        ("definition_version: 2\n", "definition_version"),
        ("definition_version: 1\nunknown: 1\n", "unknown key"),
        ("!!python/object/apply:os.system ['exit 1']", "invalid YAML"),
        ("definition_version: 1\nid: x\ndatasets: [*missing]", "aliases are unsupported"),
        ("definition_version: 1\n---\nid: x", "invalid YAML"),
        (SIMPLE.replace("rows: 3", "rows: true"), "rows"),
        (SIMPLE.replace("id: contacts", "id: ../bad"), "safe lower-case"),
        (SIMPLE.replace("kind: sequence", "kind: bogus"), "unknown generator"),
        (SIMPLE.replace("type: string", "type: bogus"), "physical type"),
        (SIMPLE.replace("name: id", "name: id\n        depends_on: [missing]"), "unknown column"),
    ],
)
def test_invalid_definition_has_source_location(tmp_path: Path, change: str, message: str) -> None:
    path = definition(tmp_path, change)
    with pytest.raises(ConfigurationError, match=message) as caught:
        load_generate_definition(path)
    assert str(path) in str(caught.value)
    assert ":" in str(caught.value)


def test_recursive_alias_and_bounds(tmp_path: Path) -> None:
    path = definition(tmp_path, "a: &a [*a]")
    with pytest.raises(ConfigurationError, match="aliases"):
        load_generate_definition(path)
    path.write_bytes(b" " * 1_048_577)
    with pytest.raises(ConfigurationError, match="exceeds"):
        load_generate_definition(path)


def test_plan_examples_and_apportion(tmp_path: Path) -> None:
    plan = build_generate_plan(
        example="insurance", output_dir=tmp_path,
        rows=3000, anomaly_profile="dirty_realistic",
    )
    assert [plan.rows[name] for name in (
        "insurance-principal", "insurance-ontario", "insurance-quebec",
        "insurance-combined",
    )] == [2182, 273, 545, 3000]
    assert len(plan.artifacts) == 7
    assert plan.artifacts[-1].path.name == "insurance-combined.dirty_realistic.summary.json"
    crm = build_generate_plan(example="crm", output=tmp_path / "crm.csv", rows=5)
    assert crm.rows == {"crm-contacts": 5}


def test_packaged_examples_match_visible_yaml() -> None:
    root = Path(__file__).resolve().parents[1]
    for name in ("crm", "insurance"):
        installed = files("tabalyst").joinpath("generate_examples", f"{name}.yaml")
        visible = root / "examples" / "generate" / f"{name}.yaml"
        assert installed.read_bytes() == visible.read_bytes()


def test_bad_options_and_collisions(tmp_path: Path) -> None:
    path = definition(tmp_path)
    output = tmp_path / "out.csv"
    with pytest.raises(ConfigurationError, match="exactly one definition"):
        build_generate_plan(path, example="crm", output=output)
    with pytest.raises(ConfigurationError, match="exactly one destination"):
        build_generate_plan(path)
    with pytest.raises(ConfigurationError, match="--rows"):
        build_generate_plan(path, output=output, rows=0)
    with pytest.raises(ConfigurationError, match="--as-of-date"):
        build_generate_plan(path, output=output, as_of_date="2026-02-30")
    with pytest.raises(ConfigurationError, match="Unknown anomaly"):
        build_generate_plan(path, output=output, anomaly_profile="bad")
    csv_named_definition = tmp_path / "definition.csv"
    csv_named_definition.write_text(SIMPLE, encoding="utf-8")
    with pytest.raises(InputError, match="overwrite an input"):
        build_generate_plan(csv_named_definition, output=csv_named_definition)
    output.write_text("old", encoding="utf-8")
    with pytest.raises(ReportError, match="--force"):
        build_generate_plan(path, output=output)
    assert build_generate_plan(path, output=output, force=True).force
    with pytest.raises(ConfigurationError, match="-o requires"):
        build_generate_plan(example="insurance", output=output)
    with pytest.raises(ConfigurationError, match="-o requires"):
        build_generate_plan(example="crm", output=output, anomaly_profile="dirty_realistic")


def test_staging_failure_leaves_finals_untouched(tmp_path: Path) -> None:
    plan = build_generate_plan(example="insurance", output_dir=tmp_path)
    first = plan.artifacts[0].path
    first.write_bytes(b"old")
    plan = build_generate_plan(example="insurance", output_dir=tmp_path, force=True)

    def writer(artifact, stage):
        if artifact == plan.artifacts[2]:
            raise OSError("injected staging failure")
        stage.write_bytes(b"new")

    with pytest.raises(ReportError, match="injected staging failure"):
        _publish_artifacts(plan, writer)
    assert first.read_bytes() == b"old"
    assert not plan.artifacts[1].path.exists()


def test_publication_failure_restores_old_files(tmp_path: Path, monkeypatch) -> None:
    plan = build_generate_plan(example="insurance", output_dir=tmp_path)
    first = plan.artifacts[0].path
    first.write_bytes(b"old")
    plan = build_generate_plan(example="insurance", output_dir=tmp_path, force=True)
    real_replace = os.replace
    calls = 0

    def fail_second(source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected publication failure")
        return real_replace(source, target)

    monkeypatch.setattr(os, "replace", fail_second)
    with pytest.raises(ReportError, match="injected publication failure"):
        _publish_artifacts(plan, lambda artifact, stage: stage.write_bytes(b"new"))
    assert first.read_bytes() == b"old"
    assert not plan.artifacts[1].path.exists()


def test_adapted_csv_writer_escapes_utf8_and_lf(tmp_path: Path) -> None:
    path = tmp_path / "stage.csv"
    assert write_csv(path, ["id", "value"], [{"id": "1", "value": 'é,"x"'}]) == 1
    assert path.read_bytes() == b'id,value\n1,"\xc3\xa9,""x"""\n'


def test_cli_reports_lot_boundary_without_output(tmp_path: Path) -> None:
    path = definition(tmp_path)
    output = tmp_path / "out.csv"
    result = CliRunner().invoke(app, ["generate", str(path), "-o", str(output)])
    assert result.exit_code == 2
    assert "lot 1" in result.output
    assert not output.exists()

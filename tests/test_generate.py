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
from tabalyst.generate_service import (
    _publish_artifacts,
    build_generate_plan,
    generate_datasets,
)

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
        visible = root / "examples" / "generate" / "input" / f"{name}.yaml"
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
    assert write_csv(path, ["id", "value"], [
        {"id": "1", "value": 'é,"x"'},
        {"id": "2", "value": "line 1\nline 2"},
    ]) == 2
    assert path.read_bytes() == b'id,value\n1,"\xc3\xa9,""x"""\n2,"line 1\nline 2"\n'


def test_cli_generates_elementary_csv(tmp_path: Path) -> None:
    path = definition(tmp_path)
    output = tmp_path / "out.csv"
    result = CliRunner().invoke(app, ["generate", str(path), "-o", str(output)])
    assert result.exit_code == 0
    assert output.read_bytes() == b"id\nC001\nC002\nC003\n"


def test_elementary_reproducibility_bounds_and_escaping(tmp_path: Path) -> None:
    path = definition(tmp_path, """\
definition_version: 1
id: elementary
defaults: {seed: 19, as_of_date: '2025-01-10'}
datasets:
  - id: sample
    rows: 3000
    columns:
      - {name: id, type: string, generate: {kind: sequence, prefix: C, width: 5}}
      - {name: note, type: string, generate: {kind: constant, value: 'a,"b"'}}
      - {name: group, type: string, generate: {kind: choice, weights: {A: 3, B: 1}}}
      - {name: amount, type: decimal, generate: {kind: decimal, min: 1.25, max: 2.75, scale: 2}}
      - {name: count, type: integer, generate: {kind: integer, min: 2, max: 5}}
      - {name: active, type: boolean, generate: {kind: boolean}}
      - {name: day, type: date, generate: {kind: date, min: '2025-01-01'}}
      - {name: time, type: datetime, generate: {kind: datetime, min: '2025-01-01T00:00:00'}}
      - {name: token, type: string, generate: {kind: text, length: 8}, missing: 0.2}
""")
    left = tmp_path / "left.csv"
    right = tmp_path / "right.csv"
    generate_datasets(build_generate_plan(path, output=left))
    generate_datasets(build_generate_plan(path, output=right))
    assert left.read_bytes() == right.read_bytes()
    import csv
    from collections import Counter
    from datetime import date, datetime
    from decimal import Decimal
    with left.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 3000
    assert rows[0]["note"] == 'a,"b"'
    assert all(Decimal("1.25") <= Decimal(row["amount"]) <= Decimal("2.75") for row in rows)
    assert all(2 <= int(row["count"]) <= 5 for row in rows)
    assert all(date.fromisoformat(row["day"]) <= date(2025, 1, 10) for row in rows)
    assert all(datetime.fromisoformat(row["time"]) <= datetime.fromisoformat("2025-01-10T23:59:59") for row in rows)
    assert {row["active"] for row in rows} == {"true", "false"}
    groups = Counter(row["group"] for row in rows)
    assert 0.72 <= groups["A"] / len(rows) <= 0.78
    missing = sum(not row["token"] for row in rows)
    assert 0.17 <= missing / len(rows) <= 0.23


def test_column_stream_is_independent_and_later_lots_fail_cleanly(tmp_path: Path) -> None:
    random_definition = SIMPLE.replace("type: string", "type: integer").replace(
        "{kind: sequence, prefix: C, width: 3}",
        "{kind: integer, min: 1, max: 1000000}",
    )
    first = definition(tmp_path, random_definition)
    initial = tmp_path / "initial.csv"
    generate_datasets(build_generate_plan(first, output=initial, seed=7))
    added = random_definition.replace(
        "      - name: id",
        "      - {name: noise, type: integer, generate: {kind: integer, min: 0, max: 9}}\n"
        "      - name: id",
    )
    definition(tmp_path, added)
    expanded = tmp_path / "expanded.csv"
    generate_datasets(build_generate_plan(first, output=expanded, seed=7))
    assert [line.split(",")[1] for line in expanded.read_text().splitlines()[1:]] == [
        line for line in initial.read_text().splitlines()[1:]
    ]
    plan = build_generate_plan(example="insurance", output_dir=tmp_path / "insurance", rows=30)
    result = generate_datasets(plan)
    assert result.row_counts["insurance-combined"] == 30
    assert (tmp_path / "insurance" / "insurance-combined.csv").is_file()


@pytest.mark.parametrize("generator, message", [
    ("{kind: integer, min: 1.5, max: 3}", "integer bounds"),
    ("{kind: decimal, min: 1.001, max: 1.002, scale: 2}", "no value"),
    ("{kind: choice, weights: {A: .nan}}", "positive numbers"),
    ("{kind: choice, weights: {A: 10000000000000000000000000000000000000000}}", "positive numbers"),
    ("{kind: date, min: '2026-02-30', max: '2026-03-01'}", "date.min"),
])
def test_elementary_invalid_parameters(tmp_path: Path, generator: str, message: str) -> None:
    source = SIMPLE.replace("type: string", "type: integer" if "kind: integer" in generator else
                            "type: decimal" if "kind: decimal" in generator else
                            "type: date" if "kind: date" in generator else "type: string")
    source = source.replace("{kind: sequence, prefix: C, width: 3}", generator)
    with pytest.raises(ConfigurationError, match=message):
        load_generate_definition(definition(tmp_path, source))


CRM_RELATIONS = """\
definition_version: 1
id: crm-relations
defaults: {seed: 31, as_of_date: '2026-10-05'}
entities:
  - id: companies
    count: 7
    generator: company
    columns:
      - {name: id, type: string, generate: {kind: sequence, prefix: A, width: 2}}
      - {name: name, type: string, generate: {kind: sequence, prefix: Company, width: 2}}
      - {name: domain, type: string, generate: {kind: sequence, prefix: domain, width: 2}}
      - {name: country, type: string, generate: {kind: choice, weights: {CA: 1, US: 1}}}
      - name: region
        type: string
        depends_on: [country]
        generate: {kind: conditional, from: country, cases: {CA: Ontario, US: NewYork}, default: Unknown}
datasets:
  - id: contacts-a
    rows: 21
    source: a
    columns:
      - {name: contact_id, type: string, generate: {kind: sequence, prefix: C, width: 3}}
      - {name: company_name, type: string, generate: {kind: reference, entity: companies, field: name}}
      - {name: company_id, type: string, generate: {kind: reference, entity: companies, field: id}}
      - {name: domain, type: string, generate: {kind: reference, entity: companies, field: domain}}
      - {name: country, type: string, generate: {kind: reference, entity: companies, field: country}}
      - {name: region, type: string, generate: {kind: reference, entity: companies, field: region}}
      - name: follow_up
        type: date
        depends_on: [signup]
        generate: {kind: relative_date, from: signup, offset: 30}
      - {name: signup, type: date, generate: {kind: date, min: '2025-01-01', max: '2025-12-31'}}
  - id: contacts-b
    rows: 7
    source: b
    columns:
      - {name: contact_id, type: string, generate: {kind: sequence, prefix: C, width: 3}}
      - {name: company_name, type: string, generate: {kind: reference, entity: companies, field: name}}
      - {name: company_id, type: string, generate: {kind: reference, entity: companies, field: id}}
      - {name: domain, type: string, generate: {kind: reference, entity: companies, field: domain}}
      - {name: country, type: string, generate: {kind: reference, entity: companies, field: country}}
      - {name: region, type: string, generate: {kind: reference, entity: companies, field: region}}
      - name: follow_up
        type: date
        depends_on: [signup]
        generate: {kind: relative_date, from: signup, offset: 30}
      - {name: signup, type: date, generate: {kind: date, min: '2025-01-01', max: '2025-12-31'}}
  - id: all-contacts
    combine: {inputs: [contacts-a, contacts-b], source_column: source}
"""


def test_crm_relations_cardinality_and_combine(tmp_path: Path) -> None:
    import csv
    from collections import Counter
    from datetime import date, timedelta

    source = definition(tmp_path, CRM_RELATIONS)
    first = tmp_path / "first"
    second = tmp_path / "second"
    result = generate_datasets(build_generate_plan(source, output_dir=first))
    generate_datasets(build_generate_plan(source, output_dir=second))
    assert result.row_counts == {"contacts-a": 21, "contacts-b": 7, "all-contacts": 28}
    assert all((first / name).read_bytes() == (second / name).read_bytes()
               for name in ("contacts-a.csv", "contacts-b.csv", "all-contacts.csv"))
    with (first / "all-contacts.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert [row["source"] for row in rows] == ["a"] * 21 + ["b"] * 7
    companies: dict[str, tuple[str, str, str, str]] = {}
    for row in rows:
        identity = row["company_id"]
        facts = (row["company_name"], row["domain"], row["country"], row["region"])
        assert identity not in companies or companies[identity] == facts
        companies[identity] = facts
        assert row["region"] == {"CA": "Ontario", "US": "NewYork"}[row["country"]]
        assert date.fromisoformat(row["follow_up"]) == date.fromisoformat(row["signup"]) + timedelta(days=30)
    assert len(companies) == 7
    assert Counter(row["company_id"] for row in rows[:21]) == dict.fromkeys(companies, 3)
    assert Counter(row["company_id"] for row in rows[21:]) == dict.fromkeys(companies, 1)
    cli_dir = tmp_path / "cli"
    cli = CliRunner().invoke(app, ["generate", str(source), "-d", str(cli_dir)])
    assert cli.exit_code == 0, cli.output
    assert (cli_dir / "all-contacts.csv").read_bytes() == (first / "all-contacts.csv").read_bytes()


@pytest.mark.parametrize("change, message", [
    ("depends_on: [signup]", "column dependency cycle"),
    ("field: id", "reference needs a declared entity field"),
    ("offset: 30", "relative_date.from must be declared"),
])
def test_relation_validation(tmp_path: Path, change: str, message: str) -> None:
    if change == "depends_on: [signup]":
        source = CRM_RELATIONS.replace(
            "{name: signup, type: date, generate:",
            "{name: signup, type: date, depends_on: [follow_up], generate:", 1,
        )
    elif change == "field: id":
        source = CRM_RELATIONS.replace("field: id", "field: missing", 1)
    else:
        source = CRM_RELATIONS.replace("depends_on: [signup]", "depends_on: []", 1)
    with pytest.raises(ConfigurationError, match=message):
        load_generate_definition(definition(tmp_path, source))

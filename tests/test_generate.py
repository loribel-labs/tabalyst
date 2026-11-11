# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Lot 1 contract tests for Generate loading, planning and publication."""

import os
from importlib.resources import files
from pathlib import Path

import pytest
from generate_package_fixture import write_columns_package
from typer.testing import CliRunner

from tabalyst.cli.app import app
from tabalyst.errors import ConfigurationError, InputError, ReportError
from tabalyst.generate_csv import write_csv
from tabalyst.generate_service import (
    _publish_artifacts,
    build_generate_plan,
    generate_datasets,
    validate_generate_package,
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
    return write_columns_package(tmp_path, text)


def test_v1_yaml_is_rejected_by_api_and_cli(tmp_path: Path) -> None:
    source = tmp_path / "legacy.yaml"
    source.write_text(SIMPLE, encoding="utf-8")
    with pytest.raises(ConfigurationError, match="PACKAGE_FORMAT.*definition_version: 1"):
        build_generate_plan(source, output=tmp_path / "out.csv")
    with pytest.raises(ConfigurationError, match="PACKAGE_FORMAT.*definition_version: 1"):
        validate_generate_package(source)
    result = CliRunner().invoke(app, ["generate", str(source), "-o", str(tmp_path / "out.csv")])
    assert result.exit_code != 0
    assert "PACKAGE_FORMAT" in result.output
    assert not (tmp_path / "out.csv").exists()


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


def test_packaged_examples_match_visible_sources() -> None:
    root = Path(__file__).resolve().parents[1]
    for name in ("crm", "insurance"):
        visible = root / "examples" / "generate" / name
        for source in visible.rglob("*"):
            if source.is_file():
                packaged = files("tabalyst").joinpath("generate_examples", name, *source.relative_to(visible).parts)
                assert packaged.read_bytes() == source.read_bytes()


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
    with pytest.raises(InputError, match="inside its source package"):
        build_generate_plan(path, output=path / "contacts.csv")
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
    ("{kind: decimal, min: 1, max: 9, distribution: normal}", "uniform or lognormal"),
    ("{kind: decimal, min: 1, max: 9, median: 3}", "require distribution lognormal"),
    ("{kind: decimal, min: 0, max: 9, distribution: lognormal, median: 3, sigma: 1}", "min above 0"),
    ("{kind: decimal, min: 1, max: 9, distribution: lognormal, median: 10, sigma: 1}", "median from min"),
    ("{kind: decimal, min: 1, max: 9, distribution: lognormal, median: 3}", "sigma above 0"),
    ("{kind: decimal, min: 1, max: 9, distribution: lognormal, median: 3, sigma: 6}", "sigma above 0"),
    ("{kind: decimal, min: 1, max: 9, round_to: {step: 0.001, share: 0.5}}", "multiple of the scale"),
    ("{kind: decimal, min: 1, max: 9, round_to: {step: 0, share: 0.5}}", "round_to.step"),
    ("{kind: decimal, min: 1, max: 9, round_to: {step: 1, share: 0}}", "round_to.share"),
    ("{kind: decimal, min: 1, max: 9, round_to: {step: 1}}", "round_to.share"),
])
def test_elementary_invalid_parameters(tmp_path: Path, generator: str, message: str) -> None:
    source = SIMPLE.replace("type: string", "type: integer" if "kind: integer" in generator else
                            "type: decimal" if "kind: decimal" in generator else
                            "type: date" if "kind: date" in generator else "type: string")
    source = source.replace("{kind: sequence, prefix: C, width: 3}", generator)
    with pytest.raises(ConfigurationError, match=message):
        validate_generate_package(definition(tmp_path, source))


def test_decimal_lognormal_is_skewed_around_its_median_within_bounds(tmp_path: Path) -> None:
    import csv
    import statistics
    from decimal import Decimal
    source = SIMPLE.replace("rows: 3", "rows: 4000").replace("type: string", "type: decimal").replace(
        "{kind: sequence, prefix: C, width: 3}",
        "{kind: decimal, min: 1500, max: 175000, scale: 2, distribution: lognormal, median: 18000, sigma: 1}",
    )
    left, right = tmp_path / "left.csv", tmp_path / "right.csv"
    generate_datasets(build_generate_plan(definition(tmp_path, source), output=left))
    generate_datasets(build_generate_plan(definition(tmp_path, source), output=right))
    assert left.read_bytes() == right.read_bytes()
    with left.open(encoding="utf-8", newline="") as stream:
        values = [Decimal(row["id"]) for row in csv.DictReader(stream)]
    assert all(Decimal(1500) <= value <= Decimal(175000) for value in values)
    assert 16000 <= statistics.median(values) <= 20000
    assert statistics.mean(values) > statistics.median(values) * Decimal("1.3")
    assert 0.01 <= sum(value > 100000 for value in values) / len(values) <= 0.06



ROW_RULES = """\
definition_version: 1
id: row-rules
defaults: {seed: 11, as_of_date: '2025-12-31'}
datasets:
  - id: deals
    rows: 3000
    columns:
      - {name: tier, type: string, generate: {kind: choice, weights: {small: 1, large: 1}}}
      - name: label
        type: string
        depends_on: [tier]
        generate:
          kind: choice
          weights: {A: 1, B: 1}
          by_case: {from: tier, cases: {large: {weights: {C: 1}}}}
      - name: score
        type: integer
        depends_on: [tier]
        generate: {kind: integer, min: 0, max: 9, by_case: {from: tier, cases: {large: {min: 50, max: 59}}}}
      - name: amount
        type: decimal
        depends_on: [tier]
        generate: {kind: decimal, min: 10, max: 20, scale: 2, by_value: {from: tier, factors: {large: 10}}}
      - {name: opened, type: date, generate: {kind: date, min: '2020-01-01', max: '2025-06-30', growth: 1}}
      - name: touched
        type: date
        depends_on: [opened]
        generate: {kind: date, min: '2019-01-01', max: '2025-12-31', after: opened, weekdays: true}
      - {name: opted, type: boolean, generate: {kind: boolean, true_share: 0.2}}
"""


def test_row_rules_read_the_other_columns_of_the_row(tmp_path: Path) -> None:
    import csv
    from collections import Counter
    from datetime import date
    from decimal import Decimal
    output = tmp_path / "deals.csv"
    generate_datasets(build_generate_plan(definition(tmp_path, ROW_RULES), output=output))
    with output.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        large = row["tier"] == "large"
        assert (row["label"] == "C") == large
        assert (50 <= int(row["score"]) <= 59) if large else (0 <= int(row["score"]) <= 9)
        amount = Decimal(row["amount"])
        assert (100 <= amount <= 200) if large else (10 <= amount <= 20)
        assert row["opened"] <= row["touched"] <= "2025-12-31"
        assert date.fromisoformat(row["touched"]).weekday() < 5
    years = Counter(row["opened"][:4] for row in rows)
    assert years["2024"] > 4 * years["2021"]
    assert 0.17 <= sum(row["opted"] == "true" for row in rows) / len(rows) <= 0.23


def test_after_keeps_the_source_date_when_it_passes_max(tmp_path: Path) -> None:
    import csv
    source = ROW_RULES.replace("max: '2025-12-31', after", "max: '2019-06-30', after")
    output = tmp_path / "deals.csv"
    generate_datasets(build_generate_plan(definition(tmp_path, source), output=output))
    with output.open(encoding="utf-8", newline="") as stream:
        assert all(row["touched"] == row["opened"] for row in csv.DictReader(stream))


@pytest.mark.parametrize("old, new, message", [
    ("cases: {large: {weights: {C: 1}}}", "cases: {large: {min: 1}}", "unknown key 'min'"),
    ("cases: {large: {weights: {C: 1}}}", "cases: {large: {weights: {C: -1}}}", "positive numbers"),
    ("cases: {large: {weights: {C: 1}}}", "cases: {large: {}}", "changes nothing"),
    ("cases: {large: {weights: {C: 1}}}", "cases: {}", "named cases"),
    ("cases: {large: {min: 50, max: 59}}", "cases: {large: {min: 59, max: 50}}", "min <= max"),
    ("depends_on: [tier]\n        generate:\n          kind: choice", "generate:\n          kind: choice",
     "by_case.from must be declared"),
    ("factors: {large: 10}", "factors: {large: 0}", "by_value requires"),
    ("growth: 1}", "growth: 0}", "growth must be above 0"),
    ("weekdays: true", "weekdays: false", "weekdays must be true"),
    ("true_share: 0.2", "true_share: 1.5", "true_share must be from 0 to 1"),
    ("depends_on: [opened]", "depends_on: []", "after must be declared"),
])
def test_row_rules_reject_invalid_declarations(tmp_path: Path, old: str, new: str, message: str) -> None:
    assert old in ROW_RULES
    with pytest.raises(ConfigurationError, match=message):
        validate_generate_package(definition(tmp_path, ROW_RULES.replace(old, new, 1)))


MISSING_BY = """\
definition_version: 1
id: missing-by
datasets:
  - id: people
    rows: 4000
    columns:
      - {name: tier, type: string, generate: {kind: choice, weights: {a: 1, b: 1}}, missing: 0.3}
      - name: note
        type: string
        depends_on: [tier]
        generate: {kind: text, length: 4}
        missing: 0.1
        missing_by: {from: tier, empty: 0.9, cases: {b: 0}}
"""


def test_missing_by_sets_the_missing_rate_from_another_column(tmp_path: Path) -> None:
    import csv
    output = tmp_path / "people.csv"
    generate_datasets(build_generate_plan(definition(tmp_path, MISSING_BY), output=output))
    with output.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))

    def empty(tier: str) -> float:
        group = [row for row in rows if row["tier"] == tier]
        return sum(not row["note"] for row in group) / len(group)

    assert 0.86 <= empty("") <= 0.94
    assert 0.07 <= empty("a") <= 0.13
    assert empty("b") == 0


@pytest.mark.parametrize("old, new", [
    ("missing_by: {from: tier, empty: 0.9, cases: {b: 0}}", "missing_by: {from: tier}"),
    ("empty: 0.9", "empty: 1.5"),
    ("cases: {b: 0}", "cases: {b: -1}"),
    ("depends_on: [tier]", "depends_on: []"),
])
def test_missing_by_rejects_invalid_declarations(tmp_path: Path, old: str, new: str) -> None:
    assert old in MISSING_BY
    with pytest.raises(ConfigurationError, match="missing_by"):
        validate_generate_package(definition(tmp_path, MISSING_BY.replace(old, new, 1)))


def test_decimal_round_to_rounds_a_share_and_keeps_the_other_values(tmp_path: Path) -> None:
    import csv
    from decimal import Decimal
    plain = SIMPLE.replace("rows: 3", "rows: 2000").replace("type: string", "type: decimal").replace(
        "{kind: sequence, prefix: C, width: 3}", "{kind: decimal, min: 100, max: 9000, scale: 2}",
    )
    rounded = plain.replace("scale: 2}", "scale: 2, round_to: {step: 100, share: 0.6}}")
    plain_path, rounded_path = tmp_path / "plain.csv", tmp_path / "rounded.csv"
    generate_datasets(build_generate_plan(definition(tmp_path / "a", plain), output=plain_path))
    generate_datasets(build_generate_plan(definition(tmp_path / "b", rounded), output=rounded_path))
    with plain_path.open(encoding="utf-8", newline="") as one, rounded_path.open(encoding="utf-8", newline="") as two:
        pairs = [(Decimal(a["id"]), b["id"]) for a, b in zip(csv.DictReader(one), csv.DictReader(two), strict=True)]
    changed = 0
    for drawn, written in pairs:
        if written != f"{drawn:.2f}":
            changed += 1
            assert written == f"{(drawn / 100).to_integral_value() * 100:.2f}"
    share = sum(written.endswith("00.00") for _, written in pairs) / len(pairs)
    assert 0.55 <= share <= 0.65
    assert changed > 0



BY_MONTH = """\
definition_version: 1
id: by-month
defaults: {seed: 5, as_of_date: '2025-12-31'}
datasets:
  - id: deals
    rows: 400
    columns:
      - {name: closed, type: date, generate: {kind: date, min: '2025-01-01', max: '2025-12-31'}, missing: 0.1}
      - name: amount
        type: decimal
        depends_on: [closed]
        generate:
          kind: decimal
          min: 100
          max: 200
          scale: 2
          by_month: {from: closed, factors: {july: 0.5, september: 1.25}}
"""


def test_decimal_by_month_scales_only_the_months_it_names(tmp_path: Path) -> None:
    import csv
    from decimal import Decimal
    plain = BY_MONTH.replace(
        "          by_month: {from: closed, factors: {july: 0.5, september: 1.25}}\n", "")
    scaled_path, plain_path = tmp_path / "scaled.csv", tmp_path / "plain.csv"
    generate_datasets(build_generate_plan(definition(tmp_path / "a", BY_MONTH), output=scaled_path))
    generate_datasets(build_generate_plan(definition(tmp_path / "b", plain), output=plain_path))
    with scaled_path.open(encoding="utf-8", newline="") as one, plain_path.open(encoding="utf-8", newline="") as two:
        pairs = list(zip(csv.DictReader(one), csv.DictReader(two), strict=True))
    factors = {"07": Decimal("0.5"), "09": Decimal("1.25")}
    months = set()
    for scaled, drawn in pairs:
        assert scaled["closed"] == drawn["closed"]
        month = scaled["closed"][5:7]
        months.add(month)
        expected = (Decimal(drawn["amount"]) * factors.get(month, Decimal(1))).quantize(Decimal("0.01"))
        assert scaled["amount"] == f"{expected:.2f}"
    assert {"07", "09", ""} <= months


@pytest.mark.parametrize("change, message", [
    ("factors: {july: 0.5, september: 1.25}", "factors: {julio: 0.5}"),
    ("factors: {july: 0.5, september: 1.25}", "factors: {july: 0}"),
    ("factors: {july: 0.5, september: 1.25}", "factors: {july: 11}"),
    ("factors: {july: 0.5, september: 1.25}", "factors: {}"),
    ("depends_on: [closed]", "depends_on: []"),
    ("type: date, generate: {kind: date,", "type: date, generate: {kind: date, format: '%d/%m/%Y',"),
])
def test_decimal_by_month_rejects_invalid_declarations(tmp_path: Path, change: str, message: str) -> None:
    with pytest.raises(ConfigurationError, match="by_month"):
        validate_generate_package(definition(tmp_path, BY_MONTH.replace(change, message)))


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
        validate_generate_package(definition(tmp_path, source))

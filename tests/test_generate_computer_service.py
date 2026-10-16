# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Check Computer planning, CLI access, and safe multi-file publication."""

import csv
import hashlib
import json
import shutil
from collections.abc import Iterable
from importlib.resources import files
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tabalyst.batch import validate_outputs
from tabalyst.cli.app import app
from tabalyst.errors import ConfigurationError, InputError, ReportError
from tabalyst.generate_computer_output import UNIT_COLUMNS
from tabalyst.generate_service import (
    ComputerPlan,
    build_generate_plan,
    generate_datasets,
    validate_generate_package,
)

PACKAGE = Path(str(files("tabalyst").joinpath("generate_examples", "computer")))


def test_packaged_computer_example_generates_three_artifacts(tmp_path: Path) -> None:
    """Load the Computer resources and create both locales through --example."""
    runner = CliRunner()
    validated = runner.invoke(app, ["generate", "--example", "computer", "--validate-only"])
    assert validated.exit_code == 0, validated.output
    destination = tmp_path / "computer"
    created = runner.invoke(app, ["generate", "--example", "computer", "-d",
                                  str(destination), "--rows", "5", "--seed", "42",
                                  "--output-profile", "extended"])
    assert created.exit_code == 0, created.output
    assert sorted(path.name for path in destination.iterdir()) == [
        "computers-en.csv", "computers-fr.csv", "computers.meta.json",
    ]
    for locale in ("en", "fr"):
        with (destination / f"computers-{locale}.csv").open(encoding="utf-8", newline="") as stream:
            assert len(list(csv.DictReader(stream))) == 5


@pytest.mark.parametrize("profile", ["dirty_realistic", "dirty_stress"])
def test_computer_anomalies_preserve_clean_locales_and_audit_cells(
    tmp_path: Path, profile: str,
) -> None:
    """Every journal entry reconstructs one change in the altered locale CSV."""
    clean_dir = tmp_path / "clean"
    dirty_dir = tmp_path / "dirty"
    generate_datasets(build_generate_plan(
        PACKAGE, output_dir=clean_dir, rows=500, seed=42, output_profile="extended",
    ))
    plan = build_generate_plan(
        PACKAGE, output_dir=dirty_dir, rows=500, seed=42,
        output_profile="extended", anomaly_profile=profile,
    )
    assert isinstance(plan, ComputerPlan)
    assert len(plan.artifacts) == 9
    result = generate_datasets(plan)
    assert len(result.paths) == 9
    summaries = {}
    journals = {}
    for locale in ("en", "fr"):
        assert (clean_dir / f"computers-{locale}.csv").read_bytes() == (
            dirty_dir / f"computers-{locale}.csv").read_bytes()
        with (dirty_dir / f"computers-{locale}.csv").open(encoding="utf-8", newline="") as stream:
            originals = list(csv.DictReader(stream))
        with (dirty_dir / f"computers-{locale}.{profile}.csv").open(
            encoding="utf-8", newline="",
        ) as stream:
            altered = list(csv.DictReader(stream))
        with (dirty_dir / f"computers-{locale}.{profile}.changes.csv").open(
            encoding="utf-8", newline="",
        ) as stream:
            changes = list(csv.DictReader(stream))
        summary = json.loads((dirty_dir / f"computers-{locale}.{profile}.summary.json").read_text(
            encoding="utf-8",
        ))
        assert summary["changed_cells"] == len(changes) == result.anomaly_counts[locale]
        assert summary["events"] > 0
        assert summary["seed"] == 42
        assert summary["locale"] == locale
        assert summary["affected_row_rate"] > 0
        assert {entry["kind"] for entry in changes} == {"set_missing", "format", "replace"}
        assert {entry["column"] for entry in changes} >= {
            "memory_gb", "cpu_model", "release_date", "current_price",
            "stock_status", "gpu_vram_gb", "stock_quantity",
        }
        for change in changes:
            row_index = int(change["row_number"]) - 2
            column = change["column"]
            assert change["dataset"] == "computers"
            assert change["profile"] == profile
            assert change["cause"] == f"{profile}.operations[{int(change['operation_index']) - 1}]"
            assert change["before"] == originals[row_index][column]
            assert change["after"] == altered[row_index][column]
            if column == "gpu_vram_gb" and change["kind"] == "replace":
                assert originals[row_index]["gpu_type"] == "dedicated"
                assert int(originals[row_index][column]) > 0
            if column == "stock_quantity":
                assert originals[row_index]["stock_status"] == "in_stock"
                assert int(originals[row_index][column]) > 0
        summaries[locale] = summary
        journals[locale] = changes
    # The unit suffix is the only localized part of a journal: GB in English, Go in French.
    def unlocalized(entries: list[dict[str, str]]) -> list[dict[str, str]]:
        return [{**entry, "after": entry["after"].replace(" Go", " GB")} for entry in entries]

    assert unlocalized(journals["en"]) == unlocalized(journals["fr"])
    assert summaries["en"]["operations"] == summaries["fr"]["operations"]
    metadata = json.loads((dirty_dir / "computers.meta.json").read_text(encoding="utf-8"))
    assert metadata["request"]["anomaly_profile"] == profile
    assert metadata["anomalies"]["en"]["changed_cells"] == summaries["en"]["changed_cells"]
    assert metadata["resource_sha256"]["dataset.yaml"] == hashlib.sha256(
        (PACKAGE / "dataset.yaml").read_bytes(),
    ).hexdigest()
    repeated = tmp_path / "repeated"
    generate_datasets(build_generate_plan(
        PACKAGE, output_dir=repeated, rows=500, seed=42,
        output_profile="extended", anomaly_profile=profile,
    ))
    for artifact in plan.artifacts:
        assert artifact.path.read_bytes() == (repeated / artifact.path.name).read_bytes()


def test_computer_anomaly_profile_in_request_and_invalid_rules_fail_before_writing(
    tmp_path: Path,
) -> None:
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"rows": 5, "anomaly_profile": "dirty_realistic"}),
                       encoding="utf-8")
    planned = build_generate_plan(PACKAGE, request=request, output_dir=tmp_path / "requested")
    assert isinstance(planned, ComputerPlan)
    assert planned.anomaly_profile == "dirty_realistic"
    assert len(planned.artifacts) == 9
    overridden = build_generate_plan(PACKAGE, request=request, output_dir=tmp_path / "override",
                                     anomaly_profile="dirty_stress")
    assert isinstance(overridden, ComputerPlan)
    assert overridden.anomaly_profile == "dirty_stress"
    with pytest.raises(ConfigurationError, match="Unknown anomaly profile"):
        build_generate_plan(PACKAGE, output_dir=tmp_path / "unknown",
                            anomaly_profile="missing")
    assert not (tmp_path / "unknown").exists()


def test_unit_variant_profile_changes_only_altered_csv_and_logs_localized_values(
    tmp_path: Path,
) -> None:
    """The unit anomaly selects matching cells in both locales and records their values."""
    plan = build_generate_plan(PACKAGE, output_dir=tmp_path / "units", rows=1000,
                               seed=42, anomaly_profile="unit_variants")
    assert isinstance(plan, ComputerPlan)
    result = generate_datasets(plan)
    assert len(result.paths) == 9
    journals = {}
    for locale, suffix in (("en", "GB"), ("fr", "Go")):
        base = tmp_path / "units" / f"computers-{locale}"
        with base.with_suffix(".csv").open(encoding="utf-8", newline="") as stream:
            clean = list(csv.DictReader(stream))
        with (tmp_path / "units" / f"computers-{locale}.unit_variants.csv").open(
            encoding="utf-8", newline="",
        ) as stream:
            altered = list(csv.DictReader(stream))
        with (tmp_path / "units" / f"computers-{locale}.unit_variants.changes.csv").open(
            encoding="utf-8", newline="",
        ) as stream:
            journal = list(csv.DictReader(stream))
        summary = json.loads((tmp_path / "units" / f"computers-{locale}.unit_variants.summary.json").read_text(
            encoding="utf-8",
        ))
        assert journal
        assert summary["changed_cells"] == len(journal) == result.anomaly_counts[locale]
        assert [operation["requested_rows"] for operation in summary["operations"]] == [80, 50, 30]
        assert {change["column"] for change in journal} == {
            "memory_gb", "storage_gb", "gpu_vram_gb",
        }
        for change in journal:
            index = int(change["row_number"]) - 2
            assert change["kind"] == "format"
            assert clean[index][change["column"]] == change["before"]
            assert altered[index][change["column"]] == change["after"]
            assert change["after"] == f"{change['before']} {suffix}"
        journals[locale] = journal
    assert [(entry["row_number"], entry["column"], entry["operation_index"])
            for entry in journals["en"]] == [
                (entry["row_number"], entry["column"], entry["operation_index"])
                for entry in journals["fr"]
            ]
    repeated = build_generate_plan(PACKAGE, output_dir=tmp_path / "repeat", rows=1000,
                                   seed=42, anomaly_profile="unit_variants")
    assert isinstance(repeated, ComputerPlan)
    generate_datasets(repeated)
    for artifact in plan.artifacts:
        assert artifact.path.read_bytes() == (tmp_path / "repeat" / artifact.path.name).read_bytes()


def test_unit_style_request_can_be_overridden_by_cli_and_rejects_invalid_value(
    tmp_path: Path,
) -> None:
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"rows": 4, "unit_style": "localized"}), encoding="utf-8")
    plan = build_generate_plan(PACKAGE, request=request, output_dir=tmp_path / "api")
    assert isinstance(plan, ComputerPlan)
    assert plan.unit_style == "localized"
    generate_datasets(plan)
    with (tmp_path / "api" / "computers-fr.csv").open(encoding="utf-8", newline="") as stream:
        assert next(csv.DictReader(stream))["memory_gb"].endswith(" Go")
    runner = CliRunner()
    created = runner.invoke(app, ["generate", "--example", "computer", "--request",
                                  str(request), "-d", str(tmp_path / "cli"),
                                  "--unit-style", "numeric"])
    assert created.exit_code == 0, created.output
    with (tmp_path / "cli" / "computers-fr.csv").open(encoding="utf-8", newline="") as stream:
        assert next(csv.DictReader(stream))["memory_gb"].isdigit()
    with pytest.raises(ConfigurationError, match="Unsupported Computer unit style"):
        build_generate_plan(PACKAGE, output_dir=tmp_path / "bad", unit_style="other")
    assert not (tmp_path / "bad").exists()


def test_unit_columns_select_multiple_measures_and_record_metadata(tmp_path: Path) -> None:
    """A request can format selected measures while other numeric fields stay numeric."""
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"rows": 20, "output_profile": "extended",
                                   "unit_columns": ["memory_gb", "display_size_in", "weight_kg"]}),
                       encoding="utf-8")
    plan = build_generate_plan(PACKAGE, request=request, output_dir=tmp_path / "units")
    assert isinstance(plan, ComputerPlan)
    assert plan.unit_style == "localized"
    assert set(plan.unit_columns) == {"memory_gb", "display_size_in", "weight_kg"}
    generate_datasets(plan)
    metadata = json.loads((tmp_path / "units" / "computers.meta.json").read_text(encoding="utf-8"))
    assert set(metadata["request"]["unit_columns"]) == set(plan.unit_columns)
    assert set(metadata["unit_columns"]) == set(plan.unit_columns)
    for locale, size_suffix, memory_suffix in (("en", "in", "GB"), ("fr", "po", "Go")):
        with (tmp_path / "units" / f"computers-{locale}.csv").open(
            encoding="utf-8", newline="",
        ) as stream:
            rows = list(csv.DictReader(stream))
        assert all(row["memory_gb"].endswith(f" {memory_suffix}") for row in rows)
        assert all(row["display_size_in"].endswith(f" {size_suffix}")
                   for row in rows if row["display_size_in"])
        assert any(row["display_size_in"].endswith(f" {size_suffix}") for row in rows)
        assert all(row["weight_kg"].endswith(" kg") for row in rows if row["weight_kg"])
        assert all(not row["storage_gb"].endswith((" GB", " Go")) for row in rows)
    runner = CliRunner()
    created = runner.invoke(app, ["generate", "--example", "computer", "-d",
                                  str(tmp_path / "cli"), "--rows", "2",
                                  "--unit-columns", "memory_gb,storage_gb"])
    assert created.exit_code == 0, created.output
    with (tmp_path / "cli" / "computers-fr.csv").open(encoding="utf-8", newline="") as stream:
        row = next(csv.DictReader(stream))
    assert row["memory_gb"].endswith(" Go")
    assert row["storage_gb"].endswith(" Go")
    assert not row["display_size_in"].endswith(" po")


@pytest.mark.parametrize("columns,style,profile", [
    ("memory_gb,unknown", None, "extended"),
    ("memory_gb,memory_gb", None, "extended"),
    ("battery_wh", None, "compact"),
    ("memory_gb", "numeric", "compact"),
])
def test_unit_columns_reject_invalid_selection(
    tmp_path: Path, columns: str, style: str | None, profile: str,
) -> None:
    with pytest.raises(ConfigurationError, match="unit_columns"):
        build_generate_plan(PACKAGE, output_dir=tmp_path / "bad", unit_columns=columns,
                            unit_style=style, output_profile=profile)
    assert not (tmp_path / "bad").exists()


def test_extended_unit_anomalies_are_localized_auditable_and_reproducible(
    tmp_path: Path,
) -> None:
    """Every configured measure has a traceable mutation in both locales."""
    plan = build_generate_plan(PACKAGE, output_dir=tmp_path / "first", rows=2000,
                               seed=42, output_profile="extended",
                               anomaly_profile="unit_variants_extended")
    assert isinstance(plan, ComputerPlan)
    generate_datasets(plan)
    journals = {}
    for locale in ("en", "fr"):
        root = tmp_path / "first"
        with (root / f"computers-{locale}.csv").open(encoding="utf-8", newline="") as stream:
            clean = list(csv.DictReader(stream))
        with (root / f"computers-{locale}.unit_variants_extended.csv").open(
            encoding="utf-8", newline="",
        ) as stream:
            altered = list(csv.DictReader(stream))
        with (root / f"computers-{locale}.unit_variants_extended.changes.csv").open(
            encoding="utf-8", newline="",
        ) as stream:
            journal = list(csv.DictReader(stream))
        summary = json.loads((root / f"computers-{locale}.unit_variants_extended.summary.json").read_text(
            encoding="utf-8",
        ))
        assert len(summary["operations"]) == 14
        assert summary["changed_cells"] == len(journal)
        assert {entry["column"] for entry in journal} == set(UNIT_COLUMNS)
        for entry in journal:
            row_index = int(entry["row_number"]) - 2
            column = entry["column"]
            assert clean[row_index][column] == entry["before"]
            assert altered[row_index][column] == entry["after"]
            assert entry["after"] == f"{entry['before']} {UNIT_COLUMNS[column][0 if locale == 'en' else 1]}"
        journals[locale] = [(entry["row_number"], entry["column"], entry["operation_index"])
                            for entry in journal]
    assert journals["en"] == journals["fr"]
    repeat = build_generate_plan(PACKAGE, output_dir=tmp_path / "repeat", rows=2000,
                                 seed=42, output_profile="extended",
                                 anomaly_profile="unit_variants_extended")
    assert isinstance(repeat, ComputerPlan)
    generate_datasets(repeat)
    for artifact in plan.artifacts:
        assert artifact.path.read_bytes() == (tmp_path / "repeat" / artifact.path.name).read_bytes()


def test_unit_anomalies_reject_already_formatted_target_columns(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="require numeric values"):
        build_generate_plan(PACKAGE, output_dir=tmp_path / "bad", unit_style="localized",
                            anomaly_profile="unit_variants")


@pytest.mark.parametrize("replacement", ["column: brand", "column: missing_column"])
def test_computer_anomaly_rules_reject_unaligned_or_missing_columns(
    tmp_path: Path, replacement: str,
) -> None:
    copied = tmp_path / "package"
    shutil.copytree(PACKAGE, copied)
    manifest = copied / "dataset.yaml"
    source = manifest.read_text(encoding="utf-8")
    assert "column: memory_gb" in source
    manifest.write_text(source.replace("column: memory_gb", replacement, 1), encoding="utf-8")
    with pytest.raises(ConfigurationError, match="PACKAGE_ANOMALY"):
        validate_generate_package(copied)
    with pytest.raises(ConfigurationError, match="PACKAGE_ANOMALY"):
        build_generate_plan(copied, output_dir=tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_api_plans_three_files_and_applies_request_overrides(tmp_path: Path) -> None:
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"rows": 3, "seed": 7, "market": "us"}), encoding="utf-8")
    plan = build_generate_plan(package_path=PACKAGE, request=request, output_dir=tmp_path / "out",
                               rows=4, seed=42)
    assert isinstance(plan, ComputerPlan)
    assert plan.rows == {"computers": 4}
    assert plan.seed == 42
    assert plan.market == "us"
    assert [item.path.name for item in plan.artifacts] == [
        "computers-en.csv", "computers-fr.csv", "computers.meta.json",
    ]
    result = generate_datasets(plan)
    assert result.paths == tuple(item.path for item in plan.artifacts)
    assert result.row_counts == {"computers": 4}
    with result.paths[0].open(encoding="utf-8", newline="") as stream:
        english = list(csv.DictReader(stream))
    with result.paths[1].open(encoding="utf-8", newline="") as stream:
        french = list(csv.DictReader(stream))
    assert len(english) == len(french) == 4
    assert [row["product_id"] for row in english] == [row["product_id"] for row in french]
    metadata = json.loads(result.paths[2].read_text(encoding="utf-8"))
    assert metadata["request"]["market"] == "us"


def test_standard_profile_is_selectable_through_request_and_cli(tmp_path: Path) -> None:
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"rows": 2, "output_profile": "standard"}), encoding="utf-8")
    plan = build_generate_plan(PACKAGE, request=request, output_dir=tmp_path / "api")
    assert isinstance(plan, ComputerPlan)
    assert plan.output_profile == "standard"
    result = generate_datasets(plan)
    with result.paths[0].open(encoding="utf-8", newline="") as stream:
        assert len(next(csv.reader(stream))) == 70
    runner = CliRunner()
    created = runner.invoke(app, ["generate", str(PACKAGE), "-d", str(tmp_path / "cli"),
                                  "--output-profile", "standard", "--rows", "2"])
    assert created.exit_code == 0, created.output
    with (tmp_path / "cli" / "computers-fr.csv").open(encoding="utf-8", newline="") as stream:
        assert len(next(csv.reader(stream))) == 70


def test_cli_validates_without_destination_and_generates(tmp_path: Path) -> None:
    runner = CliRunner()
    validated = runner.invoke(app, ["generate", str(PACKAGE), "--validate-only"])
    assert validated.exit_code == 0, validated.output
    assert validate_generate_package(PACKAGE).package_id == "mini_computer"
    destination = tmp_path / "out"
    created = runner.invoke(app, ["generate", str(PACKAGE), "-d", str(destination),
                                  "--rows", "2", "--seed", "42"])
    assert created.exit_code == 0, created.output
    assert len(list(destination.iterdir())) == 3
    repeated = runner.invoke(app, ["generate", str(PACKAGE), "-d", str(destination)])
    assert repeated.exit_code != 0
    forced = runner.invoke(app, ["generate", str(PACKAGE), "-d", str(destination),
                                 "--rows", "2", "--force"])
    assert forced.exit_code == 0, forced.output


def test_every_package_input_is_protected_even_with_force(tmp_path: Path) -> None:
    copied = tmp_path / "package"
    shutil.copytree(PACKAGE, copied)
    package = validate_generate_package(copied)
    assert len(package.input_paths) > 10
    for source in package.input_paths:
        with pytest.raises(InputError, match="overwrite an input"):
            validate_outputs(((source, source),), sources=package.input_paths,
                             force=True, label="Generate")
    target_dir = tmp_path / "outputs"
    target_dir.mkdir()
    target = target_dir / "computers-en.csv"
    target.write_text("{}", encoding="utf-8")
    with pytest.raises(InputError, match="overwrite an input"):
        build_generate_plan(copied, output_dir=target_dir, request=target, force=True)
    with pytest.raises(InputError, match="inside its source package"):
        build_generate_plan(copied, output_dir=copied, force=True)


def test_plan_passes_all_package_sources_to_collision_checker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tabalyst.generate_service as service

    checked: list[set[Path]] = []
    original = service.validate_outputs

    def capture(artifacts: Iterable[tuple[Path, Path]], *, sources: Iterable[Path], force: bool,
                label: str) -> None:
        paths = set(sources)
        checked.append(paths)
        original(artifacts, sources=paths, force=force, label=label)

    monkeypatch.setattr(service, "validate_outputs", capture)
    plan = build_generate_plan(PACKAGE, output_dir=tmp_path / "out")
    assert isinstance(plan, ComputerPlan)
    assert checked == [set(plan.package.input_paths)]
    generate_datasets(plan)
    assert checked[-2:] == [set(plan.package.input_paths)] * 2


def test_staging_failure_preserves_existing_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    destination = tmp_path / "out"
    destination.mkdir()
    old = destination / "computers-en.csv"
    old.write_bytes(b"old")
    plan = build_generate_plan(PACKAGE, output_dir=destination, force=True)
    assert isinstance(plan, ComputerPlan)

    def fail(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise RuntimeError("deliberate generation failure")

    monkeypatch.setattr("tabalyst.generate_service.write_computer_csvs", fail)
    with pytest.raises(ReportError, match="Generate failed"):
        generate_datasets(plan)
    assert old.read_bytes() == b"old"
    assert sorted(path.name for path in destination.iterdir()) == ["computers-en.csv"]


def test_publication_failure_restores_previous_files(tmp_path: Path,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    destination = tmp_path / "out"
    destination.mkdir()
    for name in ("computers-en.csv", "computers-fr.csv", "computers.meta.json"):
        (destination / name).write_bytes(b"old")
    plan = build_generate_plan(PACKAGE, output_dir=destination, force=True)
    assert isinstance(plan, ComputerPlan)
    import tabalyst.generate_service as service

    original_replace = service.os.replace
    calls = 0

    def fail_second(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("deliberate publication failure")
        original_replace(source, target)

    monkeypatch.setattr(service.os, "replace", fail_second)
    with pytest.raises(ReportError, match="publication failed"):
        generate_datasets(plan)
    assert all((destination / name).read_bytes() == b"old" for name in (
        "computers-en.csv", "computers-fr.csv", "computers.meta.json",
    ))

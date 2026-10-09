# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Check Computer planning, CLI access, and safe multi-file publication."""

import csv
import json
import shutil
from collections.abc import Iterable
from importlib.resources import files
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tabalyst.batch import validate_outputs
from tabalyst.cli.app import app
from tabalyst.errors import InputError, ReportError
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

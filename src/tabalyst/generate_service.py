# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Generate planning and safe multi-artifact publication."""

from __future__ import annotations

import csv
import json
import os
import shutil
import tempfile
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import date
from importlib.resources import files
from pathlib import Path
from typing import cast

from tabalyst import __version__
from tabalyst.batch import apply_default_file_mode, path_key, validate_outputs
from tabalyst.errors import ConfigurationError, InputError, ReportError
from tabalyst.generate_anomalies import (
    FORMAT_VALUES,
    OPERATION_KEYS,
    OPERATION_KINDS,
    ROW_KINDS,
    check_operation_counts,
    operation_option_error,
)
from tabalyst.generate_columns_package import load_columns_definition
from tabalyst.generate_computer_output import (
    LABEL_FIELDS,
    PROFILE_COLUMNS,
    UNIT_COLUMNS,
    write_computer_csvs,
)
from tabalyst.generate_csv import write_csv
from tabalyst.generate_definition import GenerateDefinition
from tabalyst.generate_insurance import InsuranceProvider
from tabalyst.generate_package import MAX_ROWS, DatasetPackage, load_generate_package
from tabalyst.generate_references import SCHEMAS, CommonReferences
from tabalyst.generate_values import generate_rows


@dataclass(frozen=True)
class GenerateArtifact:
    dataset_id: str
    kind: str
    path: Path


@dataclass(frozen=True)
class GeneratePlan:
    definition: GenerateDefinition
    artifacts: tuple[GenerateArtifact, ...]
    rows: dict[str, int]
    seed: int
    as_of_date: str
    anomaly_profile: str | None
    force: bool
    package: DatasetPackage | None = None


@dataclass(frozen=True)
class ComputerPlan:
    """Hold a validated Computer package and its complete publication plan."""

    package: DatasetPackage
    artifacts: tuple[GenerateArtifact, ...]
    rows: dict[str, int]
    seed: int
    as_of_date: str
    generation_profile: str
    output_profile: str
    market: str
    unit_style: str
    unit_columns: tuple[str, ...]
    anomaly_profile: str | None
    force: bool
    request_path: Path | None
    locales: tuple[str, ...] = ("en", "fr")


@dataclass(frozen=True)
class ValidationResult:
    """Report the identity and validated inputs of a Generate package."""

    package_id: str
    input_paths: tuple[Path, ...]


@dataclass(frozen=True)
class GenerateResult:
    paths: tuple[Path, ...]
    row_counts: dict[str, int]
    anomaly_counts: dict[str, int]


def _example_path(example: str) -> Path:
    if example not in {"crm", "insurance", "computer"}:
        raise ConfigurationError(f"Unknown Generate example: {example}")
    return Path(str(files("tabalyst").joinpath("generate_examples", example)))


def _apportion(total: int, weights: dict[str, int]) -> dict[str, int]:
    if total < len(weights):
        raise ConfigurationError("--rows is smaller than the number of combined inputs.")
    denominator = sum(weights.values())
    result = {name: total * weight // denominator for name, weight in weights.items()}
    remaining = total - sum(result.values())
    order = sorted(weights, key=lambda name: (-(total * weights[name] % denominator), name))
    for name in order[:remaining]:
        result[name] += 1
    for name in sorted(weights):
        if result[name] == 0:
            donor = min(
                (other for other in weights if result[other] > 1),
                key=lambda other: (-result[other], other),
            )
            result[donor] -= 1
            result[name] = 1
    return result


def _package_datasets(package: DatasetPackage) -> list[dict[str, object]]:
    raw = package.manifest["datasets"]
    if not isinstance(raw, list) or any(not isinstance(item, dict) for item in raw):
        raise ConfigurationError("PACKAGE_SCHEMA: invalid datasets")
    return cast(list[dict[str, object]], raw)


def validate_generate_package(path: str | Path) -> ValidationResult:
    """Validate a package without planning or creating outputs."""
    package = load_generate_package(path)
    if any(dataset.get("row_source") == "columns" for dataset in _package_datasets(package)):
        load_columns_definition(package)
    if any(dataset.get("row_source") == "catalog_steps" for dataset in _package_datasets(package)):
        _validate_computer_anomaly_profiles(package)
    return ValidationResult(package.id, tuple(sorted(package.input_paths)))


def _computer_anomaly_profile(
    package: DatasetPackage, name: str, output_profile: str,
) -> dict[str, object]:
    """Validate a Computer mutation profile against both localized outputs."""
    profiles = package.manifest.get("anomaly_profiles", {})
    if not isinstance(profiles, dict) or name not in profiles:
        available = ", ".join(profiles) if isinstance(profiles, dict) else "none"
        raise ConfigurationError(f"Unknown anomaly profile: {name}. Available: {available}")
    profile = profiles[name]
    if not isinstance(profile, dict) or set(profile) != {"targets", "operations"}:
        raise ConfigurationError(f"PACKAGE_ANOMALY: invalid profile {name}")
    if profile["targets"] != ["computers"]:
        raise ConfigurationError(f"PACKAGE_ANOMALY: {name} must target computers")
    operations = profile["operations"]
    if not isinstance(operations, list) or not 1 <= len(operations) <= 256:
        raise ConfigurationError(f"PACKAGE_ANOMALY: invalid operations in {name}")
    fields = set(PROFILE_COLUMNS[output_profile]) - set(LABEL_FIELDS)
    for index, operation in enumerate(operations, 1):
        if not isinstance(operation, dict) or set(operation) - OPERATION_KEYS:
            raise ConfigurationError(f"PACKAGE_ANOMALY: invalid operation {index} in {name}")
        kind = operation.get("kind")
        column = operation.get("column")
        value = operation.get("value")
        when = operation.get("when", {})
        problem = operation_option_error(operation)
        if (problem is not None or not isinstance(kind, str) or kind not in OPERATION_KINDS
            or kind not in ROW_KINDS and (not isinstance(column, str) or column not in fields)
            or not isinstance(when, dict) or len(when) > 1
            or any(not isinstance(key, str) or key not in fields or not isinstance(expected, str)
                   for key, expected in when.items())):
            raise ConfigurationError(
                f"PACKAGE_ANOMALY: invalid operation {index} in {name}"
                + (f": {problem}" if problem else ""))
        if kind in {"replace", "swap"} and (not isinstance(value, str)
                                                or kind == "swap" and (value not in fields or value == column)):
            raise ConfigurationError(f"PACKAGE_ANOMALY: invalid value in operation {index}")
        if kind == "format" and (not isinstance(value, str) or value not in {
            *FORMAT_VALUES, "unit_gb", "unit_suffix",
        }):
            raise ConfigurationError(f"PACKAGE_ANOMALY: invalid format in operation {index}")
        if value == "unit_gb" and column not in {"memory_gb", "storage_gb", "gpu_vram_gb"}:
            raise ConfigurationError(f"PACKAGE_ANOMALY: unit_gb requires a GB capacity in operation {index}")
        if value == "unit_suffix" and column not in UNIT_COLUMNS:
            raise ConfigurationError(f"PACKAGE_ANOMALY: unit_suffix requires a measured column in operation {index}")
        if kind in {"set_missing", "duplicate"} and "value" in operation:
            raise ConfigurationError(f"PACKAGE_ANOMALY: unused value in operation {index}")
    return {"id": name, "operations": operations}


def _check_counts(operations: list[dict[str, object]], rows: int, where: str) -> None:
    """Reject an absolute anomaly count larger than the dataset before any write."""
    try:
        check_operation_counts(operations, rows, where)
    except ValueError as exc:
        raise ConfigurationError(f"PACKAGE_ANOMALY: {exc}") from exc


def _validate_computer_anomaly_profiles(package: DatasetPackage) -> None:
    """Reject invalid rules before Computer generation or validation succeeds."""
    profiles = package.manifest.get("anomaly_profiles", {})
    if not isinstance(profiles, dict):
        raise ConfigurationError("PACKAGE_ANOMALY: profiles must be a mapping")
    for name in profiles:
        _computer_anomaly_profile(package, name, "extended")


def _computer_plan(
    path: str | Path, *, output_dir: str | Path | None,
    output: str | Path | None, request: str | Path | None,
    rows: int | None, seed: int | None, as_of_date: str | None,
    generation_profile: str | None, output_profile: str | None,
    market: str | None, locales: str | None, unit_style: str | None,
    unit_columns: str | None,
    anomaly_profile: str | None, force: bool,
    validate_only: bool,
) -> ComputerPlan:
    package = load_generate_package(path)
    _validate_computer_anomaly_profiles(package)
    if validate_only and (output_dir is not None or output is not None):
        raise ConfigurationError("--validate-only does not take a destination.")
    if (output is None) == (output_dir is None) and not validate_only:
        raise ConfigurationError("Give exactly one destination: -o or -d.")
    if request is not None:
        request_path = Path(request)
        try:
            if request_path.stat().st_size > 1_048_576:
                raise ConfigurationError("Generate request exceeds 1 MiB.")
            raw = json.loads(request_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ConfigurationError(f"Invalid Generate request {request_path}: {exc}") from exc
        allowed = {"dataset", "rows", "seed", "as_of_date", "generation_profile",
                   "output_profile", "market", "locales", "unit_style", "unit_columns",
                   "anomaly_profile"}
        if not isinstance(raw, dict) or set(raw) - allowed:
            raise ConfigurationError("Generate request has unknown fields or is not an object.")
    else:
        raw = {}
        request_path = None
    datasets = package.manifest["datasets"]
    if not isinstance(datasets, list) or len(datasets) != 1 or not isinstance(datasets[0], dict):
        raise ConfigurationError("This Generate lot supports the Computer package only.")
    dataset = datasets[0]
    if dataset.get("id") != "computers" or dataset.get("row_source") != "catalog_steps":
        raise ConfigurationError("This Generate lot supports the Computer package only.")
    if raw.get("dataset", "computers") != "computers":
        raise ConfigurationError("Unknown Generate dataset in request.")
    defaults = package.manifest["defaults"]
    if not isinstance(defaults, dict):
        raise ConfigurationError("PACKAGE_SCHEMA: invalid defaults")
    effective_rows = rows if rows is not None else raw.get("rows", defaults.get("rows", 10))
    effective_seed = seed if seed is not None else raw.get("seed", defaults.get("seed", 0))
    effective_date = as_of_date if as_of_date is not None else raw.get("as_of_date", defaults.get("as_of_date", "2000-01-01"))
    effective_generation = generation_profile if generation_profile is not None else raw.get("generation_profile", "balanced")
    effective_output = output_profile if output_profile is not None else raw.get("output_profile", "compact")
    effective_market = market if market is not None else raw.get("market", "ca")
    requested_locales = locales.split(",") if locales is not None else raw.get("locales")
    requested_columns = unit_columns if unit_columns is not None else raw.get("unit_columns")
    effective_units = (unit_style if unit_style is not None else
                       raw.get("unit_style", "localized" if requested_columns is not None else "numeric"))
    effective_anomaly = anomaly_profile if anomaly_profile is not None else raw.get("anomaly_profile")
    if type(effective_rows) is not int or not 1 <= effective_rows <= MAX_ROWS:
        raise ConfigurationError("--rows must be an integer from 1 to 10000000.")
    if type(effective_seed) is not int:
        raise ConfigurationError("--seed must be an integer.")
    try:
        if not isinstance(effective_date, str) or date.fromisoformat(effective_date).isoformat() != effective_date:
            raise ValueError
    except ValueError as exc:
        raise ConfigurationError("--as-of-date must be YYYY-MM-DD.") from exc
    generation_profiles = package.manifest.get("generation_profiles")
    if not isinstance(effective_generation, str) or not isinstance(generation_profiles, dict) or effective_generation not in generation_profiles:
        available = ", ".join(generation_profiles) if isinstance(generation_profiles, dict) else "none"
        raise ConfigurationError(
            f"Unknown generation profile: {effective_generation}. Available: {available}")
    if not isinstance(effective_output, str) or effective_output not in PROFILE_COLUMNS:
        raise ConfigurationError(f"Unsupported Computer output profile: {effective_output}")
    profiles = package.manifest.get("output_profiles")
    if not isinstance(profiles, dict) or profiles.get(effective_output) != list(PROFILE_COLUMNS[effective_output]):
        raise ConfigurationError(f"PACKAGE_OUTPUT: {effective_output} profile differs from Computer register")
    if not isinstance(effective_market, str) or effective_market not in {"ca", "us"}:
        raise ConfigurationError(f"Unsupported Computer market: {effective_market}")
    if requested_locales is None:
        # A single file is the point of -o, so it defaults to English; -d keeps both.
        requested_locales = ["en"] if output is not None else ["en", "fr"]
    if (not isinstance(requested_locales, list) or not requested_locales
            or any(item not in {"en", "fr"} for item in requested_locales)
            or len(set(requested_locales)) != len(requested_locales)):
        raise ConfigurationError("Computer locales must be en, fr or en,fr.")
    effective_locales = tuple(item for item in ("en", "fr") if item in requested_locales)
    if output is not None and len(effective_locales) != 1:
        raise ConfigurationError("-o writes one locale; use --locales en or --locales fr, or use -d.")
    if not isinstance(effective_units, str) or effective_units not in {"numeric", "localized"}:
        raise ConfigurationError(f"Unsupported Computer unit style: {effective_units}")
    if isinstance(requested_columns, str):
        selected_units = requested_columns.split(",")
    elif isinstance(requested_columns, list):
        selected_units = requested_columns
    elif requested_columns is None:
        selected_units = [column for column in PROFILE_COLUMNS[effective_output]
                          if column in UNIT_COLUMNS]
    else:
        raise ConfigurationError("unit_columns must list measured columns.")
    if (not selected_units or any(not isinstance(column, str) or
                                  column not in UNIT_COLUMNS or
                                  column not in PROFILE_COLUMNS[effective_output]
                                  for column in selected_units)
        or len(set(selected_units)) != len(selected_units)
        or effective_units == "numeric" and requested_columns is not None):
        raise ConfigurationError("unit_columns must be distinct measured columns in the output profile and require localized style.")
    ordered_units = tuple(column for column in PROFILE_COLUMNS[effective_output]
                          if column in selected_units)
    if effective_anomaly is not None:
        if not isinstance(effective_anomaly, str):
            raise ConfigurationError("anomaly_profile must name a profile.")
        selected_anomaly = _computer_anomaly_profile(package, effective_anomaly,
                                                     effective_output)
        operations = cast(list[dict[str, object]], selected_anomaly["operations"])
        _check_counts(operations, effective_rows, f"{effective_anomaly} on computers")
        if effective_units == "localized" and any(
            operation.get("value") in {"unit_gb", "unit_suffix"}
            and operation["column"] in ordered_units for operation in operations
        ):
            raise ConfigurationError("Unit anomalies require numeric values in their target columns.")
    destination = Path(output_dir) if output_dir is not None else None
    if destination is not None and destination.exists() and not destination.is_dir():
        raise InputError(f"Output directory path is a file: {destination}")
    artifacts_list: list[GenerateArtifact] = []
    if output is not None:
        target = Path(output)
        if target.suffix.lower() != ".csv":
            raise ConfigurationError("-o must name a .csv file.")
        locale = effective_locales[0]
        if effective_anomaly is None:
            artifacts_list.append(GenerateArtifact("computers", locale, target))
        else:
            # The file asked for holds the errors; the clean copy and the summary stay internal.
            artifacts_list.extend((
                GenerateArtifact("computers", f"{locale}_altered", target),
                GenerateArtifact("computers", f"{locale}_changes",
                                 target.with_name(f"{target.stem}.changes.csv")),
            ))
        destination = target.parent
    elif destination is not None:
        artifacts_list.extend(
            GenerateArtifact("computers", locale, destination / f"computers-{locale}.csv")
            for locale in effective_locales
        )
        artifacts_list.append(
            GenerateArtifact("computers", "metadata", destination / "computers.meta.json"))
        if effective_anomaly is not None:
            for locale in effective_locales:
                prefix = f"computers-{locale}.{effective_anomaly}"
                artifacts_list.extend((
                    GenerateArtifact("computers", f"{locale}_altered", destination / f"{prefix}.csv"),
                    GenerateArtifact("computers", f"{locale}_changes", destination / f"{prefix}.changes.csv"),
                    GenerateArtifact("computers", f"{locale}_summary", destination / f"{prefix}.summary.json"),
                ))
    if destination is not None and destination.resolve().is_relative_to(package.root):
        raise InputError("Generate output directory cannot be inside its source package.")
    artifacts = tuple(artifacts_list)
    sources = set(package.input_paths)
    if request_path is not None:
        sources.add(request_path.resolve())
    validate_outputs(((package.root / "dataset.yaml", item.path) for item in artifacts),
                     sources=sources, force=force, label="Generate")
    return ComputerPlan(package, artifacts, {"computers": effective_rows},
                        effective_seed, effective_date, effective_generation,
                        effective_output, effective_market, effective_units,
                        ordered_units,
                        effective_anomaly,
                        force, request_path, effective_locales)


def build_generate_plan(
    definition_path: str | Path | None = None,
    *,
    example: str | None = None,
    output: str | Path | None = None,
    output_dir: str | Path | None = None,
    rows: int | None = None,
    seed: int | None = None,
    as_of_date: str | None = None,
    anomaly_profile: str | None = None,
    force: bool = False,
    request: str | Path | None = None,
    package_path: str | Path | None = None,
    generation_profile: str | None = None,
    output_profile: str | None = None,
    market: str | None = None,
    locales: str | None = None,
    unit_style: str | None = None,
    unit_columns: str | None = None,
    validate_only: bool = False,
) -> GeneratePlan | ComputerPlan:
    """Validate a Generate source and plan every artifact before writing."""
    if package_path is not None:
        if definition_path is not None:
            raise ConfigurationError("Give either definition_path or package_path.")
        definition_path = package_path
    if (definition_path is None) == (example is None):
        raise ConfigurationError("Give exactly one definition file or --example.")
    if example is not None:
        source_path = _example_path(example)
    else:
        assert definition_path is not None
        source_path = Path(definition_path)
    package: DatasetPackage | None = None
    if source_path.is_dir() or source_path.name == "dataset.yaml":
        package = load_generate_package(source_path)
        if any(dataset.get("row_source") == "catalog_steps"
               for dataset in _package_datasets(package)):
            return _computer_plan(
                source_path, output_dir=output_dir, output=output, request=request,
                rows=rows, seed=seed, as_of_date=as_of_date,
                generation_profile=generation_profile, output_profile=output_profile,
                market=market, locales=locales, unit_style=unit_style,
                unit_columns=unit_columns,
                anomaly_profile=anomaly_profile,
                force=force,
                validate_only=validate_only,
            )
        definition = load_columns_definition(package)
        if validate_only:
            if output is not None or output_dir is not None:
                raise ConfigurationError("--validate-only does not take a destination.")
            return GeneratePlan(definition, (), {}, 0, definition.defaults.get("as_of_date", "2000-01-01"),
                                None, force, package)
    else:
        raise ConfigurationError(
            f"PACKAGE_FORMAT: {source_path} is not a Generate package; "
            "definition_version: 1 YAML is unsupported. Supply a package directory "
            "or its dataset.yaml."
        )
    if (request is not None or generation_profile is not None or output_profile is not None
        or market is not None or locales is not None or unit_style is not None
        or unit_columns is not None):
        raise ConfigurationError("Package request and profile options require a package path.")
    if (output is None) == (output_dir is None):
        raise ConfigurationError("Give exactly one destination: -o or -d.")
    if rows is not None and (type(rows) is not int or not 1 <= rows <= 10_000_000):
        raise ConfigurationError("--rows must be an integer from 1 to 10000000.")
    if seed is not None and type(seed) is not int:
        raise ConfigurationError("--seed must be an integer.")
    effective_date = as_of_date or definition.defaults.get("as_of_date", "2000-01-01")
    try:
        if date.fromisoformat(effective_date).isoformat() != effective_date:
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise ConfigurationError("--as-of-date must be YYYY-MM-DD.") from exc
    profiles = {profile["id"]: profile for profile in definition.anomaly_profiles}
    if anomaly_profile is not None and anomaly_profile not in profiles:
        raise ConfigurationError(
            f"Unknown anomaly profile: {anomaly_profile}. Available: {', '.join(profiles) or 'none'}")
    dataset_by_id = {dataset["id"]: dataset for dataset in definition.datasets}
    counts = {
        name: dataset["rows"] for name, dataset in dataset_by_id.items()
        if "combine" not in dataset
    }
    combined = [dataset for dataset in definition.datasets if "combine" in dataset]
    if rows is not None:
        if len(counts) == 1 and not combined:
            counts[next(iter(counts))] = rows
        elif len(combined) == 1 and set(combined[0]["combine"]["inputs"]) == set(counts):
            counts = _apportion(rows, counts)
        else:
            raise ConfigurationError("--rows is ambiguous for independent datasets.")
    for dataset in combined:
        counts[dataset["id"]] = sum(counts[name] for name in dataset["combine"]["inputs"])
    if anomaly_profile is not None:
        for target in profiles[anomaly_profile]["targets"]:
            _check_counts(profiles[anomaly_profile]["operations"], counts[target],
                          f"{anomaly_profile} on {target}")

    if output is not None:
        if len(definition.datasets) != 1 or anomaly_profile is not None:
            raise ConfigurationError("-o requires exactly one clean CSV; use -d.")
        target = Path(output)
        if target.suffix.lower() != ".csv":
            raise ConfigurationError("-o must name a .csv file.")
        destination = target.parent
    else:
        assert output_dir is not None
        destination = Path(output_dir)
        if destination.exists() and not destination.is_dir():
            raise InputError(f"Output directory path is a file: {destination}")
    artifacts: list[GenerateArtifact] = []
    for dataset in definition.datasets:
        name = dataset["id"]
        clean = Path(output) if output is not None else destination / f"{name}.csv"
        artifacts.append(GenerateArtifact(name, "clean", clean))
        if anomaly_profile and name in profiles[anomaly_profile]["targets"]:
            prefix = destination / f"{name}.{anomaly_profile}"
            artifacts.extend((
                GenerateArtifact(name, "altered", Path(f"{prefix}.csv")),
                GenerateArtifact(name, "changes", Path(f"{prefix}.changes.csv")),
                GenerateArtifact(name, "summary", Path(f"{prefix}.summary.json")),
            ))
    protected = [definition.source]
    if package is not None:
        if destination.resolve().is_relative_to(package.root):
            raise InputError("Generate output directory cannot be inside its source package.")
        protected.extend(package.input_paths)
    protected.extend(Path(str(files("tabalyst").joinpath("generate_resources", *name.split("/"))))
                     for name in SCHEMAS)
    validate_outputs(
        ((definition.source, artifact.path) for artifact in artifacts),
        sources=protected,
        force=force,
        label="Generate",
    )
    if output_dir is not None and path_key(destination) == path_key(definition.source):
        raise InputError("Output directory is the definition file.")
    return GeneratePlan(
        definition, tuple(artifacts), counts,
        seed if seed is not None else definition.defaults.get("seed", 0),
        effective_date, anomaly_profile, force, package,
    )


def _publish_artifacts(
    plan: GeneratePlan | ComputerPlan,
    writer: Callable[[GenerateArtifact, Path], None],
    anomaly_counts: dict[str, int] | None = None,
    batch_writer: Callable[[dict[Path, Path]], None] | None = None,
) -> GenerateResult:
    """Stage all files then replace finals, restoring earlier files on failure."""
    if isinstance(plan, ComputerPlan):
        source = plan.package.root / "dataset.yaml"
        sources = set(plan.package.input_paths)
        if plan.request_path is not None:
            sources.add(plan.request_path.resolve())
    else:
        source = plan.definition.source
        sources = {source, *(Path(str(files("tabalyst").joinpath("generate_resources", *name.split("/")))) for name in SCHEMAS)}
        if plan.package is not None:
            sources.update(plan.package.input_paths)
    validate_outputs(
        ((source, artifact.path) for artifact in plan.artifacts),
        sources=sources,
        force=plan.force, label="Generate",
    )
    stages: dict[Path, Path] = {}
    backups: dict[Path, Path] = {}
    published: list[Path] = []
    preserve_backups = False
    publishing = False
    try:
        for artifact in plan.artifacts:
            target = artifact.path
            target.parent.mkdir(parents=True, exist_ok=True)
            descriptor, name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
            os.close(descriptor)
            stage = Path(name)
            stages[target] = stage
            apply_default_file_mode(stage)
            if batch_writer is None:
                writer(artifact, stage)
            if batch_writer is None and not stage.is_file():
                raise ReportError(f"Generator did not prepare {target}")
        if batch_writer is not None:
            batch_writer(stages)
        for artifact in plan.artifacts:
            target = artifact.path
            stage = stages[target]
            if not stage.is_file():
                raise ReportError(f"Generator did not prepare {target}")
            with stage.open("r+b") as stream:
                os.fsync(stream.fileno())
        # Recheck after expensive generation: never silently overwrite a newly
        # created target when force was not selected.
        validate_outputs(
            ((source, artifact.path) for artifact in plan.artifacts),
            sources=sources, force=plan.force, label="Generate",
        )
        publishing = True
        for artifact in plan.artifacts:
            target = artifact.path
            if target.exists():
                descriptor, name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".bak")
                os.close(descriptor)
                backup = Path(name)
                backups[target] = backup
                shutil.copy2(target, backup)
            os.replace(stages[target], target)
            published.append(target)
    except Exception as exc:
        failed_recovery: list[Path] = []
        for target in reversed(published):
            try:
                if target in backups:
                    os.replace(backups[target], target)
                else:
                    target.unlink(missing_ok=True)
            except OSError:
                failed_recovery.append(target)
        if failed_recovery:
            preserve_backups = True
            details = ", ".join(str(target) for target in failed_recovery)
            saved = ", ".join(str(path) for path in backups.values() if path.exists())
            raise ReportError(f"Generate publication failed; inspect finals: {details}; backups: {saved}") from exc
        if publishing:
            finals = ", ".join(str(artifact.path) for artifact in plan.artifacts)
            raise ReportError(
                f"Generate publication failed: {exc}; previous files restored "
                f"where possible. Inspect finals: {finals}"
            ) from exc
        if isinstance(exc, (ConfigurationError, InputError, ReportError)):
            raise
        raise ReportError(f"Generate failed: {exc}") from exc
    finally:
        for path in stages.values():
            path.unlink(missing_ok=True)
        if not preserve_backups:
            for path in backups.values():
                path.unlink(missing_ok=True)
    return GenerateResult(
        tuple(artifact.path for artifact in plan.artifacts),
        dict(plan.rows), dict(anomaly_counts or {}),
    )


def generate_datasets(plan: GeneratePlan | ComputerPlan) -> GenerateResult:
    """Generate clean datasets, shared entities and ordered combines."""
    if isinstance(plan, ComputerPlan):
        if not plan.artifacts:
            raise ConfigurationError("A validation-only plan has no outputs to generate.")
        from tabalyst.generate_anomalies import inject_anomalies

        computer_anomaly_counts: dict[str, int] = {}

        def write_computer(stages: dict[Path, Path]) -> None:
            paths = {artifact.kind: stages[artifact.path] for artifact in plan.artifacts}
            # What the destination does not publish (for -o: the clean copy, the
            # metadata and the summary) is still needed to build the rest.
            # It sits beside the staged files: millions of rows would fill a small system temp.
            scratch = Path(stack.enter_context(tempfile.TemporaryDirectory(
                prefix=".generate-", dir=next(iter(stages.values())).parent)))
            for locale in plan.locales:
                paths.setdefault(locale, scratch / f"computers-{locale}.csv")
                paths.setdefault(f"{locale}_summary", scratch / f"{locale}.summary.json")
            paths.setdefault("metadata", scratch / "computers.meta.json")
            metadata = write_computer_csvs(
                plan.package, {locale: paths[locale] for locale in plan.locales}, paths["metadata"],
                rows=plan.rows["computers"], seed=plan.seed,
                as_of_date=date.fromisoformat(plan.as_of_date),
                generation_profile=plan.generation_profile,
                output_profile=plan.output_profile, market=plan.market,
                unit_style=plan.unit_style,
                unit_columns=plan.unit_columns if plan.unit_style == "localized" else None,
            )
            if plan.anomaly_profile is None:
                return
            profile = _computer_anomaly_profile(
                plan.package, plan.anomaly_profile, plan.output_profile,
            )
            summaries: dict[str, object] = {}
            for locale in plan.locales:
                summary = inject_anomalies(
                    paths[locale], paths[f"{locale}_altered"],
                    paths[f"{locale}_changes"], dataset="computers",
                    profile=profile, seed=plan.seed, count=plan.rows["computers"],
                    delimiter=",", locale=locale, unit_suffixes=UNIT_COLUMNS,
                )
                summary.update({
                    "locale": locale, "definition_id": plan.package.id,
                    "tabalyst_version": __version__, "as_of_date": plan.as_of_date,
                    "format": "tabalyst.generate.package", "format_version": "0.1.0",
                    "package_version": plan.package.package_version,
                })
                paths[f"{locale}_summary"].write_text(
                    json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8", newline="\n",
                )
                computer_anomaly_counts[locale] = cast(int, summary["changed_cells"])
                summaries[locale] = {
                    "altered": f"computers-{locale}.{plan.anomaly_profile}.csv",
                    "changes": f"computers-{locale}.{plan.anomaly_profile}.changes.csv",
                    "summary": f"computers-{locale}.{plan.anomaly_profile}.summary.json",
                    "changed_cells": summary["changed_cells"],
                }
            request = metadata["request"]
            assert isinstance(request, dict)
            request["anomaly_profile"] = plan.anomaly_profile
            metadata["anomalies"] = summaries
            paths["metadata"].write_text(
                json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8", newline="\n",
            )

        with ExitStack() as stack:
            return _publish_artifacts(plan, lambda _artifact, _stage: None,
                                      anomaly_counts=computer_anomaly_counts,
                                      batch_writer=write_computer)
    if not plan.artifacts:
        raise ConfigurationError("A validation-only plan has no outputs to generate.")
    from tabalyst.generate_anomalies import inject_anomalies

    datasets = {dataset["id"]: dataset for dataset in plan.definition.datasets}
    supported = {"constant", "sequence", "choice", "integer", "decimal",
                 "boolean", "date", "datetime", "text", "reference",
                 "relative_date", "conditional", "common", "insurance"}
    for dataset in (*plan.definition.entities, *datasets.values()):
        if "combine" in dataset:
            continue
        columns = dataset.get("columns") or plan.definition.schemas[dataset["schema"]]["columns"]
        for column in columns:
            if column["generate"]["kind"] not in supported:
                raise ConfigurationError(f"Column {column['name']!r} requires a later Generate lot.")
    references = CommonReferences() if any(
        column["generate"]["kind"] in {"common", "insurance"}
        for dataset in (*plan.definition.entities, *datasets.values()) if "combine" not in dataset
        for column in (dataset.get("columns") or plan.definition.schemas[dataset["schema"]]["columns"])
    ) else None
    needs_insurance = any(
        column["generate"]["kind"] == "insurance"
        for dataset in datasets.values() if "combine" not in dataset
        for column in (dataset.get("columns") or plan.definition.schemas[dataset["schema"]]["columns"])
    )
    if needs_insurance and references is None:
        references = CommonReferences()
    insurance = (InsuranceProvider(references, plan.package)
                 if needs_insurance and references is not None and plan.package is not None else None)
    pools = {
        entity["id"]: list(generate_rows(
            f"entity:{entity['id']}", entity["columns"], entity["count"],
            plan.seed, plan.as_of_date, references=references,
            cohorts=plan.definition.cohorts,
        )) for entity in plan.definition.entities
    }
    staged_clean: dict[str, Path] = {}
    staged_changes: dict[str, Path] = {}
    summaries: dict[str, dict] = {}
    anomaly_counts: dict[str, int] = {}
    profiles = {profile["id"]: profile for profile in plan.definition.anomaly_profiles}
    delimiter = plan.definition.csv.get("delimiter", ",")

    def combined_rows(dataset: dict):
        with ExitStack() as stack:
            for input_id in dataset["combine"]["inputs"]:
                stream = stack.enter_context(staged_clean[input_id].open(
                    "r", encoding="utf-8", newline="",
                ))
                reader = csv.DictReader(stream, delimiter=delimiter)
                for row in reader:
                    if dataset["combine"].get("source_column"):
                        row[dataset["combine"]["source_column"]] = (
                            datasets[input_id].get("source", input_id)
                        )
                    yield row

    def writer(artifact: GenerateArtifact, stage: Path) -> None:
        dataset = datasets[artifact.dataset_id]
        if artifact.kind == "altered":
            descriptor, name = tempfile.mkstemp(dir=stage.parent, prefix=".generate-changes-", suffix=".tmp")
            os.close(descriptor)
            journal = Path(name)
            staged_changes[artifact.dataset_id] = journal
            summary = inject_anomalies(
                staged_clean[artifact.dataset_id], stage, journal,
                dataset=artifact.dataset_id, profile=profiles[plan.anomaly_profile],
                seed=plan.seed, count=plan.rows[artifact.dataset_id], delimiter=delimiter,
            )
            summary.update({
                "definition_id": plan.definition.id,
                "tabalyst_version": __version__,
                "as_of_date": plan.as_of_date,
            })
            if plan.package is not None:
                summary.update({"format": "tabalyst.generate.package",
                                "format_version": "0.1.0",
                                "package_version": plan.package.package_version})
            summaries[artifact.dataset_id] = summary
            anomaly_counts[artifact.dataset_id] = cast(int, summary["changed_cells"])
            return
        if artifact.kind == "changes":
            shutil.copyfile(staged_changes[artifact.dataset_id], stage)
            return
        if artifact.kind == "summary":
            stage.write_text(json.dumps(summaries[artifact.dataset_id],
                                        ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8", newline="\n")
            return
        if "combine" in dataset:
            first = datasets[dataset["combine"]["inputs"][0]]
            columns = first.get("columns") or plan.definition.schemas[first["schema"]]["columns"]
            headers = [column["name"] for column in columns]
            if dataset["combine"].get("source_column"):
                headers.append(dataset["combine"]["source_column"])
            rows = combined_rows(dataset)
        else:
            columns = dataset.get("columns") or plan.definition.schemas[dataset["schema"]]["columns"]
            headers = [column["name"] for column in columns]
            rows = generate_rows(
                artifact.dataset_id, columns, plan.rows[artifact.dataset_id],
                plan.seed, plan.as_of_date, pools, references,
                cohorts=plan.definition.cohorts, fixed_cohort=dataset.get("cohort"),
                source=dataset.get("source"),
                insurance_provider=insurance,
            )
        count = write_csv(
            stage, headers, rows, delimiter=delimiter,
        )
        if count != plan.rows[artifact.dataset_id]:
            raise ReportError(f"Generated row count differs for {artifact.dataset_id}")
        staged_clean[artifact.dataset_id] = stage
    try:
        return _publish_artifacts(plan, writer, anomaly_counts)
    finally:
        for journal in staged_changes.values():
            journal.unlink(missing_ok=True)

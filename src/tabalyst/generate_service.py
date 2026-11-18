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
import time
from collections import Counter
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass, field, replace
from datetime import date
from functools import partial
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
    AnomalyEvent,
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
from tabalyst.generate_computer_parallel import worker_count
from tabalyst.generate_csv import write_csv
from tabalyst.generate_definition import GenerateDefinition
from tabalyst.generate_insurance import (
    EXTENDED_FIELDS as INSURANCE_EXTENDED_FIELDS,
)
from tabalyst.generate_insurance import (
    FIELDS as INSURANCE_FIELDS,
)
from tabalyst.generate_insurance import (
    TRANCHE_B_FIELDS as INSURANCE_TRANCHE_B_FIELDS,
)
from tabalyst.generate_insurance import (
    TRANCHE_C_FIELDS as INSURANCE_TRANCHE_C_FIELDS,
)
from tabalyst.generate_insurance import (
    InsuranceProvider,
    extend_insurance_row,
    extend_tranche_b_row,
    extend_tranche_c_row,
    insurance_canonical,
    insurance_contextual,
)
from tabalyst.generate_ml import is_ml_profile, write_ml_labels_csv
from tabalyst.generate_package import MAX_ROWS, DatasetPackage, load_generate_package
from tabalyst.generate_population import (
    RELATIONAL_CLIENTS_FIELDS,
    RELATIONAL_CONTRATS_FIELDS,
    RELATIONAL_PAIEMENTS_FIELDS,
    RELATIONAL_RECLAMATIONS_FIELDS,
    PopulationModel,
)
from tabalyst.generate_references import SCHEMAS, CommonReferences
from tabalyst.generate_rules import Conventions
from tabalyst.generate_scenarios import (
    CATEGORIES,
    foreign_scenario_key,
    is_scenario_profile,
)
from tabalyst.generate_truth import (
    GENERATION_VERSION,
    KINDS,
    TRUTH_COLUMNS,
    AbsenceProbability,
    Counts,
    ManifestDocument,
    MetricsDocument,
    Rows,
    RulesDocument,
    ScenarioMetrics,
    TruthResult,
    build_truth,
    document_text,
    file_entry,
    scenario_entries,
    write_truth_csv,
)
from tabalyst.generate_values import _stream, generate_rows


@dataclass(frozen=True)
class GenerateArtifact:
    dataset_id: str
    kind: str
    path: Path


# Kinds and suffixes of the files a scenario profile adds, manifest last (contract 5.1).
TRUTH_ARTIFACTS = (("truth", "csv"), ("rules", "json"), ("metrics", "json"),
                   ("manifest", "json"))


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
    output_profile: str = "default"
    relational: bool = False
    row_order: str = "default"


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
    anomaly_profiles: tuple[str, ...]
    force: bool
    request_path: Path | None
    locales: tuple[str, ...] = ("en", "fr")
    workers: int | None = None

    @property
    def anomaly_profile(self) -> str | None:
        """The first anomaly profile, which is the only one unless several were asked."""
        return self.anomaly_profiles[0] if self.anomaly_profiles else None


@dataclass(frozen=True)
class ValidationResult:
    """Report the identity and validated inputs of a Generate package."""

    package_id: str
    input_paths: tuple[Path, ...]


@dataclass(frozen=True)
class GenerateResult:
    """Paths written, row and changed-cell counts, and how long each part took.

    `timings` splits `seconds` into `rows` (generation), `errors` (anomaly
    injection) and `publish` (staging, checks and replacing the files); it is
    empty for packages that report only the total. `workers` is the number of
    processes that generated the rows. `artifacts` are the files written with
    their kind, in the order of `paths` (a scenario profile adds `truth`,
    `rules`, `metrics` and `manifest`).
    """

    paths: tuple[Path, ...]
    row_counts: dict[str, int]
    anomaly_counts: dict[str, int]
    seconds: float = 0.0
    timings: dict[str, float] = field(default_factory=dict)
    workers: int = 1
    artifacts: tuple[GenerateArtifact, ...] = ()


@dataclass(frozen=True)
class GenerateProgress:
    """One progress step of a run: what is being done and how far it is."""

    stage: str
    done: int
    total: int
    elapsed_seconds: float


GenerateProgressCallback = Callable[[GenerateProgress], None]


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
        if (foreign := foreign_scenario_key(operation)) is not None:
            raise ConfigurationError(
                f"PACKAGE_ANOMALY: operation {index} in {name}: scenario keys "
                f"({foreign}) are not supported by the Computer package")
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


def _anomaly_kind(locale: str, profile: str, part: str) -> str:
    """The artifact kind of one file of a profile in one locale."""
    return f"{locale}_{profile}_{part}"


def _report_stage(report: Callable[[str, int, int], None], stage: str, total: int, done: int) -> None:
    report(stage, done, total)


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
    validate_only: bool, workers: int | None = None,
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
    requested_anomalies = anomaly_profile if anomaly_profile is not None else raw.get("anomaly_profile")
    if type(effective_rows) is not int or not 1 <= effective_rows <= MAX_ROWS:
        raise ConfigurationError("--rows must be an integer from 1 to 10000000.")
    if workers is not None and (type(workers) is not int or workers < 1):
        raise ConfigurationError("--workers must be an integer of 1 or more.")
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
    if requested_anomalies is None:
        effective_anomalies: tuple[str, ...] = ()
    elif isinstance(requested_anomalies, str):
        effective_anomalies = tuple(item.strip() for item in requested_anomalies.split(","))
    elif isinstance(requested_anomalies, list) and all(isinstance(item, str) for item in requested_anomalies):
        effective_anomalies = tuple(requested_anomalies)
    else:
        raise ConfigurationError("anomaly_profile must name a profile.")
    if not all(effective_anomalies) or len(set(effective_anomalies)) != len(effective_anomalies):
        raise ConfigurationError("anomaly_profile must list each profile once, with no empty name.")
    if output is not None and len(effective_anomalies) > 1:
        raise ConfigurationError("-o writes one file, so it takes one anomaly profile; use -d for several.")
    for effective_anomaly in effective_anomalies:
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
        if not effective_anomalies:
            artifacts_list.append(GenerateArtifact("computers", locale, target))
        else:
            # The file asked for holds the errors; the clean copy and the summary stay internal.
            name = effective_anomalies[0]
            artifacts_list.extend((
                GenerateArtifact("computers", _anomaly_kind(locale, name, "altered"), target),
                GenerateArtifact("computers", _anomaly_kind(locale, name, "changes"),
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
        for name in effective_anomalies:
            for locale in effective_locales:
                prefix = f"computers-{locale}.{name}"
                artifacts_list.extend((
                    GenerateArtifact("computers", _anomaly_kind(locale, name, "altered"),
                                     destination / f"{prefix}.csv"),
                    GenerateArtifact("computers", _anomaly_kind(locale, name, "changes"),
                                     destination / f"{prefix}.changes.csv"),
                    GenerateArtifact("computers", _anomaly_kind(locale, name, "summary"),
                                     destination / f"{prefix}.summary.json"),
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
                        effective_anomalies,
                        force, request_path, effective_locales, workers)


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
    workers: int | None = None,
    relational: bool = False,
    row_order: str = "default",
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
            if relational:
                raise ConfigurationError("--relational applies to the Insurance package only.")
            if row_order != "default":
                raise ConfigurationError("--row-order applies to the Insurance package only.")
            return _computer_plan(
                source_path, output_dir=output_dir, output=output, request=request,
                rows=rows, seed=seed, as_of_date=as_of_date,
                generation_profile=generation_profile, output_profile=output_profile,
                market=market, locales=locales, unit_style=unit_style,
                unit_columns=unit_columns,
                anomaly_profile=anomaly_profile,
                force=force,
                validate_only=validate_only,
                workers=workers,
            )
        if row_order not in {"default", "branch", "chronological", "agency", "shuffled"}:
            raise ConfigurationError(
                f"Unsupported row order: {row_order!r}. Expected one of: "
                "agency, branch, chronological, default, shuffled."
            )
        if relational:
            if package.id != "insurance":
                raise ConfigurationError("--relational applies to the Insurance package only.")
            if output is not None:
                raise ConfigurationError("--relational generates multiple tables; use -d.")
        if row_order != "default" and package.id != "insurance":
            raise ConfigurationError("--row-order applies to the Insurance package only.")
        effective_output = output_profile or "default"
        if package.id == "insurance":
            if anomaly_profile == "rare_events" and output_profile is None:
                effective_output = "extended"
            elif anomaly_profile == "schema_drift" and output_profile is None:
                effective_output = "complete"
            elif anomaly_profile == "ml_fraud_imbalanced" and output_profile is None:
                effective_output = "extended"
            elif output_profile is None:
                effective_output = "default"
            if effective_output not in {
                "default", "extended", "complete", "flattened", "flattened-extended", "flattened-complete",
            }:
                raise ConfigurationError(f"unsupported Insurance output profile {output_profile!r}")
        elif output_profile is not None:
            raise ConfigurationError("--output-profile applies to the Computer and Insurance packages only.")
        definition = load_columns_definition(package)
        if validate_only:
            if output is not None or output_dir is not None:
                raise ConfigurationError("--validate-only does not take a destination.")
            return GeneratePlan(definition, (), {}, 0, definition.defaults.get("as_of_date", "2000-01-01"),
                                None, force, package, output_profile=effective_output, relational=relational,
                                row_order=row_order)
    else:
        raise ConfigurationError(
            f"PACKAGE_FORMAT: {source_path} is not a Generate package; "
            "definition_version: 1 YAML is unsupported. Supply a package directory "
            "or its dataset.yaml."
        )
    if (request is not None or generation_profile is not None
        or market is not None or locales is not None or unit_style is not None
        or unit_columns is not None):
        raise ConfigurationError("Package request and profile options require a package path.")
    if workers is not None:
        raise ConfigurationError("--workers applies to the Computer package only.")
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
        floor = profiles[anomaly_profile].get("min_rows")
        for target in profiles[anomaly_profile]["targets"]:
            if floor is not None and counts[target] < floor:
                raise ConfigurationError(
                    f"Profile {anomaly_profile} needs at least {floor:,} rows on {target} "
                    f"(below that its rare cases are not rare); {counts[target]:,} requested.")
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
    if relational:
        table_ids = ("clients", "contrats", "reclamations", "paiements")
        for tbl in table_ids:
            artifacts.append(GenerateArtifact(tbl, "clean", destination / f"{tbl}.csv"))
            profile_prefix = f"{tbl}.{anomaly_profile}" if anomaly_profile else tbl
            ops = profiles.get(anomaly_profile, {}).get("operations", []) if anomaly_profile else []
            for role, suffix in TRUTH_ARTIFACTS:
                if role == "manifest" and anomaly_profile and is_ml_profile(profiles[anomaly_profile], ops):
                    artifacts.append(GenerateArtifact(tbl, "ml_labels", Path(f"{destination}/{profile_prefix}.ml_labels.csv")))
                artifacts.append(GenerateArtifact(tbl, role, Path(f"{destination}/{profile_prefix}.{role}.{suffix}")))
        total_contracts = rows if rows is not None else definition.defaults.get("rows", 275000)
        counts = {tbl: total_contracts for tbl in table_ids}
    else:
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
                if is_scenario_profile(profiles[anomaly_profile]["operations"]):
                    # The ground truth of a scenario profile (contract insurance-v2.md 5.1). The
                    # manifest comes last: it lists the digest of every other file.
                    ops = profiles[anomaly_profile]["operations"]
                    for role, suffix in TRUTH_ARTIFACTS:
                        if role == "manifest" and is_ml_profile(profiles[anomaly_profile], ops):
                            artifacts.append(GenerateArtifact(name, "ml_labels", Path(f"{prefix}.ml_labels.csv")))
                        artifacts.append(GenerateArtifact(name, role, Path(f"{prefix}.{role}.{suffix}")))
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
        output_profile=effective_output,
        relational=relational,
        row_order=row_order,
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
        dict(plan.rows), dict(anomaly_counts or {}), artifacts=plan.artifacts,
    )


TRUTH_KINDS = frozenset(role for role, _ in TRUTH_ARTIFACTS) | {"ml_labels"}


def _write_truth_artifact(
    plan: GeneratePlan, artifact: GenerateArtifact, stage: Path, staged: dict[Path, Path],
    staged_clean: dict[str, Path], events: dict[str, list[AnomalyEvent]],
    truths: dict[str, TruthResult], summaries: dict[str, dict], delimiter: str,
    report: Callable[[str, int, int], None],
) -> None:
    """Write one ground-truth file of a scenario profile (contract insurance-v2.md 5).

    The truth is built once, with the first of these files, from the staged clean and altered
    files; the manifest digests every other staged file of the plan, so it is written last.
    """
    dataset = artifact.dataset_id
    profile = next(p for p in plan.definition.anomaly_profiles if p["id"] == plan.anomaly_profile)
    if dataset not in truths:
        catalogue = plan.definition.rules
        if catalogue is None:  # validate_generate_mapping refuses this profile already
            raise ConfigurationError(f"{profile['id']}: a scenario profile needs rules")
        used = {operation["rule_id"] for operation in profile["operations"]
                if "rule_id" in operation}
        altered = next(a.path for a in plan.artifacts
                       if a.dataset_id == dataset and a.kind == "altered")
        report(f"Writing the truth of {altered.name}", 0, plan.rows[dataset])
        truths[dataset] = build_truth(
            staged_clean[dataset], staged[altered], events.get(dataset, []), summaries[dataset],
            dataset=dataset, profile=profile,
            rules=[rule for rule in catalogue.rules if rule.id in used],
            conventions=catalogue.conventions, as_of_date=plan.as_of_date,
            delimiter=delimiter, canonical=insurance_canonical, seed=plan.seed)
        report(f"Writing the truth of {altered.name}", plan.rows[dataset], plan.rows[dataset])
    truth = truths[dataset]
    if artifact.kind == "truth":
        write_truth_csv(stage, truth.lines)
        return
    if artifact.kind == "ml_labels":
        write_ml_labels_csv(stage, truth.ml_labels)
        return
    if artifact.kind == "rules":
        text = document_text(truth.rules)
    elif artifact.kind == "metrics":
        text = document_text(truth.metrics)
    else:
        files = [file_entry(other.kind, other.path.name, staged[other.path])
                 for other in plan.artifacts if other.kind != "manifest"]
        manifest = ManifestDocument(
            tabalyst_version=__version__, generation_version=GENERATION_VERSION,
            seed=plan.seed, as_of_date=plan.as_of_date, rows=plan.rows[dataset],
            dataset=dataset, profile=profile["id"], output_profile=plan.output_profile,
            package_version=plan.package.package_version if plan.package else None,
            definition_id=plan.definition.id,
            scenarios=scenario_entries(profile["operations"]), files=files,
            truth_columns=list(TRUTH_COLUMNS))
        text = document_text(manifest)
    stage.write_text(text, encoding="utf-8", newline="\n")


def _generate_relational(
    plan: GeneratePlan,
    report: Callable[[str, int, int], None],
) -> GenerateResult:
    """Generate the four relational tables and their ground truth files from PopulationModel."""
    references = CommonReferences()
    total_contracts = plan.rows.get("contrats", 275000)
    m22_count = 1 if plan.anomaly_profile else 0
    assert plan.package is not None
    model = PopulationModel(
        common=references,
        package=plan.package,
        seed=plan.seed,
        total_contracts=total_contracts,
        as_of_date=plan.as_of_date,
        m22_cases=m22_count,
        row_order=plan.row_order,
    )

    actual_counts = {
        "clients": len(model._customers_list),
        "contrats": len(model.contracts),
        "reclamations": len(model.all_claims),
        "paiements": len(model.all_payments),
    }

    def write_relational(stages: dict[Path, Path]) -> None:
        table_generators = {
            "clients": (RELATIONAL_CLIENTS_FIELDS, (model.to_client_row(c) for c in model._customers_list), len(model._customers_list)),
            "contrats": (RELATIONAL_CONTRATS_FIELDS, (model.to_relational_contract_row(ctr) for ctr in model.contracts), len(model.contracts)),
            "reclamations": (RELATIONAL_RECLAMATIONS_FIELDS, (model.to_claim_row(clm) for clm in model.all_claims), len(model.all_claims)),
            "paiements": (RELATIONAL_PAIEMENTS_FIELDS, (model.to_payment_row(pmt) for pmt in model.all_payments), len(model.all_payments)),
        }

        # 1. Clean CSV tables
        for artifact in plan.artifacts:
            if artifact.kind == "clean":
                tbl = artifact.dataset_id
                headers, row_iter, total = table_generators[tbl]
                stage = stages[artifact.path]
                write_csv(
                    stage, list(headers), row_iter, delimiter=",", total=total,
                    on_rows=partial(_report_stage, report, f"Writing {artifact.path.name}", total),
                )

        # 2. Ground truth per table
        catalogue = plan.definition.rules
        for artifact in plan.artifacts:
            if artifact.kind not in TRUTH_KINDS:
                continue
            tbl = artifact.dataset_id
            stage = stages[artifact.path]
            lines = model.get_table_truth_lines(tbl)
            if artifact.kind == "truth":
                write_truth_csv(stage, lines)
            elif artifact.kind == "rules":
                rules = [r for r in catalogue.rules if r.id in {line.rule_id for line in lines if line.rule_id}] if catalogue else []
                conventions = catalogue.conventions if catalogue else Conventions(branch_column="filiale", date_format={"principal": "%Y-%m-%d"})
                rules_doc = RulesDocument(
                    dataset=tbl, profile=plan.anomaly_profile or "relational",
                    as_of_date=plan.as_of_date, conventions=conventions,
                    rules=rules,
                )
                stage.write_text(document_text(rules_doc), encoding="utf-8", newline="\n")
            elif artifact.kind == "metrics":
                injected = [line for line in lines if line.kind == "injected"]
                counts = Counts(
                    events=len({line.event_id for line in injected}),
                    changed_cells=len(injected),
                    distinct_changed_cells=len({(line.row_number, line.column) for line in injected}),
                    net_differences=sum(line.kind == "net_difference" for line in lines),
                )
                categories = dict.fromkeys(sorted(CATEGORIES), 0)
                kinds = dict.fromkeys(sorted(KINDS), 0)
                for line in lines:
                    kinds[line.kind] = kinds.get(line.kind, 0) + 1
                    if line.category in categories:
                        categories[line.category] += 1
                rule_violations = Counter(line.rule_id for line in lines if line.kind == "rule_violation" and line.rule_id)
                scenarios_metrics: dict[str, ScenarioMetrics] = {}
                scenario_groups: dict[str, set[str]] = {}
                scenario_rows: dict[str, set[int]] = {}
                scenario_meta: dict[str, tuple[str | None, str, str]] = {}
                for line in lines:
                    if line.scenario_id:
                        scenario_groups.setdefault(line.scenario_id, set()).add(line.group_id or str(line.row_number))
                        scenario_rows.setdefault(line.scenario_id, set()).add(line.row_number)
                        scenario_meta[line.scenario_id] = (line.rarity_level or "uncommon", line.category, line.severity)
                for sc_id, groups in scenario_groups.items():
                    sc_rarity, sc_cat, sc_sev = scenario_meta[sc_id]
                    scenarios_metrics[sc_id] = ScenarioMetrics(
                        rarity_level=sc_rarity,
                        requested_cases=len(groups),
                        applied_cases=len(groups),
                        rows_touched=len(scenario_rows.get(sc_id, set())),
                        eligible_population=actual_counts[tbl],
                        category=sc_cat,
                        severity=sc_sev,
                    )
                absence = {
                    sc_id: AbsenceProbability(cases=len(groups), probability=None, reason="multi_row_case")
                    for sc_id, groups in scenario_groups.items()
                }
                metrics_doc = MetricsDocument(
                    dataset=tbl, profile=plan.anomaly_profile or "relational",
                    rows=Rows(total=actual_counts[tbl], by_branch={}),
                    counts=counts,
                    scenarios=scenarios_metrics,
                    rules=dict(rule_violations),
                    categories=categories,
                    kinds=kinds,
                    absence_probability=absence,
                    root_causes={},
                )
                stage.write_text(document_text(metrics_doc), encoding="utf-8", newline="\n")
            elif artifact.kind == "manifest":
                tbl_files = [
                    file_entry(other.kind, other.path.name, stages[other.path])
                    for other in plan.artifacts
                    if other.dataset_id == tbl and other.kind != "manifest"
                ]
                manifest_doc = ManifestDocument(
                    tabalyst_version=__version__,
                    generation_version=GENERATION_VERSION,
                    seed=plan.seed,
                    as_of_date=plan.as_of_date,
                    rows=actual_counts[tbl],
                    dataset=tbl,
                    profile=plan.anomaly_profile or "relational",
                    output_profile=plan.output_profile,
                    package_version=plan.package.package_version if plan.package else None,
                    definition_id=plan.definition.id,
                    scenarios=[],
                    files=tbl_files,
                    truth_columns=list(TRUTH_COLUMNS),
                )
                stage.write_text(document_text(manifest_doc), encoding="utf-8", newline="\n")

    published = _publish_artifacts(plan, lambda _a, _s: None, batch_writer=write_relational)
    return replace(published, row_counts=actual_counts)


def generate_datasets(plan: GeneratePlan | ComputerPlan,
                      on_progress: GenerateProgressCallback | None = None) -> GenerateResult:
    """Generate clean datasets, shared entities and ordered combines.

    `on_progress` is called with the stage, the work done and the work to do,
    in rows: generated, written or altered. The result carries the
    total time and, for Computer, its split.
    """
    started = time.perf_counter()

    def report(stage: str, done: int, total: int) -> None:
        if on_progress is not None:
            on_progress(GenerateProgress(stage, done, total, time.perf_counter() - started))

    result = _generate(plan, report)
    seconds = time.perf_counter() - started
    if not result.timings:
        return replace(result, seconds=seconds)
    timings = dict(result.timings)
    timings["publish"] = max(0.0, seconds - timings.get("rows", 0.0) - timings.get("errors", 0.0))
    return replace(result, seconds=seconds, timings=timings)


def _generate(plan: GeneratePlan | ComputerPlan,
              report: Callable[[str, int, int], None]) -> GenerateResult:
    if isinstance(plan, ComputerPlan):
        if not plan.artifacts:
            raise ConfigurationError("A validation-only plan has no outputs to generate.")
        from tabalyst.generate_anomalies import inject_anomalies

        computer_anomaly_counts: dict[str, int] = {}
        timings: dict[str, float] = {"rows": 0.0, "errors": 0.0}
        rows_total = plan.rows["computers"]
        workers = worker_count(plan.workers, rows_total)

        def write_computer(stages: dict[Path, Path]) -> None:
            paths = {artifact.kind: stages[artifact.path] for artifact in plan.artifacts}
            # What the destination does not publish (for -o: the clean copy, the
            # metadata and the summary) is still needed to build the rest.
            # It sits beside the staged files: millions of rows would fill a small system temp.
            scratch = Path(stack.enter_context(tempfile.TemporaryDirectory(
                prefix=".generate-", dir=next(iter(stages.values())).parent)))
            for locale in plan.locales:
                paths.setdefault(locale, scratch / f"computers-{locale}.csv")
                for name in plan.anomaly_profiles:
                    paths.setdefault(_anomaly_kind(locale, name, "summary"),
                                     scratch / f"{locale}.{name}.summary.json")
            paths.setdefault("metadata", scratch / "computers.meta.json")
            began = time.perf_counter()
            metadata = write_computer_csvs(
                plan.package, {locale: paths[locale] for locale in plan.locales}, paths["metadata"],
                rows=plan.rows["computers"], seed=plan.seed,
                as_of_date=date.fromisoformat(plan.as_of_date),
                generation_profile=plan.generation_profile,
                output_profile=plan.output_profile, market=plan.market,
                unit_style=plan.unit_style,
                unit_columns=plan.unit_columns if plan.unit_style == "localized" else None,
                on_rows=lambda done: report("Generating rows", done, rows_total),
                workers=workers,
            )
            timings["rows"] = time.perf_counter() - began
            if not plan.anomaly_profiles:
                return
            began = time.perf_counter()
            several = len(plan.anomaly_profiles) > 1
            summaries: dict[str, dict[str, object]] = {locale: {} for locale in plan.locales}
            for name in plan.anomaly_profiles:
                profile = _computer_anomaly_profile(plan.package, name, plan.output_profile)
                for locale in plan.locales:
                    stage = f"Injecting errors ({locale}, {name})" if several else f"Injecting errors ({locale})"
                    summary = inject_anomalies(
                        paths[locale], paths[_anomaly_kind(locale, name, "altered")],
                        paths[_anomaly_kind(locale, name, "changes")], dataset="computers",
                        profile=profile, seed=plan.seed, count=plan.rows["computers"],
                        delimiter=",", locale=locale, unit_suffixes=UNIT_COLUMNS,
                        on_row=partial(_report_stage, report, stage, rows_total),
                    )
                    summary.update({
                        "locale": locale, "definition_id": plan.package.id,
                        "tabalyst_version": __version__, "as_of_date": plan.as_of_date,
                        "format": "tabalyst.generate.package", "format_version": "0.1.0",
                        "package_version": plan.package.package_version,
                    })
                    paths[_anomaly_kind(locale, name, "summary")].write_text(
                        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                        encoding="utf-8", newline="\n",
                    )
                    computer_anomaly_counts[f"{locale}/{name}" if several else locale] = cast(
                        int, summary["changed_cells"])
                    summaries[locale][name] = {
                        "altered": f"computers-{locale}.{name}.csv",
                        "changes": f"computers-{locale}.{name}.changes.csv",
                        "summary": f"computers-{locale}.{name}.summary.json",
                        "changed_cells": summary["changed_cells"],
                    }
            request = metadata["request"]
            assert isinstance(request, dict)
            # One profile keeps the layout earlier files had; several list them by name.
            if several:
                request["anomaly_profiles"] = list(plan.anomaly_profiles)
                metadata["anomalies"] = summaries
            else:
                request["anomaly_profile"] = plan.anomaly_profiles[0]
                metadata["anomalies"] = {locale: found[plan.anomaly_profiles[0]]
                                         for locale, found in summaries.items()}
            paths["metadata"].write_text(
                json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8", newline="\n",
            )
            timings["errors"] = time.perf_counter() - began

        with ExitStack() as stack:
            published = _publish_artifacts(plan, lambda _artifact, _stage: None,
                                           anomaly_counts=computer_anomaly_counts,
                                           batch_writer=write_computer)
        return replace(published, timings=timings, workers=workers)
    if isinstance(plan, GeneratePlan) and plan.relational:
        return _generate_relational(plan, report)
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
    staged: dict[Path, Path] = {}
    events: dict[str, list[AnomalyEvent]] = {}
    truths: dict[str, TruthResult] = {}
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
        staged[artifact.path] = stage
        dataset = datasets[artifact.dataset_id]
        if artifact.kind in TRUTH_KINDS:
            _write_truth_artifact(plan, artifact, stage, staged, staged_clean, events, truths,
                                  summaries, delimiter, report)
            return
        if artifact.kind == "altered":
            descriptor, name = tempfile.mkstemp(dir=stage.parent, prefix=".generate-changes-", suffix=".tmp")
            os.close(descriptor)
            journal = Path(name)
            staged_changes[artifact.dataset_id] = journal
            profile = profiles[plan.anomaly_profile]
            scenarios = is_scenario_profile(profile["operations"])
            found = events.setdefault(artifact.dataset_id, [])
            summary = inject_anomalies(
                staged_clean[artifact.dataset_id], stage, journal,
                dataset=artifact.dataset_id, profile=profile,
                seed=plan.seed, count=plan.rows[artifact.dataset_id], delimiter=delimiter,
                on_row=partial(_report_stage, report, f"Injecting errors in {artifact.path.name}",
                               plan.rows[artifact.dataset_id]),
                on_event=found.append if scenarios else None,
                canonical=insurance_canonical if scenarios else None,
                contextual=insurance_contextual(references) if scenarios and references else None,
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
        is_insurance = plan.package is not None and plan.package.id == "insurance"
        is_flattened_insurance = is_insurance and plan.output_profile.startswith("flattened")
        is_extended_insurance = is_insurance and plan.output_profile in {"extended", "complete"}
        is_complete_insurance = is_insurance and plan.output_profile == "complete"

        if is_flattened_insurance:
            sub_profile = "default" if plan.output_profile == "flattened" else plan.output_profile.split("-", 1)[1]
            is_combined = "combine" in dataset or artifact.dataset_id == "insurance-combined"
            if is_combined:
                headers = [*INSURANCE_FIELDS, "filiale"]
            else:
                headers = list(INSURANCE_FIELDS)
            if sub_profile in {"extended", "complete"}:
                headers.extend(INSURANCE_EXTENDED_FIELDS)
            if sub_profile == "complete":
                headers.extend(INSURANCE_TRANCHE_B_FIELDS)
                headers.extend(INSURANCE_TRANCHE_C_FIELDS)

            assert references is not None
            assert plan.package is not None
            pop_model = PopulationModel(
                common=references,
                package=plan.package,
                seed=plan.seed,
                total_contracts=plan.rows[artifact.dataset_id],
                as_of_date=plan.as_of_date,
                branch=dataset.get("source"),
                row_order=plan.row_order,
            )
            headers_set = set(headers)
            rows = (
                {k: v for k, v in pop_model.to_flattened_row(ctr, output_profile=sub_profile).items() if k in headers_set}
                for ctr in pop_model.contracts
            )
        elif "combine" in dataset:
            first = datasets[dataset["combine"]["inputs"][0]]
            columns = first.get("columns") or plan.definition.schemas[first["schema"]]["columns"]
            headers = [column["name"] for column in columns]
            if dataset["combine"].get("source_column"):
                headers.append(dataset["combine"]["source_column"])
            if is_extended_insurance:
                headers.extend(INSURANCE_EXTENDED_FIELDS)
            if is_complete_insurance:
                headers.extend(INSURANCE_TRANCHE_B_FIELDS)
                headers.extend(INSURANCE_TRANCHE_C_FIELDS)
            rows = combined_rows(dataset)
        else:
            columns = dataset.get("columns") or plan.definition.schemas[dataset["schema"]]["columns"]
            headers = [column["name"] for column in columns]
            base_rows = generate_rows(
                artifact.dataset_id, columns, plan.rows[artifact.dataset_id],
                plan.seed, plan.as_of_date, pools, references,
                cohorts=plan.definition.cohorts, fixed_cohort=dataset.get("cohort"),
                source=dataset.get("source"),
                insurance_provider=insurance,
            )
            if is_extended_insurance:
                headers.extend(INSURANCE_EXTENDED_FIELDS)
                streams_ext = {
                    col: _stream(plan.seed, artifact.dataset_id, col, "extended")
                    for col in INSURANCE_EXTENDED_FIELDS
                }
                branch = dataset.get("source", "")
                ext_rows = (
                    extend_insurance_row(row, branch, streams_ext, plan.as_of_date)
                    for row in base_rows
                )
                if is_complete_insurance:
                    headers.extend(INSURANCE_TRANCHE_B_FIELDS)
                    headers.extend(INSURANCE_TRANCHE_C_FIELDS)
                    streams_b = {
                        col: _stream(plan.seed, artifact.dataset_id, col, "complete")
                        for col in INSURANCE_TRANCHE_B_FIELDS
                    }
                    streams_c = {
                        col: _stream(plan.seed, artifact.dataset_id, col, "complete")
                        for col in INSURANCE_TRANCHE_C_FIELDS
                    }
                    rows = (
                        extend_tranche_c_row(
                            extend_tranche_b_row(row, streams_b),
                            branch,
                            streams_c,
                            plan.as_of_date,
                        )
                        for row in ext_rows
                    )
                else:
                    rows = ext_rows
            else:
                rows = base_rows
        total = plan.rows[artifact.dataset_id]
        count = write_csv(
            stage, headers, rows, delimiter=delimiter, total=total,
            on_rows=partial(_report_stage, report, f"Writing {artifact.path.name}", total),
        )
        if count != plan.rows[artifact.dataset_id]:
            raise ReportError(f"Generated row count differs for {artifact.dataset_id}")
        staged_clean[artifact.dataset_id] = stage
    try:
        return _publish_artifacts(plan, writer, anomaly_counts)
    finally:
        for journal in staged_changes.values():
            journal.unlink(missing_ok=True)

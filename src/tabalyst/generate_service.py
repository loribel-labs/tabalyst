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

from tabalyst import __version__
from tabalyst.batch import apply_default_file_mode, path_key, validate_outputs
from tabalyst.errors import ConfigurationError, InputError, ReportError
from tabalyst.generate_csv import write_csv
from tabalyst.generate_definition import GenerateDefinition, load_generate_definition
from tabalyst.generate_insurance import SCHEMAS as INSURANCE_SCHEMAS
from tabalyst.generate_insurance import InsuranceProvider
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


@dataclass(frozen=True)
class GenerateResult:
    paths: tuple[Path, ...]
    row_counts: dict[str, int]
    anomaly_counts: dict[str, int]


def _example_path(example: str) -> Path:
    if example not in {"crm", "insurance"}:
        raise ConfigurationError(f"Unknown Generate example: {example}")
    return Path(str(files("tabalyst").joinpath("generate_examples", f"{example}.yaml")))


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
) -> GeneratePlan:
    """Validate a v1 definition and every output before generation."""
    if (definition_path is None) == (example is None):
        raise ConfigurationError("Give exactly one definition file or --example.")
    if (output is None) == (output_dir is None):
        raise ConfigurationError("Give exactly one destination: -o or -d.")
    definition = load_generate_definition(
        _example_path(example) if example is not None else definition_path
    )
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
        raise ConfigurationError(f"Unknown anomaly profile: {anomaly_profile}")
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

    if output is not None:
        if len(definition.datasets) != 1 or anomaly_profile is not None:
            raise ConfigurationError("-o requires exactly one clean CSV; use -d.")
        target = Path(output)
        if target.suffix.lower() != ".csv":
            raise ConfigurationError("-o must name a .csv file.")
        destination = target.parent
    else:
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
    protected.extend(Path(str(files("tabalyst").joinpath("generate_resources", *name.split("/"))))
                     for name in SCHEMAS)
    protected.extend(Path(str(files("tabalyst").joinpath("generate_resources", "insurance", name)))
                     for name in INSURANCE_SCHEMAS)
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
        effective_date, anomaly_profile, force,
    )


def _publish_artifacts(
    plan: GeneratePlan,
    writer: Callable[[GenerateArtifact, Path], None],
    anomaly_counts: dict[str, int] | None = None,
) -> GenerateResult:
    """Stage all files then replace finals, restoring earlier files on failure."""
    validate_outputs(
        ((plan.definition.source, artifact.path) for artifact in plan.artifacts),
        sources=[plan.definition.source, *(Path(str(files("tabalyst").joinpath("generate_resources", *name.split("/")))) for name in SCHEMAS)],
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
            writer(artifact, stage)
            if not stage.is_file():
                raise ReportError(f"Generator did not prepare {target}")
            with stage.open("r+b") as stream:
                os.fsync(stream.fileno())
        # Recheck after expensive generation: never silently overwrite a newly
        # created target when force was not selected.
        validate_outputs(
            ((plan.definition.source, artifact.path) for artifact in plan.artifacts),
            sources=[plan.definition.source, *(Path(str(files("tabalyst").joinpath("generate_resources", *name.split("/")))) for name in SCHEMAS)],
        force=plan.force, label="Generate",
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


def generate_datasets(plan: GeneratePlan) -> GenerateResult:
    """Generate clean datasets, shared entities and ordered combines."""
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
    insurance = InsuranceProvider(references) if any(
        column["generate"]["kind"] == "insurance"
        for dataset in datasets.values() if "combine" not in dataset
        for column in (dataset.get("columns") or plan.definition.schemas[dataset["schema"]]["columns"])
    ) else None
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
                "definition_version": 1,
                "tabalyst_version": __version__,
                "as_of_date": plan.as_of_date,
            })
            summaries[artifact.dataset_id] = summary
            anomaly_counts[artifact.dataset_id] = summary["changed_cells"]
            return
        if artifact.kind == "changes":
            shutil.copyfile(staged_changes[artifact.dataset_id], stage)
            return
        if artifact.kind == "summary":
            stage.write_text(json.dumps(summaries[artifact.dataset_id],
                                        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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

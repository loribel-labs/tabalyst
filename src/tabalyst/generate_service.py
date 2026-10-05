# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Generate planning and safe multi-artifact publication."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from importlib.resources import files
from pathlib import Path

from tabalyst.batch import apply_default_file_mode, path_key, validate_outputs
from tabalyst.errors import ConfigurationError, InputError, ReportError
from tabalyst.generate_definition import GenerateDefinition, load_generate_definition


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
    # Future packaged resources are added to this list at definition resolution.
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
) -> GenerateResult:
    """Stage all files then replace finals, restoring earlier files on failure."""
    validate_outputs(
        ((plan.definition.source, artifact.path) for artifact in plan.artifacts),
        sources=[plan.definition.source], force=plan.force, label="Generate",
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
            sources=[plan.definition.source], force=plan.force, label="Generate",
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
        dict(plan.rows), {},
    )


def generate_datasets(plan: GeneratePlan) -> GenerateResult:
    """Execute a plan once its value generators are implemented in lot 2."""
    raise ConfigurationError(
        "Generate execution is not available in lot 1; the definition and "
        "all output paths can be validated with build_generate_plan()."
    )

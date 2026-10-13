# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Validate package column datasets for the shared Generate execution engine."""

from __future__ import annotations

from typing import Any

from tabalyst.errors import ConfigurationError
from tabalyst.generate_definition import GenerateDefinition, validate_generate_mapping
from tabalyst.generate_insurance import FIELDS as INSURANCE_FIELDS
from tabalyst.generate_package import DatasetPackage, _relative, _yaml


# YAML schemas are validated at runtime, so nested operation values remain dynamic.
def _columns(package: DatasetPackage, name: object) -> list[dict[str, Any]]:
    source = package.root / "dataset.yaml"
    path = _relative(package.root, name, source, schema=True)
    if path not in package.input_paths:
        raise ConfigurationError(f"PACKAGE_SCHEMA: undeclared schema {path}")
    schema = _yaml(path)
    if not isinstance(schema, dict) or not isinstance(schema.get("columns"), list):
        raise ConfigurationError(f"PACKAGE_SCHEMA: invalid output schema {path}")
    columns = schema["columns"]
    for column in columns:
        if not isinstance(column, dict) or not isinstance(column.get("generate"), dict):
            raise ConfigurationError(f"PACKAGE_SCHEMA: generated columns required in {path}")
        operation = column["generate"]
        if operation.get("kind") == "provider":
            provider = operation.get("name")
            if provider not in {"common.person", "common.address", "common.contact", "insurance"}:
                raise ConfigurationError(f"PACKAGE_PROVIDER: unknown provider {provider!r} in {path}")
            if provider == "insurance":
                if operation.get("field") not in INSURANCE_FIELDS:
                    raise ConfigurationError(f"PACKAGE_PROVIDER: unknown Insurance field in {path}")
                operation["kind"] = "insurance"
            else:
                operation["kind"] = "common"
                operation["provider"] = provider.split(".")[1]
            del operation["name"]
    return columns


def load_columns_definition(package: DatasetPackage) -> GenerateDefinition:
    """Resolve package schemas and validate their shared column semantics."""
    source = package.root / "dataset.yaml"
    manifest = package.manifest
    entities = manifest.get("entities", [])
    cohorts = manifest.get("cohorts", [])
    profiles = manifest.get("anomaly_profiles", {})
    if not isinstance(entities, list) or not isinstance(cohorts, list) or not isinstance(profiles, dict):
        raise ConfigurationError("PACKAGE_SCHEMA: invalid entities, cohorts, or profiles")
    datasets = manifest["datasets"]
    defaults = manifest["defaults"]
    if not isinstance(datasets, list) or not isinstance(defaults, dict):
        raise ConfigurationError("PACKAGE_SCHEMA: invalid datasets or defaults")
    resolved_entities: list[dict[str, Any]] = []
    for entity in entities:
        if not isinstance(entity, dict) or set(entity) != {"id", "count", "generator", "schema"}:
            raise ConfigurationError("PACKAGE_SCHEMA: invalid entity")
        resolved_entities.append({key: value for key, value in entity.items() if key != "schema"}
                                 | {"columns": _columns(package, entity["schema"])})
    resolved_datasets: list[dict[str, Any]] = []
    for dataset in datasets:
        if dataset.get("mode") == "combine":
            resolved_datasets.append({"id": dataset["id"], "combine": {
                "inputs": dataset["inputs"],
                **({"source_column": dataset["source_column"]} if "source_column" in dataset else {}),
            }})
        elif dataset.get("mode") == "generated" and dataset.get("row_source") == "columns":
            resolved_datasets.append({
                "id": dataset["id"], "rows": dataset.get("rows", defaults.get("rows")),
                "columns": _columns(package, dataset["schema"]),
                **({"source": dataset["source"]} if "source" in dataset else {}),
                **({"cohort": dataset["cohort"]} if "cohort" in dataset else {}),
            })
        else:
            raise ConfigurationError("PACKAGE_SCHEMA: expected column dataset or combine")
    anomaly_profiles = []
    for ident, profile in profiles.items():
        if not isinstance(profile, dict) or set(profile) != {"targets", "operations"}:
            raise ConfigurationError(f"PACKAGE_SCHEMA: invalid anomaly profile {ident}")
        anomaly_profiles.append({"id": ident, **profile})
    mapping = {"id": package.id, "defaults": {
        key: value for key, value in defaults.items() if key in {"seed", "as_of_date"}},
        "entities": resolved_entities, "cohorts": cohorts,
        "datasets": resolved_datasets, "anomaly_profiles": anomaly_profiles}
    definition = validate_generate_mapping(mapping, source)
    insurance_datasets = [dataset for dataset in resolved_datasets
                          if "columns" in dataset and any(
                              column["generate"]["kind"] == "insurance"
                              for column in dataset["columns"]
                          )]
    if insurance_datasets:
        if package.id == "insurance" and any(
            [column["name"] for column in dataset["columns"]] != list(INSURANCE_FIELDS)
            for dataset in insurance_datasets
        ):
            raise ConfigurationError("PACKAGE_SCHEMA: Insurance fields differ from provider contract")
        from tabalyst.generate_insurance import InsuranceProvider
        from tabalyst.generate_references import CommonReferences

        InsuranceProvider(CommonReferences(), package)
    return definition

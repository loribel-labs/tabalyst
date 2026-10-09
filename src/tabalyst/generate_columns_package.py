# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Validate package column datasets for the shared Generate execution engine."""

from __future__ import annotations

from tabalyst.errors import ConfigurationError
from tabalyst.generate_definition import GenerateDefinition, validate_generate_mapping
from tabalyst.generate_package import DatasetPackage, _relative, _yaml


def _columns(package: DatasetPackage, name: object) -> list[dict]:
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
            raise ConfigurationError(f"PACKAGE_SCHEMA: CRM requires generated columns in {path}")
        operation = column["generate"]
        if operation.get("kind") == "provider":
            provider = operation.get("name")
            if provider not in {"common.person", "common.address", "common.contact"}:
                raise ConfigurationError(f"PACKAGE_PROVIDER: unknown provider {provider!r} in {path}")
            operation["kind"] = "common"
            operation["provider"] = provider.split(".")[1]
            del operation["name"]
    return columns


def load_columns_definition(package: DatasetPackage) -> GenerateDefinition:
    """Resolve package schemas and validate their shared column semantics."""
    source = package.root / "dataset.yaml"
    manifest = package.manifest
    if package.id != "crm":
        raise ConfigurationError(f"Unsupported column package: {package.id}")
    entities = manifest.get("entities", [])
    cohorts = manifest.get("cohorts", [])
    profiles = manifest.get("anomaly_profiles", {})
    if not isinstance(entities, list) or not isinstance(cohorts, list) or not isinstance(profiles, dict):
        raise ConfigurationError("PACKAGE_SCHEMA: invalid CRM entities, cohorts, or profiles")
    datasets = manifest["datasets"]
    defaults = manifest["defaults"]
    if not isinstance(datasets, list) or not isinstance(defaults, dict):
        raise ConfigurationError("PACKAGE_SCHEMA: invalid CRM datasets or defaults")
    resolved_entities: list[dict] = []
    for entity in entities:
        if not isinstance(entity, dict) or set(entity) != {"id", "count", "generator", "schema"}:
            raise ConfigurationError("PACKAGE_SCHEMA: invalid CRM entity")
        resolved_entities.append({key: value for key, value in entity.items() if key != "schema"}
                                 | {"columns": _columns(package, entity["schema"])})
    resolved_datasets: list[dict] = []
    for dataset in datasets:
        if dataset.get("mode") != "generated" or dataset.get("row_source") != "columns":
            raise ConfigurationError("PACKAGE_SCHEMA: CRM requires generated column datasets")
        resolved_datasets.append({"id": dataset["id"], "rows": dataset.get("rows", defaults.get("rows")),
                                  "columns": _columns(package, dataset["schema"])})
    anomaly_profiles = []
    for ident, profile in profiles.items():
        if not isinstance(profile, dict) or set(profile) != {"targets", "operations"}:
            raise ConfigurationError(f"PACKAGE_SCHEMA: invalid anomaly profile {ident}")
        anomaly_profiles.append({"id": ident, **profile})
    mapping = {"definition_version": 1, "id": package.id, "defaults": {
        key: value for key, value in defaults.items() if key in {"seed", "as_of_date"}},
        "entities": resolved_entities, "cohorts": cohorts,
        "datasets": resolved_datasets, "anomaly_profiles": anomaly_profiles}
    return validate_generate_mapping(mapping, source)

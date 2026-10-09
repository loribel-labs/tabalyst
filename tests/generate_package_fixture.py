# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Build small versioned column packages for Generate behavior tests."""

from __future__ import annotations

from pathlib import Path

import yaml


def write_columns_package(destination: Path, text: str) -> Path:
    """Write a package from compact inline test declarations."""
    source = yaml.safe_load(text)
    root = destination / "package"
    schemas = root / "schemas"
    schemas.mkdir(parents=True, exist_ok=True)
    datasets = []
    entities = []

    def write_schema(name: str, columns: object) -> str:
        relative = f"schemas/{name}.yaml"
        (root / relative).write_text(
            yaml.safe_dump({"columns": columns}, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        return relative

    for entity in source.get("entities", []):
        entities.append({
            "id": entity["id"], "count": entity["count"],
            "generator": entity["generator"],
            "schema": write_schema(f"entity-{entity['id']}", entity["columns"]),
        })
    for dataset in source["datasets"]:
        if "combine" in dataset:
            datasets.append({"id": dataset["id"], "mode": "combine", **dataset["combine"]})
            continue
        columns = dataset.get("columns", source.get("schemas", {}).get(dataset.get("schema"), {}).get("columns"))
        item = {
            "id": dataset["id"], "mode": "generated", "row_source": "columns",
            "rows": dataset["rows"],
            "schema": write_schema(f"dataset-{dataset['id']}", columns),
        }
        for key in ("source", "cohort"):
            if key in dataset:
                item[key] = dataset[key]
        datasets.append(item)
    profiles = {
        profile["id"]: {"targets": profile["targets"], "operations": profile["operations"]}
        for profile in source.get("anomaly_profiles", [])
    }
    manifest = {
        "format": "tabalyst.generate.package", "format_version": "0.1.0",
        "id": source["id"].replace("-", "_"), "package_version": "0.1.0",
        "catalog": "catalog.yaml", "defaults": source.get("defaults", {}),
        "datasets": datasets,
    }
    if entities:
        manifest["entities"] = entities
    if "cohorts" in source:
        manifest["cohorts"] = source["cohorts"]
    if profiles:
        manifest["anomaly_profiles"] = profiles
    (root / "dataset.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8",
    )
    (root / "catalog.yaml").write_text("tables: {}\n", encoding="utf-8")
    return root

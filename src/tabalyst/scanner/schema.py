# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""JSON Schema of the shared Scan document, the base of Scan and Report (design
19.7), generated from the result models.
"""

from __future__ import annotations

import json
from typing import Any

from tabalyst.scanner.models import FORMAT, FORMAT_REVISION, FORMAT_VERSION, ScanResult

SCHEMA_FILE = "tabalyst.scan.schema.json"
# Members of the root that extensions of the base may add: the base reader
# ignores them and the schema of their owner validates them (design 19.1).
EXTENSION_NAMESPACES = {
    "derived": "Analyses computed after the scan, from its samples.",
    "observations": "Findings about the data.",
    "analyses": "Results of the second pass.",
    "report": "What a Report adds to the base: generation and presentation.",
}
# Members whose default is the constant of the format: always written.
_CONSTANTS = ("status", "format", "format_version", "format_revision")


def scan_schema() -> dict[str, Any]:
    """The schema of the base document.

    It describes what a reader accepts (validation mode): the serialization
    mode of Pydantic cannot describe the models that omit unknown members.
    """
    schema = ScanResult.model_json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "Tabalyst Scan"
    schema["description"] = (
        f"Base document {FORMAT}, format {FORMAT_VERSION} revision {FORMAT_REVISION}."
    )
    nodes = [schema, *schema["$defs"].values()]
    for node in nodes:
        properties = node.get("properties", {})
        required = node.setdefault("required", [])
        for name in _CONSTANTS:
            if name in properties and name not in required:
                required.append(name)
        if not required:
            del node["required"]
    schema["properties"]["format_revision"] = {"const": FORMAT_REVISION}
    for name, description in EXTENSION_NAMESPACES.items():
        schema["properties"][name] = {"description": description}
    return schema


def scan_schema_text() -> str:
    """The schema as the committed file writes it."""
    return json.dumps(scan_schema(), indent=2, ensure_ascii=False) + "\n"

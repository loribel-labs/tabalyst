# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""JSON Schema of the second-pass document, generated from its models."""

from __future__ import annotations

import json
from typing import Any

from tabalyst.scanner.schema import finalize_schema
from tabalyst.scanner.secondpass.models import (
    FORMAT,
    FORMAT_REVISION,
    FORMAT_VERSION,
    DeepResult,
)

SCHEMA_FILE = "tabalyst.scan.deep.schema.json"


def deep_schema() -> dict[str, Any]:
    """The schema of the document, in validation mode: what a reader accepts."""
    schema = DeepResult.model_json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "Tabalyst Scan second pass"
    schema["description"] = (
        f"Document {FORMAT}, format {FORMAT_VERSION} revision {FORMAT_REVISION}: "
        "analyses added to a Scan by reading its source again."
    )
    finalize_schema(schema, {"format_revision": FORMAT_REVISION})
    return schema


def deep_schema_text() -> str:
    """The schema as the committed file writes it."""
    return json.dumps(deep_schema(), indent=2, ensure_ascii=False) + "\n"

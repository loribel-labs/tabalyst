# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""JSON Schema of the Report document, the Scan base plus its ``report`` block
(design 19), generated from the report models.
"""

import json
from typing import Any

from tabalyst.models import FORMAT, FORMAT_REVISION, FORMAT_VERSION, ReportProfile
from tabalyst.scanner.schema import EXTENSION_NAMESPACES, finalize_schema

SCHEMA_FILE = "tabalyst.report.schema.json"
# Extension namespaces of the base that a Report does not use yet: open.
_OPEN_NAMESPACES = ("observations", "analyses")


def report_schema() -> dict[str, Any]:
    """The schema of the Report: its root is the base of a Scan at the same
    paths, validated like the Scan schema does, with the ``report`` block
    described. The base identity (``format``, ``format_revision``) is that of
    the Report; the Scan's is in ``report.base_scan``."""
    schema = ReportProfile.model_json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "Tabalyst Report"
    schema["description"] = (
        f"Document {FORMAT}, format {FORMAT_VERSION} revision {FORMAT_REVISION}: "
        "the Scan base at the same paths, plus the report block."
    )
    finalize_schema(schema, {"format_revision": FORMAT_REVISION})
    for name in _OPEN_NAMESPACES:
        schema["properties"][name] = {"description": EXTENSION_NAMESPACES[name]}
    return schema


def report_schema_text() -> str:
    """The schema as the committed file writes it."""
    return json.dumps(report_schema(), indent=2, ensure_ascii=False) + "\n"

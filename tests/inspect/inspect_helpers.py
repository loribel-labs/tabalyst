# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Helpers of the JSON Inspect contract tests.

Production modules of Inspect are imported lazily inside the helpers, so the
tests can be collected before they exist.
"""

import json
from pathlib import Path


def write_text(directory: Path, name: str, content: str) -> Path:
    path = directory / name
    path.write_text(content, encoding="utf-8", newline="")
    return path


def write_json(directory: Path, name: str, data: object) -> Path:
    return write_text(directory, name, json.dumps(data, ensure_ascii=False))


def write_jsonl(directory: Path, name: str, records: list[object]) -> Path:
    lines = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    return write_text(directory, name, lines)


def rows(count: int, **extra: object) -> list[dict]:
    """``count`` small object records, each with an ``id`` and ``extra``."""
    return [{"id": index, **extra} for index in range(1, count + 1)]


def run_scan(source: Path, **settings) -> dict:
    """Scan one source with configuration overrides and return its JSON form."""
    from tabalyst.scanner import ScanConfig, scan

    result = scan(source, config=ScanConfig.model_validate(settings))
    return result.model_dump(mode="json")


def dataset(result: dict, dataset_id: str) -> dict:
    matches = [item for item in result["datasets"] if item["id"] == dataset_id]
    assert len(matches) == 1, f"expected one dataset {dataset_id!r}, found {matches}"
    return matches[0]


def field(dataset_result: dict, display: str) -> dict:
    matches = [item for item in dataset_result["fields"] if item["display"] == display]
    assert len(matches) == 1, f"expected one field {display!r}, found {len(matches)}"
    return matches[0]


def displays(dataset_result: dict) -> list[str]:
    return [item["display"] for item in dataset_result["fields"]]


def inspect_document(source: Path, **settings) -> dict:
    """Inspect one source (reads it, writes nothing) and return its JSON form."""
    from tabalyst.inspector.json_inspect import inspect_source
    from tabalyst.scanner import ScanConfig

    config = ScanConfig.model_validate(settings) if settings else None
    return inspect_source(source, scan_config=config).model_dump(mode="json")


def candidates(document: dict) -> dict[str, dict]:
    return {item["path"]: item for item in document["detection"]["candidates"]}


def warning_codes(document: dict) -> list[str]:
    return [item["code"] for item in document["warnings"]]


def parameters():
    """The measured parameters of detection (design section 15)."""
    from tabalyst.inspector.json_inspect import parameters

    return parameters


def inspect_object(source: Path, **settings):
    """Like ``inspect_document`` but returns the ``InspectDocument`` model."""
    from tabalyst.inspector.json_inspect import inspect_source
    from tabalyst.scanner import ScanConfig

    config = ScanConfig.model_validate(settings) if settings else None
    return inspect_source(source, scan_config=config)


def edit_json_file(path: Path, edit, *, indent: int = 4) -> dict:
    """Load a JSON file, apply ``edit(document)`` and write it back, as a user would."""
    document = json.loads(path.read_text(encoding="utf-8"))
    edit(document)
    path.write_text(json.dumps(document, indent=indent), encoding="utf-8")
    return document

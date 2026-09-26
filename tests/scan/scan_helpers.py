"""Read Tabalyst Scan results through their JSON contract.

The engine is imported lazily so these helpers can be collected before the
``tabalyst.scanner`` package exists.
"""

import json
from pathlib import Path


def write_text(directory: Path, name: str, content: str) -> Path:
    path = directory / name
    path.write_text(content, encoding="utf-8", newline="")
    return path


def write_json(directory: Path, name: str, data: object) -> Path:
    return write_text(directory, name, json.dumps(data, ensure_ascii=False))


def run_scan(source: Path, *, registry=None, **settings) -> dict:
    """Scan one source with configuration overrides and return its JSON form."""
    from tabalyst.scanner import ScanConfig, scan

    options = {} if registry is None else {"registry": registry}
    result = scan(source, config=ScanConfig.model_validate(settings), **options)
    return result.model_dump(mode="json")


def dataset(result: dict, dataset_id: str) -> dict:
    matches = [item for item in result["datasets"] if item["id"] == dataset_id]
    assert len(matches) == 1, f"expected one dataset {dataset_id!r}, found {matches}"
    return matches[0]


def field(dataset_result: dict, display: str) -> dict:
    matches = [item for item in dataset_result["fields"] if item["display"] == display]
    assert len(matches) == 1, f"expected one field {display!r}, found {len(matches)}"
    return matches[0]


def detector(field_result: dict, detector_id: str) -> dict:
    matches = [item for item in field_result["detectors"] if item["id"] == detector_id]
    assert len(matches) == 1, f"expected one detector {detector_id!r}"
    return matches[0]


def stages(field_result: dict) -> dict[str, dict]:
    return {item["stage"]: item for item in field_result["normalization"]["stages"]}

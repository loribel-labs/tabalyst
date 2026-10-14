# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Scan contract: the JSON Schema and the semantic validator of the document
(design 19.7, lot 1a)."""

import copy
import subprocess
import sys
from pathlib import Path

import pytest
from scan_helpers import dataset, field, write_text

from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner.models import ScanResult
from tabalyst.scanner.schema import (
    EXTENSION_NAMESPACES,
    SCHEMA_FILE,
    scan_schema,
    scan_schema_text,
)
from tabalyst.scanner.validation import check_scan

pytestmark = pytest.mark.scan_json_lot("1a")

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "examples" / "input"
SOURCES = [
    "basic.csv",
    "insurance-customers.csv",
    "orders.json",
    "web-events.jsonl",
    "sales.xlsx",
]
# A workbook needs the table to read (what Inspect would choose).
TABLES = {"sales.xlsx": {"excel": {"dataset_path": "$.Orders"}}}
COMMITTED = ROOT / "src" / "tabalyst" / "schemas" / SCHEMA_FILE


def _result(name: str, **settings) -> ScanResult:
    config = ScanConfig.model_validate({**TABLES.get(name, {}), **settings})
    return scan(INPUT / name, config=config, workers=1)


def _limited(tmp_path) -> ScanResult:
    lines = ["id,note"] + [f"C{n:03d},{'y' if n % 4 else ''}" for n in range(40)]
    source = write_text(tmp_path, "ids.csv", "\n".join(lines) + "\n")
    return scan(
        source,
        config=ScanConfig.model_validate({"limits": {"max_distinct_per_field": 10}}),
        workers=1,
    )


@pytest.mark.shipped_exposure_default
def test_the_committed_schema_is_the_generated_one():
    assert COMMITTED.read_text(encoding="utf-8") == scan_schema_text()
    outcome = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "scan_schema.py"), "--check"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert outcome.returncode == 0, outcome.stdout


@pytest.mark.parametrize("name", SOURCES)
def test_the_schema_accepts_the_documents_of_the_reference_sources(name):
    jsonschema = pytest.importorskip("jsonschema")

    document = _result(name).model_dump(mode="json")

    jsonschema.Draft202012Validator(scan_schema()).validate(document)


def test_the_schema_accepts_limited_measures_and_refuses_another_revision(tmp_path):
    jsonschema = pytest.importorskip("jsonschema")
    validator = jsonschema.Draft202012Validator(scan_schema())
    document = _limited(tmp_path).model_dump(mode="json")

    validator.validate(document)
    document["format_revision"] += 1
    assert not validator.is_valid(document)


def test_the_schema_lets_extensions_add_their_namespaces_only(tmp_path):
    jsonschema = pytest.importorskip("jsonschema")
    validator = jsonschema.Draft202012Validator(scan_schema())
    document = _limited(tmp_path).model_dump(mode="json")

    for name in EXTENSION_NAMESPACES:
        document[name] = {"anything": [1, 2]}
    assert validator.is_valid(document)
    document["unknown"] = True
    assert not validator.is_valid(document)


@pytest.mark.parametrize("name", SOURCES)
def test_a_scan_the_engine_produced_has_no_violated_invariant(name):
    assert check_scan(_result(name)) == []


def test_limited_measures_and_released_tables_satisfy_the_invariants(tmp_path):
    assert check_scan(_limited(tmp_path)) == []
    exposed = _result("insurance-customers.csv", limits={"max_distinct_per_field": 50})
    assert check_scan(exposed) == []


def _first_field(document: dict, dataset_id: str, display: str) -> dict:
    return field(dataset(document, dataset_id), display)


MUTATIONS = {
    "presence": lambda d: _first_field(d, "rows", "id")["presence"].update(present=1),
    "native_types": lambda d: _first_field(d, "rows", "id")["native_types"].update(
        string=1
    ),
    "values: count": lambda d: _first_field(d, "rows", "id")["values"].update(count=1),
    "upper_bound": lambda d: _first_field(d, "rows", "id")["values"][
        "cardinality"
    ].update(upper_bound=1),
    "limit must be reached": lambda d: _first_field(d, "rows", "id")["values"][
        "cardinality"
    ].update(threshold_reached_at_record=30),
    "records are only known": lambda d: _first_field(d, "rows", "id")["values"][
        "cardinality"
    ].update(reason="global_budget"),
    "scope": lambda d: d["scope"].update(records_read=1),
    "config_sha256": lambda d: d.update(config_sha256="0" * 64),
    "source.shape": lambda d: d["source"]["shape"].update(fields=1),
    "samples: all counts": lambda d: _first_field(d, "rows", "note")["values"][
        "samples"
    ]["listed"][0].update(count=1),
    "string_lengths": lambda d: _first_field(d, "rows", "id")["string_lengths"][
        "value"
    ]["length_histogram"][0].update(count=1),
}


@pytest.mark.parametrize("expected", MUTATIONS)
def test_a_violated_invariant_is_named_with_its_location(tmp_path, expected):
    document = _limited(tmp_path).model_dump(mode="json")
    broken = copy.deepcopy(document)

    MUTATIONS[expected](broken)
    problems = check_scan(ScanResult.model_validate(broken))

    assert any(expected in problem for problem in problems), problems
    assert check_scan(ScanResult.model_validate(document)) == []

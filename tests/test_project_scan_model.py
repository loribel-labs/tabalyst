# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Project storage over the revised Scan model (lot 1d, decision Q2).

Projects consume the Scan base only: qualified cardinalities, the sample size
K, the common invariants and the refusal of documents the model rejects.
"""

import hashlib
import json

import duckdb
import pytest
from test_project_queries import publish

from tabalyst.errors import InputError
from tabalyst.project_scan_service import rescan_project
from tabalyst.projects._generation import open_generation
from tabalyst.projects._session import inspect_project
from tabalyst.projects._validation import DatabaseValidationError, validate_database
from tabalyst.projects.freshness import project_freshness
from tabalyst.scan_reuse import load_scan
from tabalyst.scanner.models import ScanResult

LIMITED = {"limits": {"max_distinct_per_field": 2}}
TEXT = "v\nA\nb\nc\nd\nA\n"


def test_project_keeps_a_limited_cardinality_with_its_qualification(tmp_path):
    location, _, _, outcome = publish(tmp_path, TEXT, settings=LIMITED)
    cardinality = outcome.result.datasets[0].fields[0].values.cardinality
    assert cardinality.status == "limited"
    assert cardinality.domain == "original"
    assert cardinality.upper_bound == 5
    reopened = load_scan(outcome.scan_path)
    assert reopened == outcome.result
    with open_generation(location, outcome.project.project_id) as pinned:
        assert pinned.result == outcome.result


def test_sample_size_follows_a_lower_tracking_limit_in_a_project(tmp_path):
    _, _, _, outcome = publish(tmp_path, TEXT, settings=LIMITED)
    assert outcome.result.config.limits.max_samples == 2


def test_rescan_with_a_lowered_tracking_limit_keeps_a_valid_configuration(tmp_path):
    location, source, _, first = publish(tmp_path, TEXT, settings=LIMITED)
    source.write_text(TEXT + "e\nf\n", encoding="utf-8")
    with rescan_project(
        location,
        first.project.project_id,
        expected_generation_id=first.project.generation.id,
        expected_source=source,
    ) as result:
        limits = result.published.result.config.limits
        assert (limits.max_distinct_per_field, limits.max_samples) == (2, 2)


def test_validation_refuses_a_scan_that_violates_a_common_invariant(tmp_path):
    _, _, _, outcome = publish(tmp_path, TEXT)
    document = json.loads(outcome.scan_path.read_text(encoding="utf-8"))
    document["datasets"][0]["fields"][0]["values"]["count"] += 1
    broken = ScanResult.model_validate(document)
    connection = duckdb.connect(str(outcome.database_path), read_only=True)
    try:
        with pytest.raises(DatabaseValidationError, match="Scan invariants violated"):
            validate_database(
                connection,
                broken,
                project_id=outcome.project.project_id,
                workspace_id=outcome.project.workspace_id,
                generation_id=outcome.project.generation.id,
                scan_sha256=outcome.project.generation.scan_sha256,
            )
    finally:
        connection.close()


def test_a_scan_written_before_the_revision_is_only_out_of_date(tmp_path):
    location, _, _, outcome = publish(tmp_path, TEXT)
    pid = outcome.project.project_id
    document = json.loads(outcome.scan_path.read_text(encoding="utf-8"))
    del document["datasets"][0]["fields"][0]["values"]["cardinality"]["domain"]
    legacy = json.dumps(document).encode("utf-8")
    outcome.scan_path.write_bytes(legacy)
    # A generation written by an earlier build is hash-consistent: only the
    # model rejects it.
    project_path = location.project_path(pid)
    manifest = json.loads(project_path.read_text(encoding="utf-8"))
    manifest["generation"]["scan_sha256"] = hashlib.sha256(legacy).hexdigest()
    project_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(InputError, match="tabalyst scan"):
        inspect_project(location, pid)
    with pytest.raises(InputError, match="tabalyst scan"):
        project_freshness(location, pid)

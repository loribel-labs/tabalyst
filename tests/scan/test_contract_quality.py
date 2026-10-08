# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contract of the adaptive normalization and of the observations (Scan and
JSON plan, test D13 and requirements NORM-01 to NORM-06, QUAL-01 to QUAL-05).

The behavior is specified in ``docs/dev/scan/design.md`` sections 10 and 18.13.
The expectations are on the document.
"""

from itertools import pairwise

import pytest
from scan_helpers import dataset, field, run_scan, stages, write_text

RELEASE = {"max_distinct_per_field": 50}
CHAIN = ["raw", "nfc", "trim", "collapse_whitespace", "casefold", "strip_accents"]


def _csv(directory, header: str, rows) -> object:
    return write_text(directory, "data.csv", header + "\n" + "\n".join(rows) + "\n")


def _ids(count: int) -> list[str]:
    return [f"v{index:04d}" for index in range(count)]


def _bare(stage: dict) -> dict:
    return stage["cardinality"]


@pytest.mark.scan_json_lot("4b")
def test_D13_stages_that_changed_nothing_take_the_count_of_their_input(tmp_path):
    result = run_scan(_csv(tmp_path, "v", _ids(200)), limits=RELEASE)

    column = field(dataset(result, "rows"), "v")
    chain = stages(column)

    raw = _bare(chain["raw"])
    assert raw == {
        "status": "limited",
        "reason": "distinct_limit",
        "limit": 50,
        "lower_bound": 51,
    }
    for before, name in pairwise(CHAIN):
        assert chain[name]["changed"] == 0
        assert chain[name]["equals"] == before
        # The same count as the raw table: a bound that holds, not "unknown".
        assert _bare(chain[name]) == raw
    # No string changed under any stage: there is no group of variants.
    assert column["normalization"]["variant_groups"] == {
        "status": "complete",
        "value": {"groups": 0, "listed": [], "truncated": False},
    }


@pytest.mark.scan_json_lot("4b")
def test_D13_an_effect_after_the_table_was_released_is_never_reconstructed(tmp_path):
    # 200 distinct values release the table; the only string trimming changes
    # comes last, when the earlier values are gone.
    result = run_scan(_csv(tmp_path, "v", [*_ids(200), '" v0001"']), limits=RELEASE)

    chain = stages(field(dataset(result, "rows"), "v"))

    raw = _bare(chain["raw"])
    assert chain["nfc"]["equals"] == "raw" and _bare(chain["nfc"]) == raw
    trim = chain["trim"]
    assert trim["changed"] == 1
    assert "equals" not in trim
    # The count after trimming cannot be rebuilt: limited, and no bound, since
    # the raw distinct values do not prove the trimmed ones.
    assert _bare(trim) == {"status": "limited", "reason": "distinct_limit", "limit": 50}
    # The stages after it changed nothing, so they have its count, not the raw one.
    for before, name in pairwise(CHAIN[2:]):
        assert chain[name]["equals"] == before
        assert _bare(chain[name]) == _bare(trim)
    groups = field(dataset(result, "rows"), "v")["normalization"]["variant_groups"]
    assert groups["status"] == "limited"


@pytest.mark.scan_json_lot("4b")
def test_D13_a_complete_table_counts_every_stage_exactly(tmp_path):
    result = run_scan(_csv(tmp_path, "v", ["a", '" a"', "b"]))

    chain = stages(field(dataset(result, "rows"), "v"))

    assert _bare(chain["raw"]) == {"status": "complete", "value": 3}
    assert chain["nfc"]["equals"] == "raw"
    assert _bare(chain["nfc"]) == {"status": "complete", "value": 3}
    # Trimming merged " a" into "a": exact because the table is complete.
    assert chain["trim"]["changed"] == 1
    assert "equals" not in chain["trim"]
    assert _bare(chain["trim"]) == {"status": "complete", "value": 2}
    assert chain["collapse_whitespace"]["equals"] == "trim"
    assert _bare(chain["strip_accents"]) == {"status": "complete", "value": 2}


@pytest.mark.scan_json_lot("4b")
def test_D13_a_disabled_stage_is_skipped_by_the_chain(tmp_path):
    result = run_scan(
        _csv(tmp_path, "v", _ids(200)),
        limits=RELEASE,
        normalization={"trim": False},
    )

    chain = stages(field(dataset(result, "rows"), "v"))

    assert chain["trim"] == {
        "stage": "trim",
        "enabled": False,
        "changed": None,
        "cardinality": None,
    }
    assert chain["collapse_whitespace"]["equals"] == "nfc"


@pytest.mark.scan_json_lot("4b")
def test_D13_a_field_without_text_stages_keeps_the_limit_of_its_values(tmp_path):
    result = run_scan(_csv(tmp_path, "n", [str(index) for index in range(200)]), limits=RELEASE)

    column = field(dataset(result, "rows"), "n")

    assert column["values"]["cardinality"]["status"] == "limited"
    assert all(stage.get("equals") for name, stage in stages(column).items() if name != "raw")


@pytest.mark.scan_json_lot("4b")
def test_QUAL01_the_three_flags_follow_their_collections(tmp_path):
    # Clean data cut by a limit: a limit, no observation, no issue.
    limited = run_scan(_csv(tmp_path, "v", _ids(200)), limits=RELEASE)["observations"]

    summary = limited["summary"]
    assert (summary["has_observations"], summary["has_quality_issues"]) == (False, False)
    assert summary["has_limits"] is True
    assert limited["items"] == []
    assert limited["datasets"][0]["dataset"] == "rows"
    assert limited["datasets"][0]["has_limits"] is True


@pytest.mark.scan_json_lot("4b")
def test_QUAL02_an_observation_names_its_rule_population_count_and_accuracy(tmp_path):
    rows = ["a,1", "b,1", "a,1", "c,"]
    result = run_scan(_csv(tmp_path, "x,y", rows))

    items = {
        (item["rule"], item.get("field")): item
        for item in result["observations"]["items"]
    }

    duplicate = items["duplicate_rows", None]
    assert duplicate == {
        "id": duplicate["id"],
        "rule": "duplicate_rows",
        "category": "records",
        "status": "candidate_anomaly",
        "dataset": "rows",
        "population": "records",
        "count": 1,
        "of": 4,
        "accuracy": "exact",
        "records": [3],
    }
    missing = next(item for key, item in items.items() if key[0] == "missing_values")
    assert (missing["status"], missing["population"]) == ("informational", "value_slots")
    assert (missing["count"], missing["of"], missing["accuracy"]) == (1, 4, "exact")


@pytest.mark.scan_json_lot("4b")
def test_QUAL03_a_mostly_empty_optional_column_is_a_remark_not_an_issue(tmp_path):
    # 190 of 200 empty cells in the second column: valid, optional, informational.
    rows = [f"{index}," if index % 20 else f"{index},x" for index in range(200)]
    result = run_scan(_csv(tmp_path, "id,note", rows))

    observations = result["observations"]
    missing = [item for item in observations["items"] if item["rule"] == "missing_values"]
    assert [item["count"] for item in missing] == [190]
    assert missing[0]["status"] == "informational"
    assert observations["summary"]["has_observations"] is True
    assert observations["summary"]["has_quality_issues"] is False


@pytest.mark.scan_json_lot("4b")
def test_QUAL04_a_limit_is_listed_apart_and_is_not_an_observation(tmp_path):
    result = run_scan(_csv(tmp_path, "v", _ids(200)), limits=RELEASE)

    observations = result["observations"]
    limit = next(
        item for item in observations["limits"] if item["measure"] == "values.cardinality"
    )
    assert (limit["dataset"], limit["reason"], limit["limit"]) == ("rows", "distinct_limit", 50)
    assert limit["lower_bound"] == 51
    # The stages that repeat the raw limit are not listed again.
    assert not any(
        item["measure"].startswith("normalization.stages")
        for item in observations["limits"]
    )
    assert all(item["rule"] != "limited_measures" for item in observations["items"])


@pytest.mark.scan_json_lot("4b")
def test_QUAL04_a_limit_that_blocks_a_count_is_named_by_the_observation(tmp_path):
    rows = [f"{index},{index}" for index in range(50)] + ["0,0"] * 5
    result = run_scan(
        _csv(tmp_path, "a,b", rows),
        limits={"max_tracked_records": 10},
    )

    observations = result["observations"]
    duplicate = next(item for item in observations["items"] if item["rule"] == "duplicate_rows")
    assert duplicate["accuracy"] == "lower_bound"
    blocking = {item["id"]: item for item in observations["limits"]}
    assert duplicate["limited_by"]
    assert all(
        blocking[identifier]["measure"] == "records.duplicates.count"
        for identifier in duplicate["limited_by"]
    )


@pytest.mark.scan_json_lot("4b")
def test_QUAL05_the_confirmed_issues_come_before_the_candidates_and_the_remarks(tmp_path):
    # A blank header and a repeated row: a confirmed issue, a candidate, a remark.
    rows = ["1,x,", "2,y,", "1,x,"]
    result = run_scan(_csv(tmp_path, ",b,c", rows))

    statuses = [item["status"] for item in result["observations"]["items"]]

    assert statuses == sorted(
        statuses, key=["confirmed_issue", "candidate_anomaly", "informational"].index
    )
    assert statuses[0] == "confirmed_issue"
    assert "informational" in statuses

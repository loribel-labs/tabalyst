# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Scan contract: record facts of each dataset (lot 5c, design 9.10).

Records with missing values, empty records, duplicate records under the
``limits.max_tracked_records`` budget, and the first records (the start of the
row sample, which replaced the preview at lot 5) through the exposure of their
fields.
"""

import json

import pytest
from scan_helpers import dataset, run_scan, write_text

from tabalyst.report_config import ReportConfig
from tabalyst.reporting import render_report
from tabalyst.service import analyze_csv

pytestmark = pytest.mark.lot("5c")


def _records(result: dict, dataset_id: str = "rows") -> dict:
    return dataset(result, dataset_id)["records"]


def _rows(result: dict, dataset_id: str = "rows") -> list[dict]:
    """The rows of the row sample, in source order for a small dataset."""
    return _records(result, dataset_id)["sample"]["rows"]


def test_csv_records_block(tmp_path):
    source = write_text(
        tmp_path, "rows.csv", "a,b\n1,x\n,\n1,x\n2,\n , \n1,x\n"
    )

    result = run_scan(source)
    records = _records(result)

    assert records["with_missing"] == {"count": 3, "records": [2, 4, 5]}
    assert records["empty"] == {"count": 2, "records": [2, 5]}
    assert records["duplicates"] == {
        "count": {"status": "complete", "value": 2},
        "records": [3, 6],
    }
    assert "preview" not in records
    assert _rows(result)[0] == {
        "record": 1,
        "origins": ["start", "end"],
        "values": {"column_1": ["1"], "column_2": ["x"]},
    }
    assert _rows(result)[4]["values"] == {"column_1": [" "], "column_2": [" "]}


def test_csv_duplicates_keep_cell_boundaries(tmp_path):
    """Table digests join the values: moving a boundary is another record."""
    source = write_text(
        tmp_path,
        "rows.csv",
        'a,b,c\nab,c,\na,bc,\n"a,b",c,\na,"b,c",\n,abc,\nabc,,\nab,c,\n',
    )

    duplicates = _records(run_scan(source))["duplicates"]

    assert duplicates == {"count": {"status": "complete", "value": 1}, "records": [7]}


def test_missing_follows_the_missing_definition(tmp_path):
    source = write_text(tmp_path, "rows.csv", "a,b\nNA,1\n,2\n")

    records = _records(
        run_scan(source, values={"null_markers": ["NA"], "missing": ["marker"]})
    )

    assert records["with_missing"] == {"count": 1, "records": [1]}
    assert records["empty"] == {"count": 0, "records": []}


def test_json_records_compare_every_observation(tmp_path):
    source = write_text(
        tmp_path,
        "items.json",
        json.dumps(
            [
                {"id": 1, "tags": ["a", "b"], "note": None},
                {"id": 1, "tags": ["a", "b"], "note": None},
                {"id": 1, "tags": ["b", "a"], "note": None},
                {"id": "1", "tags": ["a", "b"], "note": None},
                {"tags": []},
            ]
        ),
    )

    result = run_scan(source)

    records = _records(result, "$[]")
    assert records["duplicates"]["count"] == {"status": "complete", "value": 1}
    assert records["duplicates"]["records"] == [2]
    # Values are scalars: a null counts, an absent field does not.
    assert records["with_missing"]["count"] == 4
    assert records["empty"]["count"] == 0
    ids = {item["display"]: item["id"] for item in dataset(result, "$[]")["fields"]}
    assert _rows(result, "$[]")[0]["values"] == {
        ids["id"]: ["1"],
        ids["tags[]"]: ["a", "b"],
        ids["note"]: [None],
    }
    assert _rows(result, "$[]")[4]["values"] == {}


def test_duplicates_are_compared_within_a_dataset(tmp_path):
    source = write_text(
        tmp_path,
        "shop.json",
        json.dumps({"a": [{"x": 1}, {"x": 1}], "b": [{"x": 1}]}),
    )

    result = run_scan(source)

    assert _records(result, "$.a[]")["duplicates"]["count"]["value"] == 1
    assert _records(result, "$.b[]")["duplicates"]["count"]["value"] == 0


def test_duplicate_budget_gives_a_proven_lower_bound(tmp_path):
    source = write_text(tmp_path, "rows.csv", "a\n1\n2\n3\n1\n3\n3\n")

    result = run_scan(source, limits={"max_tracked_records": 2})

    duplicates = _records(result)["duplicates"]
    # 3 is never stored: only the repeats of 1 are proven.
    assert duplicates == {
        "count": {
            "status": "limited",
            "reason": "record_budget",
            "limit": 2,
            "lower_bound": 1,
        },
        "records": [4],
    }
    (diagnostic,) = [
        item for item in result["diagnostics"] if item["code"] == "record_budget"
    ]
    assert (diagnostic["level"], diagnostic["count"]) == ("warning", 3)


def test_duplicate_budget_is_shared_by_the_datasets(tmp_path):
    source = write_text(
        tmp_path,
        "shop.json",
        json.dumps({"a": [{"x": 1}, {"x": 1}], "b": [{"x": 2}, {"x": 3}]}),
    )

    result = run_scan(source, limits={"max_tracked_records": 2})

    assert _records(result, "$.a[]")["duplicates"]["count"] == {
        "status": "complete",
        "value": 1,
    }
    assert _records(result, "$.b[]")["duplicates"]["count"]["status"] == "limited"


def test_duplicates_can_be_disabled(tmp_path):
    source = write_text(tmp_path, "rows.csv", "a\n1\n1\n")

    records = _records(run_scan(source, records={"duplicates": False}))

    assert records["duplicates"] == {"count": {"status": "disabled"}, "records": []}


def test_listings_and_the_start_of_the_sample_are_bounded(tmp_path):
    source = write_text(tmp_path, "rows.csv", "a,b\n" + ",\n" * 5 + "1,1\n" * 5)
    sample = {"rows": 4, "edge": 2}

    result = run_scan(
        source, records={"sample": sample}, limits={"max_listed_records": 3}
    )

    records = _records(result)
    assert records["with_missing"] == {"count": 5, "records": [1, 2, 3]}
    assert records["duplicates"]["records"] == [2, 3, 4]
    starts = [item["record"] for item in _rows(result) if "start" in item["origins"]]
    assert starts == [1, 2]
    assert "sample" not in _records(run_scan(source, records={"sample": {"rows": 0}}))


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("mask", ["aaa9@aaaaaaa.aaa"]),
        ("hide", None),
        ("show", ["ann1@example.com"]),
    ],
)
def test_the_sample_goes_through_the_exposure(tmp_path, mode, expected):
    rows = "".join(f"ann{index}@example.com,{index}\n" for index in range(1, 4))
    source = write_text(tmp_path, "mails.csv", "email,n\n" + rows + ",4\nN/A,5\n")

    rows = _rows(
        run_scan(
            source,
            exposure={"sensitive_values": mode},
            values={"null_markers": ["N/A"]},
        )
    )

    assert rows[0]["values"]["column_1"] == expected
    # Values that are not content stay as read.
    assert rows[3]["values"]["column_1"] == [""]
    assert rows[4]["values"]["column_1"] == ["N/A"]


def test_hidden_value_hides_its_whole_cell(tmp_path):
    source = write_text(
        tmp_path,
        "mails.json",
        json.dumps([{"mails": [None, "ann@example.com"]}]),
    )

    result = run_scan(source, exposure={"sensitive_values": "hide"})

    (values,) = [item["values"] for item in _rows(result, "$[]")]
    assert list(values.values()) == [None]


def test_untracked_fields_are_not_in_the_sample(tmp_path):
    source = write_text(tmp_path, "items.json", json.dumps([{"a": 1, "b": 2}]))

    result = run_scan(source, limits={"max_fields": 1})

    ids = [item["id"] for item in dataset(result, "$[]")["fields"]]
    assert list(_rows(result, "$[]")[0]["values"]) == ids


# The report -------------------------------------------------------------------


def _report(source, **scan):
    profile = analyze_csv(source, ReportConfig.model_validate({"scan": scan}))
    return profile, profile.report.datasets[0]


def test_report_shows_a_limited_duplicate_count_as_a_lower_bound(tmp_path):
    source = write_text(tmp_path, "rows.csv", "a\n1\n2\n3\n1\n3\n")

    profile, current = _report(source, limits={"max_tracked_records": 2})

    assert (current.summary.duplicate_row_count, current.summary.duplicate_row_status) == (
        1,
        "limited",
    )
    (finding,) = [
        item for item in profile.observations.items if item.rule == "duplicate_rows"
    ]
    assert finding.accuracy == "lower_bound"
    assert "At least, beyond the first occurrence" in render_report(profile)


def test_report_without_duplicate_comparison(tmp_path):
    source = write_text(tmp_path, "rows.csv", "a\n1\n1\n")

    profile, current = _report(source, records={"duplicates": False})

    assert current.summary.duplicate_row_count is None
    assert current.summary.duplicate_row_status == "disabled"
    assert "duplicate_rows" not in {item.rule for item in profile.observations.items}
    assert "Not checked" in render_report(profile)


def test_report_row_sample_size_is_a_report_setting(tmp_path):
    source = write_text(tmp_path, "rows.csv", "a\n1\n2\n3\n4\n5\n")
    config = ReportConfig.model_validate(
        {"row_sample": {"start": 2, "middle": 0, "end": 0}}
    )

    profile = analyze_csv(source, config)

    rows = profile.datasets[0].records.sample.rows
    assert [row.record for row in rows] == [1, 2]

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Scan contract: JSON sources and the detectors section of the report (lot 5b).

Profile revision 4 lists one dataset per scan dataset holding columns; JSON
fields with scalar values are columns named by their display path, containers
are not (design 16.4 and 16.5).
"""

import json

import pytest
from scan_helpers import write_text
from typer.testing import CliRunner

from tabalyst.cli import app
from tabalyst.report_config import ReportConfig
from tabalyst.reporting import render_report
from tabalyst.service import analyze_csv

pytestmark = pytest.mark.lot("5b")

ORDERS = {
    "customers": [
        {
            "id": 1,
            "email": "ann@example.com",
            "tags": ["a", "b"],
            "address": {"city": "Paris"},
            "orders": [{"amount": 3}, {"amount": None}],
        },
        {"id": 2, "email": "bob@example.com", "address": {}, "orders": []},
        {"id": 2, "email": "bob@example.com", "address": {}, "orders": []},
    ],
    "meta": {"version": 1},
}


def _orders(tmp_path, document=ORDERS):
    return write_text(tmp_path, "orders.json", json.dumps(document))


def _config(**scan) -> ReportConfig:
    return ReportConfig.model_validate({"scan": scan})


def _datasets(profile) -> dict:
    return {dataset.id: dataset for dataset in profile.datasets}


def test_json_profile_lists_one_dataset_per_scan_dataset(tmp_path):
    profile = analyze_csv(_orders(tmp_path))

    assert profile.format_revision == 11
    assert profile.source.format == "json"
    assert profile.source.delimiter is None
    datasets = _datasets(profile)
    assert list(datasets) == ["$", "$.customers[]"]
    assert datasets["$"].kind == "document"
    assert [column.name for column in datasets["$"].columns] == ["meta.version"]
    customers = datasets["$.customers[]"]
    assert customers.kind == "collection"
    assert customers.summary.row_count == 3


def test_json_columns_are_scalar_fields_named_by_path(tmp_path):
    customers = _datasets(analyze_csv(_orders(tmp_path)))["$.customers[]"]

    columns = {column.name: column for column in customers.columns}
    # Objects and arrays are structure, not columns.
    assert list(columns) == [
        "id",
        "email",
        "tags[]",
        "address.city",
        "orders[].amount",
    ]
    assert [column.position for column in customers.columns] == [1, 2, 3, 4, 5]
    assert all(column.path == column.name for column in customers.columns)
    # Absent members are missing, over the places the field could appear.
    city = columns["address.city"]
    assert (city.missing_count, city.missing_percent) == (2, 66.67)
    amount = columns["orders[].amount"]
    assert (amount.missing_count, amount.inferred_type) == (1, "integer")
    assert customers.summary.cell_count == 3 + 3 + 2 + 3 + 2
    assert customers.summary.duplicate_row_count == 1


def test_json_preview_shows_absent_joined_and_masked_values(tmp_path):
    customers = _datasets(analyze_csv(_orders(tmp_path)))["$.customers[]"]

    first, second, _ = customers.preview
    assert first.values == ["1", "aaa@aaaaaaa.aaa", "a, b", "Paris", "3, null"]
    assert first.absent == []
    assert second.values == ["2", "aaa@aaaaaaa.aaa", None, None, None]
    assert second.absent == [2, 3, 4]


def test_json_records_excluded_by_the_tolerant_policy_are_an_issue(tmp_path):
    source = write_text(tmp_path, "rows.json", '[{"a": 1}, {"a": 2, "a": 3}, {"a": 4}]')

    profile = analyze_csv(source, _config(errors={"policy": "tolerant"}))

    (dataset,) = profile.datasets
    assert dataset.summary.row_count == 2
    issue = {issue.code: issue for issue in dataset.issues}["excluded_records"]
    assert (issue.count, issue.row_numbers) == (1, [2])


def test_detectors_are_listed_per_column(tmp_path):
    rows = "".join(f"user{index}@example.com,2026-01-0{index + 1}\n" for index in range(3))
    source = write_text(tmp_path, "contacts.csv", "email,day\n" + rows)

    profile = analyze_csv(source)

    email, day = profile.datasets[0].columns
    (detector,) = email.detectors
    assert (detector.id, detector.status, detector.primary) == ("email", "complete", True)
    assert (detector.eligible_count, detector.matched_count) == (3, 3)
    assert detector.matched_percent == 100.0
    date = next(item for item in day.detectors if item.id == "date")
    assert [item.format for item in date.formats] == ["YYYY-MM-DD"]
    assert date.formats[0].percent == 100.0
    html = render_report(profile)
    assert '<section class="panel" id="detectors"' in html
    assert "YYYY-MM-DD" in html


def test_detectors_without_matches_are_not_listed(tmp_path):
    source = write_text(tmp_path, "names.csv", "name\nAnn\nBob\n")

    column = analyze_csv(source).datasets[0].columns[0]

    assert column.detectors == []
    assert 'id="detectors"' not in render_report(analyze_csv(source))


def test_several_datasets_get_a_selector_and_prefixed_ids(tmp_path):
    html = render_report(analyze_csv(_orders(tmp_path)))

    assert 'id="ds-select"' in html
    assert html.count("<option ") == 2
    assert 'id="d1-overview"' in html and 'id="d2-overview"' in html
    assert 'href="#d2-columns"' in html
    assert 'id="overview"' not in html
    assert ">absent<" in html


def test_a_single_dataset_keeps_plain_ids(tmp_path):
    source = write_text(tmp_path, "rows.json", '[{"a": 1}, {"a": 2}]')

    html = render_report(analyze_csv(source))

    assert 'id="ds-select"' not in html
    assert 'id="overview"' in html
    assert ">JSON<" in html


def test_report_command_names_json_outputs_apart_from_the_source(tmp_path):
    source = _orders(tmp_path)

    result = CliRunner().invoke(app, ["report", str(source)])

    assert result.exit_code == 0, result.output
    # The command reads the one collection Inspect selects, not the document.
    assert "3 records and 5 fields in 1 dataset" in result.stderr
    assert json.loads(source.read_text(encoding="utf-8")) == ORDERS
    profile = json.loads((tmp_path / "orders.report.json").read_text(encoding="utf-8"))
    assert profile["source"]["format"] == "json"
    assert [item["id"] for item in profile["datasets"]] == ["$.customers[]"]
    assert (tmp_path / "orders.report.html").exists()


@pytest.mark.parametrize("text", ["[{}, {}]", "[]", '{"a": {}}'])
def test_json_without_scalar_values_is_reportable(tmp_path, text):
    source = write_text(tmp_path, "empty.json", text)

    profile = analyze_csv(source)

    (dataset,) = profile.datasets
    assert dataset.columns == []
    assert "<html" in render_report(profile)

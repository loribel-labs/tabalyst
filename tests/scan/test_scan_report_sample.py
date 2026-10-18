# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Scan contract: the Report works on a bounded sample of the Scan's values,
so the size K of the Scan sample does not change its examples (design 19.4,
lot 1a)."""

from pathlib import Path

import pytest

from tabalyst import ReportConfig, analyze_csv

pytestmark = pytest.mark.scan_json_lot("1a")

INPUT = Path(__file__).resolve().parents[2] / "examples" / "datasets"


def _datasets(name: str, **limits) -> list[dict]:
    # Masked values of a released table merge after the sample is drawn, so the
    # parity is that of unmasked values.
    scan = {"limits": limits, "exposure": {"sensitive_values": "show"}}
    config = ReportConfig.model_validate({"scan": scan})
    profile = analyze_csv(INPUT / name, config=config, workers=1)
    datasets = profile.model_dump(mode="json")["report"]["datasets"]
    # The findings and the quality counts read the observations of the Scan, which
    # discovers the minority patterns on its sample: they depend on the sample size.
    # So do the formats of the Overview (patterns on a sample) and the detail of the
    # minority patterns, which names them. The examples and the Details do not.
    for dataset in datasets:
        dataset["table"] = None
        for column in dataset["columns"]:
            column["summary"]["findings"] = None
            column["summary"]["overview"] = None
            column["summary"]["finding_details"]["patterns"] = None
    return datasets


def test_the_report_keeps_one_hundred_sample_values_per_column_by_default():
    assert ReportConfig().value_examples.kept_per_column == 100


@pytest.mark.parametrize("name", ["insurance-customers.csv", "orders.json"])
def test_a_larger_scan_sample_does_not_change_the_examples_of_the_report(name):
    # Some columns have more than 100 and fewer than 500 distinct values.
    reference = _datasets(name, max_distinct_per_field=500, max_samples=100)

    larger = _datasets(name, max_distinct_per_field=500, max_samples=500)

    assert larger == reference


def test_the_report_draws_its_examples_from_a_released_table_the_same_way():
    # 3,000 records released after 150 distinct values: a first_seen sample.
    reference = _datasets(
        "insurance-customers.csv", max_distinct_per_field=150, max_samples=100
    )

    larger = _datasets("insurance-customers.csv", max_distinct_per_field=150)

    assert larger == reference

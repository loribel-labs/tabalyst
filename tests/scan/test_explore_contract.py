# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""What Explore consumes of a Scan or a Report (specification 19.3, EXPLORE-01 to
EXPLORE-05, design 20.17). Explore itself is outside this work: these tests fix what
the profile gives it to prepare facets, so that a change of the documents cannot
silently take one away."""

import json

import pytest
from planner_helpers import scan_csv
from scan_helpers import write_text

from tabalyst import generate_reports
from tabalyst.reporting import load_profile
from tabalyst.scanner.planner import default_registry, plan_analyses

ROWS = [
    f"r{n % 4},{n * 1.5:.2f},2024-0{1 + n % 9}-1{n % 9},AB-{n % 50:03d}" for n in range(400)
]
HEADER = "region,amount,when,code"


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path.parent / f"{tmp_path.name}-home"))


def _fields(result):
    document = result.model_dump(mode="json", by_alias=True)
    return {field["display"]: field for field in document["datasets"][0]["fields"]}


def _report(tmp_path):
    source = write_text(tmp_path, "data.csv", HEADER + "\n" + "\n".join(ROWS) + "\n")
    batch = generate_reports([source], output_dir=tmp_path / "out", force=True)
    assert not batch.failures
    return source, tmp_path / "out" / "data.json"


def test_explore_01_the_scan_gives_the_inputs_of_a_facet_for_every_column(tmp_path):
    fields = _fields(scan_csv(tmp_path, HEADER, ROWS))

    region = fields["region"]
    # A facet of few values: its distinct count, its exact frequencies, its type.
    assert region["values"]["cardinality"]["value"] == 4
    assert region["values"]["cardinality"]["accuracy"] == "exact"
    assert [item["count"] for item in region["values"]["frequencies"]["value"]["listed"]] == [100] * 4
    assert region["technical_type"]["type"] == "text"
    # A range facet: numbers have their extremes, dates their bounds and formats.
    assert fields["amount"]["numeric"] is not None
    assert fields["when"]["temporal"] is not None
    # A text facet: lengths with their exact histogram.
    assert fields["code"]["string_lengths"] is not None


def test_explore_01_a_pattern_facet_comes_from_the_patterns_of_the_scan(tmp_path):
    result = scan_csv(tmp_path, HEADER, ROWS)

    code = next(item.id for item in result.datasets[0].fields if item.display == "code")
    entry = next(item for item in result.derived.patterns.fields if item.field == code)

    assert entry.status == "complete" and entry.candidates


def test_explore_01_the_planner_prices_what_explore_could_ask_for(tmp_path):
    result = scan_csv(tmp_path, HEADER, ROWS)

    plan = plan_analyses(result, registry=default_registry().runnable(), forced=True)

    # A plan says what a second reading would cost before anything runs, so a facet
    # that needs an exact figure can be offered with its price.
    assert plan.summary.second_pass_required and plan.summary.memory is not None
    assert plan.common.cells > 0 and plan.common.cpu


def test_explore_02_the_profile_does_not_pretend_to_hold_every_row(tmp_path):
    result = scan_csv(tmp_path, HEADER, ROWS[:50] * 40)

    dataset = result.datasets[0]

    # The row sample is a bounded sample, not the file: reading the rows needs the
    # source or a cache built when Explore opens (EXPLORE-02).
    assert dataset.record_count == 2_000
    assert dataset.records.sample is not None
    assert dataset.records.sample.kept < dataset.record_count


def test_explore_03_a_count_of_the_profile_names_its_population(tmp_path):
    result = scan_csv(tmp_path, HEADER, ROWS)

    fields = _fields(result)
    document = json.dumps(fields["region"])

    # Counts say what they count: the whole field, in a named domain. Nothing in
    # the profile is the count of a selection, so a filtered count must come from
    # a query or an analysis of its own scope (EXPLORE-03).
    assert fields["region"]["values"]["cardinality"]["domain"] == "original"
    assert fields["region"]["values"]["frequencies"]["value"]["listed"][0]["count"] == 100
    assert "filter" not in document and "selection_scope" not in document


def test_explore_04_a_second_pass_is_reused_when_source_and_settings_are_the_same(tmp_path):
    source, report = _report(tmp_path)
    first = json.loads(report.read_text(encoding="utf-8"))["analyses"]["deep"]["run"]

    generate_reports([source], output_dir=tmp_path / "again", force=True)

    again = json.loads((tmp_path / "again" / "data.json").read_text(encoding="utf-8"))
    second = again["analyses"]["deep"]["run"]
    assert first["executed"] > 0
    assert second["reused"] == first["executed"] and second["executed"] == 0


def test_explore_05_a_report_gives_the_initial_profile_without_the_source(tmp_path):
    source, report = _report(tmp_path)
    source.unlink()

    profile = load_profile(report)

    names = {field.name for dataset in profile.datasets for field in dataset.fields}
    assert {"region", "amount", "when", "code"} <= names
    # The profile still carries the identity of the source it describes, which is
    # what Explore checks before it trusts a cache of the rows.
    assert profile.source.sha256 and profile.source.size_bytes


def test_explore_06_the_later_analyses_are_readable_with_their_accuracy_from_the_json(tmp_path):
    source = write_text(tmp_path, "data.csv", HEADER + "\n" + "\n".join(ROWS) + "\n")
    batch = generate_reports(
        [source], output_dir=tmp_path / "forced", force=True, deep=True, confirmed=True
    )
    assert not batch.failures
    document = json.loads((tmp_path / "forced" / "data.json").read_text(encoding="utf-8"))

    results = [
        item["result"]
        for item in document["analyses"]["deep"]["analyses"]
        if item["status"] in ("complete", "limited") and "result" in item
    ]

    kinds = {result["kind"] for result in results}
    # A facet of Explore can read each of them without the source: a kind to
    # dispatch on, and the accuracy of its counts (or of its quantiles).
    assert {"numeric_shape", "datetime_parts"} <= kinds
    for result in results:
        if result["kind"] in ("numeric_shape", "datetime_parts", "residual_values", "measures"):
            assert result["accuracy"] in ("exact", "exact_counts")

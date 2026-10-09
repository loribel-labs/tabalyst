# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The ``report`` object of the configuration and the views of a report (lot 1c;
design 19.3, 19.4b)."""

import json

import pytest
from scan_helpers import write_json, write_text

from tabalyst import ReportConfig, analyze_csv, generate_reports, generate_scans
from tabalyst.config import KEPT_PER_COLUMN_MAX, load_config, resolve_config
from tabalyst.errors import ConfigurationError
from tabalyst.report_config import resolve_report_config
from tabalyst.reporting import dataset_views, render_column_report, render_report
from tabalyst.scan_document import load_base

pytestmark = pytest.mark.scan_json_lot("1c")


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "TABALYST_HOME", str(tmp_path.parent / f"{tmp_path.name}-storage")
    )


def _ids(tmp_path, count: int = 200):
    rows = "\n".join(f"id{number:04d}" for number in range(count))
    return write_text(tmp_path, "ids.csv", f"id\n{rows}\n")


def test_the_report_object_holds_the_presentation_settings(tmp_path):
    config = write_json(
        tmp_path,
        "config.json",
        {
            "report": {
                "string_analysis": {"examples_per_length": 3},
                "value_examples": {"kept_per_column": 7, "inline_display_size": 2},
            }
        },
    )

    settings = load_config([config]).report
    effective = resolve_report_config([config])

    assert settings.value_examples.kept_per_column == 7
    assert effective.value_examples.kept_per_column == 7
    assert effective.value_examples.inline_display_size == 2
    assert effective.string_analysis.examples_per_length == 3


def test_a_report_keeps_one_hundred_values_per_column_unless_told_otherwise():
    assert ReportConfig().value_examples.kept_per_column == 100


@pytest.mark.parametrize(
    ("document", "target"),
    [
        ({"string_analysis": {"examples_per_length": 3}}, "report.string_analysis"),
        ({"value_examples": {"inline_display_size": 2}}, "report.value_examples"),
        (
            {"value_examples": {"candidate_sample_size": 50}},
            "scan.limits.max_samples",
        ),
        ({"value_examples": {"random_seed": 1}}, "scan.random_seed"),
    ],
)
def test_presentation_settings_at_the_top_level_are_refused_with_their_new_place(
    tmp_path, document, target
):
    config = write_json(tmp_path, "old.json", document)

    with pytest.raises(ConfigurationError, match=target.replace(".", r"\.")):
        resolve_report_config([config])


@pytest.mark.parametrize("size", [0, KEPT_PER_COLUMN_MAX + 1])
def test_kept_per_column_stays_between_one_and_its_maximum(tmp_path, size):
    config = write_json(
        tmp_path, "config.json", {"report": {"value_examples": {"kept_per_column": size}}}
    )

    with pytest.raises(ConfigurationError, match="kept_per_column"):
        resolve_report_config([config])


def test_the_report_object_does_not_hold_analysis_settings(tmp_path):
    config = write_json(
        tmp_path, "config.json", {"report": {"scan": {"random_seed": 1}}}
    )

    with pytest.raises(ConfigurationError, match="report"):
        resolve_report_config([config])


def test_sample_reads_a_file_that_has_a_report_object(tmp_path):
    config = write_json(
        tmp_path,
        "config.json",
        {"csv": {"delimiter": ";"}, "report": {"value_examples": {"kept_per_column": 9}}},
    )

    assert resolve_config([config]).csv.delimiter == ";"


def test_kept_per_column_sets_the_samples_the_report_keeps_and_says_so(tmp_path):
    config = ReportConfig.model_validate(
        {"value_examples": {"kept_per_column": 5}, "scan": {"limits": {"max_samples": 50}}}
    )

    profile = analyze_csv(_ids(tmp_path), config=config, workers=1)

    samples = profile.datasets[0].fields[0].values.samples
    assert (samples.kept, samples.of) == (5, 50)
    assert len(samples.listed) == 5
    assert "reproducible sample of up to 5 distinct values" in render_report(profile)


def test_a_larger_kept_per_column_does_not_start_a_scan_again(tmp_path):
    source = _ids(tmp_path)
    generate_scans([source], output_dir=tmp_path / "scans", force=True)
    scan_file = tmp_path / "scans" / "ids.scan.json"
    before = scan_file.read_bytes()
    reports = {}
    for size in (5, 40):
        config = write_json(
            tmp_path,
            f"kept-{size}.json",
            {"report": {"value_examples": {"kept_per_column": size}}},
        )
        batch = generate_reports(
            [scan_file],
            output_dir=tmp_path / f"reports-{size}",
            config_path=config,
            from_scan=True,
            force=True,
        )
        assert batch.succeeded
        reports[size] = tmp_path / f"reports-{size}" / "ids.json"

    small = json.loads(reports[5].read_text(encoding="utf-8"))
    large = json.loads(reports[40].read_text(encoding="utf-8"))
    assert scan_file.read_bytes() == before
    assert small["report"]["base_scan"] == large["report"]["base_scan"]
    assert load_base(reports[5]).datasets[0].fields[0].values.samples.kept == 5
    assert load_base(reports[40]).datasets[0].fields[0].values.samples.kept == 40


def test_a_column_view_carries_the_canonical_field_of_its_projection(tmp_path):
    profile = analyze_csv(_ids(tmp_path, count=10), workers=1)

    (dataset_view,) = dataset_views(profile)

    (column,) = dataset_view.columns
    assert column.field is profile.datasets[0].fields[0]
    assert column.id == column.field.id
    assert column.string_profile is not None


def test_pages_render_when_the_scan_could_not_complete_the_numeric_measures(tmp_path):
    rows = "\n".join(f"{number},{number * 1.5},word{number}" for number in range(300))
    source = write_text(tmp_path, "limited.csv", f"id,amount,label\n{rows}\n")
    config = ReportConfig.model_validate(
        {"scan": {"limits": {"max_distinct_per_field": 20, "max_samples": 20}}}
    )

    profile = analyze_csv(source, config=config, workers=1)

    (dataset_view,) = dataset_views(profile)
    assert any(
        column.field.numeric.status != "complete" or column.numeric is None
        or column.numeric.median is None
        for column in dataset_view.columns
    )
    render_report(profile)
    for column in dataset_view.columns:
        render_column_report(profile, dataset_view, column, "../report.html")

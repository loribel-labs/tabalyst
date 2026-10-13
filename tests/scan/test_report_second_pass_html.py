# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""What the second pass adds to the pages of the report (design 20, 18.14): the
panel that says what was added or left out, and the figures the analyses
complete. The renderer reads the document alone (HTML-01)."""

import json

import pytest
from scan_helpers import write_json, write_text
from typer.testing import CliRunner

from tabalyst.cli import app
from tabalyst.report_deep import column_analyses, result_summary, second_pass_view
from tabalyst.reporting import dataset_views, load_profile, render_report

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path.parent / f"{tmp_path.name}-home"))


def _source(tmp_path, rows=900):
    lines = ["customer_id,code,price,signed"]
    for n in range(rows):
        lines.append(
            f"C{n:06d},AB{n % 700 + 100},{100 + (n * 37) % 900}.{n % 100:02d},"
            f"2024-{n % 12 + 1:02d}-{n % 28 + 1:02d}"
        )
    return write_text(tmp_path, "customers.csv", "\n".join(lines) + "\n")


def _report(tmp_path, *options):
    source = _source(tmp_path)
    result = runner.invoke(app, ["report", str(source), *options])
    assert result.exit_code == 0, result.output
    path = tmp_path / "customers.json"
    return path, load_profile(path)


def test_the_second_pass_panel_lists_what_was_computed_and_what_was_left_out(tmp_path):
    _, profile = _report(tmp_path)

    view = second_pass_view(profile.analyses, profile.datasets[0].id)
    html = render_report(profile)

    assert view.available and view.mode == "auto" and view.outcome == "ran"
    assert view.metrics is not None and view.metrics.computed == len(view.rows) > 0
    assert view.source_read and view.source_verified
    assert 'id="second-pass"' in html and "Second pass" in html
    assert "Pattern validation" in html and "Distribution over time" in html
    # What the planner left out is named with its reason, in words.
    assert view.left_out or view.metrics.already_answered
    assert "Not selected" in html


def test_a_report_of_an_earlier_build_without_analyses_has_no_panel(tmp_path):
    path, _ = _report(tmp_path)
    document = json.loads(path.read_text(encoding="utf-8"))
    del document["analyses"]
    older = write_json(tmp_path, "older.json", document)

    html = render_report(load_profile(older))

    assert 'id="second-pass"' not in html
    assert "Second pass" not in html.split("Analysis settings")[0].split("Explore the report")[-1]


def test_a_disabled_second_pass_says_so_in_the_panel(tmp_path):
    off = write_json(tmp_path, "off.json", {"deep": {"mode": "off"}})
    _, profile = _report(tmp_path, "-c", str(off))

    html = render_report(profile)
    view = second_pass_view(profile.analyses, profile.datasets[0].id)

    assert view.available and view.rows == [] and view.outcome == "disabled"
    assert "turned off" in html


def test_an_exact_distinct_count_replaces_the_one_a_scan_limit_stopped(tmp_path):
    config = write_json(tmp_path, "limit.json", {"scan": {"limits": {"max_distinct_per_field": 50}}})
    _, profile = _report(tmp_path, "-c", str(config))

    views = dataset_views(profile)
    identifiers = next(c for c in views[0].columns if c.name == "customer_id")

    assert identifiers.distinct.kind == "exact" and identifiers.distinct.source == "second_pass"
    assert identifiers.distinct.value == 900
    assert "2nd pass" in render_report(profile)


def test_a_median_the_scan_could_not_give_comes_from_the_histogram(tmp_path):
    config = write_json(tmp_path, "limit.json", {"scan": {"limits": {"max_distinct_per_field": 50}}})
    _, profile = _report(tmp_path, "-c", str(config))

    views = dataset_views(profile)
    price = next(c for c in views[0].columns if c.name == "price")

    assert price.numeric.median is None
    assert price.deep.histogram is not None and price.deep.histogram.median.accuracy == "estimated"
    html = render_report(profile)
    assert "est.</small>" in html


def test_the_validated_pattern_counts_and_the_periods_reach_their_sections(tmp_path):
    _, profile = _report(tmp_path)

    views = dataset_views(profile)
    code = next(c for c in views[0].columns if c.name == "code")
    signed = next(c for c in views[0].columns if c.name == "signed")
    html = render_report(profile)

    assert code.deep.patterns is not None and code.deep.patterns.values == 900
    assert signed.deep.periods is not None and signed.deep.periods.count == 900
    assert "Validated on every value" in html
    assert 'class="periods"' in html and "dates by day" in html


def test_every_result_has_a_sentence_and_an_accuracy(tmp_path):
    _, profile = _report(tmp_path)

    results = column_analyses(profile.analyses)
    sentences = [
        result_summary(result)
        for column in results.values()
        for result in (
            column.distinct,
            column.patterns,
            column.periods,
            column.histogram,
            column.lengths,
            column.frequencies,
        )
        if result is not None
    ]

    assert sentences and all(text and kind in ("exact", "at_least") for text, kind in sentences)


def test_a_report_of_a_scan_document_says_the_source_was_not_read(tmp_path):
    source = _source(tmp_path)
    target = tmp_path / "customers.scan.json"
    assert runner.invoke(app, ["scan", str(source), "-o", str(target)]).exit_code == 0
    assert runner.invoke(app, ["report", "--scan", str(target)]).exit_code == 0

    profile = load_profile(tmp_path / "customers.json")
    html = render_report(profile)

    assert "was not read for this report" in html
    assert "built from a scan document" in html


def test_the_validated_counts_join_the_nodes_by_id(tmp_path):
    _, profile = _report(tmp_path)

    view = next(
        c for c in dataset_views(profile)[0].columns if c.name == "code"
    ).patterns

    assert view.has_validation
    assert all(
        pattern.validated is not None for family in view.families for pattern in family.patterns
    )

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Detail of the minority lengths in the Findings table (lot R12, tranche 3).

The contract is ``docs/dev/report/summary-table.md`` 22: the dominant length and every other
length of the exact histogram, with examples of the analytical text (the one the lengths are
counted on) read from the cases the Scan keeps (scan design 18.15), through the exposure of
the column.
"""

import json

import pytest
from scan_helpers import write_text

from tabalyst import analyze_csv
from tabalyst.json_text import dump_json
from tabalyst.report_config import ReportConfig
from tabalyst.report_finding_details import EXAMPLES_PER_ITEM, LENGTHS_SHOWN
from tabalyst.report_profile import build_profile
from tabalyst.report_summary import attach_summaries
from tabalyst.reporting import load_profile, render_report
from tabalyst.scanner import ScanConfig, scan


def _csv(minority: list[str], count: int = 200) -> str:
    rows = ["key,row"] + [f"KEY{n:04d},{n}" for n in range(count)]
    rows += [f"{value},{1000 + n}" for n, value in enumerate(minority)]
    return "\n".join(rows) + "\n"


MINORITY = ["KEY12", "KEY13", "KEY 12  3"]


def _built(tmp_path, content):
    """The Scan and the Report built from it, as ``tabalyst report`` does."""
    source = write_text(tmp_path, "data.csv", content)
    result = scan(source, config=ScanConfig.model_validate({}))
    return result, build_profile(result, ReportConfig(scan=result.config))


def _detail(profile):
    column = profile.report.datasets[0].columns[0]
    assert column.summary is not None
    return column.summary.finding_details.lengths


def test_the_detail_names_the_dominant_length_and_every_other_one(tmp_path):
    _, profile = _built(tmp_path, _csv(MINORITY))

    detail = _detail(profile)

    assert detail is not None
    assert (detail.dominant.length, detail.dominant.count) == (7, 200)
    # The most frequent first: two of five characters, one of eight (analytical text).
    assert [(item.length, item.count) for item in detail.lengths] == [(5, 2), (8, 1)]
    assert detail.total == 203 and detail.more_lengths == 0
    assert detail.state == "shown"


def test_the_examples_are_analytical_texts_of_their_length(tmp_path):
    _, profile = _built(tmp_path, _csv(MINORITY))

    detail = _detail(profile)

    assert detail is not None
    examples = {item.length: [e.value for e in item.examples] for item in detail.lengths}
    assert sorted(examples[5]) == ["KEY12", "KEY13"]
    # The original has two spaces (nine characters); the histogram counts the collapsed text.
    assert examples[8] == ["KEY 12 3"]
    assert detail.examples_from == "cases"
    assert all(len(values) <= EXAMPLES_PER_ITEM for values in examples.values())


def test_lengths_beyond_the_bound_are_counted_not_listed(tmp_path):
    minority = ["K", "KE", "KEY", "KEY1", "KEY12", "KEY123", "KEY12345"]
    _, profile = _built(tmp_path, _csv(minority))

    detail = _detail(profile)

    assert detail is not None
    assert len(detail.lengths) == LENGTHS_SHOWN
    assert detail.more_lengths == len(minority) - LENGTHS_SHOWN


def test_a_column_without_minority_length_has_no_detail(tmp_path):
    _, profile = _built(tmp_path, _csv([]))

    assert _detail(profile) is None


@pytest.mark.parametrize("mode", ["mask", "hide"])
def test_the_exposure_keeps_the_lengths_and_gates_the_examples(tmp_path, mode):
    result, profile = _built(tmp_path, _csv(MINORITY))
    shown = _detail(profile)
    for column in profile.report.datasets[0].columns:
        column.exposure = mode

    attach_summaries(profile, result)

    detail = _detail(profile)
    assert shown is not None and detail is not None
    assert detail.state == ("masked" if mode == "mask" else "hidden")
    # Lengths and counts are numbers, not values: they stay.
    assert [(i.length, i.count) for i in detail.lengths] == [
        (i.length, i.count) for i in shown.lengths
    ]
    text = detail.model_dump_json()
    assert all(value not in text for value in ("KEY12", "KEY13", "KEY 12 3"))
    if mode == "hide":
        assert detail.examples_from == "none"
        assert not any(item.examples for item in detail.lengths)


def test_a_document_attached_at_the_render_keeps_the_counts(tmp_path):
    source = write_text(tmp_path, "data.csv", _csv(MINORITY))
    profile = analyze_csv(source, ReportConfig(scan=ScanConfig.model_validate({})))
    whole = _detail(profile)
    document = profile.model_dump(mode="json")
    for dataset in document["report"]["datasets"]:
        dataset["table"] = None
        for column in dataset["columns"]:
            column["summary"] = None
    older = load_profile(write_text(tmp_path, "older.json", dump_json(document)))

    render_report(older)

    detail = _detail(older)
    assert whole is not None and detail is not None
    assert [(i.length, i.count) for i in detail.lengths] == [
        (i.length, i.count) for i in whole.lengths
    ]
    assert detail.dominant == whole.dominant


def test_an_example_is_cut_and_says_so(tmp_path):
    from tabalyst.report_finding_details import EXAMPLE_MAX_CHARS

    long = "K" * (EXAMPLE_MAX_CHARS + 20)
    _, profile = _built(tmp_path, _csv(["KEY12", long]))

    detail = _detail(profile)

    assert detail is not None
    cut = [e for item in detail.lengths for e in item.examples if e.truncated]
    assert cut and all(len(e.value) == EXAMPLE_MAX_CHARS for e in cut)


def test_the_stored_detail_holds_numbers_and_values_and_no_sentence(tmp_path):
    _, profile = _built(tmp_path, _csv(MINORITY))
    column = json.loads(dump_json(profile.model_dump(mode="json")))["report"]["datasets"][0][
        "columns"
    ][0]

    detail = column["summary"]["finding_details"]["lengths"]

    assert set(detail) == {
        "state",
        "examples_from",
        "total",
        "dominant",
        "lengths",
        "more_lengths",
    }
    assert "Minority" not in json.dumps(detail) and "character" not in json.dumps(detail)


def test_the_findings_table_prints_the_stored_detail(tmp_path):
    source = write_text(tmp_path, "data.csv", _csv(MINORITY))
    profile = analyze_csv(source, ReportConfig(scan=ScanConfig.model_validate({})))
    reloaded = load_profile(
        write_text(tmp_path, "report.json", dump_json(profile.model_dump(mode="json")))
    )

    html = render_report(reloaded)

    assert "Dominant length" in html and "Lengths that few texts have" in html
    assert "5 characters" in html and "8 characters" in html
    assert "KEY 12 3" in html
    assert "The scan kept every distinct text of these cases." in html


def test_the_render_of_the_detail_equals_the_render_from_memory(tmp_path):
    source = write_text(tmp_path, "data.csv", _csv(MINORITY))
    profile = analyze_csv(source, ReportConfig(scan=ScanConfig.model_validate({})))
    reloaded = load_profile(
        write_text(tmp_path, "report.json", dump_json(profile.model_dump(mode="json")))
    )

    def strip(html: str) -> str:
        return "\n".join(
            line for line in html.splitlines() if "generated" not in line.lower()
        )

    assert strip(render_report(reloaded)) == strip(render_report(profile))


def test_a_rare_length_absent_from_the_sample_has_its_cases(tmp_path):
    keys = [f"KEY{n:05d}" for n in range(3_000)]
    keys[2_053] = "KEY2053"
    source = write_text(tmp_path, "data.csv", "\n".join(["key", *keys]) + "\n")
    config = ScanConfig.model_validate({"limits": {"max_distinct_per_field": 500, "max_samples": 20}})
    result = scan(source, config=config)
    profile = build_profile(result, ReportConfig(scan=result.config))
    sampled = {entry.value for entry in result.datasets[0].fields[0].values.samples.listed}

    detail = profile.report.datasets[0].columns[0].summary.finding_details.lengths

    assert "KEY2053" not in sampled
    assert detail is not None and detail.examples_from == "cases"
    by_length = {item.length: item for item in detail.lengths}
    assert [e.value for e in by_length[7].examples] == ["KEY2053"]
    assert by_length[7].examples[0].count == 1 and by_length[7].complete
    assert by_length[7].count == 1 and 8 not in by_length

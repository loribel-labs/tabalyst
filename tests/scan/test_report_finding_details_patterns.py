# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Detail of the minority patterns in the Findings table (lot R12, tranche 2).

The contract is ``docs/dev/report/summary-table.md`` 22: the dominant pattern, the
minority ones the Scan named with their distinct values, and examples taken from the sample
the Scan held (the Report keeps fewer), through the exposure of the column.
"""

import json
import random

import pytest
from scan_helpers import write_text

from tabalyst import analyze_csv
from tabalyst.json_text import dump_json
from tabalyst.report_config import ReportConfig
from tabalyst.report_finding_details import EXAMPLES_PER_ITEM, PATTERNS_SHOWN
from tabalyst.report_profile import build_profile
from tabalyst.report_summary import attach_summaries
from tabalyst.reporting import load_profile, render_report
from tabalyst.scanner import ScanConfig, scan

ODD = ["12345", "AB-12", "A1A1A1", "a1a 1a1", "99 999"]
LETTERS = "ABCEGHJKLMNPRSTVXY"


def _codes(count: int) -> list[str]:
    draw = random.Random(1)

    def one() -> str:
        letter = draw.choice
        return (
            f"{letter(LETTERS)}{draw.randint(0, 9)}{letter(LETTERS)} "
            f"{draw.randint(0, 9)}{letter(LETTERS)}{draw.randint(0, 9)}"
        )

    return sorted({one() for _ in range(count * 2)})[:count]


def _csv(count: int, odd: list[str]) -> str:
    rows = ["code,row"] + [f"{code},{n}" for n, code in enumerate(_codes(count))]
    rows += [f"{value},{1000 + n}" for n, value in enumerate(odd)]
    return "\n".join(rows) + "\n"


def _built(tmp_path, content, **settings):
    """The Scan and the Report built from it, as ``tabalyst report`` does."""
    source = write_text(tmp_path, "data.csv", content)
    result = scan(source, config=ScanConfig.model_validate(settings))
    config = ReportConfig(scan=result.config)
    return result, build_profile(result, config)


def _detail(profile):
    column = profile.report.datasets[0].columns[0]
    assert column.summary is not None
    return column.summary.finding_details.patterns


def test_the_detail_names_the_dominant_and_the_minority_patterns(tmp_path):
    _, profile = _built(tmp_path, _csv(90, ODD))

    detail = _detail(profile)

    assert detail is not None
    assert detail.dominant.render == "A9A 9A9" and detail.dominant.distinct == 90
    assert {item.render for item in detail.patterns} == {
        "99999",
        "99 999",
        "a9a 9a9",
        "A9A9A9",
        "AA-99",
    }
    assert all(item.distinct == 1 for item in detail.patterns)
    assert detail.population == 95 and detail.population_complete
    assert detail.more_patterns == 0
    assert detail.examples_from == "sample"


def test_each_minority_pattern_carries_examples_from_the_sample(tmp_path):
    _, profile = _built(tmp_path, _csv(90, ODD))

    detail = _detail(profile)

    assert detail is not None
    examples = {item.render: [e.value for e in item.examples] for item in detail.patterns}
    assert examples["99999"] == ["12345"] and examples["AA-99"] == ["AB-12"]
    assert all(len(values) <= EXAMPLES_PER_ITEM for values in examples.values())


def test_the_examples_come_from_the_whole_sample_not_the_reduced_base(tmp_path):
    # 300 distinct values: the Report base keeps 100 of them, the odd ones sit past them.
    result, profile = _built(tmp_path, _csv(300, ODD))
    kept = {entry.id for entry in profile.datasets[0].fields[0].values.samples.listed}
    named = {
        example
        for item in result.derived.patterns.fields[0].all_patterns()
        if item.d == 1
        for example in item.examples
    }
    assert not named <= kept, "the base must have lost examples for the test to mean anything"

    detail = _detail(profile)

    assert detail is not None
    assert {e.value for item in detail.patterns for e in item.examples} == set(ODD)


def test_a_document_attached_at_the_render_has_the_counts_and_no_lost_example(tmp_path):
    source = write_text(tmp_path, "data.csv", _csv(300, ODD))
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
    # The base holds fewer sample values: counts and shapes stay, examples may go.
    assert [(p.render, p.distinct) for p in detail.patterns] == [
        (p.render, p.distinct) for p in whole.patterns
    ]
    kept = [e for item in detail.patterns for e in item.examples]
    lost = [e for item in whole.patterns for e in item.examples]
    assert len(kept) < len(lost)
    assert (detail.examples_from == "none") == (not kept)


def test_patterns_beyond_the_bound_are_counted_not_listed(tmp_path):
    odd = ODD + ["7-7", "zz zz zz"]
    _, profile = _built(tmp_path, _csv(300, odd))

    detail = _detail(profile)

    assert detail is not None
    assert len(detail.patterns) == PATTERNS_SHOWN
    assert detail.more_patterns == len(odd) - PATTERNS_SHOWN
    source = write_text(tmp_path, "again.csv", _csv(300, odd))
    html = render_report(
        analyze_csv(source, ReportConfig(scan=ScanConfig.model_validate({})))
    )
    assert f"+{len(odd) - PATTERNS_SHOWN} more patterns" in html


def test_a_column_without_minority_pattern_has_no_detail(tmp_path):
    _, profile = _built(tmp_path, _csv(60, []))

    assert _detail(profile) is None


@pytest.mark.parametrize("mode", ["mask", "hide"])
def test_a_masked_or_hidden_column_has_no_detail_and_leaks_no_value(tmp_path, mode):
    # A render holds the literal text of the values (here the prefix and the domain): the
    # Scan finds no pattern for such a column, and a document edited afterwards gets none.
    result, profile = _built(tmp_path, _csv(90, ODD))
    assert _detail(profile) is not None
    for column in profile.report.datasets[0].columns:
        column.exposure = mode

    attach_summaries(profile, result)

    column = profile.report.datasets[0].columns[0]
    assert column.summary is not None
    assert column.summary.finding_details.patterns is None
    text = column.summary.model_dump_json()
    assert all(value not in text for value in ("12345", "AB-12", "A1A1A1", "a1a 1a1"))


def test_an_example_is_cut_and_says_so(tmp_path):
    from tabalyst.report_finding_details import EXAMPLE_MAX_CHARS

    long = "9" * (EXAMPLE_MAX_CHARS + 20)
    # The discovery reads values up to 64 characters by default: raise it so that one this
    # long takes part and the cap of the detail is the one that cuts.
    _, profile = _built(
        tmp_path,
        _csv(90, ["12345", long]),
        pattern_inference={"max_value_length": 200},
    )

    detail = _detail(profile)

    assert detail is not None
    cut = [e for item in detail.patterns for e in item.examples if e.truncated]
    assert cut and all(len(e.value) == EXAMPLE_MAX_CHARS for e in cut)


def test_the_stored_detail_holds_codes_numbers_and_values_and_no_sentence(tmp_path):
    _, profile = _built(tmp_path, _csv(90, ODD))
    column = json.loads(dump_json(profile.model_dump(mode="json")))["report"]["datasets"][0][
        "columns"
    ][0]

    detail = column["summary"]["finding_details"]["patterns"]

    assert set(detail) == {
        "examples_from",
        "population",
        "population_complete",
        "dominant",
        "patterns",
        "more_patterns",
    }
    assert "Minority" not in json.dumps(detail) and "sample of" not in json.dumps(detail)


def test_the_findings_table_prints_the_stored_detail(tmp_path):
    source = write_text(tmp_path, "data.csv", _csv(90, ODD))
    profile = analyze_csv(source, ReportConfig(scan=ScanConfig.model_validate({})))
    reloaded = load_profile(
        write_text(tmp_path, "report.json", dump_json(profile.model_dump(mode="json")))
    )

    html = render_report(reloaded)

    assert "Dominant pattern" in html and "Patterns that few distinct values share" in html
    assert "AA-99" in html and "AB-12" in html
    assert "Examples are values of a sample" in html
    # The raw pattern ids of the observation are not printed once the detail is.
    assert "Patterns f2.p1" not in html


def test_the_render_of_the_detail_equals_the_render_from_memory(tmp_path):
    source = write_text(tmp_path, "data.csv", _csv(90, ODD))
    profile = analyze_csv(source, ReportConfig(scan=ScanConfig.model_validate({})))
    reloaded = load_profile(
        write_text(tmp_path, "report.json", dump_json(profile.model_dump(mode="json")))
    )

    def strip(html: str) -> str:
        return "\n".join(
            line for line in html.splitlines() if "generated" not in line.lower()
        )

    assert strip(render_report(reloaded)) == strip(render_report(profile))

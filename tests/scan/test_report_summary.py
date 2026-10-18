# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The Report document carries its summaries and the pages print them (lot R10b).

The contract is ``docs/dev/report/summary-table.md`` 20: the findings, Overview,
Details, signals and quality are built once with the document, with the exposure
applied, and the render computes none of them.
"""

import json
import sys

import pytest
from scan_helpers import write_text

from tabalyst import analyze_csv
from tabalyst.json_text import dump_json
from tabalyst.report_config import ReportConfig
from tabalyst.reporting import load_profile, render_report
from tabalyst.scanner import ScanConfig


def _contacts() -> str:
    lines = ["contact,row"]
    lines += [f"zzsecret{n}@example.org,{n}" for n in range(100)]
    lines += [f"zzbad {n}@example.org,{100 + n}" for n in range(3)]
    return "\n".join(lines) + "\n"


def _profile(tmp_path, content, mode="show"):
    source = write_text(tmp_path, "data.csv", content)
    config = ReportConfig(
        scan=ScanConfig.model_validate({"exposure": {"sensitive_values": mode}})
    )
    return analyze_csv(source, config)


def test_every_column_and_dataset_of_a_report_carries_its_summary(tmp_path):
    profile = _profile(tmp_path, "name,amount\nAlice,1\nBob,2\n")

    for dataset in profile.report.datasets:
        assert dataset.table is not None
        assert dataset.table.quality.columns == len(dataset.columns)
        for column in dataset.columns:
            assert column.summary is not None
            assert column.summary.findings.field == column.id


def test_the_stored_summary_holds_codes_and_numbers_and_no_sentence(tmp_path):
    profile = _profile(tmp_path, _contacts())
    document = profile.model_dump(mode="json")

    column = document["report"]["datasets"][0]["columns"][0]
    overview = column["summary"]["overview"]

    assert set(overview) == {"kind", "type", "facts"}
    text = json.dumps(document["report"]["datasets"])
    assert "present values" not in text and "Spelling variants" not in text


def test_the_overview_sentence_is_written_from_the_stored_facts(tmp_path):
    profile = _profile(tmp_path, "kind,row\n" + "a,1\nb,2\na,3\n" * 5)
    document = profile.model_dump(mode="json")
    reloaded = load_profile(write_text(tmp_path, "report.json", dump_json(document)))

    column = next(c for c in reloaded.report.datasets[0].columns if c.name == "kind")

    assert column.summary is not None
    assert column.summary.overview == next(
        c.summary.overview
        for c in profile.report.datasets[0].columns
        if c.name == "kind"
    )
    assert column.summary.overview.text.endswith("and 2 distinct values.")


@pytest.mark.parametrize("mode", ["mask", "hide"])
def test_the_summaries_of_a_masked_or_hidden_column_hold_no_raw_value(tmp_path, mode):
    profile = _profile(tmp_path, _contacts(), mode)

    summaries = [
        column.summary.model_dump_json()
        for dataset in profile.report.datasets
        for column in dataset.columns
        if column.summary
    ]

    assert summaries
    assert all("zzsecret" not in item and "zzbad" not in item for item in summaries)


def test_the_render_computes_no_finding_overview_detail_or_signal(tmp_path, monkeypatch):
    profile = _profile(tmp_path, _contacts())
    reloaded = load_profile(
        write_text(tmp_path, "report.json", dump_json(profile.model_dump(mode="json")))
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("the render must not run a rule of the summary")

    # Every module that imported a rule is patched, not only ``report_summary``: a
    # render that calls one through another module's import must fail too. A name is
    # patched only when it is the function of the defining module (``report_sections``
    # has its own ``quality_view``).
    rules = {
        "column_findings": "tabalyst.report_findings",
        "overview_for": "tabalyst.report_overview",
        "details_for": "tabalyst.report_details",
        "variant_details": "tabalyst.report_finding_details",
        "signals_view": "tabalyst.report_signals",
        "quality_view": "tabalyst.report_signals",
        "expose_examples": "tabalyst.report_preview",
        "preview_examples": "tabalyst.report_preview",
        "attach_summaries": "tabalyst.report_summary",
    }
    patched = 0
    for module_name, module in list(sys.modules.items()):
        if not module_name.startswith("tabalyst."):
            continue
        for name, home in rules.items():
            if getattr(module, name, None) is getattr(sys.modules[home], name):
                monkeypatch.setattr(module, name, forbidden)
                patched += 1
    assert patched >= len(rules)

    html = render_report(reloaded)

    assert "Summary" in html


def test_a_report_renders_the_same_from_the_file_as_from_memory(tmp_path):
    profile = _profile(tmp_path, _contacts())
    reloaded = load_profile(
        write_text(tmp_path, "report.json", dump_json(profile.model_dump(mode="json")))
    )

    def strip(html: str) -> str:
        return "\n".join(
            line for line in html.splitlines() if "generated" not in line.lower()
        )

    assert strip(render_report(reloaded)) == strip(render_report(profile))


def test_a_document_without_summaries_gets_them_at_the_render(tmp_path):
    profile = _profile(tmp_path, _contacts())
    document = profile.model_dump(mode="json")
    for dataset in document["report"]["datasets"]:
        dataset["table"] = None
        for column in dataset["columns"]:
            column["summary"] = None
    older = load_profile(write_text(tmp_path, "older.json", dump_json(document)))

    html = render_report(older)

    assert all(
        column.summary is not None
        for dataset in older.report.datasets
        for column in dataset.columns
    )
    assert "Summary" in html


def test_summaries_built_for_another_exposure_are_rebuilt_at_the_render(tmp_path):
    profile = _profile(tmp_path, _contacts())
    document = profile.model_dump(mode="json")
    for dataset in document["report"]["datasets"]:
        for column in dataset["columns"]:
            column["exposure"] = "hide"
    edited = load_profile(write_text(tmp_path, "edited.json", dump_json(document)))

    render_report(edited)

    summaries = [
        column.summary
        for dataset in edited.report.datasets
        for column in dataset.columns
    ]
    assert all(summary is not None and summary.details.state == "hidden" for summary in summaries)
    assert all("zzsecret" not in summary.model_dump_json() for summary in summaries)

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The chart pages that ``--details`` writes beside a report
(docs/dev/report/chart-pages.md): the trigger, the files, the library and the links."""

from __future__ import annotations

import csv
import functools
import json
import re
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from tabalyst import generate_reports, report_chain, report_service
from tabalyst.cli import app
from tabalyst.errors import ConfigurationError
from tabalyst.report_charts import DRAWN, ECHARTS, missing_sections
from tabalyst.scanner.secondpass.models import (
    MissingColumn,
    MissingPattern,
    MissingPatternsResult,
)

runner = CliRunner()
RECORDS = 600


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path.parent / f"{tmp_path.name}-home"))


def _source(tmp_path, *, gaps: bool = True, name: str = "contacts.csv"):
    """``phone`` and ``ref`` go missing as a block, ``note`` now and then; ``id`` never."""
    path = tmp_path / name
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "phone", "ref", "note"])
        for n in range(RECORDS):
            block = gaps and 100 <= n < 220
            writer.writerow(
                [
                    n + 1,
                    "" if block else f"555-{n:04d}",
                    "" if block else f"R{n}",
                    "" if gaps and n % 7 == 0 else "a",
                ]
            )
    return path


def _report(tmp_path, *args: str, source=None):
    source = source or _source(tmp_path)
    return runner.invoke(app, ["report", str(source), "--details", *args])


# The page -------------------------------------------------------------------------


def test_details_forces_the_second_pass_and_writes_the_chart_page(tmp_path):
    result = _report(tmp_path)

    assert result.exit_code == 0, result.output
    document = json.loads((tmp_path / "contacts.json").read_text(encoding="utf-8"))
    assert document["analyses"]["mode"] == "forced"
    page = (tmp_path / "contacts" / "charts-missing.html").read_text(encoding="utf-8")
    assert '<meta name="generator" content="Tabalyst chart page">' in page
    assert 'id="rows"' in page and "Combinations of missing values" in page
    # The table holds the figures the chart draws, and reads without the library.
    assert "<code>phone</code>, <code>ref</code>" in page
    assert "<code>phone</code> and <code>ref</code> go missing together" in page
    data = json.loads(re.search(r'data-chart-data>(.*?)</script>', page, re.DOTALL).group(1))
    assert data["records"] == RECORDS and data["drawn"] == DRAWN
    assert data["columns"] == ["phone", "ref", "note"]


def test_the_chart_page_loads_the_pinned_library_and_sends_no_data():
    assert re.fullmatch(r"https://cdn\.jsdelivr\.net/npm/echarts@\d+\.\d+\.\d+/dist/echarts\.min\.js", ECHARTS.url)
    assert ECHARTS.version in ECHARTS.url
    assert re.fullmatch(r"sha384-[A-Za-z0-9+/]{64}", ECHARTS.integrity)


def test_only_the_chart_page_loads_a_script_from_outside(tmp_path):
    assert _report(tmp_path).exit_code == 0
    folder = tmp_path / "contacts"
    chart = (folder / "charts-missing.html").read_text(encoding="utf-8")
    report = (tmp_path / "contacts.html").read_text(encoding="utf-8")

    (tag,) = re.findall(r"<script src=[^>]*>", chart)
    assert f'src="{ECHARTS.url}"' in tag
    assert f'integrity="{ECHARTS.integrity}"' in tag
    assert 'crossorigin="anonymous"' in tag and 'referrerpolicy="no-referrer"' in tag
    for html in [report, *(page.read_text(encoding="utf-8") for page in folder.glob("col-*.html"))]:
        assert not re.search(r"<script[^>]+src=", html)
        assert not re.search(r"<link[^>]+href=\"https?:", html)
        assert "cdn.jsdelivr.net" not in html


def test_the_report_and_the_column_pages_link_to_the_chart_page(tmp_path):
    assert _report(tmp_path).exit_code == 0
    report = (tmp_path / "contacts.html").read_text(encoding="utf-8")
    folder = tmp_path / "contacts"

    # From the card of the dataset and from the navigation.
    assert report.count('href="contacts/charts-missing.html#rows"') == 2
    phone = next(folder.glob("col-*-phone.html")).read_text(encoding="utf-8")
    assert 'href="charts-missing.html#rows"' in phone
    # A column that never lacks a value is not on the page, so it does not link to it.
    ident = next(folder.glob("col-*-id.html")).read_text(encoding="utf-8")
    assert "charts-missing.html" not in ident
    chart = (folder / "charts-missing.html").read_text(encoding="utf-8")
    assert 'href="../contacts.html"' in chart
    assert re.search(r'<a href="col-\d+-phone\.html"><code>phone</code></a>', chart)


# The trigger ----------------------------------------------------------------------


def test_details_with_the_second_pass_turned_off_is_an_error(tmp_path):
    config = tmp_path / "off.json"
    config.write_text(json.dumps({"deep": {"mode": "off"}}), encoding="utf-8")

    result = _report(tmp_path, "-c", str(config))

    assert result.exit_code != 0
    assert "deep.mode is off" in result.output
    assert not (tmp_path / "contacts.html").exists()
    with pytest.raises(ConfigurationError):
        generate_reports([_source(tmp_path)], config_path=config, details=True, force=True)


def test_a_costly_pass_asked_by_details_outside_a_terminal_stops_with_exit_code_3(
    tmp_path, monkeypatch
):
    original = report_chain.plan_second_pass
    monkeypatch.setattr(
        report_chain, "plan_second_pass", functools.partial(original, threshold_seconds=0.0)
    )
    combine = report_service.combine_confirmations
    monkeypatch.setattr(
        report_service, "combine_confirmations", functools.partial(combine, threshold_seconds=0.0)
    )

    stopped = _report(tmp_path)
    confirmed = _report(tmp_path, "--yes")

    assert stopped.exit_code == 3
    assert confirmed.exit_code == 0, confirmed.output
    assert (tmp_path / "contacts" / "charts-missing.html").exists()


def test_details_on_a_scan_document_without_its_source_fails(tmp_path):
    source = _source(tmp_path)
    target = tmp_path / "contacts.scan.json"
    assert runner.invoke(app, ["scan", str(source), "-o", str(target)]).exit_code == 0
    source.unlink()

    result = runner.invoke(app, ["report", "--scan", str(target), "--details"])

    assert result.exit_code == 4
    assert "--details" in result.output


def test_a_dataset_without_missing_values_writes_no_chart_page_and_says_why(tmp_path):
    result = _report(tmp_path, source=_source(tmp_path, gaps=False))

    assert result.exit_code == 0, result.output
    assert not (tmp_path / "contacts" / "charts-missing.html").exists()
    assert "no chart of the missing values for rows: fewer than two columns lack a value" in result.output
    assert "charts-missing.html" not in (tmp_path / "contacts.html").read_text(encoding="utf-8")


# The files ------------------------------------------------------------------------


def test_an_existing_chart_page_needs_force_and_a_report_without_details_removes_it(tmp_path):
    source = _source(tmp_path)
    assert _report(tmp_path, source=source).exit_code == 0
    page = tmp_path / "contacts" / "charts-missing.html"

    again = _report(tmp_path, source=source)
    assert again.exit_code != 0 and "already exists" in again.output

    plain = runner.invoke(app, ["report", str(source), "--force"])
    assert plain.exit_code == 0, plain.output
    assert not page.exists()


def test_a_forced_report_whose_data_lost_its_gaps_removes_the_old_chart_page(tmp_path):
    assert _report(tmp_path).exit_code == 0
    page = tmp_path / "contacts" / "charts-missing.html"
    full = _source(tmp_path, gaps=False)

    result = _report(tmp_path, "--force", source=full)

    assert result.exit_code == 0, result.output
    assert not page.exists()
    assert next((tmp_path / "contacts").glob("col-*-phone.html")).exists()


def test_a_file_of_the_user_named_like_a_chart_page_is_not_removed(tmp_path):
    source = _source(tmp_path)
    folder = tmp_path / "contacts"
    folder.mkdir()
    mine = folder / "charts-notes.html"
    mine.write_text("<p>mine</p>", encoding="utf-8")

    assert runner.invoke(app, ["report", str(source), "--force"]).exit_code == 0

    assert mine.exists()


# The sections ---------------------------------------------------------------------


def _result() -> MissingPatternsResult:
    return MissingPatternsResult(
        records=1_000,
        columns=[
            MissingColumn(field="c1", display="phone", missing=300),
            MissingColumn(field="c2", display="ref", missing=330),
        ],
        complete_records=650,
        distinct=3,
        complete=True,
        untracked=0,
        listed=[
            MissingPattern(columns=["c1", "c2"], count=280),
            MissingPattern(columns=["c2"], count=50),
            MissingPattern(columns=["c1"], count=20),
        ],
        other_patterns=0,
        other_records=0,
    )


def _profile(result=None, exposure: str | None = None, candidates=()):
    item = SimpleNamespace(analyzer="missing_patterns", dataset="rows", status="complete", result=result)
    deep = SimpleNamespace(
        analyses=[item] if result is not None else [],
        plan=SimpleNamespace(candidates=list(candidates)),
    )
    fields = [SimpleNamespace(id="c1", exposure=exposure), SimpleNamespace(id="c2", exposure=None)]
    return SimpleNamespace(
        analyses=SimpleNamespace(deep=deep),
        datasets=[SimpleNamespace(id="rows", fields=fields)],
    )


def test_a_section_lists_the_columns_by_records_missing_and_draws_the_patterns():
    (section,), left = missing_sections(_profile(_result()), {("rows", "c1"): "col-02-phone.html"})

    assert left == []
    assert [(column.display, column.missing, column.href) for column in section.columns] == [
        ("ref", 330, None),
        ("phone", 300, "col-02-phone.html"),
    ]
    assert section.data["patterns"] == [[280, [0, 1]], [50, [1]], [20, [0]]]
    assert section.lacking == 350 and section.drawn == 3
    assert [part.text for part in section.lines[0].parts if part.code] == ["phone", "ref"]


def test_a_withheld_column_leaves_its_dataset_out():
    sections, (left,) = missing_sections(_profile(_result(), exposure="hide"))

    assert sections == [] and left.reason == "withheld_columns"


def test_a_dataset_beyond_the_column_limit_is_left_out_with_its_reason():
    candidate = SimpleNamespace(
        analyzer="missing_patterns",
        dataset="rows",
        applicability=SimpleNamespace(state="not_applicable", reasons=["too_many_columns"]),
    )

    sections, (left,) = missing_sections(_profile(candidates=[candidate]))

    assert sections == [] and left.reason == "too_many_columns"
    assert "deep.missing.max_columns" in left.words


# The reference case ---------------------------------------------------------------


def test_the_opportunity_fields_of_the_crm_example_form_the_only_block(tmp_path):
    # The case of the mockup (chart-pages.md 6): the fields of an opportunity go missing as a
    # block. 3,000 rows give the shape of the 200,000 of the mockup, about 95% of each column.
    source = tmp_path / "crm.csv"
    generated = runner.invoke(app, ["generate", "--example", "crm", "--rows", "3000", "-o", str(source)])
    assert generated.exit_code == 0, generated.output

    result = runner.invoke(app, ["report", str(source), "--details", "--yes"])

    assert result.exit_code == 0, result.output
    page = (tmp_path / "crm" / "charts-missing.html").read_text(encoding="utf-8")
    lines = re.findall(r'<p class="ins-line">(.*?)</p>', page)
    assert len(lines) == 1
    assert lines[0].startswith(
        "<code>opportunity_amount</code>, <code>opportunity_probability</code> and "
        "<code>opportunity_close_date</code> go missing together: "
    )

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The HTML restitution of the identifier uniqueness: Summary, column page, Findings, settings."""

import json
import re

import pytest
from identifier_uniqueness_helpers import population, uniqueness_of, write_csv

from tabalyst import generate_reports
from tabalyst.dedup_service import dedup_csv
from tabalyst.identifier_uniqueness.models import IdentifierUniqueness
from tabalyst.report_uniqueness import (
    uniqueness_case,
    uniqueness_settings,
    uniqueness_view,
)
from tabalyst.scanner.config import ScanConfig

pytestmark = pytest.mark.uid_lot("4")


def _pages(tmp_path, rows, **options):
    source = write_csv(tmp_path, "r.csv", rows)
    generate_reports([source], output_dir=tmp_path / "out", details=True, **options)
    out = tmp_path / "out"
    report = (out / "r.html").read_text(encoding="utf-8")
    page = next(p for p in out.rglob("*.html") if p.name != "r.html" and "customer-id" in p.name)
    document = json.loads((out / "r.json").read_text(encoding="utf-8"))
    return report, page.read_text(encoding="utf-8"), document


def _block(page: str) -> str:
    return re.search(r'id="uniqueness".*?</div>\s*(?=</div></section>)', page, re.DOTALL).group(0)


def test_case_a_a_raw_unique_id_is_told_unique_across_all_records(tmp_path):
    _, page, _ = _pages(tmp_path, population(distinct_ids=300))

    block = _block(page)
    assert "Unique across all 300 source records. No missing IDs." in block


def test_case_b_copies_explain_every_repetition_and_the_type_is_not_unique_id(tmp_path):
    report, page, _ = _pages(tmp_path, population(distinct_ids=495, copies=5))

    assert "fully explained by 5 exact duplicate rows" in _block(page)
    assert "No ID conflicts remain among 495 distinct records." in _block(page)
    assert "Unique after row deduplication" in report
    assert "Probable unique ID" not in page


def test_case_c_residual_repetitions_are_split_from_the_explained_ones(tmp_path):
    report, page, _ = _pages(tmp_path, population(distinct_ids=490, shared_id_rows=10, copies=5))

    assert "15 repetitions: 5 explained by exact duplicate rows, 10 remain" in _block(page)
    assert "10 ID repetitions remain between distinct records" in report


def test_case_d_unavailable_measures_conclude_nothing(tmp_path):
    rows = population(distinct_ids=2000, copies=600)
    report, page, _ = _pages(
        tmp_path,
        rows,
        config_path=_limited(tmp_path),
    )

    assert "No conclusion about uniqueness after deduplication." in _block(page)
    assert "Uniqueness not fully assessed" not in report  # the Summary shows concluding cases only


def test_case_e_missing_ids_cannot_establish_uniqueness(tmp_path):
    rows = population(distinct_ids=100) + [("", "active")] * 3
    config = tmp_path / "off.json"
    config.write_text(json.dumps({"deep": {"mode": "off"}}), encoding="utf-8")
    _, page, _ = _pages(tmp_path, rows, config_path=config)

    assert "some records have no ID" in _block(page)


def test_case_e_with_the_copies_counted_says_what_is_left_among_the_ids_present(tmp_path):
    rows = population(distinct_ids=100) + [("", "active")] * 3
    _, page, _ = _pages(tmp_path, rows)

    block = _block(page)
    assert "3 records have no ID" in block
    assert "No ID repeats between the 100 distinct rows that have one." in block
    assert "no ID is strictly unique" in block


def test_a_dedup_report_shows_in_the_page_and_the_analysis_settings(tmp_path):
    rows = population(distinct_ids=2000, copies=600)
    source = write_csv(tmp_path, "r.csv", rows)
    dedup_csv(source, output_dir=tmp_path)
    report, page, _ = _pages(tmp_path, rows, config_path=_limited(tmp_path))

    assert "Report r.dedup.json, found beside the source." in _block(page)
    settings = re.search(r"<dt>Identifier uniqueness</dt><dd>(.*?)</dd>", report, re.DOTALL).group(1)
    assert "r.dedup.json" in settings and "does not run Dedup" in settings


def test_the_raw_finding_stays_and_points_to_the_decomposition(tmp_path):
    _, page, _ = _pages(tmp_path, population(distinct_ids=495, shared_id_rows=5, copies=5))

    assert "ID repetitions" in page
    assert 'href="#uniqueness"' in page


def test_a_repetition_is_not_counted_twice_in_the_findings(tmp_path):
    _, page, document = _pages(tmp_path, population(distinct_ids=495, shared_id_rows=5, copies=5))

    column = next(c for c in document["report"]["datasets"][0]["columns"] if c["name"] == "customer_id")
    assert [i["code"] for i in column["summary"]["findings"]["issues"]["items"]].count(
        "identifier.repetition"
    ) == 1
    assert page.count('class="fcls fcls-error"') == 0


def test_a_column_that_is_not_an_identifier_has_no_block(tmp_path):
    source = write_csv(tmp_path, "r.csv", population(distinct_ids=50, copies=2))
    generate_reports([source], output_dir=tmp_path / "out", details=True)

    page = next(p for p in (tmp_path / "out").rglob("*.html") if "status" in p.name)
    assert 'id="uniqueness"' not in page.read_text(encoding="utf-8")


def test_the_view_reads_the_stored_object_without_a_figure_when_it_failed(tmp_path):
    document = _pages(tmp_path, population(distinct_ids=495, copies=5))[2]
    item = dict(uniqueness_of(document, "customer_id"))
    item.update(status="failed", interpretation="not_assessed", reason="inconsistent_measures")

    view = uniqueness_view(IdentifierUniqueness.model_validate(item))

    assert view.case == "D" and view.rows == [] and view.status_word == "Contradictory"
    assert uniqueness_view(None) is None
    assert uniqueness_settings([]) is None
    assert uniqueness_case(IdentifierUniqueness.model_validate(item)) == "D"


def _limited(tmp_path):
    path = tmp_path / "config.json"
    scan = ScanConfig.model_validate({"limits": {"max_tracked_records": 500}})
    document = {"scan": scan.model_dump(by_alias=True, mode="json", exclude_defaults=True)}
    path.write_text(json.dumps(document), encoding="utf-8")
    return path

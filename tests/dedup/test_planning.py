# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Details of the batch plan beyond the contract tests (design dedup 7, 13.1)."""

from pathlib import Path

import pytest
from dedup_helpers import settings, write_csv

from tabalyst.dedup.discovery import (
    BATCH_REPORT_NAME,
    exclusion_reason,
    managed_names,
    plan_batch,
)
from tabalyst.errors import ConfigurationError, InputError, ReportError

ROWS = [("1", "a"), ("1", "a")]


def _plan(specs, **options):
    return plan_batch([str(spec) for spec in specs], settings(**options))


def _names(items) -> list[str]:
    return [Path(item).name for item in items]


@pytest.mark.dedup_lot("1")
@pytest.mark.parametrize(
    ("name", "reason"),
    [
        ("a.sample.csv", "derived_csv"),
        ("A.UNIQUE.CSV", "derived_csv"),
        ("a.duplicates.csv", "derived_csv"),
        ("a.duplicates_all.csv", "derived_csv"),
        ("a.dedup.json", "dedup_output"),
        ("A.Dedup.JSON", "dedup_output"),
        ("dedup.summary.json", "dedup_output"),
        ("a.csv-inspect.json", "inspect_file"),
        ("~$book.xlsx", "lock_file"),
        ("a.csv", None),
        ("unique.csv", None),
        ("a.uniquecsv", None),
        ("a.tsv", None),
    ],
)
def test_the_reason_a_name_is_skipped(name, reason):
    assert exclusion_reason(name) == reason


@pytest.mark.dedup_lot("1")
def test_a_pattern_lists_inspect_and_lock_files_as_excluded_not_as_errors(tmp_path):
    write_csv(tmp_path, "a.csv", ROWS)
    (tmp_path / "a.csv-inspect.json").write_text("{}", encoding="utf-8")
    (tmp_path / "~$a.csv").write_text("lock", encoding="utf-8")
    plan = _plan([tmp_path / "*"])
    assert _names(item.source for item in plan.eligible) == ["a.csv"]
    assert {path.name: reason for path, reason in plan.excluded} == {
        "a.csv-inspect.json": "inspect_file",
        "~$a.csv": "lock_file",
    }


@pytest.mark.dedup_lot("1")
def test_an_inspect_file_named_explicitly_is_refused(tmp_path):
    inspect_file = tmp_path / "a.csv-inspect.json"
    inspect_file.write_text("{}", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="Inspect"):
        _plan([inspect_file])


@pytest.mark.dedup_lot("1")
def test_a_directory_is_not_a_source(tmp_path):
    (tmp_path / "folder.csv").mkdir()
    with pytest.raises(InputError):
        _plan([tmp_path / "folder.csv"])
    with pytest.raises(InputError):
        _plan([tmp_path / "*.csv"])  # a pattern ignores directories


@pytest.mark.dedup_lot("1")
def test_no_input_is_a_configuration_error():
    with pytest.raises(ConfigurationError):
        _plan([])


@pytest.mark.dedup_lot("1")
def test_a_file_named_explicitly_stays_eligible_when_a_pattern_also_finds_it(tmp_path):
    write_csv(tmp_path, "a.csv", ROWS)
    write_csv(tmp_path, "b.sample.csv", ROWS)
    both = _plan([tmp_path / "*.csv", tmp_path / "b.sample.csv"])
    assert _names(item.source for item in both.eligible) == ["a.csv", "b.sample.csv"]
    assert both.excluded == ()
    reverse = _plan([tmp_path / "b.sample.csv", tmp_path / "*.csv"])
    assert _names(item.source for item in reverse.eligible) == ["b.sample.csv", "a.csv"]
    assert reverse.excluded == ()


@pytest.mark.dedup_lot("1")
def test_sources_follow_the_order_of_the_specs_and_sort_within_a_pattern(tmp_path):
    for name in ("c.csv", "a.csv", "b.csv"):
        write_csv(tmp_path, name, ROWS)
    plan = _plan([tmp_path / "c.csv", tmp_path / "*.csv"])
    assert _names(item.source for item in plan.eligible) == ["c.csv", "a.csv", "b.csv"]


@pytest.mark.dedup_lot("1")
def test_a_file_is_listed_once_when_several_patterns_exclude_it(tmp_path):
    write_csv(tmp_path, "a.csv", ROWS)
    write_csv(tmp_path, "a.unique.csv", ROWS)
    plan = _plan([tmp_path / "*.csv", tmp_path / "a.*.csv"], force=True)
    assert _names(path for path, _ in plan.excluded) == ["a.unique.csv"]


@pytest.mark.dedup_lot("1")
def test_the_managed_names_use_the_whole_stem_and_the_destination(tmp_path):
    names = managed_names(tmp_path / "my.data.csv", tmp_path / "out")
    assert {kind: path.name for kind, path in names.items()} == {
        "unique": "my.data.unique.csv",
        "duplicates": "my.data.duplicates.csv",
        "duplicates_all": "my.data.duplicates_all.csv",
        "report": "my.data.dedup.json",
    }
    assert {path.parent for path in names.values()} == {tmp_path / "out"}


@pytest.mark.dedup_lot("1")
def test_planning_writes_nothing_and_does_not_create_the_output_directory(tmp_path):
    write_csv(tmp_path, "a.csv", ROWS)
    before = sorted(path.name for path in tmp_path.iterdir())
    _plan([tmp_path / "a.csv"], output_dir=tmp_path / "out")
    assert sorted(path.name for path in tmp_path.iterdir()) == before


@pytest.mark.dedup_lot("1")
def test_an_output_directory_that_is_a_file_is_refused(tmp_path):
    write_csv(tmp_path, "a.csv", ROWS)
    stray = tmp_path / "out"
    stray.write_text("x", encoding="utf-8")
    with pytest.raises(ReportError):
        _plan([tmp_path / "a.csv"], output_dir=stray)


@pytest.mark.dedup_lot("1")
def test_the_ownership_test_decides_which_existing_outputs_are_foreign(tmp_path):
    write_csv(tmp_path, "a.csv", ROWS)
    write_csv(tmp_path, "a.unique.csv", ROWS)
    write_csv(tmp_path, "a.duplicates.csv", ROWS)
    seen = []

    def owns(path, planned):
        seen.append((path.name, planned.source.name))
        return path.name == "a.unique.csv"

    with pytest.raises(ReportError, match="a.duplicates.csv"):
        plan_batch([str(tmp_path / "a.csv")], settings(), is_owned=owns)
    assert ("a.unique.csv", "a.csv") in seen

    plan = plan_batch(
        [str(tmp_path / "a.csv")], settings(), is_owned=lambda path, planned: True
    )
    assert _names(item.source for item in plan.eligible) == ["a.csv"]


@pytest.mark.dedup_lot("1")
def test_a_foreign_file_of_another_source_does_not_refuse_this_one(tmp_path):
    write_csv(tmp_path, "a.csv", ROWS)
    (tmp_path / "b.unique.csv").write_text("mine\n", encoding="utf-8")
    assert _names(i.source for i in _plan([tmp_path / "a.csv"]).eligible) == ["a.csv"]


@pytest.mark.dedup_lot("1")
def test_the_batch_report_goes_to_the_output_directory(tmp_path):
    write_csv(tmp_path, "a.csv", ROWS)
    plan = _plan([tmp_path / "*.csv"], output_dir=tmp_path / "out")
    assert plan.batch_report == tmp_path / "out" / BATCH_REPORT_NAME


@pytest.mark.dedup_lot("1")
def test_the_batch_report_goes_beside_sources_that_share_a_folder(tmp_path):
    write_csv(tmp_path, "a.csv", ROWS)
    write_csv(tmp_path, "b.csv", ROWS)
    assert _plan([tmp_path / "*.csv"]).batch_report == tmp_path / BATCH_REPORT_NAME


@pytest.mark.dedup_lot("1")
def test_the_batch_report_goes_to_the_current_directory_for_several_folders(
    tmp_path, monkeypatch
):
    first, second, here = tmp_path / "one", tmp_path / "two", tmp_path / "here"
    for folder in (first, second, here):
        folder.mkdir()
    write_csv(first, "a.csv", ROWS)
    write_csv(second, "b.csv", ROWS)
    monkeypatch.chdir(here)
    plan = _plan([first / "a.csv", second / "b.csv"])
    assert plan.batch_report.parent.samefile(here)
    assert plan.batch_report.name == BATCH_REPORT_NAME


@pytest.mark.dedup_lot("1")
def test_the_batch_report_follows_the_excluded_files_when_nothing_is_eligible(tmp_path):
    write_csv(tmp_path, "a.unique.csv", ROWS)
    plan = _plan([tmp_path / "*.csv"])
    assert plan.eligible == ()
    assert plan.batch_report == tmp_path / BATCH_REPORT_NAME


@pytest.mark.dedup_lot("1")
def test_the_batch_report_is_skipped_only_for_one_explicit_file(tmp_path):
    write_csv(tmp_path, "a.csv", ROWS)
    write_csv(tmp_path, "b.csv", ROWS)
    write_csv(tmp_path, "a.unique.csv", ROWS)
    assert _plan([tmp_path / "a.csv"], force=True).writes_batch_report is False
    assert _plan([tmp_path / "*.csv"], force=True).writes_batch_report is True
    both = _plan([tmp_path / "a.csv", tmp_path / "b.csv"], force=True)
    assert both.writes_batch_report is True
    twice = _plan([tmp_path / "a.csv", tmp_path / "a.csv"], force=True)
    assert twice.writes_batch_report is True
    assert _plan([tmp_path / "a.unique.csv"]).writes_batch_report is False

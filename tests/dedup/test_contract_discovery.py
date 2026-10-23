# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Discovery, exclusions and refused plans (design 7, S7.3, S8): T11, T12, T13,
T24, T26 and T28."""

from pathlib import Path

import pytest
from dedup_helpers import settings, write_csv

ROWS = [("1", "a"), ("1", "a")]


def _plan(specs, *, owned=False, **options):
    """``plan_batch``; ``owned`` stands for the lot 7 test that recognizes the results
    of earlier runs, so that an exclusion test is not also a foreign-output test."""
    from tabalyst.dedup.discovery import plan_batch

    extra = {"is_owned": lambda path, planned: True} if owned else {}
    return plan_batch([str(spec) for spec in specs], settings(**options), **extra)


def _names(paths) -> list[str]:
    return sorted(Path(path).name for path in paths)


def _excluded(plan) -> dict[str, str]:
    return {Path(path).name: reason for path, reason in plan.excluded}


def _eligible(plan) -> list[str]:
    return _names(item.source for item in plan.eligible)


@pytest.fixture
def folder(tmp_path):
    """A folder as Dedup, `sample` and Inspect leave it, beside a real source."""
    write_csv(tmp_path, "customers.csv", ROWS)
    for suffix in ("unique", "duplicates", "duplicates_all"):
        write_csv(tmp_path, f"customers.{suffix}.csv", ROWS)
    write_csv(tmp_path, "orders.sample.csv", ROWS)
    (tmp_path / "customers.dedup.json").write_text("{}", encoding="utf-8")
    (tmp_path / "dedup.summary.json").write_text("{}", encoding="utf-8")
    return tmp_path


@pytest.mark.dedup_lot("1")
@pytest.mark.dedup_t("T11", "T12")
def test_a_wildcard_skips_the_outputs_of_dedup_and_of_sample(folder):
    plan = _plan([folder / "*.csv"], owned=True)
    assert _eligible(plan) == ["customers.csv"]
    assert _excluded(plan) == {
        "customers.unique.csv": "derived_csv",
        "customers.duplicates.csv": "derived_csv",
        "customers.duplicates_all.csv": "derived_csv",
        "orders.sample.csv": "derived_csv",
    }


@pytest.mark.dedup_lot("1")
@pytest.mark.dedup_t("T11")
def test_the_reports_and_the_batch_report_are_never_sources_of_a_pattern(folder):
    plan = _plan([folder / "*"], owned=True)
    assert _eligible(plan) == ["customers.csv"]
    assert _excluded(plan)["customers.dedup.json"] == "dedup_output"
    assert _excluded(plan)["dedup.summary.json"] == "dedup_output"


@pytest.mark.dedup_lot("1")
@pytest.mark.dedup_t("T11")
def test_suffixes_are_compared_without_case(tmp_path):
    write_csv(tmp_path, "Orders.Unique.CSV", ROWS)
    write_csv(tmp_path, "Orders.SAMPLE.csv", ROWS)
    write_csv(tmp_path, "orders.csv", ROWS)
    plan = _plan([tmp_path / "*"], owned=True)
    assert _eligible(plan) == ["orders.csv"]
    assert set(_excluded(plan).values()) == {"derived_csv"}


@pytest.mark.dedup_lot("1")
@pytest.mark.dedup_t("T11")
def test_a_pattern_that_finds_only_outputs_is_a_plan_without_work_not_an_error(tmp_path):
    write_csv(tmp_path, "orders.unique.csv", ROWS)
    write_csv(tmp_path, "orders.duplicates.csv", ROWS)
    plan = _plan([tmp_path / "*.csv"])
    assert _eligible(plan) == []
    assert len(plan.excluded) == 2


@pytest.mark.dedup_lot("1")
@pytest.mark.dedup_t("T11")
def test_a_pattern_that_matches_no_file_is_an_input_error(tmp_path):
    from tabalyst.errors import InputError

    with pytest.raises(InputError):
        _plan([tmp_path / "*.csv"])


@pytest.mark.dedup_lot("1")
@pytest.mark.dedup_t("T11")
def test_an_explicit_missing_file_is_an_input_error_and_recursion_is_refused(tmp_path):
    from tabalyst.errors import ConfigurationError, InputError

    with pytest.raises(InputError):
        _plan([tmp_path / "missing.csv"])
    with pytest.raises(ConfigurationError):
        _plan([tmp_path / "**" / "*.csv"])


@pytest.mark.dedup_lot("1")
@pytest.mark.dedup_t("T13")
def test_a_file_named_explicitly_is_processed_even_with_a_derived_suffix(folder):
    plan = _plan([folder / "customers.unique.csv", folder / "orders.sample.csv"])
    assert _eligible(plan) == ["customers.unique.csv", "orders.sample.csv"]
    assert plan.excluded == ()
    names = {item.source.name: item.names for item in plan.eligible}
    assert names["customers.unique.csv"]["unique"].name == "customers.unique.unique.csv"
    assert names["customers.unique.csv"]["report"].name == "customers.unique.dedup.json"


@pytest.mark.dedup_lot("1")
@pytest.mark.dedup_t("T24")
def test_a_source_found_by_several_specs_is_planned_once(tmp_path):
    write_csv(tmp_path, "customers.csv", ROWS)
    write_csv(tmp_path, "orders.csv", ROWS)
    plan = _plan(
        [tmp_path / "*.csv", tmp_path / "c*.csv", tmp_path / "customers.csv"]
    )
    assert _eligible(plan) == ["customers.csv", "orders.csv"]


@pytest.mark.dedup_lot("1")
@pytest.mark.dedup_t("T24")
def test_the_planned_outputs_follow_the_stem_beside_the_source_or_in_the_output_dir(
    tmp_path,
):
    write_csv(tmp_path, "customers.csv", ROWS)
    beside = _plan([tmp_path / "customers.csv"]).eligible[0].names
    assert {key: path.parent for key, path in beside.items()} == {
        key: tmp_path for key in ("unique", "duplicates", "duplicates_all", "report")
    }
    assert beside["duplicates_all"].name == "customers.duplicates_all.csv"
    destination = tmp_path / "out"
    moved = _plan([tmp_path / "customers.csv"], output_dir=destination).eligible[0].names
    assert {path.parent for path in moved.values()} == {destination}


@pytest.mark.dedup_lot("1")
@pytest.mark.dedup_t("T11")
def test_a_wildcard_in_the_directory_part_skips_the_output_directory(tmp_path):
    data = tmp_path / "data"
    out = tmp_path / "out"
    data.mkdir()
    out.mkdir()
    write_csv(data, "y.csv", ROWS)
    write_csv(out, "x.csv", ROWS)
    skipped = _plan([str(tmp_path / "*" / "*.csv")], output_dir=out)
    assert _eligible(skipped) == ["y.csv"]
    assert _excluded(skipped) == {"x.csv": "output_directory"}
    named = _plan([out / "*.csv"], output_dir=out)
    assert _eligible(named) == ["x.csv"]


@pytest.mark.dedup_lot("1")
@pytest.mark.dedup_t("T26")
def test_an_output_that_would_replace_a_source_is_refused_even_with_force(tmp_path):
    from tabalyst.errors import InputError

    write_csv(tmp_path, "a.csv", ROWS)
    write_csv(tmp_path, "a.unique.csv", ROWS)
    specs = [tmp_path / "a.csv", tmp_path / "a.unique.csv"]
    with pytest.raises(InputError):
        _plan(specs)
    with pytest.raises(InputError):
        _plan(specs, force=True)


@pytest.mark.dedup_lot("1")
@pytest.mark.dedup_t("T26")
def test_two_sources_with_one_stem_in_one_destination_are_refused(tmp_path):
    from tabalyst.errors import ReportError

    write_csv(tmp_path, "data.csv", ROWS)
    write_csv(tmp_path, "data.tsv", ROWS, delimiter="\t")
    with pytest.raises(ReportError):
        _plan([tmp_path / "data.csv", tmp_path / "data.tsv"])
    first = tmp_path / "one"
    second = tmp_path / "two"
    first.mkdir()
    second.mkdir()
    write_csv(first, "same.csv", ROWS)
    write_csv(second, "same.csv", ROWS)
    with pytest.raises(ReportError):
        _plan([first / "same.csv", second / "same.csv"], output_dir=tmp_path / "out")


@pytest.mark.dedup_lot("1")
@pytest.mark.dedup_t("T26")
def test_an_existing_file_under_a_managed_name_is_refused_unless_forced(tmp_path):
    from tabalyst.errors import ReportError

    write_csv(tmp_path, "customers.csv", ROWS)
    stranger = tmp_path / "customers.duplicates_all.csv"
    stranger.write_text("mine\n", encoding="utf-8")
    with pytest.raises(ReportError):
        _plan([tmp_path / "customers.csv"])
    plan = _plan([tmp_path / "customers.csv"], force=True)
    assert _eligible(plan) == ["customers.csv"]
    assert stranger.read_text(encoding="utf-8") == "mine\n"


@pytest.mark.dedup_lot("1")
@pytest.mark.dedup_t("T26")
def test_a_directory_under_a_managed_name_is_refused_even_with_force(tmp_path):
    from tabalyst.errors import InputError

    write_csv(tmp_path, "customers.csv", ROWS)
    (tmp_path / "customers.dedup.json").mkdir()
    with pytest.raises(InputError):
        _plan([tmp_path / "customers.csv"], force=True)


@pytest.mark.dedup_lot("1")
@pytest.mark.dedup_t("T28")
def test_a_path_with_spaces_and_a_quoted_pattern_are_expanded_by_tabalyst(tmp_path):
    folder = tmp_path / "my data"
    folder.mkdir()
    write_csv(folder, "sales 2026.csv", ROWS)
    write_csv(folder, "sales 2026.unique.csv", ROWS)
    plan = _plan([str(folder) + "/*.csv"], owned=True)
    assert _eligible(plan) == ["sales 2026.csv"]
    assert plan.eligible[0].names["report"].name == "sales 2026.dedup.json"


@pytest.mark.dedup_lot("9")
@pytest.mark.dedup_t("T28")
def test_the_command_expands_a_quoted_pattern_with_spaces(tmp_path):
    from typer.testing import CliRunner

    from tabalyst.cli import app

    folder = tmp_path / "my data"
    folder.mkdir()
    write_csv(folder, "sales 2026.csv", ROWS)
    result = CliRunner().invoke(app, ["dedup", str(folder / "*.csv")])
    assert result.exit_code == 0, result.output
    assert (folder / "sales 2026.dedup.json").exists()
    assert (folder / "sales 2026.unique.csv").exists()

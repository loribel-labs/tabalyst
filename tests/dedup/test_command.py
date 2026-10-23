# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The command ``tabalyst dedup``: options, summaries, progress and exit codes (design dedup 13)."""

import dataclasses
import textwrap
from pathlib import Path

import pytest
from dedup_helpers import assert_published, write_csv
from typer.testing import CliRunner

from tabalyst import dedup_service
from tabalyst.cli import app
from tabalyst.cli import dedup as cli_dedup
from tabalyst.errors import InputError, ReportError

pytestmark = pytest.mark.dedup_lot("9")

runner = CliRunner()

TRIPLES = [("1", "a"), ("2", "b"), ("1", "a"), ("3", "c"), ("1", "a"), ("2", "b")]
PAIRS = [("1", "a"), ("2", "b"), ("1", "a"), ("2", "b"), ("3", "c")]
DISTINCT = [("1", "a"), ("2", "b"), ("3", "c")]
SECRET = "cell-secret-xyz"


def _dedup(*arguments):
    return runner.invoke(app, ["dedup", *map(str, arguments)])


def _bad_csv(folder: Path, name: str = "broken.csv") -> Path:
    path = folder / name
    path.write_text(f"id,name\r\n1,{SECRET}\r\n2\r\n", encoding="utf-8", newline="")
    return path


@pytest.fixture
def folder(tmp_path, monkeypatch):
    """Three sources, with the working folder set so that paths print relative."""
    write_csv(tmp_path, "a.csv", TRIPLES)
    write_csv(tmp_path, "b.csv", PAIRS)
    write_csv(tmp_path, "c.csv", DISTINCT)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _spec(text: str) -> str:
    return textwrap.dedent(text).strip("\n")


def _with_counts(result, total: int, extra: int):
    records = result.report.records.model_copy(
        update={"total": total, "extra_copies": extra}
    )
    return dataclasses.replace(
        result, report=result.report.model_copy(update={"records": records})
    )


# ---------------------------------------------------- the two validated shapes


def test_the_batch_summary_is_the_validated_example(folder, monkeypatch):
    for name in ("a.csv", "b.csv", "c.csv"):
        (folder / name).unlink()
    write_csv(folder, "customers.csv", DISTINCT)
    write_csv(folder, "products.csv", PAIRS)
    write_csv(folder, "orders.csv", TRIPLES)
    assert _dedup("customers.csv", "products.csv").exit_code == 0
    real = dedup_service.execute_dedups

    def staged(inputs, settings, *, on_progress=None):
        batch = real(inputs, settings, on_progress=on_progress)
        by_name = {item.source.name: item for item in batch.results}
        results = (
            _with_counts(by_name["customers.csv"], 100_000, 0),
            _with_counts(by_name["products.csv"], 45_000, 120),
            _with_counts(by_name["orders.csv"], 250_000, 1_250),
        )
        return dataclasses.replace(batch, results=results)

    monkeypatch.setattr(cli_dedup, "execute_dedups", staged)

    result = _dedup("customers.csv", "products.csv", "orders.csv")

    assert result.exit_code == 0, result.stderr
    assert result.stdout.rstrip("\n") == _spec(
        """
        Tabalyst Dedup
        ---------------------------------------------------------------
        File              Status    Rows       Extra copies  Outputs
        ---------------------------------------------------------------
        customers.csv     SKIPPED   100,000    0             0 new
        products.csv      SKIPPED    45,000    120           0 new
        orders.csv        DONE      250,000    1,250         3
        ---------------------------------------------------------------
        Eligible files:       3
        Processed:            1
        Already processed:    2
        Failed:               0
        New CSV files:        3
        JSON reports:         3 available (1 updated)
        Batch report:         dedup.summary.json
        Result:               COMPLETE
        """
    )


def test_the_single_file_summary_is_the_validated_example(folder):
    write_csv(folder, "customers.csv", ((str(n), f"name {n}") for n in range(100_000)))

    result = _dedup("customers.csv")

    assert result.exit_code == 0, result.stderr
    assert result.stdout.rstrip("\n") == _spec(
        """
        Tabalyst Dedup
        ---------------------------------------------------------------
        File:         customers.csv
        Source rows:  100,000
        Distinct:     100,000
        Groups:       0
        Extra copies: 0

        No duplicate records found.
        No CSV files generated.
        Report: customers.dedup.json
        Status: COMPLETE
        """
    )
    assert not (folder / "customers.unique.csv").exists()


def test_a_single_file_with_duplicates_lists_its_files(folder):
    result = _dedup("a.csv")

    assert result.exit_code == 0, result.stderr
    assert "Duplicate records found.\nCSV files generated:\n" in result.stdout
    for name in ("a.unique.csv", "a.duplicates.csv", "a.duplicates_all.csv"):
        assert f"\n  {name}\n" in result.stdout
    assert "Report: a.dedup.json\nStatus: COMPLETE" in result.stdout
    assert_published(folder, "a", TRIPLES)


def test_a_skipped_source_says_how_it_was_verified(folder):
    assert _dedup("a.csv").exit_code == 0

    again = _dedup("a.csv")
    digest = _dedup("a.csv", "--verify-content")

    assert again.exit_code == 0
    assert "Already processed, verified by metadata." in again.stdout
    assert "No CSV files generated." in again.stdout
    assert "Already processed, verified by digest." in digest.stdout


def test_a_pattern_prints_the_table_even_for_one_source(folder):
    result = _dedup("a.*")

    assert result.exit_code == 0, result.stderr
    assert "File              Status    Rows       Extra copies  Outputs" in result.stdout
    assert "a.csv             DONE            6    3             3\n" in result.stdout
    assert (folder / "dedup.summary.json").exists()


def test_excluded_files_are_counted_and_listed_only_with_verbose(folder):
    assert _dedup("a.csv").exit_code == 0

    plain = _dedup("*.csv")
    verbose = _dedup("*.csv", "--verbose")

    assert "Excluded:             3" in plain.stdout
    assert "a.unique.csv" not in plain.stdout
    assert "  a.unique.csv: excluded (derived_csv)" in verbose.stdout
    assert "  a.csv: already processed, verified by metadata" in verbose.stdout


def test_a_folder_of_derived_files_only_is_not_an_error(folder):
    for name in ("a.csv", "b.csv", "c.csv"):
        (folder / name).unlink()
    write_csv(folder, "x.unique.csv", DISTINCT)

    result = _dedup("*.csv")

    assert result.exit_code == 0, result.stderr
    assert "No file to process." in result.stdout
    assert "Eligible files:       0" in result.stdout
    assert "Result:               COMPLETE" in result.stdout


# ------------------------------------------------------- output and progress


def test_the_result_is_on_stdout_and_nothing_on_stderr_outside_a_terminal(folder):
    result = _dedup("*.csv")

    assert result.exit_code == 0
    assert "Tabalyst Dedup" in result.stdout
    assert result.stderr == ""
    assert "\r" not in result.stdout


def test_a_terminal_shows_the_progress_on_stderr(folder, monkeypatch):
    monkeypatch.setattr(cli_dedup, "_is_terminal", lambda: True)

    result = _dedup("*.csv")

    assert result.exit_code == 0
    assert "[1/3] a.csv - Dedup : Complete (processed)" in result.stderr
    assert "[3/3] c.csv - Dedup : Complete (processed)" in result.stderr
    assert "[" not in result.stdout


def test_a_skipped_source_ends_its_progress_line_with_the_verification(folder, monkeypatch):
    assert _dedup("a.csv").exit_code == 0
    monkeypatch.setattr(cli_dedup, "_is_terminal", lambda: True)

    result = _dedup("a.csv")

    assert "Complete (already processed, verified by metadata)" in result.stderr


def test_no_progress_and_quiet_hide_the_progress_line(folder, monkeypatch):
    monkeypatch.setattr(cli_dedup, "_is_terminal", lambda: True)

    hidden = _dedup("a.csv", "--no-progress")
    (folder / "a.dedup.json").unlink()
    for name in ("unique", "duplicates", "duplicates_all"):
        (folder / f"a.{name}.csv").unlink()
    quiet = _dedup("a.csv", "--quiet")

    assert hidden.exit_code == quiet.exit_code == 0
    assert hidden.stderr == ""
    assert quiet.stderr == ""
    assert "Tabalyst Dedup" in hidden.stdout


def test_quiet_keeps_the_final_status_only(folder):
    single = _dedup("a.csv", "--quiet")
    batch = _dedup("*.csv", "--quiet")

    assert single.stdout == "Status: COMPLETE\n"
    assert batch.stdout == "Result:               COMPLETE\n"


def test_quiet_still_shows_the_errors(folder):
    _bad_csv(folder)

    result = _dedup("broken.csv", "--quiet")

    assert result.exit_code == 4
    assert result.stdout == "Status: FAILED\n"
    assert "Error [broken.csv]:" in result.stderr


def test_verbose_adds_the_measures_of_a_single_file(folder):
    result = _dedup("a.csv", "--verbose")

    assert result.exit_code == 0
    for label in ("Storage:      memory", "Passes:       2", "First pass:", "Second pass:"):
        assert label in result.stdout
    assert "Memory peak:  " in result.stdout
    assert "MiB" in result.stdout
    plain = _dedup("a.csv", "--force")
    assert "Storage:" not in plain.stdout


def test_verbose_adds_the_measures_of_each_source_of_a_batch(folder):
    result = _dedup("*.csv", "--verbose")

    assert result.exit_code == 0
    assert "\nDetails\n  a.csv: storage memory, 2 passes, first pass " in result.stdout
    assert "memory peak " in result.stdout
    assert "\nDuration: " in result.stdout


# ---------------------------------------------------------- quoted patterns


def test_a_quoted_pattern_in_a_folder_with_spaces_is_expanded_by_the_command(
    tmp_path, monkeypatch
):
    spaced = tmp_path / "my data"
    spaced.mkdir()
    write_csv(spaced, "sales 2026.csv", TRIPLES)
    write_csv(spaced, "sales 2027.csv", PAIRS)
    monkeypatch.chdir(tmp_path)

    result = _dedup("my data/sales *.csv")

    assert result.exit_code == 0, result.stderr
    assert (spaced / "sales 2026.dedup.json").exists()
    assert (spaced / "sales 2027.unique.csv").exists()
    assert "sales 2026.csv" in result.stdout
    assert (spaced / "dedup.summary.json").exists()


# ------------------------------------------------------------- exit codes


def test_exit_0_when_nothing_failed_even_with_skipped_and_excluded_files(folder):
    assert _dedup("a.csv").exit_code == 0

    assert _dedup("*.csv").exit_code == 0


def test_exit_2_for_invalid_options_and_configuration(folder):
    cases = [
        ("a.csv", "--quiet", "--verbose"),
        ("a.csv", "--force", "--verify-content"),
        ("a.csv", "--max-rows", "0"),
        ("a.csv", "--memory-budget-mb", "0"),
        ("a.csv", "--delimiter", ";;"),
        ("**/*.csv",),
        ("a.csv", "--no-such-option"),
    ]
    for arguments in cases:
        result = _dedup(*arguments)
        assert result.exit_code == 2, (arguments, result.stderr)
    assert not (folder / "a.dedup.json").exists()


def test_an_option_that_would_be_ignored_is_an_error(folder):
    result = _dedup("a.csv", "--quiet", "--no-progress")

    assert result.exit_code == 2
    assert "--no-progress" in result.stderr
    assert not (folder / "a.dedup.json").exists()


def test_exit_4_for_a_missing_source_and_for_a_pattern_without_match(folder):
    assert _dedup("missing.csv").exit_code == 4
    assert _dedup("nothing-*.csv").exit_code == 4


def test_exit_4_when_every_failure_is_an_input_error(folder):
    _bad_csv(folder)

    result = _dedup("a.csv", "broken.csv")

    assert result.exit_code == 4
    assert_published(folder, "a", TRIPLES)


def test_exit_4_for_the_row_limit(folder):
    result = _dedup("a.csv", "--max-rows", "3")

    assert result.exit_code == 4
    assert "The file has more than 3 data records." in result.stderr
    assert "(row_limit_exceeded)" in result.stderr


def test_exit_4_when_an_output_would_replace_a_source(folder):
    write_csv(folder, "a.duplicates.csv", TRIPLES)

    result = _dedup("a.csv", "a.duplicates.csv", "--force")

    assert result.exit_code == 4
    assert not (folder / "a.dedup.json").exists()


def test_exit_1_for_a_foreign_output_and_nothing_is_written(folder):
    (folder / "b.unique.csv").write_text("mine\n", encoding="utf-8")

    result = _dedup("a.csv", "b.csv")

    assert result.exit_code == 1
    assert result.stderr.startswith("Error: ")
    assert not (folder / "a.dedup.json").exists()
    assert (folder / "b.unique.csv").read_text(encoding="utf-8") == "mine\n"


def test_exit_1_for_a_failure_that_is_not_an_input_error(folder, monkeypatch):
    real = dedup_service.process_source

    def broken(source, settings, **options):
        if Path(source).name == "b.csv":
            raise RuntimeError(SECRET)
        return real(source, settings, **options)

    monkeypatch.setattr(dedup_service, "process_source", broken)

    result = _dedup("a.csv", "b.csv", "c.csv")

    assert result.exit_code == 1
    assert "Error [b.csv]: An unexpected error stopped the run. (unexpected_error)" in result.stderr
    assert SECRET not in result.stdout + result.stderr
    assert_published(folder, "a", TRIPLES)
    assert (folder / "c.dedup.json").exists()


def test_exit_1_wins_over_4_when_the_failures_are_mixed(folder, monkeypatch):
    _bad_csv(folder)
    real = dedup_service.process_source

    def broken(source, settings, **options):
        if Path(source).name == "b.csv":
            raise RuntimeError("boom")
        return real(source, settings, **options)

    monkeypatch.setattr(dedup_service, "process_source", broken)

    assert _dedup("broken.csv", "b.csv").exit_code == 1


@pytest.mark.parametrize(
    ("raised", "code"),
    [(InputError("An output is a source"), 4), (ReportError("A foreign output"), 1)],
)
def test_a_source_refused_at_run_time_keeps_the_exit_code_of_its_refusal(
    folder, monkeypatch, raised, code
):
    real = dedup_service.process_source

    def refusing(source, settings, **options):
        if Path(source).name == "a.csv":
            raise raised
        return real(source, settings, **options)

    monkeypatch.setattr(dedup_service, "process_source", refusing)

    result = _dedup("a.csv", "b.csv")

    assert result.exit_code == code
    assert "Error [a.csv]:" in result.stderr
    assert "(output_refused)" in result.stderr
    assert (folder / "b.dedup.json").exists()


def test_exit_1_when_the_batch_report_cannot_be_written(folder, monkeypatch):
    def refuse(path, report):
        raise OSError("disk full")

    monkeypatch.setattr(dedup_service, "write_batch_report", refuse)

    result = _dedup("*.csv")

    assert result.exit_code == 1
    assert "Batch report:         not written" in result.stdout
    assert "The batch report cannot be written." in result.stderr
    assert_published(folder, "a", TRIPLES)


def test_the_command_never_asks_a_question(folder):
    result = runner.invoke(app, ["dedup", "*.csv"], input="")

    assert result.exit_code == 0
    assert "?" not in result.stdout + result.stderr
    assert "[y/N]" not in result.stdout + result.stderr


# ------------------------------------------------- a failure among several


def test_one_failure_among_several_is_shown_and_the_others_go_on(folder):
    _bad_csv(folder)

    result = _dedup("*.csv")

    assert result.exit_code == 4
    assert "broken.csv        FAILED          -    -             -\n" in result.stdout
    assert "Failed:               1" in result.stdout
    assert "Result:               PARTIAL" in result.stdout
    assert "Error [broken.csv]: Data record 2" in result.stderr
    assert "(invalid_csv)" in result.stderr
    assert_published(folder, "a", TRIPLES)
    assert_published(folder, "b", PAIRS)
    assert (folder / "broken.dedup.json").exists()


def test_a_batch_where_every_source_fails_has_the_result_failed(folder):
    _bad_csv(folder, "one.csv")
    _bad_csv(folder, "two.csv")

    result = _dedup("one.csv", "two.csv")

    assert result.exit_code == 4
    assert "Result:               FAILED" in result.stdout


def test_a_failed_single_file_prints_its_status_and_report(folder):
    _bad_csv(folder)

    result = _dedup("broken.csv")

    assert result.exit_code == 4
    assert "Failed: invalid_csv. No CSV files generated." in result.stdout
    assert "Report: broken.dedup.json\nStatus: FAILED" in result.stdout


def test_two_sources_with_one_name_are_told_apart_by_their_folder(folder):
    other = folder / "other"
    other.mkdir()
    write_csv(other, "a.csv", PAIRS)

    result = _dedup("a.csv", "other/a.csv")

    assert result.exit_code == 0, result.stderr
    table = result.stdout.split("Eligible")[0]
    assert "\na.csv " in table
    assert str(Path("other") / "a.csv") in table


# ---------------------------------------------------------- no cell content


def test_no_message_holds_a_cell(folder, monkeypatch):
    write_csv(folder, "secret.csv", [(SECRET, SECRET), (SECRET, SECRET), ("1", "x")])
    _bad_csv(folder)

    for arguments in (
        ("secret.csv",),
        ("secret.csv", "--verbose"),
        ("*.csv",),
        ("*.csv", "--verbose"),
        ("broken.csv",),
        ("secret.csv", "--max-rows", "1"),
    ):
        result = _dedup(*arguments)
        assert SECRET not in result.stdout + result.stderr, arguments


# -------------------------------------------------------------------- help


def test_help_describes_every_option_and_the_exit_codes():
    result = _dedup("--help")

    assert result.exit_code == 0
    text = " ".join(result.stdout.split())
    for option in (
        "--output-dir",
        "--config",
        "--max-rows",
        "--delimiter",
        "--encoding",
        "--memory-budget-mb",
        "--temp-dir",
        "--force",
        "--verify-content",
        "--quiet",
        "--verbose",
        "--no-progress",
    ):
        assert option in text
    for phrase in (
        "unique.csv",
        "duplicates.csv",
        "duplicates_all.csv",
        "dedup.json",
        "dedup.summary.json",
        "Exit codes",
        "Quote a pattern",
    ):
        assert phrase in text
    assert "--output " not in text


def test_the_command_is_listed_in_the_application_help():
    result = runner.invoke(app, ["--help"])

    assert "dedup" in result.stdout

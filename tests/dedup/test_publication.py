# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Publication, recovery and deletion of the obsolete outputs (design 11.5, ADR ownership)."""

import json
import os
from pathlib import Path

import pytest
from dedup_helpers import (
    assert_published,
    load_report,
    no_temporary_files,
    output_names,
    run,
    validate_report,
    write_csv,
)

from tabalyst.dedup import cache, pipeline
from tabalyst.dedup.discovery import managed_names
from tabalyst.dedup.report import write_report as real_write_report

pytestmark = pytest.mark.dedup_lot("7")

TRIPLES = [("1", "a"), ("2", "b"), ("1", "a"), ("3", "c"), ("1", "a"), ("2", "b")]
PAIRS = [("1", "a"), ("2", "b"), ("1", "a"), ("2", "b"), ("3", "c")]
DISTINCT = [("1", "a"), ("2", "b"), ("3", "c")]
BROKEN = b"id,name\r\n1,a\r\n2\r\n"


class Crash(BaseException):
    """An interruption that no handler of the engine may swallow."""


def _report_writes(monkeypatch):
    """Record the status of every report the pipeline writes, and the documents."""
    seen = []

    def spy(path, report):
        seen.append(report)
        real_write_report(path, report)

    monkeypatch.setattr(pipeline, "write_report", spy)
    return seen


def _bytes_of(directory: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}


def _crash_at_replace(monkeypatch, target: int):
    """Raise ``Crash`` at the ``target``-th ``os.replace``; return a restorer and the count."""
    real = os.replace
    calls = {"n": 0}

    def flaky(src, dst, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == target:
            raise Crash
        return real(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "replace", flaky)
    return lambda: monkeypatch.setattr(os, "replace", real), calls


def _crash_at_delete(monkeypatch, target: int):
    """Raise ``Crash`` at the ``target``-th deletion of a published CSV."""
    real = Path.unlink
    calls = {"n": 0}

    def flaky(self, *args, **kwargs):
        if self.suffix == ".csv" and not self.name.startswith("."):
            calls["n"] += 1
            if calls["n"] == target:
                raise Crash
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", flaky)
    return lambda: monkeypatch.setattr(Path, "unlink", real), calls


# ----------------------------------------------------------- the recovery report


def test_the_recovery_report_names_the_previous_and_the_planned_outputs(
    tmp_path, monkeypatch
):
    source = write_csv(tmp_path, "customers.csv", TRIPLES)
    run(source)
    old = load_report(tmp_path, "customers")["outputs"]
    write_csv(tmp_path, "customers.csv", PAIRS)
    seen = _report_writes(monkeypatch)

    run(source)

    recovery, final = seen
    assert recovery.status == "in_progress" and final.status == "complete"
    previous = {entry.file: entry for entry in recovery.recovery.previous_outputs}
    planned = {entry.file: entry for entry in recovery.recovery.planned_outputs}
    assert set(previous) == {item["file"] for item in old.values() if isinstance(item, dict)}
    assert previous["customers.unique.csv"].sha256 == old["unique"]["sha256"]
    assert set(planned) == {"customers.unique.csv", "customers.duplicates.csv"}
    now = load_report(tmp_path, "customers")["outputs"]
    assert planned["customers.unique.csv"].sha256 == now["unique"]["sha256"]
    assert planned["customers.unique.csv"].size_bytes == now["unique"]["size_bytes"]
    assert recovery.source.content_sha256 == final.source.content_sha256
    assert recovery.settings == final.settings


def test_a_first_run_also_writes_a_recovery_report_before_its_first_csv(
    tmp_path, monkeypatch
):
    source = write_csv(tmp_path, "customers.csv", TRIPLES)
    seen = _report_writes(monkeypatch)

    run(source)

    recovery = seen[0]
    assert recovery.status == "in_progress"
    assert recovery.recovery.previous_outputs == []
    assert len(recovery.recovery.planned_outputs) == 3


def test_a_source_with_nothing_to_protect_writes_only_the_complete_report(
    tmp_path, monkeypatch
):
    source = write_csv(tmp_path, "clean.csv", DISTINCT)
    seen = _report_writes(monkeypatch)

    run(source)

    assert [report.status for report in seen] == ["complete"]


def test_a_report_of_a_clean_source_that_had_duplicates_goes_through_the_recovery_report(
    tmp_path, monkeypatch
):
    source = write_csv(tmp_path, "customers.csv", TRIPLES)
    run(source)
    write_csv(tmp_path, "customers.csv", DISTINCT)
    seen = _report_writes(monkeypatch)

    run(source)

    assert [report.status for report in seen] == ["in_progress", "complete"]
    assert seen[0].recovery.planned_outputs == []
    assert len(seen[0].recovery.previous_outputs) == 3


def test_the_recovery_report_is_a_valid_document_of_the_schema(tmp_path, monkeypatch):
    source = write_csv(tmp_path, "customers.csv", TRIPLES)
    seen = _report_writes(monkeypatch)
    run(source)

    from tabalyst.dedup.report import report_json

    validate_report(json.loads(report_json(seen[0])))


# ------------------------------------------------------------ obsolete outputs


def test_a_rerun_deletes_the_duplicates_all_that_the_new_set_no_longer_holds(tmp_path):
    source = write_csv(tmp_path, "customers.csv", TRIPLES)
    run(source)
    assert (tmp_path / "customers.duplicates_all.csv").exists()
    write_csv(tmp_path, "customers.csv", PAIRS)

    run(source)

    assert not (tmp_path / "customers.duplicates_all.csv").exists()
    assert_published(tmp_path, "customers", PAIRS)
    assert load_report(tmp_path, "customers")["outputs"]["duplicates_all"] is None


def test_a_rerun_in_another_destination_leaves_the_first_destination_alone(tmp_path):
    source = write_csv(tmp_path, "customers.csv", TRIPLES)
    run(source)
    before = _bytes_of(tmp_path)

    outcome = run(source, tmp_path / "elsewhere")

    assert outcome.status == "DONE"
    assert {k: v for k, v in _bytes_of(tmp_path).items()} == before


def test_the_outputs_of_another_source_are_never_deleted(tmp_path):
    first = write_csv(tmp_path, "a.csv", TRIPLES)
    second = write_csv(tmp_path, "b.csv", TRIPLES)
    run(first)
    run(second)
    write_csv(tmp_path, "b.csv", DISTINCT)

    run(second)

    assert_published(tmp_path, "a", TRIPLES)
    assert_published(tmp_path, "b", DISTINCT)


# ---------------------------------------------------------------- failures (D2)


def test_a_failure_with_nothing_published_before_writes_only_a_failed_report(tmp_path):
    source = tmp_path / "bad.csv"
    source.write_bytes(BROKEN)

    outcome = run(source)

    assert outcome.status == "FAILED" and outcome.report_path is not None
    assert sorted(p.name for p in tmp_path.iterdir()) == ["bad.csv", "bad.dedup.json"]
    assert load_report(tmp_path, "bad")["status"] == "failed"


def test_a_failure_goes_through_the_recovery_report_when_outputs_are_retired(
    tmp_path, monkeypatch
):
    source = write_csv(tmp_path, "customers.csv", TRIPLES)
    run(source)
    source.write_bytes(BROKEN)
    seen = _report_writes(monkeypatch)

    outcome = run(source)

    assert [report.status for report in seen] == ["in_progress", "failed"]
    assert seen[0].recovery.planned_outputs == []
    assert len(seen[0].recovery.previous_outputs) == 3
    assert outcome.report == seen[1]
    for name in output_names("customers").values():
        assert not (tmp_path / name).exists()


def test_a_failure_after_a_crashed_run_does_not_write_a_second_recovery_report(
    tmp_path, monkeypatch
):
    source = write_csv(tmp_path, "customers.csv", TRIPLES)
    run(source)
    write_csv(tmp_path, "customers.csv", PAIRS)
    restore, _ = _crash_at_replace(monkeypatch, 2)
    with pytest.raises(Crash):
        run(source)
    restore()
    source.write_bytes(BROKEN)
    seen = _report_writes(monkeypatch)

    run(source)

    assert [report.status for report in seen] == ["failed"]
    for name in output_names("customers").values():
        assert not (tmp_path / name).exists()
    assert no_temporary_files(tmp_path)


def test_a_failure_deletes_only_the_owned_outputs(tmp_path):
    source = write_csv(tmp_path, "customers.csv", TRIPLES)
    run(source)
    edited = tmp_path / "customers.unique.csv"
    edited.write_bytes(edited.read_bytes() + b"x")
    source.write_bytes(BROKEN)

    outcome = run(source, force=True)

    assert outcome.status == "FAILED"
    assert edited.exists()
    assert not (tmp_path / "customers.duplicates.csv").exists()
    assert not (tmp_path / "customers.duplicates_all.csv").exists()
    assert load_report(tmp_path, "customers")["status"] == "failed"


def test_a_failure_that_cannot_delete_an_output_keeps_the_recovery_report(
    tmp_path, monkeypatch
):
    source = write_csv(tmp_path, "customers.csv", TRIPLES)
    run(source)
    source.write_bytes(BROKEN)
    real = Path.unlink

    def locked(self, *args, **kwargs):
        if self.name == "customers.duplicates.csv":
            raise PermissionError("locked")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", locked)

    outcome = run(source)

    monkeypatch.setattr(Path, "unlink", real)
    assert outcome.status == "FAILED" and outcome.reason == "invalid_csv"
    assert outcome.report is None and outcome.report_path is None
    assert load_report(tmp_path, "customers")["status"] == "in_progress"
    assert (tmp_path / "customers.duplicates.csv").exists()
    # the stuck file stays provable: the next run repairs the state
    write_csv(tmp_path, "customers.csv", PAIRS)
    assert run(source).status == "DONE"
    assert_published(tmp_path, "customers", PAIRS)


def test_a_failure_that_cannot_write_the_recovery_report_leaves_the_old_result(
    tmp_path, monkeypatch
):
    source = write_csv(tmp_path, "customers.csv", TRIPLES)
    run(source)
    source.write_bytes(BROKEN)
    before = _bytes_of(tmp_path)

    def refuse(path, report):
        raise PermissionError("denied")

    monkeypatch.setattr(pipeline, "write_report", refuse)

    outcome = run(source)

    assert outcome.status == "FAILED" and outcome.report is None
    assert _bytes_of(tmp_path) == before


# ----------------------------------------------------- publication that fails


def test_a_recovery_report_that_cannot_be_written_leaves_the_old_result(
    tmp_path, monkeypatch
):
    source = write_csv(tmp_path, "customers.csv", TRIPLES)
    run(source)
    write_csv(tmp_path, "customers.csv", PAIRS)
    before = {k: v for k, v in _bytes_of(tmp_path).items() if k != "customers.csv"}

    def refuse(path, report):
        raise PermissionError("denied")

    monkeypatch.setattr(pipeline, "write_report", refuse)
    outcome = run(source)
    monkeypatch.undo()

    assert outcome.status == "FAILED" and outcome.reason == "output_unwritable"
    assert {k: v for k, v in _bytes_of(tmp_path).items() if k != "customers.csv"} == before
    assert no_temporary_files(tmp_path)
    assert run(source).status == "DONE"


def test_an_obsolete_output_that_cannot_be_deleted_fails_the_source_and_stays_provable(
    tmp_path, monkeypatch
):
    source = write_csv(tmp_path, "customers.csv", TRIPLES)
    run(source)
    write_csv(tmp_path, "customers.csv", PAIRS)
    real = Path.unlink

    def locked(self, *args, **kwargs):
        if self.name == "customers.duplicates_all.csv":
            raise PermissionError("locked")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", locked)

    outcome = run(source)

    monkeypatch.setattr(Path, "unlink", real)
    assert outcome.status == "FAILED" and outcome.reason == "output_unwritable"
    assert load_report(tmp_path, "customers")["status"] == "in_progress"
    assert run(source).status == "DONE"
    assert_published(tmp_path, "customers", PAIRS)


# ---------------------------------------------------------------- interruptions


@pytest.mark.parametrize("target", [1, 2, 3, 4, 5])
def test_an_interrupted_first_run_is_repaired_by_the_next_without_force(
    tmp_path, monkeypatch, target
):
    source = write_csv(tmp_path, "customers.csv", TRIPLES)
    restore, calls = _crash_at_replace(monkeypatch, target)
    crashed = False
    try:
        run(source)
    except Crash:
        crashed = True
    restore()

    outcome = run(source)  # never needs --force: the recovery report proves the files

    assert crashed == (target <= calls["n"])
    assert outcome.status == ("DONE" if crashed else "SKIPPED")
    assert_published(tmp_path, "customers", TRIPLES)
    assert load_report(tmp_path, "customers")["status"] == "complete"
    assert no_temporary_files(tmp_path)


@pytest.mark.parametrize("target", [1, 2])
def test_an_interrupted_deletion_of_obsolete_outputs_is_repaired(
    tmp_path, monkeypatch, target
):
    source = write_csv(tmp_path, "customers.csv", TRIPLES)
    run(source)
    write_csv(tmp_path, "customers.csv", DISTINCT)  # all three CSV become obsolete
    restore, _ = _crash_at_delete(monkeypatch, target)
    crashed = False
    try:
        run(source)
    except Crash:
        crashed = True
    restore()

    outcome = run(source)

    assert crashed
    assert outcome.status == "DONE"
    for name in output_names("customers").values():
        assert not (tmp_path / name).exists()
    assert load_report(tmp_path, "customers")["status"] == "complete"
    assert no_temporary_files(tmp_path)


@pytest.mark.parametrize("target", [1, 2, 3])
def test_an_interrupted_retirement_after_a_failure_is_repaired(tmp_path, monkeypatch, target):
    source = write_csv(tmp_path, "customers.csv", TRIPLES)
    run(source)
    source.write_bytes(BROKEN)
    restore, _ = _crash_at_delete(monkeypatch, target)
    with pytest.raises(Crash):
        run(source)
    restore()
    assert load_report(tmp_path, "customers")["status"] == "in_progress"

    write_csv(tmp_path, "customers.csv", PAIRS)
    outcome = run(source)

    assert outcome.status == "DONE"
    assert_published(tmp_path, "customers", PAIRS)
    assert load_report(tmp_path, "customers")["status"] == "complete"


def test_a_complete_report_is_never_left_over_a_changed_set(tmp_path, monkeypatch):
    """After a crash at any step, a report on disk that says complete matches its files."""
    source = write_csv(tmp_path, "customers.csv", TRIPLES)
    run(source)
    write_csv(tmp_path, "customers.csv", PAIRS)
    attempt = 1
    while True:
        folder = tmp_path / f"copy-{attempt}"
        folder.mkdir()
        for path in tmp_path.iterdir():
            if path.is_file():
                (folder / path.name).write_bytes(path.read_bytes())
        copied = folder / "customers.csv"
        restore, _ = _crash_at_replace(monkeypatch, attempt)
        crashed = False
        try:
            run(copied)
        except Crash:
            crashed = True
        restore()
        document = load_report(folder, "customers")
        if document["status"] == "complete":
            for kind in ("unique", "duplicates", "duplicates_all"):
                item = document["outputs"][kind]
                assert (item is not None) == (folder / output_names("customers")[kind]).exists()
                if item is not None:
                    assert (folder / item["file"]).stat().st_size == item["size_bytes"]
        if not crashed:
            break
        attempt += 1
    assert attempt >= 4


# --------------------------------------------------------- foreign files kept


def test_a_forced_run_replaces_what_it_writes_and_the_report_then_owns_it(tmp_path):
    source = write_csv(tmp_path, "customers.csv", PAIRS)
    foreign = tmp_path / "customers.unique.csv"
    foreign.write_bytes(b"mine")
    outcome = run(source, force=True)

    assert outcome.status == "DONE"
    assert cache.assess(managed_names(source, tmp_path)).foreign == ()
    assert run(source).status == "SKIPPED"


# ------------------------------------------------------------ random histories


@pytest.mark.parametrize("seed", range(16))
def test_random_histories_always_end_in_a_coherent_complete_set(tmp_path, monkeypatch, seed):
    """Whatever mix of rewrites, hand deletions, crashes and failures, a plain run repairs.

    The rows differ in number from one content to the next, so every rewrite changes
    the size of the source and the metadata level cannot mistake it for the old one.
    """
    import random

    rng = random.Random(seed)
    contents = [TRIPLES, PAIRS, DISTINCT, [], TRIPLES[:4]]
    current = contents[0]
    source = write_csv(tmp_path, "customers.csv", current)
    names = [tmp_path / name for name in output_names("customers").values()]
    for _ in range(12):
        action = rng.choice(
            ["rewrite", "delete", "crash_replace", "crash_delete", "run", "break"]
        )
        if action == "rewrite":
            current = rng.choice(contents)
            write_csv(tmp_path, "customers.csv", current)
        elif action == "break":
            current = None
            source.write_bytes(BROKEN)
        elif action == "delete":
            existing = [path for path in names if path.exists()]
            if existing:
                rng.choice(existing).unlink()
        elif action.startswith("crash"):
            crash = _crash_at_replace if action == "crash_replace" else _crash_at_delete
            restore, _ = crash(monkeypatch, rng.randint(1, 5))
            try:
                run(source)
            except Crash:
                pass
            finally:
                restore()
        else:
            run(source)

        outcome = run(source)  # a plain run never needs --force after any of the above
        if current is None:
            assert outcome.status == "FAILED"
            assert not any(path.exists() for path in names)
            assert load_report(tmp_path, "customers")["status"] == "failed"
        else:
            assert outcome.status in {"DONE", "SKIPPED"}
            assert_published(tmp_path, "customers", current)
            assert load_report(tmp_path, "customers")["status"] == "complete"
        assert no_temporary_files(tmp_path)

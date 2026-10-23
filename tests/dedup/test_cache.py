# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Ownership of the managed names and the SKIPPED decision (design 7.4, 11.2, 11.3)."""

import json
import os
import shutil

import pytest
from dedup_helpers import (
    assert_published,
    load_report,
    output_names,
    read_csv,
    run,
    settings,
    write_csv,
)

from tabalyst.config import CsvConfig
from tabalyst.dedup import cache
from tabalyst.dedup.discovery import PlannedSource, managed_names, plan_batch
from tabalyst.dedup.report import (
    InProgressReport,
    InventoryEntry,
    recovery_report,
    write_report,
)
from tabalyst.errors import InputError, ReportError

pytestmark = pytest.mark.dedup_lot("7")

TRIPLES = [("1", "a"), ("2", "b"), ("1", "a"), ("3", "c"), ("1", "a"), ("2", "b")]
PAIRS = [("1", "a"), ("2", "b"), ("1", "a"), ("2", "b"), ("3", "c")]
DISTINCT = [("1", "a"), ("2", "b"), ("3", "c")]


@pytest.fixture
def source(tmp_path):
    return write_csv(tmp_path, "customers.csv", TRIPLES)


def _names(source):
    return managed_names(source, source.parent)


def _entry(document, kind):
    item = document["outputs"][kind]
    return InventoryEntry(
        file=item["file"], size_bytes=item["size_bytes"], sha256=item["sha256"]
    )


def _flip_last_byte(path):
    data = bytearray(path.read_bytes())
    data[-1] = data[-1] ^ 0x01
    path.write_bytes(bytes(data))


# ---------------------------------------------------------------- ownership


def test_a_name_that_no_report_vouches_for_is_foreign(source, tmp_path):
    stray = tmp_path / "customers.unique.csv"
    stray.write_text("id,name\r\n", encoding="utf-8")

    assessment = cache.assess(_names(source))

    assert assessment.foreign == (stray,)
    assert dict(assessment.owned) == {}
    assert assessment.report is None


def test_the_published_set_is_owned_through_its_report(source):
    run(source)

    assessment = cache.assess(_names(source))

    assert set(assessment.owned) == {"unique", "duplicates", "duplicates_all"}
    assert assessment.foreign == ()


def test_a_file_whose_size_changed_is_foreign(source, tmp_path):
    run(source)
    edited = tmp_path / "customers.duplicates.csv"
    edited.write_bytes(edited.read_bytes() + b"x")

    assessment = cache.assess(_names(source))

    assert assessment.foreign == (edited,)
    assert set(assessment.owned) == {"unique", "duplicates_all"}


def test_a_same_size_rewrite_is_owned_by_size_and_foreign_when_the_content_is_verified(
    source, tmp_path
):
    run(source)
    _flip_last_byte(tmp_path / "customers.unique.csv")

    by_size = cache.assess(_names(source))
    by_content = cache.assess(_names(source), verify_content=True)

    assert by_size.foreign == () and by_size.verified is False
    assert by_content.foreign == (tmp_path / "customers.unique.csv",)
    assert by_content.verified is True


@pytest.mark.parametrize(
    "content",
    ["{not json", "[]", '{"format": "something.else"}', "é"],
    ids=["broken", "array", "other-format", "not-utf8-json"],
)
def test_a_report_that_is_not_a_dedup_report_is_foreign(source, tmp_path, content):
    report = tmp_path / "customers.dedup.json"
    report.write_text(content, encoding="latin-1")

    assessment = cache.assess(_names(source))

    assert assessment.foreign == (report,)
    assert assessment.report is None


def test_a_report_of_another_revision_is_foreign(source, tmp_path):
    run(source)
    path = tmp_path / "customers.dedup.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["format_revision"] = 2
    path.write_text(json.dumps(document), encoding="utf-8")

    assert cache.assess(_names(source)).foreign[0] == path


def test_a_failed_report_vouches_for_no_csv(tmp_path):
    source = tmp_path / "bad.csv"
    source.write_text("id,name\r\n1\r\n", encoding="utf-8", newline="")
    assert run(source).status == "FAILED"
    stray = tmp_path / "bad.unique.csv"
    stray.write_text("id,name\r\n", encoding="utf-8")

    assessment = cache.assess(_names(source))

    assert assessment.report is not None and assessment.report.status == "failed"
    assert assessment.foreign == (stray,)


def test_a_recovery_report_vouches_for_both_of_its_inventories(source, tmp_path):
    run(source)
    document = load_report(tmp_path, "customers")
    names = _names(source)
    write_report(
        names["report"],
        recovery_report(
            "customers.csv",
            settings(),
            previous=[_entry(document, "unique")],
            planned=[_entry(document, "duplicates")],
        ),
    )

    assessment = cache.assess(names)

    assert set(assessment.owned) == {"unique", "duplicates"}
    assert assessment.foreign == (names["duplicates_all"],)


def test_the_file_names_of_an_inventory_are_never_used_as_paths(source, tmp_path):
    victim = tmp_path / "victim.csv"
    victim.write_bytes(b"precious")
    destination = tmp_path / "out"
    destination.mkdir()
    forged = InventoryEntry(
        file="../victim.csv", size_bytes=victim.stat().st_size, sha256="0" * 64
    )
    names = managed_names(source, destination)
    write_report(
        names["report"],
        recovery_report("customers.csv", settings(), previous=[forged], planned=[forged]),
    )

    assessment = cache.assess(names)
    outcome = run(source, destination)

    assert dict(assessment.owned) == {} and assessment.foreign == ()
    assert outcome.status == "DONE"
    assert victim.read_bytes() == b"precious"


def test_a_directory_under_a_managed_name_is_refused_even_with_force(source, tmp_path):
    (tmp_path / "customers.unique.csv").mkdir()

    with pytest.raises(InputError):
        run(source)
    with pytest.raises(InputError):
        run(source, force=True)

    assert not (tmp_path / "customers.dedup.json").exists()


def test_a_refused_run_writes_nothing_and_removes_nothing(source, tmp_path):
    stale = tmp_path / ".customers.unique.csv.abc123.tmp"
    stale.write_bytes(b"half")
    foreign = tmp_path / "customers.unique.csv"
    foreign.write_bytes(b"mine")

    with pytest.raises(ReportError):
        run(source)

    assert stale.exists()
    assert foreign.read_bytes() == b"mine"
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
        [stale.name, foreign.name, "customers.csv"]
    )


# --------------------------------------------------- is_owned for the planner


def _planned(source):
    return PlannedSource(source=source, names=_names(source))


def test_is_owned_accepts_the_outputs_a_report_proves(source):
    run(source)

    plan = plan_batch([str(source)], settings(), is_owned=cache.is_owned)

    assert [item.source for item in plan.eligible] == [source]


def test_is_owned_refuses_an_edited_output_and_force_allows_it(source, tmp_path):
    run(source)
    edited = tmp_path / "customers.unique.csv"
    edited.write_bytes(edited.read_bytes() + b"x")
    planned = _planned(source)

    assert cache.is_owned(tmp_path / "customers.duplicates.csv", planned) is True
    assert cache.is_owned(edited, planned) is False
    with pytest.raises(ReportError):
        plan_batch([str(source)], settings(), is_owned=cache.is_owned)
    assert plan_batch([str(source)], settings(force=True), is_owned=cache.is_owned)


def test_is_owned_is_false_for_a_name_that_does_not_exist(source, tmp_path):
    assert cache.is_owned(tmp_path / "customers.unique.csv", _planned(source)) is False


def test_is_owned_can_verify_the_content(source, tmp_path):
    run(source)
    _flip_last_byte(tmp_path / "customers.unique.csv")
    planned = _planned(source)

    assert cache.is_owned(tmp_path / "customers.unique.csv", planned) is True
    assert cache.is_owned(
        tmp_path / "customers.unique.csv", planned, verify_content=True
    ) is False


def test_a_planned_batch_accepts_the_results_of_an_interrupted_run(source, tmp_path):
    run(source)
    document = load_report(tmp_path, "customers")
    names = _names(source)
    write_report(
        names["report"],
        recovery_report(
            "customers.csv",
            settings(),
            previous=[_entry(document, kind) for kind in output_names("x")],
            planned=[],
        ),
    )

    assert plan_batch([str(source)], settings(), is_owned=cache.is_owned)


# --------------------------------------------------------- the decision, 11.2


def test_a_skipped_source_is_not_read_again_and_its_outcome_carries_the_report(
    source, tmp_path, monkeypatch
):
    run(source)
    report = tmp_path / "customers.dedup.json"
    before = (report.read_bytes(), report.stat().st_mtime_ns)

    def forbidden(*args, **kwargs):
        raise AssertionError("a skipped source is not analyzed")

    monkeypatch.setattr("tabalyst.dedup.pipeline.analyze_dedup", forbidden)
    monkeypatch.setattr(cache, "file_sha256", forbidden)
    outcome = run(source)

    assert outcome.status == "SKIPPED" and outcome.verification == "metadata"
    assert outcome.files == () and outcome.analysis is None and outcome.error is None
    assert outcome.report_path == report
    assert outcome.report.records.total == len(TRIPLES)
    assert (report.read_bytes(), report.stat().st_mtime_ns) == before


def test_a_different_size_reprocesses_without_hashing_the_source(source, tmp_path, monkeypatch):
    run(source)
    write_csv(tmp_path, "customers.csv", PAIRS)

    def forbidden(path, on_bytes=None):
        if path == source:
            raise AssertionError("the sizes differ: nothing to hash")
        return real(path, on_bytes)

    real = cache.file_sha256
    monkeypatch.setattr(cache, "file_sha256", forbidden)

    assert run(source).status == "DONE"


def test_a_rewrite_with_the_same_size_and_another_date_is_reprocessed(source, tmp_path):
    run(source)
    stat = source.stat()
    swapped = [("1", "a"), ("2", "b"), ("1", "a"), ("3", "c"), ("2", "b"), ("2", "b")]
    write_csv(tmp_path, "customers.csv", swapped)
    assert source.stat().st_size == stat.st_size
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 7_000_000_000))

    outcome = run(source)

    assert outcome.status == "DONE"
    assert_published(tmp_path, "customers", swapped)


def test_the_digest_level_also_checks_the_outputs(source, tmp_path):
    run(source)
    output = tmp_path / "customers.unique.csv"
    original = output.read_bytes()
    _flip_last_byte(output)
    stat = source.stat()
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 7_000_000_000))

    outcome = run(source)

    assert outcome.status == "DONE"
    assert output.read_bytes() == original


def test_the_metadata_level_does_not_look_inside_the_outputs(source, tmp_path):
    run(source)
    _flip_last_byte(tmp_path / "customers.unique.csv")

    assert run(source).status == "SKIPPED"


def test_verify_content_refuses_an_output_rewritten_with_its_size(source, tmp_path):
    run(source)
    _flip_last_byte(tmp_path / "customers.unique.csv")

    with pytest.raises(ReportError):
        run(source, verify_content=True)
    assert run(source, force=True).status == "DONE"
    assert run(source, verify_content=True).status == "SKIPPED"


def test_a_stray_managed_name_that_the_report_does_not_list_is_refused(tmp_path):
    source = write_csv(tmp_path, "clean.csv", DISTINCT)
    run(source)
    stray = tmp_path / "clean.duplicates_all.csv"
    stray.write_text("id,name\r\n", encoding="utf-8")

    with pytest.raises(ReportError):
        run(source)
    assert run(source, force=True).status == "DONE"
    assert stray.exists()  # --force never deletes a foreign file it does not write


def test_a_changed_encoding_reprocesses(source, tmp_path):
    run(source)

    outcome = run(source, csv=CsvConfig(encoding="latin-1"))

    assert outcome.status == "DONE"
    assert load_report(tmp_path, "customers")["settings"]["encoding"] == "latin-1"


def test_a_source_with_the_stem_of_a_processed_one_but_another_name_is_reprocessed(
    source, tmp_path
):
    run(source)
    other = tmp_path / "customers.tsv"
    shutil.copy(source, other)

    outcome = run(other)

    assert outcome.status == "DONE"
    assert load_report(tmp_path, "customers")["source"]["name"] == "customers.tsv"


def test_a_failed_report_is_reprocessed(tmp_path):
    source = tmp_path / "bad.csv"
    source.write_text("id,name\r\n1\r\n", encoding="utf-8", newline="")
    assert run(source).status == "FAILED"

    assert run(source).status == "FAILED"  # reprocessed, not skipped
    write_csv(tmp_path, "bad.csv", PAIRS)
    assert run(source).status == "DONE"


def test_two_processed_sources_are_skipped_and_the_third_is_processed(tmp_path):
    sources = [write_csv(tmp_path, f"{name}.csv", TRIPLES) for name in ("a", "b", "c")]
    run(sources[0])
    run(sources[1])

    statuses = [run(item).status for item in sources]

    assert statuses == ["SKIPPED", "SKIPPED", "DONE"]


def test_a_forced_run_replaces_the_foreign_names_it_writes_and_keeps_the_others(tmp_path):
    source = write_csv(tmp_path, "customers.csv", PAIRS)
    unique = tmp_path / "customers.unique.csv"
    unique.write_bytes(b"mine")
    spare = tmp_path / "customers.duplicates_all.csv"
    spare.write_bytes(b"mine too")

    outcome = run(source, force=True)

    assert outcome.status == "DONE" and outcome.verification is None
    assert read_csv(unique)[1] == [("1", "a"), ("2", "b"), ("3", "c")]
    assert spare.read_bytes() == b"mine too"


def test_a_touched_source_reports_the_verification_in_the_progress(source):
    from tabalyst.dedup.pipeline import process_source

    run(source)
    stat = source.stat()
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 7_000_000_000))
    events = []

    outcome = process_source(
        source, settings(), destination=source.parent, on_progress=events.append
    )

    assert outcome.verification == "digest"
    assert events and {event.stage for event in events} == {"Dedup"}
    assert any("verifying" in (event.detail or "") for event in events)


def test_the_recovery_report_is_a_valid_in_progress_document():
    report = recovery_report("x.csv", settings(), previous=[], planned=[])

    assert isinstance(report, InProgressReport)
    assert report.source.name == "x.csv"

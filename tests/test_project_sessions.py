"""Private S17 readiness, pinning and read-only ownership contracts."""

import os
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from test_project_queries import publish

from tabalyst.errors import InputError
from tabalyst.projects import _publication, _session, catalog, index
from tabalyst.projects._locks import workspace_maintenance
from tabalyst.projects._queries import QueryError, StaleCursorError
from tabalyst.projects._session import (
    GenerationConflictError,
    SessionRefusedError,
    inspect_project,
    open_project,
)
from tabalyst.projects._staging import _file_hash
from tabalyst.scan_reuse import SourceState
from tabalyst.scanner import ScanConfig
from tabalyst.scanner.config import config_sha256, resolve_config_defaults


@pytest.fixture
def project(tmp_path):
    return publish(tmp_path, 'v\na\nb\nc\n""\n""\n')


def persistent_hashes(location):
    return {
        p.relative_to(location.root): _file_hash(p)
        for p in location.root.rglob("*")
        if p.is_file() and "cache" not in p.parts and p.suffix != ".lock"
    }


def assert_no_queries(location, project_id):
    assert not list(
        (location.project_dir(project_id) / "cache").rglob(".tabalyst-query.json")
    )
    # Exclusive maintenance cannot succeed if a refused/closed session leaked
    # its shared reader lock (opening another reader alone would not prove it).
    with workspace_maintenance(location):
        pass


@pytest.mark.parametrize(
    ("change", "state", "warning"),
    [
        ("none", SourceState.FRESH, None),
        ("touch", SourceState.FRESH, None),
        ("same_size", SourceState.STALE, "source_stale"),
        ("different_size", SourceState.STALE, "source_stale"),
        ("missing", SourceState.MISSING, "source_not_checked"),
        ("directory", SourceState.MISSING, "source_not_checked"),
    ],
)
def test_readiness_matrix_and_persistent_artifacts(
    project, monkeypatch, change, state, warning
):
    location, source, config, outcome = project
    pid = outcome.project.project_id
    if change in ("touch", "same_size"):
        original = source.stat()
        if change == "same_size":
            source.write_text(source.read_text().replace("a", "z"), encoding="utf-8")
        os.utime(
            source, ns=(original.st_atime_ns, original.st_mtime_ns + 2_000_000_000)
        )
    elif change == "different_size":
        source.write_text("v\nlonger\n", encoding="utf-8")
    elif change in ("missing", "directory"):
        source.unlink()
        if change == "directory":
            source.mkdir()
    before = persistent_hashes(location)

    def forbidden(*args, **kwargs):
        pytest.fail("Read-only session called a scan/index/project mutator")

    for module, names in (
        (_publication, ("publish_scan", "_find_project")),
        (catalog, ("create_project", "record_scan")),
        (index, ("find_project", "register_project", "rebuild_index")),
    ):
        for name in names:
            monkeypatch.setattr(module, name, forbidden)
    assessment = inspect_project(location, pid, requested_config=config)
    assert assessment.source_check.state is state
    assert assessment.warnings == (() if warning is None else (warning,))
    assert assessment.current_ready is (warning is None)
    assert assessment.snapshot_ready
    assert assessment.recorded_config_sha256 == config_sha256(
        resolve_config_defaults(config, "csv")
    )
    assert assessment.project_id == pid
    assert assessment.workspace_id == location.workspace_id
    assert assessment.source == source
    with pytest.raises(FrozenInstanceError):
        assessment.generation_id = "changed"
    if warning:
        with pytest.raises(SessionRefusedError) as refusal, open_project(location, pid):
            pytest.fail("Refused session yielded")
        assert refusal.value.assessment.warnings == (warning,)
        assert_no_queries(location, pid)
    else:
        with open_project(location, pid) as current:
            assert current.assessment.current_ready
    with open_project(location, pid, intent="snapshot") as snapshot:
        page = snapshot.records_page("rows", "records.with_missing")
        assert page.scope.generation_id == assessment.generation_id
        with snapshot.materialize_values(
            "rows", outcome.result.datasets[0].fields[0].id
        ) as query:
            assert query.frequencies_page().total == 3
    assert persistent_hashes(location) == before
    assert_no_queries(location, pid)


@pytest.mark.parametrize("operation", ["stat", "hash"])
def test_source_io_failure_is_not_a_source_state(project, monkeypatch, operation):
    from tabalyst import scan_reuse

    location, source, _, outcome = project
    pid = outcome.project.project_id
    if operation == "stat":
        original = Path.stat

        def fail(path, *args, **kwargs):
            if path == source:
                raise PermissionError("denied")
            return original(path, *args, **kwargs)

        monkeypatch.setattr(Path, "stat", fail)
    else:
        stat = source.stat()
        os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))

        def fail(path):
            raise PermissionError("denied")

        monkeypatch.setattr(scan_reuse, "file_sha256", fail)
    assessment = inspect_project(location, pid)
    assert assessment.source_check is None
    assert "denied" in assessment.source_error
    assert assessment.warnings == ("source_check_failed",)
    assert not assessment.current_ready and assessment.snapshot_ready
    with pytest.raises(SessionRefusedError), open_project(location, pid):
        pass
    with open_project(location, pid, intent="snapshot") as session:
        assert (
            session.records_page("rows", "records.empty").scope.generation_id
            == assessment.generation_id
        )
    assert_no_queries(location, pid)


@pytest.mark.parametrize("intent", ["require_current", "snapshot"])
def test_complete_configuration_mismatch_blocks_both_intents(project, intent):
    location, _, _, outcome = project
    requested = ScanConfig.model_validate({"normalization": {"casefold": False}})
    assessment = inspect_project(
        location, outcome.project.project_id, requested_config=requested
    )
    assert assessment.errors == ("config_mismatch",)
    assert not assessment.current_ready and not assessment.snapshot_ready
    with (
        pytest.raises(SessionRefusedError) as refusal,
        open_project(
            location,
            outcome.project.project_id,
            intent=intent,
            requested_config=requested,
        ),
    ):
        pass
    assert refusal.value.assessment.errors == ("config_mismatch",)


def test_recorded_config_is_default_and_request_hash_is_frozen(tmp_path):
    location, _source, config, outcome = publish(
        tmp_path, "v\nA\na\n", settings={"normalization": {"casefold": False}}
    )
    pid = outcome.project.project_id
    with open_project(location, pid, requested_config=config) as session:
        config.normalization.casefold = True
        assert (
            session.refresh_assessment().requested_config_sha256
            == outcome.result.config_sha256
        )
    with open_project(location, pid) as session:
        assert session.assessment.requested_config_sha256 is None
        assert session.assessment.recorded_config_sha256 == outcome.result.config_sha256
    with pytest.raises(TypeError):
        inspect_project(location, pid, requested_config={})


@pytest.mark.parametrize("intent", ["require_current", "snapshot"])
@pytest.mark.parametrize(
    "damage",
    [
        "scan_missing",
        "database_missing",
        "scan_corrupt",
        "database_corrupt",
        "unsupported",
    ],
)
def test_integrity_never_has_snapshot_bypass(project, intent, damage):
    location, _, _, outcome = project
    pid = outcome.project.project_id
    path = (
        location.project_path(pid)
        if damage == "unsupported"
        else (outcome.scan_path if damage.startswith("scan") else outcome.database_path)
    )
    if damage.endswith("missing"):
        path.unlink()
    elif damage == "unsupported":
        path.write_text(
            path.read_text().replace('"format_revision": 2', '"format_revision": 99'),
            encoding="utf-8",
        )
    else:
        path.write_bytes(b"corrupt")
    with pytest.raises(InputError):
        inspect_project(location, pid)
    with pytest.raises(InputError), open_project(location, pid, intent=intent):
        pass
    assert_no_queries(location, pid)


def test_legacy_requires_explicit_rebuild(tmp_path):
    from tabalyst.projects import StorageLocation

    source = tmp_path / "legacy.csv"
    source.write_text("v\na\n", encoding="utf-8")
    location = StorageLocation(tmp_path / "storage")
    document = catalog.create_project(location, source)
    before = persistent_hashes(location)
    for intent in ("require_current", "snapshot"):
        with (
            pytest.raises(InputError, match="Legacy.*rebuild"),
            open_project(location, document.project_id, intent=intent),
        ):
            pass
    with pytest.raises(InputError, match="Legacy.*rebuild"):
        inspect_project(location, document.project_id)
    assert persistent_hashes(location) == before


def test_inspection_is_advisory_and_generation_precondition(project):
    location, source, config, first = project
    pid = first.project.project_id
    assessment = inspect_project(location, pid)
    source.write_text("v\nz\n", encoding="utf-8")
    # Opening must recheck even without a manifest change.
    with (
        pytest.raises(SessionRefusedError),
        open_project(location, pid, expected_generation_id=assessment.generation_id),
    ):
        pass
    second = _publication.publish_scan(source, location, config, workers=1)
    with (
        pytest.raises(GenerationConflictError),
        open_project(
            location,
            pid,
            intent="snapshot",
            expected_generation_id=assessment.generation_id,
        ),
    ):
        pass
    with pytest.raises(GenerationConflictError):
        inspect_project(location, pid, expected_generation_id=assessment.generation_id)
    with open_project(location, pid) as session:
        assert session.generation_id == second.project.generation.id


def test_rescan_between_pinning_and_assessment_keeps_old_scan(project, monkeypatch):
    location, source, config, first = project
    compare = _session.compare_source
    new = []

    def rescan_before_compare(path, recorded):
        source.write_text("v\nnew\n", encoding="utf-8")
        new.append(_publication.publish_scan(source, location, config, workers=1))
        assert recorded.sha256 == first.result.source.sha256
        return compare(path, recorded)

    monkeypatch.setattr(_session, "compare_source", rescan_before_compare)
    with open_project(location, first.project.project_id, intent="snapshot") as session:
        assert session.generation_id == first.project.generation.id
        assert session.assessment.source_check.state is SourceState.STALE
        assert (
            session.records_page("rows", "records.empty").scope.generation_id
            != new[0].project.generation.id
        )


def test_live_reader_refresh_cursor_and_owned_teardown(project):
    location, source, config, first = project
    pid = first.project.project_id
    fid = first.result.datasets[0].fields[0].id
    with open_project(location, pid) as session:
        original = session.assessment
        context = session.materialize_values("rows", fid)
        query = context.__enter__()
        cursor = query.frequencies_page(size=1).next_cursor
        source.write_text("v\nx\ny\nz\n", encoding="utf-8")
        second = _publication.publish_scan(source, location, config, workers=1)
        refreshed = session.refresh_assessment()
        assert refreshed.generation_id == original.generation_id
        assert refreshed.checked_at >= original.checked_at
        assert not refreshed.current_ready
        assert original.current_ready
        assert (
            query.frequencies_page(size=1, cursor=cursor).scope.generation_id
            == original.generation_id
        )
        assert session.records_page("rows", "records.empty").total == 2
    assert query.closed
    with pytest.raises(QueryError, match="closed"):
        query.frequencies_page()
    context.__exit__(None, None, None)
    with pytest.raises(InputError, match="closed"):
        session.refresh_assessment()
    with pytest.raises(InputError, match="closed"):
        session.records_page("rows", "records.empty")
    with (
        pytest.raises(InputError, match="closed"),
        session.materialize_values("rows", fid),
    ):
        pass
    with open_project(location, pid) as current:
        assert current.generation_id == second.project.generation.id
        with (
            current.materialize_values("rows", fid) as values,
            pytest.raises(StaleCursorError),
        ):
            values.frequencies_page(size=1, cursor=cursor)
    assert_no_queries(location, pid)


@pytest.mark.parametrize("mode", ["mask", "hide", "show"])
def test_source_free_snapshot_exposure_and_saturated_catalog(tmp_path, mode):
    location, source, _, outcome = publish(
        tmp_path,
        "secret\nSECRET-1111\nSECRET-2222\nSECRET-3333\nSECRET-1111\n",
        settings={
            "patterns": [{"id": "secret", "regex": r"SECRET-\d{4}", "sensitive": True}],
            "exposure": {"sensitive_values": mode},
        },
        value_limit=2,
    )
    source.unlink()
    pid = outcome.project.project_id
    before = persistent_hashes(location)
    with open_project(location, pid, intent="snapshot") as session:
        assert session.assessment.warnings == ("source_not_checked",)
        with session.materialize_values(
            "rows", outcome.result.datasets[0].fields[0].id
        ) as query:
            page = query.frequencies_page()
            assert page.scope.generation_id == session.assessment.generation_id
            assert page.scope.stored_distinct_limit == 2
            assert page.scope.omitted_occurrences == 1
            assert page.status == "limited"
            if mode == "show":
                assert {item.value for item in page.items} == {
                    "SECRET-1111",
                    "SECRET-2222",
                }
            elif mode == "hide":
                assert page.items == ()
            else:
                assert all("SECRET" not in item.value for item in page.items)
    assert persistent_hashes(location) == before


def test_invalid_intent_and_body_exception_release_resources(project):
    location, _, _, outcome = project
    pid = outcome.project.project_id
    with (
        pytest.raises(ValueError, match="intent"),
        open_project(location, pid, intent="automatic"),
    ):
        pass
    with (
        pytest.raises(RuntimeError),
        open_project(location, pid) as session,
        session.materialize_values("rows", outcome.result.datasets[0].fields[0].id),
    ):
        raise RuntimeError("caller failed")
    assert_no_queries(location, pid)
    with open_project(location, pid):
        pass


def test_json_snapshot_queries_keep_collection_scope(tmp_path):
    location, source, _, outcome = publish(
        tmp_path,
        '[{"v":"a","children":[{"name":"x"}]},{"v":"b","children":[{"name":"y"}]}]',
        suffix=".json",
    )
    source.unlink()
    with open_project(
        location, outcome.project.project_id, intent="snapshot"
    ) as session:
        for dataset in outcome.result.datasets:
            page = session.records_page(dataset.id, "records.with_missing")
            assert page.scope.scan_scope == outcome.result.scope
            assert page.scope.generation_id == session.generation_id
            for field in dataset.fields:
                with session.materialize_values(dataset.id, field.id) as query:
                    page = query.frequencies_page()
                    assert page.scope.structure == dataset.structure
                    assert (
                        page.scope.config_sha256
                        == session.assessment.recorded_config_sha256
                    )


def test_default_catalog_cap_survives_snapshot_open(tmp_path):
    location, source, _, outcome = publish(
        tmp_path, "v\n" + "".join(f"value-{i}\n" for i in range(10001))
    )
    source.unlink()
    with (
        open_project(
            location, outcome.project.project_id, intent="snapshot"
        ) as session,
        session.materialize_values(
            "rows", outcome.result.datasets[0].fields[0].id
        ) as query,
    ):
        page = query.frequencies_page(size=1)
        assert page.status == "limited"
        assert page.total == 10000
        assert page.scope.stored_distinct_limit == 10000
        assert page.scope.omitted_occurrences == 1

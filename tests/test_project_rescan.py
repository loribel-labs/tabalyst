"""S17 explicit project-targeted publication and post-commit reopening."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_project_queries import publish

from tabalyst.errors import InputError
from tabalyst.progress import ProgressPhase
from tabalyst.project_scan_service import CommittedRescanOpenError, rescan_project
from tabalyst.projects import _publication, _sync
from tabalyst.projects._generation import GenerationConflictError, open_generation
from tabalyst.projects._locks import ProjectBusyError, workspace_maintenance
from tabalyst.projects._session import inspect_project, open_project
from tabalyst.projects.store import read_project
from tabalyst.scanner import ScanConfig
from tabalyst.scanner.config import resolve_config_defaults


@pytest.fixture
def project(tmp_path):
    return publish(
        tmp_path,
        "v\nA\nb\n",
        settings={"normalization": {"casefold": False}},
    )


def selected_bytes(location, project_id):
    project = read_project(location, project_id)
    return location.project_path(project_id).read_bytes(), project.generation.id


def test_selected_rescan_preserves_identity_and_recorded_config(project):
    location, source, config, first = project
    assessment = inspect_project(location, first.project.project_id)
    source.write_text("v\nZ\nz\n", encoding="utf-8")
    with rescan_project(
        location,
        assessment.project_id,
        expected_generation_id=assessment.generation_id,
        expected_source=assessment.source,
    ) as result:
        second = result.published
        assert second.project.project_id == first.project.project_id
        assert second.project.created_at == first.project.created_at
        assert second.project.generation.id != assessment.generation_id
        assert second.result.config_sha256 == first.result.config_sha256
        assert second.result.config == resolve_config_defaults(config, "csv")
        assert second.result.scope.records_analyzed == 2
        assert result.session.generation_id == second.project.generation.id
        assert result.session.assessment.current_ready
        assert (
            result.session.records_page("rows", "records.empty").scope.generation_id
            == second.project.generation.id
        )
        assert first.database_path.exists() and first.scan_path.exists()
    with workspace_maintenance(location):
        pass


def test_explicit_full_config_and_smaller_cap_opt_in(project):
    location, source, _, first = project
    pid = first.project.project_id
    replacement = ScanConfig.model_validate({"normalization": {"casefold": True}})
    source.write_text("v\nA\nb\nc\nd\n", encoding="utf-8")
    with rescan_project(
        location,
        pid,
        expected_generation_id=first.project.generation.id,
        expected_source=source,
        config=replacement,
        value_limit=2,
    ) as result:
        assert result.published.result.config == resolve_config_defaults(
            replacement, "csv"
        )
        with result.session.materialize_values(
            "rows", result.published.result.datasets[0].fields[0].id
        ) as query:
            page = query.frequencies_page()
            assert page.scope.stored_distinct_limit == 2
            assert page.scope.omitted_occurrences == 2
        second = result.published
    with rescan_project(
        location,
        pid,
        expected_generation_id=second.project.generation.id,
        expected_source=source,
    ) as result:
        assert result.published.result.config == resolve_config_defaults(
            replacement, "csv"
        )
        with result.session.materialize_values(
            "rows", result.published.result.datasets[0].fields[0].id
        ) as query:
            page = query.frequencies_page()
            assert page.scope.stored_distinct_limit == 10000
            assert page.scope.omitted_occurrences == 0
            assert page.total == 4


@pytest.mark.parametrize("wrong", ["generation", "source"])
def test_stale_precondition_rejects_without_staging(project, wrong, monkeypatch):
    location, source, _, first = project
    pid = first.project.project_id
    before = selected_bytes(location, pid)

    def forbidden(*args, **kwargs):
        pytest.fail("Precondition failure reached staging")

    monkeypatch.setattr(_publication, "build_staging", forbidden)
    with (
        pytest.raises(GenerationConflictError),
        rescan_project(
            location,
            pid,
            expected_generation_id="0" * 26
            if wrong == "generation"
            else first.project.generation.id,
            expected_source=source.parent / "elsewhere.csv"
            if wrong == "source"
            else source,
        ),
    ):
        pass
    assert selected_bytes(location, pid) == before
    assert first.database_path.exists()


@pytest.mark.parametrize("source_state", ["missing", "directory", "unreadable"])
def test_unavailable_source_preserves_generation(project, monkeypatch, source_state):
    location, source, _, first = project
    pid = first.project.project_id
    before = selected_bytes(location, pid)
    if source_state == "missing":
        source.unlink()
    elif source_state == "directory":
        source.unlink()
        source.mkdir()
    else:
        original = Path.stat

        def fail(path, *args, **kwargs):
            if path == source:
                raise PermissionError("denied")
            return original(path, *args, **kwargs)

        monkeypatch.setattr(Path, "stat", fail)
    with (
        pytest.raises(InputError),
        rescan_project(
            location,
            pid,
            expected_generation_id=first.project.generation.id,
            expected_source=source,
        ),
    ):
        pass
    assert selected_bytes(location, pid) == before
    with open_generation(location, pid):
        pass


def test_precommit_failure_preserves_selection(project, monkeypatch):
    location, source, _, first = project
    pid = first.project.project_id
    before = selected_bytes(location, pid)

    def fail(*args, **kwargs):
        raise OSError("injected staging failure")

    monkeypatch.setattr(_publication, "build_staging", fail)
    with (
        pytest.raises(OSError, match="injected"),
        rescan_project(
            location,
            pid,
            expected_generation_id=first.project.generation.id,
            expected_source=source,
        ),
    ):
        pass
    assert selected_bytes(location, pid) == before
    assert first.database_path.exists()


def test_selected_artifact_hash_failure_refuses_rescan(project):
    location, source, _, first = project
    pid = first.project.project_id
    before = location.project_path(pid).read_bytes()
    first.database_path.write_bytes(b"corrupt")
    with (
        pytest.raises(InputError, match="hash mismatch"),
        rescan_project(
            location,
            pid,
            expected_generation_id=first.project.generation.id,
            expected_source=source,
        ),
    ):
        pass
    assert location.project_path(pid).read_bytes() == before


def test_index_failure_remains_postcommit_warning(project, monkeypatch):
    location, source, _, first = project

    def fail(*args, **kwargs):
        raise OSError("index unavailable")

    monkeypatch.setattr(_publication, "register_project", fail)
    with rescan_project(
        location,
        first.project.project_id,
        expected_generation_id=first.project.generation.id,
        expected_source=source,
    ) as result:
        assert "index needs repair" in result.published.warnings[0]
        assert result.session.generation_id == result.published.project.generation.id


def test_postcommit_reopen_rejects_intervening_manifest(project, monkeypatch):
    from tabalyst import project_scan_service

    location, source, config, first = project
    normal_open = open_project

    def concurrent_open(*args, **kwargs):
        _publication.publish_scan(source, location, config, workers=1)
        return normal_open(*args, **kwargs)

    monkeypatch.setattr(project_scan_service, "open_project", concurrent_open)
    with (
        pytest.raises(CommittedRescanOpenError) as error,
        rescan_project(
            location,
            first.project.project_id,
            expected_generation_id=first.project.generation.id,
            expected_source=source,
        ),
    ):
        pass
    assert isinstance(error.value.cause, GenerationConflictError)
    assert (
        error.value.published.project.generation.id
        != read_project(location, first.project.project_id).generation.id
    )


def test_postcommit_reopen_interruption_identifies_committed_result(
    project, monkeypatch
):
    from tabalyst import project_scan_service

    location, source, _, first = project

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(project_scan_service, "open_project", interrupted)
    with (
        pytest.raises(CommittedRescanOpenError) as error,
        rescan_project(
            location,
            first.project.project_id,
            expected_generation_id=first.project.generation.id,
            expected_source=source,
        ),
    ):
        pass
    assert isinstance(error.value.cause, KeyboardInterrupt)
    assert (
        error.value.published.project.generation.id
        == read_project(location, first.project.project_id).generation.id
    )


@pytest.mark.parametrize("intent", ["require_current", "snapshot"])
def test_source_change_after_commit_uses_explicit_open_intent(
    project, monkeypatch, intent
):
    from tabalyst import project_scan_service

    location, source, _, first = project
    normal_open = open_project

    def changed_source_open(*args, **kwargs):
        source.write_text("v\nchanged after commit\n", encoding="utf-8")
        return normal_open(*args, **kwargs)

    monkeypatch.setattr(project_scan_service, "open_project", changed_source_open)
    options = {
        "expected_generation_id": first.project.generation.id,
        "expected_source": source,
        "intent": intent,
    }
    if intent == "require_current":
        with (
            pytest.raises(CommittedRescanOpenError) as error,
            rescan_project(location, first.project.project_id, **options),
        ):
            pass
        assert (
            error.value.published.project.generation.id
            == read_project(location, first.project.project_id).generation.id
        )
    else:
        with rescan_project(location, first.project.project_id, **options) as result:
            assert result.session.assessment.warnings == ("source_stale",)
            assert (
                result.session.generation_id == result.published.project.generation.id
            )


def test_caller_exception_closes_rescan_session(project):
    location, source, _, first = project
    with (
        pytest.raises(RuntimeError, match="caller failed"),
        rescan_project(
            location,
            first.project.project_id,
            expected_generation_id=first.project.generation.id,
            expected_source=source,
        ) as result,
    ):
        raise RuntimeError("caller failed")
    with pytest.raises(InputError, match="closed"):
        result.session.refresh_assessment()
    with workspace_maintenance(location):
        pass


def test_progress_completes_only_after_postcommit_reopen(project):
    location, source, _, first = project
    phases = []
    committed = []

    def observe(event):
        phases.append(event.phase)
        if event.phase is ProgressPhase.COMPLETE:
            committed.append(
                read_project(location, first.project.project_id).generation.id
            )

    with rescan_project(
        location,
        first.project.project_id,
        expected_generation_id=first.project.generation.id,
        expected_source=source,
        on_progress=observe,
    ) as result:
        assert phases[-1] is ProgressPhase.COMPLETE
        assert phases.count(ProgressPhase.COMPLETE) == 1
        assert phases.index(ProgressPhase.WRITING) < len(phases) - 1
        assert committed == [result.session.generation_id]


def test_progress_callback_failure_after_commit_identifies_result(project):
    location, source, _, first = project

    def fail(event):
        if event.phase in (ProgressPhase.COMPLETE, ProgressPhase.FAILED):
            raise RuntimeError("progress callback failed")

    with (
        pytest.raises(CommittedRescanOpenError) as error,
        rescan_project(
            location,
            first.project.project_id,
            expected_generation_id=first.project.generation.id,
            expected_source=source,
            on_progress=fail,
        ),
    ):
        pass
    assert isinstance(error.value.cause, RuntimeError)
    assert (
        error.value.published.project.generation.id
        == read_project(location, first.project.project_id).generation.id
    )
    with workspace_maintenance(location):
        pass


def test_postcommit_sync_warning_and_unknown_outcome(project, monkeypatch):
    location, source, _, first = project
    original = _sync.replace_manifest

    def after_replace(path, text):
        original(path, text)
        raise OSError("sync unavailable")

    monkeypatch.setattr(_sync, "replace_manifest", after_replace)
    with rescan_project(
        location,
        first.project.project_id,
        expected_generation_id=first.project.generation.id,
        expected_source=source,
    ) as result:
        assert "committed" in result.published.warnings[0]
        committed = result.published.project.generation.id
    assert read_project(location, first.project.project_id).generation.id == committed
    monkeypatch.undo()

    def corrupt_and_fail(path, text):
        path.write_bytes(b"{")
        raise OSError("uncertain replacement")

    monkeypatch.setattr(_sync, "replace_manifest", corrupt_and_fail)
    with (
        pytest.raises(_publication.UnknownProjectOutcomeError),
        rescan_project(
            location,
            first.project.project_id,
            expected_generation_id=committed,
            expected_source=source,
        ),
    ):
        pass
    assert list(location.projects_dir.glob("*/generations/*/project.duckdb"))


def test_competing_writers_are_serialized(project, monkeypatch):
    location, source, _, first = project
    ready = threading.Event()
    release = threading.Event()
    normal = _publication.build_staging

    def delay(*args, **kwargs):
        ready.set()
        assert release.wait(timeout=15)
        return normal(*args, **kwargs)

    monkeypatch.setattr(_publication, "build_staging", delay)

    def first_rescan():
        with rescan_project(
            location,
            first.project.project_id,
            expected_generation_id=first.project.generation.id,
            expected_source=source,
        ) as result:
            return result.published.project.generation.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        future = executor.submit(first_rescan)
        assert ready.wait(timeout=15)
        with (
            pytest.raises(ProjectBusyError),
            rescan_project(
                location,
                first.project.project_id,
                expected_generation_id=first.project.generation.id,
                expected_source=source,
            ),
        ):
            pass
        release.set()
        new_id = future.result(timeout=30)
    assert read_project(location, first.project.project_id).generation.id == new_id
    with (
        pytest.raises(GenerationConflictError),
        rescan_project(
            location,
            first.project.project_id,
            expected_generation_id=first.project.generation.id,
            expected_source=source,
        ),
    ):
        pass


def test_selected_project_wins_over_other_project_sharing_path(tmp_path):
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    location, source, config, first = publish(left, "v\na\n")
    # Build the other project in the same workspace with a separate same-named
    # source, then give it the same source binding. The index points at it.
    other_source = right / "source.csv"
    other_source.write_text("v\nb\n", encoding="utf-8")
    other = _publication.publish_scan(other_source, location, config, workers=1)
    other_manifest = other.project.model_copy(update={"source": first.project.source})
    _sync.replace_manifest(
        location.project_path(other.project.project_id),
        json.dumps(other_manifest.model_dump(mode="json")) + "\n",
    )
    from tabalyst.projects.index import register_project

    register_project(location, other_manifest)
    source.write_text("v\nz\n", encoding="utf-8")
    with rescan_project(
        location,
        first.project.project_id,
        expected_generation_id=first.project.generation.id,
        expected_source=source,
    ) as result:
        assert result.published.project.project_id == first.project.project_id
    assert (
        read_project(location, other.project.project_id).generation.id
        == other.project.generation.id
    )
    assert other.database_path.exists()


def test_validation_before_publication(project):
    location, source, _, first = project
    stamp = datetime.now(UTC)
    with (
        pytest.raises(ValueError, match="limit"),
        rescan_project(
            location,
            first.project.project_id,
            expected_generation_id=first.project.generation.id,
            expected_source=source,
            value_limit=10001,
            now=stamp,
        ),
    ):
        pass
    with (
        pytest.raises(ValueError, match="intent"),
        rescan_project(
            location,
            first.project.project_id,
            expected_generation_id=first.project.generation.id,
            expected_source=source,
            intent="automatic",
        ),
    ):
        pass
    assert (
        read_project(location, first.project.project_id).generation.id
        == first.project.generation.id
    )

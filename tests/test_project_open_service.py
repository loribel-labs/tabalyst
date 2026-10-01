"""S18 first-open policy above private pinned sessions and targeted rescans."""

from pathlib import Path

import pytest
from test_project_queries import publish

from tabalyst.errors import InputError
from tabalyst.project_open_service import (
    enter_project,
    inspect_opening,
    open_snapshot,
    rescan_from_decision,
)
from tabalyst.projects import _publication, _sync
from tabalyst.projects._generation import GenerationConflictError
from tabalyst.projects._locks import workspace_maintenance
from tabalyst.projects.location import StorageLocation
from tabalyst.projects.store import read_project
from tabalyst.scan_reuse import SourceState
from tabalyst.scanner import ScanConfig
from tabalyst.scanner.config import resolve_config_defaults


@pytest.fixture
def project(tmp_path):
    return publish(tmp_path, "v\na\nb\n")


def test_fresh_opens_current_without_publication(project, monkeypatch):
    location, source, _, first = project
    pid = first.project.project_id
    before = location.project_path(pid).read_bytes()

    def forbidden(*args, **kwargs):
        pytest.fail("First-open inspection tried to publish")

    monkeypatch.setattr(_publication, "build_staging", forbidden)
    with enter_project(location, pid) as entry:
        assert entry.decision.action == "open_current"
        assert entry.decision.choices == ("open_current", "rescan")
        assert entry.session is not None
        assert entry.session.intent == "require_current"
        assert entry.session.generation_id == first.project.generation.id
        assert entry.session.assessment.source == source
        assert (
            entry.session.records_page("rows", "records.empty").scope.generation_id
            == first.project.generation.id
        )
    assert location.project_path(pid).read_bytes() == before
    with workspace_maintenance(location):
        pass


def test_current_open_preserves_requested_config_on_refresh(project):
    location, _, config, first = project
    with enter_project(
        location, first.project.project_id, requested_config=config
    ) as entry:
        assert entry.session is not None
        expected = entry.decision.assessment.requested_config_sha256
        assert expected == first.result.config_sha256
        assert entry.session.assessment.requested_config_sha256 == expected
        assert entry.session.refresh_assessment().requested_config_sha256 == expected


def test_stale_requires_choice_and_explicit_snapshot_or_rescan(project):
    location, source, _, first = project
    pid = first.project.project_id
    source.write_text("v\nz\n", encoding="utf-8")
    before = location.project_path(pid).read_bytes()
    with enter_project(location, pid) as entry:
        assert entry.session is None
        assert entry.decision.action == "choose"
        assert entry.decision.choices == ("snapshot", "rescan")
        assert entry.decision.assessment.source_check.state is SourceState.STALE
    assert location.project_path(pid).read_bytes() == before
    with open_snapshot(location, entry.decision) as snapshot:
        assert snapshot.intent == "snapshot"
        assert snapshot.assessment.warnings == ("source_stale",)
        assert snapshot.generation_id == first.project.generation.id
    with rescan_from_decision(location, entry.decision) as result:
        assert result.published.project.project_id == pid
        assert result.published.project.generation.id != first.project.generation.id
        assert result.session.assessment.current_ready
    with (
        pytest.raises(GenerationConflictError),
        open_snapshot(location, entry.decision),
    ):
        pass


@pytest.mark.parametrize("state", ["missing", "directory", "check_failed"])
def test_unavailable_source_offers_snapshot_but_no_rescan(project, monkeypatch, state):
    location, source, _, first = project
    if state in ("missing", "directory"):
        source.unlink()
        if state == "directory":
            source.mkdir()
    else:
        original = Path.stat

        def denied(path, *args, **kwargs):
            if path == source:
                raise PermissionError("denied")
            return original(path, *args, **kwargs)

        monkeypatch.setattr(Path, "stat", denied)
    decision = inspect_opening(location, first.project.project_id)
    assert decision.action == "choose"
    assert "snapshot" in decision.choices and "rescan" not in decision.choices
    with open_snapshot(location, decision) as session:
        assert session.generation_id == first.project.generation.id
        assert session.assessment.warnings == (
            ("source_check_failed",)
            if state == "check_failed"
            else ("source_not_checked",)
        )
    with (
        pytest.raises(InputError, match="not an available choice"),
        rescan_from_decision(location, decision),
    ):
        pass


def test_config_mismatch_blocks_opening_until_explicit_replacement(project):
    location, source, _, first = project
    pid = first.project.project_id
    requested = ScanConfig.model_validate({"normalization": {"casefold": False}})
    with enter_project(location, pid, requested_config=requested) as entry:
        assert entry.session is None
        assert entry.decision.action == "resolve_config"
        assert entry.decision.assessment.errors == ("config_mismatch",)
        assert entry.decision.choices == ("use_recorded_config", "rescan")
    with (
        pytest.raises(InputError, match="not an available choice"),
        open_snapshot(location, entry.decision),
    ):
        pass
    with (
        pytest.raises(InputError, match="replacement"),
        rescan_from_decision(location, entry.decision),
    ):
        pass
    with enter_project(location, pid) as recorded:
        assert recorded.session is not None
    with rescan_from_decision(location, entry.decision, config=requested) as result:
        assert result.published.result.config == resolve_config_defaults(
            requested, "csv"
        )
        assert result.session.assessment.current_ready
    assert read_project(location, pid).source.path == source.as_posix()


def test_mismatched_replacement_rejected_before_publication(project):
    location, _, _, first = project
    pid = first.project.project_id
    requested = ScanConfig.model_validate({"normalization": {"casefold": False}})
    decision = inspect_opening(location, pid, requested_config=requested)
    before = location.project_path(pid).read_bytes()
    with (
        pytest.raises(InputError, match="differs"),
        rescan_from_decision(location, decision, config=ScanConfig()),
    ):
        pass
    assert location.project_path(pid).read_bytes() == before


def test_source_change_between_inspection_and_current_open_returns_new_decision(
    project, monkeypatch
):
    from tabalyst import project_open_service

    location, source, _, first = project
    normal_open = project_open_service.open_project

    def change_source(*args, **kwargs):
        source.write_text("v\nz\n", encoding="utf-8")
        return normal_open(*args, **kwargs)

    monkeypatch.setattr(project_open_service, "open_project", change_source)
    with enter_project(location, first.project.project_id) as entry:
        assert entry.session is None
        assert entry.decision.action == "choose"
        assert entry.decision.assessment.warnings == ("source_stale",)
        assert entry.decision.assessment.generation_id == first.project.generation.id


def test_generation_change_between_inspection_and_open_requires_reinspection(
    project, monkeypatch
):
    from tabalyst import project_open_service

    location, source, config, first = project
    normal_open = project_open_service.open_project

    def rescan_first(*args, **kwargs):
        _publication.publish_scan(source, location, config, workers=1)
        return normal_open(*args, **kwargs)

    monkeypatch.setattr(project_open_service, "open_project", rescan_first)
    with (
        pytest.raises(GenerationConflictError),
        enter_project(location, first.project.project_id),
    ):
        pass


def test_snapshot_and_rescan_reject_stale_generation(project):
    location, source, config, first = project
    pid = first.project.project_id
    source.write_text("v\nz\n", encoding="utf-8")
    decision = inspect_opening(location, pid)
    _publication.publish_scan(source, location, config, workers=1)
    with pytest.raises(GenerationConflictError), open_snapshot(location, decision):
        pass
    with (
        pytest.raises(GenerationConflictError),
        rescan_from_decision(location, decision),
    ):
        pass


def test_decision_cannot_cross_workspace_or_storage_root(project, tmp_path):
    location, source, _, first = project
    source.write_text("v\nz\n", encoding="utf-8")
    decision = inspect_opening(location, first.project.project_id)
    other_workspace = StorageLocation(location.root, "other")
    other_root = StorageLocation(tmp_path / "different-root")
    with (
        pytest.raises(GenerationConflictError),
        open_snapshot(other_workspace, decision),
    ):
        pass
    with pytest.raises(GenerationConflictError), open_snapshot(other_root, decision):
        pass


def test_integrity_failure_never_becomes_a_choice(project):
    location, _, _, first = project
    first.database_path.write_bytes(b"corrupt")
    with pytest.raises(InputError), enter_project(location, first.project.project_id):
        pass


def test_explicit_rescan_keeps_older_snapshot_and_cursor_live(project):
    location, source, _, first = project
    source.write_text("v\nz\n", encoding="utf-8")
    decision = inspect_opening(location, first.project.project_id)
    field_id = first.result.datasets[0].fields[0].id
    with (
        open_snapshot(location, decision) as old,
        old.materialize_values("rows", field_id) as values,
    ):
        first_page = values.frequencies_page(size=1)
        cursor = first_page.next_cursor
        assert cursor is not None
        with rescan_from_decision(location, decision) as new:
            assert new.session.generation_id != old.generation_id
            assert (
                values.frequencies_page(size=1, cursor=cursor).scope.generation_id
                == old.generation_id
            )
            assert (
                old.records_page("rows", "records.empty").scope.generation_id
                == old.generation_id
            )


def test_source_binding_change_without_generation_change_is_a_conflict(
    project, monkeypatch, tmp_path
):
    from tabalyst import project_open_service

    location, source, _, first = project
    other_dir = tmp_path / "elsewhere"
    other_dir.mkdir()
    other_source = other_dir / source.name
    other_source.write_bytes(source.read_bytes())
    normal_open = project_open_service.open_project

    def redirect_source(*args, **kwargs):
        changed = first.project.model_copy(
            update={
                "source": first.project.source.model_copy(
                    update={"path": other_source.as_posix()}
                )
            }
        )
        _sync.replace_manifest(
            location.project_path(first.project.project_id),
            changed.model_dump_json(indent=2) + "\n",
        )
        return normal_open(*args, **kwargs)

    monkeypatch.setattr(project_open_service, "open_project", redirect_source)
    with (
        pytest.raises(GenerationConflictError),
        enter_project(location, first.project.project_id),
    ):
        pass
    with workspace_maintenance(location):
        pass

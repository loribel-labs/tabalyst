from pathlib import Path

import pytest

from tabalyst.errors import ConfigurationError
from tabalyst.projects import LOCAL_WORKSPACE, StorageLocation, local_storage_root
from tabalyst.projects.identity import new_project_id


def test_environment_variable_overrides_the_platform_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path / "home"))

    assert local_storage_root() == (tmp_path / "home").resolve()


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_environment_variable_is_ignored(monkeypatch, value):
    monkeypatch.setenv("TABALYST_HOME", value)

    root = local_storage_root()

    assert root.is_absolute()
    assert root.name.lower() == "tabalyst"


def test_platform_directory_without_override(monkeypatch):
    monkeypatch.delenv("TABALYST_HOME", raising=False)

    root = local_storage_root()

    assert root.is_absolute()
    assert root.name.lower() == "tabalyst"
    # No appauthor level: the directory sits directly under the data directory.
    assert root.parent.name.lower() != "tabalyst"


def test_local_location_uses_the_local_workspace(monkeypatch, tmp_path):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path))

    location = StorageLocation.local()

    assert location.workspace_id == LOCAL_WORKSPACE == "local"
    assert location.root == tmp_path.resolve()


def test_layout_is_the_same_below_any_root(tmp_path):
    project_id = new_project_id()
    location = StorageLocation(tmp_path, "local")

    assert location.projects_dir == tmp_path / "workspaces" / "local" / "projects"
    assert location.index_path == location.projects_dir / "index.json"
    assert location.project_dir(project_id) == location.projects_dir / project_id
    assert location.project_path(project_id) == (
        location.projects_dir / project_id / "project.json"
    )


@pytest.mark.parametrize("workspace_id", ["", "a/b", "..", "a b", "é", "a.b"])
def test_workspace_id_cannot_leave_its_directory(tmp_path, workspace_id):
    with pytest.raises(ConfigurationError):
        StorageLocation(tmp_path, workspace_id)


def test_project_directory_requires_a_project_id(tmp_path):
    location = StorageLocation(Path(tmp_path))

    with pytest.raises(ValueError):
        location.project_dir("../elsewhere")


@pytest.mark.parametrize(
    ("platform", "name"),
    [("win32", "Tabalyst"), ("darwin", "Tabalyst"), ("linux", "tabalyst")],
)
def test_application_name_follows_the_platform(monkeypatch, platform, name):
    calls = []

    def fake_user_data_dir(appname, appauthor):
        calls.append((appname, appauthor))
        return "/data/" + appname

    monkeypatch.delenv("TABALYST_HOME", raising=False)
    monkeypatch.setattr("tabalyst.projects.location.sys.platform", platform)
    monkeypatch.setattr(
        "tabalyst.projects.location.platformdirs.user_data_dir", fake_user_data_dir
    )

    assert local_storage_root() == Path("/data/" + name)
    assert calls == [(name, False)]

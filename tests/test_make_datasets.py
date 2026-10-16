# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Check ``examples/tools/make_datasets.py``: generated datasets are built outside the checkout."""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _tool() -> ModuleType:
    script = ROOT / "examples" / "tools" / "make_datasets.py"
    spec = importlib.util.spec_from_file_location("test_make_datasets_tool", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _request(directory: Path, sha: str = "0" * 64) -> Path:
    path = directory / "tiny.json"
    path.write_text(json.dumps({
        "id": "tiny",
        "generate": {"example": "crm", "rows": 12, "seed": 5},
        "files": {"tiny.csv": {"from": "crm-contacts.csv", "sha256": sha}},
    }), encoding="utf-8")
    return path


def test_shipped_request_is_listed_and_other_json_files_are_not() -> None:
    tool = _tool()

    assert "insurance-customers-100k" in tool.requests()
    assert not tool.is_request(ROOT / "examples" / "datasets" / "orders.json")


def test_default_root_is_outside_the_checkout_and_follows_the_environment(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    tool = _tool()
    monkeypatch.delenv("TABALYST_DATASETS", raising=False)

    assert not tool.default_root().is_relative_to(ROOT)
    monkeypatch.setenv("TABALYST_DATASETS", str(tmp_path))
    assert tool.default_root() == tmp_path


def test_a_changed_file_is_refused_and_leaves_nothing_behind(tmp_path: Path) -> None:
    tool = _tool()
    request = _request(tmp_path)
    root = tmp_path / "out"

    with pytest.raises(RuntimeError, match="--update-sha"):
        tool.ensure(request, root)
    assert [path.name for path in root.iterdir()] == []


def test_update_sha_records_the_digest_then_the_file_is_reused(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    tool = _tool()
    request = _request(tmp_path)
    root = tmp_path / "out"

    paths = tool.ensure(request, root, update_sha=True)
    recorded = json.loads(request.read_text(encoding="utf-8"))["files"]["tiny.csv"]["sha256"]
    assert recorded == tool.sha256(paths["tiny.csv"])

    def refuse(*_args: object) -> None:
        raise AssertionError("the file matches its digest, nothing should be generated")

    monkeypatch.setattr(tool, "_generate", refuse)
    assert tool.ensure(request, root) == paths


def test_category_manifest_lists_its_runs_in_order() -> None:
    manifest = {"id": "pair", "datasets": [
        {"id": "one", "generate": {"example": "crm", "rows": 12, "seed": 5}, "files": {}},
        {"id": "two", "generate": {"example": "crm", "rows": 20, "seed": 5}, "files": {}},
    ]}

    assert [unit["id"] for unit in _tool().units(manifest)] == ["one", "two"]


def test_every_committed_request_has_digests_and_known_options() -> None:
    tool = _tool()
    for path in tool.requests().values():
        data = json.loads(path.read_text(encoding="utf-8"))
        for unit in tool.units(data):
            assert all(len(spec["sha256"]) == 64 for spec in unit["files"].values())
            assert set(unit["generate"]) - {"example", "rows", "seed"} <= set(tool.OPTIONS)


def test_category_files_are_written_under_the_category_id(tmp_path: Path) -> None:
    tool = _tool()
    manifest = tmp_path / "pair.json"
    manifest.write_text(json.dumps({
        "id": "pair",
        "datasets": [{
            "id": "tiny",
            "generate": {"example": "crm", "rows": 12, "seed": 5},
            "files": {"tiny.csv": {"from": "crm-contacts.csv", "sha256": "0" * 64}},
        }],
    }), encoding="utf-8")
    root = tmp_path / "out"

    paths = tool.ensure(manifest, root, update_sha=True)

    assert paths["tiny.csv"] == root / "pair" / "tiny.csv"
    assert paths["tiny.csv"].is_file()
    recorded = json.loads(manifest.read_text(encoding="utf-8"))
    assert recorded["datasets"][0]["files"]["tiny.csv"]["sha256"] == tool.sha256(paths["tiny.csv"])

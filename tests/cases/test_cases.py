# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Generic test of every case: ``examples/cases/*/case.json``.

A case is checked from its manifest: the format of the manifest, the committed
input against its deterministic build, and the expectations (classes kept, and
known gaps as strict ``xfail``). A new case needs no new test file.
"""

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

CASES_DIR = Path(__file__).resolve().parents[2] / "examples" / "cases"
MANIFESTS = sorted(CASES_DIR.glob("*/case.json"))
REQUIRED_KEYS = {
    "id", "title", "tool", "question", "inputs", "build", "runs", "measure",
    "expectations", "publish",
}
OPTIONAL_KEYS = {"captures"}


def _load(manifest: Path) -> tuple[dict[str, Any], ModuleType]:
    data: dict[str, Any] = json.loads(manifest.read_text(encoding="utf-8"))
    script = manifest.parent / data["build"]["script"]
    spec = importlib.util.spec_from_file_location(f"case_{manifest.parent.name}", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return data, module


def _ids(manifests: list[Path]) -> list[str]:
    return [manifest.parent.name for manifest in manifests]


def _expectations() -> list[Any]:
    """One parameter per expected class; known gaps are strict ``xfail``."""
    params: list[Any] = []
    for manifest in MANIFESTS:
        expected = json.loads(manifest.read_text(encoding="utf-8"))["expectations"]
        case = manifest.parent.name
        for name in expected["kept"]:
            params.append(pytest.param(manifest, name, id=f"{case}-{name}"))
        for gap in expected["gaps"]:
            mark = pytest.mark.xfail(strict=True, reason=gap["reason"])
            params.append(
                pytest.param(manifest, gap["class"], marks=mark, id=f"{case}-gap-{gap['class']}")
            )
    return params


@pytest.fixture(scope="module")
def scores() -> dict[Path, dict[str, int]]:
    """Per manifest, the score of the run its expectations name (filled once)."""
    return {}


def test_cases_exist() -> None:
    assert MANIFESTS, "no examples/cases/*/case.json found"


@pytest.mark.parametrize("manifest", MANIFESTS, ids=_ids(MANIFESTS))
def test_manifest_has_the_documented_keys(manifest: Path) -> None:
    data, _ = _load(manifest)

    assert REQUIRED_KEYS <= set(data) <= REQUIRED_KEYS | OPTIONAL_KEYS
    assert data["id"] == manifest.parent.name
    assert (manifest.parent / "README.md").is_file()
    assert set(data["publish"]) == {"site", "docs"}
    expected = data["expectations"]
    assert expected["run"] in data["runs"]
    classes = json.loads((manifest.parent / data["inputs"]["truth"]).read_text(encoding="utf-8"))
    listed = list(expected["kept"]) + [gap["class"] for gap in expected["gaps"]]
    assert len(listed) == len(set(listed)), "a class is listed twice"
    assert set(listed) <= set(classes)


@pytest.mark.parametrize("manifest", MANIFESTS, ids=_ids(MANIFESTS))
def test_committed_input_is_the_deterministic_build(manifest: Path) -> None:
    _, module = _load(manifest)

    assert module.build_matches_input()


@pytest.mark.parametrize(("manifest", "name"), _expectations())
def test_case_expectation_holds(
    scores: dict[Path, dict[str, int]],
    tmp_path_factory: pytest.TempPathFactory,
    manifest: Path,
    name: str,
) -> None:
    if manifest not in scores:
        data, module = _load(manifest)
        expected = data["expectations"]
        output = tmp_path_factory.mktemp(manifest.parent.name) / "sample.csv"
        module.run(expected["run"], expected["rows"], expected["seed"], output)
        scores[manifest] = module.score(output)

    assert scores[manifest][name] > 0

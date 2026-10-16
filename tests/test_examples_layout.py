# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The layout of ``examples/``: datasets, showcase manifests, tools and the paths that cite them."""

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
DATASETS = EXAMPLES / "datasets"
MANIFESTS = sorted((EXAMPLES / "showcase").glob("*/demo.json"))
DEMO_KEYS = {"id", "title", "tool", "datasets", "steps", "publish"}
# Where a path under examples/ is quoted: the examples README, the user guide pages and the
# instructions. Releases notes are history and keep the paths of their day.
QUOTING = [
    ROOT / "AGENTS.md",
    ROOT / "README.md",
    EXAMPLES / "README.md",
    *sorted((ROOT / "docs" / "en").rglob("*.md")),
    *sorted((ROOT / "docs" / "dev").glob("*.md")),
]
PATH_PATTERN = re.compile(r"examples/(?:datasets|showcase|tools)/[\w./-]*[\w]")
RETIRED = ("examples/input/", "examples/output/", "examples/make_sales_workbook")


def _ids(paths: list[Path]) -> list[str]:
    return [path.parent.name for path in paths]


def _regenerate() -> ModuleType:
    script = EXAMPLES / "tools" / "regenerate.py"
    spec = importlib.util.spec_from_file_location("examples_regenerate", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load(manifest: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(manifest.read_text(encoding="utf-8"))
    return data


def test_showcase_has_demos() -> None:
    assert MANIFESTS, "no examples/showcase/*/demo.json found"


@pytest.mark.parametrize("manifest", MANIFESTS, ids=_ids(MANIFESTS))
def test_demo_manifest_has_the_documented_keys(manifest: Path) -> None:
    data = _load(manifest)

    assert set(data) == DEMO_KEYS
    assert data["id"] == manifest.parent.name
    assert set(data["publish"]) == {"site", "docs"}
    assert isinstance(data["publish"]["site"], bool)


@pytest.mark.parametrize("manifest", MANIFESTS, ids=_ids(MANIFESTS))
def test_demo_datasets_and_documentation_pages_exist(manifest: Path) -> None:
    data = _load(manifest)

    for name in data["datasets"]:
        assert (DATASETS / name).is_file(), name
    for page in data["publish"]["docs"]:
        assert (ROOT / "docs" / "en" / page).is_file(), page


def _declared_sources(data: dict[str, Any]) -> set[str]:
    """Paths a step may read: a plain dataset, or a file of a generation request as ``{datasets}/``."""
    declared: set[str] = set()
    for name in data["datasets"]:
        declared.add(f"examples/datasets/{name}")
        path = DATASETS / name
        if path.suffix == ".json" and "generate" in json.loads(path.read_text(encoding="utf-8")):
            files = json.loads(path.read_text(encoding="utf-8"))["files"]
            declared |= {f"{{datasets}}/{file}" for file in files}
    return declared


@pytest.mark.parametrize("manifest", MANIFESTS, ids=_ids(MANIFESTS))
def test_demo_steps_read_declared_datasets_and_write_in_their_folder(manifest: Path) -> None:
    data = _load(manifest)
    regenerate = _regenerate()
    declared = _declared_sources(data)
    folder = f"examples/showcase/{data['id']}/"

    for step in data["steps"]:
        words = regenerate.command_line(step["command"])[3:]
        sources = {word for word in words
                   if word.startswith(("examples/datasets/", "{datasets}/"))}
        outputs = [word for word in words if word.startswith("examples/showcase/")]
        assert sources and sources <= declared, step["command"]
        assert all(word.startswith(folder) for word in outputs), step["command"]
        if "stdout" in step:
            assert step["stdout"].startswith(folder)


@pytest.mark.parametrize("manifest", MANIFESTS, ids=_ids(MANIFESTS))
def test_demo_never_writes_generated_datasets_inside_the_checkout(manifest: Path) -> None:
    data = _load(manifest)

    if any(name.endswith("-100k.json") for name in data["datasets"]):
        tool = _regenerate().load_make_datasets()
        assert not tool.default_root().is_relative_to(ROOT)


def test_a_step_must_start_with_tabalyst() -> None:
    with pytest.raises(ValueError, match="start with tabalyst"):
        _regenerate().command_line("rm -rf examples")


def test_every_dataset_is_described_in_the_datasets_readme() -> None:
    described = (DATASETS / "README.md").read_text(encoding="utf-8")
    files = [path.name for path in DATASETS.iterdir() if path.suffix != ".md"]

    assert files
    for name in files:
        assert f"`{name}`" in described, name


def test_distributions_include_the_dataset_csv_files() -> None:
    manifest_in = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")

    assert "recursive-include examples/datasets *.csv" in manifest_in
    assert "examples/input" not in manifest_in


@pytest.mark.parametrize("page", QUOTING, ids=[path.name for path in QUOTING])
def test_documents_cite_no_retired_example_path(page: Path) -> None:
    text = page.read_text(encoding="utf-8")

    for retired in RETIRED:
        assert retired not in text, f"{page.relative_to(ROOT)} cites {retired}"


@pytest.mark.parametrize("page", QUOTING, ids=[path.name for path in QUOTING])
def test_example_paths_cited_by_documents_exist(page: Path) -> None:
    text = page.read_text(encoding="utf-8")

    for cited in sorted(set(PATH_PATTERN.findall(text))):
        if "<" in cited:
            continue
        assert (ROOT / cited).exists(), f"{page.relative_to(ROOT)} cites {cited}"


def test_python_code_cites_no_retired_example_folder() -> None:
    retired = re.compile(r"\"examples\"\s*/\s*\"(input|output)\"")
    offenders = [
        str(path.relative_to(ROOT))
        for folder in ("tests", "scripts")
        for path in (ROOT / folder).rglob("*.py")
        if retired.search(path.read_text(encoding="utf-8"))
    ]

    assert offenders == []

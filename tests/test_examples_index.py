# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The generated indexes of the examples READMEs (lot E3a): up to date, rewritten from the
manifests, and a drift is detected."""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def _tool() -> ModuleType:
    script = EXAMPLES / "tools" / "make_index.py"
    spec = importlib.util.spec_from_file_location("examples_make_index", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_the_generated_indexes_of_the_readmes_are_up_to_date() -> None:
    stale = _tool().stale_files()

    assert stale == [], f"run python examples/tools/make_index.py: {[p.name for p in stale]}"


def test_every_demo_folder_is_in_the_tree_of_the_examples_readme() -> None:
    tree = (EXAMPLES / "README.md").read_text(encoding="utf-8")
    folders = [p.parent.name for p in sorted(EXAMPLES.glob("showcase/*/demo.json"))]

    assert folders
    for name in folders:
        assert f"|-- {name}/" in tree or f"`-- {name}/" in tree, name


def test_a_block_is_rewritten_and_the_text_around_it_is_kept() -> None:
    text = "before\n<!-- index:x:start -->\nold\n<!-- index:x:end -->\nafter\n"

    rewritten = _tool().replace_block(text, "x", "new 1\nnew 2")

    assert rewritten == "before\n<!-- index:x:start -->\nnew 1\nnew 2\n<!-- index:x:end -->\nafter\n"


@pytest.mark.parametrize(
    "text",
    [
        "no markers\n",
        "<!-- index:x:start -->\nbody\n",
        "<!-- index:x:start -->\n<!-- index:x:end -->\n<!-- index:x:start -->\n<!-- index:x:end -->\n",
        "<!-- index:x:end -->\nbody\n<!-- index:x:start -->\n",
    ],
)
def test_a_missing_or_repeated_marker_is_an_error(text: str) -> None:
    with pytest.raises(ValueError, match="needs one"):
        _tool().replace_block(text, "x", "body")


def test_a_stale_block_is_seen_and_the_line_endings_are_kept(tmp_path: Path) -> None:
    page = tmp_path / "README.md"
    page.write_bytes(b"a\r\n<!-- index:x:start -->\r\nold\r\n<!-- index:x:end -->\r\nb\r\n")
    tool = _tool()

    content = tool.render(page, [("x", lambda: "new")])

    assert content == "a\r\n<!-- index:x:start -->\r\nnew\r\n<!-- index:x:end -->\r\nb\r\n"
    assert content != page.read_bytes().decode("utf-8")
    assert tool.render(page.with_name("README.md"), [("x", lambda: "old")]) == page.read_bytes().decode()


def test_a_new_demo_appears_in_the_lists_without_any_hand_edit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = _tool()
    monkeypatch.setattr(tool, "EXAMPLES", tmp_path)
    (tmp_path / "datasets").mkdir()
    (tmp_path / "datasets" / "data.csv").write_text("a\n1\n", encoding="utf-8")
    (tmp_path / "datasets" / "README.md").write_text("x", encoding="utf-8")
    _write(
        tmp_path / "showcase" / "demo-one" / "demo.json",
        {"id": "demo-one", "tool": "report", "datasets": ["data.csv"],
         "publish": {"site": True, "docs": ["a/b.md"]}},
    )

    assert "| `showcase/demo-one/` | `report` | yes | `a/b.md` |" in tool.showcase_table()
    assert "| `data.csv` | `showcase/demo-one/` |" in tool.dataset_users()

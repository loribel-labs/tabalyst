# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Write the indexes of ``examples/`` from the manifests of the demos.

    python examples/tools/make_index.py            # rewrite the generated blocks
    python examples/tools/make_index.py --check    # change nothing; exit 1 if a block is stale

The lists of demos and dataset users in the READMEs are generated, never written by hand:
each sits between ``<!-- index:NAME:start -->`` and ``<!-- index:NAME:end -->`` and is rebuilt
from ``showcase/*/demo.json``. Run it from anywhere; it needs only
the standard library. ``regenerate.py`` runs it after the demos.
"""

import argparse
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

EXAMPLES = Path(__file__).resolve().parents[1]
Manifests = dict[str, dict[str, Any]]


def _manifests(pattern: str) -> Manifests:
    """The manifests matching ``pattern`` under ``examples/``, by id, in folder order."""
    found: Manifests = {}
    for path in sorted(EXAMPLES.glob(pattern)):
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        found[data["id"]] = data
    return found


def showcase_table() -> str:
    """Every demo, with the tool it shows, whether tabalyst.com copies it and the pages that quote it."""
    rows = ["| Demo | Tool | Copied by tabalyst.com | Quoted by |", "| --- | --- | --- | --- |"]
    for demo in _manifests("showcase/*/demo.json").values():
        publish = demo["publish"]
        pages = ", ".join(f"`{page}`" for page in publish["docs"]) or "none"
        site = "yes" if publish["site"] else "no"
        rows.append(f"| `showcase/{demo['id']}/` | `{demo['tool']}` | {site} | {pages} |")
    return "\n".join(rows)


def dataset_users() -> str:
    """For each file of ``datasets/``, the demos that read it."""
    demos = _manifests("showcase/*/demo.json")
    rows = ["| File | Used by |", "| --- | --- |"]
    for path in sorted((EXAMPLES / "datasets").iterdir()):
        if path.suffix == ".md":
            continue
        users = [f"`showcase/{d['id']}/`" for d in demos.values() if path.name in d["datasets"]]
        rows.append(f"| `{path.name}` | {', '.join(users) or 'none'} |")
    return "\n".join(rows)


# (file under examples/, block name, renderer)
BLOCKS: list[tuple[str, str, Callable[[], str]]] = [
    ("README.md", "showcase", showcase_table),
    ("datasets/README.md", "users", dataset_users),
]


def replace_block(text: str, name: str, body: str) -> str:
    """``text`` with the block ``name`` rewritten; raises ``ValueError`` if its markers are not
    there exactly once, in order, each on its own line."""
    start, end = f"<!-- index:{name}:start -->", f"<!-- index:{name}:end -->"
    pattern = re.compile(rf"^{re.escape(start)}\n.*?^{re.escape(end)}$", re.DOTALL | re.MULTILINE)
    if len(pattern.findall(text)) != 1 or text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(f"the block {name!r} needs one {start} line and one {end} line")
    return pattern.sub(lambda _: f"{start}\n{body}\n{end}", text)


def render(path: Path, wanted: list[tuple[str, Callable[[], str]]]) -> str:
    """The content ``path`` should have, with its line endings kept."""
    original = path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in original else "\n"
    text = original.replace("\r\n", "\n")
    for name, renderer in wanted:
        text = replace_block(text, name, renderer())
    return text.replace("\n", newline)


def stale_files() -> list[Path]:
    """The files whose generated blocks differ from what the manifests say."""
    stale: list[Path] = []
    for file in dict.fromkeys(item[0] for item in BLOCKS):
        path = EXAMPLES / file
        wanted = [(name, renderer) for f, name, renderer in BLOCKS if f == file]
        if render(path, wanted) != path.read_bytes().decode("utf-8"):
            stale.append(path)
    return stale


def main() -> int:
    """Rewrite the stale blocks, or only report them with ``--check`` (exit code 1)."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="change nothing; fail if stale")
    args = parser.parse_args()
    stale = stale_files()
    for path in stale:
        relative = path.relative_to(EXAMPLES.parent).as_posix()
        if args.check:
            sys.stderr.write(f"{relative}: the generated index is stale (run make_index.py)\n")
            continue
        wanted = [(n, r) for f, n, r in BLOCKS if f == path.relative_to(EXAMPLES).as_posix()]
        content = render(path, wanted)
        path.write_bytes(content.encode("utf-8"))
        sys.stdout.write(f"updated {relative}\n")
    return 1 if args.check and stale else 0


if __name__ == "__main__":
    sys.exit(main())

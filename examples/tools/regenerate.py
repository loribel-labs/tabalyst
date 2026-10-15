# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Regenerate the showcase demos from their ``examples/showcase/<id>/demo.json``.

    python examples/tools/regenerate.py            # every demo
    python examples/tools/regenerate.py basic sales
    python examples/tools/regenerate.py --list     # ids, tool and publication
    python examples/tools/regenerate.py --fresh    # restart executions.json

Run it from the repository root with Tabalyst installed. Each step of a manifest
is a ``tabalyst`` command line written relative to the repository root. A demo whose
``datasets`` names a generation request (``examples/datasets/*.json``, see
``make_datasets.py``) reads the generated file as ``{datasets}/<file>``: the request is built
first, outside the checkout, and ``{datasets}`` is replaced by its folder. When every step has
succeeded, ``make_index.py`` refreshes the generated lists of the examples READMEs.
"""

import argparse
import importlib.util
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SHOWCASE = ROOT / "examples" / "showcase"


def load_make_datasets() -> ModuleType:
    """The sibling tool that builds generated datasets."""
    script = Path(__file__).resolve().parent / "make_datasets.py"
    spec = importlib.util.spec_from_file_location("examples_make_datasets", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def update_index() -> None:
    """Refresh the generated lists of the examples READMEs (``make_index.py``)."""
    script = Path(__file__).resolve().parent / "make_index.py"
    subprocess.run([sys.executable, str(script)], check=True)


def prepare_datasets(demo: dict[str, Any]) -> str:
    """Build the generated datasets of a demo; return the folder that replaces ``{datasets}``."""
    tool = load_make_datasets()
    folder = tool.default_root()
    for name in demo["datasets"]:
        path = tool.DATASETS / name
        if tool.is_request(path):
            tool.ensure(path, folder)
    return str(folder.as_posix())


def load_demos() -> dict[str, dict[str, Any]]:
    """Every demo manifest, by id."""
    demos: dict[str, dict[str, Any]] = {}
    for manifest in sorted(SHOWCASE.glob("*/demo.json")):
        data: dict[str, Any] = json.loads(manifest.read_text(encoding="utf-8"))
        demos[data["id"]] = data
    return demos


def command_line(command: str) -> list[str]:
    """The argument list of a step, with ``tabalyst`` run as a module of this Python."""
    words = shlex.split(command)
    if words[0] != "tabalyst":
        raise ValueError(f"a step must start with tabalyst: {command}")
    return [sys.executable, "-m", "tabalyst", *words[1:]]


def clear_details(words: list[str]) -> None:
    """Delete the ``--details`` folder a report step is about to rewrite.

    The column pages are named after the column order, so a source whose columns moved would
    leave the pages of the old order beside the new ones.
    """
    if "--details" not in words or "-o" not in words:
        return
    output = (ROOT / words[words.index("-o") + 1]).resolve()
    folder = output.with_suffix("")
    if folder.is_dir() and folder.is_relative_to(SHOWCASE):
        shutil.rmtree(folder)


def run_step(step: dict[str, str], datasets: str = "") -> int:
    """Run one step from the repository root; ``stdout`` names a file to write.

    ``{datasets}`` in the command is replaced by the folder of the generated datasets.
    """
    sys.stdout.write(f"> {step['command']}\n")
    words = command_line(step["command"].replace("{datasets}", datasets))
    clear_details(words)
    completed = subprocess.run(
        words,
        cwd=ROOT,
        capture_output="stdout" in step,
        check=False,
    )
    if "stdout" in step:
        (ROOT / step["stdout"]).write_bytes(completed.stdout)
    return completed.returncode


def main() -> int:
    """Run the chosen demos; the exit code is the first failing step's."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("ids", nargs="*", help="demos to regenerate (default: all)")
    parser.add_argument("--list", action="store_true", help="list the demos and exit")
    parser.add_argument(
        "--fresh", action="store_true", help="delete executions.json first (a one-entry history)"
    )
    args = parser.parse_args()
    demos = load_demos()
    unknown = [name for name in args.ids if name not in demos]
    if unknown:
        parser.error(f"unknown demo: {', '.join(unknown)} (known: {', '.join(demos)})")
    if args.list:
        for demo in demos.values():
            site = "site" if demo["publish"]["site"] else "docs only"
            sys.stdout.write(f"{demo['id']}\t{demo['tool']}\t{site}\t{demo['title']}\n")
        return 0
    for name in args.ids or list(demos):
        if args.fresh:
            (SHOWCASE / name / "executions.json").unlink(missing_ok=True)
        datasets = prepare_datasets(demos[name])
        for step in demos[name]["steps"]:
            code = run_step(step, datasets)
            if code:
                sys.stderr.write(f"demo {name} failed with exit code {code}\n")
                return code
    update_index()
    return 0


if __name__ == "__main__":
    sys.exit(main())

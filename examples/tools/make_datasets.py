# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Build the generated datasets of ``examples/datasets/*.json`` outside the checkout.

    python examples/tools/make_datasets.py                  # every request
    python examples/tools/make_datasets.py insurance-customers-100k
    python examples/tools/make_datasets.py --list
    python examples/tools/make_datasets.py --update-sha     # after a deliberate generator change

A request names a ``tabalyst generate`` run (example, rows, seed, anomaly profile) and, for each
file it keeps, the file produced by the run and its SHA-256. The files are written under
``$TABALYST_DATASETS``, by default ``<repository parent>.test/tabalyst/datasets`` (for
``D:/GIT/tabalyst``: ``D:/GIT.test/tabalyst/datasets``), never in the checkout: the 100,000-row
base is 27 MB. A file already there with the expected SHA-256 is reused.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATASETS = ROOT / "examples" / "datasets"


def default_root() -> Path:
    """Where generated datasets live: ``$TABALYST_DATASETS`` or the external test root."""
    configured = os.environ.get("TABALYST_DATASETS")
    if configured:
        return Path(configured)
    external = ROOT.parent.with_name(ROOT.parent.name + ".test")
    return external / ROOT.name / "datasets"


def is_request(path: Path) -> bool:
    """Whether a JSON file of ``examples/datasets`` is a generation request."""
    if path.suffix != ".json":
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and "generate" in data


def requests() -> dict[str, Path]:
    """Every generation request, by id."""
    found: dict[str, Path] = {}
    for path in sorted(DATASETS.glob("*.json")):
        if is_request(path):
            found[json.loads(path.read_text(encoding="utf-8"))["id"]] = path
    return found


def sha256(path: Path) -> str:
    """SHA-256 of a file, read in blocks."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _generate(spec: dict[str, Any], destination: Path) -> None:
    command = [
        sys.executable, "-m", "tabalyst", "generate", "--example", spec["example"],
        "--rows", str(spec["rows"]), "--seed", str(spec["seed"]), "-d", str(destination),
    ]
    if "anomaly_profile" in spec:
        command += ["--anomaly-profile", spec["anomaly_profile"]]
    done = subprocess.run(command, capture_output=True, text=True, check=False)
    if done.returncode:
        raise RuntimeError(f"tabalyst generate failed:\n{done.stderr}")


def ensure(request: Path, root: Path | None = None, update_sha: bool = False) -> dict[str, Path]:
    """Return the files of a request by name, generating them when missing or changed.

    Raises ``RuntimeError`` when a generated file does not match its SHA-256 and
    ``update_sha`` is false: the generator changed, or the Python minor version differs
    (the bytes are only guaranteed for one), and the request must be reviewed.
    """
    data: dict[str, Any] = json.loads(request.read_text(encoding="utf-8"))
    target = root or default_root()
    files: dict[str, dict[str, str]] = data["files"]
    paths = {name: target / name for name in files}
    if all(path.is_file() and sha256(path) == files[name]["sha256"] for name, path in paths.items()):
        return paths
    target.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f".{data['id']}-", dir=target))
    try:
        _generate(data["generate"], work)
        for name, spec in files.items():
            produced = work / spec["from"]
            digest = sha256(produced)
            if digest != spec["sha256"]:
                if not update_sha:
                    raise RuntimeError(
                        f"{name}: SHA-256 {digest} differs from the expected {spec['sha256']}; "
                        "review the generator change, then run with --update-sha"
                    )
                spec["sha256"] = digest
            shutil.move(str(produced), paths[name])
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if update_sha:
        request.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
    return paths


def main() -> int:
    """Build the chosen requests and print where the files are."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("ids", nargs="*", help="requests to build (default: all)")
    parser.add_argument("--list", action="store_true", help="list the requests and exit")
    parser.add_argument("--root", type=Path, help="directory of the generated files")
    parser.add_argument("--update-sha", action="store_true", help="rewrite the expected SHA-256")
    args = parser.parse_args()
    known = requests()
    unknown = [name for name in args.ids if name not in known]
    if unknown:
        parser.error(f"unknown request: {', '.join(unknown)} (known: {', '.join(known)})")
    if args.list:
        for name, path in known.items():
            sys.stdout.write(f"{name}\t{path.relative_to(ROOT).as_posix()}\n")
        return 0
    for name in args.ids or list(known):
        try:
            paths = ensure(known[name], args.root, args.update_sha)
        except RuntimeError as error:
            sys.stderr.write(f"{error}\n")
            return 1
        for path in paths.values():
            sys.stdout.write(f"{path}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Add or check the MPL-2.0 header of the source files.

    python scripts/license_headers.py          # add the missing headers
    python scripts/license_headers.py --check  # list files without a header
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BODY = (
    "This Source Code Form is subject to the terms of the Mozilla Public",
    "License, v. 2.0. If a copy of the MPL was not distributed with this",
    "file, You can obtain one at https://mozilla.org/MPL/2.0/.",
)
MARKER = "Mozilla Public"
LINE_COMMENT = {".py": "# ", ".js": "// ", ".cjs": "// "}
BLOCK_COMMENT = {".css"}
ROOTS = ("src", "tests", "benchmarks", "scripts")


def header(suffix: str) -> str:
    if suffix in BLOCK_COMMENT:
        return "/*\n" + "\n".join(f" * {line}" for line in BODY) + "\n */\n"
    prefix = LINE_COMMENT[suffix]
    return "".join(f"{prefix}{line}\n" for line in BODY)


def source_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", *ROOTS],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    suffixes = set(LINE_COMMENT) | BLOCK_COMMENT
    return [ROOT / p for p in out if Path(p).suffix in suffixes and (ROOT / p).exists()]


def has_header(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    return MARKER in "\n".join(text.splitlines()[:8])


def add_header(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    block = header(path.suffix)
    lead = ""
    if path.suffix == ".py":
        lines = text.splitlines(keepends=True)
        while lines and (lines[0].startswith("#!") or "coding" in lines[0][:20]):
            lead += lines.pop(0)
        text = "".join(lines)
    path.write_text(lead + block + ("\n" + text if text else ""), encoding="utf-8")


def missing() -> list[Path]:
    return [p for p in source_files() if not has_header(p)]


def main(argv: list[str]) -> int:
    todo = missing()
    if "--check" in argv:
        for path in todo:
            print(path.relative_to(ROOT))
        return 1 if todo else 0
    for path in todo:
        add_header(path)
    print(f"{len(todo)} header(s) added")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""File synchronization and the single same-filesystem manifest replacement.

Directory fsync is supported on POSIX local filesystems. Windows supports
file synchronization here, but no power-loss directory durability is claimed.
"""

import os
import tempfile
from pathlib import Path


def sync_file(path: Path) -> None:
    # Windows _commit requires a descriptor with write access.
    with path.open("r+b") as stream:
        os.fsync(stream.fileno())


def sync_directory(path: Path) -> bool:
    if os.name == "nt":
        return False
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return True


def replace_manifest(path: Path, text: str) -> None:
    descriptor, name = tempfile.mkstemp(
        dir=path.parent, prefix=".project.json.", suffix=".tmp"
    )
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)  # the only commit point
        sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)

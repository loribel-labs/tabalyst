# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Private resource policy for generation readers and disposable queries."""

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from tabalyst.projects._cache import (
    _safe_stat,
    create_query_directory,
    dispose_query_directory,
)


@dataclass(frozen=True)
class QueryBudget:
    # DuckDB limits each database instance, not the entire Python process.
    # A value query uses a reader and a separate materializer. Connections
    # to the same generation can share its instance; Scan has its own budgets.
    memory_bytes: int = 256 * 1024 * 1024
    spill_bytes: int = 1024 * 1024 * 1024
    batch_rows: int = 2048
    batch_bytes: int = 4 * 1024 * 1024

    def __post_init__(self):
        for name in ("memory_bytes", "spill_bytes", "batch_rows", "batch_bytes"):
            value = getattr(self, name)
            if type(value) is not int or value < (0 if name == "spill_bytes" else 1):
                raise ValueError(f"Invalid query budget {name}")

    def config(self, spill: Path) -> dict:
        return {
            "enable_external_access": False,
            "threads": 1,
            "memory_limit": f"{self.memory_bytes}B",
            "max_temp_directory_size": f"{self.spill_bytes}B",
            # Zero disables spilling independently of quota initialization.
            "temp_directory": str(spill) if self.spill_bytes else "",
            "default_collation": "binary",
            "preserve_insertion_order": False,
        }


def apply_spill_limit(connection, limit: str) -> bool:
    """Apply the runtime quota before any query; return whether spill is enabled.

    In DuckDB 1.5.5 the connect option can report the requested quota without
    initializing the temporary manager's limit. The runtime SET is required.
    Its accounting also differs from Windows file lengths (no truncation).
    """
    connection.execute("SET max_temp_directory_size = ?", [limit])
    enabled = (
        connection.execute(
            "SELECT current_setting('max_temp_directory_size')"
        ).fetchone()[0]
        != "0 bytes"
    )
    if (
        not enabled
        and connection.execute("SELECT current_setting('temp_directory')").fetchone()[0]
    ):
        connection.execute("SET temp_directory=''")
    return enabled


@contextmanager
def query_directory(project_dir: Path, generation_id: str):
    """Only remove the fresh directory owned by this operation, never a cache root."""
    cache = project_dir / "cache" / generation_id
    created = [p for p in (cache.parent, cache) if not p.exists()]
    path, location = create_query_directory(project_dir, generation_id)
    parents = [(p, _safe_stat(p)) for p in created]
    try:
        yield path
    finally:
        dispose_query_directory(path, location)
        for path, original in reversed(parents):
            try:
                current = _safe_stat(path)
                if (current.st_dev, current.st_ino) != (original.st_dev, original.st_ino):
                    continue
                path.rmdir()  # empty only; preserve unrelated/concurrent caches
            except (OSError, ValueError):
                pass

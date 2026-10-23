# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The exact row store on disk: a temporary SQLite table keyed by the whole row key."""

import contextlib
import errno
import shutil
import sqlite3
import tempfile
import weakref
from collections.abc import Callable, Iterable
from pathlib import Path

from tabalyst.dedup.failures import DedupReportError
from tabalyst.dedup.store import Occurrence

MIB = 1 << 20

# Free space that must stay on the temporary volume, over what the run itself needs.
MIN_FREE_BYTES = 64 * MIB

# Operations between two commits. The database is disposable (no journal, no sync), so
# a commit only bounds the size of the pending pages, never the durability.
COMMIT_INTERVAL = 100_000

# Page cache given to SQLite while the memory table is still alive (design dedup 8.5).
MIGRATION_CACHE_BYTES = 16 * MIB

# Entries per ``executemany`` during the migration from memory.
_LOAD_BATCH = 50_000

# The digests of the optional accelerator are non-negative 63-bit integers.
_DIGEST_MASK = (1 << 63) - 1

# SQLite 3.35 added ``RETURNING``; with an older library the store uses two statements.
_RETURNING_SUPPORTED = sqlite3.sqlite_version_info >= (3, 35, 0)

_SCHEMA_PLAIN = (
    "CREATE TABLE rows (key BLOB PRIMARY KEY, count INTEGER NOT NULL, "
    "first INTEGER NOT NULL) WITHOUT ROWID"
)
_SCHEMA_DIGEST = (
    "CREATE TABLE rows (h INTEGER NOT NULL, key BLOB NOT NULL, count INTEGER NOT NULL, "
    "first INTEGER NOT NULL, PRIMARY KEY (h, key)) WITHOUT ROWID"
)


class SqliteRowStore:
    """Counts whole row keys in a temporary SQLite database (ADR exact store, 3).

    The primary key is the whole canonical key, so equality never rests on a digest.
    ``digest`` is an optional accelerator: the table is then ordered by the digest
    first and compares keys only among equal digests, which stays exact whatever the
    function returns (a constant one only makes it slow). The database lives in a
    private folder created under ``directory`` and deleted by ``close()``, by garbage
    collection and at exit.

    Raises ``DedupReportError`` with ``storage_unavailable`` when ``directory`` or the
    database is unusable, and ``insufficient_disk_space`` when the volume has less
    than ``MIN_FREE_BYTES`` plus ``reserve_bytes`` free, or fills up during the run.
    """

    storage_mode = "disk"

    def __init__(
        self,
        directory: Path,
        *,
        digest: Callable[[bytes], int] | None = None,
        cache_bytes: int = MIGRATION_CACHE_BYTES,
        reserve_bytes: int = 0,
    ) -> None:
        self._digest = digest
        self._closed = True
        self._distinct = 0
        self._pending = 0
        self._last_size = 0
        self._growth = 0
        try:
            self._folder = Path(tempfile.mkdtemp(prefix="tabalyst-dedup-", dir=directory))
        except OSError as exc:
            raise storage_failure(exc) from exc
        self._path = self._folder / "rows.sqlite"
        try:
            self._conn = sqlite3.connect(self._path, isolation_level=None)
        except sqlite3.Error as exc:
            _discard(None, self._folder)
            raise storage_failure(exc) from exc
        self._finalizer = weakref.finalize(self, _discard, self._conn, self._folder)
        try:
            self._ensure_space(reserve_bytes)
            self._configure(cache_bytes)
        except BaseException:
            self._finalizer()
            raise
        self._closed = False
        self._observe = (
            self._observe_returning if _RETURNING_SUPPORTED else self._observe_two_statements
        )

    def _configure(self, cache_bytes: int) -> None:
        try:
            execute = self._conn.execute
            # The page size must be chosen before the first table exists.
            execute("PRAGMA page_size = 16384")
            execute("PRAGMA journal_mode = OFF")
            execute("PRAGMA synchronous = OFF")
            execute("PRAGMA locking_mode = EXCLUSIVE")
            self.set_cache_bytes(cache_bytes)
            execute(_SCHEMA_PLAIN if self._digest is None else _SCHEMA_DIGEST)
            if self._digest is None:
                self._sql_upsert = (
                    "INSERT INTO rows (key, count, first) VALUES (?, 1, ?) "
                    "ON CONFLICT (key) DO UPDATE SET count = count + 1 RETURNING count, first"
                )
            else:
                self._sql_upsert = (
                    "INSERT INTO rows (h, key, count, first) VALUES (?, ?, 1, ?) "
                    "ON CONFLICT (h, key) DO UPDATE SET count = count + 1 "
                    "RETURNING count, first"
                )
        except sqlite3.Error as exc:
            raise storage_failure(exc) from exc

    @property
    def distinct(self) -> int:
        """Number of distinct keys stored."""
        return self._distinct

    def __len__(self) -> int:
        return self._distinct

    @property
    def disk_bytes(self) -> int:
        """Size of the database file; it grows by pages as the keys arrive."""
        return self._path.stat().st_size

    def set_cache_bytes(self, cache_bytes: int) -> None:
        """Bound the page cache of the connection (the memory the store may hold)."""
        try:
            self._conn.execute(f"PRAGMA cache_size = {-max(cache_bytes // 1024, 1)}")
        except sqlite3.Error as exc:
            raise storage_failure(exc) from exc

    def observe(self, key: bytes, position: int) -> Occurrence:
        """Insert ``key`` with count 1 at ``position``, or count one more occurrence."""
        if self._closed:
            raise RuntimeError("the row store is closed")
        try:
            if not self._pending:
                self._conn.execute("BEGIN")
            occurrence = self._observe(key, position)
            self._pending += 1
            if self._pending >= COMMIT_INTERVAL:
                self._commit()
        except (sqlite3.Error, OSError) as exc:
            raise storage_failure(exc) from exc
        if occurrence.count == 1:
            self._distinct += 1
        return occurrence

    def _observe_returning(self, key: bytes, position: int) -> Occurrence:
        digest = self._digest
        if digest is None:
            row = self._conn.execute(self._sql_upsert, (key, position)).fetchone()
        else:
            row = self._conn.execute(
                self._sql_upsert, (digest(key) & _DIGEST_MASK, key, position)
            ).fetchone()
        return Occurrence(row[0], row[1])

    def _observe_two_statements(self, key: bytes, position: int) -> Occurrence:
        digest = self._digest
        execute = self._conn.execute
        ident: tuple[object, ...] = (key,)
        where = "key = ?"
        if digest is not None:
            where, ident = "h = ? AND key = ?", (digest(key) & _DIGEST_MASK, key)
        found = execute(f"SELECT count, first FROM rows WHERE {where}", ident).fetchone()
        if found is None:
            if digest is None:
                execute("INSERT INTO rows (key, count, first) VALUES (?, 1, ?)", (key, position))
            else:
                execute(
                    "INSERT INTO rows (h, key, count, first) VALUES (?, ?, 1, ?)",
                    (*ident, position),
                )
            return Occurrence(1, position)
        count = found[0] + 1
        execute(f"UPDATE rows SET count = ? WHERE {where}", (count, *ident))
        return Occurrence(count, found[1])

    def load(self, entries: Iterable[tuple[bytes, Occurrence]]) -> None:
        """Insert entries of distinct keys that the store does not hold yet.

        This is the migration from the memory table: it keeps counts and first
        positions as they are and does not look for an existing key.
        """
        if self._closed:
            raise RuntimeError("the row store is closed")
        digest = self._digest
        batch: list[tuple[object, ...]] = []
        try:
            for key, (count, first) in entries:
                row: tuple[object, ...] = (key, count, first)
                if digest is not None:
                    row = (digest(key) & _DIGEST_MASK, *row)
                batch.append(row)
                if len(batch) >= _LOAD_BATCH:
                    self._load_batch(batch)
                    batch.clear()
                    self._commit()
            self._load_batch(batch)
            if self._pending:
                self._commit()
        except (sqlite3.Error, OSError) as exc:
            raise storage_failure(exc) from exc

    def _load_batch(self, batch: list[tuple[object, ...]]) -> None:
        if not batch:
            return
        if not self._pending:
            self._conn.execute("BEGIN")
        if self._digest is None:
            sql = "INSERT INTO rows (key, count, first) VALUES (?, ?, ?)"
        else:
            sql = "INSERT INTO rows (h, key, count, first) VALUES (?, ?, ?, ?)"
        self._conn.executemany(sql, batch)
        self._distinct += len(batch)
        self._pending += len(batch)

    def _commit(self) -> None:
        """End the transaction, then check that the volume still has room to grow."""
        self._conn.execute("COMMIT")
        self._pending = 0
        size = self.disk_bytes
        self._growth = max(size - self._last_size, 0)
        self._last_size = size
        self._ensure_space(self._growth)

    def _ensure_space(self, reserve_bytes: int) -> None:
        try:
            free = shutil.disk_usage(self._folder).free
        except OSError as exc:
            raise storage_failure(exc) from exc
        if free < MIN_FREE_BYTES + reserve_bytes:
            raise DedupReportError(
                "The temporary folder does not have enough free space to keep going "
                f"({free // MIB:,} MiB free, {(MIN_FREE_BYTES + reserve_bytes) // MIB:,} MiB "
                "needed). Free some space or pass --temp-dir on a larger volume.",
                reason="insufficient_disk_space",
            )

    def close(self) -> None:
        """Close the database and delete its folder; any later use raises ``RuntimeError``."""
        self._closed = True
        self._finalizer()


def storage_failure(exc: BaseException) -> DedupReportError:
    """The Dedup failure for an ``OSError`` or ``sqlite3.Error`` of the temporary storage.

    The message names the cause without a path, so it can go into an exported report.
    """
    if _is_disk_full(exc):
        return DedupReportError(
            "The temporary disk is full. Free some space or pass --temp-dir on a "
            "larger volume.",
            reason="insufficient_disk_space",
        )
    detail = exc.strerror if isinstance(exc, OSError) and exc.strerror else str(exc)
    return DedupReportError(
        f"The temporary storage is unusable ({type(exc).__name__}: {detail}).",
        reason="storage_unavailable",
    )


def _is_disk_full(exc: BaseException) -> bool:
    if isinstance(exc, OSError):
        return exc.errno in {errno.ENOSPC, errno.EDQUOT}
    return isinstance(exc, sqlite3.OperationalError) and "full" in str(exc).lower()


def _discard(conn: sqlite3.Connection | None, folder: Path) -> None:
    """Close the connection, then delete the folder: Windows keeps an open file."""
    if conn is not None:
        with contextlib.suppress(sqlite3.Error):
            conn.close()
    shutil.rmtree(folder, ignore_errors=True)

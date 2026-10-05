# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""OS-backed local workspace locks, independent of lock-file existence/PIDs.

POSIX uses flock; Windows uses LockFileEx over one byte, including shared
maintenance locks. Locks are nonblocking and released when handles/processes
close. Never unlink lock files: another process may already hold their inode.
"""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from functools import wraps
from pathlib import Path

from tabalyst.errors import ReportError


class ProjectBusyError(ReportError):
    """A cooperating workspace reader, writer or maintenance operation is busy."""


_held = threading.local()


def _windows_lock(descriptor: int, *, exclusive: bool) -> None:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    class Overlapped(ctypes.Structure):
        _fields_ = [
            ("Internal", ctypes.c_size_t),
            ("InternalHigh", ctypes.c_size_t),
            ("Offset", wintypes.DWORD),
            ("OffsetHigh", wintypes.DWORD),
            ("hEvent", wintypes.HANDLE),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    lock = kernel.LockFileEx
    lock.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(Overlapped),
    ]
    lock.restype = wintypes.BOOL
    overlap = Overlapped()
    if not lock(
        msvcrt.get_osfhandle(descriptor),
        1 | (2 if exclusive else 0),
        0,
        1,
        0,
        ctypes.byref(overlap),
    ):
        error = ctypes.get_last_error()
        if error == 33:  # ERROR_LOCK_VIOLATION
            raise ProjectBusyError("Workspace lock is busy")
        raise ctypes.WinError(error)
    # CloseHandle via os.close releases this synchronous lock. No asynchronous
    # operation retains the stack-local OVERLAPPED structure.


@contextmanager
def _file_lock(path: Path, *, exclusive: bool):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if os.name == "nt":
            _windows_lock(descriptor, exclusive=exclusive)
        elif os.name == "posix":
            import fcntl

            try:
                fcntl.flock(
                    descriptor,
                    (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB,
                )
            except BlockingIOError as exc:
                raise ProjectBusyError("Workspace lock is busy") from exc
        else:
            raise ReportError("Workspace locking is unsupported on this platform")
        yield
    finally:
        os.close(descriptor)


def _workspace_key(location) -> str:
    return os.path.normcase(str(location.workspace_dir.resolve()))


@contextmanager
def workspace_reader(location):
    """Pin a manifest/generation against maintenance; never needs writer lock."""
    with _file_lock(location.maintenance_lock_path, exclusive=False):
        yield


@contextmanager
def workspace_writer(location):
    """Shared maintenance, then exclusive writer; nested writes on one thread reuse it."""
    held = getattr(_held, "writers", None)
    if held is None:
        held = _held.writers = set()
    key = _workspace_key(location)
    if key in held:
        yield
        return
    with (
        workspace_reader(location),
        _file_lock(location.writer_lock_path, exclusive=True),
    ):
        held.add(key)
        try:
            yield
        finally:
            held.remove(key)


@contextmanager
def workspace_maintenance(location):
    """Exclusive maintenance before writer: proves no cooperating handles remain."""
    if _workspace_key(location) in getattr(_held, "writers", set()):
        raise ProjectBusyError("Cannot upgrade an active writer to maintenance")
    with (
        _file_lock(location.maintenance_lock_path, exclusive=True),
        _file_lock(location.writer_lock_path, exclusive=True),
    ):
        yield


def locked_writer(function):
    """Apply the same lock discipline to every legacy mutating entry point."""

    @wraps(function)
    def guarded(location, *args, **kwargs):
        with workspace_writer(location):
            return function(location, *args, **kwargs)

    return guarded

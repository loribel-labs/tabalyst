# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Worker processes that process the values of fields in parallel (design 13).

A parallel scan keeps reading, frequency tables, budgets and diagnostics in
the scan process, and hands the per-value work of each field to one worker
process: a released table, then its streaming batches in reading order, or a
complete table at the end. A worker processes the values of a field exactly
as the scan process would (``values.ValueProcessor``), so results are
identical. Workers return the value blocks of their fields as plain data;
the scan process reports their diagnostics in field order, so diagnostic
indices do not depend on which worker finished first.

Workers are subprocesses of the running interpreter that exchange pickled
messages on their standard streams: unlike ``multiprocessing``, starting them
never imports the caller's main module again.
"""

from __future__ import annotations

import json
import os
import pickle
import queue
import struct
import subprocess
import sys
import threading
import time
import traceback
from collections.abc import Callable
from typing import BinaryIO

from pydantic import BaseModel

# Sources smaller than this are scanned in one process: starting workers
# costs more than it saves.
MIN_PARALLEL_BYTES = 16 << 20
MAX_WORKERS = 8
# Messages waiting to be written to one worker; beyond them, the scan waits.
OUTBOX_SIZE = 8
# Bytes of a worker's standard error kept for error messages.
STDERR_TAIL = 16_384
# Seconds to wait for every worker to be ready before scanning in one process.
START_TIMEOUT = 30
_HEADER = struct.Struct("<Q")
_PATH_VARIABLE = "TABALYST_WORKER_PATH"
_BOOTSTRAP = (
    "import json, os, sys; "
    f"sys.path[:0] = json.loads(os.environ[{_PATH_VARIABLE!r}]); "
    "from tabalyst.scanner.workers import main; main()"
)


def worker_count(requested: int | None, size: int) -> int:
    """Worker processes for a source of ``size`` bytes: ``requested`` when
    given, where 1 scans in one process; otherwise one per spare processor,
    at most ``MAX_WORKERS``, for sources of at least ``MIN_PARALLEL_BYTES``."""
    if getattr(sys, "frozen", False) or not sys.executable:
        return 1
    if requested is not None:
        return max(1, requested)
    if size < MIN_PARALLEL_BYTES:
        return 1
    return max(1, min((os.cpu_count() or 1) - 1, MAX_WORKERS))


def _write(stream: BinaryIO, payload: bytes) -> None:
    stream.write(_HEADER.pack(len(payload)))
    stream.write(payload)
    stream.flush()


def _read(stream: BinaryIO) -> object | None:
    """The next message, or ``None`` at the end of the stream."""
    header = stream.read(_HEADER.size)
    if len(header) < _HEADER.size:
        return None
    (size,) = _HEADER.unpack(header)
    payload = stream.read(size)
    if len(payload) < size:
        return None
    return pickle.loads(payload)


class WorkerError(RuntimeError):
    """A worker process failed; the scan cannot complete."""


class _Worker:
    """One worker process, with a thread writing its messages and a thread
    reading its replies into the pool's queue."""

    def __init__(self, index: int, config: str, replies: queue.Queue) -> None:
        self.index = index
        self.failure: str | None = None
        self.outbox: queue.Queue[bytes | None] = queue.Queue(OUTBOX_SIZE)
        # The worker imports Tabalyst as this process does.
        path = json.dumps([str(entry) for entry in sys.path])
        environment = {**os.environ, _PATH_VARIABLE: path}
        self.process = subprocess.Popen(
            [sys.executable, "-c", _BOOTSTRAP],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.stderr = b""
        self._threads = [
            threading.Thread(target=self._write_loop, daemon=True),
            threading.Thread(target=self._read_loop, args=(replies,), daemon=True),
            threading.Thread(target=self._error_loop, daemon=True),
        ]
        for thread in self._threads:
            thread.start()
        self.send(pickle.dumps(config, protocol=pickle.HIGHEST_PROTOCOL))

    def send(self, payload: bytes) -> None:
        while True:
            if self.failure is not None:
                raise WorkerError(self.failure)
            try:
                self.outbox.put(payload, timeout=0.5)
                return
            except queue.Full:
                continue

    def _write_loop(self) -> None:
        stdin = self.process.stdin
        try:
            while True:
                payload = self.outbox.get()
                if payload is None:
                    break
                _write(stdin, payload)
        except OSError as exc:
            self._fail(f"cannot send work to scan worker {self.index}: {exc}")
        finally:
            try:
                stdin.close()
            except OSError:
                pass

    def _read_loop(self, replies: queue.Queue) -> None:
        stdout = self.process.stdout
        try:
            while True:
                message = _read(stdout)
                if message is None:
                    break
                replies.put((self.index, message))
        except (OSError, pickle.UnpicklingError, EOFError) as exc:
            self._fail(f"cannot read scan worker {self.index}: {exc}")
        replies.put((self.index, None))

    def _error_loop(self) -> None:
        stderr = self.process.stderr
        try:
            while chunk := stderr.read(4096):
                self.stderr = (self.stderr + chunk)[-STDERR_TAIL:]
        except OSError:
            pass

    def _fail(self, message: str) -> None:
        if self.failure is None:
            self.failure = message
        # Unblock a scan waiting for room in the outbox.
        try:
            while True:
                self.outbox.get_nowait()
        except queue.Empty:
            pass

    def describe_exit(self) -> str:
        code = self.process.poll()
        detail = self.stderr.decode("utf-8", "replace").strip()
        message = f"Scan worker {self.index} stopped unexpectedly (exit code {code})."
        return f"{message}\n{detail}" if detail else message

    def stop(self) -> None:
        try:
            self.outbox.put_nowait(None)
        except queue.Full:
            self._fail("stopped")
            self.outbox.put_nowait(None)
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        for stream in (self.process.stdout, self.process.stderr):
            try:
                stream.close()
            except OSError:
                pass


class WorkerPool:
    """Worker processes of one parallel scan.

    Each field is processed by one worker; tables go to the worker with the
    fewest values to process so far.
    """

    def __init__(self, config_json: str, count: int) -> None:
        self._config = config_json
        self._count = count
        self._workers: list[_Worker] = []
        self._load = [0] * count
        self._replies: queue.Queue = queue.Queue()
        self._results: dict[int, tuple[dict, list]] = {}

    def start(self, timeout: float = START_TIMEOUT) -> bool:
        """Start the workers and wait until each is ready; ``False``, the pool
        closed, when they cannot run: the scan then stays in one process."""
        try:
            for index in range(self._count):
                self._workers.append(_Worker(index, self._config, self._replies))
        except (OSError, ValueError, subprocess.SubprocessError):
            self.close()
            return False
        deadline = time.monotonic() + timeout
        for _ in range(self._count):
            try:
                _, message = self._replies.get(
                    timeout=max(0.0, deadline - time.monotonic())
                )
            except queue.Empty:
                message = None
            if message != ("ready",):
                self.close()
                return False
        return True

    def _send(self, index: int, message: tuple, values: int) -> None:
        self._load[index] += values
        self._workers[index].send(
            pickle.dumps(message, protocol=pickle.HIGHEST_PROTOCOL)
        )

    def _least_loaded(self) -> int:
        return min(range(self._count), key=self._load.__getitem__)

    def release(
        self, field: int, keys: list, counts: list, limited, scalars: bool
    ) -> int:
        """Start processing a released table; returns the worker of the field."""
        index = self._least_loaded()
        limit = (limited.reason, limited.limit, limited.lower_bound)
        self._send(index, ("release", field, keys, counts, limit, scalars), len(keys))
        return index

    def process(
        self, index: int, field: int, keys: list, counts: list, scalars: bool
    ) -> None:
        """A streaming batch of a released field."""
        self._send(index, ("batch", field, keys, counts, scalars), len(keys))

    def finish(self, index: int, field: int, ends: tuple) -> None:
        """Finalize a released field, after its last batch."""
        self._send(index, ("finish", field, ends), 0)

    def table(
        self, field: int, keys: list, counts: list, ends: tuple, scalars: bool
    ) -> int:
        """Finalize a field from its complete table; returns its worker."""
        index = self._least_loaded()
        self._send(index, ("table", field, keys, counts, ends, scalars), len(keys))
        return index

    def result(
        self,
        field: int,
        report_failure: Callable[[str, str], int],
        report_probe: Callable[[str, int, int], int] | None,
    ) -> dict:
        """The value blocks of a field, its diagnostics reported now, in the
        order the worker met them."""
        while field not in self._results:
            self._receive()
        blocks, events = self._results.pop(field)
        indices = []
        for kind, detector, detail in events:
            if kind == "failure":
                indices.append(report_failure(detector, detail))
            else:
                indices.append(
                    None if report_probe is None else report_probe(detector, *detail)
                )
        return _with_diagnostics(blocks, indices)

    def _receive(self) -> None:
        index, message = self._replies.get()
        worker = self._workers[index]
        if message is None:
            raise WorkerError(worker.failure or worker.describe_exit())
        if message[0] == "error":
            raise WorkerError(f"Scan worker {index} failed:\n{message[1]}")
        _, field, blocks, events = message
        self._results[field] = (blocks, events)

    def close(self) -> None:
        workers, self._workers = self._workers, []
        for worker in workers:
            worker.stop()


def _with_diagnostics(blocks: dict, indices: list) -> dict:
    """Replace the placeholder diagnostic indices of a worker, ``-1`` for its
    first diagnostic, ``-2`` for the next one, with the reported ones."""

    def actual(value):
        return indices[-value - 1] if value is not None and value < 0 else value

    for result in blocks["detectors"]:
        if result.get("diagnostic") is not None:
            result["diagnostic"] = actual(result["diagnostic"])
        adaptive = result.get("adaptive")
        if adaptive is not None:
            adaptive["diagnostic"] = actual(adaptive["diagnostic"])
    temporal = blocks["temporal"]
    if isinstance(temporal, dict) and temporal.get("diagnostic") is not None:
        temporal["diagnostic"] = actual(temporal["diagnostic"])
    return blocks


def _plain(value: object) -> object:
    """Pydantic models as plain data: parametrized generic models cannot be
    pickled, and the scan process validates the data again."""
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def main() -> None:
    """Entry point of a worker process."""
    from tabalyst.scanner.config import ScanConfig
    from tabalyst.scanner.detectors.registry import DetectorSet, default_registry
    from tabalyst.scanner.models import Limited
    from tabalyst.scanner.values import ValueContext, ValueProcessor

    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    config = ScanConfig.model_validate_json(_read(stdin))
    context = ValueContext(config, DetectorSet(default_registry(), config))
    processors: dict[int, ValueProcessor] = {}
    _write(stdout, pickle.dumps(("ready",), pickle.HIGHEST_PROTOCOL))

    def finalize(field: int, processor, table, ends, scalars: bool) -> None:
        events: list[tuple[str, str, object]] = []

        def failure(detector: str, error: str) -> int:
            events.append(("failure", detector, error))
            return -len(events)

        def probe(detector: str, count: int, warmup_reactions: int) -> int:
            events.append(("probe", detector, (count, warmup_reactions)))
            return -len(events)

        blocks = processor.finalize(table, ends, failure, probe, scalars)
        plain = {key: _plain(value) for key, value in blocks.items()}
        reply = pickle.dumps(("done", field, plain, events), pickle.HIGHEST_PROTOCOL)
        _write(stdout, reply)

    try:
        while (message := _read(stdin)) is not None:
            kind, field = message[0], message[1]
            if kind == "batch":
                _, _, keys, counts, scalars = message
                processors[field].process(keys, counts, scalars=scalars)
            elif kind == "release":
                _, _, keys, counts, (reason, limit, bound), scalars = message
                processor = processors[field] = ValueProcessor(context)
                limited = Limited(reason=reason, limit=limit, lower_bound=bound)
                processor.release(keys, counts, limited, scalars)
            elif kind == "finish":
                _, _, ends = message
                finalize(field, processors.pop(field), None, ends, False)
            elif kind == "table":
                _, _, keys, counts, ends, scalars = message
                table = dict(zip(keys, counts, strict=True))
                finalize(field, ValueProcessor(context), table, ends, scalars)
    except KeyboardInterrupt:
        return
    except BaseException:  # noqa: BLE001 - reported to the scan process
        reply = pickle.dumps(("error", traceback.format_exc()), pickle.HIGHEST_PROTOCOL)
        try:
            _write(stdout, reply)
        except OSError:
            pass

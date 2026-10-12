# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The field routes of the second pass, run in worker processes (design 20.18).

A worker holds routes, counts the column of each batch it is sent in reading order and
returns the accumulators; the results do not depend on the number of workers.
"""

from __future__ import annotations

import pickle
import queue
import subprocess
import sys
import time
import traceback
from collections.abc import Iterable, Sequence

from tabalyst.errors import TabalystError
from tabalyst.scanner.config import ScanConfig
from tabalyst.scanner.planner.costmodel import NS_PER_CELL
from tabalyst.scanner.secondpass.accumulators import (
    BinAccumulator,
    DenseAccumulator,
    LengthAccumulator,
)
from tabalyst.scanner.secondpass.duplicates import DuplicateAccumulator
from tabalyst.scanner.secondpass.frequencies import FrequencyAccumulator
from tabalyst.scanner.secondpass.measures import MeasureAccumulator
from tabalyst.scanner.secondpass.parts import PartsAccumulator
from tabalyst.scanner.secondpass.patterns import PatternAccumulator
from tabalyst.scanner.secondpass.periods import PeriodAccumulator
from tabalyst.scanner.secondpass.replay import CellReader
from tabalyst.scanner.secondpass.residuals import ResidualAccumulator
from tabalyst.scanner.secondpass.routing import FieldRoute
from tabalyst.scanner.secondpass.shape import ShapeAccumulator
from tabalyst.scanner.workers import (
    START_TIMEOUT,
    WorkerError,
    _read,
    _Worker,
    _write,
)

# The members of a route that hold an accumulator, in the order a worker returns them.
PARTS = (
    "numeric",
    "lengths",
    "frequencies",
    "patterns",
    "periods",
    "parts",
    "measures",
    "shape",
    "residuals",
    "duplicates",
)
# The module and function a worker of the second pass runs.
ENTRY = ("tabalyst.scanner.secondpass.parallel", "serve")
# Reading a cell, its count and the grouping of a column, whatever the analyses.
BASE_NS_PER_CELL = 400


class SecondPassWorkerError(TabalystError):
    """A worker of the second pass failed; the pass cannot complete."""


def part_name(accumulator: object) -> str:
    """The member of a route that holds ``accumulator``."""
    if isinstance(accumulator, LengthAccumulator):
        return "lengths"
    if isinstance(accumulator, FrequencyAccumulator):
        return "frequencies"
    if isinstance(accumulator, PatternAccumulator):
        return "patterns"
    if isinstance(accumulator, PeriodAccumulator):
        return "periods"
    if isinstance(accumulator, PartsAccumulator):
        return "parts"
    if isinstance(accumulator, MeasureAccumulator):
        return "measures"
    if isinstance(accumulator, ShapeAccumulator):
        return "shape"
    if isinstance(accumulator, ResidualAccumulator):
        return "residuals"
    if isinstance(accumulator, DuplicateAccumulator):
        return "duplicates"
    assert isinstance(accumulator, DenseAccumulator | BinAccumulator)
    return "numeric"


def route_weight(route: FieldRoute) -> int:
    """Modeled nanoseconds a cell of the field costs its route: how the routes
    are shared out between the workers."""
    weight = BASE_NS_PER_CELL
    if route.numeric is not None:
        weight += NS_PER_CELL["bin" if isinstance(route.numeric, BinAccumulator) else "dense_counter"]
    if route.lengths is not None:
        weight += NS_PER_CELL["length_counter"]
    if route.frequencies is not None:
        weight += NS_PER_CELL["table"]
    if route.periods is not None:
        weight += NS_PER_CELL["period"]
    if route.parts is not None:
        weight += route.parts.cell_ns
    if route.patterns is not None:
        weight += NS_PER_CELL["matcher_base"]
    if route.measures is not None:
        weight += route.measures.cell_ns
    if route.shape is not None:
        weight += route.shape.cell_ns
    if route.residuals is not None:
        weight += route.residuals.cell_ns
    return weight


class RemoteRoute:
    """What the router sees of a route that a worker holds: it takes the column
    of a batch and sends it. The count of values and the failure of the route
    are known when the workers have finished."""

    __slots__ = ("failure", "pool", "rid", "values", "worker")

    def __init__(self, pool: SecondPassWorkers, worker: int, rid: int) -> None:
        self.pool = pool
        self.worker = worker
        self.rid = rid
        self.failure: str | None = None
        self.values = 0

    def strings(self, column: list[str], start: int = 1) -> None:
        self.pool.add(self.worker, self.rid, column, start)

    def string(self, value: str, record: int = 1) -> None:  # pragma: no cover - CSV batches only
        raise NotImplementedError("a remote route takes the columns of a batch")

    def native(  # pragma: no cover
        self, native_type: str, value: object, record: int = 1
    ) -> None:
        raise NotImplementedError("a remote route takes the columns of a batch")


class SecondPassWorkers:
    """Worker processes that hold field routes of one second pass."""

    def __init__(self, config_json: str, count: int) -> None:
        self._config = config_json
        self._count = count
        self._workers: list[_Worker] = []
        self._replies: queue.Queue = queue.Queue()
        self._pending: list[list[tuple[int, list[str], int]]] = [[] for _ in range(count)]
        self._next = 0

    @property
    def count(self) -> int:
        """Worker processes of the pool."""
        return self._count

    def start(self, timeout: float = START_TIMEOUT) -> bool:
        """Start the workers and wait until each is ready; ``False``, the pool
        closed, when they cannot run: the second pass then stays in one process."""
        try:
            for index in range(self._count):
                self._workers.append(_Worker(index, self._config, self._replies, ENTRY))
        except (OSError, ValueError, subprocess.SubprocessError):
            self.close()
            return False
        deadline = time.monotonic() + timeout
        for _ in range(self._count):
            try:
                _, message = self._replies.get(timeout=max(0.0, deadline - time.monotonic()))
            except queue.Empty:
                message = None
            if message != ("ready",):
                self.close()
                return False
        return True

    def place(self, routes: Sequence[FieldRoute]) -> list[RemoteRoute]:
        """Send each route to a worker, the heaviest first to the least loaded
        (the same assignment for the same routes), and return the stand-ins in
        the order of ``routes``."""
        load = [0] * self._count
        order = sorted(range(len(routes)), key=lambda i: (-route_weight(routes[i]), i))
        remotes: list[RemoteRoute | None] = [None] * len(routes)
        for position in order:
            route = routes[position]
            worker = min(range(self._count), key=lambda w: (load[w], w))
            load[worker] += route_weight(route)
            rid = self._next
            self._next += 1
            parts: dict[str, object] = {
                name: getattr(route, name) for name in PARTS if getattr(route, name) is not None
            }
            self._send(worker, ("setup", rid, parts, route.memo_entries))
            remotes[position] = RemoteRoute(self, worker, rid)
        return [remote for remote in remotes if remote is not None]

    def add(self, worker: int, rid: int, column: list[str], start: int) -> None:
        """Queue the column of a route, whose first record is ``start``, for the
        next message of its worker."""
        self._pending[worker].append((rid, column, start))

    def flush(self) -> None:
        """Send each worker the columns queued for it, one message each. The
        router calls it after every batch, so a route that was left out of a
        batch (its column could not be cut) holds nothing back."""
        for worker, pending in enumerate(self._pending):
            if pending:
                self._pending[worker] = []
                self._send(worker, ("batch", pending))

    def finish(
        self, remotes: Iterable[RemoteRoute]
    ) -> dict[int, tuple[dict[str, object], str | None, int]]:
        """The accumulators, failure and count of values of every route, once the
        workers have read everything they were sent."""
        self.flush()
        for worker in range(self._count):
            self._send(worker, ("finish",))
        results: dict[int, tuple[dict[str, object], str | None, int]] = {}
        for _ in range(self._count):
            index, message = self._replies.get()
            if message is None:
                worker = self._workers[index]
                raise SecondPassWorkerError(worker.failure or worker.describe_exit())
            if message[0] == "error":
                raise SecondPassWorkerError(f"Second pass worker {index} failed:\n{message[1]}")
            results.update(message[1])
        wanted = {remote.rid for remote in remotes}
        missing = wanted - results.keys()
        if missing:
            raise SecondPassWorkerError("a second pass worker returned no result for a route")
        return results

    def _send(self, worker: int, message: tuple) -> None:
        try:
            self._workers[worker].send(pickle.dumps(message, protocol=pickle.HIGHEST_PROTOCOL))
        except WorkerError as exc:
            raise SecondPassWorkerError(str(exc)) from exc

    def close(self) -> None:
        workers, self._workers = self._workers, []
        for worker in workers:
            worker.stop()


def serve() -> None:
    """Entry point of a worker of the second pass."""
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    config = ScanConfig.model_validate_json(_read(stdin))
    cells = CellReader(config)
    routes: dict[int, FieldRoute] = {}
    _write(stdout, pickle.dumps(("ready",), pickle.HIGHEST_PROTOCOL))
    try:
        while (message := _read(stdin)) is not None:
            assert isinstance(message, tuple)
            kind = message[0]
            if kind == "setup":
                _, rid, parts, memo_entries = message
                route = FieldRoute(cells, parts.get("numeric"), parts.get("lengths"))
                route.frequencies = parts.get("frequencies")
                route.patterns = parts.get("patterns")
                route.periods = parts.get("periods")
                route.parts = parts.get("parts")
                route.measures = parts.get("measures")
                route.shape = parts.get("shape")
                route.residuals = parts.get("residuals")
                route.duplicates = parts.get("duplicates")
                route.memo_entries = memo_entries
                routes[rid] = route
            elif kind == "batch":
                for rid, column, start in message[1]:
                    route = routes[rid]
                    if route.failure is not None:
                        continue
                    try:
                        route.strings(column, start)
                    except Exception as exc:  # noqa: BLE001 - one field fails alone
                        route.failure = type(exc).__name__
            elif kind == "finish":
                done = {
                    rid: (
                        {n: getattr(r, n) for n in PARTS if getattr(r, n) is not None},
                        r.failure,
                        r.values,
                    )
                    for rid, r in routes.items()
                }
                _write(stdout, pickle.dumps(("done", done), pickle.HIGHEST_PROTOCOL))
    except KeyboardInterrupt:
        return
    except BaseException:  # noqa: BLE001 - reported to the process that asked
        reply = pickle.dumps(("error", traceback.format_exc()), pickle.HIGHEST_PROTOCOL)
        try:
            _write(stdout, reply)
        except OSError:
            pass

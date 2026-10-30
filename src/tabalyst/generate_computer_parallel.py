# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Render Computer rows in worker processes, one span of row numbers at a time.

Every row depends only on its number and the request, so the output is the same
whatever the number of workers: each span is rendered to its own part files and
the parts are appended to the final CSVs in row order.
"""

from __future__ import annotations

import csv
import os
import pickle
import queue
import shutil
import sys
import traceback
from collections.abc import Callable, Mapping
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import BinaryIO

from tabalyst.errors import ConfigurationError, ReportError
from tabalyst.generate_computer import derive_computer_row
from tabalyst.generate_computer_output import render_computer_row
from tabalyst.generate_package import DatasetPackage, load_generate_package
from tabalyst.generate_selection import select_catalog_row
from tabalyst.scanner.workers import WorkerError, _read, _Worker, _write

MAX_WORKERS = 6
# Below this, starting the workers costs more than it saves.
MIN_PARALLEL_ROWS = 5_000
MIN_SPAN = 1_000
MAX_SPAN = 25_000
# Spans sent to a worker ahead of the one it is rendering, so it never waits.
SPANS_IN_FLIGHT = 2
# The module and function a worker runs.
ENTRY = ("tabalyst.generate_computer_parallel", "serve")


@dataclass(frozen=True)
class SpanSettings:
    """What a worker needs to render any span of rows of one request."""

    package_root: Path
    dataset_id: str
    seed: int
    as_of_date: date
    generation_profile: str
    output_profile: str
    market: str
    unit_style: str
    selected_units: tuple[str, ...]
    locales: tuple[str, ...]
    columns: tuple[str, ...]
    directory: Path


def worker_count(requested: int | None, rows: int) -> int:
    """Worker processes for ``rows`` rows: ``requested`` when given, where 1 renders
    in the calling process; otherwise one per spare processor, at most ``MAX_WORKERS``,
    from ``MIN_PARALLEL_ROWS`` rows."""
    if getattr(sys, "frozen", False) or not sys.executable:
        return 1
    if requested is not None:
        return max(1, requested)
    if rows < MIN_PARALLEL_ROWS:
        return 1
    return max(1, min((os.cpu_count() or 1) - 1, MAX_WORKERS))


def _part(settings: SpanSettings, start: int, locale: str) -> Path:
    return settings.directory / f"{start}-{locale}.csv"


def render_span(package: DatasetPackage, settings: SpanSettings, start: int, stop: int) -> None:
    """Write the rows ``start`` to ``stop`` of every locale as header-less part files."""
    with ExitStack() as stack:
        writers = {}
        for locale in settings.locales:
            stream = stack.enter_context(
                _part(settings, start, locale).open("w", encoding="utf-8", newline=""))
            writers[locale] = csv.DictWriter(stream, fieldnames=settings.columns,
                                             extrasaction="raise", lineterminator="\n")
        for index in range(start, stop):
            selected = select_catalog_row(package, settings.dataset_id, settings.seed,
                                          index, settings.generation_profile)
            internal = derive_computer_row(package, selected, settings.dataset_id,
                                           settings.seed, index, settings.as_of_date,
                                           settings.market)
            for locale in settings.locales:
                writers[locale].writerow(render_computer_row(
                    package, internal, locale, settings.output_profile,
                    settings.unit_style, settings.selected_units,
                ))


def serve() -> None:
    """Entry point of a worker: read the settings, then render the spans it is sent."""
    stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
    settings = _read(stdin)
    assert isinstance(settings, SpanSettings)
    package = load_generate_package(settings.package_root)
    while (message := _read(stdin)) is not None:
        assert isinstance(message, tuple)
        start, stop = int(message[0]), int(message[1])
        try:
            render_span(package, settings, start, stop)
            reply: tuple[object, ...] = ("done", start)
        except Exception as exc:  # noqa: BLE001 - any failure is reported to the calling process, which stops the run
            reply = ("error", type(exc).__name__, str(exc) or traceback.format_exc())
        _write(stdout, pickle.dumps(reply))


def span_size(rows: int, workers: int) -> int:
    """About eight spans per worker, so progress moves and the load stays even."""
    return min(MAX_SPAN, max(MIN_SPAN, -(-rows // (workers * 8))))


def append_parts(settings: SpanSettings, start: int, streams: Mapping[str, BinaryIO]) -> None:
    """Append the part files of a span to the final CSVs and delete them."""
    for locale, stream in streams.items():
        part = _part(settings, start, locale)
        with part.open("rb") as source:
            shutil.copyfileobj(source, stream)
        part.unlink()


def write_rows(settings: SpanSettings, rows: int, workers: int,
               streams: Mapping[str, BinaryIO], on_rows: Callable[[int], None] | None) -> None:
    """Render ``rows`` rows with ``workers`` processes and append them to ``streams`` in order.

    ``on_rows`` receives the rows appended so far, after each span.
    Raises ConfigurationError when a row cannot be selected, ReportError when a worker fails.
    """
    size = span_size(rows, workers)
    spans = [(start, min(start + size, rows)) for start in range(0, rows, size)]
    replies: queue.Queue[tuple[int, object]] = queue.Queue()
    pool = [_Worker(index, settings, replies, ENTRY)  # type: ignore[arg-type]
            for index in range(min(workers, len(spans)))]
    upcoming = iter(spans)

    def feed(worker: _Worker) -> None:
        span = next(upcoming, None)
        if span is not None:
            worker.send(pickle.dumps(span, protocol=pickle.HIGHEST_PROTOCOL))

    try:
        for worker in pool:
            for _ in range(SPANS_IN_FLIGHT):
                feed(worker)
        finished: set[int] = set()
        appended = 0
        if on_rows is not None:
            on_rows(0)
        while appended < len(spans):
            index, message = replies.get()
            if message is None:
                raise ReportError(pool[index].failure or pool[index].describe_exit().replace(
                    "Scan worker", "Generate worker"))
            if not isinstance(message, tuple):
                raise ReportError("Generate worker sent an unexpected reply.")
            if message[0] == "error":
                name, text = str(message[1]), str(message[2])
                if name == "ConfigurationError":
                    raise ConfigurationError(text)
                raise ReportError(f"Generate worker failed: {name}: {text}")
            finished.add(int(message[1]))
            feed(pool[index])
            while appended < len(spans) and spans[appended][0] in finished:
                append_parts(settings, spans[appended][0], streams)
                appended += 1
                if on_rows is not None:
                    on_rows(spans[appended - 1][1])
    except WorkerError as exc:
        raise ReportError(f"Generate worker failed: {exc}") from exc
    finally:
        for worker in pool:
            worker.stop()

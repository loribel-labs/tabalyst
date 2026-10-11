# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Routing of the one common reading to the fields that analyses need
(PASS2-03).

Every record is parsed once by the reader; only the selected fields are handed
to their analyses. A CSV file still has to be scanned to its separators, which
this cannot avoid. A field whose analysis raises stops receiving values and
fails alone, with the type of the exception and never its message.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Sequence

from tabalyst.scanner.models import (
    ColumnSegment,
    ItemsSegment,
    KeySegment,
    PathSegment,
)
from tabalyst.scanner.observations import (
    DatasetOpened,
    Record,
    RecordBatch,
    StreamItem,
)
from tabalyst.scanner.paths import ITEMS, Column, FieldPath, Key, Segment
from tabalyst.scanner.planner.costmodel import PAIR_FEED_ROWS, REPLAY_MEMO_ENTRIES
from tabalyst.scanner.secondpass.accumulators import (
    BinAccumulator,
    DenseAccumulator,
    LengthAccumulator,
)
from tabalyst.scanner.secondpass.crosstab import CodeFeed, CrosstabAccumulator
from tabalyst.scanner.secondpass.exactset import ExactSet
from tabalyst.scanner.secondpass.frequencies import FrequencyAccumulator
from tabalyst.scanner.secondpass.patterns import PatternAccumulator
from tabalyst.scanner.secondpass.pearson import ColumnFeed, PairAccumulator
from tabalyst.scanner.secondpass.periods import PeriodAccumulator
from tabalyst.scanner.secondpass.replay import Cell, CellReader, native_number

# The columns of the pairs and tables, converted once whatever the number of
# analyses that read them, and the analyses that read two of them.
Feed = ColumnFeed | CodeFeed
PairLike = PairAccumulator | CrosstabAccumulator


def field_path(segments: Iterable[PathSegment]) -> FieldPath:
    """The path of a field of the Scan, as the readers write it."""
    path: list[Segment] = []
    for segment in segments:
        if isinstance(segment, KeySegment):
            path.append(Key(segment.key))
        elif isinstance(segment, ItemsSegment):
            path.append(ITEMS)
        elif isinstance(segment, ColumnSegment):
            path.append(Column(segment.column))
    return tuple(path)


class FieldRoute:
    """The analyses that read one field and the way they read it: one reading
    of each raw string, shared by all of them."""

    __slots__ = (
        "distinct",
        "failure",
        "frequencies",
        "lengths",
        "memo",
        "memo_entries",
        "numeric",
        "patterns",
        "periods",
        "reader",
        "values",
    )

    def __init__(
        self,
        reader: CellReader,
        numeric: DenseAccumulator | BinAccumulator | None,
        lengths: LengthAccumulator | None,
    ) -> None:
        self.reader = reader
        self.numeric = numeric
        self.lengths = lengths
        # The exact set of the original values and the table of the analytical
        # ones: set by the executor when an analysis of the field needs them.
        self.distinct: ExactSet | None = None
        self.frequencies: FrequencyAccumulator | None = None
        # The patterns count original values (design 21); the periods read the
        # analytical text with the date detector.
        self.patterns: PatternAccumulator | None = None
        self.periods: PeriodAccumulator | None = None
        self.memo: dict[str, Cell] = {}
        # Raw strings remembered per field across batches. A column of few distinct
        # values (the case where remembering pays) fits; one of identifiers does
        # not, and the batch's own count of distinct strings serves it as well.
        # The planner charges that many entries to each field it reads; the
        # dates, which repeat, remember many more (``PERIOD_MEMO_ENTRIES``).
        self.memo_entries = REPLAY_MEMO_ENTRIES
        self.failure: str | None = None
        # Values handed to the analyses, for the cells counted by the run.
        self.values = 0

    def strings(self, column: list[str]) -> None:
        """Account for the raw strings of consecutive records of the field."""
        self.values += len(column)
        self._counted(Counter(column))

    def string(self, value: str) -> None:
        self.values += 1
        self._counted({value: 1})

    def _counted(self, counts: dict[str, int]) -> None:
        lengths = self.lengths
        numeric = self.numeric
        frequencies = self.frequencies
        distinct = self.distinct
        patterns = self.patterns
        periods = self.periods
        if lengths is None and numeric is None and frequencies is None and periods is None:
            # Only the original values: no analytical text, no number.
            if distinct is not None or patterns is not None:
                raws = list(counts)
                wanted = [raw for raw, ok in zip(raws, self.reader.content(raws), strict=True) if ok]
                weights = [counts[raw] for raw in wanted]
                if distinct is not None:
                    distinct.add_strings(wanted, weights)
                if patterns is not None:
                    patterns.add_strings(wanted, weights)
            return
        memo = self.memo
        cells: dict[str, Cell] = {}
        missing: list[str] = []
        for raw in counts:
            cell = memo.get(raw)
            if cell is None:
                missing.append(raw)
            else:
                cells[raw] = cell
        if missing:
            room = self.memo_entries - len(memo)
            read = self.reader.cells(
                missing, numbers=numeric is not None, dates=periods is not None
            )
            for raw, cell in zip(missing, read, strict=True):
                cells[raw] = cell
                if room > 0:
                    memo[raw] = cell
                    room -= 1
        for raw, count in counts.items():
            length, number, _, _ = cells[raw]
            if length < 0:
                continue
            if lengths is not None:
                lengths.add(length, count)
            if numeric is not None and number is not None:
                numeric.add(number, count)
        if frequencies is not None:
            for raw, count in counts.items():
                cell = cells[raw]
                if cell.length >= 0:
                    frequencies.add_text(cell.text, count)
        if periods is not None:
            for raw, count in counts.items():
                cell = cells[raw]
                if cell.length >= 0:
                    periods.add(cell.moment, count)
        if distinct is not None or patterns is not None:
            wanted = [raw for raw in counts if cells[raw].length >= 0]
            weights = [counts[raw] for raw in wanted]
            if distinct is not None:
                distinct.add_strings(wanted, weights)
            if patterns is not None:
                patterns.add_strings(wanted, weights)

    def native(self, native_type: str, value: object) -> None:
        """A JSON integer, number or boolean: a numeric value (but for a
        boolean), and no text. A boolean only matters to the analyses of the
        values themselves."""
        if (
            native_type == "boolean"
            and self.distinct is None
            and self.frequencies is None
            and self.patterns is None
        ):
            return
        self.values += 1
        if self.numeric is not None and native_type != "boolean":
            self.numeric.add(native_number(native_type, value), 1)
        if self.distinct is not None:
            self.distinct.add_native(native_type, value)
        if self.frequencies is not None:
            self.frequencies.add_native(native_type, value)
        if self.patterns is not None:
            self.patterns.add_native()


class Router:
    """Feeds the routes from the items a reader streams, and the pairs of
    columns from the rows they have in common.

    A column of a pair has one ``ColumnFeed`` however many pairs use it
    (REL-03): a batch of strings is converted once and handed to each pair, and
    the records of a JSON or Excel source are buffered into rows of
    ``PAIR_FEED_ROWS`` before they are.
    """

    def __init__(
        self,
        routes: dict[tuple[str, FieldPath], FieldRoute],
        feeds: dict[tuple[str, FieldPath, str], Feed] | None = None,
        pairs: Sequence[tuple[str, PairLike]] = (),
        after_batch: Callable[[], None] | None = None,
    ) -> None:
        # Called when every route has had the column of a batch: the routes of
        # worker processes send what they were given.
        self.after_batch = after_batch
        self.routes: dict[str, dict[FieldPath, FieldRoute]] = {}
        for (dataset, path), route in routes.items():
            self.routes.setdefault(dataset, {})[path] = route
        self.feeds: dict[str, dict[FieldPath, list[Feed]]] = {}
        for (dataset, path, _), feed in (feeds or {}).items():
            self.feeds.setdefault(dataset, {}).setdefault(path, []).append(feed)
        self.pairs: dict[str, list[PairLike]] = {}
        for dataset, pair in pairs:
            self.pairs.setdefault(dataset, []).append(pair)
        self.records_read = 0
        self._columns: dict[str, list[tuple[int, FieldRoute]]] = {}
        self._feed_columns: dict[str, list[tuple[int, Feed]]] = {}
        self._buffered: dict[str, int] = {}

    @property
    def cells_read(self) -> int:
        fed = sum(
            feed.values
            for paths in self.feeds.values()
            for feeds in paths.values()
            for feed in feeds
        )
        return fed + sum(
            route.values for fields in self.routes.values() for route in fields.values()
        )

    def consume(self, items: Iterable[StreamItem]) -> None:
        for item in items:
            kind = type(item)
            if kind is RecordBatch:
                self._batch(item)
            elif kind is Record:
                self._record(item)
            elif kind is DatasetOpened:
                self._open(item)
        for dataset in self.pairs:
            self._flush(dataset)

    def _open(self, item: DatasetOpened) -> None:
        wanted = self.routes.get(item.dataset, {})
        self._columns[item.dataset] = [
            (index, wanted[declared.path])
            for index, declared in enumerate(item.fields)
            if declared.path in wanted
        ]
        feeds = self.feeds.get(item.dataset, {})
        self._feed_columns[item.dataset] = [
            (index, feed)
            for index, declared in enumerate(item.fields)
            for feed in feeds.get(declared.path, ())
        ]

    def _batch(self, batch: RecordBatch) -> None:
        self.records_read += len(batch.rows)
        for index, route in self._columns.get(batch.dataset, ()):
            if route.failure is not None:
                continue
            try:
                route.strings([row[index] for row in batch.rows])
            except Exception as exc:  # noqa: BLE001 - one field fails alone
                route.failure = type(exc).__name__
        columns = self._feed_columns.get(batch.dataset)
        if columns:
            converted: dict[int, Sequence[float | None] | Sequence[int]] = {}
            for index, feed in columns:
                if feed.failure is not None:
                    continue
                try:
                    converted[id(feed)] = feed.convert(
                        [row[index] for row in batch.rows], batch.start
                    )
                except Exception as exc:  # noqa: BLE001 - one column fails with its pairs
                    feed.failure = type(exc).__name__
            self._hand(batch.dataset, lambda feed: converted.get(id(feed)))
        if self.after_batch is not None:
            self.after_batch()

    def _hand(
        self,
        dataset: str,
        rows_of: Callable[[Feed], Sequence[float | None] | Sequence[int] | None],
    ) -> None:
        """Give each pair the aligned rows of its two columns. A pair whose
        column failed is left as it was: its job fails when it is concluded."""
        for pair in self.pairs.get(dataset, ()):
            if pair.failure is not None:
                continue
            first, second = rows_of(pair.first), rows_of(pair.second)
            if first is None or second is None:
                continue
            try:
                pair.add(first, second)  # type: ignore[arg-type]
            except Exception as exc:  # noqa: BLE001 - one pair fails alone
                pair.failure = type(exc).__name__

    def _record(self, record: Record) -> None:
        self.records_read += 1
        fields = self.routes.get(record.dataset)
        feeds = self.feeds.get(record.dataset)
        if not fields and not feeds:
            return
        for observation in record.observations:
            route = fields.get(observation.path) if fields else None
            native_type = observation.type
            if route is not None and route.failure is None:
                try:
                    if native_type == "string":
                        route.string(observation.value)  # type: ignore[arg-type]
                    elif native_type in ("integer", "number", "boolean"):
                        route.native(native_type, observation.value)
                except Exception as exc:  # noqa: BLE001 - one field fails alone
                    route.failure = type(exc).__name__
            for feed in feeds.get(observation.path, ()) if feeds else ():
                if feed.failure is not None or feed.seen:
                    continue
                try:
                    if native_type == "string":
                        feed.push_string(observation.value)  # type: ignore[arg-type]
                    elif native_type in ("integer", "number", "boolean"):
                        feed.push_native(native_type, observation.value)
                except Exception as exc:  # noqa: BLE001 - one column fails with its pairs
                    feed.failure = type(exc).__name__
        if feeds:
            for column in feeds.values():
                for feed in column:
                    feed.end_record(record.index)
            count = self._buffered.get(record.dataset, 0) + 1
            self._buffered[record.dataset] = count
            if count >= PAIR_FEED_ROWS:
                self._flush(record.dataset)

    def _flush(self, dataset: str) -> None:
        """Hand the buffered rows of a record-at-a-time dataset to its pairs."""
        feeds = self.feeds.get(dataset)
        if not feeds or not self._buffered.get(dataset):
            return
        self._hand(dataset, lambda feed: feed.rows if feed.failure is None else None)
        for column in feeds.values():
            for feed in column:
                feed.reset()
        self._buffered[dataset] = 0

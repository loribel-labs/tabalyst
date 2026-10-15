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
from functools import partial
from typing import TYPE_CHECKING, TypeAlias

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
from tabalyst.scanner.secondpass.characters import CharacterAccumulator
from tabalyst.scanner.secondpass.crosstab import CodeFeed, CrosstabAccumulator
from tabalyst.scanner.secondpass.drift import DriftAccumulator
from tabalyst.scanner.secondpass.duplicates import (
    DuplicateAccumulator,
    KeyAccumulator,
    RawFeed,
)
from tabalyst.scanner.secondpass.exactset import ExactSet
from tabalyst.scanner.secondpass.forms import FormsAccumulator
from tabalyst.scanner.secondpass.frequencies import FrequencyAccumulator
from tabalyst.scanner.secondpass.measures import MeasureAccumulator
from tabalyst.scanner.secondpass.parts import PartsAccumulator
from tabalyst.scanner.secondpass.patterns import PatternAccumulator
from tabalyst.scanner.secondpass.pearson import ColumnFeed, PairAccumulator
from tabalyst.scanner.secondpass.periods import PeriodAccumulator
from tabalyst.scanner.secondpass.replay import Cell, CellReader, native_number
from tabalyst.scanner.secondpass.residuals import ResidualAccumulator
from tabalyst.scanner.secondpass.shape import ShapeAccumulator
from tabalyst.scanner.secondpass.stats import StatsAccumulator
from tabalyst.scanner.secondpass.structure import ArrayAccumulator
from tabalyst.scanner.secondpass.texts import FingerprintAccumulator, TextAccumulator

if TYPE_CHECKING:
    # The matrix and the sets of keys read the field paths this module defines.
    from tabalyst.scanner.secondpass.matrix import MatrixAccumulator
    from tabalyst.scanner.secondpass.orders import OrderAccumulator
    from tabalyst.scanner.secondpass.structure import StructureAccumulator

    # The accumulators that read the rows of a dataset on their own: the records that
    # miss a value together and the order of two dates.
    RowAccumulator: TypeAlias = MatrixAccumulator | OrderAccumulator

# The columns of the pairs and tables, converted once whatever the number of
# analyses that read them, and the analyses that read two of them.
Feed = ColumnFeed | CodeFeed | RawFeed
PairLike = PairAccumulator | CrosstabAccumulator | KeyAccumulator | StatsAccumulator
# The aligned rows of a column: floats, codes or strings.
Rows = Sequence[float | None] | Sequence[int] | Sequence[str | None]


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


def _first_record(column: list[str], start: int) -> Callable[[str], int]:
    """The record of the first occurrence of a string in ``column``, numbered
    from ``start``. The index of the column is built once, on the first call:
    most batches have nothing to quote."""
    index: dict[str, int] = {}

    def first(raw: str) -> int:
        if not index:
            # The last assignment wins, so walking backward keeps the first one.
            index.update(zip(reversed(column), range(len(column) - 1, -1, -1), strict=True))
        return start + index[raw]

    return first


def _date_order(periods: PeriodAccumulator | None, parts: PartsAccumulator | None) -> bool | str:
    """What the date detector is asked for the field: nothing, its ordinary
    reading or the order its ambiguous dates are read in (the same for the
    analyses of one field, since it follows from the Scan)."""
    order = (periods or parts).order if periods is not None or parts is not None else None  # type: ignore[union-attr]
    return order or (periods is not None or parts is not None)


class FieldRoute:
    """The analyses that read one field and the way they read it: one reading
    of each raw string, shared by all of them."""

    __slots__ = (
        "arrays",
        "characters",
        "distinct",
        "drift",
        "duplicates",
        "failure",
        "fingerprints",
        "forms",
        "frequencies",
        "lengths",
        "measures",
        "memo",
        "memo_entries",
        "numeric",
        "parts",
        "patterns",
        "periods",
        "reader",
        "residuals",
        "shape",
        "texts",
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
        # The parts of the dates read the same detector classification.
        self.parts: PartsAccumulator | None = None
        # The values with a unit read the analytical text with their detector.
        self.measures: MeasureAccumulator | None = None
        # The shape of the numbers reads the same numbers as the histogram.
        self.shape: ShapeAccumulator | None = None
        # The values that patterns and detectors leave out (original values for
        # the pattern, the analytical text for the detectors).
        self.residuals: ResidualAccumulator | None = None
        # The repeated values of an identifier (original values).
        self.duplicates: DuplicateAccumulator | None = None
        # The values and the missing ones by slice of records (analytical text).
        self.drift: DriftAccumulator | None = None
        # The lengths of the arrays of a field (JSON).
        self.arrays: ArrayAccumulator | None = None
        # The words, lines and digits of the original texts, and the fingerprints
        # of the original values.
        self.texts: TextAccumulator | None = None
        self.fingerprints: FingerprintAccumulator | None = None
        # The masks of the analytical values of a sensitive field, without a value.
        self.forms: FormsAccumulator | None = None
        self.characters: CharacterAccumulator | None = None
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

    def strings(self, column: list[str], start: int = 1) -> None:
        """Account for the raw strings of consecutive records of the field,
        numbered from ``start``."""
        self.values += len(column)
        drift = self.drift
        if drift is None:
            self._counted(Counter(column), column, start)
            return
        # The records of a slice are counted together, so a batch that crosses
        # the end of a slice is cut there.
        for low, high in drift.segments(start, len(column)):
            part = column[low:high]
            self._counted(Counter(part), part, start + low)

    def string(self, value: str, record: int = 1) -> None:
        self.values += 1
        self._counted({value: 1}, [value], record)

    def array(self, length: int) -> None:
        """An array of ``length`` items (JSON)."""
        arrays = self.arrays
        if arrays is not None:
            self.values += 1
            arrays.add(length)

    def _counted(self, counts: dict[str, int], column: list[str], start: int) -> None:
        lengths = self.lengths
        numeric = self.numeric
        frequencies = self.frequencies
        distinct = self.distinct
        patterns = self.patterns
        periods = self.periods
        parts = self.parts
        measures = self.measures
        shape = self.shape
        residuals = self.residuals
        duplicates = self.duplicates
        drift = self.drift
        texts = self.texts
        fingerprints = self.fingerprints
        forms = self.forms
        characters = self.characters
        text_wanted = (residuals is not None and residuals.needs_text) or (
            drift is not None and drift.needs_text
        )
        first = (
            _first_record(column, start)
            if residuals is not None or duplicates is not None
            else None
        )
        if (
            lengths is None
            and numeric is None
            and frequencies is None
            and periods is None
            and parts is None
            and measures is None
            and shape is None
            and not text_wanted
        ):
            # Only the original values: no analytical text, no number.
            if (
                distinct is not None
                or patterns is not None
                or residuals is not None
                or duplicates is not None
                or drift is not None
                or texts is not None
                or fingerprints is not None
                or forms is not None
                or characters is not None
            ):
                raws = list(counts)
                wanted = [raw for raw, ok in zip(raws, self.reader.content(raws), strict=True) if ok]
                weights = [counts[raw] for raw in wanted]
                if drift is not None:
                    drift.add_presence(start, sum(weights))
                if distinct is not None:
                    distinct.add_strings(wanted, weights)
                if patterns is not None:
                    patterns.add_strings(wanted, weights)
                if residuals is not None:
                    residuals.add(self.reader, wanted, weights, None, first)
                if duplicates is not None:
                    duplicates.add_strings(wanted, weights, first)
                if texts is not None:
                    texts.add_strings(wanted, weights)
                if fingerprints is not None:
                    fingerprints.add_strings(wanted, weights)
                if forms is not None:
                    forms.add_strings(self.reader, wanted, weights)
                if characters is not None:
                    characters.add_strings(wanted, weights)
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
                missing,
                numbers=numeric is not None or shape is not None,
                dates=_date_order(periods, parts),
                measure=None if measures is None else measures.detector,
                convention=None if measures is None else measures.convention,
            )
            for raw, cell in zip(missing, read, strict=True):
                cells[raw] = cell
                if room > 0:
                    memo[raw] = cell
                    room -= 1
        for raw, count in counts.items():
            length, number, _, _, _ = cells[raw]
            if length < 0:
                continue
            if lengths is not None:
                lengths.add(length, count)
            if number is not None:
                if numeric is not None:
                    numeric.add(number, count)
                if shape is not None:
                    shape.add(number, count)
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
        if parts is not None:
            for raw, count in counts.items():
                cell = cells[raw]
                if cell.length >= 0:
                    parts.add(cell.moment, cell.text, count)
        if measures is not None:
            for raw, count in counts.items():
                cell = cells[raw]
                if cell.length >= 0:
                    measures.add(cell.measure, count)
        if (
            distinct is not None
            or patterns is not None
            or residuals is not None
            or duplicates is not None
            or drift is not None
            or texts is not None
            or fingerprints is not None
            or forms is not None
            or characters is not None
        ):
            wanted = [raw for raw in counts if cells[raw].length >= 0]
            weights = [counts[raw] for raw in wanted]
            if drift is not None:
                if drift.track:
                    for raw, weight in zip(wanted, weights, strict=True):
                        drift.add_text(start, cells[raw].text, weight)
                else:
                    drift.add_presence(start, sum(weights))
            if distinct is not None:
                distinct.add_strings(wanted, weights)
            if patterns is not None:
                patterns.add_strings(wanted, weights)
            if residuals is not None:
                residuals.add(
                    self.reader,
                    wanted,
                    weights,
                    [cells[raw].text for raw in wanted] if text_wanted else None,
                    first,
                )
            if duplicates is not None:
                duplicates.add_strings(wanted, weights, first)
            if texts is not None:
                texts.add_strings(wanted, weights)
            if fingerprints is not None:
                fingerprints.add_strings(wanted, weights)
            if forms is not None:
                forms.add_strings(self.reader, wanted, weights)
            if characters is not None:
                characters.add_strings(wanted, weights)

    def native(self, native_type: str, value: object, record: int = 1) -> None:
        """A JSON integer, number or boolean: a numeric value (but for a
        boolean), and no text. A boolean only matters to the analyses of the
        values themselves."""
        if (
            native_type == "boolean"
            and self.distinct is None
            and self.frequencies is None
            and self.patterns is None
            and self.measures is None
            and self.residuals is None
            and self.duplicates is None
            and self.drift is None
            and self.fingerprints is None
            and self.forms is None
        ):
            return
        self.values += 1
        if native_type != "boolean" and (self.numeric is not None or self.shape is not None):
            number = native_number(native_type, value)
            if self.numeric is not None:
                self.numeric.add(number, 1)
            if self.shape is not None:
                self.shape.add(number, 1)
        if self.distinct is not None:
            self.distinct.add_native(native_type, value)
        if self.frequencies is not None:
            self.frequencies.add_native(native_type, value)
        if self.patterns is not None:
            # The discovery reads an integer as its decimal text (design 18.12).
            if native_type == "integer":
                self.patterns.add_strings([str(value)], [1])
            else:
                self.patterns.add_native()
        if self.measures is not None:
            self.measures.add_native()
        if self.residuals is not None:
            self.residuals.add_native()
        if self.duplicates is not None:
            self.duplicates.add_native(native_type, value, record)
        if self.fingerprints is not None:
            self.fingerprints.add_native(native_type, value)
        if self.forms is not None:
            self.forms.add_native(native_type, value)
        if self.drift is not None:
            if self.drift.track:
                self.drift.add_native(record, native_type, value)
            else:
                self.drift.add_presence(record, 1)


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
        matrices: Sequence[tuple[str, RowAccumulator]] = (),
        structures: Sequence[tuple[str, StructureAccumulator]] = (),
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
        # The records that lack a value in several columns are counted from the
        # rows of each batch, whatever the routes do with them.
        self.matrices: dict[str, list[RowAccumulator]] = {}
        for dataset, matrix in matrices:
            self.matrices.setdefault(dataset, []).append(matrix)
        # The sets of keys of the objects are counted from the observations of each
        # record, which only a source that hands records has.
        self.structures: dict[str, list[StructureAccumulator]] = {}
        for dataset, structure in structures:
            self.structures.setdefault(dataset, []).append(structure)
        # Where each member of a matrix is in a row, per dataset; ``None`` for a
        # source that hands records and not rows.
        self._matrix_indexes: dict[str, list[tuple[RowAccumulator, list[int] | None]]] = {}
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
        return (
            fed
            + sum(route.values for fields in self.routes.values() for route in fields.values())
            + sum(matrix.values for group in self.matrices.values() for matrix in group)
            + sum(
                structure.values for group in self.structures.values() for structure in group
            )
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
        for group in self.matrices.values():
            for matrix in group:
                self._guarded(matrix, matrix.flush)

    @staticmethod
    def _guarded(
        matrix: RowAccumulator | StructureAccumulator, action: Callable[[], None]
    ) -> None:
        """Run a step of a matrix or of the sets of keys: one that raises stops
        counting and fails alone."""
        if matrix.failure is not None:
            return
        try:
            action()
        except Exception as exc:  # noqa: BLE001 - one matrix fails alone
            matrix.failure = type(exc).__name__

    def _open(self, item: DatasetOpened) -> None:
        wanted = self.routes.get(item.dataset, {})
        self._columns[item.dataset] = [
            (index, wanted[declared.path])
            for index, declared in enumerate(item.fields)
            if declared.path in wanted
        ]
        declared_at = {declared.path: index for index, declared in enumerate(item.fields)}
        located = []
        for matrix in self.matrices.get(item.dataset, ()):
            # A source that declares its fields hands rows; the others, records.
            found = [declared_at.get(path, -1) for path in matrix.by_path]
            located.append((matrix, found if found and -1 not in found else None))
        self._matrix_indexes[item.dataset] = located
        feeds = self.feeds.get(item.dataset, {})
        self._feed_columns[item.dataset] = [
            (index, feed)
            for index, declared in enumerate(item.fields)
            for feed in feeds.get(declared.path, ())
        ]

    def _batch(self, batch: RecordBatch) -> None:
        self.records_read += len(batch.rows)
        for matrix, indexes in self._matrix_indexes.get(batch.dataset, ()):
            if indexes is not None:
                self._guarded(matrix, partial(matrix.add_rows, batch.rows, indexes))
        for index, route in self._columns.get(batch.dataset, ()):
            if route.failure is not None:
                continue
            try:
                route.strings([row[index] for row in batch.rows], batch.start)
            except Exception as exc:  # noqa: BLE001 - one field fails alone
                route.failure = type(exc).__name__
        columns = self._feed_columns.get(batch.dataset)
        if columns:
            converted: dict[int, Rows] = {}
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
        rows_of: Callable[[Feed], Rows | None],
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
        for matrix in self.matrices.get(record.dataset, ()):
            self._guarded(matrix, partial(matrix.add_record, record))
        for structure in self.structures.get(record.dataset, ()):
            self._guarded(structure, partial(structure.add_record, record))
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
                        route.string(observation.value, record.index)  # type: ignore[arg-type]
                    elif native_type in ("integer", "number", "boolean"):
                        route.native(native_type, observation.value, record.index)
                    elif native_type == "array":
                        route.array(observation.value)  # type: ignore[arg-type]
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

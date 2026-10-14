# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The tests that tell which targets a row covers (design 20.16, SMART-05).

The predicates of the plan name what they stand for by reference into the Scan
(an entry of the sample, a pattern, a bin). This module resolves them once, before
the source is read, into tests on the cells of a CSV row, and reads each cell as
the first pass did (``CellReader``). A target whose reference cannot be resolved
is left out with a reason, never guessed.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from itertools import chain
from typing import NamedTuple

from tabalyst.scanner.detectors.temporal import kind_of
from tabalyst.scanner.features import (
    MISSING,
    CategoryCoder,
    Coder,
    PatternCoder,
    feature_coder,
)
from tabalyst.scanner.measures import UNCONVERTIBLE
from tabalyst.scanner.models import (
    ColumnSegment,
    DatasetResult,
    FieldPatternsComplete,
    FieldResult,
    Observation,
    ScanResult,
)
from tabalyst.scanner.records import table_digest
from tabalyst.scanner.secondpass.accumulators import ScanMismatch
from tabalyst.scanner.secondpass.models import AnalysisResult, DeepResult
from tabalyst.scanner.secondpass.patterns import pattern_entry
from tabalyst.scanner.secondpass.replay import Cell, CellReader
from tabalyst.scanner.smart import reasons
from tabalyst.scanner.smart.bins import bin_index
from tabalyst.scanner.smart.models import Target

Cover = tuple[int, ...]
NO_COVER: Cover = ()

# Raw strings remembered per column across batches, and the longest one kept: a
# column of few distinct values pays for the memory, one of identifiers or of
# long texts does not (and must not hold a million long strings).
MEMO_ENTRIES = 16_384
MEMO_CHARS = 256

UNRESOLVED = reasons.UNRESOLVED

_BOOLEAN_WORDS = frozenset({"true", "false"})


class _Unresolved(Exception):
    """A target cannot be tested; the message is a code of ``UNRESOLVED``."""


class _NumericTests:
    """The numeric targets of one column, grouped so that a number is placed once:
    the extremes it may be, zero or its sign, and its bin."""

    __slots__ = ("bin_targets", "bins", "high", "low", "maximum", "minimum", "negative", "positive", "zero")

    def __init__(self, low: float, high: float) -> None:
        self.low = low
        self.high = high
        self.minimum: list[int] = []
        self.maximum: list[int] = []
        self.zero: list[int] = []
        self.negative: list[int] = []
        self.positive: list[int] = []
        self.bins = 0
        self.bin_targets: dict[int, list[int]] = {}

    def hit(self, number: int | Decimal, found: list[int]) -> None:
        if type(number) is not int and number.is_nan():
            # Not a place on any scale; comparing it would raise in the hot path.
            return
        if self.minimum and _same_number(number, self.low):
            found.extend(self.minimum)
        if self.maximum and _same_number(number, self.high):
            found.extend(self.maximum)
        if number == 0:
            found.extend(self.zero)
        elif number < 0:
            found.extend(self.negative)
        else:
            found.extend(self.positive)
        if self.bin_targets:
            index = bin_index(number, self.low, self.high, self.bins)
            if index is not None:
                hit = self.bin_targets.get(index)
                if hit:
                    found.extend(hit)


class _DateRule(NamedTuple):
    kind: str
    target: int
    temporal_kind: str
    reference: str | int | None
    instant: datetime | None


class _TypeRule(NamedTuple):
    target: int
    accepted: frozenset[str]


def _column_of(field: FieldResult) -> int:
    path = field.path
    if len(path) != 1 or not isinstance(path[0], ColumnSegment):
        raise _Unresolved("not_a_column")
    return path[0].column - 1


def _same_number(number: int | Decimal, reference: float) -> bool:
    """Whether a number of the source is the exact extreme the Scan wrote: an
    integer as it is, anything else as the float64 the Scan output."""
    if type(reference) is int:
        return number == reference
    try:
        return float(number) == reference
    except OverflowError:
        return False


def _family(cell: Cell) -> str:
    """The family of a content cell, as the first pass counted it for the
    technical type of the column (``technical.string_family``)."""
    moment = cell.moment
    if moment is not None and (
        moment.state == "ambiguous"
        or (moment.state == "matched" and type(moment.value) is date)
    ):
        return "date"
    if len(cell.text) <= 5 and cell.text.casefold() in _BOOLEAN_WORDS:
        return "boolean"
    number = cell.number
    if number is None or number is UNCONVERTIBLE:
        return "text"
    return "integer" if type(number) is int else "number"


def _accepted_families(field: FieldResult, rule: str) -> frozenset[str]:
    """The families that do not make a cell an outlier of the technical type
    (``type_outliers``), or that of the family closest to it (``mixed_types``)."""
    technical = field.technical_type
    counts = technical.counts
    integers = counts.get("integer", 0)
    options = (
        ("integer", frozenset({"integer"}), integers),
        ("number", frozenset({"integer", "number"}), integers + counts.get("number", 0)),
        ("date", frozenset({"date"}), counts.get("date", 0)),
        ("boolean", frozenset({"boolean"}), counts.get("boolean", 0)),
        ("text", frozenset({"text"}), counts.get("text", 0)),
    )
    if rule == "type_outliers":
        for name, accepted, _ in options:
            if name == technical.type:
                return accepted
        raise _Unresolved("scan_mismatch")
    best = options[0]
    for option in options[1:]:
        if option[2] > best[2]:
            best = option
    return best[1]


class _ColumnTests:
    """The tests that read one column of a row."""

    def __init__(self, evaluator: Evaluator, field: FieldResult) -> None:
        self.field = field
        self.index = _column_of(field)
        # The numbers the Scan counted in the field (design 20.27).
        self.reader = evaluator.reader.for_field(field)
        self.exact: dict[str, list[int]] = {}
        self.missing: list[int] = []
        self.coder: PatternCoder | None = None
        self.by_code: dict[int, list[int]] = {}
        self.lengths: dict[int, list[int]] = {}
        self.numeric: _NumericTests | None = None
        self.dates: list[_DateRule] = []
        self.ambiguous: list[int] = []
        self.types: list[_TypeRule] = []
        self.mixed: list[_TypeRule] = []
        self.memo: dict[str, Cover] = {}
        # The categories the Scan counts as missing (``RecordContext.missing``):
        # a cell that is not content is only an empty cell when it is one of them.
        self._blank = frozenset(evaluator.scan_missing)

    @property
    def _numbers(self) -> bool:
        return self.numeric is not None or bool(self.types or self.mixed)

    @property
    def _dates(self) -> bool:
        return bool(self.dates or self.ambiguous or self.types or self.mixed)

    @property
    def _cells(self) -> bool:
        return bool(self.lengths or self._numbers or self._dates)

    def tuples(self, column: list[str]) -> list[Cover]:
        """The targets covered by each string of a column, in order."""
        memo = self.memo
        distinct = set(column)
        if len(memo) + len(distinct) > MEMO_ENTRIES:
            memo.clear()
        fresh = [raw for raw in distinct if raw not in memo]
        extra: dict[str, Cover] = {}
        if fresh:
            for raw, cover in zip(fresh, self._compute(fresh), strict=True):
                if len(raw) <= MEMO_CHARS:
                    memo[raw] = cover
                else:
                    extra[raw] = cover
        get = memo.get
        if not extra:
            return [get(raw) for raw in column]  # type: ignore[misc]
        return [get(raw) or extra.get(raw, NO_COVER) for raw in column]

    def _compute(self, raws: list[str]) -> list[Cover]:
        reader = self.reader
        content = reader.content(raws)
        cells: list[Cell] | None = (
            reader.cells(raws, numbers=self._numbers, dates=self._dates)
            if self._cells
            else None
        )
        codes = self.coder.code_strings(raws) if self.coder is not None else None
        covers: list[Cover] = []
        for position, raw in enumerate(raws):
            found: list[int] = []
            hit = self.exact.get(raw)
            if hit:
                found.extend(hit)
            if not content[position]:
                if self.missing and self.reader.strings.category(raw) in self._blank:
                    found.extend(self.missing)
                covers.append(tuple(found))
                continue
            if codes is not None:
                hit = self.by_code.get(codes[position])
                if hit:
                    found.extend(hit)
            if cells is not None:
                self._cell(cells[position], found)
            covers.append(tuple(found))
        return covers

    def _cell(self, cell: Cell, found: list[int]) -> None:
        hit = self.lengths.get(cell.length)
        if hit:
            found.extend(hit)
        number = cell.number
        if self.numeric is not None and number is not None and number is not UNCONVERTIBLE:
            self.numeric.hit(number, found)  # type: ignore[arg-type]
        moment = cell.moment
        if moment is not None:
            if moment.state == "ambiguous":
                found.extend(self.ambiguous)
            elif moment.state == "matched" and self.dates:
                self._date(moment.value, found)
        if self.types or self.mixed:
            family = _family(cell)
            for rule in self.types:
                if family not in rule.accepted:
                    found.append(rule.target)
            for rule in self.mixed:
                if family not in rule.accepted:
                    found.append(rule.target)

    def _date(self, value: object, found: list[int]) -> None:
        kind = kind_of(value)
        if kind is None:
            return
        text = value.isoformat()  # type: ignore[attr-defined]
        for rule in self.dates:
            if rule.temporal_kind != kind:
                continue
            if rule.kind in ("date_min", "date_max"):
                if text == rule.reference or (
                    rule.instant is not None and value == rule.instant
                ):
                    found.append(rule.target)
            elif rule.kind == "date_kind" or value.year == rule.reference:
                found.append(rule.target)


class _RelationTests:
    """The exceptions of one table: the rows whose category and class of the
    feature are those of an exception cell."""

    def __init__(
        self,
        category: tuple[int, CategoryCoder],
        feature: tuple[int, Coder],
        cells: dict[tuple[int, int], list[int]],
    ) -> None:
        self.category_index, self.categories = category
        self.feature_index, self.feature = feature
        self.cells = cells

    def covers(self, rows: list[list[str]], covered: list[list[int]]) -> None:
        categories = self.categories.code_strings([row[self.category_index] for row in rows])
        classes = self.feature.code_strings([row[self.feature_index] for row in rows])
        cells = self.cells
        for position, (left, right) in enumerate(zip(categories, classes, strict=True)):
            if left == MISSING or right == MISSING or left < 0 or right < 0:
                continue
            hit = cells.get((left, right))
            if hit:
                covered[position].extend(hit)


class _DuplicateTests:
    """The rows that repeat an earlier row of the source.

    The Scan lists only a few records of its duplicates, so the evaluator digests
    every row as the Scan did (``table_digest``) and remembers the digests seen.
    Like the Scan it stops storing at ``limit`` digests: a later copy of a row that
    was not stored goes unseen, and the count is then a lower bound.
    """

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.targets: Cover = ()
        self._seen: set[bytes] = set()

    def covers(self, rows: list[list[str]]) -> list[Cover]:
        """The targets of the duplicates each row of a batch covers, in order."""
        seen = self._seen
        found: list[Cover] = []
        for row in rows:
            digest = table_digest(row)
            if digest in seen:
                found.append(self.targets)
                continue
            if len(seen) < self.limit:
                seen.add(digest)
            found.append(NO_COVER)
        return found


class Evaluator:
    """Which targets each row of the source covers.

    ``targets`` is the list of the plan; a cover is a tuple of positions in it.
    The targets the Scan cannot support while reading are in ``unresolved``,
    position to a code of ``UNRESOLVED``, and cover nothing.
    """

    def __init__(
        self,
        scan: ScanResult,
        dataset: DatasetResult,
        deep: DeepResult | None,
        targets: Sequence[Target],
    ) -> None:
        self.reader = CellReader(scan.config)
        self.scan_missing = frozenset(scan.config.values.missing) - {"absent", "null"}
        self.unresolved: dict[int, str] = {}
        self._scan = scan
        self._dataset = dataset
        self._fields = {field.id: field for field in dataset.fields}
        self._observations: dict[str, Observation] = (
            {item.id: item for item in scan.observations.items}
            if scan.observations is not None
            else {}
        )
        self._analyses: dict[str, AnalysisResult] = (
            {a.id: a for a in deep.analyses if a.dataset == dataset.id} if deep is not None else {}
        )
        self._columns: dict[str, _ColumnTests] = {}
        self._relations: dict[str, _RelationTests] = {}
        self._duplicates: _DuplicateTests | None = None
        for position, target in enumerate(targets):
            if target.feasibility != "ready":
                continue
            try:
                self._add(position, target)
            except _Unresolved as exc:
                self.unresolved[position] = str(exc)
        self.columns = sorted(self._columns.values(), key=lambda tests: tests.index)

    def _tests(self, field_id: str) -> _ColumnTests:
        field = self._fields.get(field_id)
        if field is None:
            raise _Unresolved("reference_missing")
        tests = self._columns.get(field_id)
        if tests is None:
            tests = self._columns[field_id] = _ColumnTests(self, field)
        return tests

    def _add(self, position: int, target: Target) -> None:
        predicate = target.predicate
        kind = predicate.kind
        if kind == "relation_exception":
            self._relation(position, target)
            return
        if kind == "observation" and not target.fields:
            self._dataset_observation(position, target)
            return
        if not target.fields:
            raise _Unresolved("unsupported_predicate")
        tests = self._tests(target.fields[0])
        field = tests.field
        params = predicate.params
        if kind == "value_equals":
            entry = next(
                (e for e in field.values.samples.listed if e.id == params.get("entry")), None
            )
            if entry is None:
                raise _Unresolved("reference_missing")
            tests.exact.setdefault(entry.value, []).append(position)
        elif kind == "value_missing":
            tests.missing.append(position)
        elif kind in ("pattern_matches", "pattern_other"):
            self._pattern(tests, position, target)
        elif kind in ("length_min", "length_max"):
            envelope = field.string_lengths
            if envelope.status != "complete":
                raise _Unresolved("reference_missing")
            stats = envelope.value
            length = stats.min_length if kind == "length_min" else stats.max_length
            tests.lengths.setdefault(length, []).append(position)
        elif kind.startswith("numeric_"):
            self._numeric(tests, position, target)
        elif kind.startswith("date_"):
            self._date(tests, position, target)
        elif kind == "observation":
            self._observation(tests, position, target)
        else:
            raise _Unresolved("unsupported_predicate")

    def _pattern(self, tests: _ColumnTests, position: int, target: Target) -> None:
        scan = self._scan
        entry = (
            pattern_entry(scan.derived.patterns.fields, self._dataset.id, tests.field.id)
            if scan.derived is not None and scan.derived.patterns is not None
            else None
        )
        if entry is None:
            raise _Unresolved("reference_missing")
        coder = self._pattern_coder(tests, entry)
        if target.predicate.kind == "pattern_other":
            tests.by_code.setdefault(coder.other, []).append(position)
            return
        ids = [pattern.id for pattern in entry.all_patterns()]
        wanted = target.predicate.params.get("pattern")
        if wanted not in ids:
            raise _Unresolved("reference_missing")
        tests.by_code.setdefault(ids.index(str(wanted)), []).append(position)

    def _pattern_coder(self, tests: _ColumnTests, entry: FieldPatternsComplete) -> PatternCoder:
        """The coder of the patterns of a column, made once: it reads the hierarchy as
        the validation does, and refuses an entry the samples of the Scan no longer
        give."""
        if tests.coder is None:
            try:
                tests.coder = PatternCoder(
                    self.reader, entry, tests.field, self._scan.config.pattern_inference
                )
            except ScanMismatch as exc:
                raise _Unresolved("scan_mismatch") from exc
        return tests.coder

    def _numeric(self, tests: _ColumnTests, position: int, target: Target) -> None:
        envelope = tests.field.numeric
        if envelope.status != "complete":
            raise _Unresolved("reference_missing")
        stats = envelope.value
        if tests.numeric is None:
            tests.numeric = _NumericTests(stats.min, stats.max)
        numeric = tests.numeric
        kind = target.predicate.kind
        params = target.predicate.params
        if kind == "numeric_min":
            numeric.minimum.append(position)
        elif kind == "numeric_max":
            numeric.maximum.append(position)
        elif kind == "numeric_zero":
            numeric.zero.append(position)
        elif kind == "numeric_sign":
            (numeric.negative if params.get("sign") == "negative" else numeric.positive).append(
                position
            )
        elif kind == "numeric_bin":
            numeric.bins = int(params["of"])
            numeric.bin_targets.setdefault(int(params["bin"]), []).append(position)
        else:
            raise _Unresolved("unsupported_predicate")

    def _date(self, tests: _ColumnTests, position: int, target: Target) -> None:
        envelope = tests.field.temporal
        if envelope.status != "complete":
            raise _Unresolved("reference_missing")
        params = target.predicate.params
        kind = target.predicate.kind
        name = str(params.get("kind"))
        stats = next((k for k in envelope.value.kinds if k.kind == name), None)
        if stats is None:
            raise _Unresolved("reference_missing")
        reference: str | int | None = None
        instant: datetime | None = None
        if kind in ("date_min", "date_max"):
            reference = stats.min if kind == "date_min" else stats.max
            if name == "datetime_aware":
                try:
                    instant = datetime.fromisoformat(reference)
                except ValueError:
                    instant = None
        elif kind == "date_year":
            if stats.years is None or int(params["index"]) >= len(stats.years):
                raise _Unresolved("reference_missing")
            reference = stats.years[int(params["index"])].year
        tests.dates.append(_DateRule(kind, position, name, reference, instant))

    def _observation(self, tests: _ColumnTests, position: int, target: Target) -> None:
        item = self._observations.get(target.origin or "")
        if item is None:
            raise _Unresolved("reference_missing")
        rule = item.rule
        if rule == "missing_values":
            tests.missing.append(position)
        elif rule == "ambiguous_dates":
            tests.ambiguous.append(position)
        elif rule == "minority_pattern":
            scan = self._scan
            entry = (
                pattern_entry(scan.derived.patterns.fields, self._dataset.id, tests.field.id)
                if scan.derived is not None and scan.derived.patterns is not None
                else None
            )
            if entry is None:
                raise _Unresolved("reference_missing")
            self._pattern_coder(tests, entry)
            ids = [pattern.id for pattern in entry.all_patterns()]
            for pattern in item.patterns:
                if pattern not in ids:
                    raise _Unresolved("reference_missing")
                tests.by_code.setdefault(ids.index(pattern), []).append(position)
        elif rule in ("mixed_types", "type_outliers"):
            rules = tests.mixed if rule == "mixed_types" else tests.types
            rules.append(_TypeRule(position, _accepted_families(tests.field, rule)))
        else:
            raise _Unresolved("unsupported_predicate")

    def _dataset_observation(self, position: int, target: Target) -> None:
        """An observation of the whole dataset: the duplicate rows."""
        item = self._observations.get(target.origin or "")
        if item is None:
            raise _Unresolved("reference_missing")
        if item.rule != "duplicate_rows":
            raise _Unresolved("unsupported_predicate")
        if self._duplicates is None:
            self._duplicates = _DuplicateTests(self._scan.config.limits.max_tracked_records)
        self._duplicates.targets += (position,)

    def _relation(self, position: int, target: Target) -> None:
        analysis =self._analyses.get(target.origin or "")
        if (
            analysis is None
            or analysis.status != "complete"
            or analysis.partner is None
            or len(target.fields) != 2
        ):
            raise _Unresolved("reference_missing")
        category = self._fields.get(analysis.field)
        column = self._fields.get(analysis.partner)
        if category is None or column is None:
            raise _Unresolved("reference_missing")
        existing = self._relations.get(analysis.id)
        if existing is None:
            existing = self._relations[analysis.id] = self._relation_tests(
                analysis, category, column
            )
        params = target.predicate.params
        # The cell names its classes by position in the axes of the table, which
        # are the classes of the coders, "other" last.
        left, right = int(params["category"]), int(params["column"])
        if left >= len(existing.categories.classes) or right >= len(existing.feature.classes):
            raise _Unresolved("scan_mismatch")
        existing.cells.setdefault((left, right), []).append(position)

    def _relation_tests(
        self, analysis: AnalysisResult, category: FieldResult, column: FieldResult
    ) -> _RelationTests:
        parameters = analysis.parameters
        scan = self._scan
        measure = category.values.frequencies
        max_categories = int(parameters["max_categories"])
        if measure.status != "complete" or len(measure.value.listed) < min(
            measure.value.distinct, max_categories
        ):
            raise _Unresolved("scan_mismatch")
        categories = CategoryCoder(self.reader, measure.value, max_categories)
        entry = (
            pattern_entry(scan.derived.patterns.fields, self._dataset.id, column.id)
            if scan.derived is not None and scan.derived.patterns is not None
            else None
        )
        prefix_length = int(parameters.get("prefix_length") or 0)
        coder, _ = feature_coder(
            self.reader,
            str(parameters["feature"]),
            column,
            entry,
            max_classes=int(parameters.get("max_classes") or 0) or 2,
            prefix_length=prefix_length or 1,
            inference=scan.config.pattern_inference,
        )
        if coder is None:
            raise _Unresolved("scan_mismatch")
        return _RelationTests(
            (_column_of(category), categories), (_column_of(column), coder), {}
        )

    def cover(self, rows: list[list[str]]) -> list[Cover]:
        """The targets covered by each row of a batch, in order."""
        columns = [
            tests.tuples([row[tests.index] for row in rows]) for tests in self.columns
        ]
        if self._relations:
            extra: list[list[int]] = [[] for _ in rows]
            for relation in self._relations.values():
                relation.covers(rows, extra)
            columns.append([tuple(more) for more in extra])
        if self._duplicates is not None:
            columns.append(self._duplicates.covers(rows))
        if not columns:
            return [NO_COVER] * len(rows)
        if len(columns) == 1:
            return columns[0]
        return [tuple(chain.from_iterable(parts)) for parts in zip(*columns, strict=True)]

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Accumulators of the table of a category against a feature (design 20.13).

A column is coded once per batch whatever the number of tables that use it
(``CodeFeed``, REL-03); each table keeps its own counters over the aligned codes
of its two columns (``CrosstabAccumulator``, REL-11 to REL-15). The classes are
fixed before the source is read, so nothing creates an axis while it streams
(REL-12).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from tabalyst.scanner.crosstab import (
    association,
    baseline_share,
    dominant,
    margins,
    purity_forward,
    purity_reverse,
)
from tabalyst.scanner.features import (
    FEATURE_VERSION,
    MISSING,
    Coder,
)
from tabalyst.scanner.models import FieldResult
from tabalyst.scanner.planner.costmodel import REPLAY_MEMO_ENTRIES
from tabalyst.scanner.secondpass.accumulators import ScanMismatch
from tabalyst.scanner.secondpass.models import (
    CandidateRule,
    CategorySummary,
    CrosstabResult,
    ExceptionCell,
    ExceptionExample,
    PurityFigure,
    TableAssociation,
    TableAxis,
    TableClass,
    TableExceptions,
    TableExclusions,
    TableFeature,
    TablePurity,
)

# Characters of the value an example of an exception shows.
EXAMPLE_CHARS = 64
# Exception cells a result lists, with their examples.
MAX_EXCEPTION_CELLS = 20


class CodeFeed:
    """The classes of one column, converted once for every table that uses it.

    A batch of CSV strings goes through ``convert``; a record at a time (JSON,
    Excel) goes through ``push_*`` and ``end_record``, and the rows wait in
    ``rows`` until the router hands a full buffer to the tables. ``raws`` and
    ``records`` hold, for the rows being handed, the string each came from and
    its record number, which the examples of an exception quote.
    """

    __slots__ = (
        "buffered_raws",
        "buffered_records",
        "coder",
        "failure",
        "memo",
        "pending",
        "pending_raw",
        "raws",
        "records",
        "rows",
        "seen",
        "values",
    )

    def __init__(self, coder: Coder) -> None:
        self.coder = coder
        self.memo: dict[str, int] = {}
        self.values = 0
        self.rows: list[int] = []
        # The strings and record numbers of the rows being handed to the tables:
        # the batch itself, or the buffer of the records read one at a time.
        self.raws: Sequence[str] = []
        self.records: Sequence[int] = []
        self.buffered_raws: list[str] = []
        self.buffered_records: list[int] = []
        self.pending = MISSING
        self.pending_raw = ""
        # The record has already given its value (the first occurrence counts).
        self.seen = False
        self.failure: str | None = None

    def convert(self, strings: Sequence[str], start: int = 0) -> list[int]:
        """The code of each string of consecutive records numbered from
        ``start``."""
        self.values += len(strings)
        memo = self.memo
        table: dict[str, int] = {}
        missing: list[str] = []
        for raw in dict.fromkeys(strings):
            code = memo.get(raw)
            if code is None:
                missing.append(raw)
            else:
                table[raw] = code
        if missing:
            room = REPLAY_MEMO_ENTRIES - len(memo)
            for raw, code in zip(missing, self.coder.code_strings(missing), strict=True):
                table[raw] = code
                if room > 0:
                    memo[raw] = code
                    room -= 1
        self.raws = strings
        self.records = range(start, start + len(strings))
        return [table[raw] for raw in strings]

    def push_string(self, raw: str) -> None:
        """The string a record holds in the column."""
        self.values += 1
        self.seen = True
        self.pending_raw = raw
        code = self.memo.get(raw)
        if code is None:
            code = self.coder.code_strings([raw])[0]
            if len(self.memo) < REPLAY_MEMO_ENTRIES:
                self.memo[raw] = code
        self.pending = code

    def push_native(self, native_type: str, value: object) -> None:
        """A JSON integer, number or boolean."""
        self.values += 1
        self.seen = True
        self.pending_raw = str(value)
        self.pending = self.coder.code_native(native_type, value)

    def end_record(self, index: int = 0) -> None:
        """Close the row of the record numbered ``index``: what it held, or
        nothing."""
        self.rows.append(self.pending)
        self.buffered_raws.append(self.pending_raw)
        self.buffered_records.append(index)
        self.raws, self.records = self.buffered_raws, self.buffered_records
        self.pending = MISSING
        self.pending_raw = ""
        self.seen = False

    def reset(self) -> None:
        """Forget the rows handed to the tables."""
        self.rows = []
        self.buffered_raws = []
        self.buffered_records = []
        self.raws, self.records = self.buffered_raws, self.buffered_records


def axis(field: FieldResult, coder: Coder) -> TableAxis:
    """The axis of a table: the field and the classes of its coder."""
    return TableAxis(
        field=field.id,
        display=field.display,
        domain=coder.domain,
        classes=[
            TableClass(id=item.id, label=item.label, kind=item.kind, type=item.type)
            for item in coder.classes
        ],
    )


class CrosstabAccumulator:
    """The counts of the rows of each category by class of a feature, the rows
    left out, and the first rows of every cell (REL-13, REL-15).

    The examples are the first ``examples`` rows of each cell in source order,
    kept for every cell because the dominant class of a category is only known at
    the end; the exception cells are the ones that are listed.
    """

    def __init__(
        self,
        first: CodeFeed,
        second: CodeFeed,
        *,
        feature: str,
        prefix_length: int | None,
        examples: int,
        rule_purity: int,
        rule_support: int,
    ) -> None:
        self.first = first
        self.second = second
        self.feature = feature
        self.prefix_length = prefix_length
        self.examples = examples
        self.rule_purity = rule_purity
        self.rule_support = rule_support
        self.failure: str | None = None
        self.rows = 0
        self.first_present = 0
        self.second_present = 0
        self.cells: Counter[tuple[int, int]] = Counter()
        self.kept: dict[tuple[int, int], list[ExceptionExample]] = {}

    def add(self, first: list[int], second: list[int]) -> None:
        """Account for aligned rows of the two columns."""
        total = len(first)
        self.rows += total
        self.first_present += total - first.count(MISSING)
        self.second_present += total - second.count(MISSING)
        counts = Counter(zip(first, second, strict=True))
        self.cells.update(counts)
        if not self.examples:
            return
        wanted: dict[tuple[int, int], int] = {}
        for combo in counts:
            if combo[0] >= 0 and combo[1] >= 0:
                held = self.kept.get(combo)
                need = self.examples - (0 if held is None else len(held))
                if need > 0:
                    wanted[combo] = need
        if not wanted:
            return
        raws, records = self.second.raws, self.second.records
        for position, combo in enumerate(zip(first, second, strict=True)):
            need = wanted.get(combo)
            if need is None:
                continue
            self.kept.setdefault(combo, []).append(
                ExceptionExample(
                    record=records[position], value=raws[position][:EXAMPLE_CHARS]
                )
            )
            if need == 1:
                del wanted[combo]
                if not wanted:
                    break
            else:
                wanted[combo] = need - 1

    def check(self, first: FieldResult, second: FieldResult) -> None:
        """The values the reading found in each column are the Scan's; a
        difference means the table was not read as the Scan read the columns."""
        for label, found, expected in (
            ("category", self.first_present, first.values.count),
            ("feature column", self.second_present, second.values.count),
        ):
            if found != expected:
                raise ScanMismatch(f"the {label} holds {found} values, the scan counted {expected}")

    def result(self, source: str, first: FieldResult, second: FieldResult) -> CrosstabResult:
        """The table, checked against the Scan: the rows add up, and the values
        of each column are the ones it counted."""
        categories, classes = self.first.coder, self.second.coder
        height, width = len(categories.classes), len(classes.classes)
        table = [[0] * width for _ in range(height)]
        feature_missing = [0] * height
        unclassified = [0] * height
        excluded = {"category_missing": 0, "feature_missing": 0, "both_missing": 0, "unclassified": 0}
        for (a, b), count in self.cells.items():
            if a >= 0 and b >= 0:
                table[a][b] = count
            elif a >= 0:
                if b == MISSING:
                    feature_missing[a] += count
                    excluded["feature_missing"] += count
                else:
                    unclassified[a] += count
                    excluded["unclassified"] += count
            elif b == MISSING:
                excluded["both_missing"] += count
            else:
                excluded["category_missing"] += count
        totals = margins(table)
        if totals.total + sum(excluded.values()) != self.rows:
            raise ScanMismatch("the counts of the table do not add up to the rows read")
        self.check(first, second)

        by_category: list[CategorySummary] = []
        exception_cells: list[tuple[int, int, int]] = []
        exceptions = 0
        rules: list[CandidateRule] = []
        other_row = len(categories.classes) - 1
        other_column = len(classes.classes) - 1
        for index, row in enumerate(table):
            classified = totals.rows[index]
            rows = classified + feature_missing[index] + unclassified[index]
            best = dominant(row)
            taken = 0 if best is None else row[best]
            by_category.append(
                CategorySummary(
                    rows=rows,
                    classified=classified,
                    feature_missing=feature_missing[index],
                    unclassified=unclassified[index],
                    coverage=None if rows == 0 else classified / rows,
                    dominant=best,
                    dominant_count=taken,
                    purity=None if classified == 0 else taken / classified,
                    exceptions=classified - taken,
                )
            )
            exceptions += classified - taken
            for column, count in enumerate(row):
                if count and column != best:
                    exception_cells.append((index, column, count))
            if (
                best is not None
                and index != other_row
                and best != other_column
                and classified >= self.rule_support
                and taken * 100 >= self.rule_purity * classified
            ):
                rules.append(
                    CandidateRule(
                        category=index,
                        column=best,
                        support=classified,
                        confidence=taken / classified,
                        exceptions=classified - taken,
                    )
                )
        exception_cells.sort(key=lambda item: (-item[2], item[0], item[1]))
        listed = [
            ExceptionCell(
                category=a,
                column=b,
                count=count,
                examples=self.kept.get((a, b), []),
            )
            for a, b, count in exception_cells[:MAX_EXCEPTION_CELLS]
        ]
        found = association(table)
        forward, reverse = purity_forward(table), purity_reverse(table)
        return CrosstabResult(
            source=source,  # type: ignore[arg-type]
            feature=TableFeature(
                kind=self.feature,  # type: ignore[arg-type]
                version=FEATURE_VERSION,
                prefix_length=self.prefix_length,
            ),
            categories=axis(first, categories),
            classes=axis(second, classes),
            rows=self.rows,
            counted=totals.total,
            excluded=TableExclusions(**excluded),
            counts=table,
            row_totals=list(totals.rows),
            column_totals=list(totals.columns),
            by_category=by_category,
            purity=TablePurity(
                forward=PurityFigure(
                    dominant=forward.dominant, total=forward.total, value=forward.value
                ),
                reverse=PurityFigure(
                    dominant=reverse.dominant, total=reverse.total, value=reverse.value
                ),
                baseline=baseline_share(table),
            ),
            association=TableAssociation(
                defined=found.corrected is not None,
                n=found.n,
                effective_categories=found.effective_rows,
                effective_classes=found.effective_columns,
                chi_square=found.chi_square,
                degrees=found.degrees,
                cramers_v=found.cramers_v,
                corrected=found.corrected,
                low_share=found.low_share,
                stable=found.stable,
                sparse=found.sparse,
                reason=found.reason,
            ),
            exceptions=TableExceptions(
                count=exceptions, cells=len(exception_cells), listed=listed
            ),
            rules=rules,
        )


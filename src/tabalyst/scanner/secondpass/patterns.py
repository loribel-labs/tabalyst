# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Validation of the hierarchy of patterns of a field over every occurrence (design
20.9, PAT-21 to PAT-27).

The families, patterns and nodes of the Scan were found in a sample of the distinct
values; this counts the occurrences of the whole field. Each value is recognized once
by the reader of the hierarchy (``patternreader``) and counts for the deepest pattern
or node that reads it; the counts of the ancestors are the sums of their descendants,
so the work per cell does not grow with the number of variants (AC-027). The tables
that count the values of a facet and the set of the distinct values are bounded by
deterministic budgets in bytes (TR-003), and the accumulator is a plain object that
a worker process can hold and return (TR-005).
"""

from __future__ import annotations

from collections.abc import Sequence

from tabalyst.scanner.config import PatternInferenceSettings
from tabalyst.scanner.models import (
    FamilyPattern,
    FieldPatterns,
    FieldPatternsComplete,
    FieldResult,
    PatternNode,
)
from tabalyst.scanner.patterninfer import discovery_versions
from tabalyst.scanner.planner.costmodel import (
    DISTINCT_ENTRY_BYTES,
    NS_PER_CELL,
    PATTERN_CELL_BYTES,
)
from tabalyst.scanner.secondpass.accumulators import ScanMismatch
from tabalyst.scanner.secondpass.models import (
    PatternCountCell,
    PatternCounts,
    PatternDistinct,
    PatternExclusions,
    PatternFamilyCount,
    PatternNewVariants,
    PatternNodeCount,
    PatternTableCount,
)
from tabalyst.scanner.secondpass.patternreader import (
    KNOWN,
    NEW_LENGTH,
    NEW_SEGMENT,
    TOO_LONG,
    UNKNOWN_STRUCTURE,
    Family,
    HierarchyReader,
    Node,
)

__all__ = [
    "PatternAccumulator",
    "check_pattern_counts",
    "derive_from_samples",
    "pattern_entry",
]

# A whole token is a cell only up to this many characters (patternfacets): a longer
# one is an identifier and no complete number is published (exposure).
MAX_TOKEN_CELL = 4

_OUTCOME_NAMES = {
    KNOWN: "known",
    NEW_LENGTH: "new_variant",
    NEW_SEGMENT: "new_variant",
    UNKNOWN_STRUCTURE: "unknown_structure",
}


def pattern_entry(
    patterns: Sequence[FieldPatterns], dataset: str, field: str
) -> FieldPatternsComplete | None:
    """The complete pattern entry of a field of the Scan, if it has one."""
    for entry in patterns:
        if entry.dataset == dataset and entry.field == field:
            return entry if isinstance(entry, FieldPatternsComplete) else None
    return None


class PatternAccumulator:
    """The counts of the hierarchy of a field: one counter per pattern and node (the
    values it reads and none of its children), one table per facet that a node or a
    table of the discovery reads, the combinations of lengths the discovery left in
    the table of lengths, and the set of the distinct values.

    ``unique`` says that every string fed is a distinct value of the field (the
    exact counts of the Scan), which makes the distinct values exact without a set.
    ``table_cells`` is the capacity of a table in cells, ``distinct_bytes`` the
    bytes the set of distinct values may hold (design 20.9).
    """

    __slots__ = (
        "budget",
        "distinct",
        "entry",
        "exact",
        "excluded",
        "extra",
        "lengths",
        "new_segment",
        "occurrences",
        "reader",
        "seen",
        "table_cells",
        "tables",
        "unique",
        "unknown",
        "used",
        "values",
    )

    def __init__(
        self,
        entry: FieldPatternsComplete,
        field: FieldResult,
        settings: PatternInferenceSettings,
        table_bytes: int,
        distinct_bytes: int,
        unique: bool = False,
        table_cells: int | None = None,
    ) -> None:
        self.entry = entry
        self.reader = HierarchyReader.build(entry, field, settings)
        slots = self.reader.slots
        self.occurrences = [0] * slots
        self.distinct = [0] * slots
        self.exact = [True] * slots
        self.unique = unique
        self.seen: set[str] = set()
        self.used = 0
        self.budget = distinct_bytes
        self.table_cells = max(1, table_bytes // PATTERN_CELL_BYTES) if table_cells is None else table_cells
        families = self.reader.families
        # Per family and facet: the counts of the cells of the discovery, the values it
        # never saw (up to the capacity), and the occurrences that no cell holds.
        self.tables = [[[0] * len(facet.texts) for facet in family.facets] for family in families]
        self.extra: list[list[dict[str, int]]] = [[{} for _ in family.facets] for family in families]
        self.lengths: list[dict[str, int]] = [
            dict.fromkeys(family.lengths_cells, 0) for family in families
        ]
        self.new_segment = [0] * len(families)
        self.unknown = 0
        self.values = 0
        self.excluded = {"non_string": 0, "too_long": 0, "too_complex": 0}

    @property
    def cell_ns(self) -> int:
        """Modeled nanoseconds a cell costs: the family and the facets it reads, the
        most of any family (the cost model of 20.2)."""
        facets = max((len(family.facets) for family in self.reader.families), default=0)
        return NS_PER_CELL["pattern_family"] + facets * NS_PER_CELL["pattern_facet"]

    def outcome(self, raw: str) -> str | None:
        """The outcome of one string against the hierarchy, without counting it:
        ``known``, ``new_variant`` or ``unknown_structure``; ``None`` when the
        population leaves it out."""
        return _OUTCOME_NAMES.get(self.reader.read(raw)[0])

    def add_strings(self, raws: Sequence[str], counts: Sequence[int]) -> None:
        """Account for the distinct content strings of a batch with their counts."""
        read = self.reader.read
        occurrences = self.occurrences
        distinct = self.distinct
        exact = self.exact
        unique = self.unique
        held = self.seen
        budget = self.budget
        used = self.used
        values = unknown = too_long = too_complex = 0
        for raw, count in zip(raws, counts, strict=True):
            values += count
            outcome, family, slot, reads, vector = read(raw)
            if family is None:
                if outcome == UNKNOWN_STRUCTURE:
                    unknown += count
                elif outcome == TOO_LONG:
                    too_long += count
                else:
                    too_complex += count
                continue
            occurrences[slot] += count
            if unique:
                distinct[slot] += 1
            elif raw not in held:
                cost = DISTINCT_ENTRY_BYTES + len(raw)
                if used + cost > budget:
                    # Not held, so not counted: the distinct values of every node
                    # above are a lower bound from here on.
                    exact[slot] = False
                else:
                    used += cost
                    held.add(raw)
                    distinct[slot] += 1
            if outcome == NEW_SEGMENT:
                self.new_segment[family.index] += count
            if slot == family.off_slot:
                table = self.lengths[family.index]
                text = family.lengths_text(vector)
                table[text] = table.get(text, 0) + count
            if reads:
                self._tables(family, reads, count)
        self.used = used
        self.values += values
        self.unknown += unknown
        self.excluded["too_long"] += too_long
        self.excluded["too_complex"] += too_complex

    def _tables(
        self, family: Family, reads: Sequence[tuple[int | None, str]], count: int
    ) -> None:
        """Count a value in the table of each facet of its family: in the cell that
        reads it, or, when the sample never showed it, in a new cell up to the
        capacity."""
        index = family.index
        counts = self.tables[index]
        for number, (found, text) in enumerate(reads):
            if found is not None:
                counts[number][found] += count
                continue
            facet = family.facets[number]
            if facet.seen:
                # An open facet: a value that is no cell is counted in `others`.
                continue
            extra = self.extra[index][number]
            if text in extra:
                extra[text] += count
            elif len(extra) < self.table_cells and not (
                facet.edge == "token" and len(text) > MAX_TOKEN_CELL
            ):
                extra[text] = count
            # Otherwise the table is full: the value is in `others`, which is the
            # occurrences of the family that no kept cell holds.

    def add_native(self, count: int = 1) -> None:
        """JSON numbers that are not integers, or booleans: not tested."""
        self.values += count
        self.excluded["non_string"] += count

    # Result ---------------------------------------------------------------------

    def result(self, expected_values: int, computed_from: str) -> PatternCounts:
        """The counts, checked against the Scan: the values read are the values the
        Scan counted, and the counts add up."""
        if self.values != expected_values:
            raise ScanMismatch(
                f"values: the second pass found {self.values}, the scan {expected_values}"
            )
        families = [self._family(family) for family in self.reader.families]
        matched = sum(family.occurrences for family in families)
        grammar, algorithm = discovery_versions()
        counts = PatternCounts(
            computed_from=computed_from,  # type: ignore[arg-type]
            grammar_version=grammar,
            algorithm_version=algorithm,
            values=self.values,
            matched=matched,
            families=families,
            unknown_structure=self.unknown,
            excluded=PatternExclusions(**self.excluded),
        )
        problems = check_pattern_counts(self.entry, counts)
        if problems:
            raise ScanMismatch(f"the counts of the patterns are not consistent: {problems[0]}")
        return counts

    def _node(self, node: Node) -> PatternNodeCount:
        below = [self._node(child) for child in node.children]
        own = self.occurrences[node.slot]
        exact = self.exact[node.slot] and all(item.distinct.accuracy == "exact" for item in below)
        return PatternNodeCount(
            id=node.id,
            render=node.render,
            occurrences=own + sum(item.occurrences for item in below),
            distinct=PatternDistinct(
                count=self.distinct[node.slot] + sum(item.distinct.count for item in below),
                accuracy="exact" if exact else "at_least",
            ),
            rest=own,
            nodes=below,
        )

    def _family(self, family: Family) -> PatternFamilyCount:
        patterns = [self._node(node) for node in family.patterns]
        lengths = self.occurrences[family.off_slot]
        new_length = self.occurrences[family.new_slot]
        slots = (family.off_slot, family.new_slot)
        exact = all(self.exact[slot] for slot in slots) and all(
            item.distinct.accuracy == "exact" for item in patterns
        )
        total = sum(item.occurrences for item in patterns) + lengths + new_length
        tables = []
        if family.lengths_cells or lengths:
            tables.append(self._lengths_table(family, lengths))
        index = family.index
        for facet in family.facets:
            tables.append(self._table(family, facet.index, total))
        return PatternFamilyCount(
            id=family.id,
            occurrences=total,
            distinct=PatternDistinct(
                count=sum(item.distinct.count for item in patterns)
                + sum(self.distinct[slot] for slot in slots),
                accuracy="exact" if exact else "at_least",
            ),
            patterns=patterns,
            tables=tables,
            new_variants=PatternNewVariants(length=new_length, segment=self.new_segment[index]),
        )

    def _lengths_table(self, family: Family, total: int) -> PatternTableCount:
        cells = _top(list(self.lengths[family.index].items()), self.table_cells)
        return PatternTableCount(
            facet="lengths",
            capacity=self.table_cells,
            cells=cells,
            others=total - sum(cell.occurrences for cell in cells),
            saturated=total > sum(cell.occurrences for cell in cells),
        )

    def _table(self, family: Family, number: int, total: int) -> PatternTableCount:
        facet = family.facets[number]
        index = family.index
        counts = self.tables[index][number]
        items = [(text, counts[slot]) for slot, text in enumerate(facet.texts)]
        items.extend(self.extra[index][number].items())
        cells = _top(items, self.table_cells)
        kept = sum(cell.occurrences for cell in cells)
        return PatternTableCount(
            facet=facet.label,
            capacity=self.table_cells,
            cells=cells,
            others=total - kept,
            saturated=total > kept,
        )


def check_pattern_counts(entry: FieldPatternsComplete, counts: PatternCounts) -> list[str]:
    """The problems of a ``pattern_counts`` result against the entry of the Scan it
    was made for (design 20.9, PAT-27); empty when it is consistent.

    The families, patterns and nodes are those of the entry, in its order, and the
    counts add up: the families, the values no family reads and the values left out
    are the values; a family is its patterns, its combinations of lengths left in a
    table and its new variants of length; a node is its own rest and its nodes; the
    tables are bounded and complete the family to its occurrences."""
    problems: list[str] = []
    if len(counts.families) != len(entry.families):
        return ["there is not one result for each family of the scan"]
    excluded = sum(counts.excluded.model_dump().values())
    if sum(family.occurrences for family in counts.families) != counts.matched:
        problems.append("matched must add up the families")
    if counts.matched + counts.unknown_structure + excluded != counts.values:
        problems.append("matched, unknown_structure and excluded must add up to the values")
    for family, published in zip(counts.families, entry.families, strict=True):
        where = f"families[{family.id}]"
        if family.id != published.id or [p.id for p in family.patterns] != [
            p.id for p in published.patterns
        ]:
            problems.append(f"{where}: not the family and patterns of the scan")
            continue
        for pattern, item in zip(family.patterns, published.patterns, strict=True):
            _check_node_count(pattern, item, f"{where}.patterns[{pattern.id}]", problems)
        in_patterns = sum(pattern.occurrences for pattern in family.patterns)
        lengths = family.occurrences - in_patterns - family.new_variants.length
        if lengths < 0 or family.new_variants.segment > family.occurrences:
            problems.append(f"{where}: occurrences must hold the patterns and the new variants")
        for table in family.tables:
            total = lengths if table.facet == "lengths" else family.occurrences
            cells = sum(cell.occurrences for cell in table.cells)
            if (
                len(table.cells) > table.capacity
                or cells + table.others != total
                or table.saturated != (table.others > 0)
            ):
                problems.append(f"{where}.tables[{table.facet}]: cells and others must complete it")
    return problems


def _check_node_count(
    node: PatternNodeCount,
    published: FamilyPattern | PatternNode,
    where: str,
    problems: list[str],
) -> None:
    """A counted pattern or node is the one the Scan published, and is its rest and
    its nodes."""
    if [child.id for child in node.nodes] != [child.id for child in published.nodes]:
        problems.append(f"{where}: not the nodes of the scan")
        return
    if node.rest < 0 or node.rest + sum(child.occurrences for child in node.nodes) != (
        node.occurrences
    ):
        problems.append(f"{where}: occurrences must be the rest and the nodes")
    if node.distinct.count > node.occurrences:
        problems.append(f"{where}: more distinct values than occurrences")
    for child, item in zip(node.nodes, published.nodes, strict=True):
        _check_node_count(child, item, f"{where}.nodes[{child.id}]", problems)


def _top(items: list[tuple[str, int]], capacity: int) -> list[PatternCountCell]:
    """The most frequent ``capacity`` cells, the ties in the order of their text."""
    items.sort(key=lambda item: (-item[1], item[0]))
    return [PatternCountCell(value=text, occurrences=count) for text, count in items[:capacity]]


def derive_from_samples(accumulator: PatternAccumulator, field: FieldResult) -> None:
    """Fill ``accumulator`` from the exact counts of a Scan that holds every
    distinct original value of the field, without reading the source.

    Raises ``ScanMismatch`` when the Scan does not hold them: the planner only
    leaves the source unread for a population of the inference that is complete
    (``basis`` ``all_distinct``), which this checks again.
    """
    samples = field.values.samples
    if (
        samples.selection != "all"
        or samples.kept != samples.of
        or samples.long_texts is not None
        or any(entry.count_accuracy != "exact" for entry in samples.listed)
    ):
        raise ScanMismatch("the scan does not hold every distinct value with its exact count")
    # An integer is read as its decimal text, as the discovery reads it.
    strings = [entry for entry in samples.listed if entry.type in ("string", "integer")]
    accumulator.add_strings(
        [entry.value for entry in strings], [entry.count for entry in strings]
    )
    for entry in samples.listed:
        if entry.type not in ("string", "integer"):
            accumulator.add_native(entry.count)

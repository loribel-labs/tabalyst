"""Raw frequency tables, budgets, samples and first/last values (design
sections 9.1, 11 and 13).

Each field with values keeps a raw frequency table keyed by native type and
canonical form, so the string ``"123"`` and the integer ``123`` stay apart.
While the table is complete, per-value work runs once per distinct value at
finalization. When a limit releases the table, its stored values are processed
with their counts and the field switches to streaming: later occurrences are
gathered in a batch of distinct values, processed with their counts whenever
the batch is full. Both modes give the same results.

Per-value work runs on whole batches of distinct values, in first-seen order:
strings are normalized in one pass, then each detector classifies the batch,
so a detector that adaptive detection skips costs nothing per value.
"""

from __future__ import annotations

import heapq
import random
import zlib
from collections import Counter
from decimal import Decimal
from functools import reduce
from itertools import islice
from operator import or_

from tabalyst.scanner.config import ScanConfig, exact_share
from tabalyst.scanner.detectors.registry import (
    DetectorSet,
    FailureReporter,
    ProbeReporter,
)
from tabalyst.scanner.exposure import SHOW, ExposureGate
from tabalyst.scanner.measures import ValueMeasures, canonical_text
from tabalyst.scanner.models import (
    BooleanCounts,
    Complete,
    Disabled,
    Frequencies,
    Limited,
    Normalization,
    NormalizationStage,
    NotApplicable,
    Samples,
    ValueAt,
    ValueCount,
    Variant,
    VariantGroup,
    VariantGroups,
)
from tabalyst.scanner.normalization import KEY_STAGE, STAGES, VERSION, Normalizer
from tabalyst.scanner.technical import technical_type

# Distinct values a streamed field gathers before processing them: the batch
# is also its memoization, so memory stays bounded.
BATCH_SIZE = 4_096
_TYPE_ORDER = {"string": 0, "integer": 1, "number": 2, "boolean": 3}
_NO_VALUES = NotApplicable(reason="no_values")
_WITHHELD = Disabled()
_CATEGORIES = ("empty", "blank", "marker")

# Table keys: a raw string is its own key; other values are
# ``(native type, canonical form)`` tuples, which never equal a string.
Key = str | tuple[str, object]
# Complete tables of finalization: analytical values with their counts, and
# the stage outputs of the strings that a stage changed.
Collected = tuple[dict[tuple[str, str], int], dict[str, tuple[str, ...]]]


class ValueContext:
    """Settings, detectors and the global budget shared by every field of a
    scan.

    ``discovered`` numbers fields in order of discovery across datasets.
    """

    __slots__ = (
        "budget",
        "detectors",
        "discovered",
        "max_distinct",
        "max_listed",
        "max_samples",
        "max_stored_length",
        "max_variant_groups",
        "max_variants",
        "minimum_confidence",
        "normalizer",
        "pool",
        "seed",
    )

    def __init__(self, config: ScanConfig, detectors: DetectorSet) -> None:
        limits = config.limits
        self.normalizer = Normalizer(config.normalization)
        self.detectors = detectors
        self.minimum_confidence = exact_share(config.types.minimum_confidence)
        self.max_distinct = limits.max_distinct_per_field
        self.max_stored_length = limits.max_stored_value_length
        self.max_listed = limits.max_listed_frequencies
        self.max_samples = limits.max_samples
        self.max_variant_groups = limits.max_variant_groups
        self.max_variants = limits.max_variants_per_group
        self.seed = config.random_seed
        self.budget = ValueBudget(limits.max_tracked_values)
        self.discovered = 0
        # Worker processes of a parallel scan (``workers.WorkerPool``).
        self.pool = None

    def discover(self) -> int:
        self.discovered += 1
        return self.discovered


class ValueBudget:
    """``limits.max_tracked_values``: stored distinct values of the whole scan.

    When exceeded, the largest table is released first; ties release the most
    recently discovered field.
    """

    __slots__ = ("limit", "live", "released", "tracked")

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.tracked = 0
        self.released = 0
        # Trackers holding a table, by the discovery number of their field.
        self.live: dict[int, ValueTracker] = {}

    def enforce(self) -> None:
        while self.tracked > self.limit:
            largest = max(
                self.live.values(), key=lambda item: (item.distinct, item.sequence)
            )
            largest.release("global_budget", self.limit, largest.distinct)
            self.released += 1


class ValueTracker:
    """Values of one field: raw table or streaming batch, first and last values.

    The per-value work runs in a ``ValueProcessor``: in this process, or in
    a worker process of a parallel scan (``context.pool``), which receives
    the same distinct values in the same order (``workers.py``).
    """

    __slots__ = (
        "context",
        "distinct",
        "false",
        "first",
        "known",
        "last_record",
        "last_type",
        "last_value",
        "pending",
        "processor",
        "remote",
        "scalars",
        "sequence",
        "table",
        "true",
    )

    def __init__(self, context: ValueContext, sequence: int) -> None:
        self.context = context
        self.table: Counter[Key] | None = Counter()
        # Distinct values of a streamed field waiting to be processed.
        self.pending: Counter[Key] = Counter()
        # Distinct values stored in the table, which enter the budget.
        self.distinct = 0
        self.first: tuple[str, object, int] | None = None
        self.last_type = ""
        self.last_value: object = None
        self.last_record = 0
        self.true = 0
        self.false = 0
        self.sequence = sequence
        # Whether a value other than a string was seen.
        self.scalars = False
        # Strings of columns that are not values (``add_column``), by category.
        self.known: dict[str, str] = {}
        # The local processor, or the worker that processes the values.
        self.processor: ValueProcessor | None = None
        self.remote: int | None = None
        context.budget.live[sequence] = self

    def add(self, native_type: str, value: object, record: int) -> None:
        if self.first is None:
            self.first = (native_type, value, record)
        self.last_type = native_type
        self.last_value = value
        self.last_record = record
        if native_type == "string":
            key = value
        else:
            self.scalars = True
            if native_type == "number":
                key = ("number", str(value))
            else:
                if native_type == "boolean":
                    if value:
                        self.true += 1
                    else:
                        self.false += 1
                key = (native_type, value)
        table = self.table
        if table is None:
            self._stream(key)
            return
        count = table.get(key)
        if count is not None:
            table[key] = count + 1
            return
        context = self.context
        if _stored_length(key) > context.max_stored_length:
            # Longer than every stored value, so different from each of them.
            self.release("value_too_long", context.max_stored_length, self.distinct + 1)
            self._stream(key)
            return
        table[key] = 1
        self.distinct += 1
        budget = context.budget
        budget.tracked += 1
        if self.distinct > context.max_distinct:
            self.release("distinct_limit", context.max_distinct, self.distinct)
        else:
            budget.enforce()

    def add_column(self, values, start: int, strings) -> tuple[int, int, int]:
        """Add the raw strings of a column for consecutive records, the first
        being ``start`` (design 7).

        The strings are counted into the table (or the streaming batch) at
        once; those that are not content are taken out again and returned as
        counts ``(empty, blank, marker)``. The caller makes sure the global
        budget cannot be exceeded by these strings, so only this field's own
        limits apply, in first-seen order: the result is the same as adding
        the strings one by one.
        """
        table = self.table
        target = self.pending if table is None else table
        before = len(target)
        target.update(values)
        found = [0, 0, 0]
        known = self.known
        for key, category in known.items():
            count = target.pop(key, 0)
            if count:
                found[_CATEGORIES.index(category)] += count
        fresh_count = len(target) - before
        if fresh_count:
            fresh = list(islice(reversed(target), fresh_count))
            fresh.reverse()
            if strings.has_markers or not all(map(str.strip, fresh)):
                content = []
                for key in fresh:
                    category = strings.category(key)
                    if category == "content":
                        content.append(key)
                    else:
                        known[key] = category
                        found[_CATEGORIES.index(category)] += target.pop(key)
                fresh = content
            if table is not None and fresh:
                self._admit(fresh)
        category = strings.category
        if self.first is None:
            for offset, value in enumerate(values):
                if category(value) == "content":
                    self.first = ("string", value, start + offset)
                    break
        for offset in range(len(values) - 1, -1, -1):
            value = values[offset]
            if category(value) == "content":
                self.last_type = "string"
                self.last_value = value
                self.last_record = start + offset
                break
        if self.table is None and len(self.pending) >= BATCH_SIZE:
            self.flush()
        return found[0], found[1], found[2]

    def _admit(self, fresh: list[str]) -> None:
        """New distinct strings counted into the complete table, in first-seen
        order: the first one too long or beyond ``max_distinct_per_field``
        releases the table, as if the strings had been added one by one."""
        context = self.context
        longest = context.max_stored_length
        if (
            max(map(len, fresh)) <= longest
            and self.distinct + len(fresh) <= context.max_distinct
        ):
            self.distinct += len(fresh)
            context.budget.tracked += len(fresh)
            return
        for key in fresh:
            if len(key) > longest:
                self.release("value_too_long", longest, self.distinct + 1)
                return
            self.distinct += 1
            context.budget.tracked += 1
            if self.distinct > context.max_distinct:
                self.release("distinct_limit", context.max_distinct, self.distinct)
                return

    def release(self, reason: str, limit: int, lower_bound: int) -> None:
        """Process the stored values with their counts, then stream.

        The table may already hold values counted after the one that released
        it (``add_column``): processing them now, with their counts, gives the
        same results as streaming them.
        """
        table = self.table
        budget = self.context.budget
        budget.tracked -= self.distinct
        del budget.live[self.sequence]
        self.table = None
        limited = Limited(reason=reason, limit=limit, lower_bound=lower_bound)
        keys, counts = list(table), list(table.values())
        pool = self.context.pool
        if pool is not None:
            self.remote = pool.release(self.sequence, keys, counts, limited, self.scalars)
        else:
            self._local().release(keys, counts, limited, self.scalars)

    def _local(self) -> ValueProcessor:
        processor = self.processor
        if processor is None:
            processor = self.processor = ValueProcessor(self.context)
        return processor

    def _stream(self, key: Key) -> None:
        pending = self.pending
        count = pending.get(key)
        if count is not None:
            pending[key] = count + 1
            return
        pending[key] = 1
        if len(pending) >= BATCH_SIZE:
            self.flush()

    def flush(self) -> None:
        """Process the streaming batch."""
        pending = self.pending
        if not pending:
            return
        self.pending = Counter()
        keys, counts = list(pending), list(pending.values())
        if self.remote is not None:
            self.context.pool.process(
                self.remote, self.sequence, keys, counts, self.scalars
            )
        else:
            self._local().process(keys, counts, scalars=self.scalars)

    def _ends(self) -> tuple:
        """First and last values, and native boolean counts."""
        return (
            self.first,
            (self.last_type, self.last_value, self.last_record),
            self.true,
            self.false,
        )

    def submit(self) -> None:
        """Hand the finalization of the field to the worker pool, which runs
        the fields of a scan in parallel."""
        pool = self.context.pool
        if self.remote is not None:
            self.flush()
            pool.finish(self.remote, self.sequence, self._ends())
        elif self.table is not None:
            table = self.table
            self.remote = pool.table(
                self.sequence, list(table), list(table.values()), self._ends(),
                self.scalars,
            )

    def finalize(
        self, report_failure: FailureReporter, report_probe: ProbeReporter | None = None
    ) -> dict:
        if self.remote is not None:
            return self.context.pool.result(self.sequence, report_failure, report_probe)
        if self.table is None:
            self.flush()
        return self._local().finalize(
            self.table, self._ends(), report_failure, report_probe, self.scalars
        )


class ValueProcessor:
    """Per-value work of one field: normalization, measures, detector tallies,
    samples once released, and adaptive detection (design 9 to 13).

    Adaptive detection (design 13): the first ``warmup_values`` distinct
    values, in first-seen order, go through every detector. The next one
    decides which detectors stay; the others skip every later value except
    probes. A streamed field keeps its warm-up values, so their later
    occurrences are still classified by every detector, as in a table.
    """

    __slots__ = (
        "context",
        "decided",
        "limited",
        "measures",
        "samples",
        "scalars",
        "seen",
        "skipping",
        "warm",
    )

    def __init__(self, context: ValueContext) -> None:
        self.context = context
        self.measures = ValueMeasures(context.detectors.tallies())
        # First distinct analytical values with their counts, once released.
        self.samples: dict[tuple[str, str], int] | None = None
        # The limit that released the table, if any.
        self.limited: Limited | None = None
        # Whether a value other than a string was seen.
        self.scalars = False
        # Adaptive detection: distinct values of the warm-up so far, whether
        # the warm-up is over, the detectors skipped after it, and the
        # warm-up values of a streamed field.
        self.seen = 0
        self.decided = not context.detectors.warmup_values
        self.skipping: tuple[bool, ...] | None = None
        self.warm: set[Key] | None = None

    def release(
        self, keys: list[Key], counts: list[int], limited: Limited, scalars: bool
    ) -> None:
        """Process the values of a released table, then expect streamed
        values."""
        self.limited = limited
        self.measures.numeric.median_values = None
        self.samples = {}
        self.process(keys, counts, scalars=scalars)
        self.warm = set(keys[: self.context.detectors.warmup_values])

    def process(
        self,
        keys: list[Key],
        counts: list[int],
        collected: Collected | None = None,
        scalars: bool = False,
    ) -> None:
        """Account for distinct values with their counts, in first-seen order.

        The first ``warmup_values`` distinct values go through every detector;
        the next one decides which detectors are skipped (design 13).
        """
        if scalars:
            self.scalars = True
        if not self.decided:
            end, warmup = self._warmup(keys)
            if end:
                self._measure(keys[:end], counts[:end], None, collected, warmup)
            if end == len(keys):
                return
            self.decided = True
            self.skipping = self.context.detectors.skipping(self.measures.tallies)
            keys, counts = keys[end:], counts[end:]
        tested = rewarm = None
        if self.skipping is not None:
            # Warm-up values of a streamed field and probes are tested by
            # every detector.
            warm = self.warm
            probe = self._probe
            if warm is None:
                tested = [position for position, key in enumerate(keys) if probe(key)]
            else:
                tested = []
                rewarm = set()
                for position, key in enumerate(keys):
                    if key in warm:
                        tested.append(position)
                        rewarm.add(position)
                    elif probe(key):
                        tested.append(position)
        self._measure(keys, counts, tested, collected, None, rewarm)

    def _warmup(self, keys: list[Key]) -> tuple[int, tuple]:
        """Count the new distinct values of the warm-up; returns the position
        of the first value after it, or ``len(keys)``, with the positions of
        the values met for the first time and, among them, those of the
        second half of the warm-up."""
        warm = self.warm
        limit = self.context.detectors.warmup_values
        half = limit // 2
        seen = self.seen
        if warm is None:
            # A table: every value is new.
            end = min(len(keys), limit - seen)
            self.seen = seen + end
            return end, (range(end), range(max(0, half - seen), end))
        fresh: set[int] = set()
        recent: set[int] = set()
        for position, key in enumerate(keys):
            if key in warm:
                continue
            if self.seen >= limit:
                return position, (fresh, recent)
            if self.seen >= half:
                recent.add(position)
            self.seen += 1
            # A streamed field recognizes its warm-up values.
            warm.add(key)
            fresh.add(position)
        return len(keys), (fresh, recent)

    def _probe(self, key: Key) -> bool:
        """About one distinct value in ``probe_interval``, chosen by a stable
        hash of the value, goes through every detector after the warm-up."""
        interval = self.context.detectors.probe_interval
        if not interval:
            return False
        text = key if type(key) is str else f"{key[0]}:{key[1]}"
        return zlib.crc32(text.encode("utf-8", "surrogatepass")) % interval == 0

    # Measures ------------------------------------------------------------------

    def _measure(
        self,
        keys: list[Key],
        counts: list[int],
        tested: list[int] | None,
        collected: Collected | None,
        warmup: tuple | None = None,
        rewarm: set[int] | None = None,
    ) -> None:
        """Facts of distinct values with their counts: ``tested`` lists the
        positions that skipped detectors still test, ``None`` when no detector
        is skipped, among which ``rewarm`` are warm-up values; ``warmup``
        locates the values first met in the warm-up (``_warmup``)."""
        if not self.scalars:
            texts = self._strings(keys, counts, tested, collected, warmup, rewarm)
            typed = None
        else:
            texts, typed = self._mixed(
                keys, counts, tested, collected, warmup, rewarm
            )
        if collected is not None:
            analytical = collected[0]
            for position, (text, count) in enumerate(zip(texts, counts, strict=True)):
                value = ("string" if typed is None else typed[position], text)
                analytical[value] = analytical.get(value, 0) + count
        elif self.samples is not None:
            # Samples keep the first distinct analytical values with their
            # complete counts (design 9.1).
            samples = self.samples
            room = self.context.max_samples - len(samples)
            longest = self.context.max_stored_length
            for position, (text, count) in enumerate(zip(texts, counts, strict=True)):
                value = ("string" if typed is None else typed[position], text)
                known = samples.get(value)
                if known is not None:
                    samples[value] = known + count
                elif room > 0 and len(text) <= longest:
                    samples[value] = count
                    room -= 1

    def _strings(
        self,
        raws: list[str],
        counts: list[int],
        tested: list[int] | None,
        collected: Collected | None,
        warmup: tuple | None = None,
        rewarm: set[int] | None = None,
    ) -> list[str]:
        """Normalize and classify distinct content strings; returns their
        analytical texts."""
        context = self.context
        measures = self.measures
        detectors = context.detectors
        texts, lengths = measures.add_strings(
            raws,
            counts,
            context.normalizer,
            None if collected is None else collected[1],
        )
        numbers, dates = detectors.run(
            measures.tallies,
            "string",
            texts,
            counts,
            lengths,
            self.skipping if tested is not None else None,
            tested or (),
            warmup,
            rewarm,
        )
        detectors.add_string_measures(measures, texts, counts, lengths, numbers, dates)
        return texts

    def _mixed(
        self,
        keys: list[Key],
        counts: list[int],
        tested: list[int] | None,
        collected: Collected | None,
        warmup: tuple | None = None,
        rewarm: set[int] | None = None,
    ) -> tuple[list[str], list[str]]:
        """Distinct values of several native types: each type is processed on
        its own, unless a detector accepts several of the types present, whose
        tallies then need the values in first-seen order: runs of one type."""
        types = ["string" if type(key) is str else key[0] for key in keys]
        present = set(types)
        detectors = self.context.detectors
        tested_set = None if tested is None else set(tested)
        if len(present) > 1 and detectors.spans(present):
            groups = []
            start = 0
            for position in range(1, len(keys) + 1):
                if position == len(keys) or types[position] != types[start]:
                    groups.append((types[start], range(start, position)))
                    start = position
        else:
            positions: dict[str, list[int]] = {}
            for position, native_type in enumerate(types):
                positions.setdefault(native_type, []).append(position)
            groups = list(positions.items())
        texts: list[str] = [""] * len(keys)
        for native_type, group in groups:
            group_keys = [keys[position] for position in group]
            group_counts = [counts[position] for position in group]
            group_tested = (
                None
                if tested_set is None
                else [
                    offset
                    for offset, position in enumerate(group)
                    if position in tested_set
                ]
            )
            group_warmup = (
                None
                if warmup is None
                else tuple(_offsets(group, positions) for positions in warmup)
            )
            group_rewarm = None if rewarm is None else _offsets(group, rewarm)
            if native_type == "string":
                group_texts = self._strings(
                    group_keys,
                    group_counts,
                    group_tested,
                    collected,
                    group_warmup,
                    group_rewarm,
                )
            else:
                group_texts = self._scalars(
                    native_type,
                    group_keys,
                    group_counts,
                    group_tested,
                    group_warmup,
                    group_rewarm,
                )
            for position, text in zip(group, group_texts, strict=True):
                texts[position] = text
        return texts, types

    def _scalars(
        self,
        native_type: str,
        keys: list[tuple[str, object]],
        counts: list[int],
        tested: list[int] | None,
        warmup: tuple | None = None,
        rewarm: set[int] | None = None,
    ) -> list[str]:
        """Integers, numbers or booleans: their own technical family and, but
        for booleans, numbers; detectors that accept the type see their
        canonical text (design 9.1). Returns the canonical texts."""
        measures = self.measures
        families = measures.families
        families[native_type] = families.get(native_type, 0) + sum(counts)
        if native_type == "number":
            numbers = [Decimal(form) for _, form in keys]
            texts = [str(number) for number in numbers]
        else:
            numbers = [value for _, value in keys]
            texts = [canonical_text(native_type, value) for value in numbers]
        if native_type != "boolean":
            numeric = measures.numeric
            decimal_form = native_type == "number"
            for number, count in zip(numbers, counts, strict=True):
                numeric.add(number, decimal_form, True, count)
        detectors = self.context.detectors
        if detectors.accepts(native_type):
            detectors.run(
                measures.tallies,
                native_type,
                texts,
                counts,
                None,
                self.skipping if tested is not None else None,
                tested or (),
                warmup,
                rewarm,
            )
        return texts

    # Finalization -----------------------------------------------------------

    def _value_at(
        self, native_type: str, value: object, record: int, gate: ExposureGate
    ) -> ValueAt | None:
        if native_type == "string":
            text = self.context.normalizer.analytical(value)
        else:
            text = canonical_text(native_type, value)
        exposed = gate.value(text)
        if exposed is None:
            return None
        return ValueAt(value=exposed, type=native_type, record=record)

    def finalize(
        self,
        table: dict[Key, int] | None,
        ends: tuple,
        report_failure: FailureReporter,
        report_probe: ProbeReporter | None = None,
        scalars: bool = False,
    ) -> dict:
        """The value blocks of the field; ``table`` is its complete frequency
        table, ``None`` once released, ``ends`` its first and last values and
        native boolean counts (``ValueTracker._ends``), and ``scalars`` says
        whether it holds values other than strings."""
        context = self.context
        measures = self.measures
        if scalars:
            self.scalars = True
        first, last, true, false = ends
        if table is not None:
            # Complete table: per-value work once per distinct value.
            analytical: dict[tuple[str, str], int] = {}
            # Stage outputs of the strings that a stage changed; every other
            # value is its own output at every stage.
            changed: dict[str, tuple[str, ...]] = {}
            self.process(list(table), list(table.values()), (analytical, changed))
            changes = reduce(or_, measures.changes, 0)
        detectors = context.detectors
        # Every value is now tallied: the field's sensitivity is known.
        exposure = detectors.gate(measures.tallies)
        gate = SHOW if exposure is None else exposure
        if table is not None:
            cardinality = Complete[int](value=len(table))
            stage_cardinality = _stage_cardinalities(
                context.normalizer, table, changed, changes
            )
            variant_groups = (
                _variant_groups(table, changed, context, gate)
                if measures.lengths
                else _NO_VALUES
            )
            # Listings describe exposed values: equal masks merge first.
            exposed = gate.typed_counts(analytical.items())
            distinct = len(exposed) if gate.mode == "mask" else len(analytical)
            ranked = heapq.nsmallest(
                context.max_listed,
                exposed.items(),
                key=lambda item: (-item[1], item[0][1], _TYPE_ORDER[item[0][0]]),
            )
            frequencies = Complete[Frequencies](
                value=Frequencies(
                    distinct=distinct,
                    listed=_listing(ranked),
                    truncated=distinct > len(ranked),
                )
            )
            samples = _samples(analytical, exposed, context.max_samples, context.seed)
        else:
            limited = self.limited
            cardinality = limited
            # Raw distinct values do not prove normalized ones: no bound.
            unproven = Limited(reason=limited.reason, limit=limited.limit)
            frequencies = unproven
            samples = Samples(
                selection="first_seen",
                listed=_listing(gate.typed_counts(self.samples.items()).items()),
            )
            stage_cardinality = dict.fromkeys(range(len(STAGES)), unproven)
            variant_groups = unproven if measures.lengths else _NO_VALUES
        results = detectors.results(measures.tallies, report_failure, gate, report_probe)
        # Statistics such as a minimum or a date range are values themselves:
        # a masked or hidden field withholds them (design 12.8).
        withheld = gate.mode != "show"
        return {
            "cardinality": cardinality,
            "frequencies": frequencies,
            "samples": samples,
            "first": self._value_at(*first, gate),
            "last": self._value_at(*last, gate),
            "string_characteristics": measures.string_characteristics(),
            "string_lengths": measures.string_lengths(),
            "numeric": (
                _WITHHELD if withheld else measures.numeric.finalize(self.limited)
            ),
            "booleans": (
                Complete[BooleanCounts](value=BooleanCounts(true=true, false=false))
                if true or false
                else _NO_VALUES
            ),
            "temporal": (
                _WITHHELD if withheld else detectors.temporal(measures.tallies, results)
            ),
            "normalization": _normalization(
                context.normalizer,
                cardinality,
                measures.changed,
                stage_cardinality,
                variant_groups,
            ),
            "technical_type": technical_type(
                measures.families, context.minimum_confidence
            ),
            "detectors": results,
            "interpretations": detectors.interpretations(results),
            "sensitive": exposure is not None,
            "exposure": None if exposure is None else exposure.mode,
        }


def _offsets(group, positions) -> set[int]:
    """Offsets in ``group`` of the batch positions it shares with
    ``positions``."""
    return {offset for offset, position in enumerate(group) if position in positions}


def _stored_length(key: Key) -> int:
    """Length of the canonical text a table entry stands for."""
    if type(key) is str:
        return len(key)
    native_type, form = key
    return len(form) if native_type == "number" else len(canonical_text(*key))


def _normalization(
    normalizer: Normalizer,
    raw_cardinality,
    changed: list[int],
    cardinality: dict[int, object],
    variant_groups,
) -> Normalization:
    """Stages in order, ``raw`` first; disabled stages have no counts."""
    stages = [
        NormalizationStage(
            stage="raw", enabled=True, changed=None, cardinality=raw_cardinality
        )
    ]
    for i, (stage, enabled) in enumerate(zip(STAGES, normalizer.enabled)):
        stages.append(
            NormalizationStage(
                stage=stage,
                enabled=enabled,
                changed=changed[i] if enabled else None,
                cardinality=cardinality[i] if enabled else None,
            )
        )
    return Normalization(version=VERSION, stages=stages, variant_groups=variant_groups)


def _stage_cardinalities(
    normalizer: Normalizer,
    table: dict[Key, int],
    changed: dict[str, tuple[str, ...]],
    changes: int,
) -> dict[int, Complete[int]]:
    """Distinct values after each enabled stage of a complete table.

    A stage that changed no value keeps the count of the previous one.
    Otherwise its outputs are the outputs of the changed strings plus the
    unchanged values, each its own output: a string key of the table that is
    not in ``changed`` is an unchanged string, so it merges with an equal
    output.
    """
    result = {}
    previous = len(table)
    unchanged = len(table) - len(changed)
    for i, enabled in enumerate(normalizer.enabled):
        if not enabled:
            continue
        if changes >> i & 1:
            outputs = {forms[i] for forms in changed.values()}
            merged = sum(1 for form in outputs if form in table and form not in changed)
            previous = unchanged + len(outputs) - merged
        result[i] = Complete[int](value=previous)
    return result


def _variant_groups(
    table: dict[Key, int],
    changed: dict[str, tuple[str, ...]],
    context: ValueContext,
    gate: ExposureGate,
):
    """Comparison keys with at least two distinct raw variants, most frequent
    first, then by key; variants by count, then value.

    An unchanged string is its own comparison key, so it joins the group of
    the changed strings with that key. Under ``mask``, groups with equal
    masked keys merge, and so do equal masked variants of a group; ``hide``
    keeps the number of groups only.
    """
    variants: dict[str, list[str]] = {}
    for raw, forms in changed.items():
        key = forms[KEY_STAGE]
        raws = variants.get(key)
        if raws is None:
            variants[key] = [raw]
        else:
            raws.append(raw)
    for key, raws in variants.items():
        if key in table and key not in changed:
            raws.append(key)
    # Per exposed group key: the count of each exposed variant.
    grouped: dict[str, dict[str, int]] = {}
    for key, raws in variants.items():
        if len(raws) < 2:
            continue
        if gate.hides:
            grouped[key] = {}
            continue
        counts = grouped.setdefault(gate.value(key), {})
        for raw, count in gate.counts((raw, table[raw]) for raw in raws).items():
            counts[raw] = counts.get(raw, 0) + count
    if gate.hides:
        return Complete[VariantGroups](
            value=VariantGroups(groups=len(grouped), listed=[], truncated=bool(grouped))
        )
    groups = [(sum(counts.values()), key, counts) for key, counts in grouped.items()]
    ranked = heapq.nsmallest(
        context.max_variant_groups, groups, key=lambda item: (-item[0], item[1])
    )
    listed = []
    for count, key, counts in ranked:
        top = heapq.nsmallest(
            context.max_variants, counts.items(), key=lambda item: (-item[1], item[0])
        )
        listed.append(
            VariantGroup(
                key=key,
                count=count,
                distinct=len(counts),
                variants=[Variant(value=raw, count=n) for raw, n in top],
                truncated=len(counts) > len(top),
            )
        )
    return Complete[VariantGroups](
        value=VariantGroups(
            groups=len(groups), listed=listed, truncated=len(groups) > len(listed)
        )
    )


def _listing(items) -> list[ValueCount]:
    return [
        ValueCount(value=text, type=native_type, count=count)
        for (native_type, text), count in items
    ]


def _samples(
    analytical: dict[tuple[str, str], int],
    exposed: dict[tuple[str, str], int],
    size: int,
    seed: int,
) -> Samples:
    """Every distinct exposed value, or a seeded uniform sample, in first-seen
    order. Hidden values keep the selection of the analytical values."""
    if analytical and not exposed:
        selection = "all" if len(analytical) <= size else "uniform_distinct"
        return Samples(selection=selection, listed=[])
    items = list(exposed.items())
    if len(items) <= size:
        return Samples(selection="all", listed=_listing(items))
    chosen = sorted(random.Random(seed).sample(range(len(items)), size))
    return Samples(
        selection="uniform_distinct", listed=_listing(items[i] for i in chosen)
    )


def no_values(context: ValueContext) -> dict:
    """Value blocks of a field without analyzable values (design 9.9)."""
    detectors = context.detectors
    results = detectors.results(None, _no_failure)
    return {
        "cardinality": _NO_VALUES,
        "frequencies": _NO_VALUES,
        "samples": Samples(selection="all", listed=[]),
        "first": None,
        "last": None,
        "string_characteristics": ValueMeasures().string_characteristics(),
        "string_lengths": _NO_VALUES,
        "numeric": _NO_VALUES,
        "booleans": _NO_VALUES,
        "temporal": detectors.temporal(None, results),
        "normalization": _normalization(
            context.normalizer,
            _NO_VALUES,
            [0] * len(STAGES),
            dict.fromkeys(range(len(STAGES)), _NO_VALUES),
            _NO_VALUES,
        ),
        "technical_type": technical_type({}, context.minimum_confidence),
        "detectors": results,
        "interpretations": detectors.interpretations(results),
        "sensitive": False,
        "exposure": None,
    }


def _no_failure(detector: str, error: str) -> int:
    raise AssertionError("A detector without values cannot fail")

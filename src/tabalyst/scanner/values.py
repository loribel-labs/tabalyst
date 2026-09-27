"""Raw frequency tables, budgets, samples and first/last values (design
sections 9.1, 11 and 13).

Each field with values keeps a raw frequency table keyed by native type and
canonical form, so the string ``"123"`` and the integer ``123`` stay apart.
While the table is complete, per-value work runs once per distinct value at
finalization. When a limit releases the table, its stored values are processed
with their counts and the field switches to streaming, through a bounded
cache. Both modes give the same results.
"""

from __future__ import annotations

import heapq
import random
from decimal import Decimal

from tabalyst.scanner.config import ScanConfig, exact_share
from tabalyst.scanner.detectors.registry import DetectorSet, FailureReporter
from tabalyst.scanner.measures import (
    CHANGES,
    FORMS,
    Facts,
    ValueMeasures,
    canonical_text,
    scalar_facts,
    string_facts,
)
from tabalyst.scanner.models import (
    BooleanCounts,
    Complete,
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

# Streaming memoization: cleared when full, so memory stays bounded.
CACHE_SIZE = 4_096
_TYPE_ORDER = {"string": 0, "integer": 1, "number": 2, "boolean": 3}
_NO_VALUES = NotApplicable(reason="no_values")

# Table keys: a raw string is its own key; other values are
# ``(native type, canonical form)`` tuples, which never equal a string.
Key = str | tuple[str, object]


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
    """Values of one field: raw table or streaming, first and last values."""

    __slots__ = (
        "cache",
        "context",
        "distinct",
        "false",
        "first",
        "last_record",
        "last_type",
        "last_value",
        "limited",
        "measures",
        "samples",
        "sequence",
        "table",
        "true",
    )

    def __init__(self, context: ValueContext, sequence: int) -> None:
        self.context = context
        self.table: dict[Key, int] | None = {}
        self.distinct = 0
        self.limited: Limited | None = None
        self.measures = ValueMeasures(context.detectors.tallies())
        # First distinct analytical values with their counts, once released.
        self.samples: dict[tuple[str, str], int] | None = None
        self.cache: dict[Key, Facts] = {}
        self.first: tuple[str, object, int] | None = None
        self.last_type = ""
        self.last_value: object = None
        self.last_record = 0
        self.true = 0
        self.false = 0
        self.sequence = sequence
        context.budget.live[sequence] = self

    def add(self, native_type: str, value: object, record: int) -> None:
        if self.first is None:
            self.first = (native_type, value, record)
        self.last_type = native_type
        self.last_value = value
        self.last_record = record
        if native_type == "string":
            key = value
        elif native_type == "number":
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

    def release(self, reason: str, limit: int, lower_bound: int) -> None:
        """Process the stored values with their counts, then stream."""
        table = self.table
        budget = self.context.budget
        budget.tracked -= len(table)
        del budget.live[self.sequence]
        self.table = None
        self.limited = Limited(reason=reason, limit=limit, lower_bound=lower_bound)
        self.measures.numeric.median_values = None
        self.samples = {}
        for key, count in table.items():
            self._process(self._facts(key), count)

    def _facts(self, key: Key) -> Facts:
        context = self.context
        if type(key) is str:
            return string_facts(key, context.normalizer, context.detectors)
        native_type, form = key
        if native_type == "number":
            form = Decimal(form)
        return scalar_facts(native_type, form, context.detectors)

    def _process(self, facts: Facts, count: int) -> None:
        """Account for ``count`` occurrences once the table is released."""
        self.measures.add(facts, count)
        # Samples keep the first distinct analytical values and their counts.
        samples = self.samples
        value = (facts[0], facts[1])
        known = samples.get(value)
        if known is not None:
            samples[value] = known + count
        elif (
            len(samples) < self.context.max_samples
            and len(facts[1]) <= self.context.max_stored_length
        ):
            samples[value] = count

    def _stream(self, key: Key) -> None:
        cache = self.cache
        facts = cache.get(key)
        if facts is None:
            if len(cache) >= CACHE_SIZE:
                cache.clear()
            facts = self._facts(key)
            if facts[FORMS] is not None:
                # Stage outputs serve complete tables only: do not cache them.
                facts = (*facts[:FORMS], None, *facts[FORMS + 1 :])
            cache[key] = facts
        self._process(facts, 1)

    # Finalization -----------------------------------------------------------

    def _value_at(self, native_type: str, value: object, record: int) -> ValueAt:
        if native_type == "string":
            text = self.context.normalizer.analytical(value)
        else:
            text = canonical_text(native_type, value)
        return ValueAt(value=text, type=native_type, record=record)

    def finalize(self, report_failure: FailureReporter) -> dict:
        context = self.context
        table = self.table
        measures = self.measures
        if table is not None:
            # Complete table: per-value work once per distinct value.
            analytical: dict[tuple[str, str], int] = {}
            # Stage outputs of the strings that a stage changed; every other
            # value is its own output at every stage.
            changed: dict[str, tuple[str, ...]] = {}
            changes = 0
            for key, count in table.items():
                facts = self._facts(key)
                measures.add(facts, count)
                value = (facts[0], facts[1])
                analytical[value] = analytical.get(value, 0) + count
                if facts[CHANGES]:
                    changes |= facts[CHANGES]
                    changed[key] = facts[FORMS]
            cardinality = Complete[int](value=len(table))
            stage_cardinality = _stage_cardinalities(
                context.normalizer, table, changed, changes
            )
            variant_groups = (
                _variant_groups(table, changed, context)
                if measures.lengths
                else _NO_VALUES
            )
            ranked = heapq.nsmallest(
                context.max_listed,
                analytical.items(),
                key=lambda item: (-item[1], item[0][1], _TYPE_ORDER[item[0][0]]),
            )
            frequencies = Complete[Frequencies](
                value=Frequencies(
                    distinct=len(analytical),
                    listed=_listing(ranked),
                    truncated=len(analytical) > context.max_listed,
                )
            )
            samples = _samples(analytical, context.max_samples, context.seed)
        else:
            limited = self.limited
            cardinality = limited
            # Raw distinct values do not prove normalized ones: no bound.
            unproven = Limited(reason=limited.reason, limit=limited.limit)
            frequencies = unproven
            samples = Samples(
                selection="first_seen", listed=_listing(self.samples.items())
            )
            stage_cardinality = dict.fromkeys(range(len(STAGES)), unproven)
            variant_groups = unproven if measures.lengths else _NO_VALUES
        detectors = context.detectors
        results = detectors.results(measures.tallies, report_failure)
        return {
            "cardinality": cardinality,
            "frequencies": frequencies,
            "samples": samples,
            "first": self._value_at(*self.first),
            "last": self._value_at(self.last_type, self.last_value, self.last_record),
            "string_characteristics": measures.string_characteristics(),
            "string_lengths": measures.string_lengths(),
            "numeric": measures.numeric.finalize(self.limited),
            "booleans": (
                Complete[BooleanCounts](
                    value=BooleanCounts(true=self.true, false=self.false)
                )
                if self.true or self.false
                else _NO_VALUES
            ),
            "temporal": detectors.temporal(measures.tallies, results),
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
        }


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
    table: dict[Key, int], changed: dict[str, tuple[str, ...]], context: ValueContext
):
    """Comparison keys with at least two distinct raw variants, most frequent
    first, then by key; variants by count, then value.

    An unchanged string is its own comparison key, so it joins the group of
    the changed strings with that key.
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
    groups = [
        (sum(table[raw] for raw in raws), key, raws)
        for key, raws in variants.items()
        if len(raws) > 1
    ]
    ranked = heapq.nsmallest(
        context.max_variant_groups, groups, key=lambda item: (-item[0], item[1])
    )
    listed = []
    for count, key, raws in ranked:
        top = heapq.nsmallest(
            context.max_variants, raws, key=lambda raw: (-table[raw], raw)
        )
        listed.append(
            VariantGroup(
                key=key,
                count=count,
                distinct=len(raws),
                variants=[Variant(value=raw, count=table[raw]) for raw in top],
                truncated=len(raws) > len(top),
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


def _samples(analytical: dict[tuple[str, str], int], size: int, seed: int) -> Samples:
    """Every distinct value, or a seeded uniform sample, in first-seen order."""
    items = list(analytical.items())
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
    }


def _no_failure(detector: str, error: str) -> int:
    raise AssertionError("A detector without values cannot fail")

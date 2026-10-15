# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The targets of a smart sample, by family (design 20.15, specification 15.2).

A target is a thing worth having in the sample: a value of a category, a pattern,
an extreme, a period, a problem the Scan found, an exception to a learned
relation. They are built from the finished Scan and, when it is current, the
second-pass document, before the source is read again (SMART-04). A target names
what it stands for by reference into those documents and never holds a value of
the data.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Literal, NamedTuple

from tabalyst.config import SmartSettings
from tabalyst.scanner.models import (
    CardinalityComplete,
    CardinalityLimited,
    DatasetResult,
    FieldPatternsComplete,
    FieldResult,
    Observation,
    ScanResult,
)
from tabalyst.scanner.secondpass.models import (
    AnalysisResult,
    BinnedHistogram,
    CrosstabResult,
    DateOrderResult,
    DeepResult,
    DenseHistogram,
    FrequencyTable,
    PatternCounts,
    ResidualResult,
)
from tabalyst.scanner.smart.bins import bin_index
from tabalyst.scanner.smart.models import (
    Catalog,
    Evidence,
    Family,
    Feasibility,
    Frequency,
    FrequencyAccuracy,
    Obligation,
    Predicate,
    PredicateKind,
    Target,
)
from tabalyst.scanner.smart.near import NearGroup, near_groups
from tabalyst.scanner.smart.weights import BaseKind, weight_of

# More periods than this are a distribution, not a list of targets.
MAX_PERIODS = 30
# Groups of variants of one column that get a target, the largest first: a column
# of free text with accents and capitals in thousands of groups is not a list.
MAX_VARIANT_GROUPS = 20

# What the Scan observed that a sample can recognize on a row, by rule of the
# observation; and what it cannot yet, with the reason. The other rules describe
# a column or the file (names, normalization remarks), not a row.
EVALUABLE_RULES = frozenset(
    {
        "mixed_types",
        "type_outliers",
        "ambiguous_dates",
        "minority_pattern",
        "missing_values",
        "duplicate_rows",
        "minority_length",
        "variant_groups",
        "trimmed_cells",
        "collapsed_whitespace",
    }
)
# No rule waits for a test on a row today; a rule the Scan gains before the
# sample can recognize it goes here, with a code of ``reasons.FEASIBILITY``.
NOT_EVALUABLE_RULES: dict[str, str] = {}

# The characteristics of the strings of a column that nobody expects in data
# (control characters, line breaks, tabulations, non-breaking spaces, invisible
# characters, the replacement character, non-ASCII characters), and the share
# of the strings at or below which they stand out: a column of free text that
# has line breaks everywhere is a format.
UNEXPECTED_CHARACTERISTICS = (
    "with_control_characters",
    "with_line_breaks",
    "with_tabs",
    "with_non_breaking_spaces",
    "with_invisible_characters",
    "with_replacement_character",
    "non_ascii",
)
RARE_CHARACTERISTIC_SHARE = 0.05
# The values a column holds once make a tail worth a target only when they are few
# next to its rows: in an identifier every value is seen once.
MAX_TAIL_SHARE = 0.2
# The values a detector leaves out, one target each (the second pass lists at most
# 20 per table): beyond this share of the column they are its format, not defects.
MAX_RESIDUAL_VALUES = 20
# And in all the columns of a dataset: a file full of invalid values must not fill a
# small sample with them (the first columns win).
MAX_RESIDUAL_TARGETS = 100
MAX_RESIDUAL_SHARE = 0.2
# Groups of near values (typos of a category) are optional signals: a sample smaller than
# this share of its mandatory targets cannot hold even those, and a typo would take the
# place of a value of a list (measured on the case of injected errors at 100 rows).
NEAR_MIN_MANDATORY_SHARE = 0.75

# Analyzers of the second pass that bring or sharpen the targets of a family.
ENRICHES: dict[str, Family] = {
    "numeric_histogram": "numeric",
    "pattern_validation": "structured_string",
    "category_crosstab": "relations",
}


@dataclass
class TargetSet:
    """What the builders found, before the budget of targets is applied."""

    targets: list[Target] = dataclass_field(default_factory=list)
    catalogs: list[Catalog] = dataclass_field(default_factory=list)
    # Groups of near values over the caps of the settings, counted in the plan.
    capped: int = 0


class _NearSource(NamedTuple):
    """The ``(text, rows)`` table a column's near values are looked for in, and how a
    target names the entries of the table it is made of."""

    table: list[tuple[str, int]]
    ids: list[int]
    source: Literal["scan", "second_pass"]
    ref: str
    origin: str | None


def _share(count: int, records: int) -> float | None:
    if records <= 0:
        return None
    # Twelve decimals: the weight reads this share, and a floor below 1e-6 must
    # still tell a value seen once from one seen four times in ten million rows.
    return round(min(1.0, count / records), 12)


class _Builder:
    def __init__(
        self,
        scan: ScanResult,
        dataset: DatasetResult,
        deep: DeepResult | None,
        settings: SmartSettings,
        size: int | None = None,
    ) -> None:
        self.size = size
        self.scan = scan
        self.dataset = dataset
        self.deep = deep
        self.settings = settings
        self.records = dataset.record_count
        self.fields = {field.id: field for field in dataset.fields}
        self.result = TargetSet()
        # Columns whose every value has a target: the other families have
        # nothing to add to them.
        self.enumerated: set[str] = set()
        # Columns with one mandatory target per value: their typos are values of the list.
        self.listed_whole: set[str] = set()
        # Columns that already have a target for their empty cells: the
        # observation of missing values would only repeat it.
        self.missing_targeted: set[str] = set()
        # Targets made from the values a detector leaves out, in the whole dataset.
        self.residual_targets = 0
        # The columns that have groups of near values, in file order, until the rows
        # asked for are shared between them.
        self.near_candidates: list[tuple[FieldResult, _NearSource, list[NearGroup]]] = []
        # Several tables can share the same two columns (one per feature), so the
        # analyses are a list, not a map keyed by the columns.
        self.analyses: list[AnalysisResult] = []
        if deep is not None:
            self.analyses = [
                a for a in deep.analyses if a.dataset == dataset.id and a.status == "complete"
            ]

    def analysis(self, analyzer: str, field_id: str) -> AnalysisResult | None:
        """The result of an analyzer on one field, when the second pass has it."""
        for item in self.analyses:
            if item.analyzer == analyzer and item.field == field_id and item.partner is None:
                return item
        return None

    def withheld(self, field: FieldResult) -> bool:
        return field.exposure in ("mask", "hide")

    def add(
        self,
        family: Family,
        field_ids: list[str],
        kind: PredicateKind,
        discriminator: str,
        *,
        base: BaseKind,
        frequency: Frequency,
        evidence: Evidence,
        obligation: Obligation = "optional",
        source: Literal["scan", "second_pass"] = "scan",
        ref: str | None = None,
        params: dict[str, int | str] | None = None,
        origin: str | None = None,
        feasibility: Feasibility = "ready",
        reason: str | None = None,
    ) -> None:
        name = ":".join(
            [family, self.dataset.id, "+".join(field_ids) or "-", kind, discriminator]
        ).rstrip(":")
        displays = [self.fields[i].display for i in field_ids if i in self.fields]
        self.result.targets.append(
            Target(
                id=name,
                family=family,
                dataset=self.dataset.id,
                fields=field_ids,
                displays=displays,
                predicate=Predicate(kind=kind, source=source, ref=ref, params=params or {}),
                frequency=frequency,
                weight=weight_of(base, frequency.share, self.settings.weights),
                obligation=obligation,
                feasibility=feasibility,
                reason=reason,
                evidence=evidence,
                origin=origin,
                needs=["scan"] if source == "scan" and evidence != "second_pass" else ["scan", "second_pass"],
            )
        )

    def counted(
        self, count: int, accuracy: FrequencyAccuracy = "exact", method: str = "exact_count"
    ) -> Frequency:
        return Frequency(
            accuracy=accuracy, count=count, share=_share(count, self.records), method=method
        )

    def catalog(
        self,
        family: Family,
        field: FieldResult,
        *,
        complete: bool,
        targets: int,
        reasons: list[str],
    ) -> None:
        if targets == 0:
            guarantee: Literal["catalog_complete", "known_values_only", "none"] = "none"
        else:
            guarantee = "catalog_complete" if complete else "known_values_only"
        self.result.catalogs.append(
            Catalog(
                family=family,
                dataset=self.dataset.id,
                field=field.id,
                display=field.display,
                complete=complete and targets > 0,
                guarantee=guarantee,
                targets=targets,
                reasons=reasons,
            )
        )

    # Families ------------------------------------------------------------

    def low_cardinality(self, field: FieldResult) -> None:
        if self.withheld(field):
            self.catalog("low_cardinality", field, complete=False, targets=0, reasons=["exposure"])
            return
        samples = field.values.samples
        cardinality = field.values.cardinality
        missing = field.missing.count
        if field.values.count == 0:
            self.catalog("low_cardinality", field, complete=False, targets=0, reasons=["no_values"])
            return
        exhaustive = False
        if isinstance(cardinality, CardinalityComplete):
            distinct: int | None = cardinality.value
            exhaustive = (
                samples.selection == "all"
                and samples.kept == samples.of
                and samples.long_texts is None
            )
        elif isinstance(cardinality, CardinalityLimited) and cardinality.estimate is not None:
            distinct = round(cardinality.estimate.value)
        else:
            distinct = None
        if distinct is None:
            self.catalog(
                "low_cardinality", field, complete=False, targets=0, reasons=["domain_unknown"]
            )
            return
        if distinct > self.settings.max_enum_values or len(samples.listed) > self.settings.max_enum_values:
            if self.exact_values(field):
                return
            self.catalog(
                "low_cardinality", field, complete=False, targets=0, reasons=["high_cardinality"]
            )
            return
        if not samples.listed:
            self.catalog("low_cardinality", field, complete=False, targets=0, reasons=["long_texts"])
            return
        if distinct < 2 and missing == 0:
            self.catalog(
                "low_cardinality", field, complete=False, targets=0, reasons=["single_value"]
            )
            return
        obligation: Obligation = "mandatory" if exhaustive else "optional"
        where = f"datasets/{self.dataset.id}/fields/{field.id}/values/samples"
        for entry in samples.listed:
            accuracy: FrequencyAccuracy = "exact" if entry.count_accuracy == "exact" else "indicator"
            self.add(
                "low_cardinality",
                [field.id],
                "value_equals",
                str(entry.id),
                base="value",
                frequency=self.counted(entry.count, accuracy),
                evidence="exact",
                obligation=obligation,
                ref=where,
                params={"entry": entry.id},
            )
        count = len(samples.listed) + self.missing_target(field, obligation)
        self.catalog(
            "low_cardinality",
            field,
            complete=exhaustive,
            targets=count,
            reasons=[] if exhaustive else ["domain_not_exhaustive"],
        )
        if exhaustive:
            self.enumerated.add(field.id)
            self.listed_whole.add(field.id)

    def missing_target(self, field: FieldResult, obligation: Obligation) -> int:
        """The target of the empty cells of a column, when it has some; how many
        targets it made."""
        missing = field.missing.count
        if missing <= 0:
            return 0
        self.add(
            "low_cardinality",
            [field.id],
            "value_missing",
            "",
            base="value",
            frequency=self.counted(missing),
            evidence="exact",
            obligation=obligation,
            ref=f"datasets/{self.dataset.id}/fields/{field.id}/missing",
        )
        self.missing_targeted.add(field.id)
        return 1

    def exact_values(self, field: FieldResult) -> bool:
        """One target per value of a column the first pass could not list but the
        second pass counted exactly, up to ``max_exact_values``: the values the
        Scan sampled by hash miss half of the rare ones. They are optional (a
        sample need not hold every value of a column of hundreds) and stand on the
        analytical text, which is what the table counts. Whether it made targets."""
        analysis = self.analysis("exact_frequencies", field.id)
        table = analysis.result if analysis is not None else None
        if (
            analysis is None
            or not isinstance(table, FrequencyTable)
            or not 0 < len(table.values) == table.distinct <= self.settings.max_exact_values
            # The table is keyed by native type too, but a row is tested on its text.
            or len({entry.value for entry in table.values}) < len(table.values)
        ):
            return False
        for index, entry in enumerate(table.values):
            self.add(
                "low_cardinality",
                [field.id],
                "value_equals",
                str(index),
                base="exact_value",
                frequency=self.counted(entry.count, method="exact_frequencies"),
                evidence="second_pass",
                source="second_pass",
                ref=f"analyses/{analysis.id}",
                params={"entry": index},
                origin=analysis.id,
            )
        count = len(table.values) + self.missing_target(field, "optional")
        self.catalog("low_cardinality", field, complete=True, targets=count, reasons=[])
        # Only text is left to its values: a number or a date keeps its extremes,
        # signs, bins and years, which weigh more than any one of its values.
        if field.technical_type.type in ("text", "mixed"):
            self.enumerated.add(field.id)
        return True

    def structured_string(self) -> None:
        if self.scan.derived is None or self.scan.derived.patterns is None:
            return
        for entry in self.scan.derived.patterns.fields:
            if entry.dataset != self.dataset.id or not isinstance(entry, FieldPatternsComplete):
                continue
            field = self.fields.get(entry.field)
            if field is None or self.withheld(field) or field.id in self.enumerated:
                continue
            validated = self.analysis("pattern_validation", field.id)
            counts = (
                validated.result
                if validated is not None and isinstance(validated.result, PatternCounts)
                else None
            )
            tallies = {t.id: t.occurrences for t in counts.all_patterns()} if counts else {}
            evidence: Evidence = "second_pass" if counts else (
                "exact" if entry.population.complete and not entry.limits else "sample"
            )
            where = f"derived/patterns/{self.dataset.id}/{field.id}"
            made = 0
            total = entry.population.distinct
            for pattern in entry.all_patterns():
                if counts is not None and pattern.id in tallies:
                    frequency = self.counted(tallies[pattern.id], method="pattern_validation")
                else:
                    frequency = Frequency(
                        accuracy="indicator",
                        share=round(pattern.d / total, 4) if total else 0.0,
                        method="distinct_share",
                    )
                self.add(
                    "structured_string",
                    [field.id],
                    "pattern_matches",
                    pattern.id,
                    base="pattern",
                    frequency=frequency,
                    evidence=evidence,
                    ref=where,
                    params={"pattern": pattern.id},
                )
                made += 1
            unmatched = entry.outside_patterns()[0]
            # The second pass reads every occurrence: values no pattern reads
            # may exist though the sampled values were all read (a slash in a
            # column of dates written with hyphens).
            rest = counts.outside_patterns() if counts is not None else 0
            if unmatched > 0 or rest > 0:
                if counts is not None:
                    frequency = self.counted(
                        counts.outside_patterns(), method="pattern_validation"
                    )
                else:
                    frequency = Frequency(
                        accuracy="indicator",
                        share=round(unmatched / total, 4) if total else 0.0,
                        method="distinct_share",
                    )
                self.add(
                    "structured_string",
                    [field.id],
                    "pattern_other",
                    "",
                    base="pattern",
                    frequency=frequency,
                    evidence=evidence,
                    ref=where,
                )
                made += 1
            complete = entry.population.complete and not entry.limits
            self.catalog(
                "structured_string",
                field,
                complete=complete,
                targets=made,
                reasons=[] if complete else ["sample_basis"],
            )

    def lengths(self, field: FieldResult) -> None:
        envelope = field.string_lengths
        if envelope.status != "complete" or field.technical_type.type not in ("text", "mixed"):
            return
        stats = envelope.value
        if stats.min_length >= stats.max_length:
            return
        by_length = {item.length: item.count for item in stats.length_histogram}
        lengths: list[tuple[PredicateKind, int]] = [
            ("length_min", stats.min_length),
            ("length_max", stats.max_length),
        ]
        for kind, length in lengths:
            self.add(
                "structured_string",
                [field.id],
                kind,
                "",
                base="extreme",
                frequency=self.counted(by_length.get(length, 0), method="length_histogram"),
                evidence="exact",
                ref=f"datasets/{self.dataset.id}/fields/{field.id}/string_lengths",
                # The histogram counts the analytical text (design 21): a selection
                # that measured the original value would count other rows.
                params={"domain": "analytical"},
            )

    def numeric(self, field: FieldResult) -> None:
        envelope = field.numeric
        if (
            envelope.status != "complete"
            or field.technical_type.type not in ("integer", "number")
            or envelope.value.count == 0
        ):
            return
        stats = envelope.value
        where = f"datasets/{self.dataset.id}/fields/{field.id}/numeric"
        validated = self.analysis("numeric_histogram", field.id)
        histogram = validated.result if validated is not None else None
        dense = histogram.values if isinstance(histogram, DenseHistogram) else None
        at = {item.value: item.count for item in dense} if dense is not None else {}
        if stats.min < stats.max:
            extremes: list[tuple[PredicateKind, int | float]] = [
                ("numeric_min", stats.min),
                ("numeric_max", stats.max),
            ]
            for kind, value in extremes:
                known = value in at
                self.add(
                    "numeric",
                    [field.id],
                    kind,
                    "",
                    base="extreme",
                    frequency=(
                        self.counted(at[int(value)], method="dense_counts")
                        if known
                        else Frequency(accuracy="unknown")
                    ),
                    evidence="second_pass" if known else "exact",
                    ref=where,
                )
        if stats.zero > 0 and stats.zero < stats.count:
            self.add(
                "numeric",
                [field.id],
                "numeric_zero",
                "",
                base="signal",
                frequency=self.counted(stats.zero, method="numeric_stats"),
                evidence="exact",
                ref=where,
            )
        if stats.negative > 0 and stats.positive > 0:
            for sign, count in (("negative", stats.negative), ("positive", stats.positive)):
                self.add(
                    "numeric",
                    [field.id],
                    "numeric_sign",
                    sign,
                    base="signal",
                    frequency=self.counted(count, method="numeric_stats"),
                    evidence="exact",
                    ref=where,
                    params={"sign": sign},
                )
        bins = self._bins(stats.min, stats.max)
        if bins < 3:
            return
        counts = self._bin_counts(histogram, stats.min, stats.max, bins)
        for index in range(bins):
            self.add(
                "numeric",
                [field.id],
                "numeric_bin",
                str(index),
                base="bin",
                frequency=(
                    self.counted(counts[index], method="histogram")
                    if counts is not None
                    else Frequency(accuracy="unknown")
                ),
                evidence="second_pass" if counts is not None else "exact",
                ref=where,
                params={"bin": index, "of": bins},
            )

    def _bins(self, low: float, high: float) -> int:
        bins = self.settings.numeric_bins
        if isinstance(low, int) and isinstance(high, int):
            bins = min(bins, high - low + 1)
        return bins

    @staticmethod
    def _bin_counts(
        histogram: object, low: float, high: float, bins: int
    ) -> list[int] | None:
        """Rows per equal-width bin of the exact range, from a histogram of the
        second pass that places its values exactly; ``None`` otherwise."""
        if high <= low:
            return None
        if isinstance(histogram, DenseHistogram):
            counts = [0] * bins
            for item in histogram.values:
                index = bin_index(item.value, histogram.min, histogram.max, bins)
                if index is not None:
                    counts[index] += item.count
            return counts
        if (
            isinstance(histogram, BinnedHistogram)
            and histogram.strategy == "linear"
            and histogram.bounds_source == "range"
            and histogram.requested_strategy == "linear"
            and len(histogram.counts) % bins == 0
        ):
            step = len(histogram.counts) // bins
            return [sum(histogram.counts[i * step : (i + 1) * step]) for i in range(bins)]
        return None

    def dates(self, field: FieldResult) -> None:
        envelope = field.temporal
        if envelope.status != "complete" or field.values.count == 0:
            return
        stats = envelope.value
        if stats.count == 0 or stats.count / field.values.count < 0.8:
            return
        where = f"datasets/{self.dataset.id}/fields/{field.id}/temporal"
        several = len(stats.kinds) > 1
        for position, kind in enumerate(stats.kinds):
            params: dict[str, int | str] = {"kind": kind.kind}
            bounds: list[PredicateKind] = ["date_min", "date_max"]
            for predicate in bounds:
                self.add(
                    "date",
                    [field.id],
                    predicate,
                    kind.kind,
                    base="extreme",
                    frequency=Frequency(accuracy="unknown"),
                    evidence="exact",
                    ref=where,
                    params=params,
                )
            if several:
                self.add(
                    "date",
                    [field.id],
                    "date_kind",
                    kind.kind,
                    base="bin",
                    frequency=self.counted(kind.count, method="temporal_kinds"),
                    evidence="exact",
                    ref=where,
                    params=params,
                )
            if kind.years is not None and 1 < len(kind.years) <= MAX_PERIODS:
                for year_index, year in enumerate(kind.years):
                    self.add(
                        "date",
                        [field.id],
                        "date_year",
                        f"{kind.kind}:{year_index}",
                        base="bin",
                        frequency=self.counted(year.count, method="temporal_years"),
                        evidence="exact",
                        ref=f"{where}/kinds/{position}/years/{year_index}",
                        params={"kind": kind.kind, "index": year_index},
                    )

    def tail(self, field: FieldResult) -> None:
        """One target for the values of a text column that occur once: the tail of
        its frequencies, where a typo or a stray value lives. Exact when the Scan
        sampled every distinct value, a lower bound when it kept a priority sample."""
        if field.technical_type.type not in ("text", "mixed") or field.values.count == 0:
            return
        samples = field.values.samples
        singles = [
            entry for entry in samples.listed if entry.count == 1 and entry.count_accuracy == "exact"
        ]
        if not singles or len(singles) > MAX_TAIL_SHARE * field.values.count:
            return
        exhaustive = (
            samples.selection == "all"
            and samples.kept == samples.of
            and samples.long_texts is None
            and isinstance(field.values.cardinality, CardinalityComplete)
        )
        self.add(
            "quality",
            [field.id],
            "value_rare",
            "",
            base="signal",
            frequency=self.counted(
                len(singles),
                "exact" if exhaustive else "lower_bound",
                "singleton_values",
            ),
            evidence="exact" if exhaustive else "sample",
            ref=f"datasets/{self.dataset.id}/fields/{field.id}/values/samples",
            params={"max_count": 1},
        )

    def near_source(self, field: FieldResult) -> _NearSource | None:
        """The exact values of a text column: the list of the Scan when it holds every
        value, else the table of the second pass, with at most ``max_exact_values``
        values either way. ``None`` for a column whose values are not all known."""
        limit = self.settings.max_exact_values
        samples = field.values.samples
        if (
            samples.selection == "all"
            and samples.kept == samples.of
            and samples.long_texts is None
            and isinstance(field.values.cardinality, CardinalityComplete)
        ):
            listed = samples.listed
            if 0 < len(listed) <= limit and all(
                e.type == "string" and e.count_accuracy == "exact" for e in listed
            ):
                return _NearSource(
                    [(e.value, e.count) for e in listed],
                    [e.id for e in listed],
                    "scan",
                    f"datasets/{self.dataset.id}/fields/{field.id}/values/samples",
                    None,
                )
            return None
        analysis = self.analysis("exact_frequencies", field.id)
        table = analysis.result if analysis is not None else None
        if (
            analysis is None
            or not isinstance(table, FrequencyTable)
            or not 0 < len(table.values) == table.distinct <= limit
            or any(entry.type != "string" for entry in table.values)
            or len({entry.value for entry in table.values}) < len(table.values)
        ):
            return None
        return _NearSource(
            [(e.value, e.count) for e in table.values],
            list(range(len(table.values))),
            "second_pass",
            f"analyses/{analysis.id}",
            analysis.id,
        )

    def near_values(self, field: FieldResult) -> None:
        """Remember the groups of near values of a text column: frequent values that have
        rare values one edit away from them (``Longueuuil`` for ``Longueuil``). Each typo
        is a value seen once or twice, which no other target names. ``share_near`` makes
        the targets once every column is known."""
        if not (
            self.settings.near_groups_per_column
            and self.settings.near_groups
            and self.settings.near_share
        ):
            return
        if field.technical_type.type not in ("text", "mixed") or field.values.count == 0:
            return
        found = self.near_source(field)
        groups = near_groups(found.table) if found is not None else []
        if found is not None and groups:
            self.near_candidates.append((field, found, groups))

    def share_near(self) -> None:
        """One target per group, shared between the columns in turn (the heaviest group of
        each first) up to ``near_groups`` in the dataset, ``near_groups_per_column`` in a
        column and ``near_share`` of the rows asked for, so a small sample spends few rows
        on typos and a large one more, and none below ``NEAR_MIN_MANDATORY_SHARE`` of its
        mandatory targets. What the caps leave out is counted in the plan."""
        budget = self.settings.near_groups
        if self.size is not None:
            mandatory = sum(t.obligation == "mandatory" for t in self.result.targets)
            budget = min(budget, int(self.settings.near_share * self.size))
            if self.size < NEAR_MIN_MANDATORY_SHARE * mandatory:
                budget = 0
        per_column = self.settings.near_groups_per_column
        taken = [0] * len(self.near_candidates)
        given = 0
        while given < budget:
            before = given
            for k, (_, _, groups) in enumerate(self.near_candidates):
                if given < budget and taken[k] < min(len(groups), per_column):
                    taken[k] += 1
                    given += 1
            if given == before:
                break
        for (field, found, groups), count in zip(self.near_candidates, taken, strict=True):
            for index, group in enumerate(groups[:count]):
                self.add(
                    "quality",
                    [field.id],
                    "near_value",
                    str(index),
                    base="near_value",
                    frequency=self.counted(group.count, method="near_values"),
                    evidence="exact" if found.source == "scan" else "second_pass",
                    source=found.source,
                    ref=found.ref,
                    params={
                        "of": found.ids[group.frequent],
                        "entries": ",".join(str(found.ids[i]) for i in group.neighbours),
                    },
                    origin=found.origin,
                )
        self.result.capped += sum(len(groups) for _, _, groups in self.near_candidates) - given

    def characters(self, field: FieldResult) -> None:
        """One target per unexpected characteristic that only a few strings of the
        column have, with the exact count the Scan holds."""
        strings = field.strings.count - field.strings.empty
        if strings <= 0:
            return
        counts = field.string_characteristics
        for name in UNEXPECTED_CHARACTERISTICS:
            count = int(getattr(counts, name))
            if not 0 < count <= RARE_CHARACTERISTIC_SHARE * strings:
                continue
            self.add(
                "quality",
                [field.id],
                "characteristic",
                name,
                base="character",
                frequency=self.counted(count, method=name),
                evidence="exact",
                ref=f"datasets/{self.dataset.id}/fields/{field.id}/string_characteristics",
                params={"name": name},
            )

    def quality(self) -> None:
        observations = self.scan.observations
        if observations is None:
            return
        for item in observations.items:
            if item.dataset != self.dataset.id:
                continue
            self._observation(item)

    def _observation(self, item: Observation) -> None:
        if item.rule in EVALUABLE_RULES:
            feasibility: Feasibility = "ready"
            reason = None
        elif item.rule in NOT_EVALUABLE_RULES:
            feasibility = "not_evaluable"
            reason = NOT_EVALUABLE_RULES[item.rule]
        else:
            return
        field = self.fields.get(item.field) if item.field is not None else None
        if item.field is not None and (field is None or self.withheld(field)):
            return
        if item.rule == "missing_values" and item.field in self.missing_targeted:
            return
        if item.rule == "variant_groups":
            self._variant_groups(item)
            return
        exact_population = item.population in (
            "records",
            "occurrences",
            "content_strings",
            "value_slots",
        )
        share = _share(item.count, item.of) if item.of else None
        accuracy: FrequencyAccuracy
        if not exact_population or item.accuracy == "sample":
            accuracy = "indicator"
        else:
            accuracy = "exact" if item.accuracy == "exact" else "lower_bound"
        confirmed = item.status == "confirmed_issue"
        base: BaseKind = "confirmed_issue" if confirmed else "candidate_anomaly"
        if item.status == "informational":
            # A remark (cells trimmed, whitespace collapsed): it may be perfectly
            # valid, so it weighs less than an anomaly.
            base = "remark"
        if item.rule == "missing_values":
            # An empty cell is a remark, not an anomaly: a light base, which the
            # rarity of the column raises (a required identifier with a few
            # blanks weighs more than an optional column that is mostly empty).
            base = "missing"
        self.add(
            "quality",
            [] if item.field is None else [item.field],
            "observation",
            item.id,
            base=base,
            frequency=Frequency(
                accuracy=accuracy, count=item.count, share=share, method=item.rule
            ),
            evidence="exact" if item.accuracy == "exact" else "sample",
            obligation="mandatory" if confirmed and feasibility == "ready" else "optional",
            ref=f"observations/items/{item.id}",
            params={"rule": item.rule},
            origin=item.id,
            feasibility=feasibility,
            reason=reason,
        )

    def _variant_groups(self, item: Observation) -> None:
        """One target per group of variants of a value (``Montreal``, ``MONTREAL``),
        covered by a row that holds a variant other than the one the group holds
        most of: a group is a distinct phenomenon and a sample shows each one."""
        field = self.fields.get(item.field or "")
        if field is None or field.normalization.variant_groups.status != "complete":
            return
        groups = field.normalization.variant_groups.value.listed[:MAX_VARIANT_GROUPS]
        for index, group in enumerate(groups):
            if not group.variants:
                continue
            # The variants are sorted by count and the first is always listed:
            # the rest of the group is exactly its minority variants.
            minority = group.count - group.variants[0].count
            self.add(
                "quality",
                [field.id],
                "observation",
                f"{item.id}:{index}",
                # Light, like the other remarks of the normalization: a column of
                # names has dozens of groups, and at 9 each they pushed out the
                # rows of the anomalies the Scan is surer of (measured on the case).
                base="signal",
                frequency=self.counted(minority, method="variant_groups"),
                evidence="exact",
                ref=f"observations/items/{item.id}",
                params={"rule": "variant_groups", "group": index},
                origin=item.id,
            )

    def residuals(self, field: FieldResult) -> None:
        """One target per value that a detector of the second pass reads as invalid
        or not matched. The table is exact and complete, so each value is a
        defect the Scan counted and no other target names (a space inside an
        address, a currency sign in a column of numbers)."""
        analysis = self.analysis("residual_values", field.id)
        if analysis is None or not isinstance(analysis.result, ResidualResult):
            return
        for position, table in enumerate(analysis.result.tables):
            if table.source != "detector" or not table.complete or table.truncated:
                continue
            if table.occurrences > MAX_RESIDUAL_SHARE * max(1, analysis.result.values):
                continue
            for entry_index, entry in enumerate(table.listed[:MAX_RESIDUAL_VALUES]):
                if self.residual_targets >= MAX_RESIDUAL_TARGETS:
                    return
                self.residual_targets += 1
                self.add(
                    "quality",
                    [field.id],
                    "residual_value",
                    f"{position}:{entry_index}",
                    base="candidate_anomaly",
                    frequency=self.counted(entry.count, method="residual_values"),
                    evidence="second_pass",
                    source="second_pass",
                    ref=f"analyses/{analysis.id}",
                    params={"table": position, "entry": entry_index},
                    origin=analysis.id,
                )

    def date_orders(self) -> None:
        """One target per pair of date columns whose order the second pass found
        broken in some records (``broken`` is exact): a row covers it when its
        first date is after its second."""
        for analysis in self.analyses:
            result = analysis.result
            if analysis.analyzer != "date_order" or analysis.partner is None:
                continue
            if not isinstance(result, DateOrderResult) or result.broken == 0:
                continue
            fields = [analysis.field, analysis.partner]
            if any(i not in self.fields or self.withheld(self.fields[i]) for i in fields):
                continue
            self.add(
                "quality",
                fields,
                "date_order",
                analysis.id,
                base="candidate_anomaly",
                frequency=Frequency(
                    accuracy="exact",
                    count=result.broken,
                    share=_share(result.broken, result.compared),
                    method="date_order",
                ),
                evidence="second_pass",
                source="second_pass",
                ref=f"analyses/{analysis.id}",
                origin=analysis.id,
            )

    def relations(self) -> None:
        for analysis in self.analyses:
            result = analysis.result
            field_id, partner = analysis.field, analysis.partner
            if analysis.analyzer != "category_crosstab" or partner is None:
                continue
            if not isinstance(result, CrosstabResult) or field_id not in self.fields:
                continue
            for position, cell in enumerate(result.exceptions.listed):
                self.add(
                    "relations",
                    [field_id, partner],
                    "relation_exception",
                    f"{analysis.id}:{position}",
                    base="relation_exception",
                    frequency=self.counted(cell.count, method="crosstab_exceptions"),
                    evidence="second_pass",
                    source="second_pass",
                    ref=f"analyses/{analysis.id}",
                    params={"category": cell.category, "column": cell.column},
                    origin=analysis.id,
                )


def build_targets(
    scan: ScanResult,
    dataset: DatasetResult,
    deep: DeepResult | None,
    settings: SmartSettings,
    size: int | None = None,
) -> TargetSet:
    """Every target of a dataset, the families in order, before the budget of
    targets and the sort. ``deep`` is a second-pass document that is current for
    ``scan``, or ``None``. ``size`` is the number of rows asked for, which bounds the
    groups of near values."""
    builder = _Builder(scan, dataset, deep, settings, size)
    for field in dataset.fields:
        builder.low_cardinality(field)
    builder.structured_string()
    for field in dataset.fields:
        if builder.withheld(field):
            continue
        # Also for a column with a target per value counted by the second pass: those are
        # light and one for each typo, and a group says that the typos of a value matter.
        if field.id not in builder.listed_whole:
            builder.near_values(field)
        if field.id in builder.enumerated:
            continue
        builder.lengths(field)
        builder.numeric(field)
        builder.dates(field)
        builder.characters(field)
        builder.tail(field)
        builder.residuals(field)
    builder.share_near()
    builder.quality()
    builder.date_orders()
    builder.relations()
    return builder.result

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Scan engine: consumes reader items, keeps scope and diagnostics.

The engine never tests the source format; readers describe it through stream
items (design section 6).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from tabalyst.scanner.config import ScanConfig
from tabalyst.scanner.detectors.registry import DetectorSet
from tabalyst.scanner.diagnostics import DiagnosticCollector
from tabalyst.scanner.field import StringClassifier
from tabalyst.scanner.models import DatasetResult, FieldResult
from tabalyst.scanner.observations import (
    DatasetOpened,
    Notice,
    Record,
    RecordBatch,
    RecordExcluded,
    StreamItem,
)
from tabalyst.scanner.records import RecordContext
from tabalyst.scanner.structure import DatasetState
from tabalyst.scanner.values import ValueContext

# Fields named in the message of a ``measures_limited`` warning.
LISTED_LIMITED_FIELDS = 10


def has_limited_measure(field: FieldResult) -> bool:
    # Variant groups are limited only with the raw table today; listed so a
    # later limit of their own cannot be missed.
    return any(
        measure.status == "limited"
        for measure in (
            field.values.cardinality,
            field.numeric,
            field.normalization.variant_groups,
        )
    )


class ScanEngine:
    def __init__(self, config: ScanConfig, detectors: DetectorSet) -> None:
        self.config = config
        self.strings = StringClassifier(
            config.values.null_markers, config.values.null_markers_case_sensitive
        )
        self.values = ValueContext(config, detectors)
        self.records = RecordContext(config, self.strings)
        self.diagnostics = DiagnosticCollector(config.errors.max_locations)
        self.datasets: dict[str, DatasetState] = {}
        self.records_analyzed = 0
        self.exclusions: Counter[str] = Counter()

    def consume(self, items: Iterable[StreamItem]) -> None:
        datasets = self.datasets
        strings = self.strings
        for item in items:
            if type(item) is RecordBatch:
                datasets[item.dataset].add_batch(item, strings)
                self.records_analyzed += len(item.rows)
            elif type(item) is Record:
                datasets[item.dataset].add_record(item, strings)
                self.records_analyzed += 1
            elif type(item) is DatasetOpened:
                if item.dataset in datasets:
                    raise RuntimeError(f"Dataset {item.dataset!r} opened twice")
                datasets[item.dataset] = DatasetState(
                    item.dataset,
                    item.kind,
                    item.collection_path,
                    item.fields,
                    max_fields=self.config.limits.max_fields,
                    values=self.values,
                    records=self.records,
                )
                if item.container is not None:
                    holder, path = item.container
                    datasets[holder].collections[path] = item.dataset
            elif type(item) is RecordExcluded:
                self.exclusions[item.reason] += 1
                self.diagnostics.add(
                    item.code,
                    "error",
                    item.message,
                    dataset=item.dataset,
                    location=item.location.to_dict(),
                )
            elif type(item) is Notice:
                self.diagnostics.add(
                    item.code,
                    item.level,
                    item.message,
                    dataset=item.dataset,
                    location=None if item.location is None else item.location.to_dict(),
                )
            else:
                raise TypeError(f"Unknown stream item: {item!r}")

    @property
    def records_excluded(self) -> int:
        return self.exclusions.total()

    def finalize(self) -> list[DatasetResult]:
        pool = self.values.pool
        if pool is not None:
            # Workers finalize every field at once, the largest tables first
            # for balance; results are then taken in field order.
            trackers = [
                field.values
                for state in self.datasets.values()
                for field in state.fields.values()
                if field.values is not None
            ]
            trackers.sort(
                key=lambda tracker: -len(tracker.table)
                if tracker.table is not None
                else 0
            )
            for tracker in trackers:
                tracker.submit()
        results = [
            state.finalize(self.config, self.diagnostics)
            for state in self.datasets.values()
        ]
        limits = self.config.limits
        for state in self.datasets.values():
            if state.paths_limited:
                self.diagnostics.add(
                    "field_limit",
                    "warning",
                    f"More than {limits.max_fields} field paths: later paths are "
                    "not tracked and their observations are counted in "
                    "structure.untracked_observations. Raise limits.max_fields "
                    "to track them.",
                    dataset=state.id,
                    location=state.field_limit_location,
                )
            if state.depth_truncated:
                self.diagnostics.add(
                    "depth_limit",
                    "warning",
                    f"Content deeper than {limits.max_depth} levels was not "
                    "analyzed and is counted in "
                    "structure.depth_truncated_observations. Raise "
                    "limits.max_depth to analyze it.",
                    dataset=state.id,
                    location=state.depth_limit_location,
                )
        budget = self.values.budget
        if budget.released:
            self.diagnostics.add(
                "global_budget",
                "warning",
                f"More than {limits.max_tracked_values} distinct values were "
                "stored for the whole scan: the largest frequency tables were "
                "released and their table-based measures are limited with reason "
                "global_budget. Raise limits.max_tracked_values to keep them.",
                count=budget.released,
            )
        records = self.records.budget
        if records.untracked:
            self.diagnostics.add(
                "record_budget",
                "warning",
                f"More than {limits.max_tracked_records} distinct records were "
                "stored for duplicate detection: later records were compared "
                "with the stored ones only, so duplicate counts are lower "
                "bounds with reason record_budget. Raise "
                "limits.max_tracked_records to count them exactly.",
                count=records.untracked,
            )
        for result in results:
            limited = [
                field.display for field in result.fields if has_limited_measure(field)
            ]
            if limited:
                named = ", ".join(limited[:LISTED_LIMITED_FIELDS])
                if len(limited) > LISTED_LIMITED_FIELDS:
                    named += f" and {len(limited) - LISTED_LIMITED_FIELDS} more"
                self.diagnostics.add(
                    "measures_limited",
                    "warning",
                    f"Some measures of {len(limited)} field(s) are limited: "
                    f"{named}. The status of each measure gives its reason.",
                    dataset=result.id,
                    count=len(limited),
                )
        return results

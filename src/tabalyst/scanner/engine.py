"""Scan engine: consumes reader items, keeps scope and diagnostics.

The engine never tests the source format; readers describe it through stream
items (design section 6).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from tabalyst.scanner.config import ScanConfig
from tabalyst.scanner.diagnostics import DiagnosticCollector
from tabalyst.scanner.field import StringClassifier
from tabalyst.scanner.models import DatasetResult
from tabalyst.scanner.observations import (
    DatasetOpened,
    Notice,
    Record,
    RecordExcluded,
    StreamItem,
)
from tabalyst.scanner.structure import DatasetState


class ScanEngine:
    def __init__(self, config: ScanConfig) -> None:
        self.config = config
        self.strings = StringClassifier(
            config.values.null_markers, config.values.null_markers_case_sensitive
        )
        self.diagnostics = DiagnosticCollector(config.errors.max_locations)
        self.datasets: dict[str, DatasetState] = {}
        self.records_analyzed = 0
        self.exclusions: Counter[str] = Counter()

    def consume(self, items: Iterable[StreamItem]) -> None:
        datasets = self.datasets
        strings = self.strings
        for item in items:
            if type(item) is Record:
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
        results = [state.finalize(self.config) for state in self.datasets.values()]
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
        return results

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
                    item.dataset, item.kind, item.collection_path, item.fields
                )
            elif type(item) is RecordExcluded:
                self.exclusions[item.reason] += 1
                self.diagnostics.add(
                    item.code,
                    "error",
                    item.message,
                    dataset=item.dataset,
                    location=item.location.to_dict(),
                )
            else:
                raise TypeError(f"Unknown stream item: {item!r}")

    @property
    def records_excluded(self) -> int:
        return self.exclusions.total()

    def finalize(self) -> list[DatasetResult]:
        return [state.finalize(self.config) for state in self.datasets.values()]

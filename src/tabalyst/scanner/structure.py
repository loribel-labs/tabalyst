"""Per-dataset path registry, presence and structure (design sections 5 and 7).

Presence is derived from container counts: a key or column is absent only
where its parent was an object that could have contained it.
"""

from __future__ import annotations

from collections import Counter

from tabalyst.scanner.config import ScanConfig
from tabalyst.scanner.field import FieldState, StringClassifier
from tabalyst.scanner.models import (
    ArrayStats,
    Complete,
    DatasetResult,
    FieldResult,
    FieldValues,
    Limited,
    Missing,
    MissingComponents,
    Presence,
    StringCategories,
    Structure,
)
from tabalyst.scanner.observations import (
    NATIVE_TYPES,
    DatasetKind,
    DeclaredField,
    Record,
)
from tabalyst.scanner.paths import (
    ROOT,
    Column,
    FieldPath,
    Items,
    Key,
    format_relative,
    path_to_json,
)
from tabalyst.scanner.values import ValueContext, no_values


def _ordered_types(counts: dict[str, int]) -> dict[str, int]:
    return {name: counts[name] for name in NATIVE_TYPES if counts.get(name)}


class DatasetState:
    """Fields of one dataset, bounded by ``limits.max_fields``.

    Once the limit is reached, observations at new paths are counted but not
    tracked; untracked paths are not remembered, so state stays bounded.
    """

    __slots__ = (
        "collection_path",
        "collections",
        "depth_limit_location",
        "depth_truncated",
        "field_limit_location",
        "fields",
        "id",
        "kind",
        "max_fields",
        "paths_limited",
        "record_count",
        "record_types",
        "untracked_max_depth",
        "untracked_observations",
        "values",
    )

    def __init__(
        self,
        dataset_id: str,
        kind: DatasetKind,
        collection_path: FieldPath | None,
        declared: tuple[DeclaredField, ...] = (),
        *,
        max_fields: int,
        values: ValueContext,
    ) -> None:
        self.id = dataset_id
        self.kind = kind
        self.collection_path = collection_path
        self.max_fields = max_fields
        self.record_count = 0
        self.record_types: Counter[str] = Counter()
        # Fields whose arrays hold the records of another dataset.
        self.collections: dict[FieldPath, str] = {}
        self.paths_limited = False
        self.untracked_observations = 0
        self.untracked_max_depth = 0
        self.depth_truncated = 0
        self.field_limit_location: dict[str, int] | None = None
        self.depth_limit_location: dict[str, int] | None = None
        # The record root is always tracked: its containers are parent counts.
        self.values = values
        self.fields: dict[FieldPath, FieldState] = {
            ROOT: FieldState(ROOT, values.discover())
        }
        for item in declared:
            if len(self.fields) > max_fields:
                self.paths_limited = True
                break
            self.fields[item.path] = FieldState(item.path, values.discover(), item)

    def add_record(self, record: Record, strings: StringClassifier) -> None:
        self.record_count += 1
        observations = record.observations
        self.record_types[observations[0].type] += 1
        fields = self.fields
        values = self.values
        index = record.index
        for observation in observations:
            state = fields.get(observation.path)
            if state is None:
                # ``fields`` holds the record root, which the limit excludes.
                if len(fields) > self.max_fields:
                    self._untracked(observation.path, record)
                    continue
                state = fields[observation.path] = FieldState(
                    observation.path, values.discover()
                )
            state.observe(observation, index, strings, values)
        if record.depth_truncated:
            self.depth_truncated += record.depth_truncated
            if self.depth_limit_location is None:
                self.depth_limit_location = record.location.to_dict()

    def _untracked(self, path: FieldPath, record: Record) -> None:
        self.paths_limited = True
        self.untracked_observations += 1
        self.untracked_max_depth = max(self.untracked_max_depth, len(path))
        if self.field_limit_location is None:
            self.field_limit_location = record.location.to_dict()

    def finalize(self, config: ScanConfig) -> DatasetResult:
        list_root = any(name != "object" for name in self.record_types)
        listed = [state for path, state in self.fields.items() if path or list_root]
        ids: dict[FieldPath, str] = {}
        sequence = 0
        for state in listed:
            path = state.path
            if len(path) == 1 and isinstance(path[0], Column):
                ids[path] = f"column_{path[0].position}"
            else:
                sequence += 1
                ids[path] = f"f{sequence}"

        fields = [self._field(state, ids, config) for state in listed]
        tracked = len(self.fields) - 1
        max_depth_seen = max(
            (len(path) for path, state in self.fields.items() if state.occurrences),
            default=0,
        )
        return DatasetResult(
            id=self.id,
            kind=self.kind,
            collection_path=(
                None
                if self.collection_path is None
                else path_to_json(self.collection_path)
            ),
            record_count=self.record_count,
            record_types=_ordered_types(self.record_types),
            structure=Structure(
                paths=(
                    Limited(
                        reason="field_limit",
                        limit=self.max_fields,
                        # Untracked paths are not remembered: only one more
                        # distinct path than the limit is proven.
                        lower_bound=self.max_fields + 1,
                    )
                    if self.paths_limited
                    else Complete[int](value=tracked)
                ),
                untracked_observations=self.untracked_observations,
                depth_truncated_observations=self.depth_truncated,
                max_depth_seen=max(max_depth_seen, self.untracked_max_depth),
            ),
            fields=fields,
        )

    def _presence(self, state: FieldState) -> Presence:
        path = state.path
        present = state.occurrences
        if not path:
            parent_count = self.record_count
            return Presence(
                parent_type="record",
                parent_count=parent_count,
                present=present,
                absent=parent_count - present,
            )
        parent = self.fields.get(path[:-1])
        if isinstance(path[-1], Items):
            parent_count = 0 if parent is None else parent.arrays
            return Presence(
                parent_type="array",
                parent_count=parent_count,
                present=present,
                absent=None,
            )
        parent_count = 0 if parent is None else parent.count("object")
        return Presence(
            parent_type="object",
            parent_count=parent_count,
            present=present,
            absent=parent_count - present,
        )

    def _field(
        self, state: FieldState, ids: dict[FieldPath, str], config: ScanConfig
    ) -> FieldResult:
        path = state.path
        presence = self._presence(state)
        blocks = (
            no_values(self.values) if state.values is None else state.values.finalize()
        )
        components = MissingComponents(
            absent=presence.absent,
            null=state.count("null"),
            empty=state.empty,
            blank=state.blank,
            marker=state.marker,
        )
        definition = list(config.values.missing)
        missing_count = sum(getattr(components, name) or 0 for name in definition)
        if state.declared is not None:
            name, display = state.declared.name, state.declared.display
        else:
            display = format_relative(path)
            last = path[-1] if path else None
            name = last.name if isinstance(last, Key) else ("[]" if last else "$")
        return FieldResult(
            id=ids[path],
            path=path_to_json(path),
            display=display,
            name=name,
            parent=ids.get(path[:-1]) if path else None,
            collection=self.collections.get(path),
            first_record=state.first_record,
            occurrences=state.occurrences,
            presence=presence,
            native_types=_ordered_types(state.native_types),
            strings=StringCategories(
                count=state.count("string"),
                empty=state.empty,
                blank=state.blank,
                marker=state.marker,
                content=state.content,
            ),
            missing=Missing(
                count=missing_count, definition=definition, components=components
            ),
            arrays=(
                None
                if not state.arrays
                else ArrayStats(
                    count=state.arrays,
                    empty=state.arrays_empty,
                    min_length=state.array_min_length,
                    max_length=state.array_max_length,
                    total_items=state.array_items,
                )
            ),
            values=FieldValues(
                count=state.value_count,
                cardinality=blocks["cardinality"],
                frequencies=blocks["frequencies"],
                samples=blocks["samples"],
                first=blocks["first"],
                last=blocks["last"],
            ),
            string_characteristics=blocks["string_characteristics"],
            string_lengths=blocks["string_lengths"],
            numeric=blocks["numeric"],
            booleans=blocks["booleans"],
            normalization=blocks["normalization"],
        )

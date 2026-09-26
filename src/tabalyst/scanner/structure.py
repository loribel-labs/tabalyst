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


def _ordered_types(counts: dict[str, int]) -> dict[str, int]:
    return {name: counts[name] for name in NATIVE_TYPES if counts.get(name)}


class DatasetState:
    __slots__ = (
        "collection_path",
        "fields",
        "id",
        "kind",
        "record_count",
        "record_types",
    )

    def __init__(
        self,
        dataset_id: str,
        kind: DatasetKind,
        collection_path: FieldPath | None,
        declared: tuple[DeclaredField, ...] = (),
    ) -> None:
        self.id = dataset_id
        self.kind = kind
        self.collection_path = collection_path
        self.record_count = 0
        self.record_types: Counter[str] = Counter()
        # The record root is always tracked: its containers are parent counts.
        self.fields: dict[FieldPath, FieldState] = {ROOT: FieldState(ROOT)}
        for item in declared:
            self.fields[item.path] = FieldState(item.path, item)

    def add_record(self, record: Record, strings: StringClassifier) -> None:
        self.record_count += 1
        observations = record.observations
        self.record_types[observations[0].type] += 1
        fields = self.fields
        index = record.index
        for observation in observations:
            state = fields.get(observation.path)
            if state is None:
                state = fields[observation.path] = FieldState(observation.path)
            state.observe(observation, index, strings)

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
                paths=Complete[int](value=tracked),
                untracked_observations=0,
                depth_truncated_observations=0,
                max_depth_seen=max(
                    (
                        len(path)
                        for path, state in self.fields.items()
                        if state.occurrences
                    ),
                    default=0,
                ),
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
            collection=None,
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
            values=FieldValues(count=state.value_count),
        )

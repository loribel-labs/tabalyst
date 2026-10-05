# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The event pass and the selection rule of JSON Inspect (design inspect 8).

The pass reads every event of the source once and builds no record and no
statistic. It finds the candidate collections, counts their elements and
element types exactly, and observes the structure of the first records of each
candidate within bounded memory. The selection rule is a pure function of the
exact counts.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from tabalyst.inspector.json_inspect import parameters
from tabalyst.inspector.models import NATIVE_ORDER, NativeName
from tabalyst.scanner.paths import ITEMS, Key, format_absolute
from tabalyst.scanner.readers.jsonl_reader import JsonlLine

_CONTAINERS = frozenset({"start_map", "start_array"})
_ENDS = frozenset({"end_map", "end_array"})
# Native type of the event that starts a value ("integer" and "double" are
# what a parser could emit instead of "number").
_NATIVE: dict[str, NativeName] = {
    "start_map": "object",
    "start_array": "array",
    "string": "string",
    "number": "number",
    "integer": "number",
    "double": "number",
    "boolean": "boolean",
    "null": "null",
}
_END = object()

# A field path inside a record: keys, and ``None`` for an array element.
RelPath = tuple[str | None, ...]


class Candidate:
    """A collection found by the pass, with what was observed in it."""

    __slots__ = (
        "arrays",
        "complete",
        "elements",
        "fields",
        "keys",
        "max_depth",
        "nested",
        "observed",
        "types",
    )

    def __init__(self, keys: tuple[str, ...]) -> None:
        self.keys = keys
        self.elements = 0
        self.types: dict[NativeName, int] = {}
        # Records whose structure was observed, and what that showed.
        self.observed = 0
        self.fields: set[RelPath] = set()
        self.max_depth = 0
        self.nested = False
        self.arrays = False
        # False as soon as a bound cut the observation.
        self.complete = True

    @property
    def path(self) -> str:
        """Absolute path in canonical spelling: ``$.customers[]``."""
        return format_absolute(tuple(Key(name) for name in self.keys) + (ITEMS,))

    @property
    def eligible(self) -> bool:
        """At least one element, and every element is an object (8.3)."""
        return self.elements > 0 and self.types.get("object", 0) == self.elements

    @property
    def ineligible_reason(self) -> str | None:
        if self.eligible:
            return None
        return "empty" if self.elements == 0 else "non_object_elements"

    def element_types(self) -> dict[str, int]:
        return {name: self.types[name] for name in NATIVE_ORDER if name in self.types}

    def see(self, rel: RelPath, max_fields: int) -> None:
        """Record one value of an observed record, at ``rel``."""
        depth = len(rel)
        self.max_depth = max(self.max_depth, depth)
        fields = self.fields
        if rel not in fields:
            if len(fields) < max_fields:
                fields.add(rel)
            else:
                self.complete = False


@dataclass(slots=True)
class EventPass:
    root: str
    candidates: list[Candidate] = field(default_factory=list)
    # More arrays than ``MAX_CANDIDATES`` were found: the list is cut.
    truncated: bool = False


def pass_json_events(
    events: Iterable[tuple[str, object]], discovery_depth: int
) -> EventPass:
    """Walk the parser events of a JSON source (design 8.1, 8.2, 8.5).

    A candidate is the root array, or an array reachable from the root through
    object keys only, with at most ``discovery_depth`` key segments. Elements
    of a candidate are counted by native type; the structure of the first
    ``RECORDS_OBSERVED`` object elements is observed, bounded by
    ``FIELDS_OBSERVED`` paths. Anything else is skipped.
    """
    max_records = parameters.RECORDS_OBSERVED
    max_fields = parameters.FIELDS_OBSERVED
    max_candidates = parameters.MAX_CANDIDATES
    found: dict[tuple[str, ...], Candidate] = {}
    result = EventPass(root="")
    stack: list[str | None] = []  # keys of the open objects that lead to candidates
    current: Candidate | None = None  # between the elements of a candidate
    skip = 0  # depth inside a subtree that is not examined
    # Observation of one element: relative path and kind (object?) per open
    # container, and the key waiting for its value.
    observing: Candidate | None = None
    rel_stack: list[RelPath] = []
    kinds: list[bool] = []
    key: str | None = None

    for event, value in events:
        if skip:
            if event in _CONTAINERS:
                skip += 1
            elif event in _ENDS:
                skip -= 1
            continue
        if observing is not None:
            if event == "map_key":
                key = value
                continue
            if event in _ENDS:
                rel_stack.pop()
                kinds.pop()
                if not rel_stack:
                    observing.observed += 1
                    observing = None
                continue
            rel = rel_stack[-1] + ((key,) if kinds[-1] else (None,))
            # ``Candidate.see`` inlined: this is the hot loop of the pass.
            if len(rel) > observing.max_depth:  # noqa: PLR1730
                observing.max_depth = len(rel)
            fields = observing.fields
            if rel not in fields:
                if len(fields) < max_fields:
                    fields.add(rel)
                else:
                    observing.complete = False
            if event in _CONTAINERS:
                is_map = event == "start_map"
                if is_map:
                    observing.nested = True
                else:
                    observing.arrays = True
                kinds.append(is_map)
                rel_stack.append(rel)
            continue
        if current is not None:
            if event == "end_array":
                current = None
                continue
            kind = _NATIVE[event]
            current.elements += 1
            current.types[kind] = current.types.get(kind, 0) + 1
            if event == "start_map":
                if current.observed < max_records:
                    observing = current
                    rel_stack = [()]
                    kinds = [True]
                else:
                    current.complete = False
                    skip = 1
            elif event == "start_array":
                skip = 1
            continue
        # Between candidates: only objects reachable through keys are entered.
        if event == "map_key":
            key = value
            continue
        if event in _ENDS:
            stack.pop()
            continue
        if not stack:
            if event == "start_map":
                result.root = "object"
                stack.append(None)
            elif event == "start_array":
                result.root = "array"
                current = found.setdefault((), Candidate(()))
                result.candidates.append(current)
            else:
                result.root = _NATIVE[event]
            continue
        keys_deep = len(stack)  # key segments of the value that starts
        if event == "start_map":
            if keys_deep < discovery_depth:
                stack.append(key)
            else:
                skip = 1
        elif event == "start_array":
            if keys_deep <= discovery_depth:
                keys = (*stack[1:], key)
                current = found.get(keys)
                if current is None:
                    if len(found) >= max_candidates:
                        result.truncated = True
                        skip = 1
                        continue
                    current = found[keys] = Candidate(keys)
                    result.candidates.append(current)
            else:
                skip = 1
    return result


def pass_jsonl_lines(
    lines: Iterable[JsonlLine], max_locations: int
) -> tuple[Candidate, JsonlCounts]:
    """Classify the lines of a JSONL source and observe its object records.

    The source is one implicit collection (design 9.1, 9.4). A line that is not
    valid, or is longer than ``limits.max_line_bytes``, is counted and located,
    never fatal; a line with a duplicate key is an object (nothing is built
    that could be excluded).
    """
    max_records = parameters.RECORDS_OBSERVED
    max_fields = parameters.FIELDS_OBSERVED
    candidate = Candidate(())
    counts = JsonlCounts(max_locations)
    for kind, index, line, value in lines:
        counts.read += 1
        if kind == "object":
            candidate.elements += 1
            candidate.types["object"] = candidate.elements
            if candidate.observed < max_records:
                candidate.observed += 1
                _observe_object(candidate, value, max_fields)
            else:
                candidate.complete = False
        elif kind == "not_object":
            counts.not_object.add(index, line)
        else:
            counts.invalid.add(index, line)
    return candidate, counts


def _observe_object(candidate: Candidate, root: dict, max_fields: int) -> None:
    """The ``see`` calls of the JSON event pass, for an already parsed object."""
    stack: list[tuple[object, RelPath, bool]] = [(iter(root.items()), (), True)]
    while stack:
        members, path, is_object = stack[-1]
        member = next(members, _END)
        if member is _END:
            stack.pop()
            continue
        if is_object:
            name, item = member
            rel = (*path, name)
        else:
            item = member
            rel = (*path, None)
        candidate.see(rel, max_fields)
        if isinstance(item, dict):
            candidate.nested = True
            stack.append((iter(item.items()), rel, True))
        elif isinstance(item, list):
            candidate.arrays = True
            stack.append((iter(item), rel, False))


class _Located:
    """Lines of one kind: an exact count, and the first locations."""

    __slots__ = ("count", "limit", "locations")

    def __init__(self, limit: int) -> None:
        self.count = 0
        self.limit = limit
        self.locations: list[tuple[int, int]] = []

    def add(self, record: int, line: int) -> None:
        self.count += 1
        if len(self.locations) < self.limit:
            self.locations.append((record, line))


class JsonlCounts:
    """Exact counts of the lines of a JSONL source (design 4.4)."""

    __slots__ = ("blank", "invalid", "not_object", "read")

    def __init__(self, max_locations: int) -> None:
        self.read = 0
        self.blank = 0
        self.invalid = _Located(max_locations)
        self.not_object = _Located(max_locations)


# Selection -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Choice:
    """The outcome of the selection rule (design 8.4)."""

    path: str | None
    basis: str
    over: str | None = None


def select(
    root: str, candidates: list[Candidate], *, truncated: bool, jsonl: bool
) -> Choice:
    """Choose the dataset, or none, from the exact counts. Deterministic: the
    names of properties play no role, a tie never selects."""
    if jsonl:
        # The dataset is implicit; there is one candidate, ``$[]``.
        if candidates and candidates[0].eligible:
            return Choice(candidates[0].path, "jsonl_records")
        return Choice(None, "no_eligible_candidate")
    if root == "array":
        if candidates and candidates[0].eligible:
            return Choice(candidates[0].path, "root_array")
        return Choice(None, "no_eligible_candidate")
    if truncated:
        # An incomplete list can never prove that a collection stands out.
        return Choice(None, "candidates_truncated")
    eligible = sorted(
        (item for item in candidates if item.eligible),
        key=lambda item: item.elements,
        reverse=True,
    )
    if not eligible:
        return Choice(None, "no_eligible_candidate")
    if len(eligible) == 1:
        return Choice(eligible[0].path, "only_eligible_candidate")
    first, second = eligible[0], eligible[1]
    if first.elements >= parameters.DOMINANCE_RATIO * second.elements:
        return Choice(first.path, "dominant_candidate", over=second.path)
    return Choice(None, "ambiguous")

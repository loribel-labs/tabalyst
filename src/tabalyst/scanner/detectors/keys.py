# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Declared keys of the detectors (Patterns algorithm, section 4; design 18.12).

The keys an ``email``, ``phone`` or ``postal_code`` detector declares are counted
exactly by its accumulator and selected here by floors, never by a test against
chance: the detector established their meaning.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from tabalyst.scanner.exposure import ExposureGate

# Floors of the selection (DEC-028), as a share written ``count * DIVISOR >= total``
# so that a tie never depends on a float.
FIRST_LEVEL_DIVISOR = 200  # 0.5 % of the field
CHILD_DIVISOR = 50  # 2 % of the parent
MIN_OCCURRENCES = 5  # also the privacy floor of a rare key
COVERAGE_PERCENT = 95
FIRST_LEVEL_BUDGET = 32
CHILD_BUDGET = 16


class KeyNode:
    """A key with its exact occurrences and the keys below it."""

    __slots__ = ("children", "count")

    def __init__(self, count: int = 0) -> None:
        self.count = count
        self.children: dict[str, KeyNode] = {}


def add_path(roots: dict[str, KeyNode], path: Sequence[str], count: int) -> None:
    """Add ``count`` occurrences to every key along ``path`` (one key by level)."""
    level = roots
    for key in path:
        node = level.get(key)
        if node is None:
            node = level[key] = KeyNode()
        node.count += count
        level = node.children


def from_pairs(pairs: Mapping[str, Mapping[str, int]]) -> dict[str, KeyNode]:
    """Two levels of keys from ``{first: {second: occurrences}}``."""
    roots: dict[str, KeyNode] = {}
    for first, seconds in pairs.items():
        node = roots[first] = KeyNode(sum(seconds.values()))
        node.children = {second: KeyNode(count) for second, count in seconds.items()}
    return roots


def _entries(
    nodes: Mapping[str, KeyNode], total: int, divisor: int, budget: int
) -> tuple[list[dict[str, object]], int]:
    """The entries kept at one level and the number of the keys left out.

    Sorted by decreasing count then text; a key is kept while its share of
    ``total`` reaches the floor, it has ``MIN_OCCURRENCES``, its rank is within
    ``budget`` and the cumulated coverage before it is under ``COVERAGE_PERCENT``.
    The occurrences left out are ``total`` minus the ones kept: when the names
    tracked were limited, the nodes seen may miss some.
    """
    ordered = sorted(nodes.items(), key=lambda item: (-item[1].count, item[0]))
    entries: list[dict[str, object]] = []
    covered = 0
    for key, node in ordered:
        if (
            covered * 100 >= total * COVERAGE_PERCENT
            or node.count * divisor < total
            or node.count < MIN_OCCURRENCES
            or len(entries) >= budget
        ):
            break
        entry: dict[str, object] = {"key": key, "occurrences": node.count}
        if node.children:
            below, others = _others(node)
            if below:
                entry["keys"] = below
            if others is not None:
                entry["others"] = others
        entries.append(entry)
        covered += node.count
    return entries, len(ordered) - len(entries)


def _others(node: KeyNode) -> tuple[list[dict[str, object]], dict[str, int] | None]:
    below, left_out = _entries(node.children, node.count, CHILD_DIVISOR, CHILD_BUDGET)
    occurrences = node.count - sum(child["occurrences"] for child in below)  # type: ignore[misc]
    return below, ({"keys": left_out, "occurrences": occurrences} if occurrences else None)


def keys_block(
    roots: Mapping[str, KeyNode],
    levels: Sequence[str],
    gate: ExposureGate,
    *,
    limit: int | None = None,
    incomplete_children: bool = False,
) -> dict[str, object]:
    """The ``keys`` block of a detector's ``details``.

    ``status`` is ``not_applicable`` when the detector matched no value, ``disabled`` when the gate does not expose the keys of a masked or
    hidden field, ``limited`` when ``limit`` stopped the first level (no keys) or
    ``incomplete_children`` says the levels below saw only the names tracked, else
    ``complete``. Counts are occurrences, exact in both execution modes.
    """
    if not gate.exposes_keys:
        return {"status": "disabled", "reason": "exposure"}
    if limit is not None:
        return {"status": "limited", "reason": "max_tracked", "limit": limit}
    if not roots:
        return {"status": "not_applicable", "reason": "no_values"}
    total = sum(node.count for node in roots.values())
    entries, other_keys = _entries(roots, total, FIRST_LEVEL_DIVISOR, FIRST_LEVEL_BUDGET)
    other_occurrences = total - sum(entry["occurrences"] for entry in entries)  # type: ignore[misc]
    block: dict[str, object] = {
        "status": "limited" if incomplete_children else "complete",
        "levels": list(levels),
        "keys": entries,
        "others": {"keys": other_keys, "occurrences": other_occurrences},
    }
    if incomplete_children:
        block["reason"] = "max_tracked"
    return block

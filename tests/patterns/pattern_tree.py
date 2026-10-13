# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The shape of a discovery result as the reference tests read it, and the
comparison of an expected tree with an observed one.

A node is known by the set of values it holds, not by its name: the notation
(OPEN-003) and the JSON (OPEN-002) are still open, so an expectation says which
values a node or a table cell must gather, and its label only helps the reader.
Labels follow ``kind:token:text``: ``shape:2,4`` (lengths of the variable
tokens), ``composition:DDDDU`` (classes of a merged block), ``head:1:AK`` and
``tail:5:00`` (content of the 1-based token of the family's structure).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

from tabalyst.scanner.patterninfer import tokenize

# Default depth below the family (DEC-025).
MAX_DEPTH = 3


def structure(value: str) -> str:
    """The structure key of a value under the current tokenization (E1), as
    ``patterninfer._key_text`` spells it: ``AK-1234`` gives ``UP-D``."""
    return "".join(
        code if literal is None else code + literal
        for code, literal, _, _ in tokenize(value)
    )


def token(value: str, index: int) -> str:
    """The text of token ``index`` (1-based) of ``value``."""
    return tokenize(value)[index - 1][3]


def shape(value: str) -> tuple[int, ...]:
    """The lengths of the class tokens of ``value`` (the shape facet)."""
    return tuple(count for code, _, count, _ in tokenize(value) if code != "P")


# Expectations ---------------------------------------------------------------------


@dataclass(frozen=True)
class Node:
    """An expected node: the values ``key`` accepts among its parent's, with the
    exact counts they must give, and its expected children."""

    label: str
    key: Callable[[str], bool]
    distinct: int
    occurrences: int
    children: tuple[Node, ...] = ()


@dataclass(frozen=True)
class Table:
    """An expected facet table of a family: its members split by ``key``, with the
    distinct values of each cell. ``required`` names the cells that must appear
    as cells (the others may fall in the rest of the table)."""

    label: str
    key: Callable[[str], str]
    cells: Mapping[str, int]
    required: frozenset[str] | None = None

    def required_cells(self) -> frozenset[str]:
        return frozenset(self.cells) if self.required is None else self.required


@dataclass(frozen=True)
class Rule:
    """A family of nodes described by a rule: any node whose values are exactly
    the values of its parent that share one result of ``key``."""

    label: str
    key: Callable[[str], str]


@dataclass(frozen=True)
class Family:
    """An expected family: the structures it gathers (E2), its counts, the
    constants folded into its rendering, its nodes and tables.

    ``optional`` nodes may be published or not, until a calibration decides. ``exhaustive`` forbids any
    published node that is neither expected, optional nor allowed by ``allowed``;
    ``forbidden`` lists rules no node may follow.
    """

    label: str
    structures: frozenset[str]
    distinct: int
    occurrences: int
    constants: tuple[str, ...] = ()
    nodes: tuple[Node, ...] = ()
    optional: tuple[Node, ...] = ()
    tables: tuple[Table, ...] = ()
    allowed: tuple[Rule, ...] = ()
    forbidden: tuple[Rule, ...] = ()
    exhaustive: bool = True


@dataclass(frozen=True)
class Expected:
    """What the discovery must find in one field of the corpus.

    ``conclusive`` is false for the toys of the conversation: too few values to
    conclude (algorithm, section 9.1), only the families are checked.
    """

    field: str
    families: tuple[Family, ...]
    other_distinct: int = 0
    conclusive: bool = True
    note: str = ""


# Observations ---------------------------------------------------------------------


@dataclass(frozen=True)
class SeenNode:
    """A published node of an observed result, with the values it holds."""

    label: str
    members: frozenset[str]
    children: tuple[SeenNode, ...] = ()


@dataclass(frozen=True)
class SeenTable:
    """A published facet table: the values of each listed cell; the rest of the
    family is the rest of the table."""

    label: str
    cells: tuple[frozenset[str], ...]


@dataclass(frozen=True)
class SeenFamily:
    label: str
    members: frozenset[str]
    nodes: tuple[SeenNode, ...] = ()
    tables: tuple[SeenTable, ...] = ()


@dataclass(frozen=True)
class SeenField:
    """An observed discovery result, reduced to sets of values."""

    families: tuple[SeenFamily, ...]
    other: frozenset[str] = frozenset()
    limits: tuple[str, ...] = ()


# Comparison -----------------------------------------------------------------------


@dataclass
class _Context:
    values: Mapping[str, int]
    problems: list[str] = field(default_factory=list)


def compare(expected: Expected, seen: SeenField, pairs: Iterable[tuple[str, int]]) -> list[str]:
    """The differences between an expected and an observed result, empty when
    they agree. ``pairs`` are the values the discovery read."""
    context = _Context(dict(pairs))
    _check_invariants(seen, context)
    families = {family.members: family for family in seen.families}
    claimed: set[frozenset[str]] = set()
    for family in expected.families:
        members = frozenset(
            value for value in context.values if structure(value) in family.structures
        )
        _check_counts(family.label, members, family.distinct, family.occurrences, context)
        observed = families.get(members)
        if observed is None:
            context.problems.append(f"family {family.label}: not found")
            continue
        claimed.add(members)
        if expected.conclusive:
            _check_family(family, observed, context)
    for members, observed in families.items():
        if members not in claimed:
            context.problems.append(f"unexpected family {observed.label}")
    other = frozenset(context.values).difference(*families)
    if expected.conclusive and len(other) != expected.other_distinct:
        context.problems.append(
            f"other structures: {len(other)} values, expected {expected.other_distinct}"
        )
    return context.problems


def _check_counts(
    label: str, members: frozenset[str], distinct: int, occurrences: int, context: _Context
) -> None:
    """The expectation itself must agree with the values (a guard against a
    stale expectation, not a check of the discovery)."""
    found = (len(members), sum(context.values[value] for value in members))
    if found != (distinct, occurrences):
        context.problems.append(
            f"expectation {label}: the values give {found}, "
            f"expected {(distinct, occurrences)}"
        )


def _check_family(family: Family, observed: SeenFamily, context: _Context) -> None:
    matched: set[int] = set()
    _match_nodes(
        family.label, family.nodes, observed.members, observed.nodes, matched, context
    )
    _match_nodes(
        family.label,
        family.optional,
        observed.members,
        observed.nodes,
        matched,
        _Context(context.values),
    )
    for node in _walk(observed.nodes):
        if id(node) in matched:
            continue
        parent = _parent_members(observed, node)
        if any(_follows(rule, node, parent) for rule in family.forbidden):
            context.problems.append(f"family {family.label}: forbidden node {node.label}")
        elif family.exhaustive and not any(
            _follows(rule, node, parent) for rule in family.allowed
        ):
            context.problems.append(f"family {family.label}: unexpected node {node.label}")
    for table in family.tables:
        _check_table(family, table, observed, context)


def _match_nodes(
    where: str,
    expected: tuple[Node, ...],
    parent: frozenset[str],
    observed: tuple[SeenNode, ...],
    matched: set[int],
    context: _Context,
) -> None:
    by_members = {node.members: node for node in observed}
    for node in expected:
        members = frozenset(value for value in parent if node.key(value))
        _check_counts(f"{where} > {node.label}", members, node.distinct, node.occurrences, context)
        found = by_members.get(members)
        if found is None:
            context.problems.append(f"{where}: node {node.label} not found")
            continue
        matched.add(id(found))
        _match_nodes(
            f"{where} > {node.label}", node.children, members, found.children, matched, context
        )


def _check_table(
    family: Family, table: Table, observed: SeenFamily, context: _Context
) -> None:
    groups: dict[str, set[str]] = {}
    for value in observed.members:
        groups.setdefault(table.key(value), set()).add(value)
    sizes = {cell: len(values) for cell, values in groups.items()}
    if sizes != dict(table.cells):
        context.problems.append(
            f"expectation {family.label} table {table.label}: the values give {sizes}"
        )
    wanted = {frozenset(groups.get(cell, ())) for cell in table.required_cells()}
    for seen in observed.tables:
        if wanted <= set(seen.cells):
            return
    context.problems.append(f"family {family.label}: table {table.label} not found")


def _follows(rule: Rule, node: SeenNode, parent: frozenset[str]) -> bool:
    keys = {rule.key(value) for value in node.members}
    if len(keys) != 1:
        return False
    key = keys.pop()
    return node.members == frozenset(value for value in parent if rule.key(value) == key)


def _walk(nodes: Iterable[SeenNode]) -> Iterable[SeenNode]:
    for node in nodes:
        yield node
        yield from _walk(node.children)


def _parent_members(family: SeenFamily, target: SeenNode) -> frozenset[str]:
    def search(nodes: tuple[SeenNode, ...], parent: frozenset[str]) -> frozenset[str] | None:
        for node in nodes:
            if node is target:
                return parent
            found = search(node.children, node.members)
            if found is not None:
                return found
        return None

    return search(family.nodes, family.members) or family.members


def _check_invariants(seen: SeenField, context: _Context) -> None:
    """What every result must respect (FR-012, DEC-024 to DEC-026): families are
    disjoint, a node holds a strict part of its parent, siblings are disjoint,
    the depth stays within the default."""
    families = [family.members for family in seen.families] + [seen.other]
    if sum(len(members) for members in families) != len(frozenset().union(*families)):
        context.problems.append("families overlap")
    for family in seen.families:
        _check_children(family.label, family.members, family.nodes, 1, context)


def _check_children(
    where: str,
    parent: frozenset[str],
    children: tuple[SeenNode, ...],
    depth: int,
    context: _Context,
) -> None:
    seen: set[str] = set()
    for child in children:
        if depth > MAX_DEPTH:
            context.problems.append(f"{where} > {child.label}: deeper than {MAX_DEPTH}")
        if not child.members < parent:
            context.problems.append(
                f"{where} > {child.label}: not a strict part of its parent"
            )
        if seen & child.members:
            context.problems.append(f"{where} > {child.label}: overlaps a sibling")
        seen |= child.members
        _check_children(f"{where} > {child.label}", child.members, child.children, depth + 1, context)


# Declared keys (algorithm, section 4) ------------------------------------------------


@dataclass(frozen=True)
class Key:
    """A kept key of the declared mode with its exact occurrences, its children
    and the rest of its children as (keys, occurrences)."""

    key: str
    occurrences: int
    children: tuple[Key, ...] = ()
    other: tuple[int, int] = (0, 0)


@dataclass(frozen=True)
class Declared:
    """The keys a detector declares for a field: the first level, the rest of it
    as (keys, occurrences), and whether the field is masked."""

    field: str
    detector: str
    keys: tuple[Key, ...]
    other: tuple[int, int]
    masked: bool


def tree_to_lines(seen: SeenField, values: Mapping[str, int]) -> list[str]:
    """A readable listing of an observed tree, for failure messages."""
    lines = []

    def emit(nodes: Iterable[SeenNode], indent: int) -> None:
        for node in nodes:
            occurrences = sum(values.get(value, 0) for value in node.members)
            lines.append(f"{'  ' * indent}{node.label} d={len(node.members)} o={occurrences}")
            emit(node.children, indent + 1)

    for family in seen.families:
        lines.append(f"{family.label} d={len(family.members)}")
        emit(family.nodes, 1)
    return lines


def ideal(expected: Expected, pairs: Iterable[tuple[str, int]]) -> SeenField:
    """The observed result a perfect discovery would give: the expected tree
    itself, built from the values. It checks the comparison and the counts of
    the expectations while the engine does not exist."""
    values = [value for value, _ in pairs]

    def build(nodes: tuple[Node, ...], parent: frozenset[str]) -> tuple[SeenNode, ...]:
        built = []
        for node in nodes:
            members = frozenset(value for value in parent if node.key(value))
            built.append(SeenNode(node.label, members, build(node.children, members)))
        return tuple(built)

    families = []
    for family in expected.families:
        members = frozenset(v for v in values if structure(v) in family.structures)
        tables = tuple(
            SeenTable(
                table.label,
                tuple(
                    frozenset(v for v in members if table.key(v) == cell)
                    for cell in sorted(table.required_cells())
                ),
            )
            for table in family.tables
        )
        families.append(
            SeenFamily(family.label, members, build(family.nodes, members), tables)
        )
    covered = frozenset().union(*(family.members for family in families))
    return SeenField(tuple(families), frozenset(values) - covered)

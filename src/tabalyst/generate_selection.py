# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Select catalog values with independent random streams and finite constraints."""

from __future__ import annotations

import hashlib
import math
import random
from decimal import Decimal
from fractions import Fraction
from typing import TYPE_CHECKING, Literal, NotRequired, TypedDict, cast

from tabalyst.errors import ConfigurationError
from tabalyst.generate_package import Cell, _fail

if TYPE_CHECKING:
    from tabalyst.generate_package import DatasetPackage

MAX_SEARCH_NODES = 100_000
CONSTRAINT_COLUMNS = frozenset({
    "scope_id", "condition_field", "condition_id", "target_field", "target_id", "action",
})


class RelationRef(TypedDict):
    """Reference one relation table and its prior selection context."""

    source: str
    candidate_column: str
    where: dict[str, str]


class SelectionStep(TypedDict):
    """Represent a loader-validated select or derive step."""

    id: str
    kind: Literal["select", "derive"]
    output: str
    source: NotRequired[str]
    candidate_column: NotRequired[str]
    where: NotRequired[dict[str, str]]
    filters: NotRequired[list[RelationRef]]
    influences: NotRequired[list[RelationRef]]
    weight_column: NotRequired[str]
    from_table: NotRequired[str]
    selected: NotRequired[str]
    column: NotRequired[str]


def _dataset(package: DatasetPackage, dataset_id: str) -> list[SelectionStep]:
    datasets = cast(list[dict[str, object]], package.manifest["datasets"])
    for raw in datasets:
        if raw["id"] == dataset_id and raw["mode"] == "generated" and raw["row_source"] == "catalog_steps":
            return cast(list[SelectionStep], raw["steps"])
    raise ConfigurationError(f"PACKAGE_STEP_REFERENCE: unknown catalog dataset {dataset_id!r}")


def _parts_hash(parts: tuple[str, ...]) -> int:
    digest = hashlib.sha256()
    for part in parts:
        encoded = part.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return int.from_bytes(digest.digest(), "big")


def _stream(seed: int, dataset_id: str, row_index: int, decision_id: str,
            context: tuple[str, ...]) -> random.Random:
    return random.Random(_parts_hash((str(seed), dataset_id, str(row_index), decision_id, *context)))


def _references(raw: object, package: DatasetPackage, prior: set[str],
                step_id: str, *, influence: bool) -> None:
    path = package.root / "dataset.yaml"
    if not isinstance(raw, list):
        _fail("PACKAGE_STEP_REFERENCE", path, f"{step_id}: expected a list")
    for entry in raw:
        if not isinstance(entry, dict) or set(entry) != {"source", "candidate_column", "where"}:
            _fail("PACKAGE_STEP_REFERENCE", path, f"{step_id}: invalid relation entry")
        relation = cast(RelationRef, entry)
        source = relation["source"]
        if not isinstance(source, str) or source not in package.tables:
            _fail("PACKAGE_STEP_REFERENCE", path, f"{step_id}: unknown relation table")
        table = package.tables[source]
        if table.role not in ({"weighted_relation"} if influence else {"relation", "weighted_relation"}):
            _fail("PACKAGE_STEP_REFERENCE", path, f"{step_id}: invalid relation role")
        names = {column.name for column in table.columns}
        if not isinstance(relation["candidate_column"], str) or relation["candidate_column"] not in names:
            _fail("PACKAGE_STEP_REFERENCE", path, f"{step_id}: unknown relation candidate column")
        where = relation["where"]
        if not isinstance(where, dict) or not where or any(
            not isinstance(column, str) or column not in names
            or not isinstance(field, str) or field not in prior
            for column, field in where.items()
        ):
            _fail("PACKAGE_STEP_REFERENCE", path, f"{step_id}: relation needs prior fields")
        if influence and "weight" not in names:
            _fail("PACKAGE_STEP_REFERENCE", path, f"{step_id}: influence needs weight")
        if influence:
            seen: set[tuple[Cell, ...]] = set()
            for row, line in zip(table.rows, table.row_lines, strict=True):
                key = tuple(row[column] for column in where) + (row[relation["candidate_column"]],)
                if key in seen:
                    _fail("PACKAGE_STEP_DUPLICATE", table.file,
                          f"{step_id}: duplicate influence candidate", line, relation["candidate_column"])
                seen.add(key)


def _canonical_fields(steps: list[SelectionStep]) -> tuple[dict[str, str], dict[str, str]]:
    aliases: dict[str, str] = {}
    sources: dict[str, str] = {}
    for step in steps:
        output = step["output"]
        if step["kind"] == "select":
            aliases[output] = output
            sources[output] = step["source"]
        else:
            aliases[output] = aliases[step["selected"]]
    return aliases, sources


def _constraints(package: DatasetPackage, steps: list[SelectionStep],
                 profile: str | None) -> tuple[tuple[str, Cell, str, Cell], ...]:
    aliases, sources = _canonical_fields(steps)
    profiles = cast(dict[str, object], package.manifest.get("generation_profiles", {}))
    if profile is not None and profile not in profiles:
        _fail("PACKAGE_CONSTRAINT", package.root / "dataset.yaml", f"unknown generation profile {profile!r}")
    result: set[tuple[str, Cell, str, Cell]] = set()
    for table in package.tables.values():
        if table.role != "constraint":
            continue
        names = {column.name for column in table.columns}
        if names != CONSTRAINT_COLUMNS:
            _fail("PACKAGE_CONSTRAINT", table.schema, "constraint columns must be scope_id, condition_field, condition_id, target_field, target_id, action")
        for row, line in zip(table.rows, table.row_lines, strict=True):
            scope = cast(str, row["scope_id"])
            condition = cast(str, row["condition_field"])
            target = cast(str, row["target_field"])
            if scope != "global" and scope not in profiles:
                _fail("PACKAGE_CONSTRAINT", table.file, f"unknown scope {scope!r}", line, "scope_id")
            if row["action"] != "exclude":
                _fail("PACKAGE_CONSTRAINT", table.file, "only exclude is supported", line, "action")
            for field, key in ((condition, "condition_id"), (target, "target_id")):
                if field not in aliases:
                    _fail("PACKAGE_CONSTRAINT", table.file, f"unknown selection field {field!r}", line, key)
                canonical = aliases[field]
                source = package.tables[sources[canonical]]
                step = next(item for item in steps if item["output"] == canonical)
                candidate_column = step["candidate_column"]
                # A global exclusion may reserve a valid component for later generations.
                reference = next((column.references for column in source.columns
                                  if column.name == candidate_column), None)
                if reference is None:
                    allowed = {entry[candidate_column] for entry in source.rows}
                else:
                    reference_table, reference_column = reference.split(".")
                    allowed = {entry[reference_column]
                               for entry in package.tables[reference_table].rows}
                if row[key] not in allowed:
                    _fail("PACKAGE_CONSTRAINT", table.file, f"unknown {field} ID {row[key]!r}", line, key)
            if scope in {"global", profile}:
                result.add((aliases[condition], row["condition_id"], aliases[target], row["target_id"]))
    return tuple(sorted(result))


def validate_selection_package(package: DatasetPackage) -> None:
    """Check selection relations, influences, and exclusion references at load time."""
    datasets = cast(list[dict[str, object]], package.manifest["datasets"])
    for raw in datasets:
        if raw["mode"] != "generated" or raw["row_source"] != "catalog_steps":
            continue
        steps = cast(list[SelectionStep], raw["steps"])
        prior: set[str] = set()
        for step in steps:
            if step["kind"] == "select":
                for name, influence in (("filters", False), ("influences", True)):
                    if name in step:
                        _references(step[name], package, prior, step["id"], influence=influence)
            prior.add(step["output"])
        _constraints(package, steps, None)


def _candidates(package: DatasetPackage, step: SelectionStep, values: dict[str, Cell]
                ) -> list[tuple[Cell, Fraction]]:
    source = package.tables[step["source"]]
    where = step.get("where", {})
    if where:
        key, field = next(iter(where.items()))
        indexed = package.relation_index.get(source.id, {}).get(key)
        rows = indexed.get(values[field], ()) if indexed is not None else source.rows
    else:
        rows = source.rows
    result: list[tuple[Cell, Fraction]] = []
    for row in rows:
        if any(row[column] != values[field] for column, field in where.items()):
            continue
        candidate = row[step["candidate_column"]]
        if any(not any(
            entry[relation["candidate_column"]] == candidate
            for entry in _related_rows(package, relation, values)
        ) for relation in step.get("filters", [])):
            continue
        base = row[step["weight_column"]] if "weight_column" in step else 1
        weight = Fraction(cast(int | Decimal, base))
        for relation in step.get("influences", []):
            factors = [entry["weight"] for entry in _related_rows(package, relation, values)
                       if entry[relation["candidate_column"]] == candidate]
            if len(factors) > 1:
                raise ConfigurationError(f"PACKAGE_STEP_DUPLICATE: multiple influences for {candidate!r}")
            if factors:
                weight *= Fraction(cast(int | Decimal, factors[0]))
        result.append((candidate, weight))
    return sorted(result, key=lambda item: item[0])


def _related_rows(package: DatasetPackage, relation: RelationRef, values: dict[str, Cell]
                  ) -> tuple[dict[str, Cell], ...]:
    table = package.tables[relation["source"]]
    where = relation["where"]
    key, field = next(iter(where.items()))
    indexed = package.relation_index.get(table.id, {}).get(key)
    rows = indexed.get(values[field], ()) if indexed is not None else table.rows
    return tuple(row for row in rows if all(row[column] == values[name] for column, name in where.items()))


def _conflicts(values: dict[str, Cell], constraints: tuple[tuple[str, Cell, str, Cell], ...]) -> bool:
    return any(condition in values and target in values
               and values[condition] == condition_id and values[target] == target_id
               for condition, condition_id, target, target_id in constraints)


def _choose(candidates: list[tuple[Cell, Fraction]], rng: random.Random) -> Cell:
    denominator = 1
    for _, weight in candidates:
        denominator = math.lcm(denominator, weight.denominator)
    counts = [int(weight * denominator) for _, weight in candidates]
    common = math.gcd(*counts)
    counts = [count // common for count in counts]
    roll = rng.randrange(sum(counts))
    for (candidate, _), count in zip(candidates, counts, strict=True):
        if roll < count:
            return candidate
        roll -= count
    raise AssertionError("positive candidate weights must cover the draw")


def select_catalog_row(package: DatasetPackage, dataset_id: str, seed: int,
                       row_index: int, generation_profile: str | None = None) -> dict[str, Cell]:
    """Choose one feasible internal row without changing global random state.

    Raises ConfigurationError when no completion exists or search exceeds its fixed bound.
    """
    if type(seed) is not int or type(row_index) is not int or row_index < 0:
        raise ValueError("seed must be an integer and row_index must be nonnegative")
    steps = _dataset(package, dataset_id)
    constraints = _constraints(package, steps, generation_profile)
    visited = 0
    deepest_dead_end: dict[str, Cell] = {}
    dead_end_position = 0

    def feasible(position: int, values: dict[str, Cell]) -> bool:
        nonlocal visited, deepest_dead_end, dead_end_position
        visited += 1
        if visited > MAX_SEARCH_NODES:
            raise ConfigurationError(f"GENERATION_SEARCH_LIMIT: dataset={dataset_id} row={row_index}")
        if position == len(steps):
            return True
        step = steps[position]
        output = step["output"]
        if step["kind"] == "derive":
            value = _derive(package, step, values)
            return feasible(position + 1, {**values, output: value})
        for candidate, _ in _candidates(package, step, values):
            next_values = {**values, output: candidate}
            if not _conflicts(next_values, constraints) and feasible(position + 1, next_values):
                return True
        if position > dead_end_position:
            deepest_dead_end = values.copy()
            dead_end_position = position
        return False

    values: dict[str, Cell] = {}
    for position, step in enumerate(steps):
        output = step["output"]
        if step["kind"] == "derive":
            values[output] = _derive(package, step, values)
            continue
        candidates = []
        for candidate, weight in _candidates(package, step, values):
            next_values = {**values, output: candidate}
            if not _conflicts(next_values, constraints) and feasible(position + 1, next_values):
                candidates.append((candidate, weight))
        if not candidates:
            context_values = deepest_dead_end if len(deepest_dead_end) > len(values) else values
            generation = context_values.get("generation_id", "unknown")
            detail = ",".join(f"{key}={value}" for key, value in sorted(context_values.items()))
            blocked_step = steps[dead_end_position] if dead_end_position > position else step
            raise ConfigurationError(
                f"GENERATION_IMPOSSIBLE_CONFIGURATION: dataset={dataset_id} "
                f"generation={generation} step={blocked_step['id']} "
                f"field={blocked_step['output']} choices={detail}"
            )
        context_fields = set(step.get("where", {}).values())
        for relation in (*step.get("filters", []), *step.get("influences", [])):
            context_fields.update(relation["where"].values())
        for condition, _, target, _ in constraints:
            if condition == output and target in values:
                context_fields.add(target)
            if target == output and condition in values:
                context_fields.add(condition)
        context = tuple(f"{field}={values[field]}" for field in sorted(context_fields))
        values[output] = _choose(candidates, _stream(seed, dataset_id, row_index, step["id"], context))
    return values


def _derive(package: DatasetPackage, step: SelectionStep, values: dict[str, Cell]) -> Cell:
    table = package.tables[step["from_table"]]
    matches = [row for row in table.rows if row.get("id") == values[step["selected"]]]
    if len(matches) != 1:
        raise ConfigurationError(f"PACKAGE_STEP_REFERENCE: cannot derive {step['output']!r}")
    return matches[0][step["column"]]

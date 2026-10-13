# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Where the reference and contract tests meet the engine: the one place to bind
as the lots of the Patterns plan deliver (P2 eligibility, P3 and P4 discovery, P5
declared keys, P6 validation, P7 consumers).

The first functions turn a field of the corpus into the forms of ``pattern_tree``;
the contract functions at the end return the documents the Scan and the second pass
write.
Until it is bound it raises ``NotImplementedError``; the tests that call it are
skipped by the gate of ``conftest.py`` meanwhile.
"""

from __future__ import annotations

import csv
import tempfile
from collections.abc import Mapping, Sequence
from contextlib import nullcontext
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Literal
from unittest.mock import patch

from pattern_corpus import Field, Variants
from pattern_tree import (
    Declared,
    Key,
    SeenFamily,
    SeenField,
    SeenNode,
    SeenTable,
    lengths,
    structure,
    token,
)

from tabalyst.config import DeepSettings
from tabalyst.projects.location import StorageLocation
from tabalyst.scanner import ScanConfig, patterninfer, scan
from tabalyst.scanner import api as scan_api
from tabalyst.scanner.config import DetectorSettings
from tabalyst.scanner.models import (
    FieldPatterns,
    FieldPatternsComplete,
    PatternFamily,
    PatternNode,
    PatternTable,
    ScanResult,
)
from tabalyst.scanner.patterninfer import compile_signature, infer_patterns, matches
from tabalyst.scanner.planner import plan_analyses
from tabalyst.scanner.planner.analyzers.patterns import PatternValidation
from tabalyst.scanner.planner.registry import AnalyzerRegistry
from tabalyst.scanner.secondpass import run_second_pass
from tabalyst.scanner.secondpass.models import (
    PatternCounts,
    PatternNodeCount,
    PatternTableCount,
)
from tabalyst.scanner.secondpass.patterns import PatternAccumulator, derive_from_samples
from tabalyst.scanner.validation import check_scan
from tabalyst.shared_scan_service import current_scan

# The outcomes of a value at validation (REC-006); ``invalid`` is reserved and
# never given by the inference. A set of lengths never seen in a known structure
# is a ``new_variant`` (DEC-034).
Outcome = Literal["known", "new_variant", "unknown_structure", "atypical", "invalid"]


@dataclass(frozen=True)
class Validation:
    """The outcome of each value of a file validated against a discovery."""

    outcomes: Mapping[str, Outcome]


def discover(
    field: Field, settings: Mapping[str, int] | None = None, workers: int = 1
) -> SeenField | None:
    """The tree the discovery publishes for ``field``, reduced to sets of values;
    ``None`` when the generic discovery does not apply (a masked field, FR-022).

    ``settings`` overrides ``scan.pattern_inference`` (``max_values``,
    ``max_families``, ``max_patterns_per_family``, ``max_patterns``,
    ``max_depth``); ``workers`` is the number of first-pass workers.

    A scan of the field's pairs is run and each family, pattern and node is
    mapped to the values its signature accepts, so that the matcher checks the
    signatures the discovery writes (lots P3 and P4).
    """
    entry = _scanned_entry(field, _frozen(settings), workers)
    if not isinstance(entry, FieldPatternsComplete):
        return None
    return _seen(entry, field)


def _frozen(settings: Mapping[str, int] | None) -> tuple[tuple[str, int], ...]:
    return tuple(sorted((settings or {}).items()))


def _accepted(signature, values: Sequence[str]) -> frozenset[str]:
    matcher = compile_signature(signature)
    return frozenset(value for value in values if matches(matcher, value))


def _seen(entry: FieldPatternsComplete, field: Field) -> SeenField:
    values = field.values()
    by_structure: dict[str, list[str]] = {}
    for value in values:
        by_structure.setdefault(structure(value), []).append(value)
    families = []
    for family in entry.families:
        keys = family.composition or [family.key]
        members = frozenset(v for key in keys for v in by_structure.get(key, ()))
        families.append(_seen_family(family, members))
    covered = frozenset().union(*(family.members for family in families))
    return SeenField(tuple(families), frozenset(values) - covered, tuple(entry.limits))


def _seen_family(family: PatternFamily, members: frozenset[str]) -> SeenFamily:
    patterns = [
        (pattern, _accepted(pattern.signature, sorted(members))) for pattern in family.patterns
    ]
    # A family of one pattern that holds all of it is that pattern: the nodes of
    # the pattern are the nodes of the family (a node is a strict part).
    if len(patterns) == 1 and patterns[0][1] == members:
        nodes = _seen_nodes(patterns[0][0].nodes, members)
    else:
        nodes = tuple(
            SeenNode(pattern.render, accepted, _seen_nodes(pattern.nodes, accepted))
            for pattern, accepted in patterns
        )
    taken = frozenset().union(*(accepted for _, accepted in patterns))
    tables = [_seen_table(table, members, taken) for table in family.tables]
    return SeenFamily(
        family.patterns[0].render if family.patterns else family.key, members, nodes, tuple(tables)
    )


def _seen_table(table: PatternTable, members: frozenset[str], taken: frozenset[str]) -> SeenTable:
    """The values of each cell of a table: the combination of lengths of the
    lengths table, the head, the tail or the whole token of a content table."""
    if table.facet == "lengths":
        left = members - taken
        return SeenTable(
            table.facet,
            tuple(
                frozenset(
                    value for value in left if ",".join(map(str, lengths(value))) == cell.value
                )
                for cell in table.cells
            ),
        )
    edge, _, position = table.facet.partition(":")
    reads = {
        "head": lambda text, cell: text.startswith(cell),
        "tail": lambda text, cell: text.endswith(cell),
        "token": lambda text, cell: text == cell,
    }[edge]
    return SeenTable(
        table.facet,
        tuple(
            frozenset(
                value for value in members if reads(token(value, int(position)), cell.value)
            )
            for cell in table.cells
        ),
    )


def _seen_nodes(nodes: Sequence[PatternNode], members: frozenset[str]) -> tuple[SeenNode, ...]:
    """The nodes below a parent that holds ``members``, each with the values its
    signature accepts among them and its own nodes."""
    seen = []
    for node in nodes:
        accepted = _accepted(node.signature, sorted(members))
        seen.append(SeenNode(node.render, accepted, _seen_nodes(node.nodes, accepted)))
    return tuple(seen)


def declared_keys(field: Field, exposure: Mapping[str, str] | None = None) -> Declared:
    """The keys the detector of ``field`` declares (algorithm, section 4), as the
    Scan publishes them, masked field or not (DEC-027). ``exposure`` overrides
    the ``exposure`` settings (``detector_keys``)."""
    block = detector_keys_block(field, exposure)
    assert block["status"] == "complete", block
    return Declared(
        field.id,
        field.detector or "",
        tuple(_key(item) for item in block["keys"]),
        other=(block["others"]["keys"], block["others"]["occurrences"]),
        masked=field.masked,
    )


def detector_keys_block(field: Field, exposure: Mapping[str, str] | None = None) -> dict:
    """The ``keys`` block in the ``details`` of the detector of ``field``."""
    config = tuple(sorted((exposure or {}).items()))
    [found] = [
        item
        for item in _scanned(field, exposure=config).datasets[0].fields[0].detectors
        if item.id == field.detector
    ]
    return found.details["keys"]


def _key(item: Mapping[str, object]) -> Key:
    others = item.get("others", {"keys": 0, "occurrences": 0})
    return Key(
        item["key"],
        item["occurrences"],
        tuple(_key(child) for child in item.get("keys", ())),
        other=(others["keys"], others["occurrences"]),
    )


def validate(variants: Variants) -> Validation:
    """The outcome of every value of ``variants.file`` once the discovery has
    read ``variants.sample`` (FR-013, FR-015)."""
    return _validated(variants.sample, variants.file)


def validate_file(field: Field) -> Validation:
    """The outcome of every value of ``field.file`` once the discovery has
    read ``field.pairs`` (RC-14)."""
    assert field.file is not None
    return _validated(field, field.file)


def _validated(sample: Field, file: Sequence[tuple[str, int]]) -> Validation:
    accumulator = _accumulator(sample)
    outcomes: dict[str, Outcome] = {}
    for value, _ in file:
        outcome = accumulator.outcome(value)
        assert outcome is not None, value
        outcomes[value] = outcome  # type: ignore[assignment]
    return Validation(outcomes)


def _accumulator(
    sample: Field,
    unique: bool = False,
    table_cells: int | None = None,
    distinct_bytes: int | None = None,
) -> PatternAccumulator:
    """The accumulator of the validation of ``sample`` as the second pass builds it
    from the Scan of the sample."""
    result = _scanned(sample)
    entry = _scanned_entry(sample)
    assert isinstance(entry, FieldPatternsComplete)
    deep = DeepSettings().patterns
    return PatternAccumulator(
        entry,
        result.datasets[0].fields[0],
        result.config.pattern_inference,
        table_bytes=deep.table_bytes,
        distinct_bytes=deep.distinct_bytes if distinct_bytes is None else distinct_bytes,
        unique=unique,
        table_cells=table_cells,
    )


# Contract of the Patterns plan (design 18.12 and 20.9) ---------------------------------

EligibilityState = Literal["eligible", "low_relevance", "excluded", "not_assessable"]


@dataclass(frozen=True)
class Eligibility:
    """The eligibility of a field as the Scan publishes it (FR-001): a state, a
    score from 0 to 1 and reason codes."""

    state: EligibilityState
    score: float
    reasons: tuple[str, ...]


def eligibility(field: Field) -> Eligibility:
    """The eligibility object of ``field`` in a Scan (lot P2). A column made of
    digits only is typed as an integer by the Scan (RC-10, RC-11); ``field.detector``
    names the semantic detector that recognizes the column (``date``), ``masked``
    its exposure."""
    entry = _scanned_entry(field)
    return Eligibility(
        state=entry.eligibility.state,
        score=entry.eligibility.score,
        reasons=tuple(entry.eligibility.reasons),
    )


# Every detector but ``number`` reads a meaning: a field of the corpus without a
# detector is scanned without them, so that its values alone decide.
_SEMANTIC = tuple(name for name in DetectorSettings.model_fields if name != "number")


@cache
def _scanned(
    field: Field,
    settings: tuple[tuple[str, int], ...] = (),
    workers: int = 1,
    exposure: tuple[tuple[str, str], ...] = (),
) -> ScanResult:
    """A Scan of ``field``: a CSV file of one column holding each value as many
    times as it occurs, outside the checkout."""
    config: dict[str, object] = {}
    if field.detector is None:
        config["detectors"] = {name: {"enabled": False} for name in _SEMANTIC}
    if settings:
        config["pattern_inference"] = dict(settings)
    if exposure:
        config["exposure"] = dict(exposure)
    if field.distinct > 10_000:
        # Every distinct value is kept, so the cut of the discovery acts alone.
        config["limits"] = {"max_samples": field.distinct}
    with tempfile.TemporaryDirectory(prefix="tabalyst-patterns-") as folder:
        source = Path(folder) / "field.csv"
        with source.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["value"])
            for value, count in field.pairs:
                writer.writerows([value] for _ in range(count))
        result = scan(source, config=ScanConfig.model_validate(config), workers=workers)
    scanned = result.datasets[0].fields[0]
    if field.detector is not None:
        interpreted = {item.detector for item in scanned.interpretations.candidates}
        assert field.detector in interpreted, f"{field.id}: {field.detector} not read"
    assert (scanned.exposure in ("mask", "hide")) == field.masked, field.id
    assert result.derived is not None and result.derived.patterns is not None
    return result


def _scanned_entry(
    field: Field, settings: tuple[tuple[str, int], ...] = (), workers: int = 1
) -> FieldPatterns:
    """The ``derived.patterns`` entry of a Scan of ``field``."""
    result = _scanned(field, settings, workers)
    assert result.derived is not None and result.derived.patterns is not None
    [entry] = result.derived.patterns.fields
    return entry


@dataclass(frozen=True)
class CountedTable:
    """A facet table of the validation: counted cells, the rest, and whether the
    capacity cut it."""

    label: str
    cells: Mapping[str, int]
    others: int
    saturated: bool


@dataclass(frozen=True)
class CountedNode:
    """A pattern or node of ``pattern_counts`` with its exact occurrences, its
    distinct values and their accuracy (``exact`` or ``at_least``)."""

    label: str
    occurrences: int
    distinct: int
    distinct_accuracy: Literal["exact", "at_least"]
    children: tuple[CountedNode, ...] = ()
    rest: int = 0


@dataclass(frozen=True)
class CountedFamily:
    label: str
    occurrences: int
    patterns: tuple[CountedNode, ...]
    tables: tuple[CountedTable, ...]
    new_length_variants: int
    new_segment_variants: int


@dataclass(frozen=True)
class Counted:
    """The ``pattern_counts`` of a field (design 20.9): the sums that add up and
    the keys that were written."""

    values: int
    matched: int
    unknown_structure: int
    excluded: int
    families: tuple[CountedFamily, ...]
    computed_from: Literal["samples", "source"]
    keys: frozenset[str]


def count(
    variants: Variants | Field,
    exact_budget: int | None = None,
    table_capacity: int | None = None,
) -> Counted:
    """Validate the whole file of ``variants`` against the discovery of its sample, or,
    for a ``Field``, its ``file`` when it has one (RC-14) and its ``pairs`` otherwise,
    against the discovery of ``pairs``; return the counts (lot P6). ``exact_budget``
    limits the bytes that hold the distinct values, ``table_capacity`` the cells of a
    facet table. A field whose distribution is complete and that no budget bears on is
    counted from the samples, without reading a source."""
    sample = variants.sample if isinstance(variants, Variants) else variants
    file = variants.file
    from_samples = file is None and exact_budget is None
    accumulator = _accumulator(
        sample, unique=from_samples, table_cells=table_capacity, distinct_bytes=exact_budget
    )
    if from_samples:
        derive_from_samples(accumulator, _scanned(sample).datasets[0].fields[0])
    else:
        pairs = file if file is not None else sample.pairs
        accumulator.add_strings([value for value, _ in pairs], [number for _, number in pairs])
    result = accumulator.result(
        sum(number for _, number in (file if file is not None else sample.pairs)),
        "samples" if from_samples else "source",
    )
    return _counted(result)


def _counted(result: PatternCounts) -> Counted:
    def node(item: PatternNodeCount) -> CountedNode:
        return CountedNode(
            item.render,
            item.occurrences,
            item.distinct.count,
            item.distinct.accuracy,
            tuple(node(child) for child in item.nodes),
            item.rest,
        )

    def table(item: PatternTableCount) -> CountedTable:
        cells = {cell.value: cell.occurrences for cell in item.cells}
        return CountedTable(item.facet, cells, item.others, item.saturated)

    families = tuple(
        CountedFamily(
            family.id,
            family.occurrences,
            tuple(node(pattern) for pattern in family.patterns),
            tuple(table(item) for item in family.tables),
            family.new_variants.length,
            family.new_variants.segment,
        )
        for family in result.families
    )
    return Counted(
        result.values,
        result.matched,
        result.unknown_structure,
        sum(result.excluded.model_dump().values()),
        families,
        result.computed_from,
        frozenset(_keys(result.model_dump(mode="json"))),
    )


def _keys(data: object) -> list[str]:
    if isinstance(data, dict):
        return [key for key, value in data.items()] + [
            name for value in data.values() for name in _keys(value)
        ]
    if isinstance(data, list):
        return [name for value in data for name in _keys(value)]
    return []


def source_reads(fields: Sequence[Field]) -> int:
    """How many times the second pass reads the source to validate ``fields``
    together (lot P6)."""
    with tempfile.TemporaryDirectory(prefix="tabalyst-patterns-") as folder:
        source = Path(folder) / "data.csv"
        columns = [[value for value, number in item.pairs for _ in range(number)] for item in fields]
        rows = max(len(column) for column in columns)
        with source.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow([f"c{number}" for number in range(len(columns))])
            for row in range(rows):
                writer.writerow([column[row] if row < len(column) else "" for column in columns])
        config = {
            "detectors": {name: {"enabled": False} for name in _SEMANTIC},
            "limits": {"max_samples": max(item.distinct for item in fields)},
        }
        result = scan(source, config=ScanConfig.model_validate(config))
        registry = AnalyzerRegistry([PatternValidation])
        plan = plan_analyses(result, forced=True, registry=registry)
        outcome = run_second_pass(result, source, plan)
        return int(outcome.document.run.source_read)


Tamper = Literal["family_sum", "missing_parent", "entry_count", "unknown_signature"]


def check_scan_problems(field: Field, tamper: Tamper | None = None) -> list[str]:
    """The problems ``check_scan`` reports for the Scan of ``field`` after ``tamper``
    altered its ``derived.patterns`` (lot P7); empty when none."""
    document = _scanned(field).model_dump(mode="json", by_alias=True)
    patterns = document["derived"]["patterns"]
    [entry] = patterns["fields"]
    family = entry["families"][0]
    pattern = family["patterns"][0]
    if tamper == "family_sum":
        family["d"] += 1
    elif tamper == "missing_parent":
        node = next(item for fam in entry["families"] for pat in fam["patterns"] for item in pat["nodes"])
        node["parent"] = "f9.p9"
    elif tamper == "entry_count":
        patterns["fields"].clear()
    elif tamper == "unknown_signature":
        pattern["signature"][0]["max"] = pattern["signature"][0]["min"] + 5
    return check_scan(ScanResult.model_validate(document))


Change = Literal["render_only", "setting", "algorithm_version"]


@dataclass(frozen=True)
class CacheRun:
    """What a second run recomputed after a change (FR-020)."""

    discovery: bool
    validation: bool
    scan_stale: bool


def rerun_after(field: Field, change: Change) -> CacheRun:
    """Scan and validate ``field``, make ``change``, do it again and say what the
    second run recomputed (lot P7, FR-020): the discovery when it scanned again,
    the validation when the second pass executed it instead of reusing its result."""
    with tempfile.TemporaryDirectory(prefix="tabalyst-patterns-") as folder:
        source = Path(folder) / "field.csv"
        _write_column(source, field)
        location = StorageLocation(Path(folder) / "storage")
        detectors = (
            {name: {"enabled": False} for name in _SEMANTIC} if field.detector is None else {}
        )

        def configured(**inference: int) -> ScanConfig:
            settings: dict[str, object] = {"detectors": detectors}
            if inference:
                settings["pattern_inference"] = dict(inference)
            return ScanConfig.model_validate(settings)

        first = current_scan(source, configured(), location=location)
        assert not first.reused
        registry = AnalyzerRegistry([PatternValidation])
        plan = plan_analyses(first.result, forced=True, registry=registry)
        before = run_second_pass(first.result, source, plan)
        assert before.executed and not before.reused

        setting = {"max_patterns": 64} if change == "setting" else {}
        calls = {"discovery": 0}

        def counted(*args: object, **kwargs: object) -> object:
            calls["discovery"] += 1
            return infer_patterns(*args, **kwargs)  # type: ignore[arg-type]

        bump = (
            patch.object(patterninfer, "ALGORITHM_VERSION", patterninfer.ALGORITHM_VERSION + 1)
            if change == "algorithm_version"
            else nullcontext()
        )
        with bump, patch.object(scan_api, "infer_patterns", counted):
            second = current_scan(
                source,
                configured(**setting),
                location=location,
                json_indent=change == "render_only",
            )
            plan = plan_analyses(second.result, forced=True, registry=registry)
            after = run_second_pass(second.result, source, plan, previous=before.document)
        return CacheRun(
            discovery=bool(calls["discovery"]),
            validation=bool(after.executed),
            scan_stale=not second.reused,
        )


def _write_column(path: Path, field: Field) -> None:
    """A CSV file of one column holding each value of ``field`` as often as it occurs."""
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["value"])
        for value, number in field.pairs:
            writer.writerows([value] for _ in range(number))


def published_text(field: Field) -> str:
    """Everything the Scan, the second pass and the Report publish for ``field``,
    as one text to search for values (exposure, FR-022). Lots P3 and P5.

    A masked field is searched in the whole Scan: nothing of it may appear. For a
    field the exposure leaves open the Scan publishes its samples by design, so only
    what the discovery publishes is searched (the entry of ``derived.patterns``).
    """
    if field.masked:
        return _scanned(field).model_dump_json()
    return _scanned_entry(field).model_dump_json()


def published_renders(field: Field) -> list[str]:
    """The rendering of every pattern and node published for ``field`` (lot P4)."""
    entry = _scanned_entry(field)
    assert isinstance(entry, FieldPatternsComplete)

    def nodes(items: Sequence[PatternNode]) -> list[str]:
        return [text for node in items for text in (node.render, *nodes(node.nodes))]

    return [
        text
        for family in entry.families
        for pattern in family.patterns
        for text in (pattern.render, *nodes(pattern.nodes))
    ]

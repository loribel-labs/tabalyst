# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Ground truth of a scenario profile: ``truth.csv``, ``metrics.json`` and ``manifest.json``.

The contract is ``docs/dev/generate/insurance-v2.md`` section 5. Everything here is computed
from the files the run wrote (clean, altered, journal), never copied from the profile.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import astuple, dataclass, replace
from pathlib import Path
from typing import Annotated, Any, Final, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from tabalyst.generate_anomalies import AnomalyEvent
from tabalyst.generate_rarity import SAMPLE_SIZES, absence_probability
from tabalyst.generate_rules import (
    FORMAT_REVISION,
    FORMAT_VERSION,
    Conventions,
    Rule,
    RuleContext,
    RuleEvaluator,
    RulesDocument,
)
from tabalyst.generate_scenarios import CATEGORIES

METRICS_FORMAT: Final = "tabalyst.generate.metrics"
MANIFEST_FORMAT: Final = "tabalyst.generate.manifest"
# Raised whenever the bytes of a V2 output change for the same inputs; the reason goes to
# docs/dev/generate/insurance-v2-changelog.md (contract 5.5).
GENERATION_VERSION: Final = 2
TRUTH_COLUMNS: Final = (
    "truth_id", "kind", "scenario_id", "rule_id", "category", "severity", "rarity_level",
    "root_cause_id", "group_id", "event_id", "row_number", "column", "canonical_value",
    "expected_detection",
)
# Contract 3.2, in the order lines of one cell are sorted.
KINDS: Final = ("injected", "net_difference", "rule_violation", "valid_atypical", "relational",
                "uncertain")
SCHEMA_FILES: Final = {
    "rules": "tabalyst.generate.rules.schema.json",
    "metrics": "tabalyst.generate.metrics.schema.json",
    "manifest": "tabalyst.generate.manifest.schema.json",
}

Count = Annotated[int, Field(ge=0)]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
IsoDate = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$")]
CanonicalReader = Callable[[str, str, Mapping[str, str]], str]


@dataclass(frozen=True)
class TruthLine:
    """One line of ``truth.csv`` (contract 5.2); ``0`` stands for an empty ``event_id``."""

    truth_id: int
    kind: str
    scenario_id: str
    rule_id: str
    category: str
    severity: str
    rarity_level: str
    root_cause_id: str
    group_id: str
    event_id: int
    row_number: int
    column: str
    canonical_value: str
    expected_detection: str

    def sort_key(self) -> tuple[int, str, int, int, str]:
        return (self.row_number, self.column, KINDS.index(self.kind), self.event_id,
                self.rule_id)

    def cells(self) -> list[str]:
        """The text of each column, in the order of ``TRUTH_COLUMNS``."""
        return ["" if value == 0 and name == "event_id" else str(value)
                for name, value in zip(TRUTH_COLUMNS, astuple(self), strict=True)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Rows(_Model):
    """Rows of the altered file, in total and per branch."""

    total: Count
    by_branch: dict[str, Count]


class Counts(_Model):
    """The numbers of contract 4.2, recounted from the truth."""

    events: Count
    changed_cells: Count
    distinct_changed_cells: Count
    net_differences: Count


class ScenarioMetrics(_Model):
    """What one scenario asked for and what the files hold.

    ``eligible_population`` is the sum over its operations of the rows each can change in the
    clean file. ``applied_cases`` counts the cases (a key reused on two contracts is one) and
    ``rows_touched`` the rows they involve: equal while a case is one row.
    """

    rarity_level: str | None
    requested_cases: Count
    applied_cases: Count
    rows_touched: Count
    eligible_population: Count
    category: str
    severity: str
    missing_mechanism: str | None = None
    missing_reason: str | None = None


class AbsenceProbability(_Model):
    """Chance that a uniform sample misses every case of a scenario (contract 6.3).

    ``probability`` maps a sample size to the exact probability for this file, ``null`` for a
    size above the number of rows, and is itself ``null`` with ``reason`` ``multi_row_case``
    when a case spans several rows (the formula counts single-row cases).
    """

    cases: Count
    probability: dict[str, float | None] | None
    reason: Literal["multi_row_case"] | None


class RootCauseMetrics(_Model):
    """The aggregate impact of one common root cause across scenarios (contract 5.4)."""

    events: Count
    rows_touched: Count
    scenarios: list[str]


class MissingMechanismMetrics(_Model):
    """The aggregate impact of one missing data mechanism across scenarios."""

    events: Count
    rows_touched: Count
    columns: list[str]
    scenarios: list[str]


class MissingDataMetrics(_Model):
    """Aggregate metrics on missing data mechanisms (MCAR, MAR, MNAR) and reasons."""

    mechanisms: dict[str, MissingMechanismMetrics] = Field(default_factory=dict)
    reasons: dict[str, Count] = Field(default_factory=dict)
    by_column: dict[str, dict[str, Count]] = Field(default_factory=dict)


class MetricsDocument(_Model):
    """``<dataset>.<profile>.metrics.json`` (contract 5.4)."""

    format: Literal["tabalyst.generate.metrics"] = METRICS_FORMAT
    format_version: Literal["0.2.0"] = FORMAT_VERSION
    format_revision: Literal[1] = FORMAT_REVISION
    dataset: str
    profile: str
    rows: Rows
    counts: Counts
    scenarios: dict[str, ScenarioMetrics]
    rules: dict[str, Count]
    categories: dict[str, Count]
    kinds: dict[str, Count]
    absence_probability: dict[str, AbsenceProbability]
    root_causes: dict[str, RootCauseMetrics] = Field(default_factory=dict)
    missing_data: MissingDataMetrics = Field(default_factory=MissingDataMetrics)


class ScenarioEntry(_Model):
    """One scenario of the profile: its free description and the operations that serve it."""

    id: str
    description: str | None
    operations: list[Annotated[int, Field(ge=1)]]
    expected_cases: Count


class FileEntry(_Model):
    """One other file of the run, by role (the artifact kind) and name."""

    role: str
    name: str
    bytes: Count
    sha256: Sha256


class ManifestDocument(_Model):
    """``<dataset>.<profile>.manifest.json`` (contract 5.5): what fixes every byte of the run."""

    format: Literal["tabalyst.generate.manifest"] = MANIFEST_FORMAT
    format_version: Literal["0.2.0"] = FORMAT_VERSION
    format_revision: Literal[1] = FORMAT_REVISION
    tabalyst_version: str
    generation_version: Annotated[int, Field(ge=1)]
    seed: int
    as_of_date: IsoDate
    rows: Count
    dataset: str
    profile: str
    output_profile: str
    package_version: str | None
    definition_id: str
    scenarios: list[ScenarioEntry]
    files: list[FileEntry]
    truth_columns: list[str]


@dataclass(frozen=True)
class TruthResult:
    """The truth of one altered file and the two documents computed from it."""

    lines: tuple[TruthLine, ...]
    metrics: MetricsDocument
    rules: RulesDocument


def _text(operation: Mapping[str, object], key: str) -> str:
    value = operation.get(key)
    return value if isinstance(value, str) else ""


def _line(kind: str, operation: Mapping[str, object] | None, *, row_number: int, column: str,
          event_id: int, canonical_value: str) -> TruthLine:
    """A line described by the scenario of ``operation`` (contract 5.2)."""
    meta = operation or {}
    group_id = _text(meta, "group_id")
    if not group_id and meta.get("missing_mechanism"):
        group_id = f"missing:{meta['missing_mechanism']}:{meta.get('missing_reason', 'unreported')}"
    return TruthLine(0, kind, _text(meta, "scenario_id"), _text(meta, "rule_id"),
                     _text(meta, "category"), _text(meta, "severity"),
                     _text(meta, "rarity_level"), _text(meta, "root_cause_id"), group_id, event_id,
                     row_number, column, canonical_value, _text(meta, "expected_detection"))


def build_truth(clean: Path, altered: Path, events: Sequence[AnomalyEvent],
                summary: Mapping[str, object], *, dataset: str,
                profile: Mapping[str, object], rules: Sequence[Rule],
                conventions: Conventions, as_of_date: str, delimiter: str,
                canonical: CanonicalReader) -> TruthResult:
    """Read the clean and altered files together once and return their truth.

    The clean file must satisfy every rule of the profile (ADR 2026-11-11, contract 5.3):
    a violation there is a fault of the generator and raises ValueError naming the rule and
    the row. Raises ValueError as well when the recount disagrees with ``summary`` or a cell
    differs from the clean file without an event: the truth always describes the files.
    """
    operations = cast(list[dict[str, object]], profile["operations"])
    profile_id = cast(str, profile["id"])
    context = RuleContext(conventions, as_of_date)
    clean_rules = RuleEvaluator(rules, context)
    altered_rules = RuleEvaluator(rules, context)
    by_id = {rule.id: rule for rule in rules}
    # Events of a cell and of a row, in journal order, so the last one wins.
    last_of_cell: dict[tuple[int, str], AnomalyEvent] = {}
    events_of_row: dict[int, list[AnomalyEvent]] = {}
    # Cases that span two rows: the rows to read back to check the case and to describe it.
    related = [event for event in events if event.related_row]
    watched = {row for event in related for row in (event.row_number, event.related_row)}
    clean_watched: dict[int, dict[str, str]] = {}
    altered_watched: dict[int, dict[str, str]] = {}
    lines: list[TruthLine] = []
    for event in events:
        operation = operations[event.operation_index - 1]
        last_of_cell[(event.row_number, event.column)] = event
        events_of_row.setdefault(event.row_number, []).append(event)
        lines.append(_line("injected", operation, row_number=event.row_number,
                           column=event.column, event_id=event.event_id,
                           canonical_value=event.canonical_value))
    branches: Counter[str] = Counter()
    violations = []
    total = 0
    with (clean.open("r", encoding="utf-8", newline="") as left,
          altered.open("r", encoding="utf-8", newline="") as right):
        clean_rows = csv.DictReader(left, delimiter=delimiter)
        altered_rows = csv.DictReader(right, delimiter=delimiter)
        for number, (clean_row, altered_row) in enumerate(
                zip(clean_rows, altered_rows, strict=True), 2):
            total += 1
            if number in watched:
                clean_watched[number], altered_watched[number] = clean_row, altered_row
            branches[clean_row.get(conventions.branch_column, "")] += 1
            broken = clean_rules.check(number, clean_row)
            if broken:
                rule = by_id[broken[0].rule_id]
                raise ValueError(
                    f"{dataset}: the clean file breaks rule {rule.id} ({rule.title}) at row "
                    f"{broken[0].row_number}; a scenario profile needs a clean file that "
                    "satisfies its rules")
            violations.extend(altered_rules.check(number, altered_row))
            for column, value in altered_row.items():
                if value == clean_row[column]:
                    continue
                last = last_of_cell.get((number, column))
                if last is None:
                    raise ValueError(f"{dataset}: row {number}, {column} differs from the clean "
                                     "file without an event")
                last_operation = operations[last.operation_index - 1]
                meaning = canonical(column, clean_row[column], clean_row)
                lines.append(_line("net_difference", last_operation, row_number=number,
                                   column=column, event_id=last.event_id,
                                   canonical_value=meaning))
                if last_operation.get("category") == "valid_atypical":
                    # Not a defect (contract 3.1): the cell is valid, a naive detector flags it.
                    lines.append(_line("valid_atypical", last_operation, row_number=number,
                                       column=column, event_id=last.event_id,
                                       canonical_value=meaning))
    for event in related:
        lines.extend(_relational_lines(event, operations[event.operation_index - 1], dataset,
                                       clean_watched, altered_watched, canonical))
    for violation in violations:
        rule = by_id[violation.rule_id]
        cause = next((event for event in reversed(events_of_row.get(violation.cause_row, []))
                      if event.column in rule.columns), None)
        cause_operation = operations[cause.operation_index - 1] if cause is not None else None
        line = _line("rule_violation", cause_operation, row_number=violation.row_number, column="",
                     event_id=cause.event_id if cause is not None else 0, canonical_value="")
        lines.append(replace(line, rule_id=rule.id, category=rule.category,
                             severity=rule.severity, group_id=violation.group_id,
                             expected_detection=rule.detection))
    ordered = tuple(replace(line, truth_id=position) for position, line in
                    enumerate(sorted(lines, key=TruthLine.sort_key), 1))
    metrics = _metrics(ordered, summary, operations, rules, dataset=dataset, profile=profile_id,
                       total=total, branches=branches)
    document = RulesDocument(dataset=dataset, profile=profile_id, as_of_date=as_of_date,
                             conventions=conventions, rules=list(rules))
    return TruthResult(ordered, metrics, document)


def _relational_lines(event: AnomalyEvent, operation: Mapping[str, object], dataset: str,
                      clean: Mapping[int, Mapping[str, str]],
                      altered: Mapping[int, Mapping[str, str]],
                      canonical: CanonicalReader) -> list[TruthLine]:
    """The two ``relational`` lines of a case that copies a cell of an earlier row.

    One line for the cell that repeats and one for the cell it repeats, sharing the
    ``group_id`` ``<scenario>-<first row>``. Raises ValueError when the altered file no longer
    holds the same value on both rows: the truth would describe a case that is not there.
    """
    column, source = event.column, event.related_row
    if altered[event.row_number][column] != altered[source][column]:
        raise ValueError(
            f"{dataset}: row {event.row_number} no longer repeats {column} of row {source}; "
            "a case that reuses a value needs both cells left as the operation wrote them")
    group = f"{_text(operation, 'scenario_id')}-{source}"
    first = _line("relational", operation, row_number=source, column=column, event_id=0,
                  canonical_value=canonical(column, clean[source][column], clean[source]))
    second = _line("relational", operation, row_number=event.row_number, column=column,
                   event_id=event.event_id, canonical_value=event.canonical_value)
    return [replace(first, group_id=group), replace(second, group_id=group)]


def _metrics(lines: Sequence[TruthLine], summary: Mapping[str, object],
             operations: Sequence[Mapping[str, object]], rules: Sequence[Rule], *,
             dataset: str, profile: str, total: int,
             branches: Mapping[str, int]) -> MetricsDocument:
    injected = [line for line in lines if line.kind == "injected"]
    counts = Counts(
        events=len({line.event_id for line in injected}),
        changed_cells=len(injected),
        distinct_changed_cells=len({(line.row_number, line.column) for line in injected}),
        net_differences=sum(line.kind == "net_difference" for line in lines))
    for name, value in counts.model_dump().items():
        if summary.get(name) != value:
            raise ValueError(f"{dataset}: the truth counts {value} {name} but the summary "
                             f"{summary.get(name)}")
    entries = cast(list[dict[str, object]], summary["operations"])
    rows_of: dict[str, set[int]] = {}
    groups_of: dict[str, set[str]] = {}
    for line in injected:
        rows_of.setdefault(line.scenario_id, set()).add(line.row_number)
    for line in lines:
        if line.kind == "relational":
            rows_of.setdefault(line.scenario_id, set()).add(line.row_number)
            groups_of.setdefault(line.scenario_id, set()).add(line.group_id)
    scenarios: dict[str, ScenarioMetrics] = {}
    for operation, entry in zip(operations, entries, strict=True):
        scenario = cast(str, operation["scenario_id"])
        rows = rows_of.get(scenario, set())
        known = scenarios.get(scenario)
        scenarios[scenario] = ScenarioMetrics(
            rarity_level=cast("str | None", operation.get("rarity_level")),
            requested_cases=(known.requested_cases if known else 0)
            + cast(int, operation["count"]),
            applied_cases=len(groups_of.get(scenario) or rows), rows_touched=len(rows),
            eligible_population=(known.eligible_population if known else 0)
            + cast(int, entry["eligible_population"]),
            category=cast(str, operation["category"]),
            severity=cast(str, operation["severity"]),
            missing_mechanism=cast("str | None", operation.get("missing_mechanism")),
            missing_reason=cast("str | None", operation.get("missing_reason")),
        )
    categories = dict.fromkeys(sorted(CATEGORIES), 0)
    for metrics in scenarios.values():
        categories[metrics.category] += metrics.applied_cases
    kinds = Counter(line.kind for line in lines)
    violations = Counter(line.rule_id for line in lines if line.kind == "rule_violation")
    causes_events: dict[str, set[int]] = {}
    causes_rows: dict[str, set[int]] = {}
    causes_scenarios: dict[str, set[str]] = {}
    missing_events: dict[str, set[int]] = {}
    missing_rows: dict[str, set[int]] = {}
    missing_columns: dict[str, set[str]] = {}
    missing_scenarios: dict[str, set[str]] = {}
    reason_counts: Counter[str] = Counter()
    by_column_counts: dict[str, Counter[str]] = {}

    op_by_scenario = {cast(str, op["scenario_id"]): op for op in operations if "scenario_id" in op}
    for line in injected:
        if line.root_cause_id:
            causes_events.setdefault(line.root_cause_id, set()).add(line.event_id)
            causes_rows.setdefault(line.root_cause_id, set()).add(line.row_number)
            if line.scenario_id:
                causes_scenarios.setdefault(line.root_cause_id, set()).add(line.scenario_id)
        op = op_by_scenario.get(line.scenario_id, {})
        mech = op.get("missing_mechanism")
        if isinstance(mech, str):
            missing_events.setdefault(mech, set()).add(line.event_id)
            missing_rows.setdefault(mech, set()).add(line.row_number)
            missing_columns.setdefault(mech, set()).add(line.column)
            if line.scenario_id:
                missing_scenarios.setdefault(mech, set()).add(line.scenario_id)
            reason = op.get("missing_reason", "unreported")
            if isinstance(reason, str):
                reason_counts[reason] += 1
            by_column_counts.setdefault(line.column, Counter())[mech] += 1

    root_causes = {
        cause_id: RootCauseMetrics(
            events=len(causes_events[cause_id]),
            rows_touched=len(causes_rows[cause_id]),
            scenarios=sorted(causes_scenarios[cause_id]),
        )
        for cause_id in sorted(causes_events)
    }
    missing_mechanisms_metrics = {
        mech: MissingMechanismMetrics(
            events=len(missing_events[mech]),
            rows_touched=len(missing_rows[mech]),
            columns=sorted(missing_columns[mech]),
            scenarios=sorted(missing_scenarios[mech]),
        )
        for mech in sorted(missing_events)
    }
    missing_data = MissingDataMetrics(
        mechanisms=missing_mechanisms_metrics,
        reasons=dict(sorted(reason_counts.items())),
        by_column={col: dict(sorted(counts.items())) for col, counts in sorted(by_column_counts.items())},
    )
    return MetricsDocument(
        dataset=dataset, profile=profile,
        rows=Rows(total=total, by_branch=dict(sorted(branches.items()))), counts=counts,
        scenarios=scenarios, rules={rule.id: violations[rule.id] for rule in rules},
        categories=categories, kinds={kind: kinds[kind] for kind in KINDS},
        absence_probability={
            scenario: _absence(total, entry.applied_cases, scenario in groups_of)
            for scenario, entry in scenarios.items()},
        root_causes=root_causes,
        missing_data=missing_data)


def _absence(rows: int, cases: int, spans_rows: bool) -> AbsenceProbability:
    """The probability of absence of one scenario for every documented sample size."""
    if spans_rows:
        return AbsenceProbability(cases=cases, probability=None, reason="multi_row_case")
    return AbsenceProbability(
        cases=cases, reason=None,
        probability={str(size): absence_probability(rows, cases, size) for size in SAMPLE_SIZES})


def write_truth_csv(path: Path, lines: Sequence[TruthLine]) -> None:
    """Write ``truth.csv``: UTF-8, ``\\n``, comma, header (contract 5.2)."""
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(TRUTH_COLUMNS)
        writer.writerows(line.cells() for line in lines)


def scenario_entries(operations: Sequence[Mapping[str, object]]) -> list[ScenarioEntry]:
    """The scenarios of a profile in the order they first appear."""
    found: dict[str, ScenarioEntry] = {}
    for index, operation in enumerate(operations, 1):
        scenario = cast(str, operation["scenario_id"])
        known = found.get(scenario)
        found[scenario] = ScenarioEntry(
            id=scenario, description=cast("str | None", operation.get("description")),
            operations=[*(known.operations if known else []), index],
            expected_cases=(known.expected_cases if known else 0) + cast(int, operation["count"]))
    return list(found.values())


def file_entry(role: str, name: str, path: Path) -> FileEntry:
    """Describe a written file by its size and SHA-256 digest."""
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return FileEntry(role=role, name=name, bytes=path.stat().st_size, sha256=digest)


def document_text(document: BaseModel) -> str:
    """The JSON of a document as the files hold it: declared member order, two spaces."""
    data = document.model_dump(mode="json", by_alias=True, exclude_none=isinstance(
        document, RulesDocument))
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


# A JSON Schema is an open JSON document: its values are any JSON, hence Any.
def _schema(model: type[BaseModel], title: str, what: str) -> dict[str, Any]:
    schema = model.model_json_schema(mode="validation", by_alias=True)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = title
    format_name = model.model_fields["format"].default
    schema["description"] = (f"Document {format_name}, format {FORMAT_VERSION} revision "
                             f"{FORMAT_REVISION}: {what}")
    for node in [schema, *schema.get("$defs", {}).values()]:
        properties = node.get("properties", {})
        required = node.setdefault("required", [])
        for name in ("format", "format_version", "format_revision"):
            if name in properties and name not in required:
                required.append(name)
        if not required:
            del node["required"]
    return schema


def generate_schemas() -> dict[str, str]:
    """The committed schema files of the three documents, by role, as their text."""
    schemas = {
        "rules": _schema(RulesDocument, "Tabalyst Generate rules",
                         "the verifiable rules a scenario profile uses."),
        "metrics": _schema(MetricsDocument, "Tabalyst Generate metrics",
                           "the exact counts of a scenario profile's run."),
        "manifest": _schema(ManifestDocument, "Tabalyst Generate manifest",
                            "the inputs and file digests of a scenario profile's run."),
    }
    return {role: json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
            for role, schema in schemas.items()}

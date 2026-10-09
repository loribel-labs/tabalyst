# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Models of an analysis plan (design 20.5, specification 11.5).

A plan says what is useful and possible to add to a finished Scan, and what it
would cost. It holds no data value and no date, so the same Scan, request and
budgets give the same plan on any machine.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_serializer

from tabalyst.scanner.models import ScanModel, _omit_none
from tabalyst.scanner.planner.stratmodels import Stratification

PLANNER_NAME = "tabalyst.planner"
PLANNER_VERSION = 1

CpuClass = Literal["very_low", "low", "moderate", "high"]
CPU_ORDER: tuple[CpuClass, ...] = ("very_low", "low", "moderate", "high")

AssessmentKind = Literal["applicable", "satisfied", "not_applicable"]
SelectionState = Literal["selected", "already_satisfied", "rejected"]


class Memory(ScanModel):
    """Bytes of a state in three scenarios. ``max`` is a firm bound taken from
    the counts of the Scan, ``min`` what the Scan already proves and
    ``expected`` the likely size. They are payloads of the structures, not a
    promise of process memory."""

    min: int
    expected: int
    max: int


class State(ScanModel):
    """A piece of memory an analysis needs. Two candidates with the same ``key``
    share it, and the plan counts it once (PLAN-04)."""

    key: str
    memory: Memory


class Costs(ScanModel):
    """What one analysis adds to the common reading (COST-01): its states and
    its CPU class."""

    memory: Memory
    cpu: CpuClass
    # Nanoseconds the analysis adds to each cell it reads, from the cost model.
    cell_ns: int
    states: list[State]


class Utility(ScanModel):
    """A versioned heuristic from 0 to 100 with its reasons. It orders the
    candidates; it is not a measure of the data."""

    score: int
    reasons: list[str]


class Applicability(ScanModel):
    """Whether the analysis concerns the field; ``reasons`` are codes."""

    state: Literal["applicable", "not_applicable"]
    reasons: list[str]


class Selection(ScanModel):
    """The decision on a candidate. ``reason`` is a code (design 20.5);
    ``priority`` numbers the selected candidates in the order they were chosen;
    ``satisfied_by`` locates the fact of the Scan that already answers it."""

    state: SelectionState
    reason: str
    requested: bool
    priority: int | None = None
    satisfied_by: str | None = None


class Execution(ScanModel):
    """How the analysis would run. A refusal to select never means the analysis
    is impossible (PLAN-06). ``on_limit`` is the policy when a limit is met
    while running (D08): the result is ``limited`` with its reason, and the
    count of what was read so far is never presented as complete."""

    requires_source: bool
    available: bool
    deterministic: bool
    reusable: bool
    on_limit: Literal["limited"] = "limited"


class Exploration(ScanModel):
    """What the row sample says of a pair of numeric columns (design 20.12,
    REL-05): the rows both columns have a number in (``pairs``), the
    coefficient over them and its interval, or the ``reason`` it is not defined.
    It is an exploration of ``scope`` rows and says nothing of the population
    beyond them: a pair not detected here may still hold elsewhere. The figures
    are rounded to six decimals, which keeps the plan the same on any machine.
    ``score`` is the lower bound of the absolute coefficient that the planner
    ranks by."""

    scope: Literal["interior_rows", "all_rows"]
    pairs: int
    coefficient: float | None = None
    lower: float | None = None
    upper: float | None = None
    score: float | None = None
    reason: str | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("coefficient", "lower", "upper", "score", "reason"))


class TableExploration(ScanModel):
    """What the row sample says of a table of a category against a feature of
    another column (design 20.13, REL-05): the ``rows`` classified in both
    axes, the effective ``categories`` and ``classes`` (axes with a count), and
    the association, or the ``reason`` it is not defined. It says nothing of
    the population beyond the ``scope`` rows: a relation not detected here may
    still hold elsewhere. ``score`` is the bias-corrected Cramér's V the planner
    ranks by, and ``stable`` says whether the sample has the counts to trust it (a
    table that is not is still listed: the whole file may have them). Figures are
    rounded to six decimals."""

    scope: Literal["interior_rows", "all_rows"]
    rows: int
    categories: int = 0
    classes: int = 0
    purity: float | None = None
    cramers_v: float | None = None
    score: float | None = None
    stable: bool | None = None
    reason: str | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("purity", "cramers_v", "score", "stable", "reason"))


class Candidate(ScanModel):
    """One analysis of one field with its decision. ``method`` and ``parameters``
    are absent for an analysis that does not apply; ``costs`` too. An analysis
    of a pair of fields names the second one in ``partner`` (and ``display``
    names both) and carries the ``exploration`` that proposed it."""

    id: str
    analyzer: str
    analyzer_version: int
    dataset: str
    field: str
    display: str
    method: str | None = None
    parameters: dict[str, int | str] = Field(default_factory=dict)
    outputs: list[str]
    applicability: Applicability
    utility: Utility | None = None
    costs: Costs | None = None
    selection: Selection
    execution: Execution
    partner: str | None = None
    exploration: Exploration | TableExploration | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("partner", "exploration"))


class PlanBase(ScanModel):
    """The Scan the plan stands on (design 19.5)."""

    format_revision: int
    engine_version: str
    source_sha256: str
    config_sha256: str
    facts_sha256: str


class RequestedAnalysis(ScanModel):
    """An explicit request. ``dataset`` and ``field`` are absent for every
    dataset or field; ``candidates`` counts what it matched, 0 when the
    analysis does not concern any field asked for."""

    analyzer: str
    dataset: str | None = None
    field: str | None = None
    partner: str | None = None
    feature: str | None = None
    candidates: int

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("partner", "feature"))


class Objective(ScanModel):
    """What the plan was asked for. ``forced`` is a second pass that was asked
    for as a whole (``--deep``): it takes every applicable analysis the hard
    memory budget holds, whatever the automatic limits."""

    automatic: bool
    forced: bool = False
    requested: list[RequestedAnalysis]


class Budgets(ScanModel):
    """Deterministic budgets (design 20.2). Memory is charged with the firm
    ``max`` bound of each state.

    ``memory_bytes`` is the hard budget: no selection exceeds it, whoever asked
    for it (MEM-06). ``automatic_memory_bytes``, ``max_cells`` (cells of the
    common reading) and ``automatic_max_cpu`` limit what the planner picks by
    itself; a selection beyond them, because it was requested or forced,
    requires a confirmation (R1). Values come from the cost model.
    """

    memory_bytes: int
    automatic_memory_bytes: int
    max_cells: int | None
    automatic_max_cpu: CpuClass
    overflow: Literal["reject"] = "reject"
    # Pairs of columns and tables the planner picks by itself (design 20.12,
    # 20.13).
    automatic_pairs: int = 8
    automatic_tables: int = 8


class CommonCost(ScanModel):
    """The reading shared by every selected analysis: parsed once, whatever the
    number of analyses (COST-01)."""

    requires_source: bool
    cells: int | None
    memory_bytes: int
    cpu: CpuClass | None


class Summary(ScanModel):
    """Counts of the candidates by decision, and what the selection needs."""

    candidates: int
    selected: int
    already_satisfied: int
    rejected: int
    second_pass_required: bool
    executable: bool
    memory: Memory
    # Codes of the automatic limits that the selection exceeds: empty for what
    # the planner picked by itself, which is what makes a confirmation needed.
    beyond_automatic: list[str]


class ExploredDataset(ScanModel):
    """The exploration of the pairs of one dataset (design 20.12, REL-06).

    ``rows`` are the rows of the sample the pairs were scored on, ``scope`` which
    rows they are. ``numeric`` columns were looked at; those left out are counted
    by reason in ``excluded`` (``constant``, ``sensitive_exposure``,
    ``repeated_path``, ``identifier_like``, ``not_in_sample``, ``too_few_values``,
    ``column_budget``) and ``columns`` were kept. Of the ``possible`` pairs,
    ``evaluated`` were scored, ``undefined`` of them have no coefficient (their
    reasons counted in ``undefined_reasons``) and ``listed`` are candidates of
    the plan. ``work`` is the pairs times the rows compared, the post-processing
    budget (COST-05). ``unavailable`` says why the dataset was not explored."""

    dataset: str
    scope: Literal["interior_rows", "all_rows"] | None = None
    rows: int = 0
    numeric: int = 0
    columns: int = 0
    excluded: dict[str, int] = Field(default_factory=dict)
    possible: int = 0
    evaluated: int = 0
    undefined: int = 0
    undefined_reasons: dict[str, int] = Field(default_factory=dict)
    listed: int = 0
    work: int = 0
    unavailable: str | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("scope", "unavailable"))


class ExploredTables(ScanModel):
    """The exploration of the tables of one dataset (design 20.13, REL-11).

    ``categories`` columns are eligible categories and ``features`` the tables
    of a column against a feature that were possible: of the columns looked at,
    those left out are counted by reason in ``excluded_categories`` and
    ``excluded_features``. Of the ``possible`` tables, ``evaluated`` were scored
    on ``rows`` rows of the sample (``scope`` says which), ``undefined`` have no
    score (reasons in ``undefined_reasons``) and ``listed`` are candidates of
    the plan. ``work`` is the tables times the rows coded, the post-processing
    budget (COST-05); ``cells`` the largest table of the plan, rows by classes,
    counters included. ``unavailable`` says why the dataset was not explored."""

    dataset: str
    scope: Literal["interior_rows", "all_rows"] | None = None
    rows: int = 0
    categories: int = 0
    columns: int = 0
    excluded_categories: dict[str, int] = Field(default_factory=dict)
    excluded_features: dict[str, int] = Field(default_factory=dict)
    possible: int = 0
    evaluated: int = 0
    undefined: int = 0
    undefined_reasons: dict[str, int] = Field(default_factory=dict)
    listed: int = 0
    work: int = 0
    cells: int = 0
    unavailable: str | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("scope", "unavailable"))


class Relations(ScanModel):
    """What the planner looked at to propose pairs of columns (``datasets``: one
    entry per dataset with at least two numeric columns) and tables of a
    category against a feature (``tables``: one per dataset with a category)."""

    datasets: list[ExploredDataset] = Field(default_factory=list)
    tables: list[ExploredTables] = Field(default_factory=list)

    @model_serializer(mode="wrap")
    def _omit_empty(self, handler) -> dict[str, Any]:
        data = handler(self)
        for name in ("datasets", "tables"):
            if not data.get(name):
                data.pop(name, None)
        return data


class AnalysisPlan(ScanModel):
    """What to add to a Scan, why, and at what cost.

    ``plan_id`` is the SHA-256 of the rest of the plan. ``executable`` is false
    while a selected analysis has no implementation in this version.
    """

    planner: str = PLANNER_NAME
    planner_version: int = PLANNER_VERSION
    utility_version: int
    cost_model_version: int
    plan_id: str
    base: PlanBase
    objective: Objective
    budgets: Budgets
    common: CommonCost
    summary: Summary
    relations: Relations | None = None
    # Advice on stratified sampling, present when it was asked for (20.14).
    stratification: Stratification | None = None
    candidates: list[Candidate]

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("relations", "stratification"))

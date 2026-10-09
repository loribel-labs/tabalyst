# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Models of an analysis plan (design 20.5, specification 11.5).

A plan says what is useful and possible to add to a finished Scan, and what it
would cost. It holds no data value and no date, so the same Scan, request and
budgets give the same plan on any machine.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from tabalyst.scanner.models import ScanModel

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
    is impossible (PLAN-06)."""

    requires_source: bool
    available: bool
    deterministic: bool
    reusable: bool


class Candidate(ScanModel):
    """One analysis of one field with its decision. ``method`` and ``parameters``
    are absent for an analysis that does not apply; ``costs`` too."""

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
    candidates: int


class Objective(ScanModel):
    """What the plan was asked for."""

    automatic: bool
    requested: list[RequestedAnalysis]


class Budgets(ScanModel):
    """Deterministic budgets (design 20.2). Memory is charged with the firm
    ``max`` bound of each state. ``max_cells`` (cells of the common reading) and
    ``automatic_max_cpu`` only limit what the planner picks by itself. Values
    are provisional until the calibration of lot 6b."""

    memory_bytes: int
    max_cells: int | None
    automatic_max_cpu: CpuClass
    overflow: Literal["reject"] = "reject"


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


class AnalysisPlan(ScanModel):
    """What to add to a Scan, why, and at what cost.

    ``plan_id`` is the SHA-256 of the rest of the plan. ``executable`` is false
    while a selected analysis has no implementation in this version.
    """

    planner: str = PLANNER_NAME
    planner_version: int = PLANNER_VERSION
    utility_version: int
    plan_id: str
    base: PlanBase
    objective: Objective
    budgets: Budgets
    common: CommonCost
    summary: Summary
    candidates: list[Candidate]

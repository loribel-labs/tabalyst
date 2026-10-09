# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Models of the plan of a smart sample (design 20.15, specification 15.3).

The plan says what a smart sample would aim to cover, with what weight, at what
cost and in how many readings of the source. It holds counts and references into
the Scan, never a value of the data, and no date or measured time.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_serializer

from tabalyst.config import SmartSettings
from tabalyst.scanner.models import ScanModel, _omit_none
from tabalyst.scanner.planner.models import PlanBase

SAMPLING_PLANNER_NAME = "tabalyst.smart"
SAMPLING_PLANNER_VERSION = 1
# Version of the predicates a target is described by: the sample of lot 10b
# reads them, so a change of meaning is a change of this number.
PREDICATE_VERSION = 1

Family = Literal[
    "low_cardinality", "structured_string", "numeric", "date", "quality", "relations"
]
FAMILIES: tuple[Family, ...] = (
    "low_cardinality",
    "structured_string",
    "numeric",
    "date",
    "quality",
    "relations",
)

PredicateKind = Literal[
    "value_equals",
    "value_missing",
    "pattern_matches",
    "pattern_other",
    "length_min",
    "length_max",
    "numeric_min",
    "numeric_max",
    "numeric_zero",
    "numeric_sign",
    "numeric_bin",
    "date_min",
    "date_max",
    "date_kind",
    "date_year",
    "observation",
    "relation_exception",
]

# exact: the count of the rows the target covers; lower_bound: at least that
# many; indicator: a share of distinct values or of another population, which
# says how rare the target is without being its frequency; unknown: not known.
FrequencyAccuracy = Literal["exact", "lower_bound", "indicator", "unknown"]
Evidence = Literal["exact", "sample", "second_pass"]
Obligation = Literal["mandatory", "optional"]
Feasibility = Literal["ready", "not_evaluable"]
# catalog_complete: every value of the column has a target; known_values_only:
# only the values the Scan saw have one; none: the column has no target of this
# family.
Guarantee = Literal["catalog_complete", "known_values_only", "none"]
DeepStatus = Literal["current", "stale", "absent"]
PassName = Literal["scan", "second_pass", "selection"]


class Predicate(ScanModel):
    """What makes a row cover a target, as a kind and the references that fix it
    (a sampled entry, a pattern, a bin). ``source`` is where the references
    point: the Scan, or the second-pass document. Never a value of the data."""

    kind: PredicateKind
    version: int = PREDICATE_VERSION
    source: Literal["scan", "second_pass"] = "scan"
    ref: str | None = None
    params: dict[str, int | str] = Field(default_factory=dict)

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler: Any) -> dict[str, Any]:
        data = _omit_none(handler(self), ("ref",))
        if not data.get("params"):
            data.pop("params", None)
        return data


class Frequency(ScanModel):
    """How many rows the target covers, when that is known, and how."""

    accuracy: FrequencyAccuracy
    count: int | None = None
    share: float | None = None
    method: str | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler: Any) -> dict[str, Any]:
        return _omit_none(handler(self), ("count", "share", "method"))


class Weight(ScanModel):
    """The weight of a target and what it is made of (design 20.15)."""

    version: int
    value: float
    base: float
    rarity: float
    capped: bool


class Target(ScanModel):
    """One thing a smart sample aims to cover (SRS 15.3).

    ``origin`` is the observation or the analysis the target comes from, and
    ``needs`` the documents it stands on. ``reason`` explains a target that is
    ``not_evaluable`` by the sample.
    """

    id: str
    family: Family
    dataset: str
    fields: list[str]
    displays: list[str]
    predicate: Predicate
    frequency: Frequency
    weight: Weight
    obligation: Obligation
    minimum: int = 1
    feasibility: Feasibility
    reason: str | None = None
    evidence: Evidence
    origin: str | None = None
    needs: list[str]

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler: Any) -> dict[str, Any]:
        return _omit_none(handler(self), ("reason", "origin"))


class Catalog(ScanModel):
    """What the targets of one family say about one column: whether they list
    every value it can take (E09) or only the ones the Scan saw (E12)."""

    family: Family
    dataset: str
    field: str
    display: str
    complete: bool
    guarantee: Guarantee
    targets: int
    # Codes of ``reasons.CATALOG``.
    reasons: list[str]


class FamilySummary(ScanModel):
    """The targets of one family: defined, mandatory, left out by the budget."""

    family: Family
    targets: int
    mandatory: int
    not_evaluable: int
    dropped: int
    total_weight: float


class Summary(ScanModel):
    """Counts of the targets kept. ``dropped`` are the ones the budget of
    targets left out, the lightest first (SMART-11)."""

    targets: int
    mandatory: int
    optional: int
    not_evaluable: int
    dropped: int
    total_weight: float
    families: list[FamilySummary]


class Sizes(ScanModel):
    """The sizes of the sample. ``mandatory_bound`` is the number of mandatory
    targets the Scan can evaluate: one row each is always enough, and rows that
    cover several targets need fewer. ``useful_maximum`` is the size beyond
    which the reserve would be the only thing added; ``records`` the rows of the
    dataset."""

    requested: int | None = None
    mandatory_bound: int
    useful_maximum: int
    records: int

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler: Any) -> dict[str, Any]:
        return _omit_none(handler(self), ("requested",))


class Reserve(ScanModel):
    """The rows kept for ordinary data, the bottom-k reserve of rows. They are
    a share of the sample asked for, and give way to mandatory targets: the
    reserve never prevents a coverage that is achievable (SMART-10)."""

    share: float
    rows_requested: int | None = None
    rows_granted: int | None = None
    reduced_by_mandatory: bool = False

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler: Any) -> dict[str, Any]:
        return _omit_none(handler(self), ("rows_requested", "rows_granted"))


class CandidateBudget(ScanModel):
    """The candidate rows the selection would hold in memory: a few per target
    and the reserve. ``bytes_expected`` counts the rows as source text (the mean
    row size of the source), not the memory of the process; ``fits`` says whether
    it stays within ``budget_bytes``. When it does not, ``per_target_effective``
    is the number of candidates per target the budget allows, at least one."""

    per_target: int
    per_target_effective: int
    rows: int
    row_bytes: int | None = None
    bytes_expected: int | None = None
    budget_bytes: int
    fits: bool

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler: Any) -> dict[str, Any]:
        return _omit_none(handler(self), ("row_bytes", "bytes_expected"))


class SelectionMethod(ScanModel):
    """How the sample of lot 10b chooses: a greedy cover over a bounded pool, no
    optimum promised (SMART-07), with a deterministic tie-break."""

    name: str = "weighted_cover"
    version: int = 1
    seed: int


class Awaiting(ScanModel):
    """Targets that only an enrichment (the second pass) can bring."""

    family: Family
    analyzer: str
    analyses: int


class Enrichment(ScanModel):
    """The state of the second-pass document the targets may stand on.
    ``requested`` says that a second pass was asked for before the sample;
    ``awaiting`` is then what it would add."""

    deep: DeepStatus
    used: int
    requested: bool
    awaiting: list[Awaiting]


class PassStep(ScanModel):
    """One reading of the source, or one that is not needed, with the reason."""

    name: PassName
    needed: bool
    reads_source: bool
    # Code of ``reasons.PASSES``.
    reason: str


class Passes(ScanModel):
    """The readings of the source from now to the sample, announced before any
    of them starts (E14): ``total`` counts those still needed."""

    total: int
    steps: list[PassStep]


class SamplingPlan(ScanModel):
    """What a smart sample of one dataset would aim for, and what it would take.

    ``plan_id`` is the SHA-256 of the rest of the plan. The same Scan, second-pass
    document, request and settings give the same plan on any machine.
    """

    planner: str = SAMPLING_PLANNER_NAME
    planner_version: int = SAMPLING_PLANNER_VERSION
    weights_version: int
    plan_id: str
    base: PlanBase
    settings: SmartSettings
    settings_sha256: str
    dataset: str
    size: Sizes
    reserve: Reserve
    candidates: CandidateBudget
    # Between mandatory targets and the reserve, the mandatory ones come first.
    conflict: Literal["mandatory_first"] = "mandatory_first"
    method: SelectionMethod
    enrichment: Enrichment
    passes: Passes
    summary: Summary
    catalogs: list[Catalog]
    targets: list[Target]

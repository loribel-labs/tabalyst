# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The planner: from a finished Scan to a plan of analyses (design 20.5).

It reads the Scan in memory or from the cache, never a Report and never the
source. The choice depends only on the Scan, the request and the budgets, so
the same inputs give the same plan on any machine (principle 7).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass

from tabalyst.config import DeepSettings
from tabalyst.errors import ConfigurationError
from tabalyst.scanner.identity import facts_sha256
from tabalyst.scanner.models import DatasetResult, ScanResult
from tabalyst.scanner.planner.analyzer import Analyzer, Assessment
from tabalyst.scanner.planner.analyzers.pearson import (
    PAIR_SEPARATOR,
    PearsonCorrelation,
)
from tabalyst.scanner.planner.costmodel import (
    COST_MODEL_VERSION,
    DEFAULT_AUTOMATIC_MEMORY_BYTES,
    DEFAULT_MAX_CELLS,
    DEFAULT_MEMORY_BUDGET_BYTES,
    PARSER_RESERVE_BYTES,
    cell_class,
)
from tabalyst.scanner.planner.facts import FieldFacts, scan_facts
from tabalyst.scanner.planner.models import (
    CPU_ORDER,
    AnalysisPlan,
    Applicability,
    Budgets,
    Candidate,
    CommonCost,
    Costs,
    Execution,
    Exploration,
    ExploredDataset,
    Memory,
    Objective,
    PlanBase,
    Relations,
    RequestedAnalysis,
    Selection,
    State,
    Summary,
    Utility,
)
from tabalyst.scanner.planner.registry import AnalyzerRegistry, default_registry
from tabalyst.scanner.planner.relations import (
    PairProposal,
    explicit_proposal,
    explore_dataset,
)

UTILITY_VERSION = 1
# The lowest utility the planner picks by itself (a forced plan ignores it).
AUTOMATIC_MIN_UTILITY = 45


@dataclass(frozen=True, slots=True)
class AnalysisRequest:
    """An analysis asked for explicitly. ``dataset`` and ``field`` (an id or a
    display path) narrow it; absent, it concerns every dataset or field. For an
    analysis of pairs, ``field`` and ``partner`` name one pair, which may be
    absent from what the exploration proposes; ``field`` alone asks for the
    proposed pairs that use it."""

    analyzer: str
    dataset: str | None = None
    field: str | None = None
    partner: str | None = None


def default_budgets(deep: DeepSettings | None = None) -> Budgets:
    """The budgets of the planner, calibrated on the baselines (design 20.2);
    the number of pairs it picks by itself comes from the ``deep`` settings."""
    deep = DeepSettings() if deep is None else deep
    return Budgets(
        memory_bytes=DEFAULT_MEMORY_BUDGET_BYTES,
        automatic_memory_bytes=DEFAULT_AUTOMATIC_MEMORY_BYTES,
        max_cells=DEFAULT_MAX_CELLS,
        automatic_max_cpu="moderate",
        automatic_pairs=deep.pearson.automatic_pairs,
    )


@dataclass(slots=True)
class _Entry:
    """A candidate being decided."""

    order: int
    analyzer: Analyzer
    facts: FieldFacts
    assessment: Assessment
    costs: Costs | None = None
    utility: Utility | None = None
    requested: bool = False
    selection: Selection | None = None
    # The second field of a pair and what the sample says of it.
    partner: FieldFacts | None = None
    exploration: Exploration | None = None

    @property
    def id(self) -> str:
        field = self.facts.field
        if self.partner is not None:
            field = f"{field}{PAIR_SEPARATOR}{self.partner.field}"
        return f"{self.analyzer.id}:{self.facts.dataset}:{field}"


class _Ledger:
    """The memory of the selected analyses: each state once, whoever uses it
    (PLAN-04), plus the reading they share. The totals are kept as states are
    added, so deciding a candidate costs its own states, not the whole plan."""

    def __init__(self) -> None:
        self._states: dict[str, Memory] = {}
        self._sum = [0, 0, 0]
        # Whether a selected analysis reads the source, which costs the parser.
        self.reading = False

    def _extra(self, states: Sequence[State]) -> list[int]:
        """Bytes that ``states`` add to the total, per scenario: a state already
        held counts only by what it exceeds."""
        extra = [0, 0, 0]
        for state in states:
            known = self._states.get(state.key)
            new = (state.memory.min, state.memory.expected, state.memory.max)
            old = (0, 0, 0) if known is None else (known.min, known.expected, known.max)
            for index in range(3):
                extra[index] += max(0, new[index] - old[index])
        return extra

    def total(self) -> Memory:
        reserve = PARSER_RESERVE_BYTES if self.reading else 0
        low, expected, high = self._sum
        return Memory(min=reserve + low, expected=reserve + expected, max=reserve + high)

    def fits(self, costs: Costs, reads_source: bool, budget: int) -> bool:
        """Whether the firm bound of the selection with ``costs`` stays within
        ``budget``."""
        reserve = PARSER_RESERVE_BYTES if self.reading or reads_source else 0
        return reserve + self._sum[2] + self._extra(costs.states)[2] <= budget

    def add(self, costs: Costs, reads_source: bool) -> None:
        extra = self._extra(costs.states)
        for index in range(3):
            self._sum[index] += extra[index]
        for state in costs.states:
            known = self._states.get(state.key)
            self._states[state.key] = (
                state.memory
                if known is None
                else Memory(
                    min=max(known.min, state.memory.min),
                    expected=max(known.expected, state.memory.expected),
                    max=max(known.max, state.memory.max),
                )
            )
        self.reading = self.reading or reads_source


def plan_base(scan: ScanResult) -> PlanBase:
    """The identity of the Scan a plan stands on (design 19.5): a plan is only
    valid for the Scan whose base it carries."""
    return PlanBase(
        format_revision=scan.format_revision,
        engine_version=scan.engine.version,
        source_sha256=scan.source.sha256,
        config_sha256=scan.config_sha256,
        facts_sha256=facts_sha256(scan),
    )


def _cells(scan: ScanResult) -> int:
    shape_cells = scan.source.shape.cells
    if shape_cells is not None:
        return shape_cells
    return sum(len(dataset.fields) * dataset.record_count for dataset in scan.datasets)


def _matches(request: AnalysisRequest, facts: FieldFacts, analyzer: Analyzer) -> bool:
    return (
        request.analyzer == analyzer.id
        and request.dataset in (None, facts.dataset)
        and request.field in (None, facts.field, facts.display)
    )


def _pair_matches(request: AnalysisRequest, first: FieldFacts, second: FieldFacts) -> bool:
    """Whether a request for pairs concerns the pair (in either order)."""
    if request.dataset not in (None, first.dataset):
        return False
    if request.field is None:
        return True
    members = ({first.field, first.display}, {second.field, second.display})
    if request.partner is None:
        return any(request.field in member for member in members)
    return (request.field in members[0] and request.partner in members[1]) or (
        request.field in members[1] and request.partner in members[0]
    )


def _check_requests(
    requests: Sequence[AnalysisRequest],
    registry: AnalyzerRegistry,
    scan: ScanResult,
) -> None:
    datasets = {dataset.id: dataset for dataset in scan.datasets}
    for request in requests:
        if request.analyzer not in registry:
            raise ConfigurationError(f"Unknown analyzer {request.analyzer!r}.")
        if request.dataset is not None and request.dataset not in datasets:
            raise ConfigurationError(f"Unknown dataset {request.dataset!r}.")
        if request.field is not None:
            scope = (
                [datasets[request.dataset]] if request.dataset is not None else datasets.values()
            )
            if not any(
                request.field in (field.id, field.display)
                for dataset in scope
                for field in dataset.fields
            ):
                raise ConfigurationError(f"Unknown field {request.field!r}.")
        if request.partner is not None:
            if request.analyzer != PearsonCorrelation.id:
                raise ConfigurationError(f"{request.analyzer!r} does not analyze pairs of fields.")
            if request.field is None:
                raise ConfigurationError("A partner needs the field it pairs with.")
            if request.partner == request.field:
                raise ConfigurationError("A pair needs two different fields.")
            scope = (
                [datasets[request.dataset]] if request.dataset is not None else datasets.values()
            )
            if not any(
                {request.field, request.partner}
                <= {name for field in dataset.fields for name in (field.id, field.display)}
                for dataset in scope
            ):
                raise ConfigurationError(
                    f"No dataset has both {request.field!r} and {request.partner!r}."
                )


def _decide(
    entries: list[_Entry], budgets: Budgets, automatic: bool, forced: bool, cells: int
) -> _Ledger:
    """Set the selection of every entry (PLAN-05) and return the memory the
    selection needs.

    A request or a forced plan may use the hard budget; what the planner picks
    by itself stays within the automatic limits, the memory of the requests
    already chosen included.
    """
    ledger = _Ledger()
    priority = 0
    automatic_memory = min(budgets.automatic_memory_bytes, budgets.memory_bytes)

    def reject(entry: _Entry, reason: str) -> None:
        entry.selection = Selection(state="rejected", reason=reason, requested=entry.requested)

    def try_select(entry: _Entry, reason: str, memory_limit: int) -> None:
        nonlocal priority
        assert entry.costs is not None
        reads_source = entry.assessment.requires_source
        if not ledger.fits(entry.costs, reads_source, memory_limit):
            reject(entry, "budget")
            return
        ledger.add(entry.costs, reads_source)
        priority += 1
        entry.selection = Selection(
            state="selected", reason=reason, requested=entry.requested, priority=priority
        )

    applicable: list[_Entry] = []
    for entry in entries:
        kind = entry.assessment.kind
        if kind == "satisfied":
            entry.selection = Selection(
                state="already_satisfied",
                reason=entry.assessment.reasons[0],
                requested=entry.requested,
                satisfied_by=entry.assessment.satisfied_by,
            )
        elif kind == "not_applicable":
            reject(entry, "not_applicable")
        else:
            applicable.append(entry)

    # 1. What was asked for and can be done.
    for entry in applicable:
        if entry.requested:
            try_select(entry, "requested", budgets.memory_bytes)

    # 2. The cheap analyses of the most use, then 3. the costly ones by use per
    # byte (specification 11.1).
    rest = [entry for entry in applicable if not entry.requested]
    cheap = sorted(
        (e for e in rest if e.costs is not None and CPU_ORDER.index(e.costs.cpu) <= 1),
        key=lambda e: (-(e.utility.score if e.utility else 0), e.order),
    )
    costly = sorted(
        (e for e in rest if e.costs is not None and CPU_ORDER.index(e.costs.cpu) > 1),
        key=lambda e: (
            -((e.utility.score if e.utility else 0) * 1_000_000 // max(1, e.costs.memory.max)),
            e.order,
        ),
    )
    limit = CPU_ORDER.index(budgets.automatic_max_cpu)
    reading_too_long = CPU_ORDER.index(cell_class(cells)) > limit
    automatic_pairs = 0
    for entry in [*cheap, *costly]:
        assert entry.costs is not None and entry.utility is not None
        if forced:
            try_select(entry, "forced", budgets.memory_bytes)
        elif not automatic:
            reject(entry, "not_requested")
        elif entry.utility.score < AUTOMATIC_MIN_UTILITY:
            reject(entry, "low_utility")
        elif CPU_ORDER.index(entry.costs.cpu) > limit:
            reject(entry, "cpu_class")
        elif entry.assessment.requires_source and (
            budgets.max_cells is not None and cells > budgets.max_cells
        ):
            # Only a reading of the source is limited by cells.
            reject(entry, "cells_budget")
        elif entry.assessment.requires_source and reading_too_long:
            reject(entry, "cpu_class")
        elif entry.partner is not None and automatic_pairs >= budgets.automatic_pairs:
            reject(entry, "pairs_budget")
        else:
            try_select(entry, "automatic", automatic_memory)
            if entry.partner is not None and entry.selection.state == "selected":  # type: ignore[union-attr]
                automatic_pairs += 1
    return ledger


def _beyond_automatic(
    selected: Sequence[Candidate], ledger: _Ledger, budgets: Budgets, cells: int
) -> list[str]:
    """The automatic limits that the selection exceeds, as codes (R1). What the
    planner picks by itself never exceeds them."""
    codes: list[str] = []
    if ledger.total().max > budgets.automatic_memory_bytes:
        codes.append("memory_over_automatic")
    over_cells = (
        ledger.reading and budgets.max_cells is not None and cells > budgets.max_cells
    )
    if over_cells:
        codes.append("cells_over_automatic")
    limit = CPU_ORDER.index(budgets.automatic_max_cpu)
    heavy = any(
        c.costs is not None and CPU_ORDER.index(c.costs.cpu) > limit for c in selected
    )
    long_reading = (
        ledger.reading and not over_cells and CPU_ORDER.index(cell_class(cells)) > limit
    )
    if heavy or long_reading:
        codes.append("cpu_over_automatic")
    return codes


def _candidate(entry: _Entry) -> Candidate:
    assert entry.selection is not None
    facts, assessment, analyzer = entry.facts, entry.assessment, entry.analyzer
    applicable = assessment.kind != "not_applicable"
    return Candidate(
        id=entry.id,
        analyzer=analyzer.id,
        analyzer_version=analyzer.version,
        dataset=facts.dataset,
        field=facts.field,
        display=(
            facts.display
            if entry.partner is None
            else f"{facts.display} and {entry.partner.display}"
        ),
        partner=None if entry.partner is None else entry.partner.field,
        exploration=entry.exploration,
        method=assessment.method,
        parameters=assessment.parameters,
        outputs=list(analyzer.outputs),
        applicability=Applicability(
            state="applicable" if applicable else "not_applicable",
            reasons=list(assessment.reasons) if not applicable else [],
        ),
        utility=entry.utility,
        costs=entry.costs,
        selection=entry.selection,
        execution=Execution(
            requires_source=assessment.kind == "applicable" and assessment.requires_source,
            available=analyzer.available,
            deterministic=analyzer.deterministic,
            reusable=analyzer.reusable,
        ),
    )


def _pair_entries(
    scan: ScanResult,
    analyzer: PearsonCorrelation,
    facts_list: Sequence[FieldFacts],
    requests: Sequence[AnalysisRequest],
    start: int,
) -> tuple[list[_Entry], list[ExploredDataset]]:
    """The candidates of the pairs of numeric columns: the best the exploration
    of each dataset found, then the pairs a request named that it did not list
    (REL-06). Reads the row sample of the Scan and nothing else."""
    # The second pass imports the planner, so it is imported late.
    from tabalyst.scanner.secondpass.replay import CellReader

    settings = analyzer.settings.pearson
    reader = CellReader(scan.config)
    # JSON writes its native numbers as text in the sample: a decimal reads them.
    lenient = scan.source.format != "csv"
    by_dataset: dict[str, list[FieldFacts]] = {}
    for facts in facts_list:
        by_dataset.setdefault(facts.dataset, []).append(facts)
    proposals: list[PairProposal] = []
    blocks: list[ExploredDataset] = []
    for dataset in scan.datasets:
        block, listed = explore_dataset(
            dataset, by_dataset.get(dataset.id, []), reader, settings, lenient
        )
        if block is not None:
            blocks.append(block)
        proposals.extend(listed)
    known = {(p.first.dataset, p.first.field, p.second.field) for p in proposals}
    datasets: dict[str, DatasetResult] = {dataset.id: dataset for dataset in scan.datasets}
    for request in requests:
        if request.analyzer != analyzer.id or request.field is None or request.partner is None:
            continue
        for dataset_id, members in by_dataset.items():
            if request.dataset not in (None, dataset_id):
                continue
            first = next((f for f in members if request.field in (f.field, f.display)), None)
            second = next((f for f in members if request.partner in (f.field, f.display)), None)
            if first is None or second is None:
                continue
            if members.index(first) > members.index(second):
                first, second = second, first
            if (dataset_id, first.field, second.field) in known:
                continue
            known.add((dataset_id, first.field, second.field))
            proposals.append(
                explicit_proposal(datasets[dataset_id], first, second, reader, settings, lenient)
            )
    entries: list[_Entry] = []
    for proposal in proposals:
        if proposal.reasons:
            assessment = Assessment("not_applicable", proposal.reasons)
        else:
            # Only a CSV file writes the cells of its sample as the reading does.
            assessment = analyzer.assess_pair(proposal.from_samples and not lenient)
        entry = _Entry(
            start + len(entries),
            analyzer,
            proposal.first,
            assessment,
            partner=proposal.second,
            exploration=proposal.exploration,
        )
        if assessment.kind == "applicable":
            entry.costs = analyzer.estimate_pair(proposal.first, proposal.second, assessment)
            entry.utility = analyzer.utility_pair(proposal.exploration)
        entries.append(entry)
    return entries, blocks


def plan_analyses(
    scan: ScanResult,
    *,
    requests: Sequence[AnalysisRequest] = (),
    automatic: bool = True,
    forced: bool = False,
    budgets: Budgets | None = None,
    registry: AnalyzerRegistry | None = None,
    deep: DeepSettings | None = None,
) -> AnalysisPlan:
    """Plan the analyses that could be added to a finished Scan.

    ``requests`` are chosen first when they fit the hard memory budget; with
    ``automatic`` the planner then adds the cheap, useful analyses by itself,
    within the automatic limits. ``forced`` (a second pass asked for as a whole)
    takes instead every applicable analysis the hard budget holds, whatever the
    automatic limits and the utility, which only orders them. Raises
    ``ConfigurationError`` for a request that names an unknown analyzer,
    dataset or field. ``deep`` holds the settings that parametrize the methods
    (the bins of a histogram). Reads the Scan only; nothing is run or written.
    """
    registry = default_registry() if registry is None else registry
    deep = DeepSettings() if deep is None else deep
    budgets = default_budgets(deep) if budgets is None else budgets
    _check_requests(requests, registry, scan)
    analyzers = [analyzer(deep) for analyzer in registry]
    facts_list = scan_facts(scan)

    entries: list[_Entry] = []
    matched = [0] * len(requests)
    explored: list[ExploredDataset] = []
    for analyzer in analyzers:
        if isinstance(analyzer, PearsonCorrelation):
            pairs, blocks = _pair_entries(scan, analyzer, facts_list, requests, len(entries))
            for entry in pairs:
                assert entry.partner is not None
                for index, request in enumerate(requests):
                    if request.analyzer == analyzer.id and _pair_matches(
                        request, entry.facts, entry.partner
                    ):
                        entry.requested = True
                        matched[index] += 1
            entries.extend(pairs)
            explored.extend(blocks)
            continue
        for facts in facts_list:
            if not analyzer.relevant(facts):
                continue
            assessment = analyzer.assess(facts)
            entry = _Entry(len(entries), analyzer, facts, assessment)
            for index, request in enumerate(requests):
                if _matches(request, facts, analyzer):
                    entry.requested = True
                    matched[index] += 1
            if assessment.kind == "applicable":
                entry.costs = analyzer.estimate(facts, assessment)
                entry.utility = analyzer.utility(facts, assessment)
            entries.append(entry)

    cells = _cells(scan)
    ledger = _decide(entries, budgets, automatic, forced, cells)

    candidates = [_candidate(entry) for entry in entries]
    selected = [c for c in candidates if c.selection.state == "selected"]
    reading = ledger.reading
    common = CommonCost(
        requires_source=reading,
        cells=cells if reading else None,
        memory_bytes=PARSER_RESERVE_BYTES if reading else 0,
        cpu=cell_class(cells) if reading else None,
    )
    plan = AnalysisPlan(
        utility_version=UTILITY_VERSION,
        cost_model_version=COST_MODEL_VERSION,
        plan_id="",
        base=plan_base(scan),
        objective=Objective(
            automatic=automatic,
            forced=forced,
            requested=[
                RequestedAnalysis(
                    analyzer=request.analyzer,
                    dataset=request.dataset,
                    field=request.field,
                    partner=request.partner,
                    candidates=matched[index],
                )
                for index, request in enumerate(requests)
            ],
        ),
        budgets=budgets,
        common=common,
        summary=Summary(
            candidates=len(candidates),
            selected=len(selected),
            already_satisfied=sum(c.selection.state == "already_satisfied" for c in candidates),
            rejected=sum(c.selection.state == "rejected" for c in candidates),
            second_pass_required=reading,
            executable=all(c.execution.available for c in selected),
            memory=ledger.total(),
            beyond_automatic=_beyond_automatic(selected, ledger, budgets, cells),
        ),
        relations=Relations(datasets=explored) if explored else None,
        candidates=candidates,
    )
    return plan.model_copy(update={"plan_id": plan_id(plan)})


def plan_id(plan: AnalysisPlan) -> str:
    """SHA-256 of the plan without its own ``plan_id``."""
    document = plan.model_dump(mode="json", exclude={"plan_id"})
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

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
from tabalyst.scanner.features import FEATURES
from tabalyst.scanner.identity import facts_sha256
from tabalyst.scanner.models import ScanResult
from tabalyst.scanner.planner.analyzer import (
    AnalysisRequest,
    Analyzer,
    Assessment,
    PairAnalyzer,
    PairProposal,
)
from tabalyst.scanner.planner.costmodel import (
    COST_MODEL_VERSION,
    DEFAULT_AUTOMATIC_MEMORY_BYTES,
    DEFAULT_MAX_CELLS,
    DEFAULT_MEMORY_BUDGET_BYTES,
    PARSER_RESERVE_BYTES,
    cell_class,
)
from tabalyst.scanner.planner.facts import (
    ROOT_FIELD,
    FieldFacts,
    root_facts,
    scan_facts,
)
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
    ExploredBlocks,
    Memory,
    Objective,
    PlanBase,
    Relations,
    RequestedAnalysis,
    Selection,
    State,
    StatsExploration,
    Summary,
    TableExploration,
    Utility,
)
from tabalyst.scanner.planner.registry import AnalyzerRegistry, default_registry
from tabalyst.scanner.planner.stratification import Stratify, advise_stratification

UTILITY_VERSION = 1
# The lowest utility the planner picks by itself (a forced plan ignores it).
AUTOMATIC_MIN_UTILITY = 45


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
        automatic_tables=deep.crosstab.automatic_tables,
        automatic_stats=deep.stats.automatic_stats,
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
    exploration: Exploration | TableExploration | StatsExploration | None = None
    # The feature of the second column of a table, and whether another feature
    # of the same two columns scored higher (REL-16).
    feature: str | None = None
    redundant: bool = False

    @property
    def id(self) -> str:
        field = self.facts.field
        if self.partner is not None:
            separator = (
                ">" if isinstance(self.analyzer, PairAnalyzer) and self.analyzer.directed else "+"
            )
            field = f"{field}{separator}{self.partner.field}"
        if self.feature is not None:
            field = f"{field}:{self.feature}"
        return f"{self.analyzer.id}:{self.facts.dataset}:{field}"

    @property
    def display(self) -> str:
        if self.partner is None:
            return self.facts.display
        names = f"{self.facts.display} and {self.partner.display}"
        return names if self.feature is None else f"{names} ({self.feature})"


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


def plan_base(scan: ScanResult, facts: str | None = None) -> PlanBase:
    """The identity of the Scan a plan stands on (design 19.5): a plan is only
    valid for the Scan whose base it carries. ``facts`` is the digest of the
    facts when the caller already computed it: it hashes the whole document."""
    return PlanBase(
        format_revision=scan.format_revision,
        engine_version=scan.engine.version,
        source_sha256=scan.source.sha256,
        config_sha256=scan.config_sha256,
        facts_sha256=facts if facts is not None else facts_sha256(scan),
    )


def _cells(scan: ScanResult) -> int:
    shape_cells = scan.source.shape.cells
    if shape_cells is not None:
        return shape_cells
    return sum(len(dataset.fields) * dataset.record_count for dataset in scan.datasets)


def _matches(request: AnalysisRequest, facts: FieldFacts, analyzer: Analyzer) -> bool:
    return (
        request.analyzer == analyzer.id
        and request.partner is None
        and request.dataset in (None, facts.dataset)
        and request.field in (None, facts.field, facts.display)
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
            if request.field != ROOT_FIELD and not any(
                request.field in (field.id, field.display)
                for dataset in scope
                for field in dataset.fields
            ):
                raise ConfigurationError(f"Unknown field {request.field!r}.")
        pairs = issubclass(registry[request.analyzer], PairAnalyzer)
        if request.feature is not None:
            if not (pairs and registry[request.analyzer].features):
                raise ConfigurationError(f"{request.analyzer!r} does not take a feature.")
            if request.feature not in FEATURES:
                raise ConfigurationError(f"Unknown feature {request.feature!r}.")
        if request.rules:
            if not (pairs and getattr(registry[request.analyzer], "features", False)):
                raise ConfigurationError(f"{request.analyzer!r} does not take rules.")
            if request.field is None or request.partner is None or request.feature is None:
                raise ConfigurationError("Rules need the category, the column and the feature.")
            for rule in request.rules:
                if len(rule) != 2 or not all(isinstance(label, str) and label for label in rule):
                    raise ConfigurationError(
                        "A rule is a category label and a class label, both given."
                    )
        if request.partner is not None:
            if not pairs:
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


def _columns(entry: _Entry) -> tuple[str, str, str, str]:
    """The two columns of a pair or a table, whatever its feature."""
    assert entry.partner is not None
    return (entry.facts.dataset, entry.analyzer.id, entry.facts.field, entry.partner.field)


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

    def is_cheap(entry: _Entry) -> bool:
        # A pair or a table is chosen within a count of its own, so it competes
        # by what the sample says of it, whatever the class of its CPU: a table of
        # patterns must not lose to a table of lengths for costing a little more.
        assert entry.costs is not None
        return entry.partner is not None or CPU_ORDER.index(entry.costs.cpu) <= 1

    cheap = sorted(
        (e for e in rest if e.costs is not None and is_cheap(e)),
        key=lambda e: (-(e.utility.score if e.utility else 0), e.order),
    )
    costly = sorted(
        (e for e in rest if e.costs is not None and not is_cheap(e)),
        key=lambda e: (
            -((e.utility.score if e.utility else 0) * 1_000_000 // max(1, e.costs.memory.max)),
            e.order,
        ),
    )
    limit = CPU_ORDER.index(budgets.automatic_max_cpu)
    reading_too_long = CPU_ORDER.index(cell_class(cells)) > limit
    chosen_pairs: dict[str, int] = {}
    # The pairs of columns of which a feature was chosen: no other feature of the
    # same two columns is (REL-16).
    covered: set[tuple[str, str, str, str]] = set()

    def automatic_choice(entry: _Entry) -> None:
        assert entry.costs is not None and entry.utility is not None
        analyzer = entry.analyzer
        # The candidate of a field of an analyzer that also has pairs is no pair.
        pair = (
            analyzer if isinstance(analyzer, PairAnalyzer) and entry.partner is not None else None
        )
        if entry.utility.score < AUTOMATIC_MIN_UTILITY:
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
        elif pair is not None and chosen_pairs.get(analyzer.id, 0) >= pair.automatic_limit(budgets):
            reject(entry, pair.budget_reason)
        else:
            try_select(entry, "automatic", automatic_memory)
            if pair is not None and entry.selection.state == "selected":  # type: ignore[union-attr]
                chosen_pairs[analyzer.id] = chosen_pairs.get(analyzer.id, 0) + 1
                covered.add(_columns(entry))

    # A feature that scored below another of the same two columns waits for it:
    # it is chosen only when that one was not (budget, CPU class), so a relation
    # is not lost for being told twice.
    deferred: list[_Entry] = []
    for entry in [*cheap, *costly]:
        assert entry.costs is not None and entry.utility is not None
        if forced:
            try_select(entry, "forced", budgets.memory_bytes)
        elif not automatic:
            reject(entry, "not_requested")
        elif entry.redundant:
            deferred.append(entry)
        else:
            automatic_choice(entry)
    for entry in deferred:
        if _columns(entry) in covered:
            reject(entry, "redundant_feature")
        else:
            automatic_choice(entry)
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
        display=entry.display,
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
    analyzer: PairAnalyzer,
    facts_list: Sequence[FieldFacts],
    requests: Sequence[AnalysisRequest],
    start: int,
) -> tuple[list[_Entry], ExploredBlocks]:
    """The candidates of the pairs of columns an analyzer proposes: the best its
    exploration of the row sample found, then the pairs a request named that it
    did not list (REL-06). Reads the row sample of the Scan and nothing else."""
    # The second pass imports the planner, so it is imported late.
    from tabalyst.scanner.secondpass.replay import CellReader

    reader = CellReader(scan.config)
    # JSON writes its native numbers as text in the sample: a decimal reads them.
    lenient = scan.source.format != "csv"
    proposals, blocks = analyzer.explore(scan, facts_list, requests, reader, lenient)
    entries: list[_Entry] = []
    for proposal in proposals:
        assessment = analyzer.assess_pair(proposal, lenient)
        entry = _Entry(
            start + len(entries),
            analyzer,
            proposal.first,
            assessment,
            partner=proposal.second,
            exploration=proposal.exploration,
            feature=proposal.feature,
            redundant=proposal.redundant,
        )
        if assessment.kind == "applicable":
            entry.costs = analyzer.estimate_pair(proposal, assessment)
            entry.utility = analyzer.utility_pair(proposal)
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
    stratify: Stratify | None = None,
) -> AnalysisPlan:
    """Plan the analyses that could be added to a finished Scan.

    ``requests`` are chosen first when they fit the hard memory budget; with
    ``automatic`` the planner then adds the cheap, useful analyses by itself,
    within the automatic limits. ``forced`` (a second pass asked for as a whole)
    takes instead every applicable analysis the hard budget holds, whatever the
    automatic limits and the utility, which only orders them. Raises
    ``ConfigurationError`` for a request that names an unknown analyzer,
    dataset or field. ``deep`` holds the settings that parametrize the methods
    (the bins of a histogram). ``stratify`` adds the advice on stratified
    sampling (design 20.14). Reads the Scan only; nothing is run or written.
    """
    registry = default_registry() if registry is None else registry
    deep = DeepSettings() if deep is None else deep
    budgets = default_budgets(deep) if budgets is None else budgets
    _check_requests(requests, registry, scan)
    analyzers = [analyzer(deep) for analyzer in registry]
    facts_list = scan_facts(scan)
    roots = root_facts(scan)

    entries: list[_Entry] = []
    matched = [0] * len(requests)
    explored: dict[str, list] = {}  # type: ignore[type-arg]
    for analyzer in analyzers:
        if isinstance(analyzer, PairAnalyzer):
            pairs, blocks = _pair_entries(scan, analyzer, facts_list, requests, len(entries))
            for entry in pairs:
                assert entry.partner is not None
                proposal = PairProposal(
                    entry.facts, entry.partner, entry.exploration, feature=entry.feature
                )
                for index, request in enumerate(requests):
                    if request.analyzer == analyzer.id and analyzer.matches(request, proposal):
                        entry.requested = True
                        matched[index] += 1
            entries.extend(pairs)
            explored.setdefault(analyzer.relations, []).extend(blocks)
            if not analyzer.per_field:
                continue
        for facts in (*facts_list, *roots) if analyzer.roots else facts_list:
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
                    feature=request.feature,
                    rules=len(request.rules),
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
        relations=(
            Relations(
                datasets=explored.get("datasets", []),
                tables=explored.get("tables", []),
                stats=explored.get("stats", []),
                orders=explored.get("orders", []),
            )
            if any(explored.values())
            else None
        ),
        candidates=candidates,
    )
    if stratify is not None:
        return with_stratification(plan, scan, stratify, facts_list)
    return plan.model_copy(update={"plan_id": plan_id(plan)})


def with_stratification(
    plan: AnalysisPlan,
    scan: ScanResult,
    stratify: Stratify,
    facts_list: Sequence[FieldFacts] | None = None,
) -> AnalysisPlan:
    """The plan with the advice on stratification added and its ``plan_id``
    recomputed. The advice takes no part in the choice of the analyses."""
    advice = advise_stratification(scan, stratify, facts_list)
    plan = plan.model_copy(update={"stratification": advice})
    return plan.model_copy(update={"plan_id": plan_id(plan)})


def plan_id(plan: AnalysisPlan) -> str:
    """SHA-256 of the plan without its own ``plan_id``."""
    document = plan.model_dump(mode="json", exclude={"plan_id"})
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

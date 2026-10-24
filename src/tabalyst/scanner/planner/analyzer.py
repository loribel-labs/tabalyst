# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Interface of an analyzer and the sizes it shares (design 20.5, lot 6b).

An analyzer describes what it could add to a Scan: when it applies, what is
already answered, what it would cost, and how useful it is. It does not run
anything here; the second pass (lot 7a) gives the available ones an executor.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

from tabalyst.config import DeepSettings
from tabalyst.scanner.planner.costmodel import (
    CLASS_NS,
    INT_OBJECT_BYTES,
    SET_SLOT_BYTES,
    STR_OBJECT_BYTES,
    TABLE_ENTRY_BYTES,
    cpu_class_for,
)
from tabalyst.scanner.planner.facts import FieldFacts
from tabalyst.scanner.planner.models import (
    AssessmentKind,
    Budgets,
    Costs,
    CpuClass,
    Exploration,
    ExploredBlocks,
    Memory,
    State,
    StatsExploration,
    TableExploration,
    Utility,
)

if TYPE_CHECKING:
    # The second pass imports the planner: these are only types here.
    from tabalyst.scanner.models import ScanResult
    from tabalyst.scanner.secondpass.replay import CellReader

# Longest domain of integers counted by a dense array, and bins otherwise.
DENSE_DOMAIN_MAX = 65_536
# A field with at most this many distinct values has a table of frequencies
# of a size the planner accepts without being an identifier.
LOW_CARDINALITY_MAX = 1_000
# Longest value that an exact set keeps inline or encodes compactly.
COMPACT_MAX_LENGTH = 64
LENGTH_DOMAIN_FALLBACK = 1_024


@dataclass(frozen=True, slots=True)
class Assessment:
    """What an analyzer finds when it looks at a field.

    ``satisfied_by`` locates the fact of the Scan that already answers it.
    ``parameters`` are the method's settings, written in the plan.
    """

    kind: AssessmentKind
    reasons: tuple[str, ...] = ()
    method: str | None = None
    parameters: dict[str, int | str] = field(default_factory=dict)
    satisfied_by: str | None = None
    requires_source: bool = True


def memory(minimum: int, expected: int | None = None, maximum: int | None = None) -> Memory:
    """A ``Memory`` of one scenario, or of three."""
    expected = minimum if expected is None else expected
    maximum = expected if maximum is None else maximum
    return Memory(min=minimum, expected=expected, max=maximum)


def text_length(facts: FieldFacts) -> tuple[int, int, int]:
    """Characters of a stored text: the shortest, the mean and the longest, from
    the exact length histogram. Without it the longest value an exact set holds
    (``COMPACT_MAX_LENGTH``) bounds it."""
    if facts.min_length is None or facts.mean_length is None or facts.max_length is None:
        return (1, COMPACT_MAX_LENGTH // 2, COMPACT_MAX_LENGTH)
    return (facts.min_length, round(facts.mean_length), facts.max_length)


def set_entry(key: str, length: int) -> tuple[int, int, int]:
    """Bytes of one entry of a set of ``key`` (``integer`` or ``text``) in the
    three scenarios: the key object and its slot of the hash table."""
    obj = INT_OBJECT_BYTES if key == "integer" else STR_OBJECT_BYTES + length
    low, expected, high = SET_SLOT_BYTES
    return (obj + low, obj + expected, obj + high)


def table_entry(length: int) -> int:
    """Bytes of one entry of a table of counts with a key of ``length``."""
    return TABLE_ENTRY_BYTES + length


def costs(work: CpuClass | int, states: list[State]) -> Costs:
    """The costs of an analysis: its states added scenario by scenario, and the
    nanoseconds it adds to each cell (a CPU class stands for the upper limit of
    its range)."""
    if isinstance(work, int):
        nanoseconds, cpu = work, cpu_class_for(work)
    else:
        nanoseconds, cpu = CLASS_NS[work], work
    return Costs(
        memory=Memory(
            min=sum(state.memory.min for state in states),
            expected=sum(state.memory.expected for state in states),
            max=sum(state.memory.max for state in states),
        ),
        cpu=cpu,
        cell_ns=nanoseconds,
        states=states,
    )


class Analyzer(ABC):
    """One kind of analysis the planner can propose for a field.

    ``available`` is false until an executor exists; the planner chooses on
    merit and the plan says whether its selection can run. ``deterministic``
    and ``reusable`` answer PLAN-02: the result does not depend on the run, and
    one computed for the same base and parameters can be reused. ``settings``
    are the ``deep`` settings, which parametrize the methods that have some.
    """

    id: ClassVar[str]
    version: ClassVar[int] = 1
    outputs: ClassVar[tuple[str, ...]]
    available: ClassVar[bool] = False
    deterministic: ClassVar[bool] = True
    reusable: ClassVar[bool] = True
    # Whether the analyzer also concerns the root of the records of a JSON
    # source, which the Scan holds as no field (``facts.root_facts``).
    roots: ClassVar[bool] = False
    # Whether the analyzer reads the whole rows of a CSV file, which the Scan holds as no
    # field either: it is offered the rows (facts.rows_facts), named $ like the root.
    rows: ClassVar[bool] = False

    def __init__(self, settings: DeepSettings | None = None) -> None:
        self.settings = DeepSettings() if settings is None else settings

    @abstractmethod
    def relevant(self, facts: FieldFacts) -> bool:
        """Whether the analyzer concerns this kind of field at all. A field it
        does not concern has no candidate, which keeps the plan readable."""

    def gives_distinct(self, facts: FieldFacts) -> bool:
        """Whether, once run, the analysis gives the exact distinct count of the
        analytical values that the uniqueness of an identifier needs. The planner
        chooses the count of the copies of rows only when one such count is there
        or planned (UID-011, design 20.42)."""
        return False

    @abstractmethod
    def assess(self, facts: FieldFacts) -> Assessment:
        """Whether it applies, is already answered, or does not apply and why."""

    @abstractmethod
    def estimate(self, facts: FieldFacts, assessment: Assessment) -> Costs:
        """Costs of an applicable analysis."""

    @abstractmethod
    def utility(self, facts: FieldFacts, assessment: Assessment) -> Utility:
        """Usefulness of an applicable analysis, with its reasons."""


@dataclass(frozen=True, slots=True)
class AnalysisRequest:
    """An analysis asked for explicitly. ``dataset`` and ``field`` (an id or a
    display path) narrow it; absent, it concerns every dataset or field. For an
    analysis of pairs, ``field`` and ``partner`` name one pair, which may be
    absent from what the exploration proposes; ``field`` alone asks for the
    proposed pairs that use it. For a table of a category against a feature
    (design 20.13), ``field`` is the category, ``partner`` the column and
    ``feature`` the feature (``pattern``, ``length``, ``prefix`` or ``value``).
    ``rules`` (a table only, which then needs ``field``, ``partner`` and
    ``feature``) are rules to check against it, each the label of a category and
    the label of the class its rows should take (design 20.22)."""

    analyzer: str
    dataset: str | None = None
    field: str | None = None
    partner: str | None = None
    feature: str | None = None
    rules: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class PairProposal:
    """A pair the planner puts in the plan: the two fields, what the sample says
    of them and, when the pair cannot be analyzed, why. ``feature`` names the
    feature of the second column in a table, and ``redundant`` says that another
    feature of the same pair of columns scored higher (REL-16)."""

    first: FieldFacts
    second: FieldFacts
    exploration: Exploration | TableExploration | StatsExploration | None
    reasons: tuple[str, ...] = ()
    # Both columns are fully in a complete sample: the Scan alone answers.
    from_samples: bool = False
    feature: str | None = None
    redundant: bool = False
    # Rules a user gave for the table, sorted and without repeats.
    rules: tuple[tuple[str, str], ...] = ()


class PairAnalyzer(Analyzer):
    """An analysis of two columns of a dataset (lots 8a and 8b).

    It has no candidate per field: the planner asks ``explore`` for the pairs
    the row sample proposes and the ones a request names, then ``assess_pair``,
    ``estimate_pair`` and ``utility_pair`` for each. ``relations`` is the member
    of the plan's ``relations`` block that holds the exploration.
    """

    relations: ClassVar[str]
    # Whether a request may name a feature.
    features: ClassVar[bool] = False
    # Whether the two columns have an order that a request must respect.
    directed: ClassVar[bool] = False
    # The reason the plan gives to the pairs beyond the count it picks by itself.
    budget_reason: ClassVar[str] = "pairs_budget"
    # Whether the analyzer also has a candidate for each field (a repeated value
    # of one column, a repeated combination of two).
    per_field: ClassVar[bool] = False

    def relevant(self, facts: FieldFacts) -> bool:
        return False

    def assess(self, facts: FieldFacts) -> Assessment:
        return Assessment("not_applicable", ("not_numeric",))

    def estimate(self, facts: FieldFacts, assessment: Assessment) -> Costs:
        raise NotImplementedError("a pair is estimated as a pair")

    def utility(self, facts: FieldFacts, assessment: Assessment) -> Utility:
        raise NotImplementedError("a pair is rated as a pair")

    @abstractmethod
    def automatic_limit(self, budgets: Budgets) -> int:
        """How many of its pairs the planner picks by itself."""

    @abstractmethod
    def explore(
        self,
        scan: ScanResult,
        facts: Sequence[FieldFacts],
        requests: Sequence[AnalysisRequest],
        reader: CellReader,
        lenient: bool,
    ) -> tuple[list[PairProposal], ExploredBlocks]:
        """The pairs to list: the best the exploration of each dataset found,
        then those a request named that it did not list (REL-06), and the blocks
        that describe the exploration. Reads the row sample of the Scan only."""

    @abstractmethod
    def assess_pair(self, proposal: PairProposal, lenient: bool) -> Assessment:
        """Whether a proposed pair applies and how."""

    @abstractmethod
    def estimate_pair(self, proposal: PairProposal, assessment: Assessment) -> Costs:
        """Costs of an applicable pair."""

    @abstractmethod
    def utility_pair(self, proposal: PairProposal) -> Utility:
        """Usefulness of an applicable pair, with its reasons."""

    @abstractmethod
    def matches(self, request: AnalysisRequest, proposal: PairProposal) -> bool:
        """Whether a request for this analyzer concerns the pair."""

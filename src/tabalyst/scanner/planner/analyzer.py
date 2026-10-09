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
from dataclasses import dataclass, field
from typing import ClassVar

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
    Costs,
    CpuClass,
    Memory,
    State,
    Utility,
)

# Longest domain of integers counted by a dense array, and bins otherwise.
DENSE_DOMAIN_MAX = 65_536
BIN_COUNT = 100
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
    one computed for the same base and parameters can be reused.
    """

    id: ClassVar[str]
    version: ClassVar[int] = 1
    outputs: ClassVar[tuple[str, ...]]
    available: ClassVar[bool] = False
    deterministic: ClassVar[bool] = True
    reusable: ClassVar[bool] = True

    @abstractmethod
    def relevant(self, facts: FieldFacts) -> bool:
        """Whether the analyzer concerns this kind of field at all. A field it
        does not concern has no candidate, which keeps the plan readable."""

    @abstractmethod
    def assess(self, facts: FieldFacts) -> Assessment:
        """Whether it applies, is already answered, or does not apply and why."""

    @abstractmethod
    def estimate(self, facts: FieldFacts, assessment: Assessment) -> Costs:
        """Costs of an applicable analysis."""

    @abstractmethod
    def utility(self, facts: FieldFacts, assessment: Assessment) -> Utility:
        """Usefulness of an applicable analysis, with its reasons."""

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Rules shared by the analyzers: what blocks them and what looks like an id."""

from __future__ import annotations

from tabalyst.scanner.planner.analyzer import Assessment, memory
from tabalyst.scanner.planner.costmodel import (
    MEASURE_FEW_DISTINCT,
    MEASURE_MEMO_ENTRIES,
    REPLAY_ENTRY_BYTES,
    REPLAY_MEMO_ENTRIES,
    RESULT_BYTES,
)
from tabalyst.scanner.planner.facts import FieldFacts
from tabalyst.scanner.planner.identifiers import (  # noqa: F401 - re-exported for the analyzers
    IDENTIFIER_TOKENS,
    identifier_like,
    name_suggests_identifier,
    uniqueness,
)
from tabalyst.scanner.planner.models import State


def blocked(facts: FieldFacts) -> Assessment | None:
    """The assessment that stops every analysis of a field, or ``None``: no
    value, or values that exposure keeps out of the document."""
    if facts.values == 0:
        return Assessment("not_applicable", ("no_values",))
    if facts.withheld:
        return Assessment("not_applicable", ("sensitive_exposure",))
    return None


def distinct_band(facts: FieldFacts) -> str:
    """How many distinct values a field has, as the cost of an analysis that
    handles each distinct string of a batch follows it: ``few`` (up to
    ``MEASURE_FEW_DISTINCT``), ``mid`` (up to the strings a route remembers) or
    ``wide``. A field whose count was stopped is taken at its estimate, or as
    wide."""
    distinct = facts.distinct
    if distinct is None:
        known = facts.distinct_estimate or facts.distinct_lower_bound
        distinct = None if known is None else int(known)
    if distinct is None or distinct > MEASURE_MEMO_ENTRIES:
        return "wide"
    return "few" if distinct <= MEASURE_FEW_DISTINCT else "mid"


def result_state(analyzer: str, facts: FieldFacts) -> State:
    """The small result object every analysis keeps, never shared."""
    return State(key=f"result:{analyzer}:{facts.where}", memory=memory(RESULT_BYTES))


def replay_state(
    facts: FieldFacts,
    entries: int = REPLAY_MEMO_ENTRIES,
    entry_bytes: int = REPLAY_ENTRY_BYTES,
) -> State:
    """What reading the strings of a field costs the second pass: the cells of
    the raw strings it remembers. Shared by the analyses of the field, at the
    largest of their sizes."""
    size = entries * entry_bytes
    return State(key=f"replay:{facts.where}", memory=memory(0, size // 4, size))

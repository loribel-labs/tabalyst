# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""What looks like an identifier, for the analyzers and the explorations of pairs."""

from __future__ import annotations

import re

from tabalyst.scanner.planner.facts import FieldFacts

# Name tokens that suggest an identifier. Only a secondary hint (specification
# 11.2): a name never decides alone.
IDENTIFIER_TOKENS = frozenset(
    {"id", "uid", "uuid", "guid", "key", "code", "ref", "reference", "no", "num", "number"}
)
_TOKENS = re.compile(r"[^0-9a-z]+")


def name_suggests_identifier(name: str) -> bool:
    """Whether a token of the field name is one of ``IDENTIFIER_TOKENS``."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    return any(token in IDENTIFIER_TOKENS for token in _TOKENS.split(spaced.lower()))


def uniqueness(facts: FieldFacts) -> float | None:
    """Share of the values that are distinct, from the exact count, the KMV
    estimate or the proven lower bound, in that order; ``None`` if unknown."""
    if facts.values == 0:
        return None
    for known in (facts.distinct, facts.distinct_estimate, facts.distinct_lower_bound):
        if known is not None:
            return min(1.0, known / facts.values)
    return None


def identifier_like(facts: FieldFacts) -> bool:
    """Almost unique values under a name that suggests an identifier."""
    share = uniqueness(facts)
    return share is not None and share >= 0.9 and name_suggests_identifier(facts.name)

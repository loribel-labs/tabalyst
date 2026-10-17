# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Catalogue of the active families and types of the classification (L0 foundation).

A typed Python module, not a user format (ADR catalogue in Python). Only active
entries are listed: a type of the specification that no rule produces yet is not
reserved here. Every change of an entry increases ``CATALOGUE_VERSION``.
"""

from __future__ import annotations

from dataclasses import dataclass

CATALOGUE_VERSION = 4
# Names of the versions ``classification_versions()`` returns, in order:
# ``names`` is ``names.NAME_RULES_VERSION``, the registry of the name rules.
VERSION_NAMES = ("catalogue", "names")


@dataclass(frozen=True, slots=True)
class Family:
    """A family of types with its stable code."""

    code: str
    types: tuple[str, ...]


FAMILIES = (
    Family("identifier", ("id", "unique_id")),
    Family("categorical", ("enum", "boolean", "constant")),
    Family("numeric", ("integer", "number", "currency", "percentage", "quantity")),
    Family("temporal", ("date", "datetime", "time")),
    Family("contact", ("email", "phone")),
    Family("geographic", ("postal_code",)),
    Family("web_network", ("url", "ip_address", "uuid")),
    # ``text`` alone is the Text of a column whose median length is not known.
    Family(
        "text",
        (
            "text_very_short",
            "text_short",
            "text_medium",
            "text_long",
            "text_very_long",
            "text",
        ),
    ),
    Family("other", ("mixed", "empty", "unknown")),
)

# The codes of the secondary properties (contract 3.4). A lot adds the traits it
# emits; none is emitted before the rule that decides it exists.
TRAITS = (
    "single_pattern",
    "multiple_patterns",
    "constant",
    "high_cardinality",
    "observed_unique",
    "first_column",
    "fixed_length",
)

_PAIRS = frozenset((family.code, code) for family in FAMILIES for code in family.types)


def is_catalogued(family: str, type_: str) -> bool:
    """Whether the pair is an active entry of the catalogue."""
    return (family, type_) in _PAIRS

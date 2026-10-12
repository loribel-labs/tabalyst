# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Ambiguous numbers read by the evidence of their column (design 20.27, O56).

One rule, written once: the first pass decides at the finalization of a field
and writes its decision in the Scan; every later reading of the field (second
pass, smart sample, exploration of the row sample) applies that decision and
never decides again, so they all count the numbers the Scan counted.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from tabalyst.scanner.models import DetectorComplete, FieldResult

if TYPE_CHECKING:
    # The detectors import this module through their registry.
    from tabalyst.scanner.detectors.base import Classification

EVIDENCE = "evidence"


def single_reading(evidence: Mapping[str, int], minimum: int = 1) -> str | None:
    """The only reading that at least ``minimum`` unambiguous values prove while
    no value proves another, else ``None``: with two readings the column is
    mixed, and with fewer than ``minimum`` the proof is too thin."""
    for name, count in evidence.items():
        if count >= minimum and not any(
            other for key, other in evidence.items() if key != name
        ):
            return name
    return None


@dataclass(frozen=True, slots=True)
class NumberRule:
    """The settings of the rule for one detector of numbers: ``infer`` turns it
    on, ``minimum`` is the fewest values that must prove a convention, and a
    convention given by the configuration (``ambiguous_convention``) always wins,
    so the evidence then decides nothing."""

    infer: bool
    minimum: int
    configured: str | None
    both: bool

    @classmethod
    def of(cls, settings: Mapping[str, object]) -> NumberRule:
        conventions = settings.get("conventions", ("dot", "comma"))
        configured = settings.get("ambiguous_convention")
        minimum = settings.get("min_evidence", 3)
        return cls(
            infer=bool(settings.get("infer_convention", True)),
            minimum=minimum if isinstance(minimum, int) else 3,
            configured=configured if isinstance(configured, str) else None,
            both=isinstance(conventions, (list, tuple))
            and {"dot", "comma"} <= set(conventions),
        )

    @property
    def active(self) -> bool:
        """Whether the evidence can decide: a value is only ambiguous when both
        conventions are enabled, and the configuration did not decide."""
        return self.infer and self.both and self.configured is None

    def convention(self, evidence: Mapping[str, int]) -> str | None:
        """The convention the unambiguous values of a column prove, if any."""
        if not self.active:
            return None
        return single_reading(
            {name: evidence.get(name, 0) for name in ("comma", "dot")}, self.minimum
        )


def ambiguous_thousands(text: str) -> int:
    """The integer N of an ambiguous number (``1,234``, ``-12,500``): the only
    ambiguous form is one or three digits, a comma and three digits, so its two
    readings are N (``dot``, thousands) and N / 1000 (``comma``, decimal)."""
    return int(text.replace(",", ""))


def dotted_thousands(found: Classification) -> int | None:
    """The integer N of a strict decimal that the ``comma`` convention reads as a
    thousands group (``1.234``, ``-12.500``), ``None`` for any other number. The
    number detector marks it as evidence of no convention."""
    if found.format == "0.0" and found.convention is None:
        value = found.value
        if isinstance(value, Decimal):
            return int(value.scaleb(3))
    return None


def holds_native_numbers(field: FieldResult) -> bool:
    """Whether a field holds numbers of the source's own type (JSON, Excel).
    They are numbers already: no convention applies to them."""
    return bool(field.native_types.get("integer") or field.native_types.get("number"))


def scan_convention(field: FieldResult) -> str | None:
    """The convention the Scan read the ambiguous numbers of a field in by the
    evidence of the column (``details.ambiguity.resolution`` of ``number`` with
    ``source`` ``evidence``), ``None`` when it read none of them that way."""
    for result in field.detectors:
        if result.id != "number" or not isinstance(result, DetectorComplete):
            continue
        ambiguity = result.details.get("ambiguity")
        if not isinstance(ambiguity, dict):
            return None
        resolution = ambiguity.get("resolution")
        if isinstance(resolution, dict) and resolution.get("source") == EVIDENCE:
            convention = resolution.get("convention")
            return convention if convention in ("dot", "comma") else None
        return None
    return None

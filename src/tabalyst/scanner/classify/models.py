# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Models of the classification of a field: family, type and what decided them.

Serialized as ``fields[].classification`` of the Scan (contract
``docs/dev/report/summary-table.md`` 3.1). No score and no percentage of
confidence: the evidence and the state say how sure the result is.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from tabalyst.scanner.classify.catalog import is_catalogued


class ClassifyModel(BaseModel):
    """Same rules as the other Scan models; defined here because the Scan models
    import this module."""

    model_config = ConfigDict(extra="forbid", frozen=True)


Basis = Literal["declared", "inferred", "fallback"]
State = Literal["established", "candidate", "undetermined"]
EvidenceSource = Literal[
    "detector", "technical_type", "measure", "name_rule", "position"
]
EvidenceRole = Literal["supports", "contradicts", "context"]
ScopePopulation = Literal[
    "positions", "present_values", "eligible", "tested", "records"
]
ScopeAccuracy = Literal["exact", "lower_bound", "sample", "estimated"]


class ClassificationScope(ClassifyModel):
    """What a fact covers: ``of`` is the size of its population, ``null`` when
    unknown; ``partial`` says the fact covers only part of that population (a
    limited measure, an adaptive detector)."""

    population: ScopePopulation
    of: int | None
    partial: bool
    accuracy: ScopeAccuracy


class ClassificationEvidence(ClassifyModel):
    """A fact that supports, contradicts or frames the classification: a
    detector id, a measure name (``string_lengths.median_length``), the
    technical type or a name rule id."""

    source: EvidenceSource
    id: str
    role: EvidenceRole
    scope: ClassificationScope


class ClassificationAlternative(ClassifyModel):
    """A candidate that was not retained, with the reason. Never a conclusion."""

    family: str
    type: str
    reason: str


class Classification(ClassifyModel):
    """The family and type of a field. ``basis`` says how it was decided,
    ``state`` how firmly; ``rule_version`` is the version of the catalogue that
    decided (see ``classification_versions``)."""

    family: str
    type: str
    basis: Basis
    state: State
    traits: list[str]
    evidence: list[ClassificationEvidence]
    alternatives: list[ClassificationAlternative]
    rule_version: int

    @model_validator(mode="after")
    def known_pair(self) -> Classification:
        if not is_catalogued(self.family, self.type):
            raise ValueError(
                f"{self.family}/{self.type} is not in the classification catalogue"
            )
        return self

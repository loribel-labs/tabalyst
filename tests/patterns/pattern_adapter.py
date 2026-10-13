# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Where the reference tests meet the engine: the one place to bind when the
hierarchical discovery (lot B4) and its validation (lot B5) exist.

Each function turns a field of the corpus into the shapes of ``pattern_tree``.
Until it is bound it raises ``NotImplementedError``; the tests that call it are
skipped by the gate of ``conftest.py`` meanwhile.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from pattern_corpus import Field, Variants
from pattern_tree import Declared, SeenField

# The outcomes of a value at validation (REC-006); ``invalid`` is reserved and
# never given by the inference.
Outcome = Literal["known", "new_variant", "unknown_structure", "atypical", "invalid"]


@dataclass(frozen=True)
class Validation:
    """The outcome of each value of a file validated against a discovery."""

    outcomes: Mapping[str, Outcome]


def discover(field: Field) -> SeenField | None:
    """The tree the discovery publishes for ``field``, reduced to sets of values;
    ``None`` when the generic discovery does not apply (a masked field, FR-022).

    Binding (lot B4): build a scan of the field's pairs, run the discovery and
    map each family, node and table to the values its signature accepts.
    """
    raise NotImplementedError("bind the hierarchical discovery (lot B4)")


def declared_keys(field: Field) -> Declared:
    """The keys the detector of ``field`` declares (algorithm, section 4), as the
    Scan publishes them, masked field or not (DEC-027)."""
    raise NotImplementedError("bind the declared keys of the detectors (lot B4)")


def validate(variants: Variants) -> Validation:
    """The outcome of every value of ``variants.file`` once the discovery has
    read ``variants.sample`` (FR-013, FR-015)."""
    raise NotImplementedError("bind the hierarchical validation (lot B5)")


def validate_file(field: Field) -> Validation:
    """The outcome of every value of ``field.file`` once the discovery has read
    ``field.pairs`` (RC-14)."""
    raise NotImplementedError("bind the hierarchical validation (lot B5)")

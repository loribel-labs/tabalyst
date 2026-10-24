# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Identifier uniqueness: separate ID repetitions explained by copied rows from residual ones."""

from tabalyst.identifier_uniqueness.models import (
    RULE_VERSION,
    DedupReportRef,
    DistinctEvidence,
    DuplicateEvidence,
    IdentifierUniqueness,
    RejectedProof,
    UniquenessFacts,
)
from tabalyst.identifier_uniqueness.rule import assess_identifier_uniqueness

__all__ = [
    "RULE_VERSION",
    "DedupReportRef",
    "DistinctEvidence",
    "DuplicateEvidence",
    "IdentifierUniqueness",
    "RejectedProof",
    "UniquenessFacts",
    "assess_identifier_uniqueness",
]

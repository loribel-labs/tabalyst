# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Classification of the fields of a Scan into a family and a type.

Contract: ``docs/dev/report/summary-table.md`` section 3.
"""

from tabalyst.scanner.classify.models import Classification
from tabalyst.scanner.classify.rules import (
    PENDING_CLASSIFICATION,
    ClassifyContext,
    classification_versions,
    classify_field,
    version_record,
)

__all__ = [
    "PENDING_CLASSIFICATION",
    "Classification",
    "ClassifyContext",
    "classification_versions",
    "classify_field",
    "version_record",
]

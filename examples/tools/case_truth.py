# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The truth of a case, read from the change log of a Generate run.

The log has one line per changed cell, with the 1-based ``row_number`` of the file (the header is
row 1) and the ``class`` of the operation. The truth is, per class, the sorted 0-based data rows
that carry it. Shared by the cases of ``examples/cases/``.
"""

import collections
import csv
from pathlib import Path


def truth_from_changes(changes: Path) -> dict[str, list[int]]:
    """Per class, the sorted 0-based data rows the generation changed."""
    rows: dict[str, set[int]] = collections.defaultdict(set)
    with changes.open(newline="", encoding="utf-8") as handle:
        for change in csv.DictReader(handle):
            rows[change["class"]].add(int(change["row_number"]) - 2)
    return {name: sorted(indexes) for name, indexes in rows.items()}

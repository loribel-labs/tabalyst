# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Notices for command-line options that a source cannot use.

``--delimiter`` and ``--encoding`` read CSV files, ``--collection`` and
``--all-collections`` choose among the collections of a JSON file or the tables
of a workbook. On another kind of source they have nothing to act on: they are
ignored, and the user is told so instead of believing they applied.
"""

from collections.abc import Sequence
from pathlib import Path

from tabalyst.scanner.identity import source_format_of

_ONE_DATASET = {
    "csv": "a CSV file holds one table",
    "jsonl": "a JSONL file holds one dataset, its lines",
}


def ignored_options(
    source: Path,
    *,
    delimiter: str | None = None,
    encoding: str | None = None,
    collections: Sequence[str] | None = None,
    all_collections: bool = False,
) -> list[str]:
    """Sentences for the options given that ``source`` does not use."""
    source_format = source_format_of(source)
    notices: list[str] = []
    if source_format != "csv":
        names = [
            name
            for name, value in (("--delimiter", delimiter), ("--encoding", encoding))
            if value is not None
        ]
        if names:
            verb = "is" if len(names) == 1 else "are"
            notices.append(
                f"{' and '.join(names)} {verb} ignored: {source.name} is not a CSV file."
            )
    reason = _ONE_DATASET.get(source_format)
    if reason is not None:
        if collections:
            notices.append(f"--collection is ignored: {reason}.")
        if all_collections:
            notices.append(
                f"--all-collections has no effect: {reason}, reported as usual."
            )
    return notices

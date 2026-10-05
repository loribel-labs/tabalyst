# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Streaming CSV output adapted from dataset_factory.exporters.csv."""

import csv
from collections.abc import Iterable
from pathlib import Path


def write_csv(
    path: Path,
    fieldnames: list[str],
    rows: Iterable[dict[str, str]],
    *,
    delimiter: str = ",",
) -> int:
    """Write a staged CSV using stable UTF-8/LF and strict field names."""
    count = 0
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=fieldnames,
            extrasaction="raise",
            lineterminator="\n",
            delimiter=delimiter,
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            count += 1
        stream.flush()
    return count

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Streaming CSV output adapted from dataset_factory.exporters.csv."""

import csv
from collections.abc import Callable, Iterable
from pathlib import Path


def write_csv(
    path: Path,
    fieldnames: list[str],
    rows: Iterable[dict[str, str]],
    *,
    delimiter: str = ",",
    total: int = 0,
    on_rows: Callable[[int], None] | None = None,
) -> int:
    """Write a staged CSV using stable UTF-8/LF and strict field names.

    `on_rows` receives the rows written, at 0, about 200 times for `total`
    expected rows, and at the end.
    """
    count = 0
    report_every = max(1, total // 200)
    if on_rows is not None:
        on_rows(0)
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
            if on_rows is not None and count % report_every == 0:
                on_rows(count)
        stream.flush()
    if on_rows is not None:
        on_rows(count)
    return count

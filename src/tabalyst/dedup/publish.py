# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Publication of the staged CSV outputs of a source (design dedup 11.5, CSV part)."""

import os
from pathlib import Path

from tabalyst.dedup.failures import DedupReportError
from tabalyst.dedup.writer import StagedOutputs


def publish_csv(staged: StagedOutputs) -> tuple[Path, ...]:
    """Move the staged files to their managed names, one by one, with ``os.replace``.

    Returns the published paths. If a replacement fails, the files this call had
    already published and the staged files that remain are deleted, and
    ``DedupReportError`` (``output_unwritable``) is raised. Making that failure
    recoverable across a crash needs the recovery report of lot 7; until then a
    crash between two replacements can leave a partial set.
    """
    published: list[Path] = []
    try:
        for output in staged.files:
            os.replace(output.temporary, output.final)
            published.append(output.final)
    except OSError as exc:
        for path in published:
            path.unlink(missing_ok=True)
        staged.discard()
        raise DedupReportError(
            "An output file cannot be published.", reason="output_unwritable"
        ) from exc
    return tuple(published)

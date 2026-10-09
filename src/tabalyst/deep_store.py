# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Writing of the second-pass document beside its Scan, for the command that
asks for the second pass and for Report (design 20.4)."""

from __future__ import annotations

from pathlib import Path

from tabalyst.batch import write_text_atomic
from tabalyst.errors import ReportError, TabalystError
from tabalyst.projects._locks import workspace_writer
from tabalyst.projects.location import StorageLocation
from tabalyst.scanner.planner import Confirmation
from tabalyst.scanner.secondpass import DeepResult, SecondPassOutcome, deep_document


class ConfirmationRequired(TabalystError):
    """The second pass exceeds a limit that a run needs confirming (rule R1) and
    no confirmation was given. Nothing was started. ``confirmation`` holds the
    estimate and the reasons."""

    def __init__(self, confirmation: Confirmation) -> None:
        super().__init__(
            "The second pass needs a confirmation before it starts "
            f"({', '.join(confirmation.reasons)}). Nothing was started."
        )
        self.confirmation = confirmation


def write_deep(
    deep_path: Path,
    outcome: SecondPassOutcome,
    previous: DeepResult | None,
    *,
    shared: bool,
    indent: bool = False,
) -> bool:
    """Write the second-pass document, unless the run computed nothing: it would
    only replace the record of the previous run, or store analyses that were all
    skipped. A run whose plan selected other analyses than the stored document
    keeps the complete results of that document that its plan did not select
    (they follow its own entries): an automatic report after ``scan --deep`` must
    not throw away what a forced run paid for. ``shared`` is true for a document
    beside the shared Scan, whose writes are exclusive."""
    document = outcome.document
    if not outcome.executed:
        return False
    if previous is not None and previous.base == document.base:
        held = {item.id for item in document.analyses}
        kept = [
            item
            for item in previous.analyses
            if item.status == "complete" and item.id not in held
        ]
        if kept:
            document = document.model_copy(
                update={"analyses": [*document.analyses, *kept]}
            )
    text = deep_document(document, indent=indent)
    try:
        if shared:
            with workspace_writer(StorageLocation.local()):
                write_text_atomic(deep_path, text)
        else:
            write_text_atomic(deep_path, text)
    except OSError as exc:
        raise ReportError(f"Cannot write second-pass file {deep_path}: {exc}") from exc
    return True

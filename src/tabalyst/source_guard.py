# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Checks before and after a second reading of a source (PASS2-01, PASS2-06).

A second pass stands on a Scan and a plan; it must never mix them with another
version of the source. Before reading, the plan must belong to the Scan and the
source must be there, readable and of the recorded size. The content is not
hashed in advance, which would read the file twice: the executor hashes it
while it reads and ``SourceGuard.finish`` compares the digest at the end, so
the results stay provisional until it agrees.
"""

from __future__ import annotations

from pathlib import Path

from tabalyst.errors import InputError
from tabalyst.scanner.models import ScanResult, SourceInfo
from tabalyst.scanner.planner.models import AnalysisPlan
from tabalyst.scanner.planner.planner import plan_base


class StalePlan(InputError):
    """The plan was made for another Scan than the one offered."""


class StaleSource(InputError):
    """The source is not the one the Scan read, or changed while it was read."""


class SourceNotReadable(InputError):
    """The source cannot be read again. The Scan and the plan stay valid."""


def check_plan_base(plan: AnalysisPlan, scan: ScanResult) -> None:
    """Raise ``StalePlan`` unless ``plan`` was made for ``scan`` (D04): same
    source, configuration, engine and facts."""
    current = plan_base(scan)
    if plan.base != current:
        differs = sorted(
            name
            for name in type(current).model_fields
            if getattr(plan.base, name) != getattr(current, name)
        )
        raise StalePlan(
            "Stale plan: it was made for another scan "
            f"({', '.join(differs)} differ). Plan again from the current scan."
        )


class SourceGuard:
    """Guards one second reading of ``path`` against the source ``recorded`` by
    the Scan."""

    def __init__(self, path: Path, recorded: SourceInfo) -> None:
        self.path = path
        self.recorded = recorded

    def before(self) -> None:
        """Check, without reading the content, that the source can be read
        again and has the recorded size.

        Raises ``SourceNotReadable`` when it is missing, is not a file or
        cannot be opened (D05), and ``StaleSource`` when its size differs (D04).
        Nothing is copied: a source that cannot be read again is never
        materialized in a temporary file (PASS2-06).
        """
        try:
            is_file = self.path.is_file()
            if is_file:
                with self.path.open("rb"):
                    size = self.path.stat().st_size
        except OSError as exc:
            raise SourceNotReadable(self._unreadable(str(exc))) from exc
        if not is_file:
            raise SourceNotReadable(self._unreadable("it is not a file there"))
        if size != self.recorded.size_bytes:
            raise StaleSource(
                f"Stale plan: {self.path.name} has {size:,} bytes, the scan read "
                f"{self.recorded.size_bytes:,}. {self._advice()}"
            )

    def finish(self, sha256: str, bytes_read: int) -> None:
        """Compare what the second reading hashed with what the Scan recorded.

        Raises ``StaleSource`` when they differ: the source changed, possibly
        during the reading, and the results of this pass must be discarded, not
        published beside the Scan.
        """
        if bytes_read != self.recorded.size_bytes or sha256 != self.recorded.sha256:
            raise StaleSource(
                f"The content of {self.path.name} is not what the scan read "
                "(it changed, possibly while it was read). The results of this "
                f"pass were discarded. {self._advice()}"
            )

    def _unreadable(self, why: str) -> str:
        return (
            f"Cannot read {self.path} again: {why}. The scan and the plan are "
            "still valid, but a second pass needs the source: restore it or "
            "scan a readable copy. Tabalyst does not copy a source to a "
            "temporary file."
        )

    def _advice(self) -> str:
        return f"Run tabalyst scan {self.path} again."


def prepare_second_pass(plan: AnalysisPlan, scan: ScanResult, source: Path) -> SourceGuard:
    """The checks that precede a second reading of ``source`` (D04, D05): the
    plan belongs to the Scan, and the source is there with its recorded size.
    Returns the guard whose ``finish`` closes the pass."""
    check_plan_base(plan, scan)
    guard = SourceGuard(source, scan.source)
    guard.before()
    return guard

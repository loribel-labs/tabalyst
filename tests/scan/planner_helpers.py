# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Build small Scans and read plans for the planner tests."""

from collections.abc import Iterable
from pathlib import Path

from scan_helpers import write_text

from tabalyst.scanner import ScanConfig, ScanResult, scan
from tabalyst.scanner.models import FieldResult
from tabalyst.scanner.planner import AnalysisPlan
from tabalyst.scanner.planner.models import Candidate


def scan_csv(
    directory: Path, header: str, rows: Iterable[str], **settings: object
) -> ScanResult:
    """Scan a CSV written under ``directory`` with the given scan settings."""
    path = write_text(directory, "data.csv", header + "\n" + "\n".join(rows) + "\n")
    return scan(path, config=ScanConfig.model_validate(settings))


def with_field(result: ScanResult, display: str, **changes: object) -> ScanResult:
    """The Scan with some members of one field replaced, as a document edited
    by hand or written with other settings would have them."""
    datasets = []
    for dataset in result.datasets:
        fields: list[FieldResult] = []
        for field in dataset.fields:
            fields.append(
                field.model_copy(update=changes) if field.display == display else field
            )
        datasets.append(dataset.model_copy(update={"fields": fields}))
    return result.model_copy(update={"datasets": datasets})


def by_analyzer(plan: AnalysisPlan, analyzer: str) -> dict[str, Candidate]:
    """The candidates of an analyzer by the display path of their field."""
    return {c.display: c for c in plan.candidates if c.analyzer == analyzer}


def unique_state_bytes(plan: AnalysisPlan) -> int:
    """Firm bytes of the states of the selected candidates, each key once."""
    states: dict[str, int] = {}
    for candidate in plan.candidates:
        if candidate.selection.state == "selected" and candidate.costs is not None:
            for state in candidate.costs.states:
                states[state.key] = max(states.get(state.key, 0), state.memory.max)
    return sum(states.values())

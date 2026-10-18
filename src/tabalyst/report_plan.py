# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The second-pass plan as a Report keeps it: the decisions, not the planner's costs.

A Report prints which analyses were selected, left out and why. The costs, execution
details and parameters of each candidate belong to the second-pass document written
beside the Scan (``<stem>.deep.json``), which keeps the whole plan (contract
summary-table.md 21.5).
"""

from typing import Any

from pydantic import model_serializer

from tabalyst.scanner.models import ScanModel, _omit_none
from tabalyst.scanner.planner.models import AnalysisPlan, Applicability, Selection
from tabalyst.scanner.secondpass.models import DeepResult


class ReportCandidate(ScanModel):
    """One analysis of one field with its decision: what a page prints of a candidate.

    ``partner`` names the second field of an analysis of a pair, and ``display`` both.
    """

    id: str
    analyzer: str
    dataset: str
    field: str
    display: str
    partner: str | None = None
    applicability: Applicability
    selection: Selection

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler: Any) -> dict[str, Any]:
        return _omit_none(handler(self), ("partner",))


class ReportPlan(AnalysisPlan):
    """The plan of a Report. ``plan_id`` is still the one of the whole plan, which the
    second-pass document keeps: it is not the hash of the shortened candidates."""

    candidates: list[ReportCandidate]  # type: ignore[assignment]


class ReportDeep(DeepResult):
    """The second-pass document of a Report: the results as the second pass wrote them,
    and the plan without the costs of its candidates."""

    plan: ReportPlan  # type: ignore[assignment]


def shorten_deep(deep: DeepResult) -> ReportDeep:
    """The Report's copy of a second-pass document."""
    candidates = [
        ReportCandidate(
            id=item.id,
            analyzer=item.analyzer,
            dataset=item.dataset,
            field=item.field,
            display=item.display,
            partner=item.partner,
            applicability=item.applicability,
            selection=item.selection,
        )
        for item in deep.plan.candidates
    ]
    plan = ReportPlan(**{**dict(deep.plan), "candidates": candidates})
    return ReportDeep(**{**dict(deep), "plan": plan})

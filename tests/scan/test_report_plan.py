# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The Report keeps the decisions of the second-pass plan, not its costs (lot R11b, 21.5)."""

import json

from second_pass_helpers import deep_csv

from tabalyst.models import AnalysesBlock
from tabalyst.report_deep import second_pass_view
from tabalyst.report_plan import ReportDeep, shorten_deep

KEPT = {"id", "analyzer", "dataset", "field", "display", "applicability", "selection"}


def _outcome(tmp_path):
    rows = [f"C{n:05d},{n % 7},2024-{n % 12 + 1:02d}-{n % 28 + 1:02d}" for n in range(300)]
    result, plan, outcome = deep_csv(tmp_path, "customer_id,group,signed", rows)
    return result, plan, outcome.document


def test_the_stored_plan_lists_only_the_decisions_of_each_candidate(tmp_path):
    _, _, document = _outcome(tmp_path)

    block = AnalysesBlock(mode="forced", outcome="ran", deep=document)

    candidates = json.loads(block.model_dump_json())["deep"]["plan"]["candidates"]
    assert candidates
    assert all(set(item) - {"partner"} == KEPT for item in candidates)


def test_the_second_pass_document_itself_keeps_the_whole_plan(tmp_path):
    _, plan, document = _outcome(tmp_path)

    candidate = json.loads(document.model_dump_json())["plan"]["candidates"][0]

    assert {"costs", "execution", "outputs", "parameters"} <= set(candidate)
    assert len(plan.candidates) == len(document.plan.candidates)


def test_a_whole_document_given_to_the_block_is_shortened(tmp_path):
    _, _, document = _outcome(tmp_path)

    block = AnalysesBlock(mode="forced", outcome="ran", deep=document)

    assert isinstance(block.deep, ReportDeep)


def test_shortening_keeps_the_results_and_the_rest_of_the_plan(tmp_path):
    _, _, document = _outcome(tmp_path)

    short = shorten_deep(document)

    assert short.analyses == document.analyses
    assert short.plan.plan_id == document.plan.plan_id
    assert short.plan.summary == document.plan.summary
    assert short.plan.relations == document.plan.relations
    assert [c.selection for c in short.plan.candidates] == [
        c.selection for c in document.plan.candidates
    ]


def test_the_second_pass_panel_reads_the_shortened_plan(tmp_path):
    result, _, document = _outcome(tmp_path)
    whole = AnalysesBlock(mode="forced", outcome="ran", deep=document)

    view = second_pass_view(whole, result.datasets[0].id)

    assert view.available and view.metrics is not None
    assert view.metrics.computed > 0
    assert view.metrics.already_answered + view.metrics.not_selected > 0

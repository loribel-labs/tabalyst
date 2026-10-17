# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Final classification of a column: the Scan's, refined by the second pass.

The Report starts from ``fields[].classification`` and changes it only where
``analyses.deep`` supplies a fact the first pass lacked. Pure function of the
document: no source is read, so a Report rendered from its JSON gets the same
result (contract ``docs/dev/report/summary-table.md`` 4 and 8).
"""

from __future__ import annotations

from tabalyst.models import AnalysesBlock
from tabalyst.scanner.classify.identifiers import (
    ID,
    MINIMUM_VALUES,
    UNIQUE_ID,
    positions_complete,
    unique_evidence,
)
from tabalyst.scanner.classify.models import (
    Classification,
    ClassificationEvidence,
    ClassificationScope,
)
from tabalyst.scanner.models import FieldResult
from tabalyst.scanner.planner.models import PlanBase
from tabalyst.scanner.quality import ANALYTICAL_STAGES, analytical_distinct
from tabalyst.scanner.secondpass.models import DistinctCount

DISTINCT = "exact_distinct.distinct"


def _distinct_count(
    field: FieldResult,
    analyses: AnalysesBlock | None,
    dataset: str | None,
    base: PlanBase | None,
) -> DistinctCount | None:
    """The exact distinct count the second pass holds for the field, if usable.

    ``None`` when there is no second-pass document, when it stands on another
    Scan than ``base`` (stale or incompatible), when the analysis did not end
    ``complete`` (a stopped count is only a lower bound), or when ``dataset`` is
    not given and the field id is found in several datasets.
    """
    if analyses is None or analyses.deep is None:
        return None
    deep = analyses.deep
    if base is not None and deep.base != base:
        return None
    found = [
        item
        for item in deep.analyses
        if item.analyzer == "exact_distinct"
        and item.field == field.id
        and (dataset is None or item.dataset == dataset)
    ]
    if len({item.dataset for item in found}) != 1:
        return None
    # A stored document can hold several results of the analysis for a field
    # (other parameters, a stopped run): any complete count is exact.
    for item in found:
        if item.status == "complete" and isinstance(item.result, DistinctCount):
            return item.result
    return None


def _analytical_stages_unchanged(field: FieldResult) -> bool:
    """Whether no enabled analytical stage (NFC, trim, whitespace) altered a value.

    Then the analytical values are the original ones and the second pass, which
    counts the original ones, counts the analytical ones too. Otherwise `"A"`
    and `" A "` are distinct originals and one analytical value (CA-06).
    """
    return all(
        stage.changed == 0
        for stage in field.normalization.stages
        if stage.stage in ANALYTICAL_STAGES and stage.enabled
    )


def _context(count: DistinctCount) -> ClassificationEvidence:
    """The second-pass count that did not decide, kept as a fact that frames."""
    return ClassificationEvidence(
        source="measure",
        id=DISTINCT,
        role="context",
        scope=ClassificationScope(
            population="present_values",
            of=count.values,
            partial=False,
            accuracy="exact",
        ),
    )


def refine(
    field: FieldResult,
    analyses: AnalysesBlock | None,
    *,
    dataset: str | None = None,
    base: PlanBase | None = None,
    excluded_records: int = 0,
) -> Classification:
    """The classification of the Report: the Scan's, refined by the second pass.

    One refinement exists: an ``identifier/id`` whose cardinality the first pass
    could not complete becomes ``identifier/unique_id`` when ``exact_distinct``
    proves that every present value is different and the other conditions of the
    contract 3.8 hold (not under a JSON array, no missing position, at least two
    values). The count is of the original values, so it proves uniqueness of the
    analytical values only when no analytical stage changed one; otherwise the
    ID stays and the count is kept as `context`. A refinement never contradicts
    a fact of the first pass and never loosens a type.

    ``dataset`` and ``base`` tell which dataset the field is in and which Scan
    the second pass must stand on; a document of another Scan, a missing,
    failed or stopped analysis changes nothing. ``base=None`` skips that check
    for a caller that vouches for the document. ``excluded_records`` is the
    number of records the scan left out: the scope is then ``partial``.
    """
    classification = field.classification
    if (
        (classification.family, classification.type) != ID
        or "observed_unique" in classification.traits
        or analytical_distinct(field) is not None
    ):
        return classification
    count = _distinct_count(field, analyses, dataset, base)
    if (
        count is None
        or count.values != field.values.count
        or count.values < MINIMUM_VALUES
        or not count.unique
        or not positions_complete(field)
    ):
        return classification
    if not _analytical_stages_unchanged(field):
        return classification.model_copy(
            update={"evidence": [*classification.evidence, _context(count)]}
        )
    return classification.model_copy(
        update={
            "family": UNIQUE_ID[0],
            "type": UNIQUE_ID[1],
            "traits": [*classification.traits, "observed_unique"],
            "evidence": [
                *classification.evidence,
                *unique_evidence(field, excluded_records, DISTINCT),
            ],
        }
    )

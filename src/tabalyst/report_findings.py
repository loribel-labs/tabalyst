# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Findings of a column (Missing, Errors, Issues): the checks that produce them.

Built from the document alone (contract summary-table.md 6) when the Report is
built, then stored in the column summary (section 20). The models are in
``summary_models``; the checks of the Errors (lot R6a) and of the Issues (lot R6b)
are registered in ``CHECKS``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from itertools import combinations
from typing import Literal

from pydantic import Field

from tabalyst.report_labels import finding_label
from tabalyst.report_views import ColumnView
from tabalyst.result_model import ResultModel
from tabalyst.scanner.classify.candidates import DETECTOR_TYPES
from tabalyst.scanner.classify.catalog import (
    FINDING_CODES,
    FINDINGS,
    FindingCode,
    FindingUnit,
    PopulationKind,
)
from tabalyst.scanner.models import (
    Complete,
    DetectorComplete,
    DetectorResult,
    Disabled,
    Failed,
    FieldResult,
    ItemsSegment,
    Limited,
    NotApplicable,
    Observation,
)
from tabalyst.scanner.quality import (
    DOMINANT_LENGTH_MIN_SHARE,
    MINORITY_LENGTH_MIN_VALUES,
    analytical_distinct,
    value_slots,
)
from tabalyst.summary_models import (  # noqa: F401  (re-exported for the checks)
    Accuracy,
    Assessment,
    AssessmentState,
    ColumnFindings,
    Example,
    Finding,
    FindingList,
    MissingFinding,
    Population,
    Share,
)

DetectorState = Literal["complete", "disabled", "not_applicable", "failed"]


class CheckResult(ResultModel):
    """What one check returns for one column: how far it went and what it found."""

    assessment: Assessment
    items: list[Finding] = Field(default_factory=list)


Check = Callable[[ColumnView], CheckResult]
# The check of each active code. A code without one has not run: its state is
# ``not_assessed``, never ``none_detected``. Lot R6a registers the Errors (at the
# end of this module), lot R6b the Issues.
CHECKS: dict[str, Check] = {}


# Figures ----------------------------------------------------------------------


def share(numerator: int, denominator: int, accuracy: Accuracy = "exact") -> Share:
    """The share of ``numerator`` in ``denominator`` as a percentage.

    A zero or negative denominator, or a numerator the denominator cannot hold,
    gives no percentage and the accuracy ``unavailable``: never NaN, infinity or
    a share over 100 % (RF-22).
    """
    if denominator <= 0 or not 0 <= numerator <= denominator:
        return Share(
            numerator=numerator,
            denominator=denominator,
            percent=None,
            accuracy="unavailable",
        )
    return Share(
        numerator=numerator,
        denominator=denominator,
        percent=numerator * 100 / denominator,
        accuracy=accuracy,
    )


class RepetitionFigures(ResultModel):
    """The figures of repetition of a field (contract 6.3), none of them the
    others: ``beyond_first`` is ``N - D``, not the number of duplicated
    occurrences nor of duplicated groups. The group figures are ``None`` when
    only ``N`` and ``D`` are known."""

    present: int
    distinct: int
    beyond_first: int
    duplicated_groups: int | None = None
    occurrences_in_duplicated_groups: int | None = None
    # D / N, ``None`` for no present value. It is not the share of values that
    # occur once.
    distinct_ratio: float | None


def _ratio(distinct: int, present: int) -> float | None:
    return distinct / present if present else None


def repetition_figures(values: Iterable[str]) -> RepetitionFigures:
    """The figures of repetition of a list of values: for ``A, A, A, B`` four
    present, two distinct, two repetitions beyond the first, one duplicated group
    of three occurrences."""
    counts = Counter(values)
    present = sum(counts.values())
    repeated = [count for count in counts.values() if count > 1]
    return RepetitionFigures(
        present=present,
        distinct=len(counts),
        beyond_first=present - len(counts),
        duplicated_groups=len(repeated),
        occurrences_in_duplicated_groups=sum(repeated),
        distinct_ratio=_ratio(len(counts), present),
    )


def repetition_from_counts(
    present: int, distinct: int | None
) -> RepetitionFigures | None:
    """The figures that ``N`` and an exact ``D`` give. ``None`` when ``D`` is not
    exact (a limited count proves nothing) or cannot be held by ``N``."""
    if distinct is None or distinct < 0 or distinct > present:
        return None
    return RepetitionFigures(
        present=present,
        distinct=distinct,
        beyond_first=present - distinct,
        distinct_ratio=_ratio(distinct, present),
    )


# Evaluation states ------------------------------------------------------------


def evaluation_state(
    detector_state: DetectorState,
    eligible: int = 0,
    tested: int = 0,
    found: int = 0,
) -> AssessmentState:
    """The state of a check from the state of its detector and its coverage
    (contract 6.4).

    A failed detector is ``failed`` whatever it counted: a technical failure is
    never a number of invalid values (CA30). ``none_detected`` needs a complete
    detector that tested every eligible value; one that tested 100 of 1,000 is
    ``partial`` (CA17). Nothing eligible is ``not_applicable``, and eligible
    values none of which was tested are ``not_assessed``.
    """
    if detector_state == "failed":
        return "failed"
    if detector_state == "disabled":
        return "not_assessed"
    if detector_state == "not_applicable":
        return "not_applicable"
    if detector_state != "complete":
        raise ValueError(f"Unknown detector state: {detector_state!r}")
    if found > 0:
        return "detected"
    if eligible <= 0:
        return "not_applicable"
    if tested <= 0:
        return "not_assessed"
    return "partial" if tested < eligible else "none_detected"


def assess_detector(
    code: str,
    detector: DetectorResult,
    looking_for: Literal["invalid", "ambiguous"],
) -> Assessment:
    """How far a detector checked what ``code`` looks for.

    The count of a partly tested detector is a lower bound of the eligible
    values: it says what the tested ones showed and nothing about the others.
    """
    if not isinstance(detector, DetectorComplete):
        reason = getattr(detector, "reason", None)
        return Assessment(
            code=code,
            state=evaluation_state(detector.status),
            reason=reason or ("disabled" if detector.status == "disabled" else None),
        )
    coverage = detector.coverage
    found = coverage.invalid if looking_for == "invalid" else coverage.ambiguous
    state = evaluation_state("complete", coverage.eligible, coverage.tested, found)
    accuracy: Accuracy = "unavailable"
    if state in ("detected", "none_detected"):
        accuracy = "exact" if coverage.tested >= coverage.eligible else "lower_bound"
    elif state == "partial":
        accuracy = "lower_bound"
    return Assessment(
        code=code,
        state=state,
        accuracy=accuracy,
        eligible=coverage.eligible,
        tested=coverage.tested,
    )


def detector_of(field: FieldResult, detector_id: str) -> DetectorResult | None:
    """The result of a detector for a field, ``None`` when none was run."""
    return next(
        (detector for detector in field.detectors if detector.id == detector_id), None
    )


def list_state(
    items: Sequence[Finding], assessments: Sequence[Assessment]
) -> AssessmentState:
    """The state of a whole list from its findings and the checks behind it.

    Findings make it ``detected``. Without any, the checks that apply decide:
    all in one state give that state, a mix with a check that completed (or went
    part of the way) is ``partial``, a mix of failures and checks that never ran
    is ``failed``. A list nothing applies to is ``not_applicable``.
    """
    if items:
        return "detected"
    states = {item.state for item in assessments if item.state != "not_applicable"}
    if not states:
        return "not_applicable"
    if len(states) == 1:
        return next(iter(states))
    if states & {"none_detected", "partial", "detected"}:
        return "partial"
    return "failed" if "failed" in states else "not_assessed"


# Findings from the Scan's facts -----------------------------------------------

# What an observation counts, as a unit and as the population it is out of.
_OBSERVATION_UNITS: dict[str, tuple[FindingUnit, PopulationKind]] = {
    "value_slots": ("positions", "positions"),
    "content_strings": ("occurrences", "content_strings"),
    "occurrences": ("occurrences", "occurrences"),
    "records": ("records", "records"),
    "distinct_values": ("distinct_values", "distinct_values"),
    "groups": ("groups", "groups"),
}


def finding_from_observation(code: str, observation: Observation) -> Finding:
    """A finding that states an observation of the Scan as it is: its count in
    its unit, out of its population, with its accuracy. Nothing is recomputed.

    A rule that counts columns is not about the values of one column and has no
    unit here (``ValueError``).
    """
    entry = FINDING_CODES[code]
    if entry.status != "active":
        raise ValueError(f"{code} is a recommended finding: it is never reported.")
    try:
        unit, kind = _OBSERVATION_UNITS[observation.population]
    except KeyError:
        raise ValueError(
            f"Observation {observation.id} counts {observation.population}, "
            "which no finding of a column states."
        ) from None
    if observation.field is None:
        raise ValueError(f"Observation {observation.id} is not about a field.")
    return Finding(
        code=code,
        cls=entry.cls,
        field=observation.field,
        count=observation.count,
        unit=unit,
        population=Population(kind=kind, size=observation.of),
        share=(
            None
            if observation.of is None
            else share(observation.count, observation.of, observation.accuracy)
        ),
        accuracy=observation.accuracy,
        basis=[observation.id],
    )


def records_overlap(first: Observation, second: Observation) -> bool:
    """Whether two observations are proven to concern a common record.

    Only when both list every record they count (the list is complete: its length
    is the count) and the lists meet. Equal counts prove nothing (CA26), and an
    observation that lists some of its records proves nothing for the others.
    """
    lists = []
    for observation in (first, second):
        records = observation.records
        if len(records) != observation.count or observation.accuracy != "exact":
            return False
        lists.append(set(records))
    return bool(lists[0] & lists[1])


class FindingGroup(ResultModel):
    """Findings presented as one because their overlap is proven. ``counts`` keeps
    each count: no total of the group is made up, since the sets overlap."""

    members: list[Finding]

    @property
    def merged(self) -> bool:
        return len(self.members) > 1

    @property
    def counts(self) -> list[int | None]:
        return [member.count for member in self.members]


def merge_proven(findings: Sequence[Finding]) -> list[FindingGroup]:
    """The findings grouped for presentation, in the order they come.

    Two findings share a group only when one of them names the other in
    ``overlaps``, which a builder sets from a proof (same set, or record lists
    that meet); the relation is closed by transitivity. Findings with equal
    counts and no proof stay apart (RF-24, CA26). The findings themselves are
    never changed.

    A code is a name only if one finding bears it: when several do (one
    ``semantic.invalid`` per detector), the name does not tell which one overlaps
    and nothing is merged.
    """
    parent = list(range(len(findings)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    by_code: dict[str, list[int]] = {}
    for index, finding in enumerate(findings):
        by_code.setdefault(finding.code, []).append(index)
    for index, finding in enumerate(findings):
        for code in finding.overlaps:
            named = by_code.get(code, ())
            if len(named) == 1:
                parent[find(named[0])] = find(index)
    groups: dict[int, list[Finding]] = {}
    for index, finding in enumerate(findings):
        groups.setdefault(find(index), []).append(finding)
    return [FindingGroup(members=members) for members in groups.values()]


def label_for(code: str, count: int, unit: str) -> str:
    """A count with the name of its finding, in the unit it is counted in:
    ``3 spelling-variant groups``, ``1 spelling-variant group``. The noun follows the
    real quantity and the unit follows the metric the Scan has (CA14, CA15)."""
    return finding_label(code, count, unit)


# Missing ----------------------------------------------------------------------


def missing_finding(column: ColumnView) -> MissingFinding:
    """The missing positions of a column from the Scan's components.

    Out of the positions of the field: its occurrences plus the parents that lack
    it (the same denominator as ``missing_percent``). Under a JSON array the
    positions are occurrences, not rows (CA21). The count is exact: the Scan
    counts every position.
    """
    field = column.field
    positions = value_slots(field)
    repeated = any(isinstance(segment, ItemsSegment) for segment in field.path)
    count = field.missing.count
    if positions <= 0:
        state: AssessmentState = "not_applicable"
    else:
        state = "detected" if count else "none_detected"
    return MissingFinding(
        field=field.id,
        count=count,
        unit="occurrences" if repeated else "positions",
        population=Population(kind="positions", size=positions),
        share=share(count, positions),
        state=state,
        definition=list(field.missing.definition),
        components=field.missing.components,
    )


# Errors and Issues ------------------------------------------------------------


def _not_assessed(code: str) -> CheckResult:
    return CheckResult(
        assessment=Assessment(code=code, state="not_assessed", reason="no_check")
    )


def _seen_by(assessment: Assessment, items: Sequence[Finding]) -> Assessment:
    """The check as one list sees it: ``detected`` only when the findings went to
    that list. The check of an Error that was downgraded to an Issue found
    something, but not an Error: for the Errors it found nothing (so it is
    ``partial`` if it covered only part of the values, else ``none_detected``)."""
    if assessment.state != "detected" or items:
        return assessment
    covered = assessment.accuracy != "lower_bound"
    return assessment.model_copy(
        update={"state": "none_detected" if covered else "partial"}
    )


def _settle(entry: FindingCode, item: Finding, column: ColumnView) -> Finding:
    """A finding of a check as the column may show it.

    A check answers for its own code, in its own class: an Error that the
    classification does not establish is an Issue (RF-13), whatever the check
    thought. A code or a class the catalogue does not give the check is a defect
    of the check (``ValueError``), never a finding shown to a reader.
    """
    if item.code != entry.code:
        raise ValueError(f"The check of {entry.code} returned a {item.code} finding.")
    if item.cls == "error" and column.classification.state != "established":
        return item.model_copy(update={"cls": "issue"})
    if item.cls != entry.cls and not (
        entry.downgrades_to_issue and item.cls == "issue"
    ):
        raise ValueError(f"The check of {entry.code} returned a {item.cls} finding.")
    return item


def column_findings(
    column: ColumnView, checks: Mapping[str, Check] | None = None
) -> ColumnFindings:
    """Missing, Errors and Issues of a column, computed from the document alone.

    Every active code of the catalogue is checked by its registered check (``CHECKS``;
    ``checks`` replaces it). A code with no check has not run and is
    ``not_assessed``: an empty list is never ``None detected`` unless every check
    behind it completed (CA17). An Error that the classification does not
    establish is an Issue (RF-13): its finding goes to the Issues, and its check
    counts for both lists. A check answers only for its own code and class. The
    Issues point to each other through ``overlaps`` only where the observations
    prove a common record (``prove_overlaps``).
    """
    registry = CHECKS if checks is None else checks
    errors: list[Finding] = []
    issues: list[Finding] = []
    error_checks: list[Assessment] = []
    issue_checks: list[Assessment] = []
    for entry in FINDINGS:
        if entry.status != "active" or entry.cls == "information":
            continue
        check = registry.get(entry.code)
        result = check(column) if check is not None else _not_assessed(entry.code)
        found: dict[str, list[Finding]] = {"error": [], "issue": []}
        for item in (_settle(entry, item, column) for item in result.items):
            found[item.cls].append(item)
        errors.extend(found["error"])
        issues.extend(found["issue"])
        if entry.cls == "error":
            error_checks.append(_seen_by(result.assessment, found["error"]))
            if entry.downgrades_to_issue:
                issue_checks.append(_seen_by(result.assessment, found["issue"]))
        else:
            issue_checks.append(_seen_by(result.assessment, found["issue"]))
    issues = prove_overlaps(issues, column)
    return ColumnFindings(
        field=column.field.id,
        missing=missing_finding(column),
        errors=FindingList(
            items=errors,
            state=list_state(errors, error_checks),
            assessments=error_checks,
        ),
        issues=FindingList(
            items=issues,
            state=list_state(issues, issue_checks),
            assessments=issue_checks,
        ),
    )


# Errors (lot R6a) -------------------------------------------------------------

# The detectors whose valid values define their type: the ``invalid`` of one of
# these on a field of that type is a value that has the shape of the type and
# fails its syntax. The type is read from the classification, never from the
# detector alone: a detector that finds some values in a Text column is not a
# constraint on the others (RF-14).
_SEMANTIC_TYPES = {
    DETECTOR_TYPES[detector]: detector
    for detector in ("email", "phone", "postal_code", "url", "ip_address", "uuid")
}
# The numeric types that the technical type alone decides, with their technical
# type. Date and Boolean are left out on purpose: a datetime in a Date field and a
# ``yes`` that the boolean detector accepts are outside their technical family and
# are not invalid; the impossible dates have their own check.
_TECHNICAL_NUMERIC = {
    ("numeric", "integer"): "integer",
    ("numeric", "number"): "number",
}


def _withheld(code: str, state: AssessmentState, reason: str) -> CheckResult:
    return CheckResult(assessment=Assessment(code=code, state=state, reason=reason))


def _detector_values(
    code: str,
    column: ColumnView,
    detector_id: str,
    looking_for: Literal["invalid", "ambiguous"] = "invalid",
) -> CheckResult:
    """The ``invalid`` (an Error) or ``ambiguous`` (an Issue) values of one
    detector.

    The count and its accuracy are the detector's own: a detector that tested
    part of the eligible values gives a lower bound, a failed one gives
    ``failed`` and never a count (CA30). ``column_findings`` turns an Error into
    an Issue when the classification is not established.
    """
    detector = detector_of(column.field, detector_id)
    if detector is None:
        return _withheld(code, "not_assessed", "detector_missing")
    assessment = assess_detector(code, detector, looking_for)
    if assessment.state != "detected" or not isinstance(detector, DetectorComplete):
        return CheckResult(assessment=assessment)
    entry = FINDING_CODES[code]
    coverage = detector.coverage
    found = coverage.invalid if looking_for == "invalid" else coverage.ambiguous
    finding = Finding(
        code=code,
        cls=entry.cls,
        field=column.field.id,
        count=found,
        unit=entry.unit,
        population=Population(kind=entry.population, size=coverage.eligible),
        share=share(found, coverage.eligible, assessment.accuracy),
        accuracy=assessment.accuracy,
        basis=[detector.id],
    )
    return CheckResult(assessment=assessment, items=[finding])


def invalid_dates(column: ColumnView) -> CheckResult:
    """``temporal.invalid_calendar``: the values of a Temporal field that the
    ``date`` detector reads as invalid.

    The detector does not split its ``invalid`` by reason: an impossible calendar
    date, an impossible time or offset, mixed separators and a malformed component
    width are all in the count (the Scan words it ``Invalid date``). A value that
    is not date-shaped at all is ``not_matched`` and not counted (CA13).
    """
    code = "temporal.invalid_calendar"
    if column.classification.family != "temporal":
        return _withheld(code, "not_applicable", "not_temporal")
    return _detector_values(code, column, "date")


def invalid_semantic_values(column: ColumnView) -> CheckResult:
    """``semantic.invalid``: the ``invalid`` values of the detector that gives the
    field its type (Email, Phone, Postal code, URL, IP address, UUID).

    Only that detector answers, and the detector is in ``basis``. A field whose
    type is another one, or none, has no meaning established for it to violate.
    """
    code = "semantic.invalid"
    classification = column.classification
    detector = _SEMANTIC_TYPES.get((classification.family, classification.type))
    if detector is None:
        return _withheld(code, "not_applicable", "not_semantic_type")
    return _detector_values(code, column, detector)


def values_outside_family(column: ColumnView) -> CheckResult:
    """``type.outside_family``: the values outside the family of the technical type
    of an Integer or a Number field (the requalification of ``type_error_count``).

    The count is ``technical_type.outside_count``, exact over the values the Scan
    read, less the decimals of an Integer (they are numbers). A Text field has no
    family its values can fall outside of.
    """
    code = "type.outside_family"
    field = column.field
    classification = column.classification
    technical = field.technical_type
    present = field.values.count
    expected = _TECHNICAL_NUMERIC.get((classification.family, classification.type))
    if (
        expected is None
        or technical.type != expected
        or technical.outside_count is None
        or present <= 0
    ):
        return _withheld(code, "not_applicable", "not_numeric_type")
    # A decimal in an Integer field is a number, not a value outside the numbers:
    # the technical type counts it outside the integers only.
    outside = technical.outside_count - (
        technical.counts.get("number", 0) if expected == "integer" else 0
    )
    assessment = Assessment(
        code=code,
        state="detected" if outside else "none_detected",
        accuracy="exact",
        eligible=present,
        tested=present,
    )
    if not outside:
        return CheckResult(assessment=assessment)
    entry = FINDING_CODES[code]
    finding = Finding(
        code=code,
        cls=entry.cls,
        field=field.id,
        count=outside,
        unit=entry.unit,
        population=Population(kind=entry.population, size=present),
        share=share(outside, present),
        accuracy="exact",
        basis=["technical_type"],
    )
    return CheckResult(assessment=assessment, items=[finding])


CHECKS.update(
    {
        "temporal.invalid_calendar": invalid_dates,
        "semantic.invalid": invalid_semantic_values,
        "type.outside_family": values_outside_family,
    }
)


# Issues (lot R6b) -------------------------------------------------------------

# An Issue needs no established classification (RF-13 is about Errors): it states
# what the Scan found, on whatever column it found it. Seven of the nine read an
# observation of the Scan (``quality``), one a detector and one the cardinality.


def _measure_state(
    code: str, envelope: Complete[object] | Limited | NotApplicable | Disabled | Failed
) -> Assessment:
    """What the envelope of a measure of the Scan allows to say: ``none_detected``
    stands for a complete measure, any other state is why it is not."""
    if isinstance(envelope, Complete):
        return Assessment(code=code, state="none_detected", accuracy="exact")
    if isinstance(envelope, Limited):
        return Assessment(
            code=code, state="partial", accuracy="lower_bound", reason=envelope.reason
        )
    if isinstance(envelope, NotApplicable):
        return Assessment(code=code, state="not_applicable", reason=envelope.reason)
    if isinstance(envelope, Failed):
        return Assessment(code=code, state="failed", reason=envelope.reason)
    return Assessment(code=code, state="not_assessed", reason="disabled")


def _fact(ready: Assessment, shown: bool) -> Assessment:
    """The state of a complete measure that holds a count: ``detected`` when the
    count is not zero, so that an observation is expected."""
    if ready.state == "none_detected" and shown:
        return ready.model_copy(update={"state": "detected"})
    return ready


def _issue_from_observation(code: str, observation: Observation) -> Finding:
    """The observation as an Issue, with the population kind of the catalogue.

    The pattern ids go to ``basis`` after the observation: the count is the
    distinct values they hold.
    """
    finding = finding_from_observation(code, observation)
    entry = FINDING_CODES[code]
    update: dict[str, object] = {}
    if finding.population.kind != entry.population:
        update["population"] = Population(
            kind=entry.population, size=finding.population.size
        )
    if observation.patterns:
        update["basis"] = [observation.id, *observation.patterns]
    return finding.model_copy(update=update) if update else finding


def _observed(
    code: str,
    column: ColumnView,
    rule: str,
    ready: Assessment,
    *,
    decisive: bool,
) -> CheckResult:
    """An Issue from the observation of a rule, and what an absent one means.

    ``ready`` is what the measure behind the rule allows to say. An observation
    that exists is stated as it is; if the measure was only partly tested its
    count is a lower bound. Without one, ``decisive`` tells whether the measure
    alone proves the absence (a count that is zero) or whether the rule has a
    threshold only the Scan evaluated: then a list of observations that was cut
    or never built proves nothing (CA17).
    """
    observation = next(
        (item.observation for item in column.quality if item.observation.rule == rule),
        None,
    )
    if observation is not None:
        finding = _issue_from_observation(code, observation)
        if ready.accuracy == "lower_bound" and finding.accuracy == "exact":
            finding = finding.model_copy(
                update={
                    "accuracy": "lower_bound",
                    "share": (
                        None
                        if observation.of is None
                        else share(observation.count, observation.of, "lower_bound")
                    ),
                }
            )
        return CheckResult(
            assessment=Assessment(
                code=code,
                state="detected",
                accuracy=finding.accuracy,
                eligible=observation.of,
            ),
            items=[finding],
        )
    if ready.state in ("not_applicable", "failed", "not_assessed", "partial"):
        return CheckResult(assessment=ready)
    if decisive and ready.state == "none_detected":
        return CheckResult(assessment=ready)
    state = column.observations_state
    if state == "unavailable":
        return _withheld(code, "not_assessed", "observations_unavailable")
    if ready.state == "detected" or state == "truncated":
        # The measure holds a count (or the rule is the Scan's alone) and no
        # observation states it: the list was cut, or the document is inconsistent.
        return CheckResult(
            assessment=Assessment(
                code=code,
                state="partial",
                accuracy="lower_bound",
                reason=(
                    "observations_truncated"
                    if state == "truncated"
                    else "observation_not_listed"
                ),
            )
        )
    return CheckResult(assessment=ready)


def ambiguous_dates(column: ColumnView) -> CheckResult:
    """``temporal.ambiguous_date``: the date values that two readings of the day
    and the month fit (observation ``ambiguous_dates``).

    The ``date`` detector gives the state: one that tested part of the eligible
    values makes the count a lower bound, and no ambiguity found is then only
    ``Partially assessed``.
    """
    code = "temporal.ambiguous_date"
    detector = detector_of(column.field, "date")
    ready = (
        assess_detector(code, detector, "ambiguous")
        if detector is not None
        else Assessment(code=code, state="not_assessed", reason="detector_missing")
    )
    return _observed(code, column, "ambiguous_dates", ready, decisive=True)


def ambiguous_numbers(column: ColumnView) -> CheckResult:
    """``number.ambiguous``: the numbers the ``number`` detector reads in more than
    one way (``1,234`` as one thousand or as 1.234 under another convention)."""
    return _detector_values("number.ambiguous", column, "number", "ambiguous")


def case_variants(column: ColumnView) -> CheckResult:
    """``categorical.case_variants``: groups of values that differ only by case,
    accents or spacing (observation ``variant_groups``). The unit is the group,
    never the occurrences in it (CA14)."""
    code = "categorical.case_variants"
    groups = column.field.normalization.variant_groups
    ready = _fact(
        _measure_state(code, groups),
        isinstance(groups, Complete) and groups.value.groups > 0,
    )
    return _observed(code, column, "variant_groups", ready, decisive=True)


def minority_patterns(column: ColumnView) -> CheckResult:
    """``pattern.minority``: the distinct values in patterns far rarer than the
    dominant one (observation ``minority_pattern``).

    The pattern discovery gives the state. A population or a table of patterns the
    discovery had to cut is a sample: with no minority found it is only
    ``Partially assessed``.
    """
    code = "pattern.minority"
    patterns = column.patterns
    if patterns.status == "missing":
        ready = Assessment(
            code=code, state="not_assessed", reason="patterns_unavailable"
        )
    elif patterns.status == "not_applicable":
        ready = Assessment(code=code, state="not_applicable", reason=patterns.reason)
    elif patterns.status == "failed":
        ready = Assessment(code=code, state="failed", reason=patterns.reason)
    else:
        entry = patterns.entry
        limited = entry is None or not entry.population.complete or bool(entry.limits)
        ready = Assessment(
            code=code,
            state="partial" if limited else "none_detected",
            # A sample, not a bound: the observation says ``sample`` itself.
            accuracy="sample" if limited else "exact",
            reason="patterns_sample" if limited else None,
        )
    return _observed(code, column, "minority_pattern", ready, decisive=False)


def minority_lengths(column: ColumnView) -> CheckResult:
    """``length.minority``: the text values far from the one length nearly all
    share (observation ``minority_length``). The histogram needs
    ``MINORITY_LENGTH_MIN_VALUES`` strings to say anything, and one length must
    hold ``DOMINANT_LENGTH_MIN_SHARE`` of them: with two legitimate lengths the
    Scan's rule does not apply, which is not the same as finding nothing."""
    code = "length.minority"
    lengths = column.field.string_lengths
    ready = _measure_state(code, lengths)
    if isinstance(lengths, Complete):
        total = lengths.value.count
        dominant = max(
            (item.count for item in lengths.value.length_histogram), default=0
        )
        if total < MINORITY_LENGTH_MIN_VALUES:
            ready = Assessment(
                code=code, state="not_applicable", reason="too_few_values"
            )
        elif dominant < DOMINANT_LENGTH_MIN_SHARE * total:
            ready = Assessment(
                code=code, state="not_applicable", reason="no_dominant_length"
            )
    return _observed(code, column, "minority_length", ready, decisive=False)


def mixed_types(column: ColumnView) -> CheckResult:
    """``type.mixed``: the values outside the family that comes closest to the
    technical type of a column that has no dominant one (observation
    ``mixed_types``). A numeric column with outsiders is not mixed: its values
    outside are an Error (``type.outside_family``)."""
    code = "type.mixed"
    technical = column.field.technical_type
    if technical.type == "empty":
        ready = Assessment(code=code, state="not_applicable", reason="no_values")
    else:
        ready = Assessment(
            code=code,
            state="detected" if technical.type == "mixed" else "none_detected",
            accuracy="exact",
        )
    return _observed(code, column, "mixed_types", ready, decisive=True)


def _whitespace(code: str, column: ColumnView, stage: str, rule: str) -> CheckResult:
    """The text values a normalization stage changed. A stage that is off, or that
    the Scan did not run, leaves the check ``Not assessed``."""
    field = column.field
    changes = next(
        (item for item in field.normalization.stages if item.stage == stage), None
    )
    if field.strings.content <= 0:
        ready = Assessment(code=code, state="not_applicable", reason="no_text")
    elif changes is None or not changes.enabled or changes.changed is None:
        ready = Assessment(code=code, state="not_assessed", reason="stage_disabled")
    else:
        ready = _fact(
            Assessment(code=code, state="none_detected", accuracy="exact"),
            changes.changed > 0,
        )
    return _observed(code, column, rule, ready, decisive=True)


def surrounding_whitespace(column: ColumnView) -> CheckResult:
    """``text.surrounding_whitespace``: the text values the ``trim`` stage changed
    (observation ``trimmed_cells``)."""
    return _whitespace("text.surrounding_whitespace", column, "trim", "trimmed_cells")


def repeated_whitespace(column: ColumnView) -> CheckResult:
    """``text.repeated_whitespace``: the text values the ``collapse_whitespace``
    stage changed (observation ``collapsed_whitespace``)."""
    return _whitespace(
        "text.repeated_whitespace",
        column,
        "collapse_whitespace",
        "collapsed_whitespace",
    )


def identifier_repetition(column: ColumnView) -> CheckResult:
    """``identifier.repetition``: ``N - D``, the repetitions beyond the first of an
    ID or a Unique ID (contract 6.3); not the duplicated occurrences nor the number
    of duplicated groups, which the Scan does not count.

    ``D`` is the exact count of the analytical values. When it is not exact the
    check is ``Not assessed``, unless the classification already proved the
    uniqueness (a Unique ID, or the trait ``observed_unique``).
    """
    code = "identifier.repetition"
    classification = column.classification
    if classification.family != "identifier":
        return _withheld(code, "not_applicable", "not_identifier")
    field = column.field
    present = field.values.count
    if classification.type == "unique_id" or "observed_unique" in classification.traits:
        return CheckResult(
            assessment=Assessment(
                code=code,
                state="none_detected",
                accuracy="exact",
                eligible=present,
                tested=present,
            )
        )
    figures = repetition_from_counts(present, analytical_distinct(field))
    if figures is None:
        return _withheld(code, "not_assessed", "cardinality_not_exact")
    detected = figures.beyond_first > 0
    assessment = Assessment(
        code=code,
        state="detected" if detected else "none_detected",
        accuracy="exact",
        eligible=present,
        tested=present,
    )
    if not detected:
        return CheckResult(assessment=assessment)
    entry = FINDING_CODES[code]
    finding = Finding(
        code=code,
        cls=entry.cls,
        field=field.id,
        count=figures.beyond_first,
        unit=entry.unit,
        population=Population(kind=entry.population, size=present),
        share=share(figures.beyond_first, present),
        accuracy="exact",
        basis=["values.cardinality"],
    )
    return CheckResult(assessment=assessment, items=[finding])


def prove_overlaps(items: Sequence[Finding], column: ColumnView) -> list[Finding]:
    """The findings with ``overlaps`` set where the observations they rest on
    prove a common record (``records_overlap``), else untouched (RF-24, CA26).

    Two findings of one code are never related: a code is the name by which one
    finding points to another.
    """
    observed = {
        item.observation.id: item.observation
        for item in column.quality
        if item.observation.records
    }
    if not observed:
        return list(items)
    named: dict[int, set[str]] = {}
    for first, second in combinations(range(len(items)), 2):
        a, b = items[first], items[second]
        proof_a = observed.get(a.basis[0]) if a.basis else None
        proof_b = observed.get(b.basis[0]) if b.basis else None
        if (
            a.code != b.code
            and proof_a is not None
            and proof_b is not None
            and records_overlap(proof_a, proof_b)
        ):
            named.setdefault(first, set()).add(b.code)
            named.setdefault(second, set()).add(a.code)
    return [
        item.model_copy(update={"overlaps": sorted(named[index])})
        if index in named
        else item
        for index, item in enumerate(items)
    ]


CHECKS.update(
    {
        "temporal.ambiguous_date": ambiguous_dates,
        "number.ambiguous": ambiguous_numbers,
        "categorical.case_variants": case_variants,
        "pattern.minority": minority_patterns,
        "length.minority": minority_lengths,
        "type.mixed": mixed_types,
        "identifier.repetition": identifier_repetition,
        "text.surrounding_whitespace": surrounding_whitespace,
        "text.repeated_whitespace": repeated_whitespace,
    }
)

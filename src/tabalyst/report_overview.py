# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Overview of a column: the facts behind one short sentence per profile.

Facts only, read from the classification and from the measures the column view
already holds (contract summary-table.md 7.1). The facts are stored in the column
summary (section 20); the sentence is written from them by ``overview_sentence``
when a page is rendered. A limited measure is worded "at least" or left out,
never said exact.
"""

from __future__ import annotations

from tabalyst.report_labels import (
    OVERVIEW_COMPOSITION,
    OVERVIEW_KINDS,
    OVERVIEW_NUMERIC,
    OVERVIEW_SHAPED,
    OVERVIEW_TEMPORAL,
    OVERVIEW_TEXT,
    format_number,
    plural,
)
from tabalyst.report_measures import dominant_share
from tabalyst.report_views import ColumnView
from tabalyst.scanner.models import Complete
from tabalyst.summary_models import (
    Overview,
    OverviewAccuracy,
    OverviewFact,
    OverviewKind,
    OverviewNote,
)

__all__ = ["Overview", "OverviewFact", "overview_for", "overview_sentence", "overview_text"]


class _Facts:
    """Collects the facts of a column while its profile is read."""

    def __init__(self) -> None:
        self.facts: list[OverviewFact] = []
        self.notes: list[OverviewNote] = []

    def add(
        self,
        name: str,
        value: float | str,
        accuracy: OverviewAccuracy = "exact",
    ) -> None:
        self.facts.append(OverviewFact(name=name, value=value, accuracy=accuracy))


def _distinct(column: ColumnView, facts: _Facts) -> None:
    """The distinct values, when the scan counted them."""
    view = column.distinct
    if view.kind == "not_counted" or view.value is None:
        return
    facts.add("distinct", view.value, "exact" if view.kind == "exact" else "lower_bound")


def _formats(column: ColumnView, facts: _Facts) -> None:
    """The recurring formats of the patterns, when there is one to tell."""
    view = column.patterns
    if view.status != "complete" or view.entry is None or not view.rows:
        return
    whole = view.entry.population.complete and not view.outside_distinct
    facts.add("formats", len(view.rows), "exact" if whole else "lower_bound")


def _top_share(column: ColumnView, facts: _Facts) -> None:
    """Share of the present values held by the most frequent one. The listing is
    ranked by count, so the share is exact even when the table is cut."""
    frequencies = column.field.values.frequencies
    present = column.field.values.count
    if not isinstance(frequencies, Complete) or not frequencies.value.listed or not present:
        return
    facts.add("top_share", frequencies.value.listed[0].count / present)


def _collect_numeric(column: ColumnView, facts: _Facts) -> None:
    stats = column.numeric
    if stats is not None:
        facts.add("minimum", stats.minimum)
        facts.add("maximum", stats.maximum)
        if stats.median is not None:
            facts.add("median", stats.median)
    dominant = dominant_share(column.field)
    # The marker is a value of the source: it follows the exposure of the column,
    # and only the detector that classified the column may speak for it.
    if (
        dominant is not None
        and dominant.detector == column.classification.type
        and column.exposure in (None, "show")
    ):
        facts.add("dominant", dominant.value, "exact" if dominant.exact else "lower_bound")


def _collect_temporal(column: ColumnView, facts: _Facts) -> None:
    temporal = column.field.temporal
    if not isinstance(temporal, Complete) or not temporal.value.kinds:
        return
    for kind in temporal.value.kinds:
        facts.add(f"{kind.kind}_minimum", kind.min[:10])
        facts.add(f"{kind.kind}_maximum", kind.max[:10])
    profile = column.date_profile
    if profile is not None and profile.format_count:
        facts.add("formats", profile.format_count)
    # Ambiguous values are excluded from the range (design 9.6); their number is
    # an Issue and is not repeated here.
    if temporal.value.ambiguous:
        facts.notes.append("ambiguous_left_out")


def _collect_shaped(column: ColumnView, facts: _Facts) -> None:
    kind = column.classification.type
    detector = next((item for item in column.detectors if item.id == kind), None)
    if detector is None or not detector.formats:
        return
    partial = detector.adaptive is not None or bool(
        detector.coverage and detector.coverage.not_tested
    )
    facts.add("formats", len(detector.formats), "lower_bound" if partial else "exact")


def _collect_text(column: ColumnView, facts: _Facts) -> None:
    profile = column.string_profile
    if OVERVIEW_TEXT.get(column.classification.type) is None or profile is None:
        return
    facts.add("median_length", profile.median_length)
    _distinct(column, facts)


def _collect_mixed(column: ColumnView, facts: _Facts) -> None:
    kinds = sorted(
        {
            OVERVIEW_COMPOSITION[name]
            for name, count in column.type_counts.items()
            if count and name in OVERVIEW_COMPOSITION
        }
    )
    for name in kinds:
        facts.add("composition", name)


_PLAIN_KINDS: dict[str, OverviewKind] = {
    "enum": "enum",
    "boolean": "boolean",
    "constant": "constant",
}


def _kind(column: ColumnView) -> OverviewKind:
    family = column.classification.family
    kind = column.classification.type
    if kind == "unique_id":
        return "unique_id"
    if kind == "id":
        return "identifier"
    if kind in _PLAIN_KINDS:
        return _PLAIN_KINDS[kind]
    if family == "numeric":
        return "numeric"
    if family == "temporal":
        return "temporal"
    if kind in OVERVIEW_SHAPED:
        return "shaped"
    if family == "text":
        return "text"
    if kind == "mixed":
        return "mixed"
    if kind == "empty":
        return "empty"
    return "unknown"


def overview_for(column: ColumnView) -> Overview:
    """The facts of a column and the profile that words them."""
    facts = _Facts()
    kind = _kind(column)
    if kind == "unique_id":
        facts.add("present", column.field.values.count)
        if any(item.scope.partial for item in column.classification.evidence):
            facts.notes.append("partial_scope")
        _formats(column, facts)
    elif kind == "identifier":
        _distinct(column, facts)
        _formats(column, facts)
    elif kind == "enum":
        _distinct(column, facts)
        _top_share(column, facts)
    elif kind == "boolean":
        _top_share(column, facts)
    elif kind == "constant":
        facts.add("present", column.field.values.count)
    elif kind == "numeric":
        _collect_numeric(column, facts)
    elif kind == "temporal":
        _collect_temporal(column, facts)
    elif kind == "shaped":
        _collect_shaped(column, facts)
    elif kind == "text":
        _collect_text(column, facts)
    elif kind == "mixed":
        _collect_mixed(column, facts)
    return Overview(
        kind=kind, type=column.classification.type, facts=facts.facts, notes=facts.notes
    )


def overview_text(column: ColumnView) -> str:
    """Only the sentence of a column."""
    return overview_sentence(overview_for(column))


# Words ------------------------------------------------------------------------


def _fact(overview: Overview, name: str) -> OverviewFact | None:
    return next((item for item in overview.facts if item.name == name), None)


def _real(fact: OverviewFact) -> int | float:
    """The value of a fact that must be a number; a hand-edited document may not."""
    if isinstance(fact.value, str):
        raise TypeError(f"The overview fact {fact.name!r} is not a number.")
    return fact.value


def _whole(fact: OverviewFact) -> int:
    """The value of a fact that must be a count."""
    if not isinstance(fact.value, int):
        raise TypeError(f"The overview fact {fact.name!r} is not a whole number.")
    return fact.value


def _number(fact: OverviewFact) -> str:
    """The fact as a number, with ``at least`` when it is a lower bound."""
    prefix = "at least " if fact.accuracy == "lower_bound" else ""
    return f"{prefix}{_whole(fact):,}"


def _counted(fact: OverviewFact | None, one: str, many: str) -> str | None:
    """The fact with the noun that agrees with it: ``1 format``, ``at least 3 formats``."""
    if fact is None:
        return None
    prefix = "at least " if fact.accuracy == "lower_bound" else ""
    return f"{prefix}{plural(_whole(fact), one, many)}"


def _share(fact: OverviewFact | None) -> str | None:
    if fact is None:
        return None
    share = _real(fact)
    text = f"{share:.1%}"
    # Rounding must not claim that one value holds everything when it does not.
    return "more than 99.9%" if share < 1 and text == "100.0%" else text


def _capital(text: str) -> str:
    return f"{text[0].upper()}{text[1:]}"


def _formats_phrase(overview: Overview) -> str | None:
    return _counted(_fact(overview, "formats"), "recurring format", "recurring formats")


def _recognized(overview: Overview) -> str | None:
    return _counted(_fact(overview, "formats"), "recognized format", "recognized formats")


def _unique_id(overview: Overview) -> str:
    present = _fact(overview, "present")
    if present is None:
        raise ValueError("A unique identifier overview needs its 'present' fact.")
    text = f"All {_number(present)} present values are distinct"
    if "partial_scope" in overview.notes:
        text += " in the records the scan accepted"
    formats = _formats_phrase(overview)
    return f"{text}, in {formats}." if formats else f"{text}."


def _identifier(overview: Overview) -> str:
    distinct = _counted(_fact(overview, "distinct"), "distinct value", "distinct values")
    if distinct is None:
        return "Identifier values; their distinct count was not computed."
    formats = _formats_phrase(overview)
    text = _capital(distinct)
    return f"{text} across {formats}." if formats else f"{text}."


def _enum(overview: Overview) -> str:
    distinct = _counted(_fact(overview, "distinct"), "category", "categories")
    top = _share(_fact(overview, "top_share"))
    text = _capital(distinct) if distinct else "Categories"
    return f"{text}; the most frequent holds {top} of present values." if top else f"{text}."


def _boolean(overview: Overview) -> str:
    top = _share(_fact(overview, "top_share"))
    if top is None:
        return "Boolean-like values."
    return f"Boolean-like values; the more frequent state holds {top} of present values."


def _constant(overview: Overview) -> str:
    present = _counted(_fact(overview, "present"), "present position", "present positions")
    return f"One value on all {present}."


def _numeric(overview: Overview) -> str:
    text = OVERVIEW_NUMERIC[overview.type]
    low = _fact(overview, "minimum")
    high = _fact(overview, "maximum")
    if low is not None and high is not None:
        text += f" ranging from {format_number(_real(low))} to {format_number(_real(high))}"
        median = _fact(overview, "median")
        if median is not None:
            text += f", with a median of {format_number(_real(median))}"
    dominant = _fact(overview, "dominant")
    if dominant is not None:
        word = "most often" if dominant.accuracy == "exact" else "often"
        text += f"; {word} {dominant.value}"
    return f"{text}."


def _temporal(overview: Overview) -> str:
    noun = OVERVIEW_TEMPORAL[overview.type]
    parts = []
    for fact in overview.facts:
        if not fact.name.endswith("_minimum"):
            continue
        kind = fact.name.removesuffix("_minimum")
        high = _fact(overview, f"{kind}_maximum")
        if high is None:
            raise ValueError(f"The overview fact {fact.name!r} has no maximum.")
        parts.append(f"{OVERVIEW_KINDS[kind]} range from {fact.value} to {high.value}")
    if not parts:
        return f"{noun}; their range was not computed."
    text = "; ".join(parts)
    formats = _recognized(overview)
    if formats:
        text += f", in {formats}"
    if "ambiguous_left_out" in overview.notes:
        text += " (ambiguous dates left out of the range)"
    return f"{text}."


def _shaped(overview: Overview) -> str:
    text = OVERVIEW_SHAPED[overview.type]
    formats = _recognized(overview)
    return f"{text} in {formats}." if formats else f"{text}."


def _text(overview: Overview) -> str:
    noun = OVERVIEW_TEXT.get(overview.type)
    median = _fact(overview, "median_length")
    if noun is None or median is None:
        return "Text; its length class is not determined."
    text = f"{noun}, with a median length of {format_number(_real(median))} characters"
    distinct = _counted(_fact(overview, "distinct"), "distinct value", "distinct values")
    if distinct:
        text += f" and {distinct}"
    return f"{text}."


def _mixed(overview: Overview) -> str:
    kinds = [str(fact.value) for fact in overview.facts if fact.name == "composition"]
    if len(kinds) < 2:
        return "Present values mix several representations."
    return f"Present values combine {', '.join(kinds[:-1])} and {kinds[-1]} representations."


_SENTENCES = {
    "unique_id": _unique_id,
    "identifier": _identifier,
    "enum": _enum,
    "boolean": _boolean,
    "constant": _constant,
    "numeric": _numeric,
    "temporal": _temporal,
    "shaped": _shaped,
    "text": _text,
    "mixed": _mixed,
}


def overview_sentence(overview: Overview) -> str:
    """The sentence of an Overview, written from its profile and its facts alone."""
    write = _SENTENCES.get(overview.kind)
    if write is not None:
        return write(overview)
    if overview.kind == "empty":
        return "No present values in the analyzed scope."
    return "Values fit more than one type; none is established."

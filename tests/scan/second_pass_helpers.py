# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Run the second pass on small sources and read its results for the tests."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from fractions import Fraction
from pathlib import Path

from planner_helpers import scan_csv

from tabalyst.config import DeepSettings
from tabalyst.scanner.models import FieldPatternsComplete, ScanResult
from tabalyst.scanner.planner import AnalysisPlan, default_registry, plan_analyses
from tabalyst.scanner.secondpass import (
    AnalysisResult,
    SecondPassOutcome,
    run_second_pass,
)
from tabalyst.scanner.secondpass.patterns import PatternAccumulator


def forced_plan(result: ScanResult, deep: DeepSettings | None = None) -> AnalysisPlan:
    """The plan of a forced second pass with what the executor can run."""
    return plan_analyses(
        result, forced=True, registry=default_registry().runnable(), deep=deep
    )


def deep_csv(
    directory: Path,
    header: str,
    rows: Iterable[str],
    *,
    deep: DeepSettings | None = None,
    **settings: object,
) -> tuple[ScanResult, AnalysisPlan, SecondPassOutcome]:
    """Scan a CSV, plan its forced second pass and run it."""
    result = scan_csv(directory, header, rows, **settings)
    plan = forced_plan(result, deep)
    outcome = run_second_pass(result, directory / "data.csv", plan, settings=deep)
    return result, plan, outcome


def entry(outcome: SecondPassOutcome, analyzer: str, display: str) -> AnalysisResult:
    """The result of an analyzer on the field with this display path."""
    found = [
        item
        for item in outcome.document.analyses
        if item.analyzer == analyzer and item.display == display
    ]
    assert len(found) == 1, f"expected one {analyzer} on {display}, found {len(found)}"
    return found[0]


def true_quantile(values: Sequence[Fraction], level: Fraction) -> Fraction:
    """The quantile of exact values by the convention of the document: linear
    between the ranks around ``(n - 1) * level``; the median of an even count is
    the mean of the two central values."""
    ordered = sorted(values)
    position = (len(ordered) - 1) * level
    lower = math.floor(position)
    upper = math.ceil(position)
    return ordered[lower] + (position - lower) * (ordered[upper] - ordered[lower])


def pattern_accumulator(
    result: ScanResult, patterns: FieldPatternsComplete, **options: object
) -> PatternAccumulator:
    """The accumulator of the validation of the first field of ``result`` as the
    second pass builds it, with the default budgets (``options``: ``unique``,
    ``table_cells``)."""
    deep = DeepSettings().patterns
    return PatternAccumulator(
        patterns,
        result.datasets[0].fields[0],
        result.config.pattern_inference,
        table_bytes=deep.table_bytes,
        distinct_bytes=deep.distinct_bytes,
        **options,  # type: ignore[arg-type]
    )

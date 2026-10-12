# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Build data where a category explains a number, and read the numbers by
category of the second pass for the tests (lot 16c)."""

from __future__ import annotations

import random
from collections.abc import Sequence
from fractions import Fraction
from pathlib import Path

from tabalyst.config import DeepSettings
from tabalyst.scanner.models import ScanResult
from tabalyst.scanner.planner import AnalysisPlan, default_registry, plan_analyses
from tabalyst.scanner.planner.analyzer import AnalysisRequest
from tabalyst.scanner.planner.models import Candidate
from tabalyst.scanner.secondpass import (
    AnalysisResult,
    SecondPassOutcome,
    run_second_pass,
)

REGIONS = ["north", "south", "east", "west", "centre"]


def region_rows(
    count: int = 1000,
    *,
    spread: float = 1.0,
    blank_region_every: int = 0,
    blank_price_every: int = 0,
    seed: int = 5,
) -> list[str]:
    """Rows ``region,price,noise``: the price of a region is centered on a value of
    its own (10, 20, 30...), ``spread`` wide; ``noise`` is independent of the
    region. Every ``blank_*_every``-th row has no region or no price."""
    rng = random.Random(seed)
    rows = []
    for n in range(count):
        index = rng.randrange(len(REGIONS))
        region = REGIONS[index]
        price = f"{rng.gauss(10 * (index + 1), 3 * spread):.2f}"
        if blank_region_every and n % blank_region_every == blank_region_every - 1:
            region = ""
        if blank_price_every and n % blank_price_every == blank_price_every - 1:
            price = ""
        rows.append(f"{region},{price},{rng.gauss(50, 9):.2f}")
    return rows


def groups_of(rows: Sequence[str], category: int = 0, number: int = 1) -> dict[str, list[Fraction]]:
    """The exact numbers of each category of CSV rows (rows without either left
    out)."""
    found: dict[str, list[Fraction]] = {}
    for row in rows:
        cells = row.split(",")
        if cells[category] and cells[number]:
            found.setdefault(cells[category], []).append(Fraction(cells[number]))
    return found


def exact_ratio(groups: dict[str, list[Fraction]]) -> tuple[Fraction, Fraction]:
    """The correlation ratio and its corrected form of the groups, in exact
    fractions: ``eta_squared`` and the unclamped ``epsilon_squared``."""
    values = [x for numbers in groups.values() for x in numbers]
    n, k = len(values), len(groups)
    grand = sum(values) / n
    between = sum(len(g) * (sum(g) / len(g) - grand) ** 2 for g in groups.values())
    within = sum(sum((x - sum(g) / len(g)) ** 2 for x in g) for g in groups.values())
    total = between + within
    return between / total, (between - (k - 1) * within / (n - k)) / total


def stats_plan(
    result: ScanResult,
    category: str,
    number: str,
    *,
    also: Sequence[tuple[str, str]] = (),
    deep: DeepSettings | None = None,
) -> AnalysisPlan:
    """A plan of only the numbers by category asked for."""
    requests = [
        AnalysisRequest("category_stats", field=a, partner=b)
        for a, b in [(category, number), *also]
    ]
    return plan_analyses(
        result,
        requests=requests,
        automatic=False,
        registry=default_registry().runnable(),
        deep=deep,
    )


def run_stats(
    result: ScanResult,
    source: Path,
    category: str,
    number: str,
    *,
    deep: DeepSettings | None = None,
    workers: int | None = None,
) -> SecondPassOutcome:
    """Plan the pair asked for and run the second pass."""
    plan = stats_plan(result, category, number, deep=deep)
    return run_second_pass(result, source, plan, settings=deep, workers=workers)


def stats_of(plan: AnalysisPlan) -> list[Candidate]:
    """Every candidate of the analyzer, in plan order."""
    return [c for c in plan.candidates if c.analyzer == "category_stats"]


def stats_entry(outcome: SecondPassOutcome, display: str | None = None) -> AnalysisResult:
    """The result of the only pair of the run, or of the one with this display."""
    found = [
        item
        for item in outcome.document.analyses
        if item.analyzer == "category_stats" and display in (None, item.display)
    ]
    assert len(found) == 1, f"expected one pair, found {len(found)}"
    return found[0]

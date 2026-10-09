# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Build data with known relations and read pair analyses for the tests."""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from fractions import Fraction
from pathlib import Path

from tabalyst.config import DeepSettings
from tabalyst.scanner.models import ScanResult
from tabalyst.scanner.planner import AnalysisPlan, default_registry, plan_analyses
from tabalyst.scanner.planner.models import Candidate
from tabalyst.scanner.planner.planner import AnalysisRequest
from tabalyst.scanner.secondpass import (
    AnalysisResult,
    SecondPassOutcome,
    run_second_pass,
)


def correlated_rows(
    count: int,
    *,
    columns: int = 3,
    noise: float = 0.3,
    holes: dict[str, float] | None = None,
    seed: int = 11,
) -> list[str]:
    """CSV rows of columns named ``a``, ``b``, ``c``...: every column is the first
    plus ``noise``, but the last of three, which is independent of the others.
    ``holes`` gives the share of empty cells of a column."""
    rng = random.Random(seed)
    names = "abcdefgh"[:columns]
    independent = columns == 3
    rows = []
    for _ in range(count):
        base = rng.gauss(0, 1)
        cells = []
        for index, name in enumerate(names):
            value = rng.gauss(5, 2) if independent and index == 2 else base + noise * rng.gauss(0, 1)
            if index == 0:
                value = base
            hole = (holes or {}).get(name, 0.0)
            cells.append("" if hole and rng.random() < hole else f"{value:.4f}")
        rows.append(",".join(cells))
    return rows


def exact_pair(rows: Sequence[str], first: int, second: int) -> tuple[int, float]:
    """The number of common rows and the coefficient of two columns of CSV rows,
    computed in exact fractions."""
    pairs = []
    for row in rows:
        cells = row.split(",")
        if cells[first] != "" and cells[second] != "":
            pairs.append((Fraction(cells[first]), Fraction(cells[second])))
    n = len(pairs)
    mean_x = sum(x for x, _ in pairs) / n
    mean_y = sum(y for _, y in pairs) / n
    cross = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    var_x = sum((x - mean_x) ** 2 for x, _ in pairs)
    var_y = sum((y - mean_y) ** 2 for _, y in pairs)
    return n, float(cross) / math.sqrt(float(var_x) * float(var_y))


def pairs_of(plan: AnalysisPlan) -> list[Candidate]:
    """Every candidate of the correlation analyzer, in plan order."""
    return [c for c in plan.candidates if c.analyzer == "pearson_correlation"]


def chosen(plan: AnalysisPlan) -> list[Candidate]:
    """The pairs the plan selects."""
    return [c for c in pairs_of(plan) if c.selection.state == "selected"]


def pair_plan(
    result: ScanResult,
    first: str,
    second: str,
    *,
    also: Sequence[tuple[str, str]] = (),
    deep: DeepSettings | None = None,
) -> AnalysisPlan:
    """A plan of only the pairs asked for."""
    requests = [
        AnalysisRequest("pearson_correlation", field=a, partner=b)
        for a, b in [(first, second), *also]
    ]
    return plan_analyses(
        result,
        requests=requests,
        automatic=False,
        registry=default_registry().runnable(),
        deep=deep,
    )


def run_pairs(
    result: ScanResult, source: Path, pairs: Sequence[tuple[str, str]]
) -> SecondPassOutcome:
    """Plan the pairs asked for and run the second pass."""
    plan = pair_plan(result, *pairs[0], also=pairs[1:])
    return run_second_pass(result, source, plan)


def pair_entry(outcome: SecondPassOutcome, display: str) -> AnalysisResult:
    """The result of the pair with this display ("a and b")."""
    found = [
        item
        for item in outcome.document.analyses
        if item.analyzer == "pearson_correlation" and item.display == display
    ]
    assert len(found) == 1, f"expected one pair {display!r}, found {len(found)}"
    return found[0]

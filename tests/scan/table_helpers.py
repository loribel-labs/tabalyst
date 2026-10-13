# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Build data where a category determines the shape of another column, and read
the tables of the second pass for the tests (lot 8b)."""

from __future__ import annotations

import random
import string
from collections import Counter
from collections.abc import Callable, Sequence
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

CAPITALS = string.ascii_uppercase
LOWERS = string.ascii_lowercase
DIGITS = string.digits

# Five shapes of identifier with five different structures that no family merges
# (the inference groups values by structure, so shapes that differ by their
# lengths only are one pattern, and `AA9999` with `999999` would be one family):
# A a capital, a a lowercase letter, 9 a digit, any other character itself.
SHAPE_ORDER = ["AA9999", "999-999", "aa99", "AA-9999", "99-AA"]


def make_id(shape: str, rng: random.Random) -> str:
    """A random identifier of one of the shapes."""
    out = []
    for char in shape:
        pool = {"A": CAPITALS, "a": LOWERS, "9": DIGITS}.get(char)
        out.append(char if pool is None else rng.choice(pool))
    return "".join(out)


def branch_rows(
    *,
    branches: int = 12,
    per_branch: int = 100,
    exception_every: int = 0,
    blank_every: int = 0,
    seed: int = 7,
    extra: Callable[[int, int], str] | None = None,
) -> tuple[list[str], list[tuple[str, str, str]]]:
    """Rows ``branch,client`` where branch ``b`` uses shape ``b % 5``, and the
    oracle triples ``(branch, client, shape)`` (shape ``""`` for a blank client).

    Every ``exception_every``-th row of a branch has the next shape; every
    ``blank_every``-th has no client. ``extra`` adds a text after the client."""
    rng = random.Random(seed)
    rows: list[str] = []
    oracle: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for b in range(branches):
        name = f"branch-{b + 1:02d}"
        for n in range(per_branch):
            shape = SHAPE_ORDER[b % len(SHAPE_ORDER)]
            if exception_every and n % exception_every == exception_every - 1:
                shape = SHAPE_ORDER[(b + 1) % len(SHAPE_ORDER)]
            if blank_every and n % blank_every == blank_every - 1:
                rows.append(f"{name}," + ("" if extra is None else extra(b, n)))
                oracle.append((name, "", ""))
                continue
            while True:
                client = make_id(shape, rng)
                if client not in seen:
                    seen.add(client)
                    break
            rows.append(f"{name},{client}" + ("" if extra is None else "," + extra(b, n)))
            oracle.append((name, client, shape))
    return rows, oracle


def oracle_table(
    oracle: Sequence[tuple[str, str, str]], categories: Sequence[str], shapes: Sequence[str]
) -> list[list[int]]:
    """The counts of the oracle in the order of the given categories and shapes
    (a category or shape not listed is the last, ``other``)."""
    table = [[0] * (len(shapes) + 1) for _ in range(len(categories) + 1)]
    for branch, _, shape in oracle:
        if not shape:
            continue
        row = categories.index(branch) if branch in categories else len(categories)
        column = shapes.index(shape) if shape in shapes else len(shapes)
        table[row][column] += 1
    return table


def exact_v(table: Sequence[Sequence[int]]) -> Fraction | None:
    """Cramér's V squared of a table in exact fractions (``None`` when the
    effective dimension is 1 or less); the tests compare its root."""
    rows = [i for i, row in enumerate(table) if sum(row) > 0]
    columns = [j for j in range(len(table[0])) if sum(row[j] for row in table) > 0]
    if len(rows) < 2 or len(columns) < 2:
        return None
    n = sum(sum(row) for row in table)
    chi = Fraction(0)
    for i in rows:
        for j in columns:
            expected = Fraction(sum(table[i]) * sum(row[j] for row in table), n)
            chi += (table[i][j] - expected) ** 2 / expected
    return chi / (n * (min(len(rows), len(columns)) - 1))


def table_plan(
    result: ScanResult,
    category: str,
    column: str,
    *,
    features: Sequence[str] = ("pattern",),
    deep: DeepSettings | None = None,
) -> AnalysisPlan:
    """A plan of only the tables asked for."""
    requests = [
        AnalysisRequest("category_crosstab", field=category, partner=column, feature=f)
        for f in features
    ]
    return plan_analyses(
        result,
        requests=requests,
        automatic=False,
        registry=default_registry().runnable(),
        deep=deep,
    )


def run_tables(
    result: ScanResult,
    source: Path,
    category: str,
    column: str,
    *,
    features: Sequence[str] = ("pattern",),
    deep: DeepSettings | None = None,
) -> SecondPassOutcome:
    """Plan the tables asked for and run the second pass."""
    plan = table_plan(result, category, column, features=features, deep=deep)
    return run_second_pass(result, source, plan, settings=deep)


def tables_of(plan: AnalysisPlan) -> list[Candidate]:
    """Every candidate of the table analyzer, in plan order."""
    return [c for c in plan.candidates if c.analyzer == "category_crosstab"]


def requested_tables(plan: AnalysisPlan) -> list[Candidate]:
    """The tables a request named, among everything the exploration listed."""
    return [c for c in tables_of(plan) if c.selection.requested]


def table_entry(outcome: SecondPassOutcome, feature: str) -> AnalysisResult:
    """The result of the table of one feature."""
    found = [
        item
        for item in outcome.document.analyses
        if item.analyzer == "category_crosstab" and item.parameters.get("feature") == feature
    ]
    assert len(found) == 1, f"expected one table of {feature!r}, found {len(found)}"
    return found[0]


def class_counts(counts: Sequence[Sequence[int]]) -> Counter[int]:
    """Total of each column of a table."""
    total: Counter[int] = Counter()
    for row in counts:
        for j, count in enumerate(row):
            total[j] += count
    return total


def coded_rows(
    *, branches: int = 12, per_branch: int = 60, seed: int = 9
) -> tuple[list[str], list[tuple[str, str, str]]]:
    """Rows ``branch,client`` where the client is a code of the branch followed by
    digits, a capital code on even branches and a lowercase one on odd branches,
    with 4 digits on branches 0 to 3 mod 3 and so on: the pattern, the length and
    the first two characters of the client all say something of the branch. The
    oracle triples are ``(branch, client, code)``."""
    rng = random.Random(seed)
    rows: list[str] = []
    oracle: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for b in range(branches):
        name = f"branch-{b + 1:02d}"
        code = CAPITALS[b] + CAPITALS[(b * 7 + 3) % 26]
        code = code if b % 2 == 0 else code.lower()
        digits = 4 + b % 3
        for _ in range(per_branch):
            while True:
                client = code + "".join(rng.choice(DIGITS) for _ in range(digits))
                if client not in seen:
                    seen.add(client)
                    break
            rows.append(f"{name},{client}")
            oracle.append((name, client, code))
    return rows, oracle

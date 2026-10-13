# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Arithmetic of a table of counts: margins, purity and Cramér's V (design 20.13).

The exploration of the row sample and the second pass share it. A table is a list
of rows of counts, the rows being the categories and the columns the classes of a
feature (REL-13, REL-14). The counts are exact integers; the chi-square and the
coefficients are float64 computed from them. An axis whose margin is zero takes
no part in the coefficients but stays in the table.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

Table = Sequence[Sequence[int]]

# Why an association is not defined (REL-14). Never reported as 0.
TOO_FEW_ROWS = "too_few_rows"
SINGLE_CATEGORY = "single_category"
SINGLE_CLASS = "single_class"
# An expected count below this is a low count; Cochran's rule tolerates a fifth
# of the cells below 5 and none below 1.
LOW_EXPECTED = 5.0
LOW_SHARE = 0.2


@dataclass(frozen=True, slots=True)
class Margins:
    """Row totals, column totals and the total of a table."""

    rows: tuple[int, ...]
    columns: tuple[int, ...]
    total: int


def margins(table: Table) -> Margins:
    """The margins of ``table``; every row has the same number of columns."""
    width = len(table[0]) if table else 0
    columns = [0] * width
    rows: list[int] = []
    for row in table:
        rows.append(sum(row))
        for index, count in enumerate(row):
            columns[index] += count
    return Margins(tuple(rows), tuple(columns), sum(rows))


def dominant(row: Sequence[int]) -> int | None:
    """The column that holds the most of a row, ``None`` for an empty row. A tie
    goes to the first of the columns in the order of the table, which is the
    order the result lists them in (REL-13)."""
    best = -1
    best_count = 0
    for index, count in enumerate(row):
        if count > best_count:
            best, best_count = index, count
    return None if best < 0 else best


@dataclass(frozen=True, slots=True)
class Purity:
    """The share of a table taken by the dominant cell of each line of one
    direction: ``dominant`` counts over ``total``. The reverse direction can
    give another figure (REL-13)."""

    dominant: int
    total: int

    @property
    def value(self) -> float | None:
        return None if self.total == 0 else self.dominant / self.total


def purity_forward(table: Table) -> Purity:
    """Category to class: the sum over the categories of the count of their
    dominant class, over the total."""
    taken = 0
    total = 0
    for row in table:
        total += sum(row)
        index = dominant(row)
        if index is not None:
            taken += row[index]
    return Purity(taken, total)


def purity_reverse(table: Table) -> Purity:
    """Class to category: the sum over the classes of the count of their
    dominant category, over the total."""
    if not table:
        return Purity(0, 0)
    totals = margins(table)
    taken = 0
    for column in range(len(table[0])):
        taken += max((row[column] for row in table), default=0)
    return Purity(taken, totals.total)


def baseline_share(table: Table) -> float | None:
    """The share of the most frequent class over the whole table: the purity a
    rule that always answered that class would have, to read a purity against."""
    totals = margins(table)
    if totals.total == 0:
        return None
    return max(totals.columns) / totals.total


@dataclass(frozen=True, slots=True)
class Association:
    """Cramér's V of a table, or why it is not defined.

    ``effective_rows`` and ``effective_columns`` count the axes whose margin is
    not zero. ``corrected`` is the bias-corrected V of Bergsma (2013), which does
    not grow with the number of classes or shrink with the effectif the way V
    does, and what the planner ranks by. An effective axis with fewer than 5 rows
    is ``sparse``: a stray class of one row does not make a table unreliable, so
    the stability is judged on the other axes. ``low_share`` is the share of the
    cells of those axes whose expected count is below 5; ``stable`` is false when
    it passes a fifth, when an expected count is below 1, or when fewer than two
    rows or two columns are left: such a score must not be called strong
    (REL-14).
    """

    n: int
    effective_rows: int
    effective_columns: int
    chi_square: float | None = None
    degrees: int | None = None
    cramers_v: float | None = None
    corrected: float | None = None
    low_share: float | None = None
    stable: bool | None = None
    sparse: int = 0
    reason: str | None = None


def association(table: Table, min_rows: int = 2) -> Association:
    """Cramér's V of ``table`` over the axes that have a count. Fewer than
    ``min_rows`` counted rows, or an effective dimension of 1 or less, give no
    score and a reason."""
    totals = margins(table)
    rows = [i for i, count in enumerate(totals.rows) if count > 0]
    columns = [j for j, count in enumerate(totals.columns) if count > 0]
    n = totals.total
    if len(rows) < 2:
        return Association(n, len(rows), len(columns), reason=SINGLE_CATEGORY)
    if len(columns) < 2:
        return Association(n, len(rows), len(columns), reason=SINGLE_CLASS)
    if n < max(2, min_rows):
        return Association(n, len(rows), len(columns), reason=TOO_FEW_ROWS)
    chi = 0.0
    for i in rows:
        for j in columns:
            expected = totals.rows[i] * totals.columns[j] / n
            chi += (table[i][j] - expected) ** 2 / expected
    # Stability is read on the axes that hold enough rows to be judged.
    solid_rows = [i for i in rows if totals.rows[i] >= LOW_EXPECTED]
    solid_columns = [j for j in columns if totals.columns[j] >= LOW_EXPECTED]
    sparse = len(rows) - len(solid_rows) + len(columns) - len(solid_columns)
    low = 0
    below_one = False
    for i in solid_rows:
        for j in solid_columns:
            expected = totals.rows[i] * totals.columns[j] / n
            low += expected < LOW_EXPECTED
            below_one = below_one or expected < 1.0
    cells = len(solid_rows) * len(solid_columns)
    low_share = low / cells if cells else 1.0
    stable = len(solid_rows) >= 2 and len(solid_columns) >= 2 and not below_one
    if low_share > LOW_SHARE:
        stable = False
    r, c = len(rows), len(columns)
    smallest = min(r, c) - 1
    v = math.sqrt(min(1.0, chi / (n * smallest)))
    phi = chi / n
    phi_corrected = max(0.0, phi - (r - 1) * (c - 1) / (n - 1))
    r_corrected = r - (r - 1) ** 2 / (n - 1)
    c_corrected = c - (c - 1) ** 2 / (n - 1)
    spread = min(r_corrected, c_corrected) - 1
    corrected = 0.0 if spread <= 0 else math.sqrt(min(1.0, phi_corrected / spread))
    return Association(
        n,
        r,
        c,
        chi_square=chi,
        degrees=(r - 1) * (c - 1),
        cramers_v=v,
        corrected=corrected,
        low_share=low_share,
        stable=stable,
        sparse=sparse,
    )

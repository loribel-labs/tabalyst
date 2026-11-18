# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Rarity levels of an Insurance V2 scenario: nominal case counts and the band of each level."""

from __future__ import annotations

from fractions import Fraction

# Contract insurance-v2.md 3.3: the unit is the case, not the row.
NOMINAL_CASES: dict[str, int] = {
    "frequent": 5000, "uncommon": 500, "rare": 100, "very_rare": 50,
    "extremely_rare": 5, "single": 1,
}
# Inclusive bands of a scenario total; ``None`` is open. They partition 1 and above.
RARITY_BANDS: dict[str, tuple[int, int | None]] = {
    "single": (1, 1), "extremely_rare": (2, 9), "very_rare": (10, 74),
    "rare": (75, 199), "uncommon": (200, 999), "frequent": (1000, None),
}
RARITY_LEVELS = frozenset(RARITY_BANDS)


def band_of(level: str) -> tuple[int, int | None]:
    """Return the inclusive ``(low, high)`` band of a rarity level (``high`` None is open)."""
    return RARITY_BANDS[level]


def level_of(total: int) -> str:
    """Return the rarity level whose band holds a scenario total of cases."""
    for level, (low, high) in RARITY_BANDS.items():
        if total >= low and (high is None or total <= high):
            return level
    raise ValueError(f"a scenario total must be at least 1, got {total}")


# Contract 6.3: the sizes of the sample the probability of absence is computed for.
SAMPLE_SIZES: tuple[int, ...] = (500, 1000, 5000, 10000, 50000)


def absence_probability(rows: int, cases: int, sample: int) -> float | None:
    """Return the probability that ``sample`` rows drawn without replacement hold none of ``cases``.

    The cases are single-row and distinct, so the probability is hypergeometric:
    ``C(rows - cases, sample) / C(rows, sample)``, the product for ``i`` from 0 to ``cases - 1``
    of ``(rows - sample - i) / (rows - i)``. It is computed exactly with integers and rounded
    once, so no sum of float errors builds up (contract 6.3). Returns None when the sample is
    larger than the file; 0.0 when the sample leaves fewer than ``cases`` rows out.
    """
    if sample > rows or cases > rows or sample < 0 or cases < 0:
        return None
    if cases > rows - sample:
        return 0.0
    numerator = denominator = 1
    for i in range(cases):
        numerator *= rows - sample - i
        denominator *= rows - i
    return float(Fraction(numerator, denominator))

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The bin of equal width a number falls in: one rule for the plan and the sample
(design 20.15 and 20.16), so that the counts of a target and the rows that cover it
are placed alike."""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction


def bin_index(number: int | Decimal, low: float, high: float, bins: int) -> int | None:
    """The equal-width bin of the exact range a number falls in, by the rule of
    the second pass (the last bin is closed); ``None`` outside the range."""
    if high <= low or number < low or number > high:
        return None
    if type(number) is int and type(low) is int and type(high) is int:
        return min(bins - 1, ((number - low) * bins) // (high - low))
    scaled = (float(number) - float(low)) / (float(high) - float(low)) * bins
    nearest = round(scaled)
    if abs(scaled - nearest) < 1e-9:
        # Too close to an edge for float64: place it exactly.
        scaled_exact = (Fraction(number) - Fraction(low)) * bins / (Fraction(high) - Fraction(low))
        return min(bins - 1, int(scaled_exact))
    return min(bins - 1, int(scaled))

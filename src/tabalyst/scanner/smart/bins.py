# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The bin of equal width a number falls in: one rule for the plan and the sample
(design 20.15 and 20.16), so that the counts of a target and the rows that cover it
are placed alike."""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache

from tabalyst.scanner.secondpass.accumulators import decimal_bounds
from tabalyst.scanner.secondpass.bins import BinEdges, linear_edges


@lru_cache(maxsize=256, typed=True)
def _edges(low: float, high: float, bins: int) -> BinEdges:
    # The edges of the second pass (``boundaries.place_edges``): a decimal extreme
    # is known only by the float64 the Scan wrote, which may lie on either side of
    # it, so the range widens to the neighbouring floats and the exact maximum stays
    # in the last bin, closed.
    return BinEdges(linear_edges(decimal_bounds(low)[0], decimal_bounds(high)[1], bins))


def bin_index(number: int | Decimal, low: float, high: float, bins: int) -> int | None:
    """The equal-width bin of the range the Scan wrote a number falls in, on the
    edges and by the rule of the second pass (the last bin is closed); ``None``
    outside the range."""
    if high <= low:
        return None
    edges = _edges(low, high, bins)
    index = edges.index(number)
    return index if 0 <= index < edges.bins else None

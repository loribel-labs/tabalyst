# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Random draws shared by the Generate providers, so a distribution is computed once."""

from __future__ import annotations

import math
import random
from statistics import NormalDist


def truncated_lognormal(rng: random.Random, median: float, sigma: float,
                        low: float, high: float) -> float:
    """Draw a log-normal value truncated to [low, high]; both bounds must be above 0.

    The inverse of the normal CDF on a uniform share of [CDF(low), CDF(high)] keeps
    one random number per value, without rejection, so the stream stays aligned.
    """
    normal = NormalDist(math.log(median), sigma)
    lower, upper = normal.cdf(math.log(low)), normal.cdf(math.log(high))
    share = min(max(lower + rng.random() * (upper - lower), 1e-15), 1 - 1e-15)
    return math.exp(normal.inv_cdf(share))

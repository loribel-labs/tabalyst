# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Random draws shared by the Generate providers, so a distribution is computed once."""

from __future__ import annotations

import math
import random
from datetime import date
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


def truncated_pareto(rng: random.Random, alpha: float, low: float, high: float) -> float:
    """Draw a heavy-tail Pareto value truncated to [low, high] (D04, D13).

    Uses the exact inverse transform without rejection to preserve stream alignment:
    CDF(x) = (1 - (low/x)^alpha) / (1 - (low/high)^alpha).
    """
    if not 0 < low < high:
        raise ValueError(f"truncated_pareto requires 0 < low < high, got low={low}, high={high}")
    if alpha <= 0:
        raise ValueError(f"truncated_pareto requires alpha > 0, got {alpha}")
    u = min(max(rng.random(), 1e-15), 1.0 - 1e-15)
    ratio = (low / high) ** alpha
    denom = 1.0 - u * (1.0 - ratio)
    return low / (denom ** (1.0 / alpha))


def bimodal_normal(
    rng: random.Random,
    p: float,
    m1: float,
    s1: float,
    m2: float,
    s2: float,
    low: float | None = None,
    high: float | None = None,
) -> float:
    """Draw from a two-component Gaussian mixture (D05).

    Draws from N(m1, s1) with probability p, and from N(m2, s2) with probability 1 - p.
    When low and high bounds are provided, the drawn component is truncated to [low, high].
    """
    if not 0.0 <= p <= 1.0:
        raise ValueError(f"bimodal_normal mixture weight p must be in [0, 1], got {p}")
    mean, sigma = (m1, s1) if rng.random() < p else (m2, s2)
    normal = NormalDist(mean, max(sigma, 1e-6))
    if low is not None and high is not None:
        if low >= high:
            raise ValueError(f"bimodal_normal requires low < high, got {low} >= {high}")
        c_low = normal.cdf(low)
        c_high = normal.cdf(high)
        u = min(max(c_low + rng.random() * (c_high - c_low), 1e-15), 1.0 - 1e-15)
        return normal.inv_cdf(u)
    u = min(max(rng.random(), 1e-15), 1.0 - 1e-15)
    return normal.inv_cdf(u)


def power_law_weights(n: int, alpha: float = 1.0) -> list[float]:
    """Return Zipf power-law probability weights for n items (D08)."""
    if n <= 0:
        return []
    raw = [1.0 / ((i + 1) ** alpha) for i in range(n)]
    total = sum(raw)
    return [w / total for w in raw]


def seasonal_factor(target_date: date, peak_month: int = 1, amplitude: float = 0.3) -> float:
    """Multiplicative factor simulating harmonic seasonal variation around 1.0 (D09).

    Peaks at peak_month (1.0 + amplitude) and troughs 6 months later (1.0 - amplitude).
    """
    theta = 2.0 * math.pi * (target_date.month - peak_month) / 12.0
    return 1.0 + amplitude * math.cos(theta)


def inflation_factor(current_date: date, base_date: date, annual_rate: float = 0.025) -> float:
    """Continuous compound inflation multiplier relative to base_date (D11)."""
    years = (current_date - base_date).days / 365.25
    return (1.0 + annual_rate) ** years


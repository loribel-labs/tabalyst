# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Unit tests for statistical distributions and sampling draws (lot 10, §12)."""

from __future__ import annotations

import random
from datetime import date

import pytest

from tabalyst.generate_draws import (
    bimodal_normal,
    inflation_factor,
    power_law_weights,
    seasonal_factor,
    truncated_lognormal,
    truncated_pareto,
)


def test_truncated_lognormal_bounds() -> None:
    rng = random.Random(42)
    for _ in range(500):
        val = truncated_lognormal(rng, median=100.0, sigma=0.5, low=10.0, high=1000.0)
        assert 10.0 <= val <= 1000.0


def test_truncated_pareto_bounds_and_heavy_tail() -> None:
    rng = random.Random(42)
    low, high = 100.0, 50000.0
    values = [truncated_pareto(rng, alpha=1.5, low=low, high=high) for _ in range(2000)]
    assert all(low <= v <= high for v in values)
    # Heavy tail check: 80% of values should be below the lower 30% of range, but max reaches high values
    assert sum(v < 1000.0 for v in values) > 1400
    assert max(values) > 10000.0

    with pytest.raises(ValueError, match="0 < low < high"):
        truncated_pareto(rng, alpha=1.5, low=100.0, high=50.0)
    with pytest.raises(ValueError, match="alpha > 0"):
        truncated_pareto(rng, alpha=-1.0, low=10.0, high=100.0)


def test_bimodal_normal_distribution() -> None:
    rng = random.Random(42)
    # 50% around 25 (s=3) and 50% around 55 (s=4)
    values = [bimodal_normal(rng, p=0.5, m1=25.0, s1=3.0, m2=55.0, s2=4.0, low=18.0, high=75.0)
              for _ in range(2000)]
    assert all(18.0 <= v <= 75.0 for v in values)
    low_mode = sum(v < 35.0 for v in values)
    high_mode = sum(v > 45.0 for v in values)
    # Both modes should be well represented
    assert 700 <= low_mode <= 1300
    assert 700 <= high_mode <= 1300


def test_power_law_weights() -> None:
    weights = power_law_weights(10, alpha=1.2)
    assert len(weights) == 10
    assert pytest.approx(sum(weights), 1e-6) == 1.0
    # Strictly decreasing
    for i in range(len(weights) - 1):
        assert weights[i] > weights[i + 1]
    # First weight represents significant share
    assert weights[0] > 0.25
    assert power_law_weights(0) == []


def test_seasonal_factor() -> None:
    # Peak in January (month 1), amplitude 0.3
    jan = seasonal_factor(date(2026, 1, 15), peak_month=1, amplitude=0.3)
    jul = seasonal_factor(date(2026, 7, 15), peak_month=1, amplitude=0.3)
    assert pytest.approx(jan, 0.05) == 1.3
    assert pytest.approx(jul, 0.05) == 0.7
    assert jan > jul


def test_inflation_factor() -> None:
    base = date(2020, 1, 1)
    d1 = date(2020, 1, 1)
    d2 = date(2021, 1, 1)
    d3 = date(2025, 1, 1)
    assert pytest.approx(inflation_factor(d1, base, 0.03), 1e-6) == 1.0
    assert pytest.approx(inflation_factor(d2, base, 0.03), 1e-4) == 1.03
    assert inflation_factor(d3, base, 0.03) > 1.15

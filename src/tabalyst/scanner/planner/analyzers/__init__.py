# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The built-in analyzers of the planner (design 20.5), in plan order."""

from __future__ import annotations

from tabalyst.scanner.planner.analyzer import Analyzer
from tabalyst.scanner.planner.analyzers.distinct import ExactDistinct
from tabalyst.scanner.planner.analyzers.frequencies import ExactFrequencies
from tabalyst.scanner.planner.analyzers.histogram import NumericHistogram
from tabalyst.scanner.planner.analyzers.lengths import LengthDistribution
from tabalyst.scanner.planner.analyzers.patterns import PatternValidation
from tabalyst.scanner.planner.analyzers.temporal import TemporalDistribution

BUILT_INS: tuple[type[Analyzer], ...] = (
    ExactFrequencies,
    NumericHistogram,
    LengthDistribution,
    ExactDistinct,
    PatternValidation,
    TemporalDistribution,
)

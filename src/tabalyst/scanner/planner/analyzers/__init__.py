# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The built-in analyzers of the planner (design 20.5), in plan order."""

from __future__ import annotations

from tabalyst.scanner.planner.analyzer import Analyzer
from tabalyst.scanner.planner.analyzers.crosstab import CategoryCrosstab
from tabalyst.scanner.planner.analyzers.distinct import ExactDistinct
from tabalyst.scanner.planner.analyzers.drift import PositionDrift
from tabalyst.scanner.planner.analyzers.duplicates import DuplicatesReport
from tabalyst.scanner.planner.analyzers.forms import SensitiveForms
from tabalyst.scanner.planner.analyzers.frequencies import ExactFrequencies
from tabalyst.scanner.planner.analyzers.histogram import NumericHistogram
from tabalyst.scanner.planner.analyzers.lengths import LengthDistribution
from tabalyst.scanner.planner.analyzers.matrix import MissingMatrix
from tabalyst.scanner.planner.analyzers.measures import MeasureExtraction
from tabalyst.scanner.planner.analyzers.parts import DatetimeParts
from tabalyst.scanner.planner.analyzers.patterns import PatternValidation
from tabalyst.scanner.planner.analyzers.pearson import PearsonCorrelation
from tabalyst.scanner.planner.analyzers.residuals import ResidualValues
from tabalyst.scanner.planner.analyzers.shape import NumericShape
from tabalyst.scanner.planner.analyzers.stats import CategoryStats
from tabalyst.scanner.planner.analyzers.structure import ArrayProfile, StructureVariants
from tabalyst.scanner.planner.analyzers.temporal import TemporalDistribution
from tabalyst.scanner.planner.analyzers.texts import FingerprintDistinct, TextProfile

BUILT_INS: tuple[type[Analyzer], ...] = (
    ExactFrequencies,
    NumericHistogram,
    LengthDistribution,
    ExactDistinct,
    PatternValidation,
    TemporalDistribution,
    MeasureExtraction,
    ResidualValues,
    DuplicatesReport,
    PearsonCorrelation,
    CategoryCrosstab,
    CategoryStats,
    NumericShape,
    DatetimeParts,
    PositionDrift,
    MissingMatrix,
    ArrayProfile,
    StructureVariants,
    TextProfile,
    FingerprintDistinct,
    SensitiveForms,
)

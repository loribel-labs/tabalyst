# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Eligibility of a field for the pattern discovery (design 18.12, PAT-12): a
state, a score and reasons, computed from the facts and the samples of the Scan
without building a tree.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence

from tabalyst.scanner.config import PatternInferenceSettings
from tabalyst.scanner.models import (
    EligibilityReason,
    EligibilityState,
    FieldResult,
    PatternEligibility,
    PatternExcluded,
    SampleEntry,
)

# The constants below were calibrated on the reference corpus RC-01 to RC-20
# and the contract columns (design 18.12, "Calibration of the eligibility").
# A change of one is a change of the algorithm.

# At most this many formats of fixed length...
MAX_FIXED_FORMATS = 6
# ...cover at least this share of the values (DEC-034): RC-07 needs six
# formats, the hyphenated ISBN of RC-12 reaches 0.80 with six.
MIN_FIXED_COVERAGE = 0.90
# The distinct values at which the variety saturates (2**6).
VARIETY_BITS = 6
# Factor of a field that a semantic detector already interprets (AC-002).
DETECTOR_FACTOR = 0.75
# Factor of each hard criterion a field fails (too many formats, a measure):
# it brings the best score under the threshold, so the state follows the score.
FAILED_FACTOR = 0.25
# Weights of structure and variety in the score.
STRUCTURE_WEIGHT = 0.5
VARIETY_WEIGHT = 0.5
# A field is eligible from this score.
ELIGIBLE_SCORE = 0.35
# An integer column one of whose commonest formats (those that cover
# ``MIN_FIXED_COVERAGE`` of the values, in either measure) has fewer digits reads
# as counts or measures: 0 to 2997 is mostly four digits, but a code has no
# three-digit tail.
MIN_CODE_DIGITS = 4
# Below these shares, a component is named as a weakness among the reasons.
WEAK_SHARE = 0.5

# Detectors whose interpretation does not lower the score: a code made of
# digits is a number, and a configured pattern is structural, not semantic.
_NEUTRAL_DETECTORS = frozenset({"number"})

# A token as ``patterninfer.tokenize`` gives it.
Token = tuple[str, str | None, int, str]
Format = tuple[tuple[str, str | None, int], ...]


# Reasons that speak for the field: the others say why it is not eligible.
_FAVORABLE = frozenset({"regular_structure", "integer_digits"})


def _result(
    state: EligibilityState, reasons: Sequence[EligibilityReason], score: float = 0.0
) -> PatternEligibility:
    return PatternEligibility(state=state, score=score, reasons=list(reasons))


def preselect(field: FieldResult) -> PatternEligibility | None:
    """The eligibility a field gets from its facts alone, or ``None`` when its
    values must be looked at (the first phase)."""
    if field.exposure in ("mask", "hide"):
        return _result("excluded", ["exposure"])
    if field.technical_type.type == "boolean":
        return _result("excluded", ["booleans_only"])
    samples = field.values.samples
    if samples.kept < samples.of:
        return _result("not_assessable", ["samples_withheld"])
    return None


def without_values(field: FieldResult, excluded: PatternExcluded) -> PatternEligibility:
    """The eligibility of a field whose population is empty."""
    samples = field.values.samples
    if excluded.long_text_occurrences > 0 and samples.of == 0:
        return _result("excluded", ["long_texts_only"])
    native = field.native_types
    scalars = sum(native.get(name, 0) for name in ("string", "integer", "number"))
    if not scalars and (native.get("object", 0) or native.get("array", 0)):
        return _result("excluded", ["structures_only"])
    return _result("excluded", ["no_values"])


def assess(
    field: FieldResult,
    entries: Sequence[SampleEntry],
    tokens: Sequence[Sequence[Token]],
    settings: PatternInferenceSettings,
) -> PatternEligibility:
    """The eligibility of a field from the population of the discovery and its
    tokens (the second phase): formats of fixed length, structural marks,
    variety and detectors."""
    if len(entries) < settings.min_distinct:
        return _result("not_assessable", ["too_few_distinct"])
    distinct: Counter[Format] = Counter()
    weighted: Counter[Format] = Counter()
    marked_d = marked_o = 0
    for entry, row in zip(entries, tokens, strict=True):
        # The format of fixed length: the structure with the length of every
        # token (DEC-034), a literal keeping its character.
        key = tuple((code, char, count) for code, char, count, _ in row)
        distinct[key] += 1
        weighted[key] += entry.count
        if any(code == "D" or (code == "P" and char != " ") for code, char, *_ in row):
            marked_d += 1
            marked_o += entry.count
    total_d = len(entries)
    total_o = sum(entry.count for entry in entries)
    fixed = max(_top_share(distinct, total_d), _top_share(weighted, total_o))
    structure = max(marked_d / total_d, marked_o / total_o)
    variety = min(1.0, math.log2(total_d) / VARIETY_BITS)
    score = fixed * (STRUCTURE_WEIGHT * structure + VARIETY_WEIGHT * variety)
    reasons: list[EligibilityReason] = []
    if fixed >= MIN_FIXED_COVERAGE:
        reasons.append("regular_structure")
    else:
        reasons.append("many_fixed_lengths")
        score *= FAILED_FACTOR
    kind = field.technical_type.type
    if kind == "integer":
        fewest = min(_fewest_digits(distinct, total_d), _fewest_digits(weighted, total_o))
        if fewest < MIN_CODE_DIGITS:
            reasons.append("small_integers")
            score *= FAILED_FACTOR
        else:
            reasons.append("integer_digits")
    elif kind == "number":
        reasons.append("decimal_numbers")
        score *= FAILED_FACTOR
    if structure < WEAK_SHARE:
        reasons.append("no_structural_marks")
    if variety < WEAK_SHARE:
        reasons.append("few_distinct")
    if any(
        candidate.detector not in _NEUTRAL_DETECTORS
        and not candidate.detector.startswith("pattern:")
        for candidate in field.interpretations.candidates
    ):
        reasons.append("semantic_detector")
        score *= DETECTOR_FACTOR
    score = round(score, 4)
    if score >= ELIGIBLE_SCORE:
        return _result("eligible", reasons, score)
    return _result("low_relevance", reasons, score)


def _top_share(counts: Counter[Format], total: int) -> float:
    """The share of ``total`` that the ``MAX_FIXED_FORMATS`` largest counts cover."""
    largest = sorted(counts.values(), reverse=True)[:MAX_FIXED_FORMATS]
    return sum(largest) / total


def deciding_reason(eligibility: PatternEligibility) -> EligibilityReason:
    """The first reason that keeps a field from the discovery, or the first
    reason when none does."""
    against = [reason for reason in eligibility.reasons if reason not in _FAVORABLE]
    return (against or eligibility.reasons)[0]


def _fewest_digits(counts: Counter[Format], total: int) -> int:
    """The fewest digits among the commonest formats that together cover
    ``MIN_FIXED_COVERAGE`` of ``total``."""
    covered = 0
    fewest = None
    for key in sorted(counts, key=lambda item: (-counts[item], item)):
        digits = sum(count for code, _, count in key if code == "D")
        fewest = digits if fewest is None else min(fewest, digits)
        covered += counts[key]
        if covered >= MIN_FIXED_COVERAGE * total:
            break
    return fewest or 0

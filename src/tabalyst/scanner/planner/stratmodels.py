# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The advice on stratification a plan carries (design 20.14).

Recommendations, not facts of the data (specification 11.1): each one names its
basis and its uncertainty. They hold counts and field ids, never a value.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import model_serializer

from tabalyst.scanner.models import ScanModel, _omit_none

# ``Any``: a serialized model is a plain dict whose values are JSON data, and the
# handler of a wrap serializer is pydantic's own untyped callable.

Risk = Literal["low", "moderate", "high", "excessive"]
# exact: the exact distinct count; bound: only a certain maximum is known;
# estimate: the KMV estimate of a count the Scan stopped tracking.
Basis = Literal["exact", "bound", "estimate"]


class StratificationLimits(ScanModel):
    """The deterministic thresholds the advice was made with."""

    max_strata_per_column: int
    moderate_above: int
    high_above: int
    max_states: int
    max_fields: int
    explore_min_rows: int
    # The definition of a stratum for a missing value, declared (STRAT-03).
    missing: Literal["own_stratum"] = "own_stratum"


class ColumnAdvice(ScanModel):
    """Whether one column is a good stratification key, and why."""

    dataset: str
    field: str
    display: str
    candidate: bool
    # Codes of ``reasons.STRATIFICATION``: why not, and what to know if yes.
    reasons: list[str]
    # Only for a column that can be a key: the risk of an identifier is not a
    # question anyone asks.
    risk: Risk | None = None
    # Strata the column makes: its distinct values (original domain), plus one
    # for the missing values when there are some. ``strata_bound`` is the
    # certain maximum, ``strata`` the count or the estimate it rests on.
    strata: int | None = None
    strata_basis: Basis | None = None
    strata_bound: int | None = None
    missing_share: float | None = None
    # Shares of the rarest and the most frequent stratum, from the exact
    # frequencies (analytical domain, so a little coarser than the original).
    smallest_share: float | None = None
    largest_share: float | None = None
    # The sample size at which the rarest stratum cannot get zero rows.
    size_for_every_stratum: int | None = None
    # With a sample size: the strata the classic allocation leaves without a row.
    uncovered_at_size: int | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler: Any) -> dict[str, Any]:
        return _omit_none(
            handler(self),
            (
                "risk",
                "strata",
                "strata_basis",
                "strata_bound",
                "missing_share",
                "smallest_share",
                "largest_share",
                "size_for_every_stratum",
                "uncovered_at_size",
            ),
        )


class CombinationAdvice(ScanModel):
    """The strata of several columns taken together."""

    dataset: str
    fields: list[str]
    displays: list[str]
    # The certain maximum of combinations: the product of the upper bounds of
    # the columns, capped by the records. ``saturated`` says the product passed
    # the largest count the document writes, and then ``strata_bound`` is only
    # a floor of that bound.
    strata_bound: int
    saturated: bool
    # The product of the counts or estimates, when they differ from the bound.
    # An estimate is not a certain bound (STRAT-05).
    strata_estimate: int | None = None
    # Distinct combinations in the row sample: a lower bound of the ones that
    # exist, or their exact number when the sample holds every row (STRAT-06).
    observed: int | None = None
    observed_exact: bool = False
    sample_rows: int | None = None
    sample_scope: str | None = None
    risk: Risk
    reasons: list[str]
    # Actions that would lower the risk (STRAT-07), as codes.
    suggestions: list[str]
    # The column that adds the most strata, first candidate to leave out.
    widest_field: str | None = None
    # With a sample size: the rows each stratum gets on average, a bound that
    # does not depend on how the combinations are distributed.
    mean_quota: float | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler: Any) -> dict[str, Any]:
        return _omit_none(
            handler(self),
            (
                "strata_estimate",
                "observed",
                "sample_rows",
                "sample_scope",
                "widest_field",
                "mean_quota",
            ),
        )


class Stratification(ScanModel):
    """Advice for ``stratified`` sampling and for the choice of its columns."""

    version: int
    limits: StratificationLimits
    sample_size: int | None = None
    columns: list[ColumnAdvice]
    combinations: list[CombinationAdvice]

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler: Any) -> dict[str, Any]:
        return _omit_none(handler(self), ("sample_size",))

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The weight of a target: monotone, capped, configurable, versioned (design 20.15)."""

from __future__ import annotations

import math
from typing import Literal

from tabalyst.config import SmartWeights
from tabalyst.scanner.smart.models import Weight

WEIGHTS_VERSION = 1

BaseKind = Literal[
    "confirmed_issue",
    "candidate_anomaly",
    "value",
    "relation_exception",
    "pattern",
    "extreme",
    "signal",
    "bin",
    "missing",
    "remark",
]


def rarity(share: float | None, weights: SmartWeights) -> float:
    """From 0 (a target that covers every row) to 1 (a share of ``floor`` or
    less), on a logarithmic scale; ``unknown_rarity`` without a share."""
    if share is None:
        return weights.unknown_rarity
    if share >= 1:
        return 0.0
    share = max(share, weights.floor)
    return min(1.0, math.log(1 / share) / math.log(1 / weights.floor))


def weight_of(kind: BaseKind, share: float | None, weights: SmartWeights) -> Weight:
    """The weight ``min(cap, base * (1 + gain * rarity))``.

    It never decreases when the share of the target falls or when the base rises,
    and it never exceeds ``cap``: a rare target is wanted more, but a very rare
    one does not drown out every other (the rounding to six decimals keeps this
    true, though not strictly).
    """
    base = float(getattr(weights.base, kind))
    rare = rarity(share, weights)
    raw = base * (1 + weights.gain * rare)
    return Weight(
        version=WEIGHTS_VERSION,
        value=round(min(raw, weights.cap), 6),
        base=base,
        rarity=round(rare, 6),
        capped=raw > weights.cap,
    )

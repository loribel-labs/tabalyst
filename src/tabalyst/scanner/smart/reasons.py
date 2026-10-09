# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The codes a sampling plan writes and their sentences (design 20.15)."""

from __future__ import annotations

# Why a column has no target of a family, or only some (``Catalog.reasons``).
CATALOG: dict[str, str] = {
    "exposure": "its values are masked or hidden, so no target names them",
    "no_values": "it has no values",
    "single_value": "it has a single value and no missing cell, nothing to tell apart",
    "high_cardinality": "it has too many distinct values to give each one a target",
    "domain_unknown": "its distinct values are not tracked and not estimated",
    "long_texts": "its values are long texts, which the Scan does not list",
    "domain_not_exhaustive": (
        "the Scan does not know every value it can take: only the values it saw "
        "have a target, and no value outside them is promised"
    ),
    "target_budget": (
        "the budget of targets left some of its targets out, the lightest first"
    ),
    "sample_basis": (
        "its patterns were found on a sample of distinct values: the targets are "
        "a discovery, not a validation"
    ),
}

# Why a target cannot be evaluated by the sample (``Target.reason``).
FEASIBILITY: dict[str, str] = {
    "needs_row_digest": "recognizing a duplicate row needs a digest of every row",
    "needs_variant_keys": "recognizing a variant needs the normalized key of every value",
}

# Why a reading of the source is, or is not, needed (``PassStep.reason``).
PASSES: dict[str, str] = {
    "scan_stored": "a current Scan is stored: it is not read again",
    "scan_needed": "no current Scan is stored: the first pass must run",
    "no_enrichment": "no second pass was asked for before the sample",
    "enrichment_current": "the second-pass document is current: it is not run again",
    "enrichment_needed": (
        "targets of a second pass were asked for, and it has not run on this Scan"
    ),
    "nothing_to_add": "the second pass has nothing to add to the targets",
    "selection": "the sample reads the source to choose the rows",
}

SIZE: dict[str, str] = {
    "below_mandatory": (
        "the size asked for is below the number of mandatory targets: rows that "
        "cover several targets may still cover them all, but nothing promises it"
    ),
}


def catalog_text(code: str) -> str:
    """The sentence of a catalog reason code."""
    return CATALOG.get(code, code)


def pass_text(code: str) -> str:
    """The sentence of a reason of a reading."""
    return PASSES.get(code, code)

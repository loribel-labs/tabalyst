# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Identity, location and reading of the second-pass document (design 20.4).

A result is reused when its key is the one the run would give it: the key holds
what the result depends on and nothing else, so a budget, a presentation
setting or the order of the analyses never makes a result unusable (CACHE-02,
CACHE-03). A document of another source, configuration, engine or format is not
migrated: it is ignored and rebuilt (CACHE-05, A09).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from tabalyst.json_text import dump_json
from tabalyst.scanner.planner.models import Candidate, PlanBase
from tabalyst.scanner.secondpass.models import (
    FORMAT,
    FORMAT_REVISION,
    FORMAT_VERSION,
    DeepResult,
)

SHARED_SCAN_NAME = "scan.json"
SHARED_DEEP_NAME = "deep.json"
SCAN_SUFFIX = ".scan.json"
DEEP_SUFFIX = ".deep.json"


# The analyzers that work on the original values (design 21); every other one
# works on the analytical values of design section 10.
ORIGINAL_DOMAIN_ANALYZERS = frozenset({"exact_distinct", "pattern_validation"})


def analysis_domain(analyzer: str) -> Literal["analytical", "original"]:
    """The domain of the values an analyzer counts."""
    return "original" if analyzer in ORIGINAL_DOMAIN_ANALYZERS else "analytical"


def analysis_key(base: PlanBase, candidate: Candidate) -> str:
    """The identity of what an analysis computes: the Scan it stands on, the
    analyzer and its version, the field, the method with its effective
    parameters (which hold the bins and the way their bounds are chosen), and
    the domain of the values. Budgets and costs are not part of it."""
    material = {
        "base": base.model_dump(mode="json"),
        "analyzer": candidate.analyzer,
        "analyzer_version": candidate.analyzer_version,
        "dataset": candidate.dataset,
        "field": candidate.field,
        "method": candidate.method,
        "parameters": candidate.parameters,
        "domain": analysis_domain(candidate.analyzer),
    }
    if candidate.partner is not None:
        # Absent for a single field, so the key of its analyses does not move.
        material["partner"] = candidate.partner
    canonical = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def deep_path_for(scan_path: Path) -> Path:
    """Where the second-pass document of a Scan written at ``scan_path`` goes,
    beside it: ``deep.json`` next to the shared ``scan.json``, and
    ``<stem>.deep.json`` next to ``<stem>.scan.json`` or any other scan file."""
    name = scan_path.name
    if name == SHARED_SCAN_NAME:
        return scan_path.with_name(SHARED_DEEP_NAME)
    if name.endswith(SCAN_SUFFIX):
        return scan_path.with_name(name[: -len(SCAN_SUFFIX)] + DEEP_SUFFIX)
    return scan_path.with_name(f"{scan_path.stem}{DEEP_SUFFIX}")


def deep_document(result: DeepResult, *, indent: bool = False) -> str:
    """The JSON text of a second-pass document, as it is written."""
    return dump_json(result.model_dump(mode="json", by_alias=True), indent=indent)


def load_deep(path: Path) -> DeepResult | None:
    """The second-pass document at ``path``, or ``None`` when there is none or
    it cannot be used: not this format or revision, damaged, or not valid. It
    is then simply made again, never migrated."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or (
        data.get("format"),
        data.get("format_version"),
        data.get("format_revision"),
    ) != (FORMAT, FORMAT_VERSION, FORMAT_REVISION):
        return None
    try:
        return DeepResult.model_validate(data)
    except ValidationError:
        return None

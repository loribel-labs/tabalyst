# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Identity of a scan: source content, applied rules, engine version and the
versions of the pattern discovery.

Two scans are interchangeable only when the facts are equal (design
inspect section 10, Patterns FR-020). They are compared field by field, never concatenated.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tabalyst._version import __version__
from tabalyst.scanner.config import (
    ScanConfig,
    SourceFormat,
    config_sha256,
    resolve_config_defaults,
)
from tabalyst.scanner.models import ScanResult
from tabalyst.scanner.patterninfer import discovery_versions
from tabalyst.scanner.readers.excel_common import EXCEL_SUFFIXES

JSONL_SUFFIXES = frozenset({".jsonl", ".ndjson"})


@dataclass(frozen=True, slots=True)
class ScanIdentity:
    source_sha256: str
    config_sha256: str
    engine_version: str
    # The grammar and algorithm versions of the discovery that wrote
    # ``derived.patterns``; ``None`` when the discovery is off. A tree found by
    # another version is not the one this engine would find (FR-020).
    patterns: tuple[int, int] | None = None


def source_format_of(path: Path) -> SourceFormat:
    """The format a source is read as, from its extension."""
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix in EXCEL_SUFFIXES:
        return "excel"
    return "jsonl" if suffix in JSONL_SUFFIXES else "csv"


def scan_identity(result: ScanResult) -> ScanIdentity:
    """The identity recorded by a scan document."""
    found = None if result.derived is None else result.derived.patterns
    return ScanIdentity(
        result.source.sha256,
        result.config_sha256,
        result.engine.version,
        None if found is None else (found.grammar.version, found.algorithm.version),
    )


def expected_identity(
    source_sha256: str, config: ScanConfig, *, source_format: SourceFormat = "json"
) -> ScanIdentity:
    """The identity a scan of this content with ``config`` would have now.

    Defaults are resolved for ``source_format`` first, so a ``null`` error
    policy hashes as the value it resolves to. CSV and JSON resolve alike;
    pass ``"jsonl"`` for a JSONL source.
    """
    resolved = resolve_config_defaults(config, source_format)
    return ScanIdentity(
        source_sha256,
        config_sha256(resolved),
        __version__,
        discovery_versions() if resolved.pattern_inference.enabled else None,
    )


def facts_sha256(base: ScanResult) -> str:
    """SHA-256 of the facts of a base: without ``run``, which varies between
    runs, without ``derived`` and ``observations``, which are computed from the
    facts, and without the contents of the samples and of their strata, whose
    size depends on the document and not on the data (design 19.5)."""
    # ``Any``: a serialized model is a plain dict whose values are JSON data.
    # Excluded before serializing: a Scan holds up to ``max_samples`` values per
    # field, which would be written only to be dropped.
    document: dict[str, Any] = base.model_dump(
        mode="json",
        by_alias=True,
        exclude={
            "run": True,
            "derived": True,
            "observations": True,
            "datasets": {
                "__all__": {
                    "records": {"sample": {"rows": True, "kept": True}},
                    "fields": {
                        "__all__": {
                            "values": {
                                "samples": {
                                    "listed": True,
                                    "kept": True,
                                    "by_length": {
                                        "listed": True,
                                        "strata": {"__all__": {"kept": True, "ids": True}},
                                    },
                                }
                            }
                        }
                    }
                }
            },
        },
    )
    canonical = json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

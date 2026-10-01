"""Identity of a scan: source content, applied rules and engine version.

Two scans are interchangeable only when the three facts are equal (design
inspect section 10). They are compared field by field, never concatenated.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tabalyst._version import __version__
from tabalyst.scanner.config import (
    ScanConfig,
    SourceFormat,
    config_sha256,
    resolve_config_defaults,
)
from tabalyst.scanner.models import ScanResult


@dataclass(frozen=True, slots=True)
class ScanIdentity:
    source_sha256: str
    config_sha256: str
    engine_version: str


def source_format_of(path: Path) -> SourceFormat:
    """The format a source is read as, from its extension."""
    return "json" if path.suffix.lower() == ".json" else "csv"


def scan_identity(result: ScanResult) -> ScanIdentity:
    """The identity recorded by a scan document."""
    return ScanIdentity(
        result.source.sha256, result.config_sha256, result.engine.version
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
    return ScanIdentity(source_sha256, config_sha256(resolved), __version__)

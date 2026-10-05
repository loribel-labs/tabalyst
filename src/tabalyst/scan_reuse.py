# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Reuse of a scan document by the report, with its staleness rule (O12).

A scan document written by ``tabalyst scan`` holds everything the report
needs, record facts included, so the report never reads the source again. It
must still describe the current source and the requested scan settings:

- The source is looked for beside the scan document, under its recorded
  name. A source that is not there is accepted, since the document stands on
  its own, but it is not checked: callers say so.
- A source whose size differs is stale. Otherwise its SHA-256 decides, whatever
  its modification time: a file that was only touched stays fresh, and one
  rewritten with the same size and time is stale (design inspect 10.2).
- The document's settings apply. Scan settings given by the configuration
  files must have the document's values: applied over the document's
  settings, they must leave its ``config_sha256`` unchanged. Settings the
  files do not give, such as a delimiter passed to ``tabalyst scan`` on the
  command line, are not compared.
- A document written by another engine version is still reported, with a
  warning: it is a file the user chose, not a cache (``engine_warning``).
"""

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pydantic import ValidationError

from tabalyst._version import __version__
from tabalyst.config import merge_settings, validation_message
from tabalyst.errors import ConfigurationError, InputError
from tabalyst.scanner.config import (
    config_sha256,
    resolve_config_defaults,
    scan_config_from_layer,
)
from tabalyst.scanner.models import (
    FORMAT,
    FORMAT_REVISION,
    FORMAT_VERSION,
    ScanResult,
    SourceInfo,
)

_HASH_CHUNK = 1 << 20


class UnsupportedScanDocument(InputError):
    """A scan document of another format version than this Tabalyst reads. A
    stored scan in this state is only out of date: the shared cache replaces it."""


def read_scan_document(path: Path) -> dict:
    """The JSON object of a scan document, with its format checked."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise InputError(f"Cannot read scan document {path}: {exc}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise InputError(
            f"Not a scan document: {path} is not valid UTF-8 JSON ({exc})."
        ) from exc
    if not isinstance(document, dict) or document.get("format") != FORMAT:
        raise InputError(
            f"Not a scan document: {path}. Write one with tabalyst scan."
        )
    version = (document.get("format_version"), document.get("format_revision"))
    if version != (FORMAT_VERSION, FORMAT_REVISION):
        raise UnsupportedScanDocument(
            f"Unsupported scan document {path}: format {version[0]} revision "
            f"{version[1]}; this version of Tabalyst reads format "
            f"{FORMAT_VERSION} revision {FORMAT_REVISION}. Run tabalyst scan "
            "again."
        )
    return document


def source_name(document: dict) -> str:
    """The recorded file name of the scanned source."""
    source = document.get("source")
    name = source.get("name") if isinstance(source, dict) else None
    if not isinstance(name, str) or not name or Path(name).name != name:
        raise InputError("Invalid scan document: source.name is not a file name.")
    return name


def load_scan(path: Path) -> ScanResult:
    """The scan result of a scan document."""
    document = read_scan_document(path)
    try:
        return ScanResult.model_validate(document)
    except ValidationError as exc:
        raise InputError(
            f"Invalid scan document {path}: {validation_message(exc)}"
        ) from exc


def source_path(scan_path: Path, result: ScanResult) -> Path:
    """Where the source of a scan document is looked for."""
    return scan_path.parent / result.source.name


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


class SourceState(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    MISSING = "missing"


@dataclass(frozen=True)
class SourceCheck:
    """The outcome of comparing a source with what a scan recorded of it."""

    state: SourceState
    # Why the source is stale, as a sentence naming the file; ``None`` otherwise.
    reason: str | None = None
    # SHA-256 of the current content when it was computed: not for a missing
    # source, nor for a size that already differs.
    sha256: str | None = None


def compare_source(
    source: Path, recorded: SourceInfo, *, sha256: str | None = None
) -> SourceCheck:
    """Compare the file at ``source`` with the facts a scan recorded (O12).

    A present source is compared by content: its size, then its SHA-256. The
    modification time is not consulted (design inspect DP-D). ``sha256`` is the
    hash of the current content when the caller already computed it, which
    saves reading the file again.

    Independent of where the source was looked for: the caller resolves the
    location, beside a scan document or from ``project.json``. A file that is
    not there, or is not a regular file, is ``MISSING``: nothing was checked.
    Raises ``InputError`` when the file exists but cannot be read.
    """
    try:
        stat = source.stat()
    except FileNotFoundError:
        return SourceCheck(SourceState.MISSING)
    except OSError as exc:
        raise InputError(f"Cannot read source {source}: {exc}") from exc
    if not source.is_file():
        return SourceCheck(SourceState.MISSING)
    if stat.st_size != recorded.size_bytes:
        return SourceCheck(
            SourceState.STALE,
            f"{source.name} has {stat.st_size:,} bytes, "
            f"the scan read {recorded.size_bytes:,}.",
        )
    try:
        current = sha256 or file_sha256(source)
    except OSError as exc:
        raise InputError(f"Cannot read source {source}: {exc}") from exc
    if current != recorded.sha256:
        return SourceCheck(
            SourceState.STALE,
            f"the content of {source.name} changed since the scan "
            "(SHA-256 differs).",
            current,
        )
    return SourceCheck(SourceState.FRESH, sha256=current)


def check_source(scan_path: Path, result: ScanResult) -> bool:
    """Raise ``InputError`` when the source beside the document changed.

    Returns ``False`` when no source is beside the document, so nothing was
    checked.
    """
    source = source_path(scan_path, result)
    check = compare_source(source, result.source)
    if check.state is SourceState.STALE:
        raise InputError(
            f"Stale scan {scan_path}: {check.reason} "
            f"Run tabalyst scan {source} again."
        )
    return check.state is SourceState.FRESH


def check_config(scan_path: Path, result: ScanResult, scan_layer: dict) -> None:
    """Raise ``ConfigurationError`` when the scan settings given by the
    configuration files differ from those of the document."""
    if not scan_layer:
        return
    recorded = result.config.model_dump(mode="json", by_alias=True)
    requested = resolve_config_defaults(
        scan_config_from_layer(merge_settings(recorded, scan_layer)),
        result.source.format,
    )
    if config_sha256(requested) != result.config_sha256:
        raise ConfigurationError(
            f"Stale scan {scan_path}: the scan settings of the configuration "
            "differ from those the document was written with. Run tabalyst "
            "scan again with this configuration, or remove these settings "
            "from its scan object to use those of the document."
        )


def engine_warning(result: ScanResult) -> str | None:
    """A sentence when the document was written by another engine version."""
    if result.engine.version == __version__:
        return None
    return (
        f"the scan document was written by Tabalyst {result.engine.version}, "
        f"this is {__version__}; scan the source again for the current "
        "version's analysis."
    )

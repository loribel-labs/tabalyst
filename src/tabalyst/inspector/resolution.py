"""Resolving the interpretation of a source (design inspect section 11).

One function gives ``scan``, ``report`` and the Python API the effective scan
configuration of a JSON, JSONL or NDJSON source: built-in defaults, then the
automatic detection, the ``--config`` files, the visible Inspect file and the
command-line options, from the lowest priority to the highest. A source whose
collection cannot be decided is refused before anything is read for analysis.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from tabalyst.config import merge_settings
from tabalyst.errors import ConfigurationError
from tabalyst.inspector.json_inspect import inspect_source
from tabalyst.inspector.models import InspectDocument
from tabalyst.inspector.persistence import (
    CandidateSummary,
    VisibleInspect,
    inspect_path,
    read_inspect_cache,
    read_visible_inspect,
    write_inspect_cache,
)
from tabalyst.projects.location import StorageLocation
from tabalyst.scan_reuse import file_sha256
from tabalyst.scanner.config import (
    ScanConfig,
    resolve_config_defaults,
    scan_config_from_layer,
)
from tabalyst.scanner.identity import source_format_of
from tabalyst.scanner.models import ScanResult

# Where the Inspect layer came from.
Origin = Literal["visible", "cache", "automatic", "none"]
# Which layer decided the collection of the configuration.
CollectionOrigin = Literal["command_line", "visible", "config_file", "detected", "none"]

JSONL_DATASET = "$[]"


@dataclass(frozen=True)
class Interpretation:
    """The effective configuration of one source and where it came from."""

    config: ScanConfig
    origin: Origin
    collection_origin: CollectionOrigin
    # The visible Inspect file that was read, ``None`` when there is none.
    inspect_path: Path | None
    # Sentences for the user: a command-line choice that overrides the file, a
    # cache that could not be written.
    notices: tuple[str, ...] = ()
    # ``source.sha256`` of the visible file, when it recorded one (design 11.6).
    recorded_sha256: str | None = None


def resolve_interpretation(
    source: str | Path,
    *,
    scan_layer: dict[str, Any] | None = None,
    collections: Sequence[str] | None = None,
    delimiter: str | None = None,
    encoding: str | None = None,
    location: StorageLocation | None = None,
    source_sha256: str | None = None,
) -> Interpretation:
    """The effective ``ScanConfig`` of ``source`` (design 11).

    ``scan_layer`` is the merged ``scan`` section of the ``--config`` files;
    ``collections``, ``delimiter`` and ``encoding`` are command-line options.
    ``source_sha256`` is the hash of the source when the caller already has it,
    which saves reading it again to check the cache. ``location`` is where the
    cache lives (the local storage by default).

    A CSV source has no Inspect: only the layers apply. Raises
    ``ConfigurationError`` when a visible file is not valid, or when a JSON
    source has no collection to analyze (design 11.4), and ``InputError`` when
    the automatic inspection finds the source unreadable or invalid.
    """
    source = Path(source)
    source_format = source_format_of(source)
    layer = scan_layer or {}
    visible: VisibleInspect | None = None
    detected: InspectDocument | None = None
    origin: Origin = "none"
    notices: list[str] = []

    if source_format != "csv":
        file = inspect_path(source)
        if file.exists() or file.is_symlink():
            visible = read_visible_inspect(file)
            origin = "visible"
        elif source_format == "json":
            detected, origin, note = _detect(source, layer, location, source_sha256)
            notices.extend(note)

    detected_layer: dict[str, Any] = {}
    if detected is not None and detected.config.structure.dataset_path is not None:
        detected_layer = {"json": {"collections": [detected.config.structure.dataset_path]}}
    visible_layer = {} if visible is None else visible.config.to_scan_layer()
    merged = merge_settings(merge_settings(detected_layer, layer), visible_layer)
    config = scan_config_from_layer(
        merged, delimiter=delimiter, encoding=encoding, collections=collections
    )

    if source_format == "jsonl":
        config = _jsonl_dataset(config, visible)
    config = resolve_config_defaults(config, source_format)
    if source_format == "jsonl":
        # ``$[]`` is the only dataset: whether it was written or not, the rules
        # applied are the same, so they hash the same.
        config = config.model_copy(
            update={"json_": config.json_.model_copy(update={"collections": None})}
        )

    collection_origin = _collection_origin(
        collections, visible_layer, layer, detected_layer
    )
    if visible is not None and collection_origin == "command_line":
        chosen = visible.config.structure.dataset_path
        if (
            "collections" in visible_layer.get("json", {})
            and config.json_.collections != [chosen]
        ):
            notices.append(
                f"--collection overrides config.structure.dataset_path "
                f"({chosen}) of {visible.path.name}."
            )
    if source_format == "json" and config.json_.collections is None:
        raise _suspension(source, config, visible, detected)
    return Interpretation(
        config=config,
        origin=origin,
        collection_origin=collection_origin,
        inspect_path=None if visible is None else visible.path,
        notices=tuple(notices),
        recorded_sha256=None if visible is None else visible.recorded_sha256,
    )


def check_result(interpretation: Interpretation, result: ScanResult) -> tuple[str, ...]:
    """Compare a scan result with the interpretation it was made with.

    Raises ``ConfigurationError`` when the collection came from the visible
    Inspect file and the source no longer has it (design 11.5): no other
    collection is used instead. Otherwise returns the notices to print, among
    them the one for a source that changed since the file was written
    (design 11.6), which never stops the run.
    """
    if interpretation.collection_origin == "visible":
        wanted = set(interpretation.config.json_.collections or ())
        gone = [
            item.dataset
            for item in result.diagnostics
            if item.code == "json_collection_not_found" and item.dataset in wanted
        ]
        if gone and interpretation.inspect_path is not None:
            raise ConfigurationError(
                f"The collection {gone[0]} set in the Inspect file "
                f"{interpretation.inspect_path} is not an array of "
                f"{result.source.name}, so nothing was analyzed. Set "
                "config.structure.dataset_path in that file to a collection "
                f"that exists; `tabalyst inspect {result.source.name}` lists "
                "the candidates."
            )
    notices: list[str] = []
    recorded = interpretation.recorded_sha256
    if recorded is not None and recorded != result.source.sha256:
        notices.append(
            "The Inspect file was written for a different version of the "
            f"source: {_name(interpretation.inspect_path)} still applies, but "
            "inspect the source again to refresh its detection."
        )
    return tuple(notices)


def _name(path: Path | None) -> str:
    return "its config" if path is None else path.name


def _collection_origin(
    collections: Sequence[str] | None,
    visible_layer: dict[str, Any],
    layer: dict[str, Any],
    detected_layer: dict[str, Any],
) -> CollectionOrigin:
    if collections:
        return "command_line"
    if visible_layer.get("json", {}).get("collections"):
        return "visible"
    if layer.get("json", {}).get("collections"):
        return "config_file"
    return "detected" if detected_layer else "none"


def _jsonl_dataset(config: ScanConfig, visible: VisibleInspect | None) -> ScanConfig:
    """A JSONL source has one dataset: refuse a visible file that names another."""
    if visible is not None:
        chosen = visible.config.structure.dataset_path
        if chosen not in (None, JSONL_DATASET):
            raise ConfigurationError(
                f"Invalid Inspect file {visible.path}: config.structure.dataset_path "
                f"is {chosen}, but a JSONL source has one dataset, {JSONL_DATASET}."
            )
    return config


# Automatic detection (design 11.2, 12.4) -----------------------------------


def _detect(
    source: Path,
    layer: dict[str, Any],
    location: StorageLocation | None,
    source_sha256: str | None,
) -> tuple[InspectDocument, Origin, tuple[str, ...]]:
    """The detection of a source with no visible file: the cache when it
    describes this content and this search depth, else a new inspection that
    replaces it."""
    # Validates the layer here too, so a mistake in it is named once.
    base = scan_config_from_layer(layer)
    location = location or StorageLocation.local()
    cached = read_inspect_cache(location.shared_inspect_path(source))
    if (
        cached is not None
        and cached.detection.scope.discovery_max_depth == base.json_.discovery_max_depth
        and _describes(source, cached, source_sha256)
    ):
        return cached, "cache", ()
    document = inspect_source(source, scan_config=base)
    note = write_inspect_cache(location, source, document)
    return document, "automatic", () if note is None else (note,)


def _describes(source: Path, cached: InspectDocument, sha256: str | None) -> bool:
    """Whether a cached document was made from the content of ``source``.

    Decided by content, never by date (EF-28); a different size is enough to
    say no without reading it.
    """
    try:
        if source.stat().st_size != cached.source.size_bytes:
            return False
        return (sha256 or file_sha256(source)) == cached.source.sha256
    except OSError:
        return False  # the inspection that follows reports the unreadable source


# Suspension (design 11.4) ------------------------------------------------


def _suspension(
    source: Path,
    config: ScanConfig,
    visible: VisibleInspect | None,
    detected: InspectDocument | None,
) -> ConfigurationError:
    if visible is not None:
        candidates = visible.candidates
        basis = visible.selection_basis
    else:
        assert detected is not None
        candidates = tuple(
            CandidateSummary(item.path, item.elements, item.ineligible_reason)
            for item in detected.detection.candidates
        )
        basis = detected.detection.selection.basis
    eligible = [item for item in candidates if item.ineligible_reason is None]
    depth = config.json_.discovery_max_depth
    if basis == "ambiguous":
        why = f"{len(eligible)} collections of {source.name} are equally plausible."
    elif basis == "candidates_truncated":
        why = (
            f"{source.name} holds more arrays than the detection lists, so none "
            "stood out."
        )
    elif basis == "no_eligible_candidate" or not candidates:
        why = (
            f"No supported collection was found in {source.name}: it holds no "
            "array of objects reachable through object keys at a depth of "
            f"{depth} or less (json.discovery_max_depth)."
        )
    else:
        why = f"No collection is selected for {source.name}."
    lines = [f"{why} Nothing was analyzed."]
    if candidates:
        lines.append("Candidates:")
        lines.extend(f"  {_describe(item)}" for item in candidates)
    if visible is not None:
        lines.append(
            f"Set config.structure.dataset_path in {visible.path} to the "
            "collection to analyze, or pass --collection."
        )
    else:
        lines.append(
            f"Pass --collection, or run `tabalyst inspect {source.name}` and set "
            "config.structure.dataset_path in the file it writes."
        )
    return ConfigurationError("\n".join(lines))


def _describe(item: CandidateSummary) -> str:
    count = "" if item.elements is None else f" ({item.elements} elements)"
    reason = {"empty": ", empty", "non_object_elements": ", not objects"}.get(
        item.ineligible_reason or "", ""
    )
    return f"{item.path}{count}{reason}"

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

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
from tabalyst.inspector.excel_inspect import inspect_workbook
from tabalyst.inspector.excel_inspect import parameters as excel_parameters
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
    config_sha256,
    resolve_config_defaults,
    scan_config_from_layer,
)
from tabalyst.scanner.identity import source_format_of
from tabalyst.scanner.models import ScanResult
from tabalyst.scanner.paths import Items, format_absolute, parse_path

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
    # SHA-256 of the current content when resolving had to compute it (to
    # validate the cache): later steps reuse it instead of reading again.
    source_sha256: str | None = None


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
    excel = source_format == "excel"
    if source_format in ("jsonl", "excel"):
        # A configuration file is shared by sources of every format, and its
        # collections name JSON ones: a JSONL source has the one dataset ``$[]``
        # and a workbook names its table in ``excel.dataset_path``.
        layer = _without_collections(layer)
    if excel:
        table = _excel_table(collections)
        collections = None
    else:
        table = None
    visible: VisibleInspect | None = None
    detected: InspectDocument | None = None
    origin: Origin = "none"
    notices: list[str] = []

    if source_format != "csv":
        file = inspect_path(source)
        if file.exists() or file.is_symlink():
            visible = _read_visible(file, source_format)
            origin = "visible"
        elif source_format in ("json", "excel") and not _decided(
            layer, collections, table, source_format
        ):
            detected, origin, note, source_sha256 = _detect(
                source, layer, location, source_sha256
            )
            notices.extend(note)

    detected_layer: dict[str, Any] = {}
    if detected is not None and detected.config.structure.dataset_path is not None:
        chosen_path = detected.config.structure.dataset_path
        detected_layer = (
            {"excel": {"dataset_path": chosen_path}}
            if excel
            else {"json": {"collections": [chosen_path]}}
        )
    visible_layer = {} if visible is None else visible.config.to_scan_layer()
    merged = merge_settings(merge_settings(detected_layer, layer), visible_layer)
    if table is not None:
        merged = merge_settings(merged, {"excel": {"dataset_path": table}})
    config = scan_config_from_layer(
        merged, delimiter=delimiter, encoding=encoding, collections=collections
    )

    if source_format == "jsonl":
        config = _jsonl_dataset(config, visible)
    config = resolve_config_defaults(config, source_format)
    if source_format == "jsonl":
        config = _implicit_dataset(config)

    collection_origin = _collection_origin(
        collections or table, visible_layer, layer, detected_layer, source_format
    )
    if visible is not None and collection_origin == "command_line":
        chosen = visible.config.structure.dataset_path
        overridden = (
            "dataset_path" in visible_layer.get("excel", {})
            and config.excel.dataset_path != chosen
            if excel
            else "collections" in visible_layer.get("json", {})
            and config.json_.collections != [chosen]
        )
        if overridden:
            notices.append(
                f"--collection overrides config.structure.dataset_path "
                f"({chosen}) of {visible.path.name}."
            )
    undecided = (
        config.excel.dataset_path is None
        if excel
        else source_format == "json" and config.json_.collections is None
    )
    if undecided:
        raise _suspension(source, config, visible, detected, notices)
    return Interpretation(
        config=config,
        origin=origin,
        collection_origin=collection_origin,
        inspect_path=None if visible is None else visible.path,
        notices=tuple(notices),
        recorded_sha256=None if visible is None else visible.recorded_sha256,
        source_sha256=source_sha256,
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


def inspect_notice(source: Path, result: ScanResult) -> str | None:
    """For ``report --scan``: a sentence when the visible Inspect file beside
    ``source`` asks for settings that the scan document was not written with.

    The document stands on its own and is never refused for it (the rule of
    identity is unchanged): the file only explains why a new scan would differ.
    """
    file = inspect_path(source)
    source_format = result.source.format
    if source_format == "csv" or not (file.is_file() or file.is_symlink()):
        return None
    try:
        visible = _read_visible(file, source_format)
        recorded = result.config.model_dump(mode="json", by_alias=True)
        wanted = scan_config_from_layer(
            merge_settings(recorded, visible.config.to_scan_layer())
        )
        wanted = resolve_config_defaults(wanted, source_format)
    except ConfigurationError as exc:
        return f"{exc} It was not compared with the scan document."
    if source_format == "jsonl":
        wanted = _implicit_dataset(wanted)
    if config_sha256(wanted) == result.config_sha256:
        return None
    return (
        f"the Inspect file {file.name} sets a configuration that differs from "
        f"the one recorded in this scan document; scan {source.name} again to "
        "apply it."
    )


def _read_visible(file: Path, source_format: str) -> VisibleInspect:
    """The visible Inspect file of a source, refused when it was written for
    another kind of source: its ``config`` would be read with the wrong rules."""
    visible = read_visible_inspect(file)
    expected = "excel" if source_format == "excel" else "json"
    if visible.kind != expected:
        raise ConfigurationError(
            f"Invalid Inspect file {file}: it is of kind {visible.kind!r}, but "
            f"{file.name.removesuffix('-inspect.json')} is read as {expected!r}. "
            "Replace it with `tabalyst inspect --force`."
        )
    return visible


def _implicit_dataset(config: ScanConfig) -> ScanConfig:
    """``$[]`` is the only dataset of a JSONL source: whether it was written or
    not, the rules applied are the same, so they hash the same."""
    return config.model_copy(
        update={"json_": config.json_.model_copy(update={"collections": None})}
    )


def _name(path: Path | None) -> str:
    return "its config" if path is None else path.name


def _chosen(layer: dict[str, Any], source_format: str) -> Any:
    """What a layer says about the collection: ``json.collections`` for JSON
    sources, ``excel.dataset_path`` for workbooks."""
    if source_format == "excel":
        return layer.get("excel", {}).get("dataset_path")
    return layer.get("json", {}).get("collections")


def _collection_origin(
    collections: Sequence[str] | str | None,
    visible_layer: dict[str, Any],
    layer: dict[str, Any],
    detected_layer: dict[str, Any],
    source_format: str,
) -> CollectionOrigin:
    if collections:
        return "command_line"
    if _chosen(visible_layer, source_format):
        return "visible"
    if _chosen(layer, source_format):
        return "config_file"
    return "detected" if detected_layer else "none"


def _decided(
    layer: dict[str, Any],
    collections: Sequence[str] | None,
    table: str | None,
    source_format: str,
) -> bool:
    """Whether the command line or a configuration file already names the
    collections: the detection could only propose a path that they outrank."""
    return bool(collections) or bool(table) or bool(_chosen(layer, source_format))


def _excel_table(collections: Sequence[str] | None) -> str | None:
    """The table named by ``--collection`` for a workbook.

    The command line expands ``Sales`` to the JSON path ``$.Sales[]``; a table
    is not an array, so a trailing ``[]`` is dropped."""
    if not collections:
        return None
    if len(collections) > 1:
        raise ConfigurationError(
            "A workbook is read one table at a time: pass --collection once."
        )
    try:
        path = parse_path(collections[0])
    except ValueError as exc:
        raise ConfigurationError(f"Invalid --collection {collections[0]!r}: {exc}") from exc
    if path and path[-1] == Items():
        path = path[:-1]
    return format_absolute(path)


def _without_collections(layer: dict[str, Any]) -> dict[str, Any]:
    json_layer = layer.get("json")
    if not isinstance(json_layer, dict) or "collections" not in json_layer:
        return layer
    rest = {key: value for key, value in json_layer.items() if key != "collections"}
    return {**{key: value for key, value in layer.items() if key != "json"}, "json": rest}


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
) -> tuple[InspectDocument, Origin, tuple[str, ...], str | None]:
    """The detection of a source with no visible file: the cache when it
    describes this content and this search depth, else a new inspection that
    replaces it. Also returns the hash of the content when it was computed."""
    # Validates the layer here too, so a mistake in it is named once.
    base = scan_config_from_layer(layer)
    location = location or StorageLocation.local()
    cached = read_inspect_cache(location.shared_inspect_path(source))
    excel = source_format_of(source) == "excel"
    if cached is not None and _same_search(cached, base, excel=excel):
        matches, source_sha256 = _describes(source, cached, source_sha256)
        if matches:
            return cached, "cache", (), source_sha256
    document = (
        inspect_workbook(source) if excel else inspect_source(source, scan_config=base)
    )
    note = write_inspect_cache(location, source, document)
    # The pass hashed every byte it read: that is the hash of the content.
    return document, "automatic", () if note is None else (note,), document.source.sha256


def _same_search(cached: InspectDocument, base: ScanConfig, *, excel: bool) -> bool:
    """Whether a cached detection searched the way this run would: the kind of
    the source, and the depth (JSON) or the header rows (Excel) it looked at."""
    detection = cached.detection
    if excel:
        return (
            cached.inspect.kind == "excel"
            and detection.scope.header_scan_rows == excel_parameters.HEADER_SCAN_ROWS
        )
    return (
        cached.inspect.kind == "json"
        and detection.scope.discovery_max_depth == base.json_.discovery_max_depth
    )


def _describes(
    source: Path, cached: InspectDocument, sha256: str | None
) -> tuple[bool, str | None]:
    """Whether a cached document was made from the content of ``source``, and
    the hash computed to decide it.

    Decided by content, never by date (EF-28); a different size is enough to
    say no without reading it.
    """
    try:
        if source.stat().st_size != cached.source.size_bytes:
            return False, sha256
        sha256 = sha256 or file_sha256(source)
    except OSError:
        # The inspection that follows reports the unreadable source.
        return False, sha256
    return sha256 == cached.source.sha256, sha256


# Suspension (design 11.4) ------------------------------------------------


def _suspension(
    source: Path,
    config: ScanConfig,
    visible: VisibleInspect | None,
    detected: InspectDocument | None,
    notices: Sequence[str] = (),
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
    if source_format_of(source) == "excel":
        return _excel_suspension(source, candidates, basis, eligible, visible, notices)
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
    # What was found out on the way, such as a cache that could not be written.
    lines.extend(notices)
    return ConfigurationError("\n".join(lines))


def _excel_suspension(
    source: Path,
    candidates: Sequence[CandidateSummary],
    basis: str | None,
    eligible: Sequence[CandidateSummary],
    visible: VisibleInspect | None,
    notices: Sequence[str],
) -> ConfigurationError:
    if basis == "ambiguous":
        why = f"{len(eligible)} tables of {source.name} are equally plausible."
    elif basis == "candidates_truncated":
        why = (
            f"{source.name} holds more sheets and tables than the detection "
            "lists, so none stood out."
        )
    elif basis == "no_eligible_candidate" or not candidates:
        why = (
            f"No supported table was found in {source.name}: no sheet has a "
            "recognizable header followed by data rows, and it has no named "
            "table with data."
        )
    else:
        why = f"No table is selected for {source.name}."
    lines = [f"{why} Nothing was analyzed."]
    if candidates:
        lines.append("Candidates:")
        lines.extend(f"  {_describe(item, 'row')}" for item in candidates)
    if visible is not None:
        lines.append(
            f"Set config.structure.dataset_path in {visible.path} to the "
            "table to analyze, or pass --collection."
        )
    else:
        lines.append(
            f"Pass --collection with a sheet or table path such as '$.Sheet', or "
            f"run `tabalyst inspect {source.name}` and set "
            "config.structure.dataset_path in the file it writes."
        )
    lines.extend(notices)
    return ConfigurationError("\n".join(lines))


_REASONS = {
    "empty": ", empty",
    "non_object_elements": ", not objects",
    "no_cells": ", empty",
    "no_header": ", no header row",
    "no_data_rows": ", no data row",
    "has_tables": ", its tables are listed on their own",
}


def _describe(item: CandidateSummary, noun: str = "element") -> str:
    count = (
        ""
        if item.elements is None
        else f" ({item.elements:,} {noun}{'' if item.elements == 1 else 's'})"
    )
    return f"{item.path}{count}{_REASONS.get(item.ineligible_reason or '', '')}"

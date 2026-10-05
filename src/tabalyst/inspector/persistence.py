"""Inspect files: the visible file beside a source and the automatic cache.

Shell of every Inspect kind (design inspect sections 4.6 and 12). The visible
file is the user's: it is validated strictly where it carries a choice
(``config``) and leniently elsewhere, and it is never replaced silently. The
cache is Tabalyst's: any defect makes it absent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from tabalyst._version import __version__
from tabalyst.batch import (  # noqa: F401
    INSPECT_SUFFIX,
    is_inspect_name,
    write_text_atomic,
)
from tabalyst.config import validation_message
from tabalyst.errors import ConfigurationError, ReportError
from tabalyst.inspector.models import (
    FORMAT,
    FORMAT_REVISION,
    FORMAT_VERSION,
    DetectionScope,
    ExcelInspectConfig,
    InspectConfig,
    InspectDocument,
    InspectWarning,
)
from tabalyst.projects._locks import workspace_writer
from tabalyst.projects.location import StorageLocation
from tabalyst.scanner.paths import Key, parse_path

# The Inspect kinds this Tabalyst reads (design inspect section 1).
KINDS = ("json", "excel")


def inspect_path(source: str | Path) -> Path:
    """The visible Inspect file of a source: its full name plus ``-inspect.json``.

    The extension is kept, so ``data.json`` and ``data.jsonl`` never share one
    (design 12.1).
    """
    source = Path(source)
    return source.with_name(source.name + INSPECT_SUFFIX)


# Reading the visible file ------------------------------------------------


@dataclass(frozen=True)
class CandidateSummary:
    """A candidate collection as the ``detection`` of a file recorded it."""

    path: str
    elements: int | None
    ineligible_reason: str | None


@dataclass(frozen=True)
class VisibleInspect:
    """A visible Inspect file whose triple, kind and ``config`` are valid.

    The other zones are informative: ``recorded_*`` and ``candidates`` hold
    what could be read from them, ``None`` or empty when they are damaged.
    """

    path: Path
    kind: str
    config: InspectConfig | ExcelInspectConfig
    recorded_sha256: str | None
    recorded_name: str | None
    candidates: tuple[CandidateSummary, ...]
    selection_basis: str | None
    document: dict[str, Any]


def _invalid(path: Path, message: str) -> ConfigurationError:
    return ConfigurationError(f"Invalid Inspect file {path}: {message}")


def _load_object(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ConfigurationError(f"Cannot read Inspect file {path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise _invalid(path, f"not valid UTF-8: {exc}") from exc
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _invalid(path, f"invalid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise _invalid(path, "the file must hold a JSON object")
    return document


def _unsupported(path: Path, key: str, value: object) -> ConfigurationError:
    return ConfigurationError(
        f"Unsupported Inspect file {path}: {key} is {value!r}, and this Tabalyst "
        f"reads format_version {FORMAT_VERSION} format_revision {FORMAT_REVISION}. "
        "Edit the file to that version, or replace it with `tabalyst inspect --force`."
    )


def _check_header(path: Path, document: dict[str, Any]) -> str:
    """Validate the format triple and the kind; return the kind."""
    if document.get("format") != FORMAT:
        raise _invalid(
            path, f"format is {document.get('format')!r}, expected {FORMAT!r}"
        )
    version = document.get("format_version")
    if version != FORMAT_VERSION:
        raise _unsupported(path, "format_version", version)
    revision = document.get("format_revision")
    if isinstance(revision, bool) or revision != FORMAT_REVISION:
        raise _unsupported(path, "format_revision", revision)
    info = document.get("inspect")
    kind = info.get("kind") if isinstance(info, dict) else None
    if kind not in KINDS:
        raise _invalid(
            path,
            f"inspect.kind is {kind!r}; this Tabalyst reads the Inspect kinds: "
            + ", ".join(KINDS),
        )
    return kind


def _read_config(
    path: Path, document: dict[str, Any], kind: str
) -> InspectConfig | ExcelInspectConfig:
    config = document.get("config")
    if not isinstance(config, dict):
        raise _invalid(path, "config must be a JSON object")
    model = ExcelInspectConfig if kind == "excel" else InspectConfig
    try:
        return model.model_validate(config)
    except ValidationError as exc:
        raise _invalid(path, validation_message(exc, "config")) from exc


def _text(container: object, key: str) -> str | None:
    value = container.get(key) if isinstance(container, dict) else None
    return value if isinstance(value, str) and value else None


def _summaries(document: dict[str, Any]) -> tuple[CandidateSummary, ...]:
    detection = document.get("detection")
    items = detection.get("candidates") if isinstance(detection, dict) else None
    if not isinstance(items, list):
        return ()
    found = []
    for item in items:
        path = _text(item, "path")
        if path is None:
            continue
        elements = item.get("elements")
        reason = _text(item, "ineligible_reason")
        found.append(
            CandidateSummary(
                path,
                elements if isinstance(elements, int) and not isinstance(elements, bool)
                else None,
                reason,
            )
        )
    return tuple(found)


def read_visible_inspect(path: Path) -> VisibleInspect:
    """Read and validate a visible Inspect file (design 4.6).

    Raises ``ConfigurationError``, naming the file, for anything that is not a
    document this Tabalyst supports. Nothing is coerced and nothing is
    replaced: the caller decides what an invalid file means.
    """
    document = _load_object(path)
    kind = _check_header(path, document)
    config = _read_config(path, document, kind)
    detection = document.get("detection")
    return VisibleInspect(
        path=path,
        kind=kind,
        config=config,
        recorded_sha256=_text(document.get("source"), "sha256"),
        recorded_name=_text(document.get("source"), "name"),
        candidates=_summaries(document),
        selection_basis=_text(
            detection.get("selection") if isinstance(detection, dict) else None,
            "basis",
        ),
        document=document,
    )


# Writing the visible file ------------------------------------------------


def inspect_text(
    document: InspectDocument, *, config: dict[str, Any] | None = None
) -> str:
    """The text of an Inspect file: two-space JSON, UTF-8, final newline.

    ``config`` replaces the ``config`` section by a value, as the user wrote it.
    """
    data = document.model_dump(mode="json")
    if config is not None:
        data["config"] = config
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _cannot_be_judged(path: str, document: InspectDocument) -> bool:
    """Whether the candidates cannot tell if ``path`` is an array of the source.

    Candidates are the arrays reachable through keys within the discovery
    depth. A deeper path, or one crossing an array, is a valid choice that only
    a scan can check; so is any path when the list was cut. A JSONL source has
    the one dataset ``$[]``, so every path can be judged.
    """
    if document.source.format == "excel":
        # Every sheet and table is a candidate, ineligible ones included: only
        # a cut list cannot tell.
        return document.detection.scope.candidates == "truncated"
    if document.source.format == "jsonl":
        return False
    scope: DetectionScope = document.detection.scope
    if scope.candidates == "truncated":
        return True
    keys = parse_path(path)[:-1]
    return not all(isinstance(segment, Key) for segment in keys) or len(
        keys
    ) > scope.discovery_max_depth


def _not_found_warning(path: str, kind: str) -> InspectWarning:
    if kind == "excel":
        message = (
            f"The configured table {path} is not a sheet or a named table of "
            "this workbook. Set config.structure.dataset_path to one that exists."
        )
    else:
        message = (
            f"The configured collection {path} is not an array of this source. "
            "Set config.structure.dataset_path to a collection that exists."
        )
    return InspectWarning(
        code="configured_path_not_found", level="warning", message=message, path=path
    )


def save_inspection(
    source: str | Path,
    document: InspectDocument,
    *,
    reset_config: bool = False,
    force: bool = False,
) -> tuple[Path, InspectDocument]:
    """Write the visible Inspect file of ``source``.

    Returns its path and the document as written: a re-inspection keeps the
    ``config`` of the existing file and may add warnings of its own. A kept
    ``config`` that omits keys shows their defaults in the document, while the
    file holds it as the user wrote it.

    A first inspection writes the document as it is. Re-inspecting replaces
    ``inspect``, ``source``, ``detection`` and ``warnings`` and keeps the
    ``config`` of the existing file as a value (``reset_config`` takes the
    proposed one instead). An existing file that is not valid is never
    replaced, unless ``force`` (design 12.3). The write is atomic.
    """
    path = inspect_path(source)
    existing: VisibleInspect | None = None
    # A dangling link is a file that cannot be read, not an absent one.
    if path.exists() or path.is_symlink():
        try:
            existing = read_visible_inspect(path)
        except ConfigurationError:
            if not force:
                raise
    if existing is not None and existing.kind != document.inspect.kind:
        if not force:
            raise ConfigurationError(
                f"Inspect file {path} is of kind {existing.kind!r} and this source "
                f"is inspected as {document.inspect.kind!r}. Replace it with "
                "`tabalyst inspect --force`."
            )
        existing = None
    config: dict[str, Any] | None = None
    written = document
    warnings = list(document.warnings)
    if existing is not None:
        if existing.recorded_name not in (None, document.source.name):
            warnings.append(
                InspectWarning(
                    code="source_name_mismatch",
                    level="info",
                    message=(
                        f"The Inspect file was written for {existing.recorded_name}, "
                        f"not {document.source.name}; its config still applies."
                    ),
                    path=existing.recorded_name,
                )
            )
        if not reset_config:
            config = existing.document["config"]
            written = document.model_copy(update={"config": existing.config})
            chosen = existing.config.structure.dataset_path
            known = {item.path for item in document.detection.candidates}
            if (
                chosen is not None
                and chosen not in known
                and not _cannot_be_judged(chosen, document)
            ):
                warnings.append(_not_found_warning(chosen, document.inspect.kind))
    written = written.model_copy(update={"warnings": warnings})
    try:
        write_text_atomic(path, inspect_text(written, config=config))
    except OSError as exc:
        raise ReportError(f"Cannot write Inspect file {path}: {exc}") from exc
    return path, written


def write_inspection(
    source: str | Path,
    document: InspectDocument,
    *,
    reset_config: bool = False,
    force: bool = False,
) -> Path:
    """``save_inspection`` that returns only the path of the file written."""
    return save_inspection(
        source, document, reset_config=reset_config, force=force
    )[0]


# The automatic cache -----------------------------------------------------


def read_inspect_cache(path: Path) -> InspectDocument | None:
    """The cached document, or ``None`` when it is absent, unreadable, invalid
    or written by another version of Tabalyst or of the format (design 12.4).

    Whether it describes the current source is the caller's check.
    """
    try:
        document = InspectDocument.model_validate_json(path.read_bytes())
    except (OSError, ValueError):
        return None
    return document if document.inspect.tabalyst_version == __version__ else None


def write_inspect_cache(
    location: StorageLocation, source: Path, document: InspectDocument
) -> str | None:
    """Replace the cache of ``source``; return a sentence when it could not be
    written. The cache is disposable: a failure is never an error."""
    path = location.shared_inspect_path(source)
    try:
        with workspace_writer(location):
            write_text_atomic(path, inspect_text(document))
    except (OSError, ReportError) as exc:
        return f"Could not write the Inspect cache {path}: {exc}"
    return None

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""``inspect_source``: read one JSON source and describe it (design inspect 8).

Reads and writes nothing else: no file, no cache. Persistence and the
resolution of the configuration layers are other lots.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from tabalyst._version import __version__
from tabalyst.errors import ConfigurationError, InputError
from tabalyst.inspector.json_inspect import parameters
from tabalyst.inspector.json_inspect.detect import (
    Candidate,
    Choice,
    JsonlCounts,
    pass_json_events,
    pass_jsonl_lines,
    select,
)
from tabalyst.inspector.models import Candidate as CandidateModel
from tabalyst.inspector.models import (
    DetectionScope,
    InspectConfig,
    InspectDocument,
    InspectInfo,
    InspectSource,
    InspectWarning,
    JsonDetection,
    LineCounts,
    Location,
    Observation,
    RootInfo,
    ScopeLimits,
    Selection,
)
from tabalyst.progress import (
    ProgressCallback,
    ProgressPhase,
    byte_progress,
    emit_progress,
)
from tabalyst.scanner.config import ScanConfig, SourceFormat, resolve_config_defaults
from tabalyst.scanner.identity import source_format_of
from tabalyst.scanner.readers.json_reader import JsonEvents
from tabalyst.scanner.readers.jsonl_reader import JsonlLines

# Candidates listed in a warning message.
_LISTED = 5


def inspect_source(
    source: str | Path,
    *,
    scan_config: ScanConfig | None = None,
    on_progress: ProgressCallback | None = None,
) -> InspectDocument:
    """Inspect a ``.json``, ``.jsonl`` or ``.ndjson`` source.

    ``scan_config`` is the effective configuration below the visible Inspect
    file (design 5.3): it gives the discovery depth, the error policy and the
    flatten rules that seed ``config``, the limit of a JSONL line and the
    number of located lines. Its ``json.collections`` plays no part: the
    detected selection is what ``config`` proposes.

    Raises ``InputError`` for an unreadable, empty or invalid source and
    ``ConfigurationError`` for a source Inspect does not know (CSV).
    """
    path = Path(source)
    try:
        stat = path.stat()
    except OSError as exc:
        raise InputError(f"Cannot read source {path}: {exc}") from exc
    if not path.is_file():
        raise InputError(f"Source does not exist or is not a file: {path}")
    source_format = source_format_of(path)
    if source_format == "csv":
        raise ConfigurationError(
            f"Inspect reads .json, .jsonl and .ndjson sources, not {path.name}. "
            "There is no CSV Inspect yet."
        )
    config = ScanConfig() if scan_config is None else scan_config
    emit_progress(
        on_progress, path, ProgressPhase.READING, bytes_read=0, bytes_total=stat.st_size
    )
    on_bytes = byte_progress(on_progress, path, stat.st_size)
    counts: JsonlCounts | None = None
    if source_format == "json":
        events = JsonEvents(path, on_bytes)
        found = pass_json_events(iter(events), config.json_.discovery_max_depth)
        summary = events.summary()
        root, candidates, truncated = found.root, found.candidates, found.truncated
    else:
        lines = JsonlLines(path, config.limits.max_line_bytes, on_bytes)
        candidate, counts = pass_jsonl_lines(lines, config.errors.max_locations)
        counts.blank = lines.blank
        summary = lines.summary()
        root, candidates, truncated = "lines", [candidate], False
    choice = select(root, candidates, truncated=truncated, jsonl=counts is not None)

    document = InspectDocument(
        inspect=InspectInfo(
            kind="json",
            tabalyst_version=__version__,
            generated_at=datetime.now(UTC).replace(microsecond=0),
        ),
        source=InspectSource(
            name=path.name,
            format=summary.format,
            size_bytes=summary.bytes_read,
            sha256=summary.sha256,
        ),
        detection=JsonDetection(
            scope=DetectionScope(
                limits=ScopeLimits(
                    records=parameters.RECORDS_OBSERVED,
                    fields=parameters.FIELDS_OBSERVED,
                ),
                discovery_max_depth=config.json_.discovery_max_depth,
                candidates="truncated" if truncated else None,
            ),
            root=RootInfo(type=root),
            candidates=[_candidate_model(item) for item in candidates],
            selection=Selection(path=choice.path, basis=choice.basis, over=choice.over),
            lines=None if counts is None else _line_counts(counts),
        ),
        warnings=_warnings(
            root, candidates, choice, truncated, counts, config, source_format
        ),
        config=_seed_config(config, source_format, choice.path),
    )
    emit_progress(on_progress, path, ProgressPhase.COMPLETE)
    return document


def _candidate_model(item: Candidate) -> CandidateModel:
    return CandidateModel(
        path=item.path,
        elements=item.elements,
        element_types=item.element_types(),
        eligible=item.eligible,
        ineligible_reason=item.ineligible_reason,
        observation=Observation(
            records=item.observed,
            fields=len(item.fields),
            max_depth=item.max_depth,
            nested_objects=item.nested,
            arrays=item.arrays,
            complete=item.complete,
        ),
    )


def _line_counts(counts: JsonlCounts) -> LineCounts:
    objects = counts.read - counts.invalid.count - counts.not_object.count
    return LineCounts(
        read=counts.read,
        blank=counts.blank,
        objects=objects,
        invalid=counts.invalid.count,
        not_object=counts.not_object.count,
    )


def _seed_config(
    config: ScanConfig, source_format: SourceFormat, dataset_path: str | None
) -> InspectConfig:
    """The ``config`` section Inspect proposes (design 5.3): the effective
    rules below the visible file, resolved for the format, plus the detected
    path. Every key is written."""
    base = config.model_copy(
        update={"json_": config.json_.model_copy(update={"collections": None})}
    )
    resolved = resolve_config_defaults(base, source_format)
    return InspectConfig.model_validate(
        {
            "structure": {"dataset_path": dataset_path},
            "flatten": resolved.json_.flatten.model_dump(),
            "arrays": {"mode": resolved.json_.arrays.mode},
            "errors": {"policy": resolved.errors.policy},
        }
    )


# Warnings (design 4.5) -----------------------------------------------------


def _listing(items: list[Candidate]) -> str:
    shown = ", ".join(f"{item.path} ({item.elements})" for item in items[:_LISTED])
    return shown + (", ..." if len(items) > _LISTED else "")


def _warnings(
    root: str,
    candidates: list[Candidate],
    choice: Choice,
    truncated: bool,
    counts: JsonlCounts | None,
    config: ScanConfig,
    source_format: SourceFormat,
) -> list[InspectWarning]:
    out: list[InspectWarning] = []
    if choice.basis == "ambiguous":
        eligible = [item for item in candidates if item.eligible]
        out.append(
            InspectWarning(
                code="ambiguous_collections",
                level="warning",
                message=(
                    f"{len(eligible)} collections are equally plausible: "
                    f"{_listing(eligible)}. None was selected: set "
                    "config.structure.dataset_path to the one to analyze."
                ),
                count=len(eligible),
            )
        )
    elif choice.basis == "no_eligible_candidate":
        reason = (
            "scalar_root"
            if root not in ("object", "array", "lines")
            else ("no_array" if not candidates else "no_eligible_array")
        )
        depth = config.json_.discovery_max_depth
        explanation = {
            "scalar_root": f"the root is a {root}, not an object or an array",
            "no_array": (
                "no array is reachable through object keys at a depth of "
                f"{depth} or less (json.discovery_max_depth)"
            ),
            "no_eligible_array": (
                "the arrays found are empty or hold values that are not objects"
            ),
        }[reason]
        out.append(
            InspectWarning(
                code="no_collection",
                level="warning",
                message=f"No supported collection was found: {explanation}.",
                reason=reason,
            )
        )
    elif truncated:
        out.append(
            InspectWarning(
                code="candidates_truncated",
                level="warning",
                message=(
                    f"More than {len(candidates)} arrays were found; only the first "
                    f"{len(candidates)} are listed, so none was selected. Set "
                    "config.structure.dataset_path to the one to analyze."
                ),
                count=len(candidates),
            )
        )
    ineligible = [item for item in candidates if not item.eligible]
    for item in ineligible[: parameters.MAX_INELIGIBLE_NOTES]:
        out.append(
            InspectWarning(
                code="candidate_not_eligible",
                level="info",
                message=_not_eligible_message(item),
                path=item.path,
                reason=item.ineligible_reason,
            )
        )
    if len(ineligible) > parameters.MAX_INELIGIBLE_NOTES:
        out.append(
            InspectWarning(
                code="candidate_not_eligible_truncated",
                level="info",
                message=(
                    f"{len(ineligible)} candidates are not eligible; only the "
                    f"first {parameters.MAX_INELIGIBLE_NOTES} are described."
                ),
                count=len(ineligible),
            )
        )
    if counts is not None:
        for located, code, many, one in (
            (
                counts.invalid,
                "invalid_lines",
                "lines are not valid JSON or are too long",
                "line is not valid JSON or is too long",
            ),
            (
                counts.not_object,
                "non_object_lines",
                "lines are valid JSON but not objects",
                "line is valid JSON but not an object",
            ),
        ):
            if located.count:
                out.append(
                    InspectWarning(
                        code=code,
                        level="warning",
                        message=f"{located.count} {one if located.count == 1 else many}.",
                        count=located.count,
                        locations=[
                            Location(record=record, line=line)
                            for record, line in located.locations
                        ],
                    )
                )
    return out


def _not_eligible_message(item: Candidate) -> str:
    if item.ineligible_reason == "empty":
        return f"{item.path} has no element."
    return f"{item.path} holds elements that are not objects."

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Sources, exclusions and planned outputs of a Dedup batch (design dedup 7)."""

import glob
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tabalyst.batch import (
    is_inspect_name,
    is_lock_name,
    output_directory,
    path_key,
    validate_outputs,
)
from tabalyst.dedup.settings import DedupSettings
from tabalyst.errors import ConfigurationError, InputError, ReportError

ExclusionReason = Literal[
    "derived_csv", "dedup_output", "inspect_file", "lock_file", "output_directory"
]

# Matched without case. ``.sample.csv`` is the output of ``tabalyst sample``: the
# other commands do not skip it yet, so Dedup does (design dedup 3, E3).
DERIVED_CSV_SUFFIXES = (
    ".sample.csv",
    ".unique.csv",
    ".duplicates.csv",
    ".duplicates_all.csv",
)
REPORT_SUFFIX = ".dedup.json"
BATCH_REPORT_NAME = "dedup.summary.json"

# The managed outputs of a source, in the order the design lists them.
OUTPUT_KINDS = ("unique", "duplicates", "duplicates_all", "report")
_OUTPUT_SUFFIXES = {
    "unique": ".unique.csv",
    "duplicates": ".duplicates.csv",
    "duplicates_all": ".duplicates_all.csv",
    "report": REPORT_SUFFIX,
}


@dataclass(frozen=True)
class PlannedSource:
    """A source of the batch and the paths of its four managed outputs
    (keys ``unique``, ``duplicates``, ``duplicates_all`` and ``report``)."""

    source: Path
    names: Mapping[str, Path]


@dataclass(frozen=True)
class BatchPlan:
    """What a batch will do, decided before any file is read or written.

    ``excluded`` lists the files a pattern found and Dedup skips, with the reason.
    ``batch_report`` is where ``dedup.summary.json`` goes (design dedup 13.1) and
    ``writes_batch_report`` says whether this invocation writes it at all.
    """

    eligible: tuple[PlannedSource, ...]
    excluded: tuple[tuple[Path, ExclusionReason], ...]
    batch_report: Path
    writes_batch_report: bool


# Whether a managed output is proven to have been published by a Dedup report.
# Lot 7 supplies the real test; until then nothing is owned.
OwnershipTest = Callable[[Path, PlannedSource], bool]


def _nothing_is_owned(path: Path, planned: PlannedSource) -> bool:
    return False


def exclusion_reason(name: str) -> ExclusionReason | None:
    """Why a file found by a pattern is not a source, from its name alone."""
    lowered = name.lower()
    if lowered.endswith(DERIVED_CSV_SUFFIXES):
        return "derived_csv"
    if lowered.endswith(REPORT_SUFFIX) or lowered == BATCH_REPORT_NAME:
        return "dedup_output"
    if is_inspect_name(name):
        return "inspect_file"
    if is_lock_name(name):
        return "lock_file"
    return None


def managed_names(source: Path, destination: Path | None) -> dict[str, Path]:
    """The four managed output paths of ``source``, beside it or in ``destination``."""
    directory = destination if destination is not None else source.parent
    return {
        kind: directory / f"{source.stem}{suffix}"
        for kind, suffix in _OUTPUT_SUFFIXES.items()
    }


def _discover(
    input_specs: Sequence[str | Path], destination: Path | None
) -> tuple[list[Path], list[tuple[Path, ExclusionReason]]]:
    """Expand the specs into sources and exclusions, each file once, in spec order.

    A file given by an explicit path is never excluded, and a file that any spec
    makes eligible stays eligible.
    """
    destination_key = path_key(destination) if destination is not None else None
    found: dict[str, tuple[Path, ExclusionReason | None]] = {}

    def add(path: Path, reason: ExclusionReason | None) -> None:
        key = path_key(path)
        known = found.get(key)
        if known is None or (reason is None and known[1] is not None):
            found[key] = (path, reason)

    for value in input_specs:
        text = os.fspath(value)
        if "**" in text:
            raise ConfigurationError(
                f"Recursive input patterns are not supported yet: {text}"
            )
        if glob.has_magic(text):
            matches = sorted(
                (Path(match) for match in glob.glob(text) if Path(match).is_file()),
                key=path_key,
            )
            if not matches:
                raise InputError(f'Input pattern matched no files: "{text}"')
            # A wildcard in the directory part reaches the output directory without
            # naming it; a literal directory names it on purpose (design dedup 7.2).
            wildcard_directory = glob.has_magic(os.path.dirname(text))
            for path in matches:
                reason = exclusion_reason(path.name)
                if (
                    reason is None
                    and wildcard_directory
                    and destination_key is not None
                    and path_key(path.parent) == destination_key
                ):
                    reason = "output_directory"
                add(path, reason)
        else:
            path = Path(text)
            if not path.exists():
                raise InputError(f"Input file does not exist: {path}")
            if not path.is_file():
                raise InputError(f"Input path is not a file: {path}")
            if is_inspect_name(path.name):
                raise ConfigurationError(
                    f"{path} is an Inspect file, not a source. Give the source it "
                    "describes."
                )
            add(path, None)

    sources = [path for path, reason in found.values() if reason is None]
    excluded = [(path, reason) for path, reason in found.values() if reason is not None]
    return sources, excluded


def _batch_report_directory(
    sources: Sequence[Path], destination: Path | None, found: Sequence[Path]
) -> Path:
    """Where the batch report goes (D3): the output directory, else the folder the
    sources share, else the current directory."""
    if destination is not None:
        return destination
    paths = sources or found
    folders = {path_key(path.parent): path.parent for path in paths}
    if len(folders) == 1:
        return next(iter(folders.values()))
    return Path.cwd()


def _refuse_foreign_outputs(
    planned: Sequence[PlannedSource], is_owned: OwnershipTest
) -> None:
    foreign = [
        path
        for item in planned
        for path in item.names.values()
        if os.path.lexists(path) and not is_owned(path, item)
    ]
    if foreign:
        lines = "\n".join(f"  {path}" for path in foreign)
        raise ReportError(
            "Dedup output already exists and no Tabalyst Dedup report proves it is "
            "one of its results. Use --force to allow replacing it:\n" + lines
        )


def plan_batch(
    input_specs: Sequence[str | Path],
    settings: DedupSettings,
    *,
    is_owned: OwnershipTest = _nothing_is_owned,
) -> BatchPlan:
    """Resolve the inputs and refuse an unsafe batch before any work (design dedup 7).

    A pattern that matches no file is an ``InputError``; one that matches only files
    Dedup skips gives a plan without work. A managed output that is a source or a
    directory is an ``InputError``; two sources mapping to one output, or an existing
    output that ``is_owned`` does not recognize (without ``settings.force``), is a
    ``ReportError``. Nothing is created or written.
    """
    if not input_specs:
        raise ConfigurationError("At least one input file is required.")
    destination = output_directory(settings.output_dir)
    sources, excluded = _discover(input_specs, destination)

    planned = tuple(
        PlannedSource(source=source, names=managed_names(source, destination))
        for source in sources
    )
    # ``force`` never lets an output replace a source, so this check runs first and
    # on its own terms (collisions, directories, sources).
    validate_outputs(
        ((item.source, path) for item in planned for path in item.names.values()),
        sources=sources,
        force=True,
        label="Dedup output",
    )
    if not settings.force:
        _refuse_foreign_outputs(planned, is_owned)

    found = [*sources, *(path for path, _ in excluded)]
    explicit_single = len(input_specs) == 1 and not glob.has_magic(
        os.fspath(input_specs[0])
    )
    return BatchPlan(
        eligible=planned,
        excluded=tuple(excluded),
        batch_report=_batch_report_directory(sources, destination, found)
        / BATCH_REPORT_NAME,
        writes_batch_report=not explicit_single,
    )

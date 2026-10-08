# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Common loader of the Scan base, read from a Scan or from a Report (design 19).

A Report holds the base of a Scan at the same paths, plus a ``report`` block.
``load_base`` gives the same model whichever document it reads, and
``load_document`` also says what the document is and what it can still do.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from tabalyst.config import validation_message
from tabalyst.errors import InputError
from tabalyst.models import FORMAT as REPORT_FORMAT
from tabalyst.models import FORMAT_REVISION as REPORT_REVISION
from tabalyst.models import FORMAT_VERSION as REPORT_VERSION
from tabalyst.models import ReportBlock, ReportProfile
from tabalyst.scan_reuse import (
    UnsupportedScanDocument,
    check_scan_document,
    read_json_document,
    scan_from_document,
)
from tabalyst.scanner.models import (
    FORMAT,
    FORMAT_REVISION,
    FORMAT_VERSION,
    ScanResult,
)


@dataclass(frozen=True)
class Capabilities:
    """What a document can still be used for."""

    # Every field lists the whole sample the scan kept. A Report keeps fewer
    # values (design 19.4): it renders alone, but cannot be replanned.
    complete_samples: bool


@dataclass(frozen=True)
class LoadedDocument:
    """A Scan or a Report read through the common loader."""

    kind: Literal["scan", "report"]
    base: ScanResult
    # The ``report`` block, for a Report.
    report: ReportBlock | None
    capabilities: Capabilities

    def require_complete_samples(self, purpose: str) -> None:
        """Raise ``InputError`` unless the samples are those of the Scan.

        For the computations that read samples (planning, second pass,
        patterns): they take the Scan, never a Report.
        """
        if not self.capabilities.complete_samples:
            raise InputError(
                f"A Report keeps fewer sample values than its Scan, so it cannot "
                f"be used to {purpose}. Use the scan document of the source."
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


def complete_samples(base: ScanResult) -> bool:
    """Whether the base holds every value its samples and their strata sampled,
    and every row of its row samples."""
    return all(
        dataset.records.sample is None
        or dataset.records.sample.kept == dataset.records.sample.of
        for dataset in base.datasets
    ) and all(
        field.values.samples.kept == field.values.samples.of
        and all(
            stratum.kept == stratum.of
            for stratum in (
                field.values.samples.by_length.strata
                if field.values.samples.by_length is not None
                else ()
            )
        )
        for dataset in base.datasets
        for field in dataset.fields
    )


def base_of(profile: ReportProfile) -> ScanResult:
    """The Scan base held by a Report: the same model, facts and identifiers as
    the Scan it was built from, without rounding or filtering."""
    identity = profile.report.base_scan
    return ScanResult(
        format=identity.format,
        format_version=identity.format_version,
        format_revision=identity.format_revision,
        engine=profile.engine,
        status=profile.status,
        run=profile.run,
        source=profile.source,
        config=profile.config,
        config_sha256=profile.config_sha256,
        scope=profile.scope,
        datasets=profile.datasets,
        diagnostics=profile.diagnostics,
        derived=profile.derived,
        observations=profile.observations,
    )


def load_report(document: dict, where: Path | str = "the document") -> ReportProfile:
    """Validate a Report document. A format version or revision other than the
    current one is refused, never converted (design 19.6)."""
    version = (document.get("format_version"), document.get("format_revision"))
    if version != (REPORT_VERSION, REPORT_REVISION):
        raise UnsupportedScanDocument(
            f"Unsupported report {where}: format {version[0]} revision "
            f"{version[1]}; this version of Tabalyst reads format "
            f"{REPORT_VERSION} revision {REPORT_REVISION}. Run tabalyst "
            "report again."
        )
    base_version = (document.get("report") or {}).get("base_scan") or {}
    if (base_version.get("format_version"), base_version.get("format_revision")) != (
        FORMAT_VERSION,
        FORMAT_REVISION,
    ):
        raise UnsupportedScanDocument(
            f"Unsupported report {where}: it holds a Scan base of format "
            f"{base_version.get('format_version')} revision "
            f"{base_version.get('format_revision')}; this version of Tabalyst "
            f"reads the base in format {FORMAT_VERSION} revision "
            f"{FORMAT_REVISION}. Run tabalyst report again."
        )
    try:
        profile = ReportProfile.model_validate(document)
    except ValidationError as exc:
        raise UnsupportedScanDocument(
            f"Invalid report {where}: {validation_message(exc)}. If it was "
            "written by an earlier build of this version, run tabalyst report "
            "again."
        ) from exc
    base = base_of(profile)
    identity = profile.report.base_scan
    if (identity.source_sha256, identity.config_sha256, identity.facts_sha256) != (
        base.source.sha256,
        base.config_sha256,
        facts_sha256(base),
    ):
        raise InputError(
            f"Invalid report {where}: its Scan base does not match the identity "
            "it declares (base_scan). The report was modified; run tabalyst "
            "report again."
        )
    known = {(d.id, f.id) for d in profile.datasets for f in d.fields}
    for projection in profile.report.datasets:
        for column in projection.columns:
            if (projection.id, column.id) not in known:
                raise InputError(
                    f"Invalid report {where}: the column {column.id} of dataset "
                    f"{projection.id} has no field in its Scan base."
                )
    return profile


def load_document(document: Path | str | dict) -> LoadedDocument:
    """Read a Scan or a Report: a path to its JSON file, or its JSON object."""
    if isinstance(document, dict):
        data: object = document
        where: Path | str = "the document"
    else:
        where = Path(document)
        data = read_json_document(where)
    kind = data.get("format") if isinstance(data, dict) else None
    if kind == REPORT_FORMAT:
        profile = load_report(data, where)
        base = base_of(profile)
        return LoadedDocument(
            "report", base, profile.report, Capabilities(complete_samples(base))
        )
    if kind == FORMAT:
        base = scan_from_document(check_scan_document(data, where), where)
        return LoadedDocument("scan", base, None, Capabilities(complete_samples(base)))
    raise InputError(
        f"Not a Tabalyst document: {where} has no format {FORMAT} or "
        f"{REPORT_FORMAT}."
    )


def load_base(document: Path | str | dict) -> ScanResult:
    """The Scan base of a Scan or of a Report, ignoring ``report``."""
    return load_document(document).base

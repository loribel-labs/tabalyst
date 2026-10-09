# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The web page of a scan (design 16.8): the report rendered from the Scan alone.

An explicit ``tabalyst scan`` writes it beside the scan document; a scan that
another command makes by itself (a report, a plan, a sample) writes none. The page
is the one ``tabalyst report --scan`` gives, without the analyses a second pass
would add, and it reads no source.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from tabalyst.batch import write_text_atomic
from tabalyst.config import load_config_layers, settings_from_layer
from tabalyst.errors import ReportError
from tabalyst.report_config import ReportConfig
from tabalyst.report_profile import build_profile
from tabalyst.reporting import render_report
from tabalyst.scanner.models import ScanResult

PAGE_SUFFIX = ".html"


def scan_page_path(source: Path, output: Path | None) -> Path:
    """Where the page of a scan goes: beside the scan document, with the same name
    and the extension ``.html`` (``customers.scan.json`` gives
    ``customers.scan.html``), or beside the source as ``<stem>.scan.html`` when the
    scan is in the shared storage."""
    if output is None:
        return source.with_name(f"{source.stem}.scan{PAGE_SUFFIX}")
    return output.with_suffix(PAGE_SUFFIX)


def write_scan_page(
    result: ScanResult,
    page: Path,
    config_paths: Sequence[Path] = (),
    *,
    scan_path: Path | None = None,
) -> Path:
    """Render ``result`` and write the page at ``page``, replacing it atomically.

    ``scan_path`` is the scan document on disk; when it is given, the analyses of
    its stored second-pass document appear in the page, as in ``tabalyst report
    --scan``. Raises ``ReportError`` when the page cannot be built or written; the
    scan itself is not affected.
    """
    top_level, _ = load_config_layers(list(config_paths))
    settings = settings_from_layer(top_level)
    try:
        if scan_path is not None:
            from tabalyst.service import _profile_from_scan

            profile, _ = _profile_from_scan(
                scan_path, result, settings, {}, None, started=0.0
            )
        else:
            profile = build_profile(result, ReportConfig.from_settings(settings, result.config))
        html = render_report(profile)
        write_text_atomic(page, html)
    except OSError as exc:
        raise ReportError(f"Cannot write scan page {page}: {exc}") from exc
    return page

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Effective settings of a report: presentation settings and its scan.

The report is built on Tabalyst Scan: every analysis setting, CSV reading
included, comes from the ``scan`` object of the configuration files. The
top-level settings only shape the presentation (preview, string lengths,
value examples).
"""

from collections.abc import Iterable
from pathlib import Path

from pydantic import Field

from tabalyst.config import (
    PresentationSettings,
    load_config_layers,
    settings_from_layer,
)
from tabalyst.errors import ConfigurationError
from tabalyst.scanner.config import ScanConfig, scan_config_from_layer


class ReportConfig(PresentationSettings):
    scan: ScanConfig = Field(default_factory=ScanConfig)


def _check_csv_settings(
    top_level: dict, scan: ScanConfig, overridden: set[str]
) -> None:
    """Reject a top-level ``csv`` value that differs from ``scan.csv``, except
    for settings given explicitly, which always win.

    The top-level ``csv`` settings serve ``tabalyst sample``; the report reads
    ``scan.csv``. A file written before the report moved onto Scan would
    otherwise be read with other CSV settings, silently.
    """
    effective = scan.csv.model_dump()
    for key, value in top_level.get("csv", {}).items():
        if key not in overridden and effective[key] != value:
            raise ConfigurationError(
                f"Invalid configuration: csv.{key} is {value!r} but "
                f"scan.csv.{key} is {effective[key]!r}. The report "
                "reads its CSV settings from scan.csv; the top-level csv "
                "settings apply to tabalyst sample only. Set scan.csv too."
            )


def resolve_report_config(
    paths: Iterable[Path] = (),
    *,
    separator: str | None = None,
    encoding: str | None = None,
) -> ReportConfig:
    """Resolve the report settings of the configuration layers.

    Presentation settings come from the top level of each file, the scan
    settings from its ``scan`` object, with the explicit CSV options on top
    (design section 15).
    """
    top_level, scan_layer = load_config_layers(paths)
    settings = settings_from_layer(top_level)
    scan = scan_config_from_layer(scan_layer, delimiter=separator, encoding=encoding)
    overridden = {
        key
        for key, value in (("delimiter", separator), ("encoding", encoding))
        if value is not None
    }
    _check_csv_settings(top_level, scan, overridden)
    return ReportConfig(
        **settings.model_dump(exclude={"csv"}),
        scan=scan,
    )

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contract tests for Tabalyst Scan, enabled lot by lot.

Each test declares the implementation lot that provides its behavior with
``@pytest.mark.lot("1a")``. Tests of lots missing from ``ENABLED_LOTS`` are
skipped, so the suite stays green while the engine is built. Add a lot here
when its implementation starts; see the Scan plan of the maintainer.

The expectations follow ``docs/dev/scan/design.md``. Changing one requires
updating the design document in the same lot.
"""

import pytest
from report_gate import ENABLED_LOTS as REPORT_ENABLED_LOTS
from scan_json_gate import ENABLED_LOTS as SCAN_JSON_ENABLED_LOTS

# Contract tests of the Scan and JSON work (plan 2026-10-06) are gated by
# ``scan_json_gate.py``, kept apart from the lots below because their names
# overlap: a test of a lot that is not enabled is a strict expected failure.

ENABLED_LOTS: set[str] = {"1a", "1b", "2a", "2b", "3a", "3b", "5a", "5b", "5c", "5d", "6"}


def pytest_collection_modifyitems(config, items):
    for item in items:
        sj_marker = item.get_closest_marker("scan_json_lot")
        if sj_marker is not None and sj_marker.args[0] not in SCAN_JSON_ENABLED_LOTS:
            item.add_marker(
                pytest.mark.xfail(
                    strict=True,
                    reason=f"Scan and JSON lot {sj_marker.args[0]} is not implemented yet",
                )
            )
        report_marker = item.get_closest_marker("report_lot")
        if report_marker is not None and report_marker.args[0] not in REPORT_ENABLED_LOTS:
            item.add_marker(
                pytest.mark.skip(
                    reason=f"Report overview lot {report_marker.args[0]} is not implemented yet"
                )
            )
        marker = item.get_closest_marker("lot")
        if marker is not None and marker.args[0] not in ENABLED_LOTS:
            item.add_marker(
                pytest.mark.skip(
                    reason=f"Scan lot {marker.args[0]} is not implemented yet"
                )
            )

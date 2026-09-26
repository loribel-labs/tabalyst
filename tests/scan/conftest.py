"""Contract tests for Tabalyst Scan, enabled lot by lot.

Each test declares the implementation lot that provides its behavior with
``@pytest.mark.lot("1a")``. Tests of lots missing from ``ENABLED_LOTS`` are
skipped, so the suite stays green while the engine is built. Add a lot here
when its implementation starts; see ``docs/dev/scan/plan.md``.

The expectations follow ``docs/dev/scan/design.md``. Changing one requires
updating the design document in the same lot.
"""

import pytest

ENABLED_LOTS: set[str] = set()


def pytest_collection_modifyitems(config, items):
    for item in items:
        marker = item.get_closest_marker("lot")
        if marker is not None and marker.args[0] not in ENABLED_LOTS:
            item.add_marker(
                pytest.mark.skip(
                    reason=f"Scan lot {marker.args[0]} is not implemented yet"
                )
            )

"""Contract tests for JSON Inspect, enabled lot by lot.

Each test declares the implementation lot that provides its behavior with
``@pytest.mark.inspect_lot("JI-2")``. Tests of lots missing from
``ENABLED_LOTS`` are skipped, so the suite stays green while the feature is
built. Add a lot here when its implementation starts; see the plan in
``tabalyst-gb`` (``IN-PROGRESS/2026-09-30-Plan-JSON-Inspect.md``).

The expectations follow ``docs/dev/inspect/design.md``. Changing one requires
updating the design document in the same lot. The marker is not ``lot``:
``tests/scan`` uses it for the Scan lots.
"""

import pytest

ENABLED_LOTS: set[str] = {"JI-2", "JI-3", "JI-4", "JI-5", "JI-6", "JI-7", "JI-8"}


def pytest_collection_modifyitems(config, items):
    for item in items:
        marker = item.get_closest_marker("inspect_lot")
        if marker is not None and marker.args[0] not in ENABLED_LOTS:
            item.add_marker(
                pytest.mark.skip(
                    reason=f"Inspect lot {marker.args[0]} is not implemented yet"
                )
            )

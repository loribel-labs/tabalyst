# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Reference corpus of the hierarchical pattern discovery, enabled block by block.

A test of the engine declares the block that provides its behavior with
``@pytest.mark.pattern_lot("B4")`` (blocks of the specification, section 14:
B4 discovery and declared keys, B5 validation). Tests of blocks missing from
``ENABLED_LOTS`` are skipped, "to enable" once the block delivers; bind
``pattern_adapter.py`` in the same change. Tests without the marker check the
corpus, its expectations and the hand calculations, and always run.

The marker is not ``lot``: ``tests/scan`` uses it for the Scan lots.
"""

import pytest

ENABLED_LOTS: set[str] = set()


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "pattern_lot(name): block of the pattern discovery that provides the "
        "tested behavior (B4, B5)",
    )


def pytest_collection_modifyitems(config, items):
    for item in items:
        marker = item.get_closest_marker("pattern_lot")
        if marker is not None and marker.args[0] not in ENABLED_LOTS:
            item.add_marker(
                pytest.mark.skip(
                    reason=f"to enable: pattern block {marker.args[0]} is not "
                    "implemented yet"
                )
            )

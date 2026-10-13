# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Reference corpus and contract of the hierarchical pattern discovery, enabled lot
by lot.

A test of the engine declares the lot of the Patterns plan that provides its
behavior with ``@pytest.mark.pattern_lot("P4")``: P2 eligibility, P3 families and
lengths, P4 facets and score, P5 declared keys, P6 validation, P7 consumers
(``check_scan``, cache, observations). Tests of lots missing from ``ENABLED_LOTS``
are skipped, "to enable" once the lot delivers; add the lot to ``ENABLED_LOTS`` and
bind ``pattern_adapter.py`` in the same change. Tests without the marker check the
corpus, its expectations and the hand calculations, and always run.

The marker is not ``lot``: ``tests/scan`` uses it for the Scan lots.
"""

import pytest

KNOWN_LOTS = frozenset({"P2", "P3", "P4", "P5", "P6", "P7"})
ENABLED_LOTS: set[str] = {"P2", "P3"}


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "pattern_lot(name): lot of the pattern discovery that provides the "
        "tested behavior (P2 to P7)",
    )


def pytest_collection_modifyitems(config, items):
    for item in items:
        marker = item.get_closest_marker("pattern_lot")
        if marker is not None and marker.args[0] not in KNOWN_LOTS:
            raise pytest.UsageError(
                f"{item.nodeid}: unknown pattern lot {marker.args[0]!r}"
            )
        if marker is not None and marker.args[0] not in ENABLED_LOTS:
            item.add_marker(
                pytest.mark.skip(
                    reason=f"to enable: pattern lot {marker.args[0]} is not "
                    "implemented yet"
                )
            )

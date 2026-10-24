# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contract tests of the identifier uniqueness work, enabled lot by lot.

Each test declares the lot that provides its behavior with ``@pytest.mark.uid_lot("1")``
and the requirements it covers with ``@pytest.mark.uid_t("T01")``. A lot missing from
``ENABLED_LOTS`` is skipped, so the suite stays green while the feature is built. A lot
enables itself by uncommenting its own line (one lot per line, blank lines between, so
that lots built in parallel do not conflict when merged). The contract is
``docs/dev/report/identifier-uniqueness.md``; the plan is in ``tabalyst-gb``
(``KANBAN/05-PROGRESS/2026-10-23-tabalyst-unique-id-plan.md``).
"""

import pytest

ENABLED_LOTS: set[str] = {
    "0",  # contract, oracle, properties

    "1",  # pure rule

    "2",  # Dedup proof

    "3",  # Report integration

    "4",  # HTML

    "6",  # Deep count of the copies of rows
}


def pytest_collection_modifyitems(config, items):
    for item in items:
        marker = item.get_closest_marker("uid_lot")
        if marker is not None and marker.args[0] not in ENABLED_LOTS:
            item.add_marker(
                pytest.mark.skip(
                    reason=f"Unique ID lot {marker.args[0]} is not implemented yet"
                )
            )

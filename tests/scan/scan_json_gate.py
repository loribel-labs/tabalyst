# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Which lots of the Scan and JSON work are delivered.

Contract tests carry ``@pytest.mark.scan_json_lot("<lot>")``. A test of a lot
missing from ``ENABLED_LOTS`` is a strict expected failure (see
``conftest.py``): when the lot delivers its behavior the test passes
unexpectedly and fails the suite, so the lot must add its name here. Lot
``0`` tests describe behavior that exists today and must keep passing.
"""

ENABLED_LOTS: set[str] = {"0", "1a", "1b", "1c", "2a", "2b", "2c", "3a", "3b", "4a", "4b", "5", "6a", "6b", "7a", "7b", "7c", "8a", "8b", "9", "10a"}

KNOWN_LOTS = frozenset(
    {
        "0", "1a", "1b", "1c", "1d", "2a", "2b", "2c", "3a", "3b", "4a", "4b",
        "5", "6a", "6b", "7a", "7b", "7c", "8a", "8b", "9", "10a", "10b", "11",
    }
)  # fmt: skip

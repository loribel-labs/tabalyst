# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Which lots of the Report overview work are delivered.

Contract tests of ``test_contract_summary.py`` carry
``@pytest.mark.report_lot("<lot>")``. A test of a lot missing from
``ENABLED_LOTS`` is skipped (see ``conftest.py``): it imports modules the lot
creates. A lot adds its name here when it starts. The contract is
``docs/dev/report/summary-table.md``.
"""

ENABLED_LOTS: set[str] = {"R1a"}

KNOWN_LOTS = frozenset(
    {"R1a", "R1b", "R2", "R3", "R4", "R5", "R6a", "R6b", "R7", "R8", "R9a", "R9b"}
)

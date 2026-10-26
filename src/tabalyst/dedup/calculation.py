# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The versions of the counts of the copies of rows, apart from the engine so the planner can read them."""

# Changes with any change of what the count means (identity, ceilings, order of the checks). The
# analyzer ``duplicate_rows_count`` takes it as its version, so stored results of an older count
# are stale (Unique ID lot 8, cahier 12.5).
CALCULATION_VERSION = 1

# The same for the light count of the copies of the rows that have no ID (``missing_id_copies``,
# Unique ID lot 10): what it counts, the identity of the rows, the order of the checks.
MISSING_CALCULATION_VERSION = 1

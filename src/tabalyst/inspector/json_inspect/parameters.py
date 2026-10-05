# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Measured parameters of JSON Inspect detection (design inspect section 15).

Every value comes from a measurement that the design records, and was decided
by the maintainer. Tests import these names and build their data from them.
"""

# First records of each candidate used for the detail observation.
RECORDS_OBSERVED = 1_000
# Distinct field paths tracked per candidate.
FIELDS_OBSERVED = 1_000
# Candidates kept per source.
MAX_CANDIDATES = 100
# Element count ratio from which the largest eligible candidate stands out.
DOMINANCE_RATIO = 10
# Ineligible candidates described one by one in the warnings; the rest is counted.
MAX_INELIGIBLE_NOTES = 10

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tabalyst Dedup: exact deduplication of the rows of CSV files.

The contract is ``docs/dev/dedup/design.md``. Modules are imported where they
are used; this package imports none of them, so loading it stays free.
"""

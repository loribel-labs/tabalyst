# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tabalyst Scan: the streaming analysis engine of Tabalyst.

The contract is ``docs/dev/scan/design.md``. The public entry points are
``tabalyst.scan()``, ``tabalyst.generate_scans()`` and the ``tabalyst scan``
command.
"""

from tabalyst.scanner.api import scan
from tabalyst.scanner.config import ScanConfig
from tabalyst.scanner.models import ScanResult

__all__ = ["ScanConfig", "ScanResult", "scan"]

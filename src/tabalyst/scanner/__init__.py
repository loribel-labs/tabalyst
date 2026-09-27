"""Tabalyst Scan: streaming analysis engine, beside the current pandas engine.

The contract is ``docs/dev/scan/design.md``. The public entry points are
``tabalyst.scan()``, ``tabalyst.generate_scans()`` and the ``tabalyst scan``
command.
"""

from tabalyst.scanner.api import scan
from tabalyst.scanner.config import ScanConfig
from tabalyst.scanner.models import ScanResult

__all__ = ["ScanConfig", "ScanResult", "scan"]

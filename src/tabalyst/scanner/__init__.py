"""Tabalyst Scan: streaming analysis engine, beside the current pandas engine.

The contract is ``docs/dev/scan/design.md``. The engine is built in lots and is
not part of the documented public API yet.
"""

from tabalyst.scanner.api import scan
from tabalyst.scanner.config import ScanConfig
from tabalyst.scanner.models import ScanResult

__all__ = ["ScanConfig", "ScanResult", "scan"]

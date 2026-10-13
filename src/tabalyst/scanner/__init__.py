# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tabalyst Scan: the streaming analysis engine of Tabalyst.

The contract is ``docs/dev/scan/design.md``. The public entry points are
``tabalyst.scan()``, ``tabalyst.generate_scans()`` and the ``tabalyst scan``
command.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tabalyst.scanner.api import scan as scan
    from tabalyst.scanner.config import ScanConfig as ScanConfig
    from tabalyst.scanner.models import ScanResult as ScanResult

# Loaded on first use (PEP 562): a scan worker imports modules of this package
# and must not pay for the whole engine and its services.
_LAZY: dict[str, str] = {
    "ScanConfig": "tabalyst.scanner.config",
    "ScanResult": "tabalyst.scanner.models",
    "scan": "tabalyst.scanner.api",
}


def __getattr__(name: str) -> object:
    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    value = getattr(import_module(module), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *_LAZY})


__all__ = ["ScanConfig", "ScanResult", "scan"]

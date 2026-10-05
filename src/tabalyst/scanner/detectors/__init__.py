# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Detectors of Tabalyst Scan (design section 12)."""

from tabalyst.scanner.detectors.base import (
    Classification,
    Detector,
    DetectorAccumulator,
)
from tabalyst.scanner.detectors.registry import DetectorRegistry, default_registry

__all__ = [
    "Classification",
    "Detector",
    "DetectorAccumulator",
    "DetectorRegistry",
    "default_registry",
]

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

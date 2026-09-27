"""Domain names and counted names shared by the ``email`` and ``url``
detectors (``docs/dev/scan/detectors.md``).
"""

from __future__ import annotations

import re

from tabalyst.scanner.exposure import ExposureGate

MAX_DOMAIN_LENGTH = 253
_ASCII_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")


def _is_label(label: str) -> bool:
    if not 1 <= len(label) <= 63 or label[0] == "-" or label[-1] == "-":
        return False
    return all(char.isalpha() or "0" <= char <= "9" or char == "-" for char in label)


def _is_ascii_digits(text: str) -> bool:
    return text.isascii() and text.isdigit()


def is_domain(name: str, *, single_label: bool = False) -> bool:
    """Labels of letters of any script, ASCII digits and inner ``-``, 1 to 63
    characters each, at most 253 characters, a last label that is not made of
    digits only; at least two labels unless ``single_label``."""
    if not name or len(name) > MAX_DOMAIN_LENGTH:
        return False
    labels = name.split(".")
    if len(labels) < 2 and not single_label:
        return False
    if name.isascii():
        fullmatch = _ASCII_LABEL.fullmatch
        if not all(fullmatch(label) for label in labels):
            return False
    elif not all(map(_is_label, labels)):
        return False
    return not _is_ascii_digits(labels[-1])


class NameCounts:
    """Lowercased names with exact counts, up to ``limit`` distinct names."""

    __slots__ = ("counts", "limit", "max_listed", "overflow")

    def __init__(self, limit: int, max_listed: int) -> None:
        self.counts: dict[str, int] = {}
        self.limit = limit
        self.max_listed = max_listed
        self.overflow = False

    def add(self, name: str, count: int) -> None:
        counts = self.counts
        if name in counts:
            counts[name] += count
        elif len(counts) < self.limit:
            counts[name] = count
        else:
            self.overflow = True

    def block(self, gate: ExposureGate) -> dict[str, object]:
        if self.overflow:
            envelope: dict[str, object] = {
                "status": "limited",
                "reason": "max_tracked",
                "limit": self.limit,
            }
            # Distinct raw names do not prove distinct masks.
            if gate.mode != "mask":
                envelope["lower_bound"] = self.limit + 1
            return envelope
        exposed = gate.counts(self.counts.items())
        distinct = len(exposed) if gate.mode == "mask" else len(self.counts)
        ranked = sorted(exposed.items(), key=lambda item: (-item[1], item[0]))
        listed = [
            {"value": name, "count": count} for name, count in ranked[: self.max_listed]
        ]
        return {
            "status": "complete",
            "value": {
                "distinct": distinct,
                "listed": listed,
                "truncated": len(listed) < distinct,
            },
        }

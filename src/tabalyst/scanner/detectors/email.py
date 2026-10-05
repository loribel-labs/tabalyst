# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Email address detector (``docs/dev/scan/detectors.md``).

Only a bare address (``addr-spec``) with a dot-atom local part is recognized.
Addresses identify people, so the detector is sensitive: its fields are
masked by default (design 12.8).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from tabalyst.scanner.detectors.base import (
    Classification,
    Detector,
    DetectorAccumulator,
)
from tabalyst.scanner.detectors.names import NameCounts, is_domain
from tabalyst.scanner.exposure import ExposureGate

MAX_LOCAL_LENGTH = 64
_ATOM = r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+"
_DOT_ATOM = re.compile(rf"{_ATOM}(?:\.{_ATOM})*")
# URLs (user information, paths such as ``www.x.org/a@b.org``) and display
# names such as ``Jane <jane@x.org>``.
_EXCLUDED_FROM_LOCAL = re.compile(r"[:/<>]")
_EXCLUDED_FROM_DOMAIN = re.compile(r"[/?#:<>\[\]@]")
_TOO_LONG = Classification("invalid", reason="local_part_too_long")
_BAD_LOCAL = Classification("invalid", reason="invalid_local_part")
_BAD_DOMAIN = Classification("invalid", reason="invalid_domain")


def _candidate_domain(domain: str) -> bool:
    """A dot and none of the characters that end a domain in URLs, display
    names and address literals; other errors, such as a space, make the
    value invalid."""
    return "." in domain and _EXCLUDED_FROM_DOMAIN.search(domain) is None


class EmailDetector(Detector):
    id = "email"
    family = "contact"
    sensitive = True
    max_input_length = 254

    def __init__(self, settings: Mapping[str, object]) -> None:
        super().__init__(settings)
        self.max_tracked = settings.get("max_tracked_domains", 10_000)
        self.max_listed = settings.get("max_listed_domains", 20)

    def classify(self, value: str) -> Classification | None:
        if "@" not in value:  # the most frequent case, cheaper than a shape
            return None
        local, _, domain = value.partition("@")
        if (
            not local
            or _EXCLUDED_FROM_LOCAL.search(local) is not None
            or not _candidate_domain(domain)
        ):
            return None
        if len(local) > MAX_LOCAL_LENGTH:
            return _TOO_LONG
        if _DOT_ATOM.fullmatch(local) is None:
            return _BAD_LOCAL
        if not is_domain(domain):
            return _BAD_DOMAIN
        return Classification("matched", value=domain.lower())

    def classify_many(self, values: Sequence[str]) -> list[Classification | None]:
        classify = self.classify
        return [classify(value) if "@" in value else None for value in values]

    def accumulator(self) -> EmailAccumulator:
        return EmailAccumulator(NameCounts(self.max_tracked, self.max_listed))


class EmailAccumulator(DetectorAccumulator):
    __slots__ = ("domains",)
    ignores_unmatched = True

    def __init__(self, domains: NameCounts) -> None:
        self.domains = domains

    def add(
        self, value: str, classification: Classification | None, count: int
    ) -> None:
        if classification is not None and classification.state == "matched":
            self.domains.add(classification.value, count)

    def details(self, gate: ExposureGate) -> dict[str, object]:
        return {"domains": self.domains.block(gate)}

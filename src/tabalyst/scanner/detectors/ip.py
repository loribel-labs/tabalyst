# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""IP address detector (``docs/dev/scan/detectors.md``).

IPv4 addresses in dotted-decimal notation (``ipv4``) and the IPv6 text forms
of RFC 4291 (``ipv6``). Syntax only: addresses are never checked against
assigned ranges (EF32). An IP address can identify a subscriber or a device,
so the detector is sensitive: its fields are masked by default (design 12.8).
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Mapping, Sequence

from tabalyst.scanner.detectors.base import (
    Classification,
    Detector,
    DetectorAccumulator,
)
from tabalyst.scanner.exposure import ExposureGate

DEFAULT_VERSIONS = ("ipv4", "ipv6")
# Shortest and longest accepted forms: ``::`` and
# ``ffff:ffff:ffff:ffff:ffff:ffff:255.255.255.255``.
MIN_LENGTH = 2
MAX_LENGTH = 45
_EDGE = frozenset("0123456789abcdefABCDEF:")

_IPV4 = re.compile(r"[0-9]{1,3}(?:\.[0-9]{1,3}){3}")
_IPV6_CHARACTERS = re.compile(r"[0-9A-Fa-f:.]+")
_GROUP = re.compile(r"[0-9A-Fa-f]{1,4}")

_LEADING_ZERO = Classification("invalid", reason="invalid_leading_zero")
_BAD_OCTET = Classification("invalid", reason="invalid_octet")
_BAD_COMPRESSION = Classification("invalid", reason="invalid_compression")
_BAD_GROUP = Classification("invalid", reason="invalid_group")
_BAD_GROUP_COUNT = Classification("invalid", reason="invalid_group_count")
_IPV4_MATCHED = Classification("matched", format="ipv4", value="ipv4")
_IPV6_MATCHED = Classification("matched", format="ipv6", value="ipv6")
_IPV6_COMPRESSED = Classification("matched", format="ipv6_compressed", value="ipv6")
_IPV6_IPV4 = Classification("matched", format="ipv6_ipv4", value="ipv6")


def _ipv4_error(address: str) -> Classification | None:
    """The invalid classification of an IPv4 candidate, ``None`` when valid."""
    for group in address.split("."):
        if len(group) > 1 and group[0] == "0":
            return _LEADING_ZERO
        if int(group) > 255:
            return _BAD_OCTET
    return None


def _ipv4(value: str) -> Classification | None:
    if _IPV4.fullmatch(value) is None:
        return None
    return _ipv4_error(value) or _IPV4_MATCHED


def _ipv6(value: str) -> Classification | None:
    if value.count(":") < 2 or _IPV6_CHARACTERS.fullmatch(value) is None:
        return None
    compressed = "::" in value
    groups = value.split(":")
    # Times (``22:00:00``) and MAC addresses have fewer than eight groups.
    if not compressed and len(groups) + ("." in groups[-1]) < 8:
        return None
    if value.count("::") > 1 or ":::" in value:
        return _BAD_COMPRESSION
    if compressed:
        head, _, tail = value.partition("::")
        groups = (head.split(":") if head else []) + (tail.split(":") if tail else [])
    embedded = None
    last = len(groups) - 1
    for index, group in enumerate(groups):
        if "." in group:
            # Only the last group of the value, never before ``::``.
            if index != last or value[-1] == ":" or _IPV4.fullmatch(group) is None:
                return _BAD_GROUP
            embedded = group
        elif _GROUP.fullmatch(group) is None:
            return _BAD_GROUP
    count = len(groups) + (embedded is not None)
    if count > (7 if compressed else 8):
        return _BAD_GROUP_COUNT
    if embedded is not None:
        return _ipv4_error(embedded) or _IPV6_IPV4
    return _IPV6_COMPRESSED if compressed else _IPV6_MATCHED


# The ranges that give an address its class (design 20.35), written out so the
# class does not follow the version of the library. The first range an address is
# in decides; the others are public.
_CLASS_RANGES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("unspecified", ("0.0.0.0/32", "::/128")),
    ("loopback", ("127.0.0.0/8", "::1/128")),
    ("private", ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")),
    ("shared", ("100.64.0.0/10",)),
    ("link_local", ("169.254.0.0/16", "fe80::/10")),
    ("multicast", ("224.0.0.0/4", "ff00::/8")),
    (
        "reserved",
        (
            "0.0.0.0/8",
            "192.0.0.0/24",
            "192.0.2.0/24",
            "192.88.99.0/24",
            "198.18.0.0/15",
            "198.51.100.0/24",
            "203.0.113.0/24",
            "240.0.0.0/4",
            "2001:db8::/32",
        ),
    ),
)
_CLASS_NETWORKS = tuple(
    (name, tuple(ipaddress.ip_network(network) for network in networks))
    for name, networks in _CLASS_RANGES
)
_GLOBAL_V6 = ipaddress.ip_network("2000::/3")
IP_CLASSES = tuple(
    f"{version}_{name}"
    for version in ("ipv4", "ipv6")
    for name in ("public", *(name for name, _ in _CLASS_RANGES))
)


def _ipv4_class(value: str) -> str | None:
    """The class of a dotted address by its first octets, the same ranges as
    ``_CLASS_RANGES`` without building an address object (the common case)."""
    try:
        first, second, third, fourth = map(int, value.split("."))
    except ValueError:
        return None
    if not (0 <= first <= 255 and 0 <= second <= 255 and 0 <= third <= 255 and 0 <= fourth <= 255):
        return None
    if first == 0:
        return "ipv4_unspecified" if second == third == fourth == 0 else "ipv4_reserved"
    if first == 127:
        return "ipv4_loopback"
    if first == 10 or (first == 172 and 16 <= second <= 31) or (first == 192 and second == 168):
        return "ipv4_private"
    if first == 100 and 64 <= second <= 127:
        return "ipv4_shared"
    if first == 169 and second == 254:
        return "ipv4_link_local"
    if 224 <= first <= 239:
        return "ipv4_multicast"
    if (
        first >= 240
        or (first == 192 and (second, third) in ((0, 0), (0, 2), (88, 99)))
        or (first == 198 and (second in (18, 19) or (second, third) == (51, 100)))
        or (first, second, third) == (203, 0, 113)
    ):
        return "ipv4_reserved"
    return "ipv4_public"


def ip_class(value: str) -> str | None:
    """The class of an address the detector matched: its version and what it is
    for (``ipv4_private``, ``ipv6_public``, and so on; one of ``IP_CLASSES``), or
    ``None`` for a text that is no address. An IPv6 address that embeds an IPv4 one
    is told by the IPv6 range it is in."""
    if ":" not in value:
        return _ipv4_class(value)
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return None
    for name, networks in _CLASS_NETWORKS:
        for network in networks:
            if address.version == network.version and address in network:
                return f"ipv{address.version}_{name}"
    # An IPv6 address outside the global unicast block 2000::/3 is not routable.
    if address.version == 6 and address not in _GLOBAL_V6:
        return "ipv6_reserved"
    return f"ipv{address.version}_public"


class IpAddressDetector(Detector):
    id = "ip_address"
    family = "network"
    sensitive = True

    def __init__(self, settings: Mapping[str, object]) -> None:
        super().__init__(settings)
        self.versions = tuple(settings.get("versions", DEFAULT_VERSIONS))
        self._ipv4 = "ipv4" in self.versions
        self._ipv6 = "ipv6" in self.versions

    def classify(self, value: str) -> Classification | None:
        # Exact cheap rejections, cheaper than a shape signature.
        if not MIN_LENGTH <= len(value) <= MAX_LENGTH:
            return None
        if value[0] not in _EDGE or value[-1] not in _EDGE:
            return None
        if ":" in value:
            return _ipv6(value) if self._ipv6 else None
        return _ipv4(value) if self._ipv4 else None

    def classify_many(self, values: Sequence[str]) -> list[Classification | None]:
        classify = self.classify
        return [
            classify(value)
            if MIN_LENGTH <= len(value) <= MAX_LENGTH
            and value[0] in _EDGE
            and value[-1] in _EDGE
            else None
            for value in values
        ]

    def accumulator(self) -> IpAddressAccumulator:
        return IpAddressAccumulator(self.versions)


class IpAddressAccumulator(DetectorAccumulator):
    __slots__ = ("versions",)
    ignores_unmatched = True

    def __init__(self, versions: tuple[str, ...]) -> None:
        self.versions = dict.fromkeys(sorted(versions), 0)

    def add(
        self, value: str, classification: Classification | None, count: int
    ) -> None:
        if classification is not None and classification.state == "matched":
            self.versions[classification.value] += count

    def details(self, gate: ExposureGate) -> dict[str, object]:
        return {"versions": dict(self.versions)}

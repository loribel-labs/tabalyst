"""URL detector (``docs/dev/scan/detectors.md``).

Absolute URLs of configured schemes, and ``www.`` addresses without scheme.
Syntax only: hosts are never resolved (EF32).
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Mapping

from tabalyst.scanner.detectors.base import (
    Classification,
    Detector,
    DetectorAccumulator,
)
from tabalyst.scanner.detectors.names import NameCounts, is_domain
from tabalyst.scanner.exposure import ExposureGate

DEFAULT_SCHEMES = ("http", "https", "ftp")
# Whitespace, controls and ASCII characters outside RFC 3986.
_FORBIDDEN_ASCII = re.compile(r'[\x00-\x20"<>\\^`{|}\x7f]')
_BAD_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_DOTTED_DIGITS = re.compile(r"[0-9.]+")
_BAD_CHARACTER = Classification("invalid", reason="invalid_character")
_BAD_ESCAPE_RESULT = Classification("invalid", reason="invalid_percent_encoding")
_BAD_HOST = Classification("invalid", reason="invalid_host")
_BAD_PORT = Classification("invalid", reason="invalid_port")


def _bad_character(value: str) -> bool:
    if _FORBIDDEN_ASCII.search(value) is not None:
        return True
    if value.isascii():
        return False
    return any(
        not char.isascii() and (char.isspace() or not char.isprintable())
        for char in value
    )


def _valid_host(host: str, single_label: bool) -> bool:
    if host.startswith("["):
        if not host.endswith("]"):
            return False
        try:
            ipaddress.IPv6Address(host[1:-1])
        except ValueError:
            return False
        return True
    if _DOTTED_DIGITS.fullmatch(host) is not None:
        try:
            ipaddress.IPv4Address(host)
        except ValueError:
            return False
        return True
    return is_domain(host, single_label=single_label)


def _valid_port(port: str) -> bool:
    return (
        1 <= len(port) <= 5 and port.isascii() and port.isdigit() and int(port) <= 65535
    )


class UrlDetector(Detector):
    id = "url"
    family = "web"
    max_input_length = 8_192

    def __init__(self, settings: Mapping[str, object]) -> None:
        super().__init__(settings)
        self.schemes = frozenset(settings.get("schemes", DEFAULT_SCHEMES))
        self.www = settings.get("www", True)
        self.max_tracked = settings.get("max_tracked_hosts", 10_000)
        self.max_listed = settings.get("max_listed_hosts", 20)
        # First characters of candidates: cheaper than a shape signature.
        initials = {scheme[0] for scheme in self.schemes}
        if self.www:
            initials.add("w")
        self._initials = frozenset(initials | {char.upper() for char in initials})

    def classify(self, value: str) -> Classification | None:
        if value[:1] not in self._initials:
            return None
        separator = value.find("://")
        scheme = value[:separator]
        if separator > 0 and scheme.isascii() and scheme.lower() in self.schemes:
            name = scheme.lower()
            rest = value[separator + 3 :]
        elif self.www and value[:4].isascii() and value[:4].lower() == "www.":
            name = None
            rest = value
        else:
            return None
        end = len(rest)
        for delimiter in "/?#":
            position = rest.find(delimiter)
            if position != -1 and position < end:
                end = position
        authority = rest[:end]
        if name is None and "@" in authority:
            return None  # an address such as www.jane@example.com
        if _bad_character(value):
            return _BAD_CHARACTER
        if _BAD_ESCAPE.search(value) is not None:
            return _BAD_ESCAPE_RESULT
        host_port = authority.rpartition("@")[2]
        if host_port.startswith("["):
            close = host_port.find("]")
            if close == -1:
                return _BAD_HOST
            host, port_part = host_port[: close + 1], host_port[close + 1 :]
            if port_part and not port_part.startswith(":"):
                return _BAD_HOST
            has_port, port = bool(port_part), port_part[1:]
        else:
            host, colon, port = host_port.partition(":")
            has_port = bool(colon)
        if not _valid_host(host, single_label=name is not None):
            return _BAD_HOST
        if has_port and not _valid_port(port):
            return _BAD_PORT
        return Classification("matched", format=name or "www", value=host.lower())

    def accumulator(self) -> UrlAccumulator:
        return UrlAccumulator(NameCounts(self.max_tracked, self.max_listed))


class UrlAccumulator(DetectorAccumulator):
    __slots__ = ("hosts",)

    def __init__(self, hosts: NameCounts) -> None:
        self.hosts = hosts

    def add(
        self, value: str, classification: Classification | None, count: int
    ) -> None:
        if classification is not None and classification.state == "matched":
            self.hosts.add(classification.value, count)

    def details(self, gate: ExposureGate) -> dict[str, object]:
        return {"hosts": self.hosts.block(gate)}

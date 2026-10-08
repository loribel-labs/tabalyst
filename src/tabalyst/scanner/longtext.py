# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Small bottom-k sample of long texts, identified by a digest (design 18.6).

A long text is never stored: the sampler keeps a bounded preview, the original
lengths and the digest of the complete content, which is also the identity of
the entry and the source of its priority.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import NamedTuple

from tabalyst.scanner.bottomk import BottomKSampler, Key, KmvEstimate

DIGEST_ALGORITHM = "blake2b"
DIGEST_BITS = 128
FINGERPRINT_BASED = "fingerprint_based"
# The native type of the surrogate keys the bottom-k ranks (the digest).
_DIGEST_TYPE = "digest"


class LongTextEntry(NamedTuple):
    """A retained long text: its digest, bounded preview and original sizes."""

    digest: str
    type: str
    preview: str
    truncated: bool
    original_length_chars: int
    original_length_bytes: int
    count: int
    priority: int
    # Equality of two entries is equality of digests, not of the full texts.
    identity_accuracy: str = FINGERPRINT_BASED


class _Payload(NamedTuple):
    native_type: str
    preview: str
    truncated: bool
    chars: int
    size: int


def digest_of(native_type: str, text: str) -> tuple[str, int]:
    """The hexadecimal digest of a text with its native type, and its length
    in UTF-8 bytes.

    The text is read once. The digest does not depend on the seed, so two scans
    with different seeds still recognize the same content. Lone surrogates are
    kept, as in every hash of the module ``bottomk``.
    """
    data = text.encode("utf-8", "surrogatepass")
    state = hashlib.blake2b(digest_size=DIGEST_BITS // 8)
    state.update(f"{native_type}\0".encode("ascii"))
    state.update(data)
    return state.hexdigest(), len(data)


class LongTextSampler:
    """The K long texts of smallest priority of a stream, with exact counts.

    The priority comes from the digest of the complete content (through the
    sampler of ``bottomk``), so the sample is a function of the set of distinct
    texts, of the seed and of K. Texts that differ after the preview stay
    distinct entries. ``preview_chars`` bounds the stored preview, cut on a code
    point. Memory is bounded by K entries.
    """

    __slots__ = (
        "_payload",
        "_sampler",
        "hashed_bytes",
        "hashed_texts",
        "preview_chars",
    )

    def __init__(self, k: int, *, preview_chars: int, seed: int = 0) -> None:
        if preview_chars < 1:
            raise ValueError(f"preview_chars must be at least 1, got {preview_chars}")
        self.preview_chars = preview_chars
        # Work counters: texts hashed in full and their size in UTF-8 bytes.
        self.hashed_texts = 0
        self.hashed_bytes = 0
        self._sampler = BottomKSampler(k, seed=seed)
        # Preview and sizes of the digests the sampler holds (more than K
        # between compactions; pruned when it grows beyond that).
        self._payload: dict[Key, _Payload] = {}

    @property
    def k(self) -> int:
        """Size K of the sample."""
        return self._sampler.k

    @property
    def seed(self) -> int:
        """Seed of the priority function."""
        return self._sampler.seed

    def add(self, text: str, count: int = 1, native_type: str = "string") -> None:
        """Add ``count`` occurrences of a text (at least 1)."""
        if count < 1:
            raise ValueError(f"count must be at least 1, got {count}")
        self.update(((native_type, text),), (count,))

    def update(self, items: Sequence[Key], counts: Sequence[int]) -> None:
        """Add distinct ``(native type, text)`` values with their counts, as one
        batch of occurrences."""
        sampler = self._sampler
        payload = self._payload
        digests = []
        sizes = []
        for native_type, text in items:
            digest, size = digest_of(native_type, text)
            digests.append((_DIGEST_TYPE, digest))
            sizes.append(size)
        self.hashed_texts += len(sizes)
        self.hashed_bytes += sum(sizes)
        sampler.update(digests, counts)
        for position, (native_type, text) in enumerate(items):
            key = digests[position]
            if key not in payload and sampler.holds(key):
                payload[key] = _Payload(
                    native_type,
                    text[: self.preview_chars],
                    len(text) > self.preview_chars,
                    len(text),
                    sizes[position],
                )
        if len(payload) > 2 * sampler.k + 16:
            # ``entries`` settles the sampler: only the K retained keys remain.
            kept = {entry.key for entry in sampler.entries()}
            self._payload = {key: item for key, item in payload.items() if key in kept}

    def entries(self) -> list[LongTextEntry]:
        """The retained texts ordered by priority, then digest."""
        payload = self._payload
        result = []
        for entry in self._sampler.entries():
            item = payload[entry.key]
            result.append(
                LongTextEntry(
                    digest=entry.key[1],
                    type=item.native_type,
                    preview=item.preview,
                    truncated=item.truncated,
                    original_length_chars=item.chars,
                    original_length_bytes=item.size,
                    count=entry.count,
                    priority=entry.priority,
                )
            )
        return result

    @property
    def occurrences(self) -> int:
        """Occurrences added."""
        return self._sampler.occurrences

    @property
    def retained(self) -> int:
        """Distinct texts in the sample: at most K."""
        return self._sampler.retained

    @property
    def distinct_exact(self) -> bool:
        """True while no text was dropped: ``retained`` is then the number of
        distinct texts (up to digest collisions)."""
        return self._sampler.distinct_exact

    @property
    def threshold(self) -> int | None:
        """Largest priority of the sample once a text was dropped."""
        return self._sampler.threshold

    def kmv(self) -> KmvEstimate | None:
        """The KMV estimate of the distinct texts, or ``None`` (design 18.5)."""
        return self._sampler.kmv()

    def __repr__(self) -> str:
        return (
            f"LongTextSampler(k={self.k}, retained={min(self.retained, self.k)}, "
            f"occurrences={self.occurrences})"
        )

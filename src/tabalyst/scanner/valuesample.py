# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The sample of original values of one field and its KMV estimate (design 18).

A field keeps its distinct original values with exact counts while they are at
most K, without any hash; beyond K it switches to a ``BottomKSampler``, seeded
with everything seen so far, so a key of the final sample is counted from its
first occurrence.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from itertools import repeat
from typing import cast

from tabalyst.scanner.bottomk import (
    HASH_ALGORITHM,
    HASH_BITS,
    HASH_VERSION,
    BottomKSampler,
    Key,
)
from tabalyst.scanner.exposure import ExposureGate
from tabalyst.scanner.measures import canonical_text
from tabalyst.scanner.models import SampleHash, Samples

# A table key of the engine: a raw string, or ``(native type, parsed value)``.
TableKey = str | tuple[str, object]


class ValueSample:
    """Distinct original values of a field, with their exact counts.

    Values longer than ``max_length`` are never sampled (design 18.6, lot 2c
    keeps previews of long texts): they are counted in ``excluded``, and the
    sample then claims neither to hold every distinct value nor to support a
    KMV estimate.
    """

    __slots__ = ("exact", "excluded", "k", "max_length", "sampler", "seed")

    def __init__(self, k: int, seed: int, max_length: int) -> None:
        self.k = k
        self.seed = seed
        self.max_length = max_length
        # Original key to count, in first-seen order, until K is exceeded.
        self.exact: dict[Key, int] | None = {}
        self.sampler: BottomKSampler | None = None
        self.excluded = 0

    def add(
        self, keys: Sequence[TableKey], counts: Sequence[int], scalars: bool
    ) -> None:
        """Account for distinct table keys with their counts, in first-seen
        order; ``scalars`` says whether some are not strings."""
        if not keys:
            return
        if scalars:
            pairs = [
                ("string", key) if type(key) is str else (key[0], canonical_text(*key))
                for key in keys
            ]
            self._add_pairs(*self._sieve(pairs, counts, lambda pair: pair[1]))
            return
        texts = cast("Sequence[str]", keys)
        texts, counts = self._sieve(texts, counts)
        if not texts:
            return
        sampler = self.sampler
        if sampler is not None:
            # The hot path of a field of strings: no key is built unless it
            # can enter the sample.
            sampler.update_strings(texts, counts)
        elif not self.exact and len(texts) > self.k:
            # A table released with more than K strings (the usual case).
            self.sampler = BottomKSampler.from_exact_strings(
                self.k, texts, counts, seed=self.seed
            )
            self.exact = None
        else:
            self._add_pairs(list(zip(repeat("string"), texts)), counts)

    def _sieve(self, items, counts, text_of=None):
        """The items and counts whose text is at most ``max_length`` long (the
        item itself without ``text_of``); the others are counted in
        ``excluded``."""
        longest = self.max_length
        texts = items if text_of is None else [text_of(item) for item in items]
        if max(map(len, texts)) <= longest:
            return items, counts
        kept = [position for position, text in enumerate(texts) if len(text) <= longest]
        self.excluded += len(items) - len(kept)
        return (
            [items[position] for position in kept],
            [counts[position] for position in kept],
        )

    def _add_pairs(self, pairs: list[Key], counts: Sequence[int]) -> None:
        """Account for original keys: exact while they are at most K, then in
        the bottom-k."""
        if not pairs:
            return
        sampler = self.sampler
        if sampler is not None:
            sampler.update(pairs, counts)
            return
        exact = self.exact
        if not exact:
            exact = self.exact = dict(zip(pairs, counts, strict=True))
        else:
            for pair, count in zip(pairs, counts, strict=True):
                exact[pair] = exact.get(pair, 0) + count
        if len(exact) > self.k:
            self.sampler = BottomKSampler.from_exact(self.k, exact, seed=self.seed)
            self.exact = None

    def estimate(self, gate: ExposureGate) -> dict | None:
        """The KMV estimate of the distinct original values as plain data, or
        ``None``: nothing was dropped yet, or values were excluded and the
        estimator did not see the whole domain. The threshold of a sensitive
        field is withheld: it is the priority of one of its values."""
        sampler = self.sampler
        if sampler is None or self.excluded:
            return None
        kmv = sampler.kmv()
        if kmv is None:
            return None
        return {
            "method": "kmv",
            "value": kmv.estimate,
            "relative_standard_error": kmv.relative_standard_error,
            "k": kmv.k,
            "theta_hex": kmv.theta_hex if gate.mode == "show" else None,
        }

    def samples(self, gate: ExposureGate) -> Samples:
        """The ``values.samples`` block, through the exposure gate.

        ``of`` counts the original values sampled and ``kept`` the entries
        listed: exposure can make them differ (``mask`` merges originals with
        the same mask, ``hide`` lists none), which a reader sees as a sample
        that cannot give the originals back (design 21).
        """
        exact = self.exact
        sampler = self.sampler
        if exact is not None and self.excluded:
            # The sample is not the whole domain: it is a bottom-k, ordered.
            sampler = BottomKSampler.from_exact(self.k, exact, seed=self.seed)
            exact = None
        if exact is not None:
            selection = "all"
            items = list(exact.items())
            threshold = None
        else:
            selection = "bottom_k"
            assert sampler is not None
            items = [(entry.key, entry.count) for entry in sampler.entries()]
            threshold = sampler.threshold
        listed = _entries(gate.typed_counts(items) if gate.mode != "show" else items)
        if selection == "all":
            return Samples(
                selection="all", kept=len(listed), of=len(items), listed=listed
            )
        sensitive = gate.mode != "show"
        return Samples(
            selection="bottom_k",
            kept=len(listed),
            of=len(items),
            listed=listed,
            k=self.k,
            hash=SampleHash(
                algorithm=HASH_ALGORITHM,
                version=HASH_VERSION,
                bits=HASH_BITS,
                seed=self.seed,
            ),
            threshold=(None if threshold is None or sensitive else f"{threshold:032x}"),
        )


def _entries(
    items: Mapping[Key, int] | Sequence[tuple[Key, int]],
) -> list[dict[str, object]]:
    """Numbered entries of ``(native type, text)`` values with their counts, as
    plain data for ``Samples`` to validate (cheaper than building each model);
    ``items`` is a mapping or a sequence of pairs."""
    pairs = items.items() if isinstance(items, Mapping) else items
    return [
        {
            "id": position,
            "value": text,
            "type": native_type,
            "count": count,
            "count_accuracy": "exact",
            "identity_accuracy": "exact",
        }
        for position, ((native_type, text), count) in enumerate(pairs)
    ]

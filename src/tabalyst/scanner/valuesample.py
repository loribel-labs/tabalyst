# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The sample of original values of one field and its KMV estimate (design 18).

A field keeps its distinct original values with exact counts while they are at
most K, without any hash; beyond K it switches to a ``BottomKSampler``, seeded
with everything seen so far, so a key of the final sample is counted from its
first occurrence. Values longer than the stored length go to a small sample of
long texts (design 18.6).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from itertools import repeat
from typing import Any, cast

from tabalyst.scanner.bottomk import (
    HASH_ALGORITHM,
    HASH_BITS,
    HASH_VERSION,
    BottomKSampler,
    Key,
)
from tabalyst.scanner.exposure import ExposureGate
from tabalyst.scanner.longtext import (
    DIGEST_ALGORITHM,
    DIGEST_BITS,
    FINGERPRINT_BASED,
    LongTextSampler,
)
from tabalyst.scanner.measures import canonical_text
from tabalyst.scanner.models import DigestInfo, LongTexts, SampleHash, Samples

# Reason written when the memory budget granted a sample smaller than asked.
MEMORY_BUDGET = "memory_budget"

# A table key of the engine: a raw string, or ``(native type, parsed value)``.
TableKey = str | tuple[str, object]


class ValueSample:
    """Distinct original values of a field, with their exact counts.

    ``k`` is the size granted by the memory budget (design 18.10), ``requested``
    the one the configuration asked for. Values longer than ``max_length`` go
    to a ``LongTextSampler`` of ``long_k`` texts, granted later than ``k``
    (``grant_long``) because the scan process only meets the first long value
    while streaming. A value that fits no sample (``k`` or ``long_k`` of 0)
    sets ``omitted``: the sample then claims neither to hold every distinct
    value nor to support a KMV estimate.
    """

    __slots__ = (
        "exact",
        "k",
        "long",
        "long_k",
        "long_occurrences",
        "long_requested",
        "max_length",
        "omitted",
        "preview_chars",
        "requested",
        "sampler",
        "seed",
    )

    def __init__(
        self,
        k: int,
        seed: int,
        max_length: int,
        *,
        requested: int | None = None,
        preview_chars: int = 200,
        long_requested: int = 100,
    ) -> None:
        self.k = k
        self.requested = k if requested is None else requested
        self.seed = seed
        self.max_length = max_length
        self.preview_chars = preview_chars
        # Original key to count, in first-seen order, until K is exceeded.
        self.exact: dict[Key, int] | None = {}
        self.sampler: BottomKSampler | None = None
        self.long: LongTextSampler | None = None
        # Size granted to the long texts of the field: none until the first
        # long value is met and the budget grants it.
        self.long_k = 0
        self.long_requested = long_requested
        self.long_occurrences = 0
        self.omitted = False

    def grant_long(self, k: int) -> None:
        """Size of the long text sample, granted by the memory budget."""
        if not self.long_k:
            self.long_k = k

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
            pairs, counts = self._sieve(pairs, counts, lambda pair: pair[1])
            if pairs and self._fits():
                self._add_pairs(pairs, counts)
            return
        texts = cast("Sequence[str]", keys)
        texts, counts = self._sieve(texts, counts, None)
        if not texts or not self._fits():
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

    def _fits(self) -> bool:
        """Whether the sample can hold values; a size of 0 (the budget granted
        nothing) omits them."""
        if self.k:
            return True
        self.omitted = True
        return False

    def _sieve(
        self,
        items: Sequence[Any],
        counts: Sequence[int],
        text_of: Callable[[Any], str] | None,
    ) -> tuple[list[Any], list[int]]:
        """The items and counts whose text is at most ``max_length`` long (the
        item itself without ``text_of``); the others go to the long texts."""
        longest = self.max_length
        texts = items if text_of is None else [text_of(item) for item in items]
        if max(map(len, texts)) <= longest:
            return items, counts
        kept = []
        long_items = []
        long_counts = []
        for position, text in enumerate(texts):
            if len(text) <= longest:
                kept.append(position)
            else:
                item = items[position]
                long_items.append(("string", item) if text_of is None else item)
                long_counts.append(counts[position])
        self._add_long(long_items, long_counts)
        return (
            [items[position] for position in kept],
            [counts[position] for position in kept],
        )

    def _add_long(self, items: list[Key], counts: list[int]) -> None:
        """Account for long values as ``(native type, text)`` pairs."""
        self.long_occurrences += sum(counts)
        if not self.long_k:
            self.omitted = True
            return
        long = self.long
        if long is None:
            long = self.long = LongTextSampler(
                self.long_k, preview_chars=self.preview_chars, seed=self.seed
            )
        long.update(items, counts)

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

    def counters(self) -> dict[str, int]:
        """The work counters of this field's samplers (design 18.4), as plain
        data for ``memory.SamplingTotals``."""
        sampler = self.sampler
        work = {} if sampler is None else sampler.counters
        long = self.long
        return {
            "hashed_keys": work.get("hashed", 0),
            "hit_keys": work.get("hits", 0),
            "admitted_keys": work.get("admitted", 0),
            "rejected_keys": work.get("rejected", 0),
            "evicted_keys": work.get("evicted", 0),
            "long_texts_hashed": 0 if long is None else long.hashed_texts,
            "long_bytes_hashed": 0 if long is None else long.hashed_bytes,
            "bottom_k_fields": int(sampler is not None),
            "reduced_fields": int(
                (self.k < self.requested and (sampler is not None or not self.k))
                or (
                    self.long_occurrences > 0
                    and self.long_k < self.long_requested
                )
            ),
            "k": self.k,
        }

    def estimate(self, gate: ExposureGate) -> dict | None:
        """The KMV estimate of the distinct original values as plain data, or
        ``None``: nothing was dropped yet, or a value fits no sample and the
        estimator did not see the whole domain. The threshold of a sensitive
        field is withheld: it is the priority of one of its values.

        A field with long texts has two disjoint domains, the values of the
        sample and the long texts, each exact or estimated: the estimate is
        their sum and ``parts`` gives each (design 18.6).
        """
        sampler = self.sampler
        long = self.long
        if self.omitted:
            return None
        if self.long_occurrences == 0:
            return self._estimate_values(sampler, gate)
        if sampler is None and (long is None or long.distinct_exact):
            return None
        values = self._part("values", sampler, len(self.exact or ()), gate)
        texts = self._part("long_texts", long, 0 if long is None else long.retained, gate)
        if values is None or texts is None:
            return None
        parts = [values, texts]
        total = values["value"] + texts["value"]
        error = math.sqrt(
            sum((part["value"] * part["relative_standard_error"]) ** 2 for part in parts)
        )
        return {
            "method": "kmv",
            "value": total,
            "relative_standard_error": error / total if total else 0.0,
            "parts": parts,
        }

    def _estimate_values(
        self, sampler: BottomKSampler | None, gate: ExposureGate
    ) -> dict | None:
        if sampler is None:
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

    @staticmethod
    def _part(
        domain: str,
        sampler: BottomKSampler | LongTextSampler | None,
        distinct: int,
        gate: ExposureGate,
    ) -> dict | None:
        """One domain of the estimate: exact while its sampler dropped nothing,
        else its KMV estimate (``None`` when it has none)."""
        if sampler is None or sampler.distinct_exact:
            return {
                "domain": domain,
                "accuracy": "exact",
                "value": float(distinct),
                "relative_standard_error": 0.0,
            }
        kmv = sampler.kmv()
        if kmv is None:
            return None
        return {
            "domain": domain,
            "accuracy": "estimated",
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
        that cannot give the originals back (design 21). The block describes
        the values that fit ``max_length``; ``long_texts`` describes the rest.
        """
        exact = self.exact
        sampler = self.sampler
        if not self.k:
            exact = None
        if exact is not None:
            selection = "all"
            items = list(exact.items())
            threshold = None
        else:
            selection = "bottom_k"
            items = (
                []
                if sampler is None
                else [(entry.key, entry.count) for entry in sampler.entries()]
            )
            threshold = None if sampler is None else sampler.threshold
        listed = _entries(gate.typed_counts(items) if gate.mode != "show" else items)
        long_texts = self._long_texts(gate)
        if selection == "all":
            return Samples(
                selection="all",
                kept=len(listed),
                of=len(items),
                listed=listed,
                long_texts=long_texts,
            )
        sensitive = gate.mode != "show"
        reduced = self.k < self.requested
        return Samples(
            selection="bottom_k",
            kept=len(listed),
            of=len(items),
            listed=listed,
            k=self.k,
            requested_k=self.requested if reduced else None,
            reason=MEMORY_BUDGET if reduced else None,
            hash=_hash(self.seed),
            threshold=(None if threshold is None or sensitive else f"{threshold:032x}"),
            long_texts=long_texts,
        )

    def _long_texts(self, gate: ExposureGate) -> LongTexts | None:
        """The ``long_texts`` block, or ``None`` when no long value was met.

        A sensitive field lists none of them: a preview and a digest are the
        value, so exposure withholds both (``kept < of``)."""
        if not self.long_occurrences:
            return None
        long = self.long
        entries = [] if long is None else long.entries()
        listed = (
            [
                {
                    "id": position,
                    "digest": entry.digest,
                    "type": entry.type,
                    "preview": entry.preview,
                    "truncated": entry.truncated,
                    "original_length_chars": entry.original_length_chars,
                    "original_length_bytes": entry.original_length_bytes,
                    "count": entry.count,
                    "count_accuracy": "exact",
                    "identity_accuracy": FINGERPRINT_BASED,
                }
                for position, entry in enumerate(entries)
            ]
            if gate.mode == "show"
            else []
        )
        complete = long is not None and long.distinct_exact
        threshold = None if long is None or complete else long.threshold
        reduced = self.long_k < self.long_requested
        return LongTexts(
            selection="all" if complete else "bottom_k",
            k=self.long_k,
            requested_k=self.long_requested if reduced else None,
            preview_chars=self.preview_chars,
            occurrences=self.long_occurrences,
            kept=len(listed),
            of=len(entries),
            digest=DigestInfo(algorithm=DIGEST_ALGORITHM, bits=DIGEST_BITS),
            hash=None if complete else _hash(self.seed),
            threshold=(
                None
                if threshold is None or gate.mode != "show"
                else f"{threshold:032x}"
            ),
            listed=listed,
        )


def _hash(seed: int) -> SampleHash:
    return SampleHash(
        algorithm=HASH_ALGORITHM, version=HASH_VERSION, bits=HASH_BITS, seed=seed
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

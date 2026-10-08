# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Properties of the bottom-k sampler against exhaustive oracles (design 18).

The contract tests B01 to B13 are in ``test_contract_bottomk.py``; these tests
pin the hash and check the sampler against counts computed by the test itself,
on small random streams.
"""

import hashlib
import random
from collections import Counter

import pytest

from tabalyst.scanner import bottomk
from tabalyst.scanner.bottomk import (
    HASH_ALGORITHM,
    HASH_BITS,
    HASH_VERSION,
    BottomKSampler,
    kmv_estimate,
    priority,
)

Key = tuple[str, str]


def _key(text: str, type_: str = "string") -> Key:
    return (type_, text)


def _oracle(stream, k, rank):
    counts = Counter(stream)
    ordered = sorted(counts, key=lambda item: (rank(item), item))[:k]
    return [(item, rank(item), counts[item]) for item in ordered]


def _entries(sampler):
    return [(item.key, item.priority, item.count) for item in sampler.entries()]


# Hash ---------------------------------------------------------------------


def test_hash_version_is_pinned():
    assert (HASH_ALGORITHM, HASH_VERSION, HASH_BITS) == ("blake2b", 1, 128)


@pytest.mark.parametrize(
    ("key", "seed", "expected"),
    [
        (("string", "hello"), 0, 0xBA9B3BCD3D4F2821C1014EE952EF5A6C),
        (("string", "hello"), 1, 0x121D9C88F062A6EC0F06383B5B8D2935),
        (("integer", "123"), 0, 0x57976259814AA28ED29CE60E795A0F2E),
        (("string", "café"), 3, 0x558669ABBF27DCDEAAA9887E0647E0CB),
        (("string", ""), 0, 0xADE0F99A4A2AC4D060DC77A1A22460B2),
        (("string", "\ud800"), 0, 0x1D242014C11F09E235F53A3BB9CD631B),
    ],
)
def test_priority_golden_values_never_change_within_a_hash_version(key, seed, expected):
    assert priority(key, seed=seed) == expected


def test_priority_is_blake2b_of_seed_type_nul_and_utf8_text():
    digest = hashlib.blake2b(
        (3).to_bytes(8, "little") + b"string\0" + "café".encode(),
        digest_size=16,
    ).digest()
    assert priority(("string", "café"), seed=3) == int.from_bytes(digest, "big")


def test_priority_separates_type_text_and_seed():
    values = {
        priority(("string", "1")),
        priority(("integer", "1")),
        priority(("string", "1"), seed=1),
        priority(("ab", "c")),
        priority(("a", "bc")),
        priority(("string", "00123")),
        priority(("string", "123")),
        priority(("string", " 123 ")),
    }
    assert len(values) == 8
    assert all(0 <= value < 2**128 for value in values)


def test_priority_keeps_unicode_forms_apart_and_accepts_lone_surrogates():
    composed, decomposed = "é", "é"
    assert priority(_key(composed)) != priority(_key(decomposed))
    assert priority(_key("\ud800")) != priority(_key("\udfff"))


@pytest.mark.parametrize("seed", [-1, 2**64])
def test_priority_rejects_a_seed_outside_64_bits(seed):
    with pytest.raises(ValueError, match="seed"):
        priority(_key("a"), seed=seed)
    with pytest.raises(ValueError, match="seed"):
        BottomKSampler(3, seed=seed)


def test_priorities_are_spread_over_the_whole_range():
    values = [priority(_key(f"id-{index}")) for index in range(2000)]
    top_bits = Counter(value >> (bottomk.HASH_BITS - 3) for value in values)
    assert set(top_bits) == set(range(8))
    assert min(top_bits.values()) > 2000 / 8 * 0.7


# Sampler against oracles ---------------------------------------------------


def _random_stream(rng: random.Random, distinct: int, length: int) -> list[Key]:
    return [_key(f"v{int(rng.paretovariate(1.0)) % distinct}") for _ in range(length)]


@pytest.mark.parametrize("k", [1, 2, 3, 7, 16])
@pytest.mark.parametrize("seed", [0, 5])
def test_every_prefix_of_a_random_stream_equals_the_oracle(k, seed):
    rng = random.Random(100 * k + seed)
    stream = _random_stream(rng, distinct=60, length=500)

    def rank(item):
        return priority(item, seed=seed)

    sampler = BottomKSampler(k, seed=seed)
    for position, item in enumerate(stream, start=1):
        sampler.add(item)
        if position % 17 == 0 or position == len(stream):
            assert _entries(sampler) == _oracle(stream[:position], k, rank)
            assert sampler.occurrences == position
            assert sampler.retained == min(k, len(set(stream[:position])))


@pytest.mark.parametrize("k", [1, 4, 9])
def test_batches_with_counts_give_the_sample_of_streaming_the_occurrences(k):
    rng = random.Random(k)
    stream = _random_stream(rng, distinct=80, length=900)
    streamed = BottomKSampler(k)
    for item in stream:
        streamed.add(item)

    batched = BottomKSampler(k)
    position = 0
    while position < len(stream):
        size = rng.randint(1, 120)
        batch = Counter(stream[position : position + size])
        batched.update(list(batch), list(batch.values()))
        position += size

    assert _entries(batched) == _entries(streamed)
    assert batched.occurrences == streamed.occurrences == len(stream)
    assert batched.threshold == streamed.threshold


@pytest.mark.parametrize("k", [1, 4, 9, 40])
def test_string_batches_give_the_sample_of_the_generic_batches(k):
    rng = random.Random(100 + k)
    texts = [
        f"t{rng.randrange(150)}" + ("\udcff" if n % 9 == 0 else "")
        for n in range(1200)
    ]
    generic = BottomKSampler(k)
    fast = BottomKSampler(k)
    position = 0
    while position < len(texts):
        batch = Counter(texts[position : position + rng.randint(1, 200)])
        position += sum(batch.values())
        generic.update([("string", text) for text in batch], list(batch.values()))
        fast.update_strings(list(batch), list(batch.values()))

    assert _entries(fast) == _entries(generic)
    assert fast.occurrences == generic.occurrences == len(texts)
    assert fast.threshold == generic.threshold
    assert fast.overflow_at_occurrence == generic.overflow_at_occurrence


@pytest.mark.parametrize("distinct", [0, 3, 9, 10, 11, 60])
def test_from_exact_strings_equals_from_exact_of_string_keys(distinct):
    rng = random.Random(distinct)
    texts = [f"s{n}-{rng.randrange(99)}" for n in range(distinct)]
    counts = [rng.randint(1, 5) for _ in texts]

    generic = BottomKSampler.from_exact(
        10, {("string", text): count for text, count in zip(texts, counts)}, seed=3
    )
    fast = BottomKSampler.from_exact_strings(10, texts, counts, seed=3)

    assert _entries(fast) == _entries(generic)
    assert (fast.occurrences, fast.threshold) == (generic.occurrences, generic.threshold)
    assert fast.distinct_exact == generic.distinct_exact
    for batch in ([("string", "later")], [("string", texts[0])] if texts else []):
        if batch:
            generic.update(batch, [2])
            fast.update_strings([batch[0][1]], [2])
    assert _entries(fast) == _entries(generic)


def test_from_exact_strings_rejects_a_count_below_one():
    with pytest.raises(ValueError):
        BottomKSampler.from_exact_strings(2, ["a", "b", "c"], [1, 0, 1])


def test_string_batches_use_an_injected_priority():
    collide = BottomKSampler(2, priority=lambda key: 7)

    collide.update_strings(["b", "a", "c"], [1, 1, 1])

    assert [entry.key for entry in collide.entries()] == [
        ("string", "a"),
        ("string", "b"),
    ]


@pytest.mark.parametrize("k", [1, 5, 12])
def test_any_order_of_the_stream_gives_the_same_sample(k):
    rng = random.Random(7 + k)
    stream = _random_stream(rng, distinct=70, length=700)
    reference = BottomKSampler(k)
    for item in stream:
        reference.add(item)
    for shuffle_seed in range(5):
        shuffled = stream[:]
        random.Random(shuffle_seed).shuffle(shuffled)
        sampler = BottomKSampler(k)
        for item in shuffled:
            sampler.add(item)
        assert _entries(sampler) == _entries(reference)


@pytest.mark.parametrize("k", [1, 3, 8])
def test_equal_priorities_everywhere_keep_the_smallest_keys(k):
    rng = random.Random(k)
    stream = _random_stream(rng, distinct=40, length=400)
    sampler = BottomKSampler(k, priority=lambda item: 11)
    for item in stream:
        sampler.add(item)
    assert _entries(sampler) == _oracle(stream, k, lambda item: 11)
    assert sampler.threshold == 11


def test_a_retained_key_has_the_count_of_the_whole_stream():
    rng = random.Random(3)
    stream = _random_stream(rng, distinct=90, length=2000)
    sampler = BottomKSampler(10)
    for item in stream:
        sampler.add(item)
    totals = Counter(stream)
    assert all(item.count == totals[item.key] for item in sampler.entries())


def test_the_first_overflow_occurrence_follows_the_counts_of_a_batch():
    sampler = BottomKSampler(2)
    sampler.update([_key("a"), _key("b"), _key("c")], [3, 2, 4])
    assert sampler.overflow_at_occurrence == 3 + 2 + 1
    assert sampler.occurrences == 9
    assert sampler.distinct_exact is False
    # The first overflow is not moved by later ones.
    sampler.update([_key(f"x{index}") for index in range(20)], [1] * 20)
    assert sampler.overflow_at_occurrence == 6


def test_repeated_keys_alone_never_overflow():
    sampler = BottomKSampler(3)
    for _ in range(50):
        for text in "abc":
            sampler.add(_key(text))
    assert sampler.distinct_exact is True
    assert sampler.overflow_at_occurrence is None
    assert sampler.threshold is None
    assert [item.count for item in sampler.entries()] == [50, 50, 50]


# from_exact and reduce ----------------------------------------------------


@pytest.mark.parametrize("distinct", [0, 3, 6, 7, 40])
def test_from_exact_equals_streaming_for_any_table_size(distinct):
    rng = random.Random(distinct)
    keys = [_key(f"t{index}") for index in range(distinct)]
    counts = {item: rng.randint(1, 9) for item in keys}
    stream = [item for item, count in counts.items() for _ in range(count)]
    random.Random(1).shuffle(stream)
    streamed = BottomKSampler(6)
    for item in stream:
        streamed.add(item)

    seeded = BottomKSampler.from_exact(6, counts, overflow_at_occurrence=17)

    assert _entries(seeded) == _entries(streamed)
    assert seeded.distinct_exact == streamed.distinct_exact == (distinct <= 6)
    assert seeded.threshold == streamed.threshold
    assert seeded.occurrences == len(stream)
    expected_overflow = 17 if distinct > 6 else None
    assert seeded.overflow_at_occurrence == expected_overflow
    more = [_key(f"t{rng.randrange(distinct + 30)}") for _ in range(200)]
    for item in more:
        seeded.add(item)
        streamed.add(item)
    assert _entries(seeded) == _entries(streamed)


def test_from_exact_rejects_a_count_below_one():
    with pytest.raises(ValueError, match="counts"):
        BottomKSampler.from_exact(3, {_key("a"): 0})


def test_reduce_keeps_the_exact_counts_of_the_smaller_priorities():
    rng = random.Random(4)
    stream = _random_stream(rng, distinct=60, length=800)
    sampler = BottomKSampler(12)
    for item in stream:
        sampler.add(item)
    before = _entries(sampler)

    sampler.reduce(5)
    sampler.reduce(5)

    assert _entries(sampler) == before[:5]
    assert sampler.k == 5
    more = [_key(f"v{rng.randrange(80)}") for _ in range(300)]
    for item in more:
        sampler.add(item)
    # The same sample as one that always had K = 5: the counts of the best
    # keys never depended on the ones rejected.
    direct = BottomKSampler(5)
    for item in stream + more:
        direct.add(item)
    assert _entries(sampler) == _entries(direct)


def test_reduce_of_an_exact_sampler_below_its_size_is_an_overflow_of_the_new_k():
    sampler = BottomKSampler(10)
    for index in range(6):
        sampler.add(_key(f"k{index}"))
    sampler.reduce(8)
    assert sampler.distinct_exact is True
    sampler.reduce(4)
    assert sampler.distinct_exact is False
    assert sampler.overflow_at_occurrence is None
    assert sampler.retained == 4


# Estimate and errors -------------------------------------------------------


def test_kmv_of_a_sample_reduced_below_three_is_none():
    sampler = BottomKSampler(10)
    for index in range(40):
        sampler.add(_key(f"k{index}"))
    assert sampler.kmv() is not None
    sampler.reduce(2)
    assert sampler.kmv() is None


def test_kmv_ignores_injected_priorities_outside_the_hash_space():
    sampler = BottomKSampler(3, priority=lambda item: 2**200)
    for index in range(10):
        sampler.add(_key(f"k{index}"))
    assert sampler.kmv() is None


def test_kmv_estimate_follows_the_threshold_of_the_sampler():
    sampler = BottomKSampler(50)
    for index in range(5000):
        sampler.add(_key(f"id-{index}"))
    estimate = sampler.kmv()
    assert estimate == kmv_estimate(threshold=sampler.threshold, k=50)
    assert estimate.k == 50
    assert estimate.theta_hex == f"{sampler.threshold:032x}"


def test_invalid_parameters_are_refused():
    with pytest.raises(ValueError, match="k must"):
        BottomKSampler(0)
    sampler = BottomKSampler(2)
    with pytest.raises(ValueError, match="count"):
        sampler.add(_key("a"), 0)
    with pytest.raises(ValueError):
        sampler.update([_key("a"), _key("b")], [1])
    with pytest.raises(ValueError, match="k"):
        sampler.reduce(0)


def test_a_failed_batch_keeps_the_occurrences_of_the_keys_it_admitted():
    sampler = BottomKSampler(3)
    with pytest.raises(ValueError):
        sampler.update([_key("a"), _key("b")], [4])
    assert sampler.occurrences == 4
    assert _entries(sampler)[0][2] == 4
    sampler.add(_key("c"))
    assert sampler.occurrences == 5


def test_inspecting_a_sampler_does_not_change_its_state():
    sampler = BottomKSampler(10)
    for index in range(14):  # inside the slack, before the next compaction
        sampler.add(_key(f"k{index}"))
    text = repr(sampler)
    assert "retained=10" in text
    assert len(sampler._counts) > 10

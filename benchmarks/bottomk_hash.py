# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Numbers behind the hash of the bottom-k sampler (Scan and JSON plan, lot 2a).

    python benchmarks/bottomk_hash.py micro
    python benchmarks/bottomk_hash.py engine D:/GIT.test/tabalyst/csv/insurance-combined.csv

``micro`` measures, in this process:

- the cost per key of candidate priority functions (encoding included);
- the quality of their KMV estimate on sequential identifiers, where a weak
  hash shows;
- the real ``BottomKSampler`` fed like the engine feeds it (batches of 4,096
  distinct keys) with five columns of one million unique identifiers, its
  ``from_exact`` at the table limit, and its memory per entry.

``engine`` is a throwaway prototype of lot 2b, replaced by the real engine
integration there: it patches ``ValueProcessor`` so that every released field
(and every complete table) also feeds a sampler, then compares a one-process
scan with and without it, interleaved, one fresh interpreter per run. The
hashing of a parallel scan runs in the workers, so the one-process delta is a
pessimistic bound of the cost to the scan.

Results go under the external artifacts root, never in the checkout.
"""

import argparse
import gc
import hashlib
import json
import math
import os
import random
import statistics
import subprocess
import sys
import time
import tracemalloc
import zlib
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

Key = tuple[str, str]
HashFunction = Callable[[Key], int]
Candidates = dict[str, tuple[HashFunction, int, bool]]
# A raw key of the engine's table: a string, or (native type, value).
RawKey = str | tuple[str, object]

DEFAULT_OUT = Path("D:/GIT.test/tabalyst/artifacts/scan-json-lot2a")
BATCH = 4096
K = 10_000
TABLE_LIMIT = 100_000


# Candidates -----------------------------------------------------------------


def _encode(key: Key) -> bytes:
    return f"{key[0]}\0{key[1]}".encode("utf-8", "surrogatepass")


def _candidates(seed: int = 3) -> Candidates:
    """Name to (function of a key, bits, stable across processes)."""
    prefix = seed.to_bytes(8, "little")
    prototype = hashlib.blake2b(prefix, digest_size=16)

    def blake2b_copied(key: Key) -> int:
        state = prototype.copy()
        state.update(_encode(key))
        return int.from_bytes(state.digest(), "big")

    def blake2b_prefixed(key: Key) -> int:
        return int.from_bytes(
            hashlib.blake2b(prefix + _encode(key), digest_size=16).digest(), "big"
        )

    def blake2b_salted(key: Key) -> int:
        return int.from_bytes(
            hashlib.blake2b(_encode(key), digest_size=16, salt=prefix).digest(), "big"
        )

    def blake2s(key: Key) -> int:
        return int.from_bytes(
            hashlib.blake2s(prefix + _encode(key), digest_size=16).digest(), "big"
        )

    def sha256(key: Key) -> int:
        return int.from_bytes(
            hashlib.sha256(prefix + _encode(key)).digest()[:16], "big"
        )

    def sha1(key: Key) -> int:
        return int.from_bytes(hashlib.sha1(prefix + _encode(key)).digest()[:16], "big")

    def md5(key: Key) -> int:
        digest = hashlib.md5(prefix + _encode(key), usedforsecurity=False).digest()
        return int.from_bytes(digest, "big")

    def shake128(key: Key) -> int:
        return int.from_bytes(
            hashlib.shake_128(prefix + _encode(key)).digest(16), "big"
        )

    def crc32_pair(key: Key) -> int:
        data = _encode(key)
        return ((zlib.crc32(data, seed + 1) << 32) | zlib.crc32(data, seed + 2)) << 64

    return {
        "blake2b-128, seeded state copied (retained)": (blake2b_copied, 128, True),
        "blake2b-128, seed as prefix": (blake2b_prefixed, 128, True),
        "blake2b-128, seed as salt": (blake2b_salted, 128, True),
        "blake2s-128": (blake2s, 128, True),
        "sha256 cut to 128": (sha256, 128, True),
        "sha1 cut to 128": (sha1, 128, True),
        "md5": (md5, 128, True),
        "shake_128 (16 bytes)": (shake128, 128, True),
        "crc32 twice (64 bits)": (crc32_pair, 64, True),
        "builtin hash() (floor)": (lambda key: hash(key) % (1 << 64) << 64, 64, False),
    }


def _keys(kind: str, count: int) -> list[Key]:
    rng = random.Random(1)
    if kind == "id12":
        return [("string", f"ID{index:010d}") for index in range(count)]
    if kind == "words":
        words = ["alpha", "beta", "gamma", "delta", "\u00e9psilon", "z\u00eata"]
        return [
            (
                "string",
                " ".join(rng.choice(words) for _ in range(rng.randint(1, 6)))
                + str(index),
            )
            for index in range(count)
        ]
    return [("string", f"{rng.getrandbits(128):032x}") for _ in range(count)]


def _cost(
    candidates: Candidates, count: int = 200_000, repeats: int = 5
) -> list[dict[str, object]]:
    rows = []
    for kind in ("id12", "words", "hex32"):
        keys = _keys(kind, count)
        length = statistics.fmean(len(key[1]) for key in keys)
        for name, (function, bits, stable) in candidates.items():
            best = math.inf
            for _ in range(repeats):
                started = time.perf_counter()
                for key in keys:
                    function(key)
                best = min(best, time.perf_counter() - started)
            rows.append(
                {
                    "keys": kind,
                    "mean_length": round(length, 1),
                    "function": name,
                    "bits": bits,
                    "stable": stable,
                    "ns_per_key": best / count * 1e9,
                }
            )
    return rows


def _quality(candidates: Candidates) -> list[dict[str, object]]:
    """KMV error of each stable candidate on sequential identifiers, over
    several seeds."""
    from tabalyst.scanner.bottomk import BottomKSampler

    k, distinct, runs = 256, 50_000, 12
    keys = [("string", f"ID{index:010d}") for index in range(distinct)]
    expected = 1 / math.sqrt(k - 2)
    rows = []
    for name, (_, _, stable) in candidates.items():
        if not stable:
            continue
        errors = []
        for run in range(runs):
            function = _candidates(seed=run)[name][0]
            sampler = BottomKSampler(k, priority=function)
            sampler.update(keys, [1] * len(keys))
            estimate = sampler.kmv()
            assert estimate is not None
            errors.append(estimate.estimate / distinct - 1)
        rows.append(
            {
                "function": name,
                "mean_error": statistics.fmean(errors),
                "rms_error": math.sqrt(statistics.fmean(e * e for e in errors)),
                "model_rse": expected,
            }
        )
    return rows


# The real sampler fed like the engine ---------------------------------------


def _engine_feed(columns: int = 5, rows: int = 1_000_000) -> dict[str, float]:
    from tabalyst.scanner.bottomk import BottomKSampler

    started = time.perf_counter()
    for column in range(columns):
        sampler = BottomKSampler(K)
        for start in range(0, rows, BATCH):
            keys = [
                ("string", f"C{column}-{index:09d}")
                for index in range(start, min(start + BATCH, rows))
            ]
            sampler.update(keys, [1] * len(keys))
    seconds = time.perf_counter() - started
    # The same keys built and left alone: what is not the sampler.
    started = time.perf_counter()
    for column in range(columns):
        for start in range(0, rows, BATCH):
            keys = [
                ("string", f"C{column}-{index:09d}")
                for index in range(start, min(start + BATCH, rows))
            ]
            [1] * len(keys)
    baseline = time.perf_counter() - started
    return {
        "columns": columns,
        "rows": rows,
        "k": K,
        "seconds_with_keys": seconds,
        "seconds_keys_only": baseline,
        "sampler_seconds": seconds - baseline,
        "ns_per_occurrence": (seconds - baseline) / (columns * rows) * 1e9,
    }


def _from_exact_cost() -> dict[str, float]:
    from tabalyst.scanner.bottomk import BottomKSampler

    table = {
        ("string", f"ID{index:010d}"): 1 + index % 7 for index in range(TABLE_LIMIT + 1)
    }
    best = math.inf
    for _ in range(5):
        started = time.perf_counter()
        BottomKSampler.from_exact(K, table)
        best = min(best, time.perf_counter() - started)
    return {"keys": len(table), "k": K, "seconds": best}


def _memory() -> dict[str, float]:
    from tabalyst.scanner.bottomk import BottomKSampler

    gc.collect()
    tracemalloc.start()
    before = tracemalloc.get_traced_memory()[0]
    sampler = BottomKSampler(K)
    for start in range(0, 200_000, BATCH):
        keys = [("string", f"ID{index:010d}") for index in range(start, start + BATCH)]
        sampler.update(keys, [1] * len(keys))
    entries = sampler.entries()
    retained = tracemalloc.get_traced_memory()[0] - before
    tracemalloc.stop()
    return {
        "k": K,
        "retained_bytes": retained,
        "bytes_per_entry": retained / len(entries),
    }


def micro(out: Path) -> None:
    candidates = _candidates()
    result = {
        "cost": _cost(candidates),
        "quality": _quality(candidates),
        "engine_feed": _engine_feed(),
        "from_exact": _from_exact_cost(),
        "memory": _memory(),
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "micro.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = ["| Keys | Function | Bits | ns per key |", "| --- | --- | ---: | ---: |"]
    for row in result["cost"]:
        lines.append(
            f"| {row['keys']} ({row['mean_length']}) | {row['function']} | "
            f"{row['bits']} | {row['ns_per_key']:.0f} |"
        )
    lines += [
        "",
        "| Function | Mean error | RMS error | Model RSE |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in result["quality"]:
        lines.append(
            f"| {row['function']} | {row['mean_error']:+.4f} | {row['rms_error']:.4f} | "
            f"{row['model_rse']:.4f} |"
        )
    feed = result["engine_feed"]
    lines += [
        "",
        (
            f"Sampler fed in batches of {BATCH}: {feed['columns']} columns x "
            f"{feed['rows']:,} unique identifiers, K = {feed['k']:,}: "
            f"{feed['sampler_seconds']:.2f} s ({feed['ns_per_occurrence']:.0f} ns per "
            f"occurrence), keys built alone {feed['seconds_keys_only']:.2f} s."
        ),
        (
            f"from_exact on {result['from_exact']['keys']:,} keys: "
            f"{result['from_exact']['seconds'] * 1000:.0f} ms."
        ),
        (
            f"Memory at K = {K:,}: "
            f"{result['memory']['retained_bytes'] / 1024**2:.1f} MB, "
            f"{result['memory']['bytes_per_entry']:.0f} bytes per entry."
        ),
    ]
    (out / "micro.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


# Throwaway prototype of lot 2b ----------------------------------------------


_INSTALLED = False


def _install_prototype() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    from collections import Counter

    from tabalyst.scanner import values
    from tabalyst.scanner.bottomk import BottomKSampler

    processor = values.ValueProcessor
    states: dict[int, BottomKSampler] = {}

    def original(keys: Sequence[RawKey]) -> list[Key]:
        return [
            ("string", key) if isinstance(key, str) else (key[0], str(key[1]))
            for key in keys
        ]

    def table(keys: Sequence[RawKey], counts: Sequence[int]) -> Counter[Key]:
        merged: Counter[Key] = Counter()
        for key, count in zip(original(keys), counts):
            merged[key] += count
        return merged

    release, process, finalize = (
        processor.release,
        processor.process,
        processor.finalize,
    )

    def patched_release(
        self: object,
        keys: list[RawKey],
        counts: list[int],
        limited: object,
        scalars: bool,
    ) -> None:
        release(self, keys, counts, limited, scalars)
        states[id(self)] = BottomKSampler.from_exact(K, table(keys, counts))

    def patched_process(
        self: object,
        keys: list[RawKey],
        counts: list[int],
        collected: object = None,
        scalars: bool = False,
    ) -> object:
        sampler = states.get(id(self))
        if sampler is not None:
            sampler.update(original(keys), counts)
        return process(self, keys, counts, collected, scalars)

    def patched_finalize(
        self: object,
        source: Mapping[RawKey, int] | None,
        *args: object,
        **kwargs: object,
    ) -> object:
        if source is not None and len(source) > K:
            BottomKSampler.from_exact(K, table(list(source), list(source.values())))
        return finalize(self, source, *args, **kwargs)

    processor.release = patched_release
    processor.process = patched_process
    processor.finalize = patched_finalize


def _child(variant: str, path: Path, workers: str) -> None:
    if variant == "prototype":
        _install_prototype()
    from tabalyst import scan

    started = time.perf_counter()
    result = scan(path, workers=1 if workers == "1" else None)
    seconds = time.perf_counter() - started
    print(json.dumps({"seconds": seconds, "rows": result.scope.records_analyzed}))


def _site(out: Path) -> Path:
    """A ``sitecustomize`` that patches every interpreter of the prototype
    run, the workers included (they start from the environment of the scan)."""
    folder = out / "prototype-site"
    folder.mkdir(parents=True, exist_ok=True)
    code = (
        "import os, sys",
        "if os.environ.get('TABALYST_BOTTOMK_PROTOTYPE'):",
        f"    sys.path.insert(0, {str(Path(__file__).resolve().parent)!r})",
        "    import bottomk_hash",
        "    bottomk_hash._install_prototype()",
    )
    newline = chr(10)
    (folder / "sitecustomize.py").write_text(
        newline.join(code) + newline, encoding="utf-8"
    )
    return folder


def _run(variant: str, path: Path, workers: str, site: Path) -> dict[str, float]:
    environment = dict(os.environ)
    if variant == "prototype":
        environment["TABALYST_BOTTOMK_PROTOTYPE"] = "1"
        environment["PYTHONPATH"] = os.pathsep.join(
            [str(site), environment.get("PYTHONPATH", "")]
        )
    completed = subprocess.run(
        [sys.executable, __file__, "--child", variant, str(path), workers],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    return json.loads(completed.stdout.strip().splitlines()[-1])


def engine(files: list[Path], repeat: int, out: Path, workers: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    site = _site(out)
    lines = [
        "| File | Workers | Rows | Without (s) | With (s) | Overhead |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    everything = []
    for path in files:
        runs: dict[str, list[float]] = {"baseline": [], "prototype": []}
        rows = 0
        for index in range(repeat):
            order = (
                ("baseline", "prototype")
                if index % 2 == 0
                else ("prototype", "baseline")
            )
            for variant in order:
                outcome = _run(variant, path, workers, site)
                rows = outcome["rows"]
                runs[variant].append(outcome["seconds"])
                print(
                    f"{path.name} {variant} ({workers}): {outcome['seconds']:.2f} s",
                    flush=True,
                )
        without = statistics.median(runs["baseline"])
        with_ = statistics.median(runs["prototype"])
        everything.append({"file": path.name, "rows": rows, "workers": workers, **runs})
        lines.append(
            f"| {path.name} | {workers} | {rows:,} | {without:.2f} | {with_:.2f} | "
            f"{(with_ / without - 1) * 100:+.1f}% |"
        )
    (out / f"engine-{workers}.json").write_text(
        json.dumps(everything, indent=2), encoding="utf-8"
    )
    (out / f"engine-{workers}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def main() -> None:
    if len(sys.argv) == 5 and sys.argv[1] == "--child":
        _child(sys.argv[2], Path(sys.argv[3]), sys.argv[4])
        return
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("micro", "engine"):
        command = sub.add_parser(name)
        command.add_argument("--out", type=Path, default=DEFAULT_OUT)
        if name == "engine":
            command.add_argument("files", nargs="+", type=Path)
            command.add_argument("--repeat", type=int, default=3)
            command.add_argument(
                "--workers",
                choices=["1", "auto"],
                default="auto",
                help="1: one process; auto: the default of the scan (workers hash).",
            )
    args = parser.parse_args()
    out = args.out.resolve()
    if Path(__file__).resolve().parents[1] in out.parents:
        parser.error("--out must be outside the checkout (see AGENTS.md)")
    os.environ.setdefault("PYTHONUTF8", "1")
    if args.command == "micro":
        micro(out)
    else:
        engine(args.files, args.repeat, out, args.workers)


if __name__ == "__main__":
    main()

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Cost of the priority of a row position (lot 3b, design 18.11).

    python benchmarks/rowsample_priority.py [rows]

Three ways to give 64 bits to each of ``rows`` positions (default 1,000,000):
a BLAKE2b call per position, a splitmix64 mix in Python, and the choice of
the row sample, one BLAKE2b-512 call per block of eight positions. Prints the
seconds for each and the number of distinct priorities.
"""

import gc
import hashlib
import struct
import sys
from time import perf_counter

from tabalyst.scanner.rowsample import RowPriority

SEED = 42
MASK = (1 << 64) - 1


def per_position(rows: int) -> list[int]:
    prototype = hashlib.blake2b(SEED.to_bytes(8, "little"), digest_size=8)
    copy = prototype.copy
    from_bytes = int.from_bytes
    values = []
    append = values.append
    for position in range(rows):
        state = copy()
        state.update(position.to_bytes(8, "little"))
        append(from_bytes(state.digest(), "little"))
    return values


def splitmix(rows: int) -> list[int]:
    values = []
    append = values.append
    for position in range(rows):
        z = (position + (SEED + 1) * 0x9E3779B97F4A7C15) & MASK
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK
        append(z ^ (z >> 31))
    return values


def per_block(rows: int) -> list[int]:
    return RowPriority(SEED).range(0, rows)


def per_block_standalone(rows: int) -> list[int]:
    """The same blocks without the product module, for the reader of this file."""
    prototype = hashlib.blake2b(
        SEED.to_bytes(8, "little"), digest_size=64, person=b"tabalyst.rows.v1"
    )
    unpack = struct.Struct("<8Q").unpack
    values: list[int] = []
    extend = values.extend
    for block in range((rows + 7) // 8):
        state = prototype.copy()
        state.update(block.to_bytes(8, "little"))
        extend(unpack(state.digest()))
    return values[:rows]


def main() -> None:
    rows = int(sys.argv[1]) if len(sys.argv) > 1 else 1_000_000
    for function in (per_position, splitmix, per_block_standalone, per_block):
        # The lists of a million integers weigh on the next measure otherwise.
        gc.collect()
        started = perf_counter()
        values = function(rows)
        seconds = perf_counter() - started
        print(f"{function.__name__:22} {seconds:7.3f} s {len(set(values)):>10} distinct")
        del values


if __name__ == "__main__":
    main()

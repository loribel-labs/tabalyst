# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Canonical key of a CSV row: the exact identity compared by the stores."""

from collections.abc import Sequence

IDENTITY = "full_decoded_csv_row_v1"

# The length of almost every cell fits one LEB128 byte; reusing the byte objects
# keeps the per-cell cost of the hot path at one lookup.
_SHORT = tuple(bytes((length,)) for length in range(0x80))


def varint(value: int) -> bytes:
    """Unsigned LEB128: 7 bits per byte, the high bit says that another byte follows.

    Raises ``ValueError`` for a negative value, which has no code.
    """
    if 0 <= value < 0x80:
        return _SHORT[value]
    if value < 0:
        raise ValueError(f"varint is unsigned, got {value}")
    out = bytearray()
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def canonical_key(row: Sequence[str]) -> bytes:
    """Return the key of a row: the count of cells, then each cell's length and UTF-8 bytes.

    The code is prefix-free, so two different rows never share a key and the key
    decodes in only one way (design dedup 5.2). Cells are compared as decoded, with
    no normalization of case, blanks, digits or Unicode form.

    Raises ``UnicodeEncodeError`` for a lone surrogate, which a file read with a
    strict decoder cannot produce.
    """
    parts = [varint(len(row))]
    for cell in row:
        encoded = cell.encode("utf-8")
        length = len(encoded)
        parts.append(_SHORT[length] if length < 0x80 else varint(length))
        parts.append(encoded)
    return b"".join(parts)

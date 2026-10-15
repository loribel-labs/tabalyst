# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Rare values one edit away from a much more frequent one of the same column (design 20.39).

A typo of a category (``Longueuuil`` for ``Longueuil``) is a value the column holds once or
twice, next to a value it holds hundreds of times. The groups are computed from the exact
table of the second pass and nothing else, so the same table always gives the same groups.
"""

from __future__ import annotations

import unicodedata
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

# A shorter value has too many neighbours to mean anything (``Roy`` and ``Roi``).
MIN_LENGTH = 4
# A value is frequent from this many rows, and at least MIN_RATIO times its neighbour.
MIN_FREQUENT = 10
MIN_RATIO = 10
# A value is rare up to this many rows.
MAX_RARE = 2
# A group lists this many neighbours at most, the most frequent first.
MAX_NEIGHBOURS = 20
# A longer text is a sentence, not a category, and the index of deletions of a text of a
# thousand characters (the longest the Scan keeps) would hold a thousand strings of its size.
MAX_LENGTH = 64


@dataclass(frozen=True, slots=True)
class NearGroup:
    """A frequent value and the rare values of the column one edit away from it.

    ``frequent`` and ``neighbours`` are positions in the table the groups were made
    from; ``count`` is the number of rows of the neighbours listed.
    """

    frequent: int
    neighbours: tuple[int, ...]
    count: int


def fold(text: str) -> str:
    """The text without case, accents and repeated spaces: two texts that fold alike are
    variants of one value (the business of ``variant_groups``), not typos of each other."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return " ".join("".join(c for c in decomposed if not unicodedata.combining(c)).split())


def one_edit(a: str, b: str) -> bool:
    """Whether the texts differ by exactly one insertion, deletion, substitution or
    exchange of two neighbouring characters."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        spots = [i for i, (x, y) in enumerate(zip(a, b, strict=True)) if x != y]
        if len(spots) == 1:
            return True
        return len(spots) == 2 and spots[1] == spots[0] + 1 and a[spots[0]] == b[spots[1]] and (
            a[spots[1]] == b[spots[0]]
        )
    shorter, longer = (a, b) if len(a) < len(b) else (b, a)
    spot = next((i for i, c in enumerate(shorter) if c != longer[i]), len(shorter))
    return shorter[spot:] == longer[spot + 1 :]


def _deletions(text: str) -> set[str]:
    """The text and each text made by removing one character: two texts within one edit
    share one of these, which finds the candidates without comparing every pair."""
    return {text, *(text[:i] + text[i + 1 :] for i in range(len(text)))}


def near_groups(
    table: Sequence[tuple[str, int]],
    *,
    min_length: int = MIN_LENGTH,
    max_length: int = MAX_LENGTH,
    min_frequent: int = MIN_FREQUENT,
    min_ratio: int = MIN_RATIO,
    max_rare: int = MAX_RARE,
    max_neighbours: int = MAX_NEIGHBOURS,
) -> list[NearGroup]:
    """The groups of a column, from its ``(text, rows)`` table, the heaviest first.

    Texts longer than ``max_length`` take no part. A rare value joins the most frequent value one edit away from it (a tie goes to the
    text that sorts first); a value that only differs by case, accents or spaces is a
    variant and joins nobody. Groups are sorted by the rows of their neighbours, then
    by the text of their frequent value, so the result does not depend on the order of
    the table beyond the positions it reports.
    """
    frequent = [
        i for i, (text, rows) in enumerate(table) if rows >= min_frequent and 0 < len(text) <= max_length
    ]
    index: dict[str, list[int]] = defaultdict(list)
    for i in frequent:
        for key in _deletions(table[i][0]):
            index[key].append(i)
    joined: dict[int, list[int]] = defaultdict(list)
    for position, (text, rows) in enumerate(table):
        if not 0 < rows <= max_rare or not min_length <= len(text) <= max_length:
            continue
        candidates = {
            i
            for key in _deletions(text)
            for i in index.get(key, ())
            if table[i][1] >= min_ratio * rows
            and one_edit(table[i][0], text)
            and fold(table[i][0]) != fold(text)
        }
        if candidates:
            best = min(candidates, key=lambda i: (-table[i][1], table[i][0], i))
            joined[best].append(position)
    groups = []
    for best, members in joined.items():
        members.sort(key=lambda i: (-table[i][1], table[i][0], i))
        kept = members[:max_neighbours]
        groups.append(NearGroup(best, tuple(kept), sum(table[i][1] for i in kept)))
    groups.sort(key=lambda g: (-g.count, table[g.frequent][0], g.frequent))
    return groups

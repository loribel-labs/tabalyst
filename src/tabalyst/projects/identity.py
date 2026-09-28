"""Project identity: a generated, opaque ULID (project-storage.md S02).

A ULID is 128 bits written as 26 Crockford base32 characters: 48 bits of
Unix time in milliseconds, then 80 random bits. Identifiers sort by creation
time, are safe as a directory name on every platform, and carry no meaning
that a renamed or copied source could invalidate. Ids of one millisecond are
not ordered among themselves.
"""

import re
import secrets
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_LENGTH = 26
_TIME_BITS = 48
_RANDOM_BITS = 80
# 26 characters hold 130 bits: the first one only carries the top 3, so a
# valid ULID starts with 0 to 7 (its time stays below 2**48 milliseconds).
_PATTERN = re.compile(r"[0-7][0-9A-HJKMNP-TV-Z]{25}")


def new_project_id(*, unix_ms: int | None = None) -> str:
    """Generate a project id; ``unix_ms`` fixes the time part for tests."""
    milliseconds = time.time_ns() // 1_000_000 if unix_ms is None else unix_ms
    if not 0 <= milliseconds < 1 << _TIME_BITS:
        raise ValueError("unix_ms must fit in 48 bits.")
    value = (milliseconds << _RANDOM_BITS) | secrets.randbits(_RANDOM_BITS)
    characters = []
    for _ in range(_LENGTH):
        characters.append(_ALPHABET[value & 31])
        value >>= 5
    return "".join(reversed(characters))


def is_project_id(value: object) -> bool:
    """Whether ``value`` has the form of a project id.

    Storage code checks this before using a name as a directory, so an
    arbitrary string never selects a path.
    """
    return isinstance(value, str) and _PATTERN.fullmatch(value) is not None

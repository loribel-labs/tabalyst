# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Shape signature of a value (design 12.5): ASCII digits become ``9``,
uppercase letters ``A``, other letters ``a``; other characters are kept and
runs of one character are compressed. ``2026-09-26`` has the shape ``9-9-9``
and ``Québec`` the shape ``Aa``.
"""

from __future__ import annotations

import re
import string

_ASCII = str.maketrans(
    {
        **dict.fromkeys(string.digits, "9"),
        **dict.fromkeys(string.ascii_uppercase, "A"),
        **dict.fromkeys(string.ascii_lowercase, "a"),
    }
)
_RUNS = re.compile(r"(.)\1+", re.DOTALL)


def _symbol(char: str) -> str:
    if "0" <= char <= "9":
        return "9"
    if char.isalpha():
        return "A" if char.isupper() else "a"
    return char


def shape(value: str) -> str:
    """Compressed shape signature of ``value``."""
    if value.isascii():
        mapped = value.translate(_ASCII)
    else:
        mapped = "".join(map(_symbol, value))
    return _RUNS.sub(r"\1", mapped)

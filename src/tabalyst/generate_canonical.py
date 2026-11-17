# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Canonical value of a clean cell: what it means, written one way (contract insurance-v2.md 4.5)."""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime

_PLAIN_DECIMAL = re.compile(r"[+-]?\d+(?:\.\d+)?\Z")
_DECIMAL_COMMA = re.compile(r"[+-]?\d+,\d+\Z")


def canonical_text(value: str) -> str:
    """Return a text in NFC without surrounding whitespace."""
    return unicodedata.normalize("NFC", value).strip()


def canonical_decimal(value: str) -> str:
    """Return an amount as a plain decimal with ``.`` and no unit or grouping.

    A value that is not an amount is returned trimmed: the canonical form never invents one.
    """
    text = re.sub(r"[\s $]|CAD", "", value)
    if re.fullmatch(r"[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?", text):
        text = text.replace(",", "")
    elif _DECIMAL_COMMA.fullmatch(text):
        text = text.replace(",", ".")
    return text if _PLAIN_DECIMAL.fullmatch(text) else value.strip()


def canonical_date(value: str, date_format: str) -> str:
    """Return a date read with ``date_format`` as ISO 8601.

    Raises ValueError when the value does not parse with the format: the clean file only holds
    valid dates, so a failure means a wrong convention, and a truth with a guessed value would
    be worse than no truth.
    """
    # A date has no zone: UTC only satisfies the naive-datetime rule, the day is kept.
    return datetime.strptime(value.strip(), date_format).replace(tzinfo=UTC).date().isoformat()

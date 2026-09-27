"""Date and time detector (design 9.6, 12.6 and 12.10).

Accepted forms, all with ASCII digits:

- numeric dates of the current engine: a four-digit year first (``YMD``) or
  last (``MDY``, ``DMY``), one- or two-digit month and day, one configured
  separator used twice;
- ISO 8601 date-times: ``YYYY-MM-DD``, ``T`` or a space, ``HH:MM``, optional
  seconds and fraction (up to six digits), optional ``Z`` or offset;
- times: ``H:MM`` or ``HH:MM``, optional seconds and fraction;
- dates with English or French month names, full or abbreviated:
  ``26 September 2026``, ``1er janvier 2026``, ``September 26, 2026``.

A value with both ``MDY`` and ``DMY`` readings stays ambiguous unless
``ambiguous_order`` resolves it. Evidence from unambiguous values of the field
is exposed, never applied (O06).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, date, datetime, time, timedelta, timezone

from tabalyst.scanner.detectors.base import (
    AmbiguityAccumulator,
    Classification,
    Detector,
)
from tabalyst.scanner.models import (
    Complete,
    NotApplicable,
    TemporalKind,
    TemporalStats,
    YearCount,
)

# Longer than every accepted form, so longer values are not matched.
_MAX_LENGTH = 40
_ISO_DATETIME = re.compile(
    r"([0-9]{4})-([0-9]{2})-([0-9]{2})([T ])([0-9]{2}):([0-9]{2})"
    r"(?::([0-9]{2})(?:\.([0-9]{1,6}))?)?(Z|[+-][0-9]{2}(?::?[0-9]{2})?)?"
)
_TIME = re.compile(r"([0-9]{1,2}):([0-9]{2})(?::([0-9]{2})(?:\.([0-9]{1,6}))?)?")
_DAY_FIRST = re.compile(r"([0-9]{1,2})(er)? ([^\W\d_]+)(\.?) ([0-9]{4})", re.IGNORECASE)
_MONTH_FIRST = re.compile(r"([^\W\d_]+)(\.?) ([0-9]{1,2})(,?) ([0-9]{4})")

_FULL = {
    "en": (
        "january february march april may june july august september october "
        "november december"
    ),
    "fr": (
        "janvier février|fevrier mars avril mai juin juillet août|aout septembre "
        "octobre novembre décembre|decembre"
    ),
}
_ABBREVIATED = {
    "en": "jan feb mar apr - jun jul aug sep|sept oct nov dec",
    "fr": "janv févr|fevr - avr - - juil - sept oct nov déc|dec",
}


def _month_names(languages: list[str]) -> dict[str, tuple[int, str]]:
    """Casefolded month name to its number and format label."""
    names: dict[str, tuple[int, str]] = {}
    for language in languages:
        for table, label in ((_FULL, "MMMM"), (_ABBREVIATED, "MMM")):
            for month, spellings in enumerate(table[language].split(), start=1):
                for spelling in spellings.split("|"):
                    if spelling != "-":
                        names[spelling] = (month, label)
    return names


def _date_format(
    order: str, first: str, second: str, third: str, separator: str
) -> str:
    """Component order, separator and zero-padding, as the current engine."""
    if order == "YMD":
        month, day = second, third
        parts = ("YYYY", _pad("M", month), _pad("D", day))
    elif order == "MDY":
        parts = (_pad("M", first), _pad("D", second), "YYYY")
    else:
        parts = (_pad("D", first), _pad("M", second), "YYYY")
    return separator.join(parts)


def _pad(letter: str, text: str) -> str:
    return letter * 2 if len(text) == 2 else letter


def _calendar(order: str, first: int, second: int, third: int) -> date | None:
    if order == "YMD":
        year, month, day = first, second, third
    elif order == "MDY":
        month, day, year = first, second, third
    else:
        day, month, year = first, second, third
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _clock(
    hour: str, minute: str, second: str | None, fraction: str | None
) -> tuple[int, int, int, int] | None:
    values = (int(hour), int(minute), int(second or 0))
    if values[0] > 23 or values[1] > 59 or values[2] > 59:
        return None
    return (*values, int((fraction or "").ljust(6, "0")))


def _clock_format(hour: str, second: str | None, fraction: str | None) -> str:
    label = _pad("H", hour) + ":MM"
    if second is not None:
        label += ":SS"
    if fraction is not None:
        label += "." + "f" * len(fraction)
    return label


def _offset(text: str) -> tuple[timezone, str] | None:
    if text == "Z":
        return UTC, "Z"
    digits = text[1:].replace(":", "")
    hours, minutes = int(digits[:2]), int(digits[2:] or 0)
    if hours > 23 or minutes > 59:
        return None
    delta = timedelta(hours=hours, minutes=minutes)
    label = "±HH:MM" if ":" in text else ("±HHMM" if len(digits) == 4 else "±HH")
    return timezone(-delta if text[0] == "-" else delta), label


def _invalid(reason: str) -> Classification:
    return Classification("invalid", reason=reason)


class DateDetector(Detector):
    id = "date"
    family = "temporal"

    def __init__(self, settings: Mapping[str, object]) -> None:
        super().__init__(settings)
        self.orders = tuple(settings.get("orders", ("YMD", "MDY", "DMY")))
        separators = "".join(
            re.escape(separator)
            for separator in settings.get("separators", ("-", "/", "."))
        )
        self._numeric = re.compile(
            rf"([0-9]{{1,4}})([{separators}])([0-9]{{1,4}})([{separators}])"
            r"([0-9]{1,4})"
        )
        self.resolution = settings.get("ambiguous_order")
        languages = list(settings.get("month_languages", ("en", "fr")))
        self._day_first = _month_names(languages)
        # Month-first dates are an English form.
        self._month_first = _month_names(["en"]) if "en" in languages else {}

    def classify(self, value: str) -> Classification | None:
        if not value or len(value) > _MAX_LENGTH:
            return None
        if not "0" <= value[0] <= "9":
            # Only month-first dates start with something else than a digit.
            return self._month_first_date(value) if self._month_first else None
        match = self._numeric.fullmatch(value)
        if match is not None:
            return self._numeric_date(*match.groups())
        match = _ISO_DATETIME.fullmatch(value)
        if match is not None:
            return _iso_datetime(*match.groups())
        match = _TIME.fullmatch(value)
        if match is not None:
            hour, minute, second, fraction = match.groups()
            clock = _clock(hour, minute, second, fraction)
            if clock is None:
                return _invalid("invalid_time")
            return Classification(
                "matched",
                format=_clock_format(hour, second, fraction),
                value=time(*clock),
            )
        return self._day_first_date(value) if self._day_first else None

    def _numeric_date(
        self, first: str, separator: str, second: str, other: str, third: str
    ) -> Classification | None:
        """The rule of the current engine, without resolution from evidence."""
        if len(first) == 4 and len(second) <= 2 and len(third) <= 2:
            possible = ("YMD",)
        elif len(third) == 4 and len(first) <= 2 and len(second) <= 2:
            possible = ("MDY", "DMY")
        elif len(first) == 4:
            return _invalid("invalid_component_width")
        else:
            return None
        if separator != other:
            return _invalid("mixed_separators")
        allowed = [order for order in possible if order in self.orders]
        if not allowed:
            return _invalid("unsupported_order")
        numbers = (int(first), int(second), int(third))
        valid = {
            order: parsed
            for order in allowed
            if (parsed := _calendar(order, *numbers)) is not None
        }
        if not valid:
            return _invalid("invalid_calendar_date")
        formats = {
            order: _date_format(order, first, second, third, separator)
            for order in valid
        }
        if len(valid) == 1:
            ((order, parsed),) = valid.items()
            return Classification(
                "matched", format=formats[order], value=parsed, convention=order
            )
        candidates = tuple(sorted(formats.values()))
        if self.resolution in valid:
            return Classification(
                "matched",
                format=formats[self.resolution],
                value=valid[self.resolution],
                candidates=candidates,
            )
        return Classification("ambiguous", candidates=candidates)

    def _day_first_date(self, value: str) -> Classification | None:
        match = _DAY_FIRST.fullmatch(value)
        if match is None:
            return None
        day, ordinal, name, dot, year = match.groups()
        if ordinal and day != "1":
            return None
        found = self._month(self._day_first, name, dot)
        if found is None:
            return None
        month, label = found
        return _named_date(year, month, day, f"{_pad('D', day)} {label} YYYY")

    def _month_first_date(self, value: str) -> Classification | None:
        match = _MONTH_FIRST.fullmatch(value)
        if match is None:
            return None
        name, dot, day, comma, year = match.groups()
        found = self._month(self._month_first, name, dot)
        if found is None:
            return None
        month, label = found
        return _named_date(year, month, day, f"{label} {_pad('D', day)}{comma} YYYY")

    @staticmethod
    def _month(
        names: dict[str, tuple[int, str]], name: str, dot: str
    ) -> tuple[int, str] | None:
        found = names.get(name.casefold())
        if found is None:
            return None
        month, label = found
        if dot:
            if label != "MMM":
                return None
            label += "."
        return month, label

    def accumulator(self) -> DateAccumulator:
        readings = [order for order in ("DMY", "MDY") if order in self.orders]
        resolution = (
            None
            if self.resolution is None
            else {"order": self.resolution, "source": "config"}
        )
        return DateAccumulator(readings if len(readings) == 2 else [], resolution)


def _named_date(year: str, month: int, day: str, label: str) -> Classification:
    try:
        parsed = date(int(year), month, int(day))
    except ValueError:
        return _invalid("invalid_calendar_date")
    return Classification("matched", format=label, value=parsed)


def _iso_datetime(
    year, month, day, separator, hour, minute, second, fraction, offset
) -> Classification:
    try:
        day_value = date(int(year), int(month), int(day))
    except ValueError:
        return _invalid("invalid_calendar_date")
    clock = _clock(hour, minute, second, fraction)
    if clock is None:
        return _invalid("invalid_time")
    label = f"YYYY-MM-DD{separator}{_clock_format(hour, second, fraction)}"
    zone = None
    if offset is not None:
        parsed = _offset(offset)
        if parsed is None:
            return _invalid("invalid_offset")
        zone, offset_label = parsed
        label += offset_label
    return Classification(
        "matched", format=label, value=datetime.combine(day_value, time(*clock, zone))
    )


_KINDS = ("date", "datetime_naive", "datetime_aware", "time")


class _KindStats:
    __slots__ = ("count", "maximum", "minimum", "years")

    def __init__(self, dated: bool) -> None:
        self.count = 0
        self.minimum: tuple | None = None
        self.maximum: tuple | None = None
        self.years: dict[int, int] | None = {} if dated else None

    def add(self, value, count: int) -> None:
        self.count += count
        # Aware values compare as instants; the text breaks ties between
        # offsets so the result never depends on processing order.
        key = (value, value.isoformat())
        if self.minimum is None or key < self.minimum:
            self.minimum = key
        if self.maximum is None or key > self.maximum:
            self.maximum = key
        if self.years is not None:
            self.years[value.year] = self.years.get(value.year, 0) + count


def _kind(value: object) -> str | None:
    if type(value) is date:
        return "date"
    if type(value) is datetime:
        return "datetime_naive" if value.tzinfo is None else "datetime_aware"
    if type(value) is time:
        return "time"
    return None


class DateAccumulator(AmbiguityAccumulator):
    """Ambiguity details and the ``temporal`` block of the field (design
    9.6): ambiguous values are counted, never compared."""

    __slots__ = ("kinds", "unresolved")

    def __init__(self, readings: list[str], resolution: dict[str, str] | None) -> None:
        super().__init__(readings, resolution)
        self.kinds: dict[str, _KindStats] = {}
        self.unresolved = 0

    def add(
        self, value: str, classification: Classification | None, count: int
    ) -> None:
        super().add(value, classification, count)
        if classification is None:
            return
        if classification.state == "ambiguous":
            self.unresolved += count
        elif classification.state == "matched":
            kind = _kind(classification.value)
            if kind is not None:
                stats = self.kinds.get(kind)
                if stats is None:
                    stats = self.kinds[kind] = _KindStats(kind != "time")
                stats.add(classification.value, count)

    def temporal(self):
        if not self.kinds and not self.unresolved:
            return NotApplicable(reason="no_values")
        kinds = [
            TemporalKind(
                kind=kind,
                count=stats.count,
                min=stats.minimum[1],
                max=stats.maximum[1],
                years=(
                    None
                    if stats.years is None
                    else [
                        YearCount(year=year, count=stats.years[year])
                        for year in sorted(stats.years)
                    ]
                ),
            )
            for kind in _KINDS
            if (stats := self.kinds.get(kind)) is not None
        ]
        return Complete[TemporalStats](
            value=TemporalStats(
                count=sum(item.count for item in kinds),
                ambiguous=self.unresolved,
                kinds=kinds,
            )
        )

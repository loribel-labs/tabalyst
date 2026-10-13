# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The reference corpus of the pattern discovery, RC-01 to RC-20 (block B1).

Every field is synthetic, built by a generator with a fixed seed at the scale the
algorithm fixes (algorithm, section 7; specification, annex A). No value comes
from a real dataset: card and social insurance numbers fail the Luhn check,
telephone numbers use the ranges reserved for fiction, e-mail local parts and
long-tail domains are random.
"""

from __future__ import annotations

import random
import string
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from functools import cache
from typing import Literal

UPPER = string.ascii_uppercase
LOWER = string.ascii_lowercase
DIGITS = string.digits

Pairs = tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class Field:
    """One column of a case: its distinct values with their occurrences.

    ``mode`` is ``informative`` for the generic discovery and ``declared`` for
    the keys of a detector (algorithm, section 4). ``file`` holds the values of
    the whole file when the discovery only sees a part of it (RC-14).
    """

    case: str
    name: str
    pairs: Pairs
    mode: Literal["informative", "declared"] = "informative"
    detector: str | None = None
    masked: bool = False
    toy: bool = False
    file: Pairs | None = None

    @property
    def id(self) -> str:
        return f"{self.case}/{self.name}"

    @property
    def distinct(self) -> int:
        return len(self.pairs)

    @property
    def occurrences(self) -> int:
        return sum(count for _, count in self.pairs)

    def values(self) -> list[str]:
        return [value for value, _ in self.pairs]


def _rng(case: str, name: str) -> random.Random:
    # A string seed is hashed with SHA-512 by ``random.seed`` (version 2): the
    # same on every platform and Python version.
    return random.Random(f"tabalyst-patterns/{case}/{name}")


def _pairs(values: Iterable[str]) -> Pairs:
    """Distinct values with their occurrences, sorted by value."""
    return tuple(sorted(Counter(values).items()))


def _ones(values: Iterable[str]) -> Pairs:
    """Distinct values counted once each; a repeated value is a generator bug."""
    listed = list(values)
    if len(set(listed)) != len(listed):
        raise ValueError("a generator produced the same value twice")
    return tuple(sorted((value, 1) for value in listed))


def _text(rng: random.Random, alphabet: str, size: int) -> str:
    return "".join(alphabet[rng.randrange(len(alphabet))] for _ in range(size))


def _distinct(
    rng: random.Random, count: int, make: Callable[..., str], taken: set[str]
) -> list[str]:
    """``count`` new values from ``make``, none already in ``taken``. ``make``
    takes no argument; its loop variables are bound as defaults."""
    found: list[str] = []
    while len(found) < count:
        value = make()
        if value not in taken:
            taken.add(value)
            found.append(value)
    return found


def luhn_valid(digits: str) -> bool:
    """Whether a string of digits passes the Luhn check (cards, SIN)."""
    total = 0
    for position, char in enumerate(reversed(digits)):
        digit = int(char)
        if position % 2:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def _not_luhn(rng: random.Random, head: str, size: int) -> str:
    """``head`` followed by random digits up to ``size``, failing the Luhn check
    so that it can never be a real card or social insurance number."""
    body = head + _text(rng, DIGITS, size - len(head) - 1)
    last = rng.randrange(10)
    if luhn_valid(body + str(last)):
        last = (last + 1) % 10
    return body + str(last)


# RC-01 to RC-04: prefixes, composition and weights -------------------------------


def rc01() -> list[Field]:
    values = ["AK-125", "AK-584", "AK-953", "AK-4535", "AK-5572", "AK-6219"]
    return [Field("RC-01", "toy", _ones(values), toy=True)]


def rc02() -> list[Field]:
    rng = _rng("RC-02", "scaled")
    taken: set[str] = set()
    values: list[str] = []
    # The second letter and the last character are independent: each letter
    # has three values ending with a digit for one ending with a letter.
    for letter, count in (("K", 80), ("B", 72), ("Z", 48)):
        digits = count * 3 // 4
        values += _distinct(
            rng,
            digits,
            lambda letter=letter: f"A{letter}-{_text(rng, DIGITS, 5)}",
            taken,
        )
        values += _distinct(
            rng,
            count - digits,
            lambda letter=letter: (
                f"A{letter}-{_text(rng, DIGITS, 4)}{_text(rng, UPPER, 1)}"
            ),
            taken,
        )
    toy = ["AK-2145A", "AK-21454", "AB-21554", "AZ-31554"]
    return [
        Field("RC-02", "scaled", _ones(values)),
        Field("RC-02", "toy", _ones(toy), toy=True),
    ]


RC03_PREFIXES = ("AK", "AB", "AZ", "BC", "CD", "DE", "KM", "PQ", "RT", "ZX")


def rc03() -> list[Field]:
    rng = _rng("RC-03", "scaled")
    taken: set[str] = set()
    values: list[str] = []
    for prefix in RC03_PREFIXES:
        values += _distinct(
            rng, 50, lambda prefix=prefix: f"{prefix}-{_text(rng, DIGITS, 4)}", taken
        )
    toy = ["AK-1234", "AK-5678", "AB-2345", "AZ-7890", "BC-4567"]
    return [
        Field("RC-03", "scaled", _ones(values)),
        Field("RC-03", "toy", _ones(toy), toy=True),
    ]


def rc04() -> list[Field]:
    pairs = (("AB-1234", 500), ("AK-1234", 12_000), ("AK-5678", 8_000), ("AZ-9876", 100))
    return [Field("RC-04", "weighted", pairs)]


# RC-05 and RC-06: blocks, years and variable lengths --------------------------------


def rc05() -> list[Field]:
    rng = _rng("RC-05", "invoices")
    taken: set[str] = set()
    independent: list[str] = []
    for prefix in ("INV", "ORD"):
        for year in ("2025", "2026"):
            independent += _distinct(
                rng,
                100,
                lambda prefix=prefix, year=year: (
                    f"{prefix}-{year}-{_text(rng, DIGITS, 6)}"
                ),
                taken,
            )
    rng = _rng("RC-05", "invoices_dependent")
    taken = set()
    dependent: list[str] = []
    # The year depends on the prefix: INV is mostly 2025, ORD mostly 2026.
    for prefix, year, count in (
        ("INV", "2025", 150),
        ("INV", "2026", 50),
        ("ORD", "2025", 50),
        ("ORD", "2026", 150),
    ):
        dependent += _distinct(
            rng,
            count,
            lambda prefix=prefix, year=year: f"{prefix}-{year}-{_text(rng, DIGITS, 6)}",
            taken,
        )
    rng = _rng("RC-05", "references")
    taken = set()
    references: list[str] = []
    for head, count in (("CUS", 150), ("SUP", 100), ("PRD-CA", 80), ("PRD-US", 70)):
        references += _distinct(
            rng, count, lambda head=head: f"{head}-{_text(rng, DIGITS, 6)}", taken
        )
    return [
        Field("RC-05", "invoices", _ones(independent)),
        Field("RC-05", "invoices_dependent", _ones(dependent)),
        Field("RC-05", "references", _ones(references)),
    ]


def rc06() -> list[Field]:
    rng = _rng("RC-06", "invoices")
    taken: set[str] = set()
    values: list[str] = []
    for size in (3, 4, 5):
        values += _distinct(
            rng, 100, lambda size=size: f"INV-{_text(rng, DIGITS, size)}", taken
        )
    values += _distinct(rng, 100, lambda: f"INV-2026-{_text(rng, DIGITS, 5)}", taken)
    return [Field("RC-06", "invoices", _ones(values))]


# RC-07 and RC-08: licence plates ------------------------------------------------------

# Letters of French plates (SIV): never I, O or U.
FR_PLATE_LETTERS = "".join(c for c in UPPER if c not in "IOU")
UK_AREA_TAGS = (
    ("LA", 80),
    ("LB", 60),
    ("LC", 20),
    ("MA", 60),
    ("MB", 40),
    ("YA", 50),
    ("YB", 30),
    ("KA", 30),
    ("KB", 20),
    ("KC", 10),
)
UK_AGES = ("21", "71", "22", "72", "23", "73", "24", "74")


def rc07() -> list[Field]:
    rng = _rng("RC-07", "plates")
    taken: set[str] = set()
    values: list[str] = []
    makers: list[tuple[int, Callable[[], str]]] = [
        (200, lambda: f"{_text(rng, DIGITS, 3)} {_text(rng, UPPER, 3)}"),
        (200, lambda: f"{_text(rng, UPPER, 3)} {_text(rng, DIGITS, 3)}"),
        (150, lambda: f"{_text(rng, UPPER, 1)}{_text(rng, DIGITS, 2)} {_text(rng, UPPER, 3)}"),
        (50, lambda: f"{_text(rng, DIGITS, 3)}H{_text(rng, DIGITS, 3)}"),
        (60, lambda: f"CC {_text(rng, DIGITS, 4)}"),
        (40, lambda: f"CD {_text(rng, DIGITS, 4)}"),
        (90, lambda: f"VA{_text(rng, DIGITS, 1)} {_text(rng, UPPER, 3)}"),
        (60, lambda: f"VE{_text(rng, DIGITS, 1)} {_text(rng, UPPER, 3)}"),
    ]  # fmt: skip
    for count, make in makers:
        values += _distinct(rng, count, make, taken)
    return [Field("RC-07", "plates", _ones(values))]


def rc08() -> list[Field]:
    rng = _rng("RC-08", "plates")
    taken: set[str] = set()
    values = _distinct(
        rng,
        600,
        lambda: (
            f"{_text(rng, FR_PLATE_LETTERS, 2)}-{rng.randrange(1, 1000):03d}"
            f"-{_text(rng, FR_PLATE_LETTERS, 2)}"
        ),
        taken,
    )
    position = 0
    for tag, count in UK_AREA_TAGS:
        for _ in range(count):
            # The age identifiers cycle, so that they stay independent of the tag.
            age = UK_AGES[position % len(UK_AGES)]
            position += 1
            values += _distinct(
                rng,
                1,
                lambda tag=tag, age=age: (
                    f"{tag}{age} {_text(rng, FR_PLATE_LETTERS, 3)}"
                ),
                taken,
            )
    return [Field("RC-08", "plates", _ones(values))]


# RC-09 to RC-12: permits, social insurance, cards, ISBN and codes --------------------


def rc09() -> list[Field]:
    rng = _rng("RC-09", "permits")
    taken: set[str] = set()
    values = _distinct(
        rng, 10_000, lambda: _text(rng, UPPER, 1) + _text(rng, DIGITS, 12), taken
    )
    return [Field("RC-09", "permits", _ones(values))]


def rc10() -> list[Field]:
    fields = []
    for name, heads in (
        # A 9 in 30 % of the numbers; the other first digits are 1 to 7, as a
        # real register that never starts with 0 or 8 (OPEN-008).
        ("nine_30", [("9", 300)] + [(str(d), 100) for d in range(1, 8)]),
        # A 9 in 10 %: the level of chance for a digit.
        ("nine_10", [(str(d), 100) for d in range(10)]),
    ):
        rng = _rng("RC-10", name)
        taken: set[str] = set()
        values: list[str] = []
        for head, count in heads:
            values += _distinct(
                rng, count, lambda head=head, rng=rng: _not_luhn(rng, head, 9), taken
            )
        fields.append(Field("RC-10", name, _ones(values)))
    return fields


# (first digits, length, count); "6" is 10 % of the 16-digit cards.
RC11_CARDS = (
    ("4", 16, 400),
    ("51", 16, 64),
    ("52", 16, 64),
    ("53", 16, 64),
    ("54", 16, 64),
    ("55", 16, 64),
    ("6", 16, 80),
    ("34", 15, 75),
    ("37", 15, 75),
    ("36", 14, 50),
)


def rc11() -> list[Field]:
    rng = _rng("RC-11", "cards")
    taken: set[str] = set()
    values: list[str] = []
    for head, size, count in RC11_CARDS:
        values += _distinct(
            rng, count, lambda head=head, size=size: _not_luhn(rng, head, size), taken
        )
    return [Field("RC-11", "cards", _ones(values))]


# (prefix, registration group, count): the group depends on the prefix.
RC12_GROUPS = (
    ("978", "0", 200),
    ("978", "1", 150),
    ("978", "2", 250),
    ("978", "3", 100),
    ("979", "10", 200),
    ("979", "8", 100),
)


def rc12() -> list[Field]:
    rng = _rng("RC-12", "isbn")
    taken: set[str] = set()
    isbn: list[str] = []
    for prefix, group, count in RC12_GROUPS:

        def make(prefix: str = prefix, group: str = group) -> str:
            # The group, the publisher and the title take 9 digits, the title
            # at least one.
            publisher = rng.randrange(2, 9 - len(group))
            title = 9 - len(group) - publisher
            return (
                f"{prefix}-{group}-{_text(rng, DIGITS, publisher)}"
                f"-{_text(rng, DIGITS, title)}-{_text(rng, DIGITS, 1)}"
            )

        isbn += _distinct(rng, count, make, taken)
    rng = _rng("RC-12", "codes")
    # Synthetic codes, not the ISO lists: 40 of two letters and 15 of three, with
    # a Zipf-like weight. Each code is listed with its occurrences.
    codes: dict[str, int] = {}
    for size, number, total in ((2, 40, 600), (3, 15, 400)):
        names = _distinct(rng, number, lambda size=size: _text(rng, UPPER, size), set())
        weights = [1 / rank for rank in range(1, number + 1)]
        scale = total / sum(weights)
        counts = [max(1, round(weight * scale)) for weight in weights]
        counts[0] += total - sum(counts)
        codes.update(zip(names, counts, strict=True))
    return [
        Field("RC-12", "isbn", _ones(isbn)),
        Field("RC-12", "codes", tuple(sorted(codes.items()))),
    ]


# RC-13 to RC-17: dominance, new prefixes, raw variants, segments and noise --------------

RC13_OTHERS = ("BC", "CD", "DE", "EF", "FG", "GH", "HJ", "JK", "KL", "LM")


def rc13() -> list[Field]:
    rng = _rng("RC-13", "identifiers")
    taken: set[str] = set()
    values: list[str] = []
    for prefix, count in (("AK", 9_500), ("AB", 400), ("AZ", 90)) + tuple(
        (other, 1) for other in RC13_OTHERS
    ):
        values += _distinct(
            rng, count, lambda prefix=prefix: f"{prefix}-{_text(rng, DIGITS, 6)}", taken
        )
    return [Field("RC-13", "identifiers", _ones(values))]


RC14_SAMPLED = ("AK", "BC", "CD", "DE", "EF", "FG", "GH", "HJ")
RC14_NEW = ("KL", "MN", "PQ", "RS")


def rc14() -> list[Field]:
    rng = _rng("RC-14", "prefixes")
    taken: set[str] = set()
    file: list[str] = []
    sample: list[str] = []
    for prefix in RC14_SAMPLED:
        drawn = _distinct(
            rng, 200, lambda prefix=prefix: f"{prefix}-{_text(rng, DIGITS, 4)}", taken
        )
        file += drawn
        sample += drawn[:50]
    # Four rare prefixes the discovery never sees.
    for prefix in RC14_NEW:
        file += _distinct(
            rng, 5, lambda prefix=prefix: f"{prefix}-{_text(rng, DIGITS, 4)}", taken
        )
    return [Field("RC-14", "prefixes", _ones(sample), file=_ones(file))]


def rc15() -> list[Field]:
    values = ["AK-1234", "ak-1234", "AK 1234", "AK- 1234", "AK1234"]
    return [Field("RC-15", "raw_variants", _ones(values))]


RC16_PREFIXES = (("LOT", 7), ("SER", 3))
RC16_MIDDLES = (("07", 6), ("12", 3), ("31", 1))
RC16_SUFFIXES = (("EU", 5), ("NA", 4), ("AS", 1))


def rc16() -> list[Field]:
    rng = _rng("RC-16", "lots")
    # Exact independence: each combination gets 1000 * p * m * s identifiers.
    segments = [
        (prefix, middle, suffix)
        for prefix, p in RC16_PREFIXES
        for middle, m in RC16_MIDDLES
        for suffix, s in RC16_SUFFIXES
        for _ in range(p * m * s)
    ]
    rng.shuffle(segments)
    taken: set[str] = set()
    values = []
    for number, (prefix, middle, suffix) in enumerate(segments):
        # 30 % of the numbers end with 00, whatever the segments.
        if number < 300:
            make = lambda: _text(rng, DIGITS, 4) + "00"
        else:
            make = lambda: _text(rng, DIGITS, 6)
        digits = _distinct(rng, 1, make, taken)[0]
        values.append(f"{prefix}-{middle}-{digits}-{suffix}")
    return [Field("RC-16", "lots", _ones(values))]


def rc17() -> list[Field]:
    rng = _rng("RC-17", "noise")
    taken: set[str] = set()
    values = _distinct(
        rng, 1_000, lambda: f"{_text(rng, UPPER, 2)}-{_text(rng, DIGITS, 4)}", taken
    )
    return [Field("RC-17", "noise", _ones(values))]


# RC-18 to RC-20: keys declared by the detectors -----------------------------------------

RC18_DOMAINS = (
    ("gmail.com", 4_000),
    ("hotmail.com", 1_200),
    ("outlook.com", 800),
    ("videotron.ca", 500),
    ("yahoo.ca", 400),
)
# Extensions of the long tail and their weight.
RC18_TAIL_EXTENSIONS = (("com", 5), ("ca", 3), ("fr", 1), ("net", 1))
RC18_TAIL_DOMAINS = 2_000
RC18_ROWS = 10_000


def rc18() -> list[Field]:
    rng = _rng("RC-18", "emails")
    names: set[str] = {domain for domain, _ in RC18_DOMAINS}
    weighted = "".join(
        str(index) * weight for index, (_, weight) in enumerate(RC18_TAIL_EXTENSIONS)
    )
    tail = _distinct(
        rng,
        RC18_TAIL_DOMAINS,
        lambda: (
            _text(rng, LOWER, 6 + rng.randrange(5))
            + "."
            + RC18_TAIL_EXTENSIONS[int(weighted[rng.randrange(len(weighted))])][0]
        ),
        names,
    )
    rows = RC18_ROWS - sum(count for _, count in RC18_DOMAINS)
    # Every tail domain has at least one line and at most four.
    lines = [1] * len(tail)
    extra = rows - len(tail)
    while extra:
        index = rng.randrange(len(tail))
        if lines[index] < 4:
            lines[index] += 1
            extra -= 1
    domains = [domain for domain, count in RC18_DOMAINS for _ in range(count)]
    domains += [domain for domain, count in zip(tail, lines, strict=True) for _ in range(count)]
    taken: set[str] = set()
    values = [
        _distinct(rng, 1, lambda domain=domain: f"u{_text(rng, LOWER + DIGITS, 7)}@{domain}", taken)[0]
        for domain in domains
    ]  # fmt: skip
    return [
        Field(
            "RC-18", "emails", _ones(values), mode="declared", detector="email", masked=True
        )
    ]


# North American area codes and their rows; the line numbers stay in NANPA's
# fiction range 555-0100 to 555-0199.
RC19_NANP = (("514", 2_800), ("450", 1_600), ("438", 1_200), ("418", 1_200), ("819", 800))
RC19_NANP_OTHERS = tuple(str(code) for code in range(201, 217))
RC19_NANP_OTHER_ROWS = 25
# French zones, each in a block ARCEP reserves for fiction, and their rows.
RC19_FR = (
    ("6", "06 39 98", 1_000),
    ("1", "01 99 00", 600),
    ("4", "04 65 71", 300),
    ("2", "02 61 91", 34),
    ("3", "03 53 01", 33),
    ("5", "05 36 49", 33),
)


def _nanp_format(rng: random.Random, area: str) -> str:
    line = f"01{rng.randrange(100):02d}"
    forms = (
        f"({area}) 555-{line}",
        f"+1 {area}-555-{line}",
        f"{area}.555.{line}",
        f"{area}-555-{line}",
        f"1-{area}-555-{line}",
    )
    return forms[rng.randrange(len(forms))]


def _fr_format(rng: random.Random, block: str) -> str:
    pairs = block.split() + [f"{rng.randrange(100):02d}", f"{rng.randrange(100):02d}"]
    forms = (
        " ".join(pairs),
        "+33 " + pairs[0][1] + " " + " ".join(pairs[1:]),
        "".join(pairs),
        ".".join(pairs),
    )
    return forms[rng.randrange(len(forms))]


def rc19() -> list[Field]:
    rng = _rng("RC-19", "phones")
    rows: list[str] = []
    for area, count in RC19_NANP:
        rows += [_nanp_format(rng, area) for _ in range(count)]
    for area in RC19_NANP_OTHERS:
        rows += [_nanp_format(rng, area) for _ in range(RC19_NANP_OTHER_ROWS)]
    for _, block, count in RC19_FR:
        rows += [_fr_format(rng, block) for _ in range(count)]
    return [
        Field("RC-19", "phones", _pairs(rows), mode="declared", detector="phone", masked=True)
    ]


# First letters of the postal codes and their rows (10 000 in all).
RC20_LETTERS = (
    ("H", 2_000), ("M", 1_800), ("G", 1_200), ("J", 1_000), ("K", 800), ("L", 800),
    ("V", 700), ("T", 500), ("E", 300), ("B", 250), ("R", 200), ("S", 200),
    ("N", 100), ("P", 60), ("A", 40), ("C", 30), ("Y", 10), ("X", 10),
)  # fmt: skip
# Forward sortation areas that weigh at least 2 % of their letter.
RC20_HEAVY = {"H": (("H2X", 200), ("H3A", 120)), "G": (("G1V", 180), ("G1R", 96))}
# How many light areas share the rest of a letter: each stays under 2 %.
RC20_LIGHT = {"H": 60, "G": 42}
RC20_LIGHT_DEFAULT = 64
# Letters Canada Post never uses after the first position.
CA_LETTERS = "".join(c for c in UPPER if c not in "DFIOQU")


def rc20() -> list[Field]:
    rng = _rng("RC-20", "postal_codes")
    rows: list[str] = []
    for letter, count in RC20_LETTERS:
        heavy = RC20_HEAVY.get(letter, ())
        areas = [area for area, _ in heavy]
        counts = [weight for _, weight in heavy]
        light = RC20_LIGHT.get(letter, RC20_LIGHT_DEFAULT)
        known = set(areas)
        areas += _distinct(
            rng,
            light,
            lambda letter=letter: letter + _text(rng, DIGITS, 1) + _text(rng, CA_LETTERS, 1),
            known,
        )
        rest = count - sum(counts)
        share, extra = divmod(rest, light)
        counts += [share + (1 if index < extra else 0) for index in range(light)]
        for area, rows_in_area in zip(areas, counts, strict=True):
            rows += [
                f"{area} {_text(rng, DIGITS, 1)}{_text(rng, CA_LETTERS, 1)}"
                f"{_text(rng, DIGITS, 1)}"
                for _ in range(rows_in_area)
            ]
    return [Field("RC-20", "postal_codes", _pairs(rows), mode="declared", detector="postal_code")]


# The corpus ------------------------------------------------------------------------

GENERATORS: tuple[Callable[[], list[Field]], ...] = (
    rc01, rc02, rc03, rc04, rc05, rc06, rc07, rc08, rc09, rc10,
    rc11, rc12, rc13, rc14, rc15, rc16, rc17, rc18, rc19, rc20,
)  # fmt: skip


@cache
def corpus() -> tuple[Field, ...]:
    """Every field of RC-01 to RC-20, in case order."""
    return tuple(field for generate in GENERATORS for field in generate())


def field(field_id: str) -> Field:
    """One field of the corpus by its id, ``RC-03/scaled`` for example."""
    for candidate in corpus():
        if candidate.id == field_id:
            return candidate
    raise KeyError(field_id)


# Mandatory variants (specification, annex A) ------------------------------------------


@dataclass(frozen=True)
class Variants:
    """A field seen whole by the discovery and a file that adds what the
    discovery never saw: a value with an unexpected character, a value of an
    unexpected length and a new combination of the known segments."""

    sample: Field
    file: Pairs
    unexpected: str
    wrong_length: str
    # None when every head of the field is already used (a single letter, RC-09).
    new_combination: str | None


def with_variants(base: Field) -> Variants:
    """The variants of an informative field, built deterministically from it."""
    values = base.values()
    taken = set(values)
    first = values[0]
    unexpected = first + "#"
    wrong_length = _longer(values[len(values) // 2], taken)
    new_combination = _recombined(values, taken)
    added = tuple(
        value for value in (unexpected, wrong_length, new_combination) if value
    )
    if len(set(added) | taken) != len(taken) + len(added):
        raise ValueError(f"variants of {base.id} collide")
    file = tuple(sorted([*base.pairs, *((value, 1) for value in added)]))
    return Variants(base, file, unexpected, wrong_length, new_combination)


def _longer(value: str, taken: set[str]) -> str:
    """``value`` with its last run one character longer, in the same class."""
    last = value[-1]
    for extra in "7531" if last.isdigit() else ("QXZW" if last.isupper() else "qxzw"):
        candidate = value + extra
        if candidate not in taken:
            return candidate
    raise ValueError(f"no longer variant of {value!r}")


def _recombined(values: Sequence[str], taken: set[str]) -> str | None:
    """A value whose leading run of letters (or digits) never starts a value of
    the field: a new combination of a known structure."""
    value = values[0]
    alphabet = UPPER if value[0].isupper() else LOWER if value[0].islower() else DIGITS
    run = len(value) - len(value.lstrip(alphabet))
    heads = {other[:run] for other in values}
    size = len(alphabet)
    for code in range(size ** min(run, 3)):
        head = "".join(alphabet[code // size**i % size] for i in range(run))
        candidate = head + value[run:]
        if head not in heads and candidate not in taken:
            return candidate
    return None

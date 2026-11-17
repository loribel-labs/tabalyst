# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Measured, streaming mutation pass over a staged clean Generate CSV."""

from __future__ import annotations

import csv
import math
import random
import re
import string
import unicodedata
from collections import Counter, deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from itertools import compress
from pathlib import Path
from typing import cast

from tabalyst.generate_scenarios import (
    SCENARIO_KEYS,
    conflict_map,
    is_scenario_profile,
    profile_scenario_error,
    scenario_option_error,
)

CHANGE_FIELDS = ["event_id", "dataset", "profile", "row_number", "operation_index",
                 "kind", "column", "before", "after", "cause"]

# Shared by the definition and the Computer package validators: one rule, one place.
OPERATION_KINDS = frozenset({"set_missing", "replace", "duplicate", "format", "swap",
                             "duplicate_row"})
ROW_KINDS = frozenset({"duplicate_row"})
# Kinds of the scenario profiles of Insurance V2 only (contract insurance-v2.md 6.2): a package
# that validates its own kinds (Computer) never sees them, the definition allows them for Insurance.
SCENARIO_KINDS = frozenset({"reuse_value", "copy_column"})
# Values of ``format`` that read the whole row, so the caller supplies them (``contextual``): a
# package that supplies none refuses them.
CONTEXTUAL_VALUES = frozenset({"postal_other_province"})
OPERATION_KEYS = frozenset({"kind", "column", "rate", "count", "value", "when", "class"}
                           ) | SCENARIO_KEYS
FORMAT_VALUES = frozenset({
    "upper", "lower", "strip", "date_slash", "phone_spaces", "insert_space", "double_space",
    "drop_char", "double_hyphen", "suffix_x", "strip_accents", "negate", "leading_apostrophe",
    "double_char", "swap_first_two", "transpose", "replace_char", "phone_double_space",
    "date_dmy", "date_iso", "currency_suffix", "currency_prefix", "currency_fr", "currency_code",
    "drop_digit", "insert_double_space", "trailing_space", "date_mdy_iso",
    "leading_space", "leading_tab", "insert_zero_width", "insert_replacement_char",
    "times_100", "date_plus_century",
})
CURRENCY_CODE = "CAD"
CLASS_NAME = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
# Enough to pick a copy that is not the previous line, small enough to stream in constant memory.
COPY_WINDOW = 1000


@dataclass(frozen=True)
class AnomalyEvent:
    """One cell of one event, as written to the journal, with the meaning of the clean cell.

    ``row_number`` counts the header as line 1, like ``changes.csv``; ``operation_index`` is
    1-based. ``canonical_value`` is the clean cell normalized by type (contract 4.5), so it
    stays the intended value when a defect rewrites the cell in another convention.
    """

    event_id: int
    row_number: int
    operation_index: int
    column: str
    before: str
    after: str
    canonical_value: str
    # The earlier row a ``reuse_value`` event copied the cell from (0 for any other event): the
    # case spans both rows (contract insurance-v2.md 6.4).
    related_row: int = 0


CanonicalReader = Callable[[str, str, Mapping[str, str]], str]
# Replacement of a cell that needs its row (a ``CONTEXTUAL_VALUES`` name): it returns the new
# text, the same text when nothing applies.
ContextualValue = Callable[[Mapping[str, str], random.Random], str]
ContextualValues = Mapping[str, ContextualValue]


def _insert_space(value: str, rng: random.Random) -> str:
    spots = [i for i in range(1, len(value)) if value[i - 1] != " " and value[i] != " "]
    if not spots:
        return value
    spot = rng.choice(spots)
    return f"{value[:spot]} {value[spot:]}"


def _drop_char(value: str, rng: random.Random) -> str:
    if len(value) < 2:
        return value
    spot = rng.randrange(len(value))
    return value[:spot] + value[spot + 1:]


def _negate(value: str, rng: random.Random) -> str:
    # A negative zero would read as a typo of the generator, not as a sign error.
    if re.fullmatch(r"\d+(?:\.\d+)?", value) and re.search(r"[1-9]", value):
        return f"-{value}"
    return value


def _strip_accents(value: str, rng: random.Random) -> str:
    decomposed = unicodedata.normalize("NFD", value)
    return unicodedata.normalize(
        "NFC", "".join(char for char in decomposed if unicodedata.category(char) != "Mn"))


def _drop_digit(value: str, rng: random.Random) -> str:
    spots = [i for i, char in enumerate(value) if char.isdigit()]
    if not spots or len(value) < 2:
        return value
    spot = rng.choice(spots)
    return value[:spot] + value[spot + 1:]


def _insert_double_space(value: str, rng: random.Random) -> str:
    spots = [i for i in range(1, len(value)) if value[i - 1] != " " and value[i] != " "]
    if not spots:
        return value
    spot = rng.choice(spots)
    return f"{value[:spot]}  {value[spot:]}"


def _lead(prefix: str) -> Callable[[str, random.Random], str]:
    """A transform that puts ``prefix`` in front of a value that does not start with
    whitespace already (a leading space or tab is a defect, not a layout)."""
    def lead(value: str, rng: random.Random) -> str:
        return value if value[:1].isspace() else f"{prefix}{value}"
    return lead


def _insert_invisible(char: str) -> Callable[[str, random.Random], str]:
    """A transform that inserts ``char`` inside a value of two characters or more,
    once: a value that holds it already is left alone."""
    def insert(value: str, rng: random.Random) -> str:
        if len(value) < 2 or char in value:
            return value
        spot = rng.randrange(1, len(value))
        return f"{value[:spot]}{char}{value[spot:]}"
    return insert


def _letter_spots(value: str) -> list[int]:
    return [i for i, char in enumerate(value) if char.isalpha()]


def _double_char(value: str, rng: random.Random) -> str:
    spots = _letter_spots(value)
    if not spots:
        return value
    spot = rng.choice(spots)
    return value[:spot] + value[spot] + value[spot:]


def _swap_first_two(value: str, rng: random.Random) -> str:
    if len(value) < 2 or value[0] == value[1]:
        return value
    return value[1] + value[0] + value[2:]


def _transpose(value: str, rng: random.Random) -> str:
    spots = [i for i in range(len(value) - 1)
             if value[i].isalpha() and value[i + 1].isalpha() and value[i] != value[i + 1]]
    if not spots:
        return value
    spot = rng.choice(spots)
    return value[:spot] + value[spot + 1] + value[spot] + value[spot + 2:]


def _replace_char(value: str, rng: random.Random) -> str:
    # Plain ASCII letters of the same case keep the substitution a typo, not an encoding fault.
    spots = [i for i in _letter_spots(value) if value[i].isascii()]
    if not spots:
        return value
    spot = rng.choice(spots)
    alphabet = string.ascii_uppercase if value[spot].isupper() else string.ascii_lowercase
    other = rng.choice([char for char in alphabet if char != value[spot]])
    return value[:spot] + other + value[spot + 1:]


def _phone_double_space(value: str, rng: random.Random) -> str:
    return re.sub(r"^(\+\d)-", r"\1  ", value, count=1)


def _date_dmy(value: str, rng: random.Random) -> str:
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", value)
    return f"{match[3]}-{match[2]}-{match[1]}" if match else value


def _date_iso(value: str, rng: random.Random) -> str:
    match = re.fullmatch(r"(\d{2})-(\d{2})-(\d{4})", value)
    return f"{match[3]}-{match[2]}-{match[1]}" if match else value


def _date_mdy_iso(value: str, rng: random.Random) -> str:
    # Ontario writes MM-DD-YYYY; a first part above 12 is not a month and is left alone.
    match = re.fullmatch(r"(\d{2})-(\d{2})-(\d{4})", value)
    return f"{match[3]}-{match[1]}-{match[2]}" if match and 1 <= int(match[1]) <= 12 else value


def _times_100(value: str, rng: random.Random) -> str:
    """Multiply a plain decimal by 100 (R05: a premium keyed in cents), keeping two decimals."""
    parts = _split_amount(value)
    if not parts or parts[0] == "-":
        return value
    return f"{Decimal(value) * 100:.2f}"


def _plus_century(value: str, rng: random.Random) -> str:
    """Move a date, in ISO or in day/month-first order, one century later (R02: born in the future).

    The year is the first part of an ISO date and the last of the other two orders, whose first
    two parts are left in place. A 29 February that the new year does not have becomes the 28th.
    """
    iso = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", value)
    other = re.fullmatch(r"(\d{2})-(\d{2})-(\d{4})", value)
    if iso:
        year, first, second = int(iso[1]) + 100, iso[2], iso[3]
    elif other:
        year, first, second = int(other[3]) + 100, other[1], other[2]
    else:
        return value
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    if {first, second} == {"02", "29"} and not leap:
        first, second = ("28", "02") if first == "29" else ("02", "28")
    return f"{year:04d}-{first}-{second}" if iso else f"{first}-{second}-{year:04d}"


def _split_amount(value: str) -> tuple[str, str, str] | None:
    """Return sign, integer digits and decimals of a plain decimal number."""
    match = re.fullmatch(r"([+-]?)(\d+)(\.\d+)?", value)
    return (match[1], match[2], match[3] or "") if match else None


def _currency_suffix(value: str, rng: random.Random) -> str:
    parts = _split_amount(value)
    return f"{value} $" if parts else value


def _currency_prefix(value: str, rng: random.Random) -> str:
    parts = _split_amount(value)
    return f"{parts[0]}${parts[1]}{parts[2]}" if parts else value


def _currency_fr(value: str, rng: random.Random) -> str:
    parts = _split_amount(value)
    if not parts:
        return value
    sign, whole, decimals = parts
    grouped = f"{int(whole):,}".replace(",", " ")
    return f"{sign}{grouped}{decimals.replace('.', ',')} $"


def _currency_code(value: str, rng: random.Random) -> str:
    parts = _split_amount(value)
    return f"{value} {CURRENCY_CODE}" if parts else value


# The random stream is passed to every transform so that adding one never shifts another.
TEXT_TRANSFORMS: dict[str, Callable[[str, random.Random], str]] = {
    "upper": lambda value, rng: value.upper(),
    "lower": lambda value, rng: value.lower(),
    "strip": lambda value, rng: value.strip(),
    "date_slash": lambda value, rng: value.replace("-", "/"),
    "phone_spaces": lambda value, rng: value.replace("-", " "),
    "insert_space": _insert_space,
    "double_space": lambda value, rng: value.replace(" ", "  ", 1),
    "drop_char": _drop_char,
    "double_hyphen": lambda value, rng: value.replace("-", "--", 1),
    "suffix_x": lambda value, rng: f"{value}_X",
    "strip_accents": _strip_accents,
    "negate": _negate,
    "leading_apostrophe": lambda value, rng: f"'{value}",
    "double_char": _double_char,
    "swap_first_two": _swap_first_two,
    "transpose": _transpose,
    "replace_char": _replace_char,
    "phone_double_space": _phone_double_space,
    "date_dmy": _date_dmy,
    "date_iso": _date_iso,
    "date_mdy_iso": _date_mdy_iso,
    "currency_suffix": _currency_suffix,
    "currency_prefix": _currency_prefix,
    "currency_fr": _currency_fr,
    "currency_code": _currency_code,
    "drop_digit": _drop_digit,
    "insert_double_space": _insert_double_space,
    "trailing_space": lambda value, rng: value if value.endswith(" ") else f"{value} ",
    "leading_space": _lead(" "),
    "leading_tab": _lead("\t"),
    "insert_zero_width": _insert_invisible("\u200b"),
    "insert_replacement_char": _insert_invisible("\ufffd"),
    "times_100": _times_100,
    "date_plus_century": _plus_century,
}


def operation_option_error(operation: Mapping[str, object]) -> str | None:
    """Return why the quantity, class or row options of an operation are invalid.

    Exactly one of ``rate`` and ``count`` must be given. A row operation names
    no column and no value. The scenario keys of Insurance V2 are checked first
    (``scenario_option_error``). The kind itself and the column names are checked by
    the callers, who know their schema.
    """
    problem = scenario_option_error(operation)
    if problem is not None:
        return problem
    rate = operation.get("rate")
    count = operation.get("count")
    if ("rate" in operation) == ("count" in operation):
        return "operation needs exactly one of rate and count"
    if "rate" in operation and (
            type(rate) not in (int, float) or not math.isfinite(cast(float, rate))
            or not 0 <= cast(float, rate) <= 1):
        return "operation.rate must be from 0 to 1"
    if "count" in operation and (type(count) is not int or cast(int, count) < 1):
        return "operation.count must be a positive integer"
    name = operation.get("class")
    if "class" in operation and (not isinstance(name, str) or not CLASS_NAME.match(name)):
        return "operation.class must be a lower-case identifier of at most 64 characters"
    if operation.get("kind") == "reuse_value" and "value" in operation:
        return "operation.value is unused for this kind"
    if operation.get("kind") in ROW_KINDS:
        if "column" in operation:
            return "operation.column is unused for this kind"
        if "value" in operation:
            return "operation.value is unused for this kind"
    return None


def check_operation_counts(operations: Sequence[Mapping[str, object]], rows: int,
                           where: str) -> None:
    """Raise ValueError when an absolute count asks for more rows than the file has."""
    for index, operation in enumerate(operations, 1):
        count = operation.get("count")
        if isinstance(count, int) and count > rows:
            raise ValueError(
                f"{where}: operation {index} asks for count {count} but the dataset "
                f"has {rows} rows")


def _mutate(row: dict[str, str], operation: Mapping[str, object],
            history: dict[str, list[str]],
            rng: random.Random, locale: str,
            unit_suffixes: Mapping[str, tuple[str, str]] | None,
            contextual: ContextualValues | None = None) -> dict[str, str]:
    column = cast(str, operation["column"])
    before = row[column]
    kind = operation["kind"]
    if kind == "set_missing":
        return {column: ""} if before else {}
    if kind == "replace":
        value = cast(str, operation["value"])
        return {column: value} if value != before else {}
    if kind == "copy_column":
        # A valid boundary (contract 6.2): the cell takes the value of another cell of the row.
        other = cast(str, operation["value"])
        return {column: row[other]} if before and row[other] and before != row[other] else {}
    if operation.get("value") in CONTEXTUAL_VALUES:
        name = cast(str, operation["value"])
        if contextual is None or name not in contextual:
            raise ValueError(f"format {name} needs the row context its package provides")
        after = contextual[name](row, rng)
        return {column: after} if before and after != before else {}
    if kind == "duplicate":
        choices = [value for value in history[column] if value and value != before]
        return {column: rng.choice(choices)} if choices else {}
    if kind == "swap":
        other = cast(str, operation["value"])
        return {column: row[other], other: before} if before and row[other] and before != row[other] else {}
    if operation["value"] in {"unit_gb", "unit_suffix"}:
        if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", before):
            return {}
        suffixes = ("GB", "Go") if operation["value"] == "unit_gb" else (
            unit_suffixes[column] if unit_suffixes is not None else None
        )
        if suffixes is None:
            raise ValueError(f"unit suffix is unavailable for {column}")
        return {column: f"{before} {suffixes[0 if locale == 'en' else 1]}"}
    after = TEXT_TRANSFORMS[cast(str, operation["value"])](before, rng)
    return {column: after} if before and after != before else {}


def _can_apply(row: dict[str, str], operation: Mapping[str, object], row_index: int,
               probe: random.Random, locale: str,
               unit_suffixes: Mapping[str, tuple[str, str]] | None,
               contextual: ContextualValues | None = None) -> bool:
    """Tell whether an operation would change this clean row."""
    when = cast(dict[str, str], operation.get("when", {}))
    if any(row.get(field) != value for field, value in when.items()):
        return False
    kind = operation["kind"]
    if kind == "duplicate_row":
        return row_index > 0
    if kind in {"duplicate", "reuse_value"}:
        return row_index > 0 and bool(row[cast(str, operation["column"])])
    return bool(_mutate(row, operation, {}, probe, locale, unit_suffixes, contextual))


def _choose_rows(clean: Path, delimiter: str, operations: Sequence[Mapping[str, object]],
                 rows: int, selection_rngs: Sequence[random.Random], where: str, locale: str,
                 unit_suffixes: Mapping[str, tuple[str, str]] | None,
                 contextual: ContextualValues | None = None,
                 ) -> tuple[dict[int, set[int]], dict[int, int]]:
    """Pick exactly ``count`` rows for every absolute-count operation.

    One read of the clean file marks the rows each operation can change; the
    picks then follow the profile order. Two operations never share a row unless
    both declare ``can_overlap`` and neither scenario lists the other in
    ``conflicts_with`` (contract 4.3), and the operations of one scenario never share a
    row with each other, so by default a row carries one class and an operation changes
    exactly its ``count`` rows. Three kinds of claim map keep the memory
    at a byte per row each: rows taken by an operation that cannot overlap, rows taken by
    any operation, and one map per scenario named in a conflict. Operations with
    ``rate`` are not involved. Returns the rows picked and the eligible population of
    each operation (rows it can change in the clean file, before any claim). Raises
    ValueError when fewer rows are left.
    """
    indexes = [i for i, operation in enumerate(operations) if "count" in operation]
    if not indexes:
        return {}, {}
    eligible = {i: bytearray(rows) for i in indexes}
    probe = random.Random(0)
    with clean.open("r", encoding="utf-8", newline="") as source:
        for row_index, row in enumerate(csv.DictReader(source, delimiter=delimiter)):
            if row_index >= rows:
                break
            for i in indexes:
                if _can_apply(row, operations[i], row_index, probe, locale, unit_suffixes,
                              contextual):
                    eligible[i][row_index] = 1
    conflicts = conflict_map(operations)
    exclusive = bytearray(rows)
    anything = bytearray(rows)
    for operation in operations:
        scenario = operation.get("scenario_id")
        if isinstance(scenario, str):
            # Several operations of one scenario are one case each: they never share a row.
            conflicts.setdefault(scenario, set()).add(scenario)
    by_scenario = {
        scenario: bytearray(rows) for scenario in conflicts
        if any(operation.get("scenario_id") == scenario and operation.get("can_overlap")
               for operation in operations)}
    chosen: dict[int, set[int]] = {}
    population: dict[int, int] = {}
    for i in indexes:
        operation = operations[i]
        scenario = cast("str | None", operation.get("scenario_id"))
        shares = bool(operation.get("can_overlap"))
        if not shares:
            blocking = [anything]
        else:
            blocking = [exclusive, *(by_scenario[other]
                                     for other in conflicts.get(scenario or "", ())
                                     if other in by_scenario)]
        population[i] = eligible[i].count(1)
        candidates = compress(range(rows), eligible[i])
        if len(blocking) == 1:
            claimed = blocking[0]
            pool = [r for r in candidates if not claimed[r]]
        else:
            pool = [r for r in candidates if not any(taken[r] for taken in blocking)]
        wanted = cast(int, operation["count"])
        if len(pool) < wanted:
            if scenario is None:
                name, detail = "", "not already used by an earlier count operation"
            else:
                name = f" (scenario {scenario})"
                detail = (f"eligible population {population[i]}; the others are used by an "
                          f"earlier operation that cannot share a row with it")
            raise ValueError(
                f"{where}: operation {i + 1}{name} asks for count {wanted} but only {len(pool)} "
                f"rows can take it ({detail})")
        picked = selection_rngs[i].sample(pool, wanted)
        for r in picked:
            anything[r] = 1
            if not shares:
                exclusive[r] = 1
            elif scenario in by_scenario:
                by_scenario[scenario][r] = 1
        chosen[i] = set(picked)
    return chosen, population


def _stream_keys(profile_id: str, operations: Sequence[Mapping[str, object]]) -> list[str]:
    """Name the random stream of every operation.

    A legacy profile keys them by position. A scenario profile keys them by scenario and the
    rank of the operation inside it (contract 4.4), so adding or reordering a scenario leaves
    the values of the others alone.
    """
    if not is_scenario_profile(operations):
        return [f"{profile_id}:{index}" for index in range(len(operations))]
    ranks: Counter[str] = Counter()
    keys = []
    for operation in operations:
        scenario = cast(str, operation["scenario_id"])
        ranks[scenario] += 1
        keys.append(f"{profile_id}:{scenario}:{ranks[scenario]}")
    return keys


def inject_anomalies(clean: Path, altered: Path, changes: Path, *,
                     dataset: str, profile: Mapping[str, object], seed: int, count: int,
                     delimiter: str, locale: str = "en",
                     unit_suffixes: Mapping[str, tuple[str, str]] | None = None,
                     on_row: Callable[[int], None] | None = None,
                     on_event: Callable[[AnomalyEvent], None] | None = None,
                     canonical: CanonicalReader | None = None,
                     contextual: ContextualValues | None = None) -> dict[str, object]:
    """Write altered CSV and cell log; return requested and actual counts.

    Computer unit suffixes are supplied by its output register. An operation
    selects ``round(count * rate)`` rows at random, or, with an absolute
    ``count``, exactly that many rows among those it can change (see
    ``_choose_rows``), so a fixed ``count`` changes the same number of rows in
    any file size.
    The journal gains a ``class`` column only when an operation declares one,
    which keeps the files of profiles without classes byte for byte unchanged.
    A ``duplicate_row`` operation runs after the other operations of its row and
    overwrites the row with an exact copy of an earlier output row. Changes the
    row had already received are then gone from the file, so their journal
    entries are dropped and their operations count the row as skipped: the
    journal always describes the file.
    A scenario profile (an operation declares ``scenario_id``, contract 4) is exact or
    refused: it uses ``count`` only, keys its random streams by scenario, lets two
    operations share a row only when both opt in, and raises ValueError when an operation
    applies fewer cases than its ``count`` (the clean row allowed it, the row as an earlier
    overlapping operation left it did not). Its summary adds ``distinct_changed_cells``,
    ``net_differences`` and, per operation, ``scenario_id``, ``mode`` and
    ``eligible_population``; the summary of a legacy profile gains nothing.
    ``on_row`` receives the number of rows written, about 200 times per file and at the end.
    ``on_event`` receives one ``AnomalyEvent`` per line of the journal, with the canonical
    value of the clean cell (``canonical(column, clean value, clean row)``, the clean cell
    itself when not given); it never changes the files. ``contextual`` supplies the ``format``
    values that read the whole row (``CONTEXTUAL_VALUES``); one that is missing fails the run.
    A ``reuse_value`` event copies the cell of one of the 1,000 rows before it (its
    ``related_row``): the key of a case that spans two rows.
    """
    # Imported here because generate_values reaches generate_definition, which
    # imports this module for the operation rules.
    from tabalyst.generate_values import _stream

    if locale not in {"en", "fr"}:
        raise ValueError(f"unsupported anomaly locale {locale!r}")
    operations = cast(list[dict[str, object]], profile["operations"])
    profile_id = cast(str, profile["id"])
    for index, operation in enumerate(operations, 1):
        problem = operation_option_error(operation)
        if problem is not None:
            raise ValueError(f"{profile_id}.operations[{index}]: {problem}")
    problem = profile_scenario_error(operations)
    if problem is not None:
        raise ValueError(f"{profile_id}.{problem}" if problem.startswith("operations[")
                         else f"{profile_id}: {problem}")
    scenarios = is_scenario_profile(operations)
    check_operation_counts(operations, count, f"{profile_id} on {dataset}")
    requested = [cast(int, operation["count"]) if "count" in operation
                 else round(count * cast(float, operation["rate"])) for operation in operations]
    remaining = requested.copy()
    stream_keys = _stream_keys(profile_id, operations)
    selection_rngs = [_stream(seed, dataset, key, "anomaly_selection") for key in stream_keys]
    chosen, eligible_population = _choose_rows(
        clean, delimiter, operations, count, selection_rngs,
        f"{profile_id} on {dataset}", locale, unit_suffixes, contextual)
    mutation_rngs = [_stream(seed, dataset, key, "anomaly_value") for key in stream_keys]
    applied: Counter[int] = Counter()
    skipped: Counter[int] = Counter()
    history: dict[str, list[str]] = {}
    keeps_classes = any("class" in operation for operation in operations)
    copies_rows = any(operation["kind"] in ROW_KINDS for operation in operations)
    written: deque[tuple[int, tuple[str, ...]]] = deque(maxlen=COPY_WINDOW)
    # Clean (row number, value) of the last rows of every column a ``reuse_value`` reads.
    reused = {cast(str, operation["column"]) for operation in operations
              if operation["kind"] == "reuse_value"}
    recent: dict[str, deque[tuple[int, str]]] = {
        column: deque(maxlen=COPY_WINDOW) for column in reused}
    # Row operations go last whatever their place in the profile (stable sort).
    order = sorted(range(len(operations)), key=lambda i: operations[i]["kind"] in ROW_KINDS)
    affected_rows = 0
    changed_cells = 0
    distinct_cells = 0
    net_differences = 0
    events = 0
    with (clean.open("r", encoding="utf-8", newline="") as source,
          altered.open("w", encoding="utf-8", newline="") as dirty,
          changes.open("w", encoding="utf-8", newline="") as journal):
        reader = csv.DictReader(source, delimiter=delimiter)
        fields = reader.fieldnames or []
        history = {field: [] for field in fields}
        writer = csv.DictWriter(dirty, fieldnames=fields, delimiter=delimiter,
                                lineterminator="\n", extrasaction="raise")
        log = csv.DictWriter(journal, fieldnames=[*CHANGE_FIELDS, *(["class"] if keeps_classes else [])],
                             lineterminator="\n")
        writer.writeheader()
        log.writeheader()
        observed = 0
        report_every = max(1, count // 200)
        for row_index, clean_row in enumerate(reader):
            observed += 1
            if on_row is not None and row_index % report_every == 0:
                on_row(row_index)
            row = clean_row.copy()
            # (operation index, cell updates, related row) of this row, written once it is final.
            pending: list[tuple[int, list[tuple[str, str, str, str]], int]] = []
            related = 0
            for index in order:
                operation = operations[index]
                if index in chosen:
                    if row_index not in chosen[index]:
                        continue
                else:
                    rows_left = count - row_index
                    selected = (remaining[index] == rows_left or
                                (remaining[index] > 0 and
                                 selection_rngs[index].random() < remaining[index] / rows_left))
                    if not selected:
                        continue
                    remaining[index] -= 1
                when = cast(dict[str, str], operation.get("when", {}))
                if any(row.get(field) != value for field, value in when.items()):
                    skipped[index] += 1
                    continue
                cause = f"{profile_id}.operations[{index}]"
                if operation["kind"] == "duplicate_row":
                    if not written:
                        skipped[index] += 1
                        continue
                    number, values = written[mutation_rngs[index].randrange(len(written))]
                    updates = {field: value for field, value in zip(fields, values)
                               if clean_row[field] != value}
                    if not updates:
                        skipped[index] += 1
                        continue
                    for earlier, _, _ in pending:
                        applied[earlier] -= 1
                        skipped[earlier] += 1
                    pending.clear()
                    row = clean_row.copy()
                    cause += f" copy_of_row={number}"
                elif operation["kind"] == "reuse_value":
                    column = cast(str, operation["column"])
                    sources = [(number, value) for number, value in recent[column]
                               if value and value != row[column]]
                    updates = {}
                    if sources:
                        related, value = sources[mutation_rngs[index].randrange(len(sources))]
                        updates = {column: value}
                        cause += f" reused_from_row={related}"
                else:
                    updates = _mutate(row, operation, history, mutation_rngs[index], locale,
                                      unit_suffixes, contextual)
                if not updates:
                    skipped[index] += 1
                    continue
                cells = []
                for column, after in updates.items():
                    cells.append((column, row[column], after, cause))
                    row[column] = after
                pending.append((index, cells, related if operation["kind"] == "reuse_value" else 0))
                applied[index] += 1
            for index, cells, source_row in pending:
                events += 1
                for column, before, after, cause in cells:
                    changed_cells += 1
                    entry = {"event_id": events, "dataset": dataset,
                             "profile": profile_id, "row_number": row_index + 2,
                             "operation_index": index + 1, "kind": operations[index]["kind"],
                             "column": column, "before": before, "after": after,
                             "cause": cause}
                    if keeps_classes:
                        entry["class"] = operations[index].get("class", "")
                    log.writerow(entry)
                    if on_event is not None:
                        meaning = (canonical(column, clean_row[column], clean_row)
                                   if canonical is not None else clean_row[column])
                        on_event(AnomalyEvent(events, row_index + 2, index + 1, column,
                                              before, after, meaning, source_row))
            if scenarios and pending:
                touched = {column for _, cells, _ in pending for column, *_ in cells}
                distinct_cells += len(touched)
                net_differences += sum(row[column] != clean_row[column] for column in touched)
            writer.writerow(row)
            affected_rows += int(bool(pending))
            if copies_rows:
                written.append((row_index + 2, tuple(row[field] for field in fields)))
            for field, value in clean_row.items():
                if value and len(history[field]) < 1000:
                    history[field].append(value)
            for column, window in recent.items():
                window.append((row_index + 2, clean_row[column]))
        if observed != count:
            raise ValueError(f"Clean row count changed for {dataset}: {observed} != {count}")
        if on_row is not None:
            on_row(observed)
    if scenarios:
        for index, operation in enumerate(operations):
            if applied[index] != requested[index]:
                raise ValueError(
                    f"{profile_id} on {dataset}: operation {index + 1} (scenario "
                    f"{operation['scenario_id']}) applied {applied[index]} of its count "
                    f"{requested[index]}: an earlier overlapping operation left rows it "
                    f"could not change")
    summary: dict[str, object] = {
        "dataset": dataset, "profile": profile_id, "seed": seed,
        "total_rows": count, "affected_rows": affected_rows,
        "affected_row_rate": affected_rows / count if count else 0.0,
        "events": events, "changed_cells": changed_cells,
    }
    if scenarios:
        summary.update({"distinct_changed_cells": distinct_cells,
                        "net_differences": net_differences})
    summary["operations"] = [
        _operation_summary(index, operation, requested[index], applied[index], skipped[index],
                           count, eligible_population.get(index))
        for index, operation in enumerate(operations)]
    return summary


def _operation_summary(index: int, operation: Mapping[str, object], requested: int,
                       applied: int, skipped: int, rows: int,
                       eligible: int | None = None) -> dict[str, object]:
    """Build one summary entry; the keys of rate-based operations are unchanged.

    A scenario operation adds its ``scenario_id``, the ``exact`` mode and its eligible population.
    """
    entry: dict[str, object] = {"index": index + 1, "kind": operation["kind"]}
    if "column" in operation:
        entry["column"] = operation["column"]
    if "count" in operation:
        entry["count"] = operation["count"]
    else:
        entry["rate"] = operation["rate"]
    if "class" in operation:
        entry["class"] = operation["class"]
    if "scenario_id" in operation:
        entry.update({"scenario_id": operation["scenario_id"], "mode": "exact",
                      "eligible_population": eligible})
    entry.update({"requested_rows": requested, "applied_rows": applied,
                  "skipped_rows": skipped, "applied_rate": applied / rows if rows else 0.0})
    return entry

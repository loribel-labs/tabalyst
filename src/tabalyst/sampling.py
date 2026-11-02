# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Streaming CSV sampling service."""

from __future__ import annotations

import csv
import math
import os
import random
import tempfile
from collections import Counter, defaultdict, deque
from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from tabalyst.batch import apply_default_file_mode
from tabalyst.config import CsvConfig
from tabalyst.csv_records import open_records, output_encoding
from tabalyst.errors import InputError, ReportError
from tabalyst.scanner.stratify import allocate_strata_with_minimum

# The most strata a stratified sample keeps at once (STRAT-08): one counter and
# one reservoir per stratum are held in memory while the file streams.
DEFAULT_MAX_STRATA = 100_000


class SampleMethod(StrEnum):
    """Available CSV sampling strategies."""

    FIRST = "first"
    LAST = "last"
    RANDOM = "random"
    STRATIFIED = "stratified"
    STRATIFIED_BALANCED = "stratified-balanced"
    SMART = "smart"


_STRATIFIED_METHODS = frozenset({"stratified", "stratified-balanced"})


@dataclass(frozen=True)
class SmartSummary:
    """What a smart sample covers of the catalog of targets of its plan (design
    20.16): not of every phenomenon of the data, and not in the proportions of the
    population."""

    targets: int
    evaluable: int
    covered: int
    weighted_share: float | None
    mandatory: int
    mandatory_covered: int
    reserve_rows: int
    passes: int
    scan_ran: bool
    duration_seconds: float


@dataclass(frozen=True)
class SampleResult:
    """Summary of a completed sampling operation."""

    source: Path
    output: Path
    method: SampleMethod
    source_rows: int
    sample_rows: int
    sample_rate: float
    field: str | None
    seed: int | None
    encoding: str
    delimiter: str
    # The columns of a stratified sample (``field`` joins them with a comma) and
    # its balance: the strata the file has, the ones that got rows, and the
    # ones without a row (STRAT-02). ``None`` for the other methods.
    fields: tuple[str, ...] = ()
    strata_known: int | None = None
    strata_selected: int | None = None
    strata_uncovered: int | None = None
    # ``stratified-balanced`` only: the quota asked per stratum, and the strata
    # that have more rows than it (so that were drawn from, not kept whole).
    per_value: int | None = None
    strata_capped: int | None = None
    # A smart sample writes a report beside its CSV file and sums it up here.
    report: Path | None = None
    page: Path | None = None
    smart: SmartSummary | None = None


@dataclass(frozen=True)
class _ScanResult:
    headers: list[str]
    row_count: int
    strata: Counter[Hashable]
    field_indexes: tuple[int, ...]


def _validate_paths(source: Path, output: Path, *, force: bool) -> None:
    if not source.is_file():
        raise InputError(f"CSV file does not exist or is not a file: {source}")
    if output.suffix.lower() != ".csv":
        raise InputError("Sample output must be a complete filename ending in .csv.")
    try:
        if source.resolve() == output.resolve():
            raise InputError("Sample output cannot overwrite the source CSV.")
    except OSError as exc:
        raise InputError(f"Cannot resolve the input or output path: {exc}") from exc
    if output.exists() and not force:
        raise ReportError(f"Output already exists: {output}. Use --force to replace it.")
    if output.exists() and not output.is_file():
        raise ReportError(f"Output path is not a file: {output}")


def _field_indexes(headers: Sequence[str], fields: Sequence[str]) -> tuple[int, ...]:
    indexes: list[int] = []
    for field in fields:
        matches = [index for index, name in enumerate(headers) if name == field]
        if not matches:
            raise InputError(f"Stratification field does not exist: {field}")
        if len(matches) > 1:
            raise InputError(f"Stratification field is ambiguous: {field}")
        indexes.append(matches[0])
    return tuple(indexes)


def _too_many_strata(fields: Sequence[str], max_strata: int, record: int) -> InputError:
    return InputError(
        f"Stratification by {', '.join(fields)} found more than "
        f"{max_strata:,} strata at data record {record}. Use "
        "fewer or less detailed fields, or raise --max-strata."
    )


def _scan(
    source: Path,
    config: CsvConfig,
    fields: Sequence[str],
    max_strata: int,
) -> _ScanResult:
    strata: Counter[Hashable] = Counter()
    with open_records(source, config) as records:
        headers = records.header
        field_indexes = list(_field_indexes(headers, fields))

        row_count = 0
        for row_count, row in enumerate(records, start=1):
            if field_indexes:
                key = _stratum_key(row, field_indexes)
                strata[key] += 1
                if len(strata) > max_strata:
                    raise _too_many_strata(fields, max_strata, row_count)
    return _ScanResult(headers, row_count, strata, tuple(field_indexes))


def _stratum_key(row: list[str], indexes: Sequence[int]) -> Hashable:
    """The stratum of a row: the cell itself for one field, a tuple of cells for
    several, so that ("a|b", "c") and ("a", "b|c") never collide (STRAT-03). An
    empty cell is a stratum of its own, as it always was."""
    if len(indexes) == 1:
        return row[indexes[0]]
    return tuple(row[index] for index in indexes)


def _validate_size_options(rows: int | None, percent: float | None) -> None:
    if (rows is None) == (percent is None):
        raise InputError("Specify exactly one of --rows or --percent.")
    if rows is not None:
        if rows <= 0:
            raise InputError("--rows must be greater than 0.")
    else:
        assert percent is not None
        if percent <= 0 or percent > 100:
            raise InputError("--percent must be greater than 0 and at most 100.")


def _sample_size(row_count: int, rows: int | None, percent: float | None) -> int:
    _validate_size_options(rows, percent)
    if rows is not None:
        size = rows
    else:
        assert percent is not None
        size = math.ceil(row_count * percent / 100)
    if size > row_count:
        raise InputError(
            f"Requested sample size ({size:,}) exceeds available rows ({row_count:,})."
        )
    return size


def _check_every_stratum_fits(size: int, strata: int, fields: Sequence[str]) -> None:
    """A proportional sample keeps one row of every stratum or does not run: it
    never drops categories silently."""
    if size < strata:
        raise InputError(
            f"A stratified sample of {size:,} rows cannot keep one row of each of the "
            f"{strata:,} strata of {', '.join(fields)}: use --rows {strata:,} or more, "
            "or fewer or less detailed fields."
        )


def _reservoir_add(
    reservoir: list[tuple[int, list[str]]],
    item: tuple[int, list[str]],
    seen: int,
    limit: int,
    rng: random.Random,
) -> None:
    if limit == 0:
        return
    if len(reservoir) < limit:
        reservoir.append(item)
        return
    replacement = rng.randrange(seen)
    if replacement < limit:
        reservoir[replacement] = item


def _select_rows(
    source: Path,
    config: CsvConfig,
    scan: _ScanResult,
    method: SampleMethod,
    size: int,
    seed: int | None,
    allocations: dict[Hashable, int] | None,
) -> list[list[str]]:
    rng = random.Random(seed)
    selected: list[tuple[int, list[str]]]
    with open_records(source, config) as reader:
        if method is SampleMethod.FIRST:
            selected = [(index, row) for index, row in zip(range(size), reader)]
        elif method is SampleMethod.LAST:
            selected = list(deque(enumerate(reader), maxlen=size))
        elif method is SampleMethod.RANDOM:
            selected = []
            for seen, row in enumerate(reader, start=1):
                _reservoir_add(selected, (seen - 1, row), seen, size, rng)
        else:
            assert scan.field_indexes and allocations is not None
            reservoirs: dict[Hashable, list[tuple[int, list[str]]]] = defaultdict(list)
            seen_by_stratum: Counter[Hashable] = Counter()
            for index, row in enumerate(reader):
                value = _stratum_key(row, scan.field_indexes)
                seen_by_stratum[value] += 1
                _reservoir_add(
                    reservoirs[value],
                    (index, row),
                    seen_by_stratum[value],
                    allocations[value],
                    rng,
                )
            selected = [item for items in reservoirs.values() for item in items]
    selected.sort(key=lambda item: item[0])
    return [row for _, row in selected]


@dataclass(frozen=True)
class _BalancedSelection:
    headers: list[str]
    row_count: int
    rows: list[list[str]]
    strata: int
    capped: int


def _select_balanced(
    source: Path,
    config: CsvConfig,
    fields: Sequence[str],
    per_value: int,
    seed: int | None,
    max_strata: int,
) -> _BalancedSelection:
    """Draw up to ``per_value`` rows of each stratum in one reading.

    One reservoir of ``per_value`` rows per stratum, filled independently: the
    places a small stratum leaves unused are never given to another one. The
    rows come back in file order.
    """
    rng = random.Random(seed)
    reservoirs: dict[Hashable, list[tuple[int, list[str]]]] = {}
    seen_by_stratum: Counter[Hashable] = Counter()
    row_count = 0
    with open_records(source, config) as reader:
        headers = reader.header
        indexes = _field_indexes(headers, fields)
        for index, row in enumerate(reader):
            row_count = index + 1
            key = _stratum_key(row, indexes)
            if key not in reservoirs:
                if len(reservoirs) >= max_strata:
                    raise _too_many_strata(fields, max_strata, row_count)
                reservoirs[key] = []
            seen_by_stratum[key] += 1
            _reservoir_add(reservoirs[key], (index, row), seen_by_stratum[key], per_value, rng)
    chosen = sorted(item for items in reservoirs.values() for item in items)
    capped = sum(1 for count in seen_by_stratum.values() if count > per_value)
    return _BalancedSelection(
        headers, row_count, [row for _, row in chosen], len(reservoirs), capped
    )


def write_sample_csv(
    output: Path,
    header: Sequence[str],
    rows: Sequence[Sequence[str]],
    source: Path,
    config: CsvConfig,
) -> None:
    """Write a sample next to its source's conventions (delimiter, and a byte-order
    mark only if the source had one), through a temporary file that replaces the
    output once complete."""
    writer_encoding = output_encoding(source, config.encoding)
    temporary: Path | None = None
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding=writer_encoding,
            newline="",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            apply_default_file_mode(temporary)
            writer = csv.writer(stream, delimiter=config.delimiter)
            writer.writerow(header)
            writer.writerows(rows)
        os.replace(temporary, output)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise ReportError(f"Cannot write sample to {output}: {exc}") from exc


def default_sample_output(source: Path) -> Path:
    """Return the conventional sample filename beside a source file."""

    return source.with_name(f"{source.stem}.sample.csv")


def stratification_fields(field: str | Sequence[str] | None) -> tuple[str, ...]:
    """The columns of a stratified sample from the ``field`` option: one name or
    several (the strata are then the combinations of their values)."""
    if field is None:
        return ()
    names = (field,) if isinstance(field, str) else tuple(field)
    if any(not name for name in names):
        raise InputError("A stratification field cannot be empty.")
    if len(set(names)) != len(names):
        raise InputError("A stratification field is named twice.")
    return names


def validate_sample_options(
    method: SampleMethod | str,
    *,
    rows: int | None,
    percent: float | None,
    field: str | Sequence[str] | None,
    max_strata: int = DEFAULT_MAX_STRATA,
    per_value: int | None = None,
) -> SampleMethod:
    """Validate options shared by single-file and batch adapters."""

    try:
        selected_method = SampleMethod(method)
    except ValueError as exc:
        choices = ", ".join(item.value for item in SampleMethod)
        raise InputError(f"Unknown sample method {method!r}; choose from {choices}.") from exc
    fields = stratification_fields(field)
    stratified = selected_method in _STRATIFIED_METHODS
    if stratified and not fields:
        raise InputError(f"--field is required with the {selected_method.value} method.")
    if not stratified and fields:
        raise InputError(
            "--field can only be used with the stratified and stratified-balanced methods."
        )
    if max_strata < 1:
        raise InputError("--max-strata must be at least 1.")
    if selected_method is SampleMethod.STRATIFIED_BALANCED:
        if rows is not None or percent is not None:
            raise InputError(
                "--rows and --percent do not go with stratified-balanced: it keeps "
                "up to --per-value rows of each stratum, so its size follows from the data."
            )
        if per_value is None:
            raise InputError("--per-value is required with the stratified-balanced method.")
        if isinstance(per_value, bool) or not isinstance(per_value, int) or per_value < 1:
            raise InputError("--per-value must be a whole number greater than 0.")
        return selected_method
    if per_value is not None:
        raise InputError("--per-value can only be used with the stratified-balanced method.")
    _validate_size_options(rows, percent)
    return selected_method


def sample_csv(
    source: str | Path,
    *,
    method: SampleMethod | str,
    rows: int | None = None,
    percent: float | None = None,
    field: str | Sequence[str] | None = None,
    seed: int | None = None,
    output: str | Path | None = None,
    delimiter: str = ",",
    encoding: str = "utf-8-sig",
    force: bool = False,
    max_strata: int = DEFAULT_MAX_STRATA,
    per_value: int | None = None,
) -> SampleResult:
    """Create a bounded-memory sample of a CSV file.

    A ``stratified`` sample allocates its ``rows`` to the strata in proportion
    to their size, with at least one row of each: when ``rows`` is under the
    number of strata it stops with an ``InputError`` instead of dropping some.
    A ``stratified-balanced`` sample keeps up to ``per_value`` random rows of
    each stratum (all of a smaller stratum, nothing moved to another), so its
    size is the sum of ``min(per_value, rows of the stratum)``. ``field`` may
    name several columns; a stratum is then a combination of their values. More
    than ``max_strata`` strata stop the operation with an ``InputError`` rather
    than grow without bound.
    """

    selected_method = validate_sample_options(
        method,
        rows=rows,
        percent=percent,
        field=field,
        max_strata=max_strata,
        per_value=per_value,
    )
    if selected_method is SampleMethod.SMART:
        raise InputError(
            "A smart sample needs the Scan of the file: use generate_samples, "
            "or tabalyst sample --sample-method smart."
        )
    fields = stratification_fields(field)

    try:
        config = CsvConfig(encoding=encoding, delimiter=delimiter)
    except ValueError as exc:
        raise InputError(f"Invalid CSV setting: {exc}") from exc
    source_path = Path(source)
    output_path = (
        Path(output) if output is not None else default_sample_output(source_path)
    )
    _validate_paths(source_path, output_path, force=force)
    if selected_method is SampleMethod.STRATIFIED_BALANCED:
        assert per_value is not None
        balanced = _select_balanced(
            source_path, config, fields, per_value, seed, max_strata
        )
        write_sample_csv(output_path, balanced.headers, balanced.rows, source_path, config)
        total = balanced.row_count
        return SampleResult(
            source=source_path,
            output=output_path,
            method=selected_method,
            source_rows=total,
            sample_rows=len(balanced.rows),
            sample_rate=(len(balanced.rows) / total * 100) if total else 0.0,
            field=", ".join(fields),
            seed=seed,
            encoding=config.encoding,
            delimiter=config.delimiter,
            fields=fields,
            strata_known=balanced.strata,
            strata_selected=balanced.strata,
            strata_uncovered=0,
            per_value=per_value,
            strata_capped=balanced.capped,
        )
    scan = _scan(source_path, config, fields, max_strata)
    size = _sample_size(scan.row_count, rows, percent)
    stratified = selected_method is SampleMethod.STRATIFIED
    if stratified:
        _check_every_stratum_fits(size, len(scan.strata), fields)
    allocations = allocate_strata_with_minimum(scan.strata, size) if stratified else None
    selected = _select_rows(
        source_path, config, scan, selected_method, size, seed, allocations
    )

    write_sample_csv(output_path, scan.headers, selected, source_path, config)

    rate = (size / scan.row_count * 100) if scan.row_count else 0.0
    known = selected_count = uncovered = None
    if allocations is not None:
        known = len(scan.strata)
        uncovered = sum(1 for quota in allocations.values() if quota == 0)
        selected_count = known - uncovered
    return SampleResult(
        source=source_path,
        output=output_path,
        method=selected_method,
        source_rows=scan.row_count,
        sample_rows=size,
        sample_rate=rate,
        field=", ".join(fields) if fields else None,
        seed=seed,
        encoding=config.encoding,
        delimiter=config.delimiter,
        fields=fields,
        strata_known=known,
        strata_selected=selected_count,
        strata_uncovered=uncovered,
    )

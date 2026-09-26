"""Streaming CSV sampling service."""

from __future__ import annotations

import codecs
import csv
import math
import os
import random
import tempfile
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TextIO

from tabalyst.config import CsvConfig
from tabalyst.errors import InputError, ReportError


class SampleMethod(StrEnum):
    """Available CSV sampling strategies."""

    FIRST = "first"
    LAST = "last"
    RANDOM = "random"
    STRATIFIED = "stratified"


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


@dataclass(frozen=True)
class _ScanResult:
    headers: list[str]
    row_count: int
    strata: Counter[str]
    field_index: int | None


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


def _open_reader(path: Path, config: CsvConfig) -> tuple[TextIO, csv.reader]:
    try:
        stream = path.open("r", encoding=config.encoding, newline="")
    except (OSError, UnicodeError) as exc:
        raise InputError(f"Cannot read CSV file {path}: {exc}") from exc
    return stream, csv.reader(stream, delimiter=config.delimiter, strict=True)


def _output_encoding(source: Path, encoding: str) -> str:
    """Preserve the presence or absence of a UTF-8 byte-order mark."""

    if codecs.lookup(encoding).name != "utf-8-sig":
        return encoding
    try:
        with source.open("rb") as stream:
            has_bom = stream.read(len(codecs.BOM_UTF8)) == codecs.BOM_UTF8
    except OSError as exc:
        raise InputError(f"Cannot read CSV file {source}: {exc}") from exc
    return "utf-8-sig" if has_bom else "utf-8"


def _scan(source: Path, config: CsvConfig, field: str | None) -> _ScanResult:
    stream, reader = _open_reader(source, config)
    strata: Counter[str] = Counter()
    try:
        try:
            headers = next(reader, None)
            if not headers:
                raise InputError("CSV is empty or has no header on its first record.")
            field_index = None
            if field is not None:
                matches = [index for index, name in enumerate(headers) if name == field]
                if not matches:
                    raise InputError(f"Stratification field does not exist: {field}")
                if len(matches) > 1:
                    raise InputError(f"Stratification field is ambiguous: {field}")
                field_index = matches[0]

            row_count = 0
            for row_count, row in enumerate(reader, start=1):
                if len(row) != len(headers):
                    raise InputError(
                        f"Data record {row_count} (ending at physical line "
                        f"{reader.line_num}): expected {len(headers)} fields, "
                        f"found {len(row)}. Verify the delimiter and quoting."
                    )
                if field_index is not None:
                    strata[row[field_index]] += 1
        except csv.Error as exc:
            raise InputError(
                f"Invalid CSV near physical line {reader.line_num}: {exc}"
            ) from exc
        except UnicodeError as exc:
            raise InputError(
                f"Cannot decode {source.name} as {config.encoding}. Specify --encoding."
            ) from exc
        except OSError as exc:
            raise InputError(f"Cannot read CSV file {source}: {exc}") from exc
    finally:
        stream.close()
    return _ScanResult(headers, row_count, strata, field_index)


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


def _allocate_strata(counts: Counter[str], size: int) -> dict[str, int]:
    total = counts.total()
    if not total or not size:
        return {value: 0 for value in counts}
    exact = {value: count * size / total for value, count in counts.items()}
    allocated = {value: math.floor(value_size) for value, value_size in exact.items()}
    remainder = size - sum(allocated.values())
    order = sorted(
        counts,
        key=lambda value: (-(exact[value] - allocated[value]), str(value)),
    )
    for value in order[:remainder]:
        allocated[value] += 1
    return allocated


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
) -> list[list[str]]:
    stream, reader = _open_reader(source, config)
    rng = random.Random(seed)
    selected: list[tuple[int, list[str]]]
    try:
        next(reader)
        if method is SampleMethod.FIRST:
            selected = [(index, row) for index, row in zip(range(size), reader)]
        elif method is SampleMethod.LAST:
            selected = list(deque(enumerate(reader), maxlen=size))
        elif method is SampleMethod.RANDOM:
            selected = []
            for seen, row in enumerate(reader, start=1):
                _reservoir_add(selected, (seen - 1, row), seen, size, rng)
        else:
            assert scan.field_index is not None
            allocations = _allocate_strata(scan.strata, size)
            reservoirs: dict[str, list[tuple[int, list[str]]]] = defaultdict(list)
            seen_by_stratum: Counter[str] = Counter()
            for index, row in enumerate(reader):
                value = row[scan.field_index]
                seen_by_stratum[value] += 1
                _reservoir_add(
                    reservoirs[value],
                    (index, row),
                    seen_by_stratum[value],
                    allocations[value],
                    rng,
                )
            selected = [item for items in reservoirs.values() for item in items]
    except csv.Error as exc:
        raise InputError(
            f"Invalid CSV near physical line {reader.line_num}: {exc}"
        ) from exc
    except UnicodeError as exc:
        raise InputError(
            f"Cannot decode {source.name} as {config.encoding}. Specify --encoding."
        ) from exc
    except OSError as exc:
        raise InputError(f"Cannot read CSV file {source}: {exc}") from exc
    finally:
        stream.close()
    selected.sort(key=lambda item: item[0])
    return [row for _, row in selected]


def default_sample_output(source: Path) -> Path:
    """Return the conventional sample filename beside a source file."""

    return source.with_name(f"{source.stem}.sample.csv")


def validate_sample_options(
    method: SampleMethod | str,
    *,
    rows: int | None,
    percent: float | None,
    field: str | None,
) -> SampleMethod:
    """Validate options shared by single-file and batch adapters."""

    try:
        selected_method = SampleMethod(method)
    except ValueError as exc:
        choices = ", ".join(item.value for item in SampleMethod)
        raise InputError(f"Unknown sample method {method!r}; choose from {choices}.") from exc
    if selected_method is SampleMethod.STRATIFIED and not field:
        raise InputError("--field is required with stratified sampling.")
    if selected_method is not SampleMethod.STRATIFIED and field is not None:
        raise InputError("--field can only be used with stratified sampling.")
    _validate_size_options(rows, percent)
    return selected_method


def sample_csv(
    source: str | Path,
    *,
    method: SampleMethod | str,
    rows: int | None = None,
    percent: float | None = None,
    field: str | None = None,
    seed: int | None = None,
    output: str | Path | None = None,
    delimiter: str = ",",
    encoding: str = "utf-8-sig",
    force: bool = False,
) -> SampleResult:
    """Create a bounded-memory sample of a CSV file."""

    selected_method = validate_sample_options(
        method, rows=rows, percent=percent, field=field
    )

    try:
        config = CsvConfig(encoding=encoding, delimiter=delimiter)
    except ValueError as exc:
        raise InputError(f"Invalid CSV setting: {exc}") from exc
    source_path = Path(source)
    output_path = (
        Path(output) if output is not None else default_sample_output(source_path)
    )
    _validate_paths(source_path, output_path, force=force)
    scan = _scan(source_path, config, field)
    size = _sample_size(scan.row_count, rows, percent)
    selected = _select_rows(
        source_path, config, scan, selected_method, size, seed
    )

    writer_encoding = _output_encoding(source_path, config.encoding)
    temporary: Path | None = None
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding=writer_encoding,
            newline="",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            writer = csv.writer(stream, delimiter=config.delimiter)
            writer.writerow(scan.headers)
            writer.writerows(selected)
        os.replace(temporary, output_path)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise ReportError(f"Cannot write sample to {output_path}: {exc}") from exc

    rate = (size / scan.row_count * 100) if scan.row_count else 0.0
    return SampleResult(
        source=source_path,
        output=output_path,
        method=selected_method,
        source_rows=scan.row_count,
        sample_rows=size,
        sample_rate=rate,
        field=field,
        seed=seed,
        encoding=config.encoding,
        delimiter=config.delimiter,
    )

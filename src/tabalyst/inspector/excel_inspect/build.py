"""``inspect_workbook``: read one workbook and describe it (design inspect
``excel.md``).

Reads and writes nothing else: no file, no cache. A sheet is read into memory
one at a time and dropped before the next (lot X-1 measurements).
"""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import islice
from pathlib import Path

from python_calamine import SheetTypeEnum, SheetVisibleEnum

from tabalyst._version import __version__
from tabalyst.errors import ConfigurationError, InputError
from tabalyst.inspector.excel_inspect import parameters
from tabalyst.inspector.excel_inspect.detect import (
    Candidate,
    Choice,
    Facts,
    analyze_rows,
    merged_in_table,
    select,
)
from tabalyst.inspector.models import (
    ExcelCandidate,
    ExcelDetection,
    ExcelInspectConfig,
    ExcelObservation,
    ExcelScope,
    InspectDocument,
    InspectInfo,
    InspectSource,
    InspectWarning,
    Selection,
    WorkbookInfo,
)
from tabalyst.progress import (
    ProgressCallback,
    ProgressPhase,
    byte_progress,
    emit_progress,
)
from tabalyst.scanner.config import ScanConfig
from tabalyst.scanner.paths import Key, format_absolute
from tabalyst.scanner.readers.excel_common import (
    EXCEL_SUFFIXES,
    UNSUPPORTED_SPREADSHEET_SUFFIXES,
    calamine_errors,
    cell_name,
    check_sheet_size,
    open_workbook,
    read_workbook_bytes,
    sheet_xml_sizes,
)

# Candidates listed in a warning message.
_LISTED = 5


def inspect_workbook(
    source: str | Path,
    *,
    scan_config: ScanConfig | None = None,
    on_progress: ProgressCallback | None = None,
) -> InspectDocument:
    """Inspect an ``.xlsx`` or ``.xlsm`` workbook.

    ``scan_config`` is the effective configuration below the visible Inspect
    file (design inspect 5.3): its ``excel.header_row`` seeds ``config``, so a
    new file does not silently undo what a ``--config`` file asked for. Its
    ``excel.dataset_path`` plays no part: the detected selection is proposed.

    Raises ``InputError`` for an unreadable, protected, empty or too large
    workbook, and ``ConfigurationError`` for a spreadsheet format that Tabalyst
    does not read.
    """
    path = Path(source)
    config = ScanConfig() if scan_config is None else scan_config
    suffix = path.suffix.lower()
    if suffix not in EXCEL_SUFFIXES:
        hint = (
            f" {suffix} files are not read yet; save the workbook as .xlsx."
            if suffix in UNSUPPORTED_SPREADSHEET_SUFFIXES
            else ""
        )
        raise ConfigurationError(
            f"Excel Inspect reads {' and '.join(EXCEL_SUFFIXES)} files, not "
            f"{path.name}.{hint}"
        )
    try:
        stat = path.stat()
    except OSError as exc:
        raise InputError(f"Cannot read source {path}: {exc}") from exc
    if not path.is_file():
        raise InputError(f"Source does not exist or is not a file: {path}")
    emit_progress(
        on_progress, path, ProgressPhase.READING, bytes_read=0, bytes_total=stat.st_size
    )
    # One read: the hash is that of the bytes parsed below.
    data, sha256 = read_workbook_bytes(
        path, byte_progress(on_progress, path, stat.st_size)
    )

    candidates, warnings, sheets, tables = _read_workbook(path.name, data)
    truncated = len(candidates) > parameters.MAX_CANDIDATES
    candidates = candidates[: parameters.MAX_CANDIDATES]
    choice = select(candidates, truncated=truncated)
    warnings = _selection_warnings(candidates, choice, truncated) + warnings

    document = InspectDocument(
        inspect=InspectInfo(
            kind="excel",
            tabalyst_version=__version__,
            generated_at=datetime.now(UTC).replace(microsecond=0),
        ),
        source=InspectSource(
            name=path.name, format="excel", size_bytes=len(data), sha256=sha256
        ),
        detection=ExcelDetection(
            scope=ExcelScope(
                header_scan_rows=parameters.HEADER_SCAN_ROWS,
                candidates="truncated" if truncated else None,
            ),
            workbook=WorkbookInfo(sheets=sheets, tables=tables),
            candidates=[_candidate_model(item) for item in candidates],
            selection=Selection(path=choice.path, basis=choice.basis, over=choice.over),
        ),
        warnings=warnings,
        config=ExcelInspectConfig.model_validate(
            {
                "structure": {
                    "dataset_path": choice.path,
                    "header_row": config.excel.header_row,
                }
            }
        ),
    )
    emit_progress(on_progress, path, ProgressPhase.COMPLETE)
    return document


def _path(*names: str) -> str:
    return format_absolute(tuple(Key(name) for name in names))


def _read_workbook(
    name: str, data: bytes
) -> tuple[list[Candidate], list[InspectWarning], int, int]:
    """The candidates of a workbook, their warnings and the counts of sheets
    and named tables. What calamine raises on the way is an ``InputError``."""
    workbook = open_workbook(data, name)
    sizes = sheet_xml_sizes(data)
    for sheet_name in sizes:
        check_sheet_size(name, sheet_name, sizes)
    sheets = workbook.sheets_metadata
    if not sheets:
        raise InputError(f"{name} has no sheet.")
    with calamine_errors(name):
        return _candidates_of(workbook, sheets)


def _candidates_of(
    workbook, sheets
) -> tuple[list[Candidate], list[InspectWarning], int, int]:

    tables: dict[str, list[tuple[str, tuple[int, int], tuple[int, int], list[str], int]]]
    tables = {}
    for table_name in workbook.table_names:
        table = workbook.get_table_by_name(table_name)
        tables.setdefault(table.sheet, []).append(
            (table_name, table.start, table.end, list(table.columns), table.height)
        )
        del table

    candidates: list[Candidate] = []
    warnings: list[InspectWarning] = []
    for meta in sheets:
        visible = meta.visible == SheetVisibleEnum.Visible
        item = Candidate(
            path=_path(meta.name),
            kind="sheet",
            sheet=meta.name,
            table=None,
            visible=visible,
        )
        candidates.append(item)
        if meta.name in tables:
            # The author declared the tables of the sheet: they stand for it.
            item.ineligible_reason = "has_tables"
            for table_name, start, end, columns, height in tables[meta.name]:
                candidates.append(
                    _table_candidate(
                        meta.name, table_name, start, end, columns, height, visible
                    )
                )
            continue
        if meta.typ != SheetTypeEnum.WorkSheet:
            item.ineligible_reason = "no_cells"
            continue
        sheet = workbook.get_sheet_by_name(meta.name)
        if sheet.start is None:
            item.ineligible_reason = "no_cells"
            continue
        first_row, first_column = sheet.start
        facts = analyze_rows(
            islice(sheet.iter_rows(), first_row, None),
            first_row=first_row,
            first_column=first_column,
        )
        merged = list(sheet.merged_cell_ranges or ())
        del sheet
        if facts is None:
            item.ineligible_reason = "no_header"
            continue
        _fill_sheet_candidate(item, facts, merged, warnings)
    return candidates, warnings, len(sheets), sum(len(items) for items in tables.values())


def _fill_sheet_candidate(
    item: Candidate,
    facts: Facts,
    merged: list[tuple[tuple[int, int], tuple[int, int]]],
    warnings: list[InspectWarning],
) -> None:
    on_header, in_data = merged_in_table(merged, facts)
    item.range = facts.range
    item.header_row = facts.header_row + 1
    item.columns = facts.header
    item.elements = facts.rows
    item.blank_rows = facts.blank_rows
    item.merged_ranges = on_header + in_data
    if facts.rows == 0:
        item.ineligible_reason = "no_data_rows"
        return
    item.eligible = True
    where = f"{item.path} ({item.range})"
    for code, count, message in (
        (
            "duplicate_headers",
            facts.duplicates,
            (
                f"{where} repeats {facts.duplicates} header name(s); the columns "
                "keep their position."
            ),
        ),
        (
            "blank_headers",
            facts.blank_headers,
            f"{where} has {facts.blank_headers} column(s) with an empty header.",
        ),
        (
            "blocks_not_split",
            facts.blank_rows,
            (
                f"{where} holds {facts.blank_rows} blank row(s) among its data: "
                "blocks separated by blank rows are not split into several tables."
            ),
        ),
        (
            "multi_level_header",
            on_header,
            (
                f"{where} has {on_header} merged header cell(s): a header on two "
                "levels is read as its last row only."
            ),
        ),
        (
            "merged_cells",
            in_data,
            (
                f"{where} has {in_data} merged range(s) in its data: only the "
                "top-left cell of each holds a value."
            ),
        ),
    ):
        if count:
            warnings.append(
                InspectWarning(
                    code=code,
                    level="warning",
                    message=message,
                    path=item.path,
                    count=count,
                )
            )


def _table_candidate(
    sheet: str,
    table: str,
    start: tuple[int, int],
    end: tuple[int, int],
    columns: list[str],
    height: int,
    visible: bool,
) -> Candidate:
    """A named table: its range and header come from its definition."""
    header = start[0] - 1
    item = Candidate(
        path=_path(sheet, table),
        kind="table",
        sheet=sheet,
        table=table,
        visible=visible,
        elements=height,
        range=f"{cell_name(header, start[1])}:{cell_name(end[0], end[1])}",
        header_row=header + 1,
        columns=columns,
    )
    if height > 0:
        item.eligible = True
    else:
        item.ineligible_reason = "no_data_rows"
    return item


def _candidate_model(item: Candidate) -> ExcelCandidate:
    observation = None
    if item.range is not None:
        observation = ExcelObservation(
            columns=len(item.columns),
            column_names=item.columns[: parameters.COLUMNS_LISTED],
            blank_rows=item.blank_rows,
            merged_ranges=item.merged_ranges,
        )
    return ExcelCandidate(
        path=item.path,
        kind=item.kind,
        sheet=item.sheet,
        table=item.table,
        visible=item.visible,
        range=item.range,
        header_row=item.header_row,
        elements=item.elements,
        eligible=item.eligible,
        ineligible_reason=item.ineligible_reason,
        observation=observation,
    )


# Warnings -------------------------------------------------------------------


def _listing(items: list[Candidate]) -> str:
    shown = ", ".join(f"{item.path} ({item.elements:,})" for item in items[:_LISTED])
    return shown + (", ..." if len(items) > _LISTED else "")


_NOT_ELIGIBLE = {
    "no_cells": "has no cell (an empty sheet, or a chart)",
    "no_header": "has no header row that Tabalyst can recognize",
    "no_data_rows": "has a header and no data row",
    "has_tables": "holds named tables, which are listed on their own",
}


def _selection_warnings(
    candidates: list[Candidate], choice: Choice, truncated: bool
) -> list[InspectWarning]:
    out: list[InspectWarning] = []
    if choice.basis == "ambiguous":
        eligible = [item for item in candidates if item.eligible]
        out.append(
            InspectWarning(
                code="ambiguous_collections",
                level="warning",
                message=(
                    f"{len(eligible)} tables are equally plausible: "
                    f"{_listing(eligible)}. None was selected: set "
                    "config.structure.dataset_path to the one to analyze."
                ),
                count=len(eligible),
            )
        )
    elif choice.basis == "no_eligible_candidate":
        out.append(
            InspectWarning(
                code="no_collection",
                level="warning",
                message=(
                    "No supported table was found: no sheet has a recognizable "
                    "header followed by data rows, and the workbook has no "
                    "named table with data."
                ),
                reason="no_eligible_table",
            )
        )
    elif truncated:
        out.append(
            InspectWarning(
                code="candidates_truncated",
                level="warning",
                message=(
                    f"More than {len(candidates)} sheets and tables were found; "
                    f"only the first {len(candidates)} are listed, so none was "
                    "selected. Set config.structure.dataset_path to the one to "
                    "analyze."
                ),
                count=len(candidates),
            )
        )
    ineligible = [item for item in candidates if not item.eligible]
    for item in ineligible[: parameters.MAX_INELIGIBLE_NOTES]:
        out.append(
            InspectWarning(
                code="candidate_not_eligible",
                level="info",
                message=f"{item.path} {_NOT_ELIGIBLE[item.ineligible_reason or 'no_cells']}.",
                path=item.path,
                reason=item.ineligible_reason,
            )
        )
    if len(ineligible) > parameters.MAX_INELIGIBLE_NOTES:
        out.append(
            InspectWarning(
                code="candidate_not_eligible_truncated",
                level="info",
                message=(
                    f"{len(ineligible)} candidates are not eligible; only the "
                    f"first {parameters.MAX_INELIGIBLE_NOTES} are described."
                ),
                count=len(ineligible),
            )
        )
    return out

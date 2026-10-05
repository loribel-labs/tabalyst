---
title: Inspect Excel workbooks
description: Let tabalyst inspect find which sheet or table of an Excel workbook (.xlsx, .xlsm) holds the data, then edit the Inspect file to choose the table and the header row that scan and report use.
---

A workbook can hold several sheets and several tables. Use `tabalyst inspect`
to see how Tabalyst understands an `.xlsx` or `.xlsm` workbook before you scan
it, and to choose the table when Tabalyst cannot. **Tabalyst Inspect** reads the
workbook once, lists its candidate tables, proposes one and writes the answer in
a small JSON file beside the source:

```console
tabalyst inspect sales.xlsx
```

```text
Inspect: sales.xlsx-inspect.json
Selection: $.Orders (much larger than $.Regions)
```

The Inspect file is named after the full source name plus `-inspect.json`:
`sales.xlsx-inspect.json`. Its last section, `config`, holds the rules that
`tabalyst scan` and `tabalyst report` apply to this workbook: the table, and
optionally its header row. The other sections describe what Inspect found;
Tabalyst replaces them each time it inspects. The structure of the file is in
the [Inspect format](format.md#inspect-files-of-workbooks-kind-excel).

Tabalyst reads `.xlsx` and `.xlsm` files (macros are ignored). It never modifies
the workbook. Older `.xls` files, `.xlsb` and `.ods` files are refused with exit
code `2`: save them as `.xlsx` first.

## One table: nothing to choose

A workbook with one sheet holding one table needs no Inspect file. `tabalyst
scan` and `tabalyst report` inspect it themselves, keep the result in Tabalyst's
local storage and read the table it selects:

```console
tabalyst report sales.xlsx
```

Run `tabalyst inspect` when you want to see or change the rules, or when
Inspect cannot choose.

## What is a candidate table

A candidate is a **sheet**, or a **named table** (an Excel table, also called a
list object) inside a sheet. Candidates are written as paths with the workbook as
root:

| Path | Meaning |
| --- | --- |
| `$.Sales` | The sheet `Sales`. |
| `$.Sales.Orders` | The named table `Orders` of the sheet `Sales`. |
| `$["Q1 2026"]` | A sheet whose name is not a plain identifier is quoted. |

A sheet that holds named tables is not a candidate itself: its tables are. The
author declared them, and a table guessed beside them would duplicate or
contradict them. Inspect lists such a sheet as not eligible (`has_tables`).

For a sheet, Inspect looks for the **header row** in its first 50 rows: the first
row that fills at least half the width of the sheet, holds only text, repeats few
names and is followed by data. Title lines and blank rows above the header are
skipped, and the table starts at the first and ends at the last filled column of
the header. The data rows are the filled rows under it; blank rows are not
records. A named table gives its range and header exactly, with no guessing.

| `ineligible_reason` | A candidate is not eligible when |
| --- | --- |
| `no_cells` | The sheet is empty, or is a chart sheet. |
| `no_header` | No row looks like a header followed by data: a note, a block of numbers, a header row alone. |
| `no_data_rows` | A named table has no data row. |
| `has_tables` | The sheet holds named tables, which are listed on their own. |

## When Inspect cannot choose

Inspect selects a table only when that choice is clear, with the rule that it
uses for [JSON files](json.md#when-inspect-cannot-choose): only one table is
eligible, or the largest one has at least 10 times more data rows than the next
one. A hidden sheet is selected only when no visible table is eligible. Sheet
names play no part. Otherwise nothing is selected, and `scan` and `report` stop
with exit code `2` before analyzing anything:

```text
Error [shop.xlsx]: 2 tables of shop.xlsx are equally plausible. Nothing was analyzed.
Candidates:
  $.Sales (8 rows)
  $.Costs (5 rows)
Pass --collection with a sheet or table path such as '$.Sheet', or run `tabalyst inspect shop.xlsx` and set config.structure.dataset_path in the file it writes.
Choose the table to analyze:
  tabalyst report shop.xlsx --collection Sales
  tabalyst report shop.xlsx --collection Costs
Or report every table: tabalyst report shop.xlsx --all-collections
```

`report` and `scan` print one ready-to-run command per table, and so does
`tabalyst inspect shop.xlsx`: copy the one you want and run it. The commands use
the short form, the name alone (`--collection Costs`, or `--collection
Sales.Orders` for a named table), whenever the name is plain. A sheet name that
is not a plain identifier needs the quoted path (`'$["Q1 2026"]'`), which the
commands print as it must be typed. A workbook is read one table at a time: pass
`--collection` once, or use `tabalyst report --all-collections` to report every
table, one pair of files per table (see [Report Excel
workbooks](../report/excel.md#every-table-of-a-workbook)). To make the choice
stick, open `shop.xlsx-inspect.json` and set it in `config`:

```json
"config": {
  "structure": {"dataset_path": "$.Costs", "header_row": null}
}
```

`tabalyst report shop.xlsx` then analyzes `$.Costs`. `--collection` outranks the
Inspect file, and a notice says so when they differ.

## Change how the table is read

Everything you may edit is in `config`. Omit a key to keep the default:

| Key | Default | Effect |
| --- | --- | --- |
| `structure.dataset_path` | the selection, or `null` | The table analyzed: `$.Sheet` or `$.Sheet.Table`. |
| `structure.header_row` | `null` | The 1-based row of the sheet that holds the header, instead of the detected one. Use it when the detection picks the wrong row, or finds none. |

`header_row` applies to a sheet; a named table has its own header. The row must
hold at least one value. A sheet with no recognizable header makes `scan` and
`report` stop with exit code `4` and say to set it. Unknown keys and values of
the wrong type are errors that name the key, never ignored, and `flatten`,
`arrays` and `errors` do not exist for a workbook.

## Types, dates and empty cells

Cells keep their Excel type: a number is a number, a boolean a boolean, a text a
string. Excel has a single number type, so a whole number such as `21` is read as
an integer, even in a column of amounts such as `10.5`. Dates and times are read
as ISO text (`2026-01-31`), which the date detector recognizes, so a date column
is typed `date`. A formula is read as its last calculated value. An empty cell
is a missing value, like an empty CSV cell.

## Warnings

Inspect warns about what a scan will have to live with:

| Code | When |
| --- | --- |
| `blocks_not_split` | Blank rows lie among the data. Blocks separated by blank rows are not split into several tables; the blank rows are skipped. |
| `duplicate_headers`, `blank_headers` | The header repeats a name or leaves a cell empty. The columns keep their position, and the report names them `id#1`, `id#2`. |
| `merged_cells` | Merged ranges lie in the data: only the top-left cell holds a value. |
| `multi_level_header` | Header cells are merged, as in a header on two levels. Only the last row is read as the header. |

Merged cells above the header, such as a title, are ignored. The informative
`candidate_not_eligible` entries explain why a sheet was left out.

## Inspect a workbook again

Run `tabalyst inspect` again after the workbook changes. The detection and
warnings are rewritten; your `config` is kept. `--reset-config` replaces it by
the detected one, and `--force` replaces a file that cannot be kept, such as one
written for another version of the format, one with an invalid `config`, or an
Inspect file written for a JSON source. `scan` and `report` refuse such a file of
another kind, with exit code `2`, instead of reading it with the wrong rules. If
the configured sheet or table is no longer in the workbook, the new file warns
(`configured_path_not_found`), and `scan` and `report` stop with exit code `2`
and list the sheets that exist.

## Which setting wins

A new Inspect file starts from the layers below it: `scan.excel.header_row` of a
`--config` file is written into its `config`, so the file does not undo what
the configuration asked for.

From lowest to highest priority:

1. Tabalyst defaults;
2. the table Inspect detected, when the workbook has no Inspect file;
3. the `scan.excel` section of each `--config` file (`dataset_path`,
   `header_row`);
4. the `config` of the Inspect file beside the workbook;
5. `--collection`.

## Limits

- A pattern such as `*.xlsx` skips the lock files that Excel keeps beside an open
  workbook (`~$book.xlsx`), as it skips Inspect files.

- One table per run. A workbook is not scanned sheet by sheet, and relations
  between sheets are not analyzed.
- Blocks separated by blank rows, and total or note rows under the data, are
  not recognized: a total row counts as a record.
- A real error cell (`#DIV/0!`) and a formula that was never calculated read as
  empty cells, and cannot be counted.
- Calamine reads a sheet into memory, about 0.9 byte per byte of its XML. A
  workbook with a sheet whose XML exceeds 1 GiB is refused. Reading a sheet
  of a million rows of eight columns takes about 4 seconds and 360 MB.
- Password-protected workbooks are refused with exit code `4`.

## Messages and exit codes

`--verbose` lists every candidate and the informative warnings; `--quiet` keeps
only warnings and errors. Messages use standard error.

| Code | Meaning |
| --- | --- |
| `0` | The inspection worked, including when it selected nothing. |
| `2` | Configuration problem: unsupported spreadsheet format, invalid Inspect file, unresolved table, or a configured sheet that is gone (in `scan` and `report`). |
| `4` | The workbook cannot be read: corrupt, password-protected, empty, too large, or no header in the sheet. No file is written. |
| `1` | Another failure, such as an output that cannot be written. |

## Python API

```python
import tabalyst

result = tabalyst.inspect("sales.xlsx")
print(result.path)
print(result.document.detection.selection.path)
```

`tabalyst.inspect()` and `tabalyst.generate_inspections()` accept workbooks as
they accept JSON files, with `config_path`, `reset_config` and `force`.
`tabalyst.scan()` reads the table named by `ScanConfig(excel={"dataset_path":
"$.Sales"})`; without it, a workbook is an error that says to choose.

# Excel support (Inspect, Scan, Report): cases and decisions

Written on 2026-10-04. Status: **lots X-1 to X-4 done** (measurements, Excel Inspect, Excel reader and
parcours, public documentation and demos). Prepared in the working tree, not
committed or released. This page frames the work before the lots; the contract of the
shared Inspect shell is [design.md](design.md), which this kind extends the way
section 1 of that document planned (`inspect.kind`, a sibling package, a branch
in the dispatch).

## Goal

```text
.xlsx / .xlsm -> Inspect -> Scan -> Report
```

- **Simple case**: one sheet holding one well-identified table. Nothing to
  choose: `scan` and `report` run directly, as for a one-collection JSON file.
- **Several sheets or tables**: `inspect` validates the workbook and gives the
  same information as for JSON (candidates, why, selection) plus the
  instruction to exploit one case (`--collection` or the Inspect file).
  `scan` and `report` stop with exit 2 until a table is chosen (design 11.4).

## Decisions (maintainer, 2026-10-04)

| ID | Topic | Decision |
| --- | --- | --- |
| X-1 | Library | `python-calamine` only. It exposes `table_names`, `get_table_by_name`, `merged_cell_ranges`, `sheets_metadata` (visibility), `PasswordError`. No `openpyxl`. |
| X-2 | Detection | One sheet is one candidate; named Excel tables (`ListObject`) are additional candidates. Blocks separated by blank rows are **not** split: a warning says so. |
| X-3 | Formats | `.xlsx` and `.xlsm` (case-insensitive). `.xls` and `.ods` are refused with a clear message until a later lot. |

## Mapping to the JSON model

| JSON Inspect | Excel Inspect |
| --- | --- |
| Candidate: array reachable through keys | Candidate: a sheet, or a named table |
| `dataset_path` `$.customers[]` | `dataset_path` `Sales` (sheet) or `Sales!Orders` (named table `Orders`) |
| `eligible` = at least one element, all objects | `eligible` = a header row and at least one data row |
| `ineligible_reason` `empty`, `non_object_elements` | `empty`, `no_header`, `no_data_rows` |
| `selection.basis` | Same values; `root_array` and `jsonl_records` do not apply |
| Dominance ratio (10) | Same rule over data row counts, a parameter to measure |
| Observation of the first records | Observation of the first rows: columns, blank cells, types seen |

Syntax of `dataset_path` is to be fixed in lot X-2 (sheet names may contain
spaces, `!`, quotes: a quoted form is needed, reversible like `parse_path`).

## Cases

### A. Workbook level

| # | Situation | Behavior |
| --- | --- | --- |
| A1 | One sheet, one table with a header on the first row | Selected automatically, `only_eligible_candidate`. `report` works without `inspect`. |
| A2 | Several sheets, one eligible (others empty, notes, charts) | Others listed as ineligible; the eligible one selected. |
| A3 | Several eligible sheets or tables | Dominance rule, else `ambiguous`: Scan and Report suspended (exit 2) with the candidate list (name, rows, columns) and the exits. |
| A4 | Sheet that also holds named tables | Each named table is a candidate. The sheet itself is listed as not eligible (`has_tables`) and is not analyzed: the author declared its tables, and a heuristic table beside them would duplicate or contradict them (decided in X-2; the first draft kept the sheet when no table covered its used range). |
| A5 | Hidden sheets | Listed, flagged `hidden`, never auto-selected over a visible eligible sheet. |
| A6 | Chart sheets, macro sheets | Ignored, listed as ineligible (`no_cells`). |
| A7 | Workbook with no eligible candidate | `no_collection`, unresolved, same exits as JSON. |
| A8 | Password-protected, corrupt or empty workbook | `InputError` (exit 4), nothing written, as invalid JSON (8.7). |
| A9 | `.xls`, `.ods`, `.xlsb` | `ConfigurationError` naming the supported extensions. |

### B. Table inside a sheet

| # | Situation | Behavior |
| --- | --- | --- |
| B1 | Header on the first row of the used range | Standard case. |
| B2 | Title or blank rows above the header | Header row found by rule (first row whose cells are mostly distinct text, followed by data rows); the rows skipped are reported. The rule is measured, not guessed (design 15 spirit). |
| B3 | Total or notes rows under the data | Warning when the structure changes at the end; rows are kept, never dropped silently. |
| B4 | Blank rows or columns inside the used range | Rows: kept as blank rows, warning `blocks_not_split` when a blank row separates two filled regions (X-2). Columns: kept as unnamed columns. |
| B5 | Duplicate or empty header cells | Deduplicated by a documented suffix rule, with a warning; never a silent rename. |
| B6 | Merged cells | The value belongs to the top-left cell; warning with the count. Merged header cells give a `multi_level_header` warning. |
| B7 | Named table (`ListObject`) | Exact range and header from the table definition: no heuristic. Priority over B2. |

### C. Cell content

| # | Situation | Behavior |
| --- | --- | --- |
| C1 | Native types | Number, boolean, string, date/time keep their native type (more exact than CSV). How they reach the Scan engine (typed values, not text) is the main design question of lot X-3. |
| C2 | Dates | Excel serial numbers are read as dates only when the cell is date-formatted, as calamine reports; the epoch (1900 or 1904) follows the workbook. |
| C3 | Formulas | The cached value is read. A formula never calculated has no cached value and reads as an empty cell; calamine does not say which, so no warning can count them (X-1). |
| C4 | Error cells (`#N/A`, `#DIV/0!`) | Calamine returns an empty string for a real error cell (`t="e"`), the same as for an empty cell. They read as missing values and cannot be counted. A text cell that spells `#N/A` is read as text. Known limitation to document (X-1). |
| C5 | Empty cell | Missing value, as an empty CSV cell. Calamine returns `""` for an empty cell and for an empty string alike: they cannot be told apart. |

### D. Integration

| # | Topic | Behavior |
| --- | --- | --- |
| D1 | Identity | `source_sha256` over the file bytes; the chosen table is part of the configuration (`config_sha256`). Same triple rule as design 10.1. |
| D2 | Visible file | `<name>.xlsx-inspect.json`, distinct from `<name>.xlsx`. `*-inspect.json` stays excluded from patterns. |
| D3 | Cache | Automatic Inspect and cache as for `.json`: the detected selection is layer 2 of design 11.1. |
| D4 | Output names | `.report.html` and `.report.json` for `.xlsx`/`.xlsm`; collisions with `data.csv` handled by the existing batch rule. |
| D5 | `--collection` | Accepts the sheet/table syntax; a path that is no longer in the workbook is the exit 2 of design 11.5. |
| D6 | Reading model | A workbook is read whole by calamine (no streaming). Memory grows with the file; a size guard and a measurement are part of lot X-1, as for line sizes in JI-4. |
| D7 | `sample` | Out of scope. |
| D8 | Several tables per run | One selected table by default (DP-A); repeated `--collection` follows the JSON rule. |

## Lot X-1: measurements and decisions (2026-10-04)

Spike code and workbooks are in `D:\GIT	abalyst.testrtifacts\excel-x1`
(`make_cases.py`, `gen.py`, `bench.py`, `header_rule.py`), not in the
checkout. `python-calamine` 0.8.2, Python 3.12, Windows.

**What calamine gives.** `load_workbook(path, load_tables=True)` is lazy: the
workbook costs nothing until a sheet is read. Tables need `load_tables=True`
(`TablesNotLoaded` otherwise). `sheets_metadata` gives the type (`WorkSheet`,
`ChartSheet`) and visibility of each sheet; chart sheets and empty sheets read
as zero cells. A table gives `name`, `sheet`, `start`, `end`, `columns`.
`merged_cell_ranges` gives the merged areas. Values come as `str`, `float`,
`bool`, `date`, `datetime`, `time`; an integer comes as a `float` (`1.0`).

**Cost.** `get_sheet_by_name` reads the whole sheet into memory; iterating
(`iter_rows`) afterwards is lazy. Eight columns of mixed values:

| Rows | File | calamine `iter_rows` | calamine `to_python` | openpyxl `read_only` |
| --- | --- | --- | --- | --- |
| 100,000 | 4.2 MB | 0.4 s, +37 MB | 0.4 s, +84 MB | 3.5 s, +32 MB |
| 1,000,000 | 41.9 MB | 3.4 s, +363 MB | 3.7 s, +826 MB | 41.1 s, +111 MB |

The sheet costs about 45 bytes per cell, or 0.9 byte per byte of uncompressed
sheet XML (393 MB of XML for 1,000,000 rows). Memory comes back when the sheet
is dropped (+0.5 MB afterwards) and a second read costs the same again, so
Inspect reads one sheet at a time. The 1,000,000-row case is the practical
ceiling of a sheet (1,048,576 rows).

**Decisions.**

| ID | Decision |
| --- | --- |
| X-4 | Streaming with `iter_rows`, one sheet in memory at a time; no `to_python`. |
| X-5 | Size guard before reading a sheet, from the zip directory (no decompression): uncompressed size of the sheet XML, and its ratio to the compressed size against decompression bombs. Limits to be fixed in lot X-3 with the measure above (0.9 byte of memory per XML byte). The hash is the SHA-256 of the file bytes, as for JSON. |
| X-6 | Question 2 answered: **a typed reader**, not text through the CSV path. The engine already takes native types for JSON (`integer`, `number`, `boolean`, `string`). Mapping: integral `float` within 2^53 becomes `integer`, other `float` becomes a decimal from its shortest text (no `0.1000000000000001`), `bool` stays `boolean`, `""` is a missing value, `date`, `datetime` and `time` become ISO 8601 text that the existing temporal detector classifies (the engine has no date type). Calamine gives no cell format, so an integral amount formatted `0.00` reads as `integer`. |
| X-7 | The header rule of the spike (below) is kept as the starting point of lot X-2. |

**Header rule (spike).** The header row is the first row, within the first 50,
that fills at least half the width of the sheet (a single cell is accepted only
for a one-column sheet), holds only text, has at least half of its values
distinct, and is followed by a non-blank row. On the test workbook it finds the
header under a title row, a merged subtitle and a blank row (`Sales`: row 3,
duplicate `id` kept for a warning), a table that does not start in column A,
and a blank-separated block sheet (the first block only, hence the warning
`blocks_not_split`). It was not run on real workbooks: **sample workbooks from
the maintainer are needed in lot X-2 before the rule is fixed**, as
`DOMINANCE_RATIO` was measured on real shapes.

## Questions left for the lots

1. `dataset_path` syntax for sheets and tables (quoting, reversibility).
2. ~~Typed values or text~~: answered in X-1 (X-6).
3. Header-row rule and `DOMINANCE_RATIO` for rows: measured on real workbooks
   before the values are fixed (X-7).
4. ~~Memory and time of calamine on large sheets (D6)~~: measured in X-1; the
   guard limits are fixed in lot X-3 (X-5).

## Proposed lots

| Lot | Content |
| --- | --- |
| X-1 | Done 2026-10-04: dependency, reader spike, measurements (memory, time, header rule), question 2 decided. |
| X-2 | Done 2026-10-04 (see "Lot X-2"). Excel Inspect: kind `excel`, candidates, eligibility, selection, warnings, `dataset_path`, Inspect file, cache. Tests in `tests/inspect/`. |
| X-3 | Done 2026-10-04 (see "Lot X-3"). Scan reader for a selected sheet or table; identity; `--collection`. |
| X-4 | Done 2026-10-04 (see "Lot X-4"). Report, CLI inputs and naming, public docs (`docs/en/inspect/`, `limitations.md`), demos, changelogs. |

Follow-up in `tabalyst-studio` once documented: the website advertises only
what `README.md` documents, so the README and `docs/en/` change first.

## Lot X-2: Excel Inspect (2026-10-04)

Built on synthetic workbooks, as decided with the maintainer: the header rule
and `DOMINANCE_RATIO` (10, the JSON value) stay **provisional** until measured
on real workbooks. Code: `tabalyst.inspector.excel_inspect` (`parameters`,
`detect`, `build`) and `tabalyst.scanner.readers.excel_common`; tests in
`tests/inspect/test_excel_inspect.py` (lot marker `X-2`, workbooks written
with `xlsxwriter`, now a dev dependency).

**Format (additive, `format_revision` stays 1).** `inspect.kind` is `excel`,
`source.format` is `excel` (for `.xlsx` and `.xlsm`), and `detection` and
`config` follow the kind (`InspectDocument` reads each with the model of its
kind; a mismatch is refused). The shell is unchanged: triple, `source`,
`warnings`, visible file `<name>.xlsx-inspect.json`, re-inspection keeping
`config`, `--reset-config`, `--force`. An existing file of another kind is
refused unless `--force`. `detection` holds `scope` (`header_scan_rows`,
`candidates: "truncated"` when cut at 100), `workbook` (`sheets`, `tables`),
`candidates` and `selection` (the JSON `basis` values minus `root_array` and
`jsonl_records`). A candidate has `path`, `kind` (`sheet` or `table`), `sheet`,
`table`, `visible`, `range` (A1, header included), `header_row` (1-based),
`elements` (filled data rows), `eligible`, `ineligible_reason` and
`observation` (`columns`, `column_names`, `blank_rows`, `merged_ranges`).

**Decisions.**

| ID | Decision |
| --- | --- |
| X-8 | `dataset_path` is an absolute path with the workbook as root: `$.Sales` is a sheet, `$.Sales.Orders` a table of that sheet, `$["Q1 2026"]` a name that is not an identifier. It reuses `parse_path` and `format_absolute`, so quoting is reversible and canonical, and the `--collection '$.Sheet'` form is the JSON one. |
| X-9 | `config` holds `structure.dataset_path` and `structure.header_row` (strict positive integer, 1-based sheet row; `null` means detected). Nothing else is exposed: `flatten`, `arrays` and `errors` are refused. Both are validated now and projected onto the scan configuration in lot X-3. |
| X-10 | Ineligible reasons: `no_cells` (empty sheet, chart sheet), `no_header` (no recognizable header followed by data, which includes a header row alone), `no_data_rows` (a named table without data, or a header whose data is outside its columns), `has_tables`. |
| X-11 | A hidden sheet competes only when no visible candidate is eligible. |
| X-12 | A workbook with any sheet above `MAX_SHEET_XML_BYTES` (1 GiB uncompressed, about 0.9 GB of memory) is refused with `InputError`, as a fatal reader problem is for JSON. This fixes X-5. |
| X-13 | New warnings: `blocks_not_split` (blank rows among the data, with their count), `duplicate_headers`, `blank_headers`, `merged_cells` (in the data), `multi_level_header` (merged header cells; merges above the header, such as a title, are ignored). |

**Not done in X-2, by design.**

- B3 (total or notes rows under the data): no heuristic yet; such rows are
  counted as data. Needs real workbooks.
- The automatic cache (D3) and the resolution layers: they belong to
  `resolve_interpretation`, which lot X-3 extends with the Excel reader.
  Until then `scan` and `report` do not read `.xlsx` (they would treat it as
  CSV), and `inspect` prints the `--collection` commands that lot X-3 makes
  work.
- Projection of `config` onto `ScanConfig` (`to_scan_layer`), public
  documentation (`docs/en/inspect/`, `limitations.md`, the public Inspect
  format changelog) and the website follow-up: lot X-4, so the docs ship with
  the release that has the whole feature.

## Lot X-3: Excel reader and parcours (2026-10-04)

`tabalyst scan` and `tabalyst report` read a workbook: `report data.xlsx` works
in one command for a workbook with one table, and stops with exit 2 and the
candidate list when several tables are plausible, as for JSON.

**Reader** (`tabalyst.scanner.readers.excel_reader`). One table per run, the
one `excel.dataset_path` names. The dataset is `rows`, kind `table`, with
`Column` segments and declared fields, as for CSV, so the report and the
presence rules are shared. Each filled data row is a record; blank rows are
skipped. `Location.line` holds the 1-based sheet row. Values are typed
(decision X-6): whole floats up to 2^53 are `integer`, other floats `number`
(a `Decimal` of the shortest text), booleans `boolean`, text `string`, dates
and times ISO 8601 `string` that the date detector types. The header and the
column span come from `excel_table` (shared with Inspect, so both find the same
table); `excel.header_row` overrides the detection. The file is hashed in a
pass of its own (the sheet is read by calamine from the path), and the size
guard of X-12 applies to the sheet read.

**Configuration and format.**

| ID | Decision |
| --- | --- |
| X-14 | `ScanConfig.excel` holds `dataset_path` (sheet or table path, canonical, same validation as the Inspect file) and `header_row` (strict integer ≥ 1). It is part of `config_sha256`, so the hash of every configuration changed once and **the scan format revision moves to 6**; documents of revision 5 are refused as before. `source.format` is `excel` and `source.excel` records `dataset_path`, `sheet`, `table`, `range`, `header_row` and `header`. `SourceInfo.header` is the column names of a tabular source (CSV or Excel). |
| X-15 | Resolution (`resolve_interpretation`) treats a workbook like a JSON source with `excel.dataset_path` in place of `json.collections`: layers are built-in defaults, automatic detection (cached in `inspect.json` beside `scan.json`, valid for the same content and `HEADER_SCAN_ROWS`), `--config` (`scan.excel`; `scan.json.collections` is dropped for a workbook), the visible Inspect file, then `--collection`. A visible `dataset_path: null` lets a lower layer decide. |
| X-16 | `--collection` for a workbook takes `Sales`, `$.Sales`, `$.Sales.Orders` or `$.Sales[]` (the CLI expands the short form to a JSON path; the trailing `[]` is dropped). It is accepted once: two values are a `ConfigurationError`. Collection values that are not JSON array paths no longer fail the configuration of the other sources of a batch (`json_collection_paths`). |
| X-17 | A sheet that no longer exists, a table on another sheet, an empty header row override or a sheet without a recognizable header fail with `ConfigurationError` or `InputError` that names the way out; nothing is written. Unlike JSON, a visible file that names a gone sheet is not singled out by `check_result`: the reader's message names the sheets present. |
| X-18 | The errors policy resolves to `strict` for a workbook (no row can be excluded: ragged rows do not exist). |

The report profile gets `format: "excel"`; the cells of the table are typed
columns exactly as for CSV (`ambiguous_headers` applies to duplicate or blank
headers). The project store accepts a workbook (table layout as CSV); one
smoke test only, no dedicated project tests.

**Known limits, for lot X-4 to document or fix.**

- The report profile's `source.encoding` falls back to the configuration's CSV
  encoding (`utf-8-sig`) for a workbook, which says nothing true about it; the
  profile format needs a decision (null, or a field that says `n/a`). `scan -v`
  already leaves the line out.
- `tabalyst report data.xlsx --collection X` with a table named after a
  keyword-like or non-identifier sheet needs the quoted form
  (`'$["Q1 2026"]'`).
- Public documentation, the public format changelogs (scan revision 6, Inspect
  kind `excel`, report profile `format`), `docs/en/reference/configuration.md`
  (new `excel` section), `limitations.md`, the demos and the website follow-up
  remain lot X-4.

## Lot X-4: documentation, report and demos (2026-10-04)

- **Report profile revision 11.** `source.format` can be `excel` and
  `source.encoding` is `null` for a workbook (it was the CSV encoding by
  fallback, which said nothing true). The HTML header leaves the encoding out
  when it is null, and the CLI's `Encoding:` lines too. The profile changelog,
  the profile reference and the scan format changelog (revision 6) say so.
- **Shared cache and format revisions.** A stored scan of an older format
  revision made `tabalyst report` fail ("Run tabalyst scan again") instead of
  being replaced, contrary to the documented behavior; the revision bump of
  lot X-3 would have hit every user on upgrade. `read_scan_document` now raises
  `UnsupportedScanDocument`, which `current_scan` treats as an out-of-date cache
  (a test covers it). `report --scan` of a standalone document still refuses it.
- **Public docs** (`docs/en/`): new pages `inspect/excel.md` and
  `report/excel.md`; the Excel kind in `inspect/format.md` and its changelog;
  `scan/format.md` (Excel sources, revision 6) and changelog; the `excel` scan
  settings in `reference/configuration.md`; CLI, Python API, glossary,
  concepts, limitations, examples; the overview in English and French; the
  README. `inspect/format-changelog.md` records the kind as an addition to
  revision 1, as decided in X-2.
- **Demo.** `examples/input/sales.xlsx` (written deterministically by
  `examples/make_sales_workbook.py`, `xlsxwriter` only for that) and
  `examples/output/sales/`; the other outputs were regenerated, which updates
  their profile revision.
- **Checked.** Full test suite, ruff, the links and anchors of `docs/en/`, and
  the sales report in the in-app browser (no console error). The Playwright
  script `tests/browser/report.cjs` could not run here (module missing), so the
  regression check of the architecture page was not run; the only template change
  is the encoding fact, shown or left out.

**Review fixes (2026-10-04, `/code-review` of the working tree).**

- Calamine errors raised while a sheet or table is read in Inspect are an
  `InputError` (`calamine_errors`), so a corrupt sheet fails its own file, not
  the batch.
- The seed of an Excel `config` takes `header_row` from the effective layers
  (design 5.3); it was always `null` and outranked a `--config` value.
- Patterns skip Excel lock files (`~$*`, `is_lock_name`).
- The workbook is read once into memory (`read_workbook_bytes`): the SHA-256,
  the zip directory and calamine all work on those bytes, so the identity is
  that of the content parsed even if the file is saved again meanwhile. The
  cost is the compressed file in memory, about the file size.
- `scan` and `report` refuse a visible Inspect file of another kind than the
  source (`_read_visible`), as `tabalyst inspect` already did.
- Tests: `tests/inspect/test_excel_review.py`.

**Choosing a table from the command line (2026-10-05).**

- `scan` and `report` print the commands to copy, as `inspect` did: one per
  eligible candidate when the detection is `ambiguous`, in the short form of
  `--collection` (`Costs`, `Sales.Orders`) when it expands back to the same path,
  else the quoted absolute path (`'$["Sales Q1"]'`). The library error is
  `UndecidedCollection` (a `ConfigurationError`, so exit 2 and the same message);
  each command adds its own lines (`scan` has no `--all-collections` line).
  `inspect` uses the same helper, and calls a workbook candidate a table.
- `report --all-collections` (JSON and Excel): `-d` is optional for one input and
  required for several; not with `-o`, `--collection` or `--scan`. Planning runs
  the automatic detection (`detect_collections`, cached like Scan's) and makes
  one job per visible eligible candidate, named `<stem>.<slug>.html` and
  `.json`; hidden sheets are left out with a warning (they stay chosen with
  `--collection`). The slug is the keys of the path joined by `-`, lower case,
  accents removed, other characters `-`, numbered `-2` on equal slugs,
  `collection-N` when nothing is left, `root` for `$[]`. A source with nothing to
  report fails alone (exit 2); CSV and JSONL keep their usual names in the same
  batch. The visible Inspect file is ignored by the listing, and a job's
  collection outranks it, with the usual notice.

**Follow-up in `tabalyst-studio`, not done here.** Add `inspect/excel` and
`report/excel` to the sidebar order (`src/routeMiddleware.ts`), and the five pages
`reference/cli/{report,scan,inspect,sample,cache}` (`reference/cli.md` became
`reference/cli/index.md`, same URL). The website only
advertises what the README documents, and the README now documents Excel:
update the feature list when a release carries it. The demo it copies,
`examples/output/insurance-customers/`, is regenerated (profile revision 11).

**Release, when it comes.** Excel is unreleased: update `about/releases.md` and
the version at the release, and the private status in `tabalyst-gb/DOCS/`, per
`AGENTS.md`.

# Tabalyst Dedup design

Contract of lot 0 of Tabalyst Dedup, written on 2026-10-22. It turns the functional
and technical specification (private: `tabalyst-gb`,
`KANBAN/04-SRS/2026-10-22-dedup/Tabalyst_Dedup_Cahier_des_Charges.md`, "the
specification" below) and the decisions D1 to D18 of the plan (private:
`KANBAN/05-PROGRESS/2026-10-22-tabalyst-dedup-plan.md`) into the contract that the
implementation lots 1 to 11 follow. The identifiers of the specification (`DEC-xx`,
`FR-IDENT-xx`, `T01` to `T30`, section numbers written `S9.2`) and of the plan
(`D1` to `D18`, `E1` to `E18`) are reused for traceability. The contract tests are in
`tests/dedup/`. The two architecture decisions that need their own record are
[the exact store and its disk fallback](../adr/2026-10-22-dedup-exact-store-and-disk-fallback.md)
and [the ownership of the outputs and the recovery after an interruption](../adr/2026-10-22-dedup-output-ownership-and-recovery.md).

Tabalyst Dedup is a beta feature. Nothing here is implemented before its lot, and
nothing here is public documentation: the public pages are written in lot 11, after the
feature is released (project rule: document only what the latest PyPI release has).

## 1. Status of decisions

| Label | Meaning |
| --- | --- |
| **Accepted** | Validated by the maintainer. |
| **Proposed** | Written by lot 0 to close a gap of the specification. The maintainer accepted this document with the `DD-xx` and both ADR on 2026-10-22 (gate 0). |
| **Deferred** | Left to a named lot, which settles it before implementing the affected behavior. |

Changing an Accepted or Proposed rule later is allowed during the beta, but the
change updates this document and the affected contract tests in the same lot.

### 1.1 Decisions of the specification (S2)

| ID | Decision | Section |
| --- | --- | --- |
| DEC-01 | Autonomous command `tabalyst dedup` | 4, 13 |
| DEC-02 | Whole rows, no approximation | 3, 5 |
| DEC-03 | First occurrence kept, source order preserved | 6, 8 |
| DEC-04 | A source is never modified | 7, 11 |
| DEC-05 | `*.csv` and independent files | 7 |
| DEC-06 | CSV outputs only when relevant | 6 |
| DEC-07 to DEC-09 | Meaning of `unique`, `duplicates`, `duplicates_all` | 6 |
| DEC-10 | Zero, two or three CSV | 6.2 |
| DEC-11 | JSON report always, explicit messages | 12, 13 |
| DEC-12, DEC-13 | `SKIPPED` when current, reprocess when source or settings changed | 11 |
| DEC-14 | Derived CSV excluded from wildcard discovery | 7 |
| DEC-15 | 10,000,000 data records per file by default | 9 |
| DEC-16 | CLI and Python library over one engine | 4 |
| DEC-17 | Adaptable memory budget, exact disk storage when needed | 8, ADR store |
| DEC-18 | No HTML report in V1 | 3 |

### 1.2 Decisions of the plan (D1 to D18)

Accepted on 2026-10-22 (gate 0 of the plan). They are integrated in the sections
below and are not reopened here.

| ID | Topic | Section |
| --- | --- | --- |
| D1 | Format `tabalyst.dedup`, `format_version "0.2.0"`, `format_revision 1` | 12 |
| D2 | A failure replaces the previous report and deletes the managed outputs | 11.5, 12.4 |
| D3 | Place of `dedup.summary.json` | 13.1 |
| D4 | Touched file: same size and another `mtime_ns` reads the file, the SHA-256 decides | 11.2 |
| D5 | Package `tabalyst.dedup`, `dedup_service.py`, `cli/dedup.py` | 4 |
| D6 | Canonical identity; the store always compares the whole key | 5, 8 |
| D7 | `ExactRowStore`, memory then SQLite, automatic migration | 8, ADR store |
| D8 | Discovery above `batch.py`, zero files is an error, all excluded is a report | 7 |
| D9 | Meaning of `--force` | 7.4, 11.4 |
| D10 | Inventory `file`, `rows`, `size_bytes`, `sha256` per output | 11.3, 12 |
| D11 | Exit codes | 13.4 |
| D12 | Python API `dedup_csv`, `generate_dedups` | 4.3 |
| D13 | `dedup` block of the configuration | 10 |
| D14 | Writing conventions of the CSV | 6.4 |
| D15 | No confirmation in V1 | 8.5 |
| D16 | Shared CSV reading | 4.4, 9.1 |
| D17 | Measures | 12 |
| D18 | Heavy tests | 15 |

### 1.3 Decisions proposed by lot 0 (DD-xx)

They close the gaps that the specification and the plan leave. Each one is stated in
the section named and is listed again as an open point in section 17 when the
maintainer should look at it.

| ID | Decision | Section |
| --- | --- | --- |
| DD-01 | Canonical key: unsigned LEB128 for the count and every length, then UTF-8 | 5.2 |
| DD-02 | The store answers one question, `observe`; the counters follow from the count transitions | 8.1 |
| DD-03 | The budget counts accounted bytes in MiB, never the RSS | 8.3 |
| DD-04 | One public module reads CSV records for `sample` and Dedup | 4.4 |
| DD-05 | Four managed names per source; the stem of the source names them | 6.1 |
| DD-06 | A pattern that reaches the output directory through a wildcard in its directory part skips it | 7.2 |
| DD-07 | The Dedup reports, the batch report, Inspect files and lock files are never sources of a pattern | 7.2 |
| DD-08 | The foreign-output check covers the four managed names, before any work | 7.4 |
| DD-09 | A report with `status "in_progress"` is written before the first change to the outputs | 11.5, ADR ownership |
| DD-10 | A failed report is a best effort and never hides the primary error | 12.4 |
| DD-11 | `max_rows` is not a cache key; a report is reused when `records.total` fits the limit | 11.2 |
| DD-12 | Added invariants: `M`, `G3+` and the matrix of the outputs | 12.3 |
| DD-13 | The batch report is written unless the only input is one explicit file | 13.1 |
| DD-14 | A `SKIPPED` source never rewrites its report | 11.2 |
| DD-15 | `--force` with `--verify-content` is refused | 10 |
| DD-16 | Internal entry points `analyze_dedup`, `write_outputs`, `process_source` | 4.3 |
| DD-17 | The stable `reason` codes of a failure | 12.4 |
| DD-18 | Paths of the batch report are relative to its folder | 13.1 |

## 2. Principles

1. **Exact or failed.** A report with `status "complete"` is exact. Insufficient
   memory, disk or time never degrades into an approximate count: the run fails with
   a reason (S10.2, S20).
2. **The report is written last.** A CSV is never announced before it is published, and
   a `complete` report is the proof that the whole output set was published.
3. **A source is never modified or replaced**, whatever the options (DEC-04, S9.5).
4. **Smart by default, explicit when costly** (project rule). Dedup decides by
   deterministic budgets (accounted bytes, record counts), never by measured time.
   Time only feeds progress and warnings. Nothing long is silent: the step, the
   records read and the switch to disk are named in the progress and in the result.
5. **No cell content outside the CSV outputs.** Not in the report, the logs, the
   messages or the progress (S15.3).
6. **The engine knows nothing of presentation.** Analysis, outputs and reports are
   reusable without the CLI and without writing CSV (S14.4).

## 3. Scope

Included and excluded features are those of S3. In short: CSV with a header,
explicit files and non-recursive patterns, exact whole-row comparison, up to three CSV
outputs and one JSON report per source, one batch report, incremental reuse. Excluded
from V1: removal of lines in the source, fuzzy or key-based deduplication,
normalization, other formats than CSV, an HTML page (DEC-18), a `singletons.csv`,
parallel sources, and any change to `scan`, `report` and `sample` (E3: their own
exclusion of derived files is a follow-up of lot 11).

Compatibility notes carried by the contract:

- The Scan counts duplicates with a 128-bit digest and a lower bound past
  `limits.max_tracked_records`. Dedup is its exact complement. The two numbers agree
  under the Scan limit (compared in lot 10) and the documentation of Dedup says which
  to trust (lot 11).
- Dedup reads the source with its own pass. It never starts a Scan.

## 4. Package, modules and Python API

### 4.1 Modules (D5)

```text
src/tabalyst/
  csv_records.py          shared CSV reading and writing conventions (DD-04)
  dedup_service.py        boundary for the CLI and the API: plan, run, batch result
  dedup/
    identity.py           canonical key of a row (section 5)
    store.py              ExactRowStore protocol, Occurrence, MemoryRowStore
    diskstore.py          SqliteRowStore
    tiered.py             budget, automatic migration from memory to disk
    groups.py             GroupCounters, RecordMarks, count_rows, invariants of 12.3
    failures.py           DedupInputError, DedupReportError (they carry `reason`)
    analysis.py           first pass over a file: analyze_dedup
    writer.py             second pass: temporary CSV, write_outputs
    publish.py            publication, recovery, deletion of obsolete outputs
    cache.py              ownership of outputs, SKIPPED decision
    discovery.py          sources, exclusions, planned outputs, collisions
    settings.py           DedupSettings (options effective and validated)
    report.py             Pydantic models of the report and the batch report
    pipeline.py           process_source: one source from decision to report
  cli/dedup.py            thin adapter, progress and summary text
  schemas/tabalyst.dedup.schema.json
  schemas/tabalyst.dedup.batch.schema.json
```

No module under `tabalyst/dedup/` imports `tabalyst.cli`, prints, or reads the
terminal. Progress goes through the neutral events of `progress.py`. The names of
the specification (`DedupSourceDiscovery`, `DedupAnalyzer`, `DedupOutputPlanner`,
`DedupWriter`, `DedupReport`, `DedupBatchRunner`) are indicative; the modules above are
the alignment on the repository (S11.1).

### 4.2 Errors

Dedup uses the existing classes: `ConfigurationError` (invalid option or
configuration), `InputError` (a source problem, including the exceeded row limit) and
`ReportError` (an output or storage problem). The mapping of every situation of S15.2
to a status, a `reason` and an exit code is the table of section 14.

### 4.3 Python API and internal entry points (D12, DD-16)

Public, exported lazily in `tabalyst/__init__.py` (PEP 562) and listed in
`tests/test_public_api.py`, following `sample_csv` and `generate_samples`:

```python
tabalyst.dedup_csv(
    source, *, output_dir=None, max_rows=None, delimiter=None, encoding=None,
    config_path=None, memory_budget_mb=None, temp_dir=None, force=False,
    verify_content=False, on_progress=None,
) -> DedupResult

tabalyst.generate_dedups(
    input_specs, *, <the same options>,
) -> BatchDedupResult
```

- `dedup_csv` processes one explicit file. It returns a `DedupResult` with
  `status` (`DONE`, `SKIPPED`), the report, the paths of the published files and, for
  `SKIPPED`, the verification level. A failure raises the `TabalystError` of section
  14, after the failed report is written when it can be.
- `generate_dedups` plans and runs a batch. It returns a `BatchDedupResult` with
  `plan`, `results` (one entry per source, with its status, `DONE`, `SKIPPED`,
  `EXCLUDED` or `FAILED`), `failures` and the path of the batch report. A failure of
  one source does not raise; it is in `failures`. A batch-level refusal (collision,
  foreign output, invalid option) raises before any work.
- Neither function ever asks a question (project rule). The alias `dedup_files` of
  the specification is not exported (D12); adding it later is a one-line change.

Internal, not exported, and the entry points that the tests of lots 4 to 7 use before
the public API exists (lot 8):

```python
analyze_dedup(source, *, csv, max_rows, memory_budget_mb, temp_dir, on_progress=None,
               measure_memory=False) -> DedupAnalysis   # lot 4, writes nothing
write_outputs(source, analysis, *, csv, destination, on_progress=None)
    -> StagedOutputs                      # lot 5, temporary files, validated
process_source(source, settings, *, destination, on_progress=None)
    -> SourceOutcome                      # lots 5 to 7, grows lot by lot
```

Pure, in `tabalyst.dedup`, and the entry points of the tests of lots 2 and 3:

```python
identity.canonical_key(row: Sequence[str]) -> bytes                # lot 2
store.MemoryRowStore()                                              # lot 2
diskstore.SqliteRowStore(directory: Path, *, digest=None,
    cache_bytes=MIGRATION_CACHE_BYTES, reserve_bytes=0)            # lot 3
tiered.TieredRowStore(budget_bytes: int, temp_dir=None, *,
    on_spill=None, digest=None)                                     # lot 3
groups.count_rows(rows: Iterable[Sequence[str]], store=None, *, max_rows=None)
    -> GroupResult(stats: GroupStats, marks: RecordMarks)           # lot 2
discovery.plan_batch(input_specs, settings) -> BatchPlan            # lot 1
```

`count_rows` uses a `MemoryRowStore` (closed on return) when no store is given, leaves a
given store open, and raises `DedupInputError` with `reason "row_limit_exceeded"` at record
`max_rows + 1` when `max_rows` is passed. The marks it returns are trimmed to the records
read. The members `count` of `Occurrence` and the `reason` of the errors are those of
`dedup/store.py` and `dedup/failures.py` (written in lot 2, since the row limit needs them).
`SqliteRowStore` also offers `distinct`, `disk_bytes`, `load(entries)` (the bulk insert of the
migration) and `set_cache_bytes`; `TieredRowStore` takes the budget in bytes (the caller converts
`--memory-budget-mb` with `MIB`), exposes `storage_mode` (`"memory"` then `"disk"`) and calls
`on_spill(SpillEvent(records, distinct, accounted_bytes, budget_bytes))` once the copy to disk is
done; `analyze_dedup` (lot 4) turns it into the progress line. The small T21 and T22 run through
`analyze_dedup` (lot 3 ran them through `count_rows` over a `TieredRowStore`, before the first pass
existed).
`MemoryRowStore` also offers `accounted_bytes`, `__len__` and `items()` (every entry, for the
migration of lot 3), and refuses any use after `close()`. `GroupStats.violations()` lists
the invariants of 12.3 that do not hold and `GroupStats.check()` raises a `DedupReportError`
(`unexpected_error`) on any of them.
`GroupStats` has the members of `records` in section 12.2 (`total`, `distinct`,
`singletons`, `duplicate_groups`, `groups_occurring_twice`,
`groups_occurring_three_plus`, `extra_copies`, `duplicate_group_occurrences`,
`max_occurrences`). `BatchPlan` has `eligible` (`PlannedSource` tuple: `source`, and
`names`, a mapping of `unique`, `duplicates`, `duplicates_all` and `report` to
paths), `excluded` (tuple of `(path, reason)`), `batch_report` (the path of
`dedup.summary.json`, section 13.1) and `writes_batch_report` (DD-13).
`plan_batch(input_specs, settings, *, is_owned=...)` takes the ownership test of
section 7.4 as `is_owned(path, planned_source) -> bool`.

`DedupAnalysis` (`dedup/analysis.py`, frozen) holds the `GroupStats` of section 8.2 (`stats`),
the `RecordMarks` of section 8.4 (`marks`), the `SourceIdentity` of the pass (`source`:
`size_bytes`, `mtime_ns`, `content_sha256`), the `storage_mode`, `spilled_at_record` (`None` if the
store stayed in memory), `first_pass_seconds` and `memory_peak_bytes` (`None` unless
`measure_memory`, which traces the Python allocations with `tracemalloc` and therefore runs only for
`--verbose`; the page cache of SQLite is not traced, so the figure is a Python-side measure). Its
properties `outputs` (the files of section 6.2: `()`, `("unique", "duplicates")` or the three) and
`passes` (1 or 2) give the choice of the outputs; `planned_outputs(stats)` and
`expected_rows(stats, kind)` (`D`, `G` or `O`) are the same rules as functions. `analyze_dedup`
validates `max_rows` and `memory_budget_mb` (at least 1, `ConfigurationError`), is usable without
materializing any output (S14.4) and closes the store, deleting any temporary file, whatever
happens. Its failures are `DedupInputError` (`invalid_csv`, `encoding_error`, `source_unreadable`,
`row_limit_exceeded`, `source_changed`) and `DedupReportError` (the storage reasons of 8.5).
The progress events it emits (`on_progress`) carry `stage "Dedup"`, the phase `READING`, the bytes
read of the file and, once, the line "memory budget reached at record N, continuing on disk"
as `detail`; they carry no `index` or `total` (the position in a batch is the business of the
runner of lot 8, which sets them as it forwards the events) and never a cell. `process_source(...)` returns an outcome (status, reason, report,
files). An expected per-source failure (invalid CSV, row limit, storage, changed
source) is an outcome with status `FAILED`, not an exception; the service turns it
into the exception or the `failures` entry. A refusal that happens before any work
(invalid options, a foreign or colliding output, section 7.4) is raised. The pipeline
calls the second pass as `writer.write_outputs(...)`, through the module, so that a
test can intercept it between the passes (T23).

`writer.write_outputs(source, analysis, *, csv, destination, on_progress=None)` (lot 5) does
nothing when `analysis.outputs` is empty (`StagedOutputs` with no file, no second reading).
Otherwise it creates `destination` if needed, reads the source again and writes each
record to the outputs that the marks assign it (8.4), in source order, to temporary files
`.<final name>.<token>.tmp` in `destination` (the same volume as the final names, so that
the publication is an `os.replace`). It has no `temp_dir`: the staging is in the
destination, and the temporary folder of the store (`--temp-dir`) is closed and empty by
then. It returns `StagedOutputs` (`files`: a `StagedFile` per output with `kind`,
`temporary`, `final`, `rows`, `size_bytes` and `sha256`; `second_pass_seconds`; `discard()`).
Before it returns, it has checked in this order: size and `mtime_ns` of the source against
the first pass; at most `N` records; `N` records read; the bytes read equal to the size;
the SHA-256 equal to the first pass; size and `mtime_ns` unchanged at the end; then the
rows of each file against `D`, `G` and `O`. A difference of the source is `source_changed`
(a source that became malformed or undecodable is a changed source too; one that vanished
is `source_unreadable`); a row count that disagrees while the SHA-256 is equal is a defect
of the product, `unexpected_error`. A write error is `output_unwritable`, or
`insufficient_disk_space` for `ENOSPC`. The messages carry no path and no cell. On any
exception, `KeyboardInterrupt` included, the temporary files are deleted.
`writer.remove_stale_temporaries(source, destination)` deletes the `.<managed
name>.*.tmp` files of the four managed names of a source (11.5), and no other.

`publish.publish_csv(staged)` replaces the final names one by one with `os.replace`. If one
replacement fails, the files published by that call and the staged ones left are deleted
and `output_unwritable` is raised. This is only the CSV part of 11.5: the recovery report,
the deletion of the outputs of a previous run that the new set does not contain, and the
JSON report come with lots 6 and 7. Until then a rerun does not delete a stale
`duplicates_all` and a crash between two replacements can leave a partial set.

`pipeline.process_source(source, settings, *, destination, on_progress=None)` (lot 5) deletes
the stale temporaries of the source, runs `analyze_dedup`, `writer.write_outputs` and
`publish_csv` and returns a `SourceOutcome` (`source`, `status` `DONE` or `FAILED`,
`reason`, `files` published, `analysis`, `error`). `DedupInputError` and `DedupReportError`
become a `FAILED` outcome with their `reason`; any other exception becomes `FAILED` with
`unexpected_error` and a fixed message (its cause is chained, not printed, as it may hold a
cell). `verbose` turns on the memory measure. `SKIPPED`, the report and the ownership of the
names are added by lots 6 and 7.

### 4.4 Shared CSV reading and writing (D16, DD-04)

`tabalyst/csv_records.py` is extracted from `sampling.py` (`_open_reader`,
`_output_encoding`, the width check of `_scan`) with no change of behavior of
`sample`, which has non-regression tests (`tests/test_sampling.py`, written against the code
before the extraction) and the unit tests of `tests/test_csv_records.py`. It offers:

- `open_records(path, csv_config, *, hash_content=False, on_bytes=None)`: a context manager
  that opens the file as text (`newline=""`, the configured encoding), reads the header and
  gives a `CsvRecords`: `header`, the iteration of the data records through
  `csv.reader(strict=True)` (each of the width of the header), `records_read`, `line_num`. It
  raises `CsvRecordError` (an `InputError`, with a `kind` of `invalid_csv`, `encoding_error` or
  `source_unreadable` and the `records_read` accepted so far) for an empty file, an empty first
  record, a record whose width differs from the header, a `csv.Error`, a `UnicodeError` and an
  `OSError`. The messages give the record number and the physical line (`reader.line_num`),
  never a cell. A blank line is a record of width 0, hence a width error, as in `sample` and the
  Scan. A field larger than the `csv` module limit is a `csv.Error` and therefore an input
  error (raising the limit is out of scope). `analyze_dedup` maps the `kind` to the `reason` of
  its `DedupInputError`.
- The digest hook: with `hash_content` (or `on_bytes`, the progress in bytes) the byte stream is
  the `HashingStream` of the Scan reader, so `CsvRecords.content_digest()` gives the SHA-256 of
  the whole file, and `bytes_read` its size as read, without a second read (section 9.1). It
  reads what remains of the file, so a caller that stopped early still gets the digest of the
  whole file. Without either, the file is opened as `sample` always did.
- `output_encoding(source, encoding)`: BOM only if the source had one (D14), used by `sample`.
- `open_writer(path, csv_config, encoding)` (lot 5): a context manager that creates `path`
  (`FileExistsError` if it exists) and gives a `CsvWriter` with the conventions of section
  6.4: `write_header(row)`, `write_record(row)` (`rows_written` counts the data records),
  delimiter of the configuration, `\r\n`, minimal quoting. The bytes pass through a
  digesting sink, so `size_bytes` and `sha256` of the file come from the writing itself,
  with no re-read. A normal exit flushes and `fsync`s the file; an exception closes it as it
  is. `OSError` is not translated (the caller knows whether the file is temporary).

## 5. Row identity (S5)

### 5.1 Definition (FR-IDENT-01, FR-IDENT-03)

Two records are the same row if and only if they have the same number of cells and
the same cells, in the same order, as strings decoded from the CSV and before any
normalization (case, blanks, leading zeros, Unicode form, quoting, types). The header
is not part of any row. The identity is named `full_decoded_csv_row_v1` and is
recorded in the report (`settings.identity`); another definition is another name and a
cache miss (S9.2 point 3).

The order of the output rows follows the source. The first occurrence of a row is the
one kept. Nothing is sorted.

### 5.2 Canonical key (DD-01)

The key of a row is a `bytes` value, with no separator and no ambiguity:

```text
key = varint(number of cells) + for each cell: varint(byte length) + UTF-8 bytes
```

`varint` is the unsigned LEB128 (7 bits per byte, the high bit says that another byte
follows). The code is prefix-free, so the key decodes in only one way and two
different rows never share a key. UTF-8 encoding uses the strict error handler; text
decoded from a file always encodes.

Test vectors the lot 2 tests must reproduce:

| Row | Key (hexadecimal) |
| --- | --- |
| `("a", "b")` | `02 01 61 01 62` |
| `("a|b", "c")` | `02 03 61 7c 62 01 63` |
| `("a", "b|c")` | `02 01 61 03 62 7c 63` |
| `("",)` | `01 00` |
| `("", "")` | `02 00 00` |
| `("é",)` | `01 02 c3 a9` |
| a cell of 200 ASCII bytes alone | `01 c8 01` then the 200 bytes |

`("a|b", "c")` and `("a", "b|c")` differ; `("",)` and `("", "")` differ; `("é",)`
and the NFD form of the same letter differ (no normalization).

### 5.3 Collisions (FR-IDENT-02)

The store compares the whole key (a Python dictionary, or the primary key of a SQLite
table). A digest of the key is allowed as an accelerator only, and never decides
equality: two keys with the same digest are two entries. A realization that has an
accelerator exposes the digest function as a parameter so that test T20 can inject a
colliding one. The in-memory dictionary has no accelerator; its test injects a `bytes`
subclass with a constant `__hash__`.

## 6. Outputs (S6)

### 6.1 Names (DD-05)

For a source `<dir>/<stem>.<ext>` (`stem` is `Path.stem`), the managed names, in the
output directory (`-d`) or the source directory, are:

| Output | Name | Rows |
| --- | --- | --- |
| unique | `<stem>.unique.csv` | `D` |
| duplicates | `<stem>.duplicates.csv` | `G` |
| duplicates_all | `<stem>.duplicates_all.csv` | `O` |
| report | `<stem>.dedup.json` | one document |

Two sources whose stem is the same in one output directory (`data.csv` and `data.tsv`,
or two folders with `-d`) have the same four names: that is a collision, refused
before any work (section 7.4). The CSV are not three disjoint partitions:
`duplicates.csv` is logically part of `unique.csv` and of `duplicates_all.csv`.

### 6.2 What is written (S6.2, DEC-10)

| Condition | unique | duplicates | duplicates_all | report |
| --- | --- | --- | --- | --- |
| `G = 0` | no | no | no | yes |
| `G > 0` and `M = 2` | yes | yes | no | yes |
| `M >= 3` | yes | yes | yes | yes |

The criterion is the maximum frequency `M`, not the number of groups. With `G = 0`
the second pass is skipped altogether (section 8.4).

### 6.3 Content

Definitions and the worked example are those of S6.1 and S6.3 and are the executable
example of `tests/dedup/test_contract_reference.py`. The source of that example is
`id,name` followed by `101,Alice`, `102,Bob`, `101,Alice`, `103,Charlie`, `101,Alice`
and `102,Bob`: `N=6`, `D=3`, `G=2`, `E=3`, `O=5`, `S=1`, `G2=1`, `G3+=1`, `M=3`; unique
is rows 1, 2, 4; duplicates is rows 1 and 2; duplicates_all is rows 1, 2, 3, 5, 6 in
source order.

### 6.4 Writing conventions (D14)

As `sample`: the delimiter of the configuration, the encoding of the configuration with
the BOM written only if the source had one, the line terminator `\r\n`, minimal
quoting, `newline=""`. The header (the values of the first record) is written first
in every CSV, with the same order and number of columns, and no technical column is
added. Values are kept; the bytes of quoting and line endings of the source are not.
Writing is deterministic for one source and one configuration. A row with a single
empty cell is written `""` and reads back as that row. Each CSV is written to a
temporary file in the destination directory (`.<final name>.<token>.tmp`), flushed and
`fsync`ed, and published by `os.replace` only after the whole set is validated
(section 11).

### 6.5 No duplicate (S6.5)

With `G = 0` no CSV is written, the report is, and `outputs.csv_files_created` is 0.
A header-only file is valid: `N = 0`, no CSV, a complete report (`M = 0`).

## 7. Discovery and the plan of a batch (S7.3, S8, D8, D9)

### 7.1 Inputs

Inputs are explicit files and non-recursive patterns, expanded by Tabalyst
(`batch.resolve_input_specs` conventions: `**` refused as a `ConfigurationError`, an
explicit missing file is an `InputError`). Several specs may find one file; it is one
source (identity by `batch.path_key`). The set of sources is frozen before any work:
what the run publishes is never discovered by the same run.

### 7.2 Exclusions (S8.1, DD-06, DD-07)

A file found by a pattern is excluded, with a reason, in these cases:

| Reason | Rule |
| --- | --- |
| `derived_csv` | The name ends, case-insensitively, with `.sample.csv`, `.unique.csv`, `.duplicates.csv` or `.duplicates_all.csv` |
| `dedup_output` | The name ends with `.dedup.json` or is `dedup.summary.json` (DD-07) |
| `inspect_file`, `lock_file` | The existing rules of `batch.is_inspect_name` and `is_lock_name` |
| `output_directory` | The file is in the output directory and the pattern reached it through a wildcard in its directory part (DD-06) |

The last rule keeps `"*/*.csv" -d out` from reading the previous results of `out`.
A pattern whose directory part is literal (`"out/*.csv"`) names the folder on
purpose, so its files are not excluded for that reason. A file given by an explicit
path is never excluded, whatever its suffix (S8.1; T13), except that an Inspect file
stays refused as `batch.resolve_input_specs` does today. Excluded files are listed in
the result (reason and name) and are never an error (S8.1; T11, T12).

### 7.3 Nothing found, everything excluded (E2, D8)

- A pattern that matches no file at all is an `InputError` (exit code 4), as today.
- A pattern that matches only excluded files is not an error. If no source remains,
  the result is a report with `Eligible files: 0`, exit code 0.

### 7.4 Planned outputs and refusals

For every eligible source the plan lists the four managed names. The whole batch is
refused, before any work and before any write, when:

1. a managed name is the path of a source of the batch (even with `--force`);
2. two sources map to one managed name (compared with `batch.path_key`, so case and
   spelling do not hide a collision);
3. a managed name exists and is a directory;
4. a managed name exists, is not a source, and is **foreign** (DD-08), without
   `--force`.

`process_source` repeats the ownership check of its own four names before its first
write, so a library caller that skips `plan_batch` gets the same refusal.

The classes follow `batch.validate_outputs`: a managed name that is a source or a
directory is an `InputError` (exit code 4), two sources with one name or a foreign
existing file is a `ReportError` (exit code 1), as for `sample`.

A managed name is **owned** when the report beside it (`<stem>.dedup.json`, status
`complete` or `in_progress`) lists it in its inventory with the size of the file on
disk (section 11.3). Anything else that exists under a managed name is foreign,
including a file whose size changed by hand. The report is itself
owned only if it reads as a Dedup report of this format (a `failed` report is one);
a file of that name that does not is foreign. In lot 1 nothing can be owned yet:
`plan_batch` takes the ownership test as a parameter that defaults to "nothing is
owned", and lot 7 supplies the real one. Until then a folder that already holds the results of an
earlier run is refused without `--force`; the exclusion tests of lot 1 pass an ownership
test that owns everything, to test the exclusions alone. The check covers the four names, not
only the ones the run will write: what the run writes is known only after the first
pass, and the refusal must come before any work (D9). `--force` allows replacing a
foreign file the run writes and never deletes a foreign file it does not write. It
never allows replacing a source. A `dedup.summary.json` that is not a Tabalyst batch
report follows the same rule (section 13.1).

## 8. Analysis: the first and the second pass (S11.2, S11.3, S11.4)

### 8.1 The store (D6, D7, DD-02)

```python
class Occurrence(NamedTuple):
    count: int            # occurrences of the key so far, this one included
    first_position: int   # 0-based index of its first record

class ExactRowStore(Protocol):
    storage_mode: str                      # "memory" or "disk"
    def observe(self, key: bytes, position: int) -> Occurrence: ...
    def close(self) -> None: ...           # releases memory, deletes temporary files
```

`observe` inserts the key with count 1 and `first_position = position` when the key
is new, and increments its count otherwise. It is the only operation of the
first pass. The realizations are `MemoryRowStore`, `SqliteRowStore` and the
`TieredRowStore` that starts in memory and migrates to disk without losing a group
(ADR store). A store is exact by construction (section 5.3).

### 8.2 Counters

`GroupCounters` updates the quantities of the specification from the count
transitions reported by `observe`, so no pass over the store is needed at the end:

| Count after the record | Effect |
| --- | --- |
| 1 | `N += 1`, `D += 1` |
| 2 | `N += 1`, `E += 1`, `G += 1`, `G2 += 1`, mark the first position as the first of a repeated group |
| 3 | `N += 1`, `E += 1`, `G2 -= 1`, `G3+ += 1` |
| more than 3 | `N += 1`, `E += 1` |

In all cases `M = max(M, count)` and the extra-occurrence mark of the record is set when
the count is 2 or more. At the end: `S = D - G`, `O = G + E`. The invariants of the
specification (S4) and of section 12.3 are checked on every result, and a violation is
an internal error, never a published report.

### 8.3 Memory budget (DD-03)

`--memory-budget-mb` (default 512) is in MiB (1 MiB = 1,048,576 bytes) and bounds the
**accounted bytes** of the in-memory store: for each distinct row,
`len(key) + ENTRY_OVERHEAD`, where `ENTRY_OVERHEAD` is a constant calibrated against the
real cost of the dictionary: 160 bytes, measured in lot 2 (Python 3.12, `tracemalloc`, 1
million distinct rows of 2, 4 and 8 cells): the real cost beyond the key is 100 to 125
bytes per distinct row at the checkpoints of the dictionary growth (key object header,
slot, index table, packed count and position), so the accounted bytes stay above the real
ones (real over accounted from 0.67 to 0.84); the memory-to-disk transition of lot 3
can still lower the constant if its own measures say so. The accounting is deterministic: the
same file and the same budget choose the same storage mode on any machine. It is not a
bound of the process RSS (S10.2) and it does not include the two bit arrays of the
records, the CSV buffers or the interpreter. When the accounted bytes pass the budget,
the store migrates to disk (section 8.5). Minimum accepted value: 1.

### 8.4 First and second pass (S11.2, S11.3)

First pass, for each data record `i` (0-based): validate (section 9.1), check the row
limit (9.2), build the key, `observe`, update the counters, set the bits of
`RecordMarks`:

- `extra[i]`: the record is an extra copy (count 2 or more);
- `group_first[p]`: set when a count reaches 2, `p` being the first position of that
  key.

`RecordMarks` is two growable bit arrays (`bytearray`), about 2.5 MB for 10 million
records, read with `is_extra(i)` and `is_group_first(i)`. They fix the content of the outputs without the store: the second pass never
touches the store, which is closed (and its temporary files deleted) at the end of the
first pass.

Second pass, only if `G > 0`: read the source again with the same configuration and
write, for each record `i`:

```text
unique.csv          if not extra[i]
duplicates.csv      if group_first[i]
duplicates_all.csv  if (extra[i] or group_first[i]) and M >= 3
```

It checks that the records read equal `N`, that each output holds the expected number
of rows (`D`, `G`, `O`), and that the source is unchanged between the passes
(section 9.3). On any difference of the source it discards the temporary files and fails
with `source_changed`; a row count that disagrees although the SHA-256 is the same is an
internal error (`unexpected_error`). No inconsistent set is published.

With `G = 0` there is one pass (`passes = 1`) and no temporary CSV. Otherwise
`passes = 2`.

### 8.5 Disk fallback (D7, D15)

When the accounted bytes pass the budget, `TieredRowStore` copies the entries into a
temporary SQLite database under `--temp-dir` (default: the system temporary folder), in a
private subfolder (`tabalyst-dedup-*`, deleted by `close()`, by garbage collection and at
exit). The migration is named in the progress ("memory budget reached at record N,
continuing on disk", from the `SpillEvent`) and recorded as `run.storage_mode: "disk"`.

- **Table.** `rows(key BLOB PRIMARY KEY, count, first) WITHOUT ROWID`, page size 16 KiB,
  no journal, no sync, exclusive lock, one transaction per `COMMIT_INTERVAL` (100,000)
  operations. One upsert per record returns the new count and the first position
  (`RETURNING`; two statements with a SQLite older than 3.35).
- **Migration.** The entries go in key order (`MemoryRowStore.sorted_items`): inserted at
  random they cost three times more once the table outgrows its cache (3 million random
  keys: 28 s, 8.6 s sorted). The page cache is 16 MiB during the copy, then the whole
  `--memory-budget-mb` once the dictionary is dropped, so the budget bounds the
  accounted memory in both modes.
- **Space.** Before the copy, the free space of the temporary volume
  (`shutil.disk_usage`) must be at least `MIN_FREE_BYTES` (64 MiB) plus
  `estimate_disk_bytes` of the entries already held (`(key bytes + 24 per entry) * 1.25`);
  after every commit it must cover the same minimum plus the growth of the last interval.
  The estimate is a floor, not a forecast of the final size, which only the rest of the
  file tells. An `OSError` (`ENOSPC`), an `sqlite3.OperationalError` ("database or disk is
  full"), a refused estimate or a temporary folder that is missing or is a file fail the
  source with `insufficient_disk_space` or `storage_unavailable`, delete the temporary
  files and publish nothing. The messages carry no path.
- **Interruption.** An exception or Ctrl-C during the copy closes the database and
  deletes its folder before it propagates.
- **No digest by default.** The optional digest accelerator (`digest=`) is exact but
  measured slower and larger (5 million rows: 8.4 against 5.3 microseconds per row, 82
  against 74 bytes per distinct row), so it is off.

There is no confirmation prompt and no `--yes` in V1 (D15): Dedup is the last step of
its command and the progress and the summary tell what it did. The decisions are in the
[store ADR](../adr/2026-10-22-dedup-exact-store-and-disk-fallback.md).

Measures of lot 3 (Windows 11, Python 3.12, 31 GB of memory, SSD, narrow rows of 4 cells
of about 60 bytes of key, default budget 512 MiB, store and key encoding only, no CSV
reading; script `tabalyst-lab/benchmarks/dedup_store.py`):

| Rows | Extra copies | Distinct | Mode | Store time | Per row | Peak working set | Database |
| ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| 1 M | 0, 25, 90 % | 1 M, 750 k, 100 k | memory | 1.3 to 1.6 s | 1.3 to 1.6 us | 41 to 183 MiB | |
| 5 M | 0 % | 5 M | disk | 25 s | 4.9 us | 451 MiB | 360 MiB |
| 5 M | 25 % | 3.75 M | disk | 26 s | 5.3 us | 468 MiB | 266 MiB |
| 5 M | 90 % | 500 k | memory | 12 s | 2.5 us | 113 MiB | |
| 10 M | 0 % | 10 M | disk | 52 s | 5.2 us | 547 MiB | 728 MiB |
| 10 M | 25 % | 7.5 M | disk | 43 to 71 s | 4.3 to 7.2 us | 556 MiB | 541 MiB |
| 10 M | 90 % | 1 M | memory | 15 s | 1.5 us | 204 MiB | |
| 10 M | 0 %, keys in random order | 10 M | disk | 126 s | 12.6 us | 547 MiB | 801 MiB |
| 10 M | 25 %, keys in random order | 7.5 M | disk | 97 s | 9.7 us | 553 MiB | 604 MiB |

The same 10 million rows with 25 % copies in memory only (budget 100 GB) take 15 s and
peak at 1.4 GiB, so the budget is what keeps the default under 600 MiB. Twenty-cell rows
(1 M distinct) stay in memory at 415 MiB. The database holds 66 to 82 bytes per distinct
narrow row. Timings vary by about 40 % between identical runs on this machine (the
10 M, 25 % case took 43, 62, 71 and 69 s). The switch happens at 2.5 to 3.3 million
distinct narrow rows and the copy takes 3 to 5 s.

## 9. Reading, limits and measures

### 9.1 Reading (S15.1, D16)

The reading rules are those of section 4.4. A header-only file is valid. The
SHA-256 of the file is computed from the bytes read in the first pass (lot 4) and again in the
second pass (lot 5); the number of records is counted, not the physical lines (a multiline
cell is one record). The first pass finishes the reading of the file (`content_digest`) before it
compares the identity.

### 9.2 Row limit (S10.1, DEC-15)

`max_rows` defaults to 10,000,000 data records and must be at least 1. Exactly
`max_rows` records are allowed. At the record number `max_rows + 1` the pass stops
with the reason `row_limit_exceeded`, no CSV is published, and the failed report
carries the limit and `records_read = max_rows + 1`, marked partial and not certified
(section 12.4). The exceeded limit is an `InputError` of this file; the other files
of the batch go on.

### 9.3 Stability of the source

At the start and at the end of each pass the size and `mtime_ns` of the source are
read, and the bytes read are compared with the size; with the SHA-256 of the two passes, a
difference fails the source with `source_changed`. The first pass makes its own check (lot 4):
a source that grew, shrank or was touched while it was read fails there, before any second
pass. A source that is shorter, longer or different between the two reads therefore never
produces a published set (T23).

### 9.4 Measures (D17)

Durations come from `time.perf_counter` per step (first pass, second pass, total).
`run.memory_peak_bytes` is the `tracemalloc` peak, only when `--verbose` enabled the
tracing, else `null`. The RSS is not measured in V1. A measure that is not available is
`null`, never invented.

## 10. Configuration and options (D13, S7.2, S14.2)

`DedupSettings` is the effective, validated set of options of one run (a frozen
dataclass in `dedup/settings.py` that raises `ConfigurationError` on construction):
`csv` (`CsvConfig`), `max_rows`, `memory_budget_mb`, `temp_dir`, `output_dir`,
`force`, `verify_content`, `quiet` and `verbose` (`verbose` also switches on the
memory measure of section 9.4; `quiet` is kept here only so that the exclusion with
`verbose` is checked once, with the other rules). `resolve_dedup_settings(config_path,
**options)` builds it. Precedence: command line, then configuration, then default.

The `dedup` block of `SettingsFile` (`extra="forbid"`, rejected unknown keys, no change
for the other blocks):

```json
{"dedup": {"max_rows": 10000000, "memory_budget_mb": 512, "verify_content_on_skip": false}}
```

`--verify-content` or `verify_content_on_skip: true` select the digest verification
of a reused source (section 11.2). The command line cannot turn a configured `true`
off. A forced run does not take `verify_content_on_skip` from the configuration (it
reprocesses, so there is nothing to verify); only the explicit `--verify-content`
with `--force` is refused. The options of S7.2 are those of the specification. Rules that follow the
project rule "no option is silently ignored":

- `--quiet` with `--verbose` is a `ConfigurationError`.
- `--force` with `--verify-content` is a `ConfigurationError`: a forced run always
  reprocesses, so the verification has nothing to decide (DD-15).
- `--max-rows` and `--memory-budget-mb` must be integers of at least 1 (also in
  the configuration); `--delimiter` is one character; `--temp-dir` must not be a
  file, and must be a usable directory when the store needs it (section 8.5).
- `-o` does not exist in V1 (S7.2).

## 11. Incremental processing, ownership and publication (S9, S11.5)

### 11.1 Unit of work

Each source is decided and processed alone. The steps of one source are: the decision
(11.2), the first pass (8.4), the second pass if needed, the staging of the files, the
publication (11.5) and the report.

### 11.2 `SKIPPED` (S9.2, S9.3, D4, DD-11, DD-14)

A source is `SKIPPED` when all the conditions hold, evaluated in this order and
stopping at the first failure (the source is then reprocessed):

1. `<stem>.dedup.json` exists and is a readable document of the format `tabalyst.dedup`.
2. Its `status` is `complete`.
3. Its `format_version`, `format_revision`, `settings.identity`, `settings.delimiter` and
   `settings.encoding` equal the requested ones, and `records.total <= max_rows`.
   `max_rows` is not otherwise a key: raising it keeps a result valid, lowering it
   below the recorded total reprocesses and fails with `row_limit_exceeded` (DD-11).
4. The source identity (D4): the name is the same; the sizes are equal (else
   reprocess without reading); if `mtime_ns` is equal the verification level is
   `metadata`, otherwise the file is read and its SHA-256 must equal the recorded one
   (level `digest`). `--verify-content` always reads and compares the digest.
5. The expected outputs (derived from `records` by the matrix of section 6.2) are
   exactly the inventory, and each one exists.
6. Each inventoried output has the recorded size; with the digest verification its
   SHA-256 equals the recorded one too.
7. No managed name outside the inventory exists (it would be foreign, section 7.4).

The level (`metadata` or `digest`) is in the result and the CLI summary. A source with
no duplicate has no CSV: its report alone proves the processing (S9.2). The existing
report is not rewritten by a `SKIPPED` decision (DD-14). Consequence, accepted: a
source copied with a new `mtime_ns` is read and hashed at every run until it is
reprocessed. The reuse statistics of the batch report come from the existing report.

### 11.3 Inventory and ownership (D10)

Each published output is recorded in the report as `file`, `rows`, `size_bytes` and
`sha256` (computed while writing, with no re-reading). Ownership and the recovery
rule are in the [ownership ADR](../adr/2026-10-22-dedup-output-ownership-and-recovery.md).

### 11.4 `--force` (D9, S9.5)

`--force` skips the `SKIPPED` decision, reprocesses and republishes the complete set,
and allows replacing a foreign output of the four names that the run writes. It never
replaces a source (even another input of the batch), deletes a foreign file or
changes the meaning of the verification options.

### 11.5 Publication and failure (DD-09, D2)

Success, in this order, for one source:

1. The staged files are complete and validated (rows, sizes, digests).
2. The report `<stem>.dedup.json` is replaced, atomically, by the **recovery report**
   (`status "in_progress"`, the previous inventory and the planned one). This is the
   write-ahead record that keeps the owned names provable if the run is interrupted.
3. The staged CSV are published with `os.replace`, one by one.
4. The owned outputs of the previous run that are not in the new set are deleted.
5. The final `complete` report replaces the recovery report, atomically.

Failure after the staging started, or after a previous report exists (D2): the same
protocol runs with an empty planned set (the recovery report, deletion of the owned
outputs, then a `failed` report). A source that fails before any previous report or
output exists writes its failed report only. A pre-flight refusal (section 7.4,
configuration) writes nothing at all. An interruption (Ctrl-C) before the recovery
report leaves the previous result untouched; after it, the next run recovers. The next
run deletes the stale `.<managed name>.*.tmp` files of its source, and only those.

No lock file in V1: two simultaneous runs on the same outputs are not protected
(section 17).

## 12. JSON report of a source (S12, D1, D10, D17)

### 12.1 Format

`format "tabalyst.dedup"`, `format_version "0.2.0"`, `format_revision 1` (D1). The
Pydantic models of `report.py` are the source of truth; the JSON Schema
`schemas/tabalyst.dedup.schema.json` is generated from them and compared by a
consistency test, like the other schemas. A change of structure or meaning raises the
revision and is written in `docs/dev/dedup/format-changelog.md` (lot 6); its public
counterpart `docs/en/dedup/format-changelog.md` comes with the public documentation (lot 11). The
report contains no cell content and no absolute path (S15.3).

The module `dedup/report.py` (lot 6) holds the models (`CompleteReport`, `FailedReport`, and the
blocks `SourceIdentity`, `FailedSource`, `ReportSettings`, `Records`, `Outputs`, `OutputFile`,
`Run`, `Failure`, `Partial`), the invariants of 12.3 (`broken_invariants`, run by a validator of
`CompleteReport`, so a model cannot hold a report that breaks one), the builders
(`complete_report` from the analysis and the staged files, `failed_report` from the error),
`report_json`/`write_report` (atomic, through `batch.write_text_atomic`), the reading API
(`parse_report(document)` and `read_report(path)`, which raise `DedupDocumentError`, an
`InputError` whose message names the member and the rule and never a value of the file) and
`dedup_schema()`/`dedup_schema_text()`. The schema is one document with two variants told apart
by the constant `status`; it refuses unknown members and any other `format_revision`. The
`in_progress` variant (12.5) is not parsed yet: it comes with lot 7.

The inventory of D10 is the `outputs` block: for each CSV the name, the rows, the size and the
SHA-256 of what was published, taken from the staged file, not re-read. `process_source`
publishes the CSV, then the report, last. If the report cannot be written, the CSV just
published are deleted (without the report they would be unowned) and the source fails with
`output_unwritable`. A failed source gets a failed report on a best-effort basis; the primary
failure stays the outcome whatever happens to it. `partial.records_read` is `null` when the
failure did not know it (an unreadable source). Until lot 7, a failed report replaces an
earlier report but not the earlier CSV, which stay in place.

### 12.2 Complete report

```json
{
  "format": "tabalyst.dedup",
  "format_version": "0.2.0",
  "format_revision": 1,
  "generator": {"name": "tabalyst", "version": "0.7.0"},
  "status": "complete",
  "source": {
    "name": "customers.csv",
    "size_bytes": 12345678,
    "mtime_ns": 1792700000000000000,
    "content_sha256": "ece53017..."
  },
  "settings": {
    "max_rows": 10000000,
    "delimiter": ",",
    "encoding": "utf-8-sig",
    "identity": "full_decoded_csv_row_v1"
  },
  "records": {
    "total": 100000, "distinct": 99850, "singletons": 99770,
    "duplicate_groups": 80, "groups_occurring_twice": 60,
    "groups_occurring_three_plus": 20, "extra_copies": 150,
    "duplicate_group_occurrences": 230, "max_occurrences": 8,
    "extra_copy_percent": 0.15
  },
  "outputs": {
    "csv_files_created": 3,
    "unique": {"file": "customers.unique.csv", "rows": 99850,
               "size_bytes": 11950231, "sha256": "9a01c4e2..."},
    "duplicates": {"file": "customers.duplicates.csv", "rows": 80,
                   "size_bytes": 9871, "sha256": "41bd07aa..."},
    "duplicates_all": {"file": "customers.duplicates_all.csv", "rows": 230,
                       "size_bytes": 28114, "sha256": "c7e55b19..."}
  },
  "run": {
    "passes": 2, "storage_mode": "disk",
    "duration_seconds": 12.4, "first_pass_seconds": 7.1, "second_pass_seconds": 5.2,
    "memory_peak_bytes": null
  }
}
```

The hashes shown are abbreviations. A real report holds the 64 hexadecimal
characters. `extra_copy_percent` is `100 * extra_copies / total` and `0` when `total` is
0. `storage_mode` is `memory` or `disk` (a migrated run is `disk`).

Variants:

- **No duplicate**: `csv_files_created 0`, `unique`, `duplicates`, `duplicates_all`
  all `null`, `passes 1`, `second_pass_seconds null`.
- **Groups of two only**: `csv_files_created 2`, `duplicates_all null`.
- **Header only**: every count `0`, `max_occurrences 0`, `extra_copy_percent 0`.
- **Failed**: section 12.4.
- **In progress** (recovery report): section 12.5.

### 12.3 Invariants

The schema checks the structure and the business validation checks all of:

```text
total = distinct + extra_copies
distinct = singletons + duplicate_groups
duplicate_group_occurrences = duplicate_groups + extra_copies
duplicate_groups = groups_occurring_twice + groups_occurring_three_plus
0 <= singletons <= distinct <= total
outputs.unique.rows = distinct                            (if present)
outputs.duplicates.rows = duplicate_groups                (if present)
outputs.duplicates_all.rows = duplicate_group_occurrences (if present)
```

Added by lot 0 (DD-12):

```text
max_occurrences = 0 if total = 0, else >= 1
duplicate_groups = 0           <=> max_occurrences <= 1
groups_occurring_three_plus > 0 <=> max_occurrences >= 3
outputs present <=> section 6.2 (unique and duplicates iff duplicate_groups > 0,
                    duplicates_all iff max_occurrences >= 3)
csv_files_created = number of non-null outputs
passes = 1 iff duplicate_groups = 0
```

The reading API of lot 6 validates these on a document read from disk. A document that
breaks one is not `complete`: the cache treats it as unreadable.

### 12.4 Failed report (D2, DD-10, DD-17)

```json
{
  "format": "tabalyst.dedup", "format_version": "0.2.0", "format_revision": 1,
  "generator": {"name": "tabalyst", "version": "0.7.0"},
  "status": "failed",
  "source": {"name": "customers.csv"},
  "settings": {"max_rows": 10000000, "delimiter": ",", "encoding": "utf-8-sig",
               "identity": "full_decoded_csv_row_v1"},
  "failure": {"reason": "row_limit_exceeded", "message": "...", "limit": 10000000},
  "partial": {"records_read": 10000001, "certified": false}
}
```

The exceptions raised by the Dedup modules are `DedupInputError` (an `InputError`) and
`DedupReportError` (a `ReportError`), which carry the `reason` code and the number of
records read when it is known; the class decides the exit code (section 13.4).

A failed report has no `records`, no `outputs` and announces no CSV. `source`
carries the size and `mtime_ns` when they could be read. Writing it is a best effort:
if it cannot be written, the primary error is raised unchanged and the secondary one is
only in the diagnostics. It is not written for a pre-flight refusal.

The stable `reason` codes:

| `reason` | Situation | Class | Exit |
| --- | --- | --- | --- |
| `row_limit_exceeded` | more than `max_rows` records | `InputError` | 4 |
| `invalid_csv` | empty file, bad width, `csv.Error` | `InputError` | 4 |
| `encoding_error` | the file cannot be decoded | `InputError` | 4 |
| `source_unreadable` | the source cannot be opened or read | `InputError` | 4 |
| `source_changed` | size, `mtime_ns` or digest differ between the passes | `InputError` | 4 |
| `insufficient_disk_space` | memory spilled and the disk has no room | `ReportError` | 1 |
| `storage_unavailable` | the temporary folder or the database is unusable | `ReportError` | 1 |
| `output_unwritable` | an output or the report cannot be written | `ReportError` | 1 |
| `unexpected_error` | any other failure | `ReportError` | 1 |

### 12.5 Recovery report

`status "in_progress"`, the format members, the `source` name, the `settings`, and
`recovery: {"previous_outputs": [...], "planned_outputs": [...]}` where each item has
`file`, `size_bytes`, `sha256`. It never counts as a processing: the cache never
reuses it (S15.2: "an incomplete JSON is reprocessed"). Its role is described in the
ownership ADR.

## 13. Batch report and command output (S13)

### 13.1 Batch report (D3, DD-13, DD-18)

`dedup.summary.json` is written unless the invocation is one explicit file only
(DD-13: any pattern, or two or more inputs, writes it, even if nothing is eligible).
Place (D3): the output directory with `-d`; otherwise beside the sources if they all
share one folder; otherwise the current directory. It is overwritten by each batch
and has `format "tabalyst.dedup.batch"`, the same version and revision family
(`0.2.0`, revision 1) and its own schema. An existing file of that name that is not a
Tabalyst batch report is replaced only with `--force`.

Content: the specs and the destination; the counters (`found`, `eligible`,
`excluded`, `done`, `skipped`, `failed`); for each source its name, status, reason,
verification level, path of its report and its main counts; the counters of the
sources `done` and the ones `reused` from a valid report kept apart so that nothing is
counted twice; the number of CSV files created by the current run only; the total
duration; diagnostics. The excluded files are listed with their reason and have no
report of their own. Paths are relative to the folder of the batch report with `/`
separators, and absent (name only) when no relative path exists (another drive).

### 13.2 Command output (D11, S13.2, S13.3)

Progress and diagnostics go to `stderr`; the result is on `stdout` and readable
without a TTY. The two validated shapes are the contract of lot 9:

```text
Tabalyst Dedup
---------------------------------------------------------------
File              Status    Rows       Extra copies  Outputs
---------------------------------------------------------------
customers.csv     SKIPPED   100,000    0             0 new
products.csv      SKIPPED    45,000    120           0 new
orders.csv        DONE      250,000    1,250         3
---------------------------------------------------------------
Eligible files:       3
Processed:            1
Already processed:    2
Failed:               0
New CSV files:        3
JSON reports:         3 available (1 updated)
Batch report:         dedup.summary.json
Result:               COMPLETE
```

(The specification shows `0` for the first skipped file and `0 new` for the second; the
contract is `0 new` for every `SKIPPED` source, `n` for a `DONE` one, so that zero
CSV never reads as zero duplication.)

```text
Tabalyst Dedup
---------------------------------------------------------------
File:         customers.csv
Source rows:  100,000
Distinct:     100,000
Groups:       0
Extra copies: 0

No duplicate records found.
No CSV files generated.
Report: customers.dedup.json
Status: COMPLETE
```

A `SKIPPED` source states its reason and verification level (`already processed,
verified by metadata`). `--verbose` adds the measures and the storage mode.
`--quiet` reduces the messages that are not essential; `--no-progress` hides the
progress indicator. No message contains a cell.

### 13.3 Statuses

`DONE`, `SKIPPED`, `EXCLUDED`, `FAILED`. Skipped and excluded files are never an
error and never change the exit code.

### 13.4 Exit codes (D11)

| Code | Situation |
| --- | --- |
| 0 | Nothing failed (`SKIPPED` and `EXCLUDED` do not count) |
| 1 | At least one failure that is not an input error |
| 2 | Invalid option or configuration |
| 3 | Not used (Dedup asks no confirmation) |
| 4 | A source explicitly missing, or every failure of the batch is an `InputError` (as `sample`), the exceeded row limit included |

## 14. Errors and situations (S15.2)

| Situation | Status | `reason` | Written | Exit |
| --- | --- | --- | --- | --- |
| Current file already processed | `SKIPPED` | `already_processed` | nothing | 0 |
| Derived file found by a pattern | `EXCLUDED` | its exclusion reason | nothing | 0 |
| No duplicate | `DONE` | | report only | 0 |
| More than `max_rows` | `FAILED` | `row_limit_exceeded` | failed report | 4 |
| Malformed CSV, bad header | `FAILED` | `invalid_csv`, `encoding_error` | failed report | 4 |
| No disk space for the temporary store | `FAILED` | `insufficient_disk_space` | failed report, cleanup | 1 |
| Temporary storage unavailable | `FAILED` | `storage_unavailable` | failed report | 1 |
| Source changed between the passes | `FAILED` | `source_changed` | failed report | 4 |
| Output collides with a source | refused | | nothing | 4 |
| Two sources with one managed name | refused | | nothing | 1 |
| Foreign output without `--force` | refused | | nothing | 1 |
| Existing report incomplete | reprocessed | | normal | |
| One source fails among several | the others go on | | | 4 or 1 |
| Invalid option | refused | | nothing | 2 |

Pre-flight refusals (collision, foreign output) raise before the first source is read.

## 15. Tests (S16, D18)

The contract tests T01 to T30 are in `tests/dedup/`, one file per theme, skipped until
their lot is enabled in `tests/dedup/conftest.py` (`ENABLED_LOTS`, one lot per line so
that parallel lots do not conflict). Each carries `@pytest.mark.dedup_lot("<n>")` for
the lot that provides the behavior and `@pytest.mark.dedup_t("Txx", ...)` for the
requirement. Tests marked `dedup_heavy` (large scale) never run by default; they run
with `-m dedup_heavy` and write their data under the external artifact root (never in
the checkout). `test_contract_reference.py` and `test_contract_inventory.py` are not
skipped: they prove the worked example of the specification with a reference
implementation, and that T01 to T30 and the lots of this document are all covered.

| Test | Scenario | Lot | File | Heavy |
| --- | --- | --- | --- | --- |
| T01 | 100 distinct rows | 4 counts, 5 outputs, 6 report | `test_contract_groups.py` | no |
| T02 | Header only | 4, 5, 6 | `test_contract_groups.py` | no |
| T03 | Group `A,A` | 4, 5, 6 | `test_contract_groups.py` | no |
| T04 | Groups `A,A` and `B,B` | 4, 5, 6 | `test_contract_groups.py` | no |
| T05 | Group `A,A,A` | 4, 5, 6 | `test_contract_groups.py` | no |
| T06 | `A,A,A`, `B,B`, `C` | 4, 5, 6 | `test_contract_groups.py` | no |
| T07 | One million rows, 275,000 copies | 4 (small), 10 (full) | `test_contract_scale.py` | full only |
| T08 | 10,000,000 rows | 10 | `test_contract_scale.py` | yes |
| T09 | 10,000,001 rows | 4 (small), 10 (full) | `test_contract_scale.py` | full only |
| T10 | Three files, two already valid | 8 | `test_contract_cache.py` | no |
| T11 | `*.csv` beside the outputs | 1 | `test_contract_discovery.py` | no |
| T12 | `customers.sample.csv` in a pattern | 1 | `test_contract_discovery.py` | no |
| T13 | `customers.unique.csv` named explicitly | 1 | `test_contract_discovery.py` | no |
| T14 | Source modified after a success | 7 | `test_contract_cache.py` | no |
| T15 | CSV settings changed | 7 | `test_contract_cache.py` | no |
| T16 | Report present, expected CSV deleted | 7 | `test_contract_cache.py` | no |
| T17 | Source without duplicate processed twice | 6, 7 | `test_contract_cache.py` | no |
| T18 | Commas, quotes, multiline cells | 2 | `test_contract_identity.py` | no |
| T19 | Blanks, case, leading zeros differ | 2 | `test_contract_identity.py` | no |
| T20 | Injected digest collisions | 2 | `test_contract_identity.py` | no |
| T21 | Memory too small, disk available | 3 (small), 10 | `test_contract_scale.py` | full only |
| T22 | Temporary storage unavailable | 3 | `test_contract_scale.py` | no |
| T23 | Source changed between the passes | 5 | `test_contract_integrity.py` | no |
| T24 | Two patterns, one source | 1 | `test_contract_discovery.py` | no |
| T25 | Invalid header, irregular rows | 4 | `test_contract_integrity.py` | no |
| T26 | Output colliding with a source | 1 | `test_contract_discovery.py` | no |
| T27 | Run after an interruption | 7 | `test_contract_cache.py` | no |
| T28 | Windows paths with spaces, quoted pattern | 1 (discovery), 9 (command) | `test_contract_discovery.py` | no |
| T29 | `--force` | 7 | `test_contract_cache.py` | no |
| T30 | `--verify-content` finds a hidden rewrite | 7 | `test_contract_cache.py` | no |

Every result `complete` is checked, by the helpers, against the invariants of
section 12.3, against the reference `Counter(tuple(row) for row in csv)` on small
inputs, and for the ordered content of each CSV and its re-reading with the same
dialect, plus the absence of any provisional data file after a failure (S16.2).

## 16. Glossary

The terms below are the vocabulary of the code, the messages and (from lot 11) the
public glossary. The French equivalents are for that later page.

| Term | French | Meaning |
| --- | --- | --- |
| record, data record | enregistrement | One CSV record after the header; a multiline cell stays in one record |
| row identity | identité de ligne | The tuple of decoded cells of a record, compared without normalization |
| canonical key | clé canonique | The unambiguous bytes of a row identity (section 5.2) |
| distinct row | ligne distincte | One row identity; counted once by `D` |
| duplicate group | groupe de doublons | All the occurrences of one row that occurs at least twice; counted by `G` |
| repeated row | ligne répétée | The row of a duplicate group, as written once to `duplicates.csv` |
| extra copy | occurrence supplémentaire | An occurrence after the first of its row; counted by `E` |
| first occurrence | première occurrence | The first record of a row in source order; the one kept |
| singleton | ligne unique | A row that occurs exactly once; counted by `S` |
| maximum frequency | fréquence maximale | `M`, the largest number of occurrences of one row |
| group occurrences | occurrences des groupes | `O`, every occurrence of the rows of the duplicate groups, firsts included |
| managed output | sortie gérée | A file that a Dedup report proves it published (owned) |
| foreign output | sortie étrangère | A file under a managed name that no report proves it published |
| recovery report | rapport de reprise | The `in_progress` report written before the first change to the outputs |
| verification level | niveau de vérification | `metadata` (size and `mtime_ns`) or `digest` (SHA-256), shown with a `SKIPPED` source |
| storage mode | mode de stockage | `memory` or `disk`, how the first pass kept the rows |
| spill | repli sur disque | The automatic switch from memory to disk storage |

## 17. Open points

To read with this document; none blocks lot 1 or lot 2.

1. **Two simultaneous runs** on the same outputs: no lock in V1 (plan, open point).
   To document, to reopen if a lock file is wanted.
2. **A stray file under a managed name** that the run does not write (for example a
   hand-made `x.duplicates_all.csv` when `M = 2`) is foreign, and keeps refusing the
   source without `--force` (DD-08). The alternative, checking only the names the run
   writes, would refuse after a long first pass.
3. **Copied source** (same content, new `mtime_ns`): read and hashed at every run
   because a `SKIPPED` decision never rewrites the report (DD-14). Updating the
   `mtime_ns` of the report would remove the cost at the price of a write.
4. **`ENTRY_OVERHEAD`** is measured by lot 2 (160, section 8.3); the spill estimate
   (24 bytes and a 1.25 factor) and the SQLite settings are those measured in lot 3
   (section 8.5). Gate 3 reads those numbers; the budgets of the whole command are fixed at gate 10.
5. **Alias `dedup_files`**: not exported (D12).
6. **Batch report of zero or one source**: written whenever a pattern or two inputs are
   given (DD-13); lot 8 confirms that a folder with only derived files should get one.
7. **Foreign `dedup.summary.json`**: recognized by `format "tabalyst.dedup.batch"`
   (lot 8 confirms).
8. **Numbers of the budgets** (time, memory, disk) are fixed from the measures at gates
   3 and 10, not before (S16.3).

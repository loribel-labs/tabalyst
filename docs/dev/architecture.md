# Architecture

Iteration 1 implements `CSV -> report.json -> report.html` with a single global
JSON file. Its column summaries stay inside that file. The format is experimental;
breaking changes are expected while iterating.

Report profiles use `format_version: "0.2.0"` and start at
`format_revision: 1`. The integer revision increases for each meaningful
structural or semantic change. See the
[JSON profile changelog](../en/report/profile-changelog.md).

## Boundaries

- `report_profile.py`: builds the report profile from a `ScanResult`, fresh
  or read back from a scan document; record-level facts (preview, duplicate,
  empty and incomplete records) come from the `records` block of each scan
  dataset. No file access.
- `report_config.py`: `ReportConfig`, the effective report settings: the
  top-level presentation settings and the `scan` configuration.
- `models.py`: Pydantic models of the report profile (format 0.2.0, revision 1: one
  profile per dataset in `datasets`, with its limits and, for JSON, its
  structure; column scan evidence is retained for standalone detail pages).
- `config.py`: validated settings, loaded from optional JSON configuration files.
  `load_config_layers()` validates every file completely (top-level settings and
  the `scan` section), rejects the settings moved to `scan` with their new
  location, and merges files in order; each command resolves its own settings
  from the merged layers.
- `service.py`: public `analyze(...)` orchestration plus the reusable
  `analyze_csv(path, config)` boundary, which scans the source and builds its
  profile, and `analyze_scan(path)`, which builds it from a scan document.
  Output replacement is an explicit service-level choice rather than a
  CLI-only safeguard.
- `scan_reuse.py`: reads scan documents for `tabalyst report --scan` and
  applies the staleness rule (design O12): source size and SHA-256, and the
  `config_sha256` of requested scan settings; `scanner/identity.py` holds the
  scan identity (source SHA-256, resolved configuration hash, engine version).
  `compare_source()` holds the comparison alone, for a source located by the
  caller: beside the document (`check_source()`), from scan-only storage, or
  from `project.json`.
- `batch.py`: shared batch planning: shell-independent input resolution (a
  pattern skips `*-inspect.json` files and an explicit path to one is refused),
  output naming for `-o` and `-d`, collision, input-overwrite and `--force`
  checks, and atomic text writes.
- `report_service.py`: report batch planning on `batch.py` and sequential
  multi-report execution.
- `sampling.py`: streaming, reusable single-file CSV sampling strategies and
  atomic output writing.
- `sampling_service.py`: sample batch planning on `batch.py` and sequential
  multi-sample execution.
- `scan_service.py`: scan batch planning on `batch.py`, configuration layers,
  sequential scans and atomic `.scan.json` writes (`generate_scans()`). A JSON,
  JSONL or NDJSON source takes the configuration resolved by
  `inspector/resolution.py`, per source; without `-o` or `-d` the scan of every
  format goes to the shared storage.
- `inspect_service.py`: inspect batch planning on `batch.py` (unknown kinds and
  unsafe outputs reject the batch before any reading), sequential inspections
  and the visible Inspect file writes (`generate_inspections()`); `inspect()` is
  its single-source form in the public API.
- `generate_definition.py`: strict, bounded YAML version 1 loading and located
  validation for Generate. `generate_service.py` resolves overrides, apportions
  rows, plans every artifact and owns staging and best-effort publication.
  `generate_csv.py` is the UTF-8/LF streaming writer adapted from the Generate
  prototype. `generate_values.py` evaluates elementary and dependent columns,
  with shared entity pools and stable random streams. Lot 3 adds relations and
  staged `combine` output. Lot 4 adds clean weighted cohorts and a separate
  measured anomaly pass in `generate_anomalies.py`, preserving the clean CSV.
  `generate_insurance.py` loads and validates packaged Insurance tables and
  generates one coherent 33-field branch row per request; the shared CSV
  writer and combine pass produce its three branch files and union.
- `projects/`: private DuckDB project storage, not used by default Scan/Report
  (design in
  `scan/project-storage.md`): `identity.py` (ULID project ids), `location.py`
  (storage root and layout), `models.py` and `store.py` (`project.json`),
  `index.py` (`projects/index.json` lookup, rebuilt from the project files) and
  `catalog.py` (create, find and update a project) and `freshness.py`
  (`project_freshness()`: the source located by `project.json` compared with
  the facts of the project's `scan.json`). `freshness.py` reads scan
  models, through `scan_reuse.py`; nothing in it runs a scan.
- `projects/_codec.py`, `_schema.py`, `_staging.py`, `_bounded_values.py` and
  `_validation.py`: private explicit project-db schemas and bounded Scan
  record sink. Revision 1 retains exhaustive observations; new revision-2
  generations retain the first 10,000 raw typed analyzable values per field
  and their continuing counts, with explicit omissions. Complete record
  facts/memberships persist independently. Validation checks all retained
  data and Scan invariants; discarded cells cannot be reconstructed or used
  to recompute digests at reopen. DuckDB is pinned to 1.5.5 with a physical
  `v1.4.0` target. The loader owns only its new staging directory.
- `projects/_publication.py`, `_generation.py`, `_locks.py`, `_sync.py` and
  `_recovery.py`: private revision-2 publication and pinned read-only sessions.
  A workspace OS writer lock serializes mutation; a shared maintenance lock
  protects readers and writers against explicit orphan quarantine. One atomic
  manifest replacement commits an immutable scan/database pair. Both hashes
  and database bindings are verified before opening; an index failure after
  commit is a repair warning. File fsync is supported locally; directory fsync
  is implemented on POSIX and explicitly unavailable on Windows. No stronger
  power-loss or network-filesystem guarantee is claimed.
- `projects/_queries.py` and `_query_budget.py`: private generation-bound
  complete record memberships and field frequencies/normalization groups,
  with independently paged variants. Shared Scan categorization,
  normalization and exposure precede ranking. Disposable materializations
  and reader spill live only in generation-scoped `cache/` directories;
  memory/spill budgets fail explicitly. Value pages are exact for the stored
  population and marked limited when the catalog omitted occurrences.
  Cursors bind project, generation and query semantics. D07 row attribution
  and source reconstruction remain deferred.
- `projects/_cache.py`: private inventory/dry-run and explicit cleanup of
  owned disposable query directories. New caches have synchronized path-bound
  ownership markers. Execution revalidates a supplied plan under exclusive
  maintenance/writer locks; unknown/unmarked contents and links/reparse points
  stay in place. It never opens the source or modifies project storage.
  Automatic TTL/quotas and generation retention remain deferred (D03).
- `projects/_session.py`: private S17 inspection and context-managed opening
  above verified generations and exposure-aware queries. Immutable assessments
  identify the pinned generation, source check time, configuration fingerprints
  and readiness for `require_current`/explicit `snapshot`. Refresh compares the
  same Scan; a closed inspection is advisory and opening rechecks with an
  optional expected-generation precondition. Source I/O failures remain separate
  from the three source states. Query contexts close with the session. No scan,
  index mutation, legacy upgrade or public export occurs; f2 remains deferred.
- `project_scan_service.py`: `scan_project()`, the peer of `scan_service.py` for
  project storage: reserves identity privately, builds a staged scan/database
  pair and publishes its revision-2 manifest through the protocol above.
  Rescans preserve identity and previous generations. Legacy revision-1
  projects remain readable as scan-only metadata; explicit rebuilding from
  source upgrades them on success. The service and SQL sessions remain
  internal; lot 7.storage-d3 supplies private exposure-aware queries. The one-shot CLI
  and public API keep their existing output behavior.
  `rescan_project()` is the private S17 f2 context: the caller supplies the
  selected project id, generation id and source path from inspection. Publication
  verifies all three under writer ownership, bypasses source-index selection,
  retains the pinned Scan configuration unless given a complete replacement,
  and defaults to the 10,000-key bound. A smaller bound is explicit. It releases
  the writer before reopening a separately verified reader at the exact new
  generation; post-commit open failures carry the committed publication.
  Selected old artifact hashes and the recorded Scan/config are checked before
  staging without a second DuckDB connection, so an active old reader with a
  different private spill directory does not block an explicit rescan.
- `project_open_service.py`: private S18 first-open adapter. It inspects one
  project by id, opens a fresh selected generation as current, or returns a
  transient decision with explicit snapshot/rescan choices. Actions carry
  storage, workspace, generation and source preconditions. No public adapter
  or product presentation is exposed yet.
- `shared_scan_service.py`: CSV command handoff. Scan writes a scan-only
  document under `workspaces/local/scans/<source-path-hash>/scan.json`;
  Report reuses it after source SHA-256 and settings checks or atomically
  replaces it when stale. Ordinary Scan/Report runs neither open nor build a
  DuckDB database. Existing private project generations remain untouched.
- `projects/_retention.py`: removes the previously selected generation and its
  owned cache after successful replacement under exclusive maintenance
  ownership. Active readers or unknown contents retain it with a warning.
- `cache_service.py`, `cli/cache.py`: read-only cache information and explicit
  cleanup, for one source project or all valid projects. Only owned disposable
  query caches are cleaned; selected Scan/database artifacts remain storage.
- `progress.py`: presentation-neutral progress events emitted by report services
  and consumed by adapters such as the CLI.
- `reporting.py`: renders a validated JSON result through Jinja2. With
  `--details`, the report service writes one independent HTML page per column
  under a folder named after the main HTML stem. No CSV access. Column
  filenames use source order and a bounded slug.
- `execution_log.py`: records successful run metadata and timing in a shared,
  atomically updated `executions.json` file.
- `scanner/`: Tabalyst Scan, the streaming engine (see below); `tabalyst scan`
  and `tabalyst.scan()` expose it. Tabalyst has no pandas dependency.
- `inspector/`: Tabalyst Inspect (design in `docs/dev/inspect/design.md`),
  under construction. `models.py` holds the Inspect document and the editable
  `config`; `json_inspect/` is the JSON kind: `inspect_source()` reads a
  `.json`, `.jsonl` or `.ndjson` source in one event pass (shared with the Scan
  readers through `JsonEvents` and `JsonlLines`), hashes it, finds the candidate
  collections, applies the selection rule and returns an `InspectDocument`.
  `persistence.py` writes and reads the visible file and the automatic cache;
  `resolution.py` resolves the configuration of a source by layers and is
  called by Scan and Report (`resolve_interpretation()`, `check_result()`).
  `excel_inspect/` is the Excel kind (`inspect_workbook()`: one candidate per
  sheet and per named table, header detection, the selection rule of JSON
  with table row counts). The shell is shared; `InspectDocument` reads
  `detection` and `config` by `inspect.kind`. The contract and the lots X-1 to X-4
  are in `docs/dev/inspect/excel.md`.
- `scanner/readers/excel_reader.py`: reads the one sheet or named table that
  `excel.dataset_path` names, with typed values and the shape of a CSV table
  (dataset `rows`, `Column` fields), so the report and the project store
  treat it like CSV. `excel_common.py` opens workbooks with calamine, bounds
  the memory of a sheet from the zip directory and hashes the file;
  `excel_table.py` is the header rule that Inspect and the reader share.
- `cli/app.py`: root command registration and global options.
- `cli/inspect.py`, `cli/report.py`, `cli/sample.py`, `cli/scan.py`: thin command adapters and
  error/diagnostic presentation over the services.
- `cli/terminal.py`: progress line, exit codes shared by the adapters.
- `templates/` and `static/`: self-contained report presentation. The Signature
  design system, embedded font subsets, table controls and interaction script are
  included directly in every report; no CDN is required.

## Python API

```python
import tabalyst

result = tabalyst.analyze("data.csv", "reports/client-a.html")
print(result["summary"]["row_count"])
```

The equivalent CLI operation is:

```console
tabalyst report data.csv -o reports/client-a.html
```

When no output is specified, the source stem is preserved beside the source.
Batch inputs use the same rule or a shared explicit output directory:

```console
tabalyst report data.csv
tabalyst report *.csv -d reports
```

`report_service.py` resolves explicit paths and non-recursive globs, deduplicates
inputs, and validates every planned artifact before processing begins. `-o`
maps one input to one explicit HTML file. `-d` maps one or more inputs to HTML
files named from their source stems. Output collisions and existing artifacts
without `--force` reject the complete plan before any report is generated.

Processing errors remain attached to their individual jobs. Other jobs continue,
and the batch result exposes its complete successes and failures to the CLI or
another adapter.

The command layer contains no profiling or rendering rules. Status and diagnostic
messages use standard error so standard output remains available for future data
streams. Existing report artifacts require explicit replacement through
`--force` or `force=True`.

`sample_csv()` is the reusable single-file sampling boundary. It validates CSV
structure in a first streaming pass, then keeps bounded selection state in a
second pass. `first` and `last` retain only the requested rows; `random` uses
reservoir sampling; `stratified` first counts distinct field values, allocates
the exact requested size with largest remainders, then uses one bounded
reservoir per stratum. Selected records are written in source order through an
atomic temporary file replacement.

`generate_samples()` resolves explicit paths and non-recursive globs before any
work begins. Without an output option, `data.csv` maps to `data.sample.csv`.
`-o` maps one source to one file and `-d` maps one or more sources into a shared
directory. The complete plan rejects input/output conflicts, duplicate output
names and existing files unless `--force` is explicit.

## Progress reporting boundary

Progress belongs at the boundary between the engine and its adapters. The engine
emits reading, analysis, rendering, writing, completion and failure events without
depending on terminal libraries. The CLI combines these events with exact batch
positions such as `[2/8]`.

Scans and reports report reading progress by bytes: the readers' hashing
stream counts every byte, and `scan()` emits `reading` events with
`bytes_read` and `bytes_total` at most once per percent of the file and never
more often than every MiB. Reports then emit analyzing, rendering and writing.

Interactive progress must use standard error, remain silent under `--quiet`, and
disable terminal animation when output is redirected. `--no-progress` disables it
explicitly.

## Current semantics

The report is built on Tabalyst Scan ([scan/design.md](scan/design.md)). The
first record is the header. Row numbers identify logical data records, starting
at 1; quoted multiline cells count as one record. Structural errors stop the
report under the default `strict` policy; under `tolerant`, malformed records
are excluded and listed by the `excluded_records` issue.

Raw strings are preserved. Missing cells follow `scan.values`: empty and
whitespace-only cells by default, plus configured markers compared after
trimming. Distinct values, examples, types and lengths use the analytical value
(NFC, trim, collapse whitespace). The preview and duplicate-row comparison
retain raw values; duplicate counts exclude each group's first row and compare
a 128-bit BLAKE2b digest per row, one per distinct row, the only record-level
state that grows with the file (lot 5c bounds it).

Column types are the scan's technical types. A date column is `date` even with
several formats or ambiguous values; ambiguous values are never resolved from
column evidence (design 12.6): the report shows the evidence and suggests
`scan.detectors.date.ambiguous_order` when it is one-sided, and the
`ambiguous_dates` issue counts them. Semantic types are `date` for date columns,
otherwise the scan's primary interpretation. Values of sensitive columns are
masked by default in examples, value profiles and the preview.

Each column materializes `with_issues`: missing values, inferred type `mixed` or
unresolved ambiguous dates. Dataset-level type counts, section counts and date
aggregates are also serialized so the HTML renderer does not recreate analysis
rules. A measure stopped by a scan limit is `null` in the profile, shown as
`limited`, and listed by the `limited_measures` issue.

JSON and HTML may include raw data and should be shared accordingly. The
generated report is self-contained and does not need an internet connection.

The JSON profile records the scan and profile time in `processing_seconds`. The
adjacent `executions.json` also records total run time, including JSON and HTML
generation, plus package and optional Git metadata.

## Browser checks

With Node.js, Playwright and Edge installed, run the interactive regression check
on a generated report and its JSON:

```powershell
node tests/browser/report.cjs examples/output/insurance-customers/report.html examples/output/insurance-customers/report.json
```

An optional third argument is the Playwright module path. `TABALYST_BROWSER`
selects another installed browser channel. Run from the repository root with an
external artifact directory for screenshots. By default the browser check uses
`<OS temporary directory>/tabalyst/artifacts`; set `TABALYST_ARTIFACTS_DIR` to
override it. For a local Windows checkout watched by Obsidian, always keep test and
benchmark evidence in the external `D:\GIT.test\tabalyst` (never inside the
checkout), for example:

```powershell
$env:TABALYST_ARTIFACTS_DIR = 'D:\GIT.test\tabalyst\artifacts'
.\.venv\Scripts\python.exe -m pytest --basetemp "$env:TABALYST_ARTIFACTS_DIR\pytest-session-1" -p no:cacheprovider
```

Choose a fresh `--basetemp` path for each run: pytest clears that exact
directory when reusing it. Put benchmark `--root`/`--stage` paths under the
same external artifact directory. The environment setting affects browser
screenshots; pytest receives its path explicitly. Checks cover JSON-backed issue
filtering, numeric ordering and filtering, percentage/count alignment,
date-format tooltips, theme persistence, collapsible panels and desktop/mobile
popup layout. Filtering never recalculates dataset metrics.

## Next iterations

The shared dataset source, chunked readers, engine progress events, sampling,
per-column JSON files, an evidence CSV with selected/context rows, configurable
semantic rules, localization and an HTTP adapter build on these boundaries. No
compatibility layer or migration system is planned during the current alpha.

Tabalyst Scan replaced the pandas engine with a streaming, bounded-memory
engine for CSV and JSON (lot 5c removed the pandas engine). Its contract is [scan/design.md](scan/design.md) and
its lot plan is kept in the private maintainer repository. `tabalyst.scanner` provides
`scan()`, `ScanConfig` and `ScanResult`; since lot 4, the `tabalyst scan`
command and the top-level `tabalyst.scan()` and `tabalyst.generate_scans()`
expose it, and the `scan` section of configuration files configures it. Since
lot 5a, `tabalyst report` is built on it; since lot 5c, it can reuse a scan
document (`--scan`). Since lot 6, it processes distinct values in batches
and hands the values of large sources to worker processes
(`scanner/workers.py`), plain subprocesses of the running interpreter, with
the same results (design section 13).

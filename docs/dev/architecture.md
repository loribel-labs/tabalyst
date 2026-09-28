# Architecture

Iteration 1 implements `CSV -> report.json -> report.html` with a single global
JSON file. Its column summaries stay inside that file. The format is experimental;
breaking changes are expected while iterating.

During the `0.1.0aX` application series, profiles use `format_version: "0.1.0a"`.
The integer `format_revision` increases for each meaningful structural or semantic
change. See the [format changelog](../en/reference/profile-format-changelog.md).

## Boundaries

- `report_profile.py`: builds the report profile from a `ScanResult`, fresh
  or read back from a scan document; record-level facts (preview, duplicate,
  empty and incomplete records) come from the `records` block of each scan
  dataset. No file access.
- `report_config.py`: `ReportConfig`, the effective report settings: the
  top-level presentation settings and the `scan` configuration.
- `models.py`: Pydantic models of the report profile (revision 6: one
  profile per dataset in `datasets`, with its limits and, for JSON, its
  structure).
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
  applies the staleness rule (design O12): source size, modification time and
  SHA-256, and the `config_sha256` of requested scan settings.
- `batch.py`: shared batch planning: shell-independent input resolution,
  output naming for `-o` and `-d`, collision, input-overwrite and `--force`
  checks, and atomic text writes.
- `report_service.py`: report batch planning on `batch.py` and sequential
  multi-report execution.
- `sampling.py`: streaming, reusable single-file CSV sampling strategies and
  atomic output writing.
- `sampling_service.py`: sample batch planning on `batch.py` and sequential
  multi-sample execution.
- `scan_service.py`: scan batch planning on `batch.py`, configuration layers,
  sequential scans and atomic `.scan.json` writes (`generate_scans()`).
- `progress.py`: presentation-neutral progress events emitted by report services
  and consumed by adapters such as the CLI.
- `reporting.py`: renders a validated JSON result through Jinja2. No CSV access.
- `execution_log.py`: records successful run metadata and timing in a shared,
  atomically updated `executions.json` file.
- `scanner/`: Tabalyst Scan, the streaming engine (see below); `tabalyst scan`
  and `tabalyst.scan()` expose it. Tabalyst has no pandas dependency.
- `cli/app.py`: root command registration and global options.
- `cli/report.py`, `cli/sample.py`, `cli/scan.py`: thin command adapters and
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
`artifacts/` directory available for screenshots. Checks cover JSON-backed issue
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
its lots are in [scan/plan.md](scan/plan.md). `tabalyst.scanner` provides
`scan()`, `ScanConfig` and `ScanResult`; since lot 4, the `tabalyst scan`
command and the top-level `tabalyst.scan()` and `tabalyst.generate_scans()`
expose it, and the `scan` section of configuration files configures it. Since
lot 5a, `tabalyst report` is built on it; since lot 5c, it can reuse a scan
document (`--scan`). Since lot 6, it processes distinct values in batches
and hands the values of large sources to worker processes
(`scanner/workers.py`), plain subprocesses of the running interpreter, with
the same results (design section 13).

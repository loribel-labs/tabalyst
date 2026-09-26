# Architecture

Iteration 1 implements `CSV -> report.json -> report.html` with a single global
JSON file. Its column summaries stay inside that file. The format is experimental;
breaking changes are expected while iterating.

During the `0.1.0aX` application series, profiles use `format_version: "0.1.0a"`.
The integer `format_revision` increases for each meaningful structural or semantic
change. See the [format changelog](../en/reference/profile-format-changelog.md).

## Boundaries

- `ingestion.py`: validates record widths and quoting, then loads raw strings with
  pandas. Duplicate and blank headers retain their names and get positional IDs.
- `analysis.py`: computes dataset and column statistics without writing files.
- `models.py`: Pydantic models for JSON serialization and validation.
- `config.py`: validated settings, loaded from optional JSON configuration files.
- `service.py`: public `analyze(...)` orchestration plus the reusable
  `analyze_csv(path, config)` engine boundary. Output replacement is an explicit
  service-level choice rather than a CLI-only safeguard.
- `report_service.py`: shell-independent input resolution, complete batch
  planning, collision checks and sequential multi-report execution.
- `sampling.py`: streaming, reusable single-file CSV sampling strategies and
  atomic output writing.
- `sampling_service.py`: wildcard resolution, batch planning, collision checks
  and sequential multi-sample execution.
- `progress.py`: presentation-neutral progress events emitted by report services
  and consumed by adapters such as the CLI.
- `reporting.py`: renders a validated JSON result through Jinja2. No CSV access.
- `execution_log.py`: records successful run metadata and timing in a shared,
  atomically updated `executions.json` file.
- `cli/app.py`: root command registration and global options.
- `cli/report.py`: thin `report` command adapter and error/diagnostic
  presentation over `analyze()`.
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

Accurate row counts, throughput and estimates require the future chunked reader;
a blocking `pandas.read_csv()` call cannot provide a truthful per-file percentage.

Interactive progress must use standard error, remain silent under `--quiet`, and
disable terminal animation when output is redirected. `--no-progress` disables it
explicitly.

## Current semantics

The first record is the header. Row numbers identify logical data records, starting
at 1; quoted multiline cells count as one record. Structural errors stop ingestion,
including blank physical records, short rows and extra fields. Empty cells in a
correctly sized record are supported.

Raw strings are preserved. Whitespace-only values are missing by default; literal
`NA`, `NULL` and `NaN` remain text unless configured as missing markers. Missing
markers are matched after trimming whitespace, with case preserved. Normalization
is applied before distinct counts, occurrences, examples, enum detection, type
inference and string-length analysis. The preview and duplicate-row comparison
deliberately retain raw values; duplicate counts exclude each group's first row.

Type inference checks every present normalized value and applies the configured
confidence threshold. It recognizes integers without leading zeros,
dot-decimal/scientific numbers, true/false and configured strict YMD, MDY and DMY
dates. Date profiles retain explicit format, ambiguity and calendar-error counts
even when the resulting column type is mixed. Error counts describe values outside
the accepted dominant type; a generic mixed column has no error rate. Decimal
commas, email addresses and postal codes remain text at this stage. Types are
descriptive hints, not conversions or domain validation. Numeric statistics use
accepted numeric values with floating-point arithmetic and are omitted when
conversion is not finite.

Each column materializes `with_issues` in the canonical JSON. It is true exactly
when the column has one or more missing values or its inferred type is `mixed`.
Dataset-level type counts, section counts and date aggregates are also serialized
so the HTML renderer does not recreate analysis rules.

The complete CSV is loaded into memory. The preview contains the first N records;
its size does not affect analysis. JSON and HTML may include raw data and should be
shared accordingly. The generated report is self-contained and does not need an
internet connection.

The JSON profile records end-to-end CSV ingestion and analysis time in
`processing_seconds`. The adjacent `executions.json` also records total run time,
including JSON and HTML generation, plus package and optional Git metadata.

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

Tabalyst Scan will replace the pandas engine with a streaming, bounded-memory
engine for CSV and JSON. Its contract is [scan/design.md](scan/design.md) and
its lots are in [scan/plan.md](scan/plan.md).

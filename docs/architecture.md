# Architecture

Iteration 1 implements `CSV -> report.json -> report.html` with a single global
JSON file. Its column summaries stay inside that file. The format is experimental;
breaking changes are expected while iterating.

During the `0.1.0aX` application series, profiles use `format_version: "0.1.0a"`.
The integer `format_revision` increases for each meaningful structural or semantic
change. See the [format changelog](format-changelog.md).

## Boundaries

- `ingestion.py`: validates record widths and quoting, then loads raw strings with
  pandas. Duplicate and blank headers retain their names and get positional IDs.
- `analysis.py`: computes dataset and column statistics without writing files.
- `models.py`: Pydantic models for JSON serialization and validation.
- `config.py`: validated settings, loaded from optional JSON configuration files.
- `service.py`: callable `analyze_csv(path, config)` for CLI and future HTTP adapters.
- `reporting.py`: renders a validated JSON result through Jinja2. No CSV access.
- `execution_log.py`: records successful CLI run metadata and timing in a shared,
  atomically updated `execution.json` file.
- `cli.py`: command-line options, error reporting and output files.
- `templates/` and `static/`: report presentation; Bootstrap 5.3.8 CSS uses a CDN
  with an integrity hash. DataTables 3.0.4 and ColumnControl 2.0.2 also load from a
  CDN with pinned versions and integrity hashes. The Tabalyst theme and table
  configuration script are embedded.

## Python API

```python
import pandas as pd
from tabalyst import AnalysisConfig, analyze_column, analyze_csv, render_report

profile = analyze_csv("data.csv", AnalysisConfig(preview_rows=10))
json_text = profile.model_dump_json(indent=2)
html_text = render_report(profile)
column = analyze_column(pd.Series(["001", "002", ""]), name="customer_id")
```

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

The complete CSV is loaded into memory. The preview contains the first N records;
its size does not affect analysis. JSON and HTML may include raw data and should be
shared accordingly. Bootstrap needs an internet connection; data is embedded in
the report and is not sent to the CDN.

The JSON profile records end-to-end CSV ingestion and analysis time in
`processing_seconds`. The adjacent `execution.json` also records total CLI time,
including JSON and HTML generation, plus package and optional Git metadata.

## Browser checks

With Node.js, Playwright and Edge installed, run the interactive regression check
on a generated report and its JSON:

```powershell
node tests/browser/report.cjs reports/data/report.html reports/data/report.json
```

An optional third argument is the Playwright module path. `TABALYST_BROWSER`
selects another installed browser channel. Run from the repository root with an
`artifacts/` directory available for screenshots. Checks cover combined filters,
numeric ordering, reset, original row numbers, and desktop/mobile popup layout.
`tests/fixtures/report_filters.csv` additionally exercises duplicate column names
and HTML-like content in filter menus. Checks include combined filters, numeric
ordering, secondary-table reset placement, date-format tooltips, original row
numbers and desktop/mobile popup layout. Filtering never recalculates dataset
metrics.

## Next iterations

Per-column JSON files, an evidence CSV with selected/context rows, advanced sampling,
configurable semantic rules, localization and an HTTP adapter build on these
boundaries. No compatibility layer or migration system is planned yet.

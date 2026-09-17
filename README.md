# Tabalyst

Tabalyst profiles CSV files into structured JSON and customizable HTML reports.
Built with pandas, Pydantic, Jinja2 and Bootstrap 5.3.8.

## Quick start

Python 3.11+ is required. From the project directory, on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m tabalyst analyze data.csv
```

This creates `dataset.json` and `report.html` in the current directory. Open the
HTML file directly in your browser; Bootstrap loads from a CDN and needs internet.
The default input is UTF-8 (with or without BOM), comma-separated, with a header.

Try the included sample:

```powershell
.\.venv\Scripts\python.exe -m tabalyst analyze examples\basic.csv -o reports\demo\report.html
```

## Test with your own CSV

Place your CSV in the project directory, then run:

```powershell
.\.venv\Scripts\python.exe -m tabalyst analyze data.csv -o reports\data\report.html
```

Replace `data.csv` with your file path. The command analyzes the complete CSV and
creates both `reports\data\dataset.json` and `reports\data\report.html`. Open the
HTML file directly in a browser to inspect the report. UTF-8 and a comma delimiter
are used by default; specify other formats when needed:

```powershell
.\.venv\Scripts\python.exe -m tabalyst analyze "C:\data\customers.csv" `
  -o reports\customers\report.html --encoding cp1252 --delimiter ";"
```

## Iteration 1

- Row/column counts, missing cells, exact duplicate rows and quality observations.
- Column summaries: inferred types, distinct values, examples and numeric statistics.
- Numbered raw-data preview; all records are analyzed regardless of preview size.
- Independent JSON-to-HTML rendering, ready for custom report templates.
- Sortable tables with column filters, multi-select checklists and numeric conditions.

The column summary supports name/type selection and numeric filters on Missing (%)
and Distinct: `=`, `>`, `>=`, `<`, `<=`, or an inclusive `[minimum, maximum]` range.
Filters combine and Reset restores the original
view. Sample filters apply only to embedded preview rows, not the complete CSV.
DataTables 3.0.4 and ColumnControl 2.0.2 load from their CDN alongside Bootstrap.

Raw values are preserved. Blank/whitespace-only values count as missing by default;
literal `NA` and `NULL` do not. Malformed records produce errors rather than being
silently skipped. The full CSV is currently loaded into memory.

```powershell
# Change CSV options or load one or more configuration files.
.\.venv\Scripts\python.exe -m tabalyst analyze data.csv --delimiter ";" --encoding cp1252
.\.venv\Scripts\python.exe -m tabalyst analyze data.csv --config examples\config.json --preview-rows 20

# Regenerate a report from JSON, without the original CSV.
.\.venv\Scripts\python.exe -m tabalyst render dataset.json -o report.html

# Run checks.
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
```

Configuration files merge in order; later values win, lists replace previous lists,
and CLI options take precedence. See [example settings](examples/config.json).

## Roadmap

Per-column JSON files, contextual evidence rows, configurable semantic rules,
sampling modes, localization and an HTTP API are planned. The JSON format is
experimental and may change without backward compatibility.

See [architecture and Python API](docs/architecture.md) for details and the
[development progress](docs/progress.md) for the current implementation history.

## License

Released under the MIT License.

Created by Gregory Borelli - Catalyseur Numérique.

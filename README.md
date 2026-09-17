# Tabalyst

Tabalyst profiles CSV files into structured JSON and customizable HTML reports.
Built with pandas, Pydantic, Jinja2 and Bootstrap 5.3.8.

## Run the alpha from a clone

Tabalyst is currently an alpha project. It is not yet published as an application
or a PyPI package: run it from a Git clone. The editable installation below only
installs the clone's Python dependencies and makes its command available inside the
local virtual environment.

Python 3.11+ is required. On Windows, a practical workspace layout is:

```text
D:\CODEX\gb-csv-analysis\
├── tabalyst\              # Git clone: run all commands here
└── test-divers\
    └── data.csv            # Your local CSV file
```

From `D:\CODEX\gb-csv-analysis\tabalyst`, create the virtual environment and
install the runtime and development libraries:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m tabalyst --help
```

`pandas`, `Pydantic`, `Jinja2`, `Typer`, `charset-normalizer`, `pytest` and Ruff
are installed by that command. Repeat it after pulling dependency changes.

### Analyze a CSV

Still from the clone directory, analyze the sibling file shown above:

```powershell
.\.venv\Scripts\python.exe -m tabalyst analyze ..\test-divers\data.csv `
  -o reports\data\report.html
```

This creates local, Git-ignored output files:

```text
tabalyst\reports\data\
├── dataset.json            # Complete global analysis profile
└── report.html             # Open this file directly in a browser
```

The default input is UTF-8 (with or without BOM), comma-separated, with a header.
For a different encoding or delimiter:

```powershell
.\.venv\Scripts\python.exe -m tabalyst analyze "C:\data\customers.csv" `
  -o reports\customers\report.html --encoding cp1252 --delimiter ";"
```

To test the tracked sample instead, use:

```powershell
.\.venv\Scripts\python.exe -m tabalyst analyze examples\basic.csv `
  -o reports\demo\report.html
```

### Optional package build

A build is not required to analyze CSV files. To verify that the clone can produce
a Python distribution, install the build helper and create artifacts in `dist\`:

```powershell
.\.venv\Scripts\python.exe -m pip install build
.\.venv\Scripts\python.exe -m build
```

`dist\` is Git-ignored. This is a packaging check for the alpha; it does not make
Tabalyst a published or system-wide installed application.

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

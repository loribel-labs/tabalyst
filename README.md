# Tabalyst

Tabalyst profiles CSV files into structured JSON and customizable HTML reports.
Built with pandas, Pydantic, Jinja2 and Bootstrap 5.3.8.

Tabalyst is an alpha project. It is not published on PyPI and is not installed
system-wide: it runs from a Git clone. If you are trying it for the first time,
jump to [Testing the alpha](#testing-the-alpha) at the end of this file.

## Features

- Row and column counts, missing cells, exact duplicate rows and quality observations.
- Column summaries: inferred types, semantic enum candidates, value occurrences,
  representative examples and numeric statistics.
- Numbered raw-data preview; all records are analyzed regardless of preview size.
- Independent JSON-to-HTML rendering, ready for custom report templates.
- Sortable tables with column filters, multi-select checklists and numeric conditions.

The column summary supports name and type selection, plus numeric filters on
Missing (%) and Distinct: `=`, `>`, `>=`, `<`, `<=`, or an inclusive
`[minimum, maximum]` range. Filters combine, and Reset restores the original view.
Sample filters apply only to the embedded preview rows, not to the complete CSV.
DataTables 3.0.4 and ColumnControl 2.0.2 load from their CDN alongside Bootstrap.
Google Fonts supplies Oswald, Roboto and Caveat, so the generated report needs an
internet connection for its complete presentation.

Raw values are preserved. Blank and whitespace-only values count as missing by
default; literal `NA` and `NULL` do not. Malformed records produce errors rather
than being silently skipped. The full CSV is currently loaded into memory.

## Requirements

Python 3.11 or later.

`pandas`, `Pydantic`, `Jinja2`, `Typer` and `charset-normalizer` are installed with
the package. `pytest` and Ruff come with the optional `dev` extra.

## Usage

```powershell
# Analyze a CSV and write the HTML report.
python -m tabalyst analyze data.csv -o reports\data\report.html

# Non-default encoding or delimiter.
python -m tabalyst analyze data.csv --encoding cp1252 --delimiter ";"

# Add one or more overrides after the automatic tabalyst.json, and set the preview size.
python -m tabalyst analyze data.csv --config examples\config.json --preview-rows 20

# Regenerate a report from JSON, without the original CSV.
python -m tabalyst render dataset.json -o report.html

# Full option list.
python -m tabalyst --help
```

The default input is UTF-8 (with or without BOM), comma-separated, with a header row.

Each `analyze` run writes two files in the output folder: `dataset.json`, the
complete global analysis profile, and the HTML report itself.

## Configuration

When `tabalyst.json` exists in the directory where the command is run, Tabalyst
loads it automatically. Files passed with `--config` merge afterward: later values
win, lists replace previous lists, and CLI options take precedence over every file. See
[example settings](examples/config.json) and the full
[configuration reference](docs/configuration.md).

The `value_examples` section controls distribution, sampling, text-length and
display thresholds. The `enum_detection` section controls low-cardinality text
classification. These values are part of the generated JSON so every report keeps
the exact settings used for its analysis.

## Development

```powershell
pip install -e ".[dev]"
python -m pytest
python -m ruff check .
```

To verify that the clone can produce a Python distribution:

```powershell
pip install build
python -m build
```

Artifacts land in `dist\`, which is Git-ignored. This is a packaging check only;
it does not make Tabalyst a published or system-wide application.

## Roadmap

Per-column JSON files, contextual evidence rows, configurable semantic rules,
sampling modes, localization and an HTTP API are planned. The JSON format is
experimental and may change without backward compatibility.

See [architecture and Python API](docs/architecture.md) for details, and the
[development progress](docs/progress.md) for the current implementation history.

## License

Released under the MIT License.

Created by Gregory Borelli - Catalyseur Numérique.

---

# Testing the alpha

A step-by-step guide for Windows, from the clone to your first report.
No prior Python experience needed. Every command runs in PowerShell.

## 1. Install Python

Download Python 3.11 or later from [python.org](https://www.python.org/downloads/)
and run the installer. On the first screen, check **Add python.exe to PATH** before
clicking Install.

Open PowerShell (Start menu, type `powershell`) and check the version:

```powershell
python --version
```

You should see `Python 3.11.x` or higher. If the command is not recognized, close
PowerShell, reopen it, and try again.

## 2. Choose a workspace folder

Create one folder that will hold the project and your test data:

```powershell
mkdir C:\projects
cd C:\projects
```

## 3. Clone the repository

```powershell
git clone <repository-url>
cd tabalyst
```

If `git` is not recognized, install [Git for Windows](https://git-scm.com/download/win)
first, then reopen PowerShell.

You are now in `C:\projects\tabalyst`. **Every command below runs from here.**

## 4. Create the virtual environment

A virtual environment keeps Tabalyst's libraries isolated from the rest of your
machine.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Your prompt now starts with `(.venv)`. That prefix means the environment is active.

If PowerShell refuses to run the activation script, allow it for this window only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
```

You will repeat the activation line each time you open a new PowerShell window.

## 5. Install Tabalyst

```powershell
pip install -e .
```

Check that the command is available:

```powershell
python -m tabalyst --help
```

## 6. Run it on the sample file

The repository ships with a small CSV, so you can produce a report right away:

```powershell
python -m tabalyst analyze examples\basic.csv -o reports\demo\report.html
```

Open the result:

```powershell
start reports\demo\report.html
```

Your browser displays the report. If you got this far, the installation works.

## 7. Run it on your own CSV

Put your file in a folder next to the clone, not inside it:

```text
C:\projects\
├── tabalyst\           <- the clone, where you run the commands
└── test-csv\
    └── data.csv        <- your file
```

```powershell
mkdir ..\test-csv
```

Copy your CSV into `C:\projects\test-csv\`, name it `data.csv`, then run:

```powershell
python -m tabalyst analyze ..\test-csv\data.csv -o reports\test-csv\report.html
start reports\test-csv\report.html
```

The `reports\` folder is Git-ignored, so your outputs stay local.

## 8. Adjust for your file format

If your CSV comes from Excel in French, it is probably semicolon-separated and
encoded in Windows-1252:

```powershell
python -m tabalyst analyze ..\test-csv\data.csv -o reports\test-csv\report.html --encoding cp1252 --delimiter ";"
```

## Troubleshooting

| Message | What to do |
| --- | --- |
| `python : The term 'python' is not recognized` | Python is not in your PATH. Reinstall it with **Add python.exe to PATH** checked. |
| `Activate.ps1 cannot be loaded because running scripts is disabled` | Run the `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` line from step 4. |
| `No module named tabalyst` | The environment is not active, or step 5 did not complete. Rerun `.venv\Scripts\Activate.ps1`, then `pip install -e .`. |
| `UnicodeDecodeError` | Wrong encoding. Add `--encoding cp1252`. |
| Everything lands in a single column | Wrong delimiter. Add `--delimiter ";"`. |
| `FileNotFoundError` | Check that you are in `D:\projects\tabalyst` and that the path to your CSV is correct. |

## Starting a new session

Next time you open PowerShell, two lines put you back to work:

```powershell
cd C:\projects\tabalyst
.venv\Scripts\Activate.ps1
```

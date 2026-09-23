# Tabalyst

Tabalyst is a local-first CSV profiling library and command-line tool. It reads a
CSV file once, produces a structured JSON profile, and renders the same result as
an interactive HTML report.

Version `0.1.0` is the first packaged public API. The analysis format is still
young, so larger schema changes are reserved for future minor releases.

## Requirements and installation

Tabalyst supports Python 3.11, 3.12, 3.13, and 3.14.

```console
pip install tabalyst
```

For local development from a clone:

```console
python -m venv .venv
python -m pip install -e ".[dev]"
```

## Command line

Pass the CSV source and the complete HTML report path as positional arguments:

```console
tabalyst data.csv reports/report.html
```

The report path must end in `.html`. Parent directories are created
automatically, and existing artifacts are replaced. A successful run creates:

```text
reports/
|-- report.html
|-- report.json
`-- executions.json
```

The JSON profile always shares the HTML filename stem. `executions.json` keeps a
cumulative history for successful analyses in the same report directory, so
several named reports can coexist there.

Common options are:

```console
tabalyst data.csv reports/report.html --separator ";" --encoding cp1252
tabalyst data.csv reports/report.html --config tabalyst.json
tabalyst --help
tabalyst --version
```

`python -m tabalyst` accepts the same arguments.

## Python API

```python
import tabalyst

result = tabalyst.analyze(
    "data.csv",
    "reports/report.html",
    separator=";",
    encoding="cp1252",
    config_path="tabalyst.json",
)

print(tabalyst.__version__)
print(result["summary"]["row_count"])
```

`analyze()` returns a JSON-serializable dictionary whose logical content matches
the adjacent JSON file. The HTML is rendered from that canonical JSON profile.
Expected failures derive from `tabalyst.TabalystError`; callers may distinguish
`InputError`, `ConfigurationError`, and `ReportError`.

## Configuration

Configuration files are strict JSON. Unknown names and invalid values are errors.
The existing analysis settings remain available; the smallest useful file is:

```json
{
  "csv": {
    "delimiter": ";",
    "encoding": "cp1252"
  }
}
```

Resolution order is:

1. an explicit `separator` or `encoding` argument;
2. the file passed with `config_path` or `--config`;
3. Tabalyst defaults: comma and `utf-8-sig`.

`utf-8-sig` accepts ordinary UTF-8 and UTF-8 with a byte-order mark. See the
[configuration reference](https://github.com/loribel-labs/tabalyst/blob/main/docs/configuration.md)
for analysis, normalization,
date, type-inference, sampling, and enum settings.

## Public examples

The repository contains two reproducible examples:

- `basic`: five rows covering common CSV values and one duplicate row.
- `insurance-customers`: 3,000 synthetic customer and contract records across
  34 columns. Names and contact details are fictional, and email addresses use
  reserved `.example` domains.

Each dataset under `examples/input/` has a matching generated report under
`examples/output/`. Regenerate both with:

```console
tabalyst examples/input/basic.csv examples/output/basic/report.html --config examples/config.json
tabalyst examples/input/insurance-customers.csv examples/output/insurance-customers/report.html --config examples/config.json
```

See the complete layout and maintenance notes in the
[examples README](https://github.com/loribel-labs/tabalyst/blob/main/examples/README.md).

## What the report contains

- Dataset dimensions, missing cells, duplicate rows, and quality observations.
- Physical and semantic type inference with explicit confidence and error rates.
- Numeric, date, string-length, normalization, and value-distribution profiles.
- A bounded raw-data preview while all records are analyzed.
- Sortable and filterable HTML tables in the self-contained Signature report.

Raw strings are preserved. The complete CSV is currently loaded into memory.
Report data remains local and Tabalyst adds no telemetry or remote analysis. The
report embeds its design system, font subsets and interaction code, so it works
without CDN or network access.

## Compatibility with alpha commands

The earlier commands remain available during the `0.1.x` transition:

```console
tabalyst analyze data.csv -o reports/report.html
tabalyst render reports/report.json -o reports/regenerated.html
```

The alpha `analyze` form also retains automatic `tabalyst.json` discovery,
multiple `--config` overrides, and `--preview-rows`. New integrations should use
the direct command or `tabalyst.analyze()`.

## Development and packaging

```console
python -m pytest
python -m ruff check .
python -m build
```

The build creates a wheel and source distribution under `dist/`. Release steps,
including the clean-wheel smoke test and PyPI Trusted Publishing setup, are in
[RELEASING.md](https://github.com/loribel-labs/tabalyst/blob/main/RELEASING.md).
The packaging architecture and automated publication flow are documented in
[docs/python-package-and-release.md](https://github.com/loribel-labs/tabalyst/blob/main/docs/python-package-and-release.md).

Report format details and internal boundaries are documented in
[docs/architecture.md](https://github.com/loribel-labs/tabalyst/blob/main/docs/architecture.md).
Please report defects through the
[GitHub issue tracker](https://github.com/loribel-labs/tabalyst/issues).

## License

Tabalyst is released under the
[MIT License](https://github.com/loribel-labs/tabalyst/blob/main/LICENSE).

Created by Gregory Borelli - Catalyseur Numérique.

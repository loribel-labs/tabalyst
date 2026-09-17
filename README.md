# Tabalyst

Tabalyst is an open-source data profiling engine that turns CSV files into
structured JSON analyses and customizable HTML reports.

## Project goals

- Read real-world CSV files, including imperfect data and varied encodings.
- Produce reusable JSON results independently from report rendering.
- Generate standalone HTML reports with contextual data samples.
- Support configurable detection rules and future API integrations.

## Roadmap

The first iteration covers the complete `CSV -> dataset.json -> report.html`
workflow. Later iterations will add detailed per-column analyses, evidence rows,
sampling strategies, and more advanced data-quality checks.

The JSON format is experimental and may change without backward compatibility
while the project is in its early development phase.

## Development setup

Tabalyst requires Python 3.11 or newer.

```powershell
python -m pip install -e ".[dev]"
```

## License

Released under the MIT License.

Created by Gregory Borelli - Catalyseur Numérique.

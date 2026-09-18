# Development progress

## 2026-09-17

- Established the Python project, dependencies, CLI, configuration loading and reusable analysis service.
- Added robust pandas CSV ingestion with configurable delimiters, encodings and preview size.
- Implemented the global JSON profile with dataset metrics, inferred column types, missing values, distinct values, examples and numeric statistics.
- Built the Bootstrap HTML report with quality observations and numbered raw-data previews.
- Added sortable and filterable tables, type badges, numeric comparisons and inclusive ranges.
- Refined filter ergonomics with compact controls, active states, draggable dialogs and responsive desktop/mobile layouts.
- Applied the report typography and semantic color system, with full-width bands and persistent dark/light themes.
- Added automated Python and browser coverage, including malformed data and HTML-injection checks.
- Added configurable value distributions and representative sampling, plus low-cardinality `enum` candidates with report tooltips.
- Added automatic project configuration through a root-level `tabalyst.json`, with explicit files and CLI options as later overrides.
- Added configurable trim and internal-whitespace normalization with detailed column and dataset counters.
- Added strict multi-format date profiling with ambiguity, validation-error and format occurrence counts.

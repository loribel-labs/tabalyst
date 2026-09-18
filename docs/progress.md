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

## 2026-09-18

- Added confidence-based physical typing with separate semantic types and explicit error counts.
- Split normalization metrics into a filterable Transformations table.
- Added five string-length categories, independent fixed lengths, and bounded
  per-length occurrence samples for short values.
- Expanded Date analysis with explicit format distributions in interactive tooltips.
- Aligned secondary-table Reset controls with section titles and show them only
  while a filter or sort is active. The Columns reset remains available beside
  its permanent text search field.
- Refined report interaction colors, quality metrics, percentage columns, large-number formatting, date variants and fixed-length string presentation.
- Added end-to-end processing time and clearer data-cleaning observations.
- Added distinct string-length counts and per-length occurrence examples to the report.
- Expanded string distributions through medium-length values, retained up to ten
  examples per length, and added mean and median length statistics.
- Unified numeric table filters and numeric-column spacing across the report.
- Derived profile JSON names from HTML outputs and added a cumulative, versioned
  `execution.json` performance history with optional Git state.
- Made filter-level Clear actions contextual and aligned them with each filter name.
- Established application version `0.1.0a1` and separate profile format family and
  revision identifiers with a dedicated format changelog.
- Published preliminary `0.1.0a1` release notes with highlights, format identifiers,
  validation coverage, upgrade guidance, and known limitations.

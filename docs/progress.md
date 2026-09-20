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

## 2026-09-19

- Added the Tabalyst application version and a GitHub repository link to the generated report footer.
- Released Tabalyst `0.1.0a2` with the report footer improvements.
- Reworked the generated report layout with a responsive, sticky left navigation
  that groups report and analysis sections.
- Made navigation links open collapsed analysis sections and expanded the desktop
  report content to the full available layout width.
- Unified report sections as collapsible panels, retaining quality information and
  columns open by default while keeping the data sample collapsed.
- Refined report metadata formatting for compact elapsed times and KB/MB source
  sizes, and aligned the footer with the main layout width.
- Added smooth open and close transitions for report panels, respecting reduced
  motion preferences.
- Enhanced panel transitions with animated chevrons and a staged content reveal.
- Added distinct-value counts to string analysis and standardized compact table
  widths while preserving space for example and format columns.
- Prepared Tabalyst `0.1.0a3` for the report navigation update.

## 2026-09-20

- Finalized and published Tabalyst `0.1.0a3` with the responsive report navigation,
  animated collapsible panels, compact tables, and metadata presentation updates.
- Prepared the `0.1.0` public package with `tabalyst.analyze()`, direct CLI syntax,
  public exceptions, metadata-backed versioning, and retained alpha compatibility.
- Centralized HTML, JSON, and cumulative `executions.json` production behind the
  public API and added contract tests for configuration precedence and errors.
- Added Python 3.11-3.14 CI, clean-wheel smoke coverage, PyPI Trusted Publishing,
  release documentation, and concise package-oriented README guidance.
- Reorganized public examples into named inputs and matching generated outputs,
  including a small smoke dataset and a 3,000-row synthetic insurance dataset.

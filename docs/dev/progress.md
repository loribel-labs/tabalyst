# Development progress

## 2026-09-28

- Detailed project.duckdb design (Tabalyst Scan lot 7.storage-c, D01), no
  implementation or new dependency: project-storage.md specifies independent
  logical versioning, shared dataset/field/record/observation tables, canonical
  path identities and tagged raw Scan values. S07 now uses the Scan record
  hook instead of a second parser with DuckDB inference. Full record lists
  and storage-derived value listings keep Scan's scope, limits and exposure
  explicit. A revision-2 project manifest will commit an immutable generation
  containing scan.json and project.duckdb; separate file replacements in the
  current a/b service do not yet provide this guarantee. Recovery states,
  acceptance tests and implementation lots d1/d2/d3 are specified. Runtime
  selection, richer detector/exclusion attribution and JSON ancestry, and
  platform durability remain deferred with required evidence (D06-D08).
  Decisions remain Proposed for the implementation gate. Existing code and
  working-tree changes are preserved; no public behavior or studio change.
  Validation: 1,165 tests passed, 2 skipped; Ruff and diff whitespace checks
  passed. Three demos regenerated successfully, with the original nine demo
  files restored byte-for-byte afterward to preserve existing edits.
- Project scan service and freshness (Tabalyst Scan lot 7.storage-b): the
  comparison of the staleness rule (size, modification time, SHA-256) is
  extracted from `scan_reuse.check_source` into `compare_source()`, which
  returns `fresh`, `stale` (with its reason) or `missing` for a source located
  by the caller; the report's messages are unchanged. Project storage reuses it
  through `project_freshness()`, which locates the source with `project.json`
  and reads the recorded facts in the project's `scan.json`. The new internal
  service `project_scan_service.scan_project()` finds or creates the project of
  a source, runs `scan()`, writes `scan.json` atomically in the project
  directory and calls `record_scan`; a project created by a failed scan is
  removed, a failed rescan leaves the previous scan. `tabalyst.scanner` is
  untouched and `project.duckdb` is not started. Tests in
  `tests/test_source_freshness.py` and `tests/test_project_scan.py`.
- Project identity and `project.json` (Tabalyst Scan lot 7.storage-a), first
  implementation of [project-storage.md](scan/project-storage.md): the new
  internal package `tabalyst.projects` generates `project_id` (ULID, never
  derived from the source path), resolves the local storage root with the new
  dependency `platformdirs` (override `TABALYST_HOME`), defines and atomically
  writes `project.json` (format revision 1) and keeps the reconstructible
  `projects/index.json` lookup, which repairs itself from the project files.
  No CLI command, `tabalyst.scanner` untouched, `project.duckdb` not started.
  The example `project_id` of the design was not a valid ULID and is
  corrected. Tests in `tests/test_project_*.py`.
- Project storage design (Tabalyst Scan lot 7.storage), design only, no code:
  [docs/dev/scan/project-storage.md](scan/project-storage.md) settles how a
  future Explore and Transform will persist project state instead of
  re-scanning a source, ahead of any implementation. Storage layout shared
  between local and SaaS mode, `project_id` generation independent of the
  source path, `workspace_id` fixed to `local` in CLI mode, the
  `project.json` schema, the boundary between project storage (`project.json`,
  `scan.json`, `project.duckdb`) and `cache/`, and how `project.duckdb` is
  populated by a layer above `tabalyst.scanner`, which stays untouched.
  DuckDB table layout, cache policy, Transform history storage and the
  default behavior on a stale project are left explicitly open.
- Report table filters: the name search and segmented buttons of the Columns
  table are now generic (`data-search` / `data-seg` toolbar controls, rows
  carry `data-name` / `data-flags`) and added to Transformations (All / With
  transform), Variant groups (search, and the subsection can be collapsed),
  Date analysis (All / Mixed), String analysis (All / Fixed / Not fixed, and
  All / Enum) and Detectors and formats (search). Detector format chips keep
  their display and gain a hover tooltip listing every format with count and
  percentage. Demos regenerated; the filters were checked in the browser.
- Prepared Tabalyst `0.4.2` with faster scans of large files, worker
  processes, rare detectors, less horizontal scrolling in wide reports, scan
  format revision 4 and profile format revision 8.
- Less horizontal scrolling in reports, checked at 1,920 px: the content
  width cap rises from 1,440 to 1,760 px, table header labels may wrap so a
  table narrows before it scrolls, and in data samples column names break
  after `_`, `.`, `-` and `/` (`breakable` filter of `reporting.py`) and
  lists of JSON values wrap. At 1,920 px, the analysis tables of the three
  demos no longer scroll; the insurance data sample overflows by 3,091 px
  instead of 4,056 and the JSON sample by 897 px instead of 2,331. The
  browser regression check passes at desktop and mobile sizes.
- Faster scans of large files (Tabalyst Scan lot 6, second session): 1
  million rows of 20 columns in about 11 s instead of 177 s with 0.4.1 (and
  109 s with the former pandas engine), 100,000 JSON records in about 8 s
  instead of 22 s. Distinct values are processed in batches, detector by
  detector: built-in detectors reject most values with a check inside a list
  comprehension (`classify_many`), a skipped detector costs nothing per
  value, and an enumeration that can no longer match stops (`rejects_field`).
  Printable strings are normalized inline, masks use a translation table,
  and classifications and observations are named tuples. CSV records reach
  the engine as batches of rows, counted column by column at C speed, with
  the global budget checked in record order when a batch could exceed it.
  Sources of 16 MiB or more are analyzed by worker processes, one field per
  worker, at most 8 by default: `scan(workers=...)`, `--workers` for `scan`
  and `report`; a worker failing to start leaves the scan in one process.
  The JSON reader shares one path object per path, and table duplicate
  digests hash values joined by NUL characters. Results are identical to the
  previous engine on a corpus of 24 scans, and between one process and
  workers.
- Rare detectors (decision O24, proposed): after the warm-up, a detector that
  recognized at most `detection.rare_share` (default 0.001) of its distinct
  values, and none in its second half, is skipped too; a sensitive detector
  without a match is not. Probes that react more often than the warm-up
  raise `detector_skipped_reacted`. Scan format revision 4
  (`adaptive.warmup_reactions`), profile revision 8, the report's analysis
  settings describe the rule. French pages and `tabalyst-studio` follow-ups
  are listed in the lot 6 notes of the scan plan.
- Prepared Tabalyst `0.4.1` with adaptive detection, faster streaming, the
  total time of reports built from scan documents, scan format revision 3
  and profile format revision 7.
- Adaptive detection (lot 6, design 13 item 4, decision O23): the first
  `detection.warmup_values` distinct values of a field (default 10,000) go
  through every detector; detectors that reacted to none of them then skip
  the other values, counted `not_tested`, except probes (CRC-32 of the value,
  about one in `detection.probe_interval`, default 100). A reacting probe
  raises a `detector_skipped_reacted` warning; a skipped detector is never
  re-enabled, which would break identical results between execution modes.
  `number` and `date` are never skipped; sensitive detectors are skipped like
  the others for now (open point in design 13). Scan format revision 3
  (`adaptive` in detector results), profile revision 7 (`detection`
  settings), a line in the report's analysis settings. On a 120,000-row
  benchmark, about 14% faster with identical types, interpretations and
  sensitivity. French pages to update with lot 5d-fr: `configuration`,
  `json-profile`, `known-limitations`, `profile-format-changelog`,
  `scan-format`, `scan-format-changelog`.
- A report built with `--scan` shows the total time: `processing_seconds`
  (and `analysis_seconds`, `total_seconds` of the execution history) add the
  scan duration recorded in the document. French page to update with them:
  `json-profile`.
- Scan speed after the `0.4.0` regression report (550,000-row, 35-column
  CSV: 73 s in `0.3.0`, 160 s in `0.4.0`, about 110 s now; profiles and
  reports unchanged). Field states and duplicate digests look paths up by
  identity first (a path hashes and prints each segment dataclass), and
  duplicate digests number paths instead of printing them. Detector shape
  checks are memoized per shape (`SHAPE_CACHE_SIZE`). Accumulators whose
  `add` ignores unmatched values declare `ignores_unmatched` in their own
  class body, and the tally skips those calls. Duplicate digests of CSV
  rows hash the value lengths and the joined values instead of the `repr`
  of every observation (about half the cost of duplicate detection; other
  records keep the full key). The remaining time is mostly
  the classification of distinct values in high-cardinality columns (phase 6).
- Prepared Tabalyst `0.4.0` with Tabalyst Scan, `tabalyst scan`, reports
  of JSON files built on the streaming engine and profile format revision 6.
- Normalization, limits and structure sections of the report (Tabalyst Scan
  lot 5d): profile format revision 6. "Transformations" shows every
  normalization stage (Unicode composition, trimming, whitespace collapsing,
  case folding, accent removal) with the distinct counts and a table of
  variant groups; new `variant_groups` info issue. A "Limits and
  diagnostics" section, shown only when needed, lists every measure stopped
  by a scan limit with its reason, limit and proven lower bound, structural
  truncation and the scan diagnostics. JSON reports have a "JSON structure"
  section: every path, containers included, with depth, native types,
  presence per parent and array lengths.
- Scan reuse, streaming duplicates and pandas removal (Tabalyst Scan lot 5c):
  every scan dataset has a `records` block (scan format revision 2) with
  records with missing values, empty records, duplicate records and a
  preview through the exposure gate. Duplicates are bounded by the new
  `scan.limits.max_tracked_records` budget (2,000,000 by default); beyond it
  the count is a proven lower bound with reason `record_budget`, shown as
  `≥ N` in the report. `tabalyst report --scan data.scan.json` (and
  `generate_reports(from_scan=True)`, `analyze_scan()`) builds the report
  from a scan document without reading the source, and refuses a stale scan:
  a source beside it that changed (size, then SHA-256 when its modification
  time changed) or `--config` scan settings that differ from the document's;
  a source not beside the document is reported as not checked.
  Profile format revision 5 adds `summary.duplicate_row_status`;
  `preview_rows` moved to `scan.records.preview`. After gate 5, the pandas
  engine (`analysis.py`, `ingestion.py`, `legacy_models.py`), its settings
  classes, `analyze_column`, `AnalysisConfig`, the parity tests, the
  `pandas-engine` benchmark task and the pandas dependency were removed.

## 2026-09-27

- French documentation for lots 5a and 5b (lot 5a-fr): configuration, glossary
  and known limitations follow the report built on Tabalyst Scan; the JSON
  profile and the profile format changelog are translated.
- Reports of JSON files and a detectors section (Tabalyst Scan lot 5b):
  `tabalyst report data.json` writes `data.report.html` and
  `data.report.json`, one view per dataset with a dataset selector, JSON
  columns named by their path and absent fields counted as missing. Profile
  format revision 4 lists datasets in `datasets` and adds `source.format`,
  column `path` and `detectors`, and preview `absent`. The new "Detectors and
  formats" section shows what each detector recognized per column. Added the
  `orders.json` demo and the how-to page "Report JSON files".
- Built `tabalyst report` on Tabalyst Scan (lot 5a): one streaming pass through
  `scan(on_record=...)`, the profile built by `report_profile.py`, profile
  format revision 3. The analysis settings of the report moved to the `scan`
  object of configuration files; former keys are rejected with their new
  location, and a top-level `csv` that differs from `scan.csv` is an error.
  Date columns are `date` with a new `ambiguous_dates` issue, ambiguity is
  never resolved from column evidence (the report shows it), semantic types
  are the scan's primary interpretations, sensitive values are masked in
  examples and the preview, and limited measures and excluded records have
  their own issues. Parity tests compare both demos with the pandas engine,
  kept until lot 5c. Fixed the overview link of the `trimmed_cells` issue.
- Fixed `*.sample.csv` permissions on Linux and macOS: samples written through a
  temporary file were readable by their owner only; they now follow the umask
  like scan outputs, through a shared `apply_default_file_mode` helper.
- Translated the lot 4 documentation to French (Tabalyst Scan lot 4-fr):
  `docs/fr/` now holds the index, how-to scan, configuration, glossary,
  known limitations, scan format and scan format changelog pages.
- Added `tabalyst scan` (Tabalyst Scan lot 4): CSV and JSON sources, default
  `<stem>.scan.json` output, `-o`, `-d`, repeatable `--config` and
  `--collection`, `--delimiter`, `--encoding`, `--force`, atomic writes,
  batches that continue after a failed source, partial-scan warnings and
  reading progress as a share of the file. Added `tabalyst.scan()`,
  `tabalyst.generate_scans()`, `ScanConfig` and `ScanResult` to the package.
  Configuration files accept a `scan` section, validated by every command and
  merged in order (objects merge, lists replace). Batch planning moved to
  `batch.py`, shared by `report`, `sample` and `scan`. Fixed a process crash
  of the compiled `ijson` backend on integers above 4,300 digits. New English
  pages: how-to scan, scan format and its changelog; configuration, glossary,
  known limitations and README updated.
- Added the Tabalyst Scan `uuid` and `ip_address` detectors (lot 3b, UUID
  and IP address family), which complete lot 3b. `uuid` recognizes the
  hyphenated, braced and `urn:uuid:` forms, formats such as `hyphenated` and
  `braced_upper`, and counts versions (`4`, `7`, `nil`, `other`) without
  validating them; not sensitive. `ip_address` recognizes dotted-decimal
  IPv4 and the IPv6 text forms (compressed, with an embedded IPv4 address),
  with `invalid` reasons such as `invalid_octet` and `invalid_compression`,
  a narrow IPv6 candidate so that times and MAC addresses are never invalid,
  and a `versions` setting; sensitive, so its fields are masked by default.
  No value of the demos matches; the 100,000-row benchmark file scans about
  5 to 8% slower.
- Added the Tabalyst Scan `currency`, `percentage` and `quantity` detectors
  (lot 3b, currency and percentage family, extended to generic quantities):
  amounts with a currency symbol or ISO 4217 code before or after the number
  (`$1,234.56`, `12,50 €`, `USD 12`, accounting parentheses), percentages
  (`12,5 %`) and a number followed by any unit (`10 Go`, `1 024 Mo`,
  `90 km/h`). The number part follows the number detector's conventions and
  ambiguity; formats such as `$#,##0.0` and `# ##0 [unit]`; currency counts
  per marker and counted units in `details`. Not sensitive. No value of the
  insurance demo matches; the 100,000-row benchmark file scans about 7 to
  15% slower.
- Added the Tabalyst Scan `postal_code` detector (lot 3b, postal code
  family): Canadian postal codes (`ca`, with or without the space, ignoring
  case) and United States ZIP and ZIP+4 codes (`us`), format templates such
  as `A9A 9A9` and `99999-9999`, `invalid` reasons for letters Canada Post
  does not use, region counts in `details`. Not sensitive: a postal code is a
  quasi-identifier, and five-digit integer columns would otherwise be masked.
  Every complete postal code of the insurance demo matches. The 100,000-row
  benchmark file scans about 7% slower.

## 2026-09-26

- Added `tabalyst sample` with streaming first, last, random and proportional
  stratified strategies, reproducible seeds, row or percentage sizing and
  atomic CSV output.
- Added multi-file and non-recursive wildcard sampling, `[name].sample.csv`
  default names, `-o` and `-d` destinations, batch collision protection and a
  reusable Python API.
- Documented sampling in English and French and added coverage for strategies,
  proportions, null and small strata, invalid requests, empty inputs and batch
  output planning.
- Prepared Tabalyst `0.3.0` with Tabalyst Sample, its reusable Python APIs and
  unchanged report-profile compatibility.
- Completed phase 0 of Tabalyst Scan: design contract (`docs/dev/scan/design.md`)
  with its decision register, lot plan with models and session management
  (`docs/dev/scan/plan.md`), contract tests for lots 1a to 3b in `tests/scan/`
  (skipped until each lot is enabled), deterministic benchmark data and
  measurement tools in `benchmarks/`, and the baseline of the current engine:
  about 9,000 rows per second and 4.6 GB of memory for 1 million CSV rows.
  Every design decision was accepted at gate 0.
- Completed Tabalyst Scan lot 1a: `tabalyst.scanner` package with `scan()`,
  the complete `ScanConfig` schema with hard caps and fingerprint, immutable
  result models and measure envelopes, reversible path display syntax, the
  reader protocol and a streaming CSV reader that hashes while reading, strict
  and tolerant error policies with located diagnostics, presence counters,
  disjoint string categories, derived missing values and scan scope. Its
  contract tests are enabled. A 1-million-row CSV scans in about 13 seconds
  with about 77 MB of peak memory (lot 1a counters only). The minimum Pydantic
  version is now 2.11.
- Completed Tabalyst Scan lot 1b: streaming JSON reader on `ijson` (new
  runtime dependency, compiled backend required in CI) with its own path
  stack, automatic document and collection datasets, explicit collections that
  may cross arrays, duplicate-key and byte-order-mark handling, and the
  structural limits `max_fields`, `max_depth` and `max_record_observations`
  for CSV and JSON. Its contract tests are enabled; gate 1 items are listed in
  `docs/dev/scan/plan.md`.
- Completed Tabalyst Scan lot 2a: raw frequency tables keyed by native type,
  exact cardinality with proven bounds, per-field and global limits, long
  values, analytical frequency listings, seeded samples, first and last
  values, string characteristics and lengths, exact numeric statistics with a
  `precision` limit, native boolean counts, `measures_limited` and
  `global_budget` warnings. Per-value work runs once per distinct value, or in
  streaming after a table is released, with identical results. JSON strings
  with a lone surrogate escape are now rejected by both `ijson` backends where
  they can be detected. Its contract tests are enabled.
- Completed Tabalyst Scan lot 2b: normalization version 1 with its five
  stages, exact change counters that continue after a table is released,
  distinct counts after each stage and variant groups listed by comparison
  key with their raw variants. Group and variant limits truncate output only.
  Its contract tests are enabled; the 100,000-row benchmark file scans about
  5% slower than after lot 2a.
- Completed Tabalyst Scan lot 3a: detector framework (registry, coverage,
  formats, evidence, interpretations, per-field isolation of failures, shape
  signatures), technical type inference ported from the current engine, and
  the `number`, `date`, `boolean` and `enumeration` detectors. Numbers accept
  dot and comma decimal conventions and expose `1,234` as ambiguous; dates
  add ISO date-times, times and English and French month names, with a
  `temporal` block per kind. Ambiguity is exposed with its evidence and
  resolved only by configuration. Its contract tests are enabled; the
  100,000-row benchmark file scans about 60% slower, recorded for lot 6.
- Started Tabalyst Scan lot 3b: detector specifications in
  `docs/dev/scan/detectors.md`, declarative pattern detectors
  (`pattern:<id>`) built from the `patterns` configuration, and one exposure
  gate for sensitive fields that masks (default) or hides every value-bearing
  block, including detector evidence and variant groups. Its contract tests
  are enabled; the priority 1 catalogue families remain.
- Added the Tabalyst Scan `email` and `url` detectors (lot 3b, first
  catalogue family): syntax validation with `invalid` reasons, casefolded
  domain and host counts in `details` through the exposure gate, email
  fields sensitive and masked by default. The 12 mistyped addresses of the
  insurance demo are reported as invalid. The 100,000-row benchmark file
  scans about 8% slower.
- Added the Tabalyst Scan `phone` detector (lot 3b, phone family): North
  American (`nanp`, Canada and the United States) and French (`fr`) numbers in
  national and international forms, format templates such as
  `(999) 999-9999`, `invalid` reasons for area, exchange, trunk and leading
  digits, digit-only values never invalid, region counts in `details`, phone
  fields sensitive and masked by default. Every phone of the insurance demo
  matches. The 100,000-row benchmark file scans about 8% slower.

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
- Published Tabalyst `0.1.0` on PyPI through the Trusted Publishing workflow.
- Prepared Tabalyst `0.1.1` with section-specific sidebar icons, distinct counts
  and representative examples in numeric analysis, and distinct counts in date
  analysis, plus consistent badge styling for the empty semantic-type filter.
- Reworked the generated report footer into a responsive product footer with
  version, copyright, official website, and GitHub information.
- Made the clean-wheel CI smoke test version-agnostic so patch releases validate
  installed metadata and generated footer versions without hard-coded numbers.

## 2026-09-21

- Hid sidebar analysis links when their report sections are absent and corrected
  the overview metric list to use valid description-list markup.

## 2026-09-23

- Ported the Signature v1 report design into the JSON-driven generator, including
  self-contained fonts, responsive panels, custom sorting/filtering and print
  presentation without third-party CDNs.
- Materialized report semantics in profile revision 2: `with_issues`, type and
  section counts, date aggregates and percentages, numeric ranges, and string
  length display values.
- Defined `with_issues` as columns with missing values or inferred type `mixed`.
- Aligned percentages to the left and occurrence counts to the right across all
  percentage cells.
- Reworked browser regression coverage for the Signature report at desktop and
  mobile sizes.
- Prepared Tabalyst `0.1.2` with the Signature v1 report, profile revision 2,
  report-facing JSON semantics, and the final table-hover and product-link polish.
- Replaced the transitional direct/alpha CLI dispatch with the command-oriented
  `tabalyst report INPUT -o OUTPUT` contract.
- Split the CLI into root application and report-command adapters, with diagnostics
  on stderr, documented exit codes, quiet/verbose modes and explicit overwrite
  protection through `--force`.
- Defined the engine/adapter boundary for future progress events; truthful
  percentage and throughput reporting will accompany chunked ingestion.
- Repositioned the public README around Tabalyst as the platform, Tabalyst Report
  as the first tool, and Tabalyst CSV Report as the currently available format-
  specific offering.
- Added automatic source-stem outputs, multiple positional inputs,
  `-d/--output-dir`, native non-recursive glob resolution and deterministic input
  deduplication to Tabalyst Report.
- Added complete batch preflight checks for existing artifacts, input/output
  conflicts and same-stem collisions before any report is processed.
- Added reusable batch result models and engine progress events; the CLI now shows
  exact file position and processing phase in interactive terminals and continues
  with remaining inputs after an individual CSV failure.
- Prepared version `0.2.0` with concise release highlights for the new CLI and
  batch workflows.
- Hardened the CLI help regression test against ANSI styling differences on
  GitHub Actions and prepared the corrective `0.2.1` release after the `v0.2.0`
  workflow stopped before publication.
- Updated the clean-wheel CI smoke test to invoke the command-oriented
  `tabalyst report` interface.

## 2026-09-25

- Split `docs/` into published user documentation (`docs/en/`, `docs/fr/`) and
  maintainer documentation (`docs/dev/`), with a CC BY 4.0 license for the
  published pages, a bilingual glossary and documentation rules in `AGENTS.md`.
- Wrote the first English pages for the future docs.tabalyst.com site: home,
  installation (Windows first), first-report tutorial, JSON profile reference
  and known limitations, checked against the published `0.2.1` behavior.

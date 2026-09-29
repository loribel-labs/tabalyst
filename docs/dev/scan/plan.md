# Tabalyst Scan plan

How Tabalyst Scan is built: lots, their status, the model and effort to use,
and how work moves from one conversation to the next. The contract is
[design.md](design.md); measurements are in [benchmarks.md](benchmarks.md).

Every lot must leave the project releasable: tests and lint green, demos
regenerated, documentation consistent with what is released.

## Status

| Lot | Title | Status | Model | Effort | Branch |
| --- | --- | --- | --- | --- | --- |
| 0 | Design, contract tests, baseline benchmark | Done | Opus 5.5 | High | `scan/phase-0` |
| 1a | Engine core and CSV reader | Done | Opus 5.5 | High | `scan/phase-1` |
| 1b | JSON reader, collections and structural limits | Done | Opus 5.5 | High | `scan/phase-1` |
| 2a | Values, frequencies, limits and statistics | Done | Sonnet 5 | High | `scan/phase-2` |
| 2b | Normalization version 1 and variant groups | Done | Sonnet 5 | High | `scan/phase-2` |
| 3a | Detector framework, technical type, ported detectors | Done | Opus 5.5 | High | `scan/phase-3` |
| 3b | Priority 1 catalogue, patterns, sensitive values | Done | Sonnet 5 | Medium | `scan/phase-3` |
| 4 | `tabalyst scan` command, configuration layers, documentation | Done | Sonnet 5 | Medium | `scan/phase-4` |
| 4-fr | French translation of the lot 4 documentation | Done | Sonnet 5 | Low | `scan/phase-4-fr` |
| 5a | Report built on Scan, parity on the demos | Done | Opus 5.5 | High | `scan/phase-5` |
| 5a-fr | French translation of the lot 5a documentation | Done | Sonnet 5 | Low | `scan/phase-5-fr` |
| 5b | JSON sources and new sections in the report | Done | Opus 5.5 | Medium | `scan/phase-5` |
| 5c | Scan reuse, streaming duplicates, pandas removal | Done | Opus 5.5 | High | `scan/phase-5` |
| 5c-fr | French translation of the lot 5b and 5c documentation | Planned | Sonnet 5 | Low | `scan/phase-5-fr` |
| 5d | Normalization, limits and structure sections of the report | Done | Opus 5.5 | Medium | `scan/phase-5` |
| 5d-fr | French translation of the lot 5d documentation | Planned | Sonnet 5 | Low | `scan/phase-5-fr` |
| 6 | Measure, set targets, optimize | In progress | Opus 5.5 | High | `scan/phase-6` |
| 7.x | Extensions, one lot each | Planned | See lot 7 | - | `scan/<topic>` |
| 7.storage | Project storage design: identity, `project.json`, cache boundary | Done | Sonnet 5 | High | `scan/phase-7-storage` |
| 7.storage-a | Project identity, storage root, `project.json`, `projects/index.json` | Done | Sonnet 5 | High | `scan/phase-7-storage` |
| 7.storage-b | Project scan service and freshness | Done | Sonnet 5.5 | High | `scan/phase-7-storage` |
| 7.storage-c | Detailed project.duckdb design (D01), no implementation | Done | Session model | - | Existing working tree; no branch created |
| 7.storage-d1 | Database codec, staged loader and semantic parity | Done | Session model | High | Existing working tree; no branch created |
| 7.storage-d2 | Atomic generations, publication and recovery | Done | Session model | High | Existing working tree; no branch created |
| 7.storage-d3 | Large listings, exposure and storage benchmarks | Done | Session model | High | Existing working tree; no branch created |
| 7.storage-e | Explicit private query-cache maintenance | Done | Session model | High | Existing working tree; no branch created |
| 7.storage-f | Private project reopening design (D04/S17) | Done | Session model | High | Existing working tree; no branch created |
| 7.storage-f1 | Private pinned inspection/open sessions | Done | Session model | High | Existing working tree; no branch created |
| 7.storage-f2 | Explicit project-targeted conditional rescan | Planned | Session model | High | Existing working tree; no branch created |

Status values: Planned, Next, In progress, Done, Blocked. The session that
works on a lot updates this table.

### Gates

The maintainer validates before the next lot starts:

- **Gate 0**, before 1a: the Proposed decisions of the design register
  (design.md section 1) become Accepted or are amended. Passed on 2026-09-26:
  all accepted without change.
- **Gate 1**, after 1b: reader contract, paths and presence semantics. The
  items to validate are listed in the lot 1b notes.
- **Gate 3**, after 3a: detector contract and ambiguity handling.
- **Gate 4**, before releasing `tabalyst scan`.
- **Gate 5**, before removing the pandas engine in 5c. Passed on
  2026-09-28: removal approved at the start of lot 5c.
- **Storage implementation gate**, before 7.storage-d1: review the detailed
  D01 design in project-storage.md (S07, S10-S16), especially the shared Scan
  reader, raw local storage and generation layout. Choose/test the DuckDB
  runtime in d1; do not claim D06-D08 are already resolved. Project database
  use is enabled only after d2's publication/recovery acceptance tests.

## Why these models

- **Opus 5.5, high effort** where an error spreads to everything built later:
  the design, reader contracts and presence semantics (1a, 1b), the detector
  contract (3a), the report migration (5a) and optimization choices (6).
- **Sonnet 5** where a written contract and failing tests already define the
  work: measures (2a, 2b), catalogue detectors (3b), the command and its
  documentation (4, 4-fr) and the pandas removal (5c). If a Sonnet session
  finds that the contract itself is wrong, it stops, records the problem in
  this file and proposes an Opus session to amend the design.
- Model and effort are chosen in the app's selector before sending the first
  message of the conversation.

## Conversations

- **One conversation per lot.** Never start a second lot in the same
  conversation: a fresh session reloads `AGENTS.md`, this plan and the design,
  whereas a long conversation is eventually compacted and loses detail.
- **The repository is the memory.** Decisions go to design.md, status and next
  steps to this file, history to `docs/dev/progress.md`. Nothing needed later
  may exist only in a conversation.
- **A lot too large for one conversation** stops at a coherent point, with
  tests green and the "Notes" of the lot updated with what remains; the next
  conversation continues the same lot with the same prompt.
- **Branches and worktrees.** One branch per phase, as in the table. The app
  can open a session in a worktree on that branch. Commits, merges, tags and
  pushes happen only when the maintainer asks.
- **Parallel sessions** are allowed only where marked below, each in its own
  worktree. Everything before 3b is sequential because each lot depends on the
  previous contract.

## Session ritual

At the start:

1. Read `AGENTS.md`, this plan (the lot's section) and design.md.
2. Mark the lot In progress and add it to `ENABLED_LOTS` in
   `tests/scan/conftest.py`.
3. Propose the plan of the lot before editing anything.

At the end:

1. `.\.venv\Scripts\python.exe -m pytest` and
   `.\.venv\Scripts\python.exe -m ruff check .` pass, with the lot's contract
   tests enabled.
2. Regenerate the public demos with the commands in `examples/README.md`.
3. Update this plan (status, notes), design.md section 17 if the contract
   changed, and `docs/dev/progress.md`.
4. Run `/code-review` on the lot's changes and address the findings.
5. Propose a commit message; commit only if asked.
6. Propose the next conversation: lot, model, effort, branch and the starting
   prompt below, in the maintainer's conversation language.

## Starting prompt

```text
Tabalyst Scan, lot <ID>: <title>.
Read AGENTS.md, then docs/dev/scan/plan.md (lot <ID>) and docs/dev/scan/design.md.
Follow the session ritual of plan.md: enable lot <ID> in tests/scan/conftest.py,
propose your plan for the lot before editing, then implement until its contract
tests pass. At the end, complete the ritual and propose the next conversation.
```

## Lots

### Lot 0: design, contract tests, baseline

Done on 2026-09-26: design.md, contract tests for lots 1a to 3b (skipped until
enabled), benchmark tooling in `benchmarks/` and the baseline in
benchmarks.md.

### Lot 1a: engine core and CSV reader

- `tabalyst.scanner` package, `scan()` API, result models, `ScanConfig` with
  the complete schema of design section 15, hard caps and fingerprint.
- Paths: segments, display syntax and its parser (design section 4).
- Reader protocol and stream items; streaming CSV reader with SHA-256 computed
  while reading, strict and tolerant policies, positional identities.
- Engine, structure and presence counters, string categories, `missing`,
  `values.count`, diagnostics collector, scan status and scope.
- Done when: `tests/scan/test_scan_csv.py` passes. Reuse the CSV error
  messages of `ingestion.py` and `sampling.py` where they apply.
- Done on 2026-09-26; contract changes recorded in design section 17.

### Lot 1b: JSON reader, collections and structural limits

- Add `ijson` to the dependencies; verify wheels for Python 3.11 to 3.14 in CI
  (the pure-Python backend is the fallback).
- JSON reader with its own path stack; automatic and explicit collections;
  document, collection and scalar datasets; root field; arrays block.
- Structural limits: `max_fields`, `max_depth`, `max_record_observations`.
- Done when: `tests/scan/test_scan_json.py` passes. Then gate 1.
- Done on 2026-09-26; contract changes recorded in design section 17.

### Lot 2a: values, frequencies, limits and statistics

- Raw frequency tables keyed by native type, cardinality with proven bounds,
  global budget, long values, listings, samples, first and last values.
- String characteristics and lengths, exact numeric statistics, booleans,
  `not_applicable` measures, `measures_limited` diagnostic.
- Done when: `tests/scan/test_scan_measures.py` passes.
- Done on 2026-09-26; contract changes recorded in design section 17.

### Lot 2b: normalization version 1 and variant groups

- Stages, change counters that continue after table release, stage
  cardinalities, variant groups.
- Done when: `tests/scan/test_scan_normalization.py` passes.
- Done on 2026-09-26; contract changes recorded in design section 17.

### Lot 3a: detector framework, technical type, ported detectors

- Detector base class, registry, coverage, evidence, interpretations,
  isolation of failures, shape classifier.
- Execution modes: per distinct value while tables are complete, streaming with
  memoization afterwards (design section 13).
- Technical type inference ported from `analysis.py`.
- Ported and extended detectors: numbers (strict rule, then dot and comma
  decimal conventions with ambiguity), dates (current strict formats, ISO
  date-times and times, English and French month names), textual booleans,
  enumeration candidates.
- Done when: `tests/scan/test_scan_detectors.py` passes. Then gate 3.
- Done on 2026-09-26; contract changes recorded in design section 17. The
  items to validate at gate 3 are listed in the lot 3a notes.

### Lot 3b: priority 1 catalogue, patterns, sensitive values

- First, in one session: `detectors.md` (one short specification per
  detector, design section 12.9), the pattern detector and the exposure gate
  (`tests/scan/test_scan_patterns.py`).
- Then catalogue families, which may run as parallel sessions in separate
  worktrees: email and URL; phone (CA, US, FR); postal codes (CA, US ZIP);
  currency and percentage; UUID and IP addresses.
- Each detector adds its own positive, negative, variant and overlap tests.
- First session done on 2026-09-26: `detectors.md`, pattern detector and
  exposure gate; `tests/scan/test_scan_patterns.py` passes. Contract changes
  recorded in design section 17. The catalogue families remain; see the lot
  3b notes.
- Email and URL family done on 2026-09-26: `email` and `url` built-ins,
  enabled by default; `tests/test_scanner_email_url.py`.
- Phone family done on 2026-09-26: `phone` built-in (regions `nanp` for CA
  and US, `fr`), enabled by default; `tests/test_scanner_phone.py`.
- Postal code family done on 2026-09-27: `postal_code` built-in (regions
  `ca` and `us`), enabled by default, not sensitive;
  `tests/test_scanner_postal.py`.
- Currency and percentage family done on 2026-09-27, extended to generic
  quantities (`10 Go`, `1 024 Mo`) at the maintainer's request: `currency`,
  `percentage` and `quantity` built-ins, enabled by default, not sensitive;
  `tests/test_scanner_amounts.py`.
- UUID and IP address family done on 2026-09-27: `uuid` (not sensitive) and
  `ip_address` (versions `ipv4` and `ipv6`, sensitive) built-ins, enabled by
  default; `tests/test_scanner_uuid_ip.py`.
- Done on 2026-09-27: every priority 1 family is implemented; contract
  changes recorded in design section 17.

### Lot 4: `tabalyst scan` command, configuration layers, documentation

- `tabalyst scan INPUT... [-o | -d] [--config] [--collection] [--force]`,
  default output `data.scan.json`, atomic writes (design section 16.3).
- Shared batch planning with `report` and `sample`, progress by bytes read.
- `scan` section in `tabalyst.json`, configuration layers and merge rules;
  top-level `tabalyst.scan()` and `tabalyst.generate_scans()`.
- Documentation in `docs/en/`: how-to, scan format reference and changelog,
  configuration, glossary, known limitations; README. Note the follow-up needed
  in `tabalyst-studio`. Then gate 4 and release preparation.
- Done on 2026-09-27: `tabalyst scan`, `tabalyst.scan()`,
  `tabalyst.generate_scans()`, shared planning in `batch.py`, configuration
  layers, byte progress, the `ijson` long-integer crash fixed, English
  documentation. Contract changes recorded in design section 17. The items to
  validate at gate 4 are listed in the lot 4 notes.

### Lot 4-fr: French documentation

- Translate the lot 4 pages to `docs/fr/` with the glossary. Can run in
  parallel once the English pages are merged.
- Done on 2026-09-27, branch `scan/phase-4-fr`: French pages for `index`,
  `how-to/scan-files`, `reference/configuration`, `reference/glossary`,
  `reference/known-limitations`, `reference/scan-format` and
  `reference/scan-format-changelog`, translated in full since `docs/fr/` held
  only `how-to/sample-csv`. Relative links are unchanged, so links to pages
  not yet translated (install, first report, JSON profile, execution
  history, profile format changelog) have no French target yet. French
  headings change the generated anchors: `configuration.md` keeps an explicit
  `<a id="scan-settings"></a>` for the links of the other pages, while the
  anchor `install.md#keep-tabalyst-up-to-date` of the French index will need
  the same when `install` is translated.

### Lot 5a: report built on Scan

- Adapter from `ScanResult` to the report, profile format revision 3, parity
  tests on both demos, decision on how the report presents date ambiguity and
  evidence (design section 12.6).
- Done on 2026-09-27: `report_profile.py` (adapter and `RowFacts`),
  `report_config.py`, `scan(on_record=...)`, profile revision 3, report
  settings moved to `scan`, template and documentation updated;
  `tests/scan/test_scan_report.py` passes. Decisions recorded in design
  section 16.4 (O16). Notes for lots 5b and 5c below.

### Lot 5a-fr: French documentation

- Update the French pages changed by lot 5a from the English ones:
  `reference/configuration`, `reference/glossary` and
  `reference/known-limitations`, and translate `reference/json-profile` and
  `reference/profile-format-changelog` if the maintainer wants them. Can run
  in parallel with lot 5b.
- Done on 2026-09-27, branch `scan/phase-5-fr`: `reference/configuration`,
  `reference/glossary` and `reference/known-limitations` synchronized with the
  current English pages, which also include the lot 5b changes (JSON reports).
  `configuration.md` keeps explicit anchors `scan-settings` and
  `how-the-report-uses-the-scan-settings`. `json-profile` (revision 4) and
  `profile-format-changelog` translated in full.

### Lot 5b: JSON sources and new report sections

- `tabalyst report data.json`, sections for detectors and formats,
  normalization variants, limits and structure; browser checks at desktop and
  mobile sizes; a public JSON demo in `examples/`.
- Done on 2026-09-27: profile revision 4 (`datasets`), JSON sources with
  flattened scalar fields, record facts per dataset, the "Detectors and
  formats" section, `.report` output names for JSON sources, a dataset
  selector, the `orders.json` demo and `tests/scan/test_scan_report_json.py`.
  The maintainer kept only the detectors section: normalization variants,
  limits and structure sections are deferred (notes below). Decisions in
  design section 16.5.

### Lot 5c: reuse, duplicates, pandas removal

- `tabalyst report --scan data.scan.json` with the staleness rule (O12).
- Duplicate records in streaming under a budget.
- Remove `ingestion.py`, the pandas parts of `analysis.py` and the pandas
  dependency after gate 5.
- Done on 2026-09-28, decisions of the maintainer at the start of the lot:
  record facts live in the scan (a `records` block per dataset, scan format
  revision 2), stale scans fail, gate 5 passed. `tabalyst report --scan`,
  `scan_reuse.py`, the `record_budget` limit, profile revision 5 with
  `duplicate_row_status`, `preview_rows` moved to `scan.records.preview`;
  pandas engine and dependency removed. Contract tests
  `tests/scan/test_scan_records.py` and `tests/scan/test_scan_reuse.py`.
  Decisions in design sections 9.10 and 16.6. Notes below.

### Lot 5c-fr: French documentation

- Update the French pages from the English ones changed by lots 5b and 5c:
  `index`, `how-to/scan-files`, new `how-to/report-json-files`,
  `reference/configuration`, `reference/glossary`,
  `reference/known-limitations`, `reference/json-profile`,
  `reference/profile-format-changelog`, `reference/scan-format` and
  `reference/scan-format-changelog`.

### Lot 5d: normalization, limits and structure sections

- The report sections deferred by lot 5b: normalization variants, limits and
  JSON structure.
- Done on 2026-09-28, decisions of the maintainer at the start of the lot:
  the "Transformations" section is extended with every stage and a variant
  groups table; the "Limits and diagnostics" section appears only when
  something was limited or diagnosed; the "JSON structure" section is for
  JSON sources only. Profile revision 6, `variant_groups` issue, contract
  tests `tests/scan/test_scan_report_sections.py`. Decisions in design
  section 16.7. Notes below.

### Lot 5d-fr: French documentation

- Update the French pages from the English ones changed by lot 5d:
  `how-to/report-json-files`, `tutorials/first-report` (if translated),
  `reference/configuration`, `reference/json-profile`,
  `reference/known-limitations` and `reference/profile-format-changelog`. Can
  be merged with lot 5c-fr.

### Lot 6: measure, set targets, optimize

- Scan benchmarks next to the baseline, including 10 million rows, wide files,
  long strings and deep JSON; targets decided with the maintainer (O19).
- Fast paths, adaptive detection with explicit `not_tested`, mergeable states
  as preparation for parallelism.
- Done so far (2026-09-28): adaptive detection (design 13 item 4, O23,
  scan format revision 3, profile revision 7), CSV duplicate digests without
  `repr`.
- Done in a second session (2026-09-28), at the maintainer's request (the most
  speed on large files, progressive learning that drops what became unlikely,
  reading that uses the machine): batches of distinct values processed
  detector by detector, with `classify_many` prefilters and `rejects_field`
  (design 12.1, 13 item 5); CSV records read as column batches (design 6, 13
  item 6); streaming batches instead of the memoization cache; worker
  processes for sources of 16 MiB or more, `scan(workers=...)` and
  `--workers` (13 item 7); rare detectors, `detection.rare_share` (O24, scan
  format revision 4, profile revision 8); shared JSON path objects; faster
  table digests. Results are identical to the first session's engine, with
  `rare_share` 0, on a corpus of 24 scans (demos, edge cases, 100,000 and
  300,000 rows, JSON, streaming and budget limits), and identical between one
  process and workers. Benchmarks in benchmarks.md (lot 6).
- Open: targets (O19); benchmarks of 10 million rows, wide files, long
  strings and deep JSON; the sensitive detectors open point (design 13 item
  4); validation of O24 and O25 by the maintainer; reading one source with
  several processes (lot 7, needs mergeable states); batching JSON records in
  the engine like CSV rows.

### Lot 7: extensions

One conversation per topic, each starting with a short design addition:
catalogue waves 2 to 5 and profiles (Sonnet 5, medium); Excel, XML, database
and API readers, exact quantiles, parallel execution and plugins (Opus 5.5,
high, for their design).

### Lot 7.storage: project storage design

- Design only, no code: [project-storage.md](project-storage.md) settles how
  a future Explore and Transform will persist project state instead of
  re-scanning a source, requested ahead of any implementation lot.
- Done on 2026-09-28: storage layout shared between local and SaaS mode
  (`workspaces/<workspace_id>/projects/<project_id>/`), `project_id`
  generation (ULID, never derived from the source path), `workspace_id`
  fixed to `local` in CLI mode, the `project.json` schema, the boundary
  between project storage (`project.json`, `scan.json`, `project.duckdb`)
  and `cache/`, and how `project.duckdb` is populated by a layer above
  `tabalyst.scanner`, which stays untouched. Relation to the existing
  staleness rule (O12, `scan_reuse.py`) clarified: same comparison logic,
  reused rather than duplicated, resolved from `project.json`'s stored path
  instead of "beside the document". Decisions in project-storage.md section
  1 (S01 to S09).
- Explicitly deferred (project-storage.md section 1, D01 to D05): the exact
  `project.duckdb` table layout and how large listings beyond `scan.json`'s
  limits are produced; storage of future Transform history; cache TTL, size
  quotas and the `tabalyst cache` command surface; the default behavior when
  a project's source has changed (PROJ-04); a `dataset_id` distinct from
  `project_id`, should a project ever hold more than one source. Notes
  below.

### Lot 7.storage-a: project identity and `project.json`

- First implementation lot of project-storage.md: the `tabalyst.projects`
  package, with no CLI command and nothing exported by `tabalyst`. It does not
  touch `tabalyst.scanner` and does not start `project.duckdb` (D01).
- Done on 2026-09-28, the maintainer accepting `platformdirs` at the start of
  the lot: `identity.py` (`new_project_id()`, a ULID written by hand, and
  `is_project_id()`), `location.py` (`StorageLocation`, `local_storage_root()`
  with `platformdirs` and the `TABALYST_HOME` override), `models.py`
  (`ProjectDocument`, `project.json` format revision 1), `store.py` (atomic
  writer, validated reader, listing), `index.py` (`projects/index.json`, its
  rebuild and validated lookup) and `catalog.py` (`create_project`,
  `open_or_create_project`, `record_scan`). Tests in
  `tests/test_project_identity.py`, `test_project_location.py`,
  `test_project_store.py` and `test_project_index.py` (no `lot` marker: they
  are not scan contract tests). Notes below.

### Lot 7.storage-b: project scan service and freshness

- Done on 2026-09-28: `scan_reuse.compare_source()` separates O12's source
  comparison from the beside-the-document lookup; `check_source()` keeps the
  report's existing behavior and messages. `projects.freshness` applies the
  same comparison to the source path recorded in `project.json` and the facts
  recorded in the project's `scan.json` (S05 and S09).
- The internal `project_scan_service.scan_project()` finds or creates the
  project of one source, resolves Scan configuration like `generate_scans()`,
  runs `scan()`, writes the same `scan.json` document atomically and records
  the successful scan in `project.json`. A scan failure removes a project
  created by that call and leaves an existing project's artifacts unchanged.
  Progress uses the existing presentation-neutral events.
- No CLI or public API, no change to `tabalyst.scanner`, and no
  `project.duckdb`: D01 was the next design decision, detailed in 7.storage-c.
  Tests are in
  `tests/test_source_freshness.py` and `tests/test_project_scan.py`.

### Lot 7.storage-c: detailed project.duckdb design (D01)

- Done on 2026-09-28, design only: project-storage.md sections 8-10 define
  the logical database format, fixed metadata/record/observation tables,
  dataset/field/path identity, tagged raw values, absence and collections,
  effective configuration, large listings, publication and recovery tests.
- S07 is amended: consume the existing Scan record hook in a storage layer
  above the engine, instead of independently inferring the source with DuckDB.
  Scan keeps its bounded JSON; the database holds all analyzed observations
  and full baseline record memberships. No dependency or loader added.
- The target revision-2 project manifest points to an immutable generation;
  its atomic replacement commits scan.json and project.duckdb together.
  Current a/b code remains unchanged: its separate scan/metadata writes do
  not yet satisfy this multi-artifact protocol.
- S10-S16 are Proposed pending the implementation gate, not Implemented.
  D06 (runtime/performance), D07 (richer attribution/ancestry) and D08
  (deployment durability) remain explicit evidence requirements. D02-D05
  retain their original deferred scope.
- No contract-test lot is enabled for documentation-only work. No public
  format changes, branch, commit, tag or tabalyst-studio edit in this lot.
- Validation: 1,165 tests passed, 2 skipped; Ruff and `git diff --check`
  passed. All three demos regenerated successfully, then their nine original
  working-tree files were restored byte-for-byte to preserve existing edits.
  Manual design review checked reader/record semantics and publication
  boundaries; no `/code-review` command is available in this session.

### Next implementation: lots 7.storage-d1 to d3

- **d1:** explicit codec/schema, private staged loader through on_record,
  DuckDB compatibility selection, record listings and semantic parity.
- **d2:** manifest revision 2, generation resolver, OS writer lock, first
  scan/rescan publication, pinned readers, freshness/index integration,
  legacy rebuild and crash/recovery tests. Only then enable project DB use.
- **d3:** paginated large record/value queries, normalization and exposure,
  resource benchmarks. Detector/exclusion row attribution requires D07 first.
- Acceptance matrix and evidence to collect: project-storage.md section 10.
  Prefer a separate conversation for each lot; the maintainer requested d2
  as a continuation of d1. Model/branch are selected at the
  implementation gate; this plan does not authorize creating a branch.

### Lot 7.storage-d1: codec and private staging loader

- The maintainer accepted the lot c design before implementation. D06 pins
  DuckDB 1.5.5 and physical storage compatibility `v1.4.0`; local Windows
  Python 3.12 evidence, wheel coverage and measurements are recorded in
  project-storage.md section 10.1. A 12-job OS/Python storage CI matrix is
  added; remote execution remains unverified in this session.
- Private modules in `projects/` build a new staging directory only, through
  `scan(on_record=...)`. They use explicit constrained tables, row/byte-bound
  parameterized buffers, canonical paths and native payloads, metadata bound
  to exact scan document bytes, complete record memberships and exhaustive
  validation before commit and after checkpoint/close/read-only reopen.
- The storage-neutral record digest helper is shared with Scan. CSV layouts
  include unprofiled columns; JSON comparison retains observation order and
  Decimal representations. Scan's bounded lists/envelopes are unchanged.
- DuckDB does not support cross-schema foreign keys. Their bindings are
  checked explicitly, alongside nullable parent/collection links, native
  counts, array statistics, record flags/digests and listing parity.
- Lots a/b remain unchanged. No manifest/index/generation publication or
  default value APIs are added. Failed staging is retained privately for
  d2's ownership-aware recovery. d2 must supply locking, synchronization,
  atomic publication, pinned readers and legacy revision-1 rebuilding.
- d3 retains pagination, exposure-aware value queries, million-record and
  old/new-generation resource measurements. Small d1 measurements are not
  performance guarantees. There is no public behavior/studio follow-up.
- Validation: 1,252 tests passed, 2 skipped (87 new storage tests); Ruff and
  diff whitespace checks passed. All three demos regenerated and the nine
  pre-existing demo files restored byte-for-byte. No report presentation
  change, so no new browser regression run was required for d1.

### Lot 7.storage-d2: atomic publication and recovery

- Revision-2 manifests bind immutable generation scan/database hashes.
  OS-backed nonblocking workspace locks serialize all mutators; shared
  maintenance locks protect pinned readers and writers. First-scan identity
  stays private until the single manifest replacement. Rescans retain old
  generations and timestamps on pre-commit failure. Post-commit index errors
  are repair warnings; uncertain replacement outcomes are reclassified from
  the manifest, with evidence preserved when unreadable.
- Read-only sessions pin and verify one generation; freshness follows its
  scan. Missing/corrupt selected artifacts fail closed. Explicit legacy
  rebuilding preserves identity/created_at and upgrades only on success.
  Legacy mutators cannot bypass publication or downgrade revision 2.
- Explicit maintenance quarantines unselected ULID directories only under
  exclusive maintenance and writer ownership; it preserves unknown contents
  and never runs automatically during a scan. Retention policy remains D03.
- File synchronization is implemented; POSIX directory fsync is implemented,
  while Windows reports directory synchronization unsupported. Local tests
  establish process-failure atomic visibility, not power-loss durability.
  D08, remote OS CI, consumer APIs and d3 resource budgets remain open.
- Validation: 1,300 passed, 2 skipped, including 48 new failure/concurrency/
  recovery tests and real subprocess termination before/after commit. Ruff
  passed. Storage CI now includes these tests across its 12 OS/Python jobs;
  only Windows/Python 3.12 ran locally. Public behavior is unchanged; no
  tabalyst-studio follow-up, branch, commit or tag.

Handoff prompt used for d3:

```text
Tabalyst Scan, lot 7.storage-d3 : requêtes paginées et budgets project.duckdb.
Lis AGENTS.md, README.md, docs/dev/architecture.md, docs/dev/scan/plan.md,
design.md, project-storage.md et docs/dev/progress.md. Préserve toutes les
modifications existantes des lots a/b/d1/d2. Implémente les requêtes de records
et de valeurs paginées, liées à une génération, avec normalisation et
exposition Tabalyst. Vérifie la parité exhaustive, les limites et les curseurs
périmés. Mesure les sources volumineuses, la mémoire, le spill, l'ouverture
et le pic disque ancien/nouveau/staging. D07 reste différé : pas d'attribution
par détecteur ni de reconstruction JSON exacte sans nouvelle conception.
Garde les interfaces de projet privées. Ne crée ni commit, ni tag, ni branche
et ne modifie pas tabalyst-studio.
```

### Lot 7.storage-d3: bounded catalogs and generation queries

- Private keyset pages expose complete missing/empty/duplicate memberships,
  frequencies, normalization groups and independently paged variants. Every
  page identifies its pinned generation, Scan/structural scope, configuration,
  exposure and semantic versions. Cursors reject another generation or query
  and remain valid for an old reader or an identical rebuilt materialization.
- The maintainer amended retention on 2026-09-29: the 10,000-value limit
  applies to values actually kept in `project.duckdb`. New database revision
  2 retains the first raw typed analyzable keys per profiled field and counts
  their later occurrences; omitted occurrences are explicit. Record facts and
  memberships remain complete. Revision-1 databases keep their exhaustive
  behavior; Scan JSON and the project manifest format do not change.
- Shared categorization/normalization/exposure run before grouping/ranking.
  Masked collisions merge before ordering; hidden values have no items or
  cursors. Saturated catalogs yield limited pages with retained/omitted
  populations; normalized/masked counts can be lower bounds for the full
  source. Retained catalogs contain no record-to-value mapping.
- Reader/materializer memory and spill budgets are explicit per DuckDB instance.
  Disposable generation caches close before ownership-safe removal. Bounded
  ingestion commits short private batches to release update/delete undo;
  d2's manifest remains the sole publication point. Failures never yield a
  partially built complete query. D07 and D08 remain deferred; all interfaces
  remain private and there is no CLI/API/report/studio change.
- Validation: 1,424 passed, 2 skipped (124 new query/storage-budget tests);
  Ruff and diff whitespace checks passed. Small exhaustive fixtures,
  both JSON backends, all 32 normalization combinations, native/Unicode ties,
  released Scan tables, zero listings, sensitive modes, long values, 10,000
  stored keys, omitted analytical collisions, batch independence, corruption,
  real memory exhaustion and stale cursors are covered. On Windows, the d2
  termination test now waits for process death before closing stdin: closing
  the pipe could otherwise release its commit barrier while termination was
  pending. The three demos were regenerated and all nine original files were
  restored byte-for-byte. Repeated resource results, quota initialization
  probes and a final million-record run with enforced spill are recorded in
  storage section 10.2. All runtime quotas use SET; zero disables spilling.
  Windows file lengths are measured independently of DuckDB accounting.

### Lot 7.storage-e: explicit private query-cache maintenance

Framed on 2026-09-29; the maintainer subsequently requested implementation.
This is a narrow first part of D03, not acceptance of a complete
cache/retention policy. Project-storage.md section 7.1 details its private
ownership/maintenance contract; sections 8.6-8.7 and 9 still govern storage.

**Why next:** d3 disposes each query directory on normal close/failure, but
process termination can leave `cache/<generation_id>/query-*` behind. Its
long-value measurements show materialization files can exceed the committed
database size. An explicit maintenance operation closes that concrete gap
without choosing Explore's stale-source default (D04), exposing projects or
changing Scan's reader contract (D07).

Implementation scope:

- A private cache inventory, dry-run plan and explicit execution boundary,
  with structured candidate/skipped/error results and logical byte counts.
  Missing cache is a normal empty result. Do not promise allocated disk size
  or a hard disk quota. Inventory must not follow links or read raw values.
- Establish durable ownership/version/binding metadata when creating new
  query directories. A `query-*` name, timestamp or PID alone is insufficient
  proof. Unmarked existing caches, unknown files, unsupported metadata and
  links/reparse points are preserved and reported as skipped. Define the
  marker protocol and allowed directory contents in project-storage.md
  before implementing deletion; interruption before the marker is written
  must leave preserved, unclassified evidence.
- Reuse d2's exclusive workspace maintenance lock, then writer lock, for
  execution. Busy readers, materializers, scans or another maintenance
  operation cause an explicit busy result, with no mutation. Unsupported
  ownership/locking primitives disable cleanup. A dry-run is advisory:
  execution re-inventories and revalidates under the locks, including path
  containment and ownership, instead of trusting old paths or byte counts.
- Remove only positively identified disposable query directories inside
  the chosen project's `cache/`, including abandoned caches for an older
  generation. Preserve unknown contents rather than recursively clearing a
  whole cache root. Never touch the source, manifest, committed generations,
  legacy artifacts, index, `.staging`, `.quarantine` or lock files.
- Keep cleanup independent of source freshness and source availability;
  rebuilding queries uses the pinned project storage and the same exposure,
  ordering and cursor semantics. Cleanup is never invoked automatically by
  a scan, an open or a query. Keep all entry points private, without exports,
  CLI, HTTP adapter, report controls or public configuration.

Acceptance before marking e Done:

- Fixtures cover missing/empty cache, marked abandoned directories, unmarked
  legacy directories, unknown contents, invalid/unsupported markers,
  project/generation binding mismatches and symlinks/Windows reparse points.
- Subprocess termination leaves an eligible marked query cache; live reader,
  materializer and writer contention blocks cleanup. A stale dry-run cannot
  delete a replaced/newly active target. Inject deletion failures and retry:
  report partial progress explicitly, preserve project storage and remaining
  evidence, and define marker removal order so retries remain classifiable.
- Hash every persistent project artifact before/after maintenance. Rebuild
  frequency/group/variant pages without the source and compare items, counts,
  exposure, limitations and cursor meaning against the original pages.
  The first-at-most-10,000 raw typed analyzable keys per field, omitted
  occurrences and complete record memberships remain unchanged.
- Run pytest/Ruff and the relevant OS/Python storage CI matrix; record actual
  platform evidence, leaving unexecuted platforms explicitly unverified.
  Regenerate the three demos while preserving their pre-existing bytes.

Separate later decisions: automatic TTL/size quotas/eviction, retention or
deletion of old generations, staging/quarantine disposal, the public
`tabalyst cache` surface (remaining D03), stale-project policy (D04), Transform
history (D02), multi-source identity (D05), richer findings/reconstruction
(D07) and stronger deployment durability (D08). D06/platform evidence remains
to collect; local cleanup tests cannot establish power-loss guarantees.
No Scan/profile/project database revision is proposed. No tabalyst-studio
follow-up is needed while behavior stays private. No commit is created by
this lot; an implementation commit can be prepared after validation.

Implementation starting prompt (lot e, now completed):

```text
Tabalyst Scan, lot 7.storage-e : maintenance explicite des caches de requêtes.
Lis AGENTS.md, README.md, docs/dev/architecture.md, docs/dev/scan/plan.md,
design.md, project-storage.md et docs/dev/progress.md. Reprends le cadrage
proposé de 7.storage-e, précise le contrat de propriété des caches et les
résultats d'inventaire/simulation/exécution avant d'implémenter. Préserve les
modifications existantes. Utilise les verrous de maintenance de d2 ; ne nettoie
que les caches identifiés, jamais les générations ni le stockage persistant.
Pas de TTL/quota/nettoyage automatique ni d'interface publique. Le stockage
reste borné à 10 000 valeurs distinctes brutes typées analysables par colonne.
D07 reste différé. Valide les échecs, les processus interrompus et la
reconstruction sans source ; termine le rituel du lot. Ne modifie pas
tabalyst-studio et ne crée ni commit, ni tag, ni push sans demande explicite.
```

Implementation notes (2026-09-29):

- `projects/_cache.py` implements private immutable inventories/plans and
  per-target cleanup results. New query directories have synchronized
  `.tabalyst-query.json` markers. Execution rejects other project/root plans,
  revalidates file/directory identities and acts only on unchanged candidates
  under exclusive maintenance/writer locks. Unknown/unmarked contents,
  symlinks/reparse points and hardlinks stay untouched. Explicit file deletion
  retains/restores marker evidence on ordinary failures; interrupted final
  marker removal may leave an unmarked empty directory, conservatively skipped.
- `_query_budget.query_directory()` marks before use and validates normal
  teardown after handles close. Empty parents are removed only with unchanged
  identities. There is no new cleanup invocation in scans/opens/queries,
  public adapter/export, automatic policy or project-storage format change.
- `tests/test_project_cache.py` adds 48 cases: 41 pass locally, seven actual
  symlink fixtures lack Windows privileges. The real Windows junction and
  seven reparse-attribute cases pass; remote OS/Python CI remains unverified.
  Killed materializers, live ownership, stale plans, partial deletion/retry,
  unknown/corrupt markers and source-free exposed/limited page/cursor parity
  are covered. Persistent artifact hashes remain unchanged after cleanup.
- Full suite: 1,465 passed, 9 skipped; Ruff/diff checks and browser harness
  syntax pass. Three demos regenerated and nine existing files restored
  byte-for-byte. Manual review completed; `/code-review` is unavailable.
  After final parent-identity hardening, the targeted cache/query/generation
  suite also passes: 213 passed, 7 skipped.
- Local artifact evidence now lives in `D:\GIT.test\tabalyst\artifacts` at
  the maintainer's request; browser captures default outside the repository
  and accept `TABALYST_ARTIFACTS_DIR`. No branch/commit/tag was created.
  Suggested commit, when requested:
  `feat(projects): add explicit owned query cache maintenance`.
- Suggested next conversation: frame D04's private project reopening policy
  (`fresh`/`stale`/`missing`, explicit caller actions and pinned generation
  scope) before its implementation. Keep D07 and public project exposure
  deferred; this does not settle automatic D03 quotas or generation retention.

### Lot 7.storage-f: private project reopening design (D04/S17)

Design only, completed on 2026-09-29 after the maintainer requested the next
step. Proposed contract: project-storage.md section 6.1 (S17). No engine,
service, public API or persistent format change; no contract-test lot enabled.

- f1 inspects/opens one fully verified generation by project id. Proposed
  private default `require_current` refuses stale/missing/failed source
  checks; explicit `snapshot` allows stored-generation queries with the
  corresponding warning. Integrity failures never get a snapshot bypass.
- Assessments bind the pinned manifest, source comparison time and config.
  Source I/O failures remain failures, not a new `SourceState`. No requested
  config means the recorded config; a complete explicit ScanConfig mismatch
  blocks both opening intents. Adapter/file-layer merging is out of scope.
- A check is a point-in-time O12 fact, not continuous source validity. Refresh
  compares the same pinned scan. No index lookup/repair, automatic scan,
  project creation or legacy upgrade occurs during read-only opening.
- f2 is separate because `publish_scan()` currently selects a project via
  source/index lookup. An explicitly selected project requires a target id
  and generation precondition checked under writer ownership. New-reader
  opening after publication must also reject an intervening manifest change.
- S17 remains Proposed for the implementation gate; the product default of
  D04 remains deferred. D07, public project interfaces, automatic D03 policy,
  history/version comparison and source relocation stay out of scope. The
  10,000 stored-key bound remains unchanged.

### Implementation lot 7.storage-f1: pinned inspection/open sessions

Implemented on 2026-09-29 after the maintainer requested f1, accepting S17's
read-only boundary. Private `_session.py` supplies `inspect_project()`,
`open_project()`, immutable `SessionAssessment` and owned query contexts.
Structured source warnings are `source_stale`, `source_not_checked` and
`source_check_failed`; `config_mismatch` blocks both intents. Changed selection
raises `GenerationConflictError`; readiness refusal includes its assessment.
Legacy/integrity failures keep `open_generation()`'s fail-closed semantics.
Explicit refresh updates facts about the pinned generation, preserving old
assessments and cursors; readiness gates entry, not ongoing snapshot queries.
Session teardown closes outstanding materializations before the pinned reader.
Existing low-level readers, public exports, formats and value caps are unchanged.
f2 still requires its own design/implementation gate. Storage-platform CI now
includes the session tests; remote results have not been observed locally.
Validation: full pytest suite 1,496 passed / 9 skipped; 31 focused session tests
passed again with explicit exclusive-maintenance lock-release assertions.
Ruff passed. All three demos regenerated and nine pre-existing outputs restored
byte-for-byte. Tests used external OS temporary paths (architecture.md); no
repository artifacts or studio changes. No branch, commit, tag or push.

The original implementation scope and acceptance requirements follow:

Implement only after accepting/amending S17. Use a private session module
above `_generation`/`_queries`; do not export it from `tabalyst` or projects.
Keep low-level `open_generation()` semantics unchanged for current consumers.
Add immutable assessment/warnings and context-managed sessions, reusing
`compare_source` against the already pinned manifest/Scan. Implement the
source/config readiness matrix, explicit assessment refresh, deterministic
refusal and resource release. Do not implement f2's publisher mutation yet.
Opening after a closed inspection rechecks its own pinned generation and
supports an optional expected-generation precondition for that earlier decision.

Acceptance matrix is in storage section 6.1. In particular, prove no scan,
publication/index mutation or persistent hash changes; source I/O errors must
not become missing/fresh, and a rescan between pinning and assessment must
not mix generations. Tests cover settings mismatch, legacy/corruption,
mask/hide/show and saturated catalogs. Run pytest/Ruff, regenerate demos and
restore pre-existing outputs, and extend storage-platform CI without claiming
remote results. Keep pytest/benchmark evidence under the external artifact
root (`D:\GIT.test\tabalyst\artifacts` locally), never recreate repository
`artifacts/`. No branch/commit/tag/push or studio changes without a request.

Suggested fresh-session prompt:

```text
Tabalyst Scan, lot 7.storage-f1 : inspection et réouverture privées d'un projet.
Lis AGENTS.md, README.md, docs/dev/architecture.md, docs/dev/scan/plan.md,
design.md, project-storage.md et docs/dev/progress.md. Reprends la proposition
S17 (section 6.1) et précise les modèles d'assessment/session avant de coder.
Préserve les modifications existantes. Une session reste liée à sa génération
vérifiée ; require_current refuse stale/missing/failed, snapshot est explicite
avec avertissements. Compare la configuration complète à celle du scan épinglé.
Pas de rescan automatique, de mutation d'index ni d'interface publique. f2 reste
séparé. Le stockage garde au maximum 10 000 valeurs distinctes brutes typées
analysables par colonne ; D07 reste différé. Place les artefacts de tests dans
D:\GIT.test\tabalyst\artifacts et termine le rituel sans commit ni push.
```

## Notes

Lots record here what remains when a conversation stops before the lot is
done, and anything the next lot must know.

- Lot 0: the current report engine resolves date ambiguity from evidence in
  the same column; Scan exposes that evidence without applying it (design
  section 12.6). Lot 5a must decide how the report presents it.
- Lot 1b, for gate 1 (the maintainer validates or amends):
  - Provisional choices of lot 1a: the `name` of an items field is `"[]"` and
    of the root field `"$"`; `missing.components.absent` is `null` for items
    fields and counts as 0 in `missing.count`; a field's `parent` is `null`
    for top-level fields even when the root field is listed;
    `RecordExcluded.index` counts every record read, so indices of analyzed
    records have gaps after exclusions.
  - Decided with the maintainer during lot 1b: duplicate keys make a record
    malformed (fatal, or `duplicate_key` exclusion); a UTF-8 byte order mark
    is accepted and reported as `utf-8-sig`.
  - Lot 1b choices: JSON `element` locations are 0-based; the `max_fields`
    lower bound is `max_fields + 1`; `max_record_observations` counts emitted
    observations only; explicit collections are always listed, with
    `json_collection_not_found` when absent; `DatasetOpened.container`,
    `Record.depth_truncated` and `Notice` extend the reader contract.
  - Still open: the CSV reader keeps the default `csv.field_size_limit`
    (131,072 characters), so a longer cell is a fatal quoting error, and JSON
    strings have no length bound while reading. Recommendation: one bounded,
    configurable `limits.max_value_length` shared by CSV and JSON (fatal, or a
    `value_too_long` exclusion under the tolerant policy) rather than raising
    the process-wide `csv` limit.
- Lot 1b, for lot 2a, settled in lot 2a: a lone surrogate escape (the JSON
  text `"\ud800"`) makes the source invalid. The pure-Python backend is
  checked by the reader; the compiled backend rejects lone low surrogates and
  replaces lone high ones with `"?"`, a documented limitation (design 5.2).
- Found in lot 2a, fixed in lot 4: the compiled `ijson` backend crashes the
  Python process (access violation on Windows) on a JSON integer of more than
  4,300 digits, Python's `sys.int_max_str_digits` limit, when it is a scalar
  document or crosses a read buffer; elsewhere it raised a bare `ValueError`.
  The reader now finds such digit runs before parsing (about 800 MB/s) and
  parses those files with the pure-Python backend (design 5.2). Reporting the
  crash upstream is still worth doing.
- Lot 2a, for lot 2b:
  - `normalization.py` already computes the analytical value (`nfc`, `trim`,
    `collapse_whitespace`); lot 2b adds the stage counters, stage
    cardinalities and variant groups. The value tracker (`values.py`) computes
    per-value facts once per distinct value while the table is complete, then
    per occurrence through a bounded cache after release: stage change
    counters should be facts too, so they continue after release.
  - `measures_limited` looks at `values.cardinality` and `numeric`; add the
    normalization envelopes when they exist.
- Lot 2b, for later lots:
  - Facts now carry the normalization changes and the output of every stage
    (`measures.Facts`, positions `CHANGES` and `FORMS`; the streaming cache
    drops the stage outputs). Detectors of lot 3a receive the
    analytical value; stage outputs are available if a detector needs the
    comparison key.
  - Variant groups hold raw values: lot 3b must pass them through the
    exposure gate of sensitive fields (design 12.8).
  - `measures_limited` now also looks at `normalization.variant_groups`.
  - Stage cardinalities of a complete table reuse the previous count when a
    stage changed nothing, and only build sets from changed strings; variant
    groups are built from changed strings only.
- Lot 3a, for gate 3 (the maintainer validates or amends; design 9.7,
  12 and 12.10):
  - Numbers: the strict rule wins, so `1.234` is 1.234 and never ambiguous,
    while `1,234` is ambiguous between `dot` (1234) and `comma` (1.234);
    `12,5`, `1.234,5` and `1 234` match one reading. Formats use
    spreadsheet notation (`0`, `0.0`, `0E0`, `#,##0.0`, `0,0`). Risk found
    in review: European thousands such as `1.500` (1500) are silently read
    as 1.5, even beside comma evidence such as `12.500,50`. The alternative
    is to make a strict decimal with exactly three decimals ambiguous when
    the comma convention is enabled, which changes lot 2a results for such
    values.
  - Dates: numeric dates of the current engine, ISO date-times and times,
    English and French month names; `ambiguity.count` includes values
    resolved by configuration, `coverage.ambiguous` only unresolved ones.
  - Technical type: families from the number and date detectors, textual
    booleans limited to `true`/`false`; a date column with several formats
    is `date` (the current engine says `mixed`, lot 5a decides);
    `confidence` is `null` for `empty`, `outside_count` `null` for `mixed`.
  - Boolean pairs by default `true/false`, `yes/no`, `y/n`, `oui/non`,
    `vrai/faux`, as an interpretation only.
  - Enumeration is a field-level detector: all values match or none; it
    counts eligible values, not rows, and overlaps other interpretations.
  - Every registered detector is listed per field (`complete`,
    `not_applicable`, `disabled`, `failed`); failures keep the exception type
    only; evidence has four keys.
- Lot 3a, for lot 3b:
  - Detectors live in `scanner/detectors/`: `base.py` (contract,
    `AmbiguityAccumulator`), `registry.py` (`DetectorRegistry`,
    `DetectorSet`, `DetectorTally`), `shape.py`, one module per built-in.
    `DetectorSet.classify` runs every active detector on each distinct value
    and returns one entry per detector; facts carry it at position
    `CLASSIFICATIONS`, the technical family at `FAMILY`.
  - The pattern detector can declare `max_input_length` (values above it are
    `not_tested`) and `shapes`. Pattern ids must not collide with the
    built-in ids `number`, `date`, `boolean`, `enumeration`.
  - Evidence examples, the `enumeration` accumulator and boolean details hold
    analytical values: the exposure gate must cover `detectors[].evidence`
    and any value-bearing `details`.
- Lot 3a, open points found in review:
  - Detectors added with `registry.register()` cannot be configured or
    disabled: `DetectorSettings` rejects unknown ids (O13). To settle with
    patterns (3b) or plugins (7), for example a `detectors.<id>` mapping
    validated against the registry.
  - `DetectorSet` finds the number and date detectors by id, and the
    `temporal` block through the date accumulator's `temporal()` method: a
    replacement `date` detector without it gives `temporal: disabled`. A
    declared capability would remove the special case.
- Lot 3b, first session, for the catalogue sessions:
  - Write the family's entries in `detectors.md` first (template at its top),
    then one module per detector in `scanner/detectors/`, added to
    `BUILT_INS` in `registry.py` and with a settings class in
    `DetectorSettings` (`config.py`) when it has parameters. Parallel sessions
    touch the same two lists: merge conflicts there are expected and trivial.
  - Tests go to `tests/test_scanner_<family>.py` (positive, negative, variant
    and overlap values, and exposure for sensitive detectors); there is no
    catalogue contract test file.
  - Declare `shapes` and `max_input_length`: the per-value cost of lot 3a is
    already a concern (lot 3a note for lot 6).
  - `details(gate)` receives the exposure gate: pass any value it carries
    through `gate.value`, `gate.counts` or `gate.examples`.
  - Enabling a detector by default adds an entry to every field and to
    `engine.detectors`; check the demos still regenerate.
- Lot 3b, for the maintainer (decided in the first session, design 12.8):
  a failed sensitive detector makes its field sensitive; under `mask`,
  listings describe the masked values (equal masks merge before ranking and
  sampling, `frequencies.distinct` counts masks, variant groups merge by
  masked key); under `hide`, listings are empty and `first` and `last` are
  `null`. Found in review: under `mask` and `hide`, `numeric` and `temporal`
  of a sensitive field are `disabled`, since their minimum, maximum, median
  or date range are values.
- Lot 3b, email and URL session, for the other catalogue sessions and the
  maintainer:
  - Prefer an exact cheap check (a required character, the first character)
    to `shapes`: on the 100,000-row benchmark file, shapes on both detectors
    cost about 30% more time, a `"@" in value` and first-character check
    about 8%, because the signature is computed for nearly every value. The
    note of the first session ("declare `shapes`") is amended in
    `detectors.md`.
  - `detectors/names.py` holds the domain name rule and `NameCounts`, the
    counted names block of `details` (`email` domains, `url` hosts), with its
    own `max_tracked_*` and `max_listed_*` settings. Reuse it for any
    detector that counts parts of values.
  - The demo `courriel` column has 12 deliberately mistyped addresses (a space
    inside); the candidate rule excludes only characters that mark URLs,
    display names and address literals, so they are `invalid`, not
    `not_matched`.
  - For the maintainer: every field where `email` matches is sensitive, so by
    default its domains are listed as masks (`aaaaaaa.aaa`), which makes them
    useless; exempting them would amend design 12.8. `url` is not sensitive
    although query strings may carry tokens. URLs with `{`, `|` or spaces are
    `invalid` (strict RFC 3986).
- Lot 3b, phone session, for the other catalogue sessions and the
  maintainer:
  - Canada and the United States share one numbering plan that syntax cannot
    tell apart, so they form one region, `nanp`; numbers of other countries
    are `not_matched`, not `invalid`.
  - A value made of digits only is `matched` when valid and `not_matched`
    otherwise, never `invalid`, so that numeric identifier columns are not
    reported as invalid phones. Postal and ZIP codes face the same question
    (`12345` in an identifier column).
  - The detector has no `max_input_length`: values outside the length and
    digit-count bounds of the accepted forms are rejected exactly as
    `not_matched`, since `not_tested` would claim that long text values might
    be phones. A detector whose accepted forms have a short maximum length
    should do the same.
  - Cost: `classify` over the 925,549 distinct values of the 100,000-row
    benchmark file takes about 0.45 s; the whole scan is about 8% slower
    with values shown, a little more under `mask` since the benchmark
    `phone` column becomes sensitive. A no-op detector alone costs about 3%
    (per-detector tally work, lot 3a note for lot 6).
  - Bare NANP numbers (`5145550100`) are also integers for `number`, so such
    columns have no primary interpretation; under `mask` their `numeric`
    block is `disabled` since the field is sensitive.
- Lot 3b, postal code session, for the other catalogue sessions and the
  maintainer:
  - One detector, `postal_code`, with regions `ca` and `us`, as `phone`
    does; the forms never overlap. Rejection by length (5, 6, 7 or 10
    characters) then first character is exact and cheap: `classify` over the
    925,550 distinct values of the 100,000-row benchmark file takes about
    0.4 s, the whole scan about 7% more (noisy measure).
  - Not sensitive, a decision for the maintainer: a postal code is a
    quasi-identifier (a Canadian code covers a few dozen households), but
    since every five-digit integer is ZIP syntax, a sensitive detector would
    mask identifier columns and disable their `numeric` block. A sensitive
    pattern can flag postal codes where needed.
  - ZIP codes are never `invalid` (any five digits are syntax; `00000` is a
    real-world check), consistent with the digits-only rule of `phone`. A
    column of five-digit integers lists `number` and `postal_code` and has
    no primary (CA10); ZIP codes with a leading zero are not numbers.
  - Canadian codes are `invalid` only for letters Canada Post excludes
    (`invalid_first_letter`, `invalid_letter`); hyphenated (`H2X-1Y4`) and
    truncated values are `not_matched`. The demo `code_postal` column has 21
    truncated or shortened codes (`T3A 95`, `J1 5M4`), `not_matched`, and its
    double spaces are collapsed by the analytical value.
- Lot 3b, currency and percentage session, for the other catalogue sessions
  and the maintainer:
  - Three detectors share `detectors/amount.py`: the number part is read by
    a `NumberDetector` built from each detector's own `conventions` and
    `ambiguous_convention` (independent of `detectors.number`), with the sign
    outside the number part and no exponent. An amount-shaped part that
    `number` rejects is `invalid` (`invalid_amount`, `invalid_number`),
    except digits only (`01 m`, `01A`, `05%`), which are `not_matched` like
    the digits-only rule of `phone`; a number part needs a digit, so `.com`
    is not a quantity (both found in review). Inherited risk of gate 3:
    `1.234 €` is 1.234, never ambiguous.
  - A marker is required: a bare number is never a currency amount,
    percentage or quantity, so the three never overlap `number`, nor each
    other (currency codes and ordinals are not units).
  - For the maintainer: currency codes are a fixed ISO 4217 list (current
    codes plus `ANG`, `BGN`, `HRK`, `SLL`, `ZWL`), to update when ISO
    replaces a currency; a configurable `codes` setting is an option.
    Accounting negatives in parentheses (`($1,234.56)`) are accepted.
  - `quantity` is generic, as decided with the maintainer: any one-token unit
    of letters, `°`, `²`, `³`, `/` and `·`, kept as written (`Mo` and `mo`
    differ). Formats use the placeholder `[unit]` so they stay bounded;
    units are a counted names block, through the exposure gate. `12 ans`,
    `3 pommes` and codes such as `12B` or `2A` are quantities. Known units grouped by dimension (data size,
    length, mass, time) are left to a later catalogue wave (lot 7).
  - The field's `numeric` block does not include amounts, percentages or
    quantities (design 9.4); lot 5a decides whether the report needs them.
  - Cost: `classify` of the three detectors over the 988,148 distinct values
    of the 100,000-row benchmark file takes about 0.57 s in total; the whole
    scan is about 7 to 15% slower (noisy), mostly the per-detector tally work
    of the lot 3a note for lot 6. No value of the insurance demo matches.
- Lot 3b, UUID and IP address session, for the maintainer and later lots:
  - `uuid` accepts the hyphenated, braced and `urn:uuid:` forms, with a case
    suffix in the format (`hyphenated_upper`, `braced_mixed`). A candidate is
    `invalid` only for a letter beyond `f`; version and variant are counted
    in `details.versions` (`"4"`, `"7"`, `"nil"`, `"max"`, `"other"`), never
    validated, so generated test values such as
    `12345678-1234-1234-1234-123456789012` still match. 32 bare hexadecimal
    digits are `not_matched`: syntax cannot tell them from an MD5 hash (a
    hash detector belongs to a later wave).
  - For the maintainer: `uuid` is not sensitive (a record identifier, like
    `CLI-00000281`), `ip_address` is (personal data in several
    jurisdictions, like email and phone). Consequences: columns of
    four-part version numbers (`1.0.0.12`) are IPv4 syntax and become
    sensitive; IPv4 addresses whose last three groups have three digits
    (`192.168.100.200`) are also numbers under the `comma` convention, so
    such columns have no primary and, under `mask`, no `numeric` block.
  - The IPv6 candidate is narrow on purpose: `::` or at least eight groups,
    so times (`22:00:00`) and MAC addresses (`00:1A:2B:3C:4D:5E`) are
    `not_matched`, never `invalid`; EUI-64 identifiers in eight colon groups
    are IPv6 syntax. Prefix lengths, ports, brackets, zone indices and IPv4
    shorthands are not accepted in version 1; network ranges (CIDR) are a
    candidate for a later wave.
  - Cost: `classify` over the 988,150 distinct values of the 100,000-row
    benchmark file takes about 0.25 s for `uuid` and 0.36 s for
    `ip_address`; the whole scan is about 5 to 8% slower (noisy). The
    benchmark `customer_uuid` and `ip` columns get `uuid` and `ip_address`
    as primary interpretations. No value of the demos matches.
- Lot 3b, for lot 4: the scanner now has thirteen built-in detectors besides
  patterns; the configuration reference of lot 4 documents each
  `detectors.<id>` section from design section 15 and `detectors.md`.
- Lot 3b, still open: the O13 point of lot 3a (detectors added with
  `register()` cannot be configured) is not needed by patterns, which have
  their own `patterns` section; it stays for the catalogue or lot 7.
- Lot 3a, for lot 5a: the number detector extends the numeric population of
  string fields (decimal commas, grouped thousands), as in the `amount_fr`
  column of the benchmark file; the demos have no such column. The date
  fields of `insurance-customers` hold ambiguous numeric dates, so their date
  detector share stays below 0.95 and they have no primary interpretation,
  while their technical type is `date`: the report must decide how to show
  that ambiguity (design 12.6).
- Lot 4, for gate 4 (the maintainer validates or amends before release):
  - Decided with the maintainer: no automatic `tabalyst.json`; one
    configuration file for every command, with scan settings in a `scan`
    object that every command validates; the scan does not inherit the
    top-level `csv` settings. In phase 5 the report settings are restructured
    around `ScanConfig` (design 15); the top-level `csv` duplication disappears
    then.
  - Lot 4 choices: `--config` is repeatable for `scan` only (the other commands
    keep one file); `scan` has `--delimiter` and `--encoding` like the other
    commands although the plan listed only `--collection`; a partial scan exits
    0 with a warning even under `--quiet`; a scan output can never replace a
    configuration file; `-d` defaults to `<stem>.scan.json`, so `data.csv` and
    `data.json` in one batch collide and the batch is rejected.
  - `report` and `sample` now share `batch.py` (same messages); report
    artifacts still use plain writes, not the atomic helper.
  - The JSON pre-pass reads each JSON file twice when the compiled backend is
    installed (design 5.2 allows two passes); about 0.05 s for 44 MB.
  - Release preparation, not done in lot 4: version bump, release notes in
    `docs/dev/releases/`, the `engine.version` example of the scan format page
    (`0.4.0`) to align with the released version, the French pages (lot
    4-fr), and in `tabalyst-studio` a mention of `tabalyst scan` on the site
    and the new documentation pages (`how-to/scan-files`,
    `reference/scan-format`, `reference/scan-format-changelog`).
  - Still open for gate 4: the `max_value_length` question of gate 1 (a CSV
    cell above 131,072 characters is a fatal quoting error; JSON strings are
    unbounded while reading) and O13 for detectors added with `register()`.
- Lot 2a, still open with the `max_value_length` question of gate 1: `first`
  and `last` keep whole values, even beyond `max_stored_value_length`.
- Lot 1a, for lot 6: indicative measure, not a benchmark row: 1 million rows
  of `synthetic-1m.csv` in about 13 s with 77 MB peak memory, counters only.
  Each cell creates one `Observation`; a CSV fast path is an option for lot 6.
- Lot 2a, for lot 6: indicative measure, not a benchmark row: 1 million rows
  of `synthetic-1m.csv` in about 40 s with value measures (13 s with counters
  only in lot 1a), 100,000 rows in about 4 s. Most of the time is per-distinct
  facts of high-cardinality columns (characteristics, analytical value, number
  parsing). The global budget finds the largest table by scanning the fields,
  O(fields) per release.
- Lot 2b, for lot 6: indicative measure, not a benchmark row: the 100,000
  rows of `synthetic-100k.csv` in about 4.3 s, against 4.15 s after lot 2a.
  Most of the added work is `casefold` and `strip_accents` per distinct value;
  `strip_accents` calls `unicodedata.category` per character, a candidate for
  a fast path.
- Lot 3a, for lot 6: indicative measure, not a benchmark row: the 100,000
  rows of `synthetic-100k.csv` in about 7.4 s, against 4.6 s before lot 3a on
  the same machine. About 990,000 distinct values are classified by four
  detectors; the costs are the per-value loop of `DetectorSet.classify`, the
  number detector on digit-leading values (phones, IP addresses, amounts),
  `Decimal` parsing, and one `DetectorTally.add` per detector and distinct
  value. Candidates: dispatch by first character, skipping detectors a
  cheap check rules out, and batching tallies.
- Lot 5a, for lot 5b:
  - The report shows one semantic type per column (the primary
    interpretation) and `limited_measures` / `excluded_records` issues as a
    stopgap; detectors, formats, normalization variants (NFC changes
    included), limits and structure sections are lot 5b.
  - JSON sources are rejected by `analyze_csv()` with an `InputError`;
    `build_profile()` assumes one CSV dataset (`rows`).
  - The tooltip of a masked column shows sampled masks against the raw
    distinct count (`100 / 2,992`), and a complete masked listing shows no
    `+N`: a dedicated presentation of masked values may be better.
  - `executions.json` still records `rows` and `columns` only; scan status and
    `config_sha256` could join it.
- Lot 5b, for later lots:
  - Deferred by the maintainer: report sections for normalization variants
    (stages including NFC, variant groups), limits (limited or not tested
    measures, dataset envelopes, scan diagnostics) and JSON structure
    (collections, record types, depth, presence per parent, array lengths).
    They need a lot of their own (Opus 5.5 or Sonnet 5, medium).
  - `tabalyst report` has no `--collection` option; collections come from
    `scan.json.collections` in a configuration file.
  - JSON record facts ignore absent fields: `rows_with_missing` and empty
    records count nulls and missing strings only, while column missing counts
    include absent members.
  - Overview labels still say rows and columns for JSON datasets.
  - `executions.json` records the sums of rows and columns over datasets.
  - `tests/browser/report.cjs` checks the first dataset of a profile; the
    multi-dataset view was checked with an ad hoc script (selector, prefixed
    ids, no horizontal overflow at desktop and mobile sizes).
  - `tabalyst-studio` follow-up: `report.json` is revision 4 (the site reads
    `examples/output/insurance-customers/`), the new detectors section, the
    new `orders` demo and the new how-to page `how-to/report-json-files`.
  - French documentation: the pages changed by lot 5b (`index`,
    `reference/known-limitations`, `reference/json-profile`,
    `reference/profile-format-changelog`, new `how-to/report-json-files`).
- Lot 5a, for lot 5c and gate 5:
  - The pandas engine remains only for `analyze_column`, `tabalyst.AnalysisConfig`
    (alpha compatibility exports), `tests/test_analysis.py`, the parity half of
    `tests/scan/test_scan_report.py` and the `pandas-engine` benchmark task:
    `analysis.py`, `ingestion.py`, `legacy_models.py` and the `AnalysisConfig`
    classes of `config.py` (`NormalizationConfig`, `TypeInferenceConfig`,
    `EnumDetectionConfig`, `ValueExamplesConfig`) go with it.
  - `RowFacts` keeps one 16-byte digest per distinct row for duplicates: the
    only record-level state that grows with the file. A report reusing a scan
    (`--scan`) has no records: duplicates, empty rows, rows with missing values
    and the preview must then come from the scan document or a second read.
  - Measured on `synthetic-100k.csv` (benchmarks.md, lot 5a): the report on
    Scan takes about 45% more time than the pandas engine, with about 40% of
    its memory growth. Lot 6 sets targets.
- Lot 5a, for the maintainer and release preparation:
  - Breaking changes for users: configuration keys moved to `scan` (clear
    error messages), profile revision 3, masked emails and phones in reports,
    `date` instead of `mixed`, `enumeration` instead of `enum`. The release
    notes must say so.
  - `tabalyst-studio` follow-up: the insurance demo changed (masked
    `courriel` and `telephone`, `date` types, `ambiguous_dates` issue, new
    semantic types, resampled examples); `examples/config.json` has the new
    structure; the configuration, JSON profile, profile changelog, known
    limitations and glossary pages changed.
  - The browser check needs the Playwright Node module; lot 5a installed it
    outside the repository for the session.
- Lot 5c, for lot 6 and the maintainer:
  - Indicative measures, not benchmark rows, `synthetic-100k.csv`: the report
    takes about 13.7 s (13.2 s in lot 5a) with 226 MB peak memory (269 MB in
    lot 5a, pandas no longer imported); a scan takes about 13.2 s with
    duplicate detection and 11.8 s without (about 12%). The digest is built
    from `repr()` of the observations: a cheaper key (CSV rows by position)
    is a candidate for lot 6. A stored digest costs about 83 bytes, so the
    default budget of 2,000,000 records is about 165 MB at most.
  - `tabalyst scan` documents now hold a preview of 10 records by default,
    raw values of non-sensitive fields included, as samples and first values
    already did.
  - Report planning with `--scan` reads each scan document to name its
    outputs, then reads it again to build the report (found in review; kept,
    a candidate for lot 6). An unreadable document fails its own job only.
  - Found in review and fixed: scans written with `-d` elsewhere have no
    source beside them, so their staleness cannot be checked; the command
    now warns. Recording the source path relative to the scan document would
    let the check follow them: a decision for the maintainer (format
    revision 3).
  - `on_record` of `scan()` stays in the API but the report no longer uses
    it.
  - Still open from lot 5b: `executions.json` records sums over datasets
    (the report sections were done by lot 5d).
- Lot 5d, for later lots and the maintainer:
  - The "Case folded" stage changes almost every value of identifiers and
    capitalized names, so its column is mostly full; it is exact, but a
    presentation that highlights stages that change the distinct count may
    read better.
  - Datasets without columns (a `$` whose values all lie in collections) are
    still omitted, so their structure, including the promoted array, is not
    shown; the collection's own view shows its records.
  - Scan-wide diagnostics (`global_budget`, `record_budget`) appear in every
    dataset view.
  - `tests/browser/report.cjs` now checks the variant, structure and limits
    tables of the first dataset; the limits and structure sections were
    checked with an ad hoc JSON file under small limits at desktop and mobile
    sizes (no demo reaches a limit).
  - `tabalyst-studio` follow-up: `report.json` is revision 6 (the site reads
    `examples/output/insurance-customers/`), the insurance demo shows the
    extended Transformations section with 74 variant groups; pages changed:
    JSON profile, profile changelog, known limitations, configuration,
    how-to report JSON files, first-report tutorial.
  - Release notes: profile revision 6 (additive, apart from the revision
    number), new report sections.
  - `tabalyst-studio` follow-up: `report.json` is revision 5 (the site reads
    `examples/output/insurance-customers/`), `examples/config.json` moved
    `preview_rows` to `scan.records.preview`, the report can be built from a
    scan (`--scan`); pages changed: how-to scan files, configuration, JSON
    profile, profile changelog, scan format and its changelog, known
    limitations, glossary.
  - Release notes: breaking changes for users are `preview_rows` moved to
    `scan.records.preview`, profile revision 5, scan format revision 2, the
    removal of `tabalyst.analyze_column` and `tabalyst.AnalysisConfig`, and
    no pandas dependency.
- Lot 1b, for lot 6: indicative measure, not a benchmark row: 200,000
  records of 25 MB of JSON (about 11 observations each) in about 2.5 s with
  about 1.3 MB of traced peak memory, compiled `ijson` backend, counters only.
- Lot 6, second session, for the maintainer and later lots:
  - Where the time went: the rules were cheap, the calls were not. Per
    distinct value, 13 `classify` calls and 13 tally updates cost about 10
    microseconds; skipped detectors still cost their bookkeeping. Batches
    make a skipped detector free and an unmatched value a C-level test in a
    list comprehension.
  - The rare rule was first written without the second-half condition: on
    the benchmark, the sorted `id` column crosses from 4 to 5 digits at
    10,000, so `postal_code` reacted once in the warm-up and then matched 90%
    of the column, all skipped. Keeping detectors that react in the second
    half fixed it; the corpus shows no difference with `rare_share` 0. The
    rule saves little time once detectors are batched: it mostly drops
    patterns and detectors whose early matches were noise.
  - Workers: the scan process reads, counts columns, and computes record
    digests, about 10 microseconds per row of 20 columns; beyond 4 to 8
    workers it is the bottleneck (1M rows: 11.5 s with 4 workers, 11.3 s
    with 16). The automatic count is capped at 8: each worker costs about 60
    to 80 MB. Reading one source with several processes needs mergeable
    tables, samples, first-seen orders and duplicate digests: a lot 7 design.
  - Each worker is a `python -c` subprocess importing Tabalyst through the
    scan process's `sys.path` (`TABALYST_WORKER_PATH`), not `multiprocessing`,
    so an unguarded caller script is never imported again. Frozen
    applications and custom registries stay in one process.
  - The JSON reader now shares one path object per logical path: the engine
    looked paths up by identity, which always missed, and hashed each
    dataclass segment in Python. JSON consume time halved; the rest is the
    event loop and the per-observation engine, which could batch records by
    field like CSV columns.
  - French pages to update, with lots 5c-fr and 5d-fr: `how-to/scan-files`
    (large files, `--workers`), `reference/configuration`
    (`detection.rare_share`), `reference/known-limitations`,
    `reference/scan-format`, `reference/scan-format-changelog` (revision 4),
    `reference/json-profile` and `reference/profile-format-changelog`
    (revision 8).
  - `tabalyst-studio` follow-up: `report.json` is revision 8 (the site reads
    `examples/output/insurance-customers/`), the report's analysis settings
    mention rare detectors, the report uses up to 1,760 px of width,
    `--workers` is a new option of `scan` and `report`.
  - Released as 0.4.2 (`docs/dev/releases/0.4.2.md`).
- Lot 7.storage, for its implementation lot:
  - `platformdirs` was accepted by the maintainer in lot 7.storage-a and is
    now a runtime dependency (`platformdirs>=4`).
  - Settled in 7.storage-b: `scan_reuse.check_source` keeps the beside-source
    lookup, while `compare_source` provides the shared comparison for a
    project source resolved from `project.json` (project-storage.md section 6).
  - D01's detailed design is now in project-storage.md sections 8-10
    (7.storage-c); implement only after its gate. S07's initial independent
    DuckDB-reader proposal is superseded by the shared observation stream.
  - No default behavior is chosen yet for reopening a project whose source
    changed (D04, PROJ-04): unlike `tabalyst report --scan`'s hard failure,
    this is likely a per-session UX choice for Explore, not a scan-engine
    concern.
- Lot 7.storage-a, for the next implementation lot and the maintainer:
  - The example `project_id` of project-storage.md section 5 was not a valid
    ULID (it contained `U`, which Crockford base32 excludes); corrected.
    `is_project_id()` checks the exact form and `StorageLocation.project_dir()`
    refuses anything else, so a directory name never selects a path.
  - Storage root: `TABALYST_HOME` overrides the platform directory (tests,
    servers); it is added to project-storage.md section 3. `platformdirs`
    keeps the case of the application name, so Linux uses `tabalyst` (as the
    design says) and Windows and macOS `Tabalyst`, chosen in `location.py`.
    The `platformdirs` handling of the Microsoft Store Python redirection of
    `%LOCALAPPDATA%` is relied upon, not tested here.
  - `projects/index.json` has its own format (`tabalyst.project-index`,
    revision 1) and keys are `batch.path_key` (resolved, `normcase`d: lower
    case with backslashes on Windows, so keys are not portable between
    machines, which is fine for a reconstructible local file).
    `find_project()` trusts an entry only when its `project.json` confirms the
    path; otherwise (missing, corrupt or stale entry, missing index) it
    rebuilds the index once from `projects/*/project.json`, so an unknown path
    costs one listing of the workspace and writes nothing (stored paths are
    already resolved, so keys of stored paths need no file access). Several
    projects for one path keep the most recently created on rebuild (`created_at`,
    then id, since ULIDs of one millisecond are not ordered); `create_project()` always
    creates and makes its project the entry of its path. No lock (section 4).
  - `create_project()` writes `project.json` before the index, so an
    interrupted creation leaves at worst an unindexed project that the next
    lookup finds; a failed first write removes its empty directory.
    `list_projects()` skips directories whose `project.json` is missing or
    invalid without reporting them: a `tabalyst project` diagnostic command
    would need a reporting variant.
  - The workspace check is duplicated on purpose: `read_project()` refuses a
    document whose `project_id` differs from its directory name or whose
    `workspace_id` differs from the location's (a copied file must not pass
    for another project); `write_project()` refuses another workspace.
  - Settled in lot 7.storage-b: the shared source comparison (S09) and the
    layer that runs `scan()` and writes `scan.json` into the project directory.
    Left for the next lots: `project.duckdb` implementation (D01 detailed
    in 7.storage-c) and any CLI surface.
  - `tabalyst-studio` follow-up: none, nothing public changed; the new runtime
    dependency `platformdirs` matters for packaging and the release notes only
    when a feature uses the storage.
- Lot 7.storage-b, for the next implementation lot and the maintainer:
  - `project_scan_service.py` deliberately stops after `scan.json`; D01 is
    now detailed by 7.storage-c. The next implementation must replace the
    separate scan/metadata publication with S14 before exposing a database.
  - `project_freshness()` returns the three-way fact `fresh`, `stale` or
    `missing`. D04 remains deferred: an Explore interface, not this storage
    service, will decide whether a stale source is reused, rescanned, compared
    or versioned.
  - There is still no CLI or public Python API and therefore no
    `tabalyst-studio` follow-up.

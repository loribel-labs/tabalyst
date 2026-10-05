# Development progress

## 2026-10-04 (Excel review fixes)

- Fixed five findings of the review of the Excel lots (corrupt sheets in
  Inspect, `header_row` seed, Excel lock files in patterns, hash of the parsed
  bytes, Inspect file of another kind), with tests in
  `tests/inspect/test_excel_review.py`.

## 2026-10-04 (Excel lot X-4)

- Documented Excel support for the public site and the README (new Inspect and
  Report pages, formats, configuration, limits), added the `sales.xlsx` demo,
  regenerated all demos. Report profile revision 11 (`encoding` null for
  workbooks). A stored scan of an older format is now replaced by the shared
  cache instead of stopping `report`. Details in `docs/dev/inspect/excel.md`.

## 2026-10-04 (Excel lot X-3)

- `scan` and `report` read `.xlsx` and `.xlsm` workbooks: typed Excel reader,
  `scan.excel` settings, resolution layers and detection cache shared with the
  JSON parcours, `--collection` for a sheet or table. Scan format revision 6.
  Public docs and changelogs are lot X-4; details in
  `docs/dev/inspect/excel.md`.

## 2026-10-04 (Excel lot X-2)

- Added Excel Inspect (`tabalyst inspect` on `.xlsx` and `.xlsm`): kind `excel`,
  one candidate per sheet and per named table, header detection, selection
  with the JSON rules, warnings, visible file and re-inspection. Provisional
  parameters on synthetic workbooks; details in `docs/dev/inspect/excel.md`.
  Scan and report of workbooks are lots X-3 and X-4; the public docs and
  format changelog follow in X-4.

## 2026-10-04 (Excel lot X-1)

- Excel support framed in `docs/dev/inspect/excel.md` (cases, decisions X-1 to
  X-3, lots X-1 to X-4). Lot X-1 added the `python-calamine` dependency and
  measured its reading cost and behavior; results are in section "Lot X-1" of
  that page. No product behavior changes yet.

## 2026-10-01 (external test root)

- Test, benchmark and screenshot evidence now lives in
  `D:\GIT\tabalyst.test\artifacts` (an `artifacts/pytest-043` folder in the
  checkout broke Obsidian). Moved the repository `artifacts/` tree and the old
  `D:\GIT.test` tree there; `AGENTS.md` and `architecture.md` updated. Some old
  folders could not be moved (access denied) and remain in `D:\GIT.test`.

## 2026-10-01 (version 0.5.1 prepared)

- Version 0.5.1 prepared, not tagged: `pyproject.toml`, release notes
  `docs/dev/releases/0.5.1.md`, `docs/en/about/releases.md`, version in the
  overviews and the install page. Demos regenerated. No JSON format change.
  Studio follow-up: the site rebuilds from the release tag.

## 2026-10-01 (--collection on report)

- `tabalyst report` gains `--collection`, with the semantics of `scan`: it
  outranks the Inspect file and the configuration; refused with `--scan`
  (`generate_reports(collections=...)`).
- Short form on both commands, resolved in `cli/terminal.py`
  (`collection_paths`): `data.items` is `$.data.items[]`, `[]` is implied.
  Config files and the Python API stay strict (absolute paths).
- When the selection is ambiguous, `tabalyst inspect` prints one ready-to-run
  `tabalyst report FILE --collection '<path>'` per eligible collection.
- `tabalyst-studio`: the CLI reference and the Inspect/Report pages changed.

## 2026-10-01 (report theme modes)

- The report theme button now cycles auto (system preference, the new default),
  light and dark, with one icon per mode. `data-theme` stays the resolved theme;
  `data-theme-mode` holds the choice. The stored `tabalyst-theme` value is
  `light` or `dark`; auto removes it. Demos regenerated.
- `tabalyst-studio` (docs site): new menu and labels, redirects from the old
  URLs, EN | FR switch, auto/light/dark icon button, footer modelled on
  tabalyst.com, French banner. The tabalyst.com demo stays dark.

## 2026-10-01 (documentation menu restructure)

- Moved `project/` to `about/` (`concepts`, `limitations`, `releases`,
  `contributing`), `report/history` to `reference/history` and
  `report/profile` to `report/json-profile`; links, `docs/README.md` and
  `AGENTS.md` updated.
- Shorter menu labels are the job of `tabalyst-studio` (`src/navigation.ts`);
  page titles stay complete (`Report JSON and JSONL files`, `Command line (CLI)`,
  `Python API`, `Contributing and issues`).
- Follow-up in `tabalyst-studio`: new menu (Overview, Get started, Report,
  Inspect, Scan, Sample, Reference, About Tabalyst, with an `Overview` entry for
  Report, Inspect and Scan), new slugs `/about/*`, `/reference/history/`,
  `/report/json-profile/`, and redirects from `/project/*`,
  `/reference/limitations/`, `/report/history/`, `/report/profile/`.

## 2026-10-01 (documentation overhaul)

- Reorganized `docs/en/` by tool, with URLs of the form `/tool/subject/`:
  `install`, `examples`, `report/`, `inspect/`, `scan/`, `sample/`,
  `reference/` and `project/`. Files were renamed with `git mv` and every
  relative link rewritten; the old `how-to/`, `tutorials/` and most `reference/`
  URLs are gone.
- New pages: `report/index`, `report/csv`, `inspect/index`, `scan/index`, `scan/cache`, `reference/index`
  (`tabalyst cache`, moved out of the scan guide), `examples`,
  `reference/cli`, `reference/python-api`, `project/concepts`, `report/profile`, `sample/index`,
  `project/release-notes` and `project/contributing`. `index.md` now starts with
  a goal-to-page table.
- English only during the beta: `docs/fr/` holds one page that points to
  docs.tabalyst.com; the 16 translated pages were removed. `AGENTS.md` and
  `docs/README.md` updated.
- `tabalyst-studio`: new menu (`src/navigation.ts`), no i18n, `llms.txt`,
  `llms-full.txt`, a Markdown twin of each page and `robots.txt`.
  Follow-ups: `tabalyst.com` links to
  `docs.tabalyst.com/fr/reference/configuration/` (French site) and `llms.txt`
  of tabalyst.com; the README links of PyPI's description change at the next
  release.

## 2026-10-01

- Prepared package version `0.5.0`, the first release with Tabalyst Inspect and
  JSONL support: `pyproject.toml`, the version assertions, the version shown in
  the installation, scan format and Inspect format pages (EN and FR), release
  notes `docs/dev/releases/0.5.0.md` and the public demos. No tag is created
  and nothing is published; the tag, `RELEASING.md` steps and the
  `tabalyst-studio` follow-up need the maintainer's approval.

- JSON Inspect, lot JI-10 (finalization): point-by-point conformity check of the
  specification (design inspect 16.5), with one test added (CA-07, a root array
  through inspect, edit and report) and no unmet requirement. On Windows the
  command line library expanded `*.json` and passed the `*-inspect.json` files
  as explicit paths, which were refused: `main()` now passes
  `windows_expand_args=False`, so Tabalyst's own resolver expands wildcards and
  skips Inspect files (test added, workaround removed from the Inspect how-to).
  Documentation: `json-profile.md` said profile revision `9` (now `10`); the
  `errors.policy` bullet of `configuration.md` was cut off from its list (EN and
  FR); French versions added of `how-to/install.md`,
  `reference/execution-history.md` and `tutorials/first-report.md`, which
  `docs/fr/index.md` already linked. Demos regenerated. The target version
  number stays an open decision (E12).

- JSON Inspect, lot JI-9-fr (French translation): `docs/fr/` brought in line
  with `docs/en/` for the 13 pages of JI-9. New pages
  `how-to/inspect-json-files.md`, `reference/inspect-format.md` and
  `reference/inspect-format-changelog.md`; updated `index`, `scan-files`,
  `report-json-files`, `configuration`, `glossary` (new Inspect terms),
  `known-limitations`, `scan-format`, `scan-format-changelog`,
  `profile-format-changelog` and `json-profile`. The French pages lagged further
  than JI-9: they were also caught up on earlier English changes (profile
  revisions 6 to 9 and the `normalization`, `scan_details`, `limits` and
  `structure` sections, scan revisions 3 and 4, adaptive detection settings,
  `--workers`, the report structure section). Checked EN/FR parity on headings,
  code fences and code spans. Console output and messages stay in English, as
  the CLI prints them. Findings left for JI-10 in the English pages:
  `json-profile.md` still says revision `9` (the profile is at 10), and the
  `errors.policy` bullet of `configuration.md` follows a paragraph that splits
  the list. No code touched. Nothing committed.

- JSON Inspect, lot JI-9 (consolidated English documentation, README):
  new `docs/en/how-to/inspect-json-files.md`, `reference/inspect-format.md` and
  `reference/inspect-format-changelog.md` (revision 1, including
  `candidate_not_eligible_truncated`); updated `scan-files`,
  `report-json-files` (one dataset chosen by Inspect, no `$` dataset, JSONL
  policies), `configuration` (layers with the Inspect file, `json.collections`
  `null`), `glossary`, `known-limitations`, `scan-format`, `json-profile`,
  `index`, both format changelogs and `README.md`, which now announces
  `tabalyst inspect` and JSONL. Every command and message of the new pages was
  run against the real CLI on the `orders.json` and `web-events.jsonl` demos.
  Finding left as is: on Windows the command line library expands `*.json`
  before Tabalyst, so `tabalyst inspect "*.json"` also passes `*-inspect.json`
  files and is refused (documented in the how-to and known limitations). French
  pages are JI-9-fr. Follow-up in `tabalyst-studio`: imported docs change, the
  site may now announce Inspect and JSONL. Suite: 1,990 passed, 10 skipped;
  `ruff` clean. Nothing committed.

- JSON Inspect, lot JI-8 (verification matrix, measurements, demo):
  the specification's minimal matrix is mapped to tests in `design.md` 16.4
  (checked: every referenced test exists); two cases that only had engine tests
  got command-level tests (`test_json_inspect_matrix.py`: several collections
  chosen with `--collection`, a JSONL source with nested objects and bad lines
  from the file to the report; `ENABLED_LOTS` adds `JI-8`). Measurements in
  the new `docs/dev/inspect/benchmarks.md` from new `benchmarks/run_baseline.py`
  tasks (`sha256`, `events`, `inspect`, `resolve-cold`, `resolve-warm`,
  `report-cold`, `report-reuse`, `jsonl-parse-hook`, `jsonl-parse-plain`) and
  JSONL output in `benchmarks/generate_data.py`: the full hash is 0.5% of a
  Scan, Inspect 8 to 12%, a report from a stored scan 0.3 to 0.7 s whatever the
  size; `RECORDS_OBSERVED` (1,000) confirmed; the duplicate-key hook costs 16 to
  20% of JSONL parse time on these records (accepted). Decided by the
  maintainer: `candidate_not_eligible` lists the first `MAX_INELIGIBLE_NOTES`
  (10) ineligible candidates, then one `candidate_not_eligible_truncated` entry
  with the count (new warning code; format revision unchanged, not published).
  New public demo `examples/input/web-events.jsonl` (300 fictional web events,
  nested objects, three bad lines excluded by the tolerant policy), its command
  in `examples/README.md`; the three other demos regenerated (timestamps only).
  Suite: 1,990 passed, 10 skipped; `ruff` clean; browser check of the
  `web-events` report at desktop and 375 px (no console error, no overflow).
  Public docs, README and site untouched (JI-9). Nothing committed.

- JSON Inspect, lot JI-7 (command, Scan and Report integration, Python API):
  `tabalyst inspect INPUT... [--config FILE]... [--reset-config] [--force]
  [--quiet] [--verbose] [--no-progress]` writes only the visible file; new
  `inspect_service.py` (`generate_inspections()`, plan before any reading, an
  unknown kind such as a CSV rejects the batch with exit 2) and `cli/inspect.py`;
  `persistence.save_inspection()` returns the document as written (the existing
  file's `config` kept, the warnings it added). `tabalyst.inspect()` (one source,
  raises) and `tabalyst.generate_inspections()` join the public API. `scan` and
  `report` on `.json`, `.jsonl` and `.ndjson` call `resolve_interpretation()` per
  source and `check_result()` on the in-memory result, before any write of scan,
  cache or report (`current_scan(check=...)`); a source with no decided
  collection is suspended with its candidates (exit 2). **Behavior change:** a
  scan with no `-o` or `-d` goes to the shared storage for every format, so JSON
  and JSONL reports reuse a fresh scan (identity: content, resolved
  configuration, engine version) and `scan x.json` no longer writes
  `x.scan.json`; the CLI no longer lists a `$` document dataset (DP-A), so the
  `orders.json` demo report has one dataset. Patterns skip `*-inspect.json` and an
  explicit path to an Inspect file is refused. Decisions of the maintainer on the
  review findings of lot JI-6: the automatic inspection is skipped when
  `--collection` or a `--config` collection already decides; the source hash
  computed to validate the cache is passed to `current_scan` and
  `compare_source`; the "cache not written" notice joins the suspension message.
  `report --scan` warns (never refuses) when the visible file beside the source
  asks for a configuration that differs from the document's. In a mixed batch
  `json.collections` of a `--config` file is ignored for JSONL sources and a
  command-line `--collection` fails the JSONL job alone. Inspect messages: "1
  line", "1 element". 26 contract tests of `test_json_inspect_cli.py` enabled
  (`ENABLED_LOTS` adds `JI-7`) plus 27 in `test_json_inspect_cli_services.py`;
  two existing tests updated for DP-A (`orders.json` report has one dataset;
  `[1, 2]` is not a collection). Demos regenerated; browser check of the
  `orders` report (single dataset, desktop and 375 px). Nothing committed.

- JSON Inspect, lot JI-6 (persistence and resolution, no command):
  `inspector/persistence.py` names the visible file (`<full name>-inspect.json`),
  reads it (`read_visible_inspect`: triple, kind and `config` validated, other
  zones read leniently, unknown keys and unsupported versions refused naming the
  file and the key) and writes it atomically (`write_inspection`: a first
  inspection writes the document; re-inspecting replaces every zone but `config`,
  kept as a value; `reset_config`, `force`; an invalid file is never replaced;
  `configured_path_not_found` and `source_name_mismatch` warnings). It also reads
  and writes the automatic cache `inspect.json` beside `scan.json`
  (`StorageLocation.shared_inspect_path`); a defective cache is absent, a failed
  write is a notice. `inspector/resolution.py` resolves the effective
  `ScanConfig` of a source by layers (defaults, detection, `--config`, visible
  file, command line), runs the automatic inspection when nothing is stored,
  suspends with the candidates listed when no collection is decided, and
  `check_result` refuses a visible path that no longer exists and notes a source
  that changed since the file was written. Design amendment:
  `detection.scope.discovery_max_depth` is recorded and a cache made at another
  depth is rebuilt (format revision 1, unpublished). `scan_reuse.file_sha256` is
  public. 66 contract tests enabled (`ENABLED_LOTS` adds `JI-6`) plus 18 in
  `test_json_inspect_persistence_services.py`. Demos regenerated; nothing
  committed.

## 2026-09-30

- JSON Inspect, lot JI-5 (Inspect engine, no command): new package
  `tabalyst.inspector`. `models.py` holds `InspectDocument` (the fixed zones of
  design 4.1; optional keys absent, not `null`) and the editable `InspectConfig`
  (validation without coercion, `to_scan_layer()`); `json_inspect.inspect_source()`
  reads a `.json`, `.jsonl` or `.ndjson` source in one event pass, hashes it,
  finds the candidate collections (root array, or arrays reachable through
  object keys up to `json.discovery_max_depth`), counts elements and element
  types exactly, observes the structure of the first records within bounded
  memory, applies the selection rule (root array, only eligible candidate,
  dominant candidate, ambiguity, truncated list, no collection), writes the
  warnings and the proposed `config`, and writes nothing. JSONL lines are
  counted and located, never fatal. To share the same refusals with Scan, the
  event source of `JsonReader` became `JsonEvents` and the line classifier of
  `JsonlReader` became `JsonlLines`, with no change of behavior (the Scan suite
  is untouched); `byte_progress` moved to `progress.py`. Parameters measured
  before being fixed and decided by the maintainer: `RECORDS_OBSERVED` 1,000,
  `FIELDS_OBSERVED` 1,000, `MAX_CANDIDATES` 100, `DOMINANCE_RATIO` 10 (tables in
  inspect design 15, with the result of the rule at gate G2). Inspect costs
  1.2 to 1.6 times a bare event pass and about a tenth of a Scan, with 3 MB of
  memory. 77 contract tests enabled (`ENABLED_LOTS` adds `JI-5`) plus 35 in
  `test_json_inspect_engine.py`. Demos regenerated; nothing committed.

- JSON Inspect, lot JI-4 (JSONL reader and error policy): files ending in
  `.jsonl` or `.ndjson` (any letter case) are read as one dataset `$[]` by the new
  `scanner/readers/jsonl_reader.py`; `source_format_of` returns `jsonl`. Each line
  is parsed with `json.loads` (`Decimal` decimals, `NaN` rejected, a hook marks
  duplicate keys) and walked into the observations of a JSON array element, with
  the flatten limit, `limits.max_depth` and `limits.max_record_observations`.
  Lines split on LF only; BOM, CRLF, a last line without a break and blank lines
  follow the design; invalid UTF-8 and an empty source are fatal. Excluded lines
  (`jsonl_invalid_line`, `jsonl_record_not_object`, `jsonl_line_too_long`, plus
  the existing duplicate-key and too-large codes) are counted and located by
  physical line under the default `tolerant` policy; `strict` stops at the first,
  naming its line. New `limits.max_line_bytes`, fixed by measurement (16 MiB
  default, 256 MiB cap; table in inspect design 15). Shared helpers moved to
  `readers/json_common.py`. `report`, `service` and project staging route JSONL
  like JSON (no shared scan cache until JI-7); `report_name` gives
  `.report.html`; the profile accepts `source.format` `jsonl`, the report counts
  excluded lines in `excluded_records` and presents the dataset as records.
  Documentation, changelogs (Scan revision 5, profile revision 10) and designs
  updated. 48 contract tests enabled (`ENABLED_LOTS` adds `JI-4`) plus 21 in
  `test_json_inspect_jsonl_services.py` and a DuckDB staging parity test. Demos
  regenerated; nothing committed.

- JSON Inspect, lot JI-3 (JSON reader, flatten and complex columns): the JSON
  reader applies `json.flatten`: a container whose path reaches `max_depth`
  segments (`enabled: false` is 1) is observed whole, with its array length,
  and its children are not observed, not counted as truncated and not warned of
  (distinct from `limits.max_depth`); content below the limit is not checked for
  duplicate keys. `format_relative(path, separator)` and
  `parse_path(text, *, separator)` join field names with `flatten.separator`;
  absolute paths always use `.`. The report shows a container kept whole as a
  column with `inferred_type` `complex` (profile revision 10, completed; no
  change without a flatten limit). 36 contract tests enabled
  (`ENABLED_LOTS = {"JI-2", "JI-3"}`) plus 11 in
  `test_json_inspect_flatten_report.py`. Demos regenerated; nothing committed.
  The JSONL reader is untouched (JI-4).

- JSON Inspect, lot JI-2 (configuration and Scan identity): `ScanConfig` gains
  `json.flatten` (`enabled`, `separator`, `max_depth`) and `json.arrays`
  (`mode`, `preserve` only), with the validation of the design; `errors.policy`
  is nullable and `resolve_config_defaults()` resolves it by source format and
  normalizes unused flatten settings; collection paths are stored canonically.
  `scan()` records the resolved configuration. New `scanner/identity.py`:
  `ScanIdentity`, `scan_identity()`, `expected_identity()`, `source_format_of()`.
  `compare_source()` always compares the SHA-256 of a present source (DP-D) and
  returns it; `current_scan()` reuses a scan only when source hash, resolved
  configuration hash and engine version are all equal; project freshness and
  sessions compare the engine version (`engine_version_changed` warning,
  blocking `require_current` only); `report --scan` warns, and still reports,
  for a document of another engine version. Scan format revision 5 and profile
  revision 10 (changelogs, O12 and section 15 of the Scan design amended). The
  project tests that compared a recorded configuration now compare its resolved
  form. `json.flatten` and `json.arrays` were recorded and hashed only until lot
  JI-3. Demos regenerated. 63 contract tests of
  `tests/inspect/` enabled (`ENABLED_LOTS = {"JI-2"}`) plus 8 on where the
  identity applies; nothing committed.

- JSON Inspect, lot JI-1 (design only; gate G1 passed): wrote
  `docs/dev/inspect/design.md`, the contract of the Inspect file (zones,
  `config` keys and defaults, projection onto `ScanConfig`), path syntax with a
  configurable separator, flatten depth, candidate and selection rule, JSONL
  rules and diagnostics, Scan identity (source SHA-256, configuration hash,
  engine version), configuration layers, visible file and cache, and the
  mapping of every acceptance criterion to a test. The design separates the
  Inspect shell from the JSON kind, since other kinds will follow. No numeric
  parameter is fixed: the observation bounds, the dominance ratio and the JSONL
  line limit each have a measurement protocol in the design. Added
  `tests/inspect/`, 316 contract tests gated by `ENABLED_LOTS` (all skipped
  today) and registered the `inspect_lot` marker. With the lots JI-2 and JI-3
  enabled temporarily, the 41 tests that describe behavior Scan already has
  pass and the 58 that need new code fail for that reason. No production code,
  no format change, no demo output change; nothing committed.

- Prepared package version `0.4.4` after the `v0.4.4` release workflow rejected
  a tag pointing to a commit that still declared `0.4.3`. Updated version
  assertions, format examples, release notes and public demos. The existing
  tag must be moved to the version-preparation commit before the workflow can
  build the intended release; no publication is implied by these source edits.

## 2026-09-29

- Measured the 0.4.2-to-0.4.3 scan regression on 20,000 synthetic CSV rows and
  20 fields (Windows, Python 3.12, one worker): standalone Scan took 1.23 s;
  staging Scan plus DuckDB took 9.47 s, including 4.47 s in Scan with the
  database observation sink and 1.79 s reopening/validating the database.
  The default CSV Scan/Report path now stores and reuses only `scan.json` in a
  source-keyed local location. Existing DuckDB project generations remain
  untouched and the private project API remains available. This changes
  storage behavior, not the experimental Scan/profile JSON formats. The
  Tabalyst Studio follow-up is to update the documented default scan location
  and remove claims that ordinary scans build a DuckDB project. The new
  command took 1.52 s on the same file; a report reusing that scan took 0.57 s.
  Validation: 1,545 tests passed / 9 skipped before the final regression test;
  69 focused tests passed afterward, Ruff passed, and all three demos were
  regenerated. A process-termination test failed in a later suite interrupted
  by a long host pause; it passed alone and in the 69-test focused run.

- Added opt-in `report --details` for standalone column HTML reports under
  `<report-stem>/`, with source-order numbered slugs, links from the main
  Columns table, and the same
  sidebar/panel design. Each page shows stored values with counts and all
  detected formats in Overview, then the column's analyses, sample and limits.
  Sensitive values remain subject to the profile's exposure setting. The
  default report omits column pages; a forced plain rerun removes generated
  pages while preserving unrelated files. The `insurance-customers` demo was
  regenerated with `--details` for review. Studio follow-up:
  refresh the copied insurance demo and describe the column pages after release.

- Reduced per-push storage platform CI from 12 OS/Python combinations to
  Windows and macOS on Python 3.12. The full test suite still runs on Ubuntu
  with Python 3.11-3.14, including all storage tests. This keeps cross-platform
  storage coverage while avoiding duplicate Linux and interpreter runs.

- Aligned French documentation's beta-status references and scan version
  example with the 0.4.3 English sources. Other French format content remains
  behind the English source and needs a separate translation pass.

- Prepared version `0.4.3` as the first beta: updated package metadata, English
  public documentation and version assertions. The documentation site now
  displays the beta status and groups English navigation by Report, Scan and
  Sample; the French page navigation was left unchanged, while beta status
  references in French source pages were aligned separately.
  The experimental JSON format identifiers and revisions remain unchanged.
  Validation: 1,536 tests passed / 9 skipped, Ruff and both documentation
  builds passed. All three public demos were regenerated for `0.4.3`.

- Fixed CI workflow YAML parsing by quoting the DuckDB binary-wheel install
  command, whose `:all:` option otherwise made the `run` value invalid.

- Connected the CSV `scan` and `report` commands to project generations.
  Default Scan writes generation-bound `scan.json`; Report verifies committed
  artifact hashes, source freshness and requested Scan settings, reuses a
  current scan or publishes a replacement. Superseded generations and owned
  query caches are removed under exclusive maintenance ownership; active
  readers keep the old generation with a warning. Added `tabalyst cache info`
  and `tabalyst cache clean`, globally or for one source, over owned disposable
  query caches. Explicit `scan -o/-d` and `report --scan` remain standalone.
  Public English/French docs and tests were updated. Studio needs to refresh
  CLI copy and the insurance demo after these public changes. Validation:
  1,536 tests passed / 9 skipped in the full suite, then 98 focused tests
  passed / 7 skipped after the cache lookup refinement; Ruff and diff
  whitespace checks passed. All three demos were regenerated and their nine
  tracked outputs restored byte-for-byte because only volatile timestamps,
  durations and cumulative execution entries changed.

- Accepted S18 and implemented the first private reopening adapter (Scan lot
  7.storage-g1). Fresh projects open with a verified current session; stale,
  missing or failed-check projects return a decision requiring an explicit
  snapshot or rescan. Config mismatch remains a blocker until the inspected
  complete replacement config is supplied; generation/source races fail
  closed. An integration test with a live old reader found that F2's preflight
  opened the same DuckDB file with a different private spill directory. F2 now
  checks manifest artifact hashes and the recorded Scan/config without a
  second old-database connection; f1 still fully verifies query-session opens.
  Older pinned readers and cursors continue through an explicit rescan. No
  CLI/API/HTTP/UI, demo, studio, commit or push change. D07 and the 10,000-key
  cap remain unchanged. Review follow-up: current opening now carries the
  inspected requested ScanConfig into its live session, preserving its
  fingerprint on refresh. Validation: 1,532 tests passed / 9 skipped, including
  live old-reader and source-binding races; Ruff and diff whitespace checks
  passed. Demo regeneration remains deferred at the maintainer's request.

- Proposed S18 as the next product reopening decision (Scan lot 7.storage-g),
  design only. A verified fresh project would open with `require_current`;
  stale/missing/failed source checks would present the assessment and require
  an explicit snapshot or targeted rescan choice. Configuration mismatch,
  legacy and integrity failures remain separate blockers. Concurrent changes
  trigger reinspection; a post-commit open failure must report the generation
  already published. The proposal is pending maintainer review before any
  adapter or public interface. D07, history comparison and automatic D03
  policies remain deferred. No demo, code, studio, commit or push change.

- Implemented Scan lot 7.storage-f2 privately: explicit project-targeted
  rescan checks the selected generation and source binding under writer
  ownership, verifies the old generation, and bypasses source-index selection.
  It retains recorded ScanConfig by default or accepts a complete replacement.
  New generations default to 10,000 stored raw typed analyzable keys per field;
  a lower bound is opt-in. Publication preserves project identity and older
  generations, then releases writer ownership before a new verified session
  opens at the exact returned generation. Post-commit opening failures carry
  the committed result; existing d2 warnings and unknown-outcome errors are
  retained. Added F2 cases to storage-platform CI. D07, public project
  interfaces, automatic rescan and product D04 defaults remain deferred.
  Progress reports completion only after verified reopening; post-commit
  callback failures still identify the committed generation. Validation:
  20 focused f2 tests and the full suite (1,516 passed / 9 skipped) pass; Ruff
  and diff whitespace checks pass.
  At the end of the lot, all three public demos were regenerated and their nine
  pre-existing outputs restored byte-for-byte. No studio change, commit or push.

- Implemented private pinned inspection/open sessions (Scan lot 7.storage-f1),
  accepting S17's read-only boundary after the maintainer requested f1.
  `_session.py` verifies the selected generation before immutable source/config
  readiness assessment. `require_current` refuses stale/missing/failed checks;
  explicit `snapshot` carries structured warnings. Exact full-config mismatch
  blocks both intents. Optional expected-generation preconditions reject an
  intervening publication; explicit refresh compares the original pinned Scan.
  Exposure-aware record/value queries retain generation/cursor scope, and
  outstanding materializations close with their session. Inspection/opening
  never scans, repairs an index or upgrades legacy projects. Low-level
  `open_generation()`, public exports, persisted formats and the 10,000-value
  cap are unchanged. f2, product D04 defaults, D07 and automatic D03 policies
  remain deferred. Added session tests to storage-platform CI without claiming
  remote-platform results. No studio follow-up is needed for this private
  boundary; the public demos were regenerated and all nine initial output files
  restored byte-for-byte, preserving the existing working tree.
  Validation: full suite 1,496 passed / 9 skipped; 31 focused session tests
  passed again after strengthening exclusive-lock release checks. Ruff and diff
  whitespace checks passed. Test evidence
  lives outside the checkout in the OS temporary directory, as supported by
  architecture.md; no repository `artifacts/`, branch, commit, tag or push.

- Designed the next private project reopening boundary (Scan lot 7.storage-f,
  D04/S17), without implementation. Proposed inspection/open sessions bind
  one verified generation, point-in-time source assessment and effective
  recorded/explicit configuration. Private `require_current` refuses stale,
  missing or failed checks; explicit `snapshot` permits historical-generation
  queries with warnings, never an integrity bypass or current-source claim.
  A separate f2 rescan must target the selected project and compare its
  generation under writer ownership: current source/index lookup may select
  another project sharing that path. S17 remains Proposed before f1, which
  is Next; product defaults/public exposure, D07 and automatic D03 policies
  stay deferred. The 10,000-value cap and external test-artifact location
  remain unchanged. No code, branch, commit, tag or public format change.
  Validation: diff whitespace checks passed; all three demos regenerated and
  their nine initial outputs restored byte-for-byte. Hash checks preserved
  existing changes outside the three design/plan/history documents. No local
  `artifacts/` directory created; Python tests not rerun for design-only work.

- Implemented Tabalyst Scan lot 7.storage-e: private metadata-only query-cache
  inventory/dry-run and explicit cleanup of unchanged planned candidates
  under exclusive workspace maintenance/writer ownership. New query caches
  have synchronized ULID/path-bound ownership markers. Unknown/unmarked
  contents, invalid markers, symlinks/reparse points and hardlinks are
  preserved; regular known files are removed individually, marker last.
  Per-target outcomes report removed/skipped/error states and partial removed
  logical bytes; ordinary final-directory failures restore retry metadata.
  Normal query teardown also validates ownership/contents and unchanged
  empty parent identities. Cleanup never opens the source or changes project
  storage. Rebuilt pages/cursors retain exposure and storage-limit semantics.
  D03 is only partly implemented: automatic TTL/quotas, generation retention
  and public commands remain deferred; D07 and the 10,000 raw typed analyzable
  values per column cap stay unchanged. The storage CI matrix includes the
  new tests; remote OS/Python runs remain unverified. No public format,
  CLI/report behavior, studio follow-up, branch or commit.
  Validation: full suite 1,465 passed, 9 skipped, including 48 new cache tests
  (41 passed; seven symlink fixtures require privileges unavailable locally).
  Native Windows junction and reparse-attribute cases passed. Ruff and diff
  whitespace checks passed; browser test harness syntax checked with Node.
  All three demos regenerated and their nine existing files restored exactly;
  hash checks preserved existing changes outside the intended edit scope.
  Manual review used in place of an unavailable `/code-review` command.
  Final cache/query/generation verification after parent-identity hardening:
  213 passed, 7 skipped.
- At the maintainer's request, moved the existing local `artifacts/` tree to
  `D:\GIT\tabalyst.test\artifacts`, outside the Obsidian-watched checkout.
  Subsequent pytest runs use fresh external base directories and disable
  pytest's cache provider. Browser screenshots now honor
  `TABALYST_ARTIFACTS_DIR`, defaulting to the OS temporary directory rather
  than recreating `artifacts/` in the repository. Developer instructions
  explain external pytest/benchmark paths; no local artifacts directory was
  recreated.

- Framed the proposed next Scan lot, 7.storage-e, before implementation:
  explicit private inventory/dry-run/cleanup of owned query caches abandoned
  after process termination. The plan requires an ownership marker contract,
  exclusive maintenance/writer locking, execution-time revalidation,
  preservation of unknown contents and all persistent project artifacts,
  and failure/concurrency/source-free rebuild tests. This addresses a narrow
  part of D03; automatic TTL/quotas, old-generation retention/deletion and
  public cache/project interfaces remain undecided. The 10,000 raw typed
  analyzable-value storage cap and complete record memberships stay intact;
  D07 remains deferred. No implementation or cleanup ran, and no branch,
  commit, tag or public behavior changed.
  Validation: diff whitespace checks passed; all three demos regenerated
  successfully, then their nine pre-existing outputs were restored byte for
  byte. Hash checks preserved all 214 other existing changed/untracked files.
  Python tests were not rerun for this documentation-only framing.

- Private generation queries and budgets (Tabalyst Scan lot 7.storage-d3):
  keyset pages for complete missing/empty/duplicate record memberships,
  frequencies, normalization groups and independently paged variants.
  Scope identifies project/workspace/generation, dataset/field, configuration,
  Scan/structural limits, exposure and semantic versions. Cursors reject a
  different generation/query and survive an identical cache rebuild or an
  old pinned reader. Shared classification/normalization/exposure precede
  ranking, including masked collisions and hidden lists.
  The maintainer explicitly amended retention to cap values actually kept
  in `project.duckdb`: new logical DB revision 2 keeps the first 10,000 raw
  typed analyzable keys per field and counts their later occurrences. It
  discards other payloads after bounded batches and reports retained/omitted
  populations; saturated frequency/variant pages are limited. Complete
  record facts/memberships persist; old DB revision 1 remains readable and
  Scan JSON/manifest formats are unchanged. Short private ingestion commits
  release catalog update/delete undo; d2's manifest is still the sole
  publication point. Reopen checks all retained data and memberships, but
  cannot reconstruct discarded cells or independently recompute their
  record digests. D07 richer attribution and exact JSON/row reconstruction
  remain deferred.
  Loader/readers/materializers use 256 MiB and 1 GiB of DuckDB-accounted
  spill per database instance. Quotas also use runtime SET, after detecting
  that pinned DuckDB's connect option alone could report an unenforced spill
  limit; zero disables spill entirely. Maintenance verification uses the
  reader policy too. Disposable query caches close/remove after failure;
  budgets do not promise process RSS or hard OS disk quotas. Real sort and
  value-query probes cover disabled/exhausted spill and memory failures.
  Repeated synthetic CSV/JSON/wide/deep/long-value measurements and the
  old+new+staging/cache disk composition are recorded in project-storage.md
  section 10.2, reproduced by `benchmarks/project_queries.py`. The final
  million-record CSV under enforced quotas builds first/rescan pairs in
  61.33/58.05 s, opens with full verification in 4.10 s, uses a 68.51 MiB DB,
  peaks at 432.40 MiB process RSS, 10.75 MiB sampled spill files and 138.51 MiB
  simultaneous project disk. The 10,000 retained id keys omit 980,000 value
  occurrences explicitly; all 500,000 duplicate references remain paginable.
  Resource evidence is local Windows/Python 3.12 only; remote OS CI and D08
  durability remain unverified. Validation: 1,424 passed, 2 skipped, including
  124 new query/storage-budget tests; Ruff and diff whitespace checks passed.
  The d2 termination test waits for Windows process death before closing its
  stdin barrier, avoiding a race with pending termination. The three demos
  were regenerated and all
  nine initial working-tree outputs restored byte-for-byte. All interfaces
  remain private; no public format/CLI/report change or studio follow-up,
  and no branch, commit or tag created.

## 2026-09-28

- Atomic project generations (Tabalyst Scan lot 7.storage-d2), continued at
  the maintainer's request: revision-2 manifests commit one immutable
  scan/database pair through a single replacement. OS-backed workspace
  writer locks cover every mutator; shared maintenance locks pin readers
  and block explicit quarantine until no reader/writer remains. First scans
  stay invisible before commit; rescans preserve identity and old generations.
  File synchronization precedes publication; POSIX directory fsync is
  implemented, Windows directory synchronization explicitly unsupported.
  The tested guarantee is local process-failure atomic visibility; power-loss
  durability, network filesystems and multi-host coordination remain D08.
  Read-only sessions validate manifest hashes and database bindings, with
  no fallback for corruption; freshness uses the pinned scan. Explicit
  revision-1 rebuild preserves identity/created_at and upgrades on success.
  Index updates follow commit and failures produce repair warnings; ambiguous
  replacement errors are classified from the manifest, preserving artifacts
  if the outcome is unknown. Explicit quarantine preserves unselected ULID
  directories and their contents; scans never clean up old generations.
  Service and SQL access remain private, with consumer query APIs in d3.
  Validation: 48 new tests include eleven injected pre-commit boundaries for
  first scans/rescans, subprocess termination before/after commit, lock
  owner termination, old readers, index failure, unknown outcome, corruption,
  source absence, legacy upgrade/failure and ownership-safe quarantine.
  Full suite: 1,300 passed, 2 skipped; Ruff passed. The 12-job OS/Python CI
  matrix includes generation tests; remote execution remains unverified.
  All three demos regenerated with the nine pre-existing output files
  restored byte-for-byte. No public format/CLI change or studio follow-up;
  no branch, commit or tag created. A fresh conversation is recommended for
  d3, with its handoff prompt in scan/plan.md.

- Private project database staging (Tabalyst Scan lot 7.storage-d1), after
  maintainer acceptance of c: pinned DuckDB 1.5.5 with physical target
  `v1.4.0`, explicit revision-1 schema, canonical path/native-value codec,
  bounded parameterized `on_record` ingestion, Scan document hash binding,
  complete missing/empty/duplicate record memberships and exhaustive
  validation before commit and after checkpoint/close/read-only reopen.
  The record digest helper is shared with Scan; its envelopes and sampled
  lists are unchanged. Cross-schema FK checks are explicit because DuckDB
  cannot declare them. Lots a/b and their scan-only service remain intact:
  no manifest, index, generation publication or default value-query API.
  D06 wheel/platform evidence and initial CSV/JSON, batching, spill, memory,
  hash/open measurements are recorded in project-storage.md section 10.1;
  `benchmarks/project_storage.py` reproduces them. A 12-job storage CI matrix
  covers Windows/Linux/macOS and Python 3.11-3.14; only Windows/Python 3.12
  was executed locally. The generated physical database also reopened in an
  isolated DuckDB 1.4.2 reader. Low-memory failure is explicit; d3 retains
  large-scale and old/new-generation measurements and exposure-aware
  queries. d2 must provide atomic publication/recovery before any DB use.
  Validation: 87 new tests cover both JSON backends, raw representations,
  structures/limits/configuration, missing/empty/duplicate parity, more than
  12,438 affected records, disabled duplicates/exposure, corruption, reader/
  sink/finalization/serialization/source-mutation/memory failures and spill.
  Full suite: 1,252 passed, 2 skipped; Ruff and diff whitespace checks passed.
  All three demos were regenerated, then their nine original working-tree
  files restored byte-for-byte to preserve existing edits. No public format
  change or tabalyst-studio follow-up; no branch, commit or tag created.

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

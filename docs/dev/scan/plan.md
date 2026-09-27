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
| 5a-fr | French translation of the lot 5a documentation | Planned | Sonnet 5 | Low | `scan/phase-5-fr` |
| 5b | JSON sources and new sections in the report | Done | Opus 5.5 | Medium | `scan/phase-5` |
| 5c | Scan reuse, streaming duplicates, pandas removal | Planned | Sonnet 5 | High | `scan/phase-5` |
| 6 | Measure, set targets, optimize | Planned | Opus 5.5 | High | `scan/phase-6` |
| 7.x | Extensions, one lot each | Planned | See lot 7 | - | `scan/<topic>` |

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
- **Gate 5**, before removing the pandas engine in 5c.

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

### Lot 6: measure, set targets, optimize

- Scan benchmarks next to the baseline, including 10 million rows, wide files,
  long strings and deep JSON; targets decided with the maintainer (O19).
- Fast paths, adaptive detection with explicit `not_tested`, mergeable states
  as preparation for parallelism.

### Lot 7: extensions

One conversation per topic, each starting with a short design addition:
catalogue waves 2 to 5 and profiles (Sonnet 5, medium); Excel, XML, database
and API readers, exact quantiles, parallel execution and plugins (Opus 5.5,
high, for their design).

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
- Lot 1b, for lot 6: indicative measure, not a benchmark row: 200,000
  records of 25 MB of JSON (about 11 observations each) in about 2.5 s with
  about 1.3 MB of traced peak memory, compiled `ijson` backend, counters only.
